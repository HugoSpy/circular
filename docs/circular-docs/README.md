# Circular Docs

Socle du service documentaire privé. Le navigateur utilise l’interface React/TypeScript. FastAPI sert cette interface et l’API sur une même origine. PostgreSQL conserve les identités et les sessions. Le [contrat du lot 1](identite.md) décrit le provisionnement et les réponses de l’API. Le [contrat du lot 2](espaces.md) décrit les espaces privés, les invitations et l’arborescence. Le [contrat du lot 3](edition.md) décrit l’éditeur et l’historique des révisions. Le [contrat du lot 4](liens.md) décrit les références et la recherche. Le [contrat du lot 5](corbeille-export.md) décrit la corbeille et l’export Markdown. Le [rapport du lot 6](recette-pilote.md) donne les résultats et les commandes de la recette locale.

## Démarrer en local

Exécuter les commandes ci-dessous à la racine du dépôt du service Circular Docs. Voir le [plan d’implémentation](../knowledge-workspace-implementation-plan.md) pour les lots suivants.

Prérequis pour la recette du lot 1 : Python 3.12 ou ultérieur, une version LTS de Node compatible avec Vite 7 et PostgreSQL (les outils `initdb` et `pg_ctl` doivent être dans le `PATH` pour les tests). Fournir une base PostgreSQL **de développement propre à Circular Docs**.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm ci
npm run build
```

Pour créer une base locale dédiée sur le port 55432, utiliser par exemple :

```sh
initdb --pgdata .local/pg --username circular_docs --auth=scram-sha-256 --pwprompt
pg_ctl -D .local/pg -l .local/postgres.log -o '-h 127.0.0.1 -p 55432' -w start
```

La base par défaut est `postgres` dans cette instance. Pour l’arrêter, utiliser `pg_ctl -D .local/pg -m fast -w stop`.

Renseigner `DOCS_DATABASE_URL`, `DOCS_OIDC_CLIENT_ID` et `DOCS_OIDC_CLIENT_SECRET` dans l’environnement local. `DOCS_PUBLIC_ORIGIN` vaut `http://127.0.0.1:8000` par défaut. La redirection correspondante est déclarée par le client public de test Forge ID. Conserver le secret du client dans l’environnement local.

```sh
.venv/bin/python -m circular_docs migrate
.venv/bin/python -m circular_docs allow votre.adresse@epita.fr
.venv/bin/python -m circular_docs serve
```

Ouvrir `http://127.0.0.1:8000`. Pour révoquer l’accès d’un compte, exécuter `.venv/bin/python -m circular_docs disable adresse@epita.fr` avec l’adresse de provisionnement. La réactivation demande une opération de maintenance explicite.

## Vérifier

```sh
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

Les tests démarrent un PostgreSQL éphémère sur un socket local et le ferment à la sortie. Le parcours navigateur utilise le port local 8000 et un fournisseur OIDC de test. Les JWT de recette sont signés avec une clé propre à l’exécution. Le test vérifie que le code échangé présente le bon vérificateur PKCE. Les tests API couvrent aussi les migrations répétées, les revendications invalides, la réutilisation d’une tentative et la révocation.

[Documentation Forge ID consultée le 21 novembre 2026](https://docs.forge.epita.fr/services/forge-id/oidc/)
