ALTER TABLE issues ADD COLUMN assignee_id BIGINT REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE issues ADD COLUMN estimate INTEGER CHECK (estimate BETWEEN 0 AND 1000);
ALTER TABLE issues ADD COLUMN archived_at TEXT;

CREATE TABLE issue_relations (
    issue_id BIGINT NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    target_id BIGINT NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('parent','blocks','related','duplicate')),
    CHECK (issue_id <> target_id),
    PRIMARY KEY (issue_id, target_id, kind)
);
CREATE UNIQUE INDEX issue_relations_parent ON issue_relations(issue_id, kind) WHERE kind IN ('parent','duplicate');
CREATE INDEX issue_relations_target ON issue_relations(target_id, kind);
