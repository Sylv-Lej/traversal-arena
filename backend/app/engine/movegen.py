"""Génération des coups légaux (R4 à R7).

Déplacement normal = Dijkstra borné par le Mouvement, à travers les cases vides
uniquement (on ne traverse aucune pièce). Les attaques sont des déplacements dont la
dernière marche entre sur une case ennemie ; la sortie est une marche de plus au-delà
de la dernière rangée.
"""

import heapq

from app.engine import config as C
from app.engine.types import Combat, GameState, Move, Piece, Term

SIZE = C.SIZE

# Voisins orthogonaux, précalculés une fois pour toutes.
NEIGHBORS: tuple[tuple[int, ...], ...] = tuple(
    tuple(
        ny * SIZE + nx
        for nx, ny in ((x, y + 1), (x + 1, y), (x, y - 1), (x - 1, y))
        if 0 <= nx < SIZE and 0 <= ny < SIZE
    )
    for y in range(SIZE)
    for x in range(SIZE)
)

DIAGONALS = ((1, 1), (1, -1), (-1, 1), (-1, -1))
CARDINALS = ((0, 1), (1, 0), (0, -1), (-1, 0))


def step_cost(heights: tuple[int, ...], a: int, b: int) -> int:
    """R4.3 : 1 sur le plat, sinon |Δh| + 1."""
    dh = abs(heights[a] - heights[b])
    return 1 if dh == 0 else dh + 1


def exit_row(owner: int) -> int:
    return SIZE - 1 if owner == 1 else 0


def rows_to_go(owner: int, square: int) -> int:
    y = square // SIZE
    return (SIZE - 1 - y) if owner == 1 else y


def _reach(state: GameState, piece: Piece) -> tuple[dict[int, int], dict[int, int]]:
    """Dijkstra borné : coût minimal vers chaque case vide atteignable."""
    budget = C.MOVEMENT[piece.kind]
    occ = state.occupancy()
    heights = state.heights
    dist = {piece.sq: 0}
    prev: dict[int, int] = {}
    heap = [(0, piece.sq)]
    while heap:
        d, cur = heapq.heappop(heap)
        if d > dist[cur]:
            continue
        for nb in NEIGHBORS[cur]:
            if nb in occ:
                continue
            nd = d + step_cost(heights, cur, nb)
            if nd <= budget and nd < dist.get(nb, budget + 1):
                dist[nb] = nd
                prev[nb] = cur
                heapq.heappush(heap, (nd, nb))
    return dist, prev


def _path(prev: dict[int, int], start: int, end: int) -> tuple[int, ...]:
    out = [end]
    while out[-1] != start:
        out.append(prev[out[-1]])
    return tuple(reversed(out))


def combat(state: GameState, attacker: Piece, target: Piece, charge: bool) -> Combat:
    """R7.3 / R7.4 / R7.5 — forces effectives et leur détail."""
    occ = state.occupancy()
    heights = state.heights
    att_terms = [Term("base", C.STRENGTH[attacker.kind])]
    dh = heights[attacker.sq] - heights[target.sq]
    if dh > 0:
        att_terms.append(Term("height", 1))
    elif dh < 0:
        att_terms.append(Term("height", -1))
    for nb in NEIGHBORS[target.sq]:
        ally = occ.get(nb)
        if ally and ally.owner == attacker.owner and ally.id != attacker.id:
            att_terms.append(Term(f"ally:{ally.kind}", C.STRENGTH[ally.kind]))
    if charge:
        att_terms.append(Term("charge", 1))
    def_terms = [Term("base", C.STRENGTH[target.kind])]
    for nb in NEIGHBORS[target.sq]:
        ally = occ.get(nb)
        if ally and ally.owner == target.owner:
            def_terms.append(Term(f"reinforcement:{ally.kind}", 1))
    return Combat(
        attack=sum(t.value for t in att_terms),
        defense=sum(t.value for t in def_terms),
        attack_terms=tuple(att_terms),
        defense_terms=tuple(def_terms),
    )


def piece_moves(state: GameState, piece: Piece) -> list[Move]:
    occ = state.occupancy()
    heights = state.heights
    budget = C.MOVEMENT[piece.kind]
    dist, prev = _reach(state, piece)
    moves: dict[int, Move] = {}

    # R4 Déplacements vers les cases vides (jamais la case de départ).
    for square, d in dist.items():
        if square != piece.sq:
            moves[square] = Move(piece.id, "move", square, _path(prev, piece.sq, square), d)

    # R7 Attaques : dernière marche vers une case ennemie, coût d'entrée compris.
    best: dict[int, tuple[int, int]] = {}  # cible -> (coût, case d'approche)
    for square, d in dist.items():
        for nb in NEIGHBORS[square]:
            target = occ.get(nb)
            if target is None or target.owner == piece.owner:
                continue
            cost = d + step_cost(heights, square, nb)
            if cost <= budget and cost < best.get(nb, (budget + 1, 0))[0]:
                best[nb] = (cost, square)
    for tsq, (cost, approach) in best.items():
        target = occ[tsq]
        charge = piece.kind == C.VANGUARD and cost == C.VANGUARD_CHARGE_COST
        fight = combat(state, piece, target, charge)
        if fight.attack >= fight.defense:
            path = _path(prev, piece.sq, approach) + (tsq,)
            moves[tsq] = Move(piece.id, "attack", tsq, path, cost, combat=fight)

    # R6 Sortie : atteindre la dernière rangée avec au moins 1 point restant.
    row = exit_row(piece.owner)
    exits = [(d, s) for s, d in dist.items() if s // SIZE == row and d <= budget - 1]
    if exits:
        d, s = min(exits)
        moves_exit = Move(piece.id, "exit", None, _path(prev, piece.sq, s), d + 1)
    else:
        moves_exit = None

    # R5 Coups spéciaux de l'Explorateur (ignorent la hauteur).
    if piece.kind == C.EXPLORER:
        x, y = piece.sq % SIZE, piece.sq // SIZE
        specials = [("diag", dx, dy, None) for dx, dy in DIAGONALS]
        specials += [("leap", 2 * dx, 2 * dy, (x + dx) + (y + dy) * SIZE) for dx, dy in CARDINALS]
        for kind, dx, dy, middle in specials:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < SIZE and 0 <= ny < SIZE):
                continue
            if middle is not None and not C.LEAP_OVER_PIECES and middle in occ:
                continue
            dest = ny * SIZE + nx
            if dest in moves:  # déjà atteignable normalement : même résultat
                continue
            path = (piece.sq, dest) if middle is None else (piece.sq, middle, dest)
            target = occ.get(dest)
            if target is None:
                moves[dest] = Move(piece.id, "move", dest, path, 0, special=kind)
            elif target.owner != piece.owner and C.SPECIAL_MOVES_CAN_ATTACK:
                fight = combat(state, piece, target, False)
                if fight.attack >= fight.defense:
                    moves[dest] = Move(piece.id, "attack", dest, path, 0, special=kind, combat=fight)

    out = list(moves.values())
    if moves_exit:
        out.append(moves_exit)
    return out


def legal_moves(state: GameState) -> list[Move]:
    if state.over:
        return []
    out: list[Move] = []
    for piece in state.pieces:
        if piece.owner == state.to_move:
            out.extend(piece_moves(state, piece))
    if not out:
        # R4.8 [?] Aucun coup : le joueur passe.
        out.append(Move("", "pass", None))
    return out
