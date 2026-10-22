"""Bot natif : le même algorithme que `app.bot`, en Rust (module `traversal_rs`, compilé
depuis `engine-rs`). Environ 80 à 90× plus rapide (mesuré sur 2000 parties).

Le moteur Python reste la référence : Rust renvoie seulement (pièce, type, case), et le
coup complet (chemin, détail du combat) est reconstruit ici par `find_move`.

Utilisé dès que le module est installé (image Docker de prod) ; `BOT_ENGINE=python`
force le bot Python. Sans le module (dev local avec l'image Python standard), le bot
Python prend le relais tout seul.
"""

import os
import random

from app.engine import GameState, Move, find_move, legal_moves

try:
    import traversal_rs
except ImportError:  # module non compilé : bot Python
    traversal_rs = None

ENABLED = traversal_rs is not None and os.environ.get("BOT_ENGINE", "rust") != "python"


def pack(state: GameState) -> tuple:
    """Position au format du module Rust (l'ordre des pièces fait leur indice)."""
    return (list(state.heights), [(p.owner, p.kind, p.sq) for p in state.pieces], state.to_move, state.ply,
            tuple(state.scores), len(state.finished), state.move_limit)


def to_move(state: GameState, piece: int, kind: str, to: int) -> Move:
    """Coup Python complet à partir de la réponse du module."""
    if kind == "pass":
        return next(m for m in legal_moves(state) if m.kind == "pass")
    return find_move(state, state.pieces[piece].id, kind, None if to < 0 else to)


def choose_move(state: GameState, level, rng: random.Random) -> Move:
    (piece, kind, to), _info = traversal_rs.choose_move(
        pack(state), level.depth, level.beam, level.noise, int(level.budget_s * 1000), rng.getrandbits(64),
        level.insight)
    return to_move(state, piece, kind, to)
