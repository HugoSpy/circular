# Recette locale du pilote Circular Docs — lot 6

Cadrage validé le 22 novembre 2026. La recette couvre les six scénarios du premier jalon sur un projet et des comptes fictifs. Elle utilise les applications réelles en local, PostgreSQL pour Circular Docs, et une base SQLite de test pour le ticket Circular. Les tests d’intégration PostgreSQL de Circular ont été vérifiés séparément.

## Résultats du 22 novembre 2026

Circular `4291fdd` et Circular Docs `7a59bd8` ont servi de référence. Les deux applications étaient locales sur macOS 26.6.2 ARM64, avec Chromium sans interface et PostgreSQL 14.20. La recette croisée a utilisé des sessions distinctes de propriétaire, d’éditeur et de lecteur en fenêtres de 1 440 et 390 px.

| Scénario | Preuve locale |
| --- | --- |
| Création et partage | Avant acceptation, le lien direct renvoie le même `404` qu’un UUID inconnu et la décision n’apparaît pas en recherche. Après acceptation, le lecteur ouvre la page et retrouve la décision. Une modification renvoie `403`. |
| Lien, renommage et déplacement | Deux pages de même titre sont distinguées par leur fil d’Ariane. Le lien conserve son UUID après renommage et déplacement. PostgreSQL contient un seul couple source-cible et l’autre page n’a aucun backlink. |
| Sauvegardes concurrentes | À partir de la révision 3, la première sauvegarde crée la révision 4 et l’autre reçoit `409`. Le rejeu conserve exactement les révisions 1 à 4 en base. Le scénario navigateur existant vérifie aussi le brouillon conservé après perte de réponse et lors du conflit. |
| Corbeille et récupération | PostgreSQL relève trois pages dans l’opération. Le lien entrant signale l’indisponibilité. Après restauration, les trois pages et le backlink sont rétablis. Un déplacement du parent sous son enfant renvoie `409` et laisse le parent à la racine. |
| Export et ouverture | Le lecteur télécharge un ZIP. La recette de volume extrait 100 fichiers UTF-8, dont deux homonymes Unicode. Les deux liens relatifs mènent aux fichiers attendus et les destinations Circular et externe sont conservées. Le test API du lot 5 vérifie l’exclusion d’une page en corbeille. |
| Révocation et frontière Circular | Le propriétaire ouvre le ticket depuis Docs. Le lecteur Docs connecté à un compte Circular sans accès ouvre la même URL et voit « Espace inaccessible ». Après révocation de son adhésion Docs, l’accès direct, les backlinks, les suggestions et l’export retournent `404`. La recherche retourne une liste vide. |

Sources consultées le 22 novembre 2026. [Six scénarios d’acceptation](../knowledge-workspace-spec.md#acceptance-scenarios) · [Plan du lot 6](../knowledge-workspace-implementation-plan.md#lot-6--recette-du-pilote) · [Recette du lot 5](corbeille-export.md) · [Parcours croisé](verifier-parcours.mjs)

### Mesures locales

Jeu déterministe de 100 pages actives sur trois niveaux, avec 983 308 octets de Markdown UTF-8. L’archive contrôlée contenait 100 fichiers et pesait 259 322 octets lors de la mesure. Pour chaque largeur et chaque action, deux exécutions ont servi au préchauffage et vingt ont été mesurées. Le p95 correspond à la 19ᵉ valeur de l’échantillon trié.

| Fenêtre Chromium | Recherche, médiane / p95 | ZIP complet, médiane / p95 |
| --- | --- | --- |
| 1 440 px | 299,0 ms / **304,4 ms** | 99,7 ms / **113,0 ms** |
| 390 px | 296,8 ms / **303,0 ms** | 100,5 ms / **114,7 ms** |

La recherche est mesurée de la saisie à l’apparition du résultat attendu. Le ZIP est mesuré du clic jusqu’à la disponibilité du fichier complet. Les deux p95 restent sous les seuils locaux de 1 s et 5 s. Le mode mobile adapte la fenêtre Chromium. Pendant le pilote, refaire les mesures sur les appareils et le réseau réellement utilisés. [Script de mesure et d’extraction](mesurer-recette.mjs)

### Vérification de la recette

- `npm test` de Circular Docs — 28 réussis, 0 échec, 0 ignoré sur PostgreSQL. `npm run build` — réussi. `npm run test:e2e` — 8 réussis, 0 échec, 0 ignoré dans Chromium.
- Les contrôles de publication du commit Circular `4291fdd` avaient donné 168 tests réussis avec PostgreSQL, une compilation réussie et 34 parcours Chromium Linux réussis. Les scripts du lot 6 ajoutent le contrôle croisé et la mesure de volume au dossier de recette. Le code des applications provient des mêmes commits.
- La mutation du lien Circular a remplacé le nom d’espace dans l’URL. Le parcours a échoué sur l’adresse exacte, puis a réussi avec la source restaurée.
- La mutation de l’export a omis le dernier fichier. L’extraction a trouvé 99 fichiers, puis 100 après restauration.
- Les parcours existants de Circular Docs couvrent les sauvegardes, les changements d’arborescence concurrents et les contrôles d’accès sur PostgreSQL. Les avertissements de dépendances Tiptap, Starlette et Authlib apparaissent dans les sorties de compilation ou de tests.

## Reproduire

Installer les dépendances et compiler les deux applications selon leurs guides. Dans Circular, installer Chromium avec `npx playwright install chromium`. Prévoir `initdb`, `pg_ctl`, `psql` et `unzip`. Les scripts utilisent les ports locaux 8000 et 4316. [Démarrage de Circular Docs](README.md) · [Tests Circular](../../README.md#tests)

1. Démarrer un PostgreSQL neuf sur un socket Unix avec l’écoute TCP désactivée. Utiliser une base dédiée et exporter `DOCS_TEST_DATABASE_URL` dans les terminaux de recette. La base reste jetable.
2. Dans Circular Docs, appliquer les migrations et ajouter l’identité fictive `gamma@epita.fr`. Le serveur de recette initialise les identités `alpha` et `beta`.

   ```sh
   DOCS_DATABASE_URL="$DOCS_TEST_DATABASE_URL" .venv/bin/python -m circular_docs migrate
   DOCS_DATABASE_URL="$DOCS_TEST_DATABASE_URL" .venv/bin/python -m circular_docs allow gamma@epita.fr
   .venv/bin/python -m uvicorn tests.browser_app:app --host 127.0.0.1 --port 8000
   ```

3. Dans Circular, démarrer l’application en mode de test avec une nouvelle base SQLite dans un dossier temporaire. L’environnement de ce processus doit être dépourvu de paramètres de production `CIRCULAR_*`.

   ```sh
   circular_recette=$(mktemp -d)
   CIRCULAR_ENV=test CIRCULAR_HOST=127.0.0.1 CIRCULAR_PORT=4316 \
     CIRCULAR_DB="$circular_recette/recette.sqlite" .venv/bin/python -m backend
   ```

4. Dans un troisième terminal, depuis Circular, exécuter `node docs/circular-docs/verifier-parcours.mjs`. Le script crée les comptes et le ticket fictifs, vérifie les statuts et interroge PostgreSQL en lecture sur les données créées.
5. Pour la mesure, redémarrer Circular Docs sur une autre base PostgreSQL neuve. Depuis Circular, exécuter `node docs/circular-docs/mesurer-recette.mjs`. La sortie JSON donne le volume, la preuve d’extraction et les mesures par largeur. Éviter d’exécuter d’autres suites en parallèle.
6. Arrêter les serveurs de recette, puis éliminer les bases et les fichiers de test. Relancer les suites `npm test`, `npm run build` et `npm run test:e2e` dans chaque dépôt pour la vérification habituelle.

## Validation avec l’équipe pilote

L’équipe, le projet et le ticket Circular autorisé restent à confirmer. Il reste à rejouer le parcours avec les personnes habilitées et à confirmer le volume, les mesures et les règles de rétention sur leur environnement. Le résultat local couvre les données fictives du scénario. [Décisions du lot 6](../knowledge-workspace-implementation-plan.md#décisions-à-consigner)
