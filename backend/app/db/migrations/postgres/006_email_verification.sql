ALTER TABLE users ADD COLUMN email_verified BIGINT NOT NULL DEFAULT 0 CHECK(email_verified IN (0, 1));

CREATE TABLE pending_accounts (
    email TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    normalized_username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    expires_at BIGINT NOT NULL
);
CREATE INDEX pending_accounts_expiry ON pending_accounts(expires_at);

CREATE TABLE email_verification_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at BIGINT NOT NULL
);
CREATE INDEX email_verification_tokens_user ON email_verification_tokens(user_id);
CREATE INDEX email_verification_tokens_expiry ON email_verification_tokens(expires_at);
