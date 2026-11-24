"""Explicit document sharing for members who do not have access to the Docs workspace."""
from backend.app.db.session import timestamp
from backend.app.repositories.docs import ACTIVE_PAGE
from backend.app.services.scope import scoped_connection
from backend.app.services.workspace import DomainError, WorkspaceService


class DocumentShares:
    def __init__(self, database, user_id, workspace_id):
        self.database = database
        self.user_id = user_id
        self.workspace_id = workspace_id

    def get(self, page_id):
        with scoped_connection(self.database, self.user_id, self.workspace_id) as connection:
            row = connection.execute(f"""SELECT p.id, p.title, p.markdown, p.revision FROM docs_page_shares s
                JOIN docs_pages p ON p.workspace_id = s.workspace_id AND p.id = s.page_id
                WHERE s.workspace_id = ? AND s.user_id = ? AND s.page_id = ? AND {ACTIVE_PAGE}""",
                (self.workspace_id, self.user_id, page_id)).fetchone()
            return dict(WorkspaceService.require(row, "Document introuvable."))

    def list(self, cursor=""):
        with scoped_connection(self.database, self.user_id, self.workspace_id) as connection:
            rows = connection.execute(f"""SELECT p.id, p.title FROM docs_page_shares s
                JOIN docs_pages p ON p.workspace_id = s.workspace_id AND p.id = s.page_id
                WHERE s.workspace_id = ? AND s.user_id = ? AND p.id > ? AND {ACTIVE_PAGE}
                ORDER BY p.id LIMIT 31""", (self.workspace_id, self.user_id, cursor)).fetchall()
            return {"items": [dict(row) for row in rows[:30]], "nextCursor": rows[29]["id"] if len(rows) > 30 else None}

    def asset(self, asset_id):
        with scoped_connection(self.database, self.user_id, self.workspace_id) as connection:
            row = connection.execute(f"""SELECT a.* FROM docs_assets a WHERE a.workspace_id = ? AND a.id = ? AND EXISTS (
                SELECT 1 FROM docs_page_shares s JOIN docs_pages p ON p.workspace_id = s.workspace_id AND p.id = s.page_id
                JOIN docs_asset_links l ON l.workspace_id = p.workspace_id AND l.page_id = p.id AND l.asset_id = a.id
                WHERE s.workspace_id = a.workspace_id AND s.user_id = ? AND {ACTIVE_PAGE})""",
                (self.workspace_id, asset_id, self.user_id)).fetchone()
            return dict(WorkspaceService.require(row, "Pièce jointe introuvable."))

    def apply(self, repo, page_id, recipient, remove):
        if repo.access != "owner":
            raise DomainError(403, "Seul un propriétaire de Docs peut partager cet élément.")
        if recipient == self.user_id:
            raise DomainError(422, "Choisissez un autre membre de l’espace.")
        WorkspaceService.require(repo.page(page_id), "Document introuvable.")
        WorkspaceService.require(repo.execute("SELECT 1 FROM workspace_members WHERE workspace_id = ? AND user_id = ?", recipient).fetchone(),
                                 "Membre introuvable.")
        if remove:
            repo.execute("DELETE FROM docs_page_shares WHERE workspace_id = ? AND page_id = ? AND user_id = ?", page_id, recipient)
        else:
            repo.execute("""INSERT INTO docs_page_shares (workspace_id, page_id, user_id, granted_by, created_at)
                VALUES (?, ?, ?, ?, ?) ON CONFLICT (workspace_id, page_id, user_id) DO NOTHING""",
                page_id, recipient, self.user_id, timestamp())
