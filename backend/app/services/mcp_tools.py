"""Circular tools for an explicitly authorized workspace."""
import json
import time
from typing import Annotated, Generic, TypeVar
from urllib.parse import urlencode

from anyio import to_thread
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field, StringConstraints

from backend.app.db.session import Database
from backend.app.repositories.workspace import WorkspaceRepository
from backend.app.schemas.workspace import CommentCreate, IssueCreate, MAX_ID, PositiveId, Priority, ProjectStatus, Status, Title
from backend.app.services.auth import verifier
from backend.app.services.scope import scoped_connection
from backend.app.services.workspace import DomainError, WorkspaceService


READ_SCOPE = "circular:read"
WRITE_SCOPE = "circular:write"
WRITE_SCOPES = f"{READ_SCOPE} {WRITE_SCOPE}"
WRITE_TOOLS = frozenset({"create_ticket", "add_comment"})
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
ADDITIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WriteKey = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{16,100}$")]
Limit = Annotated[int, Field(strict=True, ge=1, le=50)]
Cursor = Annotated[int, Field(strict=True, ge=0, le=MAX_ID)]
Query = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Item = TypeVar("Item")


class ProjectSummary(BaseModel):
    id: int
    name: str
    key: str
    status: ProjectStatus


class TicketSummary(BaseModel):
    id: int
    identifier: str
    title: str
    projectId: int
    status: Status
    priority: Priority
    dueDate: str | None


class TicketDetail(TicketSummary):
    description: str
    updatedAt: str


class CreatedTicket(BaseModel):
    id: int
    identifier: str
    projectId: int
    url: str


class AddedComment(BaseModel):
    id: int
    ticketId: int
    url: str


class Page(BaseModel, Generic[Item]):
    items: list[Item]
    nextCursor: int | None


def oauth_metadata(scopes: str) -> dict:
    return {"securitySchemes": [{"type": "oauth2", "scopes": scopes.split()}]}


def register_tools(server: FastMCP, database: Database, origin: str) -> None:
    def workspace() -> WorkspaceService:
        token = get_access_token()
        if token is None or READ_SCOPE not in token.scopes or token.claims is None:
            raise ToolError("Accès à Circular non autorisé.")
        user_id = token.claims.get("user_id")
        workspace_id = token.claims.get("workspace_id")
        if type(user_id) is not int or user_id <= 0 or type(workspace_id) is not int or workspace_id <= 0:
            raise ToolError("Accès à Circular non autorisé.")
        return WorkspaceService(database, user_id, workspace_id)

    @server.tool(title="Lister les projets", annotations=READ_ONLY, meta=oauth_metadata(READ_SCOPE))
    async def list_projects(limit: Limit = 20, cursor: Cursor = 0) -> Page[ProjectSummary]:
        """Liste les projets accessibles dans l’espace autorisé. Pour continuer, réutilise nextCursor."""
        try:
            rows = await to_thread.run_sync(lambda: workspace().projects(limit=limit + 1, after_id=cursor))
        except DomainError as error:
            raise ToolError(error.message) from error
        return Page[ProjectSummary](items=rows[:limit], nextCursor=rows[limit - 1]["id"] if len(rows) > limit else None)

    @server.tool(title="Rechercher des tickets", annotations=READ_ONLY, meta=oauth_metadata(READ_SCOPE))
    async def search_tickets(query: Query = "", project_id: PositiveId | None = None,
                             status: Status | None = None, priority: Priority | None = None,
                             limit: Limit = 20, cursor: Cursor = 0) -> Page[TicketSummary]:
        """Cherche dans les titres, identifiants et descriptions. Pour continuer, conserve les filtres et réutilise nextCursor."""
        filters = {"q": query, "projectId": project_id, "status": status, "priority": priority}
        try:
            rows = await to_thread.run_sync(lambda: workspace().issues(filters, limit=limit + 1, after_id=cursor))
        except DomainError as error:
            raise ToolError(error.message) from error
        return Page[TicketSummary](items=rows[:limit], nextCursor=rows[limit - 1]["id"] if len(rows) > limit else None)

    @server.tool(title="Consulter un ticket", annotations=READ_ONLY, meta=oauth_metadata(READ_SCOPE))
    async def get_ticket(ticket_id: PositiveId) -> TicketDetail:
        """Lit le détail du ticket correspondant à l’identifiant numérique renvoyé par la recherche."""
        try:
            row = await to_thread.run_sync(lambda: workspace().issue(ticket_id))
        except DomainError as error:
            raise ToolError(error.message) from error
        return TicketDetail.model_validate(row)

    def write(request_key: str, data: IssueCreate | CommentCreate, target_id: int) -> CreatedTicket | AddedComment:
        token = get_access_token()
        if token is None or WRITE_SCOPE not in token.scopes:
            raise ToolError("Autorisation d’écriture requise.")
        service = workspace()
        user_id, workspace_id = service.user_id, service.workspace_id
        is_ticket = isinstance(data, IssueCreate)
        action = "create_ticket" if is_ticket else "add_comment"
        result_type = CreatedTicket if is_ticket else AddedComment
        fingerprint = verifier(json.dumps([action, target_id, data.model_dump(mode="json")], sort_keys=True))

        with scoped_connection(database, user_id, workspace_id, write=True) as connection:
            postgres = database.dialect == "postgresql"
            # Serialize writes and refresh/revocation on the same grant before looking up a replay.
            grant = connection.execute("""SELECT g.id, w.slug FROM mcp_connections g
                JOIN workspaces w ON w.id = g.workspace_id
                WHERE g.access_hash = ? AND g.client_id = ? AND g.user_id = ? AND g.workspace_id = ?
                  AND g.resource = ? AND g.scope = ?""" + (" FOR UPDATE OF g" if postgres else ""),
                (verifier(token.token), token.client_id, user_id, workspace_id, f"{origin}/mcp", WRITE_SCOPES)).fetchone()
            if grant is None or not token.expires_at or token.expires_at <= int(time.time()):
                raise ToolError("Accès à Circular non autorisé.")

            repo = WorkspaceRepository(connection, user_id, workspace_id)
            project_id = target_id
            if not is_ticket:
                repo.lock_issue(target_id)
                ticket = service.require(repo.issue(target_id), "Ticket introuvable.")
                project_id = ticket["projectId"]
            if postgres:
                # Keep the project and any explicit membership stable through commit.
                repo.lock_project(project_id, shared=True)
                connection.execute("SELECT user_id FROM project_members WHERE project_id = ? AND user_id = ? FOR KEY SHARE",
                                   (project_id, user_id)).fetchone()
            unavailable = "Projet introuvable." if is_ticket else "Ticket introuvable."
            service.require(repo.project(project_id), unavailable)

            prior = connection.execute("SELECT fingerprint, result FROM mcp_writes WHERE connection_id = ? AND request_key = ?",
                                       (grant["id"], request_key)).fetchone()
            if prior:
                if prior["fingerprint"] != fingerprint:
                    raise ToolError("Cette clé de relance a déjà été utilisée pour une autre écriture.")
                result = result_type.model_validate_json(prior["result"])
                if isinstance(result, CreatedTicket):
                    service.require(repo.issue(result.id), "Ticket introuvable.")
                return result

            if is_ticket:
                ticket = service.create_issue_in(repo, data.model_dump())
                result = CreatedTicket(id=ticket["id"], identifier=ticket["identifier"], projectId=project_id,
                                       url=ticket_url(origin, grant["slug"], ticket["id"]))
            else:
                comment = service.create_comment_in(repo, target_id, data.body)
                result = AddedComment(id=comment["id"], ticketId=target_id, url=ticket_url(origin, grant["slug"], target_id))
            connection.execute("INSERT INTO mcp_writes (connection_id, request_key, fingerprint, result) VALUES (?, ?, ?, ?)",
                               (grant["id"], request_key, fingerprint, result.model_dump_json()))
            return result

    @server.tool(title="Créer un ticket", annotations=ADDITIVE, meta=oauth_metadata(WRITE_SCOPES))
    async def create_ticket(project_id: PositiveId, title: Title, request_key: WriteKey,
                            description: Annotated[str, Field(max_length=20000)] = "") -> CreatedTicket:
        """Crée un ticket dans le projet choisi. Génère une clé unique pour chaque action et réutilise-la à l’identique en cas de relance."""
        try:
            return await to_thread.run_sync(write, request_key, IssueCreate(projectId=project_id, title=title, description=description), project_id)
        except DomainError as error:
            raise ToolError(error.message) from error

    @server.tool(title="Ajouter un commentaire", annotations=ADDITIVE, meta=oauth_metadata(WRITE_SCOPES))
    async def add_comment(ticket_id: PositiveId, body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)],
                          request_key: WriteKey) -> AddedComment:
        """Ajoute un commentaire au ticket choisi. Génère une clé unique pour chaque action et réutilise-la à l’identique en cas de relance."""
        try:
            return await to_thread.run_sync(write, request_key, CommentCreate(body=body), ticket_id)
        except DomainError as error:
            raise ToolError(error.message) from error


def ticket_url(origin: str, slug: str, ticket_id: int) -> str:
    return f"{origin}/?{urlencode({'workspace': slug, 'issue': ticket_id, 'mode': 'page'})}"
