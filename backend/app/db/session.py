"""Versioned migrations and one database connection per unit of work."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from backend.app.db.postgres import PostgresConnection


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Database:
    def __init__(self, path: Path | str):
        value = str(path)
        self.dialect = "postgresql" if value.startswith(("postgresql://", "postgres://")) else "sqlite"
        self.dsn: str | None = value if self.dialect == "postgresql" else None
        self.path: Path | None = None if self.dsn else Path(path).resolve()
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    @contextmanager
    def connect(self, *, write: bool = False) -> Iterator[sqlite3.Connection | PostgresConnection]:
        if self.dsn:
            import psycopg
            from psycopg.rows import dict_row

            connection = PostgresConnection(psycopg.connect(self.dsn, connect_timeout=10, row_factory=dict_row))
            try:
                connection.execute("SET LOCAL statement_timeout = '30s'")
                connection.execute("SET LOCAL idle_in_transaction_session_timeout = '60s'")
                yield connection
                if write:
                    connection.commit()
                else:
                    connection.rollback()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()
            return
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            if write:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            if write:
                connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def migrate(self) -> None:
        if self.dialect == "postgresql":
            self._migrate_postgres()
            return
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
            connection.commit()
        for migration in sorted((Path(__file__).parent / "migrations").glob("[0-9]*.sql")):
            with self.connect(write=True) as connection:
                if connection.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (migration.name,)).fetchone():
                    continue
                # sqlite3.executescript commits pending transactions, so execute each
                # complete statement inside the explicit migration transaction.
                statement = ""
                for line in migration.read_text(encoding="utf-8").splitlines(keepends=True):
                    statement += line
                    if sqlite3.complete_statement(statement):
                        connection.execute(statement)
                        statement = ""
                if statement.strip():
                    raise ValueError(f"Migration SQL incomplète : {migration.name}")
                if migration.name == "005_workspaces.sql":
                    from backend.app.db.backfill import backfill_workspaces
                    backfill_workspaces(connection)
                connection.execute("INSERT INTO schema_migrations VALUES (?, ?)", (migration.name, timestamp()))

    def _migrate_postgres(self) -> None:
        """One transaction and advisory lock protect parallel process startup."""
        directory = Path(__file__).parent / "migrations"
        sqlite_versions = {path.name for path in directory.glob("[0-9]*.sql")}
        migrations = sorted((directory / "postgres").glob("[0-9]*.sql"))
        if sqlite_versions != {path.name for path in migrations}:
            raise RuntimeError("PostgreSQL migrations are incomplete; refusing to start.")
        with self.connect(write=True) as connection:
            connection.execute("SELECT pg_advisory_xact_lock(724205731)")
            connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
            for migration in migrations:
                if connection.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (migration.name,)).fetchone():
                    continue
                statement = ""
                for line in migration.read_text(encoding="utf-8").splitlines(keepends=True):
                    statement += line
                    if sqlite3.complete_statement(statement):
                        connection.execute(statement)
                        statement = ""
                if statement.strip():
                    raise ValueError(f"Migration SQL incomplète : {migration.name}")
                if migration.name == "005_workspaces.sql":
                    from backend.app.db.backfill import backfill_workspaces
                    backfill_workspaces(connection)
                connection.execute("INSERT INTO schema_migrations VALUES (?, ?)", (migration.name, timestamp()))
