ALTER TABLE users ADD COLUMN display_name TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN title TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN profile_completed INTEGER NOT NULL DEFAULT 0 CHECK(profile_completed IN (0, 1));
UPDATE users SET display_name = username, profile_completed = 1;
CREATE TABLE workspaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    owner_user_id INTEGER NOT NULL REFERENCES users(id),
    legacy_owner_user_id INTEGER UNIQUE REFERENCES users(id),
    initial_project_id INTEGER,
    created_at TEXT NOT NULL
);
CREATE TABLE workspace_members (
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('owner', 'member', 'guest')),
    onboarding_completed INTEGER NOT NULL DEFAULT 1 CHECK(onboarding_completed IN (0, 1)),
    joined_at TEXT NOT NULL,
    PRIMARY KEY(workspace_id, user_id)
);
CREATE INDEX workspace_members_user ON workspace_members(user_id);
CREATE TABLE workspace_invitations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    inviter_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    UNIQUE(workspace_id, email)
);
CREATE INDEX workspace_invitations_email ON workspace_invitations(email);
CREATE TABLE workspace_invite_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE workspace_user_settings (
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    payload TEXT NOT NULL,
    PRIMARY KEY(workspace_id, user_id)
);
ALTER TABLE projects ADD COLUMN workspace_id INTEGER REFERENCES workspaces(id);
ALTER TABLE projects ADD COLUMN visibility TEXT NOT NULL DEFAULT 'private' CHECK(visibility IN ('private', 'workspace'));
ALTER TABLE labels ADD COLUMN workspace_id INTEGER REFERENCES workspaces(id);
ALTER TABLE saved_views ADD COLUMN workspace_id INTEGER REFERENCES workspaces(id);
ALTER TABLE issue_templates ADD COLUMN workspace_id INTEGER REFERENCES workspaces(id);
CREATE INDEX projects_workspace ON projects(workspace_id);
CREATE INDEX labels_workspace ON labels(workspace_id);
CREATE INDEX views_workspace_owner ON saved_views(workspace_id, owner_user_id);
CREATE INDEX templates_workspace_owner ON issue_templates(workspace_id, owner_user_id);
