"""Adversarial route access and stale-reference regressions for private projects."""
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor
from threading import Event, local
import pytest
from fastapi.testclient import TestClient
from backend.app.main import create_app
from backend.app.db.session import Database
from backend.app.repositories.preferences import PreferencesRepository
from backend.app.services.auth import AuthService
from backend.app.services.preferences import PreferencesService
from tests.test_postgres import postgres_url


@pytest.fixture
def people(tmp_path):
    app = create_app(tmp_path / "sharing-security.sqlite")
    with ExitStack() as stack:
        clients = []
        for username in ("Alice", "Bob", "Charlie"):
            client = stack.enter_context(TestClient(app, base_url="http://127.0.0.1:4310"))
            result = client.post("/api/auth/register", json={"email": f"{username.lower()}@epita.fr", "username": username, "password": "Une phrase de passe fictive 42!"})
            assert result.status_code == 201
            client.headers["X-CSRF-Token"] = result.json()["csrfToken"]
            client.user_id = result.json()["user"]["id"]
            clients.append(client)
        yield app, *clients


def fixture_records(client):
    project = client.post("/api/projects", json={"name": "Projet privé", "key": "PRIV"}).json()
    label = client.post("/api/labels", json={"name": "Étiquette privée"}).json()
    issue = client.post("/api/issues", json={"projectId": project["id"], "title": "Information privée", "labelIds": [label["id"]]}).json()
    comment = client.post(f'/api/issues/{issue["id"]}/comments', json={"body": "Commentaire privé"}).json()
    view = client.post("/api/views", json={"name": "Vue privée"}).json()
    template = client.post("/api/templates", json={"name": "Modèle privé"}).json()
    return project, label, issue, comment, view, template


def test_anonymous_routes_and_csrf_protect_every_resource_family(people):
    app, owner, _, _ = people
    project, label, issue, comment, view, template = fixture_records(owner)
    mutation_requests = [
        ("POST", "/api/projects", {"name": "Projet", "key": "NEW"}),
        ("PATCH", f'/api/projects/{project["id"]}', {"name": "Tentative"}),
        ("DELETE", f'/api/projects/{project["id"]}', None),
        ("POST", "/api/issues", {"projectId": project["id"], "title": "Tentative"}),
        ("PATCH", f'/api/issues/{issue["id"]}', {"title": "Tentative"}),
        ("DELETE", f'/api/issues/{issue["id"]}', None),
        ("POST", f'/api/issues/{issue["id"]}/duplicate', {}),
        ("POST", f'/api/issues/{issue["id"]}/comments', {"body": "Tentative"}),
        ("PATCH", f'/api/issues/{issue["id"]}/comments/{comment["id"]}', {"body": "Tentative"}),
        ("DELETE", f'/api/issues/{issue["id"]}/comments/{comment["id"]}', None),
        ("POST", "/api/labels", {"name": "Tentative"}),
        ("PATCH", f'/api/labels/{label["id"]}', {"name": "Tentative"}),
        ("DELETE", f'/api/labels/{label["id"]}', None),
        ("PATCH", "/api/settings", {"fontSize": "large"}),
        ("POST", "/api/views", {"name": "Tentative"}),
        ("PATCH", f'/api/views/{view["id"]}', {"name": "Tentative"}),
        ("DELETE", f'/api/views/{view["id"]}', None),
        ("POST", "/api/templates", {"name": "Tentative"}),
        ("PATCH", f'/api/templates/{template["id"]}', {"name": "Tentative"}),
        ("DELETE", f'/api/templates/{template["id"]}', None),
        ("POST", f'/api/projects/{project["id"]}/invitations', {"email": "bob@epita.fr"}),
        ("DELETE", f'/api/projects/{project["id"]}/invitations/1', None),
        ("DELETE", f'/api/projects/{project["id"]}/members/2', None),
        ("POST", "/api/invitations/1/accept", {}),
        ("POST", "/api/invitations/1/decline", {}),
    ]
    with TestClient(app, base_url="http://127.0.0.1:4310") as anonymous:
        for path in ("/api/projects", "/api/issues", f'/api/issues/{issue["id"]}', f'/api/issues/{issue["id"]}/comments', f'/api/issues/{issue["id"]}/activity', "/api/labels", "/api/settings", "/api/views", "/api/templates", "/api/invitations", f'/api/projects/{project["id"]}/members', f'/api/projects/{project["id"]}/invitations'):
            assert anonymous.get(path).status_code == 401, path
        for method, path, payload in mutation_requests:
            response = anonymous.request(method, path, **({"json": payload} if payload is not None else {}))
            assert response.status_code == 401, (method, path, response.text)
    csrf = owner.headers.pop("X-CSRF-Token")
    for method, path, payload in mutation_requests:
        response = owner.request(method, path, **({"json": payload} if payload is not None else {}))
        assert response.status_code == 403, (method, path, response.text)
    owner.headers["X-CSRF-Token"] = csrf
    assert owner.get(f'/api/issues/{issue["id"]}').json()["title"] == "Information privée"
    assert owner.get("/api/views").json()[0]["name"] == "Vue privée"


def test_outsider_ids_do_not_reveal_or_modify_private_records(people):
    _, owner, outsider, _ = people
    project, label, issue, comment, view, template = fixture_records(owner)
    for path in (f'/api/issues/{issue["id"]}', f'/api/issues/{issue["id"]}/comments', f'/api/issues/{issue["id"]}/activity', f'/api/projects/{project["id"]}/members', f'/api/projects/{project["id"]}/invitations'):
        assert outsider.get(path).status_code == 404, path
    for path in ("/api/projects", "/api/issues", "/api/labels", "/api/views", "/api/templates"):
        assert outsider.get(path).json() == [], path
    for method, path, payload in [
        ("PATCH", f'/api/projects/{project["id"]}', {"name": "Intrusion"}),
        ("PATCH", f'/api/issues/{issue["id"]}', {"title": "Intrusion"}),
        ("POST", f'/api/issues/{issue["id"]}/duplicate', {}),
        ("PATCH", f'/api/issues/{issue["id"]}/comments/{comment["id"]}', {"body": "Intrusion"}),
        ("PATCH", f'/api/labels/{label["id"]}', {"name": "Intrusion"}),
        ("PATCH", f'/api/views/{view["id"]}', {"name": "Intrusion"}),
        ("PATCH", f'/api/templates/{template["id"]}', {"name": "Intrusion"}),
        ("POST", f'/api/projects/{project["id"]}/invitations', {"email": "charlie@epita.fr"}),
    ]:
        assert outsider.request(method, path, json=payload).status_code == 404, path
    for path in (f'/api/projects/{project["id"]}', f'/api/issues/{issue["id"]}', f'/api/issues/{issue["id"]}/comments/{comment["id"]}', f'/api/labels/{label["id"]}', f'/api/views/{view["id"]}', f'/api/templates/{template["id"]}'):
        assert outsider.delete(path).status_code == 404, path
    for path, payload in [
        ("/api/issues", {"projectId": project["id"], "title": "Intrusion"}),
        ("/api/templates", {"name": "Intrusion", "projectId": project["id"]}),
        ("/api/templates", {"name": "Intrusion", "labelIds": [label["id"]]}),
        ("/api/views", {"name": "Intrusion", "filters": {"projectId": str(project["id"])}}),
    ]:
        assert outsider.post(path, json=payload).status_code == 422, path
    assert owner.get(f'/api/issues/{issue["id"]}').json()["title"] == "Information privée"


def test_invitation_recipient_cannot_be_forged_or_replayed(people):
    _, owner, invited, outsider = people
    project, _, _, _, _, _ = fixture_records(owner)
    invitation = owner.post(f'/api/projects/{project["id"]}/invitations', json={"email": "bob@epita.fr"}).json()
    for action in ("accept", "decline"):
        assert outsider.post(f'/api/invitations/{invitation["id"]}/{action}', json={}).status_code == 404
    assert outsider.get("/api/invitations").json() == []
    assert invited.get("/api/projects").json() == []
    assert invited.post(f'/api/invitations/{invitation["id"]}/accept', json={}).status_code == 204
    assert invited.post(f'/api/invitations/{invitation["id"]}/accept', json={}).status_code == 404
    assert len(invited.get("/api/projects").json()) == 1
    assert len(owner.get(f'/api/projects/{project["id"]}/members').json()) == 2


def test_revocation_cleans_personal_references_to_inaccessible_labels(people):
    _, owner, member, _ = people
    project, label, _, _, _, _ = fixture_records(owner)
    invitation = owner.post(f'/api/projects/{project["id"]}/invitations', json={"email": "bob@epita.fr"}).json()
    assert member.post(f'/api/invitations/{invitation["id"]}/accept', json={}).status_code == 204
    filters = {"projectId": str(project["id"]), "labelIds": [label["id"]]}
    assert member.patch("/api/settings", json={"filters": filters}).status_code == 200
    assert member.post("/api/views", json={"name": "Suivi partagé", "filters": filters}).status_code == 201
    assert member.post("/api/templates", json={"name": "Modèle partagé", "projectId": project["id"], "labelIds": [label["id"]]}).status_code == 201
    assert owner.delete(f'/api/projects/{project["id"]}/members/{member.user_id}').status_code == 204
    assert member.get("/api/labels").json() == []
    assert member.get("/api/settings").json()["filters"]["labelIds"] == []
    assert member.get("/api/views").json()[0]["filters"]["labelIds"] == []
    template = member.get("/api/templates").json()[0]
    assert template["projectId"] is None and template["labelIds"] == []


def test_postgres_parallel_first_settings_changes_preserve_both_fields(postgres_url, monkeypatch):
    database = Database(postgres_url)
    account, _ = AuthService(database).register("parallel@epita.fr", "Parallel", "Phrase de passe de test 42!", "test-peer")
    service = PreferencesService(database, account["user"]["id"])
    first_read, second_read, first_saved = Event(), Event(), Event()
    worker = local()
    original_read, original_save = PreferencesRepository.settings, PreferencesRepository.save_settings

    def observed_read(repository):
        result = original_read(repository)
        if getattr(worker, "role", None) == "first":
            first_read.set()
            # If reads are not serialized, allow the second request to capture
            # its stale snapshot before the first update is committed.
            second_read.wait(1)
        elif getattr(worker, "role", None) == "second":
            second_read.set()
            assert first_saved.wait(5)
        return result

    def observed_save(repository, value):
        result = original_save(repository, value)
        if getattr(worker, "role", None) == "first":
            first_saved.set()
        return result

    def update(role, patch):
        worker.role = role
        return service.update_settings(patch)

    monkeypatch.setattr(PreferencesRepository, "settings", observed_read)
    monkeypatch.setattr(PreferencesRepository, "save_settings", observed_save)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(update, "first", {"fontSize": "large"})
        assert first_read.wait(5)
        second = pool.submit(update, "second", {"density": "comfortable"})
        first.result(timeout=10)
        second.result(timeout=10)
    persisted = service.settings()
    assert persisted["fontSize"] == "large"
    assert persisted["density"] == "comfortable"
