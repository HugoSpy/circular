# Circular — remise à l’infrastructure de l’école

État du 28 octobre 2026. Les fichiers fournis préparent un déploiement ; aucune publication de registre, configuration du réseau de l’école ou mise en production distante n’a été effectuée. Voir la [validation des espaces, version 2.1](workspace-validation.md), et la [validation initiale, version 2.0](production-validation.md).

## Architecture livrée

Un conteneur `app` sert le build React et l’API FastAPI sur le port interne 4310. PostgreSQL conserve les comptes, sessions, projets, tickets et préférences. Le frontend utilise la même origine HTTP que l’API. L’infrastructure termine HTTPS devant l’application et gère le DNS, les certificats, les sauvegardes et la supervision.

- `compose.yaml` : application raccordée à une base PostgreSQL externe par secret monté.
- `compose.postgres.yaml` : ajout facultatif d’un PostgreSQL 17 dédié, volume persistant et rôle applicatif sans privilèges superutilisateur, création de bases ou création de rôles.
- `compose.local.yaml` : uniquement pour la validation locale sur loopback, sans HTTPS. **Ne pas utiliser ce fichier en production.**
- `Dockerfile` : compilation frontend séparée, image Python finale sans Node/npm, utilisateur `10001:10001`, contrôle `/api/ready`. Les images de base et PostgreSQL sont figées par digest ; les dépendances Python par versions et SHA-256, npm par lockfile.

Le conteneur applicatif a un système de fichiers en lecture seule, `/tmp` temporaire, toutes les capabilities retirées et `no-new-privileges`. Les limites initiales sont 1 Gio et 2 CPU pour chaque service. Ce sont des valeurs de départ à ajuster après mesure ; aucun test de charge ni dimensionnement pour toute l’école n’est revendiqué.

Prévoir Docker Engine et Docker Compose. L’override local utilise `!override`, qui nécessite Compose 2.24.4 ou supérieur ([documentation Docker](https://docs.docker.com/reference/compose-file/merge/)). Python 3 n’est nécessaire sur l’hôte que pour le petit générateur de secrets et les scripts de validation ; l’application s’exécute dans l’image.

## Configuration publique et secrets

Copier `.env.example` vers `.env` puis renseigner les valeurs **non secrètes** :

| Variable | Rôle |
| --- | --- |
| `CIRCULAR_PUBLIC_URL` | Origine HTTPS exacte, par exemple `https://circular.ecole.example`, sans chemin ni identifiants |
| `CIRCULAR_IMAGE_TAG` | Version livrée, actuellement `2.1.0` ; conserver les anciennes images pour le retour arrière |
| `CIRCULAR_BIND_ADDRESS` | `127.0.0.1` si le proxy est sur le même hôte ; adapter explicitement pour un réseau privé de proxy |
| `CIRCULAR_HTTP_PORT` | Port hôte de l’application, 4310 par défaut |
| `CIRCULAR_SECRETS_DIR` | Répertoire privé des fichiers montés en secrets ; `./secrets` par défaut |
| `CIRCULAR_TRUSTED_PROXIES` | IP ou CIDR exacts des proxys autorisés à fournir les en-têtes transmis ; jamais `*` |

L’application lit la connexion dans `/run/secrets/database_url`, via `CIRCULAR_DATABASE_URL_FILE`. Le fichier contient une URL PostgreSQL ; son contenu ne doit pas être placé dans `.env`, dans une commande visible, dans le dépôt ou dans un ticket d’exploitation. Les secrets ne sont pas inclus dans le contexte de build grâce à la liste d’autorisation de `.dockerignore`.

Pour une base fournie par Compose :

```bash
cp .env.example .env
python3 scripts/init-secrets.py --directory secrets
```

Le script génère des mots de passe distincts pour le compte d’initialisation et le compte applicatif. Il refuse d’écraser un secret existant. Sous Linux, le dossier doit être en mode `0700` ; les fichiers sont `0444` à l’intérieur de ce dossier privé, afin que les UID des conteneurs lisent leurs fichiers montés individuellement. Les autres comptes hôte ne peuvent pas traverser le dossier. Avec un gestionnaire de secrets de l’école, remplacer les montages par ceux de l’orchestrateur et conserver cette séparation des accès. Sur Windows, appliquer les ACL équivalentes au dossier ; les bits POSIX ne remplacent pas les ACL Windows.

Ne pas relancer le générateur pour « changer le mot de passe » d’un volume PostgreSQL existant : les fichiers d’initialisation ne s’appliquent qu’au premier démarrage d’un volume vide. La rotation doit changer le rôle PostgreSQL, mettre à jour les secrets par le gestionnaire et recréer l’application de façon coordonnée.

## Option A — PostgreSQL fourni par l’école

Faire créer une base dédiée et un rôle applicatif `NOSUPERUSER NOCREATEDB NOCREATEROLE`. Ce rôle doit posséder la base/le schéma de Circular ou disposer des droits DDL nécessaires aux migrations, ainsi que des droits sur les tables et séquences. L’application ne nécessite pas le mot de passe de l’administrateur PostgreSQL.

Faire déposer l’URL dans `secrets/database_url` par le mécanisme approuvé. Pour une connexion hors réseau local de l’hôte, utiliser TLS avec vérification du serveur (`sslmode=verify-full`) et, si nécessaire, monter l’autorité de certification PostgreSQL dans le conteneur et indiquer `sslrootcert=/run/secrets/postgres_ca`. Le nom DNS doit correspondre au certificat. La configuration Compose de base ne monte que `database_url` ; ajouter le secret `postgres_ca` dans l’override d’infrastructure si nécessaire. Ne pas désactiver la validation TLS pour résoudre une erreur de certificat.

Depuis le dossier du projet, après configuration de `.env` et des secrets :

```bash
docker compose -f compose.yaml config --quiet
docker compose -f compose.yaml build app
docker compose -f compose.yaml up -d --no-build --wait
docker compose -f compose.yaml exec -T app python -m backend.migrate
docker compose -f compose.yaml ps
```

Les migrations sont déjà exécutées au démarrage ; la commande explicite vérifie leur idempotence. Elles sont versionnées et transactionnelles, avec un verrou PostgreSQL pour les démarrages concurrents. Aucun jeu de démonstration n’est injecté automatiquement.

## Option B — PostgreSQL inclus dans Compose

Après génération des secrets et configuration de `.env` :

```bash
docker compose -f compose.yaml -f compose.postgres.yaml config --quiet
docker compose -f compose.yaml -f compose.postgres.yaml build app
docker compose -f compose.yaml -f compose.postgres.yaml up -d --no-build --wait
docker compose -f compose.yaml -f compose.postgres.yaml ps
```

PostgreSQL n’expose aucun port hôte. L’application attend sa disponibilité avant de démarrer. Le volume `<projet-compose>_postgres_data` conserve les données après arrêt, redémarrage ou recréation des conteneurs. `docker compose down` ne supprime pas ce volume ; **ne pas employer `down -v` sur les données de l’école**.

Les deux options servent le même code et le même schéma PostgreSQL. Le choix dépend de la politique de sauvegarde et de supervision de l’école.

## Build derrière une autorité de certification d’entreprise

Si le proxy réseau de l’école présente une CA interne, fournir un bundle public approuvé contenant les autorités nécessaires. Le Dockerfile accepte un secret BuildKit facultatif, valable uniquement pendant `npm ci` et `pip install` :

```bash
docker build --secret id=build_ca,src=/chemin/approuve/ca-bundle.pem -t circular:2.1.0 .
docker compose -f compose.yaml -f compose.postgres.yaml up -d --no-build --wait
```

Le certificat n’est pas copié dans l’image ; aucune option de désactivation TLS n’est utilisée. Un build sans cette option convient à un réseau utilisant les autorités publiques habituelles. Pour remettre une image sans registre : `docker save circular:2.1.0 -o circular-2.1.0.tar`, puis `docker load -i circular-2.1.0.tar` sur l’hôte cible. Le registre et le tag immuable de l’école peuvent remplacer cette procédure.

## Reverse proxy HTTPS et contrôle d’accès réseau

Adapter [deploy/nginx.example.conf](../deploy/nginx.example.conf) au proxy déjà géré par l’école. Cet exemple n’a pas été installé sur la machine ; il faut fournir les véritables DNS et chemins de certificats. Un autre proxy est possible s’il conserve `Host` et transmet `X-Forwarded-Proto`/`X-Forwarded-For` correctement.

Le proxy en bordure doit remplacer les en-têtes de transmission fournis par le client. Autoriser uniquement son adresse ou son réseau strict dans `CIRCULAR_TRUSTED_PROXIES` ([référence Uvicorn](https://uvicorn.dev/deployment/)). Si le proxy tourne sur l’hôte, son adresse vue depuis Docker peut être la passerelle du réseau Docker plutôt que `127.0.0.1` : déterminer cette adresse lors de l’installation. Sinon les limites de connexion risquent de regrouper tous les utilisateurs sous l’adresse du proxy. Ne pas exposer directement le port applicatif à Internet pour contourner cette configuration.

La production exige `CIRCULAR_ENV=production`, une origine HTTPS et PostgreSQL. L’application refuse les autres hôtes/origines, utilise des cookies `HttpOnly`, `Secure`, `SameSite=Lax`, des jetons CSRF pour les mutations authentifiées, une CSP et HSTS. Les secrets de session restent côté serveur ; les mots de passe utilisent Argon2id. Les limites de tentatives sont stockées en base et partagées entre processus.

Superviser `GET /api/health` pour le processus et `GET /api/ready` pour l’accès effectif à la base. Ces probes sont accessibles sans session, sans contenu métier. Examiner les erreurs serveur et événements d’authentification avec la rétention de l’école ; ne pas enregistrer mots de passe, cookies ou corps de requêtes dans le proxy. Les logs Docker ont une rotation locale limitée à trois fichiers de 10 Mo.

## Comptes, projets et limites fonctionnelles

L’inscription nécessite un pseudo unique, une adresse dont le domaine est exactement `epita.fr`, et un mot de passe de 12 à 128 caractères. **Le domaine est contrôlé, la possession de l’adresse n’est pas vérifiée** : aucun SMTP, code de confirmation ou SSO n’est livré. Cette limite doit être acceptée par l’école avant ouverture publique ; un SSO ou une vérification mail est une évolution distincte.

Les comptes créent des espaces privés et peuvent y inviter des adresses EPITA, même avant leur inscription, ou partager un lien révocable valable sept jours. Les nouveaux projets sont accessibles aux membres de leur espace ; les projets historiques restent privés avec leurs accès existants. Une invitation limitée à un projet donne uniquement un accès d’invité à ce périmètre. Toute adhésion exige un compte connecté et une acceptation explicite. Préférences, vues et modèles sont personnels et séparés par espace. Un retrait de membre révoque ses accès et les invitations ciblées encore en attente ; les liens partagés doivent être révoqués séparément. Les contrôles sont dans l’API, indépendamment de l’affichage des boutons.

La migration 005 ajoute les espaces et rattache les données existantes sans élargir les droits sur les anciens projets. Tester cette migration sur une restauration isolée avant la mise à jour ; elle n’a pas de downgrade automatique. GitHub et Slack sont des présentations « À venir » qui affichent une erreur explicite au clic, sans appel externe ni configuration de secret.

Pas de collaboration en temps réel, notifications email, pièces jointes, administration générale ou récupération autonome du mot de passe. L’opérateur habilité peut réinitialiser un mot de passe dans un terminal interactif, avec saisie masquée :

```bash
docker compose -f compose.yaml exec app python -m backend.manage reset-password --email personne@epita.fr
```

Cette opération révoque toutes les sessions du compte. Un fichier secret monté peut être fourni avec `--password-file` pour une procédure automatisée ; ne pas passer le mot de passe en argument ou dans un ticket. L’accès Docker/opérateur donne des privilèges sur l’application et doit rester limité à l’infrastructure.

## Import de la base SQLite historique

L’ancienne base n’est jamais publiée automatiquement aux nouveaux inscrits. Ses données sans propriétaire restent masquées tant qu’un opérateur n’a pas effectué d’attribution explicite. Sauvegarder le fichier SQLite backend arrêté avant l’import.

Sur une **destination PostgreSQL vide**, monter la copie en lecture seule. Sous Linux, cette copie doit être lisible par l’UID `10001` du conteneur : placer par exemple la copie dans un dossier privé `0700` avec un fichier `0444`, puis monter uniquement le fichier. Ne pas modifier les permissions de la base originale. Exemple Linux à adapter au chemin réel :

```bash
docker compose -f compose.yaml run --rm --no-deps --volume /chemin/copied/circular.sqlite:/import/source.sqlite:ro app python -m backend.import_sqlite /import/source.sqlite
```

L’import conserve les identifiants et ajuste les séquences. Il refuse de fusionner avec des données déjà présentes, annule les données importées en cas d’échec, et ne modifie pas le fichier source. Les sessions et compteurs de tentatives ne sont pas transférés. Démarrer ensuite l’application, créer le compte destiné aux données historiques, puis attribuer explicitement celles-ci :

```bash
docker compose -f compose.yaml exec -T app python -m backend.claim_legacy --email personne@epita.fr
```

Vérifier que le compte choisi correspond au propriétaire attendu avant cette commande. Elle attribue les anciens projets, étiquettes, vues, modèles et favoris ; elle ne supprime pas de contenu. Pour l’option PostgreSQL intégrée, démarrer d’abord `postgres` avec les deux fichiers Compose et ajouter `-f compose.postgres.yaml` aux commandes si nécessaire.

## Sauvegarde et restauration

Utiliser la sauvegarde gérée par l’école pour une base externe. Pour PostgreSQL inclus, exemple en shell Linux, avec le même projet et `.env` que la production :

```bash
umask 077
mkdir -p backups
docker compose -f compose.yaml -f compose.postgres.yaml exec -T postgres pg_dump -U circular_admin -d circular -Fc > backups/circular.dump
```

Le format personnalisé se restaure avec `pg_restore` ([documentation PostgreSQL](https://www.postgresql.org/docs/17/app-pgrestore.html)). Chiffrer les archives selon la politique de l’école, les conserver hors de l’hôte, contrôler les erreurs de sauvegarde et tester périodiquement une restauration. Une archive contient les données et les empreintes des mots de passe ; ne pas la joindre aux rapports. Sous PowerShell ancien, éviter de rediriger un flux binaire avec `>` ; le script de validation fourni emploie des fichiers binaires Python.

Restaurer d’abord dans une **nouvelle base dédiée**, jamais en écrasant la base active pour un simple test :

```bash
docker compose -f compose.yaml -f compose.postgres.yaml exec -T postgres createdb -U circular_admin -O circular_app circular_restore
docker compose -f compose.yaml -f compose.postgres.yaml exec -T postgres pg_restore -U circular_admin --no-owner --role=circular_app --exit-on-error -d circular_restore < backups/circular.dump
```

Comparer les migrations, les comptes et des projets/tickets de contrôle, puis effectuer les parcours de connexion et de collaboration sur une instance isolée. Pour une bascule réelle, arrêter les écritures, modifier le secret de connexion par le gestionnaire, recréer l’application, vérifier `/api/ready` et les parcours, puis révoquer les sessions restaurées si la politique de reprise le prévoit. Garder la base précédente jusqu’à validation de la reprise.

## Mise à jour et retour arrière

Avant chaque version, conserver l’image précédente et une sauvegarde vérifiée. Tester la nouvelle image avec une restauration isolée et exécuter les tests de non-régression. Mettre à jour `CIRCULAR_IMAGE_TAG`, charger/construire l’image validée, puis :

```bash
docker compose -f compose.yaml -f compose.postgres.yaml up -d --no-build --wait app
docker compose -f compose.yaml -f compose.postgres.yaml ps
```

Les migrations ne disposent pas de downgrade automatique. Si le schéma reste compatible, revenir au tag précédent dans `.env` et réexécuter la même commande. Sinon, restaurer la sauvegarde dans une nouvelle base, rétablir le secret de connexion et le tag précédent, puis vérifier les parcours avant de rouvrir l’accès. Les écritures postérieures à la sauvegarde doivent être prises en compte dans la décision de reprise. Ne pas supprimer le volume pour corriger une migration.

Les versions d’images, leurs digests et les dépendances figées doivent être actualisés par une livraison testée. Le [workflow GitHub](../.github/workflows/container.yml) construit l’image et exécute un scan Trivy des paquets système/Python, bloquant sur les niveaux HIGH/CRITICAL à chaque push sur `main` et à chaque pull request. Les actions et le scanner sont figés ; il ne publie aucune image et ne déploie rien. Vérifier le résultat du commit à livrer dans [GitHub Actions](https://github.com/HugoSpy/circular/actions/workflows/container.yml). L’équipe peut transposer ces étapes à son CI ; le rythme des mises à jour, les objectifs de disponibilité et les tests de charge restent à définir.

## Validation locale reproductible

Sur des données fictives et un projet Compose isolé :

```bash
python3 scripts/init-secrets.py --directory .test-data/docker-secrets
docker compose --env-file .test-data/docker.env -p circular-validation -f compose.yaml -f compose.postgres.yaml -f compose.local.yaml up -d --no-build --wait
python3 scripts/docker-smoke.py --url http://127.0.0.1:14310 --env-file .test-data/docker.env --project circular-validation
```

Créer auparavant `.test-data/docker.env` à partir de `.env.example`, avec `CIRCULAR_HTTP_PORT=14310`, `CIRCULAR_SECRETS_DIR=.test-data/docker-secrets` et une origine HTTPS fictive (la surcharge locale l’annule). Le script crée deux comptes fictifs, exerce les permissions et les opérations métier, redémarre app/PostgreSQL, sauvegarde et restaure dans une base temporaire, puis vérifie révocation et suppressions après redémarrage. Il refuse une URL non locale ou un projet dont le nom ne commence pas par `circular-validation`.

Ce test n’installe aucun proxy ni certificat de production et ne constitue pas une validation du réseau, du SSO ou de la charge de l’école.
