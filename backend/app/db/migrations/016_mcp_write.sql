ALTER TABLE mcp_connections ADD COLUMN scope TEXT NOT NULL DEFAULT 'circular:read'
    CHECK (scope IN ('circular:read', 'circular:read circular:write'));

CREATE TABLE mcp_writes (
    connection_id TEXT NOT NULL REFERENCES mcp_connections(id) ON DELETE CASCADE,
    request_key TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    result TEXT NOT NULL,
    PRIMARY KEY (connection_id, request_key)
);
