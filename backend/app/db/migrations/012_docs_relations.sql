ALTER TABLE docs_fields RENAME TO docs_fields_legacy;
CREATE TABLE docs_fields (
    workspace_id INTEGER NOT NULL,
    collection_id TEXT NOT NULL,
    id TEXT NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('text', 'number', 'date', 'select', 'checkbox', 'url', 'multi', 'relation')),
    options TEXT NOT NULL,
    position INTEGER NOT NULL,
    target_collection_id TEXT,
    PRIMARY KEY (workspace_id, collection_id, id),
    FOREIGN KEY (workspace_id, collection_id) REFERENCES docs_collections(workspace_id, id) ON DELETE CASCADE,
    FOREIGN KEY (workspace_id, target_collection_id) REFERENCES docs_collections(workspace_id, id),
    CHECK ((kind = 'relation') = (target_collection_id IS NOT NULL)),
    CHECK (target_collection_id <> collection_id)
);
INSERT INTO docs_fields (workspace_id, collection_id, id, name, kind, options, position)
    SELECT workspace_id, collection_id, id, name, kind, options, position FROM docs_fields_legacy;
DROP TABLE docs_fields_legacy;

CREATE TABLE docs_page_relations (
    workspace_id INTEGER NOT NULL,
    source_page_id TEXT NOT NULL,
    source_collection_id TEXT NOT NULL,
    field_id TEXT NOT NULL,
    target_page_id TEXT NOT NULL,
    PRIMARY KEY (workspace_id, source_page_id, field_id, target_page_id),
    FOREIGN KEY (workspace_id, source_page_id) REFERENCES docs_pages(workspace_id, id) ON DELETE CASCADE,
    FOREIGN KEY (workspace_id, target_page_id) REFERENCES docs_pages(workspace_id, id) ON DELETE CASCADE,
    FOREIGN KEY (workspace_id, source_collection_id, field_id) REFERENCES docs_fields(workspace_id, collection_id, id) ON DELETE CASCADE
);
CREATE INDEX docs_page_relations_target ON docs_page_relations(workspace_id, target_page_id);
