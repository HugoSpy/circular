"""SQLite persistence of preferences and reusable workspace configurations."""
import json
import sqlite3


class PreferencesRepository:
    def __init__(self, connection: sqlite3.Connection, user_id: int | None = None):
        self.connection = connection
        self.user_id = user_id

    def scope(self) -> tuple[str, list]:
        return ("owner_user_id = ?", [self.user_id]) if self.user_id is not None else ("1 = 1", [])

    def lock_settings(self) -> None:
        # Lock the account, which exists even before its first settings row.
        if self.user_id is not None and getattr(self.connection, "dialect", "sqlite") == "postgresql":
            self.connection.execute("SELECT id FROM users WHERE id = ? FOR UPDATE", (self.user_id,)).fetchone()

    def settings(self) -> dict | None:
        row = self.connection.execute("SELECT payload FROM user_settings WHERE user_id = ?", (self.user_id,)).fetchone() if self.user_id is not None else self.connection.execute("SELECT payload FROM workspace_settings WHERE id = 1").fetchone()
        return json.loads(row["payload"]) if row else None

    def save_settings(self, data: dict) -> dict:
        if self.user_id is not None:
            self.connection.execute("INSERT INTO user_settings(user_id, payload) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET payload = excluded.payload", (self.user_id, json.dumps(data, ensure_ascii=False)))
        else:
            self.connection.execute("INSERT INTO workspace_settings(id, payload) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET payload = excluded.payload", (json.dumps(data, ensure_ascii=False),))
        return data

    @staticmethod
    def decode_view(row: sqlite3.Row | None) -> dict | None:
        return {"id": row["id"], "name": row["name"], "filters": json.loads(row["filters"]), "display": json.loads(row["display"])} if row else None

    def views(self) -> list[dict]:
        where, values = self.scope()
        return [self.decode_view(row) for row in self.connection.execute(f"SELECT * FROM saved_views WHERE {where} ORDER BY id", values)]

    def view(self, view_id: int) -> dict | None:
        where, values = self.scope()
        return self.decode_view(self.connection.execute(f"SELECT * FROM saved_views WHERE id = ? AND {where}", [view_id, *values]).fetchone())

    def create_view(self, data: dict) -> dict:
        result = self.connection.execute("INSERT INTO saved_views(name, filters, display, owner_user_id) VALUES (?, ?, ?, ?)", (data["name"], json.dumps(data["filters"]), json.dumps(data["display"]), self.user_id))
        return self.view(result.lastrowid)

    def update_view(self, view_id: int, data: dict) -> dict:
        self.connection.execute("UPDATE saved_views SET name = ?, filters = ?, display = ? WHERE id = ?", (data["name"], json.dumps(data["filters"]), json.dumps(data["display"]), view_id))
        return self.view(view_id)

    def delete_view(self, view_id: int) -> None:
        self.connection.execute("DELETE FROM saved_views WHERE id = ?", (view_id,))

    def template(self, template_id: int) -> dict | None:
        where, values = self.scope()
        row = self.connection.execute(f"SELECT id, name, title, description, project_id AS projectId, status, priority FROM issue_templates WHERE id = ? AND {where}", [template_id, *values]).fetchone()
        if not row:
            return None
        result = dict(row)
        result["labelIds"] = [label[0] for label in self.connection.execute("SELECT label_id FROM template_labels WHERE template_id = ? ORDER BY label_id", (template_id,))]
        return result

    def templates(self) -> list[dict]:
        where, values = self.scope()
        return [self.template(row["id"]) for row in self.connection.execute(f"SELECT id FROM issue_templates WHERE {where} ORDER BY id", values)]

    def replace_template_labels(self, template_id: int, label_ids: list[int]) -> None:
        self.connection.execute("DELETE FROM template_labels WHERE template_id = ?", (template_id,))
        self.connection.executemany("INSERT INTO template_labels VALUES (?, ?)", [(template_id, label_id) for label_id in label_ids])

    def create_template(self, data: dict) -> dict:
        result = self.connection.execute("INSERT INTO issue_templates(name, title, description, project_id, status, priority, owner_user_id) VALUES (?, ?, ?, ?, ?, ?, ?)", (data["name"], data["title"], data["description"], data["projectId"], data["status"], data["priority"], self.user_id))
        self.replace_template_labels(result.lastrowid, data["labelIds"])
        return self.template(result.lastrowid)

    def update_template(self, template_id: int, data: dict) -> dict:
        self.connection.execute("UPDATE issue_templates SET name = ?, title = ?, description = ?, project_id = ?, status = ?, priority = ? WHERE id = ?", (data["name"], data["title"], data["description"], data["projectId"], data["status"], data["priority"], template_id))
        self.replace_template_labels(template_id, data["labelIds"])
        return self.template(template_id)

    def delete_template(self, template_id: int) -> None:
        self.connection.execute("DELETE FROM issue_templates WHERE id = ?", (template_id,))

    def remove_filter_reference(self, *, project_id: int | None = None, label_id: int | None = None) -> None:
        """Remove stale IDs atomically with deletion of the referenced entity."""
        def clean(filters: dict) -> dict:
            result = dict(filters)
            if project_id is not None and result.get("projectId") == str(project_id):
                result["projectId"] = ""
            if label_id is not None:
                result["labelIds"] = [value for value in result.get("labelIds", []) if value != label_id]
            return result

        settings = self.settings()
        if settings:
            settings["filters"] = clean(settings["filters"])
            self.save_settings(settings)
        if self.user_id is None:
            for row in self.connection.execute("SELECT user_id, payload FROM user_settings"):
                payload = json.loads(row["payload"])
                payload["filters"] = clean(payload["filters"])
                PreferencesRepository(self.connection, row["user_id"]).save_settings(payload)
        for view in self.views():
            view["filters"] = clean(view["filters"])
            self.update_view(view["id"], view)
