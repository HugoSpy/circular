CREATE TABLE issue_shares (
    workspace_id BIGINT NOT NULL,
    issue_id BIGINT NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    granted_by BIGINT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    PRIMARY KEY (issue_id, user_id),
    FOREIGN KEY (workspace_id, user_id) REFERENCES workspace_members(workspace_id, user_id) ON DELETE CASCADE
);
CREATE INDEX issue_shares_recipient ON issue_shares(workspace_id, user_id, issue_id);
