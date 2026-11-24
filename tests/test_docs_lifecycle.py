"""Revision and restoration contracts through Circular's authenticated API."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import re
from urllib.parse import unquote
from zipfile import ZipFile

from backend.app.db.session import Database
from tests.test_docs import created
from tests.test_postgres import postgres_url  # noqa: F401
from tests.test_workspaces import create_workspace, invite, workspace_people  # noqa: F401


def page_url(base, page):
    return base + "/pages/" + page["id"]


def save(client, base, page, markdown):
    response = client.patch(page_url(base, page) + "/body", json={"revision": page["revision"], "markdown": markdown})
    assert response.status_code == 200, response.text
    return response.json()


def trash(client, base, page):
    return created(client.post(page_url(base, page) + "/trash", json={"revision": page["revision"]}))


def test_restore_revision_preserves_arrangement_and_detects_a_stale_comparison(workspace_people):
    app, (owner, editor, outsider), _ = workspace_people
    space, _ = create_workspace(owner, "revisions-docs")
    base = f"/api/workspaces/{space['id']}/docs"
    parent = created(owner.post(base + "/pages", json={"title": "Dossier"}))
    target = created(owner.post(base + "/pages", json={"title": "Référence"}))
    original = created(owner.post(base + "/pages", json={"title": "Premier titre"}))
    initial = save(owner, base, original, f"Voir [](/pages/{target['id']}).")
    url = page_url(base, initial)
    renamed = owner.patch(url + "/placement", json={"title": "Nouveau titre", "parentId": parent["id"], "revision": initial["revision"]})
    assert renamed.status_code == 200
    assert renamed.json()["revision"] == 3
    assert outsider.get(url + "/revisions").status_code == 404
    invitation = invite(owner, space, "bob@epita.fr")
    assert editor.post(f"/api/workspace-invitations/{invitation}/accept", json={}).status_code == 200
    latest = save(editor, base, renamed.json(), "Version concurrente")
    assert latest["revision"] == 4
    first_page = owner.get(url + "/revisions", params={"limit": 2}).json()
    assert [item["revision"] for item in first_page["items"]] == [4, 3]
    assert first_page["nextBefore"] == 3
    previous = owner.get(url + "/revisions", params={"before": 3}).json()
    assert [item["title"] for item in previous["items"]] == ["Premier titre", "Premier titre"]
    snapshot = owner.get(url + "/revisions/2").json()
    assert snapshot["markdown"] == initial["markdown"] and snapshot["createdAt"]
    assert owner.post(url + "/revisions/2/restore", json={"revision": 3}).status_code == 409
    restored = owner.post(url + "/revisions/2/restore", json={"revision": 4})
    assert restored.status_code == 200, restored.text
    restored = restored.json()
    assert (restored["id"], restored["parentId"], restored["title"], restored["revision"]) == (
        original["id"], parent["id"], "Premier titre", 5,
    )
    assert restored["markdown"] == snapshot["markdown"]
    assert owner.get(page_url(base, target)).json()["backlinks"] == [original["id"]]
    with app.state.database.connect() as connection:
        history = connection.execute("""
            SELECT revision, title FROM docs_revisions WHERE workspace_id = ? AND page_id = ? ORDER BY revision
        """, (space["id"], original["id"])).fetchall()
    assert [row["revision"] for row in history] == [1, 2, 3, 4, 5]


def test_duplicate_page_keeps_collection_properties_and_outgoing_links(workspace_people):
    _, (owner, _, other), _ = workspace_people
    space, _ = create_workspace(owner, "copie-docs")
    base = f"/api/workspaces/{space['id']}/docs"
    parent = created(owner.post(base + "/pages", json={"title": "Dossier"}))
    target = created(owner.post(base + "/pages", json={"title": "Cible"}))
    collection = created(owner.post(base + "/collections", json={"title": "Bibliothèque"}))
    field = created(owner.post(base + f"/collections/{collection['id']}/fields", json={"name": "Revu", "kind": "checkbox"}))
    source = created(owner.post(base + "/pages", json={
        "title": "Guide", "parentId": parent["id"], "collectionId": collection["id"],
    }))
    child = created(owner.post(base + "/pages", json={"title": "Sous-page", "parentId": source["id"]}))
    source = save(owner, base, source, f"[](/pages/{target['id']})")
    url = page_url(base, source)
    assert owner.patch(url + f"/properties/{field['id']}", json={"value": True}).status_code == 200
    assert other.post(url + "/duplicate", json={}).status_code == 404
    copy = created(owner.post(url + "/duplicate", json={}))
    assert copy["id"] != source["id"] and copy["revision"] == 1
    assert (copy["parentId"], copy["collectionId"], copy["title"], copy["markdown"]) == (
        parent["id"], collection["id"], "Copie de Guide", source["markdown"],
    )
    assert copy["properties"] == {field["id"]: True}
    assert owner.get(page_url(base, child)).json()["parentId"] == source["id"]
    assert all(item["parentId"] != copy["id"] for item in owner.get(base).json()["pages"])
    assert set(owner.get(page_url(base, target)).json()["backlinks"]) == {source["id"], copy["id"]}
    assert [item["revision"] for item in owner.get(page_url(base, copy) + "/revisions").json()["items"]] == [1]


def test_trash_hides_active_subtree_and_restores_only_its_operation(workspace_people, tmp_path):
    _, (owner, viewer, _), _ = workspace_people
    space, _ = create_workspace(owner, "corbeille-docs")
    base = f"/api/workspaces/{space['id']}/docs"
    upper = created(owner.post(base + "/pages", json={"title": "Dossier"}))
    root = created(owner.post(base + "/pages", json={"title": "Plan", "parentId": upper["id"]}))
    active_child = created(owner.post(base + "/pages", json={"title": "Enfant actif", "parentId": root["id"]}))
    hidden_child = created(owner.post(base + "/pages", json={"title": "Enfant masqué", "parentId": root["id"]}))
    external = created(owner.post(base + "/pages", json={"title": "Sommaire"}))
    external = save(owner, base, external, f"[](/pages/{active_child['id']})")
    save(owner, base, active_child, f"Un indice unique. [](/pages/{external['id']})")
    active_child = owner.get(page_url(base, active_child)).json()
    child_op = trash(owner, base, hidden_child)
    root_op = trash(owner, base, root)
    assert root_op["count"] == 2
    assert trash(owner, base, root) == root_op
    parent_op = trash(owner, base, upper)
    assert parent_op["count"] == 1
    assert viewer.get(base + "/trash").status_code == 404
    assert viewer.post(base + f"/trash/{root_op['id']}/restore", json={}).status_code == 404
    assert all(owner.get(page_url(base, page)).status_code == 404 for page in (upper, root, active_child, hidden_child))
    assert owner.get(page_url(base, root) + "/revisions").status_code == 404
    assert owner.get(base + "/search", params={"q": "indice"}).json() == []
    assert owner.get(page_url(base, external)).json()["backlinks"] == []
    assert {page["id"] for page in owner.get(base).json()["pages"]} == {external["id"]}
    external = save(owner, base, external, external["markdown"] + "\n\nLien conservé.")
    with ZipFile(BytesIO(owner.get(base + "/export").content)) as archive:
        assert len(archive.namelist()) == 1
        assert "page indisponible" in archive.read(archive.namelist()[0]).decode()

    entry = next(item for item in owner.get(base + "/trash").json() if item["id"] == root_op["id"])
    assert entry["parentTitle"] == upper["title"] and not entry["parentAvailable"]
    response = owner.post(base + f"/trash/{root_op['id']}/restore", json={})
    assert response.status_code == 200, response.text
    revived = response.json()
    assert revived["count"] == 2 and revived["parentUnavailable"]
    assert (revived["page"]["id"], revived["page"]["parentId"]) == (root["id"], None)
    assert owner.get(page_url(base, active_child)).json()["backlinks"] == [external["id"]]
    assert owner.get(page_url(base, external)).json()["backlinks"] == [active_child["id"]]
    assert owner.get(page_url(base, hidden_child)).status_code == 404
    assert {item["id"] for item in owner.get(base + "/trash").json()} == {child_op["id"], parent_op["id"]}
    with ZipFile(BytesIO(owner.get(base + "/export").content)) as archive:
        archive.extractall(tmp_path)
    extracted = list(tmp_path.rglob("*.md"))
    source_file = next(path for path in extracted if external["id"][:8] in path.name)
    destination = next(path for path in extracted if active_child["id"][:8] in path.name)
    match = re.search(r"\[Enfant actif\]\(([^)]+)\)", source_file.read_text())
    assert match and (source_file.parent / unquote(match[1])).resolve(strict=True) == destination.resolve(strict=True)


def test_trash_and_concurrent_save_are_serialized(workspace_people):
    _, (owner, editor, _), _ = workspace_people
    space, _ = create_workspace(owner, "corbeille-concurrente")
    base = f"/api/workspaces/{space['id']}/docs"
    invitation = invite(owner, space, "bob@epita.fr")
    assert editor.post(f"/api/workspace-invitations/{invitation}/accept", json={}).status_code == 200
    root = created(owner.post(base + "/pages", json={"title": "Page"}))
    url = page_url(base, root)
    with ThreadPoolExecutor(max_workers=2) as pool:
        archiving = pool.submit(owner.post, url + "/trash", json={"revision": 1})
        saving = pool.submit(editor.patch, url + "/body", json={"revision": 1, "markdown": "Dernière version"})
        status = (archiving.result().status_code, saving.result().status_code)
    assert status in {(201, 404), (409, 200)}
    if status[0] == 201:
        assert owner.get(url).status_code == 404
    else:
        assert owner.get(url).json()["markdown"] == "Dernière version"

    second = created(owner.post(base + "/pages", json={"title": "Une autre page"}))
    latest = save(editor, base, second, "Révision confirmée")
    stale = owner.post(page_url(base, second) + "/trash", json={"revision": second["revision"]})
    assert stale.status_code == 409
    assert owner.get(page_url(base, second)).json()["revision"] == latest["revision"]


def test_lifecycle_migration_backfills_the_last_known_revision(workspace_people):
    app, (owner, _, _), target = workspace_people
    space, _ = create_workspace(owner, "migration-docs")
    base = f"/api/workspaces/{space['id']}/docs"
    legacy = created(owner.post(base + "/pages", json={"title": "Page existante"}))
    legacy = save(owner, base, legacy, "Contenu existant")
    with app.state.database.connect(write=True) as connection:
        for table in ("docs_trashed_pages", "docs_trash", "docs_revisions"):
            connection.execute("DROP TABLE " + table)
        connection.execute("DELETE FROM schema_migrations WHERE version = ?", ("008_docs_lifecycle.sql",))
    Database(target)
    Database(target)
    url = page_url(base, legacy)
    assert owner.get(url + "/revisions").json()["items"] == [
        {"revision": 2, "title": "Page existante", "author": None, "createdAt": None},
    ]
    assert owner.get(url + "/revisions/2").json()["markdown"] == "Contenu existant"
    assert save(owner, base, legacy, "Nouveau contenu")["revision"] == 3
