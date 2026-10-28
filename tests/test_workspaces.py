"""Real onboarding, workspace isolation and invitations on SQLite and PostgreSQL."""
import hashlib
from contextlib import ExitStack
from pathlib import Path
import sqlite3
import pytest
from fastapi.testclient import TestClient
from backend.app.main import create_app
from backend.app.db.session import Database
from backend.app.db.backfill import backfill_workspaces
from tests.test_postgres import postgres_url  # noqa: F401

PASSWORD = "Une phrase de test de 24 caracteres!"


def account(app, name):
    client = TestClient(app, base_url="http://127.0.0.1:4310")
    response = client.post("/api/auth/register", json={"email": f"{name}@epita.fr", "username": name, "password": PASSWORD})
    assert response.status_code == 201, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrfToken"]
    return client


@pytest.fixture(params=["sqlite", "postgres"])
def workspace_people(request, tmp_path):
    target = request.getfixturevalue("postgres_url") if request.param == "postgres" else tmp_path / "workspaces.sqlite"
    app = create_app(target)
    with ExitStack() as stack:
        clients = [stack.enter_context(account(app, name)) for name in ("alice", "bob", "charlie")]
        yield app, clients, target


def create_workspace(client, slug="premier-espace", *, welcome=False):
    response = client.post("/api/workspaces", json={"name": "Projet de groupe", "slug": slug, "includeWelcomeIssues": welcome})
    assert response.status_code == 201, response.text
    data = response.json()
    client.headers["X-Workspace-Id"] = str(data["workspace"]["id"])
    return data["workspace"], data["project"]


def issue(client, project_id, **values):
    response = client.post("/api/issues", json={"projectId": project_id, "title": "Ticket persistant", **values})
    assert response.status_code == 201, response.text
    return response.json()


def invite(client, workspace, email):
    response = client.post(f'/api/workspaces/{workspace["id"]}/invitations', json={"email": email})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_onboarding_profile_welcome_once_and_restart(workspace_people):
    app, (alice, bob, _), target = workspace_people
    assert alice.get("/api/workspaces").json() == []
    assert alice.get("/api/auth/me").json()["user"]["profileCompleted"] is False
    updated = alice.patch("/api/auth/profile", json={"displayName": "Alice Exemple", "title": "Élève ingénieure"})
    assert updated.status_code == 200
    assert updated.json()["profileCompleted"] is True
    space, project = create_workspace(alice, welcome=True)
    assert project["name"] == space["name"] and project["workspaceId"] == space["id"]
    assert space["initialProjectId"] == project["id"] and not space["onboardingCompleted"]
    assert len(alice.get("/api/issues").json()) == 3
    completed = alice.post(f'/api/workspaces/{space["id"]}/onboarding/complete', json={})
    assert completed.json()["onboardingCompleted"] is True
    first = alice.get("/api/issues").json()[0]
    assert alice.delete(f'/api/issues/{first["id"]}').status_code == 204
    assert bob.get("/api/workspaces").json() == []
    reopened = create_app(target)
    with TestClient(reopened, base_url="http://127.0.0.1:4310") as restarted:
        restarted.cookies.update(alice.cookies)
        restarted.headers.update({"X-Workspace-Id": str(space["id"])})
        assert restarted.get("/api/auth/me").json()["user"]["displayName"] == "Alice Exemple"
        assert restarted.get("/api/workspaces").json()[0]["onboardingCompleted"] is True
        assert len(restarted.get("/api/issues").json()) == 2
        assert restarted.get(f'/api/issues/{first["id"]}').status_code == 404


def test_all_resource_ids_and_settings_are_scoped(workspace_people):
    app, (alice, _, _), _target = workspace_people
    first, first_project = create_workspace(alice, "premier-espace")
    label = alice.post("/api/labels", json={"name": "Confidentiel"}).json()
    ticket = issue(alice, first_project["id"], labelIds=[label["id"]])
    comment = alice.post(f'/api/issues/{ticket["id"]}/comments', json={"body": "Dans le premier espace"}).json()
    view = alice.post("/api/views", json={"name": "Ma vue", "filters": {"projectId": str(first_project["id"])}}).json()
    template = alice.post("/api/templates", json={"name": "Mon modèle", "projectId": first_project["id"], "labelIds": [label["id"]]}).json()
    assert alice.patch("/api/settings", json={"density": "comfortable", "filters": {"projectId": str(first_project["id"])}}).status_code == 200
    second, second_project = create_workspace(alice, "second-espace")
    assert alice.get("/api/projects").json() == [second_project]
    for endpoint in ("issues", "labels", "views", "templates"):
        assert alice.get(f"/api/{endpoint}").json() == []
    assert alice.get("/api/settings").json()["density"] == "compact"
    for method, path, payload in (
        ("get", f'/api/issues/{ticket["id"]}', None),
        ("get", f'/api/issues/{ticket["id"]}/activity', None),
        ("get", f'/api/issues/{ticket["id"]}/comments', None),
        ("patch", f'/api/issues/{ticket["id"]}', {"title": "Wrong space"}),
        ("delete", f'/api/issues/{ticket["id"]}', None),
        ("post", f'/api/issues/{ticket["id"]}/duplicate', {}),
        ("patch", f'/api/issues/{ticket["id"]}/comments/{comment["id"]}', {"body": "wrong"}),
        ("delete", f'/api/projects/{first_project["id"]}', None),
        ("get", f'/api/projects/{first_project["id"]}/members', None),
        ("patch", f'/api/labels/{label["id"]}', {"name": "wrong"}),
        ("delete", f'/api/views/{view["id"]}', None),
        ("patch", f'/api/templates/{template["id"]}', {"name": "wrong"}),
    ):
        response = getattr(alice, method)(path, **({"json": payload} if payload is not None else {}))
        assert response.status_code == 404, (path, response.text)
    for path, payload in (
        ("/api/issues", {"title": "Cross", "projectId": first_project["id"]}),
        ("/api/issues", {"title": "Cross", "projectId": second_project["id"], "labelIds": [label["id"]]}),
        ("/api/views", {"name": "Cross", "filters": {"projectId": str(first_project["id"])}}),
        ("/api/templates", {"name": "Cross", "projectId": first_project["id"]}),
    ):
        assert alice.post(path, json=payload).status_code == 422
    alice.headers["X-Workspace-Id"] = str(first["id"])
    assert alice.get("/api/settings").json()["density"] == "comfortable"
    assert alice.get(f'/api/issues/{ticket["id"]}').json()["title"] == "Ticket persistant"
    assert alice.get("/api/views").json()[0]["id"] == view["id"]


def test_outsider_header_and_workspace_administration_denied(workspace_people):
    _app, (alice, bob, charlie), _target = workspace_people
    space, project = create_workspace(alice)
    bob.headers["X-Workspace-Id"] = str(space["id"])
    for path in ("projects", "issues", "labels", "settings", "views", "templates"):
        assert bob.get(f"/api/{path}").status_code == 404
    assert bob.post("/api/projects", json={"name": "Intrusion", "key": "BAD"}).status_code == 404
    invitation = invite(alice, space, "bob@epita.fr")
    assert charlie.post(f"/api/workspace-invitations/{invitation}/accept", json={}).status_code == 404
    assert bob.post(f"/api/workspace-invitations/{invitation}/accept", json={}).json()["role"] == "member"
    assert bob.get("/api/projects").json()[0]["id"] == project["id"]
    assert bob.patch(f'/api/workspaces/{space["id"]}', json={"name": "Intrusion"}).status_code == 403
    for path in ("invitations", "invite-links"):
        assert bob.get(f'/api/workspaces/{space["id"]}/{path}').status_code == 403
    assert bob.post(f'/api/workspaces/{space["id"]}/invitations', json={"email": "charlie@epita.fr"}).status_code == 403
    assert bob.delete(f'/api/workspaces/{space["id"]}/members/1').status_code == 403
    own_id = alice.get("/api/auth/me").json()["user"]["id"]
    assert alice.delete(f'/api/workspaces/{space["id"]}/members/{own_id}').status_code == 409


def test_future_account_invite_revoke_decline_and_expiry(workspace_people):
    app, (alice, bob, _), _target = workspace_people
    space, _project = create_workspace(alice)
    invitation = invite(alice, space, "future@epita.fr")
    with account(app, "future") as future:
        assert future.get("/api/workspace-invitations").json()[0]["id"] == invitation
        accepted = future.post(f"/api/workspace-invitations/{invitation}/accept", json={})
        assert accepted.json()["id"] == space["id"]
        assert future.post(f"/api/workspace-invitations/{invitation}/accept", json={}).status_code == 404
    declined = invite(alice, space, "bob@epita.fr")
    assert bob.post(f"/api/workspace-invitations/{declined}/decline", json={}).status_code == 204
    assert bob.get("/api/workspaces").json() == []
    revoked = invite(alice, space, "bob@epita.fr")
    assert alice.delete(f'/api/workspaces/{space["id"]}/invitations/{revoked}').status_code == 204
    assert bob.post(f"/api/workspace-invitations/{revoked}/accept", json={}).status_code == 404
    expired = invite(alice, space, "bob@epita.fr")
    with app.state.database.connect(write=True) as connection:
        connection.execute("UPDATE workspace_invitations SET expires_at = ? WHERE id = ?", ("2000-01-01T00:00:00Z", expired))
    assert bob.get("/api/workspace-invitations").json() == []
    assert bob.post(f"/api/workspace-invitations/{expired}/accept", json={}).status_code == 404
    assert alice.post(f'/api/workspaces/{space["id"]}/invitations', json={"email": "wrong@example.com"}).status_code == 422


def test_links_hash_expiry_revoke_and_membership_removal(workspace_people):
    app, (alice, bob, charlie), _target = workspace_people
    space, project = create_workspace(alice)
    ticket = issue(alice, project["id"])
    link = alice.post(f'/api/workspaces/{space["id"]}/invite-links', json={}).json()
    with app.state.database.connect() as connection:
        row = dict(connection.execute("SELECT * FROM workspace_invite_links WHERE id = ?", (link["id"],)).fetchone())
        assert row["token_hash"] == hashlib.sha256(link["token"].encode()).hexdigest()
        assert link["token"] not in str(row)
    assert "token" not in alice.get(f'/api/workspaces/{space["id"]}/invite-links').json()[0]
    assert bob.post("/api/workspace-invite-links/preview", json={"token": link["token"]}).json()["workspaceName"] == space["name"]
    assert bob.get("/api/workspaces").json() == []
    assert bob.post("/api/workspace-invite-links/accept", json={"token": link["token"]}).json()["role"] == "member"
    bob.headers["X-Workspace-Id"] = str(space["id"])
    member_project = bob.post("/api/projects", json={"name": "Projet du membre", "key": "MEMBER"}).json()
    member_issue = issue(bob, member_project["id"])
    members = alice.get(f'/api/projects/{project["id"]}/members').json()
    bob_member = next(member for member in members if member["username"] == "bob")
    assert bob_member["inherited"] and not bob_member["canRemove"]
    assert alice.delete(f'/api/projects/{project["id"]}/members/{bob_member["id"]}').status_code == 409
    assert bob.patch(f'/api/issues/{ticket["id"]}', json={"status": "done"}).status_code == 200
    assert alice.delete(f'/api/workspaces/{space["id"]}/invite-links/{link["id"]}').status_code == 204
    assert charlie.post("/api/workspace-invite-links/accept", json={"token": link["token"]}).status_code == 404
    bob_id = bob.get("/api/auth/me").json()["user"]["id"]
    assert alice.delete(f'/api/workspaces/{space["id"]}/members/{bob_id}').status_code == 204
    assert bob.get("/api/issues").status_code == 404
    del bob.headers["X-Workspace-Id"]
    assert bob.get(f'/api/issues/{ticket["id"]}').status_code == 404
    assert bob.get(f'/api/issues/{member_issue["id"]}').status_code == 404
    assert bob.patch(f'/api/projects/{member_project["id"]}', json={"name": "Former owner"}).status_code == 404
    assert alice.patch(f'/api/projects/{member_project["id"]}', json={"name": "Projet conservé"}).status_code == 200
    assert bob.get("/api/workspaces").json() == []
    expired = alice.post(f'/api/workspaces/{space["id"]}/invite-links', json={}).json()
    with app.state.database.connect(write=True) as connection:
        connection.execute("UPDATE workspace_invite_links SET expires_at = ? WHERE id = ?", ("2000-01-01T00:00:00Z", expired["id"]))
    assert charlie.post("/api/workspace-invite-links/preview", json={"token": expired["token"]}).status_code == 404
    assert charlie.post("/api/workspace-invite-links/accept", json={"token": expired["token"]}).status_code == 404


def test_project_guest_never_gains_other_project_access(workspace_people):
    _app, (alice, bob, _), _target = workspace_people
    space, initial = create_workspace(alice)
    other = alice.post("/api/projects", json={"name": "Autre projet", "key": "AUTRE"}).json()
    hidden_issue = issue(alice, other["id"])
    shared_issue = issue(alice, initial["id"])
    invitation = alice.post(f'/api/projects/{initial["id"]}/invitations', json={"email": "bob@epita.fr"}).json()
    assert bob.get("/api/invitations").json()[0]["workspaceId"] == space["id"]
    assert bob.post(f'/api/invitations/{invitation["id"]}/accept', json={}).status_code == 204
    guest_space = bob.get("/api/workspaces").json()[0]
    assert guest_space["role"] == "guest"
    bob.headers["X-Workspace-Id"] = str(space["id"])
    assert [p["id"] for p in bob.get("/api/projects").json()] == [initial["id"]]
    assert bob.get(f'/api/issues/{hidden_issue["id"]}').status_code == 404
    assert bob.patch(f'/api/issues/{shared_issue["id"]}', json={"status": "done"}).status_code == 200
    assert bob.post("/api/projects", json={"name": "Unauthorized", "key": "BAD"}).status_code == 403
    assert len(bob.get(f'/api/workspaces/{space["id"]}/members').json()) == 1
    label = alice.post("/api/labels", json={"name": "Partagée temporairement"}).json()
    assert alice.patch(f'/api/issues/{shared_issue["id"]}', json={"labelIds": [label["id"]]}).status_code == 200
    assert bob.patch("/api/settings", json={"filters": {"projectId": str(initial["id"]), "labelIds": [label["id"]]}}).status_code == 200
    assert bob.post("/api/views", json={"name": "Vue partagée", "filters": {"projectId": str(initial["id"]), "labelIds": [label["id"]]}}).status_code == 201
    bob_id = bob.get("/api/auth/me").json()["user"]["id"]
    assert alice.delete(f'/api/projects/{initial["id"]}/members/{bob_id}').status_code == 204
    assert bob.get("/api/projects").json() == []
    assert bob.get("/api/workspaces").json()[0]["initialProjectId"] is None
    assert bob.get("/api/settings").json()["filters"]["labelIds"] == []
    assert bob.get("/api/settings").json()["filters"]["projectId"] == ""
    assert bob.get("/api/views").json()[0]["filters"]["labelIds"] == []
    assert bob.get("/api/views").json()[0]["filters"]["projectId"] == ""


def test_legacy_unscoped_clients_cannot_attach_labels_across_workspaces(workspace_people):
    _app, (alice, _, _), _target = workspace_people
    first, project = create_workspace(alice)
    label = alice.post("/api/labels", json={"name": "Premier espace"}).json()
    _second, second_project = create_workspace(alice, "autre-espace")
    second_label = alice.post("/api/labels", json={"name": "Second espace"}).json()
    ticket = issue(alice, second_project["id"])
    del alice.headers["X-Workspace-Id"]
    assert alice.patch(f'/api/labels/{label["id"]}', json={"name": "Même nom"}).status_code == 200
    assert alice.patch(f'/api/labels/{second_label["id"]}', json={"name": "Même nom"}).status_code == 200
    assert alice.post("/api/issues", json={"title": "Cross", "projectId": second_project["id"], "labelIds": [label["id"]]}).status_code == 422
    assert alice.patch(f'/api/issues/{ticket["id"]}', json={"labelIds": [label["id"]]}).status_code == 422
    alice.headers["X-Workspace-Id"] = str(first["id"])
    valid = issue(alice, project["id"], labelIds=[label["id"]])
    del alice.headers["X-Workspace-Id"]
    assert alice.patch(f'/api/issues/{valid["id"]}', json={"projectId": second_project["id"]}).status_code == 422


def test_workspace_creation_validation_and_transaction_rollback(workspace_people, monkeypatch):
    app, (alice, _, _), _target = workspace_people
    first, _ = create_workspace(alice)
    for slug in ("NO CAPS", "ab", "with/slash", "-leading", "trailing-", "x" * 65):
        assert alice.post("/api/workspaces", json={"name": "Test", "slug": slug}).status_code == 422
    assert alice.post("/api/workspaces", json={"name": "Duplicate", "slug": first["slug"]}).status_code == 409
    assert len(alice.get("/api/workspaces").json()) == 1
    from backend.app.repositories.workspace import WorkspaceRepository
    def fail_create(*args, **kwargs):
        raise sqlite3.IntegrityError("Simulated welcome issue failure")
    monkeypatch.setattr(WorkspaceRepository, "create_issue", fail_create)
    assert alice.post("/api/workspaces", json={"name": "Rollback", "slug": "rollback-test"}).status_code == 409
    with app.state.database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 1


def test_csrf_profile_and_workspace_mutations_remain_protected(workspace_people):
    _app, (alice, _, _), _target = workspace_people
    space, _ = create_workspace(alice)
    del alice.headers["X-CSRF-Token"]
    assert alice.post("/api/workspaces", json={"name": "No CSRF", "slug": "no-csrf"}).status_code == 403
    assert alice.patch("/api/auth/profile", json={"displayName": "Wrong", "title": ""}).status_code == 403
    assert alice.post(f'/api/workspaces/{space["id"]}/invite-links', json={}).status_code == 403
    for invalid in ("0", "-1", "1,2", "abc", "9223372036854775808"):
        alice.headers["X-Workspace-Id"] = invalid
        assert alice.get("/api/projects").status_code == 422


def test_backfill_is_idempotent_and_preserves_private_project_access(workspace_people):
    app, (alice, bob, _), _target = workspace_people
    project = alice.post("/api/projects", json={"name": "Ancien partagé", "key": "OLD"}).json()
    hidden = alice.post("/api/projects", json={"name": "Ancien privé", "key": "PVT"}).json()
    visible_issue, hidden_issue = issue(alice, project["id"]), issue(alice, hidden["id"])
    invitation = alice.post(f'/api/projects/{project["id"]}/invitations', json={"email": "bob@epita.fr"}).json()
    assert bob.post(f'/api/invitations/{invitation["id"]}/accept', json={}).status_code == 204
    with app.state.database.connect(write=True) as connection:
        backfill_workspaces(connection)
        backfill_workspaces(connection)
        assert connection.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM projects WHERE visibility = 'private'").fetchone()[0] == 2
    space = bob.get("/api/workspaces").json()[0]
    assert space["role"] == "guest" and space["onboardingCompleted"]
    bob.headers["X-Workspace-Id"] = str(space["id"])
    assert bob.get(f'/api/issues/{visible_issue["id"]}').status_code == 200
    assert bob.get(f'/api/issues/{hidden_issue["id"]}').status_code == 404
    assert [item["id"] for item in bob.get("/api/projects").json()] == [project["id"]]


def test_backfill_marker_survives_slug_collision_and_rename(workspace_people):
    app, (alice, bob, _), _target = workspace_people
    alice_id = alice.get("/api/auth/me").json()["user"]["id"]
    create_workspace(bob, f"personnel-{alice_id}")
    alice.post("/api/projects", json={"name": "Ancien", "key": "MIG"})
    with app.state.database.connect(write=True) as connection:
        backfill_workspaces(connection)
    space = alice.get("/api/workspaces").json()[0]
    assert space["slug"] == f"personnel-{alice_id}-1"
    assert alice.patch(f'/api/workspaces/{space["id"]}', json={"slug": "renomme-par-alice"}).status_code == 200
    alice.post("/api/projects", json={"name": "Autre ancien", "key": "MIG2"})
    with app.state.database.connect(write=True) as connection:
        backfill_workspaces(connection)
    assert len(alice.get("/api/workspaces").json()) == 1
    alice.headers["X-Workspace-Id"] = str(space["id"])
    assert len(alice.get("/api/projects").json()) == 2


def test_display_name_is_used_in_comments_and_activity(workspace_people):
    _app, (alice, _, _), _target = workspace_people
    _space, project = create_workspace(alice)
    assert alice.patch("/api/auth/profile", json={"displayName": "Alice Exemple", "title": "Design"}).status_code == 200
    ticket = issue(alice, project["id"])
    comment = alice.post(f'/api/issues/{ticket["id"]}/comments', json={"body": "Bonjour"})
    assert comment.json()["author"]["displayName"] == "Alice Exemple"
    assert alice.get(f'/api/issues/{ticket["id"]}/activity').json()[-1]["actor"]["displayName"] == "Alice Exemple"


def test_postgres_member_creation_and_removal_do_not_deadlock(postgres_url, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from backend.app.repositories.workspace import WorkspaceRepository
    from backend.app.repositories.spaces import SpacesRepository
    from backend.app.services.workspace import WorkspaceService
    from backend.app.services.spaces import SpacesService
    from backend.app.schemas.workspace import ProjectCreate

    app = create_app(postgres_url)
    with account(app, "owner") as owner, account(app, "member") as member:
        space, _project = create_workspace(owner)
        invitation = invite(owner, space, "member@epita.fr")
        assert member.post(f"/api/workspace-invitations/{invitation}/accept", json={}).status_code == 200
        owner_id = owner.get("/api/auth/me").json()["user"]["id"]
        member_id = member.get("/api/auth/me").json()["user"]["id"]
        writer_ready, workspace_locked, continue_writer = Event(), Event(), Event()
        original_create, original_workspace = WorkspaceRepository.create_project, SpacesRepository.workspace

        def gated_create(repo, data):
            if repo.user_id == member_id:
                writer_ready.set()
                assert continue_writer.wait(10)
            return original_create(repo, data)

        def observed_lock(repo, workspace_id, *, lock=False):
            result = original_workspace(repo, workspace_id, lock=lock)
            if lock and repo.user_id == owner_id:
                workspace_locked.set()
            return result

        monkeypatch.setattr(WorkspaceRepository, "create_project", gated_create)
        monkeypatch.setattr(SpacesRepository, "workspace", observed_lock)
        with ThreadPoolExecutor(max_workers=2) as executor:
            writer = executor.submit(WorkspaceService(app.state.database, member_id, space["id"]).create_project,
                ProjectCreate(name="Concurrent", key="CONCURRENT").model_dump())
            assert writer_ready.wait(10)
            removal = executor.submit(SpacesService(app.state.database, owner_id).remove_member, space["id"], member_id)
            try:
                assert workspace_locked.wait(10)
            finally:
                continue_writer.set()
            created = writer.result(timeout=15)
            assert removal.result(timeout=15) is None
        assert member.get("/api/projects").json() == []
        assert any(project["id"] == created["id"] for project in owner.get("/api/projects").json())


def pending_guest_invitations(owner, guest):
    space, project = create_workspace(owner)
    guest_email = guest.get("/api/auth/me").json()["user"]["email"]
    initial = owner.post(f'/api/projects/{project["id"]}/invitations', json={"email": guest_email}).json()["id"]
    assert guest.post(f"/api/invitations/{initial}/accept", json={}).status_code == 204
    other_project = owner.post("/api/projects", json={"name": "Projet suivant", "key": "NEXT"}).json()
    project_invitation = owner.post(f'/api/projects/{other_project["id"]}/invitations', json={"email": guest_email}).json()["id"]
    workspace_invitation = invite(owner, space, guest_email)
    return space, workspace_invitation, project_invitation


def test_removal_revokes_all_targeted_pending_invitations(workspace_people):
    _app, (alice, bob, charlie), _target = workspace_people
    space, workspace_invitation, project_invitation = pending_guest_invitations(alice, bob)
    untouched = invite(alice, space, "charlie@epita.fr")
    bob_id = bob.get("/api/auth/me").json()["user"]["id"]
    assert alice.delete(f'/api/workspaces/{space["id"]}/members/{bob_id}').status_code == 204
    assert bob.get("/api/workspace-invitations").json() == []
    assert bob.get("/api/invitations").json() == []
    assert bob.post(f"/api/workspace-invitations/{workspace_invitation}/accept", json={}).status_code == 404
    assert bob.post(f"/api/invitations/{project_invitation}/accept", json={}).status_code == 404
    assert bob.get("/api/workspaces").json() == []
    assert charlie.get("/api/workspace-invitations").json()[0]["id"] == untouched
    assert charlie.post(f"/api/workspace-invitations/{untouched}/accept", json={}).status_code == 200


@pytest.mark.parametrize("kind", ["workspace", "project"])
@pytest.mark.parametrize("first", ["removal", "acceptance"])
def test_postgres_pending_invitation_acceptance_and_removal_are_serialized(postgres_url, monkeypatch, kind, first):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from backend.app.repositories.spaces import SpacesRepository
    from backend.app.repositories.sharing import SharingRepository
    from backend.app.services.spaces import SpacesService
    from backend.app.services.sharing import SharingService
    from backend.app.services.workspace import DomainError

    app = create_app(postgres_url)
    with account(app, "owner") as owner, account(app, "guest") as guest:
        space, workspace_invitation, project_invitation = pending_guest_invitations(owner, guest)
        owner_id = owner.get("/api/auth/me").json()["user"]["id"]
        guest_user = guest.get("/api/auth/me").json()["user"]
        repo_type = SpacesRepository if kind == "workspace" else SharingRepository
        original_workspace = SpacesRepository.workspace
        original_invitation = repo_type.invitation
        original_lock = repo_type.lock_invitation_workspace
        first_holds_lock, other_arrived, continue_first = Event(), Event(), Event()

        def workspace_gate(repo, workspace_id, *, lock=False):
            if lock and repo.user_id == owner_id and first == "acceptance":
                other_arrived.set()
            result = original_workspace(repo, workspace_id, lock=lock)
            if lock and repo.user_id == owner_id and first == "removal":
                first_holds_lock.set()
                assert continue_first.wait(10)
            return result

        def invitation_observed(repo, invitation_id, recipient, *, lock=True):
            result = original_invitation(repo, invitation_id, recipient, lock=lock)
            if not lock and first == "removal":
                other_arrived.set()
            return result

        def acceptance_gate(repo, container_id):
            original_lock(repo, container_id)
            if first == "acceptance":
                first_holds_lock.set()
                assert continue_first.wait(10)

        monkeypatch.setattr(SpacesRepository, "workspace", workspace_gate)
        monkeypatch.setattr(repo_type, "invitation", invitation_observed)
        monkeypatch.setattr(repo_type, "lock_invitation_workspace", acceptance_gate)

        def accept_pending():
            if kind == "workspace":
                return SpacesService(app.state.database, guest_user["id"]).respond(workspace_invitation, guest_user["email"], True)
            return SharingService(app.state.database, guest_user["id"]).respond(project_invitation, True)

        def remove_guest():
            return SpacesService(app.state.database, owner_id).remove_member(space["id"], guest_user["id"])

        with ThreadPoolExecutor(max_workers=2) as executor:
            leading = executor.submit(remove_guest if first == "removal" else accept_pending)
            try:
                assert first_holds_lock.wait(10)
                following = executor.submit(accept_pending if first == "removal" else remove_guest)
                assert other_arrived.wait(10)
            finally:
                continue_first.set()
            leading.result(timeout=15)
            if first == "removal":
                with pytest.raises(DomainError) as error:
                    following.result(timeout=15)
                assert error.value.status == 404
            else:
                assert following.result(timeout=15) is None
        assert guest.get("/api/workspaces").json() == []
        assert guest.get("/api/projects").json() == []
        assert guest.get("/api/invitations").json() == []
        assert guest.get("/api/workspace-invitations").json() == []
