"""Driver parity, real PostgreSQL transactions, and migration/import checks.

Set CIRCULAR_TEST_POSTGRES_URL_FILE to an ignored secret file to run PostgreSQL
checks. Every test uses a unique disposable schema, never public business data.
"""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import sqlite3
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from backend.app.main import create_app
from backend.app.db.postgres import Record, compile_sql
from backend.app.db.session import Database
from backend.import_sqlite import import_sqlite
from backend.app.repositories.workspace import WorkspaceRepository
from backend.app.repositories.preferences import PreferencesRepository
from backend.app.schemas.workspace import ProjectCreate, IssueCreate, LabelCreate
from backend.app.schemas.preferences import Settings, ViewCreate, TemplateCreate


def test_postgres_sql_driver_translation_preserves_literals():
    sql = "SELECT '?' AS literalValue, 'AS camelCase', 100 AS total, ? AS userId -- ? AS untouchedAlias\n WHERE value LIKE ? ESCAPE '\\' AND rate = '50%'"
    compiled = compile_sql(sql)
    assert "'?' AS \"literalValue\"" in compiled
    assert "'AS camelCase'" in compiled
    assert "100 AS total" in compiled
    assert '%s AS "userId"' in compiled
    assert "-- ? AS untouchedAlias" in compiled
    assert "LIKE %s ESCAPE '\\'" in compiled
    assert "'50%%'" in compiled
    assert compile_sql("SELECT '50%'", parameters=False) == "SELECT '50%'"


def test_postgres_rows_support_dictionary_and_positional_access():
    row = Record({"id": 12, "username": "exemple"})
    assert row[0] == row["id"] == 12
    assert row[1] == row["username"] == "exemple"
    assert dict(row) == {"id": 12, "username": "exemple"}


@pytest.fixture
def postgres_url():
    file = os.environ.get("CIRCULAR_TEST_POSTGRES_URL_FILE")
    if not file:
        pytest.skip("PostgreSQL integration requires CIRCULAR_TEST_POSTGRES_URL_FILE.")
    import psycopg
    from psycopg import sql

    base = Path(file).read_text(encoding="utf-8").strip()
    schema = "circular_test_" + uuid4().hex
    with psycopg.connect(base, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    parsed = urlsplit(base)
    query = dict(parse_qsl(parsed.query))
    query["options"] = "-csearch_path=" + schema
    isolated = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))
    try:
        yield isolated
    finally:
        with psycopg.connect(base, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_postgres_migrations_aliases_ids_and_transaction_rollback(postgres_url):
    database = Database(postgres_url)
    assert database.dialect == "postgresql"
    Database(postgres_url)  # migrations are idempotent
    with database.connect() as connection:
        versions = connection.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
        assert len(versions) == len(list((Path(__file__).parents[1] / "backend/app/db/migrations").glob("[0-9]*.sql")))
    with database.connect(write=True) as connection:
        result = connection.execute("INSERT INTO users(email, username, normalized_username, password_hash, created_at) VALUES (?, ?, ?, ?, ?)", ("one@epita.fr", "Exemple", "exemple", "not-a-real-password-hash", "2026-10-28T00:00:00Z"))
        assert isinstance(result.lastrowid, int)
        user_id = result.lastrowid
        assert connection.execute("SELECT id AS userId, created_at AS createdAt FROM users WHERE id = ?", (user_id,)).fetchone()["userId"] == user_id
    with pytest.raises(sqlite3.IntegrityError):
        with database.connect(write=True) as connection:
            connection.execute("UPDATE users SET username = ? WHERE id = ?", ("Must roll back", user_id))
            connection.execute("INSERT INTO users(email, username, normalized_username, password_hash, created_at) VALUES (?, ?, ?, ?, ?)", ("one@epita.fr", "Duplicate", "duplicate", "fake", "2026-10-28T00:00:00Z"))
    with database.connect() as connection:
        assert connection.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()[0] == "Exemple"


def test_postgres_concurrent_counters_are_atomic(postgres_url):
    database = Database(postgres_url)
    with database.connect(write=True) as connection:
        connection.execute("INSERT INTO project_sequences(project_key) VALUES (?)", ("TEST",))
    def next_number(_index):
        with database.connect(write=True) as connection:
            return connection.execute("UPDATE project_sequences SET last_number = last_number + 1 WHERE project_key = ? RETURNING last_number", ("TEST",)).fetchone()[0]
    with ThreadPoolExecutor(max_workers=6) as pool:
        values = list(pool.map(next_number, range(18)))
    assert sorted(values) == list(range(1, 19))


def test_postgres_concurrent_migration_startup_is_idempotent(postgres_url):
    with ThreadPoolExecutor(max_workers=4) as pool:
        databases = list(pool.map(lambda _index: Database(postgres_url), range(4)))
    with databases[0].connect() as connection:
        count = connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
    assert count == len(list((Path(__file__).parents[1] / "backend/app/db/migrations").glob("[0-9]*.sql")))


def test_postgres_repository_workflows_and_personal_state(postgres_url):
    database = Database(postgres_url)
    with database.connect(write=True) as connection:
        users = []
        for number in (1, 2):
            result = connection.execute("INSERT INTO users(email, username, normalized_username, password_hash, created_at) VALUES (?, ?, ?, ?, ?)", (f"person{number}@epita.fr", f"Person{number}", f"person{number}", "fake-hash", "2026-10-28T00:00:00Z"))
            users.append(result.lastrowid)
        owner, outsider = users
        repo = WorkspaceRepository(connection, owner)
        target = repo.create_project(ProjectCreate(name="Projet PostgreSQL", key="PGSQL").model_dump())
        label = repo.create_label(LabelCreate(name="Données", color="#F2CF63").model_dump())
        ticket = repo.create_issue(IssueCreate(title="ÉCRAN 100%_prêt", projectId=target["id"], labelIds=[label["id"]], isFavorite=True, dueDate="2027-05-20").model_dump())
        assert ticket["identifier"] == "PGSQL-1"
        assert ticket["isFavorite"] is True
        assert repo.project(target["id"])["issueCount"] == 1
        assert [item["id"] for item in repo.issues({"q": "écran 100%_", "favoritesOnly": True, "sortBy": "title"})] == [ticket["id"]]
        assert WorkspaceRepository(connection, outsider).issues({}) == []
        connection.execute("INSERT INTO project_members(project_id, user_id) VALUES (?, ?)", (target["id"], outsider))
        member_repo = WorkspaceRepository(connection, outsider)
        assert member_repo.issue(ticket["id"])["isFavorite"] is False
        comment = member_repo.create_comment(ticket["id"], "Commentaire partagé")
        assert comment["author"]["id"] == outsider
        assert repo.comment(ticket["id"], comment["id"])["canEdit"] is False
        assert repo.comment(ticket["id"], comment["id"])["canDelete"] is True
        assert len(repo.activity(ticket["id"])) == 2
        prefs = PreferencesRepository(connection, owner)
        prefs.save_settings(Settings(fontSize="large").model_dump())
        prefs.create_view(ViewCreate(name="Vue personnelle").model_dump())
        template = prefs.create_template(TemplateCreate(name="Modèle personnel", projectId=target["id"], labelIds=[label["id"]]).model_dump())
        assert template["projectId"] == target["id"]
        assert PreferencesRepository(connection, outsider).settings() is None
        assert PreferencesRepository(connection, outsider).views() == []
        assert PreferencesRepository(connection, outsider).templates() == []
    reopened = Database(postgres_url)
    with reopened.connect() as connection:
        assert PreferencesRepository(connection, owner).settings()["fontSize"] == "large"
        assert WorkspaceRepository(connection, outsider).comments(ticket["id"])[0]["body"] == "Commentaire partagé"


def test_sqlite_import_preserves_ids_and_refuses_overwrite(postgres_url, tmp_path):
    source = Database(tmp_path / "source.sqlite")
    with source.connect(write=True) as connection:
        connection.execute("INSERT INTO project_sequences(project_key, last_number) VALUES (?, ?)", ("OLD", 7))
        connection.execute("INSERT INTO projects(id, name, key, description, color, created_at) VALUES (?, ?, ?, ?, ?, ?)", (7, "Ancien projet", "OLD", "Historique", "#F2CF63", "2026-10-28T00:00:00Z"))
    destination = Database(postgres_url)
    assert import_sqlite(source.path, destination)["projects"] == 1
    with destination.connect(write=True) as connection:
        assert connection.execute("SELECT name FROM projects WHERE id = ?", (7,)).fetchone()[0] == "Ancien projet"
        connection.execute("INSERT INTO project_sequences(project_key) VALUES (?)", ("NEW",))
        result = connection.execute("INSERT INTO projects(name, key, description, color, created_at) VALUES (?, ?, ?, ?, ?)", ("Nouveau", "NEW", "", "#F2CF63", "2026-10-28T00:00:00Z"))
        assert result.lastrowid > 7
    with pytest.raises(ValueError, match="destination contient"):
        import_sqlite(source.path, destination)
    with source.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 1


def test_original_sqlite_v1_import_without_migrating_source(postgres_url, tmp_path):
    source = tmp_path / "original-v1.sqlite"
    initial = Path(__file__).parents[1] / "backend/app/db/migrations/001_initial.sql"
    with sqlite3.connect(source) as connection:
        connection.executescript(initial.read_text(encoding="utf-8"))
        connection.execute("CREATE TABLE schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
        connection.execute("INSERT INTO schema_migrations VALUES (?, ?)", (initial.name, "2026-10-15T00:00:00Z"))
        connection.execute("INSERT INTO project_sequences(project_key, last_number) VALUES (?, ?)", ("VONE", 1))
        connection.execute("INSERT INTO projects(id, name, key, created_at) VALUES (?, ?, ?, ?)", (1, "Projet v1", "VONE", "2026-10-15T00:00:00Z"))
    before = source.read_bytes()
    destination = Database(postgres_url)
    assert import_sqlite(source, destination)["projects"] == 1
    assert source.read_bytes() == before
    with destination.connect() as connection:
        project = connection.execute("SELECT status, due_date, owner_user_id FROM projects WHERE id = 1").fetchone()
        assert dict(project) == {"status": "planned", "due_date": None, "owner_user_id": None}


def test_sqlite_import_constraint_error_rolls_back_all_business_rows(postgres_url, tmp_path):
    source = Database(tmp_path / "invalid-source.sqlite")
    with sqlite3.connect(source.path) as connection:
        # A damaged source with disabled foreign keys must not partially import.
        connection.execute("INSERT INTO project_sequences(project_key) VALUES ('VALID')")
        connection.execute("INSERT INTO projects(id, name, key, created_at) VALUES (1, 'Valide', 'VALID', '2026-10-28T00:00:00Z')")
        connection.execute("INSERT INTO issues(identifier, title, project_id, status, priority, search_text, created_at, updated_at) VALUES ('BAD-1', 'Invalide', 999, 'todo', 'none', 'bad', '2026-10-28T00:00:00Z', '2026-10-28T00:00:00Z')")
    destination = Database(postgres_url)
    with pytest.raises(sqlite3.IntegrityError):
        import_sqlite(source.path, destination)
    with destination.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM project_sequences").fetchone()[0] == 0


def test_postgres_authenticated_api_collaboration_and_restart(postgres_url):
    app = create_app(postgres_url)
    origin = "http://127.0.0.1:4310"
    with TestClient(app, base_url=origin, headers={"Content-Type": "application/json"}) as alice, TestClient(app, base_url=origin, headers={"Content-Type": "application/json"}) as bob, TestClient(app, base_url=origin, headers={"Content-Type": "application/json"}) as outsider:
        assert alice.get("/api/projects").status_code == 401
        users = []
        for client, name in ((alice, "AlicePG"), (bob, "BobPG"), (outsider, "CharliePG")):
            response = client.post("/api/auth/register", json={"username": name, "email": name.lower() + "@epita.fr", "password": "Une phrase PostgreSQL fictive 42!"})
            assert response.status_code == 201
            client.headers["X-CSRF-Token"] = response.json()["csrfToken"]
            users.append(response.json()["user"])
        response = alice.post("/api/projects", json={"name": "Projet privé PostgreSQL", "key": "PGAPI"})
        assert response.status_code == 201
        project = response.json()
        label = alice.post("/api/labels", json={"name": "Travail partagé"}).json()
        response = alice.post("/api/issues", json={"projectId": project["id"], "title": "ÉCRAN 100%_prêt", "labelIds": [label["id"]], "isFavorite": True})
        assert response.status_code == 201
        ticket = response.json()
        assert bob.get("/api/projects").json() == []
        assert bob.get(f'/api/issues/{ticket["id"]}').status_code == 404
        invite = alice.post(f'/api/projects/{project["id"]}/invitations', json={"email": users[1]["email"]})
        assert invite.status_code == 201
        invitation_id = invite.json()["id"]
        assert bob.get("/api/invitations").json()[0]["projectName"] == project["name"]
        assert outsider.post(f"/api/invitations/{invitation_id}/accept", json={}).status_code == 404
        assert bob.post(f"/api/invitations/{invitation_id}/accept", json={}).status_code == 204
        assert bob.get("/api/projects").json()[0]["role"] == "member"
        assert bob.patch(f'/api/projects/{project["id"]}', json={"name": "Unauthorized"}).status_code == 403
        assert bob.get(f'/api/issues/{ticket["id"]}').json()["isFavorite"] is False
        assert bob.patch(f'/api/issues/{ticket["id"]}', json={"status": "done"}).status_code == 200
        comment = bob.post(f'/api/issues/{ticket["id"]}/comments', json={"body": "Un commentaire PostgreSQL"})
        assert comment.status_code == 201
        comment = comment.json()
        assert comment["author"]["username"] == users[1]["username"]
        assert alice.patch(f'/api/issues/{ticket["id"]}/comments/{comment["id"]}', json={"body": "Forbidden edit"}).status_code == 403
        assert bob.patch(f'/api/issues/{ticket["id"]}/comments/{comment["id"]}', json={"body": "Commentaire corrigé"}).status_code == 200
        assert len(alice.get(f'/api/issues/{ticket["id"]}/activity').json()) == 4
        assert [item["id"] for item in alice.get("/api/issues", params={"q": "écran 100%_", "status": "done", "favoritesOnly": True}).json()] == [ticket["id"]]
        assert alice.get("/api/projects").json()[0]["doneCount"] == 1
        assert alice.patch("/api/settings", json={"fontSize": "large"}).status_code == 200
        assert bob.get("/api/settings").json()["fontSize"] == "default"
        view = alice.post("/api/views", json={"name": "Ma vue privée"}).json()
        template = alice.post("/api/templates", json={"name": "Mon modèle", "projectId": project["id"], "labelIds": [label["id"]]}).json()
        assert bob.get("/api/views").json() == []
        assert bob.get("/api/templates").json() == []
        assert bob.patch(f'/api/views/{view["id"]}', json={"name": "Not mine"}).status_code == 404
        assert alice.patch(f'/api/views/{view["id"]}', json={"name": "Vue renommée"}).status_code == 200
        assert alice.patch(f'/api/templates/{template["id"]}', json={"title": "Titre prérempli"}).status_code == 200
        assert alice.delete(f'/api/projects/{project["id"]}/members/{users[1]["id"]}').status_code == 204
        assert bob.get(f'/api/issues/{ticket["id"]}').status_code == 404
        assert bob.post(f'/api/issues/{ticket["id"]}/comments', json={"body": "No more access"}).status_code == 404
        cookies = dict(alice.cookies)
        csrf = alice.headers["X-CSRF-Token"]
    with TestClient(create_app(postgres_url), base_url=origin, cookies=cookies, headers={"Content-Type": "application/json", "X-CSRF-Token": csrf}) as restarted:
        assert restarted.get("/api/auth/me").json()["user"]["id"] == users[0]["id"]
        assert restarted.get("/api/settings").json()["fontSize"] == "large"
        assert restarted.get(f'/api/issues/{ticket["id"]}').json()["status"] == "done"
        assert restarted.get(f'/api/issues/{ticket["id"]}/comments').json()[0]["body"] == "Commentaire corrigé"
        assert restarted.delete(f'/api/issues/{ticket["id"]}/comments/{comment["id"]}').status_code == 204
        assert restarted.delete(f'/api/issues/{ticket["id"]}').status_code == 204
        assert restarted.delete(f'/api/templates/{template["id"]}').status_code == 204
        assert restarted.delete(f'/api/views/{view["id"]}').status_code == 204
        assert restarted.delete(f'/api/labels/{label["id"]}').status_code == 204
        assert restarted.delete(f'/api/projects/{project["id"]}').status_code == 204
    with TestClient(create_app(postgres_url), base_url=origin, cookies=cookies) as restarted:
        assert restarted.get("/api/projects").json() == []
        assert restarted.get("/api/issues").json() == []
        assert restarted.get("/api/views").json() == []
        assert restarted.get("/api/templates").json() == []
