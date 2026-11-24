"""Document comments, mentions and workspace-scoped access."""
from backend.app.db.session import timestamp
from backend.app.repositories.docs import ACTIVE_PAGE
from backend.app.services.workspace import DomainError


def found(row):
    if row is None:
        raise DomainError(404, "Document introuvable.")
    return row


COMMENT_FIELDS = """
    SELECT c.id, c.author_id AS authorId, c.body, c.revision, c.created_at AS createdAt,
           COALESCE(NULLIF(u.display_name, ''), u.username) AS author,
           m.recipient_id AS mentionId,
           COALESCE(NULLIF(recipient.display_name, ''), recipient.username) AS mentionName
    FROM docs_comments c
    JOIN users u ON u.id = c.author_id
    LEFT JOIN docs_mentions m ON m.workspace_id = c.workspace_id AND m.comment_id = c.id
    LEFT JOIN users recipient ON recipient.id = m.recipient_id
    WHERE c.workspace_id = ? AND c.page_id = ?
"""


class DocsCollaboration:
    def access_members(self):
        with self.repository(permission="owner") as repo:
            return [dict(row) for row in repo.execute("""
                SELECT u.id, COALESCE(NULLIF(u.display_name, ''), u.username) AS name,
                       CASE WHEN m.role = 'owner' THEN 'owner' ELSE m.docs_role END AS role
                FROM workspace_members m JOIN users u ON u.id = m.user_id
                WHERE m.workspace_id = ? AND m.role IN ('owner', 'member')
                ORDER BY u.username, u.id
            """)]

    def change_access(self, user_id, role):
        with self.repository(write=True, permission="owner") as repo:
            changed = repo.connection.execute("""
                UPDATE workspace_members SET docs_role = ?
                WHERE workspace_id = ? AND user_id = ? AND role = 'member'
            """, (role, self.workspace_id, user_id))
            if not changed.rowcount:
                raise DomainError(404, "Membre introuvable.")

    def comments(self, page_id):
        with self.repository() as repo:
            found(repo.page(page_id))
            items = [dict(row) for row in repo.execute(COMMENT_FIELDS + " ORDER BY c.created_at, c.id", page_id)]
            people = [] if repo.access == "reader" else [dict(row) for row in repo.execute("""
                SELECT u.id, COALESCE(NULLIF(u.display_name, ''), u.username) AS name
                FROM workspace_members m JOIN users u ON u.id = m.user_id
                WHERE m.workspace_id = ? AND m.role IN ('owner', 'member') AND u.id <> ?
                ORDER BY u.username, u.id
            """, self.user_id)]
            return {"items": items, "people": people}

    def write_comment(self, page_id, comment_id, data, *, create=False):
        with self.repository(write=True) as repo:
            return self.write_comment_in(repo, page_id, comment_id, data, create=create)

    def write_comment_in(self, repo, page_id, comment_id, data, *, create=False):
        found(repo.page(page_id))
        old = repo.execute(COMMENT_FIELDS + " AND c.id = ?", page_id, comment_id).fetchone()
        if old and old["authorId"] != self.user_id:
            raise DomainError(403, "Seul l’auteur peut modifier ce commentaire.")
        if create and old:
            if (old["body"], old["mentionId"]) == (data.body, data.mentionId):
                return dict(old)
            raise DomainError(409, "Ce commentaire a déjà été publié.")
        if not create and found(old)["revision"] != data.revision:
            raise DomainError(409, "Ce commentaire a changé. Actualisez la discussion.")
        recipient = data.mentionId
        if recipient is not None and (recipient == self.user_id or not repo.execute("""
            SELECT 1 FROM workspace_members
            WHERE workspace_id = ? AND user_id = ? AND role IN ('owner', 'member')
        """, recipient).fetchone()):
            raise DomainError(404, "Cette personne ne peut pas lire cette page.")
        if create:
            inserted = repo.execute("""
                INSERT INTO docs_comments (workspace_id, id, page_id, author_id, body, created_at)
                VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (workspace_id, id) DO NOTHING
            """, comment_id, page_id, self.user_id, data.body, timestamp())
            if not inserted.rowcount:
                raise DomainError(409, "Ce commentaire a déjà été publié.")
        else:
            repo.connection.execute("""
                UPDATE docs_comments SET body = ?, revision = revision + 1
                WHERE workspace_id = ? AND id = ?
            """, (data.body, self.workspace_id, comment_id))
        if not old or old["mentionId"] != recipient:
            repo.execute("DELETE FROM docs_mentions WHERE workspace_id = ? AND comment_id = ?", comment_id)
            if recipient is not None:
                repo.execute("""
                    INSERT INTO docs_mentions (workspace_id, comment_id, recipient_id, created_at)
                    VALUES (?, ?, ?, ?)
                """, comment_id, recipient, timestamp())
        return dict(found(repo.execute(COMMENT_FIELDS + " AND c.id = ?", page_id, comment_id).fetchone()))

    def delete_comment(self, page_id, comment_id):
        with self.repository(write=True) as repo:
            found(repo.page(page_id))
            old = found(repo.execute(COMMENT_FIELDS + " AND c.id = ?", page_id, comment_id).fetchone())
            if old["authorId"] != self.user_id and repo.access != "owner":
                raise DomainError(403, "Vous ne pouvez pas supprimer ce commentaire.")
            repo.execute("DELETE FROM docs_comments WHERE workspace_id = ? AND id = ?", comment_id)

    def notifications(self):
        with self.repository() as repo:
            return [dict(row) for row in repo.execute(f"""
                SELECT m.comment_id AS commentId, c.page_id AS pageId, p.title AS title,
                       COALESCE(NULLIF(u.display_name, ''), u.username) AS author, m.read_at AS readAt
                FROM docs_mentions m
                JOIN docs_comments c ON c.workspace_id = m.workspace_id AND c.id = m.comment_id
                JOIN docs_pages p ON p.workspace_id = c.workspace_id AND p.id = c.page_id
                JOIN users u ON u.id = c.author_id
                WHERE m.workspace_id = ? AND m.recipient_id = ? AND {ACTIVE_PAGE}
                    AND (m.snoozed_until IS NULL OR m.snoozed_until <= ?)
                ORDER BY m.created_at DESC, m.comment_id
            """, self.user_id, timestamp())]

    def mark_read(self, comment_id):
        with self.repository(write=True, permission="reader") as repo:
            self.update_notification_in(repo, comment_id, read=True)

    def update_notification_in(self, repo, comment_id, *, read, snooze=None):
        mention = found(repo.execute("""
            SELECT c.page_id FROM docs_mentions m JOIN docs_comments c
            ON c.workspace_id = m.workspace_id AND c.id = m.comment_id
            WHERE m.workspace_id = ? AND m.comment_id = ? AND m.recipient_id = ?
        """, comment_id, self.user_id).fetchone())
        found(repo.page(mention["page_id"]))
        repo.connection.execute("""
            UPDATE docs_mentions SET read_at = COALESCE(read_at, ?), snoozed_until = ?
            WHERE workspace_id = ? AND comment_id = ? AND recipient_id = ?
        """, (timestamp() if read else None, snooze, self.workspace_id, comment_id, self.user_id))
