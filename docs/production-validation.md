# Circular — validation de la livraison Docker et multi-utilisateur

Vérifications du **28 octobre 2026**, sur Windows avec Docker Desktop exécutant des conteneurs Linux. Les bases de test, comptes et projets utilisés sont fictifs. Aucune connexion au réseau de production de l’école, aucune publication de registre et aucune modification de la base SQLite utilisateur n’ont été effectuées.

## Résultats Docker réellement exécutés

| Vérification | Résultat |
| --- | --- |
| Configuration Compose avec PostgreSQL intégré, avec/sans override local | `docker compose … config --quiet` réussi |
| Build multistage Node → Python avec dépendances verrouillées | Réussi ; frontend `index-Cj9vRTq3.js` et `index-Chwh7RWC.css` |
| Image des parcours Docker | ID `sha256:35045b73bf0d394f3ea24c08ad87dbce602c6adf6fd2f57634140bb814b5b7fe` |
| Correspondance backend image/sources | SHA-256 comparés fichier par fichier : aucune différence |
| Démarrage app + PostgreSQL via `up --wait` | Deux conteneurs healthy ; port de test 14310 sur loopback |
| Exécution applicative | UID/GID `10001:10001`, racine en lecture seule, secret monté lisible |
| Rôle PostgreSQL `circular_app` | `rolsuper=false`, `rolcreatedb=false`, `rolcreaterole=false` |
| Génération des secrets dans un conteneur Linux | Dossier `0700`, trois fichiers `0444`, aucun contenu imprimé |
| Session, projet privé, invitation et travail partagé | Parcours HTTP réel réussi avec deux comptes distincts |
| Redémarrage de PostgreSQL et de l’application | Projet, ticket, statut, commentaire, sessions et préférences retrouvés |
| Sauvegarde/restauration | `pg_dump -Fc`, `pg_restore --exit-on-error` dans une nouvelle base isolée ; nombres de comptes/projets et contenu du ticket/commentaire comparés avec succès |
| Révocation et suppressions | Membre retiré : accès au ticket refusé ; ticket/projet supprimés puis absence vérifiée après redémarrage |
| Mode production réel du conteneur | Readiness HTTP 200 ; Host non autorisé 403 ; API privée sans session 401 ; Origin étranger 403 |
| Cookie et en-têtes de production | Cookie `Secure`, `HttpOnly`, `SameSite=Lax` ; HSTS, CSP et `nosniff` présents |

L’image de livraison `circular:2.0.0` a ensuite été reconstruite avec pour seule modification la copie de `LICENSE` et `THIRD_PARTY_NOTICES.md` : ID `sha256:aa53e674a394559d0809e48f7c77462760cfd4084e901d4a70a752767812b8da`. Le build a réussi et la présence des deux documents a été vérifiée dans ce conteneur. Le code applicatif est identique ; les parcours complets ci-dessus ont été exécutés avant cet ajout documentaire.

Le scénario Docker est conservé dans [scripts/docker-smoke.py](../scripts/docker-smoke.py). Il vérifie les propriétaires des conteneurs avant les redémarrages, refuse une origine non locale, et ne supprime que la base de restauration et le fichier de sauvegarde créés pendant son exécution. Il n’affiche ni mots de passe ni cookies. Les deux comptes fictifs restent dans la base jetable jusqu’au nettoyage du projet Compose.

Commandes significatives exécutées depuis le dossier du projet :

```powershell
docker build --secret id=build_ca,src=.test-data/build-ca.pem -t circular:2.0.0 .
docker compose --env-file .test-data/docker.env -p circular-validation -f compose.yaml -f compose.postgres.yaml -f compose.local.yaml up -d --no-build --wait --wait-timeout 90
.venv/Scripts/python.exe scripts/docker-smoke.py --url http://127.0.0.1:14310 --env-file .test-data/docker.env --project circular-validation
docker compose --env-file .test-data/docker.env -p circular-validation -f compose.yaml -f compose.postgres.yaml up -d --no-build --wait --wait-timeout 90 app
```

La première tentative de build a échoué parce que les images de base ne connaissaient pas l’autorité de certification utilisée par le réseau local. La relance a monté temporairement un bundle de **certificats publics déjà approuvés par le système** dans BuildKit. La validation TLS est restée active ; le bundle n’a pas été incorporé à l’image (`/run/secrets/build_ca` absent du conteneur final). Ce mécanisme facultatif est documenté pour les réseaux d’entreprise.

## PostgreSQL et migration

La commande suivante a réellement passé **10 tests**, dont deux tests unitaires d’adaptation du pilote et huit scénarios utilisant PostgreSQL 17 dans un conteneur distinct :

```powershell
$env:CIRCULAR_TEST_POSTGRES_URL_FILE = '.test-data/pg-url.txt'
.venv/Scripts/python.exe -m pytest tests/test_postgres.py -q --tb=short --basetemp=.test-data/pg-pytest-api
```

Résultat : **10 passed, 1 warning**, 9,43 s. L’avertissement est la dépréciation Starlette/httpx déjà présente. Chaque scénario PostgreSQL crée un schéma aléatoire et supprime uniquement ce schéma.

Couverture vérifiée : migrations idempotentes et démarrages concurrents, génération concurrente de numéros, annulation transactionnelle sur contrainte, alias et identifiants PostgreSQL, filtres Unicode avec `%`/`_` littéraux, favoris et préférences personnels, commentaires attribués à leur auteur, vues/modèles privés, ainsi qu’un parcours API complet à trois comptes avec invitations, refus d’accès, reprise de l’application et suppressions persistantes.

L’import SQLite a été testé avec une base v1 non migrée : le fichier source est resté identique octet par octet, les identifiants ont été conservés et les nouveaux identifiants PostgreSQL ont continué au-delà des valeurs importées. Une destination non vide est refusée. Une source incohérente provoque un rollback de l’ensemble des données métier importées. Les sessions ne sont pas transférées.

## Suites API et navigateur finales

| Commande exécutée | Résultat |
| --- | --- |
| `CIRCULAR_TEST_POSTGRES_URL_FILE=.test-data/pg-url.txt` puis `.venv/Scripts/python.exe -m pytest tests -q --tb=short` | **129 tests réussis**, 40,88 s, aucun test ignoré ; un avertissement de dépréciation Starlette/httpx |
| `npm run build` | TypeScript et Vite réussis, bundle final `index-Cj9vRTq3.js` |
| `node node_modules/@playwright/test/cli.js test --reporter=list --output=test-results/production-suite` | **28 parcours Chrome réussis**, 1,4 minute |
| Parcours ciblé copie du lien/duplication après ajustement du libellé | **1 test réussi**, 7,3 s |

Les 129 tests comprennent les 73 scénarios métier historiques désormais authentifiés, 28 tests d’authentification, 13 tests de partage, 5 tests de sécurité du partage (dont une mise à jour concurrente des préférences sur PostgreSQL) et les 10 tests PostgreSQL décrits plus haut. Les tests historiques ne bénéficient d’aucun contournement de l’authentification : ils créent/connectent un compte et utilisent son cookie et son CSRF.

Les parcours navigateur couvrent les opérations métier précédentes et quatre scénarios nouveaux : inscription/connexion par pseudo/changement de mot de passe/déconnexion ; projet privé puis invitation/collaboration/retrait ; compte et invitations à 390 px ; refus/annulation d’invitation et erreur de mot de passe conservant la session. Le contrôle réseau et celui des exceptions JavaScript restent actifs ; aucune requête externe ni exception détectée dans ces parcours.

Captures réellement ouvertes et inspectées : [connexion bureau](images/production-login.png), [partage de projet](images/production-sharing.png), [compte à 390 px](images/production-account-mobile.png). Le navigateur mobile est simulé dans Chrome ; Safari, Firefox et un téléphone physique n’ont pas été testés.

Les résultats des versions locales précédentes restent dans [validation.md](validation.md) à titre historique.

## Limites précises de cette validation

- Les conteneurs Linux ont été testés sur Docker Desktop Windows. Un serveur Linux natif de l’école et ses ACL/montages n’ont pas été testés ; les modes générés des secrets ont toutefois été contrôlés à l’intérieur d’un conteneur Linux.
- Le mode production et ses contrôles HTTP ont été exercés localement avec l’hôte HTTPS déclaré. Aucun véritable reverse proxy TLS, DNS de l’école ou certificat de production n’a été installé ou testé. Le modèle Nginx doit être adapté et validé par l’infrastructure.
- La sauvegarde a été restaurée dans une nouvelle base de test et son contenu comparé. La rotation distante, le chiffrement, la rétention et la reprise complète sur un autre serveur restent à intégrer aux procédures de l’école.
- L’audit automatique npm du build a signalé zéro vulnérabilité. Le scan de l’image OS/Python n’a **pas** été exécuté localement ; le workflow GitHub configure Trivy à chaque push sur `main`. Son résultat pour chaque commit est consultable dans [GitHub Actions](https://github.com/HugoSpy/circular/actions/workflows/container.yml) et ne doit pas être déduit des seuls tests fonctionnels ci-dessus.
- Pas de test de charge, de haute disponibilité, de panne disque, de montée de version PostgreSQL ou de déploiement sur plusieurs machines. Les tests de concurrence portent sur les transactions ciblées, pas sur un dimensionnement global.
- L’adresse `@epita.fr` est validée syntaxiquement ; sa possession n’est pas prouvée. Aucun SSO, SMTP, email de récupération ou collaboration temps réel n’est livré.

Les commandes de mise en service, de raccordement à une base externe, d’import, de sauvegarde, de restauration et de retour arrière figurent dans [deployment.md](deployment.md).
