# Circular — implémentation issue de l’audit

État du **16 octobre 2026**. Ce document décrit les adaptations réalisées à partir du [relevé Linear](observation-linear.md), qui reste une observation historique distincte. Le code reste propre à Circular, avec React/TypeScript, FastAPI en couches et SQLite. L’identité graphite/jaune et l’exécution locale sans compte ni service cloud sont conservées.

## Fonctions raccordées à la persistance

| Chantier de l’audit | État implémenté | Portée précise |
| --- | --- | --- |
| Paramètres | Page Préférences, Étiquettes, Modèles | Accueil, trois tailles de texte, deux densités, réduction des animations, touche d’envoi des commentaires ; sauvegarde serveur |
| Affichage | Options séparées des filtres | Liste groupée par statut/projet/priorité/aucun ; tri et direction ; huit propriétés configurables ; groupes repliables et vides configurables |
| Tableau | Colonnes de statut, repli et masquage | Glisser-déposer et sélecteur clavier enregistrent le statut ; réaffichage des colonnes ; pas d’ordre manuel entre cartes |
| Filtres | Recherche, projet, statuts/priorités multiples, étiquettes, favoris | ET entre catégories, OU entre valeurs d’une catégorie, y compris étiquettes ; même résultat de base en liste/tableau |
| Vues enregistrées | Création, ouverture, mise à jour/renommage, suppression | Instantané nommé des filtres et de l’affichage ; supprimer une vue conserve les tickets |
| Favoris et commandes | Étoiles et entrée Favoris ; palette Ctrl/⌘+K | Favoris persistants ; recherche de tickets et navigation vers les commandes/vues existantes |
| Détail et liens | Panneau ou mode page, URL locale directe | Copie d’identifiant/lien et erreurs presse-papiers ; contexte d’affichage conservé à la fermeture |
| Étiquettes | Création, recherche, modification, suppression | Nom, couleur, description ; retrait des associations et références de filtres lors de la suppression |
| Modèles | Création, recherche, modification, suppression | Préremplissage titre/description/projet facultatif/statut/priorité/étiquettes ; aucun ticket créé au choix d’un modèle |
| Création répétée | Option Créer un autre | Enregistre puis vide titre/description, conserve les autres champs et replace le focus |
| Duplication | Action du détail | Nouvel identifiant, champs de la version enregistrée, suffixe « (copie) » ; sans commentaires, ancien historique ni favori |
| Commentaires | Création, modification, suppression | Saisie conservée sur erreur ; confirmation de suppression ; raccourci d’envoi configurable |
| Historique | Journal serveur dans le détail | Création, champs de ticket modifiés et opérations de commentaires, enregistrés dans la transaction métier |
| Échéances et projets | Date facultative sur ticket/projet et statut de projet | Dates civiles validées ; cinq statuts de projet fixes ; pas de changement automatique du statut des tickets |

Le tri couvre création, modification, titre, priorité et échéance. Les dates absentes sont placées après les dates renseignées. Les menus de propriétés portent sur l’identifiant, le statut, la priorité, le projet, les étiquettes, la création, la modification et l’échéance. La configuration des colonnes du tableau n’altère pas le statut des tickets masqués.

## Persistance et migration

Les données métier et de personnalisation restent dans `data/circular.sqlite`, ou dans le fichier désigné par `CIRCULAR_DB`. Aucun localStorage ne remplace la persistance serveur. Les réglages d’affichage/filtres sont sauvegardés au fil des changements ; l’interface signale les échecs et permet de réessayer. Les préférences générales, modèles, étiquettes, vues et formulaires métier sont enregistrés par leurs commandes explicites.

La migration [002_preferences_workflows.sql](../backend/app/db/migrations/002_preferences_workflows.sql) est appliquée automatiquement au démarrage ou par `npm run migrate`. Le registre de versions rend les relances idempotentes. Elle conserve la base existante, ajoute les tables nécessaires et initialise les nouvelles colonnes avec des valeurs compatibles : statut Planifié des projets, échéances absentes et favoris désactivés. Une copie facultative de la base peut être réalisée backend arrêté ; aucune réinitialisation ni réinstallation de dépendances n’est requise pour cette extension.

Le journal commence aux nouvelles opérations après migration. Il ne reconstitue pas les événements passés et ne conserve pas les anciennes valeurs complètes. Un ticket créé après migration possède son propre événement de création ; la suppression du ticket entraîne celle de ses commentaires et de son journal. L’édition d’un commentaire conserve son horodatage de création et consigne l’opération de modification dans le journal.

## Vérifications de cette extension

La validation finale a été exécutée le **16 octobre 2026**, après correction des régressions. Les résultats historiques dans [validation.md](validation.md) restent distincts de cette extension.

| Vérification finale | Commande | Résultat |
| --- | --- | --- |
| API et persistance | `.venv/Scripts/python.exe -m pytest tests -q --basetemp=.test-data/final-api --tb=short` | **73 tests réussis**, 6,20 s ; un avertissement de dépréciation Starlette/httpx |
| TypeScript et build frontend | `npm run build` | **Réussi** ; bundle final `index-BGJXGcpF.js` |
| Parcours navigateur Chrome | `node node_modules/@playwright/test/cli.js test --reporter=list` | **24 tests réussis**, 38,1 s, deux workers |
| Régression préférences et commentaires | Deux parcours ciblés, `--repeat-each=3` | **6 exécutions réussies**, 18,1 s |
| Application livrée | `npm start`, GET `/`, `/api/health`, `/api/settings` et bundle final | **HTTP 200**, santé `ok: true`, accessible sur `http://127.0.0.1:4310/` |

La suite API comprend le socle et `tests/test_extensions.py` pour les réglages, vues, filtres, tri, modèles, duplication, étiquettes, commentaires, activité, dates, contraintes et migration. Les parcours navigateur ajoutés couvrent paramètres/affichage, navigation/vues, création/modèles/duplication/commentaires et erreurs asynchrones. Les fixtures utilisent leurs propres bases SQLite et processus FastAPI, sans toucher à la base utilisateur. Chaque parcours contrôle les requêtes externes et les exceptions JavaScript : aucune détectée. Un build récent est nécessaire avant les tests navigateur. `npm test` et `npm run test:e2e` sont les raccourcis documentés pour relancer les suites.

Les critères de livraison sont les opérations réelles dans l’interface, leurs résultats après actualisation/redémarrage, la conservation des données en cas d’erreur et la suppression effective des enregistrements. La compilation seule ne suffit pas à les valider.

### Captures inspectées

Captures produites par les parcours Chrome avec des données fictives et réellement ouvertes pour inspection : [préférences à 1440 px](images/implementation-settings.png), [liste groupée par projet à 1440 px](images/implementation-list.png), [navigation et liste à 390 px](images/implementation-mobile.png). Elles illustrent Circular, pas le compte Linear observé.

## Limites conservées

- Les workflows de tickets et les catégories de statut de projet sont fixes. Leur personnalisation, les sous-tickets et relations/blocages restent une tranche distincte.
- Le thème reste sombre graphite/jaune ; il n’y a pas de thème clair/système, d’éditeur de raccourcis ou de réorganisation complète de la barre latérale.
- Pas de filtres booléens imbriqués, de tri manuel des cartes, de sélection/mutation en masse, d’archivage, de restauration d’anciennes versions ou de brouillons persistants.
- Pièces jointes, texte riche, récurrence, estimations, releases, équipes, comptes, collaboration, intégrations et agents cloud restent hors périmètre.
- Les listes ne sont pas paginées ; les volumes importants ne sont pas évalués. La palette affiche au maximum vingt tickets à la fois parmi les résultats de recherche.
- Vérification sous Windows/Chrome, avec viewport mobile de 390 px. Firefox, Safari, les autres systèmes et un téléphone physique ne sont pas validés.
- Les liens pointent vers l’application locale sur cet appareil. La copie dépend des autorisations presse-papiers du navigateur et retourne une erreur explicite si elle échoue.

L’[architecture](architecture.md) détaille les responsabilités des couches et la [spécification](specification.md) fixe la sémantique des interactions. Les commandes exactes d’installation, de lancement et de test restent dans le [README](../README.md).
