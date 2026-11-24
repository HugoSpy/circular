"""Circular Docs endpoints under an explicit workspace."""
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from backend.app.api.auth import require_user
from backend.app.api.routes import Id
from backend.app.schemas.docs import (
    CommentEdit, CommentInput, DocsAccess, CollectionCreate, FieldCreate, FieldEdit, FieldOrder, GalleryPreviewRequest, PageFromTemplate, PagePlacement, PageSave, PropertyUpdate, RelationUpdate, RevisionCheck, TemplateCreate, TemplateName, ViewSave,
)
from backend.app.schemas.workspace import MAX_ID
from backend.app.services.docs import DocsService
from backend.app.services.docs_export import zip_chunks

router = APIRouter(prefix="/api/workspaces/{workspace_id}/docs", tags=["Docs"])


def service(request: Request, workspace_id: Id, user: Annotated[dict, Depends(require_user)]) -> DocsService:
    return DocsService(request.app.state.database, workspace_id, user["id"])


Service = Annotated[DocsService, Depends(service)]


@router.get("")
def index(docs: Service):
    return docs.index()


@router.get("/search")
def search(docs: Service, q: Annotated[str, Query(max_length=200)] = ""):
    return docs.search(q)


@router.get("/export")
def export(docs: Service):
    return StreamingResponse(zip_chunks(docs.export()), media_type="application/zip", headers={
        "Content-Disposition": 'attachment; filename="circular-docs.zip"',
        "Cache-Control": "private, no-store",
    })


@router.get("/pages/{page_id}")
def page(page_id: UUID, docs: Service):
    return docs.page(str(page_id))


@router.post("/pages", status_code=201)
def create_page(data: PageFromTemplate, docs: Service):
    return docs.create_page(data)


@router.patch("/pages/{page_id}/placement")
def place_page(page_id: UUID, data: PagePlacement, docs: Service):
    return docs.place_page(str(page_id), data)


@router.patch("/pages/{page_id}/body")
def save_page(page_id: UUID, data: PageSave, docs: Service):
    return docs.save_page(str(page_id), data)


@router.patch("/pages/{page_id}/properties/{field_id}")
def update_property(page_id: UUID, field_id: UUID, data: PropertyUpdate, docs: Service):
    return docs.update_property(str(page_id), str(field_id), data.value)


@router.patch("/pages/{page_id}/relations/{field_id}")
def update_relations(page_id: UUID, field_id: UUID, data: RelationUpdate, docs: Service):
    return docs.update_relations(str(page_id), str(field_id), data)


@router.post("/pages/{page_id}/duplicate", status_code=201)
def duplicate_page(page_id: UUID, docs: Service):
    return docs.duplicate_page(str(page_id))


@router.get("/pages/{page_id}/revisions")
def revisions(page_id: UUID, docs: Service, before: Annotated[int | None, Query(ge=1, le=MAX_ID)] = None,
              limit: Annotated[int, Query(ge=1, le=100)] = 30):
    return docs.revisions(str(page_id), before, limit)


@router.get("/pages/{page_id}/revisions/{revision}")
def revision(page_id: UUID, revision: Id, docs: Service):
    return docs.revision(str(page_id), revision)


@router.post("/pages/{page_id}/revisions/{revision}/restore")
def restore_revision(page_id: UUID, revision: Id, data: RevisionCheck, docs: Service):
    return docs.restore_revision(str(page_id), revision, data.revision)


@router.post("/pages/{page_id}/trash", status_code=201)
def trash_page(page_id: UUID, data: RevisionCheck, docs: Service):
    return docs.trash_page(str(page_id), data.revision)


@router.get("/trash")
def trash_entries(docs: Service):
    return docs.trash_entries()


@router.post("/trash/{operation}/restore")
def restore_trash(operation: UUID, docs: Service):
    return docs.restore_trash(str(operation))


@router.get("/collections/{collection_id}")
def collection(collection_id: UUID, docs: Service):
    return docs.collection(str(collection_id))


@router.post("/collections/{collection_id}/gallery-previews")
def gallery_previews(collection_id: UUID, data: GalleryPreviewRequest, docs: Service):
    return docs.gallery_previews(str(collection_id), data)


@router.post("/collections", status_code=201)
def create_collection(data: CollectionCreate, docs: Service):
    return docs.create_collection(data)


@router.post("/collections/{collection_id}/fields", status_code=201)
def create_field(collection_id: UUID, data: FieldCreate, docs: Service):
    return docs.create_field(str(collection_id), data)


@router.patch("/collections/{collection_id}/fields/order")
def order_fields(collection_id: UUID, data: FieldOrder, docs: Service):
    return docs.order_fields(str(collection_id), [str(identifier) for identifier in data.fieldIds])


@router.patch("/collections/{collection_id}/fields/{field_id}")
def edit_field(collection_id: UUID, field_id: UUID, data: FieldEdit, docs: Service):
    return docs.edit_field(str(collection_id), str(field_id), data)


@router.post("/collections/{collection_id}/views", status_code=201)
def create_view(collection_id: UUID, data: ViewSave, docs: Service):
    return docs.save_view(str(collection_id), data)


@router.patch("/collections/{collection_id}/views/{view_id}")
def save_view(collection_id: UUID, view_id: UUID, data: ViewSave, docs: Service):
    return docs.save_view(str(collection_id), data, str(view_id))


@router.delete("/collections/{collection_id}/views/{view_id}", status_code=204)
def delete_view(collection_id: UUID, view_id: UUID, docs: Service):
    docs.delete_view(str(collection_id), str(view_id))
    return Response(status_code=204)


@router.get("/templates")
def templates(docs: Service):
    return docs.templates()


@router.post("/pages/{page_id}/templates", status_code=201)
def save_template(page_id: UUID, data: TemplateCreate, docs: Service):
    return docs.save_template(str(page_id), data)


@router.patch("/templates/{template_id}")
def rename_template(template_id: UUID, data: TemplateName, docs: Service):
    return docs.change_template(str(template_id), data.name)


@router.delete("/templates/{template_id}", status_code=204)
def archive_template(template_id: UUID, docs: Service):
    docs.change_template(str(template_id))
    return Response(status_code=204)


@router.post("/pages/{page_id}/attachments", status_code=201)
async def upload_asset(page_id: UUID, request: Request, docs: Service, assetId: UUID,
                       name: Annotated[str, Query(min_length=1, max_length=240)], image: bool = False):
    content = await request.body()
    return await run_in_threadpool(docs.upload_asset, str(page_id), str(assetId), name, content, image)


@router.get("/attachments/{asset_id}")
def download_asset(asset_id: UUID, docs: Service, preview: bool = False):
    asset = docs.asset(str(asset_id))
    inline = preview and asset["media_type"].startswith("image/")
    mode = "inline" if inline else "attachment"
    return Response(bytes(asset["content"]), media_type=asset["media_type"], headers={
        "Content-Disposition": f"{mode}; filename*=UTF-8''{quote(asset['name'], safe='')}",
        "Cache-Control": "private, no-store",
    })


@router.get("/access")
def access_members(docs: Service):
    return docs.access_members()


@router.patch("/access/{user_id}", status_code=204)
def change_access(user_id: Id, data: DocsAccess, docs: Service):
    docs.change_access(user_id, data.role)
    return Response(status_code=204)


@router.get("/pages/{page_id}/comments")
def comments(page_id: UUID, docs: Service):
    return docs.comments(str(page_id))


@router.put("/pages/{page_id}/comments/{comment_id}", status_code=201)
def create_comment(page_id: UUID, comment_id: UUID, data: CommentInput, docs: Service):
    return docs.write_comment(str(page_id), str(comment_id), data, create=True)


@router.patch("/pages/{page_id}/comments/{comment_id}")
def edit_comment(page_id: UUID, comment_id: UUID, data: CommentEdit, docs: Service):
    return docs.write_comment(str(page_id), str(comment_id), data)


@router.delete("/pages/{page_id}/comments/{comment_id}", status_code=204)
def delete_comment(page_id: UUID, comment_id: UUID, docs: Service):
    docs.delete_comment(str(page_id), str(comment_id))
    return Response(status_code=204)


@router.get("/notifications")
def notifications(docs: Service):
    return docs.notifications()


@router.patch("/notifications/{comment_id}/read", status_code=204)
def read_notification(comment_id: UUID, docs: Service):
    docs.mark_read(str(comment_id))
    return Response(status_code=204)
