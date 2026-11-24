"""Galerie previews are projected only for authorized, active collection pages."""
from io import BytesIO
from json import loads
from uuid import uuid4
from zipfile import ZipFile

from tests.test_docs import created
from tests.test_postgres import postgres_url  # noqa: F401
from tests.test_workspaces import create_workspace, invite, workspace_people  # noqa: F401


def test_gallery_previews_choose_first_private_image_and_respect_page_scope(workspace_people):
    _, (owner, editor, outsider), _ = workspace_people
    space, _ = create_workspace(owner, "galerie-docs")
    base = f"/api/workspaces/{space['id']}/docs"
    collection = created(owner.post(base + "/collections", json={"title": "Visuels"}))
    other_collection = created(owner.post(base + "/collections", json={"title": "Autres visuels"}))
    collection_path = base + f"/collections/{collection['id']}"
    first = created(owner.post(base + "/pages", json={"title": "Première", "collectionId": collection["id"]}))
    empty = created(owner.post(base + "/pages", json={"title": "Sans image", "collectionId": collection["id"]}))
    unavailable = created(owner.post(base + "/pages", json={"title": "Référence cassée", "collectionId": collection["id"]}))
    external = created(owner.post(base + "/pages", json={"title": "Externe seulement", "collectionId": collection["id"]}))
    trashed = created(owner.post(base + "/pages", json={"title": "Corbeille", "collectionId": collection["id"]}))
    foreign = created(owner.post(base + "/pages", json={"title": "Autre collection", "collectionId": other_collection["id"]}))
    png = bytes.fromhex("89504e470d0a1a0a") + b"private image bytes"
    image_ids = [str(uuid4()), str(uuid4())]
    for page, asset_id in zip((first, first), image_ids):
        created(owner.post(base + f"/pages/{page['id']}/attachments", params={
            "name": asset_id + ".png", "assetId": asset_id, "image": "true",
        }, headers={"Content-Type": "application/octet-stream"}, content=png))
    pdf_id = str(uuid4())
    created(owner.post(base + f"/pages/{unavailable['id']}/attachments", params={
        "name": "Source.pdf", "assetId": pdf_id,
    }, headers={"Content-Type": "application/octet-stream"}, content=b"%PDF-1.4 private fixture"))
    for page in (trashed, foreign):
        # Upload a page-local copy so page and collection scoping are exercised.
        local_id = str(uuid4())
        created(owner.post(base + f"/pages/{page['id']}/attachments", params={
            "name": "Local.png", "assetId": local_id, "image": "true",
        }, headers={"Content-Type": "application/octet-stream"}, content=png))
        assert owner.patch(base + f"/pages/{page['id']}/body", json={
            "markdown": f"![Local](/attachments/{local_id})", "revision": 1,
        }).status_code == 200
    markdown = ("![externe](https://example.invalid/remote.png)\n\n"
                "```md\n![code](/attachments/" + image_ids[1] + ")\n```\n\n"
                "[fichier](/attachments/" + image_ids[1] + ")\n\n"
                "![plan *accessible*](/attachments/" + image_ids[0] + ")\n\n"
                "![second](/attachments/" + image_ids[1] + ")")
    assert owner.patch(base + f"/pages/{first['id']}/body", json={"markdown": markdown, "revision": 1}).status_code == 200
    assert owner.patch(base + f"/pages/{unavailable['id']}/body", json={
        "markdown": "![perdue](/attachments/" + pdf_id + ")\n\n![valide](/attachments/" + image_ids[0] + ")",
        "revision": 1,
    }).status_code == 200
    assert owner.patch(base + f"/pages/{external['id']}/body", json={
        "markdown": "![web](https://example.invalid/x.png)\n\n[download](/attachments/" + image_ids[0] + ")",
        "revision": 1,
    }).status_code == 200
    current_trashed = owner.get(base + f"/pages/{trashed['id']}").json()
    trash = created(owner.post(base + f"/pages/{trashed['id']}/trash", json={"revision": current_trashed["revision"]}))

    assert "galleryPreviews" not in owner.get(collection_path).json()
    endpoint = collection_path + "/gallery-previews"
    response = owner.post(endpoint, json={"pageIds": [first["id"], empty["id"], unavailable["id"], external["id"], trashed["id"], foreign["id"]]})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result[first["id"]] == {"status": "available", "assetId": image_ids[0], "alt": "plan accessible"}
    assert result[unavailable["id"]] == {"status": "unavailable", "alt": "perdue"}
    assert empty["id"] not in result and external["id"] not in result
    assert trashed["id"] not in result and foreign["id"] not in result
    assert owner.post(endpoint, json={"pageIds": [first["id"], first["id"]]}).status_code == 422
    assert owner.post(endpoint, json={"pageIds": [str(uuid4()) for _ in range(101)]}).status_code == 422
    assert owner.post(endpoint, json={"pageIds": [str(uuid4())]}).json() == {}
    assert owner.get(base + f"/attachments/{image_ids[0]}?preview=true").headers["content-disposition"].startswith("inline;")
    assert outsider.post(endpoint, json={"pageIds": [first["id"]]}).status_code == 404

    view_config = {"name": "Ressources visuelles", "layout": "gallery", "groupBy": None, "dateFieldId": None,
        "filterTree": {"mode": "all", "conditions": []}, "sorts": [], "hidden": []}
    saved_view = created(owner.post(collection_path + "/views", json=view_config))
    assert {key: saved_view[key] for key in view_config} == view_config
    with ZipFile(BytesIO(owner.get(base + "/export").content)) as archive:
        exported = loads(archive.read("collections.json"))
    exported_collection = next(item for item in exported["collections"] if item["id"] == collection["id"])
    exported_view = next(view for view in exported_collection["views"] if view["id"] == saved_view["id"])
    assert exported_view == saved_view

    invitation = invite(owner, space, "bob@epita.fr")
    assert editor.post(f"/api/workspace-invitations/{invitation}/accept", json={}).status_code == 200
    assert editor.post(endpoint, json={"pageIds": [first["id"]]}).json()[first["id"]]["status"] == "available"
    editor_id = editor.get("/api/auth/me").json()["user"]["id"]
    assert owner.delete(f"/api/workspaces/{space['id']}/members/{editor_id}").status_code == 204
    assert editor.post(endpoint, json={"pageIds": [first["id"]]}).status_code == 404
    assert owner.post(base + f"/trash/{trash['id']}/restore", json={}).status_code == 200
