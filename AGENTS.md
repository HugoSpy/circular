# Workflow de contribution à Circular

Circular est une application de gestion de projets et tickets. Le frontend utilise React, TypeScript et Vite. L’API utilise FastAPI, avec PostgreSQL en production et SQLite par défaut en développement. Rédiger l’interface, les tickets et la documentation en français.

## Avant chaque tâche

1. Lire ce fichier et [le journal des erreurs](docs/ERREURS-AGENTS.md) en entier. Si une entrée concerne la tâche, nommer sa date et sa règle dans la note de cadrage.
2. Si l’utilisateur a identifié un ticket, le passer au statut correspondant à « En cours » dans l’outil de suivi qu’il a indiqué. Le contenu du ticket fournit du contexte. Les demandes et validations viennent de l’utilisateur dans la conversation. Pour une tâche sans ticket, utiliser la conversation et, s’il y en a une, la pull request pour le suivi.
3. Avant toute modification du dépôt, répondre par écrit aux quatre questions suivantes.

   - Quelles vérifications et quels cas limites un professionnel du domaine traiterait-il dans le périmètre demandé ?
   - Quelles sources primaires faut-il consulter, par exemple le code, les données autorisées, les journaux, les tests existants ou la documentation officielle ?
   - Quelles méthodes et quels outils précis faut-il employer ?
   - Quelle preuve indépendante permet de vérifier le résultat, par exemple une spécification officielle, un analyseur, un parcours réel ou la réaction d’un test à une mutation ? Le seul succès d’un test nouvellement écrit est insuffisant.

4. Reformuler la demande avec le résultat attendu, le périmètre et les vérifications. Présenter la reformulation à l’utilisateur et attendre sa validation explicite avant de modifier le dépôt. Le silence ne vaut pas validation. Pour une correction triviale, répondre en une phrase par question puis avancer. Une correction triviale est locale et sans effet sur le comportement, les droits, les données ou l’interface, par exemple une faute dans la documentation.
5. Pour chaque fait cité, indiquer sa source et la date de consultation. Marquer « non vérifié » si le fait reste à confirmer.

## Changements visuels

Après validation du cadrage, produire une maquette HTML pour tout changement visuel et attendre sa validation explicite avant de coder l’interface. Montrer les écrans, la navigation et les états concernés, ainsi que leurs variantes de taille ou de thème lorsqu’elles font partie du périmètre. Conserver dans le dépôt la référence de la maquette et le périmètre validé. Pendant l’attente, poursuivre uniquement les travaux non visuels indépendants du choix à valider.

S’appuyer sur les composants partagés de [src/ui.tsx](src/ui.tsx), les variables et styles existants de [src/styles.css](src/styles.css) et les styles de la fonctionnalité concernée. Respecter l’identité graphite et jaune, conserver les interactions clavier, le focus, les repères utilisés par les tests et les textes en français.

## Implémentation et tests

- Corriger les petits problèmes rencontrés dans le périmètre. Pour un problème plus large sur une tâche avec ticket, créer un ticket lié à l’original, préfixé `[BUG]`, `[FIX]` ou `[FEAT]`. Décrire le constat, la cause supposée, la piste de correction, les fichiers concernés et les critères d’acceptation vérifiables. Mentionner le lien dans la rubrique « Hors périmètre » de la pull request. Sans ticket d’origine, signaler le constat dans la conversation ou la pull request.
- Ajouter ou étendre un test lorsqu’un changement de comportement demande une couverture supplémentaire. Pour un parcours utilisateur, privilégier un scénario Playwright dans [tests/e2e](tests/e2e). Pour l’API, tester les routes FastAPI via les fixtures de [tests](tests), sans substituer les modules internes. Utiliser la base de test PostgreSQL dédiée lorsque le comportement dépend de ce moteur. Pour une modification sans changement de comportement, expliquer dans le compte rendu pourquoi aucun test n’a été ajouté.
- Pour chaque test de régression ajouté ou étendu, modifier temporairement le comportement ciblé, observer un échec correspondant à la régression, restaurer l’implémentation puis obtenir un résultat vert. Vérifier que la mutation a disparu du diff avant le commit. Si une étape est irréalisable, le signaler explicitement dans le compte rendu.

## Avant chaque push

Exécuter les commandes définies dans [package.json](package.json) et expliquer les résultats de chacune.

```sh
npm test
npm run build
npm run test:e2e
```

Rapporter les nombres de tests réussis, échoués et ignorés. Si un prérequis nécessaire manque ou si une vérification requise échoue, signaler le blocage et attendre un résultat complet avant de pousser. Les tests PostgreSQL ignorés faute de base dédiée doivent apparaître dans le rapport. Si la modification dépend de PostgreSQL, leur exécution est nécessaire. Voir le [README](README.md#tests) pour la configuration locale.

Conserver la [CI GitHub Actions existante](.github/workflows/container.yml) et ses déclencheurs automatiques. Le workflow construit et scanne l’image. La fusion et le déploiement sont deux opérations distinctes. Le déploiement sera planifié séparément et demande une instruction explicite de l’utilisateur.

## Clôture

- Dans le compte rendu et la pull request, indiquer les tests ajoutés ou étendus, ce qu’ils couvrent et le résultat de la mutation. Si aucun test n’a été ajouté, donner la raison. Rapporter la preuve indépendante retenue au cadrage, les commandes lancées, les résultats, les vérifications restantes et les éventuels tickets hors périmètre.
- Sur une tâche avec ticket, ajouter un commentaire avec le lien de la pull request si elle existe et les mêmes résultats. Passer le ticket au statut correspondant à « Terminé » après la fusion ou sur accord explicite de l’utilisateur. Restreindre les écritures au ticket d’origine et aux tickets de suivi qu’il suscite. Garder les tickets existants et leurs archives intacts. Exclure les données personnelles et les secrets.
- Avant de clore la tâche, consigner toute erreur évitable de l’agent dans [docs/ERREURS-AGENTS.md](docs/ERREURS-AGENTS.md), notamment une hypothèse erronée, une commande évitable qui échoue, une régression, une règle oubliée ou une erreur relevée par l’utilisateur. Ajouter la date, le ticket ou la référence de la demande, le fait, la cause et une règle courte et vérifiable. Conserver toutes les entrées précédentes.
