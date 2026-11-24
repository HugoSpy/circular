"""Collection relations through the API on both database engines."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from json import loads
from uuid import uuid4
from zipfile import ZipFile

from tests.test_docs import created
from tests.test_docs_collaboration import join
from tests.test_docs_collections import entry, field, make_collection, set_value
from tests.test_postgres import postgres_url  # noqa: F401
from tests.test_workspaces import create_workspace, workspace_people  # noqa: F401


def relation(client, base, source, target, name="Pages associées"):
    return created(client.post(base + f"/collections/{source['id']}/fields", json={
        "name": name, "kind": "relation", "targetCollectionId": target["id"],
    }))


def test_relation_writes_validate_scope_and_merge_concurrent_changes(workspace_people):
    _, (owner, editor, guest), _ = workspace_people
    space, base, projects, collection_url = make_collection(owner, "relations-ecriture")
    resources = created(owner.post(base + "/collections", json={"title": "Ressources"}))
    other = created(owner.post(base + "/collections", json={"title": "Autre collection"}))
    scalar = field(owner, collection_url, "Durée", "number")
    editor_id = join(owner, editor, space, "bob@epita.fr")
    source = entry(owner, base, projects, "Atelier")
    targets = [entry(owner, base, resources, "Guide"), entry(owner, base, resources, "Guide")]
    wrong = entry(owner, base, other, "Hors collection")
    foreign_space, _ = create_workspace(guest, "autre-espace-relations")
    foreign_base = f"/api/workspaces/{foreign_space['id']}/docs"
    foreign_collection = created(guest.post(foreign_base + "/collections", json={"title": "Confidentiel"}))
    foreign = entry(guest, foreign_base, foreign_collection, "Hors espace")
    for target, expected in ((None, 422), (foreign_collection["id"], 404), (projects["id"], 422)):
        response = owner.post(collection_url + "/fields", json={"name": "Relation", "kind": "relation", "targetCollectionId": target})
        assert response.status_code == expected
    linked = relation(owner, base, projects, resources)
    assert linked["targetCollectionId"] == resources["id"]
    assert owner.get(collection_url).json()["fields"] == [scalar, linked]
    url = base + f"/pages/{source['id']}/relations/{linked['id']}"
    for candidate in (wrong["id"], foreign["id"], str(uuid4())):
        failed = owner.patch(url, json={"add": [targets[0]["id"], candidate]})
        assert failed.status_code == 404
        assert failed.json() == {"error": "Document introuvable."}
    page_url = base + f"/pages/{source['id']}"
    assert owner.get(page_url).json()["properties"] == {}
    assert owner.patch(url, json={"add": [targets[0]["id"]] * 2}).status_code == 422
    assert owner.patch(page_url + f"/relations/{scalar['id']}", json={"add": [targets[0]["id"]]}).status_code == 422
    assert set_value(owner, base, source, linked, None).status_code == 422

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(client.patch, url, json={"add": [item["id"]]}) for client, item in zip((owner, editor), targets)]
        assert [item.result().status_code for item in results] == [200, 200]
    expected = sorted(target["id"] for target in targets)
    assert owner.get(page_url).json()["properties"][linked["id"]] == expected
    assert owner.patch(url, json={"add": [expected[0]]}).json()["properties"][linked["id"]] == expected
    assert owner.patch(base + f"/access/{editor_id}", json={"role": "reader"}).status_code == 204
    assert editor.get(page_url).json()["properties"][linked["id"]] == expected
    assert editor.patch(url, json={"remove": [expected[0]]}).status_code == 403
    assert guest.get(page_url).status_code == 404
    assert owner.patch(url, json={"remove": [expected[0]]}).json()["properties"][linked["id"]] == expected[1:]
    assert owner.patch(url, json={"remove": [expected[0]]}).json()["properties"][linked["id"]] == expected[1:]
    assert owner.delete(f"/api/workspaces/{space['id']}/members/{editor_id}").status_code == 204
    assert editor.get(page_url).status_code == 404
    assert editor.patch(url, json={"add": [expected[0]]}).status_code == 404


def test_relation_projection_archive_restore_duplicate_and_export(workspace_people, tmp_path):
    _, (owner, _, _), _ = workspace_people
    _, base, projects, _ = make_collection(owner, "relations-lecture")
    resources = created(owner.post(base + "/collections", json={"title": "Ressources"}))
    source = entry(owner, base, projects, "Une page vierge")
    target = entry(owner, base, resources, "Ancien titre")
    retired = entry(owner, base, resources, "Marqueur confidentiel")
    direct = relation(owner, base, projects, resources)
    reverse = relation(owner, base, resources, projects, "Projet")
    source_url = base + f"/pages/{source['id']}"
    target_url = base + f"/pages/{target['id']}"
    archived_url = base + f"/pages/{retired['id']}"
    write = source_url + f"/relations/{direct['id']}"
    assert owner.patch(write, json={"add": [target["id"], retired["id"]]}).status_code == 200
    assert owner.patch(target_url + f"/relations/{reverse['id']}", json={"add": [source["id"]]}).status_code == 200
    assert owner.patch(target_url + "/placement", json={"title": "Guide renommé", "collectionId": resources["id"]}).status_code == 200
    operation = created(owner.post(archived_url + "/trash", json={"revision": 1}))
    assert owner.patch(write, json={"add": [retired["id"]]}).status_code == 404
    assert owner.get(source_url).json()["properties"][direct["id"]] == [target["id"]]
    assert owner.get(target_url).json()["properties"][reverse["id"]] == [source["id"]]
    summaries = {item["id"]: item for item in owner.get(base).json()["pages"]}
    assert retired["id"] not in summaries
    assert summaries[source["id"]]["properties"] == {direct["id"]: [target["id"]]}
    assert summaries[target["id"]]["title"] == "Guide renommé"

    copy = created(owner.post(source_url + "/duplicate", json={}))
    assert copy["properties"] == {direct["id"]: [target["id"]]}
    template = created(owner.post(source_url + "/templates", json={"name": "Modèle", "revision": 1}))
    from_template = created(owner.post(base + "/pages", json={
        "title": "Issue du modèle", "templateId": template["id"], "collectionId": projects["id"],
    }))
    assert from_template["properties"] == {}
    archive = owner.get(base + "/export")
    assert archive.status_code == 200
    folder = tmp_path / "extrait"
    with ZipFile(BytesIO(archive.content)) as zipped:
        zipped.extractall(folder)
    manifest_text = (folder / "collections.json").read_text()
    assert retired["id"] not in manifest_text and "Marqueur confidentiel" not in manifest_text
    data = loads(manifest_text)
    source_path = next(path for path in data["pages"] if source["id"][:8] in path)
    target_path = next(path for path in data["pages"] if target["id"][:8] in path)
    recorded, = data["pages"][source_path]["values"][direct["id"]]
    assert (folder / recorded).resolve(strict=True) == (folder / target_path).resolve(strict=True)
    back, = data["pages"][target_path]["values"][reverse["id"]]
    assert (folder / back).resolve(strict=True) == (folder / source_path).resolve(strict=True)
    assert owner.post(base + f"/trash/{operation['id']}/restore", json={}).status_code == 200
    assert owner.get(source_url).json()["properties"][direct["id"]] == sorted([target["id"], retired["id"]])
    assert owner.get(base + f"/pages/{copy['id']}").json()["properties"][direct["id"]] == [target["id"]]
