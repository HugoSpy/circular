"""Real Docs authorization and collaboration on SQLite and PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from io import BytesIO
import re
from urllib.parse import unquote
from uuid import uuid4
from zipfile import ZipFile

from fastapi.testclient import TestClient

from tests.test_docs import created
from tests.test_postgres import postgres_url  # noqa: F401
from tests.test_workspaces import create_workspace, invite, workspace_people  # noqa: F401


def join(owner, member, space, email):
    invitation = invite(owner, space, email)
    assert member.post(f"/api/workspace-invitations/{invitation}/accept", json={}).status_code == 200
    return member.get("/api/auth/me").json()["user"]["id"]


def test_docs_reader_scope_and_revocation(workspace_people, tmp_path):
    app, (owner, reader, guest), _ = workspace_people
    space, project = create_workspace(owner, "collaboration")
    space_url = f"/api/workspaces/{space['id']}"
    base = space_url + "/docs"
    reader_id = join(owner, reader, space, "bob@epita.fr")
    assert reader.get(base).json()["access"] == "editor"
    grant = created(owner.post(f"/api/projects/{project['id']}/invitations", json={"email": "charlie@epita.fr"}))
    assert guest.post(f"/api/invitations/{grant['id']}/accept", json={}).status_code == 204
    guest_id = guest.get("/api/auth/me").json()["user"]["id"]
    assert owner.patch(base + f"/access/{guest_id}", json={"role": "reader"}).status_code == 404
    assert reader.patch(base + f"/access/{reader_id}", json={"role": "reader"}).status_code == 403
    assert owner.patch(base + f"/access/{reader_id}", json={"role": "reader"}).status_code == 204
    assert reader.get(base).json()["access"] == "reader"

    guide = created(owner.post(base + "/pages", json={"title": "Guide"}))
    source = created(owner.post(base + "/pages", json={"title": "Préparation", "parentId": guide["id"]}))
    source_url = base + f"/pages/{source['id']}"
    guide_url = base + f"/pages/{guide['id']}"
    image = bytes.fromhex("89504e470d0a1a0a") + b"circular-test"
    asset_id = str(uuid4())
    uploaded = owner.post(source_url + "/attachments", params={"assetId": asset_id, "name": "Plan.png", "image": "true"},
                          content=image, headers={"Content-Type": "application/octet-stream"})
    assert uploaded.status_code == 201, uploaded.text
    payload = {"markdown": f"Trace documentaire unique. [](/pages/{guide['id']}) ![Plan](/attachments/{asset_id})", "revision": 1}
    assert owner.patch(source_url + "/body", json=payload).status_code == 200

    assert reader.get(guide_url).json()["backlinks"] == [source["id"]]
    assert reader.get(base + "/search?q=Trace").json() == [{"id": source["id"], "title": "Préparation"}]
    for suffix in ("/trash", "/templates", "/access"):
        assert reader.get(base + suffix).status_code == 403
    for suffix in ("/revisions", "/revisions/1"):
        assert reader.get(source_url + suffix).status_code == 403
    assert reader.patch(source_url + "/body", json={"markdown": "Écriture interdite", "revision": 2}).status_code == 403
    assert reader.post(base + "/pages", json={"title": "Interdite"}).status_code == 403
    publish = source_url + f"/comments/{uuid4()}"
    assert reader.put(publish, json={"body": "Interdit"}).status_code == 403
    assert guest.get(source_url).json() == guest.get(base + f"/pages/{uuid4()}").json()
    with TestClient(app, base_url="http://127.0.0.1:4310") as anonymous:
        assert anonymous.get(source_url).status_code == 401

    asset = base + f"/attachments/{asset_id}?preview=true"
    preview = reader.get(asset)
    assert preview.status_code == 200 and "no-store" in preview.headers["cache-control"]
    assert sha256(preview.content).digest() == sha256(image).digest()
    response = reader.get(base + "/export")
    assert response.status_code == 200
    with ZipFile(BytesIO(response.content)) as archive:
        archive.extractall(tmp_path / "zip-lecteur")
    files = list((tmp_path / "zip-lecteur").rglob("*.md"))
    document = next(file for file in files if source["id"][:8] in file.name)
    content = document.read_text()
    link = re.search(r"\[Guide\]\(([^)]+)\)", content)
    picture = re.search(r"!\[Plan\]\(([^)]+)\)", content)
    assert link and (document.parent / unquote(link[1])).resolve(strict=True) == next(
        file.resolve(strict=True) for file in files if guide["id"][:8] in file.name
    )
    assert picture and sha256((document.parent / unquote(picture[1])).read_bytes()).digest() == sha256(image).digest()

    secondary, _ = create_workspace(owner, "autre-collaboration")
    foreign_page = created(owner.post(f"/api/workspaces/{secondary['id']}/docs/pages", json={"title": "Repère hors espace"}))
    assert reader.get(base + f"/pages/{foreign_page['id']}").status_code == 404
    assert all("Repère hors espace" not in file.read_text() for file in files)
    assert owner.delete(space_url + f"/members/{reader_id}").status_code == 204
    for url in (base, guide_url, source_url, source_url + "/comments", asset, base + "/search?q=Trace",
                base + "/export", base + "/notifications"):
        denied = reader.get(url)
        assert denied.status_code == 404 and denied.json() == {"error": "Espace introuvable."}
    assert owner.get(asset).content == image


def test_docs_mentions_are_transactional_and_follow_access(workspace_people):
    _, (owner, member, outsider), _ = workspace_people
    space, _ = create_workspace(owner, "mentions")
    space_url = f"/api/workspaces/{space['id']}"
    base = space_url + "/docs"
    member_id = join(owner, member, space, "bob@epita.fr")
    outsider_id = outsider.get("/api/auth/me").json()["user"]["id"]
    page = created(owner.post(base + "/pages", json={"title": "Nouvelle page"}))
    page_url = base + f"/pages/{page['id']}"
    comments = page_url + "/comments"
    comment_id = str(uuid4())
    comment = comments + "/" + comment_id
    assert owner.get(comments).json()["items"] == []
    assert owner.put(comment, json={"body": " "}).status_code == 422
    assert owner.put(comment, json={"body": "Autre compte", "mentionId": outsider_id}).status_code == 404
    assert owner.get(comments).json()["items"] == []
    payload = {"body": "Peux-tu relire ? @Charlie", "mentionId": member_id}
    first = created(owner.put(comment, json=payload))
    assert created(owner.put(comment, json=payload)) == first
    assert owner.put(comment, json={"body": "Autre publication"}).status_code == 409
    assert len(owner.get(comments).json()["items"]) == 1
    assert owner.get(base + "/notifications").json() == []
    assert outsider.get(base + "/notifications").status_code == 404
    event, = member.get(base + "/notifications").json()
    assert event["commentId"] == comment_id and event["title"] == "Nouvelle page" and event["readAt"] is None
    assert owner.patch(base + f"/access/{member_id}", json={"role": "reader"}).status_code == 204
    assert member.get(comments).json()["people"] == []
    assert member.get(comments).json()["items"][0]["body"] == payload["body"]
    read = base + f"/notifications/{comment_id}/read"
    assert owner.patch(read, json={}).status_code == 404
    assert member.patch(read, json={}).status_code == 204
    saved = owner.patch(comment, json={**payload, "body": "Peux-tu relire demain ?", "revision": 1})
    assert saved.status_code == 200 and saved.json()["revision"] == 2
    read_at = member.get(base + "/notifications").json()[0]["readAt"]
    assert read_at is not None
    assert member.patch(read, json={}).status_code == 204
    assert member.get(base + "/notifications").json()[0]["readAt"] == read_at
    assert owner.patch(comment, json={**payload, "revision": 1}).status_code == 409

    def publish_edit(body):
        return owner.patch(comment, json={**payload, "revision": 2, "body": body}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(publish_edit, ("Première version", "Deuxième version"))) == [200, 409]
    assert member.get(base + "/notifications").json()[0]["readAt"] == read_at
    assert owner.patch(base + f"/access/{member_id}", json={"role": "editor"}).status_code == 204
    assert member.delete(comment).status_code == 403
    assert member.patch(comment, json={**payload, "revision": 3}).status_code == 403
    other_comment = comments + f"/{uuid4()}"
    assert member.put(other_comment, json={"body": "Modération"}).status_code == 201
    assert owner.delete(other_comment).status_code == 204

    duplicate = created(owner.post(page_url + "/duplicate", json={}))
    assert owner.get(base + f"/pages/{duplicate['id']}/comments").json()["items"] == []
    operation = created(owner.post(page_url + "/trash", json={"revision": 1}))
    assert member.get(base + "/notifications").json() == []
    assert member.get(comments).status_code == 404
    assert member.patch(read, json={}).status_code == 404
    assert owner.post(base + f"/trash/{operation['id']}/restore", json={}).status_code == 200
    assert member.get(base + "/notifications").json()[0]["readAt"] == read_at
    assert owner.patch(comment, json={"body": "Sans mention", "revision": 3}).status_code == 200
    assert member.get(base + "/notifications").json() == []
    assert owner.patch(comment, json={**payload, "revision": 4}).status_code == 200
    assert member.get(base + "/notifications").json()[0]["readAt"] is None

    racing_comment = comments + f"/{uuid4()}"
    with ThreadPoolExecutor(max_workers=2) as pool:
        written = pool.submit(member.put, racing_comment, json={"body": "Publication concurrente"})
        downgraded = pool.submit(owner.patch, base + f"/access/{member_id}", json={"role": "reader"})
        assert downgraded.result().status_code == 204
        assert written.result().status_code in {201, 403}
    assert member.put(comments + f"/{uuid4()}", json={"body": "Trop tard"}).status_code == 403
    if written.result().status_code == 201:
        assert owner.delete(racing_comment).status_code == 204

    with ThreadPoolExecutor(max_workers=2) as pool:
        changed = pool.submit(owner.patch, comment, json={**payload, "revision": 5})
        removed = pool.submit(owner.delete, space_url + f"/members/{member_id}")
        assert removed.result().status_code == 204
        assert changed.result().status_code in {200, 404}
    assert member.get(base + "/notifications").status_code == 404
    join(owner, member, space, "bob@epita.fr")
    assert member.get(base + "/notifications").json() == []
    assert owner.delete(comment).status_code == 204
    assert owner.get(comments).json()["items"] == []
