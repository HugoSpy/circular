# Audit et refonte de Circular

## Périmètre et méthode

Audit du 15 octobre 2026, réalisé sur l'application locale `http://127.0.0.1:4310` dans Chrome avec Playwright déjà installé. Liste, tableau, détail, projets et écran mobile 390 × 844 capturés ; mesures desktop à 1440 × 960. Aucun accès à Linear, aucun recours à ses ressources. Les observations portent sur Circular ; les propositions ci-dessous sont nos choix de conception.

Workflow : **front-maxer**, combinant **UI UX Pro Max** et **Apple Design** pour une application. Les principes web transférables de lisibilité, hiérarchie, regroupement et navigation clavier sont retenus. Les dimensions natives Apple ne sont pas présentées comme des règles CSS. La recherche initiale « project management productivity dark » proposait un schéma marketing et des couleurs inadéquates : rejetés. La recherche affinée « dense task dashboard » confirme une interface centrée sur les données, sans ajouter de graphiques ou de KPI étrangers au besoin. Les recherches clavier/formulaires confortent les contrôles HTML natifs et le focus visible.

## Constats avant modification

| Priorité | Observation vérifiée | Décision |
| --- | --- | --- |
| Haute | Titres de tickets 12 px, identifiants 10 px, étiquettes et statut carte 9 px, filtres 10 px (9 sur mobile). | Titres 14 px, métadonnées 12 px, contrôles 13 px ; gagner de la densité dans les espacements. |
| Haute | Texte bas de sidebar 3,85:1 ; identifiant sur carte 4,33:1. Calcul CSS des placeholders : 3,73:1. | Tokens de texte secondaires neutres ; contrôler les contrastes après rendu. La majorité des textes existants dépasse déjà 4,5:1. |
| Haute | Faible, moyenne et haute utilisent le même pictogramme, uniquement recoloré. | Dessiner des niveaux de barres distincts et garder un nom accessible. |
| Moyenne | En-tête desktop de 164 px ; premier groupe à y=311. Sur mobile, premier groupe à y=457 et titre de ticket à y=535. | Retirer slogans et sourcil répétitif, conserver descriptions réelles des projets et action principale. |
| Moyenne | « + » de sidebar 25 × 25 px, statut carte 20 px de haut ; libellé principal caché sur mobile. | Cibles secondaires 32 px desktop, 44 px mobile ; libellés d'action conservés. |
| Moyenne | Champs empilés du détail ; commentaires éloignés. | Regrouper les propriétés, rapprocher le composer et distinguer explicitement l'enregistrement. |

À préserver : persistance FastAPI/SQLite, sauvegarde explicite, erreurs et états occupés, protection des brouillons, dialogue natif et retour du focus, alternative au glisser-déposer par un sélecteur de statut, recherche et filtres, raccourcis et réduction du mouvement.

## Direction retenue

- Surfaces graphite neutres ; jaune `#F2CF63` pour marque, action principale, sélection et focus. Texte principal `#F1F1F3`, secondaire `#A5A7AF`.
- Les couleurs enregistrées des projets et des étiquettes restent des données utilisateur. Les statuts gardent des formes et couleurs sémantiques distinctes.
- Une hiérarchie de travail : navigation discrète, titre court, commandes lisibles, lignes structurées et cartes de tableau plus nettes. Pas d'illustrations ni de décoration distante.
- Police système locale, espacements de 4/8 px, rayon de 6–10 px selon surface, transitions courtes limitées aux états des contrôles.
- Aucun outil ou dépendance ajouté ; aucune configuration globale changée.

## Vérification après refonte

| Mesure au navigateur | Avant | Après |
| --- | --- | --- |
| Hauteur de l’en-tête desktop | 164 px | 83 px |
| Début du premier groupe desktop | y = 311 px | y = 219 px |
| Début du premier groupe mobile 390 px | y = 457 px | y = 393 px |
| Titre de ticket en liste | 12 px | 14 px |
| Texte des filtres desktop / mobile | 10 / 9 px | 13 / 13 px |
| Hauteur du sélecteur de statut sur carte desktop | 20 px | 32 px |
| Cible du bouton secondaire échantillonné desktop / mobile | 25 × 25 px | 32 × 32 / 44 × 44 px |
| Contraste de l’identifiant sur carte | 4,33:1 | 6,53:1 |
| Contraste du texte bas de sidebar | 3,85:1 | 7,24:1 |
| Contraste du bouton jaune principal | — | 11,02:1 |

Les contrastes sont calculés sur les styles effectivement rendus, texte opaque sur surface opaque. Les contrôles sont des échantillons ciblés, pas une certification d’accessibilité exhaustive. Les mesures sont prises avec les mêmes données de démonstration et les mêmes dimensions avant/après.

Vérifications exécutées :

- `npm run build` : TypeScript et Vite réussis après la dernière correction.
- `npm test` : **34 tests API réussis**, avec l’avertissement de dépréciation Starlette/httpx déjà présent.
- `node node_modules/@playwright/test/cli.js test` : **11 parcours réussis** en 17 s. Après la dernière correction mobile, **3 parcours ciblés réussis** en 5,9 s.
- Liste, tableau, création, détail et projets contrôlés à **320, 390, 768, 1024 et 1440 px** : aucun débordement horizontal du document ou du dialogue. Sur petit écran, le tableau défile dans son propre conteneur.
- Création/modification/suppression, commentaires, glisser-déposer, filtres, persistance après redémarrage et erreurs réseau restent couverts. Nouveaux contrôles : commandes lisibles, focus visible et retour après fermeture, accès direct aux commentaires, premier ticket visible sans défilement initial à 390 px.
- `prefers-reduced-motion: reduce` vérifié : transition calculée à `0s`.
- Aucun appel HTTP externe ni exception JavaScript pendant les parcours et les captures.

La revue finale a corrigé un espace vide mobile lorsque la liste contenait peu de tickets : les lignes implicites de la grille étiraient la navigation. La navigation conserve désormais sa hauteur de contenu. Un test clavier trop strict assimilait le passage natif vers la barre du navigateur à une fuite du dialogue ; il accepte cette sortie du document mais interdit le focus sur les contrôles d’arrière-plan. Aucun piège de focus supplémentaire n’a été ajouté.

## Captures et provenance

- [Liste avant](images/avant-liste.png) et [liste après](images/apres-liste.png).
- [Tableau après](images/apres-tableau.png), [détail après](images/apres-detail.png), [création après](images/apres-creation.png).
- [Mobile après](images/apres-mobile.png) et [projets après](images/apres-projets.png).
- Mesures brutes : [avant](evidence/ui-avant.json), [après](evidence/ui-apres.json), [largeurs et mouvement réduit](evidence/responsive.json).

Les captures avant/après ont été ouvertes et inspectées. La capture finale des projets a été refaite avec les transitions terminées : « Projets » est bien la navigation active. Les deux passes de correction ont porté sur l’espacement des commentaires, la barre de sauvegarde mobile et la grille avec peu de tickets.

Références de méthode lues dans les skills locaux : `front-maxer` (workflow applications), `ui-ux-pro-max` (focus, formulaires React, interface dense) et `apple-design` : Accessibility/Vision et Mobility ; Typography/Ensuring legibility ; Color/Inclusive color ; Layout/Visual hierarchy ; Buttons/Style et Content ; Toolbars/Item groupings. Les recommandations de lisibilité, d’alternatives à la couleur et de regroupement ont guidé les corrections ; la palette jaune vient de la préférence utilisateur.

Limites : tests sur Windows/Chrome et mobile émulé, sans téléphone physique, Safari, Firefox ou lecteur d’écran. Pas d’observation supplémentaire de Linear/REA. Le backend et le schéma SQLite restent inchangés.
