"""Idempotent assignment of pre-workspace data, inside the caller's transaction.

Project visibility and explicit project memberships are deliberately preserved.
An invited project participant receives only a container-level guest membership.
"""
import json
from backend.app.db.session import timestamp


def backfill_workspaces(connection) -> None:
    owners = connection.execute("""SELECT id, username FROM users WHERE id IN (
        SELECT owner_user_id FROM projects WHERE workspace_id IS NULL
        UNION SELECT owner_user_id FROM labels WHERE workspace_id IS NULL
        UNION SELECT owner_user_id FROM saved_views WHERE workspace_id IS NULL
        UNION SELECT owner_user_id FROM issue_templates WHERE workspace_id IS NULL) ORDER BY id""").fetchall()
    for owner in owners:
        slug = f'personnel-{owner["id"]}'
        existing = connection.execute("SELECT id FROM workspaces WHERE legacy_owner_user_id = ?", (owner["id"],)).fetchone()
        if existing:
            workspace_id = existing[0]
        else:
            suffix = 0
            while connection.execute("SELECT 1 FROM workspaces WHERE slug = ?", (slug,)).fetchone():
                suffix += 1
                slug = f'personnel-{owner["id"]}-{suffix}'
            workspace_id = connection.execute("INSERT INTO workspaces(name, slug, owner_user_id, legacy_owner_user_id, created_at) VALUES (?, ?, ?, ?, ?)",
                (f'Espace de {owner["username"]}', slug, owner["id"], owner["id"], timestamp())).lastrowid
        connection.execute("INSERT INTO workspace_members(workspace_id, user_id, role, onboarding_completed, joined_at) VALUES (?, ?, 'owner', 1, ?) ON CONFLICT DO NOTHING", (workspace_id, owner["id"], timestamp()))
        for table in ("projects", "labels", "saved_views", "issue_templates"):
            connection.execute(f"UPDATE {table} SET workspace_id = ? WHERE owner_user_id = ? AND workspace_id IS NULL", (workspace_id, owner["id"]))
        settings = connection.execute("SELECT payload FROM user_settings WHERE user_id = ?", (owner["id"],)).fetchone()
        if settings:
            connection.execute("INSERT INTO workspace_user_settings(workspace_id, user_id, payload) VALUES (?, ?, ?) ON CONFLICT DO NOTHING", (workspace_id, owner["id"], settings[0]))

    for row in connection.execute("SELECT DISTINCT p.workspace_id, m.user_id FROM project_members m JOIN projects p ON p.id = m.project_id WHERE p.workspace_id IS NOT NULL").fetchall():
        connection.execute("INSERT INTO workspace_members(workspace_id, user_id, role, joined_at) VALUES (?, ?, 'guest', ?) ON CONFLICT DO NOTHING", (row[0], row[1], timestamp()))

    # A formerly personal label may have been attached to another owner's project.
    # Copy that taxonomy into the target container, keeping all issue associations.
    copies = {}
    for row in connection.execute("""SELECT il.issue_id, l.*, p.workspace_id AS target_workspace
        FROM issue_labels il JOIN labels l ON l.id = il.label_id JOIN issues i ON i.id = il.issue_id
        JOIN projects p ON p.id = i.project_id WHERE p.workspace_id IS NOT NULL
        AND (l.workspace_id IS NULL OR l.workspace_id <> p.workspace_id)""").fetchall():
        key = (row["id"], row["target_workspace"])
        if key not in copies:
            copies[key] = connection.execute("""INSERT INTO labels(name, normalized_name, color, description, owner_user_id, workspace_id)
                VALUES (?, ?, ?, ?, ?, ?)""", (row["name"], f'workspace:{key[1]}:legacy:{key[0]}', row["color"], row["description"], row["owner_user_id"], key[1])).lastrowid
        connection.execute("DELETE FROM issue_labels WHERE issue_id = ? AND label_id = ?", (row["issue_id"], key[0]))
        connection.execute("INSERT INTO issue_labels(issue_id, label_id) VALUES (?, ?) ON CONFLICT DO NOTHING", (row["issue_id"], copies[key]))

    # Existing personal saved configurations retain valid references only inside
    # their assigned container. Unscoped user settings remain available to old clients.
    for row in connection.execute("SELECT id, workspace_id, filters FROM saved_views WHERE workspace_id IS NOT NULL").fetchall():
        filters = _filters(connection, row["workspace_id"], json.loads(row["filters"]))
        connection.execute("UPDATE saved_views SET filters = ? WHERE id = ?", (json.dumps(filters), row["id"]))
    for row in connection.execute("SELECT workspace_id, user_id, payload FROM workspace_user_settings").fetchall():
        payload = json.loads(row["payload"])
        if "filters" in payload:
            payload["filters"] = _filters(connection, row["workspace_id"], payload["filters"])
            connection.execute("UPDATE workspace_user_settings SET payload = ? WHERE workspace_id = ? AND user_id = ?", (json.dumps(payload), row["workspace_id"], row["user_id"]))
    connection.execute("""UPDATE issue_templates SET project_id = NULL WHERE workspace_id IS NOT NULL AND project_id IS NOT NULL
        AND NOT EXISTS(SELECT 1 FROM projects p WHERE p.id = issue_templates.project_id AND p.workspace_id = issue_templates.workspace_id)""")
    connection.execute("""DELETE FROM template_labels WHERE template_id IN (SELECT id FROM issue_templates WHERE workspace_id IS NOT NULL)
        AND NOT EXISTS(SELECT 1 FROM issue_templates t JOIN labels l ON l.workspace_id = t.workspace_id WHERE t.id = template_labels.template_id AND l.id = template_labels.label_id)""")


def _filters(connection, workspace_id: int, filters: dict) -> dict:
    if filters.get("projectId") and not connection.execute("SELECT 1 FROM projects WHERE id = ? AND workspace_id = ?", (int(filters["projectId"]), workspace_id)).fetchone():
        filters["projectId"] = ""
    filters["labelIds"] = [value for value in filters.get("labelIds", []) if connection.execute("SELECT 1 FROM labels WHERE id = ? AND workspace_id = ?", (value, workspace_id)).fetchone()]
    return filters
