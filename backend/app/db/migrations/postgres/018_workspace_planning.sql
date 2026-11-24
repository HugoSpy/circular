CREATE TABLE workspace_records (
    id TEXT PRIMARY KEY,
    workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('initiative','milestone','cycle','update','triage','customer','request','pipeline','release','release_note','review_criterion','pull_link','instruction','learning','friction')),
    project_id BIGINT REFERENCES projects(id) ON DELETE CASCADE,
    ticket_id BIGINT REFERENCES issues(id) ON DELETE SET NULL,
    parent_id TEXT REFERENCES workspace_records(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    state TEXT NOT NULL,
    source_url TEXT,
    starts_on TEXT,
    ends_on TEXT,
    created_by BIGINT NOT NULL REFERENCES users(id),
    updated_by BIGINT NOT NULL REFERENCES users(id),
    updated_at TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    archived_at TEXT
);
CREATE INDEX workspace_records_listing ON workspace_records(workspace_id, kind, archived_at, id);
CREATE INDEX workspace_records_project ON workspace_records(project_id);
CREATE INDEX workspace_records_parent ON workspace_records(parent_id);

CREATE TABLE learning_reactions (
    record_id TEXT NOT NULL REFERENCES workspace_records(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (record_id, user_id)
);
