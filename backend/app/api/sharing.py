"""Authenticated adapters for project membership and invitations."""
from typing import Annotated
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from backend.app.api.auth import require_user
from backend.app.api.routes import Id
from backend.app.services.sharing import SharingService

router = APIRouter(prefix="/api")


def service(request: Request, user: Annotated[dict, Depends(require_user)]) -> SharingService:
    return SharingService(request.app.state.database, user["id"])


Service = Annotated[SharingService, Depends(service)]


class InvitationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    email: str = Field(max_length=254)

    @field_validator("email")
    @classmethod
    def email_domain(cls, value: str) -> str:
        value = value.casefold()
        local, separator, domain = value.rpartition("@")
        if separator != "@" or not local or "@" in local or domain != "epita.fr" or any(char.isspace() for char in value):
            raise ValueError("Adresse @epita.fr requise.")
        return value


@router.get("/projects/{project_id}/members")
def members(project_id: Id, workspace: Service):
    return workspace.members(project_id)


@router.get("/projects/{project_id}/invitations")
def project_invitations(project_id: Id, workspace: Service):
    return workspace.invitations(project_id)


@router.post("/projects/{project_id}/invitations", status_code=201)
def invite(project_id: Id, data: InvitationInput, workspace: Service):
    return workspace.invite(project_id, data.email)


@router.delete("/projects/{project_id}/invitations/{invitation_id}", status_code=204)
def revoke(project_id: Id, invitation_id: Id, workspace: Service):
    workspace.revoke(project_id, invitation_id)
    return Response(status_code=204)


@router.delete("/projects/{project_id}/members/{user_id}", status_code=204)
def remove(project_id: Id, user_id: Id, workspace: Service):
    workspace.remove(project_id, user_id)
    return Response(status_code=204)


@router.get("/invitations")
def inbox(workspace: Service):
    return workspace.inbox()


@router.post("/invitations/{invitation_id}/accept", status_code=204)
def accept(invitation_id: Id, workspace: Service):
    workspace.respond(invitation_id, True)
    return Response(status_code=204)


@router.post("/invitations/{invitation_id}/decline", status_code=204)
def decline(invitation_id: Id, workspace: Service):
    workspace.respond(invitation_id, False)
    return Response(status_code=204)
