"""Tests du moteur : chaque règle de RULES.md (Rx.y) a au moins un test."""

import random

import pytest

from app.engine import (
    TERRAIN_MODES,
    GameState,
    IllegalMove,
    Piece,
    apply_move,
    find_move,
    generate_terrain,
    legal_moves,
    new_game,
)
from app.engine import config as C
from app.engine.movegen import piece_moves, step_cost
from app.engine.types import sq


def flat(h: int = 1) -> tuple[int, ...]:
    return tuple([h] * 100)


def state(pieces: list[Piece], heights=None, to_move: int = 1, **kw) -> GameState:
    return GameState(heights=heights or flat(), pieces=tuple(pieces), to_move=to_move, **kw)


def P(pid: str, owner: int, kind: str, x: int, y: int) -> Piece:
    return Piece(pid, owner, kind, sq(x, y))


def dests(moves, kind=None):
    return {m.to for m in moves if kind is None or m.kind == kind}


# --- R2 Terrain ----------------------------------------------------------------------


@pytest.mark.parametrize("mode", TERRAIN_MODES)
@pytest.mark.parametrize("seed", range(60))
def test_terrain_is_fair_and_traversable(mode, seed):
    _, _, h = generate_terrain(mode, seed)
    assert len(h) == 100
    assert all(C.MIN_HEIGHT <= v <= C.MAX_HEIGHT for v in h)
    for y in range(10):
        for x in range(10):
            assert h[sq(x, y)] == h[sq(9 - x, 9 - y)], "R2.2 symétrie centrale"
            if x < 9:
                assert abs(h[sq(x, y)] - h[sq(x + 1, y)]) <= 2, "R2.1"
            if y < 9:
                assert abs(h[sq(x, y)] - h[sq(x, y + 1)]) <= 2, "R2.1"


@pytest.mark.parametrize("mode", TERRAIN_MODES[1:])
def test_terrain_varies_a_lot(mode):
    boards = [generate_terrain(mode, seed)[2] for seed in range(120)]
    assert len(set(boards)) >= 118
    means = [sum(h) / 100 for h in boards]
    assert max(means) - min(means) >= 1.5  # pas toujours le même niveau moyen
    assert sum(len(set(h)) >= 3 for h in boards) >= 110  # quasiment jamais plat


def test_terrain_is_reproducible():
    assert generate_terrain("random", 7) == generate_terrain("random", 7)
    with pytest.raises(ValueError):
        generate_terrain("lava", 1)


# --- R3 Mise en place ----------------------------------------------------------------


def test_setup_symmetric_two_of_each():
    s = new_game(flat())
    assert len(s.pieces) == 12
    for owner, row in ((1, 0), (2, 9)):
        mine = [p for p in s.pieces if p.owner == owner]
        assert sorted(p.sq % 10 for p in mine) == [2, 3, 4, 5, 6, 7]
        assert all(p.sq // 10 == row for p in mine)
        for kind in C.KINDS:
            assert sum(p.kind == kind for p in mine) == 2
    by_sq = {p.sq: p for p in s.pieces}
    for p in s.pieces:
        twin = by_sq[99 - p.sq]
        assert twin.kind == p.kind and twin.owner != p.owner
    assert s.to_move == 1


# --- R4 Déplacement ------------------------------------------------------------------


def test_step_costs():
    h = list(flat(2))
    h[sq(1, 0)] = 4
    h = tuple(h)
    assert step_cost(h, sq(0, 0), sq(0, 1)) == 1  # plat
    assert step_cost(h, sq(0, 0), sq(1, 0)) == 3  # 2 -> 4 : montée
    assert step_cost(h, sq(1, 0), sq(0, 0)) == 3  # 4 -> 2 : descente, même coût


def test_flat_reach_equals_movement_diamond():
    s = state([P("s", 1, C.SENTINEL, 5, 5)])
    moves = piece_moves(s, s.pieces[0])
    reached = dests(moves, "move")
    # Losange de rayon 3 privé du centre : 2*3*(3+1) = 24 cases.
    assert len(reached) == 24
    assert sq(5, 5) not in reached  # R4.6
    assert all(m.cost <= 3 for m in moves)


def test_slopes_consume_movement():
    h = list(flat(0))
    for x in range(10):
        h[sq(x, 6)] = 2  # mur de hauteur 2 juste devant
    s = state([P("s", 1, C.SENTINEL, 5, 5)], heights=tuple(h))
    reached = dests(piece_moves(s, s.pieces[0]), "move")
    assert sq(5, 6) in reached  # coût 3 : pile le budget
    assert sq(5, 7) not in reached


def test_cannot_pass_through_pieces():
    # Sentinelle encerclée par 3 pièces : seule issue vers le bas.
    s = state(
        [
            P("s", 1, C.SENTINEL, 5, 5),
            P("a", 1, C.EXPLORER, 4, 5),
            P("b", 1, C.EXPLORER, 6, 5),
            P("c", 1, C.EXPLORER, 5, 6),
        ]
    )
    reached = dests(piece_moves(s, s.pieces[0]), "move")
    assert sq(5, 7) not in reached and sq(3, 5) not in reached
    assert sq(5, 4) in reached


def test_paths_are_orthogonal_and_cost_consistent():
    _, _, h = generate_terrain("highlands", 3)
    s = new_game(h)
    for m in legal_moves(s):
        if m.special or m.kind == "pass":
            continue
        assert sum(step_cost(h, a, b) for a, b in zip(m.path, m.path[1:])) + (m.kind == "exit") == m.cost
        for a, b in zip(m.path, m.path[1:]):
            assert abs(a - b) in (1, 10)


# --- R5 Explorateur ------------------------------------------------------------------


def test_explorer_diagonal_and_leap_ignore_height():
    h = list(flat(0))
    for x, y in ((6, 6), (5, 7), (5, 6), (6, 5)):
        h[sq(x, y)] = 6
    h[sq(5, 7)] = 4
    s = state([P("e", 1, C.EXPLORER, 5, 5)], heights=tuple(h))
    moves = {m.to: m for m in piece_moves(s, s.pieces[0])}
    assert moves[sq(6, 6)].special == "diag"
    assert moves[sq(5, 7)].special == "leap"


def test_explorer_cannot_leap_over_a_piece():
    s = state([P("e", 1, C.EXPLORER, 5, 5), P("x", 2, C.SENTINEL, 5, 6)], heights=flat())
    moves = piece_moves(s, s.pieces[0])
    leap = [m for m in moves if m.special == "leap" and m.to == sq(5, 7)]
    assert not leap  # case intermédiaire occupée
    # (5,7) reste atteignable en contournant, mais pas par un bond.
    assert any(m.to == sq(5, 7) and m.special is None for m in moves)


def test_explorer_leap_cannot_land_on_ally():
    h = list(flat(0))
    h[sq(5, 6)] = 6  # infranchissable normalement
    s = state([P("e", 1, C.EXPLORER, 5, 5), P("a", 1, C.SENTINEL, 5, 7)], heights=tuple(h))
    assert sq(5, 7) not in dests(piece_moves(s, s.pieces[0]))


# --- R6 / R8 Sortie et fin de partie -------------------------------------------------


def test_exit_requires_one_movement_left():
    s = state([P("s", 1, C.SENTINEL, 5, 7)])  # 2 pas pour la rangée 9, +1 pour sortir
    assert any(m.kind == "exit" for m in piece_moves(s, s.pieces[0]))
    s = state([P("s", 1, C.SENTINEL, 5, 6)])  # 3 pas : plus rien pour sortir
    assert not any(m.kind == "exit" for m in piece_moves(s, s.pieces[0]))


def test_blue_exits_through_row_zero():
    s = state([P("v", 2, C.VANGUARD, 0, 2)], to_move=2)
    ex = [m for m in piece_moves(s, s.pieces[0]) if m.kind == "exit"]
    assert ex and ex[0].path[-1] // 10 == 0


def test_sentinel_first_out_wins_immediately():
    s = state([P("s", 1, C.SENTINEL, 5, 9), P("x", 2, C.EXPLORER, 0, 0)])
    after = apply_move(s, find_move(s, "s", "exit", None))
    assert after.over and after.winner == 1 and after.reason == "sentinel"
    assert after.scores == (3, 0)


def test_two_finishers_end_game_on_score():
    s = state(
        [P("e", 1, C.EXPLORER, 5, 9), P("v", 2, C.VANGUARD, 5, 0), P("k", 2, C.SENTINEL, 0, 5)]
    )
    s = apply_move(s, find_move(s, "e", "exit", None))
    assert not s.over and s.scores == (1, 0)
    s = apply_move(s, find_move(s, "v", "exit", None))
    assert s.over and s.reason == "score" and s.winner == 2 and s.scores == (1, 2)


def test_sentinel_second_out_is_not_special():
    s = state([P("e", 1, C.EXPLORER, 5, 9), P("s", 2, C.SENTINEL, 5, 0)])
    s = apply_move(s, find_move(s, "e", "exit", None))
    s = apply_move(s, find_move(s, "s", "exit", None))
    assert s.reason == "score" and s.winner == 2


def test_tie_is_draw():
    s = state([P("e", 1, C.EXPLORER, 5, 9), P("f", 2, C.EXPLORER, 5, 0)])
    s = apply_move(s, find_move(s, "e", "exit", None))
    s = apply_move(s, find_move(s, "f", "exit", None))
    assert s.over and s.winner is None


def test_move_limit_adjudication():
    # Personne n'a marqué : la pièce la plus avancée gagne.
    s = state([P("a", 1, C.SENTINEL, 0, 5), P("b", 2, C.SENTINEL, 9, 6)], move_limit=1)
    s = apply_move(s, find_move(s, "a", "move", sq(0, 6)))
    assert s.over and s.reason == "move_limit" and s.winner == 1
    # Égalité de distance : la plus forte gagne.
    s = state([P("a", 1, C.EXPLORER, 0, 4), P("b", 2, C.SENTINEL, 9, 5)], move_limit=1)
    s = apply_move(s, find_move(s, "a", "move", sq(1, 4)))
    assert s.winner == 2
    # Égalité totale : nulle.
    s = state([P("a", 1, C.SENTINEL, 0, 4), P("b", 2, C.SENTINEL, 9, 5)], move_limit=1)
    s = apply_move(s, find_move(s, "a", "move", sq(1, 4)))
    assert s.over and s.winner is None


def test_pass_when_no_move():
    s = state([P("x", 2, C.SENTINEL, 0, 0)], to_move=1)
    moves = legal_moves(s)
    assert [m.kind for m in moves] == ["pass"]
    after = apply_move(s, moves[0])
    assert after.to_move == 2 and after.ply == 1


# --- R7 Combat -----------------------------------------------------------------------


def test_example_hill_advantage():
    """Exemple 1 de la source : Avant-garde 2 +1 hauteur = 3 vs Avant-garde 2 +1 renfort."""
    h = list(flat(1))
    h[sq(5, 4)] = 2  # l'attaquant part d'une case plus haute
    s = state(
        [
            P("rv", 1, C.VANGUARD, 5, 4),
            P("bv", 2, C.VANGUARD, 5, 5),
            P("bs", 2, C.EXPLORER, 6, 5),  # renfort du défenseur
        ],
        heights=tuple(h),
    )
    m = find_move(s, "rv", "attack", sq(5, 5))
    assert (m.combat.attack, m.combat.defense) == (3, 3)
    after = apply_move(s, m)
    assert after.piece("bv") is None
    assert after.piece("rv").sq == sq(5, 5)  # l'attaquant prend la case
    assert [p.id for p in after.captured] == ["bv"]
    assert after.scores == (0, 0)  # R7.2 une capture ne marque pas


def test_example_allied_assault():
    """Exemple 2 : Explorateur 1 + Avant-garde alliée adjacente (+2) = 3 vs Sentinelle 3."""
    s = state(
        [
            P("re", 1, C.EXPLORER, 5, 3),
            P("rv", 1, C.VANGUARD, 6, 5),
            P("bs", 2, C.SENTINEL, 5, 5),
        ]
    )
    m = find_move(s, "re", "attack", sq(5, 5))
    assert (m.combat.attack, m.combat.defense) == (3, 3)
    assert any(t.label == "ally:vanguard" and t.value == 2 for t in m.combat.attack_terms)


def test_losing_attack_is_illegal():
    s = state([P("re", 1, C.EXPLORER, 5, 4), P("bs", 2, C.SENTINEL, 5, 5)])
    assert sq(5, 5) not in dests(legal_moves(s))
    with pytest.raises(IllegalMove):
        find_move(s, "re", "attack", sq(5, 5))


def test_uphill_attack_penalty():
    h = list(flat(1))
    h[sq(5, 5)] = 2
    s = state([P("rs", 1, C.SENTINEL, 5, 4), P("bs", 2, C.SENTINEL, 5, 5)], heights=tuple(h))
    assert sq(5, 5) not in dests(legal_moves(s))  # 3 - 1 = 2 < 3


def test_vanguard_charge_needs_exactly_four():
    # Cible à 4 pas sur le plat : charge (+1) -> 3 >= 3.
    s = state([P("rv", 1, C.VANGUARD, 5, 1), P("bs", 2, C.SENTINEL, 5, 5)])
    m = find_move(s, "rv", "attack", sq(5, 5))
    assert m.cost == 4 and m.combat.attack == 3
    # Cible à 3 pas : pas de charge -> 2 < 3, attaque illégale.
    s = state([P("rv", 1, C.VANGUARD, 5, 2), P("bs", 2, C.SENTINEL, 5, 5)])
    assert sq(5, 5) not in dests(legal_moves(s))


def test_attack_moves_into_target_with_entry_cost():
    h = list(flat(0))
    h[sq(5, 5)] = 2  # entrer sur la cible coûte 3
    s = state([P("rs", 1, C.SENTINEL, 5, 4), P("be", 2, C.EXPLORER, 5, 5)], heights=tuple(h))
    m = find_move(s, "rs", "attack", sq(5, 5))
    assert m.cost == 3 and m.path == (sq(5, 4), sq(5, 5))


# --- Robustesse ----------------------------------------------------------------------


def test_random_games_always_terminate():
    rng = random.Random(0)
    for game in range(60):
        _, _, h = generate_terrain(rng.choice(TERRAIN_MODES), game)
        s = new_game(h)
        while not s.over:
            moves = legal_moves(s)
            assert moves
            s = apply_move(s, rng.choice(moves))
        assert s.ply <= C.MOVE_LIMIT
        assert len(s.pieces) + len(s.finished) + len(s.captured) == 12


def test_setup_puts_the_fastest_pieces_in_the_centre():
    s = new_game(tuple([1] * 100))
    for owner, row in ((1, 0), (2, 9)):
        # Vu par chaque joueur (le bleu a le plateau tourné) : S V E E V S, colonnes c à h.
        line = sorted((p.sq, p.kind) for p in s.pieces if p.owner == owner)
        kinds = [k for _, k in line] if owner == 1 else [k for _, k in reversed(line)]
        assert kinds == ["sentinel", "vanguard", "explorer", "explorer", "vanguard", "sentinel"]
        assert {sq // 10 for sq, _ in line} == {row}


def test_old_games_replay_with_their_own_setup():
    from app.services.store import replay

    classic = new_game(tuple([1] * 100), setup="classic")
    assert [p.kind for p in classic.pieces[:6]] == ["explorer", "vanguard", "sentinel", "sentinel", "vanguard", "explorer"]
    states = replay([1] * 100, 200, [], None, None, setup="classic")
    assert states[0].pieces == classic.pieces
    # Sans mise en place enregistrée (parties d'avant), c'est l'ancienne.
    assert replay([1] * 100, 200, [], None, None)[0].pieces == classic.pieces
