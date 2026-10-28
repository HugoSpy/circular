"""Membership and invitation persistence; access decisions live in SharingService."""
from backend.app.db.session import timestamp


class SharingRepository:
    def __init__(self, connection):
        self.connection = connection

    def members(self, project_id: int) -> list[dict]:
        members = [dict(row) for row in self.connection.execute("""SELECT u.id, u.email, u.username,
            CASE WHEN u.id = p.owner_user_id OR (p.visibility = 'workspace' AND EXISTS
                (SELECT 1 FROM workspace_members wm WHERE wm.workspace_id = p.workspace_id AND wm.user_id = u.id AND wm.role = 'owner')) THEN 'owner' ELSE 'member' END AS role,
            CASE WHEN p.visibility = 'workspace' AND EXISTS
                (SELECT 1 FROM workspace_members wm WHERE wm.workspace_id = p.workspace_id AND wm.user_id = u.id AND wm.role IN ('owner', 'member')) THEN 1 ELSE 0 END AS inherited
            FROM users u JOIN projects p ON p.id = ?
            WHERE (u.id = p.owner_user_id OR EXISTS
            (SELECT 1 FROM project_members m WHERE m.project_id = p.id AND m.user_id = u.id)
            OR (p.visibility = 'workspace' AND EXISTS (SELECT 1 FROM workspace_members wm WHERE wm.workspace_id = p.workspace_id AND wm.user_id = u.id AND wm.role IN ('owner', 'member'))))
            AND (p.workspace_id IS NULL OR EXISTS(SELECT 1 FROM workspace_members wm WHERE wm.workspace_id = p.workspace_id AND wm.user_id = u.id))
            ORDER BY u.username""", (project_id,))]
        for member in members:
            member["inherited"] = bool(member["inherited"])
        return members

    def recipient(self, email: str) -> dict | None:
        row = self.connection.execute("SELECT id FROM users WHERE email = ?", (email.casefold().strip(),)).fetchone()
        return dict(row) if row else None

    def invitations(self, project_id: int) -> list[dict]:
        return [dict(row) for row in self.connection.execute("""SELECT i.id, u.email, u.username, i.created_at AS createdAt
            FROM project_invitations i JOIN users u ON u.id = i.user_id WHERE project_id = ? ORDER BY i.id""", (project_id,))]

    def invite(self, project_id: int, user_id: int, inviter_id: int) -> dict:
        self.connection.execute("INSERT INTO project_invitations(project_id, user_id, inviter_id, created_at) VALUES (?, ?, ?, ?) ON CONFLICT(project_id, user_id) DO NOTHING", (project_id, user_id, inviter_id, timestamp()))
        return dict(self.connection.execute("""SELECT i.id, u.email, u.username, i.created_at AS createdAt
            FROM project_invitations i JOIN users u ON u.id = i.user_id WHERE project_id = ? AND user_id = ?""", (project_id, user_id)).fetchone())

    def inbox(self, user_id: int) -> list[dict]:
        return [dict(row) for row in self.connection.execute("""SELECT i.id, p.id AS projectId, p.name AS projectName, p.workspace_id AS workspaceId,
            u.username AS inviterName, i.created_at AS createdAt FROM project_invitations i
            JOIN projects p ON p.id = i.project_id JOIN users u ON u.id = i.inviter_id
            WHERE i.user_id = ? ORDER BY i.id""", (user_id,))]

    def invitation(self, invitation_id: int, user_id: int, *, lock: bool = True) -> dict | None:
        locking = " FOR UPDATE" if lock and getattr(self.connection, "dialect", "sqlite") == "postgresql" else ""
        row = self.connection.execute("SELECT id, project_id FROM project_invitations WHERE id = ? AND user_id = ?" + locking, (invitation_id, user_id)).fetchone()
        return dict(row) if row else None

    def lock_invitation_workspace(self, project_id: int) -> None:
        if getattr(self.connection, "dialect", "sqlite") == "postgresql":
            self.connection.execute("SELECT id FROM workspaces WHERE id = (SELECT workspace_id FROM projects WHERE id = ?) FOR NO KEY UPDATE", (project_id,)).fetchone()

    def accept(self, invitation: dict, user_id: int) -> None:
        self.connection.execute("INSERT INTO project_members(project_id, user_id) VALUES (?, ?) ON CONFLICT DO NOTHING", (invitation["project_id"], user_id))
        workspace = self.connection.execute("SELECT workspace_id FROM projects WHERE id = ?", (invitation["project_id"],)).fetchone()
        if workspace and workspace[0]:
            self.connection.execute("INSERT INTO workspace_members(workspace_id, user_id, role, joined_at) VALUES (?, ?, 'guest', ?) ON CONFLICT DO NOTHING", (workspace[0], user_id, timestamp()))
        self.connection.execute("DELETE FROM project_invitations WHERE id = ? AND user_id = ?", (invitation["id"], user_id))

    def decline(self, invitation_id: int, user_id: int) -> None:
        self.connection.execute("DELETE FROM project_invitations WHERE id = ? AND user_id = ?", (invitation_id, user_id))

    def revoke(self, project_id: int, invitation_id: int) -> bool:
        return self.connection.execute("DELETE FROM project_invitations WHERE project_id = ? AND id = ?", (project_id, invitation_id)).rowcount > 0

    def remove(self, project_id: int, user_id: int) -> bool:
        return self.connection.execute("DELETE FROM project_members WHERE project_id = ? AND user_id = ?", (project_id, user_id)).rowcount > 0

    def clear_personal_project_references(self, project_id: int, user_id: int) -> None:
        from backend.app.repositories.preferences import PreferencesRepository
        from backend.app.repositories.workspace import WorkspaceRepository
        scopes = [None, *[row[0] for row in self.connection.execute("SELECT workspace_id FROM workspace_members WHERE user_id = ?", (user_id,))]]
        for workspace_id in scopes:
            preferences = PreferencesRepository(self.connection, user_id, workspace_id)
            preferences.remove_filter_reference(project_id=project_id)
            visible_labels = {label["id"] for label in WorkspaceRepository(self.connection, user_id, workspace_id).labels()}
            settings = preferences.settings()
            if settings:
                settings["filters"]["labelIds"] = [label_id for label_id in settings["filters"]["labelIds"] if label_id in visible_labels]
                preferences.save_settings(settings)
            for view in preferences.views():
                view["filters"]["labelIds"] = [label_id for label_id in view["filters"]["labelIds"] if label_id in visible_labels]
                preferences.update_view(view["id"], view)
            for template in preferences.templates():
                preferences.replace_template_labels(template["id"], [label_id for label_id in template["labelIds"] if label_id in visible_labels])
        self.connection.execute("UPDATE issue_templates SET project_id = NULL WHERE owner_user_id = ? AND project_id = ?", (user_id, project_id))
        self.connection.execute("DELETE FROM issue_favorites WHERE user_id = ? AND issue_id IN (SELECT id FROM issues WHERE project_id = ?)", (user_id, project_id))
