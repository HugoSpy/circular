# Périmètre validé — protection de l’inscription et des invitations

Date de validation : 2026-11-20. Demande suivie dans la conversation, sans ticket identifié.
Maquette approuvée explicitement le 2026-11-20 avant les modifications React.

## Problèmes couverts

- Une adresse déclarée sans preuve de possession peut recevoir l’accès à une invitation privée.
- Les réponses publiques de création de compte permettent de déduire si une adresse existe.
- Toute violation d’intégrité au cours de l’inscription est présentée comme un conflit de pseudo ou d’adresse, ce qui masque les erreurs inattendues.
- Le formulaire refuse une casse de domaine que l’API normalise et accepte.

## Résultat attendu

- L’adresse est vérifiée avant qu’un compte nouvellement inscrit devienne actif et avant qu’une invitation nominative puisse être acceptée.
- La réponse HTTP publique d’inscription reste indifférenciée pour une nouvelle adresse, une adresse existante ou un pseudo déjà pris; aucune session de compte n’est créée avant validation.
- Les journaux internes distinguent les collisions attendues des erreurs inattendues sans enregistrer les valeurs saisies, mots de passe ou jetons.
- La validation HTML et API est cohérente, notamment pour la casse du domaine EPITA.
- Le parcours reste accessible au clavier et conserve l’identité Circular graphite et jaune.

## Dépendance d’exploitation

Le dépôt ne contenait pas de service d’envoi de courriels (consultation du dépôt le 2026-11-20). Le code SMTP est configurable; en développement, le lien est écrit dans les logs locaux. L’infrastructure doit fournir et valider un relais STARTTLS, son identifiant, son mot de passe dans `secrets/smtp_password`, et l’adresse d’expédition. Cette configuration d’exploitation n’est pas vérifiée.

## Preuves prévues

- Tests API pour création en attente, validation, expiration, renvoi, répétition, doublons, absence de session avant validation, liens sans jeton dans la query et invitations.
- Scénarios Playwright pour les écrans et la navigation clavier.
- Exécution sur SQLite et PostgreSQL dédié; une base PostgreSQL de test reste requise pour conclure sur PostgreSQL.
- Inspection des journaux et réponses pour vérifier l’absence de PII et de secrets.

## Mise en œuvre et résultat (2026-11-21)

- Migration 006 SQLite/PostgreSQL, comptes en attente (conservés 24 heures pour renvoi) et jetons de confirmation hashés, uniques et expirables au bout de 30 minutes. Le jeton du lien est dans le fragment d’URL, non transmis dans la requête HTTP.
- Endpoints d’inscription, renvoi et confirmation; l’activation et la création de session arrivent après confirmation. Les anciens comptes reçoivent un état « adresse non confirmée » et peuvent demander un lien.
- Les invitations de projet et d’espace sont filtrées ou refusées côté API tant que l’adresse du destinataire n’est pas confirmée.
- Configuration SMTP obligatoire en production, documentée dans `README.md`, `.env.example` et `compose.yaml`.
- Tests API ajoutés pour le message neutre, la confirmation à usage unique, la rotation du lien expiré, les erreurs d’intégrité inconnues, le fragment sans query et le refus d’invitations non confirmées. Les mutations temporaires ciblant ces comportements ont fait échouer les tests correspondants, puis ont été supprimées.
- `npm test` a d’abord donné 139 réussites et 29 tests ignorés faute de base dédiée. La relance sur une instance PostgreSQL temporaire a donné 168 réussites, 0 échec et 0 test ignoré, avec un avertissement de dépréciation Starlette/httpx.
- `npm run build` et `docker compose --env-file .env.example -f compose.yaml -f compose.postgres.yaml -f compose.local.yaml config --quiet` ont réussi.
- `npm run test:e2e` a donné 33 réussites et 1 échec avec Chrome 157 sur macOS. Sur un sélecteur HTML isolé, la même frappe `ArrowUp` n’a pas changé la valeur ni émis d’événement `change`. Le code de Chromium prévoit l’ouverture du menu natif sur cette touche lorsque le thème de la plateforme le demande. La suite complète sous Linux avec Chrome for Testing 156 a donné 34 réussites, 0 échec et 0 test ignoré, y compris le scénario clavier d’origine. [Code de Chromium consulté le 21 novembre 2026](https://chromium.googlesource.com/chromium/src/+/d80340771321ba42a504c4998aad693199f8554c/third_party/blink/renderer/core/html/forms/select_type.cc)
- Le relais SMTP et la base de production restent à qualifier par l’infrastructure.

## Maquette

[Maquette HTML du parcours de validation](mockups/auth-email-verification.html)
