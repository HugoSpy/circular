"""Model snapshots and private binary data through the authenticated Docs API."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re
from urllib.parse import unquote
from uuid import uuid4
from zipfile import ZipFile

from tests.test_docs import created
from tests.test_postgres import postgres_url  # noqa: F401
from tests.test_workspaces import create_workspace, invite, workspace_people  # noqa: F401


def test_template_is_an_independent_collection_snapshot(workspace_people):
    _, (owner, _, outsider), _ = workspace_people
    space, _ = create_workspace(owner, "atelier-modeles")
    base = f"/api/workspaces/{space['id']}/docs"
    collection = created(owner.post(base + "/collections", json={"title": "Ateliers"}))
    scope = {"collectionId": collection["id"]}
    field = created(owner.post(base + f"/collections/{collection['id']}/fields",
                              json={"name": "État", "kind": "select", "options": ["À préparer", "Prêt"]}))
    target = created(owner.post(base + "/pages", json={"title": "Ressources"}))
    page = created(owner.post(base + "/pages", json={"title": "Original", **scope}))
    path = base + f"/pages/{page['id']}"
    markdown = f"## Objectif\n\n[Ressources](/pages/{target['id']})."
    assert owner.patch(path + "/body", json={"markdown": markdown, "revision": 1}).status_code == 200
    assert owner.patch(path + f"/properties/{field['id']}", json={"value": "À préparer"}).status_code == 200
    assert owner.post(path + "/templates", json={"name": "Brouillon", "revision": 1}).status_code == 409
    model = created(owner.post(path + "/templates", json={"name": "Fiche", "revision": 2}))
    assert owner.patch(path + "/body", json={"markdown": "Contenu remplacé", "revision": 2}).status_code == 200
    assert owner.post(base + "/pages", json={"title": "Hors collection", "templateId": model["id"]}).status_code == 404
    assert outsider.get(base + "/templates").status_code == 404
    another, _ = create_workspace(owner, "autres-modeles")
    foreign = f"/api/workspaces/{another['id']}/docs"
    assert owner.post(foreign + "/pages", json={"title": "Autre", "templateId": model["id"]}).status_code == 404

    payload = {"title": "Atelier du mardi", "templateId": model["id"], **scope}
    copied = created(owner.post(base + "/pages", json=payload))
    assert copied["markdown"] == markdown
    assert copied["properties"] == {field["id"]: "À préparer"}
    assert copied["revision"] == 1
    assert owner.get(base + f"/pages/{target['id']}").json()["backlinks"] == [copied["id"]]
    rename = owner.patch(base + f"/templates/{model['id']}", json={"name": "Fiche réutilisable"})
    assert rename.json()["name"] == "Fiche réutilisable"
    options = ["À planifier", "Prêt"]
    field_path = base + f"/collections/{collection['id']}/fields/{field['id']}"
    assert owner.patch(field_path, json={"name": "État", "options": options, "previousOptions": field["options"]}).status_code == 200
    refreshed = created(owner.post(base + "/pages", json=payload))
    assert refreshed["properties"] == {}
    assert refreshed["skippedTemplateProperties"] == 1
    assert owner.delete(base + f"/templates/{model['id']}").status_code == 204
    assert owner.get(base + "/templates").json() == []
    assert owner.post(base + "/pages", json=payload).status_code == 404
    assert owner.get(base + f"/pages/{copied['id']}").json()["markdown"] == markdown


def test_attachments_are_private_and_portable(workspace_people, tmp_path):
    _, (owner, editor, outsider), _ = workspace_people
    space, project = create_workspace(owner, "atelier-prive")
    base = f"/api/workspaces/{space['id']}/docs"
    parent = created(owner.post(base + "/pages", json={"title": "Atelier"}))
    page = created(owner.post(base + "/pages", json={"title": "Supports", "parentId": parent["id"]}))
    path = base + f"/pages/{page['id']}"
    pdf = (Path(__file__).resolve().parents[1] / "docs/circular-docs/mockups/support-atelier.pdf").read_bytes()
    asset_id = str(uuid4())
    params = {"name": "Éléments (v1).pdf", "assetId": asset_id}
    headers = {"Content-Type": "application/octet-stream"}
    assert owner.post(path + "/attachments", params=params, headers=headers, content=b"<html>").status_code == 415
    assert owner.post(path + "/attachments", params=params, headers=headers, content=b"x" * (10 * 1024 * 1024 + 1)).status_code == 413
    asset = created(owner.post(path + "/attachments", params=params, headers=headers, content=pdf))
    assert created(owner.post(path + "/attachments", params=params, headers=headers, content=pdf)) == asset
    href = base + f"/attachments/{asset_id}"
    assert owner.get(href + "?preview=true").headers["content-disposition"].startswith("attachment;")
    assert owner.get(href).content == pdf
    assert outsider.get(href).status_code == 404
    guest = created(owner.post(f"/api/projects/{project['id']}/invitations", json={"email": "charlie@epita.fr"}))
    assert outsider.post(f"/api/invitations/{guest['id']}/accept", json={}).status_code == 204
    assert outsider.get(href).status_code == 404
    invitation = invite(owner, space, "bob@epita.fr")
    assert editor.post(f"/api/workspace-invitations/{invitation}/accept", json={}).status_code == 200
    assert editor.get(href).content == pdf

    png = bytes.fromhex("89504e470d0a1a0a") + b"fixture"
    image_id = str(uuid4())
    created(owner.post(path + "/attachments", params={"name": "Plan.png", "assetId": image_id, "image": "true"},
                       headers=headers, content=png))
    assert owner.get(base + f"/attachments/{image_id}?preview=true").headers["content-disposition"].startswith("inline;")
    markdown = f"> [!NOTE]- Ressources\n> [Fiche](/attachments/{asset_id})\n\n![Plan](/attachments/{image_id})"
    assert owner.patch(path + "/body", json={"markdown": markdown, "revision": 1}).status_code == 200
    model = created(owner.post(path + "/templates", json={"name": "Supports utiles", "revision": 2}))
    trash_id = created(owner.post(path + "/trash", json={"revision": 2}))["id"]
    assert editor.get(href).status_code == 404
    copy = created(owner.post(base + "/pages", json={"title": "Autres supports", "templateId": model["id"]}))
    assert copy["markdown"] == markdown
    assert editor.get(href).content == pdf
    assert owner.post(base + f"/trash/{trash_id}/restore", json={}).status_code == 200

    archive_response = editor.get(base + "/export")
    assert archive_response.status_code == 200
    extracted = tmp_path / "assets-export"
    with ZipFile(BytesIO(archive_response.content)) as archive:
        assert sum(name.startswith("assets/") for name in archive.namelist()) == 2
        archive.extractall(extracted)
    source = next(file for file in extracted.rglob("*.md") if page["id"][:8] in file.name)
    exported = source.read_text()
    assert "> [!NOTE]- Ressources" in exported
    expected = [("[Fiche]", pdf), ("![Plan]", png)]
    for label, content in expected:
        match = re.search(re.escape(label) + r"\(([^)]+)\)", exported)
        assert match
        linked = (source.parent / unquote(match[1])).resolve(strict=True)
        stored = next((extracted / "assets").glob(f"*{linked.suffix}")).resolve(strict=True)
        assert linked == stored
        assert sha256(linked.read_bytes()).digest() == sha256(content).digest()

    editor_id = editor.get("/api/auth/me").json()["user"]["id"]
    assert owner.delete(f"/api/workspaces/{space['id']}/members/{editor_id}").status_code == 204
    assert editor.get(href).status_code == 404
    assert owner.get(href).content == pdf
    other, _ = create_workspace(owner, "atelier-exterieur")
    assert owner.get(f"/api/workspaces/{other['id']}/docs/attachments/{asset_id}").status_code == 404
