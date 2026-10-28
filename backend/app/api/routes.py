"""HTTP routing and request/response adaptation. No SQL or domain rules."""
from typing import Annotated, get_args
from fastapi import APIRouter, Depends, Request, Query, Path, Response
from backend.app.schemas.workspace import ProjectCreate, ProjectUpdate, IssueCreate, IssueUpdate, LabelCreate, LabelUpdate, CommentCreate, Status, Priority, MAX_ID
from backend.app.schemas.preferences import SortBy, Direction
from backend.app.schemas.responses import Project, Issue, Label, Comment, Error, Activity
from backend.app.services.workspace import WorkspaceService, DomainError
from backend.app.api.auth import require_user
from backend.app.api.scope import selected_workspace

router = APIRouter(prefix="/api", responses={status: {"model": Error} for status in (400, 403, 404, 409, 413, 415, 422)})


def service(request: Request, user: Annotated[dict, Depends(require_user)]) -> WorkspaceService:
    return WorkspaceService(request.app.state.database, user["id"], selected_workspace(request, user["id"]))


Service = Annotated[WorkspaceService, Depends(service)]
Id = Annotated[int, Path(gt=0, le=MAX_ID)]


@router.get("/health")
def health():
    return {"ok": True}


@router.get("/ready")
def ready(request: Request):
    try:
        with request.app.state.database.connect() as connection:
            connection.execute("SELECT 1").fetchone()
        return {"ok": True}
    except Exception:
        from fastapi.responses import JSONResponse
        return JSONResponse({"ok": False}, status_code=503)


@router.get("/projects", response_model=list[Project])
def projects(workspace: Service):
    return workspace.projects()


@router.post("/projects", status_code=201, response_model=Project)
def create_project(data: ProjectCreate, workspace: Service):
    return workspace.create_project(data.model_dump())


@router.patch("/projects/{project_id}", response_model=Project)
def update_project(project_id: Id, data: ProjectUpdate, workspace: Service):
    return workspace.update_project(project_id, data.model_dump(exclude_unset=True))


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: Id, workspace: Service):
    workspace.delete_project(project_id)
    return Response(status_code=204)


@router.get("/issues", response_model=list[Issue])
def issues(workspace: Service, q: Annotated[str | None, Query(max_length=200)] = None,
           projectId: Annotated[int | None, Query(gt=0, le=MAX_ID)] = None, status: Status | None = None, priority: Priority | None = None,
           statuses: Annotated[str, Query(max_length=100)] = "", priorities: Annotated[str, Query(max_length=100)] = "",
           labelIds: Annotated[str, Query(max_length=240)] = "", favoritesOnly: bool = False,
           sortBy: SortBy = "createdAt", direction: Direction = "desc"):
    def choices(raw: str, allowed: tuple[str, ...]) -> list[str]:
        values = raw.split(",") if raw else []
        if any(value not in allowed for value in values) or len(values) != len(set(values)):
            raise DomainError(422, "Valeur de filtre invalide.")
        return values

    labels = labelIds.split(",") if labelIds else []
    if len(labels) > 20 or any(not value.isascii() or not value.isdigit() or not 1 <= int(value) <= MAX_ID for value in labels) or len(labels) != len(set(labels)):
        raise DomainError(422, "Étiquettes de filtre invalides.")
    return workspace.issues({"q": q, "projectId": projectId, "status": status, "priority": priority,
        "statuses": choices(statuses, get_args(Status)), "priorities": choices(priorities, get_args(Priority)),
        "labelIds": [int(value) for value in labels], "favoritesOnly": favoritesOnly, "sortBy": sortBy, "direction": direction})


@router.get("/issues/{issue_id}", response_model=Issue)
def issue(issue_id: Id, workspace: Service):
    return workspace.issue(issue_id)


@router.post("/issues", status_code=201, response_model=Issue)
def create_issue(data: IssueCreate, workspace: Service):
    return workspace.create_issue(data.model_dump())


@router.patch("/issues/{issue_id}", response_model=Issue)
def update_issue(issue_id: Id, data: IssueUpdate, workspace: Service):
    return workspace.update_issue(issue_id, data.model_dump(exclude_unset=True))


@router.post("/issues/{issue_id}/duplicate", status_code=201, response_model=Issue)
def duplicate_issue(issue_id: Id, workspace: Service):
    return workspace.duplicate_issue(issue_id)


@router.get("/issues/{issue_id}/activity", response_model=list[Activity])
def activity(issue_id: Id, workspace: Service):
    return workspace.activity(issue_id)


@router.delete("/issues/{issue_id}", status_code=204)
def delete_issue(issue_id: Id, workspace: Service):
    workspace.delete_issue(issue_id)
    return Response(status_code=204)


@router.get("/labels", response_model=list[Label])
def labels(workspace: Service):
    return workspace.labels()


@router.post("/labels", status_code=201, response_model=Label)
def create_label(data: LabelCreate, workspace: Service):
    return workspace.create_label(data.model_dump())


@router.patch("/labels/{label_id}", response_model=Label)
def update_label(label_id: Id, data: LabelUpdate, workspace: Service):
    return workspace.update_label(label_id, data.model_dump(exclude_unset=True))


@router.delete("/labels/{label_id}", status_code=204)
def delete_label(label_id: Id, workspace: Service):
    workspace.delete_label(label_id)
    return Response(status_code=204)


@router.get("/issues/{issue_id}/comments", response_model=list[Comment])
def comments(issue_id: Id, workspace: Service):
    return workspace.comments(issue_id)


@router.post("/issues/{issue_id}/comments", status_code=201, response_model=Comment)
def create_comment(issue_id: Id, data: CommentCreate, workspace: Service):
    return workspace.create_comment(issue_id, data.body)


@router.patch("/issues/{issue_id}/comments/{comment_id}", response_model=Comment)
def update_comment(issue_id: Id, comment_id: Id, data: CommentCreate, workspace: Service):
    return workspace.update_comment(issue_id, comment_id, data.body)


@router.delete("/issues/{issue_id}/comments/{comment_id}", status_code=204)
def delete_comment(issue_id: Id, comment_id: Id, workspace: Service):
    workspace.delete_comment(issue_id, comment_id)
    return Response(status_code=204)
