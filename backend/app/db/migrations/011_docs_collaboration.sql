ALTER TABLE workspace_members ADD COLUMN docs_role TEXT NOT NULL DEFAULT 'editor' CHECK (docs_role IN ('editor', 'reader'));

CREATE TABLE docs_comments (
    workspace_id INTEGER NOT NULL,
    id TEXT NOT NULL,
    page_id TEXT NOT NULL,
    author_id INTEGER NOT NULL REFERENCES users(id),
    body TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, id),
    FOREIGN KEY (workspace_id, page_id) REFERENCES docs_pages(workspace_id, id) ON DELETE CASCADE
);
CREATE INDEX docs_comments_page ON docs_comments(workspace_id, page_id, created_at, id);

CREATE TABLE docs_mentions (
    workspace_id INTEGER NOT NULL,
    comment_id TEXT NOT NULL,
    recipient_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    read_at TEXT,
    PRIMARY KEY (workspace_id, comment_id, recipient_id),
    FOREIGN KEY (workspace_id, comment_id) REFERENCES docs_comments(workspace_id, id) ON DELETE CASCADE,
    FOREIGN KEY (workspace_id, recipient_id) REFERENCES workspace_members(workspace_id, user_id) ON DELETE CASCADE
);
CREATE INDEX docs_mentions_recipient ON docs_mentions(workspace_id, recipient_id, created_at);
