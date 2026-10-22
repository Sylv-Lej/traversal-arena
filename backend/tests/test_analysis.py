"""Bilan de partie : moteur d'analyse (pur) et service (file, résultat, API)."""

import asyncio
import random

import pytest
from conftest import KEY

from app.analysis import accuracy, analyse_game, analyse_position, classify
from app.bot import choose_move
from app.engine import GameState, Piece, apply_move, find_move, generate_terrain, new_game
from app.engine.types import sq
from app.services.store import MoveRecord


def flat_state(pieces, to_move=1):
    return GameState(heights=tuple([1] * 100), pieces=tuple(pieces), to_move=to_move)


def test_missing_a_winning_exit_is_a_blunder():
    # La Sentinelle rouge peut sortir en premier (victoire immédiate) : ne pas le faire = gaffe.
    s = flat_state([Piece("rs", 1, "sentinel", sq(4, 9)), Piece("bs", 2, "sentinel", sq(0, 0))])
    best = analyse_position(s, find_move(s, "rs", "exit", None))
    assert best.best.kind == "exit" and classify(best) == "best"
    other = find_move(s, "rs", "move", sq(4, 8))
    r = analyse_position(s, other)
    assert r.best.kind == "exit" and classify(r) == "blunder"


def test_accuracy_bounds():
    assert accuracy(300, 300) == pytest.approx(100, abs=0.01)
    assert accuracy(1500, -1500) < 5
    assert 0 <= accuracy(0, -200) < 100


def test_strong_bot_is_more_accurate_than_weak_bot():
    rng = random.Random(8)
    _, _, h = generate_terrain("random", 8)
    states, records = [new_game(h)], []
    while not states[-1].over:
        s = states[-1]
        m = choose_move(s, 1 if s.to_move == 1 else 5, rng)
        records.append(MoveRecord(s.ply + 1, s.to_move, m.piece_id, m.kind, m.special, None, m.to,
                                  m.path, "x", None, None, None))
        states.append(apply_move(s, m))
    seen = []
    res = analyse_game(states, records, lambda d, n: seen.append(d))
    assert seen[-1] == len(records) and len(res["moves"]) == len(records)
    weak, strong = res["accuracy"]
    assert strong > weak
    assert sum(res["counts"][1].values()) + sum(res["counts"][0].values()) == len(records)
    for m in res["moves"]:
        assert m["class"] in {"best", "excellent", "good", "inaccuracy", "mistake", "blunder", "forced"}
        if m["best"]:
            assert m["best"]["notation"] and m["best"]["path"]


async def test_analysis_api(client):
    h = {**KEY, "x-session": (await client.post("/api/players", json={}, headers=KEY)).json()["token"]}
    g = (await client.post("/api/games", json={"mode": "local"}, headers=h)).json()
    assert (await client.post(f"/api/games/{g['id']}/analysis", headers=KEY)).status_code == 409
    for _ in range(6):
        m = g["legalMoves"][0]
        g = (await client.post(f"/api/games/{g['id']}/moves",
                               json={"pieceId": m["pieceId"], "kind": m["kind"], "to": m["to"]}, headers=h)).json()
    await client.post(f"/api/games/{g['id']}/resign", headers=h)
    st = (await client.get(f"/api/games/{g['id']}/analysis", headers=KEY)).json()
    assert st["status"] == "none"
    st = (await client.post(f"/api/games/{g['id']}/analysis", headers=KEY)).json()
    assert st["status"] in ("queued", "running", "done")
    for _ in range(100):
        await asyncio.sleep(0.05)
        st = (await client.get(f"/api/games/{g['id']}/analysis", headers=KEY)).json()
        if st["status"] == "done":
            break
    assert st["status"] == "done" and len(st["result"]["moves"]) == 6
    # Relancer ne recalcule pas : le bilan est gardé.
    again = (await client.post(f"/api/games/{g['id']}/analysis", headers=KEY)).json()
    assert again["status"] == "done" and again["result"] == st["result"]
