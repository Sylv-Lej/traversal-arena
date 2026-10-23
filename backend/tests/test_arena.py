"""Arène des bots : envoi, validation, parties rendues par le runner (vérifiées par le
moteur Python), classement."""

import base64

import os
import re

from conftest import KEY
from sqlalchemy import func, select

from app import db
from app.engine import apply_move, legal_moves, new_game
from app.services import accounts, arena, mailer
from app.services.store import store

RUNNER = {"x-arena-token": "test-arena"}
WASM = base64.b64encode(b"\0asm\x01\0\0\0" + b"\0" * 64).decode()  # jamais exécuté ici


async def registered(client, email="bots@example.com", verified=True):
    r = await client.post("/api/players", json={}, headers=KEY)
    h = {**KEY, "x-session": r.json()["token"]}
    r = await client.post("/api/auth/signup", json={"email": email, "password": "motdepasse-solide",
                                                    "country": "FR"}, headers=h)
    assert r.status_code == 200, r.text
    if verified:
        await accounts.flush_mails()
        token = re.search(r"/verify\?token=([\w-]+)", mailer.outbox[-1]["text"]).group(1)
        assert (await client.post("/api/auth/verify", json={"token": token}, headers=KEY)).status_code == 200
    return h


def wire(job, pick=lambda moves: moves[0], plies=None):
    """Joue la partie d'une tâche avec le moteur Python, coups au format du runner."""
    s = new_game(tuple(job["heights"]), job["moveLimit"])
    out = []
    while not s.over and (plies is None or len(out) < plies):
        m = pick(legal_moves(s))
        idx = next((i for i, p in enumerate(s.pieces) if p.id == m.piece_id), -1)
        out.append([idx, m.kind, -1 if m.to is None else m.to])
        s = apply_move(s, m)
    return out


async def claim(client):
    r = await client.post("/api/arena/runner/claim", json={}, headers=RUNNER)
    assert r.status_code == 200, r.text
    return r.json()["job"]


async def active_bot(client, h, name="Alpha", replaces=None):
    r = await client.post("/api/arena/bots", json={"name": name, "wasm": WASM, "replaces": replaces}, headers=h)
    assert r.status_code == 200, r.text
    bot = r.json()
    job = await claim(client)
    assert job["kind"] == "check" and job["red"] == {"id": bot["id"], "sha256": bot["sha256"]}
    assert job["blue"] == {"id": "bot1", "house": 1} and job["fuel"] == arena.FUEL_PER_MOVE
    r = await client.post(f"/api/arena/runner/jobs/{job['id']}", json={"ok": True}, headers=RUNNER)
    assert r.status_code == 200, r.text
    return bot["id"]


def test_fit_is_anchored_and_ordered():
    games = [("bot1", "x", 0.0)] * 8 + [("bot1", "x", 1.0)] * 2 + [("x", "y", 0.0)] * 7 + [("x", "y", 0.5)] * 2
    r = arena.fit(games)
    assert round(r["bot1"][0]) == 920
    assert r["bot1"][0] < r["x"][0] < r["y"][0]
    assert all(m > 0 for _, m in r.values())
    # Invaincu : classement fini grâce à l'adversaire fictif.
    assert arena.fit([("bot1", "z", 0.0)] * 3)["z"][0] < 3000


async def test_runner_needs_its_token(client):
    assert (await client.post("/api/arena/runner/claim", json={})).status_code == 401
    # La clé d'API du front n'ouvre pas l'API du runner.
    assert (await client.post("/api/arena/runner/claim", json={}, headers=KEY)).status_code == 401


async def test_guests_cannot_submit_and_files_are_checked(client):
    guest = {**KEY, "x-session": (await client.post("/api/players", json={}, headers=KEY)).json()["token"]}
    r = await client.post("/api/arena/bots", json={"name": "Alpha", "wasm": WASM}, headers=guest)
    assert r.status_code == 403
    h = await registered(client)
    r = await client.post("/api/arena/bots", json={"name": "Alpha", "wasm": base64.b64encode(b"MZ...").decode()},
                          headers=h)
    assert r.status_code == 422
    r = await client.post("/api/arena/bots", json={"name": "Sommet", "wasm": WASM}, headers=h)
    assert r.status_code == 409  # nom d'un bot maison
    # Adresse pas encore confirmée : pas de bot.
    unconfirmed = await registered(client, "pasconfirme@example.com", verified=False)
    r = await client.post("/api/arena/bots", json={"name": "Beta", "wasm": WASM}, headers=unconfirmed)
    assert r.status_code == 403 and "Confirme" in r.json()["detail"]


async def test_validation_placement_and_leaderboard(client):
    h = await registered(client)
    bot_id = await active_bot(client, h)
    me = (await client.get("/api/arena/mine", headers=h)).json()
    assert [(b["name"], b["status"]) for b in me] == [("Alpha", "active")]

    # Placement : une paire de parties contre chacun des 5 bots maison.
    async with store.engine.connect() as conn:
        assert (await conn.execute(select(func.count()).select_from(db.arena_jobs))).scalar() == 10
    for _ in range(10):
        job = await claim(client)
        assert job["kind"] == "game" and bot_id in (job["red"]["id"], job["blue"]["id"])
        r = await client.post(f"/api/arena/runner/jobs/{job['id']}", json={"moves": wire(job)}, headers=RUNNER)
        assert r.status_code == 200, r.text

    await arena.recompute(force=True)
    board = (await client.get("/api/arena/leaderboard", headers=KEY)).json()
    row = next(b for b in board if b["id"] == bot_id)
    assert row["games"] == 10 and row["author"]["id"] and row["rating"] is not None
    assert next(b for b in board if b["id"] == "bot1")["rating"] == 920
    # Division : comme les joueurs (Galet = 920 -> Ardoise II), placement fini après 10 parties.
    assert next(b for b in board if b["id"] == "bot1")["tier"]["label"] == "Ardoise II"
    assert row["tier"]["placement"] is None and row["tier"]["tier"] is not None
    view = (await client.get(f"/api/arena/bots/{bot_id}", headers=KEY)).json()
    assert len(view["recent"]) == 10 and view["versions"][0]["version"] == 1
    assert all(g["currentSetup"] for g in view["recent"])
    # Pas de relecture tant que ce n'est pas ouvert ; ensuite, comme les autres parties.
    gid = view["recent"][0]["id"]
    assert (await client.get("/api/arena/info", headers=KEY)).json()["replays"] is False
    for path in (f"games/{gid}", f"games/{gid}/history", f"games/{gid}/analysis"):
        assert (await client.get(f"/api/{path}", headers=h)).status_code == 404
    # Sauf la partie de l'accueil, choisie par le serveur : celle du meilleur bot.
    shown = (await client.get("/api/arena/showcase", headers=KEY)).json()["game"]
    assert shown["mode"] == "arena" and len(shown["positions"]) == len(shown["moves"]) + 1
    assert bot_id in {p["id"] for p in shown["players"] if p}
    os.environ["ARENA_REPLAYS"] = "1"
    try:
        game = (await client.get(f"/api/games/{gid}", headers=h)).json()
        assert game["mode"] == "arena" and game["status"] == "finished"
        assert (await client.get("/api/arena/info", headers=KEY)).json()["replays"] is True
    finally:
        del os.environ["ARENA_REPLAYS"]

    # File vide : un nouveau lot est tiré (le bot contre un voisin, + calibrage maison).
    job = await claim(client)
    assert job is not None and job["kind"] == "game"


async def test_new_version_replaces_the_old_one(client):
    h = await registered(client)
    v1 = await active_bot(client, h)
    # Même nom sans dire « mise à jour » : refusé (pas de nouvelle version par mégarde).
    r = await client.post("/api/arena/bots", json={"name": "Alpha", "wasm": WASM}, headers=h)
    assert r.status_code == 409
    # Seul l'auteur peut envoyer une version d'un bot.
    other = await registered(client, "autre@example.com")
    r = await client.post("/api/arena/bots", json={"wasm": WASM, "replaces": v1}, headers=other)
    assert r.status_code == 404
    v2 = await active_bot(client, h, name="", replaces=v1)
    view = (await client.get(f"/api/arena/bots/{v1}", headers=KEY)).json()
    assert view["status"] == "retired"
    assert [v["version"] for v in view["versions"]] == [2, 1]
    async with store.engine.connect() as conn:
        assert (await conn.execute(select(db.arena_bots.c.wasm).where(db.arena_bots.c.id == v1))).scalar() is None
    board = (await client.get("/api/arena/leaderboard", headers=KEY)).json()
    assert v2 in {b["id"] for b in board} and v1 not in {b["id"] for b in board}


async def test_rejected_bot(client):
    h = await registered(client)
    r = await client.post("/api/arena/bots", json={"name": "Buggy", "wasm": WASM}, headers=h)
    job = await claim(client)
    await client.post(f"/api/arena/runner/jobs/{job['id']}", json={"ok": False, "error": "fuel épuisé"},
                      headers=RUNNER)
    view = (await client.get(f"/api/arena/bots/{r.json()['id']}", headers=KEY)).json()
    assert (view["status"], view["error"]) == ("rejected", "fuel épuisé")


async def test_results_are_replayed_not_trusted(client):
    h = await registered(client)
    bot_id = await active_bot(client, h)
    job = await claim(client)
    # Coup illégal : refusé, la tâche disparaît.
    bad = wire(job, plies=3)
    bad[2] = [0, "exit", -1]
    r = await client.post(f"/api/arena/runner/jobs/{job['id']}", json={"moves": bad}, headers=RUNNER)
    assert r.status_code == 422
    assert (await client.post(f"/api/arena/runner/jobs/{job['id']}", json={"moves": []},
                              headers=RUNNER)).status_code == 404
    # Partie inachevée sans faute déclarée : refusée.
    job = await claim(client)
    r = await client.post(f"/api/arena/runner/jobs/{job['id']}", json={"moves": wire(job, plies=4)}, headers=RUNNER)
    assert r.status_code == 422
    # Faute du camp au trait : il perd.
    job = await claim(client)
    moves = wire(job, plies=4)  # 4 demi-coups : rouge au trait
    r = await client.post(f"/api/arena/runner/jobs/{job['id']}", json={
        "moves": moves, "fault": {"side": 1, "kind": "fuel", "detail": "fuel épuisé"}}, headers=RUNNER)
    assert r.status_code == 200, r.text
    view = (await client.get(f"/api/arena/bots/{bot_id}", headers=KEY)).json()
    g = view["recent"][0]
    assert (g["reason"], g["ply"]) == ("timeout", 4)
    assert g["result"] == ("loss" if g["side"] == 1 else "win")


async def test_retire(client):
    h = await registered(client)
    bot_id = await active_bot(client, h)
    other = await registered(client, "autre@example.com")
    assert (await client.post(f"/api/arena/bots/{bot_id}/retire", json={}, headers=other)).status_code == 404
    r = await client.post(f"/api/arena/bots/{bot_id}/retire", json={}, headers=h)
    assert r.json()["status"] == "retired"
    async with store.engine.connect() as conn:
        assert (await conn.execute(select(func.count()).select_from(db.arena_jobs))).scalar() == 0


async def test_oversized_bodies_are_refused_before_reading(client):
    h = await registered(client)
    big = "A" * (3 * 1024 * 1024)
    r = await client.post("/api/arena/bots", json={"name": "Gros", "wasm": big}, headers=h)
    assert r.status_code == 413
    # Sans longueur annoncée (envoi par morceaux) : compté au fil de l'eau.
    async def chunks():
        for _ in range(40):
            yield b"x" * 65536
    r = await client.post("/api/arena/runner/jobs/x", content=chunks(), headers=RUNNER)
    assert r.status_code == 413


def test_a_player_s_bots_can_meet():
    ratings = {"a1": 1500, "a2": 1500, "b1": 2400}  # a1 et a2 (même auteur) sont voisins
    pairs = [{job["red_id"], job["blue_id"]} for _ in range(50) for job in arena.plan_batch(["a1", "a2", "b1"], ratings, {})]
    assert {"a1", "a2"} in pairs


def test_division_waits_for_placement():
    assert arena.division(None, 0) is None
    assert arena.division(1700, 4)["placement"] == {"played": 4, "total": arena.PROVISIONAL_GAMES}
    assert arena.division(1700, 10)["label"] == "Jade II"


async def test_round_robin_between_players_bots_only(client):
    h = await registered(client)
    bots = [await active_bot(client, h, name) for name in ("Alpha", "Bravo")]
    bots.append(await active_bot(client, await registered(client, "autre@example.com"), "Charlie"))
    async with store.engine.begin() as conn:
        await conn.execute(db.arena_jobs.delete())  # placements : hors sujet ici
    assert await arena.round_robin(4) == (3, 12)  # 3 duels × 4 parties
    async with store.engine.connect() as conn:
        rows = (await conn.execute(select(db.arena_jobs.c.red_id, db.arena_jobs.c.blue_id, db.arena_jobs.c.terrain,
                                          db.arena_jobs.c.seed).order_by(db.arena_jobs.c.created_at))).all()
    assert all(r.red_id in bots and r.blue_id in bots for r in rows)  # aucun bot maison
    for i, x in enumerate(bots):
        for y in bots[i + 1:]:
            duel = [r for r in rows if {r.red_id, r.blue_id} == {x, y}]
            assert len(duel) == 4 and sum(r.red_id == x for r in duel) == 2  # couleurs équilibrées
    # Ronde par ronde : chaque duel a sa première paire avant qu'un duel joue sa deuxième.
    assert len({frozenset((r.red_id, r.blue_id)) for r in rows[:6]}) == 3
