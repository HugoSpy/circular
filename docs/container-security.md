# Correction du scan de l’image

Diagnostic du 28 octobre 2026 du [run GitHub en échec](https://github.com/HugoSpy/circular/actions/runs/40734658150/job/122979846897).

Le build fonctionnait. Le scan Trivy échouait sur l’ancienne base `python:3.12-slim-bookworm`, avec **61 résultats paquet/CVE HIGH ou CRITICAL**, correspondant à **15 CVE distinctes** : 59 HIGH et 2 CRITICAL. Le rapport ne proposait aucune version corrigée pour ces paquets dans cette distribution. Les dépendances Python verrouillées n’avaient aucun résultat à ces niveaux.

La reproduction locale a utilisé Trivy **0.76.1** dans un conteneur éphémère. Le scanner a lu une archive de l’image en lecture seule, sans montage du socket Docker ni accès aux bases, secrets ou profils navigateur. Les certificats publics nécessaires au réseau local ont été montés séparément ; TLS est resté vérifié. Aucun outil n’a été installé sur Windows.

## Changement retenu

- Runtime remplacé par l’[image officielle Python](https://hub.docker.com/_/python) **3.12 sur Alpine 3.24**, figée au digest `sha256:5789aa194f757888f41fa3d48e14b6feaa1b57c0af0b56fcb1372d6474d3bff0`.
- Dépendances Python inchangées et vérifiées par `requirements.lock`. Leurs wheels musllinux sont disponibles pour la plateforme Linux amd64 testée.
- Compte applicatif conservé à l’UID/GID `10001`, avec les commandes de création de compte adaptées à Alpine.
- Version de Trivy du workflow actualisée à `v0.76.1`.

Les essais de la base et de cette base avec toutes les dépendances runtime ont donné **0 HIGH et 0 CRITICAL**. L’import de FastAPI, psycopg et SQLite, ainsi que le hachage/vérification Argon2, ont réussi dans le conteneur non-root. La base Debian Trixie avait également été évaluée, mais conservait des résultats HIGH sans correction disponible ; elle n’a pas été retenue.

Le seuil de la CI reste bloquant sur HIGH/CRITICAL, y compris les résultats sans version corrigée : pas de `continue-on-error`, de liste d’exclusion ou d’activation de `ignore-unfixed`. La [documentation Trivy](https://trivy.dev/docs/latest/scanner/vulnerability/) explique la différence entre vulnérabilités corrigibles et non corrigées ; masquer ces dernières n’aurait pas corrigé l’image.

## Portée

Ce résultat daté ne garantit pas l’absence de toute vulnérabilité. Les résultats MEDIUM/LOW ne sont pas le critère de blocage de ce workflow. Le frontend est compilé dans une étape Node distincte ; Node et ses outils de build ne sont pas présents dans le runtime.

La validation de l’image applicative finale et ses parcours Docker figurent dans le [rapport de validation 2.1](workspace-validation.md). Le résultat de la CI du commit livré est disponible dans les [runs GitHub](https://github.com/HugoSpy/circular/actions/workflows/container.yml).
