"""Persistence and behavior coverage for audit-driven local workflow extensions."""
import sqlite3
from pathlib import Path
import pytest
from tests.helpers import AuthenticatedTestClient as TestClient
from backend.app.db.session import Database
from backend.app.main import create_app
from backend.app.schemas.preferences import Display, Filters
from backend.claim_legacy import claim_legacy


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "extensions.sqlite"), base_url="http://127.0.0.1:4310") as instance:
        yield instance


def project(client, key="EXT"):
    response = client.post("/api/projects", json={"name": f"Projet {key}", "key": key})
    assert response.status_code == 201, response.text
    return response.json()


def issue(client, project_id, **changes):
    response = client.post("/api/issues", json={"projectId": project_id, "title": "Ticket", **changes})
    assert response.status_code == 201, response.text
    return response.json()


def label(client, name="Produit"):
    response = client.post("/api/labels", json={"name": name, "description": "Contexte", "color": "#e6c65c"})
    assert response.status_code == 201
    return response.json()


def test_settings_defaults_partial_updates_and_restart(tmp_path):
    path = tmp_path / "settings.sqlite"
    with TestClient(create_app(path), base_url="http://127.0.0.1:4310") as client:
        initial = client.get("/api/settings").json()
        assert initial["homeView"] == "resume"
        display = {**initial["display"], "view": "board", "grouping": "priority", "sortBy": "dueDate", "properties": ["identifier", "dueDate"], "hiddenStatuses": ["done"]}
        settings = client.patch("/api/settings", json={"fontSize": "large", "reduceMotion": True, "display": display}).json()
        assert settings["filters"] == initial["filters"]
        assert settings["display"] == display
        assert client.patch("/api/settings", json={"density": "comfortable"}).status_code == 200
    with TestClient(create_app(path), base_url="http://127.0.0.1:4310") as reopened:
        persisted = reopened.get("/api/settings").json()
        assert persisted["display"] == display
        assert persisted["density"] == "comfortable"
        assert persisted["fontSize"] == "large"
        assert persisted["reduceMotion"] is True


@pytest.mark.parametrize("payload", [{}, {"density": "huge"}, {"reduceMotion": "true"}, {"fontSize": None}, {"display": None}, {"display": {"properties": ["unknown"]}}, {"display": {"properties": ["status", "status"]}}, {"filters": {"projectId": "-1"}}, {"filters": {"statuses": ["bad"]}}, {"filters": {"labelIds": [999]}}])
def test_invalid_settings_are_atomic(client, payload):
    before = client.get("/api/settings").json()
    assert client.patch("/api/settings", json=payload).status_code == 422
    assert client.get("/api/settings").json() == before


def test_saved_views_and_templates_crud_and_reference_cleanup(client):
    target = project(client)
    tag = label(client)
    filters = Filters(projectId=str(target["id"]), labelIds=[tag["id"]]).model_dump()
    display = Display(view="board").model_dump()
    assert client.patch("/api/settings", json={"filters": filters}).status_code == 200
    response = client.post("/api/views", json={"name": "Mon suivi", "filters": filters, "display": display})
    assert response.status_code == 201
    view = response.json()
    assert client.patch(f'/api/views/{view["id"]}', json={"name": "Suivi renommé"}).json()["filters"] == filters
    response = client.post("/api/templates", json={"name": "Bug", "title": "Décrire", "projectId": target["id"], "priority": "high", "labelIds": [tag["id"]]})
    assert response.status_code == 201
    template = response.json()
    assert client.patch(f'/api/templates/{template["id"]}', json={"description": "Étapes"}).json()["description"] == "Étapes"
    assert client.delete(f'/api/labels/{tag["id"]}').status_code == 204
    assert client.get("/api/templates").json()[0]["labelIds"] == []
    assert client.get("/api/views").json()[0]["filters"]["labelIds"] == []
    assert client.get("/api/settings").json()["filters"]["labelIds"] == []
    assert client.delete(f'/api/projects/{target["id"]}').status_code == 204
    assert client.get("/api/templates").json()[0]["projectId"] is None
    assert client.get("/api/views").json()[0]["filters"]["projectId"] == ""
    assert client.get("/api/settings").json()["filters"]["projectId"] == ""
    assert client.delete(f'/api/views/{view["id"]}').status_code == 204
    assert client.delete(f'/api/templates/{template["id"]}').status_code == 204
    assert client.get("/api/views").json() == []
    assert client.get("/api/templates").json() == []


def test_labels_rename_color_description_uniqueness_and_delete_associations(client):
    target = project(client)
    tag, another = label(client), label(client, "Autre")
    item = issue(client, target["id"], labelIds=[tag["id"], another["id"]])
    url = f'/api/labels/{tag["id"]}'
    result = client.patch(url, json={"name": "Conception", "description": "Mis à jour", "color": "#abcdef"})
    assert result.status_code == 200
    assert result.json()["description"] == "Mis à jour"
    assert client.patch(url, json={"name": "AUTRE"}).status_code == 409
    assert client.patch(url, json={"name": "CONCEPTION"}).status_code == 200
    assert client.delete(url).status_code == 204
    persisted = client.get(f'/api/issues/{item["id"]}').json()
    assert persisted["title"] == item["title"]
    assert [value["id"] for value in persisted["labels"]] == [another["id"]]


def test_multiselect_filters_or_within_fields_and_across_fields(client):
    target, other = project(client), project(client, "OTHER")
    one, two = label(client), label(client, "Technique")
    first = issue(client, target["id"], title="Chercher alpha", status="todo", priority="high", labelIds=[one["id"]], isFavorite=True)
    second = issue(client, target["id"], title="Chercher bêta", status="in_progress", priority="urgent", labelIds=[two["id"]], isFavorite=True)
    issue(client, target["id"], title="Sans étiquette", status="todo", priority="high", isFavorite=True)
    issue(client, other["id"], title="Chercher autre", status="todo", priority="high", labelIds=[one["id"]], isFavorite=True)
    issue(client, target["id"], title="Chercher terminé", status="done", priority="high", labelIds=[one["id"]])
    params = {"projectId": target["id"], "q": "chercher", "statuses": "todo,in_progress", "status": "done", "priorities": "high,urgent", "priority": "none", "labelIds": f'{one["id"]},{two["id"]}', "favoritesOnly": "true"}
    found = client.get("/api/issues", params=params)
    assert found.status_code == 200
    assert {item["id"] for item in found.json()} == {first["id"], second["id"]}


def test_sort_priority_title_and_dates_with_nulls_last(client):
    target = project(client)
    low = issue(client, target["id"], title="Zulu", priority="low", dueDate="2026-12-01")
    urgent = issue(client, target["id"], title="Alpha", priority="urgent", dueDate="2026-11-01")
    none = issue(client, target["id"], title="Beta")
    def ids(sort, direction="asc"):
        response = client.get("/api/issues", params={"sortBy": sort, "direction": direction})
        assert response.status_code == 200
        return [row["id"] for row in response.json()]
    assert ids("priority") == [none["id"], low["id"], urgent["id"]]
    assert ids("priority", "desc") == [urgent["id"], low["id"], none["id"]]
    assert ids("title") == [urgent["id"], none["id"], low["id"]]
    assert ids("dueDate") == [urgent["id"], low["id"], none["id"]]
    assert ids("dueDate", "desc") == [low["id"], urgent["id"], none["id"]]


@pytest.mark.parametrize("query", [{"statuses": "unknown"}, {"statuses": "todo,todo"}, {"priorities": "high,bad"}, {"labelIds": "1,x"}, {"labelIds": "0"}, {"labelIds": "1,1"}, {"labelIds": "999999999999999999999"}, {"projectId": "999999999999999999999"}, {"sortBy": "DROP TABLE issues"}, {"direction": "other"}])
def test_invalid_filter_and_sort_values(client, query):
    assert client.get("/api/issues", params=query).status_code == 422


def test_duplicate_favorite_due_date_and_activity_are_independent(client):
    target = project(client)
    tag = label(client)
    original = issue(client, target["id"], title="x" * 240, description="À conserver", status="in_review", priority="urgent", labelIds=[tag["id"]], dueDate="2027-01-15", isFavorite=True)
    url = f'/api/issues/{original["id"]}'
    client.post(url + "/comments", json={"body": "Commentaire original"})
    assert client.patch(url, json={"description": "Dernière version"}).status_code == 200
    response = client.post(url + "/duplicate", headers={"content-type": "application/json"})
    assert response.status_code == 201
    copy = response.json()
    assert copy["identifier"] != original["identifier"]
    assert len(copy["title"]) == 240 and copy["title"].endswith(" (copie)")
    assert copy["description"] == "Dernière version"
    assert copy["labels"] == original["labels"]
    assert copy["dueDate"] == original["dueDate"]
    assert copy["isFavorite"] is False
    assert client.get(f'/api/issues/{copy["id"]}/comments').json() == []
    assert [row["kind"] for row in client.get(f'/api/issues/{copy["id"]}/activity').json()] == ["created"]
    assert client.patch(url, json={"dueDate": None, "isFavorite": False}).json()["dueDate"] is None
    assert client.get("/api/issues", params={"favoritesOnly": "true"}).json() == []


def test_comment_edit_delete_ownership_and_atomic_history(client):
    target = project(client)
    first, second = issue(client, target["id"]), issue(client, target["id"])
    url = f'/api/issues/{first["id"]}'
    comment = client.post(url + "/comments", json={"body": "Texte initial"}).json()
    comment_url = url + f'/comments/{comment["id"]}'
    assert client.patch(f'/api/issues/{second["id"]}/comments/{comment["id"]}', json={"body": "Mauvaise cible"}).status_code == 404
    assert client.delete(f'/api/issues/{second["id"]}/comments/{comment["id"]}').status_code == 404
    assert client.patch(comment_url, json={"body": "Texte modifié"}).json()["body"] == "Texte modifié"
    assert client.delete(comment_url).status_code == 204
    assert client.get(url + "/comments").json() == []
    activity = client.get(url + "/activity").json()
    assert [row["kind"] for row in activity] == ["created", "comment_created", "comment_updated", "comment_deleted"]
    assert all("Texte" not in row["body"] for row in activity)
    assert client.patch(url, json={"title": "Tentative", "labelIds": [999]}).status_code == 422
    assert client.get(url + "/activity").json() == activity
    assert client.patch(url, json={"title": first["title"]}).status_code == 200
    assert client.get(url + "/activity").json() == activity


@pytest.mark.parametrize("date", ["2026-02-30", "2026-2-01", "20261016", "2026-10-16T00:00:00", "tomorrow", 42])
def test_due_date_validation(client, date):
    target = project(client)
    item = issue(client, target["id"])
    assert client.patch(f'/api/issues/{item["id"]}', json={"dueDate": date}).status_code == 422
    assert client.patch(f'/api/projects/{target["id"]}', json={"dueDate": date}).status_code == 422


def test_project_workflow_and_optional_template_project(client):
    target = project(client)
    assert target["status"] == "planned" and target["dueDate"] is None
    url = f'/api/projects/{target["id"]}'
    updated = client.patch(url, json={"status": "in_progress", "dueDate": "2026-12-31"}).json()
    assert updated["dueDate"] == "2026-12-31"
    assert updated["status"] == "in_progress"
    assert client.patch(url, json={"status": "done"}).status_code == 422
    assert client.patch(url, json={"dueDate": None}).json()["dueDate"] is None
    template = client.post("/api/templates", json={"name": "Sans projet", "projectId": None}).json()
    assert template["projectId"] is None
    assert client.patch(f'/api/templates/{template["id"]}', json={"projectId": target["id"]}).status_code == 200
    assert client.patch(f'/api/templates/{template["id"]}', json={"projectId": None}).json()["projectId"] is None


def test_extended_records_and_deletions_survive_restart(client):
    target = project(client)
    tag = label(client)
    item = issue(client, target["id"], isFavorite=True, dueDate="2027-04-01", labelIds=[tag["id"]])
    client.post("/api/views", json={"name": "Persistante"})
    template = client.post("/api/templates", json={"name": "Persistant"}).json()
    client.delete(f'/api/templates/{template["id"]}')
    with TestClient(create_app(client.app.state.workspace.database.path), base_url="http://127.0.0.1:4310") as restarted:
        persisted = restarted.get(f'/api/issues/{item["id"]}').json()
        assert persisted["isFavorite"] is True and persisted["dueDate"] == "2027-04-01"
        assert restarted.get("/api/views").json()[0]["name"] == "Persistante"
        assert restarted.get("/api/templates").json() == []
        assert restarted.delete(f'/api/issues/{item["id"]}').status_code == 204
    with client.app.state.workspace.database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM issue_activity").fetchone()[0] == 0
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_migration_002_preserves_original_database_and_is_idempotent(tmp_path):
    path = tmp_path / "legacy.sqlite"
    initial = Path(__file__).parents[1] / "backend/app/db/migrations/001_initial.sql"
    with sqlite3.connect(path) as connection:
        connection.executescript(initial.read_text(encoding="utf-8"))
        connection.execute("CREATE TABLE schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
        connection.execute("INSERT INTO schema_migrations VALUES ('001_initial.sql', '2026-10-01')")
        connection.execute("INSERT INTO project_sequences VALUES ('OLD', 1)")
        connection.execute("INSERT INTO projects VALUES (1, 'Ancien', 'OLD', '', '#aaaaaa', '2026-10-01')")
        connection.execute("INSERT INTO issues VALUES (1, 'OLD-1', 'Préservé', '', 1, 'todo', 'high', 'préservé', '2026-10-01', '2026-10-01')")
    Database(path)
    Database(path)
    with TestClient(create_app(path), base_url="http://127.0.0.1:4310") as migrated:
        assert migrated.get("/api/issues/1").status_code == 404
        assert migrated.get("/api/projects").json() == []
        assert claim_legacy(migrated.app.state.database, migrated.user["id"]) == 1
        assert claim_legacy(migrated.app.state.database, migrated.user["id"]) == 0
        original = migrated.get("/api/issues/1").json()
        assert original["title"] == "Préservé" and original["identifier"] == "OLD-1"
        assert original["isFavorite"] is False and original["dueDate"] is None
        assert issue(migrated, 1)["identifier"] == "OLD-2"
        assert migrated.get("/api/projects").json()[0]["status"] == "planned"
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 5


def test_missing_extension_resources(client):
    for method, path, payload in [("patch", "/api/labels/999", {"name": "Absent"}), ("delete", "/api/labels/999", None), ("patch", "/api/views/999", {"name": "Absent"}), ("delete", "/api/views/999", None), ("patch", "/api/templates/999", {"name": "Absent"}), ("delete", "/api/templates/999", None), ("get", "/api/issues/999/activity", None), ("post", "/api/issues/999/duplicate", None)]:
        response = client.request(method, path, headers={"content-type": "application/json"}, **({"json": payload} if payload else {}))
        assert response.status_code == 404, response.text


def test_openapi_describes_extension_resources(client):
    schema = client.get("/api/openapi.json").json()
    for path in ("/api/settings", "/api/views", "/api/templates", "/api/issues/{issue_id}/activity", "/api/issues/{issue_id}/duplicate"):
        assert path in schema["paths"]
    assert "isFavorite" in schema["components"]["schemas"]["Issue"]["properties"]


def test_reference_errors_do_not_leave_partial_templates_or_views(client):
    for payload in ({"name": "Invalide", "projectId": 999}, {"name": "Invalide", "labelIds": [999]}, {"name": "Invalide", "labelIds": [1, 1]}):
        assert client.post("/api/templates", json=payload).status_code == 422
    assert client.get("/api/templates").json() == []
    assert client.post("/api/views", json={"name": "Invalide", "filters": {"projectId": "999"}}).status_code == 422
    assert client.get("/api/views").json() == []
    assert client.patch("/api/settings", json={"filters": {"projectId": "9999999999999999999"}}).status_code == 422
