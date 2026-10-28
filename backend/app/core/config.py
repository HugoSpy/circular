"""Local paths and environment configuration; no global configuration is read."""
import os
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[3]


def secret_value(name: str) -> str:
    """Prefer a mounted secret file; never print its contents."""
    file = os.environ.get(name + "_FILE")
    return Path(file).read_text(encoding="utf-8").strip() if file else os.environ.get(name, "")


def production() -> bool:
    mode = os.environ.get("CIRCULAR_ENV", "development")
    if mode not in {"development", "production", "test"}:
        raise ValueError("CIRCULAR_ENV doit être development, test ou production.")
    return mode == "production"


def public_url() -> str:
    value = os.environ.get("CIRCULAR_PUBLIC_URL", "").rstrip("/")
    if not value and not production():
        return ""
    parsed = urlsplit(value)
    if not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment or parsed.scheme not in {"http", "https"}:
        raise ValueError("CIRCULAR_PUBLIC_URL doit être une origine complète, sans chemin ni identifiants.")
    if production() and parsed.scheme != "https":
        raise ValueError("CIRCULAR_PUBLIC_URL doit utiliser HTTPS en production.")
    return value


def database_target() -> Path | str:
    value = secret_value("CIRCULAR_DATABASE_URL")
    if value:
        if not value.startswith(("postgresql://", "postgres://")):
            raise ValueError("CIRCULAR_DATABASE_URL doit être une URL PostgreSQL.")
        return value
    if production():
        raise ValueError("Une connexion PostgreSQL est requise en production.")
    return database_path()


def server_host() -> str:
    return os.environ.get("CIRCULAR_HOST", "127.0.0.1")


def database_path() -> Path:
    value = Path(os.environ.get("CIRCULAR_DB", "data/circular.sqlite"))
    return value if value.is_absolute() else ROOT / value


def server_port() -> int:
    port = int(os.environ.get("CIRCULAR_PORT", "4310"))
    if not 1 <= port <= 65535:
        raise ValueError("CIRCULAR_PORT doit être compris entre 1 et 65535.")
    return port
