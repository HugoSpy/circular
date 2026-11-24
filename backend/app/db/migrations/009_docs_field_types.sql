ALTER TABLE docs_fields RENAME TO docs_fields_legacy;
CREATE TABLE docs_fields (
    workspace_id INTEGER NOT NULL,
    collection_id TEXT NOT NULL,
    id TEXT NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('text', 'number', 'date', 'select', 'checkbox', 'url', 'multi')),
    options TEXT NOT NULL,
    position INTEGER NOT NULL,
    PRIMARY KEY (workspace_id, collection_id, id),
    FOREIGN KEY (workspace_id, collection_id) REFERENCES docs_collections(workspace_id, id) ON DELETE CASCADE
);
INSERT INTO docs_fields (workspace_id, collection_id, id, name, kind, options, position)
    SELECT workspace_id, collection_id, id, name, kind, options, position FROM docs_fields_legacy;
DROP TABLE docs_fields_legacy;
