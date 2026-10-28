ALTER TABLE projects ADD COLUMN owner_user_id INTEGER REFERENCES users(id);
ALTER TABLE labels ADD COLUMN owner_user_id INTEGER REFERENCES users(id);
ALTER TABLE saved_views ADD COLUMN owner_user_id INTEGER REFERENCES users(id);
ALTER TABLE issue_templates ADD COLUMN owner_user_id INTEGER REFERENCES users(id);
ALTER TABLE comments ADD COLUMN author_user_id INTEGER REFERENCES users(id);
ALTER TABLE issue_activity ADD COLUMN actor_user_id INTEGER REFERENCES users(id);

CREATE TABLE project_members (
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  PRIMARY KEY (project_id, user_id)
);
CREATE TABLE project_invitations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  inviter_id INTEGER NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL,
  UNIQUE (project_id, user_id)
);
CREATE TABLE issue_favorites (
  issue_id INTEGER NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  PRIMARY KEY (issue_id, user_id)
);
CREATE TABLE user_settings (
  user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  payload TEXT NOT NULL
);
CREATE INDEX projects_owner ON projects(owner_user_id);
CREATE INDEX project_members_user ON project_members(user_id, project_id);
CREATE INDEX project_invitations_user ON project_invitations(user_id);
CREATE INDEX saved_views_owner ON saved_views(owner_user_id);
CREATE INDEX issue_templates_owner ON issue_templates(owner_user_id);
CREATE INDEX labels_owner ON labels(owner_user_id);
