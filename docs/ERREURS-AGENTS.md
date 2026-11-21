# Journal des erreurs des agents

Ce journal conserve les erreurs évitables et la règle qui aurait permis de les éviter. Consulter toutes les entrées au début de chaque tâche. Ajouter toute nouvelle entrée en fin de fichier avant de clore la tâche et conserver les entrées précédentes.

Format d’une entrée

```markdown
### AAAA-MM-JJ — Ticket ou référence de la demande

- Fait observé
- Cause
- Règle vérifiable
```

## Entrées

### 2026-11-20 — Ajout du workflow Circular

- Fait observé — La première commande de validation a interrompu la chaîne avant la vérification des liens et des scénarios.
- Cause — Le statut 1 de `git diff --no-index` signale aussi la présence d’un diff.
- Règle vérifiable — Pour un nouveau fichier, accepter le statut 1 de `git diff --no-index --check` seulement si sa sortie est vide. Exécuter les autres vérifications indépendamment.

### 2026-11-21 — Protection de l’inscription Circular

- Fait observé — Deux lectures ont ciblé des chemins absents (`deploy/README.md`, puis `tests/conftest.py`); une première suite API a aussi échoué quand les clients de reprise tentaient de s’inscrire avec un compte déjà confirmé. Le premier parcours E2E a détecté que l’écran de confirmation restait affiché après « Continuer ».
- Cause — Les chemins de documentation et de fixtures avaient été supposés au lieu d’être listés; le helper supposait que chaque inscription générique créait un nouveau compte; la transition UI n’avait pas été vérifiée de bout en bout avant le premier run.
- Règle vérifiable — Lister les chemins avec `rg --files` avant de lire un fichier; pour un statut HTTP neutre, traiter aussi le cas « compte déjà existant » dans les fixtures; vérifier dans Playwright que chaque action de confirmation atteint l’écran attendu.
- Revue de sécurité — Le premier lien plaçait le jeton dans la query HTTP. Le lien utilise désormais le fragment, qui n’est pas transmis au serveur; pour les jetons d’e-mail, vérifier aussi l’URL visible dans les journaux d’accès.
- Fait observé — Une exécution complète ultérieure a révélé un helper Playwright supplémentaire qui construisait encore le lien de confirmation avec l’ancienne query string ; les liens d’auth-sharing ont été migrés, puis la suite ciblée a réussi.
- Cause — La recherche initiale des usages de l’ancien format n’a pas couvert toutes les constructions d’URL de fixture.
- Règle vérifiable — Après un changement de format de lien, rechercher l’ancien paramètre dans toutes les sources de tests (`rg '\\?verification' tests`) et exécuter la suite E2E complète.
- Fait observé — Au contrôle pré-push du 21 novembre, la première exécution Playwright dans le bac à sable a échoué avant le test parce que Chrome s’est arrêté avec `SIGABRT`/`EPERM`; l’exécution autorisée de la suite complète a ensuite atteint les tests et confirmé un échec préexistant sur le changement de statut au clavier.
- Cause — Le premier lancement n’avait pas l’accès local au navigateur nécessaire ; le scénario E2E restant n’a pas encore de cause établie.
- Règle vérifiable — Si Playwright échoue au lancement du navigateur (`EPERM`), distinguer ce blocage d’un échec de scénario et relancer avec l’accès local approprié. Ne pas pousser si la suite requise échoue.

### 2026-11-21 — Reprise du contrôle avant push

- Fait observé — Le premier lancement Linux s’est arrêté avant les scénarios. Playwright a interprété les fichiers AppleDouble `._*.spec.ts` de l’archive comme des tests.
- Cause — L’archive créée sur macOS incluait les métadonnées du système de fichiers.
- Règle vérifiable — Pour transférer les sources macOS vers Linux, créer l’archive avec `tar --no-mac-metadata --no-xattrs` et vérifier l’absence de fichiers `._*` dans le répertoire de tests avant de lancer Playwright.
- Fait observé — La première lecture de l’inventaire Docker a rencontré un refus d’accès au socket. Une recherche a aussi visé un `pyproject.toml` absent et une lecture trop large de l’ancienne conversation a renvoyé du texte que le script a tenté de décoder comme du JSON.
- Cause — Le contrôle a supposé l’accès au daemon, l’existence du manifeste et le format de la réponse de l’outil.
- Règle vérifiable — Pour Docker Desktop, utiliser l’accès au socket autorisé. Lister les manifestes existants avant de les lire. Pour l’historique d’une conversation, limiter la taille de la réponse et vérifier son type avant de la décoder.

### 2026-11-21 — Socle et identité de Circular Docs

- Fait observé — L’installation Python dans le bac à sable a échoué sur la résolution DNS, et l’installation npm hors ligne sur un paquet absent du cache. Une lecture de cache pip a également échoué et deux anciens chemins documentaires Authlib ont renvoyé 404.
- Cause — Les vérifications ont supposé l’accès à PyPI, un cache exploitable et des URL documentaires toujours valides.
- Règle vérifiable — Pour de nouvelles dépendances, utiliser un cache temporaire en écriture et l’accès réseau autorisé. Rechercher les pages officielles avant d’ouvrir les chemins de documentation.
- Fait observé — La première mutation de résolution d’identité est restée verte. Seule la première des deux lectures de la ligne avait été touchée.
- Cause — La seconde lecture, après acquisition du verrou de provisionnement, retrouvait encore l’identité stable.
- Règle vérifiable — Lorsqu’un test reste vert après mutation, vérifier les chemins de repli avant de conclure. Ici, modifier les deux lectures a fait échouer le scénario de changement d’adresse.
- Fait observé — Le script de mutation du focus s’est interrompu avant restauration, car `status` est en lecture seule dans zsh. Une relance a donc encore compilé la source mutée. La source a ensuite été restaurée et comparée octet par octet à sa sauvegarde.
- Cause — Le script a supposé qu’une variable de statut ordinaire était disponible et que son piège de sortie s’exécuterait après cette erreur.
- Règle vérifiable — Employer un nom propre au test pour le code de retour. Vérifier la restauration de la source et reconstruire le frontend avant de relancer le scénario.

### 2026-11-22 — Intégration de la documentation de Circular Docs

- Fait observé — La première vérification a pris un exemple Markdown de lien interne, affiché en code dans le plan, pour un lien relatif du dépôt.
- Cause — Le contrôle recherchait la syntaxe des liens dans le texte brut, y compris dans les exemples de code.
- Règle vérifiable — Exclure les blocs et fragments de code avant le contrôle des liens Markdown. Faire échouer la commande si la vérification des liens échoue.

### 2026-11-22 — Espaces privés de Circular Docs

- Fait observé — Le premier contrôle d’une mutation a interrompu le lot sur une assertion de durée qui avait échoué comme attendu.
- Cause — Le script exigeait le texte exact `AssertionError`. Pytest présentait la comparaison sous la forme `E assert`.
- Règle vérifiable — Identifier le scénario dans le résumé pytest et reconnaître la forme de comparaison enrichie avant de conclure que la mutation est inexploitable.
- Fait observé — La compilation a rejeté l’accès à la page parente dans un formulaire. Le premier scénario de révocation a attendu le libellé exact du sélecteur de rôle jusqu’à expiration.
- Cause — Deux types de formulaire partageaient une variante de l’union TypeScript. Le test ciblait la structure du libellé plutôt que le nom accessible affiché dans la trace.
- Règle vérifiable — Déclarer une variante annotée par action lorsque les champs diffèrent. Pour une sélection Playwright, utiliser le rôle et le nom accessible confirmés dans l’arbre d’accessibilité.

### 2026-11-22 — Éditeur Markdown de Circular Docs

- Fait observé — Le premier test de saisie visuelle a placé le texte au début du paragraphe alors que le scénario l’attendait à la fin.
- Cause — La touche `End` a été utilisée comme raccourci de déplacement du curseur dans un contrôle éditable, avec un comportement différent sur macOS.
- Règle vérifiable — Quand le test vise la sérialisation d’un contenu, saisir le texte complet dans le contrôle accessible. Tester les raccourcis propres à chaque plateforme dans un scénario dédié.
