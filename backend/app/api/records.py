"""Browser entry points for the workspace records also exposed through MCP."""
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from pydantic import BaseModel, StrictBool, UUID4

from backend.app.api.auth import User
from backend.app.schemas.records import RecordChange, RecordKind
from backend.app.schemas.workspace import MAX_ID, PositiveId
from backend.app.services.records import Record, RecordPage, RecordsService
from backend.app.services.document_shares import DocumentShares
from backend.app.services.github_reviews import GithubReviews, PullFiles, RepositoryName
from backend.app.services.scope import scoped_connection
from backend.app.services.ticket_shares import TicketShares
from backend.app.services.workspace import DomainError

router = APIRouter(prefix="/api/workspaces/{workspace_id}/records", tags=["Planification"])
shares_router = APIRouter(prefix="/api/workspaces/{workspace_id}/ticket-shares", tags=["Tickets"])
document_shares_router = APIRouter(prefix="/api/workspaces/{workspace_id}/document-shares", tags=["Docs"])
github_router = APIRouter(prefix="/api/workspaces/{workspace_id}/github", tags=["GitHub"])
PathId = Annotated[int, Path(gt=0, le=MAX_ID)]


def records(request: Request, workspace_id: PathId, user: User) -> RecordsService:
    return RecordsService(request.app.state.database, user["id"], workspace_id)


Service = Annotated[RecordsService, Depends(records)]
QueryText = Annotated[str, Query(max_length=200)]
Cursor = Annotated[str, Query(max_length=36)]


class ArchiveRequest(BaseModel):
    revision: PositiveId
    approved: StrictBool


@router.get("/{kind}", response_model=RecordPage)
def list_records(kind: RecordKind, service: Service, q: QueryText = "", cursor: Cursor = "", include_archived: bool = False):
    return service.list(kind, q, cursor, archived=include_archived)


@router.get("/{kind}/{record_id}", response_model=Record)
def get_record(kind: RecordKind, record_id: UUID4, service: Service):
    return service.get(kind, str(record_id))


@router.post("/{kind}", response_model=Record)
def save_record(kind: RecordKind, data: RecordChange, service: Service):
    return service.save(kind, data)


@router.post("/{kind}/{record_id}/archive", response_model=Record)
def archive_record(kind: RecordKind, record_id: UUID4, data: ArchiveRequest, service: Service):
    if not data.approved:
        raise DomainError(422, "Confirmez l’archivage de cet élément.")
    return service.archive(kind, str(record_id), data.revision)


@shares_router.get("")
def list_shares(request: Request, workspace_id: PathId, user: User, cursor: Annotated[int, Query(ge=0, le=MAX_ID)] = 0):
    return TicketShares(request.app.state.database, user["id"], workspace_id).list(cursor)


@shares_router.get("/{ticket_id}")
def current_share(request: Request, workspace_id: PathId, ticket_id: PathId, user: User):
    return TicketShares(request.app.state.database, user["id"], workspace_id).get(ticket_id)


@document_shares_router.get("")
def list_document_shares(request: Request, workspace_id: PathId, user: User, cursor: Cursor = ""):
    return DocumentShares(request.app.state.database, user["id"], workspace_id).list(cursor)


@document_shares_router.get("/{page_id}")
def current_document_share(request: Request, workspace_id: PathId, page_id: UUID4, user: User):
    return DocumentShares(request.app.state.database, user["id"], workspace_id).get(str(page_id))


@document_shares_router.get("/attachments/{asset_id}")
def shared_attachment(request: Request, workspace_id: PathId, asset_id: UUID4, user: User):
    asset = DocumentShares(request.app.state.database, user["id"], workspace_id).asset(str(asset_id))
    return Response(bytes(asset["content"]), media_type=asset["media_type"], headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(asset['name'], safe='')}", "Cache-Control": "private, no-store",
    })


@github_router.get("/pull", response_model=PullFiles)
def github_pull(request: Request, workspace_id: PathId, user: User, repository: RepositoryName,
                number: Annotated[int, Query(gt=0, le=MAX_ID)], page: Annotated[int, Query(ge=1, le=100)] = 1):
    with scoped_connection(request.app.state.database, user["id"], workspace_id):
        return GithubReviews(user["id"], workspace_id).files(repository, number, page)
