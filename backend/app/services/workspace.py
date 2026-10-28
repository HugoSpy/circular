"""Domain rules and atomic units of work, independent from FastAPI."""
import sqlite3
from backend.app.db.session import Database
from backend.app.repositories.workspace import WorkspaceRepository
from backend.app.repositories.preferences import PreferencesRepository


class DomainError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message
        super().__init__(message)


class WorkspaceService:
    def __init__(self, database: Database, user_id: int | None = None):
        self.database = database
        self.user_id = user_id

    @staticmethod
    def require(value, message: str):
        if value is None:
            raise DomainError(404, message)
        return value

    @staticmethod
    def owner(project: dict) -> None:
        if project["role"] != "owner":
            raise DomainError(403, "Action réservée au propriétaire du projet.")

    @staticmethod
    def validate_references(repo: WorkspaceRepository, data: dict):
        if data.get("projectId") is not None and repo.project(data["projectId"]) is None:
            raise DomainError(422, "Le projet sélectionné n’existe pas.")
        for label_id in data.get("labelIds", []):
            if repo.label(label_id) is None:
                raise DomainError(422, "Une étiquette sélectionnée n’existe pas.")

    def projects(self) -> list[dict]:
        with self.database.connect() as connection:
            return WorkspaceRepository(connection, self.user_id).projects()

    def create_project(self, data: dict) -> dict:
        try:
            with self.database.connect(write=True) as connection:
                return WorkspaceRepository(connection, self.user_id).create_project(data)
        except sqlite3.IntegrityError as error:
            raise DomainError(409, "Ce préfixe de projet existe déjà.") from error

    def update_project(self, project_id: int, data: dict) -> dict:
        with self.database.connect(write=True) as connection:
            repo = WorkspaceRepository(connection, self.user_id)
            repo.lock_project(project_id)
            current = self.require(repo.project(project_id), "Projet introuvable.")
            self.owner(current)
            return repo.update_project(project_id, {**current, **data})

    def delete_project(self, project_id: int) -> None:
        with self.database.connect(write=True) as connection:
            repo = WorkspaceRepository(connection, self.user_id)
            repo.lock_project(project_id)
            project = self.require(repo.project(project_id), "Projet introuvable.")
            self.owner(project)
            if project["issueCount"]:
                raise DomainError(409, "Ce projet contient des tickets. Déplacez-les ou supprimez-les avant de supprimer le projet.")
            repo.delete_project(project_id)
            PreferencesRepository(connection).remove_filter_reference(project_id=project_id)

    def issues(self, filters: dict) -> list[dict]:
        with self.database.connect() as connection:
            return WorkspaceRepository(connection, self.user_id).issues(filters)

    def issue(self, issue_id: int) -> dict:
        with self.database.connect() as connection:
            return self.require(WorkspaceRepository(connection, self.user_id).issue(issue_id), "Ticket introuvable.")

    def create_issue(self, data: dict) -> dict:
        with self.database.connect(write=True) as connection:
            repo = WorkspaceRepository(connection, self.user_id)
            self.validate_references(repo, data)
            return repo.create_issue(data)

    def update_issue(self, issue_id: int, data: dict) -> dict:
        with self.database.connect(write=True) as connection:
            repo = WorkspaceRepository(connection, self.user_id)
            repo.lock_issue(issue_id)
            current = self.require(repo.issue(issue_id), "Ticket introuvable.")
            self.validate_references(repo, data)
            before = {**current, "labelIds": [label["id"] for label in current["labels"]]}
            changes = [key for key, value in data.items() if (set(value) != set(before[key]) if key == "labelIds" else value != before[key])]
            if not changes:
                return current
            if "isFavorite" in data:
                repo.set_favorite(issue_id, data["isFavorite"])
                changes = [key for key in changes if key != "isFavorite"]
                if not changes:
                    return repo.issue(issue_id)
            updated = repo.update_issue(issue_id, {**current, **data})
            names = {"title": "titre", "description": "description", "projectId": "projet", "status": "statut", "priority": "priorité", "labelIds": "étiquettes", "dueDate": "échéance", "isFavorite": "favori"}
            repo.add_activity(issue_id, "updated", "Modification : " + ", ".join(names[key] for key in changes) + ".")
            return updated

    def duplicate_issue(self, issue_id: int) -> dict:
        with self.database.connect(write=True) as connection:
            repo = WorkspaceRepository(connection, self.user_id)
            original = self.require(repo.issue(issue_id), "Ticket introuvable.")
            suffix = " (copie)"
            data = {**original, "title": original["title"][:240 - len(suffix)] + suffix,
                    "labelIds": [label["id"] for label in original["labels"]], "isFavorite": False}
            return repo.create_issue(data)

    def activity(self, issue_id: int) -> list[dict]:
        with self.database.connect() as connection:
            repo = WorkspaceRepository(connection, self.user_id)
            self.require(repo.issue(issue_id), "Ticket introuvable.")
            return repo.activity(issue_id)

    def delete_issue(self, issue_id: int) -> None:
        with self.database.connect(write=True) as connection:
            repo = WorkspaceRepository(connection, self.user_id)
            self.require(repo.issue(issue_id), "Ticket introuvable.")
            repo.delete_issue(issue_id)

    def labels(self) -> list[dict]:
        with self.database.connect() as connection:
            return WorkspaceRepository(connection, self.user_id).labels()

    def create_label(self, data: dict) -> dict:
        with self.database.connect(write=True) as connection:
            repo = WorkspaceRepository(connection, self.user_id)
            if repo.label_by_name(data["name"]):
                raise DomainError(409, "Une étiquette porte déjà ce nom.")
            return repo.create_label(data)

    def update_label(self, label_id: int, data: dict) -> dict:
        with self.database.connect(write=True) as connection:
            repo = WorkspaceRepository(connection, self.user_id)
            current = self.require(repo.label(label_id), "Étiquette introuvable.")
            if not current["canEdit"]:
                raise DomainError(403, "Seul le créateur peut modifier cette étiquette.")
            if "name" in data:
                duplicate = repo.label_by_name(data["name"])
                if duplicate and duplicate["id"] != label_id:
                    raise DomainError(409, "Une étiquette porte déjà ce nom.")
            return repo.update_label(label_id, {**current, **data})

    def delete_label(self, label_id: int) -> None:
        with self.database.connect(write=True) as connection:
            repo = WorkspaceRepository(connection, self.user_id)
            label = self.require(repo.label(label_id), "Étiquette introuvable.")
            if not label["canEdit"]:
                raise DomainError(403, "Seul le créateur peut supprimer cette étiquette.")
            repo.delete_label(label_id)
            PreferencesRepository(connection).remove_filter_reference(label_id=label_id)

    def comments(self, issue_id: int) -> list[dict]:
        with self.database.connect() as connection:
            repo = WorkspaceRepository(connection, self.user_id)
            self.require(repo.issue(issue_id), "Ticket introuvable.")
            return repo.comments(issue_id)

    def create_comment(self, issue_id: int, body: str) -> dict:
        with self.database.connect(write=True) as connection:
            repo = WorkspaceRepository(connection, self.user_id)
            self.require(repo.issue(issue_id), "Ticket introuvable.")
            return repo.create_comment(issue_id, body)

    def update_comment(self, issue_id: int, comment_id: int, body: str) -> dict:
        with self.database.connect(write=True) as connection:
            repo = WorkspaceRepository(connection, self.user_id)
            self.require(repo.issue(issue_id), "Ticket introuvable.")
            comment = self.require(repo.comment(issue_id, comment_id), "Commentaire introuvable.")
            if not comment["canEdit"]:
                raise DomainError(403, "Seul l’auteur peut modifier ce commentaire.")
            return repo.update_comment(issue_id, comment_id, body)

    def delete_comment(self, issue_id: int, comment_id: int) -> None:
        with self.database.connect(write=True) as connection:
            repo = WorkspaceRepository(connection, self.user_id)
            self.require(repo.issue(issue_id), "Ticket introuvable.")
            comment = self.require(repo.comment(issue_id, comment_id), "Commentaire introuvable.")
            if not comment["canDelete"]:
                raise DomainError(403, "Vous ne pouvez pas supprimer ce commentaire.")
            repo.delete_comment(issue_id, comment_id)
