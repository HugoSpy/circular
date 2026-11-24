"""Collection schema, view compatibility and property validation on both engines."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from json import loads
from pathlib import Path
from zipfile import ZipFile

from backend.app.db.session import Database
from tests.test_docs import created
from tests.test_postgres import postgres_url  # noqa: F401
from tests.test_workspaces import create_workspace, invite, workspace_people  # noqa: F401


def make_collection(owner, slug):
    workspace, _ = create_workspace(owner, slug)
    root = f"/api/workspaces/{workspace['id']}/docs"
    collection = created(owner.post(root + "/collections", json={"title": "Bibliothèque"}))
    return workspace, root, collection, root + f"/collections/{collection['id']}"


def field(owner, path, name, kind, options=()):
    return created(owner.post(path + "/fields", json={"name": name, "kind": kind, "options": list(options)}))


def entry(owner, base, collection, title="Guide"):
    return created(owner.post(base + "/pages", json={"title": title, "collectionId": collection["id"]}))


def set_value(owner, base, page, field_, value):
    return owner.patch(base + f"/pages/{page['id']}/properties/{field_['id']}", json={"value": value})


def condition(field_, operator, value=None):
    return {"fieldId": field_["id"], "operator": operator, "value": value}


def test_field_type_migration_preserves_legacy_views_and_values(workspace_people):
    app, (owner, _, _), target = workspace_people
    space, base, collection, path = make_collection(owner, "vues-historiques")
    stage = field(owner, path, "État", "select", ["Publié", "À relire"])
    score = field(owner, path, "Score", "number")
    page = entry(owner, base, collection)
    assert set_value(owner, base, page, stage, "Publié").status_code == 200
    assert set_value(owner, base, page, score, 0).status_code == 200
    view = created(owner.post(path + "/views", json={
        "name": "Vues historiques", "filters": [{"fieldId": stage["id"], "value": "Publié"}],
        "sortBy": score["id"], "direction": "desc", "hidden": [stage["id"]],
    }))
    original = Path(__file__).parents[1] / "backend/app/db/migrations/007_docs.sql"
    definition = original.read_text().split("CREATE TABLE docs_fields (", 1)[1].split(";", 1)[0]
    with app.state.database.connect(write=True) as connection:
        connection.execute("DROP TABLE docs_page_relations")
        connection.execute("DELETE FROM schema_migrations WHERE version IN ('012_docs_relations.sql', '013_docs_aggregations.sql', '014_docs_formulas.sql')")
        if app.state.database.dialect == "sqlite":
            connection.execute("ALTER TABLE docs_fields RENAME TO fields_new")
            connection.execute("CREATE TABLE docs_fields (" + definition)
            connection.execute("""
                INSERT INTO docs_fields (workspace_id, collection_id, id, name, kind, options, position)
                SELECT workspace_id, collection_id, id, name, kind, options, position FROM fields_new
            """)
            connection.execute("DROP TABLE fields_new")
        else:
            connection.execute("ALTER TABLE docs_fields DROP COLUMN formula")
            connection.execute("ALTER TABLE docs_fields DROP COLUMN aggregation")
            connection.execute("ALTER TABLE docs_fields DROP COLUMN target_collection_id")
            connection.execute("ALTER TABLE docs_fields DROP CONSTRAINT docs_fields_kind_check")
            connection.execute("""
                ALTER TABLE docs_fields ADD CONSTRAINT docs_fields_kind_check
                CHECK (kind IN ('text', 'number', 'date', 'select', 'checkbox'))
            """)
        connection.execute("DELETE FROM schema_migrations WHERE version = ?", ("009_docs_field_types.sql",))
    Database(target)
    Database(target)
    schema = owner.get(path).json()
    assert schema["fields"] == [stage, score]
    assert schema["views"][-1] == view
    assert owner.get(base + f"/pages/{page['id']}").json()["properties"] == {stage["id"]: "Publié", score["id"]: 0}
    multi = field(owner, path, "Thèmes", "multi", ["Atelier"])
    assert multi["kind"] == "multi"
    with app.state.database.connect() as connection:
        assert connection.execute("SELECT workspace_id FROM docs_fields WHERE id = ?", (stage["id"],)).fetchone()[0] == space["id"]


def test_rename_options_updates_archived_pages_and_nested_filters(workspace_people):
    _, (owner, editor, outsider), _ = workspace_people
    space, base, collection, path = make_collection(owner, "options-collections")
    state = field(owner, path, "État", "select", ["À relire", "Publié"])
    tags = field(owner, path, "Thèmes", "multi", ["Docs", "Atelier"])
    live = entry(owner, base, collection)
    archived = entry(owner, base, collection, "Ancien guide")
    for page in (live, archived):
        assert set_value(owner, base, page, state, "Publié").status_code == 200
        assert set_value(owner, base, page, tags, ["Docs", "Atelier"]).status_code == 200
    trash = created(owner.post(base + f"/pages/{archived['id']}/trash", json={"revision": archived["revision"]}))
    legacy = created(owner.post(path + "/views", json={"name": "Publiés", "filters": [{"fieldId": state["id"], "value": "Publié"}]}))
    advanced = created(owner.post(path + "/views", json={
        "name": "Kanban", "layout": "board", "groupBy": state["id"],
        "filterTree": {"mode": "all", "conditions": [{"mode": "any", "conditions": [
            condition(tags, "contains", "Docs"), condition(state, "eq", "Publié"),
        ]}]},
    }))
    edit_state = {"name": "Publication", "previousOptions": state["options"], "options": ["À relire", "Prêt"]}
    assert outsider.patch(path + f"/fields/{state['id']}", json=edit_state).status_code == 404
    assert owner.patch(path + f"/fields/{state['id']}", json=edit_state).json()["options"] == ["À relire", "Prêt"]
    # A simultaneous editor using a superseded label cannot restore the old value.
    invitation = invite(owner, space, "bob@epita.fr")
    assert editor.post(f"/api/workspace-invitations/{invitation}/accept", json={}).status_code == 200
    with ThreadPoolExecutor(max_workers=2) as pool:
        old_schema = pool.submit(editor.patch, path + f"/fields/{state['id']}", json=edit_state)
        old_value = pool.submit(set_value, editor, base, live, state, "Publié")
        assert old_schema.result().status_code == 409 and old_value.result().status_code == 422
    assert owner.patch(path + f"/fields/{tags['id']}", json={
        "name": tags["name"], "previousOptions": tags["options"], "options": ["Documentation", "Atelier", "Équipe"],
    }).status_code == 200

    result = owner.patch(path + "/fields/order", json={"fieldIds": [tags["id"], state["id"]]})
    assert [item["id"] for item in result.json()] == [tags["id"], state["id"]]
    assert owner.patch(path + "/fields/order", json={"fieldIds": [state["id"]]}).status_code == 409
    views = {item["id"]: item for item in owner.get(path).json()["views"]}
    assert views[legacy["id"]]["filters"][0]["value"] == "Prêt"
    assert [item["value"] for item in views[advanced["id"]]["filterTree"]["conditions"][0]["conditions"]] == ["Documentation", "Prêt"]
    expected = {state["id"]: "Prêt", tags["id"]: ["Documentation", "Atelier"]}
    assert owner.get(base + f"/pages/{live['id']}").json()["properties"] == expected
    restored = owner.post(base + f"/trash/{trash['id']}/restore", json={})
    assert restored.json()["page"]["properties"] == expected


def test_advanced_views_validate_typed_operands_and_export_new_values(workspace_people):
    _, (owner, reader, _), _ = workspace_people
    space, base, collection, path = make_collection(owner, "types-collections")
    url = field(owner, path, "Documentation", "url")
    tags = field(owner, path, "Thèmes", "multi", ["Équipe", "Atelier"])
    score = field(owner, path, "Score", "number")
    due = field(owner, path, "Échéance", "date")
    end_due = field(owner, path, "Fin", "date")
    verified = field(owner, path, "Vérifié", "checkbox")
    page = entry(owner, base, collection)
    assert set_value(owner, base, page, url, "https://example.org/guide").status_code == 200
    for invalid in ("ftp://example.org", "javascript:alert(1)", "https://", "https://example.org/a b", "https://example.org:99999"):
        assert set_value(owner, base, page, url, invalid).status_code == 422
    assert set_value(owner, base, page, tags, ["Équipe", "Atelier"]).status_code == 200
    assert set_value(owner, base, page, tags, ["Atelier", "Atelier"]).status_code == 422
    assert set_value(owner, base, page, tags, ["Autre"]).status_code == 422
    assert set_value(owner, base, page, verified, False).status_code == 200
    assert set_value(owner, base, page, score, 0).status_code == 200

    data = {"name": "Liste filtrée", "layout": "list", "groupBy": verified["id"], "dateFieldId": None, "hidden": [url["id"]],
            "sorts": [{"fieldId": score["id"], "direction": "desc"}, {"fieldId": "title", "direction": "asc"}],
            "filterTree": {"mode": "all", "conditions": [condition(score, "gte", 0), {"mode": "any", "conditions": [
                condition(tags, "contains", "Équipe"), condition(verified, "eq", False),
            ]}]}}
    view = created(owner.post(path + "/views", json=data))
    assert view == {"id": view["id"], **data}
    assert owner.get(path).json()["views"][-1] == view
    calendar_data = {"name": "Calendrier", "layout": "calendar", "groupBy": None, "dateFieldId": due["id"],
                     "filterTree": {"mode": "all", "conditions": []}, "sorts": [], "hidden": []}
    calendar = created(owner.post(path + "/views", json=calendar_data))
    assert {key: value for key, value in calendar.items() if key != "id"} == calendar_data
    invitation = invite(owner, space, "bob@epita.fr")
    assert reader.post(f"/api/workspace-invitations/{invitation}/accept", json={}).status_code == 200
    member = reader.get("/api/auth/me").json()["user"]["id"]
    assert owner.patch(base + f"/access/{member}", json={"role": "reader"}).status_code == 204
    reader_view = reader.get(path).json()["views"][-1]
    assert reader_view == calendar
    timeline_data = {"name": "Chronologie", "layout": "timeline", "groupBy": None,
                     "dateFieldId": due["id"], "endDateFieldId": end_due["id"],
                     "filterTree": {"mode": "all", "conditions": []}, "sorts": [], "hidden": []}
    timeline = created(owner.post(path + "/views", json=timeline_data))
    assert {key: value for key, value in timeline.items() if key != "id"} == timeline_data
    assert reader.get(path).json()["views"][-1] == timeline
    assert reader.patch(path + f"/views/{timeline['id']}", json=timeline_data).status_code == 403
    for invalid in (
        {**data, "layout": "board"}, {**data, "groupBy": score["id"]},
        {**data, "sorts": [*data["sorts"], data["sorts"][0]]},
        {**data, "sorts": [{"fieldId": tags["id"], "direction": "asc"}]},
        {**data, "filterTree": {"mode": "all", "conditions": [condition(score, "gte", "0")]}},
        {**data, "filterTree": {"mode": "all", "conditions": [condition(tags, "contains", "Inconnu")]}},
        {**calendar_data, "dateFieldId": None}, {**calendar_data, "dateFieldId": score["id"]},
        {**calendar_data, "dateFieldId": "22222222-2222-4222-8222-222222222222"},
        {**calendar_data, "groupBy": verified["id"]},
        {**timeline_data, "endDateFieldId": due["id"]},
        {**timeline_data, "endDateFieldId": score["id"]},
        {**timeline_data, "endDateFieldId": "22222222-2222-4222-8222-222222222222"},
        {**timeline_data, "endDateFieldId": None},
        {**timeline_data, "dateFieldId": score["id"]},
        {**timeline_data, "groupBy": verified["id"]},
    ):
        assert owner.post(path + "/views", json=invalid).status_code == 422

    with ZipFile(BytesIO(owner.get(base + "/export").content)) as archive:
        metadata = loads(archive.read("collections.json"))
    exported_collection = next(item for item in metadata["collections"] if item["id"] == collection["id"])
    assert next(view for view in exported_collection["views"] if view["id"] == calendar["id"])["dateFieldId"] == due["id"]
    exported_timeline = next(view for view in exported_collection["views"] if view["id"] == timeline["id"])
    assert exported_timeline["dateFieldId"] == due["id"]
    assert exported_timeline["endDateFieldId"] == end_due["id"]
    exported = next(iter(metadata["pages"].values()))["values"]
    assert exported == {url["id"]: "https://example.org/guide", tags["id"]: ["Équipe", "Atelier"], score["id"]: 0, verified["id"]: False}
