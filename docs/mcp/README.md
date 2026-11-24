# Connecter un assistant IA à Circular

Dans **Paramètres › Intégrations › Assistants IA**, copiez l’adresse du serveur MCP. Ajoutez-la dans les connecteurs personnalisés de votre assistant, lancez la connexion, puis choisissez un espace dans Circular. Chaque autorisation donne accès aux projets et tickets consultables par votre compte dans cet espace. Le résultat des outils est transmis à l’assistant.

Pour retirer l’accès, sélectionnez **Révoquer** sur la connexion dans les intégrations. Le retrait d’un accès à un projet s’applique à la prochaine consultation. Le retrait de l’espace invalide la connexion.

## Configuration

Circular expose `/mcp` lorsque `CIRCULAR_PUBLIC_URL` est renseignée. En production, utilisez l’origine HTTPS publique de Circular pour que les clients hébergés puissent atteindre le serveur. En local, pour la recette avec un client local, configurez par exemple `CIRCULAR_PUBLIC_URL=http://127.0.0.1:4310` et ouvrez cette même origine dans le navigateur.

Dans le client, configurez l’enregistrement dynamique OAuth (DCR). Les adresses de retour documentées de Claude et ChatGPT sont reconnues. Pour un autre client, renseignez son adresse de retour exacte via `CIRCULAR_MCP_REDIRECT_URIS`. Les adresses supplémentaires doivent utiliser HTTPS ou une adresse HTTP locale. La recette de bout en bout depuis Claude et ChatGPT reste à réaliser sur une instance publiquement accessible.

Le transport est Streamable HTTP. La ressource OAuth est l’URL complète du serveur MCP, le flux utilise PKCE S256 et la portée est `circular:read`. Le code et les jetons utilisateur sont stockés sous forme d’empreintes. Les jetons d’accès durent 15 minutes et le renouvellement repose sur un jeton rotatif, dans la limite de 30 jours après l’autorisation.

Sources officielles consultées le 24 novembre 2026. [Spécification MCP](https://modelcontextprotocol.io/specification/latest/basic/authorization) · [Claude, connecteurs personnalisés](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp) · [ChatGPT, authentification des connecteurs](https://developers.openai.com/plugins/build/auth)

## Périmètre validé le 24 novembre 2026

- Lister les projets accessibles, rechercher des tickets et consulter un ticket. Les listes sont paginées.
- Parcours de connexion, choix d’un espace, consentement de lecture, refus, expiration et révocation selon la [maquette HTML](maquette.html).
- La V2 ajoutera des outils d’écriture. Le détail des actions sera cadré à part. Les connexions du MVP restent limitées à leur autorisation de lecture.

Pour la recette locale, lancez `npm run build`, puis `npm run test:e2e -- tests/e2e/mcp.spec.ts`. Les tests du protocole et de l’isolation des droits se trouvent dans `tests/test_mcp.py`.
