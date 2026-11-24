"""Workspace authorization and document transactions."""
from contextlib import contextmanager
import json
from uuid import uuid4

from backend.app.repositories.docs import DocsRepository, attachment_targets, parse_markdown, view_references
from backend.app.schemas.docs import CollectionCreate, FieldCreate, FieldEdit, GalleryPreviewRequest, LegacyViewSave, PageFromTemplate, PagePlacement, PageSave, ViewSave
from backend.app.services.docs_assets import SPACE_LIMIT, attachment_type
from backend.app.services.docs_collaboration import DocsCollaboration
from backend.app.services.docs_collections import remap_options, validate_value, validate_view
from backend.app.services.docs_formulas import validate_formula
from backend.app.services.workspace import DomainError


def require(item):
    if item is None:
        raise DomainError(404, "Document introuvable.")
    return item


def template_summary(row):
    return {"id": row["id"], "name": row["name"], "collectionId": row["collection_id"]}


class DocsService(DocsCollaboration):
    def __init__(self, database, workspace_id: int, user_id: int):
        self.database = database
        self.workspace_id = workspace_id
        self.user_id = user_id

    @contextmanager
    def repository(self, *, write=False, permission=None):
        with self.database.connect(write=write) as connection:
            postgres = self.database.dialect == "postgresql"
            if write and postgres:
                # Match space administration's lock order, including member removal.
                connection.execute("SELECT id FROM workspaces WHERE id = ? FOR NO KEY UPDATE", (self.workspace_id,)).fetchone()
            elif not write:
                connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY" if postgres else "BEGIN")
            yield self.repository_on(connection, permission or ("editor" if write else "reader"))

    def repository_on(self, connection, permission):
        member = connection.execute("""
            SELECT role, docs_role FROM workspace_members WHERE workspace_id = ? AND user_id = ?
        """, (self.workspace_id, self.user_id)).fetchone()
        # A guest's membership comes from a project invitation.
        if member is None or member["role"] == "guest":
            raise DomainError(404, "Espace introuvable.")
        access = "owner" if member["role"] == "owner" else member["docs_role"]
        if ((permission == "owner" and access != "owner")
                or (permission == "editor" and access == "reader")):
            raise DomainError(403, "Votre accès Docs ne permet pas cette action.")
        return DocsRepository(connection, self.workspace_id, access)

    def index(self):
        with self.repository() as repo:
            return {"pages": repo.summaries(), "collections": repo.collections(), "access": repo.access}

    def page(self, page_id):
        with self.repository() as repo:
            return repo.page_detail(require(repo.page(page_id)))

    def collection(self, collection_id):
        with self.repository() as repo:
            return {**dict(require(repo.collection(collection_id))),
                    "fields": repo.fields(collection_id), "views": repo.views(collection_id)}

    def gallery_previews(self, collection_id, data: GalleryPreviewRequest):
        with self.repository() as repo:
            require(repo.collection(collection_id))
            return repo.gallery_previews(collection_id, [str(identifier) for identifier in data.pageIds])

    def _placement(self, repo, data, page_id=None):
        parent = str(data.parentId) if data.parentId else None
        collection = str(data.collectionId) if data.collectionId else None
        if collection:
            require(repo.collection(collection))
        visited = {page_id}
        ancestor = parent
        while ancestor:
            if ancestor in visited:
                raise DomainError(409, "Une page ne peut pas être déplacée sous elle-même ou l’un de ses descendants.")
            visited.add(ancestor)
            ancestor = require(repo.page(ancestor))["parent_id"]
        return parent, collection

    def templates(self):
        with self.repository(permission="editor") as repo:
            return [template_summary(row) for row in repo.execute("""
                SELECT id, name, collection_id FROM docs_templates
                WHERE workspace_id = ? AND archived = 0 ORDER BY name, id
            """)]

    def save_template(self, page_id, data):
        with self.repository(write=True) as repo:
            page = require(repo.page(page_id))
            self._check_revision(page, data.revision)
            template_id = str(uuid4())
            repo.execute("""
                INSERT INTO docs_templates (workspace_id, id, collection_id, name, markdown, properties)
                VALUES (?, ?, ?, ?, ?, ?)
            """, template_id, page["collection_id"], data.name, page["markdown"], page["properties"])
            return template_summary(repo.template(template_id))

    def change_template(self, template_id, name=None):
        with self.repository(write=True) as repo:
            original = require(repo.template(template_id))
            repo.connection.execute("""
                UPDATE docs_templates SET name = ?, archived = ?
                WHERE workspace_id = ? AND id = ?
            """, (name if name is not None else original["name"], int(name is None), self.workspace_id, template_id))
            if name is not None:
                return template_summary(repo.template(template_id))

    def create_page(self, data: PageFromTemplate):
        with self.repository(write=True) as repo:
            return self.create_page_in(repo, data)

    def create_page_in(self, repo, data: PageFromTemplate):
        page_id = str(uuid4())
        parent, collection = self._placement(repo, data)
        if data.templateId is None:
            repo.create_page(page_id, parent, collection, data.title)
            return self._append_revision(repo, page_id)
        template = require(repo.template(str(data.templateId)))
        if template["collection_id"] and template["collection_id"] != collection:
            raise DomainError(404, "Modèle introuvable dans cette collection.")
        defaults = json.loads(template["properties"])
        fields = {field["id"]: field for field in repo.fields(collection)} if collection else {}
        values = {}
        skipped = 0
        for field_id, value in defaults.items():
            try:
                validate_value(fields[field_id], value)
                values[field_id] = value
            except (DomainError, KeyError):
                skipped += 1
        markdown = template["markdown"]
        searchable, targets = parse_markdown(markdown)
        repo.create_page(page_id, parent, collection, data.title, markdown=markdown,
                         searchable=searchable.casefold(), properties=json.dumps(values))
        repo.replace_links(page_id, {target for target in targets if repo.page(target, include_trashed=True)})
        repo.replace_assets(page_id, attachment_targets(markdown))
        created = self._append_revision(repo, page_id)
        return {**created, "skippedTemplateProperties": skipped}

    def _append_revision(self, repo, page_id):
        page = repo.page(page_id)
        repo.record_revision(page, self.user_id)
        return repo.page_detail(page)

    @staticmethod
    def _check_revision(current, expected):
        if current["revision"] != expected:
            raise DomainError(409, "Cette page a été modifiée depuis son ouverture.")

    def place_page(self, page_id, data: PagePlacement):
        with self.repository(write=True) as repo:
            return self.place_page_in(repo, page_id, data)

    def place_page_in(self, repo, page_id, data: PagePlacement):
        previous = require(repo.page(page_id))
        if data.revision is not None:
            self._check_revision(previous, data.revision)
        parent, collection = self._placement(repo, data, page_id)
        if previous["collection_id"] and previous["collection_id"] != collection:
            raise DomainError(409, "Cette page appartient déjà à une collection.")
        repo.connection.execute("""
            UPDATE docs_pages SET parent_id = ?, collection_id = ? WHERE workspace_id = ? AND id = ?
        """, (parent, collection, self.workspace_id, page_id))
        if (previous["title"], previous["parent_id"], previous["collection_id"]) != (data.title, parent, collection):
            repo.update_content(page_id, data.title, previous["markdown"], previous["search_text"])
            return self._append_revision(repo, page_id)
        return repo.page_detail(repo.page(page_id))

    def upload_asset(self, page_id, asset_id, name, content, image):
        with self.repository(write=True) as repo:
            return self.upload_asset_in(repo, page_id, asset_id, name, content, image)

    def upload_asset_in(self, repo, page_id, asset_id, name, content, image):
        name, media_type = attachment_type(name, content, image)
        require(repo.page(page_id))
        existing = repo.asset(asset_id)
        if existing:
            if (existing["page_id"], existing["name"], existing["media_type"], bytes(existing["content"])) != (page_id, name, media_type, content):
                raise DomainError(409, "Cette pièce jointe a déjà été enregistrée.")
        else:
            used = repo.execute("""
                SELECT COALESCE(SUM(size_bytes), 0) AS used FROM docs_assets WHERE workspace_id = ?
            """).fetchone()["used"]
            if used + len(content) > SPACE_LIMIT:
                raise DomainError(413, "L’espace a atteint sa limite de 250 Mio de fichiers.")
            repo.execute("""
                INSERT INTO docs_assets (workspace_id, id, page_id, name, media_type, size_bytes, content)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, asset_id, page_id, name, media_type, len(content), content)
        return {"id": asset_id, "name": name}

    def asset(self, asset_id):
        with self.repository() as repo:
            return dict(require(repo.asset(asset_id, active_only=True)))

    def save_page(self, page_id, data: PageSave):
        with self.repository(write=True) as repo:
            return self.save_page_in(repo, page_id, data)

    def save_page_in(self, repo, page_id, data: PageSave):
        current = require(repo.page(page_id))
        if current["markdown"] == data.markdown:
            return repo.page_detail(current)
        self._check_revision(current, data.revision)
        searchable, targets = parse_markdown(data.markdown)
        for target in targets - repo.link_targets(page_id):
            require(repo.page(target))
        assets = attachment_targets(data.markdown)
        added = assets - attachment_targets(current["markdown"])
        if repo.asset_ids(added, active_only=True) != added:
            raise DomainError(404, "Pièce jointe introuvable.")
        for collection_id, view_id in view_references(data.markdown) - view_references(current["markdown"]):
            if not repo.has_view(collection_id, view_id):
                raise DomainError(404, "Vue introuvable.")
        repo.update_content(page_id, current["title"], data.markdown, searchable.casefold())
        repo.replace_assets(page_id, assets)
        repo.replace_links(page_id, targets)
        return self._append_revision(repo, page_id)

    def duplicate_page(self, page_id):
        with self.repository(write=True) as repo:
            source = require(repo.page(page_id))
            copied_id = str(uuid4())
            title = ("Copie de " + source["title"])[:160].rstrip()
            repo.create_page(copied_id, source["parent_id"], source["collection_id"], title,
                             markdown=source["markdown"], searchable=source["search_text"], properties=source["properties"])
            repo.replace_links(copied_id, repo.link_targets(page_id))
            repo.replace_assets(copied_id, attachment_targets(source["markdown"]))
            for field_id, targets in repo.visible_relations(page_id).get(page_id, {}).items():
                repo.change_relations(copied_id, source["collection_id"], field_id, targets)
            return self._append_revision(repo, copied_id)

    def revisions(self, page_id, before, limit):
        with self.repository(permission="editor") as repo:
            require(repo.page(page_id))
            rows = repo.revisions(page_id, before, limit + 1)
            return {"items": rows[:limit], "nextBefore": rows[limit - 1]["revision"] if len(rows) > limit else None}

    def revision(self, page_id, revision):
        with self.repository(permission="editor") as repo:
            require(repo.page(page_id))
            return dict(require(repo.revision(page_id, revision)))

    def restore_revision(self, page_id, revision, expected):
        with self.repository(write=True) as repo:
            current = require(repo.page(page_id))
            source = require(repo.revision(page_id, revision))
            self._check_revision(current, expected)
            if revision == current["revision"]:
                return repo.page_detail(current)
            searchable, targets = parse_markdown(source["markdown"])
            # A historical link may still target a trashed page. Restore the
            # reference so it can resolve when that target is brought back.
            existing = {target for target in targets if repo.page(target, include_trashed=True)}
            repo.update_content(page_id, source["title"], source["markdown"], searchable.casefold())
            repo.replace_links(page_id, existing)
            repo.replace_assets(page_id, attachment_targets(source["markdown"]))
            return self._append_revision(repo, page_id)

    def trash_page(self, page_id, expected):
        with self.repository(write=True) as repo:
            page = repo.page(page_id)
            if page is None:
                entry = require(repo.trash_for_root(page_id))
                return {"id": entry["id"], "count": repo.trash_count(entry["id"])}
            self._check_revision(page, expected)
            operation = str(uuid4())
            return {"id": operation, "count": repo.trash_branch(page, operation)}

    def trash_entries(self):
        with self.repository(permission="editor") as repo:
            return repo.trash_entries()

    def restore_trash(self, operation):
        with self.repository(write=True) as repo:
            entry = require(repo.trash_entry(operation))
            original = entry["original_parent_id"]
            parent = original if original is not None and repo.page(original) else None
            count = repo.trash_count(operation)
            repo.restore_branch(entry, parent)
            return {"page": repo.page_detail(repo.page(entry["root_id"])), "count": count,
                    "parentUnavailable": original is not None and parent is None}

    def create_collection(self, data: CollectionCreate):
        with self.repository(write=True) as repo:
            collection_id = str(uuid4())
            repo.execute("""
                INSERT INTO docs_collections (workspace_id, id, title, description) VALUES (?, ?, ?, ?)
            """, collection_id, data.title, data.description)
            view = self._write_view(repo, collection_id, LegacyViewSave(name="Toutes les pages"), None)
            return {"id": collection_id, **data.model_dump(), "fields": [], "views": [view]}

    def create_field(self, collection_id, data: FieldCreate):
        with self.repository(write=True) as repo:
            require(repo.collection(collection_id))
            fields = repo.fields(collection_id)
            if len(fields) >= 50:
                raise DomainError(422, "Une collection contient au plus 50 propriétés.")
            if any(field["name"].casefold() == data.name.casefold() for field in fields):
                raise DomainError(409, "Une propriété porte déjà ce nom.")
            target = str(data.targetCollectionId) if data.targetCollectionId else None
            if target is not None:
                require(repo.collection(target))
                if target == collection_id:
                    raise DomainError(422, "Choisissez une autre collection.")
            aggregation = None
            formula = None
            if data.aggregation:
                config = data.aggregation.model_dump(mode="json", exclude_none=True)
                relation = next((field for field in fields if field["id"] == config["relationFieldId"]), None)
                if not relation or relation["kind"] != "relation":
                    raise DomainError(422, "Choisissez une propriété Relation de cette collection.")
                if source_id := config.get("sourceFieldId"):
                    sources = repo.fields(relation["targetCollectionId"])
                    if not any(field["id"] == source_id and field["kind"] == "number" for field in sources):
                        raise DomainError(422, "Choisissez une propriété Nombre de la collection liée.")
                aggregation = json.dumps(config)
            if data.formula:
                fields_by_id = {field["id"]: field for field in fields}
                formula = json.dumps(validate_formula(data.formula.expression, fields_by_id))
            identifier = str(uuid4())
            repo.execute("""
                INSERT INTO docs_fields
                    (workspace_id, collection_id, id, name, kind, options, position, target_collection_id, aggregation, formula)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, collection_id, identifier, data.name, data.kind, json.dumps(data.options), len(fields), target, aggregation, formula)
            return {"id": identifier, **data.model_dump(mode="json", exclude_none=True),
                    **({"formula": json.loads(formula)} if formula is not None else {})}

    def edit_field(self, collection_id, field_id, data: FieldEdit):
        with self.repository(write=True) as repo:
            fields = repo.fields(collection_id)
            field = require(next((item for item in fields if item["id"] == field_id), None))
            if data.previousOptions != field["options"]:
                raise DomainError(409, "Les options ont changé. Rechargez les propriétés.")
            if any(item["id"] != field_id and item["name"].casefold() == data.name.casefold() for item in fields):
                raise DomainError(409, "Une propriété porte déjà ce nom.")
            if len(data.options) < len(field["options"]) or (data.options and field["kind"] not in {"select", "multi"}):
                raise DomainError(422, "Conservez une option pour chaque choix existant.")
            formula = None
            if field["kind"] == "formula":
                if data.formula is None:
                    raise DomainError(422, "Saisissez une formule.")
                fields_by_id = {item["id"]: item for item in fields}
                formula = validate_formula(data.formula.expression, fields_by_id, field_id)
                repo.update_formula(collection_id, field_id, formula)
            elif data.formula is not None:
                raise DomainError(422, "Cette propriété n’accepte pas de formule.")
            renames = {old: new for old, new in zip(field["options"], data.options) if old != new}
            if renames:
                repo.rename_property_options(collection_id, field_id, renames)
                for view in repo.views(collection_id):
                    identifier, name = view.pop("id"), view.pop("name")
                    if remap_options(view, field_id, renames):
                        repo.update_view(collection_id, identifier, name, view)
            repo.update_field(collection_id, field_id, data.name, data.options)
            return {**field, "name": data.name, "options": data.options,
                    **({"formula": formula} if formula is not None else {})}

    def order_fields(self, collection_id, field_ids):
        with self.repository(write=True) as repo:
            require(repo.collection(collection_id))
            existing = repo.fields(collection_id)
            if len(field_ids) != len(existing) or set(field_ids) != {item["id"] for item in existing}:
                raise DomainError(409, "Les propriétés ont changé. Rechargez leur ordre.")
            repo.order_fields(collection_id, field_ids)
            return repo.fields(collection_id)

    def update_property(self, page_id, field_id, value):
        with self.repository(write=True) as repo:
            page = require(repo.page(page_id))
            field = require(next((field for field in repo.fields(page["collection_id"]) if field["id"] == field_id), None))
            if field["kind"] == "relation":
                raise DomainError(422, "Utilisez la mise à jour des relations.")
            if field["kind"] in {"aggregate", "formula"}:
                raise DomainError(422, "Une propriété calculée est en lecture seule.")
            validate_value(field, value)
            properties = json.loads(page["properties"])
            if value is None:
                properties.pop(field_id, None)
            else:
                properties[field_id] = value
            repo.update_properties(page_id, properties)
            return repo.summary(repo.page(page_id))

    def update_relations(self, page_id, field_id, data):
        with self.repository(write=True) as repo:
            page = require(repo.page(page_id))
            field = require(next((item for item in repo.fields(page["collection_id"]) if item["id"] == field_id), None))
            if field["kind"] != "relation":
                raise DomainError(422, "Cette propriété ne contient pas de relations.")
            add = {str(target) for target in data.add}
            remove = {str(target) for target in data.remove}
            for target in sorted(add):
                candidate = require(repo.page(target))
                if candidate["collection_id"] != field["targetCollectionId"]:
                    raise DomainError(404, "Document introuvable.")
            current = repo.relation_targets(page_id, field_id)
            if len((current - remove) | add) > 50:
                raise DomainError(422, "Une propriété contient au plus 50 relations, corbeille comprise.")
            repo.change_relations(page_id, page["collection_id"], field_id, sorted(add - current), sorted(remove & current))
            return repo.summary(page)

    def _write_view(self, repo, collection_id, data, view_id):
        configuration = data.model_dump(mode="json", exclude={"name"})
        if "endDateFieldId" not in data.model_fields_set:
            configuration.pop("endDateFieldId", None)
        views = repo.views(collection_id)
        if view_id is not None:
            require(next((item for item in views if item["id"] == view_id), None))
            repo.update_view(collection_id, view_id, data.name, configuration)
        else:
            view_id = str(uuid4())
            position = repo.execute("""
                SELECT COALESCE(MAX(position), -1) + 1 FROM docs_views WHERE workspace_id = ? AND collection_id = ?
            """, collection_id).fetchone()[0]
            repo.execute("""
                INSERT INTO docs_views (workspace_id, collection_id, id, name, configuration, position)
                VALUES (?, ?, ?, ?, ?, ?)
            """, collection_id, view_id, data.name, json.dumps(configuration), position)
        return {"id": view_id, "name": data.name, **configuration}

    def save_view(self, collection_id, data: ViewSave, view_id=None):
        with self.repository(write=True) as repo:
            require(repo.collection(collection_id))
            fields = {field["id"]: field for field in repo.fields(collection_id)}
            validate_view(data, fields)
            return self._write_view(repo, collection_id, data, view_id)

    def delete_view(self, collection_id, view_id):
        with self.repository(write=True) as repo:
            views = repo.views(collection_id)
            require(next((view for view in views if view["id"] == view_id), None))
            if len(views) == 1:
                raise DomainError(409, "Conservez au moins une vue dans la collection.")
            repo.execute("""
                DELETE FROM docs_views WHERE workspace_id = ? AND collection_id = ? AND id = ?
            """, collection_id, view_id)

    def search(self, query):
        term = query.strip().casefold()
        with self.repository() as repo:
            if not term:
                return []
            matches = []
            for row in repo.search_rows():
                title = row["title"].casefold()
                if term in title or term in row["search_text"]:
                    matches.append((term not in title, title, row["id"], row["title"]))
            return [{"id": item[2], "title": item[3]} for item in sorted(matches)[:50]]

    def export(self):
        from backend.app.services.docs_export import build_zip

        with self.repository() as repo:
            pages = repo.export_pages()
            collections = [
                {**item, "fields": repo.fields(item["id"]), "views": repo.views(item["id"])}
                for item in repo.collections()
            ]
            asset_ids = set().union(*(attachment_targets(page["markdown"]) for page in pages))
            return build_zip(pages, collections, (asset for asset_id in sorted(asset_ids)
                                                  if (asset := repo.asset(asset_id)) is not None))
