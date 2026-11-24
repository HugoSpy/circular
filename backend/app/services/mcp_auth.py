"""Circular's OAuth grants behind the MCP SDK's authorization endpoints."""
import re
import secrets
import time
from functools import wraps
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

from anyio import to_thread
from mcp.server.auth.provider import (
    AccessToken, AuthorizationCode, AuthorizationParams, AuthorizeError,
    RefreshToken, RegistrationError, TokenError, construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from backend.app.db.session import Database, timestamp
from backend.app.services.auth import verifier
from backend.app.services.mcp_tools import READ_SCOPE
from backend.app.services.spaces import SpacesService
from backend.app.services.workspace import DomainError

REQUEST_TTL = 600
CODE_TTL = 120
ACCESS_TTL = 900
REFRESH_TTL = 30 * 24 * 60 * 60
CHALLENGE = re.compile(r"[A-Za-z0-9_-]{43}")
CHATGPT_CALLBACK = re.compile(r"https://chatgpt\.com/(?:connector_platform_oauth_redirect|connector/oauth/[A-Za-z0-9_-]+)")
CLAUDE_CALLBACK = "https://claude.ai/api/mcp/auth_callback"


def threaded(method):
    """The SDK calls its provider asynchronously, while Circular's database is synchronous."""
    @wraps(method)
    async def execute(*args):
        return await to_thread.run_sync(method, *args)
    return execute


class CircularCode(AuthorizationCode):
    user_id: int
    workspace_id: int


class CircularMcpAuth:
    def __init__(self, database: Database, origin: str, extra_redirects: set[str]):
        self.database = database
        self.origin = origin
        self.resource = f"{origin}/mcp"
        self.extra_redirects = extra_redirects

    def client_name(self, metadata: OAuthClientInformationFull) -> str:
        redirects = {str(uri) for uri in metadata.redirect_uris or []}
        if redirects == {CLAUDE_CALLBACK}:
            return "Claude"
        if redirects and all(CHATGPT_CALLBACK.fullmatch(uri) for uri in redirects):
            return "ChatGPT"
        return "Client MCP"

    @threaded
    def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT metadata FROM mcp_clients WHERE id = ?", (client_id,)).fetchone()
        return OAuthClientInformationFull.model_validate_json(row["metadata"]) if row else None

    @threaded
    def register_client(self, client_info: OAuthClientInformationFull) -> None:
        redirects = [str(uri) for uri in client_info.redirect_uris or []]
        if not redirects or len(redirects) > 5 or any(not self.allowed_redirect(uri) for uri in redirects):
            raise RegistrationError("invalid_redirect_uri", "Adresse de retour MCP non autorisée.")
        with self.database.connect(write=True) as connection:
            connection.execute("INSERT INTO mcp_clients VALUES (?, ?)", (client_info.client_id, client_info.model_dump_json()))

    def allowed_redirect(self, uri: str) -> bool:
        if uri == CLAUDE_CALLBACK or CHATGPT_CALLBACK.fullmatch(uri):
            return True
        parsed = urlsplit(uri)
        return bool(uri in self.extra_redirects and not (parsed.username or parsed.password or parsed.fragment)
                    and (parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"})))

    @threaded
    def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        if not self.allowed_redirect(str(params.redirect_uri)) or not CHALLENGE.fullmatch(params.code_challenge):
            raise AuthorizeError("invalid_request", "Demande d’autorisation MCP invalide.")
        if params.resource not in {None, self.resource}:
            raise AuthorizeError("invalid_request", "Ressource MCP invalide.")
        if set(params.scopes or [READ_SCOPE]) != {READ_SCOPE}:
            raise AuthorizeError("invalid_scope", "Cet accès permet la lecture des projets et tickets.")
        params = params.model_copy(update={"resource": self.resource})
        request_id = secrets.token_urlsafe(32)
        now = int(time.time())
        with self.database.connect(write=True) as connection:
            connection.execute("DELETE FROM mcp_authorizations WHERE expires_at <= ?", (now,))
            connection.execute("DELETE FROM mcp_codes WHERE expires_at <= ?", (now,))
            connection.execute("INSERT INTO mcp_authorizations VALUES (?, ?, ?, ?)",
                               (verifier(request_id), client.client_id, params.model_dump_json(), now + REQUEST_TTL))
        return f"{self.origin}/#{urlencode({'mcp': request_id})}"

    def pending(self, request_id: str, user_id: int) -> dict:
        with self.database.connect() as connection:
            row = connection.execute("""SELECT c.metadata FROM mcp_authorizations a
                JOIN mcp_clients c ON c.id = a.client_id WHERE a.request_hash = ? AND a.expires_at > ?""",
                (verifier(request_id), int(time.time()))).fetchone()
        if row is None:
            raise DomainError(404, "La demande d’autorisation a expiré.")
        return {"client": self.client_name(OAuthClientInformationFull.model_validate_json(row["metadata"])),
                "workspaces": [{"id": row["id"], "name": row["name"]} for row in SpacesService(self.database, user_id).workspaces()]}

    def decide(self, request_id: str, user_id: int, workspace_id: int | None) -> str:
        now = int(time.time())
        with self.database.connect(write=True) as connection:
            if workspace_id is not None:
                lock = " FOR KEY SHARE" if self.database.dialect == "postgresql" else ""
                member = connection.execute("SELECT 1 FROM workspace_members WHERE workspace_id = ? AND user_id = ?" + lock,
                                            (workspace_id, user_id)).fetchone()
                if member is None:
                    raise DomainError(404, "Espace introuvable.")
            row = connection.execute("""DELETE FROM mcp_authorizations WHERE request_hash = ? AND expires_at > ?
                RETURNING client_id, parameters""", (verifier(request_id), now)).fetchone()
            if row is None:
                raise DomainError(404, "La demande d’autorisation a expiré.")
            params = AuthorizationParams.model_validate_json(row["parameters"])
            if params.resource != self.resource or not self.allowed_redirect(str(params.redirect_uri)):
                raise DomainError(404, "La demande d’autorisation a expiré.")
            if workspace_id is None:
                return construct_redirect_uri(str(params.redirect_uri), error="access_denied", state=params.state)
            code = secrets.token_urlsafe(32)
            connection.execute("INSERT INTO mcp_codes VALUES (?, ?, ?, ?, ?, ?)",
                               (verifier(code), row["client_id"], user_id, workspace_id, row["parameters"], now + CODE_TTL))
            return construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state)

    @threaded
    def load_authorization_code(self, client: OAuthClientInformationFull, authorization_code: str) -> CircularCode | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM mcp_codes WHERE code_hash = ? AND client_id = ? AND expires_at > ?",
                                     (verifier(authorization_code), client.client_id, int(time.time()))).fetchone()
        if not row:
            return None
        params = AuthorizationParams.model_validate_json(row["parameters"])
        if params.resource != self.resource or not self.allowed_redirect(str(params.redirect_uri)):
            return None
        return CircularCode(code=authorization_code, scopes=[READ_SCOPE], expires_at=row["expires_at"],
                            client_id=row["client_id"], redirect_uri=params.redirect_uri,
                            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
                            code_challenge=params.code_challenge, resource=self.resource,
                            user_id=row["user_id"], workspace_id=row["workspace_id"])

    @staticmethod
    def new_tokens() -> OAuthToken:
        return OAuthToken(access_token=secrets.token_urlsafe(32), refresh_token=secrets.token_urlsafe(32),
                          expires_in=ACCESS_TTL, scope=READ_SCOPE)

    @threaded
    def exchange_authorization_code(self, client: OAuthClientInformationFull, authorization_code: CircularCode) -> OAuthToken:
        now = int(time.time())
        tokens = self.new_tokens()
        with self.database.connect(write=True) as connection:
            lock = " FOR KEY SHARE" if self.database.dialect == "postgresql" else ""
            if connection.execute("SELECT 1 FROM workspace_members WHERE workspace_id = ? AND user_id = ?" + lock,
                                  (authorization_code.workspace_id, authorization_code.user_id)).fetchone() is None:
                raise TokenError("invalid_grant")
            row = connection.execute("""DELETE FROM mcp_codes WHERE code_hash = ? AND client_id = ? AND expires_at > ?
                RETURNING user_id, workspace_id""", (verifier(authorization_code.code), client.client_id, now)).fetchone()
            if row is None:
                raise TokenError("invalid_grant")
            connection.execute("INSERT INTO mcp_connections VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                               (str(uuid4()), client.client_id, row["user_id"], row["workspace_id"], self.resource,
                                verifier(tokens.access_token), verifier(tokens.refresh_token), now + ACCESS_TTL,
                                now + REFRESH_TTL, timestamp()))
        return tokens

    @threaded
    def load_access_token(self, token: str) -> AccessToken | None:
        with self.database.connect() as connection:
            row = connection.execute("""SELECT client_id, user_id, workspace_id, access_expires_at FROM mcp_connections
                WHERE access_hash = ? AND resource = ? AND access_expires_at > ?""",
                (verifier(token), self.resource, int(time.time()))).fetchone()
        if not row:
            return None
        return AccessToken(token=token, client_id=row["client_id"], scopes=[READ_SCOPE], expires_at=row["access_expires_at"],
                           resource=self.resource, subject=str(row["user_id"]),
                           claims={"user_id": row["user_id"], "workspace_id": row["workspace_id"]})

    @threaded
    def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        with self.database.connect() as connection:
            row = connection.execute("""SELECT refresh_expires_at FROM mcp_connections WHERE refresh_hash = ?
                AND client_id = ? AND resource = ? AND refresh_expires_at > ?""",
                (verifier(refresh_token), client.client_id, self.resource, int(time.time()))).fetchone()
        if not row:
            return None
        return RefreshToken(token=refresh_token, client_id=client.client_id, scopes=[READ_SCOPE],
                            expires_at=row["refresh_expires_at"], resource=self.resource)

    @threaded
    def exchange_refresh_token(self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]) -> OAuthToken:
        if set(scopes) != {READ_SCOPE}:
            raise TokenError("invalid_scope")
        now = int(time.time())
        if not refresh_token.expires_at or refresh_token.expires_at <= now:
            raise TokenError("invalid_grant")
        expires_in = min(ACCESS_TTL, refresh_token.expires_at - now)
        tokens = self.new_tokens().model_copy(update={"expires_in": expires_in})
        with self.database.connect(write=True) as connection:
            updated = connection.execute("""UPDATE mcp_connections SET access_hash = ?, refresh_hash = ?, access_expires_at = ?
                WHERE refresh_hash = ? AND client_id = ? AND resource = ? AND refresh_expires_at > ?""",
                (verifier(tokens.access_token), verifier(tokens.refresh_token), now + expires_in,
                 verifier(refresh_token.token), client.client_id, self.resource, now))
            if updated.rowcount != 1:
                raise TokenError("invalid_grant")
        return tokens

    @threaded
    def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        token_hash = verifier(token.token)
        with self.database.connect(write=True) as connection:
            connection.execute("DELETE FROM mcp_connections WHERE client_id = ? AND (access_hash = ? OR refresh_hash = ?)",
                               (token.client_id, token_hash, token_hash))

    def connections(self, user_id: int) -> list[dict]:
        with self.database.connect() as connection:
            rows = connection.execute("""SELECT g.id, g.created_at, w.name AS workspace, c.metadata
                FROM mcp_connections g JOIN mcp_clients c ON c.id = g.client_id JOIN workspaces w ON w.id = g.workspace_id
                WHERE g.user_id = ? AND g.resource = ? AND g.refresh_expires_at > ? ORDER BY g.created_at DESC, g.id""",
                (user_id, self.resource, int(time.time()))).fetchall()
        return [{"id": row["id"], "workspace": row["workspace"], "createdAt": row["created_at"],
                 "client": self.client_name(OAuthClientInformationFull.model_validate_json(row["metadata"]))} for row in rows]

    def revoke_connection(self, user_id: int, connection_id: str) -> None:
        with self.database.connect(write=True) as connection:
            connection.execute("DELETE FROM mcp_connections WHERE id = ? AND user_id = ?", (connection_id, user_id))
