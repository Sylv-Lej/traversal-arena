"""Bot Traversal : alpha-beta à approfondissement itératif, borné en temps.

`choose_move` passe par le bot natif (Rust, `app.bot.native`) quand il est disponible ;
ce module en reste la référence (même évaluation, même recherche) et le repli. Le repli
Python ignore `Level.insight` : sans le module, Crête, Sommet et Mont Blanc jouent comme avant
(un peu plus faibles).
"""

import math
import random
import time
from dataclasses import dataclass
from functools import lru_cache

from app.engine import GameState, Move, apply_move, legal_moves
from app.engine import config as C
from app.bot import native
from app.engine.movegen import NEIGHBORS, step_cost

WIN = 100_000


@dataclass(frozen=True)
class Level:
    name: str
    depth: int
    beam: int  # nombre de coups explorés sous la racine
    noise: float  # bruit sur l'évaluation des coups racine (erreurs « humaines »)
    budget_s: float
    # Compréhension du jeu (bot Rust seulement, cumulative ; voir engine-rs/core/src/bot.rs) :
    # 1 les échanges (captures et sorties suivies jusqu'au calme), 2 + le terrain et les
    # parades (pièces qui barrent le chemin), 3 + la course des Sentinelles (R8.2).
    insight: int = 0
    # Classement de départ du bot (tournoi entre bots, ancré sur Galet = 920, voir
    # engine-rs/README.md) ; il bouge ensuite avec ses résultats contre les joueurs.
    start_rating: float = 1500.0


LEVELS = {
    1: Level("Galet", 1, 999, 90.0, 0.2, start_rating=920),
    2: Level("Sentier", 1, 999, 25.0, 0.3, start_rating=1090),
    3: Level("Crête", 2, 12, 8.0, 0.6, insight=1, start_rating=1520),
    4: Level("Sommet", 3, 9, 2.0, 1.0, insight=2, start_rating=1645),
    5: Level("Mont Blanc", 4, 7, 0.0, 1.8, insight=3, start_rating=1730),
}


@lru_cache(maxsize=64)
def exit_costs(heights: tuple[int, ...], owner: int) -> tuple[int, ...]:
    """Coût minimal (sur le relief, sans tenir compte des pièces) pour sortir depuis chaque case."""
    import heapq

    row = C.SIZE - 1 if owner == 1 else 0
    dist = [10**6] * C.SQUARES
    heap = []
    for x in range(C.SIZE):
        s = row * C.SIZE + x
        dist[s] = 1
        heap.append((1, s))
    heapq.heapify(heap)
    while heap:
        d, cur = heapq.heappop(heap)
        if d > dist[cur]:
            continue
        for nb in NEIGHBORS[cur]:
            nd = d + step_cost(heights, cur, nb)
            if nd < dist[nb]:
                dist[nb] = nd
                heapq.heappush(heap, (nd, nb))
    return tuple(dist)


def evaluate(state: GameState, side: int) -> float:
    """Évaluation du point de vue de `side`."""
    if state.over:
        if state.winner is None:
            return 0.0
        return WIN - state.ply if state.winner == side else -WIN + state.ply
    nobody_out = not state.finished
    total = 100.0 * (state.scores[side - 1] - state.scores[2 - side])
    for p in state.pieces:
        strength = C.STRENGTH[p.kind]
        turns = math.ceil(exit_costs(state.heights, p.owner)[p.sq] / C.MOVEMENT[p.kind])
        v = 14 * strength + max(0, 7 - turns) * (3 + 2 * strength)
        if p.kind == C.SENTINEL and nobody_out:
            v += max(0, 6 - turns) ** 2 * 5
        total += v if p.owner == side else -v
    return total


def _order_key(state: GameState, move: Move) -> float:
    if move.kind == "exit":
        piece = state.piece(move.piece_id)
        return 1000 + C.STRENGTH[piece.kind]
    if move.kind == "attack":
        target = state.occupancy()[move.to]
        return 500 + 10 * C.STRENGTH[target.kind]
    if move.kind == "pass":
        return 0
    piece = state.piece(move.piece_id)
    costs = exit_costs(state.heights, piece.owner)
    return costs[piece.sq] - costs[move.to]


def _ordered(state: GameState) -> list[Move]:
    return sorted(legal_moves(state), key=lambda m: _order_key(state, m), reverse=True)


class _Timeout(Exception):
    pass


def _negamax(state, depth, alpha, beta, level: Level, deadline: float) -> float:
    if state.over or depth == 0:
        return evaluate(state, state.to_move)
    if time.monotonic() > deadline:
        raise _Timeout
    best = -math.inf
    for move in _ordered(state)[: level.beam]:
        score = -_negamax(apply_move(state, move), depth - 1, -beta, -alpha, level, deadline)
        if score > best:
            best = score
        alpha = max(alpha, score)
        if alpha >= beta:
            break
    return best


def choose_move(state: GameState, level_id: int = 3, rng: random.Random | None = None) -> Move:
    level = LEVELS.get(level_id, LEVELS[3])
    rng = rng or random.Random()
    if native.ENABLED:
        return native.choose_move(state, level, rng)
    return choose_move_py(state, level, rng)


def choose_move_py(state: GameState, level: Level, rng: random.Random) -> Move:
    """Le bot en Python pur (référence)."""
    root = _ordered(state)
    if len(root) == 1:
        return root[0]
    deadline = time.monotonic() + level.budget_s
    noise = {id(m): rng.uniform(-level.noise, level.noise) for m in root}
    best_move = root[0]
    for depth in range(1, level.depth + 1):
        try:
            scored = []
            alpha = -math.inf
            for move in root:
                score = -_negamax(
                    apply_move(state, move), depth - 1, -math.inf, -alpha + 1e-9, level, deadline
                ) if depth > 1 else evaluate(apply_move(state, move), state.to_move)
                scored.append((score + noise[id(move)], move))
                alpha = max(alpha, score)
        except _Timeout:
            break
        scored.sort(key=lambda t: t[0], reverse=True)
        best_move = scored[0][1]
        # Coups racine triés par le résultat de cette itération : meilleure coupe ensuite.
        root = [m for _, m in scored]
    return best_move
