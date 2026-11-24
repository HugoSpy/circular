"""Family grants and V3 workflows against the actual OAuth, MCP and HTTP routes."""
from base64 import b64encode
from urllib.parse import parse_qs, urlsplit

from tests.test_mcp import approve, authorize, exchange, mcp_app, refresh, register, request_id, rpc, tool  # noqa: F401
from tests.test_postgres import postgres_url  # noqa: F401
from tests.test_workspaces import account, create_workspace, issue

BASE = "circular:read"
TICKET_READ = "circular:tickets:read"
TICKET_WRITE = "circular:tickets:write"


def request_grant(client, owner, workspace_id, requested, granted):
    client_id = register(client).json()["client_id"]
    scope = " ".join(sorted({BASE, *requested}))
    pending = request_id(authorize(client, client_id, scope=scope))
    decision = owner.post("/api/mcp/consent/decision", json={"requestId": pending, "workspaceId": workspace_id, "scopes": granted})
    assert decision.status_code == 200, decision.text
    code = parse_qs(urlsplit(decision.json()["redirectUrl"]).query)["code"][0]
    response = exchange(client, client_id, code)
    assert response.status_code == 200, response.text
    return client_id, response.json()


def test_mcp_v3_partial_consent_cannot_widen_at_refresh(mcp_app):
    app, client = mcp_app
    owner = account(app, "alice")
    space, project = create_workspace(owner)
    ticket = issue(owner, project["id"])
    client_id, grant = request_grant(client, owner, space["id"], [TICKET_READ, TICKET_WRITE], [TICKET_READ])
    token = grant["access_token"]
    detail = tool(client, token, "get_ticket_context", reference=ticket["identifier"])["structuredContent"]
    assert detail["ticket"]["id"] == ticket["id"]
    denied = rpc(client, token, "tools/call", {"name": "update_ticket", "arguments": {}})
    assert denied.status_code == 403 and TICKET_WRITE in denied.headers["www-authenticate"]
    assert refresh(client, client_id, grant["refresh_token"], scope=f"{BASE} {TICKET_READ} {TICKET_WRITE}").json()["error"] == "invalid_scope"
    renewed = refresh(client, client_id, grant["refresh_token"]).json()
    assert set(renewed["scope"].split()) == {BASE, TICKET_READ}
    listed = owner.get("/api/mcp/connections").json()["connections"][0]
    assert listed["write"] is False and listed["families"][0]["write"] is None

    pending = request_id(authorize(client, client_id, scope=f"{BASE} {TICKET_READ} {TICKET_WRITE}"))
    payload = {"requestId": pending, "workspaceId": space["id"], "scopes": ["circular:docs:read"]}
    assert owner.post("/api/mcp/consent/decision", json=payload).status_code == 422
    assert approve(owner, pending, None) == {"error": ["access_denied"]}


def test_mcp_v3_updates_ticket_once_and_detects_conflict(mcp_app):
    app, client = mcp_app
    owner = account(app, "alice")
    space, project = create_workspace(owner)
    ticket = issue(owner, project["id"])
    _, grant = request_grant(client, owner, space["id"], [TICKET_READ, TICKET_WRITE], [TICKET_READ, TICKET_WRITE])
    token = grant["access_token"]
    changes = {"ticket_id": ticket["id"], "expected_updated_at": ticket["updatedAt"], "changes": {"status": "in_progress"}}
    first = tool(client, token, "update_ticket", **changes, request_key="v3-update-ticket-01")
    assert first["structuredContent"]["ticket"]["status"] == "in_progress"
    assert tool(client, token, "update_ticket", **changes, request_key="v3-update-ticket-01")["structuredContent"] == first["structuredContent"]
    stale = tool(client, token, "update_ticket", **{**changes, "changes": {"status": "done"}}, request_key="v3-update-ticket-02")
    assert stale["isError"] and "a changé" in stale["content"][0]["text"]
    events = owner.get(f'/api/issues/{ticket["id"]}/activity').json()
    assert [entry["kind"] for entry in events] == ["created", "updated"]
    assert owner.get(f'/api/issues/{ticket["id"]}').json()["status"] == "in_progress"
    latest = first["structuredContent"]["ticket"]
    identity = owner.get("/api/auth/me").json()["user"]["id"]
    planned = tool(client, token, "update_ticket", ticket_id=ticket["id"], expected_updated_at=latest["updatedAt"],
                   changes={"assigneeId": identity, "estimate": 3}, request_key="v3-update-ticket-03")["structuredContent"]
    assert planned["ticket"]["id"] == ticket["id"]
    detail = tool(client, token, "get_ticket_context", reference=ticket["identifier"])["structuredContent"]
    assert (detail["planning"]["assigneeId"], detail["planning"]["estimate"]) == (identity, 3)
    assert tool(client, token, "filter_tickets", assignee_id=identity)["structuredContent"]["items"][0]["id"] == ticket["id"]


def test_mcp_v3_workspace_records_use_same_data_as_rest(mcp_app):
    app, client = mcp_app
    owner = account(app, "alice")
    space, project = create_workspace(owner)
    scope = [f"circular:{family}:{mode}" for family in ("projects", "customers", "releases", "agents") for mode in ("read", "write")]
    _, grant = request_grant(client, owner, space["id"], scope, scope)
    token = grant["access_token"]
    api = f'/api/workspaces/{space["id"]}/records'
    flows = [
        ("save_planning", "list_planning", "initiative", {"title": "Fiabilisation", "projectId": project["id"]}),
        ("save_customer_record", "list_customer_records", "customer", {"title": "Atelier Horizon"}),
        ("save_release_record", "list_release_records", "pipeline", {"title": "Application mobile"}),
        ("save_assistant_context", "list_assistant_context", "learning", {"title": "Recette vérifiée", "body": "Recette locale"}),
    ]
    for write, read, kind, record in flows:
        key = f"v3-create-{kind}-0001"
        arguments = {"kind": kind, "change": {"record": record}, "request_key": key}
        result = tool(client, token, write, **arguments)
        saved = result["structuredContent"]
        assert tool(client, token, write, **arguments)["structuredContent"] == saved
        assert owner.get(f'{api}/{kind}/{saved["id"]}').json() == saved
        listed = tool(client, token, read, kind=kind, query=record["title"])["structuredContent"]
        assert listed["items"] == [saved]
        edit = {"id": saved["id"], "revision": saved["revision"], "record": {**record, "title": record["title"] + " (précisé)"}}
        updated = owner.post(f"{api}/{kind}", json=edit)
        assert updated.status_code == 200, updated.text
        assert updated.json()["revision"] == 2
        assert owner.post(f"{api}/{kind}", json=edit).status_code == 409

    _, second = create_workspace(owner, "autre-espace")
    denied = tool(client, token, "save_planning", kind="milestone",
                  change={"record": {"title": "Jalon inaccessible", "projectId": second["id"]}}, request_key="v3-hidden-project-001")
    assert denied["isError"] and "Projet introuvable" in denied["content"][0]["text"]


def test_mcp_v3_document_writes_use_real_revisions(mcp_app):
    app, client = mcp_app
    owner = account(app, "alice")
    space, _project = create_workspace(owner)
    scope = ["circular:docs:read", "circular:docs:write"]
    _, grant = request_grant(client, owner, space["id"], scope, scope)
    token = grant["access_token"]
    created = tool(client, token, "create_document", page={"title": "Recette MCP"}, request_key="v3-create-doc-0001")["structuredContent"]
    change = {"page_id": created["id"], "change": {"revision": created["revision"], "markdown": "Le guide de la recette."}}
    saved = tool(client, token, "update_document", **change, request_key="v3-update-doc-0001")["structuredContent"]
    assert saved["revision"] > created["revision"]
    verified = owner.get(f'/api/workspaces/{space["id"]}/docs/pages/{created["id"]}').json()
    assert verified["markdown"] == "Le guide de la recette."
    assert tool(client, token, "update_document", **change, request_key="v3-update-doc-0001")["structuredContent"] == saved
    denied = tool(client, token, "update_document", **{**change, "change": {**change["change"], "markdown": "Autre texte"}}, request_key="v3-update-doc-0002")
    assert denied["isError"] and "a été modifiée" in denied["content"][0]["text"]
    assert tool(client, token, "search_documents", query="recette")["structuredContent"]["items"][0]["id"] == created["id"]
    replacement = tool(client, token, "patch_document", page_id=created["id"],
                       change={"revision": saved["revision"], "oldText": "guide", "newText": "manuel"}, request_key="v3-doc-patch-0001")["structuredContent"]
    content = b64encode(b"%PDF-1.4\nRecette V3\n").decode("ascii")
    attached = tool(client, token, "attach_document_file", page_id=created["id"], file={
        "revision": replacement["revision"], "name": "recette.pdf", "contentBase64": content,
    }, request_key="v3-doc-attach-0001")["structuredContent"]
    file = tool(client, token, "get_document_file", asset_id=attached["assetId"], include_content=True)["structuredContent"]
    assert file["contentBase64"] == content
    api = f'/api/workspaces/{space["id"]}/docs'
    assert owner.get(f'{api}/attachments/{attached["assetId"]}').content.startswith(b"%PDF-1.4")
    markdown = owner.get(f'{api}/pages/{created["id"]}').json()["markdown"]
    assert f'/attachments/{attached["assetId"]}' in markdown and "Le manuel de la recette." in markdown


def test_mcp_v3_relation_cycles_and_confirmed_archive(mcp_app):
    app, client = mcp_app
    owner, other = account(app, "alice"), account(app, "bob")
    space, project = create_workspace(owner)
    parent, child = (issue(owner, project["id"], title=name) for name in ("Parent", "Enfant"))
    _, grant = request_grant(client, owner, space["id"], [TICKET_READ, TICKET_WRITE], [TICKET_READ, TICKET_WRITE])
    token = grant["access_token"]
    linked = tool(client, token, "relate_tickets", ticket_id=child["id"], target_id=parent["id"], relation="parent",
                  request_key="v3-add-parent-0001")["structuredContent"]
    assert linked["planning"]["relations"][0]["ticketId"] == parent["id"]
    loop = tool(client, token, "relate_tickets", ticket_id=parent["id"], target_id=child["id"], relation="parent",
                request_key="v3-add-parent-0002")
    assert loop["isError"] and "boucle" in loop["content"][0]["text"]
    pending = tool(client, token, "prepare_ticket_archive", ticket_id=child["id"], expected_updated_at=child["updatedAt"],
                   request_key="v3-archive-ticket-0001")["structuredContent"]
    action = f'/api/mcp/actions/{pending["id"]}'
    assert other.get(action).status_code == 404
    assert other.post(action, json={"approved": True}).status_code == 404
    assert child["id"] in {item["id"] for item in owner.get("/api/issues").json()}
    prepared = owner.get(action).json()
    assert prepared["state"] == "pending" and child["identifier"] in prepared["target"]
    assert owner.post(action, json={"approved": True}).json()["state"] == "done"
    assert owner.post(action, json={"approved": True}).status_code == 409
    assert child["id"] not in {item["id"] for item in owner.get("/api/issues").json()}
    assert owner.get(f'/api/issues/{child["id"]}').status_code == 200
    assert tool(client, token, "get_ticket_action_status", action_id=pending["id"])["structuredContent"]["state"] == "done"


def test_mcp_v3_share_is_read_only_and_revocable(mcp_app):
    app, client = mcp_app
    owner, guest = account(app, "alice"), account(app, "bob")
    space, visible = create_workspace(owner)
    invitation = owner.post(f'/api/projects/{visible["id"]}/invitations', json={"email": "bob@epita.fr"}).json()
    assert guest.post(f'/api/invitations/{invitation["id"]}/accept', json={}).status_code == 204
    private = owner.post("/api/projects", json={"name": "MCP privé", "key": "PRIVE"}).json()
    with app.state.database.connect(write=True) as db:
        db.execute("UPDATE projects SET visibility = 'private' WHERE id = ?", (private["id"],))
    ticket = issue(owner, private["id"], title="Visible seulement après confirmation")
    recipient = guest.get("/api/auth/me").json()["user"]["id"]
    _, issued = request_grant(client, owner, space["id"], [TICKET_READ, TICKET_WRITE], [TICKET_READ, TICKET_WRITE])
    _, guest_grant = request_grant(client, guest, space["id"], [TICKET_READ, TICKET_WRITE], [TICKET_READ, TICKET_WRITE])
    assert guest.get(f'/api/issues/{ticket["id"]}').status_code == 404
    args = {"ticket_id": ticket["id"], "recipient_id": recipient, "expected_updated_at": ticket["updatedAt"]}
    path = f'/api/workspaces/{space["id"]}/ticket-shares'
    for remove in (False, True):
        action = tool(client, issued["access_token"], "prepare_ticket_share", **args, remove=remove,
                      request_key=f"share-recipient-{int(remove):04d}")["structuredContent"]
        assert owner.post(f'/api/mcp/actions/{action["id"]}', json={"approved": True}).status_code == 200
        shared = guest.get(f'{path}/{ticket["id"]}')
        assert shared.status_code == (404 if remove else 200)
        if not remove:
            assert shared.json()["ticket"]["id"] == ticket["id"]
            read = tool(client, guest_grant["access_token"], "get_ticket_context", reference=ticket["identifier"])
            assert read["structuredContent"]["ticket"]["id"] == ticket["id"]
            write = tool(client, guest_grant["access_token"], "update_ticket", ticket_id=ticket["id"], expected_updated_at=ticket["updatedAt"],
                         changes={"status": "done"}, request_key="guest-must-not-edit")
            assert write["isError"] and "Ticket introuvable" in write["content"][0]["text"]


def test_mcp_v3_github_requires_repository_configuration(mcp_app, monkeypatch):
    monkeypatch.delenv("CIRCULAR_GITHUB_CONNECTIONS_FILE", raising=False)
    app, client = mcp_app
    owner = account(app, "alice")
    space, _project = create_workspace(owner)
    scopes = ["circular:releases:read", "circular:releases:write"]
    _, grant = request_grant(client, owner, space["id"], scopes, scopes)
    token = grant["access_token"]
    denied = tool(client, token, "get_github_pull", repository="owner/test", number=42)
    assert denied["isError"] and "connexion GitHub n’est pas configurée" in denied["content"][0]["text"]
    review = {"repository": "owner/test", "number": 42, "sha": "a" * 40, "action": "merge"}
    denied = tool(client, token, "prepare_github_review", review=review, request_key="v3-no-github-token")
    assert denied["isError"] and "connexion GitHub n’est pas configurée" in denied["content"][0]["text"]
    with app.state.database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM mcp_confirmations").fetchone()[0] == 0


def test_mcp_v3_doc_sharing_and_notifications_apply_document_rights(mcp_app):
    app, client = mcp_app
    owner, guest, member = (account(app, name) for name in ("alice", "bob", "charlie"))
    space, project = create_workspace(owner)
    invitation = owner.post(f'/api/projects/{project["id"]}/invitations', json={"email": "bob@epita.fr"}).json()
    assert guest.post(f'/api/invitations/{invitation["id"]}/accept', json={}).status_code == 204
    invite = owner.post(f'/api/workspaces/{space["id"]}/invitations', json={"email": "charlie@epita.fr"}).json()
    assert member.post(f'/api/workspace-invitations/{invite["id"]}/accept', json={}).status_code == 200
    scopes = ["circular:docs:read", "circular:docs:write"]
    _, own = request_grant(client, owner, space["id"], scopes, scopes)
    _, visitor = request_grant(client, guest, space["id"], scopes, scopes)
    _, notified = request_grant(client, member, space["id"], scopes, scopes)
    author, reader = own["access_token"], visitor["access_token"]
    page = tool(client, author, "create_document", page={"title": "Document partagé V3"}, request_key="v3-shareable-doc-0001")["structuredContent"]
    page_id = page["id"]
    bob = guest.get("/api/auth/me").json()["user"]["id"]
    charlie = member.get("/api/auth/me").json()["user"]["id"]
    assert tool(client, reader, "get_document", page_id=page_id)["isError"]
    for remove in (False, True):
        action = tool(client, author, "prepare_document_share", page_id=page_id, recipient_id=bob, revision=page["revision"],
                      remove=remove, request_key=f"v3-share-document-{int(remove):02d}")["structuredContent"]
        assert owner.post(f'/api/mcp/actions/{action["id"]}', json={"approved": True}).status_code == 200
        path = f'/api/workspaces/{space["id"]}/document-shares/{page_id}'
        assert guest.get(path).status_code == (404 if remove else 200)
        if not remove:
            assert tool(client, reader, "get_document", page_id=page_id)["structuredContent"]["title"] == page["title"]
            blocked = tool(client, reader, "update_document", page_id=page_id,
                           change={"revision": page["revision"], "markdown": "Écriture refusée"}, request_key="v3-guest-edit-document")
            assert blocked["isError"]

    comment = tool(client, author, "comment_document", page_id=page_id, comment={"body": "À relire", "mentionId": charlie},
                   request_key="v3-notification-comment")["structuredContent"]
    token = notified["access_token"]
    assert tool(client, token, "list_document_notifications")["structuredContent"]["items"][0]["commentId"] == comment["id"]
    tool(client, token, "update_document_notification", comment_id=comment["id"], change={"action": "snooze", "hours": 1},
         request_key="v3-snooze-notification")
    assert tool(client, token, "list_document_notifications")["structuredContent"]["items"] == []
    tool(client, token, "update_document_notification", comment_id=comment["id"], change={"action": "read"},
         request_key="v3-read-notification")
    assert tool(client, token, "list_document_notifications")["structuredContent"]["items"][0]["readAt"]


def test_mcp_v3_github_review_is_bound_to_confirmation_and_sha(mcp_app, tmp_path, monkeypatch):
    import json

    import httpx

    app, client = mcp_app
    owner = account(app, "alice")
    space, _project = create_workspace(owner)
    identity = owner.get("/api/auth/me").json()["user"]["id"]
    repository = "recette/mobile"
    selection = tmp_path / "github.json"
    selection.write_text(json.dumps([{"workspaceId": space["id"], "userId": identity, "repository": repository, "token": "test_token"}]))
    monkeypatch.setenv("CIRCULAR_GITHUB_CONNECTIONS_FILE", str(selection))

    head = "a" * 40
    endpoint = "https://api.github.com/repos/recette/mobile/pulls/24"
    mutations = []

    def external_api(method, url, *, json, headers, **_options):
        assert headers["Authorization"] == "Bearer test_token"
        if method == "GET":
            assert url == endpoint
            return httpx.Response(200, json={"title": "Reprise de session", "body": "", "head": {"sha": head},
                                            "base": {"ref": "main"}, "state": "open", "merged": False})
        mutations.append((method, url, json))
        return httpx.Response(200, json={"merged": True})

    monkeypatch.setattr(httpx, "request", external_api)
    scopes = ["circular:releases:read", "circular:releases:write"]
    _, issued = request_grant(client, owner, space["id"], scopes, scopes)
    token = issued["access_token"]
    review = {"repository": repository, "number": 24, "sha": head, "action": "merge"}

    def pending(key):
        prepared = tool(client, token, "prepare_github_review", review=review, request_key=key)["structuredContent"]
        return '/api/mcp/actions/' + prepared["id"]

    old = pending("github-current-sha-01")
    assert owner.get(old).json()["target"] == "recette/mobile · PR #24"
    assert mutations == []
    head = "b" * 40
    assert owner.post(old, json={"approved": True}).json()["state"] == "failed"
    assert mutations == []

    review["sha"] = head
    change = pending("github-current-sha-02")
    assert owner.post(change, json={"approved": True}).json()["state"] == "done"
    assert mutations == [("PUT", endpoint + "/merge", {"sha": head})]
    assert owner.post(change, json={"approved": True}).status_code == 409
