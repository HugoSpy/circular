# Vérifications de Circular

**Version multi-utilisateur du 28 octobre 2026 : voir [production-validation.md](production-validation.md).** Les résultats ci-dessous restent l’historique des livraisons locales et ne décrivent pas seuls la version actuelle.

Environnement : Windows, Node.js 22.12.0, Python 3.12.14, navigateur Chrome déjà installé. Aucun outil ou navigateur installé globalement.

## Provenance des observations

Au démarrage de la tâche le 15 octobre 2026, le catalogue d’outils ne proposait aucun outil REA et `Get-Command rea` ne trouvait pas la CLI. `GET http://127.0.0.1:9222/json/version` a d’abord été bloqué par le sandbox, puis a renvoyé une connexion refusée lors de l’essai avec accès local. Aucune page Linear ni aucun comportement Linear n’avait alors été observé. Les tests ci-dessous concernent uniquement Circular et ses données fictives.

Le **16 octobre**, une observation directe a été effectuée avec **Computer Use dans Opera GX**, sans REA. Le [relevé détaillé](observation-linear.md) consigne les interactions réellement observées et leurs limites. Cette étape a modifié uniquement la documentation : les tests API/E2E ci-dessous n’ont pas été réexécutés pour ce relevé.

## Première tranche — effectuée avant extension

- Test API : **1 passé**. Création projet, création ticket, fermeture/réouverture de l’application et du fichier SQLite, ticket retrouvé et compteur projet exact.
- Test Chrome : **1 passé**. Projet et ticket créés par leurs formulaires, identifiant affiché, actualisation, ticket encore visible. Garde réseau : aucun appel HTTP externe ; aucune exception JavaScript observée.
- Build React : TypeScript et Vite réussis. Le premier lancement Vite sous sandbox avait échoué sur `realpath` Windows (EPERM) ; la relance avec accès au dossier a réussi.
- `npm run migrate` exécuté avec succès sur la base locale.

Les tests Python utilisant TestClient requéraient ici un accès hors sandbox, car le sandbox Windows bloquait le socket interne de la boucle asyncio. Cela n’a nécessité aucune modification de configuration du système.

## Validation de la première version

| Vérification réellement exécutée | Résultat |
| --- | --- |
| `.venv/Scripts/python.exe -m pytest tests/test_api.py -q --basetemp=.pytest-backend-final` | **34 tests réussis**, avec les cas Unicode et les schémas OpenAPI finaux |
| `npm run build` (TypeScript puis Vite) | Réussi après les dernières modifications frontend |
| `node node_modules/@playwright/test/cli.js test` | **9 parcours réussis**, 14,7 s, 2 workers Chrome |
| Relances ciblées des parcours modification/commentaires, mutation lente et clavier | **2 + 2 tests réussis**, 6 s pour chaque relance, après ajout des assertions et dernières corrections de focus |
| `npm run migrate`, `npm run seed` | Réussis ; démonstration de 3 projets, 16 tickets, 5 étiquettes et 3 commentaires |
| `npm start`, GET `/`, GET `/api/health` | Page HTTP 200 et API opérationnelle sur 4310 |
| `npm run dev`, GET `/` et `/api/health` via Vite, GET `/api/projects` | HTTP 200 sur 5173, proxy FastAPI opérationnel, 3 projets retournés |
| Arrêt par Ctrl+C | Les deux ports 4310 et 5173 ne répondent plus ; serveurs E2E arrêtés par leurs fixtures |

### Couverture API

Création/modification/suppression projets et tickets ; préfixes immuables et refus de suppression d’un projet non vide ; étiquettes et commentaires ; filtres cumulés ; recherche titre/description/identifiant, Unicode et caractères `%`/`_` littéraux ; entrées invalides sans effets secondaires ; transactions annulées sur erreur ; identifiants monotones malgré suppression, déplacement et recréation d’un préfixe ; allocations concurrentes ; cascades de suppression ; réouverture du fichier ; migrations/seed idempotents et collisions de seed sans perte de données ; Host/Origin/JSON/taille des corps ; CSP, fichiers statiques et 404 ; description de 20 000 emojis acceptée dans la limite de 128 Kio ; schémas OpenAPI locaux.

### Neuf parcours navigateur

1. Création projet et ticket via formulaires, identifiant affiché et actualisation.
2. Modification de ticket, commentaire, arrêt et redémarrage réel du processus FastAPI, vérification des valeurs ; suppression puis second redémarrage pour vérifier l’absence du ticket.
3. Déplacement avec `dragTo` entre colonnes, puis actualisation ; changement de statut au clavier via le select de la carte.
4. Recherche par titre, identifiant et description ; filtres projet/statut/priorité cumulés et réinitialisation.
5. Création par `C`, focus initial, absence de déclenchement pendant la saisie, `/`, `Ctrl+Entrée`, protection des modifications sur Échap et restitution du focus.
6. Parcours à largeur 390 px : création, détail, tableau et absence de débordement horizontal de la page.
7. Arrêt effectif du backend pendant un formulaire ; erreur affichée, saisie conservée, relance puis sauvegarde réussie.
8. Renommage projet, préfixe immuable, refus de suppression non vide puis suppression projet vide ; création/affectation d’étiquette et persistance après redémarrage.
9. PATCH de statut volontairement retardé, changement de filtre avant sa réponse : les résultats restent ceux du filtre courant. Carte et ligne inaccessibles pendant la mutation pour éviter de charger un état périmé.

Chaque scénario utilise un fichier SQLite isolé et un processus backend dédié. Le garde réseau intercepte les requêtes HTTP émises par les pages : **aucune requête externe et aucune exception JavaScript détectée**. Les tests n’accèdent pas au profil Chrome personnel.

### Inspection visuelle et corrections

Captures réellement ouvertes et inspectées : liste, tableau, panneau de détail à 1440 px ; liste mobile à 390 px. Le contrôle complémentaire du navigateur a retourné `horizontalOverflow: false`, sans erreur JavaScript ni requête externe. Les captures de démonstration sont conservées localement dans `.test-data/circular-{list,board,detail,mobile}.png` (répertoire ignoré).

Corrections effectuées puis vérifiées : focus initial des dialogues, restauration du focus après rafraîchissement, protection de l’ouverture d’un ticket pendant une mutation, rafraîchissement utilisant les filtres actuels, gel des champs pendant sauvegarde, messages d’erreur réseau en français. Deux échecs initiaux de tests provenaient de sélecteurs trop larges sur des champs remplis ; ils ont été remplacés par des rôles et noms accessibles exacts.

## Limites restantes

- Aucune observation de Linear via REA : limite détaillée dans la spécification. Les tests Chrome de Circular ne constituent pas une observation de la référence.
- Validation effectuée sur Windows/Chrome. Les commandes macOS/Linux, Firefox, Safari et un téléphone physique n’ont pas été testés. Le contrôle mobile utilise un viewport Chrome de 390 px.
- Application mono-utilisateur locale : absence volontaire de comptes, collaboration, intégrations, texte riche et pièces jointes. La liste n’est pas paginée ; les gros volumes n’ont pas été évalués.
- Un avertissement de dépréciation de la combinaison Starlette/httpx est émis pendant pytest ; les 34 tests passent. Les versions installées sont figées dans `requirements-dev.lock`.

Les serveurs de vérification de cette première version ont été arrêtés à sa livraison. Le build et la base de démonstration sont conservés ; `npm start` relance l’application.

## Refonte UI/UX graphite et jaune — 15 octobre 2026

La refonte demandée avec `front-maxer` a été auditée puis implémentée. Le [rapport UI/UX](audit-ui-ux.md) contient les mesures et les captures avant/après.

| Vérification exécutée après refonte | Résultat |
| --- | --- |
| `npm test` | **34 tests réussis**, 2,57 s ; même avertissement Starlette/httpx |
| `npm run build` | TypeScript et Vite réussis après la dernière correction CSS |
| `node node_modules/@playwright/test/cli.js test` | **11 tests réussis**, 17 s |
| Relance ergonomie desktop/mobile et parcours mobile après correction de la grille | **3 tests réussis**, 5,9 s |
| Liste, tableau, création, détail, projets à 320/390/768/1024/1440 px | Aucun débordement horizontal du document ou dialogue ; défilement du tableau contenu |
| Mouvement réduit | Durée de transition calculée : `0s` |
| Garde réseau et erreurs navigateur | Aucun HTTP externe, aucune exception JavaScript |

Les deux nouveaux parcours vérifient la lisibilité et la taille des commandes, la navigation clavier avec focus visible, l’absence de focus sur le fond pendant un dialogue, le retour du focus, le raccourci vers le commentaire et sa publication, et les cibles tactiles. Le test mobile protège également contre une grande zone vide avant le premier ticket sur une base peu remplie.

Les tests gardent leurs bases et processus isolés. Aucun changement du backend, de la migration ou des données de démonstration n’a été nécessaire. Le serveur d’application local sur 4310 est laissé accessible pour examiner cette refonte, et l’onglet déjà ouvert a été actualisé. Les serveurs propres aux tests sont arrêtés par leurs fixtures.

## Ajouts fonctionnels issus de l’observation — 16 octobre 2026

Le [bilan d’implémentation](implementation-audit.md) détaille les fonctionnalités livrées et leurs limites. Cette phase ajoute du code frontend/backend, une migration et des tests ; elle est distincte du relevé historique dans Opera GX.

| Vérification effectivement exécutée | Résultat final |
| --- | --- |
| `.venv/Scripts/python.exe -m pytest tests -q --basetemp=.test-data/final-api --tb=short` | **73 tests réussis**, 6,20 s ; un avertissement Starlette/httpx |
| `npm run build` | **Réussi** après la dernière correction de persistance ; TypeScript et Vite, bundle `index-BGJXGcpF.js` |
| `node node_modules/@playwright/test/cli.js test --reporter=list` | **24 parcours réussis**, 38,1 s, deux workers Chrome |
| Deux parcours ciblés de commentaires/préférences, répétés trois fois | **6 exécutions réussies**, 18,1 s, avant la suite globale finale |
| `npm start`, GET `/`, `/api/health`, `/api/settings` et bundle final | **HTTP 200**, santé `ok: true` ; serveur laissé actif sur 4310 |

La couverture ajoutée comprend les préférences sauvegardées et relues après redémarrage, la gestion des étiquettes et modèles, les filtres multiples, le tri/groupement/propriétés, les colonnes repliées/masquées, les vues nommées créées/modifiées/supprimées, les favoris, la palette au clavier, les liens locaux et le mode page, la création successive, la duplication, les échéances/statuts de projets, les commentaires édités/supprimés et leur historique. Les parcours vérifient également les erreurs réseau, la conservation de saisie et les confirmations d’abandon. Les arrêts/redémarrages des backends de test sont réels, avec réutilisation du même fichier SQLite.

Les premières exécutions ont révélé des régressions de focus, de disposition mobile, de glisser-déposer et de sauvegarde des préférences. Elles ont été corrigées avant l’exécution globale finale. En particulier, une sauvegarde de filtre n’envoie plus toutes les préférences : seuls les champs concernés sont transmis. Un test dédié vérifie qu’une préférence modifiée ailleurs n’est pas écrasée, y compris après un échec de sauvegarde puis un réessai.

Les 24 parcours utilisent des bases fictives et isolées, sans profil Chrome personnel. Le garde réseau et le contrôle des exceptions JavaScript sont actifs sur chaque parcours : **aucune requête HTTP externe et aucune exception JavaScript détectée**. Le processus applicatif local utilise la base existante, migrée automatiquement, sans réinitialisation ni réinjection des données de démonstration.

Captures réellement inspectées : [paramètres à 1440 px](images/implementation-settings.png), [liste groupée à 1440 px](images/implementation-list.png) et [navigation/liste à 390 px](images/implementation-mobile.png). Les tests contrôlent l’accessibilité des commandes, le focus et l’absence de débordement horizontal de la page sur le viewport mobile.

Limites de validation : Windows/Chrome uniquement ; mobile simulé à 390 px, pas de téléphone physique, Safari ou Firefox. Les volumes importants ne sont pas évalués. Aucune dépendance supplémentaire ni configuration globale n’a été installée ou modifiée pour cette extension.
