# Plan d’implémentation de l’espace documentaire

Le jalon 1 livre un wiki privé pour écrire des spécifications, retrouver les décisions d’un projet et ouvrir les tickets correspondants dans Circular. L’application documentaire est un service distinct. Circular conserve la gestion des tickets et de leurs droits. Les collections éditables constituent le jalon 2. Le déploiement fera l’objet d’un plan séparé.

Les contrats ci-dessous servent de base aux lots d’implémentation. La [spécification produit approuvée](knowledge-workspace-spec.md) fixe les comportements attendus.

## Ordre des lots

| Lot | Livrable | Dépendances | Exigences |
| --- | --- | --- | --- |
| 1 | Socle du service et contrat d’identité | Décisions sur le dépôt cible et le fournisseur d’identité | DOC-05 |
| 2 | Espaces privés, invitations et arborescence | Lot 1. Validation de la maquette avant le code d’interface | DOC-01, DOC-05 |
| 3 | Éditeur Markdown, sauvegardes et révisions | Lot 2, contrat Markdown du lot 4 pour les références internes | DOC-02, DOC-06 |
| 4 | Liens, backlinks et recherche | Lots 2 et 3 pour l’intégration. Contrat Markdown à définir dès le lot 3 | DOC-03, DOC-04, DOC-08 |
| 5 | Corbeille et export Markdown | Lots 2 à 4 | DOC-06, DOC-07 |
| 6 | Recette du pilote | Lots 1 à 5, équipe et projet pilote identifiés | DOC-01 à DOC-08 |

Après validation du cadrage, préparer une maquette HTML avec des données fictives. Montrer l’arborescence, la lecture et l’édition, les invitations, la recherche, les backlinks, l’historique et la corbeille, ainsi que les états vides, les erreurs et les conflits de sauvegarde. Vérifier les parcours sur ordinateur et mobile. Conserver dans le dépôt la référence et le périmètre validés. Le code d’interface attend la validation explicite de la maquette. Le schéma, les contrats et les tests API peuvent avancer en parallèle lorsqu’ils n’en dépendent pas. [Workflow Circular](../AGENTS.md)

## Lot 1 — Socle du service et identité

Le socle a été vérifié localement le 21 novembre 2026. Le [contrat d’identité et le rapport de recette](circular-docs/identite.md) consignent les décisions et les vérifications restantes, dont la connexion au fournisseur avec un compte EPITA réel. Le [guide local de Circular Docs](circular-docs/README.md) explique comment démarrer le service.

- **Livrables.** Définir le dépôt cible, le propriétaire des comptes et le mode de provisionnement. Mettre en place React/TypeScript, l’API FastAPI, les migrations et une base PostgreSQL isolée pour le développement et les tests. Reprendre de Circular le découpage routes, services et dépôts, ainsi que le principe de vérifier l’accès côté serveur.
- **Contrat.** Fixer la représentation de l’identité stable, le cycle de session et le traitement d’une session expirée ou révoquée. Définir le format commun des erreurs et des listes paginées. Prévoir `401` en l’absence de session et `404` pour une ressource absente ou située hors du périmètre de l’appelant. Utiliser `403` si un membre peut voir la ressource mais ne possède pas le droit demandé.
- **Critère de sortie.** Sur une base vierge, les migrations aboutissent et leur relance préserve les données. Deux identités de test distinctes ouvrent des sessions indépendantes. Une requête sans session reçoit `401`. La décision d’identité est consignée avant l’implémentation du parcours d’invitation.

## Lot 2 — Espaces, invitations et arborescence

Le [contrat du lot 2 et la maquette approuvée](circular-docs/espaces.md) décrivent les droits, les invitations de sept jours et la navigation.

- **Livrables.** Créer les espaces, les adhésions et les invitations. Créer, lire, renommer et déplacer une page racine ou enfant. Afficher l’arborescence et le fil d’Ariane après validation de la maquette.
- **Contrat.** Donner à l’espace et à la page des identifiants stables. Un parent appartient au même espace que son enfant. Autoriser les doublons de titre et trier les frères par titre puis identifiant. Créer l’espace et son adhésion propriétaire en une transaction. L’acceptation d’une invitation est réservée au compte invité et crée une seule adhésion. Appliquer les rôles propriétaire, éditeur et lecteur à chaque requête. Sérialiser les modifications concurrentes de l’arborescence au sein d’un espace pour empêcher les cycles et les parents devenus indisponibles.
- **Critère de sortie.** Un lecteur invité obtient `404` sur le lien direct avant acceptation, peut lire après acceptation et obtient `403` sur une tentative d’édition. Un déplacement change le fil d’Ariane sans changer l’URL. Une tentative de cycle, y compris par deux déplacements concurrents, laisse une arborescence valide.

## Lot 3 — Éditeur Markdown, sauvegarde et révisions

Le [contrat d’édition du lot 3 et la maquette approuvée](circular-docs/edition.md) décrivent la conversion Markdown, les erreurs de sauvegarde et la restauration.

- **Livrables.** Stocker le titre, la source Markdown et le numéro de révision. Fournir l’éditeur visuel et la vue source, l’autosauvegarde, la reprise après erreur, l’historique et la restauration d’une révision. Couvrir les formats de DOC-02. Maintenir la page en mode source lorsque l’éditeur visuel ne peut pas représenter le contenu fidèlement.
- **Contrat.** Figer le sous-ensemble Markdown et ses règles de conversion à partir d’exemples représentatifs, dont les références internes du lot 4. Chaque sauvegarde transporte la révision attendue et un identifiant de requête. Après vérification des droits, le serveur rejoue le résultat d’une requête déjà appliquée si son contenu est identique. Un identifiant réutilisé avec un contenu différent ou une révision périmée reçoit `409`. Une sauvegarde modifiée crée un instantané immuable du titre et du corps avec son auteur. La restauration d’une ancienne révision crée une nouvelle révision et suit les mêmes contrôles. Au lot 4, la mise à jour de l’index des liens rejoint cette transaction.
- **Critère de sortie.** Deux éditeurs chargent la révision 3. Le premier crée la révision 4. Le second voit le conflit, garde son brouillon et peut le comparer à la version enregistrée. Rejouer la première demande après une réponse perdue ne duplique pas la révision. La vérification de conversion couvre le cycle source, visuel, source ainsi que le maintien en mode source si nécessaire.

## Lot 4 — Références internes, backlinks et recherche

Le [contrat du lot 4 et la maquette approuvée](circular-docs/liens.md) décrivent la palette, l’index des références, la recherche et les droits d’accès.

- **Livrables.** Ajouter la recherche par titre et contenu, la palette de liens `[[`, les backlinks et la saisie de liens Circular. La palette affiche le fil d’Ariane pour distinguer les titres identiques.
- **Contrat.** Analyser le Markdown et indexer les liens explicites hors des blocs et fragments de code. Utiliser `[](/pages/{id})` pour un libellé automatique et `[Libellé](/pages/{id})` pour un libellé personnalisé. Résoudre le libellé automatique à partir du titre courant. Garantir un backlink par paire source-cible, et mettre à jour l’index dans la transaction de sauvegarde ou de restauration d’une révision. La recherche filtre par accès et état actif avant de calculer extraits et résultats. Une requête vide renvoie une liste vide. Appliquer le classement titre d’abord, date de modification décroissante puis identifiant. Un lien Circular reste une URL avec un libellé saisi par l’utilisateur. L’ouverture du ticket utilise les droits de Circular.
- **Critère de sortie.** Parmi deux pages de même titre, seule la cible choisie reçoit un backlink, même si le lien figure plusieurs fois. Renommer ou déplacer la cible conserve le lien, actualise le libellé automatique et préserve le libellé personnalisé. Une recherche avec une casse différente retrouve le contenu attendu. Un membre révoqué ne retrouve la page ni dans les résultats, ni dans les suggestions, ni dans les backlinks.

## Lot 5 — Corbeille et export Markdown

- **Livrables.** Mettre à la corbeille et restaurer des sous-arbres, puis exporter les pages actives dans un ZIP de Markdown UTF-8 accessible aux membres actuels.
- **Contrat.** Définir comment marquer les pages emportées par une opération de corbeille afin de préserver une suppression antérieure lors d’une restauration. Traiter chaque opération en une transaction. Si le parent d’origine est indisponible, restaurer à la racine. Exclure les pages supprimées des surfaces actives. Pour l’export, établir la carte des chemins avant de générer les fichiers, assainir les noms et ajouter un suffixe stable afin de gérer les doublons. Utiliser un instantané cohérent des pages exportées. Réécrire les liens de page vers des chemins relatifs et produire un libellé suivi de « (page indisponible) » si la cible est absente de l’export. Conserver les URL externes et Circular.
- **Critère de sortie.** Après suppression d’un parent, son sous-arbre disparaît des surfaces actives et ses liens entrants signalent l’indisponibilité. La restauration rétablit les liens et backlinks. Après extraction d’un ZIP contenant des titres identiques et des caractères Unicode, les liens relatifs s’ouvrent dans les deux sens et les URL externes et Circular restent utilisables. Une demande postérieure à la révocation de l’adhésion ne permet plus de télécharger l’export.

## Lot 6 — Recette du pilote

- Identifier l’équipe et le projet pilote. Parcourir le scénario complet avec les rôles propriétaire, éditeur et lecteur, sur ordinateur et mobile. Utiliser un jeu de données fictif pour la recette reproductible et un ticket Circular accessible uniquement aux personnes autorisées.
- Vérifier sur PostgreSQL les permissions, les collisions de sauvegarde, la reprise après perte de réponse et les mutations d’arborescence concurrentes. Utiliser Playwright pour les parcours navigateur et vérifier le ZIP extrait indépendamment de l’interface.
- Pour chaque test de régression ajouté ou étendu, constater l’échec attendu après une mutation temporaire, restaurer le comportement et relancer le test. Avant chaque push dans Circular, suivre les commandes et règles de compte rendu du workflow. Les commandes du futur dépôt seront consignées avec son socle.
- Clore le jalon lorsque les scénarios ci-dessous sont vérifiés et que les résultats, les écarts et les vérifications restantes sont documentés. [Workflow Circular](../AGENTS.md)

| Scénario de la spécification | Lot qui apporte la preuve | Preuve à conserver |
| --- | --- | --- |
| 1. Création et partage | Lots 2 et 4 | Résultats API et parcours de recherche du lecteur avant et après acceptation |
| 2. Lien, renommage et déplacement | Lots 2 et 4 | Identifiant de cible, lien encore navigable et backlink unique |
| 3. Sauvegardes concurrentes | Lot 3 | Réponse `409`, brouillon conservé et décompte des révisions après rejeu |
| 4. Corbeille et restauration | Lots 2 et 5 | Arborescence avant et après, réapparition des liens et refus d’un cycle |
| 5. Export et ouverture | Lot 5 | ZIP de test et vérification des chemins et URL après extraction |
| 6. Révocation | Lots 2, 4 et 5 | Résultats post-révocation sur lien direct, recherche, suggestions, backlinks et export, puis contrôle séparé des droits du ticket Circular |

## Décisions à consigner

| Décision | Échéance |
| --- | --- |
| Dépôt du service, fournisseur d’identité, provisionnement des comptes et éventuelle identité EPITA partagée | Lot 1 |
| Durée de validité des invitations, formats et limites de titre et de Markdown, règles de comparaison et de pagination | Avant les contrats des lots 2 à 4 concernés |
| Volumes du pilote, conservation de l’historique, durée de rétention de la corbeille et suppression définitive | Avant de figer les contrats de révisions et de corbeille |
| Équipe pilote, projet, volume représentatif et critères de performance mesurables | Avant la recette du lot 6 |
| Besoin d’import d’un coffre Obsidian, traitement des propriétés et pièces jointes | Décision de périmètre distincte |
| Schémas de collections, types de propriétés, vues table et filtres enregistrés | Plan du jalon 2 |
| Hébergement, environnements, domaines et exploitation | Plan de déploiement séparé |

Références locales consultées le 20 novembre 2026. [Spécification produit](knowledge-workspace-spec.md) · [Architecture Circular](architecture.md) · [Commandes du dépôt](../package.json) · [Configuration Playwright](../playwright.config.ts)
