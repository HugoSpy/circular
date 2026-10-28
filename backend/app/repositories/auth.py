"""Persistence for accounts, revocable sessions and shared rate-limit counters."""
import unicodedata
from backend.app.db.session import timestamp


class AuthRepository:
    def __init__(self, connection):
        self.connection = connection

    def user_by_email(self, email: str) -> dict | None:
        row = self.connection.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None

    def user_by_identifier(self, identifier: str) -> dict | None:
        normalized = unicodedata.normalize("NFC", identifier.strip()).casefold()
        row = self.connection.execute("SELECT * FROM users WHERE email = ? OR normalized_username = ?", (normalized, normalized)).fetchone()
        return dict(row) if row else None

    def user(self, user_id: int, *, lock: bool = False) -> dict | None:
        locking = " FOR UPDATE" if lock and getattr(self.connection, "dialect", "sqlite") == "postgresql" else ""
        row = self.connection.execute("SELECT * FROM users WHERE id = ?" + locking, (user_id,)).fetchone()
        return dict(row) if row else None

    def create_user(self, email: str, username: str, password_hash: str) -> dict:
        row = self.connection.execute("""INSERT INTO users(email, username, normalized_username, password_hash, created_at)
            VALUES (?, ?, ?, ?, ?) RETURNING id""", (email, username, unicodedata.normalize("NFC", username).casefold(), password_hash, timestamp())).fetchone()
        return self.user(row["id"])

    def update_password(self, user_id: int, password_hash: str) -> None:
        self.connection.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))

    def create_session(self, token_hash: str, user_id: int, csrf: str, now: int, expires: int) -> None:
        self.connection.execute("""INSERT INTO user_sessions(token_hash, user_id, csrf_token, created_at, last_seen_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)""", (token_hash, user_id, csrf, now, now, expires))

    def session(self, token_hash: str) -> dict | None:
        row = self.connection.execute("""SELECT s.*, u.email, u.username, u.active FROM user_sessions s
            JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?""", (token_hash,)).fetchone()
        return dict(row) if row else None

    def touch_session(self, token_hash: str, now: int) -> None:
        self.connection.execute("UPDATE user_sessions SET last_seen_at = ? WHERE token_hash = ?", (now, token_hash))

    def delete_session(self, token_hash: str) -> None:
        self.connection.execute("DELETE FROM user_sessions WHERE token_hash = ?", (token_hash,))

    def revoke_user_sessions(self, user_id: int) -> None:
        self.connection.execute("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))

    def consume_limit(self, key: str, expires: int) -> int:
        row = self.connection.execute("""INSERT INTO auth_rate_limits(bucket_key, attempts, expires_at) VALUES (?, 1, ?)
            ON CONFLICT(bucket_key) DO UPDATE SET attempts = auth_rate_limits.attempts + 1 RETURNING attempts""", (key, expires)).fetchone()
        return row["attempts"]

    def cleanup(self, now: int) -> None:
        self.connection.execute("DELETE FROM user_sessions WHERE expires_at <= ?", (now,))
        self.connection.execute("DELETE FROM auth_rate_limits WHERE expires_at <= ?", (now,))
