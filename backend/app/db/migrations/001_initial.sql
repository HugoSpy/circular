CREATE TABLE project_sequences (
  project_key TEXT PRIMARY KEY,
  last_number INTEGER NOT NULL DEFAULT 0 CHECK (last_number >= 0)
);

CREATE TABLE projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 100),
  key TEXT NOT NULL UNIQUE REFERENCES project_sequences(project_key),
  description TEXT NOT NULL DEFAULT '',
  color TEXT NOT NULL DEFAULT '#71d9b2',
  created_at TEXT NOT NULL
);

CREATE TABLE issues (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  identifier TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 240),
  description TEXT NOT NULL DEFAULT '',
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  status TEXT NOT NULL CHECK (status IN ('backlog','todo','in_progress','in_review','done')),
  priority TEXT NOT NULL CHECK (priority IN ('none','low','medium','high','urgent')),
  search_text TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE labels (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  normalized_name TEXT NOT NULL UNIQUE,
  color TEXT NOT NULL
);

CREATE TABLE issue_labels (
  issue_id INTEGER NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
  label_id INTEGER NOT NULL REFERENCES labels(id) ON DELETE CASCADE,
  PRIMARY KEY (issue_id, label_id)
);

CREATE TABLE comments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  issue_id INTEGER NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
  body TEXT NOT NULL CHECK (length(body) BETWEEN 1 AND 10000),
  created_at TEXT NOT NULL
);

CREATE TABLE seed_runs (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE INDEX issues_project ON issues(project_id);
CREATE INDEX issues_filters ON issues(status, priority);
CREATE INDEX comments_issue ON comments(issue_id, id);
