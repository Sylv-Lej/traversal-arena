"""Bilans de partie par l'arène : le n°1 du classement propose, orque note (runner), le
backend vérifie les coups du bot et range le bilan ; repli sur orque seul sinon."""

import time

from conftest import KEY, new_player
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app import db
from app.services import analysis_jobs, imports
from test_imports import DATA, REF

RUNNER = {"x-arena-token": "test-arena"}


async def imported_game(client, monkeypatch) -> tuple[str, dict]:
    async def fake_fetch(ref):
        return DATA

    monkeypatch.setattr(imports, "fetch", fake_fetch)
    me = await new_player(client)
    r = await client.post("/api/imports", json={"url": REF}, headers=me)
    assert r.status_code == 200, r.text
    return r.json()["id"], me


async def top_bot(store) -> None:
    """Mont Blanc en tête du classement de l'arène (placement fini)."""
    async with store.engine.begin() as conn:
        await conn.execute(pg_insert(db.arena_ratings).values(
            player_id="bot5", rating=2000.0, margin=50.0, games=40, wins=30, losses=10, draws=0, updated_at=time.time()))


async def claim_analysis(client) -> dict:
    r = await client.post("/api/arena/runner/claim", json={}, headers=RUNNER)
    job = r.json()["job"]
    assert job["kind"] == "analyse", job
    return job


async def test_the_arena_s_best_bot_reviews_the_game(client, monkeypatch):
    from app.services.store import store

    monkeypatch.setenv("ARENA_ANALYSES", "1")
    await top_bot(store)
    gid, me = await imported_game(client, monkeypatch)
    st = (await client.post(f"/api/games/{gid}/analysis", json={}, headers=me)).json()
    assert st["status"] == "queued" and st["byArena"]

    job = await claim_analysis(client)
    assert job["red"] == {"id": "bot5", "house": 5} and len(job["positions"]) == 17
    # Un coup du bot qui n'existe pas (sortie depuis la rangée de départ) : bilan refusé,
    # et orque seul prend le relais dans le backend.
    bad = [{"bot": pos["played"], "botScore": 30, "playedScore": 30, "depth": 7} for pos in job["positions"]]
    bad[11] = {**bad[11], "bot": [0, "exit", -1]}
    r = await client.post(f"/api/arena/runner/jobs/{job['id']}", json={"positions": bad}, headers=RUNNER)
    assert r.status_code == 422
    st = (await client.get(f"/api/games/{gid}/analysis", headers=me)).json()
    assert st["status"] in ("queued", "running", "done") and not st.get("byArena")


async def test_arena_review_is_stored_with_the_bot_s_name(client, monkeypatch):
    from app.engine import legal_moves
    from app.services.store import store

    monkeypatch.setenv("ARENA_ANALYSES", "1")
    await top_bot(store)
    gid, me = await imported_game(client, monkeypatch)
    await client.post(f"/api/games/{gid}/analysis", json={}, headers=me)
    job = await claim_analysis(client)
    game = await store.get_game(gid)
    positions = []
    for i, pos in enumerate(job["positions"]):
        bot_move, bot_score, played_score = pos["played"], 20, 20
        if i == 11:  # la gaffe : le bot préfère un autre coup, bien meilleur
            s = game.states[i]
            other = next(m for m in legal_moves(s) if m.kind == "move" and m.piece_id != game.moves[i].piece_id)
            idx = next(k for k, p in enumerate(s.pieces) if p.id == other.piece_id)
            bot_move, bot_score, played_score = [idx, "move", other.to], 40, -400
        positions.append({"bot": bot_move, "botScore": bot_score, "playedScore": played_score, "depth": 9})
    r = await client.post(f"/api/arena/runner/jobs/{job['id']}", json={"positions": positions}, headers=RUNNER)
    assert r.status_code == 200, r.text

    st = (await client.get(f"/api/games/{gid}/analysis", headers=me)).json()
    assert st["status"] == "done"
    res = st["result"]
    assert res["engine"] == {"bot": {"id": "bot5", "name": "Mont Blanc", "rating": 2000}, "eval": "orque"}
    assert res["moves"][11]["class"] == "blunder" and res["moves"][11]["best"] is not None
    assert all(m["class"] in ("best", "forced") for k, m in enumerate(res["moves"]) if k != 11)
    assert res["depth"] == 9


async def test_without_the_runner_orque_reviews_in_the_backend(client, monkeypatch):
    monkeypatch.delenv("ARENA_ANALYSES", raising=False)
    gid, me = await imported_game(client, monkeypatch)
    st = (await client.post(f"/api/games/{gid}/analysis", json={}, headers=me)).json()
    assert not st.get("byArena")
    r = await client.post("/api/arena/runner/claim", json={}, headers=RUNNER)
    assert (r.json()["job"] or {}).get("kind") != "analyse"


async def test_unanswered_arena_review_falls_back_to_orque(client, monkeypatch):
    from app.services.store import store

    monkeypatch.setenv("ARENA_ANALYSES", "1")
    await top_bot(store)
    gid, me = await imported_game(client, monkeypatch)
    await client.post(f"/api/games/{gid}/analysis", json={}, headers=me)
    monkeypatch.setattr(analysis_jobs, "ARENA_WAIT_S", -1)
    await analysis_jobs.claim()  # plus d'attente : le backend s'en charge (ce worker ou un autre)
    st = (await client.get(f"/api/games/{gid}/analysis", headers=me)).json()
    assert not st.get("byArena")
