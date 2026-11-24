# Espaces privés, invitations et arborescence — lot 2

Cadrage et [maquette HTML](mockups/espaces.html) validés le 22 novembre 2026 dans la conversation Circular. La maquette couvre la navigation, le fil d’Ariane, les invitations, les rôles et les états vide, expiré et révoqué. Le code de ce lot appartient au service distinct Circular Docs. Ce document complète le [contrat d’identité](identite.md).

## Accès et invitations

- La création d’un espace et de l’adhésion propriétaire s’effectue dans une transaction. Le propriétaire gère le nom de l’espace, les adhésions et les invitations. Les éditeurs modifient l’arborescence. Les lecteurs consultent les pages. La modification et le retrait de l’adhésion propriétaire sont interdits.
- Une invitation désigne l’UUID d’un compte EPITA actif déjà provisionné. Elle s’affiche dans l’application, attribue le rôle lecteur ou éditeur et expire après 168 heures. Une seule invitation en attente est possible par compte et par espace. Une nouvelle invitation peut remplacer une invitation expirée. Le propriétaire peut révoquer une invitation en attente.
- Seul le compte désigné peut accepter. Une acceptation rejouée renvoie l’adhésion actuelle si elle existe. Une invitation acceptée précédemment ne permet jamais de rétablir une adhésion retirée. Une invitation expirée renvoie `410` à son destinataire. Une invitation révoquée ou inconnue renvoie `404`.
- Une requête sans session valide reçoit `401`. En l’absence de droit de lecture, une ressource privée produit le même `404` qu’une ressource absente. Une action interdite à un membre sur une ressource visible reçoit `403`. Les requêtes de mutation exigent l’origine du service.

## Arborescence

- Une URL `/pages/{uuid}` reste stable après renommage ou déplacement. Le fil d’Ariane est calculé à partir des parents enregistrés.
- Une page racine a un parent nul. La clé étrangère composite impose qu’un parent appartienne au même espace. Les titres doublons sont autorisés. Les pages sœurs sont triées par titre exact sous la collation PostgreSQL `C`, puis par UUID. Les noms et titres sont limités à 160 caractères après suppression des espaces en début et en fin.
- Les mutations d’un espace prennent le verrou exclusif de sa ligne avant de revérifier l’adhésion et de lire l’arborescence. Une destination qui créerait un cycle renvoie `409`. Un parent absent ou situé dans un autre espace renvoie `404`.

## API du lot

| Chemin | Méthodes | Usage |
| --- | --- | --- |
| `/api/workspaces` | GET, POST | Lister ses espaces ou créer un espace privé |
| `/api/workspaces/{espace}` | GET, PATCH | Consulter ou renommer un espace |
| `/api/workspaces/{espace}/members` | GET | Lister les membres pour le propriétaire |
| `/api/workspaces/{espace}/members/{compte}` | PATCH, DELETE | Modifier un rôle ou retirer une adhésion |
| `/api/workspaces/{espace}/invitations` | GET, POST | Lister les invitations en attente ou inviter un compte |
| `/api/workspaces/{espace}/invitations/{invitation}` | DELETE | Révoquer une invitation |
| `/api/invitations` | GET | Lister les invitations reçues, avec leur état |
| `/api/invitations/{invitation}/accept` | POST | Accepter une invitation |
| `/api/workspaces/{espace}/pages` | GET, POST | Lister les racines ou les enfants de `parentId`, ou créer une page |
| `/api/pages/{page}` | GET, PATCH | Lire le titre et le fil d’Ariane, renommer ou déplacer |

Les listes utilisent `limit` et `cursor` avec le format commun du lot 1. Le curseur des pages suit le couple titre et UUID. Les autres listes sont ordonnées par UUID. Réutiliser le curseur d’une liste avec les mêmes filtres.

Sources consultées le 22 novembre 2026. [Spécification DOC-01 et DOC-05](../knowledge-workspace-spec.md) · [Plan du lot 2](../knowledge-workspace-implementation-plan.md#lot-2--espaces-invitations-et-arborescence) · [Contrat du lot 1](identite.md)

## Recette locale du 22 novembre 2026

- `npm test` du service : 15 réussis, 0 échec, 0 ignoré sur PostgreSQL. Les cinq nouveaux tests couvrent l’accès avant et après acceptation et révocation, l’expiration et le remplacement d’une invitation, les opérations réservées au propriétaire, la pagination et les déplacements concurrents. Les avertissements httpx de la recette du lot 1 se reproduisent.
- `npm run build` : TypeScript et Vite réussis. `npm run test:e2e` : 2 réussis, 0 échec, 0 ignoré dans Chromium. Le test de session conserve la vérification de déconnexion et le retour du focus. Le nouveau parcours ouvre la même URL avec deux profils, vérifie l’acceptation à 390 px, puis le déplacement et la révocation.
- Les cinq mutations API et les deux mutations navigateur ont déclenché les échecs attendus. Les fichiers originaux ont été restaurés et comparés octet par octet avant la relance finale.
- Preuves indépendantes : le lien direct est passé de `404` à visible puis à `404` dans un navigateur réel. Deux requêtes concurrentes ont donné `200` et `409`. Une requête récursive PostgreSQL après leur exécution a relevé zéro cycle.
- Les parcours utilisent un fournisseur OIDC simulé. La recette Forge ID avec un compte EPITA réel reste ouverte au titre du lot 1.
