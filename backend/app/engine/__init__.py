"""Moteur Traversal : pur, déterministe, sans I/O. Spécification : `RULES.md`."""

from app.engine.movegen import legal_moves
from app.engine.rules import IllegalMove, apply_move, end_game, find_move, new_game, notation
from app.engine.terrain import MODES as TERRAIN_MODES
from app.engine.terrain import generate as generate_terrain
from app.engine.types import Combat, GameState, Move, Piece

__all__ = [
    "Combat",
    "GameState",
    "IllegalMove",
    "Move",
    "Piece",
    "TERRAIN_MODES",
    "apply_move",
    "end_game",
    "find_move",
    "generate_terrain",
    "legal_moves",
    "new_game",
    "notation",
]
