"""Explicit operator assignment of the original single-user data to one account."""
import argparse
import sqlite3
from backend.app.core.config import database_target
from backend.app.db.session import Database


def claim_legacy(database: Database, user_id: int) -> int:
    with database.connect(write=True) as connection:
        if not connection.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone():
            raise ValueError("Compte introuvable.")
        count = connection.execute("SELECT COUNT(*) FROM projects WHERE owner_user_id IS NULL").fetchone()[0]
        for row in connection.execute("SELECT id, normalized_name FROM labels WHERE owner_user_id IS NULL"):
            key = f'{user_id}:{row["normalized_name"]}'
            if connection.execute("SELECT id FROM labels WHERE normalized_name = ?", (key,)).fetchone():
                raise ValueError("Une étiquette du compte entre en conflit avec les données historiques. Renommez-la avant de recommencer.")
            connection.execute("UPDATE labels SET owner_user_id = ?, normalized_name = ? WHERE id = ?", (user_id, key, row["id"]))
        for table in ("projects", "saved_views", "issue_templates"):
            connection.execute(f"UPDATE {table} SET owner_user_id = ? WHERE owner_user_id IS NULL", (user_id,))
        connection.execute("""INSERT INTO issue_favorites(issue_id, user_id)
            SELECT i.id, ? FROM issues i JOIN projects p ON p.id = i.project_id
            WHERE p.owner_user_id = ? AND i.is_favorite = 1 ON CONFLICT DO NOTHING""", (user_id, user_id))
        old = connection.execute("SELECT payload FROM workspace_settings WHERE id = 1").fetchone()
        if old:
            connection.execute("INSERT INTO user_settings(user_id, payload) VALUES (?, ?) ON CONFLICT DO NOTHING", (user_id, old[0]))
        return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Attribuer explicitement les données mono-utilisateur historiques à un compte existant.")
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    database = Database(database_target())
    with database.connect() as connection:
        user = connection.execute("SELECT id FROM users WHERE email = ?", (args.email.strip().casefold(),)).fetchone()
    if not user:
        raise SystemExit("Compte introuvable. Créez d’abord ce compte dans l’interface.")
    try:
        count = claim_legacy(database, user[0])
    except (ValueError, sqlite3.IntegrityError) as error:
        raise SystemExit(str(error)) from error
    print(f"Attribution terminée : {count} projet(s). Aucun contenu supprimé.")


if __name__ == "__main__":
    main()
