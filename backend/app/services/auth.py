"""Account authentication, session lifecycle and rate limits independent of HTTP."""
import hashlib
import logging
import secrets
import sqlite3
import time
import unicodedata
from backend.app.core.passwords import HASHER, dummy_password_hash, hash_password, verify_password
from backend.app.db.session import Database
from backend.app.repositories.auth import AuthRepository
from backend.app.services.workspace import DomainError

logger = logging.getLogger("circular.security")
SESSION_TTL = 12 * 60 * 60
SESSION_IDLE_TIMEOUT = 30 * 60


def verifier(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def public_user(user: dict) -> dict:
    return {"id": user["id"], "email": user["email"], "username": user["username"], "displayName": user["display_name"] or user["username"], "title": user["title"], "profileCompleted": bool(user["profile_completed"])}


class AuthService:
    def __init__(self, database: Database, *, session_ttl: int = SESSION_TTL, idle_timeout: int = SESSION_IDLE_TIMEOUT):
        self.database = database
        self.session_ttl = session_ttl
        self.idle_timeout = idle_timeout

    def _limits(self, action: str, peer: str, identifier: str = "") -> None:
        """Atomic counters are shared by all workers; failed attempts also commit."""
        now = int(time.time())
        limits = [(f"{action}:ip:{peer}", 3600, 20)] if action == "register" else [(f"{action}:ip:{peer}", 600, 50)]
        if identifier:
            normalized = unicodedata.normalize("NFC", identifier.strip()).casefold()
            limits.append((f"{action}:account:{normalized}", 600, 10))
        exceeded = False
        with self.database.connect(write=True) as connection:
            repo = AuthRepository(connection)
            repo.cleanup(now)
            for scope, window, maximum in limits:
                bucket = now // window
                key = verifier(f"{scope}:{bucket}")
                exceeded |= repo.consume_limit(key, (bucket + 1) * window) > maximum
        if exceeded:
            logger.warning("auth_rate_limit action=%s", action)
            raise DomainError(429, "Trop de tentatives. Réessayez dans quelques minutes.")

    def _new_session(self, repo: AuthRepository, user: dict) -> tuple[dict, str]:
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        now = int(time.time())
        repo.create_session(verifier(token), user["id"], csrf, now, now + self.session_ttl)
        return {"user": public_user(user), "csrfToken": csrf}, token

    def register(self, email: str, username: str, password: str, peer: str) -> tuple[dict, str]:
        self._limits("register", peer)
        encoded = hash_password(password)
        try:
            with self.database.connect(write=True) as connection:
                repo = AuthRepository(connection)
                user = repo.create_user(email, username, encoded)
                result = self._new_session(repo, user)
        except sqlite3.IntegrityError as error:
            raise DomainError(409, "Impossible de créer ce compte avec ces informations. Essayez un autre pseudo ou connectez-vous.") from error
        logger.info("account_created user_id=%s", user["id"])
        return result

    def login(self, identifier: str, password: str, peer: str) -> tuple[dict, str]:
        self._limits("login", peer, identifier)
        with self.database.connect() as connection:
            user = AuthRepository(connection).user_by_identifier(identifier)
        encoded = user["password_hash"] if user else dummy_password_hash()
        valid = verify_password(encoded, password)
        if not valid or not user or not user["active"]:
            logger.warning("authentication_failed")
            raise DomainError(401, "Identifiant ou mot de passe incorrect.")
        with self.database.connect(write=True) as connection:
            repo = AuthRepository(connection)
            # A reset between verification and session creation must invalidate this login.
            current = repo.user(user["id"], lock=True)
            if not current or not current["active"] or current["password_hash"] != encoded:
                raise DomainError(401, "Identifiant ou mot de passe incorrect.")
            if HASHER.check_needs_rehash(encoded):
                repo.update_password(user["id"], hash_password(password))
            result = self._new_session(repo, current)
        logger.info("authentication_succeeded user_id=%s", user["id"])
        return result

    def authenticate(self, token: str | None) -> dict:
        if not token or len(token) > 128:
            raise DomainError(401, "Connectez-vous pour accéder à votre espace.")
        digest = verifier(token)
        now = int(time.time())
        result = None
        with self.database.connect(write=True) as connection:
            repo = AuthRepository(connection)
            session = repo.session(digest)
            if session:
                if not session["active"] or session["expires_at"] <= now or session["last_seen_at"] + self.idle_timeout <= now:
                    repo.delete_session(digest)
                else:
                    repo.touch_session(digest, now)
                    result = {"user": public_user({**session, "id": session["user_id"]}), "csrfToken": session["csrf_token"]}
        if result is None:
            raise DomainError(401, "Votre session a expiré. Reconnectez-vous.")
        return result

    def logout(self, token: str) -> None:
        with self.database.connect(write=True) as connection:
            AuthRepository(connection).delete_session(verifier(token))

    def change_password(self, user_id: int, current_password: str, new_password: str, peer: str) -> None:
        self._limits("password", peer, str(user_id))
        encoded = hash_password(new_password)
        with self.database.connect(write=True) as connection:
            repo = AuthRepository(connection)
            user = repo.user(user_id, lock=True)
            if not user or not verify_password(user["password_hash"], current_password):
                raise DomainError(400, "Mot de passe actuel incorrect.")
            repo.update_password(user_id, encoded)
            repo.revoke_user_sessions(user_id)
        logger.info("password_changed user_id=%s", user_id)

    def reset_password(self, email: str, new_password: str) -> None:
        """Operator-only CLI entry point. No public reset endpoint or default account."""
        encoded = hash_password(new_password)
        with self.database.connect(write=True) as connection:
            repo = AuthRepository(connection)
            user = repo.user_by_email(email)
            if not user:
                raise DomainError(404, "Compte introuvable.")
            repo.user(user["id"], lock=True)
            repo.update_password(user["id"], encoded)
            repo.revoke_user_sessions(user["id"])
        logger.info("password_reset_by_operator user_id=%s", user["id"])

    def update_profile(self, user_id: int, data: dict) -> dict:
        with self.database.connect(write=True) as connection:
            return public_user(AuthRepository(connection).update_profile(user_id, data))
