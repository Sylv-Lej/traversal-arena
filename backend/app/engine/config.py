"""Constantes du jeu et choix retenus sur les ambiguïtés des règles.

Tout ce qui est marqué [?] dans `RULES.md` est tranché ICI, et seulement ici : changer
une règle ambiguë = changer une constante, sans toucher au reste du moteur.
"""

SIZE = 10
SQUARES = SIZE * SIZE

# R2.4 [?] Plage de hauteurs.
MIN_HEIGHT = 0
MAX_HEIGHT = 6
# R2.1 Deux cases adjacentes diffèrent d'au plus 2.
MAX_STEP = 2

EXPLORER = "explorer"
VANGUARD = "vanguard"
SENTINEL = "sentinel"
KINDS = (EXPLORER, VANGUARD, SENTINEL)

# R3 Mouvement = coins de la base, Force = pointes au sommet, M + F = 6.
MOVEMENT = {EXPLORER: 5, VANGUARD: 4, SENTINEL: 3}
STRENGTH = {EXPLORER: 1, VANGUARD: 2, SENTINEL: 3}

# R3.2 [?] Ordre de mise en place sur les colonnes 2..7 (vu par chaque joueur) : de la
# pièce la plus rapide au centre à la plus lente sur les côtés.
SETUP_COLUMNS = (2, 3, 4, 5, 6, 7)
# Une partie est rejouée avec la mise en place de son début (`games.setup`) : les
# anciennes restent justes quand la mise en place change. Ne jamais modifier une entrée
# existante, en ajouter une.
SETUPS = {
    "classic": (EXPLORER, VANGUARD, SENTINEL, SENTINEL, VANGUARD, EXPLORER),  # jusqu'au 22/10/2026
    "speed": (SENTINEL, VANGUARD, EXPLORER, EXPLORER, VANGUARD, SENTINEL),
}
SETUP = "speed"  # celle des nouvelles parties (identique dans engine-rs/core/src/rules.rs)
SETUP_ORDER = SETUPS[SETUP]

# R3.3 [?] Le joueur 1 (rouge) commence.
FIRST_PLAYER = 1

# R5.2 Le bond de l'Explorateur ne passe jamais au-dessus d'une pièce.
LEAP_OVER_PIECES = False
# R5 [?] Diagonale / bond peuvent attaquer une pièce ennemie sur la case d'arrivée.
SPECIAL_MOVES_CAN_ATTACK = True

# R7.5 Bonus de charge de l'Avant-garde : plus court chemin == ce coût exact.
VANGUARD_CHARGE_COST = 4

# R8.1 La partie s'arrête quand ce nombre de pièces (tous camps) est sorti.
FINISHERS_TO_END = 2
# R8.3 Limite de coups (demi-coups, les deux joueurs confondus) — validée : 200.
MOVE_LIMIT = 200
