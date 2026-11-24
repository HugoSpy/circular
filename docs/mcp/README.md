# Connecter un assistant IA à Circular

Dans **Paramètres › Intégrations › Assistants IA**, copiez l’adresse du serveur MCP. Ajoutez-la dans les connecteurs personnalisés de votre assistant, lancez la connexion, puis choisissez un espace dans Circular. L’accès par défaut permet de lister les projets, de rechercher des tickets et de consulter leur détail. Le résultat des outils est transmis à l’assistant.

Pour créer un ticket ou ajouter un commentaire, l’assistant doit demander une nouvelle autorisation. Vérifiez le nom de l’assistant, l’espace et les deux actions affichées avant de sélectionner **Autoriser la lecture et l’écriture**. Les autorisations délivrées avant la V2 restent en lecture seule, y compris après renouvellement. Les écritures suivent les droits de votre compte dans l’espace et le projet ciblés.

Les intégrations affichent **Lecture seule** ou **Lecture et écriture** pour chaque connexion. Sélectionnez **Révoquer** sur la connexion à retirer. Le retrait d’un accès à un projet s’applique à la prochaine action. Le retrait de l’espace invalide la connexion.

## Configuration

Circular expose `/mcp` lorsque `CIRCULAR_PUBLIC_URL` est renseignée. En production, utilisez l’origine HTTPS publique de Circular pour que les clients hébergés puissent atteindre le serveur. En local, pour la recette avec un client local, configurez par exemple `CIRCULAR_PUBLIC_URL=http://127.0.0.1:4310` et ouvrez cette même origine dans le navigateur.

Dans le client, configurez l’enregistrement dynamique OAuth (DCR). Les adresses de retour documentées de Claude et ChatGPT sont reconnues. Pour un autre client, renseignez son adresse de retour exacte via `CIRCULAR_MCP_REDIRECT_URIS`. Les adresses supplémentaires doivent utiliser HTTPS ou une adresse HTTP locale. La recette de bout en bout depuis Claude et ChatGPT reste à réaliser sur une instance publiquement accessible.

Le transport est Streamable HTTP. La ressource OAuth est l’URL complète du serveur MCP et le flux utilise PKCE S256. La portée initiale est `circular:read`. Une nouvelle demande OAuth avec `circular:read circular:write` permet de demander l’écriture. Le code et les jetons utilisateur sont stockés sous forme d’empreintes. Les jetons d’accès durent 15 minutes et le renouvellement repose sur un jeton rotatif, dans la limite de 30 jours après l’autorisation.

`create_ticket` et `add_comment` demandent chacun une clé `request_key` unique à l’action. Pour relancer un appel dont la réponse est incertaine, réutilisez cette clé et les mêmes arguments avec la même connexion. Le résultat de l’appel initial est restitué si le compte dispose encore de l’accès à la cible.

Sources officielles consultées le 24 novembre 2026. [Spécification MCP](https://modelcontextprotocol.io/specification/latest/basic/authorization) · [Claude, connecteurs personnalisés](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp) · [ChatGPT, authentification des connecteurs](https://developers.openai.com/plugins/build/auth)

## Périmètre validé le 24 novembre 2026

- Lister les projets accessibles, rechercher des tickets et consulter un ticket. Les listes sont paginées.
- Parcours de connexion, choix d’un espace, consentement de lecture, refus, expiration et révocation selon la [maquette HTML](maquette.html).
- V2. Création d’un ticket et ajout d’un commentaire, droits existants par espace et projet, nouvel accord OAuth et révocation individuelle selon la [maquette V2 validée](maquette-v2.html). La recette sur les connecteurs hébergés de Claude et ChatGPT reste à confirmer.
- V3. Triage, feuille de route, documents et fichiers, demandes clients, releases et revues, et contexte des assistants. La [maquette interactive V3 validée](maquette-v3.html) présente les écrans, les autorisations par famille et les confirmations.

Pour la recette locale, lancez `npm run build`, puis `npm run test:e2e -- tests/e2e/mcp.spec.ts`. Les tests du protocole et de l’isolation des droits se trouvent dans `tests/test_mcp.py`.

## Utiliser la V3

Les outils déclarent leurs portées dans le catalogue MCP. Une demande d’accès V3 présente les autorisations demandées par l’assistant. Vous pouvez choisir un sous-ensemble par famille, puis révoquer l’accord dans **Paramètres › Intégrations › Assistants IA**. Une modification implique la consultation de la même famille. Les accords MVP et V2 conservent la portée consentie avant la V3.

Les modifications d’un ticket, d’un document ou d’un élément de pilotage utilisent la version obtenue à la consultation. En cas de conflit, relisez la cible, puis créez une nouvelle demande avec sa version actuelle. Pour relancer un appel dont la réponse est incertaine, utilisez les mêmes arguments et la même clé sur la même connexion. Pour un partage, un archivage, une suppression de commentaire ou une revue GitHub, l’assistant transmet un lien de confirmation à ouvrir dans Circular. L’action requiert le compte à l’origine de la demande et une autorisation encore valide.

Dans **Projets › Pilotage**, retrouvez les initiatives, jalons, cycles, bilans, permanences de triage, fiches clients, demandes, releases, notes de version, liens GitHub, consignes, notes vérifiées et blocages. Dans **Tickets › Partagés avec moi**, les tickets et les documents partagés individuellement sont consultables en lecture seule. Via MCP, les fichiers PDF et les images sont limités à 64 Kio par appel.

### Configuration GitHub

L’intégrateur peut monter un fichier secret en lecture seule avec `CIRCULAR_GITHUB_CONNECTIONS_FILE`. Le fichier contient un tableau d’entrées avec `workspaceId`, `userId`, `repository` (au format `propriétaire/dépôt`) et `token`. Configurez un jeton personnel GitHub limité au dépôt et aux permissions requises. Circular envoie ce jeton uniquement à l’API GitHub et le sélectionne pour le même espace et le même utilisateur. GitHub applique ses propres permissions et protections de branche. En cas de résultat incertain, vérifiez la PR sur GitHub avant de créer une nouvelle demande. [Permissions pour les revues](https://docs.github.com/en/rest/pulls/reviews#create-a-review-for-a-pull-request) · [Permissions pour la fusion](https://docs.github.com/en/rest/pulls/pulls#merge-a-pull-request)

La recette V3 utilise également `tests/test_mcp_v3.py` et `tests/e2e/mcp-v3.spec.ts`. Les parcours GitHub en lecture et en écriture nécessitent un dépôt de recette et des jetons dédiés. Les parcours des clients hébergés nécessitent une instance de recette HTTPS accessible depuis ces clients.
