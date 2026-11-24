CREATE TABLE mcp_clients (
    id TEXT PRIMARY KEY,
    metadata TEXT NOT NULL
);
CREATE TABLE mcp_authorizations (
    request_hash TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES mcp_clients(id) ON DELETE CASCADE,
    parameters TEXT NOT NULL,
    expires_at BIGINT NOT NULL
);
CREATE TABLE mcp_codes (
    code_hash TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES mcp_clients(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    workspace_id BIGINT NOT NULL,
    parameters TEXT NOT NULL,
    expires_at BIGINT NOT NULL,
    FOREIGN KEY (workspace_id, user_id) REFERENCES workspace_members(workspace_id, user_id) ON DELETE CASCADE
);
CREATE TABLE mcp_connections (
    id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES mcp_clients(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    workspace_id BIGINT NOT NULL,
    resource TEXT NOT NULL,
    access_hash TEXT NOT NULL UNIQUE,
    refresh_hash TEXT NOT NULL UNIQUE,
    access_expires_at BIGINT NOT NULL,
    refresh_expires_at BIGINT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (workspace_id, user_id) REFERENCES workspace_members(workspace_id, user_id) ON DELETE CASCADE
);
CREATE INDEX mcp_connections_user ON mcp_connections(user_id);
CREATE INDEX mcp_connections_membership ON mcp_connections(workspace_id, user_id);
CREATE INDEX mcp_codes_membership ON mcp_codes(workspace_id, user_id);
