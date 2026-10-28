"""HTTP adapters for local settings, saved views and templates."""
from typing import Annotated
from fastapi import APIRouter, Depends, Request, Path, Response
from backend.app.schemas.preferences import Settings, SettingsUpdate, SavedView, ViewCreate, ViewUpdate, Template, TemplateCreate, TemplateUpdate
from backend.app.schemas.responses import Error
from backend.app.schemas.workspace import MAX_ID
from backend.app.services.preferences import PreferencesService
from backend.app.api.auth import require_user

router = APIRouter(prefix="/api", responses={status: {"model": Error} for status in (400, 403, 404, 409, 413, 415, 422)})


def service(request: Request, user: Annotated[dict, Depends(require_user)]) -> PreferencesService:
    return PreferencesService(request.app.state.database, user["id"])


Service = Annotated[PreferencesService, Depends(service)]
Id = Annotated[int, Path(gt=0, le=MAX_ID)]


@router.get("/settings", response_model=Settings)
def settings(workspace: Service):
    return workspace.settings()


@router.patch("/settings", response_model=Settings)
def update_settings(data: SettingsUpdate, workspace: Service):
    return workspace.update_settings(data.model_dump(include=data.model_fields_set))


@router.get("/views", response_model=list[SavedView])
def views(workspace: Service):
    return workspace.views()


@router.post("/views", response_model=SavedView, status_code=201)
def create_view(data: ViewCreate, workspace: Service):
    return workspace.create_view(data.model_dump())


@router.patch("/views/{view_id}", response_model=SavedView)
def update_view(view_id: Id, data: ViewUpdate, workspace: Service):
    return workspace.update_view(view_id, data.model_dump(include=data.model_fields_set))


@router.delete("/views/{view_id}", status_code=204)
def delete_view(view_id: Id, workspace: Service):
    workspace.delete_view(view_id)
    return Response(status_code=204)


@router.get("/templates", response_model=list[Template])
def templates(workspace: Service):
    return workspace.templates()


@router.post("/templates", response_model=Template, status_code=201)
def create_template(data: TemplateCreate, workspace: Service):
    return workspace.create_template(data.model_dump())


@router.patch("/templates/{template_id}", response_model=Template)
def update_template(template_id: Id, data: TemplateUpdate, workspace: Service):
    return workspace.update_template(template_id, data.model_dump(exclude_unset=True))


@router.delete("/templates/{template_id}", status_code=204)
def delete_template(template_id: Id, workspace: Service):
    workspace.delete_template(template_id)
    return Response(status_code=204)
