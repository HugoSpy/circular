"""Read-only Circular tools for an explicitly authorized workspace."""
from typing import Annotated, Generic, TypeVar

from anyio import to_thread
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field, StringConstraints

from backend.app.db.session import Database
from backend.app.schemas.workspace import MAX_ID, PositiveId, Priority, ProjectStatus, Status
from backend.app.services.workspace import DomainError, WorkspaceService


READ_SCOPE = "circular:read"
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
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


class Page(BaseModel, Generic[Item]):
    items: list[Item]
    nextCursor: int | None


def register_read_tools(server: FastMCP, database: Database) -> None:
    def workspace() -> WorkspaceService:
        token = get_access_token()
        if token is None or READ_SCOPE not in token.scopes or token.claims is None:
            raise ToolError("Accès à Circular non autorisé.")
        user_id = token.claims.get("user_id")
        workspace_id = token.claims.get("workspace_id")
        if type(user_id) is not int or user_id <= 0 or type(workspace_id) is not int or workspace_id <= 0:
            raise ToolError("Accès à Circular non autorisé.")
        return WorkspaceService(database, user_id, workspace_id)

    @server.tool(title="Lister les projets", annotations=READ_ONLY)
    async def list_projects(limit: Limit = 20, cursor: Cursor = 0) -> Page[ProjectSummary]:
        """Liste les projets accessibles dans l’espace autorisé. Pour continuer, réutilise nextCursor."""
        try:
            rows = await to_thread.run_sync(lambda: workspace().projects(limit=limit + 1, after_id=cursor))
        except DomainError as error:
            raise ToolError(error.message) from error
        return Page[ProjectSummary](items=rows[:limit], nextCursor=rows[limit - 1]["id"] if len(rows) > limit else None)

    @server.tool(title="Rechercher des tickets", annotations=READ_ONLY)
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

    @server.tool(title="Consulter un ticket", annotations=READ_ONLY)
    async def get_ticket(ticket_id: PositiveId) -> TicketDetail:
        """Lit le détail du ticket correspondant à l’identifiant numérique renvoyé par la recherche."""
        try:
            row = await to_thread.run_sync(lambda: workspace().issue(ticket_id))
        except DomainError as error:
            raise ToolError(error.message) from error
        return TicketDetail.model_validate(row)
