# Références internes, backlinks et recherche — lot 4

Cadrage et [maquette HTML](mockups/liens.html) validés le 22 novembre 2026 dans la conversation Circular. La maquette couvre la palette dans les modes visuel et source, les homonymes, la recherche, les backlinks, les liens Circular et les états vide ou indisponible.

## Références internes

- La palette `[[` recherche les titres dans l’espace courant. Le fil d’Ariane complet distingue les pages homonymes. Les flèches permettent de choisir un résultat, Entrée l’insère et Échap ferme la palette.
- `[](/pages/{uuid})` garde un libellé automatique qui suit le titre actuel de la cible. `[Libellé](/pages/{uuid})` conserve le libellé saisi. Le lien garde le même UUID quand la page est renommée ou déplacée. Les cibles indisponibles sont signalées sans exposer leur titre.
- L’index est dérivé de la source Markdown. Le parseur exclut les références contenues dans les fragments et blocs de code. Un couple source-cible ne produit qu’un backlink, quel que soit le nombre d’occurrences. L’index est mis à jour dans la transaction de sauvegarde ou de restauration.
- Une nouvelle référence vers une page introuvable ou située hors de l’espace renvoie `422`. La migration préserve à l’identique les sources existantes et indexe uniquement les références valides. Une référence ancienne devenue indisponible reste dans la source.
- Un lien vers un ticket Circular est un lien HTTP ou HTTPS avec un libellé choisi. L’ouverture utilise les permissions du service Circular.

## Recherche et droits

Les recherches filtrent d’abord les espaces accessibles puis cherchent le terme dans le titre et le texte Markdown. La casse Unicode est ignorée. Une requête vide renvoie une liste vide. Les titres correspondants précèdent les résultats trouvés dans le corps. À rang égal, les pages sont triées par date de modification décroissante puis UUID croissant. Les extraits sont en texte brut et le curseur opaque reprend cet ordre.

Les suggestions et les backlinks vérifient les droits au moment de la requête. Une révocation donne une réponse `404` sur ces ressources et retire la page des résultats globaux à la requête suivante.

| Route | Résultat |
| --- | --- |
| `GET /api/search?q=…` | Pages accessibles qui correspondent au terme |
| `GET /api/workspaces/{espace}/link-suggestions?q=…` | Pages suggérées de l’espace, avec fil d’Ariane |
| `GET /api/pages/{page}/backlinks` | Pages de l’espace qui pointent vers la cible |
| `GET /api/pages/{page}` | Données du lot 3 et titres actuels des références résolues |

Sources consultées le 22 novembre 2026. [Spécification DOC-03, DOC-04, DOC-05 et DOC-08](../knowledge-workspace-spec.md) · [Plan du lot 4](../knowledge-workspace-implementation-plan.md#lot-4--références-internes-backlinks-et-recherche) · [Contrat du lot 3](edition.md) · [Analyse Markdown côté serveur](https://markdown-it-py.readthedocs.io/en/latest/using.html)

## Recette locale du 22 novembre 2026

- `npm test` du service : 24 réussis, 0 échec, 0 ignoré sur PostgreSQL. Les quatre nouveaux tests couvrent la reprise de l’existant, l’index des homonymes, la restauration, le rejet atomique des nouvelles références indisponibles et les droits sur les trois surfaces de découverte.
- `npm run build` : TypeScript et Vite réussis. Les avertissements récurrents sur Tiptap et la taille de son module chargé à la demande restent visibles.
- `npm run test:e2e` : 6 réussis, 0 échec, 0 ignoré dans Chromium. Les deux nouveaux parcours couvrent la sélection dans les modes visuel et source, les libellés, une URL de ticket, les backlinks, la recherche et la révocation à 390 px.
- Les quatre mutations API et deux mutations navigateur ont déclenché les échecs attendus. Les fichiers ont été restaurés et comparés avant les trois relances finales.
- Preuve indépendante : une requête SQL dans PostgreSQL a relevé un seul couple source-cible malgré deux occurrences et aucun couple pour une référence dans le code. Dans Chromium, le lien a gardé son UUID après renommage et déplacement. Après révocation, la recherche n’a renvoyé aucun résultat et les suggestions et backlinks ont renvoyé `404`.
