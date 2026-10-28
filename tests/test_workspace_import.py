"""Workspace data survives upgrades, explicit claims and SQLite → PostgreSQL import."""
import json
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient

from backend.app.core.passwords import hash_password
from backend.app.db.session import Database
from backend.app.main import create_app
from backend.app.schemas.preferences import Settings
from backend.claim_legacy import claim_legacy
from backend.import_sqlite import import_sqlite
from tests.test_postgres import postgres_url  # noqa: F401; isolated schema fixture

ORIGIN = "http://127.0.0.1:4310"
PASSWORD = "Une phrase de test import espaces 42!"
CREATED = "2026-10-28T00:00:00Z"


def login(client, username):
    result = client.post("/api/auth/login", json={"identifier": username, "password": PASSWORD})
    assert result.status_code == 200, result.text
    client.headers["X-CSRF-Token"] = result.json()["csrfToken"]
    return result.json()["user"]


def register(client, username):
    result = client.post("/api/auth/register", json={"username": username, "email": username.lower() + "@epita.fr", "password": PASSWORD})
    assert result.status_code == 201, result.text
    client.headers["X-CSRF-Token"] = result.json()["csrfToken"]
    return result.json()["user"]


def test_import_v4_assigns_spaces_without_expanding_project_access(postgres_url, tmp_path):
    source = tmp_path / "v4.sqlite"
    migrations = Path(__file__).parents[1] / "backend/app/db/migrations"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
        for name in ("001_initial.sql", "002_preferences_workflows.sql", "003_auth.sql", "004_sharing.sql"):
            connection.executescript((migrations / name).read_text(encoding="utf-8"))
            connection.execute("INSERT INTO schema_migrations VALUES (?, ?)", (name, CREATED))
        for user_id, name in ((1, "OwnerImport"), (2, "GuestImport")):
            connection.execute("INSERT INTO users(id,email,username,normalized_username,password_hash,created_at) VALUES (?,?,?,?,?,?)",
                               (user_id, name.lower() + "@epita.fr", name, name.lower(), hash_password(PASSWORD), CREATED))
        for project_id, key in ((10, "SHARED"), (11, "PRIVATE")):
            connection.execute("INSERT INTO project_sequences(project_key) VALUES (?)", (key,))
            connection.execute("INSERT INTO projects(id,name,key,created_at,owner_user_id) VALUES (?,?,?,?,1)", (project_id, key, key, CREATED))
        connection.execute("INSERT INTO project_members VALUES (10,2)")
        connection.execute("INSERT INTO labels(id,name,normalized_name,color,owner_user_id) VALUES (12,'Import','1:import','#F2CF63',1)")
        connection.execute("INSERT INTO user_settings VALUES (1,?)", (Settings(fontSize="large").model_dump_json(),))
    before = source.read_bytes()
    target = Database(postgres_url)
    assert import_sqlite(source, target)["projects"] == 2
    assert source.read_bytes() == before

    app = create_app(postgres_url)
    with TestClient(app, base_url=ORIGIN) as owner, TestClient(app, base_url=ORIGIN) as guest:
        imported_user = login(owner, "OwnerImport")
        assert imported_user["displayName"] == "OwnerImport"
        assert imported_user["profileCompleted"] is True
        login(guest, "GuestImport")
        owner_spaces = owner.get("/api/workspaces").json()
        assert len(owner_spaces) == 1
        workspace_id = owner_spaces[0]["id"]
        guest_space = next(item for item in guest.get("/api/workspaces").json() if item["id"] == workspace_id)
        assert guest_space["role"] == "guest"
        for client in (owner, guest):
            client.headers["X-Workspace-Id"] = str(workspace_id)
        assert {item["id"] for item in owner.get("/api/projects").json()} == {10, 11}
        assert [item["id"] for item in guest.get("/api/projects").json()] == [10]
        assert guest.patch("/api/projects/11", json={"name": "Interdit"}).status_code == 404
        assert owner.get("/api/settings").json()["fontSize"] == "large"
        assert owner.get("/api/labels").json()[0]["id"] == 12
    Database(postgres_url)
    with target.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0] == 1
        assert connection.execute("SELECT visibility FROM projects WHERE id=11").fetchone()[0] == "private"


def test_workspace_snapshot_round_trip_preserves_ids_members_and_preferences(postgres_url, tmp_path):
    source = tmp_path / "workspaces.sqlite"
    app = create_app(source)
    with TestClient(app, base_url=ORIGIN) as owner, TestClient(app, base_url=ORIGIN) as member:
        owner_user = register(owner, "OwnerSnapshot")
        register(member, "MemberSnapshot")
        created = owner.post("/api/workspaces", json={"name": "Espace importé", "slug": "espace-importe"})
        assert created.status_code == 201, created.text
        workspace = created.json()["workspace"]
        wid = workspace["id"]
        owner.headers["X-Workspace-Id"] = str(wid)
        invite = owner.post(f"/api/workspaces/{wid}/invitations", json={"email": "membersnapshot@epita.fr"})
        assert invite.status_code == 201, invite.text
        assert member.post(f'/api/workspace-invitations/{invite.json()["id"]}/accept', json={}).status_code == 200
        assert owner.patch("/api/settings", json={"fontSize": "large"}).status_code == 200
        assert owner.post(f"/api/workspaces/{wid}/onboarding/complete", json={}).status_code == 200
        issues = owner.get("/api/issues").json()
        assert len(issues) == 3
        ticket = issues[0]
        comment = owner.post(f'/api/issues/{ticket["id"]}/comments', json={"body": "Commentaire avant migration"})
        assert comment.status_code == 201
        old_cookie = dict(owner.cookies)
    with sqlite3.connect(source) as checkpoint:
        checkpoint.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    before = source.read_bytes()
    destination = Database(postgres_url)
    counts = import_sqlite(source, destination)
    assert source.read_bytes() == before
    assert counts["workspaces"] == 1
    assert counts["workspace_members"] == 2

    imported_app = create_app(postgres_url)
    with TestClient(imported_app, base_url=ORIGIN, cookies=old_cookie) as owner, TestClient(imported_app, base_url=ORIGIN) as member:
        assert owner.get("/api/auth/me").status_code == 401  # Sessions never migrate.
        assert login(owner, "OwnerSnapshot")["id"] == owner_user["id"]
        login(member, "MemberSnapshot")
        for client in (owner, member):
            client.headers["X-Workspace-Id"] = str(wid)
            assert {item["id"] for item in client.get("/api/issues").json()} == {item["id"] for item in issues}
        assert owner.get("/api/settings").json()["fontSize"] == "large"
        assert member.get("/api/settings").json()["fontSize"] == "default"
        assert owner.get("/api/workspaces").json()[0]["onboardingCompleted"] is True
        assert member.get(f'/api/issues/{ticket["id"]}/comments').json()[0]["body"] == "Commentaire avant migration"
        next_space = owner.post("/api/workspaces", json={"name": "Suivant", "slug": "suivant", "includeWelcomeIssues": False})
        assert next_space.status_code == 201, next_space.text
        assert next_space.json()["workspace"]["id"] > wid


def test_explicit_legacy_claim_creates_accessible_workspace_once(tmp_path):
    path = tmp_path / "unclaimed.sqlite"
    database = Database(path)
    with database.connect(write=True) as connection:
        connection.execute("INSERT INTO project_sequences(project_key) VALUES ('LEGACY')")
        connection.execute("INSERT INTO projects(name,key,created_at) VALUES ('Projet historique','LEGACY',?)", (CREATED,))
        connection.execute("INSERT INTO labels(name,normalized_name,color) VALUES ('Historique','historique','#F2CF63')")
        connection.execute("INSERT INTO workspace_settings VALUES (1,?)", (json.dumps(Settings(fontSize="large").model_dump()),))
    with TestClient(create_app(path), base_url=ORIGIN) as owner:
        user = register(owner, "LegacyClaim")
        assert owner.get("/api/workspaces").json() == []
        assert owner.get("/api/projects").json() == []
        assert claim_legacy(database, user["id"]) == 1
        spaces = owner.get("/api/workspaces").json()
        assert len(spaces) == 1
        owner.headers["X-Workspace-Id"] = str(spaces[0]["id"])
        assert owner.get("/api/projects").json()[0]["name"] == "Projet historique"
        assert owner.get("/api/labels").json()[0]["name"] == "Historique"
        assert owner.get("/api/settings").json()["fontSize"] == "large"
        assert claim_legacy(database, user["id"]) == 0
        assert len(owner.get("/api/workspaces").json()) == 1
