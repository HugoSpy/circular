ALTER TABLE labels ADD COLUMN description TEXT NOT NULL DEFAULT '';
ALTER TABLE projects ADD COLUMN status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('backlog','planned','in_progress','completed','canceled'));
ALTER TABLE projects ADD COLUMN due_date TEXT;
ALTER TABLE issues ADD COLUMN due_date TEXT;
ALTER TABLE issues ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0 CHECK (is_favorite IN (0,1));

CREATE TABLE workspace_settings (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  payload TEXT NOT NULL
);
CREATE TABLE saved_views (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  filters TEXT NOT NULL,
  display TEXT NOT NULL
);
CREATE TABLE issue_templates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  status TEXT NOT NULL CHECK (status IN ('backlog','todo','in_progress','in_review','done')),
  priority TEXT NOT NULL CHECK (priority IN ('none','low','medium','high','urgent'))
);
CREATE TABLE template_labels (
  template_id INTEGER NOT NULL REFERENCES issue_templates(id) ON DELETE CASCADE,
  label_id INTEGER NOT NULL REFERENCES labels(id) ON DELETE CASCADE,
  PRIMARY KEY (template_id, label_id)
);
CREATE TABLE issue_activity (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  issue_id INTEGER NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  body TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX issue_activity_issue ON issue_activity(issue_id, id);
CREATE INDEX issue_labels_label ON issue_labels(label_id, issue_id);
CREATE INDEX issues_favorites ON issues(is_favorite);
