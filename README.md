# Circular

Gestion de projets et de tickets avec **comptes utilisateurs et projets privés partageables sur invitation**. Interface React/TypeScript graphite et jaune, backend FastAPI en couches, **PostgreSQL en production**. Docker fournit le frontend compilé et l’API dans une même image. Aucun appel à Linear ni clé API externe.

Code publié sous [licence MIT](LICENSE), avec [notices des dépendances](THIRD_PARTY_NOTICES.md). Dépôt : [HugoSpy/circular](https://github.com/HugoSpy/circular).

## Livraison à l’infrastructure de l’école

Le [guide de déploiement](docs/deployment.md) est le document à transmettre à l’infra : secrets, HTTPS/reverse proxy, PostgreSQL fourni ou externe, sauvegarde/restauration, mises à jour et retour arrière. Le [rapport de validation](docs/production-validation.md) distingue les vérifications exécutées des opérations restant à réaliser sur l’environnement de l’école.

Fichiers livrés :

- `Dockerfile` multi-stage, processus non-root et contrôle de santé.
- `compose.yaml` : application connectée à une base PostgreSQL externe via secret monté.
- `compose.postgres.yaml` : ajout facultatif de PostgreSQL 17 avec volume persistant et rôle applicatif non-superutilisateur.
- `compose.local.yaml` : HTTP sur loopback pour les essais locaux uniquement.
- `.env.example` : configuration publique ; `scripts/init-secrets.py` génère les secrets de la base Compose sans les afficher ni remplacer les fichiers existants.
- Migrations SQLite/PostgreSQL, outil d’import de l’ancienne base SQLite, tests API et navigateur.

### Essai Docker local avec PostgreSQL

Prérequis : Docker avec moteur Linux et Compose récent, Python 3 pour générer les secrets. À la racine de ce dossier :

```powershell
Copy-Item .env.example .env
python scripts/init-secrets.py
docker compose -f compose.yaml -f compose.postgres.yaml -f compose.local.yaml up -d --build
```

Ouvrir **http://127.0.0.1:4310**, créer un compte puis un projet. Si le port est occupé, changer `CIRCULAR_HTTP_PORT` dans `.env`. Sous Linux, utiliser `cp .env.example .env` et `python3` pour les deux premières commandes.

```powershell
docker compose -f compose.yaml -f compose.postgres.yaml -f compose.local.yaml ps
docker compose -f compose.yaml -f compose.postgres.yaml -f compose.local.yaml logs --tail 100 app
docker compose -f compose.yaml -f compose.postgres.yaml -f compose.local.yaml down
```

`down` conserve le volume de données. **Ne pas ajouter `-v`** pour un environnement contenant des données à conserver. Le [guide](docs/deployment.md) précise la construction derrière une autorité de certification d’entreprise ; TLS ne doit pas être désactivé.

### Production

L’infra définit le domaine HTTPS, le reverse proxy, les adresses de proxy autorisées et les secrets. Le fichier `secrets/database_url` contient l’URL PostgreSQL ; ne pas la coller dans le dépôt ou les rapports. Pour une base externe, le rôle possède le schéma et peut appliquer les migrations, sans être superutilisateur. Vérifier les certificats de la base distante avec `sslmode=verify-full` et son certificat d’autorité si nécessaire.

```bash
# Après préparation de .env, des secrets et du reverse proxy selon le guide :
docker compose -f compose.yaml up -d --build
# Ou avec PostgreSQL fourni et son volume :
docker compose -f compose.yaml -f compose.postgres.yaml up -d --build
```

Ne pas inclure `compose.local.yaml` en production. L’application refuse une configuration de production sans URL publique HTTPS ou sans PostgreSQL. Le port HTTP interne reste derrière le reverse proxy ; `/api/health` indique la vie du processus et `/api/ready` teste aussi la base.

## Comptes, confidentialité et partage

Inscription avec pseudo unique, adresse `@epita.fr` et mot de passe de 12 à 128 caractères ; connexion par pseudo ou adresse. Le contrôle du domaine **ne vérifie pas la possession de l’adresse** : aucun courriel de validation ou d’invitation n’est envoyé. Ce point doit être accepté pour le pilote, ou complété par une validation mail/SSO avant une ouverture nécessitant une identité scolaire certifiée.

Chaque projet appartient à son créateur et reste privé. Celui-ci invite un compte déjà inscrit par son adresse ; le destinataire accepte ou refuse dans l’application. Après acceptation, les membres gèrent les tickets et commentent. Seul le propriétaire modifie/supprime le projet, invite ou retire les membres. Les liens de tickets restent soumis à ces droits.

Préférences, vues enregistrées, modèles et favoris sont personnels. Les étiquettes appartiennent à leur créateur ; une étiquette attachée à un ticket partagé est visible aux membres, mais seul son créateur la modifie. Les commentaires affichent leur auteur : seul cet auteur les modifie ; le propriétaire du projet peut aussi les supprimer. Un retrait d’accès prend effet sur les requêtes suivantes.

Mots de passe hachés avec Argon2id, sessions serveur révocables, cookies HttpOnly/SameSite et Secure en production, contrôle CSRF des mutations, limites de tentatives conservées en base. Durée maximale de session : 12 heures, expiration après 30 minutes d’inactivité. Changer ou réinitialiser un mot de passe révoque les sessions. Aucun jeton n’est conservé dans localStorage.

## Fonctions

- Projets : nom, préfixe stable, description, couleur, statut, échéance et membres.
- Tickets : identifiant, titre, description, projet, statut, priorité, étiquettes, échéance ; création/modification/suppression, duplication et modèles.
- Liste et tableau : glisser-déposer, recherche, filtres multiples, tri, groupement, propriétés et colonnes configurables.
- Détail en panneau ou page, liens directs, commentaires et journal des opérations.
- Vues enregistrées, favoris, création successive et palette de commandes.
- Raccourcis : `C`, `/`, `Ctrl/⌘+K`, `Ctrl/⌘+Entrée`, `Échap` ; protections des saisies non sauvegardées.

Un projet contenant des tickets ne peut pas être supprimé. Le préfixe de projet est unique à l’instance et l’identifiant d’un ticket reste stable après changement de projet.

## Développement hors Docker

Node.js 22.12+ et Python 3.11+ requis. Sous PowerShell :

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
npm ci
npm run build
npm start
```

Si `.venv` a été créé sans pip et que `uv` est déjà installé : `uv pip install --python .venv/Scripts/python.exe -r requirements-dev.lock`. Sous Linux/macOS : `python3 -m venv .venv`, puis `.venv/bin/python -m pip install -r requirements-dev.lock`.

Sans configuration PostgreSQL, le développement utilise `data/circular.sqlite`. L’authentification reste obligatoire. `npm run dev` démarre Vite sur 5173 avec proxy vers FastAPI sur 4310. Relancer après modification du backend. Les migrations s’appliquent automatiquement et ne réinjectent jamais de démonstration.

## Anciennes données et démonstration

Les données de la version mono-utilisateur sont conservées par migration et restent invisibles aux nouveaux comptes jusqu’à leur attribution explicite. Après inscription du compte destinataire :

```powershell
.\.venv\Scripts\python.exe -m backend.claim_legacy --email votre.adresse@epita.fr
```

Cette commande opérateur attribue les projets historiques encore sans propriétaire ; elle ne revendique pas l’identité des auteurs de commentaires historiques. `npm run seed` reste facultatif et réservé au développement : il crée un jeu fictif, à attribuer ensuite par cette commande. Il est refusé en production.

L’import vers PostgreSQL s’effectue **vers une base vide**, application arrêtée, avec `python -m backend.import_sqlite chemin/source.sqlite` et la connexion cible fournie par `CIRCULAR_DATABASE_URL_FILE`. La source est lue sans modification. L’outil conserve les identifiants et ne transfère pas les sessions. Voir les commandes Docker détaillées dans le guide.

## Tests

```powershell
npm test
npm run build
npm run test:e2e
```

Chrome installé est utilisé par Playwright ; les tests ne se connectent pas au profil personnel. Chaque parcours démarre un backend et une base isolés. Pour inclure PostgreSQL, fournir une **base de test dédiée** par `CIRCULAR_TEST_POSTGRES_URL_FILE` : un schéma temporaire est créé et supprimé par test. Sans configuration, ces tests sont explicitement ignorés, pas déclarés réussis. Les résultats datés figurent dans [production-validation.md](docs/production-validation.md).

## Architecture et documents

```text
src/                       React, authentification, partage et client API typé
backend/app/api/           Routes HTTP et dépendances d’authentification
backend/app/schemas/       Validation Pydantic et contrats JSON
backend/app/services/      Droits d’accès, règles métier et transactions
backend/app/repositories/  Requêtes SQL paramétrées et filtrées par compte
backend/app/db/            Connexions SQLite/PostgreSQL et migrations
backend/app/core/          Configuration, mots de passe et protections HTTP
deploy/                   Initialisation PostgreSQL et exemples d’exploitation
tests/                    Tests API, PostgreSQL et parcours navigateur
docs/                     Spécifications, architecture, audits et exploitation
```

[Architecture](docs/architecture.md) · [Spécification](docs/specification.md) · [Déploiement](docs/deployment.md) · [Validation actuelle](docs/production-validation.md) · [Audit de référence](docs/observation-linear.md)

## Limites actuelles

Pas de validation de propriété de l’adresse mail, SSO, récupération de mot de passe par mail ni collaboration temps réel. La récupération est opérée par l’infra via `python -m backend.manage reset-password --email ...` après vérification de l’identité. Les workflows personnalisables, sous-tickets, pièces jointes, texte riche et administration avancée restent hors périmètre. Les listes ne sont pas paginées et aucun test de charge à l’échelle de l’école n’a été réalisé. La qualification sur le domaine, le proxy et la base de l’école reste à faire par son infrastructure.
