CREATE TABLE mcp_confirmations (
    id TEXT PRIMARY KEY,
    connection_id TEXT NOT NULL REFERENCES mcp_connections(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    payload TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('pending','refused','running','done','failed','uncertain')),
    expires_at BIGINT NOT NULL,
    created_at TEXT NOT NULL,
    result TEXT
);
CREATE INDEX mcp_confirmations_connection ON mcp_confirmations(connection_id);
