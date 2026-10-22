"""Équivalence moteur Python (référence) ↔ moteur Rust (`traversal_rs`, bot natif).

Sur des milliers de positions tirées de parties aléatoires (tous les terrains, sorties,
captures, limite de coups) : mêmes coups légaux (coût, coup spécial, forces du combat),
même position après chaque coup, même évaluation. Sautés si le module n'est pas compilé.
"""

import random

import pytest

from app import bot
from app.bot import native
from app.engine import TERRAIN_MODES, GameState, Piece, apply_move, generate_terrain, legal_moves, new_game
from app.engine import config as C

rs = pytest.importorskip("traversal_rs")


def rust_moves(state):
    return sorted(rs.legal_moves(native.pack(state)), key=repr)


def py_moves(state):
    index = {p.id: i for i, p in enumerate(state.pieces)}
    out = []
    for m in legal_moves(state):
        fight = m.combat
        out.append((index.get(m.piece_id, -1), m.kind, -1 if m.to is None else m.to, m.cost, m.special,
                    fight.attack if fight else 0, fight.defense if fight else 0))
    return sorted(out, key=repr)


def positions(games: int, seed: int):
    """Positions de parties où l'on préfère souvent sortir ou attaquer (fins de partie)."""
    rng = random.Random(seed)
    for g in range(games):
        mode = TERRAIN_MODES[1 + g % (len(TERRAIN_MODES) - 1)]
        _, _, heights = generate_terrain(mode, rng.randrange(2**31))
        s = new_game(heights, move_limit=rng.choice((C.MOVE_LIMIT, 24, 40)))
        while not s.over:
            yield s
            moves = legal_moves(s)
            sharp = [m for m in moves if m.kind in ("exit", "attack")]
            s = apply_move(s, rng.choice(sharp if sharp and rng.random() < 0.5 else moves))
        yield s


def test_constants_match():
    got = dict(rs.constants())
    want = {"SIZE": C.SIZE, "MIN_HEIGHT": C.MIN_HEIGHT, "MAX_HEIGHT": C.MAX_HEIGHT, "MAX_STEP": C.MAX_STEP,
            "LEAP_OVER_PIECES": int(C.LEAP_OVER_PIECES), "SPECIAL_MOVES_CAN_ATTACK": int(C.SPECIAL_MOVES_CAN_ATTACK),
            "VANGUARD_CHARGE_COST": C.VANGUARD_CHARGE_COST, "FINISHERS_TO_END": C.FINISHERS_TO_END,
            "MOVE_LIMIT": C.MOVE_LIMIT, "WIN": bot.WIN}
    for kind in C.KINDS:
        want[f"MOVEMENT.{kind}"] = C.MOVEMENT[kind]
        want[f"STRENGTH.{kind}"] = C.STRENGTH[kind]
    assert got == want


def test_legal_moves_apply_and_evaluate_match():
    rng = random.Random(3)
    seen = ends = 0
    for s in positions(150, seed=11):
        if s.over:  # une position finie n'est jamais confiée au bot ; la fin est vérifiée via apply_move
            ends += 1
            continue
        seen += 1
        assert rust_moves(s) == py_moves(s), f"coups légaux différents au demi-coup {s.ply}"
        for side in (1, 2):
            assert rs.evaluate(native.pack(s), side) == bot.evaluate(s, side)
        m = rng.choice(legal_moves(s))
        index = {p.id: i for i, p in enumerate(s.pieces)}
        after = apply_move(s, m)
        got, (over, winner, reason) = rs.apply_move(native.pack(s), (index.get(m.piece_id, -1), m.kind,
                                                                    -1 if m.to is None else m.to))
        assert got == native.pack(after)
        assert (over, winner, reason) == (after.over, after.winner, after.reason)
    assert seen > 3000 and ends == 150


def test_native_bot_plays_legal_moves_and_takes_the_win():
    for s in list(positions(20, seed=5))[::7]:
        if s.over:
            continue
        for level in bot.LEVELS.values():
            m = native.choose_move(s, level, random.Random(1))
            assert m in legal_moves(s)
    # Sentinelle rouge sur la dernière rangée, personne n'est sorti : elle sort et gagne
    # (même Galet : la victoire vaut bien plus que son bruit).
    s = GameState(heights=tuple([1] * 100), pieces=(Piece("rs1", 1, "sentinel", 94), Piece("bs1", 2, "sentinel", 5)),
                  to_move=1, ply=10)
    for level in bot.LEVELS.values():
        assert native.choose_move(s, level, random.Random(2)).kind == "exit"
