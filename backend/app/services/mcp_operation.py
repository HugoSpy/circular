"""Run an authorized MCP operation against a single business transaction."""
import json
import time
from collections.abc import Callable
from typing import TypeVar

from mcp.server.auth.middleware.auth_context import get_access_token
from pydantic import BaseModel

from backend.app.db.session import Database
from backend.app.repositories.workspace import WorkspaceRepository
from backend.app.services.auth import verifier
from backend.app.services.mcp_policy import row_scopes
from backend.app.services.scope import scoped_connection
from backend.app.services.workspace import DomainError, WorkspaceService

Result = TypeVar("Result", bound=BaseModel)


def principal(database: Database, required: set[str]):
    token = get_access_token()
    claims = token.claims if token else None
    if token is None or not required.issubset(token.scopes) or not claims:
        raise DomainError(403, "Autorisations MCP insuffisantes.")
    user_id, workspace_id = claims.get("user_id"), claims.get("workspace_id")
    if type(user_id) is not int or user_id <= 0 or type(workspace_id) is not int or workspace_id <= 0:
        raise DomainError(403, "Accès à Circular non autorisé.")
    return token, WorkspaceService(database, user_id, workspace_id)


def lock_target_project(repo: WorkspaceRepository, project_id: int, *, shared: bool = True) -> dict:
    repo.lock_project(project_id, shared=shared)
    if getattr(repo.connection, "dialect", "sqlite") == "postgresql":
        repo.connection.execute("SELECT user_id FROM project_members WHERE project_id = ? AND user_id = ? FOR KEY SHARE",
                                (project_id, repo.user_id)).fetchone()
    return WorkspaceService.require(repo.project(project_id), "Projet introuvable.")


def transact(database: Database, required: set[str], action: str, arguments: dict, key: str,
             result_type: type[Result], validate: Callable, write: Callable, *, lock_workspace: bool = False) -> Result:
    token, service = principal(database, required)
    user_id, workspace_id = service.user_id, service.workspace_id
    fingerprint = verifier(json.dumps([action, arguments], sort_keys=True))
    with scoped_connection(database, user_id, workspace_id, write=True, lock_workspace=lock_workspace) as connection:
        lock = " FOR UPDATE OF g" if database.dialect == "postgresql" else ""
        grant = connection.execute("""SELECT g.id, g.scope, g.family_scopes, g.access_expires_at, w.slug
            FROM mcp_connections g JOIN workspaces w ON w.id = g.workspace_id
            WHERE g.access_hash = ? AND g.client_id = ? AND g.user_id = ? AND g.workspace_id = ? AND g.resource = ?""" + lock,
            (verifier(token.token), token.client_id, user_id, workspace_id, str(token.resource))).fetchone()
        if not grant or grant["access_expires_at"] <= int(time.time()) or not required.issubset(row_scopes(grant)):
            raise DomainError(403, "Accès à Circular non autorisé.")
        repo = WorkspaceRepository(connection, user_id, workspace_id)
        target = validate(service, repo)
        prior = connection.execute("SELECT fingerprint, result FROM mcp_writes WHERE connection_id = ? AND request_key = ?",
                                   (grant["id"], key)).fetchone()
        if prior:
            if prior["fingerprint"] != fingerprint:
                raise DomainError(409, "Cette clé de relance a déjà été utilisée pour une autre écriture.")
            return result_type.model_validate_json(prior["result"])
        outcome = write(service, repo, target, grant["slug"])
        connection.execute("INSERT INTO mcp_writes (connection_id, request_key, fingerprint, result) VALUES (?, ?, ?, ?)",
                           (grant["id"], key, fingerprint, outcome.model_dump_json()))
        return outcome
