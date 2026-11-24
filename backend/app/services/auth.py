"""Account authentication, session lifecycle and rate limits independent of HTTP."""
import hashlib
import logging
import secrets
import sqlite3
import time
import unicodedata
from backend.app.services.email import send_verification
from backend.app.core.passwords import HASHER, dummy_password_hash, hash_password, verify_password
from backend.app.db.session import Database
from backend.app.repositories.auth import AuthRepository
from backend.app.services.workspace import DomainError

logger = logging.getLogger("circular.security")
SESSION_TTL = 12 * 60 * 60
SESSION_IDLE_TIMEOUT = 30 * 60
VERIFICATION_TTL = 30 * 60
REGISTRATION_MESSAGE = "Si cette adresse peut être utilisée, un lien de confirmation vient d’y être envoyé. Si vous avez déjà un compte, connectez-vous."


def verifier(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def public_user(user: dict) -> dict:
    return {"id": user["id"], "email": user["email"], "username": user["username"], "displayName": user["display_name"] or user["username"], "title": user["title"], "profileCompleted": bool(user["profile_completed"])}


class AuthService:
    def __init__(self, database: Database, *, session_ttl: int = SESSION_TTL, idle_timeout: int = SESSION_IDLE_TIMEOUT, email_sender=None):
        self.database = database
        self.session_ttl = session_ttl
        self.idle_timeout = idle_timeout
        self.email_sender = email_sender or send_verification

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
        return {"user": public_user(user), "csrfToken": csrf, "emailVerified": bool(user["email_verified"])}, token

    @staticmethod
    def _identity_lock(connection) -> None:
        if getattr(connection, "dialect", "sqlite") == "postgresql":
            connection.execute("SELECT pg_advisory_xact_lock(724205734)")

    @staticmethod
    def _integrity_reason(error: sqlite3.IntegrityError) -> str | None:
        constraint = getattr(error, "constraint_name", None) or ""
        if constraint in {"users_email_key", "pending_accounts_email_key"}:
            return "email"
        if constraint in {"users_normalized_username_key", "pending_accounts_normalized_username_key"}:
            return "username"
        name = getattr(error, "sqlite_errorname", "")
        message = str(error)
        if name == "SQLITE_CONSTRAINT_UNIQUE":
            if "users.email" in message or "pending_accounts.email" in message:
                return "email"
            if "users.normalized_username" in message or "pending_accounts.normalized_username" in message:
                return "username"
        return None

    def _deliver_verification(self, email: str, token: str) -> None:
        try:
            self.email_sender(email, token)
        except Exception as error:
            logger.error("email_delivery_failed error_type=%s", type(error).__name__)

    def _request_user_verification(self, repo: AuthRepository, user: dict) -> tuple[str, str] | None:
        if user["email_verified"]:
            return None
        token = secrets.token_urlsafe(32)
        repo.set_verification_token(user["id"], verifier(token), int(time.time()) + VERIFICATION_TTL)
        return user["email"], token

    def register(self, email: str, username: str, password: str, peer: str) -> dict:
        self._limits("register", peer, email)
        encoded = hash_password(password)
        delivery = None
        outcome = "unavailable"
        try:
            with self.database.connect(write=True) as connection:
                self._identity_lock(connection)
                repo = AuthRepository(connection)
                existing = repo.user_by_email(email)
                if existing:
                    delivery = self._request_user_verification(repo, existing)
                    outcome = "existing_unverified" if delivery else "existing_verified"
                else:
                    pending = repo.pending_by_email(email)
                    if pending:
                        username_owner = repo.user_by_username(username)
                        pending_username_owner = repo.pending_by_username(username)
                        if username_owner or (pending_username_owner and pending_username_owner["email"] != email):
                            outcome = "duplicate_username"
                        else:
                            token = secrets.token_urlsafe(32)
                            repo.update_pending_registration(email, username, encoded, verifier(token), int(time.time()) + VERIFICATION_TTL)
                            delivery = (email, token)
                            outcome = "pending_resent"
                    elif repo.user_by_username(username) or repo.pending_by_username(username):
                        outcome = "duplicate_username"
                    else:
                        token = secrets.token_urlsafe(32)
                        repo.create_pending(email, username, encoded, verifier(token), int(time.time()) + VERIFICATION_TTL)
                        delivery = (email, token)
                        outcome = "pending_created"
        except sqlite3.IntegrityError as error:
            reason = self._integrity_reason(error)
            if reason:
                outcome = f"duplicate_{reason}"
            else:
                logger.error("account_registration_integrity_failure constraint=%s", getattr(error, "constraint_name", "unknown"))
                raise DomainError(503, "Inscription temporairement indisponible. Réessayez dans quelques instants.") from error
        logger.info("account_registration outcome=%s", outcome)
        if delivery:
            self._deliver_verification(*delivery)
        return {"message": REGISTRATION_MESSAGE}

    def request_verification(self, email: str, peer: str) -> dict:
        self._limits("register", peer, email)
        delivery = None
        with self.database.connect(write=True) as connection:
            repo = AuthRepository(connection)
            if user := repo.user_by_email(email):
                delivery = self._request_user_verification(repo, user)
                outcome = "account_unverified" if delivery else "account_verified"
            elif pending := repo.pending_by_email(email):
                token = secrets.token_urlsafe(32)
                repo.rotate_pending_token(email, verifier(token), int(time.time()) + VERIFICATION_TTL)
                delivery = (email, token)
                outcome = "registration_pending"
            else:
                outcome = "address_unavailable"
        logger.info("email_verification_requested outcome=%s", outcome)
        if delivery:
            self._deliver_verification(*delivery)
        return {"message": REGISTRATION_MESSAGE}

    def request_current_verification(self, user_id: int, peer: str) -> dict:
        self._limits("register", peer, str(user_id))
        with self.database.connect(write=True) as connection:
            repo = AuthRepository(connection)
            user = repo.user(user_id)
            if not user:
                raise DomainError(401, "Connectez-vous pour continuer.")
            delivery = self._request_user_verification(repo, user)
            outcome = "account_unverified" if delivery else "account_verified"
        logger.info("email_verification_requested outcome=%s", outcome)
        if delivery:
            self._deliver_verification(*delivery)
        return {"message": "Si votre adresse doit être confirmée, un lien vient d’être envoyé."}

    def verify_email(self, token: str, peer: str) -> tuple[dict, str]:
        self._limits("verify", peer)
        digest = verifier(token)
        now = int(time.time())
        pseudo_changed = False
        with self.database.connect(write=True) as connection:
            self._identity_lock(connection)
            repo = AuthRepository(connection)
            pending = repo.pending_by_token(digest)
            if pending:
                if pending["expires_at"] <= now:
                    raise DomainError(400, "Ce lien de confirmation est invalide ou expiré. Demandez-en un nouveau.")
                if repo.user_by_email(pending["email"]) or repo.user_by_username(pending["username"]):
                    repo.delete_pending(pending["email"])
                    pseudo_changed = True
                else:
                    user = repo.create_user(pending["email"], pending["username"], pending["password_hash"], email_verified=True)
                    repo.delete_pending(pending["email"])
                    result = self._new_session(repo, user)
                    logger.info("account_email_verified source=registration")
                    return result
            else:
                verification = repo.verification_by_token(digest)
                if not verification or verification["expires_at"] <= now:
                    raise DomainError(400, "Ce lien de confirmation est invalide ou expiré. Demandez-en un nouveau.")
                repo.delete_verification_token(digest)
                user = repo.mark_email_verified(verification["user_id"])
                result = self._new_session(repo, user)
        if pseudo_changed:
            raise DomainError(409, "Le pseudo n’est plus disponible. Recommencez l’inscription avec un autre pseudo.")
        logger.info("account_email_verified source=existing_account")
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
                    result = {"user": public_user({**session, "id": session["user_id"]}), "csrfToken": session["csrf_token"], "emailVerified": bool(session["email_verified"])}
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
