"""Explicit, atomic, one-time demo seed. Startup never invokes this module."""
from backend.app.core.config import database_path, production
from backend.app.db.session import Database, timestamp
from backend.app.repositories.workspace import WorkspaceRepository
from backend.app.schemas.workspace import ProjectCreate, IssueCreate, LabelCreate

SEED_NAME = "circular-demo-v1"
PROJECTS = [
    {"name": "Lancement produit", "key": "ORB", "description": "Préparer la première version de notre espace de travail.", "color": "#75dbb2"},
    {"name": "Application mobile", "key": "MOB", "description": "Un compagnon simple pour retrouver l’essentiel en déplacement.", "color": "#a7a0f4"},
    {"name": "Site vitrine", "key": "WEB", "description": "Raconter le produit et faciliter sa découverte.", "color": "#e8b575"},
]
LABELS = [("Interface", "#a7a0f4"), ("Amélioration", "#75dbb2"), ("Bug", "#ee858f"), ("Recherche", "#e8b575"), ("Documentation", "#83b3ef")]
ISSUES = [
    ("ORB", "Définir le parcours de création d’un projet", "Documenter les étapes minimales et les états vides du premier lancement.", "done", "high", ["Recherche"]),
    ("ORB", "Construire la navigation latérale", "Afficher les projets actifs et conserver une navigation compacte.", "done", "medium", ["Interface"]),
    ("ORB", "Clarifier les états de priorité", "Vérifier que les cinq niveaux sont faciles à distinguer au clavier et à l’écran.", "in_review", "medium", ["Interface", "Amélioration"]),
    ("ORB", "Améliorer les messages de confirmation", "Préciser l’impact d’une suppression et conserver le contexte du ticket.", "in_progress", "high", ["Amélioration"]),
    ("ORB", "Corriger le focus après fermeture du détail", "Le focus doit revenir au ticket sélectionné après la fermeture du panneau.", "todo", "urgent", ["Bug", "Interface"]),
    ("ORB", "Rédiger le guide de démarrage", "Expliquer la création du premier projet et les raccourcis essentiels.", "todo", "low", ["Documentation"]),
    ("ORB", "Étudier les besoins d’archivage", "Recueillir des exemples de projets terminés avant de proposer une évolution.", "backlog", "none", ["Recherche"]),
    ("MOB", "Dessiner la liste des tickets sur petit écran", "Conserver l’identifiant, le titre et le statut sur une largeur de 390 pixels.", "in_progress", "high", ["Interface"]),
    ("MOB", "Augmenter les zones tactiles", "Rendre les actions de statut confortables sans charger la mise en page.", "todo", "medium", ["Interface", "Amélioration"]),
    ("MOB", "Vérifier le clavier virtuel du formulaire", "Le champ description et le bouton de sauvegarde doivent rester accessibles.", "in_review", "high", ["Bug"]),
    ("MOB", "Définir les scénarios de consultation", "Lister les informations nécessaires lors d’un déplacement.", "done", "medium", ["Recherche"]),
    ("MOB", "Documenter les gestes de navigation", "Proposer des interactions cohérentes avec les commandes visibles.", "backlog", "low", ["Documentation"]),
    ("WEB", "Finaliser le texte de la page d’accueil", "Présenter le bénéfice principal avec des exemples concrets.", "in_review", "medium", ["Amélioration"]),
    ("WEB", "Créer une page de présentation accessible", "Utiliser une hiérarchie claire et des liens descriptifs.", "todo", "high", ["Interface"]),
    ("WEB", "Corriger les contrastes du pied de page", "Vérifier la lisibilité des liens secondaires sur fond sombre.", "in_progress", "medium", ["Bug"]),
    ("WEB", "Préparer la checklist de publication", "Recenser les vérifications de contenu, navigation et accessibilité.", "backlog", "low", ["Documentation"]),
]


def seed_database(database: Database) -> bool:
    """Return False if already applied. Roll back every change on collision/error."""
    with database.connect(write=True) as connection:
        if connection.execute("SELECT 1 FROM seed_runs WHERE name = ?", (SEED_NAME,)).fetchone():
            return False
        repo = WorkspaceRepository(connection)
        existing_keys = {project["key"] for project in repo.projects()}
        if existing_keys.intersection(project["key"] for project in PROJECTS):
            raise ValueError("Un préfixe de démonstration (ORB, MOB, WEB) existe déjà. Aucune donnée n’a été modifiée.")
        projects = {data["key"]: repo.create_project(ProjectCreate(**data).model_dump()) for data in PROJECTS}
        labels = {}
        for name, color in LABELS:
            labels[name] = repo.label_by_name(name) or repo.create_label(LabelCreate(name=name, color=color).model_dump())
        created = []
        for key, title, description, status, priority, names in ISSUES:
            data = IssueCreate(title=title, description=description, projectId=projects[key]["id"], status=status,
                               priority=priority, labelIds=[labels[name]["id"] for name in names])
            created.append(repo.create_issue(data.model_dump()))
        repo.create_comment(created[2]["id"], "La proposition est prête pour une dernière lecture. Les libellés restent visibles en plus des couleurs.")
        repo.create_comment(created[3]["id"], "Conserver le titre du ticket dans le message de confirmation.")
        repo.create_comment(created[7]["id"], "Premier essai réalisé à 390 pixels ; les métadonnées secondaires passent sur une seconde ligne.")
        connection.execute("INSERT INTO seed_runs VALUES (?, ?)", (SEED_NAME, timestamp()))
        return True


if __name__ == "__main__":
    if production():
        raise SystemExit("Le jeu de démonstration est réservé au développement ; aucune donnée n’a été écrite.")
    try:
        applied = seed_database(Database(database_path()))
        print("Démonstration créée : 3 projets, 16 tickets, 5 étiquettes et 3 commentaires." if applied else "Démonstration déjà appliquée ; aucune modification.")
    except ValueError as error:
        raise SystemExit(str(error)) from error
