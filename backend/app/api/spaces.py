"""Authenticated workspace administration endpoints, independent of current selection."""
from typing import Annotated
from fastapi import APIRouter, Depends, Request, Response
from backend.app.api.auth import User, require_user
from backend.app.api.routes import Id
from backend.app.schemas.spaces import SpaceCreate, SpaceUpdate, SpaceInvitation, InviteToken
from backend.app.services.spaces import SpacesService

router = APIRouter(prefix="/api", tags=["Workspaces"])


def service(request: Request, user: Annotated[dict, Depends(require_user)]) -> SpacesService:
    return SpacesService(request.app.state.database, user["id"])


Service = Annotated[SpacesService, Depends(service)]


@router.get("/workspaces")
def workspaces(spaces: Service):
    return spaces.workspaces()


@router.post("/workspaces", status_code=201)
def create(data: SpaceCreate, spaces: Service):
    return spaces.create(data.model_dump())


@router.patch("/workspaces/{workspace_id}")
def update(workspace_id: Id, data: SpaceUpdate, spaces: Service):
    return spaces.update(workspace_id, data.model_dump(exclude_unset=True))


@router.post("/workspaces/{workspace_id}/onboarding/complete")
def complete(workspace_id: Id, spaces: Service):
    return spaces.complete_onboarding(workspace_id)


@router.get("/workspaces/{workspace_id}/members")
def members(workspace_id: Id, spaces: Service):
    return spaces.members(workspace_id)


@router.delete("/workspaces/{workspace_id}/members/{user_id}", status_code=204)
def remove_member(workspace_id: Id, user_id: Id, spaces: Service):
    spaces.remove_member(workspace_id, user_id)
    return Response(status_code=204)


@router.get("/workspaces/{workspace_id}/invitations")
def invitations(workspace_id: Id, spaces: Service):
    return spaces.invitations(workspace_id)


@router.post("/workspaces/{workspace_id}/invitations", status_code=201)
def invite(workspace_id: Id, data: SpaceInvitation, spaces: Service):
    return spaces.invite(workspace_id, data.email)


@router.delete("/workspaces/{workspace_id}/invitations/{invitation_id}", status_code=204)
def revoke(workspace_id: Id, invitation_id: Id, spaces: Service):
    spaces.revoke_invitation(workspace_id, invitation_id)
    return Response(status_code=204)


@router.get("/workspace-invitations")
def inbox(spaces: Service, user: User):
    return spaces.inbox(user["email"])


@router.post("/workspace-invitations/{invitation_id}/accept")
def accept(invitation_id: Id, spaces: Service, user: User):
    return spaces.respond(invitation_id, user["email"], True)


@router.post("/workspace-invitations/{invitation_id}/decline", status_code=204)
def decline(invitation_id: Id, spaces: Service, user: User):
    spaces.respond(invitation_id, user["email"], False)
    return Response(status_code=204)


@router.get("/workspaces/{workspace_id}/invite-links")
def links(workspace_id: Id, spaces: Service):
    return spaces.links(workspace_id)


@router.post("/workspaces/{workspace_id}/invite-links", status_code=201)
def create_link(workspace_id: Id, spaces: Service):
    return spaces.create_link(workspace_id)


@router.delete("/workspaces/{workspace_id}/invite-links/{link_id}", status_code=204)
def revoke_link(workspace_id: Id, link_id: Id, spaces: Service):
    spaces.revoke_link(workspace_id, link_id)
    return Response(status_code=204)


@router.post("/workspace-invite-links/preview")
def preview(data: InviteToken, spaces: Service):
    return spaces.use_link(data.token)


@router.post("/workspace-invite-links/accept")
def accept_link(data: InviteToken, spaces: Service):
    return spaces.use_link(data.token, accept=True)
