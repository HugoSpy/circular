"""Restricted operator commands, run inside the application container by the school."""
import argparse
import getpass
import sys
from pathlib import Path
from backend.app.core.config import database_target
from backend.app.db.session import Database
from backend.app.schemas.auth import normalize_email
from backend.app.services.auth import AuthService
from backend.app.services.workspace import DomainError


def main() -> int:
    parser = argparse.ArgumentParser(description="Maintenance des comptes Circular (accès opérateur requis).")
    commands = parser.add_subparsers(dest="command", required=True)
    reset = commands.add_parser("reset-password", help="Changer un mot de passe et révoquer toutes les sessions du compte.")
    reset.add_argument("--email", required=True)
    reset.add_argument("--password-file", type=Path, help="Fichier secret monté dans le conteneur ; sinon saisie interactive masquée.")
    args = parser.parse_args()
    try:
        email = normalize_email(args.email)
        if args.password_file:
            password = args.password_file.read_text(encoding="utf-8").rstrip("\r\n")
        else:
            if not sys.stdin.isatty():
                raise ValueError("Utilisez un terminal interactif ou --password-file pour éviter toute saisie non masquée.")
            password = getpass.getpass("Nouveau mot de passe (12 à 128 caractères) : ")
            if password != getpass.getpass("Confirmation : "):
                raise ValueError("Les mots de passe ne correspondent pas.")
        if not 12 <= len(password) <= 128:
            raise ValueError("Le mot de passe doit contenir 12 à 128 caractères.")
        AuthService(Database(database_target())).reset_password(email, password)
    except (DomainError, ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print("Mot de passe modifié. Toutes les sessions de ce compte ont été révoquées.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
