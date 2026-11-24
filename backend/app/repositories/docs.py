"""SQL for the documents of one already-authorized workspace."""
from collections import defaultdict
from fractions import Fraction
import json
import re

from markdown_it import MarkdownIt

from backend.app.db.session import timestamp
from backend.app.services.docs_formulas import evaluate_formula, parse_formula

MARKDOWN = MarkdownIt("commonmark").enable(["table", "strikethrough"])
ACTIVE_PAGE = """NOT EXISTS (
    SELECT 1 FROM docs_trashed_pages t WHERE t.workspace_id = p.workspace_id AND t.page_id = p.id
)"""
VIEW_REFERENCE = re.compile(r"/collections/([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})/views/([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})", re.IGNORECASE)
INTERNAL = re.compile(r"/pages/([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})", re.IGNORECASE)


ATTACHMENT = re.compile(r"/attachments/([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})", re.IGNORECASE)


def first_markdown_image(markdown):
    """Return the first local Circular attachment referenced by an image token."""
    for block in MARKDOWN.parse(markdown):
        pending = list(block.children or ())
        while pending:
            token = pending.pop(0)
            if token.type == "image":
                match = ATTACHMENT.fullmatch(token.attrGet("src") or "")
                if match:
                    alt = "".join(child.content if child.type in {"text", "code_inline", "html_inline"}
                                  else child.content if child.type == "image" else " "
                                  if child.type in {"softbreak", "hardbreak"} else ""
                                  for child in (token.children or ()))
                    return match[1].lower(), alt
                # Markdown inside the alt text of an external image is not a
                # separately rendered preview candidate.
                continue
            pending[0:0] = token.children or ()
    return None


def attachment_targets(markdown):
    targets = set()
    for block in MARKDOWN.parse(markdown):
        for token in block.children or ():
            match = ATTACHMENT.fullmatch(token.attrGet("href") or token.attrGet("src") or "")
            if match:
                targets.add(match[1].lower())
    return targets


def view_references(markdown):
    return {
        (match[1].lower(), match[2].lower())
        for block in MARKDOWN.parse(markdown)
        for token in block.children or ()
        if token.type == "link_open" and (match := VIEW_REFERENCE.fullmatch(token.attrGet("href") or ""))
    }


def parse_markdown(markdown: str) -> tuple[str, set[str]]:
    text = []
    targets = set()
    for block in MARKDOWN.parse(markdown):
        if block.type in {"fence", "code_block"}:
            text.append(block.content)
        if block.type != "inline":
            continue
        inline = []
        for token in block.children or ():
            if token.type == "link_open":
                match = INTERNAL.fullmatch(token.attrGet("href") or "")
                if match:
                    targets.add(match[1].lower())
            elif token.type in {"text", "code_inline"}:
                inline.append(token.content)
            elif token.type in {"softbreak", "hardbreak"}:
                inline.append(" ")
        text.append("".join(inline))
    return " ".join(" ".join(text).split()), targets


def aggregate_value(config, targets, properties):
    if config["operation"] == "count":
        return len(targets)
    source = config["sourceFieldId"]
    values = [value for target in targets if (value := properties[target].get(source)) is not None]
    if not values:
        return None
    # Round only after checking the range, including a fractional excess at the limit.
    result = sum(map(Fraction, values))
    if config["operation"] == "average":
        result /= len(values)
    if abs(result) > 9_007_199_254_740_991:
        return {"error": "out_of_range"}
    return int(result) if result.denominator == 1 else float(result)


def page_summary(record, properties):
    return {
        "id": record["id"], "parentId": record["parent_id"], "collectionId": record["collection_id"],
        "title": record["title"], "properties": properties,
    }


def view_record(record):
    return {"id": record["id"], "name": record["name"], **json.loads(record["configuration"])}


class DocsRepository:
    def __init__(self, connection, workspace_id: int, access: str):
        self.connection = connection
        self.workspace_id = workspace_id
        self.access = access

    def execute(self, sql, *values):
        return self.connection.execute(sql, (self.workspace_id, *values))

    def template(self, template_id):
        return self.execute("""
            SELECT * FROM docs_templates WHERE workspace_id = ? AND id = ? AND archived = 0
        """, template_id).fetchone()

    def asset(self, asset_id, *, active_only=False, metadata_only=False):
        condition = f"""AND EXISTS (
            SELECT 1 FROM docs_pages p
            WHERE p.workspace_id = a.workspace_id AND {ACTIVE_PAGE}
              AND (p.id = a.page_id OR EXISTS (
                SELECT 1 FROM docs_asset_links l WHERE l.workspace_id = p.workspace_id
                AND l.page_id = p.id AND l.asset_id = a.id
              ))
        )""" if active_only else ""
        columns = "a.id" if metadata_only else "a.*"
        return self.execute(f"SELECT {columns} FROM docs_assets a WHERE a.workspace_id = ? AND a.id = ? {condition}",
                            asset_id).fetchone()

    def asset_ids(self, ids, *, active_only=False):
        return {asset_id for asset_id in ids if self.asset(asset_id, active_only=active_only, metadata_only=True)}

    def replace_assets(self, page_id, targets):
        existing = self.asset_ids(targets)
        self.execute("DELETE FROM docs_asset_links WHERE workspace_id = ? AND page_id = ?", page_id)
        self.connection.executemany(
            "INSERT INTO docs_asset_links (workspace_id, page_id, asset_id) VALUES (?, ?, ?)",
            [(self.workspace_id, page_id, asset_id) for asset_id in sorted(existing)],
        )

    def page(self, page_id, *, include_trashed=False):
        active = "" if include_trashed else f" AND {ACTIVE_PAGE}"
        return self.execute(f"SELECT p.* FROM docs_pages p WHERE p.workspace_id = ? AND p.id = ?{active}", page_id).fetchone()

    def summaries(self):
        rows = self.execute(f"""
            SELECT p.id, p.parent_id, p.collection_id, p.title, p.properties FROM docs_pages p
            WHERE p.workspace_id = ? AND {ACTIVE_PAGE}
        """).fetchall()
        properties = self.projected_properties(rows)
        return sorted((page_summary(row, properties[row["id"]]) for row in rows),
                      key=lambda page: (page["title"].casefold(), page["id"]))

    def summary(self, row):
        return page_summary(row, self.projected_properties([row], single=True)[row["id"]])

    def projected_properties(self, rows, *, single=False):
        definitions = defaultdict(dict)
        if not single or rows[0]["collection_id"]:
            condition = "AND collection_id = ?" if single else ""
            params = (rows[0]["collection_id"],) if single else ()
            for field in self.execute(f"""
                SELECT collection_id, id, kind, aggregation, formula FROM docs_fields
                WHERE workspace_id = ? AND kind IN ('aggregate', 'formula') {condition}
            """, *params):
                definition = field["aggregation"] if field["kind"] == "aggregate" else field["formula"]
                definitions[field["collection_id"]][field["id"]] = {
                    "kind": field["kind"], "config": json.loads(definition),
                }
        properties = {row["id"]: json.loads(row["properties"]) for row in rows}
        target_properties = {} if single and definitions else None
        relations = self.visible_relations(rows[0]["id"] if single else None, target_properties=target_properties)
        targets = properties if target_properties is None else target_properties
        formulas = {}
        for collection_id, collection_fields in definitions.items():
            pending = {field: definition["config"] for field, definition in collection_fields.items()
                       if definition["kind"] == "formula"}
            ordered = {}
            while pending:
                progressed = False
                for field, config in list(pending.items()):
                    if all(dependency not in pending for dependency in config["dependencies"]):
                        ordered[field] = parse_formula(config["expression"])[0]
                        del pending[field]
                        progressed = True
                if not progressed:
                    break
            formulas[collection_id] = ordered
        result = {}
        for row in rows:
            page_id = row["id"]
            linked = relations.get(page_id, {})
            values = {**properties[page_id], **linked}
            calculated = definitions.get(row["collection_id"], {})
            for field, definition in calculated.items():
                if definition["kind"] == "aggregate":
                    config = definition["config"]
                    values[field] = aggregate_value(config, linked.get(config["relationFieldId"], ()), targets)
            for field, tree in formulas.get(row["collection_id"], {}).items():
                values[field] = evaluate_formula(tree, values)
            result[page_id] = values
        return result

    def visible_relations(self, source_id=None, *, target_properties=None):
        source_filter = " AND r.source_page_id = ?" if source_id else ""
        params = (source_id,) if source_id else ()
        target_column = ", p.properties" if target_properties is not None else ""
        by_page = defaultdict(lambda: defaultdict(list))
        for row in self.execute(f"""
            SELECT r.source_page_id, r.field_id, r.target_page_id {target_column}
            FROM docs_page_relations r
            JOIN docs_pages p ON p.workspace_id = r.workspace_id AND p.id = r.target_page_id
            JOIN docs_pages s ON s.workspace_id = r.workspace_id AND s.id = r.source_page_id
                AND s.collection_id = r.source_collection_id
            JOIN docs_fields f ON f.workspace_id = r.workspace_id
                AND f.collection_id = r.source_collection_id AND f.id = r.field_id
                AND f.target_collection_id = p.collection_id
            WHERE r.workspace_id = ? AND {ACTIVE_PAGE}{source_filter}
            ORDER BY r.source_page_id, r.field_id, r.target_page_id
        """, *params):
            by_page[row["source_page_id"]][row["field_id"]].append(row["target_page_id"])
            if target_properties is not None and row["target_page_id"] not in target_properties:
                target_properties[row["target_page_id"]] = json.loads(row["properties"])
        return by_page

    def relation_targets(self, page_id, field_id):
        return {row["target_page_id"] for row in self.execute("""
            SELECT target_page_id FROM docs_page_relations
            WHERE workspace_id = ? AND source_page_id = ? AND field_id = ?
        """, page_id, field_id)}

    def change_relations(self, page_id, collection_id, field_id, add, remove=()):
        self.connection.executemany("""
            DELETE FROM docs_page_relations
            WHERE workspace_id = ? AND source_page_id = ? AND field_id = ? AND target_page_id = ?
        """, [(self.workspace_id, page_id, field_id, target) for target in remove])
        self.connection.executemany("""
            INSERT INTO docs_page_relations (workspace_id, source_page_id, source_collection_id, field_id, target_page_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (workspace_id, source_page_id, field_id, target_page_id) DO NOTHING
        """, [(self.workspace_id, page_id, collection_id, field_id, target) for target in add])

    def search_rows(self):
        return self.execute(f"""
            SELECT p.id, p.title, p.search_text FROM docs_pages p WHERE p.workspace_id = ? AND {ACTIVE_PAGE}
        """)

    def page_detail(self, row):
        backlinks = self.execute(f"""
            SELECT l.source_id FROM docs_links l
            JOIN docs_pages p ON p.workspace_id = l.workspace_id AND p.id = l.source_id
            WHERE l.workspace_id = ? AND l.target_id = ? AND {ACTIVE_PAGE}
            ORDER BY l.source_id
        """, row["id"])
        return {
            **self.summary(row), "markdown": row["markdown"], "revision": row["revision"],
            "backlinks": [link["source_id"] for link in backlinks],
        }

    def create_page(self, page_id, parent, collection, title, *, markdown="", searchable="", properties="{}"):
        self.execute("""
            INSERT INTO docs_pages (workspace_id, id, parent_id, collection_id, title, markdown, search_text, properties)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, page_id, parent, collection, title, markdown, searchable, properties)

    def update_content(self, page_id, title, markdown, searchable):
        self.connection.execute("""
            UPDATE docs_pages SET title = ?, markdown = ?, search_text = ?, revision = revision + 1
            WHERE workspace_id = ? AND id = ?
        """, (title, markdown, searchable, self.workspace_id, page_id))

    def link_targets(self, page_id):
        return {row["target_id"] for row in self.execute(
            "SELECT target_id FROM docs_links WHERE workspace_id = ? AND source_id = ?", page_id,
        )}

    def replace_links(self, page_id, targets):
        self.execute("DELETE FROM docs_links WHERE workspace_id = ? AND source_id = ?", page_id)
        self.connection.executemany(
            "INSERT INTO docs_links (workspace_id, source_id, target_id) VALUES (?, ?, ?)",
            [(self.workspace_id, page_id, target) for target in sorted(targets)],
        )

    def record_revision(self, page, author):
        self.execute("""
            INSERT INTO docs_revisions (workspace_id, page_id, revision, title, markdown, author_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, page["id"], page["revision"], page["title"], page["markdown"], author, timestamp())

    def revisions(self, page_id, before, limit):
        cursor = "" if before is None else " AND r.revision < ?"
        params = (page_id, limit) if before is None else (page_id, before, limit)
        rows = self.execute(f"""
            SELECT r.revision, r.title, r.created_at AS createdAt, COALESCE(NULLIF(u.display_name, ''), u.username) AS author
            FROM docs_revisions r LEFT JOIN users u ON r.author_id = u.id
            WHERE r.workspace_id = ? AND r.page_id = ?{cursor} ORDER BY r.revision DESC LIMIT ?
        """, *params)
        return [dict(row) for row in rows]

    def revision(self, page_id, revision):
        return self.execute("""
            SELECT r.revision, r.title, r.markdown, r.created_at AS createdAt, COALESCE(NULLIF(u.display_name, ''), u.username) AS author
            FROM docs_revisions r LEFT JOIN users u ON r.author_id = u.id
            WHERE r.workspace_id = ? AND r.page_id = ? AND r.revision = ?
        """, page_id, revision).fetchone()

    def trash_branch(self, root, operation):
        self.execute("""
            INSERT INTO docs_trash (workspace_id, id, root_id, original_parent_id, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, operation, root["id"], root["parent_id"], timestamp())
        self.connection.execute(f"""
            WITH RECURSIVE branch(id) AS (
                SELECT id FROM docs_pages WHERE workspace_id = ? AND id = ?
                UNION ALL
                SELECT p.id FROM docs_pages p JOIN branch ON p.parent_id = branch.id
                WHERE p.workspace_id = ? AND {ACTIVE_PAGE}
            )
            INSERT INTO docs_trashed_pages (workspace_id, page_id, operation_id)
            SELECT ?, id, ? FROM branch
        """, (self.workspace_id, root["id"], self.workspace_id, self.workspace_id, operation))
        return self.trash_count(operation)

    def trash_count(self, operation):
        return self.execute("SELECT COUNT(*) FROM docs_trashed_pages WHERE workspace_id = ? AND operation_id = ?", operation).fetchone()[0]

    def trash_entry(self, operation):
        return self.execute("SELECT * FROM docs_trash WHERE workspace_id = ? AND id = ?", operation).fetchone()

    def trash_for_root(self, page_id):
        return self.execute("SELECT id FROM docs_trash WHERE workspace_id = ? AND root_id = ?", page_id).fetchone()

    def trash_entries(self):
        rows = self.execute("""
            SELECT t.id, t.root_id AS rootId, root.title, t.original_parent_id AS parentId, parent.title AS parentTitle,
                   t.created_at AS trashedAt, hidden.page_id IS NULL AND parent.id IS NOT NULL AS parentAvailable,
                   (SELECT COUNT(*) FROM docs_trashed_pages m WHERE m.workspace_id = t.workspace_id AND m.operation_id = t.id) AS count
            FROM docs_trash t
            JOIN docs_pages root ON root.workspace_id = t.workspace_id AND root.id = t.root_id
            LEFT JOIN docs_pages parent ON parent.workspace_id = t.workspace_id AND parent.id = t.original_parent_id
            LEFT JOIN docs_trashed_pages hidden ON hidden.workspace_id = parent.workspace_id AND hidden.page_id = parent.id
            WHERE t.workspace_id = ? ORDER BY t.created_at DESC, t.id
        """)
        return [{**dict(row), "parentAvailable": bool(row["parentAvailable"])} for row in rows]

    def restore_branch(self, entry, parent):
        self.connection.execute("UPDATE docs_pages SET parent_id = ? WHERE workspace_id = ? AND id = ?",
                                (parent, self.workspace_id, entry["root_id"]))
        self.execute("DELETE FROM docs_trash WHERE workspace_id = ? AND id = ?", entry["id"])

    def collection(self, collection_id):
        return self.execute("""
            SELECT id, title, description FROM docs_collections WHERE workspace_id = ? AND id = ?
        """, collection_id).fetchone()

    def gallery_previews(self, collection_id, page_ids):
        """Project first image refs for a bounded set of active pages in one collection."""
        if not page_ids:
            return {}
        placeholders = ",".join("?" for _ in page_ids)
        rows = self.execute(f"""
            SELECT p.id, p.markdown FROM docs_pages p
            WHERE p.workspace_id = ? AND p.collection_id = ? AND p.id IN ({placeholders}) AND {ACTIVE_PAGE}
        """, collection_id, *page_ids).fetchall()
        candidates = {row["id"]: first_markdown_image(row["markdown"]) for row in rows}
        candidates = {page_id: value for page_id, value in candidates.items() if value is not None}
        if not candidates:
            return {}

        # The one eligibility query is scoped to these requested active pages. The
        # attachment endpoint remains responsible for access checks on the bytes.
        page_ids = list(candidates)
        asset_ids = list({asset_id for asset_id, _alt in candidates.values()})
        page_placeholders = ",".join("?" for _ in page_ids)
        asset_placeholders = ",".join("?" for _ in asset_ids)
        eligible = {(row["pageId"], row["assetId"]) for row in self.execute(f"""
            SELECT p.id AS pageId, a.id AS assetId FROM docs_pages p
            JOIN docs_assets a ON a.workspace_id = p.workspace_id AND a.media_type LIKE 'image/%' AND (
                a.page_id = p.id OR EXISTS (
                    SELECT 1 FROM docs_asset_links l WHERE l.workspace_id = p.workspace_id
                    AND l.page_id = p.id AND l.asset_id = a.id
                )
            )
            WHERE p.workspace_id = ? AND p.collection_id = ? AND p.id IN ({page_placeholders})
              AND a.id IN ({asset_placeholders}) AND {ACTIVE_PAGE}
        """, collection_id, *page_ids, *asset_ids)}
        return {
            page_id: ({"status": "available", "assetId": asset_id, "alt": alt}
                      if (page_id, asset_id) in eligible else {"status": "unavailable", "alt": alt})
            for page_id, (asset_id, alt) in candidates.items()
        }

    def collections(self):
        return [dict(row) for row in self.execute("""
            SELECT id, title, description FROM docs_collections WHERE workspace_id = ? ORDER BY title, id
        """)]

    def fields(self, collection_id):
        rows = self.execute("""
            SELECT id, name, kind, options, target_collection_id AS targetCollectionId, aggregation, formula FROM docs_fields
            WHERE workspace_id = ? AND collection_id = ? ORDER BY position, id
        """, collection_id)
        fields = []
        for row in rows:
            field = dict(row)
            field["options"] = json.loads(field["options"])
            if field["targetCollectionId"] is None:
                del field["targetCollectionId"]
            aggregation = field.pop("aggregation")
            if aggregation is not None:
                field["aggregation"] = json.loads(aggregation)
            formula = field.pop("formula")
            if formula is not None:
                field["formula"] = json.loads(formula)
            fields.append(field)
        return fields

    def update_field(self, collection_id, field_id, name, options):
        self.connection.execute("""
            UPDATE docs_fields SET name = ?, options = ? WHERE workspace_id = ? AND collection_id = ? AND id = ?
        """, (name, json.dumps(options), self.workspace_id, collection_id, field_id))

    def update_formula(self, collection_id, field_id, config):
        self.connection.execute("""
            UPDATE docs_fields SET formula = ? WHERE workspace_id = ? AND collection_id = ? AND id = ?
        """, (json.dumps(config), self.workspace_id, collection_id, field_id))

    def order_fields(self, collection_id, field_ids):
        self.connection.executemany("""
            UPDATE docs_fields SET position = ? WHERE workspace_id = ? AND collection_id = ? AND id = ?
        """, [(index, self.workspace_id, collection_id, field_id) for index, field_id in enumerate(field_ids)])

    def update_properties(self, page_id, properties):
        self.connection.execute("""
            UPDATE docs_pages SET properties = ? WHERE workspace_id = ? AND id = ?
        """, (json.dumps(properties), self.workspace_id, page_id))

    def rename_property_options(self, collection_id, field_id, renames):
        rows = self.execute("""
            SELECT id, properties FROM docs_pages WHERE workspace_id = ? AND collection_id = ?
        """, collection_id).fetchall()
        for row in rows:
            properties = json.loads(row["properties"])
            value = properties.get(field_id)
            if isinstance(value, str):
                replacement = renames.get(value, value)
            elif isinstance(value, list):
                replacement = [renames.get(option, option) for option in value]
            else:
                continue
            if replacement != value:
                properties[field_id] = replacement
                self.update_properties(row["id"], properties)

    def update_view(self, collection_id, view_id, name, configuration):
        self.connection.execute("""
            UPDATE docs_views SET name = ?, configuration = ?
            WHERE workspace_id = ? AND collection_id = ? AND id = ?
        """, (name, json.dumps(configuration), self.workspace_id, collection_id, view_id))

    def has_view(self, collection_id, view_id):
        return self.execute("""
            SELECT 1 FROM docs_views WHERE workspace_id = ? AND collection_id = ? AND id = ?
        """, collection_id, view_id).fetchone() is not None

    def views(self, collection_id):
        return list(map(view_record, self.execute("""
            SELECT id, name, configuration FROM docs_views
            WHERE workspace_id = ? AND collection_id = ? ORDER BY position, id
        """, collection_id)))

    def export_pages(self):
        rows = self.execute(f"""
            SELECT p.id, p.parent_id, p.collection_id, p.title, p.markdown, p.properties
            FROM docs_pages p WHERE p.workspace_id = ? AND {ACTIVE_PAGE} ORDER BY p.id
        """).fetchall()
        properties = self.projected_properties(rows)
        return [{**dict(row), "properties": properties[row["id"]]} for row in rows]
