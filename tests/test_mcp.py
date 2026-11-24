"""OAuth and MCP on the real FastAPI routes, with actual workspace memberships."""
import base64
import hashlib
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
import pytest

from backend.app.main import create_app
from tests.test_postgres import postgres_url  # noqa: F401
from tests.test_workspaces import account, create_workspace, issue

ORIGIN = "http://127.0.0.1:4310"
RESOURCE = f"{ORIGIN}/mcp"
CALLBACK = "https://claude.ai/api/mcp/auth_callback"
VERIFIER = "circular-test-code-verifier-with-enough-characters"
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).decode().rstrip("=")
ACCEPT = {"Accept": "application/json, text/event-stream"}


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


def approve(user, pending, workspace_id):
    response = user.post("/api/mcp/consent/decision", json={"requestId": pending, "workspaceId": workspace_id})
    assert response.status_code == 200, response.text
    parts = parse_qs(urlsplit(response.json()["redirectUrl"]).query)
    assert parts.pop("state") == ["test-state"]
    return parts


def exchange(client, client_id, code, **overrides):
    return client.post("/token", data={
        "grant_type": "authorization_code", "client_id": client_id, "code": code,
        "code_verifier": VERIFIER, "redirect_uri": CALLBACK, "resource": RESOURCE, **overrides,
    })


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
        "client": "Claude", "workspaces": [{"id": space["id"], "name": space["name"]}],
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
    assert set(names) == {"list_projects", "search_tickets", "get_ticket"}
    assert all(entry["annotations"]["readOnlyHint"] for entry in names.values())
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
    assert client.post("/token", data={"grant_type": "refresh_token", "client_id": client_id,
                                       "refresh_token": refreshed.json()["refresh_token"]}).status_code == 400


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
    refreshed = client.post("/token", data={"grant_type": "refresh_token", "client_id": client_id,
                                          "refresh_token": issued["refresh_token"]}).json()
    token = refreshed["access_token"]
    assert rpc(client, token, "tools/list").status_code == 200
    bob_id = bob.get("/api/auth/me").json()["user"]["id"]
    assert alice.delete(f'/api/workspaces/{workspace["id"]}/members/{bob_id}').status_code == 204
    assert rpc(client, token, "tools/list").status_code == 401
