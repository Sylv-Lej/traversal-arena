# Traversal — règles (référence pour le moteur)

Source : <https://www.traversalgame.com/rules> (page rendue en JS ; texte extrait des
bundles `rules-*.js` FR/EN le 2026-10-20). Ce fichier est la **spécification du moteur**
(`backend/app/engine/`) : chaque règle numérotée doit avoir au moins un test.
Les points marqués **[?]** sont ambigus dans la source : le choix retenu est indiqué, il
est isolé dans `engine/config.py` pour pouvoir le changer sans toucher au reste.

## R1. Vue d'ensemble

- 2 joueurs, plateau **10×10**, chaque case a une **hauteur** (paysage 3D).
- 6 pièces par joueur. Objectif : faire **sortir** ses pièces par le bord opposé.
  Chaque pièce sortie rapporte sa **Force**.
- Fin de partie dès que **2 pièces au total** (tous joueurs confondus) sont sorties.

## R2. Plateau

- R2.1 Deux cases orthogonalement adjacentes diffèrent d'**au plus 2** en hauteur.
- R2.2 Plateau **différent à chaque partie**, généré **équitable** (aucun camp avantagé).
  Choix d'implémentation : symétrie centrale (rotation 180°) → équité garantie par construction.
- R2.3 Modes de terrain (le site original en a 16) : `random`, `mountains` (pics centraux),
  `valleys` (cuvettes bordées de crêtes), `highlands` (montagnes + vallées), `woodlands`
  (plutôt plat, collines douces), `desert` (plat, rares pics). V1 : ces 6.
- R2.4 **[?]** Plage de hauteurs non précisée → `0..6`.

## R3. Pièces

**Mouvement = nombre de coins de la base** (budget de déplacement par tour, cf. R4.4) ;
Force = nombre de pointes au sommet ; M + F = 6.

| Pièce        | Forme              | Mouvement | Force | Spécial |
|--------------|--------------------|-----------|-------|---------|
| Explorateur  | cône pentagonal    | 5         | 1     | R5      |
| Avant-garde  | coin en losange    | 4         | 2     | R7.5    |
| Sentinelle   | prisme triangulaire| 3         | 3     | R8.2    |

- R3.1 2 pièces de chaque type par joueur.
- R3.2 Mise en place : rangée de départ, **colonnes 2 à 7**, disposition symétrique.
  **[?]** Ordre exact non précisé → `S V E E V S` : de la pièce la plus rapide au centre
  (Explorateurs) à la plus lente sur les côtés (Sentinelles). Avant le 22/10/2026 :
  `E V S S V E` ; chaque partie garde la mise en place de son début (`games.setup`,
  `engine/config.py` `SETUPS`).
- R3.3 J1 (rouge) part de la rangée 1 et sort par la rangée 10 ; J2 (bleu) l'inverse.
  **[?]** Qui commence → J1.

## R4. Déplacement

- R4.1 À son tour, le joueur déplace **une** pièce. Pas de passe.
- R4.2 Déplacement orthogonal case par case, changements de direction autorisés.
- R4.3 Coût d'un pas : **1** si même hauteur, sinon **|Δh| + 1** (montée comme descente).
- R4.4 Total des pas ≤ Mouvement de la pièce (= nombre de coins de sa base : 5 / 4 / 3).
- R4.5 Impossible de **traverser** une pièce (alliée ou ennemie).
- R4.6 Impossible de **finir sur sa case de départ**.
- R4.7 Le tour se termine après le déplacement (ou l'attaque).
- R4.8 **[?]** Aucun coup légal → le joueur passe (cas rare, documenté et testé).

## R5. Explorateur — coups spéciaux

À la place d'un déplacement normal, **depuis sa case de départ**, non combinables :
- R5.1 **Diagonale** : 1 case en diagonale, quelle que soit la hauteur.
- R5.2 **Bond** : exactement 2 cases dans une direction cardinale, quelle que soit la hauteur.
  **Interdit de sauter par-dessus une pièce** : la case intermédiaire doit être vide
  (comme R4.5, aucune pièce ne passe au-dessus d'une autre).
  **[?]** Attaque via diagonale/bond → autorisée si la case d'arrivée est ennemie.
  **[?]** Sortie du plateau via bond → non (la sortie suit R6.1).

## R6. Sortie (« franchir l'arrivée »)

- R6.1 Une pièce sur la **dernière rangée** avec **≥ 1 point de Mouvement restant** peut sortir.
  Équivaut à : coût min. pour atteindre la dernière rangée ≤ Mouvement − 1.
- R6.2 La pièce sortie est retirée ; sa Force s'ajoute au score de son joueur.

## R7. Combat

- R7.1 Attaquer = déplacer sa pièce **sur la case d'une pièce ennemie** atteignable avec son
  Mouvement (le coût d'entrée dans la case cible compte). L'attaquant occupe ensuite la
  case libérée.
- R7.2 Résolution immédiate : si **Force attaquant ≥ Force défenseur**, la pièce attaquée
  **sort du plateau** : retirée définitivement, elle **ne marque aucun point** (ce n'est pas
  une sortie au sens de R6/R8). Sinon le coup est **illégal** (on ne propose jamais une
  attaque perdante).
- R7.3 Force attaquant = Force de base
  **+1** si la case de départ de l'attaquant (début du tour) est **plus haute** que la cible,
  **−1** si **plus basse**,
  **+ Force de base** de chaque **autre** pièce alliée adjacente à la cible.
- R7.4 Force défenseur = Force de base **+1** par pièce alliée (du défenseur) adjacente au défenseur.
  **[?]** « Adjacent » = 4-voisinage orthogonal.
- R7.5 **Avant-garde** : **+1** en attaque si le **plus court chemin** vers la cible coûte
  **exactement 4**.
- R7.6 Attaquer termine le tour.

Exemples de la source (→ tests) :
- Avant-garde rouge (2) +1 hauteur = 3 vs Avant-garde bleue (2) +1 renfort = 3 → capture.
- Explorateur rouge (1) + Avant-garde alliée adjacente à la cible (+2) = 3 vs Sentinelle (3) → capture.

## R8. Fin de partie

- R8.1 Dès que **2 pièces au total** sont sorties : score = somme des Forces sorties par
  joueur ; le plus haut gagne ; égalité = nulle.
- R8.2 **Sentinelle** : si la **toute première** pièce sortie (tous camps) est une
  Sentinelle, son joueur **gagne immédiatement**.
- R8.3 **Limite de coups** N : la partie s'arrête, le meilleur score gagne. Si personne n'a
  marqué : gagne le joueur dont la pièce la plus avancée a le moins de rangées à franchir ;
  à égalité, la plus forte ; sinon nulle. **N = 200** coups (100 par joueur) — validé.
- R8.4 (site) Abandon, temps écoulé (pendule), nulle par accord.
