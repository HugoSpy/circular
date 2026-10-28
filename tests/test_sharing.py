"""Cross-account access checks against the real HTTP dependencies and persistence."""
import pytest
from fastapi.testclient import TestClient
from backend.app.main import create_app

PASSWORD = "Mot-de-passe-test-37!"


@pytest.fixture
def people(tmp_path):
    app = create_app(tmp_path / "sharing.sqlite")
    clients = []
    for name in ("alice", "bob", "charlie"):
        client = TestClient(app, base_url="http://127.0.0.1:4310")
        result = client.post("/api/auth/register", json={"email": f"{name}@epita.fr", "username": name, "password": PASSWORD})
        assert result.status_code == 201, result.text
        client.headers["X-CSRF-Token"] = result.json()["csrfToken"]
        clients.append(client)
    yield clients
    for client in clients:
        client.close()


def project(client, key="PVT"):
    response = client.post("/api/projects", json={"name": "Projet privé", "key": key})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def ticket(client, project_id):
    response = client.post("/api/issues", json={"title": "Information privée", "projectId": project_id})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def invite(alice, bob, project_id):
    response = alice.post(f"/api/projects/{project_id}/invitations", json={"email": "bob@epita.fr"})
    assert response.status_code == 201, response.text
    invitation = response.json()["id"]
    assert bob.post(f"/api/invitations/{invitation}/accept", json={}).status_code == 204
    return invitation


@pytest.mark.parametrize("method,suffix,payload", [
    ("get", "", None), ("patch", "", {"title": "Écrasement"}), ("delete", "", None),
    ("get", "/comments", None), ("post", "/comments", {"body": "Intrusion"}),
    ("get", "/activity", None), ("post", "/duplicate", {}),
])
def test_outsider_cannot_read_or_mutate_issue(people, method, suffix, payload):
    alice, bob, _ = people
    issue_id = ticket(alice, project(alice))
    args = {"json": payload} if payload is not None else {}
    assert getattr(bob, method)(f"/api/issues/{issue_id}{suffix}", **args).status_code == 404
    assert bob.get("/api/issues").json() == []
    assert bob.get("/api/projects").json() == []
    assert alice.get(f"/api/issues/{issue_id}").json()["title"] == "Information privée"


def test_invitation_is_targeted_requires_acceptance_and_can_be_revoked(people):
    alice, bob, charlie = people
    pid = project(alice)
    iid = ticket(alice, pid)
    invitation = alice.post(f"/api/projects/{pid}/invitations", json={"email": "bob@epita.fr"}).json()["id"]
    assert bob.get(f"/api/issues/{iid}").status_code == 404
    assert charlie.get("/api/invitations").json() == []
    assert charlie.post(f"/api/invitations/{invitation}/accept", json={}).status_code == 404
    assert bob.post(f"/api/invitations/{invitation}/accept", json={}).status_code == 204
    assert bob.get("/api/projects").json()[0]["role"] == "member"
    assert bob.patch(f"/api/issues/{iid}", json={"title": "Partagé"}).status_code == 200
    assert bob.patch(f"/api/projects/{pid}", json={"name": "Sans autorisation"}).status_code == 403
    assert bob.delete(f"/api/projects/{pid}").status_code == 403
    assert bob.post(f"/api/projects/{pid}/invitations", json={"email": "charlie@epita.fr"}).status_code == 403
    member = next(item for item in alice.get(f"/api/projects/{pid}/members").json() if item["role"] == "member")
    assert alice.delete(f"/api/projects/{pid}/members/{member['id']}").status_code == 204
    assert bob.get("/api/projects").json() == []
    assert bob.get(f"/api/issues/{iid}").status_code == 404


def test_personal_settings_favorites_views_and_templates_are_isolated(people):
    alice, bob, _ = people
    pid = project(alice)
    iid = ticket(alice, pid)
    invite(alice, bob, pid)
    assert alice.patch(f"/api/issues/{iid}", json={"isFavorite": True}).status_code == 200
    assert bob.get("/api/issues?favoritesOnly=true").json() == []
    assert bob.get(f"/api/issues/{iid}").json()["isFavorite"] is False
    settings = alice.get("/api/settings").json()
    assert alice.patch("/api/settings", json={"fontSize": "large"}).status_code == 200
    assert bob.get("/api/settings").json()["fontSize"] == "default"
    view = alice.post("/api/views", json={"name": "Vue privée", "filters": settings["filters"], "display": settings["display"]}).json()
    template = alice.post("/api/templates", json={"name": "Modèle privé", "projectId": pid}).json()
    assert bob.get("/api/views").json() == []
    assert bob.get("/api/templates").json() == []
    for collection, item in (("views", view), ("templates", template)):
        assert bob.patch(f"/api/{collection}/{item['id']}", json={"name": "Modification"}).status_code == 404
        assert bob.delete(f"/api/{collection}/{item['id']}").status_code == 404


def test_comment_author_and_project_moderation(people):
    alice, bob, _ = people
    pid = project(alice)
    iid = ticket(alice, pid)
    invite(alice, bob, pid)
    comment = alice.post(f"/api/issues/{iid}/comments", json={"body": "Écrit par Alice"}).json()
    listed = bob.get(f"/api/issues/{iid}/comments").json()[0]
    assert listed["author"]["username"] == "alice"
    assert listed["canEdit"] is False and listed["canDelete"] is False
    assert bob.patch(f"/api/issues/{iid}/comments/{comment['id']}", json={"body": "Faux auteur"}).status_code == 403
    assert bob.delete(f"/api/issues/{iid}/comments/{comment['id']}").status_code == 403
    own = bob.post(f"/api/issues/{iid}/comments", json={"body": "Écrit par Bob"}).json()
    assert bob.patch(f"/api/issues/{iid}/comments/{own['id']}", json={"body": "Corrigé"}).status_code == 200
    assert alice.delete(f"/api/issues/{iid}/comments/{own['id']}").status_code == 204
    events = bob.get(f"/api/issues/{iid}/activity").json()
    assert events[-1]["actor"]["username"] == "alice"


def test_label_library_is_personal_but_attached_labels_are_shared(people):
    alice, bob, _ = people
    pid = project(alice)
    iid = ticket(alice, pid)
    private = alice.post("/api/labels", json={"name": "Secret"}).json()
    shared = alice.post("/api/labels", json={"name": "Produit"}).json()
    assert bob.get("/api/labels").json() == []
    assert alice.patch(f"/api/issues/{iid}", json={"labelIds": [shared["id"]]}).status_code == 200
    invite(alice, bob, pid)
    labels = bob.get("/api/labels").json()
    assert [item["id"] for item in labels] == [shared["id"]]
    assert labels[0]["canEdit"] is False
    assert bob.delete(f"/api/labels/{shared['id']}").status_code == 403
    assert bob.patch(f"/api/labels/{shared['id']}", json={"name": "Interdit"}).status_code == 403
    assert bob.patch(f"/api/issues/{iid}", json={"labelIds": [private["id"]]}).status_code == 422
    assert bob.post("/api/labels", json={"name": "Produit"}).status_code == 201


def test_invitation_decline_cancel_and_owner_protection(people):
    alice, bob, _ = people
    pid = project(alice)
    item = alice.post(f"/api/projects/{pid}/invitations", json={"email": "bob@epita.fr"}).json()
    assert bob.post(f"/api/invitations/{item['id']}/decline", json={}).status_code == 204
    assert alice.get(f"/api/projects/{pid}/invitations").json() == []
    item = alice.post(f"/api/projects/{pid}/invitations", json={"email": "bob@epita.fr"}).json()
    assert alice.delete(f"/api/projects/{pid}/invitations/{item['id']}").status_code == 204
    assert bob.post(f"/api/invitations/{item['id']}/accept", json={}).status_code == 404
    owner = alice.get(f"/api/projects/{pid}/members").json()[0]["id"]
    assert alice.delete(f"/api/projects/{pid}/members/{owner}").status_code == 409


def test_anonymous_api_denies_data_and_csrf_is_mandatory(people):
    alice, _, _ = people
    with TestClient(alice.app, base_url="http://127.0.0.1:4310") as anonymous:
        for path in ("projects", "issues", "labels", "settings", "views", "templates", "invitations"):
            assert anonymous.get(f"/api/{path}").status_code == 401
    alice.headers.pop("X-CSRF-Token")
    assert alice.post("/api/projects", json={"key": "NO", "name": "Refus"}).status_code == 403
