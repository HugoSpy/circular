"""Domain validation and transactions for local preferences and saved configurations."""
from backend.app.db.session import Database
from backend.app.repositories.preferences import PreferencesRepository
from backend.app.repositories.workspace import WorkspaceRepository
from backend.app.schemas.preferences import Settings
from backend.app.services.workspace import WorkspaceService


class PreferencesService:
    def __init__(self, database: Database, user_id: int | None = None):
        self.database = database
        self.user_id = user_id

    @staticmethod
    def validate_filters(repo: WorkspaceRepository, filters: dict) -> None:
        references = {"labelIds": filters.get("labelIds", [])}
        if filters.get("projectId"):
            references["projectId"] = int(filters["projectId"])
        WorkspaceService.validate_references(repo, references)

    def settings(self) -> dict:
        with self.database.connect() as connection:
            return PreferencesRepository(connection, self.user_id).settings() or Settings().model_dump()

    def update_settings(self, data: dict) -> dict:
        with self.database.connect(write=True) as connection:
            repo = PreferencesRepository(connection, self.user_id)
            repo.lock_settings()
            if "filters" in data:
                self.validate_filters(WorkspaceRepository(connection, self.user_id), data["filters"])
            current = repo.settings() or Settings().model_dump()
            return repo.save_settings({**current, **data})

    def views(self) -> list[dict]:
        with self.database.connect() as connection:
            return PreferencesRepository(connection, self.user_id).views()

    def create_view(self, data: dict) -> dict:
        with self.database.connect(write=True) as connection:
            self.validate_filters(WorkspaceRepository(connection, self.user_id), data["filters"])
            return PreferencesRepository(connection, self.user_id).create_view(data)

    def update_view(self, view_id: int, data: dict) -> dict:
        with self.database.connect(write=True) as connection:
            repo = PreferencesRepository(connection, self.user_id)
            current = WorkspaceService.require(repo.view(view_id), "Vue introuvable.")
            if "filters" in data:
                self.validate_filters(WorkspaceRepository(connection, self.user_id), data["filters"])
            return repo.update_view(view_id, {**current, **data})

    def delete_view(self, view_id: int) -> None:
        with self.database.connect(write=True) as connection:
            repo = PreferencesRepository(connection, self.user_id)
            WorkspaceService.require(repo.view(view_id), "Vue introuvable.")
            repo.delete_view(view_id)

    def templates(self) -> list[dict]:
        with self.database.connect() as connection:
            return PreferencesRepository(connection, self.user_id).templates()

    def create_template(self, data: dict) -> dict:
        with self.database.connect(write=True) as connection:
            WorkspaceService.validate_references(WorkspaceRepository(connection, self.user_id), data)
            return PreferencesRepository(connection, self.user_id).create_template(data)

    def update_template(self, template_id: int, data: dict) -> dict:
        with self.database.connect(write=True) as connection:
            repo = PreferencesRepository(connection, self.user_id)
            current = WorkspaceService.require(repo.template(template_id), "Modèle introuvable.")
            WorkspaceService.validate_references(WorkspaceRepository(connection, self.user_id), data)
            return repo.update_template(template_id, {**current, **data})

    def delete_template(self, template_id: int) -> None:
        with self.database.connect(write=True) as connection:
            repo = PreferencesRepository(connection, self.user_id)
            WorkspaceService.require(repo.template(template_id), "Modèle introuvable.")
            repo.delete_template(template_id)
