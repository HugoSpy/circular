# Espaces et parcours de création

Évolution du 28 octobre 2026. Cette spécification s’appuie sur les captures fournies par l’utilisateur, pas sur une nouvelle session d’observation de Linear. Aucun code, logo ou fichier de marque n’est repris.

## Ce que montrent les références

- Un écran de création d’espace avec nom et identifiant d’URL.
- Une préparation du profil, des invitations et des étapes facultatives de connexion à des services.
- Une arrivée dans une liste de tickets déjà contextualisée ; les captures montrent une équipe dans Linear.
- Un menu en haut à gauche réunissant paramètres, membres, changement d’espace et déconnexion.

## Adaptation à Circular

Un **espace** contient des **projets**, qui contiennent des **tickets**. La première création d’espace prépare un premier projet du même nom et trois tickets d’accueil originaux, modifiables et supprimables. Ce projet initial est un choix de conception Circular qui répond au parcours demandé ; il ne prétend pas reproduire le modèle d’équipes complet de Linear.

Après inscription, un compte sans espace voit la création d’espace. Le nom et le slug sont validés et sauvegardés par l’API. Le profil et les invitations peuvent être configurés ensuite ou passés. Une actualisation ne doit ni dupliquer le projet initial ni recommencer les étapes déjà terminées.

Le menu d’espace permet de changer d’espace, en créer un autre, accéder aux paramètres, gérer les membres, ouvrir le profil et se déconnecter. La gestion des membres n’est pas proposée aux invités limités à un projet. Le bouton « Mon compte » reste accessible dans l’application pour le mot de passe. L’espace courant reste identifiable dans la navigation. Le changement recharge les projets, tickets, filtres, vues et modèles de cet espace ; aucun état du précédent ne doit apparaître dans le suivant.

Le profil, les invitations et la fin de l’onboarding sont persistés en base. La sous-étape en cours est représentée par le paramètre d’URL `setup`, qui permet de reprendre le même écran après actualisation ; aucun stockage navigateur ne remplace la persistance serveur.

Les données existantes sont conservées lors de la migration. L’accès à un ancien projet partagé ne donne pas automatiquement accès aux autres projets de son propriétaire. Les contrôles d’accès sont effectués par le backend, y compris pour les identifiants saisis directement dans les URLs et les appels API.

## Intégrations explicitement limitées

À la demande de l’utilisateur, GitHub et Slack disposent d’écrans de présentation portant la mention « À venir ». Leur action affiche « Intégration pas encore implémentée ». Aucun OAuth, jeton, synchronisation ou appel à ces services n’est effectué. Il n’existe pas de faux état « connecté » ni d’abonnement aux actualités.

La région d’hébergement n’est pas sélectionnable : elle est déterminée par l’infrastructure qui déploie Circular. Les invitations fonctionnent dans Circular ; aucun email n’est envoyé par un service SMTP.

## Direction et interactions

Le graphite, le jaune, la typographie et les composants existants restent la base. Un formulaire principal par étape, des libellés visibles, des états de chargement et d’erreur, un retour possible et des étapes facultatives évitent un parcours bloquant. Les menus doivent être utilisables au clavier, se fermer avec Échap et rendre le focus au déclencheur. Le parcours et la navigation doivent rester utilisables à 390 px.

Le skill `front-maxer` a guidé cette adaptation. La première recherche de système de design Pro Max a proposé un résultat hors sujet ; il n’a pas été appliqué. La recherche ciblée sur l’onboarding a confirmé l’intérêt des actions Passer/Retour. Les principes transférables des références Apple sur l’onboarding et les menus ont servi à examiner la progression, le regroupement des actions et le focus, sans imposer des conventions natives au web.

## Critères de validation

1. Un nouveau compte crée un espace, configure ou passe les étapes et retrouve son projet et ses tickets d’accueil.
2. Le profil, l’avancement et les données survivent à une actualisation et à un redémarrage.
3. Deux espaces distincts conservent leurs projets, tickets, vues, modèles et filtres sans mélange.
4. Les invitations et retraits de membres changent réellement les accès ; un utilisateur non autorisé ne peut pas lire un autre espace.
5. Les projets historiques et leurs restrictions restent intacts après migration.
6. Les menus fonctionnent au clavier et sur une largeur mobile ; GitHub/Slack affichent leur limitation sans requête externe.

Les tests effectivement exécutés et les limites constatées sont consignés lors de la livraison ; ces critères seuls ne constituent pas une preuve d’exécution.
