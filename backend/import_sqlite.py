"""Explicit one-way import from a read-only SQLite snapshot into empty PostgreSQL.

The source is never migrated or modified. Existing PostgreSQL business rows are
never merged or overwritten. Authentication sessions and throttling records are
deliberately not transferred, so users must sign in again after migration.
"""
import argparse
from pathlib import Path
import sqlite3
from backend.app.core.config import database_target
from backend.app.db.session import Database
from backend.app.db.backfill import backfill_workspaces


TABLES = (
    "users", "workspaces", "workspace_members", "project_sequences", "projects", "labels", "issues", "comments",
    "issue_labels", "workspace_settings", "saved_views", "issue_templates",
    "template_labels", "issue_activity", "project_members", "project_invitations",
    "issue_favorites", "user_settings", "workspace_invitations", "workspace_invite_links",
    "workspace_user_settings", "seed_runs",
)
IDENTITY_TABLES = (
    "users", "projects", "labels", "issues", "comments", "saved_views",
    "issue_templates", "issue_activity", "project_invitations", "workspaces",
    "workspace_invitations", "workspace_invite_links",
)


def quoted(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def import_sqlite(source: Path, destination: Database) -> dict[str, int]:
    if destination.dialect != "postgresql":
        raise ValueError("La destination doit être une base PostgreSQL vide.")
    source = source.resolve(strict=True)
    if not source.is_file():
        raise ValueError("Le fichier SQLite source est introuvable.")
    # mode=ro plus an explicit read transaction supplies a consistent snapshot,
    # including committed WAL records when the source has a WAL file.
    reader = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
    reader.row_factory = sqlite3.Row
    counts: dict[str, int] = {}
    try:
        reader.execute("BEGIN")
        available = {row[0] for row in reader.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if not {"projects", "issues", "schema_migrations"} <= available:
            raise ValueError("Le fichier source n’est pas une base Circular reconnue.")
        known_versions = {path.name for path in (Path(__file__).parent / "app/db/migrations").glob("[0-9]*.sql")}
        source_versions = {row[0] for row in reader.execute("SELECT version FROM schema_migrations")}
        if not source_versions <= known_versions:
            raise ValueError("La base source utilise une migration inconnue de cette version de Circular.")
        with destination.connect(write=True) as connection:
            # Match the migration lock, then lock all import targets to close the
            # emptiness-check race with a concurrent signup or project creation.
            connection.execute("SELECT pg_advisory_xact_lock(724205731)")
            for table in TABLES:
                connection.execute(f"LOCK TABLE {quoted(table)} IN ACCESS EXCLUSIVE MODE")
            if any(connection.execute(f"SELECT 1 FROM {quoted(table)} LIMIT 1").fetchone() for table in TABLES):
                raise ValueError("Import refusé : la destination contient déjà des données. Utilisez une base PostgreSQL vide.")
            for table in TABLES:
                if table not in available:
                    continue
                source_columns = [row[1] for row in reader.execute(f"PRAGMA table_info({quoted(table)})")]
                target_columns = {row[0] for row in connection.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = ?", (table,))}
                if not set(source_columns) <= target_columns:
                    raise ValueError(f"Schéma source incompatible pour la table {table}.")
                names = ", ".join(quoted(column) for column in source_columns)
                placeholders = ", ".join("?" for _ in source_columns)
                cursor = reader.execute(f"SELECT {names} FROM {quoted(table)}")
                count = 0
                while rows := cursor.fetchmany(500):
                    connection.executemany(f"INSERT INTO {quoted(table)} ({names}) VALUES ({placeholders})", [tuple(row) for row in rows])
                    count += len(rows)
                if table == "users" and "display_name" not in source_columns:
                    connection.execute("UPDATE users SET display_name = username, profile_completed = 1")
                counts[table] = count
            for table in IDENTITY_TABLES:
                # IDs remain stable, and future inserts continue above imported
                # IDs rather than colliding with identity sequences starting at 1.
                connection.execute(f"SELECT setval(pg_get_serial_sequence(?, 'id'), COALESCE((SELECT MAX(id) FROM {quoted(table)}), 1), EXISTS(SELECT 1 FROM {quoted(table)}))", (table,))
            # Older snapshots have owners but no workspace columns. Apply the
            # same idempotent transition as startup, inside this transaction.
            # Unclaimed v1 rows remain private and unassigned until claim_legacy.
            backfill_workspaces(connection)
        return counts
    finally:
        reader.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Copie du fichier SQLite Circular ; ouvert en lecture seule.")
    args = parser.parse_args()
    try:
        target = database_target()
        if not isinstance(target, str) or not target.startswith(("postgresql://", "postgres://")):
            raise ValueError("PostgreSQL destination required.")
        counts = import_sqlite(args.source, Database(target))
    except Exception:
        # Driver exceptions can include DSNs, SQL values or authentication data.
        # Keep the command output safe; operators can inspect configuration and
        # retry against a new empty database without leaking secrets in logs.
        raise SystemExit("Import refusé ou échoué. Vérifiez le fichier source, la connexion et que la base PostgreSQL est vide. Aucune donnée métier partielle n’a été conservée.") from None
    print(f"Import terminé : {sum(counts.values())} enregistrements dans {len(counts)} tables. Sessions non transférées.")


if __name__ == "__main__":
    main()
