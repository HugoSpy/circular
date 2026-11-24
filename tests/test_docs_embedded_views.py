"""Markdown collection-view references through the API and exported ZIP."""
from io import BytesIO
from json import loads
import re
from urllib.parse import unquote
from uuid import uuid4
from zipfile import ZipFile

from tests.test_docs import created
from tests.test_docs_collaboration import join
from tests.test_docs_collections import condition, entry, field, make_collection, set_value
from tests.test_postgres import postgres_url  # noqa: F401
from tests.test_workspaces import create_workspace, workspace_people  # noqa: F401


def view_ref(collection, view, label="Ressources — À relire"):
    return f"[{label}](/collections/{collection['id']}/views/{view['id']})"


def test_embedded_view_markdown_respects_access_and_deleted_views(workspace_people, tmp_path):
    _, (owner, reader, outsider), _ = workspace_people
    space, base, collection, collection_url = make_collection(owner, "vues-integrees")
    status = field(owner, collection_url, "État", "select", ["À relire", "Prêt"])
    view = created(owner.post(collection_url + "/views", json={
        "name": "À relire", "layout": "table",
        "filterTree": {"mode": "all", "conditions": [condition(status, "eq", "À relire")]},
        "sorts": [{"fieldId": "title", "direction": "desc"}],
        "hidden": [status["id"]],
    }))
    target = entry(owner, base, collection, "Ressource autorisée")
    trashed = entry(owner, base, collection, "Titre à masquer")
    assert set_value(owner, base, target, status, "À relire").status_code == 200
    created(owner.post(base + f"/pages/{trashed['id']}/trash", json={"revision": 1}))
    parent = created(owner.post(base + "/pages", json={"title": "Atelier"}))
    host = created(owner.post(base + "/pages", json={"title": "Carnet", "parentId": parent["id"]}))
    url = base + f"/pages/{host['id']}"
    ref = view_ref(collection, view)
    body = "Les ressources liées.\n\n" + ref
    response = owner.patch(url + "/body", json={"markdown": body, "revision": 1})
    assert response.status_code == 200
    assert response.json()["markdown"] == body

    foreign_space, _ = create_workspace(outsider, "vues-confidentielles")
    foreign_base = f"/api/workspaces/{foreign_space['id']}/docs"
    foreign = created(outsider.post(foreign_base + "/collections", json={"title": "Autre espace"}))
    foreign_link = view_ref(foreign, foreign["views"][0], "Vue externe")
    wrong_view = view_ref(collection, {"id": str(uuid4())})
    wrong_collection = view_ref(collection, foreign["views"][0])
    for invalid in (foreign_link, wrong_view, wrong_collection):
        denied = owner.patch(url + "/body", json={"markdown": body + "\n\n" + invalid, "revision": 2})
        assert denied.status_code == 404 and denied.json() == {"error": "Vue introuvable."}
    assert owner.get(url).json()["markdown"] == body
    assert outsider.get(collection_url).status_code == 404
    reader_id = join(owner, reader, space, "bob@epita.fr")
    assert owner.patch(base + f"/access/{reader_id}", json={"role": "reader"}).status_code == 204
    assert reader.get(url).json()["markdown"] == body
    assert reader.get(collection_url).json()["views"][-1] == view
    assert reader.patch(url + "/body", json={"markdown": ref, "revision": 2}).status_code == 403

    code = "\n\n```md\n" + foreign_link + "\n```"
    assert owner.patch(url + "/body", json={"markdown": body + code, "revision": 2}).status_code == 200
    archive = reader.get(base + "/export")
    assert archive.status_code == 200
    folder = tmp_path / "archive"
    with ZipFile(BytesIO(archive.content)) as zip_:
        zip_.extractall(folder)
    index_file, = (folder / "collections").glob("*.md")
    host_file = next(path for path in folder.rglob("*.md") if host["id"][:8] in path.name)
    archived_content = host_file.read_text()
    match = re.search(r"\]\(([^)]+collections/[^)]+\.md)\)", archived_content)
    assert match and (host_file.parent / unquote(match[1])).resolve(strict=True) == index_file.resolve(strict=True)
    assert foreign_link in archived_content
    index_markdown = index_file.read_text()
    assert "Titre à masquer" not in index_markdown and trashed["id"] not in index_markdown
    row_link, = re.findall(r"^- \[.*\]\(([^)]+)\)$", index_markdown, re.M)
    target_file = next(path for path in folder.rglob("*.md") if target["id"][:8] in path.name)
    assert (index_file.parent / unquote(row_link)).resolve(strict=True) == target_file.resolve(strict=True)
    metadata = loads((folder / "collections.json").read_text())
    saved_collection = next(item for item in metadata["collections"] if item["id"] == collection["id"])
    assert saved_collection["views"][-1] == view

    assert owner.delete(collection_url + f"/views/{view['id']}").status_code == 204
    updated = body + code + "\n\nLe reste du texte est modifiable."
    assert owner.patch(url + "/body", json={"markdown": updated, "revision": 3}).status_code == 200
    with ZipFile(BytesIO(owner.get(base + "/export").content)) as zip_:
        assert not any(name.startswith("collections/") for name in zip_.namelist())
        rewritten = zip_.read(next(name for name in zip_.namelist() if host["id"][:8] in name)).decode()
        assert "Vue indisponible" in rewritten and ref not in rewritten
    assert owner.delete(f"/api/workspaces/{space['id']}/members/{reader_id}").status_code == 204
    assert reader.get(url).status_code == reader.get(collection_url).status_code == 404
