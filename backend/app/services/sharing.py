"""Explicit acceptance and project-owner authorization for private collaboration."""
from backend.app.repositories.sharing import SharingRepository
from backend.app.repositories.workspace import WorkspaceRepository
from backend.app.services.workspace import WorkspaceService, DomainError


class SharingService:
    def __init__(self, database, user_id: int):
        self.database, self.user_id = database, user_id

    def project(self, connection, project_id: int, owner: bool = False) -> dict:
        project = WorkspaceService.require(WorkspaceRepository(connection, self.user_id).project(project_id), "Projet introuvable.")
        if owner:
            WorkspaceService.owner(project)
        return project

    def members(self, project_id: int) -> list[dict]:
        with self.database.connect() as connection:
            self.project(connection, project_id)
            return SharingRepository(connection).members(project_id)

    def invitations(self, project_id: int) -> list[dict]:
        with self.database.connect() as connection:
            self.project(connection, project_id, owner=True)
            return SharingRepository(connection).invitations(project_id)

    def invite(self, project_id: int, email: str) -> dict:
        with self.database.connect(write=True) as connection:
            self.project(connection, project_id, owner=True)
            repo = SharingRepository(connection)
            user = WorkspaceService.require(repo.recipient(email), "Ce compte n’existe pas. La personne doit d’abord s’inscrire.")
            if any(member["id"] == user["id"] for member in repo.members(project_id)):
                raise DomainError(409, "Ce compte a déjà accès au projet.")
            return repo.invite(project_id, user["id"], self.user_id)

    def inbox(self) -> list[dict]:
        with self.database.connect() as connection:
            return SharingRepository(connection).inbox(self.user_id)

    def respond(self, invitation_id: int, accept: bool) -> None:
        with self.database.connect(write=True) as connection:
            repo = SharingRepository(connection)
            invitation = WorkspaceService.require(repo.invitation(invitation_id, self.user_id), "Invitation introuvable.")
            if accept:
                repo.accept(invitation, self.user_id)
            else:
                repo.decline(invitation_id, self.user_id)

    def revoke(self, project_id: int, invitation_id: int) -> None:
        with self.database.connect(write=True) as connection:
            self.project(connection, project_id, owner=True)
            if not SharingRepository(connection).revoke(project_id, invitation_id):
                raise DomainError(404, "Invitation introuvable.")

    def remove(self, project_id: int, user_id: int) -> None:
        with self.database.connect(write=True) as connection:
            project = self.project(connection, project_id)
            if user_id != self.user_id:
                WorkspaceService.owner(project)
            members = SharingRepository(connection).members(project_id)
            target = next((item for item in members if item["id"] == user_id), None)
            WorkspaceService.require(target, "Membre introuvable.")
            if target["role"] == "owner":
                raise DomainError(409, "Le propriétaire ne peut pas être retiré du projet.")
            repo = SharingRepository(connection)
            repo.remove(project_id, user_id)
            repo.clear_personal_project_references(project_id, user_id)
