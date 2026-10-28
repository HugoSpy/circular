# Linear → Circular : relevé fonctionnel

Observation du **16 octobre 2026**, dans la session Linear ouverte par l’utilisateur dans **Opera GX**, avec le plugin **Computer Use**. Objectif : relever les interactions utiles à Circular, application locale mono-utilisateur, sans reprendre le code ni l’identité de Linear.

> **État après implémentation, 16 octobre 2026.** Ce document conserve le relevé et la comparaison tels qu’établis avant les développements. Les mentions « actuel », « proposé » et « non implémenté » ci-dessous se rapportent à ce moment de l’audit. Les paramètres persistants, affichages, filtres, vues, favoris, commandes, modèles, duplication et fonctions de suivi ajoutés ensuite sont décrits dans le [bilan d’implémentation](implementation-audit.md) et la [spécification actualisée](specification.md). Les limites d’observation de Linear restent inchangées.

## Méthode et niveau de preuve

La fenêtre Opera GX et l’interface Linear ont réellement été observées à l’écran. Les menus ont été ouverts par clics et les pages parcourues par défilement. L’arbre d’accessibilité retourné par Opera était vide ; l’observation a donc utilisé les captures de l’outil et les positions des contrôles visibles. Aucun DOM, script propriétaire, stockage du navigateur, cookie, jeton ou appel réseau privé n’a été extrait.

Le relevé conserve uniquement les noms génériques des fonctions et leurs interactions. Aucun titre ou contenu de ticket, identifiant métier, nom d’espace, nom de membre, adresse électronique ou capture de l’espace privé n’est enregistré dans le dépôt. Les captures de travail ont été affichées par l’outil, sans être exportées en fichiers.

Trois niveaux sont distingués :

- **Observé** : écran ou menu réellement ouvert et lu.
- **Vérifié** : réaction réellement constatée après une action sans modification métier.
- **Proposé** : adaptation pour Circular ; ce n’est ni un comportement prouvé de Linear ni une fonction déjà livrée.

Les seuls changements de présentation effectués ont été temporaires : ouverture d’un filtre avancé vide puis retrait, passage Liste → Tableau → Liste. Le formulaire de ticket est resté vide ; la ligne de création d’étiquette a été annulée vide. Aucun ticket, commentaire, étiquette ou réglage métier n’a été créé, modifié ou supprimé. À la fin, la liste initiale était affichée sans menu ni formulaire ouvert ; les indicateurs de modification de présentation avaient disparu. La persistance des préférences Linear n’a pas été testée par rechargement.

Ce relevé complète le constat du **15 octobre** : REA était indisponible et le port 9222 refusait alors la connexion. L’observation du 16 octobre a utilisé Computer Use, **pas REA** ; elle ne prouve pas que REA ou ce port sont désormais disponibles. Aucun outil supplémentaire n’a été installé et aucune configuration globale n’a été modifiée.

## 1. Liste et affichage

**Observé.** Navigation latérale, fil d’Ariane, favori et barre d’outils. Onglets de tickets **Active**, **Backlog**, **All issues**. Groupes par statut avec icône, titre, compteur, chevron et bouton d’ajout. Lignes compactes : priorité, identifiant, statut, titre, puis métadonnées. Une case de sélection apparaît sur une ligne. La zone basse peut signaler des tickets masqués par les options et propose **Show options**.

Le bouton d’affichage ouvre un panneau :

| Contrôle | Options réellement lues | Limite |
| --- | --- | --- |
| Présentation | List / Board | Bascule aller-retour vérifiée |
| Grouping | No grouping, Status, Assignee, Agent, Project, Priority, Label | Menu ouvert ; aucun autre groupement appliqué |
| Sub-grouping | Champ visible, No grouping affiché | Autres choix non ouverts |
| Ordering | Manual, Title, Status, Priority, Assignee, Agent, Estimate, Updated, Created, Due date, Link count, Time in status | Menu ouvert ; tri non changé |
| Sens du groupement et du tri | Icônes de direction | Effet non testé |
| Tickets terminés | Order completed by recency ; Completed issues | Sélecteur et interrupteur visibles ; valeurs alternatives non explorées |
| Sous-tickets et triage | Show sub-issues ; Show triage issues | Visibles, non modifiés |
| Options de liste | Nested sub-issues ; Show empty groups | Visibles, non modifiées |
| Propriétés de ligne | ID, Status, Assignee, Creator, Priority, Project, Due date, Milestone, Release, Labels, Links, Time in status, Created, Updated, Merge requests | Boutons d’affichage visibles ; non activés/désactivés |

**Pour Circular.** Conserver une liste dense et lisible, séparer le filtrage du réglage d’affichage, rendre les groupes repliables et permettre tri/groupement/propriétés visibles. Les champs proposés doivent correspondre aux données réellement présentes dans la base. Les fonctions Agent, Release ou Merge requests ne justifient pas des boutons vides.

## 2. Tableau

**Vérifié.** Le choix Board transforme la liste en colonnes. **Observé.** Chaque en-tête comprend statut, compteur, menu et ajout. Les cartes portent identifiant, titre et métadonnées. Une barre de défilement horizontale est visible sous le tableau et une barre verticale dans une colonne longue ; ces défilements n’ont pas été actionnés. Des colonnes réduites sont visibles à droite.

**Observé.** Le panneau d’affichage adapte son vocabulaire : **Columns**, **Rows**, **Ordering**, **Show empty columns**, propriétés de carte. Les actions **Reset** et **Set default for everyone** apparaissent après le changement de présentation. Elles n’ont pas été exécutées. Le menu d’une colonne contient **Select all in column** et **Hide column**, sans action exécutée.

Le déplacement d’une carte, la sélection groupée et le masquage d’une colonne n’ont pas été testés sur les données réelles. Le retour à **List** a été vérifié à l’écran.

**Pour Circular.** Ajouter le masquage/repli des colonnes et la configuration des propriétés. Conserver le changement de statut déjà fonctionnel par déplacement et par commande accessible au clavier. Si un groupement autre que statut est ajouté, expliciter quelle propriété un déplacement modifie et tester son effet serveur avant de l’activer.

## 3. Filtres

**Observé.** Le menu comporte une recherche de filtre et les entrées : AI filter, Advanced filter, Status, Assignee, Agent, Agent Session, Creator, Priority, Labels, Relations, Suggested label, Dates, Project, Project properties, Initiative, Subscribers, Auto-closed, Content, Links, Template. Le raccourci **F** est indiqué dans cette interface ; il n’a pas été essayé.

**Vérifié.** Advanced filter ajoute un conteneur de filtre vide avec une commande d’ajout de condition. Ce conteneur a été retiré ensuite. Aucune condition n’a été construite : la combinaison ET/OU, les opérateurs, les valeurs multiples et leur résultat ne sont **pas vérifiés**.

**Pour Circular.** Première extension utile : filtres d’étiquettes et valeurs multiples de statut/priorité, avec résumé visible et réinitialisation. Proposition de sémantique à documenter et tester : OU entre valeurs d’un même champ, ET entre champs. Cette règle est un choix Circular, pas une conclusion tirée de Linear. Les filtres de dates attendront l’ajout effectif des dates concernées.

## 4. Création de ticket

**Observé.** L’icône globale de composition ouvre un formulaire superposé. Il contient :

- Sélecteur de contexte d’équipe et bouton **Template** en haut.
- Titre puis description, sans grande série de libellés répétitifs.
- Propriétés sous forme de boutons : statut, priorité, responsable, projet, étiquettes.
- Menu supplémentaire : **Set due date**, **Make recurring…**, **Add link…**, **Add to release**, **Add sub-issue**.
- Pièce jointe, option **Create more**, bouton **Create issue**, agrandissement et fermeture.

**Vérifié.** Ouverture du formulaire et de son menu supplémentaire ; fermeture du formulaire vide. Aucun champ rempli, aucune soumission. La récurrence, les modèles, l’agrandissement, les pièces jointes et l’effet de Create more restent non testés.

**Pour Circular.** Garder les champs actuels avec des sélecteurs compacts et leur libellé accessible. Ajouter « Créer un autre » et la duplication avant les fonctions complexes. Un modèle local peut préremplir titre/description/propriétés ; une création normale doit rester possible sans modèle. L’équipe et le responsable ne sont pas nécessaires à la version mono-utilisateur.

## 5. Détail, commentaires et actions

**Vérifié.** Le clic sur une ligne ouvre, dans le parcours observé, une **page de détail** avec un chemin propre dans l’adresse. Le fil d’Ariane permet de revenir à la liste. Cela ne démontre pas que tous les parcours Linear utilisent une page plutôt qu’un panneau.

**Observé.** Titre et description structurée au centre ; propriétés à droite : statut, équipe, priorité, responsable, étiquettes, projet. Sections de dépendances **Blocked by** et **Blocking**. Favori, menu et flèches de navigation entre tickets dans l’en-tête. Au bas du contenu : **Add sub-issues**, **Activity**, abonnement, événements datés puis champ de commentaire avec pièce jointe et bouton d’envoi. Le journal présente des changements de propriétés et de relations ; aucun contenu privé n’est repris ici.

Le menu du ticket, réellement ouvert, présente :

| Famille | Commandes visibles |
| --- | --- |
| Propriétés et contenu | Team, Due date, Release, Add link, Add document |
| Relations | Create related, Mark as, Remove |
| Réutilisation | Copy, Convert to, Make a copy |
| Accès personnel | Favorite, Remind me, Unsubscribe |
| Historique et suppression | Show description history, Delete |

Le sous-menu **Create related** a été ouvert : **Issue**, **Sub-issue**, **Parent issue**, **Blocked issue**, **Blocking issue**. Les autres sous-menus n’ont pas été développés. Aucune commande métier exécutée ; aucune modification ou publication de commentaire. Les raccourcis affichés à côté des commandes ne constituent pas des raccourcis testés.

**Pour Circular.** Conserver le panneau actuel pour consulter rapidement une liste, puis lui ajouter un lien local stable et un mode page. Prévoir un menu réel pour dupliquer, copier l’identifiant/lien et supprimer. Ajouter ensuite un historique serveur, une échéance et des relations : leurs effets doivent être visibles et persistants. Une commande de suppression nécessite toujours un retour clair en cas d’erreur.

## 6. Paramètres et personnalisation

Le menu d’espace a été ouvert : **Settings** avec raccourci affiché **G puis S**, téléchargement de l’application, changement d’espace, déconnexion. Seul Settings a été utilisé.

### Préférences réellement ouvertes

| Domaine | Contrôles observés | Exploration |
| --- | --- | --- |
| Général | Default home view, Display names, First day of week | Sélecteurs visibles, non modifiés |
| Saisie | Conversion des émoticônes en emojis ; touche d’envoi des commentaires | Contrôles visibles ; Enter affiché pour l’envoi, autres choix non lus |
| Navigation | App sidebar → Customize | Dialogue ouvert, voir ci-dessous |
| Typographie | Font size | Menu ouvert : Smaller, Small, Default, Large, Larger ; fermé sans sélection |
| Confort | Use pointer cursors, Underline links, Disable animated images & emoji | Interrupteurs visibles, non modifiés |
| Apparence | Interface theme ; thèmes Light et Dark | Mode système visible ; autres menus non ouverts |
| Code | Thème et police du code, aperçu | Présence observée, détail non étudié |

### Personnalisation de la barre latérale

**Observé.** Dialogue avec sections personnelles et espace de travail, poignées de déplacement, visibilité par entrée et style de badge par défaut. Les valeurs **Always show**, **Show when badged**, **Don’t show** sont visibles sur des entrées. La valeur **Count** est affichée pour les badges. Aucun déplacement ni changement appliqué ; persistance non vérifiée.

### Étiquettes de tickets

**Observé.** Page dédiée, recherche par nom, boutons **New group**, **New label**, filtres et affichage. Tableau : nom, description, portée, utilisation, dernière utilisation, création. Le menu d’une étiquette expose **Edit label name**, **Move to teams**, **View labeled issues**, **Archive**, **Delete**.

**Vérifié.** New label ouvre une ligne de saisie avec couleur, nom et description ; Échap annule la ligne restée vide. Les actions sur une étiquette existante n’ont pas été exécutées.

### Modèles et statuts de projets

**Observé.** La page de modèles de tickets décrit une portée espace de travail ou équipe, liste des modèles et présente un ajout ainsi qu’un type Form. L’éditeur de modèle n’a pas été ouvert.

La page **Project statuses** comporte les catégories **Backlog**, **Planned**, **In Progress**, **Completed**, **Canceled**, des lignes de statuts, compteurs et commandes d’ajout par catégorie. Aucune modification effectuée. Ce sont des **statuts de projets** : la configuration du workflow des **tickets** n’a pas été observée.

### Rubriques seulement aperçues

La navigation des paramètres mentionne profil, notifications, sécurité, comptes connectés, code/reviews, personnalisation d’agent, SLAs, modèles/étiquettes de projets, mises à jour, initiatives, documents, demandes clients, releases, pulse, asks, emojis et intégrations. Ces rubriques n’ont pas été ouvertes. Leur présence ne démontre ni leur disponibilité pour cet abonnement ni leur comportement.

## 7. Écart avec le code actuel de Circular

État établi par lecture du code local le 16 octobre, indépendamment de l’observation Linear. Cette collecte **ne modifie pas l’application**.

| Domaine | Circular actuel | Évolution utile proposée |
| --- | --- | --- |
| Paramètres | Aucun écran ; sombre/jaune fixe | Préférences et gestion des étiquettes |
| Affichage | Liste par statut, tableau à cinq colonnes | Groupement, tri, propriétés visibles, groupes repliables |
| Persistance de vue | Vue/filtres conservés seulement en mémoire React | Préférences et vues enregistrées en SQLite |
| Filtres | Recherche + projet/statut/priorité | Étiquettes, valeurs multiples, filtres nommés |
| Tri | ID décroissant dans chaque groupe | Priorité, titre, création et modification, avec direction |
| Création | Formulaire, raccourci C, projet/statut contextuels | Créer un autre, duplication, modèles locaux |
| Détail | Panneau, édition explicite, commentaires et suppression | Lien stable, mode page, actions rapides, journal |
| Étiquettes | Création et sélection depuis le ticket | Renommer, couleur, description et suppression dédiée |
| Projets | Création/modification ; suppression uniquement si vide ; préfixe stable, couleur, progression | Statut propre au projet, puis échéance |
| Relations | Aucune | Sous-tickets et blocages après le socle |
| Navigation | Tickets, projets, raccourcis clavier et aide | Favoris et palette de commandes locale |

Sources locales : [App.tsx](../src/App.tsx), [IssueViews.tsx](../src/IssueViews.tsx), [IssueDetail.tsx](../src/IssueDetail.tsx), [IssueFields.tsx](../src/IssueFields.tsx), [forms.tsx](../src/forms.tsx), [types.ts](../src/types.ts), [routes.py](../backend/app/api/routes.py), [workspace.py](../backend/app/repositories/workspace.py).

## 8. Plan de rapprochement proposé

Ce plan est une spécification pour les prochaines tranches, **pas une liste de fonctionnalités déjà implémentées**. Le thème Circular reste graphite avec accent jaune ; la structure des interactions peut s’inspirer du relevé sans copier les ressources de Linear.

### P1 — Paramètres et affichage réellement persistants

Ajouter une entrée Paramètres, avec Préférences et Étiquettes. Préférences initiales : vue d’accueil, taille du texte, densité, réduction des animations et touche d’envoi des commentaires. Ajouter un menu Affichage aux tickets : liste/tableau, groupement statut/projet/priorité/aucun, tri priorité/titre/création/modification, direction, propriétés visibles et groupes vides. Le tableau conserve d’abord des colonnes par statut.

Stocker ces réglages dans SQLite via routes → schémas → services → dépôts, avec migration versionnée, valeurs par défaut et validation. Les réglages d’affichage sont propres à une vue ; les préférences d’interface sont globales à l’utilisateur local. Aucune dépendance à un compte Linear ni remplacement de cette persistance par localStorage.

**Critères :** un réglage modifié dans l’interface survit à l’actualisation puis au redémarrage du backend ; valeurs invalides refusées ; réinitialisation réelle ; noms de contrôles accessibles ; erreur de sauvegarde visible ; taille de texte et focus restent utilisables à 390 px. Les étiquettes renommées sont mises à jour dans tous les tickets ; leur suppression retire les associations sans supprimer les tickets.

### P2 — Filtres et navigation quotidienne

Ajouter le filtre d’étiquettes, les valeurs multiples et des vues nommées enregistrant filtres/tri/groupement/propriétés. Ajouter favoris, liens locaux vers les tickets et palette de commandes ne proposant que des actions existantes.

**Critères :** mêmes résultats en liste et tableau ; résultat vide explicite ; suppression d’une vue persistante ; lien direct retrouvé après rechargement ; retour au contexte de liste ; navigation complète au clavier. Tests API sur les combinaisons de filtres et leur sémantique documentée, tests navigateur de sauvegarde et restauration d’une vue.

### P3 — Création et suivi plus rapides

Ajouter Créer un autre, duplication et modèles locaux ; ensuite journal d’activité, édition/suppression de commentaires, échéance et statut de projet. Prévoir les relations/sous-tickets comme une tranche distincte plutôt que des contrôles désactivés dans le détail.

**Critères :** duplication avec nouvel identifiant, sans recopier les commentaires ni l’historique ; aucune création à la simple ouverture d’un modèle ; aucune double soumission ; chaque changement journalisé dans la même transaction métier ; dates validées ; suppressions persistantes. Pour les relations, interdiction d’auto-référence et de cycles de parenté, retrait cohérent lors d’une suppression.

### Fonctions à garder hors du socle local

Membres et équipes, abonnements collaboratifs, intégrations, agents cloud, facturation, administration avancée et temps réel multi-utilisateur restent hors du périmètre demandé. Récurrence, pièces jointes, texte riche, releases et estimations ont des coûts fonctionnels propres ; leur simple présence chez Linear ne les rend pas nécessaires à la prochaine tranche.

## 9. Limites et validations complémentaires

L’observation couvre les quatre surfaces prioritaires et plusieurs paramètres utiles, sans prétendre inventorier tout Linear. Aucun test de sauvegarde, suppression, déplacement métier, envoi de commentaire, récurrence, modèle, permission ou synchronisation n’a été réalisé dans l’espace réel. Les dimensions, polices, espacements et comportements responsifs de Linear n’ont pas été mesurés ; les impressions visuelles ne sont pas des valeurs CSS.

Si une validation plus poussée de Linear devient nécessaire, l’utilisateur devra préparer un projet et des tickets **explicitement fictifs** dans un espace autorisé. Un parcours manuel pourra alors vérifier création avec Create more, déplacement et retour d’un ticket, commentaires, filtres composés, modèle et persistance d’un réglage. L’authentification et les éventuelles restrictions restent à la charge de l’utilisateur ; aucun contournement n’est requis. Aucun de ces parcours supplémentaires n’est nécessaire pour commencer P1 dans Circular.

Pour cette livraison documentaire : navigation et contrôles ci-dessus réellement observés, liens locaux de la documentation vérifiés. **Aucun nouveau test API ou E2E de Circular exécuté** ; le code et la base n’ont pas été modifiés. Les résultats antérieurs restent consignés dans [validation.md](validation.md), sans être présentés comme une nouvelle exécution.
