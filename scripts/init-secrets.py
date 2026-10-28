"""Generate initial Docker secret files without displaying or overwriting credentials."""
import argparse
import os
from pathlib import Path
import secrets
import stat

parser = argparse.ArgumentParser(description="Créer les secrets initiaux pour PostgreSQL fourni par Compose.")
parser.add_argument("--directory", default="secrets")
args = parser.parse_args()
directory = Path(args.directory).resolve()
names = ("database_admin_password", "database_password", "database_url")
if any((directory / name).exists() for name in names):
    raise SystemExit("Refus : un secret existe déjà. Les mots de passe de la base ne sont pas remplacés.")
directory.mkdir(parents=True, exist_ok=True, mode=0o700)
if os.name != "nt" and stat.S_IMODE(directory.stat().st_mode) & 0o077:
    raise SystemExit("Refus : le dossier secrets doit être privé (chmod 700). Aucun secret n’a été créé.")
password = secrets.token_urlsafe(36)
values = (secrets.token_urlsafe(36), password, f"postgresql://circular_app:{password}@postgres:5432/circular")
for name, value in zip(names, values):
    descriptor = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
        file.write(value + "\n")
    # Compose mounts individual files. UID 10001 (app) and the PostgreSQL UID
    # must read their respective mounts even when the host operator owns them.
    # The enclosing 0700 host directory prevents other host users opening them.
    os.chmod(directory / name, 0o444)
print("Trois fichiers secrets créés. Aucun identifiant affiché. Ne pas les versionner.")
