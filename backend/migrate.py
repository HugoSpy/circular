from backend.app.core.config import database_target
from backend.app.db.session import Database

if __name__ == "__main__":
    database = Database(database_target())
    print(f"Migrations appliquées ({database.dialect}).")
