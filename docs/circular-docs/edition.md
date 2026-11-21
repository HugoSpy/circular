# Éditeur Markdown, sauvegarde et révisions — lot 3

Cadrage et [maquette HTML](mockups/edition.html) validés le 22 novembre 2026 dans la conversation Circular. La maquette couvre les modes visuel et source, la lecture seule, l’autosauvegarde, la reprise, la comparaison lors d’un conflit et la restauration sur ordinateur et mobile. Le code de ce lot appartient au service distinct Circular Docs.

## Contrat Markdown

La source Markdown UTF-8 est la représentation de référence. Elle est limitée à 256 Kio par page. Le mode visuel couvre les paragraphes, titres, mises en gras et italiques, listes ordonnées et à puces, listes de tâches, citations, liens, code en ligne et blocs de code. La conversion utilise Tiptap et compare les arbres Markdown avec un analyseur CommonMark/GFM avant d’ouvrir le mode visuel. Un aller-retour sans modification conserve la source exacte.

Les éléments non représentables passent en mode source avec un message explicite. Le HTML brut reste du texte source. Le mode visuel accepte les liens HTTP, HTTPS et `/pages/{uuid}`. Les références `[](/pages/{uuid})` et `[Libellé](/pages/{uuid})` sont préservées. La sélection, la résolution et l’indexation des liens internes sont prévues au lot 4.

## Révisions et sauvegarde

- Une page commence à la révision 1. La migration crée un instantané initial pour les pages existantes. L’auteur est inconnu pour ces instantanés repris.
- Une modification de titre ou de corps crée un instantané immuable et attribué au compte qui a enregistré. Une sauvegarde identique conserve le numéro courant. Le déplacement dans l’arborescence conserve la révision de contenu. Restaurer un instantané antérieur ajoute une nouvelle révision et conserve le parent courant.
- Une sauvegarde ou une restauration transporte `expectedRevision` et `requestId`. Après contrôle des droits, une même requête rejouée retourne son résultat initial. Un identifiant réutilisé avec un contenu différent et une révision périmée renvoient `409`. La réponse contient la dernière version autorisée dans `error.latest`.
- L’autosauvegarde démarre après 700 ms sans modification. Après une erreur, le brouillon reste dans la page. La reprise réutilise l’identifiant de la tentative. Les saisies effectuées pendant la requête sont conservées pour la suivante. L’interface avertit avant de quitter une page avec un brouillon. En cas de conflit, l’utilisateur compare le brouillon à la dernière version et choisit la version à reprendre.
- Les propriétaires et éditeurs consultent et restaurent l’historique. Les lecteurs consultent le contenu actuel. Les droits d’accès sont vérifiés avant chaque lecture ou rejeu.

| Méthode et chemin | Contrat |
| --- | --- |
| `GET /api/pages/{page}` | Données d’arborescence, titre, Markdown et révision |
| `PATCH /api/pages/{page}` | `parentId` seul pour déplacer. `title` ou `markdown`, avec `expectedRevision` et `requestId`, pour modifier le contenu |
| `GET /api/pages/{page}/revisions` | Historique paginé, révision la plus récente en premier |
| `GET /api/pages/{page}/revisions/{revision}` | Instantané de la révision |
| `POST /api/pages/{page}/revisions/{revision}/restore` | Restaurer avec `expectedRevision` et `requestId` |

Sources consultées le 22 novembre 2026. [Spécification DOC-02 et DOC-06](../knowledge-workspace-spec.md) · [Plan du lot 3](../knowledge-workspace-implementation-plan.md#lot-3--éditeur-markdown-sauvegarde-et-révisions) · [CommonMark 0.31.2](https://spec.commonmark.org/0.31.2/) · [Listes de tâches GFM](https://github.github.com/gfm/#task-list-items-extension-) · [Tiptap Markdown](https://tiptap.dev/docs/editor/markdown)

## Recette locale du 22 novembre 2026

- `npm test` du service : 20 réussis, 0 échec, 0 ignoré sur PostgreSQL. Les cinq nouveaux tests couvrent la migration, la concurrence et le rejeu, les droits sur l’historique, la restauration et la limite UTF-8. Deux scénarios d’espaces existants ont été adaptés au contrat versionné du renommage. Les intégrations Authlib et Starlette émettent deux avertissements httpx.
- `npm run build` : TypeScript et Vite réussis. Vite signale la directive React de Tiptap et la taille du module visuel chargé à la demande (environ 188 Kio compressés).
- `npm run test:e2e` : 4 réussis, 0 échec, 0 ignoré. Les deux nouveaux parcours couvrent la conversion Markdown, le repli source, la reprise après réponse perdue, la comparaison des brouillons, l’avertissement de navigation et la restauration.
- Les sept mutations API et deux mutations navigateur ont provoqué les échecs attendus. Les fichiers ont été restaurés et comparés à leurs originaux avant les trois relances finales.
- Preuve indépendante : deux sessions ont obtenu `200` et `409` sur la même révision. Une requête SQL a compté un seul instantané ajouté après le rejeu. Un parcours Chromium a reproduit la perte de réponse après validation par le serveur et vérifié la conservation du brouillon.
