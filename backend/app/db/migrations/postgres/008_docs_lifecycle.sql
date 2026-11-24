CREATE TABLE docs_revisions (
    workspace_id BIGINT NOT NULL,
    page_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    title TEXT NOT NULL,
    markdown TEXT NOT NULL,
    author_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT,
    PRIMARY KEY (workspace_id, page_id, revision),
    FOREIGN KEY (workspace_id, page_id) REFERENCES docs_pages(workspace_id, id) ON DELETE CASCADE
);
INSERT INTO docs_revisions (workspace_id, page_id, revision, title, markdown)
    SELECT workspace_id, id, revision, title, markdown FROM docs_pages;

CREATE TABLE docs_trash (
    workspace_id BIGINT NOT NULL,
    id TEXT NOT NULL,
    root_id TEXT NOT NULL,
    original_parent_id TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, id),
    UNIQUE (workspace_id, root_id),
    FOREIGN KEY (workspace_id, root_id) REFERENCES docs_pages(workspace_id, id) ON DELETE CASCADE
);
CREATE TABLE docs_trashed_pages (
    workspace_id BIGINT NOT NULL,
    page_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    PRIMARY KEY (workspace_id, page_id),
    FOREIGN KEY (workspace_id, page_id) REFERENCES docs_pages(workspace_id, id) ON DELETE CASCADE,
    FOREIGN KEY (workspace_id, operation_id) REFERENCES docs_trash(workspace_id, id) ON DELETE CASCADE
);
CREATE INDEX docs_trash_group ON docs_trashed_pages(workspace_id, operation_id);
