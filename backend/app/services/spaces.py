"""Atomic onboarding, private containers and explicit membership administration."""
import secrets
import sqlite3
import unicodedata
from datetime import datetime, timedelta, timezone
from backend.app.db.session import timestamp
from backend.app.repositories.spaces import SpacesRepository
from backend.app.repositories.workspace import WorkspaceRepository
from backend.app.repositories.sharing import SharingRepository
from backend.app.services.workspace import WorkspaceService, DomainError
from backend.app.services.auth import verifier


def invitation_expiry() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class SpacesService:
    def __init__(self, database, user_id: int):
        self.database, self.user_id = database, user_id

    def require(self, repo: SpacesRepository, workspace_id: int, *, owner: bool = False, lock: bool = False) -> dict:
        workspace = WorkspaceService.require(repo.workspace(workspace_id, lock=lock), "Espace introuvable.")
        if owner and workspace["role"] != "owner":
            raise DomainError(403, "Action réservée au propriétaire de l’espace.")
        return workspace

    def workspace(self, workspace_id: int) -> dict:
        with self.database.connect() as connection:
            return self.require(SpacesRepository(connection, self.user_id), workspace_id)

    def workspaces(self) -> list[dict]:
        with self.database.connect() as connection:
            return SpacesRepository(connection, self.user_id).workspaces()

    def create(self, data: dict) -> dict:
        try:
            with self.database.connect(write=True) as connection:
                # Serialize generated project-key selection across concurrent creates.
                if getattr(connection, "dialect", "sqlite") == "postgresql":
                    connection.execute("SELECT pg_advisory_xact_lock(724205732)")
                spaces = SpacesRepository(connection, self.user_id)
                space = spaces.create(data["name"], data["slug"])
                repo = WorkspaceRepository(connection, self.user_id, space["id"])
                letters = ''.join(char for char in unicodedata.normalize("NFKD", data["name"]).upper() if char.isascii() and char.isalpha())
                prefix = (letters[:5] or "CIRC")
                if len(prefix) < 2:
                    prefix += "C"
                key, suffix = prefix, 0
                while connection.execute("SELECT 1 FROM project_sequences WHERE project_key = ?", (key,)).fetchone():
                    suffix += 1
                    key = prefix[:10 - len(str(suffix))] + str(suffix)
                project = repo.create_project({"name": data["name"], "key": key, "description": "Le premier projet de votre espace Circular.", "color": "#e6c65c", "status": "planned"})
                connection.execute("UPDATE workspaces SET initial_project_id = ? WHERE id = ?", (project["id"], space["id"]))
                if data.get("includeWelcomeIssues", True):
                    for title, description, status in (
                        ("Donner un cap au projet", "Remplacez ce ticket par votre objectif principal. Une phrase précise aide toute l’équipe à avancer dans la même direction.", "todo"),
                        ("Organiser votre prochain pas", "Créez un ticket avec C, choisissez une priorité et retrouvez-le dans la liste ou le tableau.", "backlog"),
                        ("Échanger avec votre équipe", "Invitez les personnes de votre choix dans cet espace. Les commentaires gardent les décisions près du travail concerné.", "backlog"),
                    ):
                        repo.create_issue({"title": title, "description": description, "projectId": project["id"], "status": status, "priority": "none", "labelIds": []})
                return {"workspace": spaces.workspace(space["id"]), "project": repo.project(project["id"])}
        except sqlite3.IntegrityError as error:
            raise DomainError(409, "Cette adresse d’espace est déjà utilisée.") from error

    def update(self, workspace_id: int, data: dict) -> dict:
        try:
            with self.database.connect(write=True) as connection:
                repo = SpacesRepository(connection, self.user_id)
                current = self.require(repo, workspace_id, owner=True, lock=True)
                return repo.update(workspace_id, {**current, **data})
        except sqlite3.IntegrityError as error:
            raise DomainError(409, "Cette adresse d’espace est déjà utilisée.") from error

    def complete_onboarding(self, workspace_id: int) -> dict:
        with self.database.connect(write=True) as connection:
            repo = SpacesRepository(connection, self.user_id)
            self.require(repo, workspace_id)
            return repo.complete_onboarding(workspace_id)

    def members(self, workspace_id: int) -> list[dict]:
        with self.database.connect() as connection:
            repo = SpacesRepository(connection, self.user_id)
            current = self.require(repo, workspace_id)
            if current["role"] == "guest":
                # Project guests must not enumerate unrelated workspace accounts.
                return [item for item in repo.members(workspace_id) if item["id"] == self.user_id]
            return repo.members(workspace_id)

    def remove_member(self, workspace_id: int, user_id: int) -> None:
        with self.database.connect(write=True) as connection:
            repo = SpacesRepository(connection, self.user_id)
            self.require(repo, workspace_id, owner=user_id != self.user_id, lock=True)
            member = WorkspaceService.require(next((item for item in repo.members(workspace_id) if item["id"] == user_id), None), "Membre introuvable.")
            if member["role"] == "owner":
                raise DomainError(409, "Le propriétaire ne peut pas quitter son espace.")
            connection.execute("DELETE FROM workspace_members WHERE workspace_id = ? AND user_id = ?", (workspace_id, user_id))
            connection.execute("DELETE FROM project_members WHERE user_id = ? AND project_id IN (SELECT id FROM projects WHERE workspace_id = ?)", (user_id, workspace_id))
            connection.execute("DELETE FROM project_invitations WHERE (inviter_id = ? OR user_id = ?) AND project_id IN (SELECT id FROM projects WHERE workspace_id = ?)", (user_id, user_id, workspace_id))
            connection.execute("DELETE FROM workspace_invitations WHERE workspace_id = ? AND email = ?", (workspace_id, member["email"]))
            connection.execute("DELETE FROM workspace_user_settings WHERE workspace_id = ? AND user_id = ?", (workspace_id, user_id))
            for project in connection.execute("SELECT id FROM projects WHERE workspace_id = ?", (workspace_id,)).fetchall():
                SharingRepository(connection).clear_personal_project_references(project[0], user_id)

    def invitations(self, workspace_id: int) -> list[dict]:
        with self.database.connect() as connection:
            repo = SpacesRepository(connection, self.user_id)
            self.require(repo, workspace_id, owner=True)
            return repo.invitations(workspace_id)

    def invite(self, workspace_id: int, email: str) -> dict:
        with self.database.connect(write=True) as connection:
            repo = SpacesRepository(connection, self.user_id)
            self.require(repo, workspace_id, owner=True, lock=True)
            if any(member["email"] == email and member["role"] != "guest" for member in repo.members(workspace_id)):
                raise DomainError(409, "Ce compte appartient déjà à l’espace.")
            return repo.invite(workspace_id, email, invitation_expiry())

    def revoke_invitation(self, workspace_id: int, invitation_id: int) -> None:
        with self.database.connect(write=True) as connection:
            self.require(SpacesRepository(connection, self.user_id), workspace_id, owner=True)
            if not connection.execute("DELETE FROM workspace_invitations WHERE workspace_id = ? AND id = ?", (workspace_id, invitation_id)).rowcount:
                raise DomainError(404, "Invitation introuvable.")

    def inbox(self, email: str) -> list[dict]:
        with self.database.connect() as connection:
            return SpacesRepository(connection, self.user_id).inbox(email)

    def respond(self, invitation_id: int, email: str, accept: bool) -> dict | None:
        with self.database.connect(write=True) as connection:
            repo = SpacesRepository(connection, self.user_id)
            invitation = WorkspaceService.require(repo.invitation(invitation_id, email, lock=False), "Invitation introuvable ou expirée.")
            # Member removal takes the same container lock before deleting pending
            # invitations. Re-read after acquiring it: an earlier removal wins.
            repo.lock_invitation_workspace(invitation["workspace_id"])
            invitation = WorkspaceService.require(repo.invitation(invitation_id, email), "Invitation introuvable ou expirée.")
            result = repo.join(invitation["workspace_id"]) if accept else None
            connection.execute("DELETE FROM workspace_invitations WHERE id = ?", (invitation_id,))
            return result

    def links(self, workspace_id: int) -> list[dict]:
        with self.database.connect() as connection:
            repo = SpacesRepository(connection, self.user_id)
            self.require(repo, workspace_id, owner=True)
            return repo.links(workspace_id)

    def create_link(self, workspace_id: int) -> dict:
        with self.database.connect(write=True) as connection:
            repo = SpacesRepository(connection, self.user_id)
            self.require(repo, workspace_id, owner=True, lock=True)
            if len(repo.links(workspace_id)) >= 20:
                raise DomainError(409, "Révoquez un lien existant avant d’en créer un nouveau.")
            token, created, expires = secrets.token_urlsafe(32), timestamp(), invitation_expiry()
            link_id = connection.execute("INSERT INTO workspace_invite_links(workspace_id, token_hash, created_by, created_at, expires_at) VALUES (?, ?, ?, ?, ?)", (workspace_id, verifier(token), self.user_id, created, expires)).lastrowid
            return {"id": link_id, "token": token, "createdAt": created, "expiresAt": expires}

    def revoke_link(self, workspace_id: int, link_id: int) -> None:
        with self.database.connect(write=True) as connection:
            self.require(SpacesRepository(connection, self.user_id), workspace_id, owner=True)
            if not connection.execute("DELETE FROM workspace_invite_links WHERE workspace_id = ? AND id = ?", (workspace_id, link_id)).rowcount:
                raise DomainError(404, "Lien introuvable.")

    def use_link(self, token: str, *, accept: bool = False) -> dict:
        with self.database.connect(write=accept) as connection:
            repo = SpacesRepository(connection, self.user_id)
            link = WorkspaceService.require(repo.link(verifier(token), lock=accept), "Lien introuvable ou expiré.")
            if accept:
                return repo.join(link["workspace_id"])
            space = connection.execute("SELECT name, slug FROM workspaces WHERE id = ?", (link["workspace_id"],)).fetchone()
            return {"workspaceName": space["name"], "workspaceSlug": space["slug"], "expiresAt": link["expires_at"]}
