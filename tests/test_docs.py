"""Circular Docs through real sessions and both supported databases."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from json import loads
import re
from urllib.parse import unquote
from uuid import uuid4
from zipfile import ZipFile

from tests.test_workspaces import create_workspace, invite, workspace_people  # noqa: F401
from tests.test_postgres import postgres_url  # noqa: F401


def created(response):
    assert response.status_code == 201, response.text
    return response.json()


def test_workspace_docs_links_export_and_revocation(workspace_people, tmp_path):
    _, (owner, editor, outsider), _ = workspace_people
    space, project = create_workspace(owner, "studio-docs")
    base = f"/api/workspaces/{space['id']}/docs"
    parent = created(owner.post(base + "/pages", json={"title": "Équipe"}))
    source = created(owner.post(base + "/pages", json={"title": "Guide", "parentId": parent["id"]}))
    target = created(owner.post(base + "/pages", json={"title": "Guide"}))
    assert outsider.get(base + "/pages/" + target["id"]).status_code == 404
    guest = created(owner.post(
        f"/api/projects/{project['id']}/invitations", json={"email": "charlie@epita.fr"},
    ))
    assert outsider.post(f"/api/invitations/{guest['id']}/accept", json={}).status_code == 204
    assert outsider.get("/api/workspaces").json()[0]["role"] == "guest"
    assert outsider.get(base + "/export").status_code == 404
    invitation = invite(owner, space, "bob@epita.fr")
    assert editor.post(f"/api/workspace-invitations/{invitation}/accept", json={}).status_code == 200
    cycle = owner.patch(base + f"/pages/{parent['id']}/placement", json={"title": "Équipe", "parentId": source["id"]})
    assert cycle.status_code == 409
    assert owner.get(base + "/pages/" + parent["id"]).json()["parentId"] is None

    source_body = f"## À retrouver\n\n[](/pages/{target['id']}) et [Guide](/pages/{target['id']}).\n\n[Ticket](/?issue=18)"
    path = base + f"/pages/{source['id']}/body"
    payload = {"markdown": source_body, "revision": 1}
    saved = editor.patch(path, json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["revision"] == 2
    assert editor.patch(path, json=payload).json()["revision"] == 2
    assert owner.patch(path, json={"markdown": "Brouillon concurrent", "revision": 1}).status_code == 409
    assert owner.patch(base + f"/pages/{target['id']}/placement", json={"title": "Guide déplacé", "parentId": parent["id"]}).status_code == 200
    target_page = owner.get(base + f"/pages/{target['id']}").json()
    assert target_page["id"] == target["id"]
    assert target_page["backlinks"] == [source["id"]]
    assert editor.get(base + "/search", params={"q": "À RETROUVER"}).json() == [{"id": source["id"], "title": "Guide"}]

    another_space, _ = create_workspace(owner, "autre-espace")
    another_base = f"/api/workspaces/{another_space['id']}/docs"
    foreign = created(owner.post(another_base + "/pages", json={"title": "Autre espace"}))
    assert owner.get(another_base + f"/pages/{target['id']}").status_code == 404
    assert owner.patch(path, json={"markdown": f"[](/pages/{foreign['id']})", "revision": 2}).status_code == 404
    assert editor.get(base + f"/pages/{source['id']}").json()["markdown"] == source_body

    download = editor.get(base + "/export")
    assert download.status_code == 200 and download.headers["content-type"] == "application/zip"
    with ZipFile(BytesIO(download.content)) as archive:
        archive.extractall(tmp_path / "extrait")
    files = list((tmp_path / "extrait").rglob("*.md"))
    assert len(files) == 3
    source_file = next(file for file in files if source["id"][:8] in file.name)
    target_file = next(file for file in files if target["id"][:8] in file.name)
    exported = source_file.read_text(encoding="utf-8")
    link = re.search(r"\[Guide déplacé\]\(([^)]+)\)", exported)
    assert link
    assert (source_file.parent / unquote(link[1])).resolve(strict=True) == target_file.resolve(strict=True)
    assert "[Ticket](/?issue=18)" in exported

    editor_id = editor.get("/api/auth/me").json()["user"]["id"]
    assert owner.delete(f"/api/workspaces/{space['id']}/members/{editor_id}").status_code == 204
    for suffix in ("", "/search?q=Guide", "/export", f"/pages/{source['id']}"):
        assert editor.get(base + suffix).status_code == 404


def test_collection_values_and_views_are_independent(workspace_people):
    _, (owner, _, outsider), _ = workspace_people
    space, _ = create_workspace(owner, "collections-docs")
    base = f"/api/workspaces/{space['id']}/docs"
    collection = created(owner.post(base + "/collections", json={"title": "Ressources"}))
    path = base + f"/collections/{collection['id']}"
    assert outsider.get(path).status_code == 404
    fields = {}
    for name, kind, options in (
        ("État", "select", ["Prêt", "Idée"]), ("Date", "date", []), ("Score", "number", []),
        ("Résumé", "text", []), ("Vérifié", "checkbox", []),
    ):
        fields[kind] = created(owner.post(path + "/fields", json={"name": name, "kind": kind, "options": options}))["id"]
    page = created(owner.post(base + "/pages", json={"title": "Ma ressource"}))
    assert owner.patch(base + f"/pages/{page['id']}/placement", json={
        "title": page["title"], "collectionId": collection["id"],
    }).status_code == 200
    for kind, value in (("select", "Prêt"), ("date", "2026-11-22"), ("number", 2.5), ("checkbox", False), ("text", "Résumé")):
        response = owner.patch(base + f"/pages/{page['id']}/properties/{fields[kind]}", json={"value": value})
        assert response.status_code == 200, response.text
        assert response.json()["properties"][fields[kind]] == value
    assert owner.patch(base + f"/pages/{page['id']}/properties/{fields['date']}", json={"value": "2026-02-30"}).status_code == 422
    assert owner.patch(base + f"/pages/{page['id']}/properties/{fields['number']}", json={"value": False}).status_code == 422

    configuration = {"name": "Prêtes", "sortBy": fields["number"], "direction": "desc", "hidden": [fields["date"]],
                     "filters": [{"fieldId": fields["select"], "value": "Prêt"}, {"fieldId": fields["checkbox"], "value": False}]}
    view = created(owner.post(path + "/views", json=configuration))
    assert view == {"id": view["id"], **configuration}
    assert owner.post(path + "/views", json={**configuration, "sortBy": str(uuid4())}).status_code == 422
    assert owner.delete(path + "/views/" + view["id"]).status_code == 204
    assert owner.get(path).json()["views"] == collection["views"]
    assert owner.delete(path + "/views/" + collection["views"][0]["id"]).status_code == 409
    assert owner.get(base + f"/pages/{page['id']}").json()["properties"][fields["select"]] == "Prêt"
    with ZipFile(BytesIO(owner.get(base + "/export").content)) as archive:
        metadata = loads(archive.read("collections.json"))
        assert metadata["collections"][0]["id"] == collection["id"]
        exported = next(iter(metadata["pages"].values()))
        assert exported == {"collectionId": collection["id"], "values": owner.get(base + f"/pages/{page['id']}").json()["properties"]}


def test_concurrent_doc_moves_cannot_create_a_cycle(workspace_people):
    _, (owner, other, _), _ = workspace_people
    space, _ = create_workspace(owner, "concurrence-docs")
    base = f"/api/workspaces/{space['id']}/docs"
    invitation = invite(owner, space, "bob@epita.fr")
    assert other.post(f"/api/workspace-invitations/{invitation}/accept", json={}).status_code == 200
    first, second = [created(owner.post(base + "/pages", json={"title": name})) for name in ("Premier", "Second")]

    def move(client, page, target):
        return client.patch(base + f"/pages/{page['id']}/placement", json={
            "title": page["title"], "parentId": target["id"],
        }).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        left = pool.submit(move, owner, first, second)
        right = pool.submit(move, other, second, first)
        assert sorted((left.result(), right.result())) == [200, 409]
    assert sum(page["parentId"] is not None for page in owner.get(base).json()["pages"]) == 1
