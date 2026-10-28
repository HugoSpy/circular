import sqlite3
from concurrent.futures import ThreadPoolExecutor
import pytest
from tests.helpers import AuthenticatedTestClient as TestClient
from backend.app.main import create_app
from backend.app.db.session import Database
from backend.seed import seed_database


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "test.sqlite"), base_url="http://127.0.0.1:4310") as instance:
        yield instance


def project(client, key="TEST", name="Projet de test"):
    response = client.post("/api/projects", json={"name": name, "key": key, "description": "Projet fictif", "color": "#71d9b2"})
    assert response.status_code == 201, response.text
    return response.json()


def issue(client, project_id, **overrides):
    response = client.post("/api/issues", json={"title": "Un ticket", "description": "Description", "projectId": project_id, "status": "todo", "priority": "medium", "labelIds": [], **overrides})
    assert response.status_code == 201, response.text
    return response.json()


def test_vertical_slice_survives_database_reopening(tmp_path):
    database = tmp_path / "test.sqlite"
    with TestClient(create_app(database), base_url="http://127.0.0.1:4310") as client:
        project = client.post("/api/projects", json={"name": "Site démo", "key": "SITE", "description": "Un projet local", "color": "#71d9b2"})
        assert project.status_code == 201, project.text
        issue = client.post("/api/issues", json={"title": "Créer la page d’accueil", "description": "Premier ticket persistant", "projectId": project.json()["id"], "status": "todo", "priority": "medium", "labelIds": []})
        assert issue.status_code == 201, issue.text
        assert issue.json()["identifier"] == "SITE-1"
    with TestClient(create_app(database), base_url="http://127.0.0.1:4310") as restarted:
        response = restarted.get("/api/issues")
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["title"] == "Créer la page d’accueil"
        assert response.json()[0]["identifier"] == "SITE-1"
        assert restarted.get("/api/projects").json()[0]["issueCount"] == 1


def test_edit_comment_labels_and_counts(client):
    target = project(client)
    label = client.post("/api/labels", json={"name": "Interface", "color": "#123abc"}).json()
    item = issue(client, target["id"], labelIds=[label["id"]])
    assert item["labels"] == [label]
    updated = client.patch(f'/api/issues/{item["id"]}', json={"title": "Titre modifié", "description": "Nouveau texte", "status": "done", "priority": "urgent", "labelIds": []})
    assert updated.status_code == 200
    assert updated.json()["labels"] == []
    assert updated.json()["identifier"] == item["identifier"]
    assert updated.json()["title"] == "Titre modifié"
    comment = client.post(f'/api/issues/{item["id"]}/comments', json={"body": " Un commentaire sauvegardé. "})
    assert comment.status_code == 201
    assert comment.json()["body"] == "Un commentaire sauvegardé."
    assert client.get(f'/api/issues/{item["id"]}/comments').json() == [comment.json()]
    assert client.get("/api/projects").json()[0]["doneCount"] == 1
    response = client.patch(f'/api/projects/{target["id"]}', json={"name": "Nouveau nom", "description": "Modifiée", "color": "#ABCDEF"})
    assert response.status_code == 200
    assert response.json()["name"] == "Nouveau nom"
    assert response.json()["key"] == target["key"]
    assert client.get("/api/labels").json() == [label]


def test_filters_are_combined_and_search_is_literal_and_unicode_case_insensitive(client):
    alpha, beta = project(client, "ALPHA"), project(client, "BETA")
    first = issue(client, alpha["id"], title="ÉCRAN 100%_prêt", description="Une référence précise", status="in_progress", priority="high")
    issue(client, alpha["id"], title="écran secondaire", status="todo", priority="high")
    issue(client, beta["id"], title="Écran autre projet", status="in_progress", priority="high")
    for query in ("écran 100%_", "RÉFÉRENCE", first["identifier"].lower(), "%_", "100%"):
        result = client.get("/api/issues", params={"q": query}).json()
        assert [row["id"] for row in result] == [first["id"]]
    result = client.get("/api/issues", params={"q": "ÉCRAN", "projectId": alpha["id"], "status": "in_progress", "priority": "high"}).json()
    assert [row["id"] for row in result] == [first["id"]]
    assert client.get("/api/issues", params={"priority": "urgent"}).json() == []
    assert client.get("/api/issues", params={"q": "' OR 1=1 --"}).json() == []
    assert len(client.get("/api/issues", params={"q": "écran"}).json()) == 3


def test_identifier_is_stable_and_counters_never_reuse_deleted_numbers(client):
    alpha, beta = project(client, "ALPHA"), project(client, "BETA")
    first = issue(client, alpha["id"])
    moved = client.patch(f'/api/issues/{first["id"]}', json={"projectId": beta["id"]})
    assert moved.status_code == 200
    assert moved.json()["identifier"] == "ALPHA-1"
    assert client.delete(f'/api/projects/{alpha["id"]}').status_code == 204
    recreated = project(client, "ALPHA")
    second = issue(client, recreated["id"])
    assert second["identifier"] == "ALPHA-2"
    assert client.delete(f'/api/issues/{second["id"]}').status_code == 204
    assert issue(client, recreated["id"])["identifier"] == "ALPHA-3"
    assert issue(client, beta["id"])["identifier"] == "BETA-1"


def test_deletions_cascade_and_survive_reopening(tmp_path):
    database = tmp_path / "delete.sqlite"
    with TestClient(create_app(database), base_url="http://127.0.0.1:4310") as client:
        target = project(client)
        label = client.post("/api/labels", json={"name": "Bug"}).json()
        item = issue(client, target["id"], labelIds=[label["id"]])
        client.post(f'/api/issues/{item["id"]}/comments', json={"body": "À supprimer en cascade"})
        assert client.delete(f'/api/projects/{target["id"]}').status_code == 409
        assert client.delete(f'/api/issues/{item["id"]}').status_code == 204
        assert client.delete(f'/api/projects/{target["id"]}').status_code == 204
    with TestClient(create_app(database), base_url="http://127.0.0.1:4310") as restarted:
        assert restarted.get("/api/projects").json() == []
        assert restarted.get("/api/issues").json() == []
        assert restarted.get(f'/api/issues/{item["id"]}').status_code == 404
        assert restarted.get(f'/api/issues/{item["id"]}/comments').status_code == 404
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM comments").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM issue_labels").fetchone()[0] == 0
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("changes", [
    {"title": " "}, {"title": "x" * 241}, {"title": 42}, {"description": "x" * 20001},
    {"projectId": 0}, {"projectId": "1"}, {"projectId": True}, {"projectId": 999999},
    {"status": "unknown"}, {"priority": "critical"}, {"labelIds": [999999]}, {"labelIds": [1, 1]},
    {"labelIds": [True]}, {"labelIds": "bad"}, {"identifier": "HACK-99"}, {"title": None},
])
def test_invalid_issue_creation_has_no_side_effects(client, changes):
    target = project(client)
    response = client.post("/api/issues", json={"title": "Valide", "projectId": target["id"], **changes})
    assert response.status_code == 422, response.text
    assert "error" in response.json()
    assert client.get("/api/issues").json() == []
    assert issue(client, target["id"])["identifier"] == "TEST-1"


def test_invalid_update_is_atomic_and_project_prefix_immutable(client):
    target = project(client)
    item = issue(client, target["id"])
    response = client.patch(f'/api/issues/{item["id"]}', json={"title": "Perdu", "labelIds": [999999]})
    assert response.status_code == 422
    assert client.get(f'/api/issues/{item["id"]}').json() == item
    for invalid in ({}, {"title": None}, {"identifier": "NOPE-1"}):
        assert client.patch(f'/api/issues/{item["id"]}', json=invalid).status_code == 422
    assert client.patch(f'/api/projects/{target["id"]}', json={"key": "NEW"}).status_code == 422
    assert client.patch(f'/api/projects/{target["id"]}', json={"name": None}).status_code == 422
    assert client.post("/api/projects", json={"name": "Duplicate", "key": "TEST"}).status_code == 409


@pytest.mark.parametrize("payload", [{"name": " ", "key": "OK"}, {"name": "OK", "key": "x"}, {"name": "OK", "key": "_BAD"}, {"name": "OK", "key": "OK", "color": "red"}, {"name": "OK", "key": "OK", "extra": 1}])
def test_project_input_validation(client, payload):
    assert client.post("/api/projects", json=payload).status_code == 422
    assert client.get("/api/projects").json() == []


def test_comments_labels_and_missing_resources(client):
    target = project(client)
    item = issue(client, target["id"])
    for body in ("", " ", "x" * 10001, None, 42):
        assert client.post(f'/api/issues/{item["id"]}/comments', json={"body": body}).status_code == 422
    assert client.get(f'/api/issues/{item["id"]}/comments').json() == []
    assert client.post("/api/labels", json={"name": "Étiquette"}).status_code == 201
    assert client.post("/api/labels", json={"name": "éTIQUETTE"}).status_code == 409
    assert client.post("/api/labels", json={"name": " "}).status_code == 422
    for method, path, data in (("get", "/api/issues/999", None), ("patch", "/api/issues/999", {"title": "Valid"}), ("delete", "/api/issues/999", None), ("delete", "/api/projects/999", None), ("post", "/api/issues/999/comments", {"body": "Valid"})):
        assert client.request(method, path, **({"json": data} if data else {})).status_code == 404
    for query in ({"status": "unknown"}, {"priority": "unknown"}, {"projectId": "x"}, {"projectId": "-1"}, {"q": "x" * 201}):
        assert client.get("/api/issues", params=query).status_code == 422


def test_local_host_origin_and_json_body_protection(client):
    assert client.get("/api/health").json() == {"ok": True}
    for host in ("evil.test", "127.0.0.1.evil.test", "localhost:99999", "localhost:0", "localhost:abc"):
        assert client.get("/api/health", headers={"host": host}).status_code == 403
    for origin in ("https://evil.test", "null", "http://127.0.0.1:5555", "http://127.0.0.1:5173.evil.test"):
        assert client.post("/api/projects", json={"name": "X", "key": "XX"}, headers={"origin": origin}).status_code == 403
    for origin in ("http://127.0.0.1:4310", "http://127.0.0.1:5173"):
        result = client.options("/api/projects", headers={"origin": origin, "access-control-request-method": "POST"})
        assert result.status_code == 204
        assert result.headers["access-control-allow-origin"] == origin
    assert client.post("/api/projects", content='{"name":"X","key":"XX"}', headers={"content-type": "text/plain"}).status_code == 415
    assert client.post("/api/projects", content="broken", headers={"content-type": "application/json"}).status_code == 422
    assert client.post("/api/projects", content="x" * 131073, headers={"content-type": "application/json"}).status_code == 413
    assert client.get("/api/health", headers={"sec-fetch-site": "cross-site"}).status_code == 403
    assert client.get("/api/projects").json() == []


def test_frontend_routing_csp_and_missing_assets(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>Circular test</html>", encoding="utf-8")
    (dist / "app.js").write_text("console.log('local')", encoding="utf-8")
    with TestClient(create_app(tmp_path / "static.sqlite", dist), base_url="http://127.0.0.1:4310") as client:
        home = client.get("/")
        assert home.status_code == 200
        assert "default-src 'self'" in home.headers["content-security-policy"]
        assert "Circular test" in client.get("/projects").text
        assert client.get("/app.js").status_code == 200
        for path in ("/api/typo", "/api", "/assets/missing.js", "/missing.png", "/%2e%2e/private", "/%5cprivate", "/.env"):
            response = client.get(path)
            assert response.status_code == 404, path
            assert "Circular test" not in response.text
        assert client.get("/api/openapi.json").json()["info"]["title"] == "Circular"


def test_concurrent_creation_allocates_unique_identifiers(client):
    target = project(client)
    with ThreadPoolExecutor(max_workers=6) as pool:
        issues = list(pool.map(lambda index: issue(client, target["id"], title=f"Ticket {index}"), range(12)))
    assert len({item["identifier"] for item in issues}) == 12
    assert sorted(int(item["identifier"].split("-")[1]) for item in issues) == list(range(1, 13))


def test_full_length_unicode_description_fits_body_limit(client):
    target = project(client)
    item = issue(client, target["id"], description="🟢" * 20000)
    assert len(item["description"]) == 20000


def test_seed_collision_rolls_back_everything(client):
    project(client, "ORB")
    database = client.app.state.workspace.database
    with pytest.raises(ValueError, match="préfixe"):
        seed_database(database)
    assert len(client.get("/api/projects").json()) == 1
    assert client.get("/api/issues").json() == []
    assert client.get("/api/labels").json() == []


def test_seed_is_explicit_atomic_idempotent_and_preserves_deleted_demo(tmp_path):
    database = Database(tmp_path / "seed.sqlite")
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM issues").fetchone()[0] == 0
    assert seed_database(database) is True
    assert seed_database(database) is False
    with database.connect(write=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM issues").fetchone()[0] == 16
        assert connection.execute("SELECT COUNT(*) FROM labels").fetchone()[0] == 5
        assert connection.execute("SELECT COUNT(*) FROM comments").fetchone()[0] == 3
        connection.execute("DELETE FROM issues WHERE id = (SELECT MIN(id) FROM issues)")
    assert seed_database(database) is False
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM issues").fetchone()[0] == 15
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 4
