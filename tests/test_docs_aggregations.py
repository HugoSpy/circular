"""Aggregation definitions and projections through the API on both engines."""
from io import BytesIO
from json import loads
from pathlib import Path
from zipfile import ZipFile

from backend.app.db.session import Database

from tests.test_docs import created
from tests.test_docs_collaboration import join
from tests.test_docs_collections import condition, entry, field, make_collection, set_value
from tests.test_docs_relations import relation
from tests.test_postgres import postgres_url  # noqa: F401
from tests.test_workspaces import workspace_people  # noqa: F401


def test_aggregation_permissions_and_projections(workspace_people, tmp_path):
    app, (owner, reader, outsider), _ = workspace_people
    space, base, projects, project_collection = make_collection(owner, "agregations")
    resources = created(owner.post(base + "/collections", json={"title": "Ressources"}))
    resource_collection = base + "/collections/" + resources["id"]
    hours = field(owner, resource_collection, "Heures", "number")
    text = field(owner, resource_collection, "Commentaire", "text")
    wrong_number = field(owner, project_collection, "Coefficient", "number")
    links = relation(owner, base, projects, resources)
    reciprocal = relation(owner, base, resources, projects, "Projet")
    member = join(owner, reader, space, "bob@epita.fr")
    assert owner.patch(base + f"/access/{member}", json={"role": "reader"}).status_code == 204

    def definition(name, operation, source=None, link=links):
        config = {"relationFieldId": link["id"], "operation": operation}
        if source:
            config["sourceFieldId"] = source["id"]
        return {"name": name, "kind": "aggregate", "aggregation": config}

    fields_url = project_collection + "/fields"
    for invalid in (
        definition("Relation invalide", "count", link=wrong_number),
        definition("Sans nombre", "sum"),
        definition("Avec nombre", "count", hours),
        definition("Mauvais type", "average", text),
        definition("Mauvaise collection", "sum", wrong_number),
    ):
        assert owner.post(fields_url, json=invalid).status_code == 422
    assert reader.post(fields_url, json=definition("Interdite", "count")).status_code == 403

    count = created(owner.post(fields_url, json=definition("Ressources liées", "count")))
    total = created(owner.post(fields_url, json=definition("Total", "sum", hours)))
    average = created(owner.post(fields_url, json=definition("Moyenne", "average", hours)))
    ids = [item["id"] for item in (count, total, average)]
    reverse_count = created(owner.post(resource_collection + "/fields", json=definition("Projets liés", "count", link=reciprocal)))
    assert owner.post(fields_url, json=definition("Dépendance calculée", "sum", reverse_count)).status_code == 422

    project = entry(owner, base, projects, "Préparer l’atelier")
    page_url = base + "/pages/" + project["id"]
    links_url = page_url + "/relations/" + links["id"]
    assert set_value(owner, base, project, total, None).status_code == 422

    def calculated(properties):
        return [properties[identifier] for identifier in ids]

    def check(count_value, total_value, average_value, client=owner):
        expected = [count_value, total_value, average_value]
        assert calculated(client.get(page_url).json()["properties"]) == expected
        summary = next(page for page in client.get(base).json()["pages"] if page["id"] == project["id"])
        assert calculated(summary["properties"]) == expected

    check(0, None, None)
    targets = [entry(owner, base, resources, title) for title in ("Repérage privé", "Ajustement", "Contrôle", "Notes")]
    for target, value in zip(targets, (6, -2, 0)):
        assert set_value(owner, base, target, hours, value).status_code == 200
    assert owner.patch(links_url, json={"add": [target["id"] for target in targets]}).status_code == 200
    reverse_url = base + f"/pages/{targets[0]['id']}/relations/{reciprocal['id']}"
    assert owner.patch(reverse_url, json={"add": [project["id"]]}).json()["properties"][reverse_count["id"]] == 1
    check(4, 4, 4 / 3)
    assert set_value(owner, base, targets[1], hours, -2.5).status_code == 200
    check(4, 3.5, 3.5 / 3)
    assert set_value(owner, base, targets[1], hours, None).status_code == 200
    check(4, 6, 3)
    assert set_value(owner, base, targets[1], hours, -2).status_code == 200

    view = created(owner.post(project_collection + "/views", json={
        "name": "Budget", "layout": "table",
        "filterTree": {"mode": "all", "conditions": [{"mode": "any", "conditions": [
            condition(total, "gte", 0), condition(average, "empty"),
        ]}]},
        "sorts": [{"fieldId": total["id"], "direction": "desc"}],
    }))
    assert owner.post(project_collection + "/views", json={
        "name": "Filtre invalide", "layout": "table",
        "filterTree": {"conditions": [condition(total, "contains", "4")]},
    }).status_code == 422
    renamed = owner.patch(fields_url + "/" + total["id"], json={"name": "Total prévu", "options": [], "previousOptions": []})
    assert renamed.json() == {**total, "name": "Total prévu"}
    check(4, 4, 4 / 3, reader)

    operation = created(owner.post(base + f"/pages/{targets[0]['id']}/trash", json={"revision": 1}))
    check(3, -2, -1, reader)
    archive = reader.get(base + "/export")
    assert archive.status_code == 200
    with ZipFile(BytesIO(archive.content)) as zipped:
        zipped.extractall(tmp_path / "zip")
    manifest = (tmp_path / "zip/collections.json").read_text()
    assert targets[0]["id"] not in manifest and "Repérage privé" not in manifest
    data = loads(manifest)
    schema = next(collection for collection in data["collections"] if collection["id"] == projects["id"])
    assert view in schema["views"] and renamed.json() in schema["fields"]
    source, = [path for path in data["pages"] if project["id"][:8] in path]
    exported = data["pages"][source]["values"]
    assert calculated(exported) == [3, -2, -1]
    for path in exported[links["id"]]:
        assert (tmp_path / "zip" / path).resolve(strict=True).is_file()
    assert owner.post(base + f"/trash/{operation['id']}/restore", json={}).status_code == 200
    check(4, 4, 4 / 3, reader)

    assert owner.patch(links_url, json={"remove": [targets[0]["id"]]}).status_code == 200
    check(3, -2, -1)
    assert owner.patch(links_url, json={"add": [targets[0]["id"]]}).status_code == 200
    maximum = 9_007_199_254_740_991
    for target, value in zip(targets, (maximum, 0, 0, 0.125)):
        assert set_value(owner, base, target, hours, value).status_code == 200
    check(4, {"error": "out_of_range"}, maximum / 4)
    with ZipFile(BytesIO(reader.get(base + "/export").content)) as zipped:
        final_values = loads(zipped.read("collections.json"))["pages"][source]["values"]
    assert calculated(final_values) == [4, {"error": "out_of_range"}, maximum / 4]
    with app.state.database.connect() as connection:
        stored = connection.execute("SELECT properties FROM docs_pages WHERE id = ?", (project["id"],)).fetchone()
        assert loads(stored["properties"]) == {}
    assert outsider.get(page_url).status_code == 404
    assert owner.delete(f"/api/workspaces/{space['id']}/members/{member}").status_code == 204
    assert reader.get(page_url).status_code == reader.get(base + "/export").status_code == 404


def test_aggregation_migration_preserves_existing_relations(workspace_people):
    app, (owner, _, _), target = workspace_people
    _, base, projects, project_collection = make_collection(owner, "agregations-historiques")
    resources = created(owner.post(base + "/collections", json={"title": "Ressources"}))
    hours = field(owner, base + "/collections/" + resources["id"], "Heures", "number")
    links = relation(owner, base, projects, resources)
    project = entry(owner, base, projects)
    resource = entry(owner, base, resources)
    page_url = base + "/pages/" + project["id"]
    assert set_value(owner, base, resource, hours, 6).status_code == 200
    assert owner.patch(page_url + "/relations/" + links["id"], json={"add": [resource["id"]]}).status_code == 200
    view = created(owner.post(project_collection + "/views", json={"name": "Historique", "hidden": [links["id"]]}))
    trash = created(owner.post(base + f"/pages/{resource['id']}/trash", json={"revision": 1}))

    database = app.state.database
    with database.connect(write=True) as connection:
        connection.execute("DELETE FROM schema_migrations WHERE version IN ('013_docs_aggregations.sql', '014_docs_formulas.sql')")
        if database.dialect == "postgresql":
            connection.execute("ALTER TABLE docs_fields DROP COLUMN formula")
            connection.execute("ALTER TABLE docs_fields DROP COLUMN aggregation")
            connection.execute("ALTER TABLE docs_fields DROP CONSTRAINT docs_fields_kind_check")
            connection.execute("""
                ALTER TABLE docs_fields ADD CONSTRAINT docs_fields_kind_check
                CHECK (kind IN ('text', 'number', 'date', 'select', 'checkbox', 'url', 'multi', 'relation'))
            """)
        else:
            migration = Path(__file__).parents[1] / "backend/app/db/migrations/012_docs_relations.sql"
            relation_schema = migration.read_text().split("CREATE TABLE docs_page_relations", 1)[1]
            field_schema = migration.read_text().split("CREATE TABLE docs_fields", 1)[1].split(";", 1)[0]
            connection.execute("ALTER TABLE docs_page_relations RENAME TO relations_current")
            connection.execute("ALTER TABLE docs_fields RENAME TO fields_current")
            connection.execute("CREATE TABLE docs_fields" + field_schema)
            connection.execute("""
                INSERT INTO docs_fields (workspace_id, collection_id, id, name, kind, options, position, target_collection_id)
                SELECT workspace_id, collection_id, id, name, kind, options, position, target_collection_id FROM fields_current
            """)
            table, index = relation_schema.strip().rstrip(";").split(";", 1)
            connection.execute("CREATE TABLE docs_page_relations" + table)
            connection.execute("INSERT INTO docs_page_relations SELECT * FROM relations_current")
            connection.execute("DROP TABLE relations_current")
            connection.execute("DROP TABLE fields_current")
            connection.execute(index)

    Database(target)
    Database(target)
    assert owner.get(project_collection).json()["views"][-1] == view
    assert owner.get(project_collection).json()["fields"] == [links]
    assert owner.get(page_url).json()["properties"] == {}
    assert owner.post(base + f"/trash/{trash['id']}/restore", json={}).status_code == 200
    properties = owner.get(page_url).json()["properties"]
    assert properties == {links["id"]: [resource["id"]]}
    total = created(owner.post(project_collection + "/fields", json={
        "name": "Total", "kind": "aggregate",
        "aggregation": {"relationFieldId": links["id"], "operation": "sum", "sourceFieldId": hours["id"]},
    }))
    doubled = created(owner.post(project_collection + "/fields", json={
        "name": "Total doublé", "kind": "formula", "formula": {"expression": "2 * {" + total["id"] + "}"},
    }))
    assert owner.get(page_url).json()["properties"][total["id"]] == 6
    assert owner.get(page_url).json()["properties"][doubled["id"]] == 12
    trashed = created(owner.post(base + f"/pages/{resource['id']}/trash", json={"revision": 1}))
    assert owner.get(page_url).json()["properties"][doubled["id"]] is None
    assert owner.post(base + f"/trash/{trashed['id']}/restore", json={}).status_code == 200
    assert owner.get(page_url).json()["properties"][doubled["id"]] == 12


def test_formula_migration_preserves_existing_aggregation(workspace_people):
    app, (owner, _, _), target = workspace_people
    _, base, projects, project_url = make_collection(owner, "formules-migration")
    resources = created(owner.post(base + "/collections", json={"title": "Ressources"}))
    resources_url = base + "/collections/" + resources["id"]
    hours = field(owner, resources_url, "Heures", "number")
    links = relation(owner, base, projects, resources)
    project = entry(owner, base, projects)
    resource = entry(owner, base, resources)
    assert set_value(owner, base, resource, hours, 6).status_code == 200
    assert owner.patch(base + f"/pages/{project['id']}/relations/{links['id']}", json={"add": [resource["id"]]}).status_code == 200
    aggregate = created(owner.post(project_url + "/fields", json={
        "name": "Total", "kind": "aggregate",
        "aggregation": {"relationFieldId": links["id"], "operation": "sum", "sourceFieldId": hours["id"]},
    }))
    assert owner.get(base + f"/pages/{project['id']}").json()["properties"][aggregate["id"]] == 6

    database = app.state.database
    with database.connect(write=True) as connection:
        connection.execute("DELETE FROM schema_migrations WHERE version = '014_docs_formulas.sql'")
        if database.dialect == "postgresql":
            connection.execute("ALTER TABLE docs_fields DROP COLUMN formula")
            connection.execute("ALTER TABLE docs_fields DROP CONSTRAINT docs_fields_kind_check")
            connection.execute("ALTER TABLE docs_fields ADD CONSTRAINT docs_fields_kind_check CHECK (kind IN ('text', 'number', 'date', 'select', 'checkbox', 'url', 'multi', 'relation', 'aggregate'))")
        else:
            migration = Path(__file__).parents[1] / "backend/app/db/migrations/013_docs_aggregations.sql"
            schema = migration.read_text()
            field_schema = schema.split("CREATE TABLE docs_fields", 1)[1].split(";", 1)[0]
            relation_schema = schema.split("CREATE TABLE docs_page_relations", 1)[1].split(";", 1)[0]
            connection.execute("DROP INDEX docs_page_relations_target")
            connection.execute("ALTER TABLE docs_page_relations RENAME TO relations_current")
            connection.execute("ALTER TABLE docs_fields RENAME TO fields_current")
            connection.execute("CREATE TABLE docs_fields" + field_schema)
            connection.execute("""
                INSERT INTO docs_fields (workspace_id, collection_id, id, name, kind, options, position, target_collection_id, aggregation)
                SELECT workspace_id, collection_id, id, name, kind, options, position, target_collection_id, aggregation FROM fields_current
            """)
            connection.execute("CREATE TABLE docs_page_relations" + relation_schema)
            connection.execute("INSERT INTO docs_page_relations SELECT * FROM relations_current")
            connection.execute("DROP TABLE relations_current")
            connection.execute("DROP TABLE fields_current")
            connection.execute("CREATE INDEX docs_page_relations_target ON docs_page_relations(workspace_id, target_page_id)")

    Database(target)
    saved = owner.get(project_url).json()["fields"]
    assert next(field for field in saved if field["id"] == aggregate["id"])["aggregation"] == aggregate["aggregation"]
    assert owner.get(base + f"/pages/{project['id']}").json()["properties"][aggregate["id"]] == 6


def test_formula_calculation_validation_dependencies_and_views(workspace_people):
    app, (owner, reader, outsider), _ = workspace_people
    space, base, projects, project_url = make_collection(owner, "formules")
    resources = created(owner.post(base + "/collections", json={"title": "Ressources"}))
    resources_url = base + "/collections/" + resources["id"]
    hours = field(owner, resources_url, "Heures", "number")
    links = relation(owner, base, projects, resources)
    project = entry(owner, base, projects, "Atelier")
    resource = entry(owner, base, resources, "Ressource")
    assert set_value(owner, base, resource, hours, 6).status_code == 200
    assert owner.patch(base + f"/pages/{project['id']}/relations/{links['id']}", json={"add": [resource["id"]]}).status_code == 200
    aggregate = created(owner.post(project_url + "/fields", json={
        "name": "Total lié", "kind": "aggregate",
        "aggregation": {"relationFieldId": links["id"], "operation": "sum", "sourceFieldId": hours["id"]},
    }))
    local_hours = field(owner, project_url, "Heures locales", "number")
    collection_url = project_url

    def create_formula(name, expression):
        return created(owner.post(collection_url + "/fields", json={
            "name": name, "kind": "formula", "formula": {"expression": expression},
        }))

    first = create_formula("Double", "2 * {" + aggregate["id"] + "}")
    second = create_formula("Composé", "({"+first["id"]+"} + 4) / 2")
    empty_formula = create_formula("Référence vide", "{" + local_hours["id"] + "} + 1")
    assert owner.post(collection_url + "/fields", json={
        "name": "Texte invalide", "kind": "formula", "formula": {"expression": "{"+hours["id"]+"}"},
    }).status_code == 422
    assert owner.post(collection_url + "/fields", json={
        "name": "Expression invalide", "kind": "formula", "formula": {"expression": "__import__('os')"},
    }).status_code == 422
    assert owner.patch(base + f"/pages/{project['id']}/properties/{first['id']}", json={"value": 10}).status_code == 422
    page_url = base + f"/pages/{project['id']}"
    assert owner.get(page_url).json()["properties"][first["id"]] == 12
    assert owner.get(page_url).json()["properties"][second["id"]] == 8
    assert owner.get(page_url).json()["properties"][empty_formula["id"]] is None
    assert owner.patch(base + f"/pages/{resource['id']}/properties/{hours['id']}", json={"value": 10}).status_code == 200
    assert owner.get(page_url).json()["properties"][first["id"]] == 20
    assert owner.get(page_url).json()["properties"][second["id"]] == 12
    assert set_value(owner, base, resource, hours, 6).status_code == 200
    fields_url = collection_url + "/fields"
    changed = owner.patch(fields_url + "/" + first["id"], json={
        "name": "Double renommé", "options": [], "previousOptions": [],
        "formula": {"expression": "2 + {" + aggregate["id"] + "}"},
    })
    assert changed.status_code == 200
    assert owner.get(page_url).json()["properties"][first["id"]] == 8
    assert owner.get(page_url).json()["properties"][second["id"]] == 6

    cycle = owner.patch(fields_url + "/" + first["id"], json={
        "name": "Double renommé", "options": [], "previousOptions": [],
        "formula": {"expression": "{" + second["id"] + "} + 1"},
    })
    assert cycle.status_code == 422 and "cycle" in cycle.json()["error"].lower()
    assert owner.get(page_url).json()["properties"][first["id"]] == 8
    division = create_formula("Division", "1 / 0")
    assert owner.get(page_url).json()["properties"][division["id"]] == {"error": "division_by_zero"}
    upstream_error = create_formula("Erreur transmise", "{" + division["id"] + "} * -2")
    assert owner.get(page_url).json()["properties"][upstream_error["id"]] == {"error": "division_by_zero"}
    assert create_formula("Priorité", "2 + 3 * 4")["formula"]["dependencies"] == []
    assert create_formula("Parenthèses", "(2 + 3) * 4")["formula"]["dependencies"] == []
    assert create_formula("Opérateurs français", "2 × 3 − 1 ÷ 1")["formula"]["dependencies"] == []
    assert owner.get(page_url).json()["properties"][
        next(item["id"] for item in owner.get(collection_url).json()["fields"] if item["name"] == "Opérateurs français")
    ] == 5
    empty = create_formula("Vide", "{" + aggregate["id"] + "} + 1")
    assert owner.patch(base + f"/pages/{project['id']}/relations/{links['id']}", json={"remove": [resource["id"]]}).status_code == 200
    values = owner.get(page_url).json()["properties"]
    assert values[first["id"]] is None and values[second["id"]] is None and values[empty["id"]] is None

    saved = created(owner.post(collection_url + "/views", json={
        "name": "Formules renseignées", "layout": "table",
        "filterTree": {"mode": "all", "conditions": [condition(second, "filled")]},
        "sorts": [{"fieldId": second["id"], "direction": "desc"}],
    }))
    assert saved["name"] == "Formules renseignées"
    with ZipFile(BytesIO(owner.get(base + "/export").content)) as archive:
        manifest = loads(archive.read("collections.json"))
    path, = [key for key in manifest["pages"] if project["id"][:8] in key]
    assert manifest["pages"][path]["values"][second["id"]] is None
    assert manifest["pages"][path]["values"][division["id"]] == {"error": "division_by_zero"}
    assert owner.patch(base + f"/access/{join(owner, reader, space, 'bob@epita.fr')}", json={"role": "reader"}).status_code == 204
    assert reader.get(page_url).json()["properties"][first["id"]] is None
