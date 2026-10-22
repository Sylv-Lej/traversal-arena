"""Puzzles : classés (Glicko joueur et puzzle), indice, solution, puzzle du jour, Rush."""

import time

from conftest import KEY, new_player
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app import db, puzzles
from app.engine import GameState, Piece, apply_move, legal_moves
from app.engine.types import sq
from app.services import training
from app.services.store import store

FLAT = tuple([1] * 100)


def _state(pieces, to_move=2):
    return GameState(heights=FLAT, pieces=tuple(pieces), to_move=to_move)


def _key(m):
    return {"pieceId": m.piece_id, "kind": m.kind, "to": m.to}


def win_in_one(pid="pz1", rating=1200.0, two_exits=False):
    """Bleu joue (n'importe quoi), puis Rouge sort sa Sentinelle : victoire immédiate."""
    ps = [Piece("rs1", 1, "sentinel", sq(4, 9)), Piece("re1", 1, "explorer", sq(1, 2)),
          Piece("bs1", 2, "sentinel", sq(0, 5)), Piece("bv1", 2, "vanguard", sq(8, 6))]
    if two_exits:
        ps.append(Piece("rs2", 1, "sentinel", sq(6, 9)))
    start = _state(ps)
    opp = next(m for m in legal_moves(start) if m.piece_id == "bv1" and m.kind == "move")
    s1 = apply_move(start, opp)
    exit_ = next(m for m in legal_moves(s1) if m.piece_id == "rs1" and m.kind == "exit")
    return {"id": pid, "terrain": "woodlands", "start": puzzles.state_to_json(start),
            "solution": [_key(opp), _key(exit_)], "themes": ["exit", "sentinel", "winIn1"], "side": 1,
            "rating": rating}


def two_steps(pid="pz2", rating=1500.0):
    """Deux coups du joueur : avancer la Sentinelle, puis la sortir (après la réponse bleue)."""
    start = _state([Piece("rs1", 1, "sentinel", sq(4, 7)), Piece("bs1", 2, "sentinel", sq(0, 5)),
                    Piece("bv1", 2, "vanguard", sq(8, 6))])
    opp = next(m for m in legal_moves(start) if m.piece_id == "bv1" and m.kind == "move")
    s = apply_move(start, opp)
    up = next(m for m in legal_moves(s) if m.piece_id == "rs1" and m.kind == "move" and m.to // 10 == 9)
    s = apply_move(s, up)
    reply = next(m for m in legal_moves(s) if m.piece_id == "bv1" and m.kind == "move")
    s = apply_move(s, reply)
    exit_ = next(m for m in legal_moves(s) if m.piece_id == "rs1" and m.kind == "exit")
    return {"id": pid, "terrain": "woodlands", "start": puzzles.state_to_json(start),
            "solution": [_key(opp), _key(up), _key(reply), _key(exit_)], "themes": ["winIn2"], "side": 1,
            "rating": rating}


async def add(*items):
    now = time.time()
    async with store.engine.begin() as conn:
        for p in items:
            await conn.execute(pg_insert(db.puzzles).values(
                id=p["id"], terrain=p["terrain"], start=p["start"], solution=p["solution"], tree=p.get("tree"),
                themes=p["themes"],
                side=p["side"], rating=p["rating"], rd=training.PUZZLE_RD, vol=0.06, plays=0, solves=0,
                created_at=now))


async def move(client, h, att, m):
    r = await client.post(f"/api/puzzles/attempts/{att['id']}/move", json=m, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


async def test_rated_puzzle_solved_moves_both_ratings(client):
    pz = win_in_one()
    await add(pz)
    h = await new_player(client)
    a = (await client.get("/api/puzzles/next", headers=h)).json()
    assert a["status"] == "playing" and a["rated"] and a["side"] == 1
    assert len(a["moves"]) == 1 and a["position"]["toMove"] == 1  # le coup adverse est déjà joué
    assert "solution" not in a and "puzzle" not in a  # rien ne fuit avant la fin
    a = await move(client, h, a, pz["solution"][1])
    assert a["status"] == "solved" and a["ratingChange"]["after"] > a["ratingChange"]["before"]
    assert a["puzzle"]["themes"] == pz["themes"] and len(a["solution"]) == 2
    async with store.engine.connect() as conn:
        pr = (await conn.execute(select(db.puzzles.c.rating, db.puzzles.c.plays, db.puzzles.c.solves)
                                 .where(db.puzzles.c.id == "pz1"))).first()
    assert pr[0] < 1200 and pr[1] == 1 and pr[2] == 1
    st = (await client.get("/api/puzzles/stats", headers=h)).json()
    assert st["rated"] == 1 and st["solved"] == 1 and st["rating"] > 1200
    assert st["rank"]["placement"] == {"played": 1, "total": 5}  # rang puzzles, comme en partie


async def test_wrong_move_fails_and_shows_solution(client):
    await add(win_in_one())
    h = await new_player(client)
    a = (await client.get("/api/puzzles/next", headers=h)).json()
    wrong = next(m for m in a["legalMoves"] if m["pieceId"] == "re1")
    a = await move(client, h, a, {"pieceId": wrong["pieceId"], "kind": wrong["kind"], "to": wrong["to"]})
    assert a["status"] == "failed" and a["wrong"]["pieceId"] == "re1" and a["solution"]
    assert a["ratingChange"]["after"] < a["ratingChange"]["before"]
    bad = await client.post(f"/api/puzzles/attempts/{a['id']}/move", json={"pieceId": "rs1", "kind": "exit"}, headers=h)
    assert bad.status_code == 409


async def test_multi_step_with_opponent_reply(client):
    pz = two_steps()
    await add(pz)
    h = await new_player(client)
    a = (await client.get("/api/puzzles/next", headers=h)).json()
    assert a["playerMoves"] == 2
    a = await move(client, h, a, pz["solution"][1])
    assert a["status"] == "playing" and len(a["moves"]) == 3  # + la réponse bleue
    a = await move(client, h, a, pz["solution"][3])
    assert a["status"] == "solved"


async def test_failed_puzzle_blocks_even_after_a_wrong_retry(client):
    await add(win_in_one("pza"), win_in_one("pzb"))
    h = await new_player(client)
    a = (await client.get("/api/puzzles/next", headers=h)).json()
    wrong = next(m for m in a["legalMoves"] if m["pieceId"] == "re1")
    await move(client, h, a, {"pieceId": "re1", "kind": wrong["kind"], "to": wrong["to"]})
    for _ in range(2):  # raté encore : toujours bloqué sur le même
        r = (await client.get("/api/puzzles/next", headers=h)).json()
        assert r["puzzleId"] == a["puzzleId"]
        r = await move(client, h, r, {"pieceId": "re1", "kind": wrong["kind"], "to": wrong["to"]})
        assert r["status"] == "failed"


def with_variant(pz):
    """`two_steps` + une variante : un autre chemin de la Sentinelle vers la dernière rangée."""
    s = puzzles.state_from_json(pz["start"])
    for d in pz["solution"][:1]:
        s = apply_move(s, training.find_move(s, d["pieceId"], d["kind"], d["to"]))
    ups = [m for m in legal_moves(s) if m.piece_id == "rs1" and m.kind == "move" and m.to // 10 == 9]
    alt = next(m for m in ups if not puzzles.same(m, pz["solution"][1]))
    a = apply_move(s, alt)
    reply = next(m for m in legal_moves(a) if m.piece_id == "bv1" and m.kind == "move")
    b = apply_move(a, reply)
    exit_ = next(m for m in legal_moves(b) if m.piece_id == "rs1" and m.kind == "exit")
    main = {"m": pz["solution"][1], "r": pz["solution"][2], "next": [{"m": pz["solution"][3]}]}
    pz["tree"] = [main, {"m": _key(alt), "r": _key(reply), "next": [{"m": _key(exit_)}]}]
    return pz, _key(alt), _key(exit_)


async def test_variant_from_the_tree_is_accepted_and_explained(client):
    pz, alt, exit_ = with_variant(two_steps())
    await add(pz)
    h = await new_player(client)
    a = (await client.get("/api/puzzles/next", headers=h)).json()
    assert a["goal"] == "win" and a["playerMoves"] == 2 and "notes" not in a
    a = await move(client, h, a, alt)
    assert a["status"] == "playing" and len(a["moves"]) == 3
    assert (await client.get(f"/api/puzzles/attempts/{a['id']}", headers=h)).json()["moves"] == a["moves"]
    a = await move(client, h, a, exit_)
    assert a["status"] == "solved"
    # La solution montrée suit la variante jouée, et chaque coup du joueur est expliqué.
    assert len(a["solution"]) == 4 and a["solution"][1]["to"] == alt["to"]
    assert a["notes"][0] is None and a["notes"][1] and a["notes"][3][0]["code"] == "sentinelFirst"


async def test_any_immediate_win_is_accepted(client):
    pz = win_in_one(two_exits=True)
    await add(pz)
    h = await new_player(client)
    a = (await client.get("/api/puzzles/next", headers=h)).json()
    a = await move(client, h, a, {"pieceId": "rs2", "kind": "exit", "to": None})
    assert a["status"] == "solved"


async def test_hint_counts_as_failure_and_open_puzzle_is_resumed(client):
    await add(win_in_one("pza"), win_in_one("pzb"))
    h = await new_player(client)
    a = (await client.get("/api/puzzles/next", headers=h)).json()
    hint = (await client.post(f"/api/puzzles/attempts/{a['id']}/hint", json={}, headers=h)).json()  # comme le relais
    assert hint["pieceId"] == "rs1"
    a = await move(client, h, a, {"pieceId": "rs1", "kind": "exit", "to": None})
    assert a["status"] == "failed" and a["ratingChange"]["after"] < a["ratingChange"]["before"]
    # Raté : il bloque la suite, on le rejoue (non classé) jusqu'à le réussir.
    blocked = (await client.get("/api/puzzles/next", headers=h)).json()
    assert blocked["puzzleId"] == a["puzzleId"] and blocked["mode"] == "retry" and not blocked["rated"]
    assert (await client.get("/api/puzzles/next", headers=h)).json()["id"] == blocked["id"]  # repris tel quel
    await move(client, h, blocked, {"pieceId": "rs1", "kind": "exit", "to": None})
    b = (await client.get("/api/puzzles/next", headers=h)).json()
    assert b["puzzleId"] != a["puzzleId"] and b["rated"]  # réussi : on passe au suivant, classé
    again = (await client.get("/api/puzzles/next", headers=h)).json()
    assert again["id"] == b["id"]  # un puzzle classé en cours est repris, pas changé
    # Rejouer : jamais classé.
    r = (await client.post(f"/api/puzzles/{a['puzzleId']}/retry", headers=h)).json()
    r = await move(client, h, r, {"pieceId": "rs1", "kind": "exit", "to": None})
    assert r["status"] == "solved" and "ratingChange" not in r


async def test_daily_is_the_same_for_everyone(client):
    await add(win_in_one("pza"), win_in_one("pzb"), win_in_one("pzc"))
    a, b = await new_player(client), await new_player(client)
    da = (await client.get("/api/puzzles/daily", headers=a)).json()
    db_ = (await client.get("/api/puzzles/daily", headers=b)).json()
    assert da["puzzleId"] == db_["puzzleId"] and not da["rated"] and da["daily"] == training.daily_key()
    assert (await client.get("/api/puzzles/daily", headers=a)).json()["id"] == da["id"]  # on reprend


async def test_puzzle_rush(client):
    await add(*[win_in_one(f"r{i}", rating=600 + 40 * i) for i in range(8)])
    h = await new_player(client, "Rusher")
    r = (await client.post("/api/puzzles/rush", json={"mode": "3min"}, headers=h)).json()
    assert r["status"] == "running" and r["remainingMs"] > 170_000 and r["attempt"]
    await move(client, h, r["attempt"], {"pieceId": "rs1", "kind": "exit", "to": None})
    r = (await client.get(f"/api/puzzles/rush/{r['id']}", headers=h)).json()
    assert r["score"] == 1 and r["attempt"]["puzzleId"] != r["history"][0]["puzzleId"]
    for _ in range(3):  # 3 erreurs : fini
        wrong = next(m for m in r["attempt"]["legalMoves"] if m["pieceId"] == "re1")
        await move(client, h, r["attempt"], {"pieceId": "re1", "kind": wrong["kind"], "to": wrong["to"]})
        r = (await client.get(f"/api/puzzles/rush/{r['id']}", headers=h)).json()
    assert r["status"] == "over" and r["score"] == 1 and r["strikes"] == 3 and r["best"] == 1
    lb = (await client.get("/api/puzzles/rush/leaderboard?mode=3min", headers=KEY)).json()
    assert lb[0]["name"] == "Rusher" and lb[0]["score"] == 1


async def test_rush_caps_puzzles_and_ramps_up(client):
    n = training.RUSH_MAX + 2
    await add(*[win_in_one(f"c{i:02d}", rating=training.RUSH_START + training.RUSH_STEP * i) for i in range(n)])
    h = await new_player(client)
    r = (await client.post("/api/puzzles/rush", json={"mode": "survival"}, headers=h)).json()
    assert r["maxPuzzles"] == training.RUSH_MAX
    while r["status"] == "running":
        await move(client, h, r["attempt"], {"pieceId": "rs1", "kind": "exit", "to": None})
        r = (await client.get(f"/api/puzzles/rush/{r['id']}", headers=h)).json()
    assert r["score"] == training.RUSH_MAX and len(r["history"]) == training.RUSH_MAX
    played = [x["rating"] for x in r["history"]]
    assert played == sorted(played) and played[-1] >= training.RUSH_START + training.RUSH_STEP * 15


async def test_rush_time_runs_out(client):
    await add(*[win_in_one(f"t{i}") for i in range(3)])
    h = await new_player(client)
    r = (await client.post("/api/puzzles/rush", json={"mode": "5min"}, headers=h)).json()
    async with store.engine.begin() as conn:
        await conn.execute(update(db.puzzle_rushes).where(db.puzzle_rushes.c.id == r["id"])
                           .values(deadline_at=time.time() - 1))
    r = (await client.get(f"/api/puzzles/rush/{r['id']}", headers=h)).json()
    assert r["status"] == "over" and r["attempt"] is None


async def test_seed_loads_the_shipped_puzzles():
    data = puzzles.load()
    if not data:
        return  # jeu de puzzles pas encore généré
    async with store.engine.begin() as conn:
        await conn.execute(db.puzzles.delete())
    assert await training.seed() == len(data)
    assert await training.seed() == 0  # idempotent
    # Chaque puzzle livré est jouable : sa solution est légale de bout en bout.
    for p in data[:50]:
        s = puzzles.state_from_json(p["start"])
        for d in p["solution"]:
            m = next(m for m in legal_moves(s) if puzzles.same(m, d))
            s = apply_move(s, m)
