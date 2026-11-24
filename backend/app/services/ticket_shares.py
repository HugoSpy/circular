"""Explicit, read-only access to a ticket without access to its project."""
from backend.app.db.session import timestamp
from backend.app.repositories.workspace import WorkspaceRepository
from backend.app.services.scope import scoped_connection
from backend.app.services.workspace import DomainError, WorkspaceService


class TicketShares:
    def __init__(self, database, user_id, workspace_id):
        self.database = database
        self.user_id = user_id
        self.workspace_id = workspace_id

    def shared(self, repo, reference):
        join = """SELECT i.id FROM issue_shares s JOIN issues i ON i.id = s.issue_id
            JOIN projects p ON p.id = i.project_id AND p.workspace_id = s.workspace_id
            WHERE s.workspace_id = ? AND s.user_id = ?"""
        if str(reference).isascii() and str(reference).isdigit() and 0 < int(reference) <= 9223372036854775807:
            equality, value = "i.id", int(reference)
        else:
            equality, value = "i.identifier", str(reference).upper()
        row = repo.connection.execute(join + " AND " + equality + " = ?", (self.workspace_id, self.user_id, value)).fetchone()
        if row is None:
            return None
        # This repository is reachable only for the ticket explicitly granted above.
        scoped = WorkspaceRepository(repo.connection, None, self.workspace_id)
        ticket = WorkspaceService.require(scoped.issue(row["id"]), "Ticket introuvable.")
        ticket["isFavorite"] = False
        comments = [{**entry, "canEdit": False, "canDelete": False} for entry in scoped.comments(row["id"])]
        return {"ticket": ticket, "comments": comments, "activity": scoped.activity(row["id"])}

    def get(self, ticket_id):
        with scoped_connection(self.database, self.user_id, self.workspace_id) as connection:
            repo = WorkspaceRepository(connection, self.user_id, self.workspace_id)
            return WorkspaceService.require(self.shared(repo, ticket_id), "Ticket introuvable.")

    def list(self, after=0, limit=30):
        with scoped_connection(self.database, self.user_id, self.workspace_id) as connection:
            rows = connection.execute("""SELECT i.id, i.identifier, i.title, i.status
                FROM issue_shares s JOIN issues i ON i.id = s.issue_id
                JOIN projects p ON p.id = i.project_id AND p.workspace_id = s.workspace_id
                WHERE s.workspace_id = ? AND s.user_id = ? AND i.id > ? AND i.archived_at IS NULL ORDER BY i.id LIMIT ?""",
                (self.workspace_id, self.user_id, after, limit + 1)).fetchall()
            return {"items": [dict(row) for row in rows[:limit]], "nextCursor": rows[limit - 1]["id"] if len(rows) > limit else None}

    @staticmethod
    def recipient(repo, recipient_id):
        if recipient_id == repo.user_id:
            raise DomainError(422, "Choisissez un autre membre de l’espace.")
        lock = " FOR KEY SHARE OF m" if getattr(repo.connection, "dialect", "sqlite") == "postgresql" else ""
        row = repo.connection.execute("""SELECT u.id, COALESCE(NULLIF(u.display_name, ''), u.username) AS name
            FROM workspace_members m JOIN users u ON u.id = m.user_id
            WHERE m.workspace_id = ? AND m.user_id = ?""" + lock, (repo.workspace_id, recipient_id)).fetchone()
        return WorkspaceService.require(row, "Membre introuvable.")

    def apply(self, repo, ticket, recipient_id, remove):
        WorkspaceService.owner(repo.project(ticket["projectId"]))
        self.recipient(repo, recipient_id)
        if remove:
            changed = repo.connection.execute("DELETE FROM issue_shares WHERE workspace_id = ? AND issue_id = ? AND user_id = ?",
                                              (self.workspace_id, ticket["id"], recipient_id)).rowcount
        else:
            changed = repo.connection.execute("""INSERT INTO issue_shares (workspace_id, issue_id, user_id, granted_by, created_at)
                VALUES (?, ?, ?, ?, ?) ON CONFLICT (issue_id, user_id) DO NOTHING""",
                (self.workspace_id, ticket["id"], recipient_id, self.user_id, timestamp())).rowcount
        if changed:
            repo.add_activity(ticket["id"], "updated", "Partage du ticket retiré." if remove else "Lecture du ticket partagée.")
