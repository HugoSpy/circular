"""Persistence for accounts, revocable sessions and shared rate-limit counters."""
import unicodedata
from datetime import datetime, timedelta, timezone
from backend.app.db.session import timestamp


class AuthRepository:
    def __init__(self, connection):
        self.connection = connection

    def user_by_email(self, email: str) -> dict | None:
        row = self.connection.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None

    def user_by_username(self, username: str) -> dict | None:
        normalized = unicodedata.normalize("NFC", username.strip()).casefold()
        row = self.connection.execute("SELECT * FROM users WHERE normalized_username = ?", (normalized,)).fetchone()
        return dict(row) if row else None

    def user_by_identifier(self, identifier: str) -> dict | None:
        normalized = unicodedata.normalize("NFC", identifier.strip()).casefold()
        row = self.connection.execute("SELECT * FROM users WHERE email = ? OR normalized_username = ?", (normalized, normalized)).fetchone()
        return dict(row) if row else None

    def user(self, user_id: int, *, lock: bool = False) -> dict | None:
        locking = " FOR UPDATE" if lock and getattr(self.connection, "dialect", "sqlite") == "postgresql" else ""
        row = self.connection.execute("SELECT * FROM users WHERE id = ?" + locking, (user_id,)).fetchone()
        return dict(row) if row else None

    def create_user(self, email: str, username: str, password_hash: str, *, email_verified: bool = True) -> dict:
        row = self.connection.execute("""INSERT INTO users(email, username, normalized_username, password_hash, created_at, display_name, email_verified)
            VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id""", (email, username, unicodedata.normalize("NFC", username).casefold(), password_hash, timestamp(), username, int(email_verified))).fetchone()
        return self.user(row["id"])

    def pending_by_email(self, email: str) -> dict | None:
        row = self.connection.execute("SELECT * FROM pending_accounts WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None

    def pending_by_username(self, username: str) -> dict | None:
        normalized = unicodedata.normalize("NFC", username.strip()).casefold()
        row = self.connection.execute("SELECT * FROM pending_accounts WHERE normalized_username = ?", (normalized,)).fetchone()
        return dict(row) if row else None

    def pending_by_token(self, token_hash: str) -> dict | None:
        row = self.connection.execute("SELECT * FROM pending_accounts WHERE token_hash = ?", (token_hash,)).fetchone()
        return dict(row) if row else None

    def create_pending(self, email: str, username: str, password_hash: str, token_hash: str, expires_at: int) -> None:
        self.connection.execute("""INSERT INTO pending_accounts(email, username, normalized_username, password_hash, token_hash, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""", (email, username, unicodedata.normalize("NFC", username).casefold(), password_hash, token_hash, timestamp(), expires_at))

    def rotate_pending_token(self, email: str, token_hash: str, expires_at: int) -> None:
        self.connection.execute("UPDATE pending_accounts SET token_hash = ?, expires_at = ? WHERE email = ?", (token_hash, expires_at, email))

    def update_pending_registration(self, email: str, username: str, password_hash: str, token_hash: str, expires_at: int) -> None:
        normalized = unicodedata.normalize("NFC", username.strip()).casefold()
        self.connection.execute("UPDATE pending_accounts SET username = ?, normalized_username = ?, password_hash = ?, token_hash = ?, expires_at = ? WHERE email = ?",
                                (username, normalized, password_hash, token_hash, expires_at, email))

    def delete_pending(self, email: str) -> None:
        self.connection.execute("DELETE FROM pending_accounts WHERE email = ?", (email,))

    def verification_for_user(self, user_id: int) -> dict | None:
        row = self.connection.execute("SELECT * FROM email_verification_tokens WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def verification_by_token(self, token_hash: str) -> dict | None:
        row = self.connection.execute("SELECT * FROM email_verification_tokens WHERE token_hash = ?", (token_hash,)).fetchone()
        return dict(row) if row else None

    def set_verification_token(self, user_id: int, token_hash: str, expires_at: int) -> None:
        self.connection.execute("DELETE FROM email_verification_tokens WHERE user_id = ?", (user_id,))
        self.connection.execute("INSERT INTO email_verification_tokens(token_hash, user_id, expires_at) VALUES (?, ?, ?)", (token_hash, user_id, expires_at))

    def delete_verification_token(self, token_hash: str) -> None:
        self.connection.execute("DELETE FROM email_verification_tokens WHERE token_hash = ?", (token_hash,))

    def mark_email_verified(self, user_id: int) -> dict:
        self.connection.execute("UPDATE users SET email_verified = 1 WHERE id = ?", (user_id,))
        return self.user(user_id)

    def update_password(self, user_id: int, password_hash: str) -> None:
        self.connection.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))

    def create_session(self, token_hash: str, user_id: int, csrf: str, now: int, expires: int) -> None:
        self.connection.execute("""INSERT INTO user_sessions(token_hash, user_id, csrf_token, created_at, last_seen_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)""", (token_hash, user_id, csrf, now, now, expires))

    def session(self, token_hash: str) -> dict | None:
        row = self.connection.execute("""SELECT s.*, u.email, u.username, u.active, u.display_name, u.title, u.profile_completed, u.email_verified FROM user_sessions s
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
        pending_cutoff = datetime.fromtimestamp(now, timezone.utc) - timedelta(hours=24)
        pending_cutoff_text = pending_cutoff.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        self.connection.execute("DELETE FROM pending_accounts WHERE created_at <= ?", (pending_cutoff_text,))
        self.connection.execute("DELETE FROM email_verification_tokens WHERE expires_at <= ?", (now,))

    def update_profile(self, user_id: int, data: dict) -> dict:
        self.connection.execute("UPDATE users SET display_name = ?, title = ?, profile_completed = 1 WHERE id = ?", (data["displayName"], data["title"], user_id))
        return self.user(user_id)
