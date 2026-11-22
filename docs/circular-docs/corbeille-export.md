# Corbeille et export Markdown — lot 5

Cadrage et [maquette HTML](mockups/corbeille-export.html) validés le 22 novembre 2026 dans la conversation Circular. La maquette couvre le parcours de mise à la corbeille, la restauration à la racine, le lien indisponible, le téléchargement en mode lecteur et la relance après un échec, sur ordinateur et mobile.

## Corbeille

- Le propriétaire et les éditeurs peuvent mettre une page et ses descendants actifs à la corbeille. La confirmation avertit que le sous-arbre disparaîtra de la navigation, de la recherche et des exports.
- PostgreSQL rattache les pages emportées à une opération contenant la page racine, le parent d’origine, l’auteur et l’horodatage. Le verrou d’écriture de l’espace sérialise la corbeille et la restauration avec les déplacements, les sauvegardes et les modifications de rôles.
- Les pages de chaque opération restent groupées. Restaurer un parent laisse en corbeille les pages supprimées dans une opération antérieure. Si le parent d’origine est indisponible lors de la restauration, le sous-arbre retrouve la racine de l’espace. Il conserve ses identifiants, ses contenus Markdown et ses révisions.
- La corbeille masque aussi l’accès direct, les suggestions, l’historique et les backlinks des pages concernées. Les liens entrants signalent la cible indisponible. La restauration les réactive parce que l’index garde les couples source-cible existants.
- La durée de rétention et la suppression définitive restent à définir pour le pilote.

## Export Markdown

Depuis l’accueil de l’espace, tout membre actuel peut télécharger le ZIP. L’API lit l’adhésion et les pages actives dans le même instantané PostgreSQL. Une demande d’un membre révoqué reçoit `404`. Un espace vide produit un ZIP valide sans fichiers.

Les fichiers sont en Markdown UTF-8. L’export construit les chemins avant d’écrire le ZIP. Chaque nom part du titre normalisé en NFC, nettoyé et tronqué à 80 octets avant ajout d’un suffixe UUID. Le suffixe utilise huit caractères hexadécimaux et s’allonge à l’UUID complet en cas de préfixe partagé. Le Markdown de la page parente et le dossier de ses sous-pages partagent le même nom de base.

L’export réécrit les liens internes en chemins relatifs encodés. Le libellé automatique devient le titre de la cible. Une cible absente donne un libellé en texte suivi de « (page indisponible) ». Les URL externes et Circular gardent leur destination et les liens dans le code restent du texte. Les sources stockées restent identiques. Les documents qui contiennent des liens internes peuvent changer de mise en forme Markdown pendant la réécriture.

Le navigateur prépare le téléchargement et affiche une action de relance en cas d’erreur. Il reçoit le ZIP complet avant de lancer le téléchargement. Le lot de recette vérifiera le volume représentatif du pilote.

| Route | Résultat |
| --- | --- |
| `POST /api/pages/{page}/trash` | `201` avec identifiant d’opération et nombre de pages placées en corbeille |
| `GET /api/workspaces/{espace}/trash` | Liste paginée des opérations à restaurer |
| `POST /api/workspaces/{espace}/trash/{operation}/restore` | Identifiant de la racine, nombre de pages restaurées et indication de retour à la racine |
| `GET /api/workspaces/{espace}/export` | Archive `application/zip` en pièce jointe, avec `Cache-Control: no-store` |

Sources consultées le 22 novembre 2026. [Spécification DOC-03, DOC-05, DOC-06 et DOC-07](../knowledge-workspace-spec.md) · [Plan du lot 5](../knowledge-workspace-implementation-plan.md#lot-5--corbeille-et-export-markdown) · [Documentation de zipfile](https://docs.python.org/3/library/zipfile.html)

## Recette locale du 22 novembre 2026

- `npm test` du service — 28 réussis, 0 échec et 0 ignoré sur PostgreSQL. Les quatre nouveaux tests couvrent le masquage des surfaces actives, la reprise des liens, les suppressions imbriquées, la restauration à la racine, un déplacement concurrent, le ZIP et la révocation des droits.
- `npm run build` — TypeScript et Vite réussis. Les avertissements récurrents sur Tiptap et la taille du module chargé à la demande sont visibles dans la sortie de compilation.
- `npm run test:e2e` — 8 réussis, 0 échec et 0 ignoré dans Chromium. Les deux nouveaux parcours vérifient l’usage au clavier, le focus, le lien indisponible, la restauration à la racine et la relance d’un téléchargement pour un lecteur à 390 px.
- Les quatre mutations API et les deux mutations navigateur ont déclenché les échecs attendus. Les sources ont été restaurées et comparées avant les relances finales.
- `unzip -t` et extraction indépendante du ZIP renvoyé par l’API — trois fichiers aux titres Unicode identiques, deux liens relatifs résolus dans les deux sens et destinations Circular et externe conservées.
