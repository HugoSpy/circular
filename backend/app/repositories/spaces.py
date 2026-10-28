"""Workspace containers, memberships and invitations persistence."""
from backend.app.db.session import timestamp


class SpacesRepository:
    def __init__(self, connection, user_id: int):
        self.connection, self.user_id = connection, user_id

    def workspace(self, workspace_id: int, *, lock: bool = False) -> dict | None:
        if lock and getattr(self.connection, "dialect", "sqlite") == "postgresql":
            # Keep foreign-key inserts compatible while serializing administration;
            # a member writer may already hold a key-share lock on its membership.
            self.connection.execute("SELECT id FROM workspaces WHERE id = ? FOR NO KEY UPDATE", (workspace_id,)).fetchone()
        row = self.connection.execute("""SELECT w.id, w.name, w.slug, m.role,
            m.onboarding_completed AS onboardingCompleted, w.initial_project_id AS initialProjectId
            FROM workspaces w JOIN workspace_members m ON m.workspace_id = w.id
            WHERE w.id = ? AND m.user_id = ?""", (workspace_id, self.user_id)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["onboardingCompleted"] = bool(result["onboardingCompleted"])
        if result["initialProjectId"]:
            from backend.app.repositories.workspace import WorkspaceRepository
            if not WorkspaceRepository(self.connection, self.user_id, workspace_id).project(result["initialProjectId"]):
                result["initialProjectId"] = None
        return result

    def workspaces(self) -> list[dict]:
        return [self.workspace(row[0]) for row in self.connection.execute("SELECT workspace_id FROM workspace_members WHERE user_id = ? ORDER BY workspace_id", (self.user_id,))]

    def create(self, name: str, slug: str) -> dict:
        workspace_id = self.connection.execute("INSERT INTO workspaces(name, slug, owner_user_id, created_at) VALUES (?, ?, ?, ?)", (name, slug, self.user_id, timestamp())).lastrowid
        self.connection.execute("INSERT INTO workspace_members(workspace_id, user_id, role, onboarding_completed, joined_at) VALUES (?, ?, 'owner', 0, ?)", (workspace_id, self.user_id, timestamp()))
        return self.workspace(workspace_id)

    def update(self, workspace_id: int, data: dict) -> dict:
        self.connection.execute("UPDATE workspaces SET name = ?, slug = ? WHERE id = ?", (data["name"], data["slug"], workspace_id))
        return self.workspace(workspace_id)

    def complete_onboarding(self, workspace_id: int) -> dict:
        self.connection.execute("UPDATE workspace_members SET onboarding_completed = 1 WHERE workspace_id = ? AND user_id = ?", (workspace_id, self.user_id))
        return self.workspace(workspace_id)

    def members(self, workspace_id: int) -> list[dict]:
        return [dict(row) for row in self.connection.execute("""SELECT u.id, u.username, u.email, u.display_name AS displayName,
            u.title, m.role FROM workspace_members m JOIN users u ON u.id = m.user_id WHERE m.workspace_id = ? ORDER BY u.username""", (workspace_id,))]

    def join(self, workspace_id: int) -> dict:
        self.connection.execute("""INSERT INTO workspace_members(workspace_id, user_id, role, joined_at) VALUES (?, ?, 'member', ?)
            ON CONFLICT(workspace_id, user_id) DO UPDATE SET role = CASE WHEN workspace_members.role = 'guest' THEN 'member' ELSE workspace_members.role END""", (workspace_id, self.user_id, timestamp()))
        return self.workspace(workspace_id)

    def invitations(self, workspace_id: int) -> list[dict]:
        return [dict(row) for row in self.connection.execute("SELECT id, email, created_at AS createdAt, expires_at AS expiresAt FROM workspace_invitations WHERE workspace_id = ? AND expires_at > ? ORDER BY id", (workspace_id, timestamp()))]

    def invite(self, workspace_id: int, email: str, expires_at: str) -> dict:
        self.connection.execute("""INSERT INTO workspace_invitations(workspace_id, email, inviter_id, created_at, expires_at) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(workspace_id, email) DO UPDATE SET inviter_id = excluded.inviter_id, created_at = excluded.created_at, expires_at = excluded.expires_at""", (workspace_id, email, self.user_id, timestamp(), expires_at))
        return next(item for item in self.invitations(workspace_id) if item["email"] == email)

    def inbox(self, email: str) -> list[dict]:
        return [dict(row) for row in self.connection.execute("""SELECT i.id, i.workspace_id AS workspaceId, w.name AS workspaceName,
            u.display_name AS inviterName, i.email, i.expires_at AS expiresAt FROM workspace_invitations i JOIN workspaces w ON w.id = i.workspace_id
            JOIN users u ON u.id = i.inviter_id WHERE i.email = ? AND i.expires_at > ? ORDER BY i.id""", (email, timestamp()))]

    def invitation(self, invitation_id: int, email: str, *, lock: bool = True) -> dict | None:
        locking = " FOR UPDATE" if lock and getattr(self.connection, "dialect", "sqlite") == "postgresql" else ""
        row = self.connection.execute("SELECT * FROM workspace_invitations WHERE id = ? AND email = ? AND expires_at > ?" + locking, (invitation_id, email, timestamp())).fetchone()
        return dict(row) if row else None

    def lock_invitation_workspace(self, workspace_id: int) -> None:
        if getattr(self.connection, "dialect", "sqlite") == "postgresql":
            self.connection.execute("SELECT id FROM workspaces WHERE id = ? FOR NO KEY UPDATE", (workspace_id,)).fetchone()

    def links(self, workspace_id: int) -> list[dict]:
        return [dict(row) for row in self.connection.execute("SELECT id, created_at AS createdAt, expires_at AS expiresAt FROM workspace_invite_links WHERE workspace_id = ? AND expires_at > ? ORDER BY id", (workspace_id, timestamp()))]

    def link(self, token_hash: str, *, lock: bool = False) -> dict | None:
        locking = " FOR UPDATE" if lock and getattr(self.connection, "dialect", "sqlite") == "postgresql" else ""
        row = self.connection.execute("SELECT * FROM workspace_invite_links WHERE token_hash = ? AND expires_at > ?" + locking, (token_hash, timestamp())).fetchone()
        return dict(row) if row else None
