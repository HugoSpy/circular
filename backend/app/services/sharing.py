"""Explicit acceptance and project-owner authorization for private collaboration."""
from backend.app.repositories.sharing import SharingRepository
from backend.app.repositories.workspace import WorkspaceRepository
from backend.app.services.scope import scoped_connection
from backend.app.services.workspace import WorkspaceService, DomainError


class SharingService:
    def __init__(self, database, user_id: int, workspace_id: int | None = None):
        self.database, self.user_id, self.workspace_id = database, user_id, workspace_id

    def project(self, connection, project_id: int, owner: bool = False) -> dict:
        project = WorkspaceService.require(WorkspaceRepository(connection, self.user_id, self.workspace_id).project(project_id), "Projet introuvable.")
        if owner:
            WorkspaceService.owner(project)
        return project

    def members(self, project_id: int) -> list[dict]:
        with scoped_connection(self.database, self.user_id, self.workspace_id) as connection:
            project = self.project(connection, project_id)
            members = SharingRepository(connection).members(project_id)
            for member in members:
                member["canRemove"] = not member["inherited"] and member["role"] != "owner" and (project["role"] == "owner" or member["id"] == self.user_id)
            return members

    def invitations(self, project_id: int) -> list[dict]:
        with scoped_connection(self.database, self.user_id, self.workspace_id) as connection:
            self.project(connection, project_id, owner=True)
            return SharingRepository(connection).invitations(project_id)

    def invite(self, project_id: int, email: str) -> dict:
        with scoped_connection(self.database, self.user_id, self.workspace_id, write=True) as connection:
            self.project(connection, project_id, owner=True)
            repo = SharingRepository(connection)
            user = WorkspaceService.require(repo.recipient(email), "Ce compte n’existe pas. La personne doit d’abord s’inscrire.")
            if any(member["id"] == user["id"] for member in repo.members(project_id)):
                raise DomainError(409, "Ce compte a déjà accès au projet.")
            return repo.invite(project_id, user["id"], self.user_id)

    def inbox(self) -> list[dict]:
        with scoped_connection(self.database, self.user_id, self.workspace_id) as connection:
            return SharingRepository(connection).inbox(self.user_id)

    def respond(self, invitation_id: int, accept: bool) -> None:
        with scoped_connection(self.database, self.user_id, self.workspace_id, write=True) as connection:
            repo = SharingRepository(connection)
            invitation = WorkspaceService.require(repo.invitation(invitation_id, self.user_id, lock=False), "Invitation introuvable.")
            repo.lock_invitation_workspace(invitation["project_id"])
            invitation = WorkspaceService.require(repo.invitation(invitation_id, self.user_id), "Invitation introuvable.")
            if accept:
                repo.accept(invitation, self.user_id)
            else:
                repo.decline(invitation_id, self.user_id)

    def revoke(self, project_id: int, invitation_id: int) -> None:
        with scoped_connection(self.database, self.user_id, self.workspace_id, write=True) as connection:
            self.project(connection, project_id, owner=True)
            if not SharingRepository(connection).revoke(project_id, invitation_id):
                raise DomainError(404, "Invitation introuvable.")

    def remove(self, project_id: int, user_id: int) -> None:
        with scoped_connection(self.database, self.user_id, self.workspace_id, write=True) as connection:
            project = self.project(connection, project_id)
            if user_id != self.user_id:
                WorkspaceService.owner(project)
            members = SharingRepository(connection).members(project_id)
            target = next((item for item in members if item["id"] == user_id), None)
            WorkspaceService.require(target, "Membre introuvable.")
            if target["role"] == "owner":
                raise DomainError(409, "Le propriétaire ne peut pas être retiré du projet.")
            if target["inherited"]:
                raise DomainError(409, "Cet accès provient de l’espace. Gérez cette personne dans les membres de l’espace.")
            repo = SharingRepository(connection)
            repo.remove(project_id, user_id)
            repo.clear_personal_project_references(project_id, user_id)
