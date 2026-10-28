"""SQL persistence only. Transactions are owned by the service layer."""
import sqlite3
import unicodedata
from backend.app.db.session import timestamp


def normalize(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def search_text(identifier: str, title: str, description: str) -> str:
    return normalize("\n".join((identifier, title, description)))


class WorkspaceRepository:
    def __init__(self, connection: sqlite3.Connection, user_id: int | None = None):
        self.connection = connection
        self.user_id = user_id

    def access_clause(self, alias: str = "p") -> tuple[str, list]:
        if self.user_id is None:
            return "1 = 1", []
        return f"({alias}.owner_user_id = ? OR EXISTS (SELECT 1 FROM project_members pm WHERE pm.project_id = {alias}.id AND pm.user_id = ?))", [self.user_id, self.user_id]

    def lock_issue(self, issue_id: int) -> None:
        if getattr(self.connection, "dialect", "sqlite") == "postgresql":
            access, values = self.access_clause()
            self.connection.execute(f"SELECT id FROM issues WHERE id = ? AND project_id IN (SELECT p.id FROM projects p WHERE {access}) FOR UPDATE", [issue_id, *values]).fetchone()

    def lock_project(self, project_id: int) -> None:
        if getattr(self.connection, "dialect", "sqlite") == "postgresql":
            access, values = self.access_clause()
            self.connection.execute(f"SELECT p.id FROM projects p WHERE p.id = ? AND {access} FOR UPDATE", [project_id, *values]).fetchone()

    def project(self, project_id: int) -> dict | None:
        access, values = self.access_clause()
        if not self.connection.execute(f"SELECT id FROM projects p WHERE p.id = ? AND {access}", [project_id, *values]).fetchone():
            return None
        row = self.connection.execute("""SELECT p.id, p.name, p.key, p.description, p.color, p.status, p.due_date AS dueDate,
            p.created_at AS createdAt, COUNT(i.id) AS issueCount,
            COALESCE(SUM(CASE WHEN i.status = 'done' THEN 1 ELSE 0 END), 0) AS doneCount
            FROM projects p LEFT JOIN issues i ON i.project_id = p.id WHERE p.id = ? GROUP BY p.id""", (project_id,)).fetchone()
        result = dict(row) if row else None
        if result is not None:
            owner = self.connection.execute("SELECT owner_user_id FROM projects WHERE id = ?", (project_id,)).fetchone()[0]
            result["role"] = "owner" if self.user_id is None or owner == self.user_id else "member"
        return result

    def projects(self) -> list[dict]:
        access, values = self.access_clause()
        return [self.project(row["id"]) for row in self.connection.execute(f"SELECT id FROM projects p WHERE {access} ORDER BY id", values)]

    def create_project(self, data: dict) -> dict:
        self.connection.execute("INSERT INTO project_sequences(project_key) VALUES (?) ON CONFLICT DO NOTHING", (data["key"],))
        result = self.connection.execute("INSERT INTO projects(name, key, description, color, status, due_date, created_at, owner_user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (data["name"], data["key"], data["description"], data["color"], data.get("status", "planned"), data.get("dueDate"), timestamp(), self.user_id))
        return self.project(result.lastrowid)

    def update_project(self, project_id: int, data: dict) -> dict:
        self.connection.execute("UPDATE projects SET name = ?, description = ?, color = ?, status = ?, due_date = ? WHERE id = ?",
            (data["name"], data["description"], data["color"], data["status"], data["dueDate"], project_id))
        return self.project(project_id)

    def delete_project(self, project_id: int) -> None:
        self.connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    def issue(self, issue_id: int) -> dict | None:
        row = self.connection.execute("""SELECT id, identifier, title, description, project_id AS projectId,
            status, priority, due_date AS dueDate, is_favorite AS isFavorite, created_at AS createdAt, updated_at AS updatedAt FROM issues WHERE id = ?""", (issue_id,)).fetchone()
        if not row:
            return None
        issue = dict(row)
        if not self.project(issue["projectId"]):
            return None
        issue["isFavorite"] = bool(issue["isFavorite"]) if self.user_id is None else bool(self.connection.execute("SELECT 1 FROM issue_favorites WHERE issue_id = ? AND user_id = ?", (issue_id, self.user_id)).fetchone())
        issue["labels"] = [self.decode_label(label) for label in self.connection.execute("""SELECT l.id, l.name, l.color, l.description, l.owner_user_id
            FROM labels l JOIN issue_labels il ON il.label_id = l.id WHERE il.issue_id = ? ORDER BY l.name""", (issue_id,))]
        return issue

    def issues(self, filters: dict) -> list[dict]:
        clauses, values = [], []
        if self.user_id is not None:
            access, access_values = self.access_clause()
            clauses.append(f"project_id IN (SELECT p.id FROM projects p WHERE {access})")
            values.extend(access_values)
        for name, column in (("projectId", "project_id"),):
            if filters.get(name) is not None:
                clauses.append(f"{column} = ?")
                values.append(filters[name])
        for single, plural in (("status", "statuses"), ("priority", "priorities")):
            chosen = filters.get(plural) or ([filters[single]] if filters.get(single) else [])
            if chosen:
                clauses.append(f"{single} IN ({','.join('?' for _ in chosen)})")
                values.extend(chosen)
        if filters.get("labelIds"):
            labels = filters["labelIds"]
            clauses.append(f"EXISTS (SELECT 1 FROM issue_labels il WHERE il.issue_id = issues.id AND il.label_id IN ({','.join('?' for _ in labels)}))")
            values.extend(labels)
        if filters.get("favoritesOnly"):
            if self.user_id is None:
                clauses.append("is_favorite = 1")
            else:
                clauses.append("EXISTS (SELECT 1 FROM issue_favorites fav WHERE fav.issue_id = issues.id AND fav.user_id = ?)")
                values.append(self.user_id)
        if filters.get("q"):
            clauses.append("search_text LIKE ? ESCAPE '\\'")
            literal = normalize(filters["q"].strip()).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            values.append(f"%{literal}%")
        condition = " WHERE " + " AND ".join(clauses) if clauses else ""
        columns = {"createdAt": "created_at", "updatedAt": "updated_at", "title": "lower(title)",
                   "priority": "CASE priority WHEN 'none' THEN 0 WHEN 'low' THEN 1 WHEN 'medium' THEN 2 WHEN 'high' THEN 3 ELSE 4 END",
                   "dueDate": "due_date"}
        ordering = columns[filters.get("sortBy", "createdAt")]
        direction = "ASC" if filters.get("direction") == "asc" else "DESC"
        nulls = "due_date IS NULL ASC, " if filters.get("sortBy") == "dueDate" else ""
        ids = self.connection.execute("SELECT id FROM issues" + condition + f" ORDER BY {nulls}{ordering} {direction}, id {direction}", values).fetchall()
        return [self.issue(row["id"]) for row in ids]

    def create_issue(self, data: dict) -> dict:
        key = self.connection.execute("SELECT key FROM projects WHERE id = ?", (data["projectId"],)).fetchone()["key"]
        number = self.connection.execute("UPDATE project_sequences SET last_number = last_number + 1 WHERE project_key = ? RETURNING last_number", (key,)).fetchone()[0]
        identifier, now = f"{key}-{number}", timestamp()
        result = self.connection.execute("""INSERT INTO issues(identifier, title, description, project_id, status, priority, due_date, is_favorite, search_text, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (identifier, data["title"], data["description"], data["projectId"], data["status"], data["priority"], data.get("dueDate"), int(data.get("isFavorite", False)), search_text(identifier, data["title"], data["description"]), now, now))
        self.replace_labels(result.lastrowid, data["labelIds"])
        if self.user_id is not None and data.get("isFavorite"):
            self.set_favorite(result.lastrowid, True)
        self.add_activity(result.lastrowid, "created", "Ticket créé.")
        return self.issue(result.lastrowid)

    def replace_labels(self, issue_id: int, label_ids: list[int]) -> None:
        self.connection.execute("DELETE FROM issue_labels WHERE issue_id = ?", (issue_id,))
        self.connection.executemany("INSERT INTO issue_labels VALUES (?, ?)", [(issue_id, label_id) for label_id in label_ids])

    def update_issue(self, issue_id: int, data: dict) -> dict:
        self.connection.execute("""UPDATE issues SET title = ?, description = ?, project_id = ?,
            status = ?, priority = ?, due_date = ?, is_favorite = ?, search_text = ?, updated_at = ? WHERE id = ?""",
            (data["title"], data["description"], data["projectId"], data["status"], data["priority"],
             data["dueDate"], int(data["isFavorite"]),
             search_text(data["identifier"], data["title"], data["description"]), timestamp(), issue_id))
        if "labelIds" in data:
            self.replace_labels(issue_id, data["labelIds"])
        if self.user_id is not None:
            self.set_favorite(issue_id, data["isFavorite"])
        return self.issue(issue_id)

    def set_favorite(self, issue_id: int, value: bool) -> None:
        if self.user_id is None:
            self.connection.execute("UPDATE issues SET is_favorite = ? WHERE id = ?", (int(value), issue_id))
        elif value:
            self.connection.execute("INSERT INTO issue_favorites(issue_id, user_id) VALUES (?, ?) ON CONFLICT DO NOTHING", (issue_id, self.user_id))
        else:
            self.connection.execute("DELETE FROM issue_favorites WHERE issue_id = ? AND user_id = ?", (issue_id, self.user_id))

    def delete_issue(self, issue_id: int) -> None:
        self.connection.execute("DELETE FROM issues WHERE id = ?", (issue_id,))

    def label(self, label_id: int) -> dict | None:
        return next((label for label in self.labels() if label["id"] == label_id), None)

    def decode_label(self, row) -> dict:
        result = dict(row)
        owner = result.pop("owner_user_id")
        result["canEdit"] = self.user_id is None or owner == self.user_id
        return result

    def labels(self) -> list[dict]:
        condition, values = "", []
        if self.user_id is not None:
            access, values = self.access_clause()
            condition = f"WHERE l.owner_user_id = ? OR EXISTS (SELECT 1 FROM issue_labels il JOIN issues i ON i.id = il.issue_id JOIN projects p ON p.id = i.project_id WHERE il.label_id = l.id AND {access})"
            values = [self.user_id, *values]
        return [self.decode_label(row) for row in self.connection.execute(f"SELECT l.id, l.name, l.color, l.description, l.owner_user_id FROM labels l {condition} ORDER BY normalized_name", values)]

    def label_key(self, name: str) -> str:
        return f"{self.user_id}:{normalize(name)}" if self.user_id is not None else normalize(name)

    def label_by_name(self, name: str) -> dict | None:
        row = self.connection.execute("SELECT id, name, color, description, owner_user_id FROM labels WHERE normalized_name = ?", (self.label_key(name),)).fetchone()
        return self.decode_label(row) if row else None

    def create_label(self, data: dict) -> dict:
        result = self.connection.execute("INSERT INTO labels(name, normalized_name, color, description, owner_user_id) VALUES (?, ?, ?, ?, ?)",
            (data["name"], self.label_key(data["name"]), data["color"], data.get("description", ""), self.user_id))
        return self.label(result.lastrowid)

    def update_label(self, label_id: int, data: dict) -> dict:
        self.connection.execute("UPDATE labels SET name = ?, normalized_name = ?, color = ?, description = ? WHERE id = ?",
            (data["name"], self.label_key(data["name"]), data["color"], data["description"], label_id))
        return self.label(label_id)

    def delete_label(self, label_id: int) -> None:
        self.connection.execute("DELETE FROM labels WHERE id = ?", (label_id,))

    def comments(self, issue_id: int) -> list[dict]:
        return [self.comment(issue_id, row["id"]) for row in self.connection.execute("SELECT id FROM comments WHERE issue_id = ? ORDER BY id", (issue_id,))]

    def create_comment(self, issue_id: int, body: str) -> dict:
        now = timestamp()
        result = self.connection.execute("INSERT INTO comments(issue_id, body, created_at, author_user_id) VALUES (?, ?, ?, ?)", (issue_id, body, now, self.user_id))
        self.connection.execute("UPDATE issues SET updated_at = ? WHERE id = ?", (now, issue_id))
        self.add_activity(issue_id, "comment_created", "Commentaire ajouté.")
        return self.comment(issue_id, result.lastrowid)

    def comment(self, issue_id: int, comment_id: int) -> dict | None:
        row = self.connection.execute("SELECT id, issue_id AS issueId, body, created_at AS createdAt, author_user_id FROM comments WHERE issue_id = ? AND id = ?", (issue_id, comment_id)).fetchone()
        if not row:
            return None
        result = dict(row)
        author = result.pop("author_user_id")
        result["author"] = self.person(author)
        result["canEdit"] = self.user_id is None or author == self.user_id
        project = self.connection.execute("SELECT p.owner_user_id FROM issues i JOIN projects p ON p.id = i.project_id WHERE i.id = ?", (issue_id,)).fetchone()
        result["canDelete"] = result["canEdit"] or project[0] == self.user_id
        return result

    def person(self, user_id: int | None) -> dict | None:
        row = self.connection.execute("SELECT id, username FROM users WHERE id = ?", (user_id,)).fetchone() if user_id else None
        return dict(row) if row else None

    def update_comment(self, issue_id: int, comment_id: int, body: str) -> dict:
        self.connection.execute("UPDATE comments SET body = ? WHERE issue_id = ? AND id = ?", (body, issue_id, comment_id))
        self.connection.execute("UPDATE issues SET updated_at = ? WHERE id = ?", (timestamp(), issue_id))
        self.add_activity(issue_id, "comment_updated", "Commentaire modifié.")
        return self.comment(issue_id, comment_id)

    def delete_comment(self, issue_id: int, comment_id: int) -> None:
        self.connection.execute("DELETE FROM comments WHERE issue_id = ? AND id = ?", (issue_id, comment_id))
        self.connection.execute("UPDATE issues SET updated_at = ? WHERE id = ?", (timestamp(), issue_id))
        self.add_activity(issue_id, "comment_deleted", "Commentaire supprimé.")

    def add_activity(self, issue_id: int, kind: str, body: str) -> None:
        self.connection.execute("INSERT INTO issue_activity(issue_id, kind, body, created_at, actor_user_id) VALUES (?, ?, ?, ?, ?)", (issue_id, kind, body, timestamp(), self.user_id))

    def activity(self, issue_id: int) -> list[dict]:
        results = []
        for row in self.connection.execute("SELECT id, issue_id AS issueId, kind, body, created_at AS createdAt, actor_user_id FROM issue_activity WHERE issue_id = ? ORDER BY id", (issue_id,)):
            item = dict(row)
            item["actor"] = self.person(item.pop("actor_user_id"))
            results.append(item)
        return results
