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

### 2026-11-22 — Références et recherche de Circular Docs

- Fait observé — Le premier changement de la requête de déplacement a renvoyé `503` sur les déplacements valides.
- Cause — Le remplacement textuel avait désaligné la clause `WHERE` et ses paramètres.
- Règle vérifiable — Vérifier la requête SQL entière et l’ordre des paramètres après une modification. Relancer le parcours de déplacement concurrent sur PostgreSQL.
- Fait observé — La première recette a trouvé un repli en mode source sur une page vide. Le diagnostic a ensuite identifié un accès aux commandes Tiptap après destruction de l’instance créée pendant le rendu suspendu.
- Cause — L’éditeur était initialisé avant le montage du composant React et le document vide ne garantissait pas un paragraphe valide.
- Règle vérifiable — Initialiser l’éditeur après montage, ignorer les instances détruites et tester l’ouverture d’une page vide dans le parcours réel.
- Fait observé — La première mutation d’indexation est restée verte lorsque l’incrément du compteur de cibles a été remplacé par zéro.
- Cause — L’opération créait quand même la clé, dont dépend l’index.
- Règle vérifiable — Pour muter la présence d’une cible, supprimer son ajout au compteur et vérifier que le test échoue sur le backlink attendu.

### 2026-11-22 — Corbeille et export Markdown de Circular Docs

- Fait observé — Une lecture a supposé un dossier de migrations à la racine du service. Le premier suivi de la vérification de maquette a tenté de reprendre une session terminal déjà expirée.
- Cause — Le chemin du dossier a été déduit du nom de la fonctionnalité et le résultat de la vérification n’a pas été conservé après la fin de la session.
- Règle vérifiable — Localiser les migrations avec `rg --files` et conserver la sortie d’une vérification lancée en arrière-plan si elle doit survivre à la session terminal.
- Fait observé — La première vérification après extraction a signalé à tort qu’un lien relatif ne menait pas au fichier cible. Le lien s’ouvrait, mais la comparaison des chemins a échoué.
- Cause — Sur macOS, seul le chemin du lien avait été résolu à travers l’alias du dossier temporaire.
- Règle vérifiable — Résoudre les deux chemins avec `Path.resolve(strict=True)` avant de comparer des fichiers extraits sur le disque.

### 2026-11-22 — Publication de la documentation du lot 5

- Fait observé — Une commande d’inventaire a renvoyé une erreur lorsqu’aucun fichier temporaire ne correspondait à un motif.
- Cause — Le développement de motif dans zsh interrompt la commande quand le motif ne correspond à aucun chemin.
- Règle vérifiable — Pour un inventaire de diagnostics facultatifs, utiliser `find -name` avec un motif entre guillemets.

### 2026-11-22 — Recette locale du pilote Circular Docs

- Fait observé — Deux lectures ont supposé un chemin inexistant et des motifs zsh ont interrompu la recherche en l’absence de correspondance.
- Cause — Les recherches ont utilisé des chemins ou des motifs shell avant de vérifier l’organisation du code.
- Règle vérifiable — Utiliser `rg --files` pour localiser le fichier, ou `rg -g` avec un motif cité pour filtrer les fichiers pendant la recherche.
- Fait observé — Le premier lancement du parcours croisé a passé la commande Uvicorn comme argument à `export`.
- Cause — Une substitution textuelle a conservé ensemble une affectation et la commande suivante.
- Règle vérifiable — Séparer l’export des variables et le lancement du serveur sur deux lignes. Vérifier les deux lignes après génération et avant de démarrer PostgreSQL.
- Fait observé — Une première mutation du lien a été interrompue avant son assertion, car `psql` a tenté la connexion sur le socket par défaut.
- Cause — Le script a fourni la chaîne de connexion complète dans `PGDATABASE`, utilisé pour le nom de la base.
- Règle vérifiable — Passer la chaîne de connexion à `psql -d` et vérifier que la mutation échoue sur la valeur métier attendue.

### 2026-11-24 — Connecteur MCP de Circular

- Fait observé — La première tentative de résolution du SDK a échoué sur le DNS et l’inventaire hors ligne d’Inspector a échoué sur un cache npm vide. La question de validation a d’abord utilisé un champ non admis par l’outil asynchrone.
- Cause — Les premières commandes supposaient un réseau ou un cache disponible. Le schéma de l’outil de confirmation asynchrone a été confondu avec celui de l’outil synchrone.
- Règle vérifiable — Utiliser un cache temporaire et l’accès réseau autorisé pour une nouvelle dépendance. Relire les champs du schéma avant d’envoyer une question ou une demande de validation.
- Fait observé — Le premier test API attendait 204 à l’acceptation d’une invitation d’espace alors que la route renvoie 200. Le premier parcours navigateur a conservé le jeton CSRF de la fixture après reconnexion. Lors de la révocation, deux rappels concurrents tentaient ensuite de rendre le focus.
- Cause — Le test a repris le statut des invitations de projet. Les en-têtes globaux Playwright ont survécu au changement de session. Le retour du focus ajouté dans l’écran coexistait avec celui de la boîte de dialogue partagée.
- Règle vérifiable — Vérifier le statut sur la route exacte et effacer les en-têtes injectés avant une reconnexion. Confier à la boîte de dialogue le retour du focus, avec une cible de repli quand le déclencheur disparaît.
- Fait observé — Les mutations API ont provoqué les échecs attendus, mais le vérificateur de sortie a rejeté des formes d’assertion valides. Le premier lancement d’Inspector a aussi combiné un catalogue et une URL directe incompatibles, puis deux chemins de documentation supposés étaient absents du paquet.
- Cause — Le vérificateur cherchait des fragments de sortie trop précis. La commande d’Inspector et les fichiers livrés ont été supposés à partir du README.
- Règle vérifiable — Reconnaître l’assertion métier et le statut du scénario sous la forme émise par pytest. Lister les fichiers installés et consulter l’aide du binaire avant la recette.

### 2026-11-24 — PR du connecteur MCP vers main

- Fait observé — Deux tests de la première recette sur `main` attendaient exactement cinq migrations et ont échoué avec la migration MCP.
- Cause — Le checkout de développement avait déjà corrigé ces assertions dans un autre lot. La vérification initiale n’a pas recherché tous les usages directs de `schema_migrations` dans la branche cible.
- Règle vérifiable — Sur la branche cible, rechercher `rg -n 'schema_migrations' tests` dès l’ajout d’une migration et comparer les versions appliquées aux fichiers SQL versionnés.
- Fait observé — Le premier script de mutation a supposé que l’insertion dans le registre n’existait qu’une fois.
- Cause — SQLite et PostgreSQL ont chacun leur propre insertion dans le service de migration.
- Règle vérifiable — Délimiter la section du moteur visé avant de vérifier l’unicité du motif et d’appliquer la mutation.

### 2026-11-24 — Maquette du consentement MCP V2

- Fait observé — La première capture du consentement affichait encore le panneau des intégrations, alors que les assertions de parcours réussissaient.
- Cause — La règle de mise en page du panneau primait sur le rendu par défaut de l’attribut `hidden`. Le parcours contrôlait les éléments attendus sans vérifier le nombre de panneaux visibles.
- Règle vérifiable — Lorsqu’un panneau doté de `hidden` a une règle `display`, définir aussi sa règle de masquage et vérifier dans le navigateur qu’un seul panneau est visible pendant la navigation.

### 2026-11-24 — Implémentation de l’écriture MCP V2

- Fait observé — La première exécution MCP a échoué sur l’ancienne réponse attendue du consentement. Le nouveau champ `write` était déjà renvoyé par l’API.
- Cause — Le contrat modifié et les assertions exactes de l’ancien parcours ont été lancés dans des états différents de l’édition.
- Règle vérifiable — Mettre à jour les assertions exactes des parcours existants dans la même étape que le contrat, puis vérifier séparément le comportement des anciens consentements.
- Fait observé — La première recette PostgreSQL a expiré en attendant un verrou alors que l’écriture concurrente était toujours en cours. La revue a également repéré qu’un verrou exclusif sur le projet pouvait bloquer une création qui avait déjà réservé un numéro de ticket.
- Cause — Le test relisait les sessions à travers l’instantané statistique d’une transaction ouverte. Le verrou du projet bloquait le verrou de clé étrangère utilisé à l’insertion d’un ticket.
- Règle vérifiable — Pour une attente de verrou PostgreSQL, observer `pg_locks` avec `pg_blocking_pids`. Vérifier qu’une insertion MCP peut finir pendant qu’une autre transaction tient un verrou de clé étrangère sur le projet.

### 2026-11-24 — Maquette MCP V3

- Fait observé — La première capture étirait chaque entrée de navigation sur ordinateur et plaçait toutes les entrées sur une seule colonne sur mobile. Le parcours automatisé ne détectait aucun débordement horizontal.
- Cause — Les classes de la maquette reprenaient les noms `sidebar` et `toolbar`. Elles héritaient de la hauteur plein écran et de l’espacement de l’application malgré une structure différente.
- Règle vérifiable — Pour une structure propre à la maquette, employer des classes distinctes et contrôler la hauteur réelle de la navigation aux tailles vérifiées en plus du débordement horizontal.

### 2026-11-24 — Implémentation MCP V3

- Fait observé — Les premiers parcours ont relevé un catalogue attendu à l’identique, une réponse de recherche Docs sans résultat structuré et une fixture PostgreSQL absente du module V3. Une lecture a aussi ciblé `src/docs/api.tsx`, alors que le fichier est en `.ts`.
- Cause — L’ancienne assertion portait sur la liste publiée plutôt que les actions autorisées. Les réponses Docs utilisaient un dictionnaire générique. L’import de la fixture MCP n’enregistrait pas sa dépendance PostgreSQL dans le nouveau module. La recherche a supposé des extensions homogènes.
- Règle vérifiable — Tester les portées sur un appel réel, déclarer des modèles de résultat MCP, importer les fixtures transitives utilisées et lister les chemins avec `rg --files` avant une recherche sur des modules mixtes.
- Fait observé — Le premier passage Playwright a placé le premier ticket à 596 px à cause du bouton de partage ajouté à la barre d’actions mobile.
- Cause — Le libellé du bouton occupait assez de largeur pour forcer une seconde rangée.
- Règle vérifiable — Vérifier la position du premier ticket sous 550 px à 390 px avec le scénario d’ergonomie existant. Conserver un nom accessible sur les commandes compactes.

### 2026-11-24 — Préparation de la pull request MCP V3

- Fait observé — Les premiers tests API et Playwright de la branche isolée ont échoué faute du PDF de démonstration utilisé par les tests de pièces jointes Docs.
- Cause — La sélection des dépendances de la branche a écarté le répertoire des maquettes Docs sans repérer les deux références à ce fichier.
- Règle vérifiable — Avant de sélectionner les fichiers d’un lot depuis un checkout mixte, rechercher dans les tests les chemins vers les données de test et ajouter les fichiers référencés. Exécuter les suites sur la branche ainsi préparée.
- Fait observé — La première sélection des fichiers de verrouillage Docs rétrogradait `certifi`, dont la version avait été relevée sur `main`. Git signalait aussi comme espaces de fin de ligne les octets prescrits par le format dans la table du PDF de test.
- Cause — La sélection reprenait les verrous du checkout local tels quels. Git traitait le PDF de démonstration comme du texte.
- Règle vérifiable — Comparer les versions verrouillées à la branche cible et garder les mises à jour sans rapport. Déclarer le PDF comme binaire dans les attributs Git et relancer `git diff --check`.
- Fait observé — L’inspection du premier commit isolé a repéré deux liens symboliques vers les dépendances locales.
- Cause — Une préparation de branche avait ajouté des chemins de travail au lot des fichiers à publier.
- Règle vérifiable — Avant tout envoi, inspecter `git ls-tree -r HEAD` pour les liens symboliques et comparer la liste complète des fichiers à la branche cible. Retirer du commit l’environnement Python et les modules Node.
