CREATE TABLE docs_templates (
    workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    id TEXT NOT NULL,
    collection_id TEXT,
    name TEXT NOT NULL,
    markdown TEXT NOT NULL,
    properties TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workspace_id, id),
    FOREIGN KEY (workspace_id, collection_id) REFERENCES docs_collections(workspace_id, id) ON DELETE CASCADE
);
CREATE TABLE docs_assets (
    workspace_id BIGINT NOT NULL,
    id TEXT NOT NULL,
    page_id TEXT NOT NULL,
    name TEXT NOT NULL,
    media_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    content BYTEA NOT NULL,
    PRIMARY KEY (workspace_id, id),
    FOREIGN KEY (workspace_id, page_id) REFERENCES docs_pages(workspace_id, id) ON DELETE CASCADE
);
CREATE TABLE docs_asset_links (
    workspace_id BIGINT NOT NULL,
    page_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    PRIMARY KEY (workspace_id, page_id, asset_id),
    FOREIGN KEY (workspace_id, page_id) REFERENCES docs_pages(workspace_id, id) ON DELETE CASCADE,
    FOREIGN KEY (workspace_id, asset_id) REFERENCES docs_assets(workspace_id, id) ON DELETE CASCADE
);
CREATE INDEX docs_asset_active_lookup ON docs_asset_links(workspace_id, asset_id);
