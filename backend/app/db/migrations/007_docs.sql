CREATE TABLE docs_collections (
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    PRIMARY KEY (workspace_id, id)
);
CREATE TABLE docs_fields (
    workspace_id INTEGER NOT NULL,
    collection_id TEXT NOT NULL,
    id TEXT NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('text', 'number', 'date', 'select', 'checkbox')),
    options TEXT NOT NULL,
    position INTEGER NOT NULL,
    PRIMARY KEY (workspace_id, collection_id, id),
    FOREIGN KEY (workspace_id, collection_id) REFERENCES docs_collections(workspace_id, id) ON DELETE CASCADE
);
CREATE TABLE docs_views (
    workspace_id INTEGER NOT NULL,
    collection_id TEXT NOT NULL,
    id TEXT NOT NULL,
    name TEXT NOT NULL,
    configuration TEXT NOT NULL,
    position INTEGER NOT NULL,
    PRIMARY KEY (workspace_id, collection_id, id),
    FOREIGN KEY (workspace_id, collection_id) REFERENCES docs_collections(workspace_id, id) ON DELETE CASCADE
);
CREATE TABLE docs_pages (
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    id TEXT NOT NULL,
    parent_id TEXT,
    collection_id TEXT,
    title TEXT NOT NULL,
    markdown TEXT NOT NULL DEFAULT '',
    search_text TEXT NOT NULL DEFAULT '',
    revision INTEGER NOT NULL DEFAULT 1,
    properties TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (workspace_id, id),
    FOREIGN KEY (workspace_id, parent_id) REFERENCES docs_pages(workspace_id, id) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (workspace_id, collection_id) REFERENCES docs_collections(workspace_id, id),
    CHECK (id <> parent_id)
);
CREATE INDEX docs_pages_parent ON docs_pages(workspace_id, parent_id);
CREATE INDEX docs_pages_collection ON docs_pages(workspace_id, collection_id);
CREATE TABLE docs_links (
    workspace_id INTEGER NOT NULL,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    PRIMARY KEY (workspace_id, source_id, target_id),
    FOREIGN KEY (workspace_id, source_id) REFERENCES docs_pages(workspace_id, id) ON DELETE CASCADE,
    FOREIGN KEY (workspace_id, target_id) REFERENCES docs_pages(workspace_id, id) ON DELETE CASCADE
);
CREATE INDEX docs_links_backlinks ON docs_links(workspace_id, target_id);
