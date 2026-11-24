"""OAuth and MCP on the real FastAPI routes, with actual workspace memberships."""
import base64
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
import pytest

from backend.app.main import create_app
from backend.app.services.auth import verifier
from tests.test_postgres import postgres_url  # noqa: F401
from tests.test_workspaces import account, create_workspace, issue

ORIGIN = "http://127.0.0.1:4310"
RESOURCE = f"{ORIGIN}/mcp"
CALLBACK = "https://claude.ai/api/mcp/auth_callback"
VERIFIER = "circular-test-code-verifier-with-enough-characters"
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).decode().rstrip("=")
ACCEPT = {"Accept": "application/json, text/event-stream"}
READ = "circular:read"
WRITE = "circular:read circular:write"


@pytest.fixture(params=["sqlite", "postgres"])
def mcp_app(request, tmp_path, monkeypatch):
    monkeypatch.setenv("CIRCULAR_PUBLIC_URL", ORIGIN)
    target = request.getfixturevalue("postgres_url") if request.param == "postgres" else tmp_path / "mcp.sqlite"
    app = create_app(target)
    with TestClient(app, base_url=ORIGIN, follow_redirects=False) as client:
        yield app, client


def register(client, redirect_uri=CALLBACK):
    return client.post("/register", json={
        "redirect_uris": [redirect_uri], "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
    })


def authorize(client, client_id, **overrides):
    return client.get("/authorize", params={
        "client_id": client_id, "redirect_uri": CALLBACK, "response_type": "code", "state": "test-state",
        "code_challenge": CHALLENGE, "code_challenge_method": "S256", "resource": RESOURCE, **overrides,
    }, headers={"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"})


def request_id(response):
    assert response.is_redirect, response.text
    return parse_qs(urlsplit(response.headers["location"]).fragment)["mcp"][0]


def approve(user, pending, workspace_id, *, write=False):
    response = user.post("/api/mcp/consent/decision", json={"requestId": pending, "workspaceId": workspace_id, "write": write})
    assert response.status_code == 200, response.text
    parts = parse_qs(urlsplit(response.json()["redirectUrl"]).query)
    assert parts.pop("state") == ["test-state"]
    return parts


def exchange(client, client_id, code, **overrides):
    return client.post("/token", data={
        "grant_type": "authorization_code", "client_id": client_id, "code": code,
        "code_verifier": VERIFIER, "redirect_uri": CALLBACK, "resource": RESOURCE, **overrides,
    })


def refresh(client, client_id, refresh_token, **overrides):
    return client.post("/token", data={"grant_type": "refresh_token", "client_id": client_id,
                                       "refresh_token": refresh_token, **overrides})


def rpc(client, token, method, params=None):
    headers = {**ACCEPT, **({"Authorization": f"Bearer {token}"} if token else {})}
    return client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})


def tool(client, token, name, **arguments):
    response = rpc(client, token, "tools/call", {"name": name, "arguments": arguments})
    assert response.status_code == 200, response.text
    return response.json()["result"]


def test_mcp_permissions_and_revocation(mcp_app):
    app, client = mcp_app
    alice, bob = account(app, "alice"), account(app, "bob")
    space, project = create_workspace(alice, "premier-espace")
    shared = issue(alice, project["id"], title="Première panne", priority="urgent")
    next_ticket = issue(alice, project["id"], title="Deuxième panne", priority="urgent")
    issue(alice, project["id"], title="Panne mineure", priority="low")
    private = alice.post("/api/projects", json={"name": "Autre projet", "key": "AUTRE"}).json()
    private_ticket = issue(alice, private["id"], title="Panne projet privé", priority="urgent")
    invite = alice.post(f'/api/projects/{project["id"]}/invitations', json={"email": "bob@epita.fr"}).json()
    assert bob.post(f'/api/invitations/{invite["id"]}/accept', json={}).status_code == 204
    second, other_project = create_workspace(alice, "second-espace")
    other_ticket = issue(alice, other_project["id"], title="Panne autre espace", priority="urgent")

    unauthenticated = rpc(client, None, "tools/list")
    assert unauthenticated.status_code == 401
    assert "/.well-known/oauth-protected-resource/mcp" in unauthenticated.headers["www-authenticate"]
    assert client.get("/.well-known/oauth-protected-resource/mcp").json()["resource"] == RESOURCE
    assert client.get("/.well-known/oauth-authorization-server").json()["token_endpoint"] == f"{ORIGIN}/token"
    assert register(client, "https://example.org/callback").status_code == 400
    assert register(client, "https://chatgpt.com/connector/oauth/test-callback").status_code == 201
    registered = register(client)
    assert registered.status_code == 201, registered.text
    client_id = registered.json()["client_id"]
    pending = request_id(authorize(client, client_id))
    assert bob.post("/api/mcp/consent", json={"requestId": pending}).json() == {
        "client": "Claude", "write": False, "workspaces": [{"id": space["id"], "name": space["name"]}],
    }
    assert bob.post("/api/mcp/consent/decision", json={"requestId": pending, "workspaceId": second["id"]}).status_code == 404
    code = approve(bob, pending, space["id"])["code"][0]
    assert bob.post("/api/mcp/consent", json={"requestId": pending}).status_code == 404
    assert exchange(client, client_id, code, code_verifier="incorrect").status_code == 400
    assert exchange(client, client_id, code, resource=f"{ORIGIN}/other").status_code == 400
    issued = exchange(client, client_id, code)
    assert issued.status_code == 200, issued.text
    first = issued.json()
    assert exchange(client, client_id, code).status_code == 400
    _, bob_project = create_workspace(bob, "espace-de-bob")
    bob_ticket = issue(bob, bob_project["id"], title="Panne dans mon autre espace", priority="urgent")

    refreshed = client.post("/token", data={"grant_type": "refresh_token", "client_id": client_id, "refresh_token": first["refresh_token"]})
    assert refreshed.status_code == 200, refreshed.text
    assert rpc(client, first["access_token"], "tools/list").status_code == 401
    token = refreshed.json()["access_token"]
    initialized = rpc(client, token, "initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                                     "clientInfo": {"name": "Circular test", "version": "1"}})
    assert initialized.json()["result"]["serverInfo"]["name"] == "Circular"
    names = {entry["name"]: entry for entry in rpc(client, token, "tools/list").json()["result"]["tools"]}
    assert all(names[name]["annotations"]["readOnlyHint"] for name in ("list_projects", "search_tickets", "get_ticket"))
    assert all(not names[name]["annotations"]["readOnlyHint"] for name in ("create_ticket", "add_comment"))
    unapproved = rpc(client, token, "tools/call", {"name": "get_ticket_context", "arguments": {"reference": shared["identifier"]}})
    assert unapproved.status_code == 403
    assert 'scope="circular:read circular:tickets:read"' in unapproved.headers["www-authenticate"]
    projects = tool(client, token, "list_projects")["structuredContent"]
    assert [item["id"] for item in projects["items"]] == [project["id"]]
    first_page = tool(client, token, "search_tickets", query="panne", priority="urgent", limit=1)["structuredContent"]
    assert [item["id"] for item in first_page["items"]] == [shared["id"]]
    assert first_page["nextCursor"] == shared["id"]
    second_page = tool(client, token, "search_tickets", query="panne", priority="urgent", limit=1,
                       cursor=first_page["nextCursor"])["structuredContent"]
    assert [item["id"] for item in second_page["items"]] == [next_ticket["id"]]
    assert second_page["nextCursor"] is None
    assert tool(client, token, "search_tickets", query="introuvable")["structuredContent"]["items"] == []
    assert tool(client, token, "get_ticket", ticket_id=shared["id"])["structuredContent"]["title"] == shared["title"]
    for hidden in (private_ticket, other_ticket, bob_ticket):
        result = tool(client, token, "get_ticket", ticket_id=hidden["id"])
        assert result["isError"] and "Ticket introuvable" in result["content"][0]["text"]

    connection_id = bob.get("/api/mcp/connections").json()["connections"][0]["id"]
    assert alice.delete(f"/api/mcp/connections/{connection_id}").status_code == 204
    assert rpc(client, token, "tools/list").status_code == 200
    assert bob.delete(f"/api/mcp/connections/{connection_id}").status_code == 204
    assert rpc(client, token, "tools/list").status_code == 401
    assert refresh(client, client_id, refreshed.json()["refresh_token"]).status_code == 400


def test_mcp_mvp_grant_stays_read_only_after_migration(mcp_app):
    app, client = mcp_app
    owner = account(app, "alice")
    space, project = create_workspace(owner)
    ticket = issue(owner, project["id"], title="Ticket de référence")
    client_id = register(client).json()["client_id"]
    pending = request_id(authorize(client, client_id))
    code = approve(owner, pending, space["id"])["code"][0]
    grant = exchange(client, client_id, code).json()
    # Reconstitute the pre-V2 schema with the persisted grant, then apply the real migration.
    database = app.state.database
    with database.connect(write=True) as db:
        db.execute("DROP TABLE mcp_writes")
        db.execute("ALTER TABLE mcp_connections DROP COLUMN scope")
        db.execute("DELETE FROM schema_migrations WHERE version = '016_mcp_write.sql'")
    database.migrate()
    assert refresh(client, client_id, grant["refresh_token"], scope=WRITE).json()["error"] == "invalid_scope"
    renewed = refresh(client, client_id, grant["refresh_token"]).json()
    assert renewed["scope"] == READ
    assert tool(client, renewed["access_token"], "list_projects")["structuredContent"]["items"][0]["id"] == project["id"]
    assert tool(client, renewed["access_token"], "search_tickets")["structuredContent"]["items"][0]["id"] == ticket["id"]
    assert tool(client, renewed["access_token"], "get_ticket", ticket_id=ticket["id"])["structuredContent"]["id"] == ticket["id"]
    for name, arguments in [
        ("create_ticket", {"project_id": project["id"], "title": "Création refusée", "request_key": "legacy-create-0001"}),
        ("add_comment", {"ticket_id": ticket["id"], "body": "Commentaire refusé", "request_key": "legacy-comment-001"}),
    ]:
        denied = rpc(client, renewed["access_token"], "tools/call", {"name": name, "arguments": arguments})
        assert denied.status_code == 403
        assert denied.json()["error"] == "insufficient_scope"
        assert f'scope="{WRITE}"' in denied.headers["www-authenticate"]
        assert "/.well-known/oauth-protected-resource/mcp" in denied.headers["www-authenticate"]
    assert [item["id"] for item in owner.get("/api/issues").json()] == [ticket["id"]]
    assert owner.get(f'/api/issues/{ticket["id"]}/comments').json() == []


def test_mcp_explicit_write_grant_and_project_permissions(mcp_app):
    app, client = mcp_app
    alice, bob, charlie = (account(app, name) for name in ("alice", "bob", "charlie"))
    space, project = create_workspace(alice)
    private = alice.post("/api/projects", json={"name": "Privé", "key": "PRIVE"}).json()
    with app.state.database.connect(write=True) as db:
        db.execute("UPDATE projects SET visibility = 'private' WHERE id = ?", (private["id"],))
    private_ticket = issue(alice, private["id"])
    invitation = alice.post(f'/api/projects/{project["id"]}/invitations', json={"email": "bob@epita.fr"}).json()
    assert bob.post(f'/api/invitations/{invitation["id"]}/accept', json={}).status_code == 204
    invitation = alice.post(f'/api/workspaces/{space["id"]}/invitations', json={"email": "charlie@epita.fr"}).json()
    assert charlie.post(f'/api/workspace-invitations/{invitation["id"]}/accept', json={}).status_code == 200
    _, other = create_workspace(bob, "ailleurs")
    other_ticket = issue(bob, other["id"])
    for user in (bob, charlie):
        user.headers["X-Workspace-Id"] = str(space["id"])
        assert user.get(f'/api/issues/{private_ticket["id"]}').status_code == 404
    client_id = register(client).json()["client_id"]
    pending = request_id(authorize(client, client_id, scope=WRITE))
    assert bob.post("/api/mcp/consent", json={"requestId": pending}).json()["write"] is True
    wrong_agreement = bob.post("/api/mcp/consent/decision", json={"requestId": pending, "workspaceId": space["id"]})
    assert wrong_agreement.status_code == 422
    assert approve(bob, pending, None) == {"error": ["access_denied"]}
    assert bob.get("/api/mcp/connections").json()["connections"] == []

    def connect(user, scope, write):
        code = approve(user, request_id(authorize(client, client_id, scope=scope)), space["id"], write=write)["code"][0]
        response = exchange(client, client_id, code)
        assert response.status_code == 200, response.text
        assert response.json()["scope"] == scope
        return response.json()

    read = connect(bob, READ, False)
    grant = connect(bob, WRITE, True)
    grant = refresh(client, client_id, grant["refresh_token"]).json()
    assert grant["scope"] == WRITE
    token = grant["access_token"]
    assert {item["write"] for item in bob.get("/api/mcp/connections").json()["connections"]} == {False, True}
    for user in (alice, charlie):
        allowed = connect(user, WRITE, True)["access_token"]
        manual = issue(user, project["id"], title="Ticket manuel")
        created = tool(client, allowed, "create_ticket", project_id=project["id"], title="Ticket MCP", request_key="action-create-0001")["structuredContent"]
        assert parse_qs(urlsplit(created["url"]).query)["issue"] == [str(created["id"])]
        manual = user.get(f'/api/issues/{manual["id"]}').json()
        persisted = user.get(f'/api/issues/{created["id"]}').json()
        assert (persisted["status"], persisted["priority"]) == (manual["status"], manual["priority"])

    manual = issue(bob, project["id"], title="Ticket invité")
    arguments = {"project_id": project["id"], "title": "Ticket issu d’une relance", "request_key": "concurrent-create-01"}
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: tool(client, token, "create_ticket", **arguments), range(2)))
    created = results[0]["structuredContent"]
    assert results[1]["structuredContent"] == created
    assert [row["id"] for row in bob.get("/api/issues").json() if row["title"] == arguments["title"]] == [created["id"]]
    assert tool(client, token, "create_ticket", **{**arguments, "title": "Autre contenu"})["isError"]
    assert tool(client, token, "create_ticket", **{**arguments, "title": "   "})["isError"]

    assert bob.post(f'/api/issues/{manual["id"]}/comments', json={"body": "Commentaire manuel"}).status_code == 201
    comment = {"ticket_id": created["id"], "body": "Compte rendu", "request_key": "retry-comment-0001"}
    first = tool(client, token, "add_comment", **comment)["structuredContent"]
    assert tool(client, token, "add_comment", **comment)["structuredContent"] == first
    comments = bob.get(f'/api/issues/{created["id"]}/comments').json()
    assert [(entry["id"], entry["body"], entry["author"]["username"]) for entry in comments] == [(first["id"], "Compte rendu", "bob")]
    activity = bob.get(f'/api/issues/{created["id"]}/activity').json()
    assert [(event["kind"], event["actor"]["username"]) for event in activity] == [("created", "bob"), ("comment_created", "bob")]
    for hidden_project, hidden_ticket in [(private, private_ticket), (other, other_ticket)]:
        denied = tool(client, token, "create_ticket", **{**arguments, "project_id": hidden_project["id"], "request_key": "hidden-create-0001"})
        assert denied["isError"] and "Projet introuvable" in denied["content"][0]["text"]
        denied = tool(client, token, "add_comment", **{**comment, "ticket_id": hidden_ticket["id"], "request_key": "hidden-comment-001"})
        assert denied["isError"] and "Ticket introuvable" in denied["content"][0]["text"]
    with app.state.database.connect() as db:
        for hidden_ticket in (private_ticket, other_ticket):
            persisted = db.execute("SELECT COUNT(*) FROM comments WHERE issue_id = ?", (hidden_ticket["id"],)).fetchone()[0]
            assert persisted == 0
        for hidden_project in (private, other):
            persisted = db.execute("SELECT COUNT(*) FROM issues WHERE project_id = ?", (hidden_project["id"],)).fetchone()[0]
            assert persisted == 1

    bob_id = bob.get("/api/auth/me").json()["user"]["id"]
    assert alice.delete(f'/api/projects/{project["id"]}/members/{bob_id}').status_code == 204
    denied = tool(client, token, "add_comment", **comment)
    assert denied["isError"] and "Ticket introuvable" in denied["content"][0]["text"]
    denied = tool(client, token, "create_ticket", **arguments)
    assert denied["isError"] and "Projet introuvable" in denied["content"][0]["text"]
    connection = next(row for row in bob.get("/api/mcp/connections").json()["connections"] if row["write"])
    assert bob.delete(f'/api/mcp/connections/{connection["id"]}').status_code == 204
    assert rpc(client, token, "tools/list").status_code == 401
    assert refresh(client, client_id, grant["refresh_token"]).status_code == 400
    assert rpc(client, read["access_token"], "tools/list").status_code == 200


def test_mcp_denial_expiry_and_membership_removal(mcp_app):
    app, client = mcp_app
    alice, bob = account(app, "alice"), account(app, "bob")
    workspace, _ = create_workspace(alice)
    client_id = register(client).json()["client_id"]
    pending = request_id(authorize(client, client_id))
    assert approve(alice, pending, None) == {"error": ["access_denied"]}
    assert alice.get("/api/mcp/connections").json()["connections"] == []

    expired = request_id(authorize(client, client_id))
    with app.state.database.connect(write=True) as db:
        db.execute("UPDATE mcp_authorizations SET expires_at = 0")
    assert alice.post("/api/mcp/consent", json={"requestId": expired}).status_code == 404

    invitation = alice.post(f'/api/workspaces/{workspace["id"]}/invitations', json={"email": "bob@epita.fr"}).json()
    assert bob.post(f'/api/workspace-invitations/{invitation["id"]}/accept', json={}).status_code == 200
    code = approve(bob, request_id(authorize(client, client_id)), workspace["id"])["code"][0]
    issued = exchange(client, client_id, code).json()
    token = issued["access_token"]
    assert rpc(client, token, "tools/list").status_code == 200
    with app.state.database.connect(write=True) as db:
        db.execute("UPDATE mcp_connections SET access_expires_at = 0")
    assert rpc(client, token, "tools/list").status_code == 401
    refreshed = refresh(client, client_id, issued["refresh_token"]).json()
    token = refreshed["access_token"]
    assert rpc(client, token, "tools/list").status_code == 200
    bob_id = bob.get("/api/auth/me").json()["user"]["id"]
    assert alice.delete(f'/api/workspaces/{workspace["id"]}/members/{bob_id}').status_code == 204
    assert rpc(client, token, "tools/list").status_code == 401


def test_mcp_revocation_wins_over_an_in_flight_write(postgres_url, monkeypatch):
    monkeypatch.setenv("CIRCULAR_PUBLIC_URL", ORIGIN)
    app = create_app(postgres_url)
    with TestClient(app, base_url=ORIGIN, follow_redirects=False) as client, ThreadPoolExecutor(max_workers=1) as executor:
        owner = account(app, "alice")
        space, project = create_workspace(owner)
        client_id = register(client).json()["client_id"]
        pending = request_id(authorize(client, client_id, scope=WRITE))
        code = approve(owner, pending, space["id"], write=True)["code"][0]
        token = exchange(client, client_id, code).json()["access_token"]
        token_hash = verifier(token)
        with app.state.database.connect(write=True) as db:
            db.execute("SELECT id FROM mcp_connections WHERE access_hash = ? FOR UPDATE", (token_hash,)).fetchone()
            write = executor.submit(tool, client, token, "create_ticket", project_id=project["id"],
                                    title="Écriture en attente", request_key="waiting-create-001")
            deadline = time.monotonic() + 5
            while not db.execute("""SELECT EXISTS (SELECT 1 FROM pg_locks
                WHERE NOT granted AND pg_backend_pid() = ANY(pg_blocking_pids(pid)))""").fetchone()[0]:
                assert not write.done() and time.monotonic() < deadline, "L’écriture doit attendre le verrou de l’autorisation."
                time.sleep(0.02)
            db.execute("DELETE FROM mcp_connections WHERE access_hash = ?", (token_hash,))
        denied = write.result(timeout=5)
        assert denied["isError"] and "Accès à Circular non autorisé" in denied["content"][0]["text"]
        assert owner.get("/api/issues").json() == []


def test_mcp_create_ticket_accepts_concurrent_project_references(postgres_url, monkeypatch):
    monkeypatch.setenv("CIRCULAR_PUBLIC_URL", ORIGIN)
    app = create_app(postgres_url)
    with TestClient(app, base_url=ORIGIN, follow_redirects=False) as client, ThreadPoolExecutor(max_workers=1) as executor:
        owner = account(app, "alice")
        space, project = create_workspace(owner)
        client_id = register(client).json()["client_id"]
        pending = request_id(authorize(client, client_id, scope=WRITE))
        code = approve(owner, pending, space["id"], write=True)["code"][0]
        token = exchange(client, client_id, code).json()["access_token"]
        with app.state.database.connect(write=True) as db:
            # A concurrent insertion referencing this project takes this lock for its foreign key.
            db.execute("SELECT id FROM projects WHERE id = ? FOR KEY SHARE", (project["id"],)).fetchone()
            write = executor.submit(tool, client, token, "create_ticket", project_id=project["id"],
                                    title="Ticket créé en parallèle", request_key="parallel-create-001")
            created = write.result(timeout=5)["structuredContent"]
        assert owner.get(f'/api/issues/{created["id"]}').json()["title"] == "Ticket créé en parallèle"
