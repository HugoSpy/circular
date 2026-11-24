CREATE TABLE docs_page_shares (
    workspace_id BIGINT NOT NULL,
    page_id TEXT NOT NULL,
    user_id BIGINT NOT NULL,
    granted_by BIGINT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, page_id, user_id),
    FOREIGN KEY (workspace_id, page_id) REFERENCES docs_pages(workspace_id, id) ON DELETE CASCADE,
    FOREIGN KEY (workspace_id, user_id) REFERENCES workspace_members(workspace_id, user_id) ON DELETE CASCADE
);
CREATE INDEX docs_page_shares_recipient ON docs_page_shares(workspace_id, user_id, page_id);
ALTER TABLE docs_mentions ADD COLUMN snoozed_until TEXT;
