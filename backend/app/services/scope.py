"""Keep the selected membership valid for a complete unit of work."""
from contextlib import contextmanager


@contextmanager
def scoped_connection(database, user_id: int | None, workspace_id: int | None, *, write: bool = False):
    with database.connect(write=write) as connection:
        if workspace_id is not None and user_id is not None:
            lock = " FOR KEY SHARE" if write and getattr(connection, "dialect", "sqlite") == "postgresql" else ""
            membership = connection.execute("SELECT user_id FROM workspace_members WHERE workspace_id = ? AND user_id = ?" + lock, (workspace_id, user_id)).fetchone()
            if not membership:
                from backend.app.services.workspace import DomainError
                raise DomainError(404, "Espace introuvable.")
        yield connection
