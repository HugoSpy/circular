# Contrat d’identité et de session — lot 1

Cadrage et [maquette de connexion](mockups/connexion.html) validés le 21 novembre 2026 dans la conversation Circular. Le parcours couvre la redirection vers Forge ID, le retour authentifié, l’expiration, l’accès refusé et la reprise après erreur. Dépôt cible approuvé : `HugoSpy/circular-docs`, avec visibilité privée. La préparation du service et le développement se font dans un dépôt séparé de Circular.

## Identités et admission

- Forge ID authentifie les titulaires des comptes EPITA. L’opérateur du pilote autorise une adresse normalisée via `allow`. Lors de la première connexion, une adresse EPITA vérifiée, issue du jeton signé ou de UserInfo avec un sujet correspondant, permet de lier une ligne préautorisée à un couple `(iss, sub)`.
- L’association à l’identifiant local UUID est atomique. Une fois le compte associé, ce couple conserve l’identité après changement d’adresse. L’adresse de provisionnement reste le repère de l’opérateur et le libellé de la session. Le transfert d’un compte provisionné à un autre sujet demande une décision d’exploitation.
- Les invitations du lot 2 désigneront l’UUID local d’un compte existant. Les droits d’un espace seront consultés côté serveur à chaque requête. Un lien de ticket délègue l’accès à Circular.

## Connexion et révocation

- Le retour OIDC accepte des jetons ID signés en RS256. La tentative expire après dix minutes et est consommée une seule fois. Le serveur associe `state`, `nonce` et le vérificateur PKCE à la tentative et exige le cookie du navigateur qui l’a initiée. Les codes et jetons OIDC restent hors des réponses applicatives et des journaux d’accès du serveur local. Une future couche proxy devra également masquer les paramètres de retour.
- La session locale porte un jeton opaque de 256 bits. PostgreSQL conserve son empreinte. Le cookie est `HttpOnly`, `SameSite=Lax` et `Secure` sous HTTPS. La durée absolue est de huit heures. Une nouvelle connexion renouvelle la session du navigateur. La déconnexion demande une requête POST de la même origine, puis supprime la session côté serveur.
- Désactiver un compte supprime ses sessions et ferme ses prochains accès. Une session absente, expirée ou révoquée reçoit le même `401`. La fermeture de la session locale laisse la session Forge sous la responsabilité de l’utilisateur et du fournisseur.

## HTTP

| Méthode et chemin | Réponse |
| --- | --- |
| `GET /api/health` | `200` si la table d’identité est accessible, sinon `503` |
| `GET /api/session/login` | `303` vers Forge ID, ou retour à l’écran d’erreur |
| `GET /login/oauth2/code/epita` | `303` vers l’interface avec le résultat de connexion |
| `GET /api/session` | `200` avec `account.id` et `account.email`, ou `401` |
| `POST /api/session/logout` | `204` pour une origine valide, `403` sinon |

Les erreurs HTTP utilisent `{"error":{"code":"not_found","message":"Cette ressource est introuvable."}}`. Le code est stable et le texte en français. Pour les futures ressources privées, utiliser `404` pour une ressource absente ou hors du périmètre de lecture et `403` si la ressource est visible mais l’action interdite.

Une liste paginée répond `{"items":[],"nextCursor":null}`. Le curseur est opaque, `null` indique la fin, et la limite par défaut est 25, bornée de 1 à 100. Chaque route de liste documentera son ordre stable, ses filtres et leurs interactions avec le curseur avant implémentation.

## Sources consultées le 21 novembre 2026

- [Forge ID et client de test](https://docs.forge.epita.fr/services/forge-id/oidc/)
- [Découverte Forge ID](https://cri.epita.fr/.well-known/openid-configuration)
- [Identité stable dans OpenID Connect Core](https://openid.net/specs/openid-connect-core-1_0.html#ClaimStability)
- [Authlib](https://docs.authlib.org/en/stable/oauth2/client/web/index.html)
- Cadrage et plan du lot 1 dans Circular. Règle du journal du 21 novembre 2026 sur le contrôle des secrets dans les URL et les journaux. Le client de production et la prise en charge effective de PKCE par Forge ID sont à vérifier avec un compte EPITA de test. Le document de découverte ne déclare pas de méthode PKCE.

## Recette locale du 21 novembre 2026

- `npm test` sur PostgreSQL 14.20 : 10 réussis, 0 échec, 0 ignoré. Deux avertissements signalent la dépréciation d’httpx dans les intégrations Authlib et Starlette.
- `npm run build` : TypeScript et Vite réussis.
- `npm run test:e2e` : 1 réussi, 0 échec, 0 ignoré dans Chromium. Le scénario couvre le clavier, deux sessions indépendantes, la vue mobile à 390 px, la déconnexion et le refus d’admission.
- Chaque cas API a échoué lors de sa mutation ciblée, puis la suite complète a réussi après restauration. La mutation Playwright a supprimé le retour du focus après déconnexion. L’assertion de focus a échoué, puis le scénario a réussi après restauration et recompilation.
- Contrôle indépendant : `psql` a retourné les mêmes données témoins et le même historique de migration avant et après la seconde exécution de la commande de migration.
- Le parcours OIDC de recette utilise des comptes fictifs et des jetons signés localement. La connexion avec un compte EPITA réel et la création du dépôt GitHub privé restent à vérifier.
