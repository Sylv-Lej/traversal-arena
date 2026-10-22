"""Backend sans état : plusieurs instances sur la même base.

- dans le process : échéances balayées par les workers, coups concurrents sérialisés ;
- deux VRAIS serveurs (uvicorn) sur la même base : temps réel, bot et matchmaking
  traversent les instances.
"""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from conftest import KEY, URL, new_player
from sqlalchemy import update

from app import db
from app.services import games as svc
from app.services import workers
from app.services.store import store

BACKEND = Path(__file__).resolve().parents[1]


async def wait_for(fn, timeout=5.0, every=0.05):
    end = time.time() + timeout
    while True:
        value = await fn()
        if value or time.time() > end:
            return value
        await asyncio.sleep(every)


async def test_first_move_timeout_is_swept(client):
    a, b = await new_player(client), await new_player(client)
    g = (await client.post("/api/games", json={"mode": "online", "type": "classic", "side": 1},
                           headers=a)).json()
    await client.post(f"/api/games/{g['id']}/join", headers=b)
    async with store.engine.begin() as conn:  # le délai du premier coup est dépassé
        await conn.execute(update(db.games).where(db.games.c.id == g["id"]).values(deadline_at=time.time() - 1))
    workers.clocks.wake()

    async def aborted():
        v = (await client.get(f"/api/games/{g['id']}", headers=a)).json()
        return v if v["status"] == "aborted" else None

    v = await wait_for(aborted)
    assert v and v["result"] == {"winner": None, "reason": "abandon"}


async def test_clock_runs_out_without_any_request(client, monkeypatch):
    a, b = await new_player(client), await new_player(client)
    g = (await client.post("/api/games", json={"mode": "online", "type": "bullet", "side": 1},
                           headers=a)).json()
    await client.post(f"/api/games/{g['id']}/join", headers=b)
    for h in (a, b):  # un coup chacun : la pendule démarre
        v = (await client.get(f"/api/games/{g['id']}", headers=h)).json()
        m = v["legalMoves"][0]
        await client.post(f"/api/games/{g['id']}/moves",
                          json={"pieceId": m["pieceId"], "kind": m["kind"], "to": m["to"]}, headers=h)
    async with store.locked_game(g["id"]) as game:  # il ne reste que 0,3 s à Rouge
        game.remaining[0] = 300
        game.version += 1
        svc._start_turn(game)

    async def finished():
        v = (await client.get(f"/api/games/{g['id']}", headers=a)).json()
        return v if v["status"] == "finished" else None

    v = await wait_for(finished, timeout=3)
    assert v and v["result"] == {"winner": 2, "reason": "timeout"} and v["clock"]["remaining"][0] == 0
    assert v["ratingChange"][1] > 0


async def test_concurrent_moves_are_serialized(client):
    h = await new_player(client)
    g = (await client.post("/api/games", json={"mode": "local"}, headers=h)).json()
    moves = g["legalMoves"][:2]
    rs = await asyncio.gather(*[
        client.post(f"/api/games/{g['id']}/moves",
                    json={"pieceId": m["pieceId"], "kind": m["kind"], "to": m["to"], "version": g["version"]},
                    headers=h)
        for m in moves
    ])
    assert sorted(r.status_code for r in rs) == [200, 409]
    v = (await client.get(f"/api/games/{g['id']}", headers=h)).json()
    assert len(v["moves"]) == 1


# --- Deux vrais serveurs ---------------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest_asyncio.fixture(scope="module")
async def instances(backend):
    procs, urls = [], []
    env = {**os.environ, "DATABASE_URL": URL, "API_KEY": "test-key"}
    for _ in range(2):
        port = _free_port()
        procs.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--log-level", "warning"],
            cwd=BACKEND, env=env,
        ))
        urls.append(f"http://127.0.0.1:{port}")
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            for u in urls:
                for _ in range(200):
                    try:
                        if (await c.get(f"{u}/healthz")).status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    await asyncio.sleep(0.1)
                else:
                    pytest.fail(f"instance {u} n'a pas démarré")
        yield urls
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            p.wait(10)


async def _player(c: httpx.AsyncClient, url: str) -> dict:
    r = await c.post(f"{url}/api/players", json={}, headers=KEY)
    return {**KEY, "x-session": r.json()["token"]}


async def test_realtime_bot_and_matchmaking_across_instances(instances):
    a_url, b_url = instances
    async with httpx.AsyncClient(timeout=10) as c:
        alice = await _player(c, a_url)
        bruno = await _player(c, b_url)  # session créée sur B, utilisable sur A et inversement

        # Partie créée sur A, rejointe sur B.
        g = (await c.post(f"{a_url}/api/games", json={"mode": "online", "side": 1}, headers=alice)).json()
        g = (await c.post(f"{b_url}/api/games/{g['id']}/join", headers=bruno)).json()
        assert g["status"] == "active" and g["you"] == [2]

        # Flux SSE ouvert sur A ; Alice joue sur B : A doit le pousser.
        received: list[dict] = []

        async def listen():
            async with c.stream("GET", f"{a_url}/api/games/{g['id']}/stream", headers=bruno) as r:
                event = None
                async for line in r.aiter_lines():
                    if line.startswith("event:"):
                        event = line.split(":", 1)[1].strip()
                    elif line.startswith("data:") and event == "state":
                        received.append(json.loads(line[5:]))
                        if len(received) == 2:
                            return

        task = asyncio.create_task(listen())
        await wait_for(lambda: _true(received), timeout=5)
        m = (await c.get(f"{b_url}/api/games/{g['id']}", headers=alice)).json()["legalMoves"][0]
        t0 = time.time()
        r = await c.post(f"{b_url}/api/games/{g['id']}/moves",
                         json={"pieceId": m["pieceId"], "kind": m["kind"], "to": m["to"]}, headers=alice)
        assert r.status_code == 200
        await asyncio.wait_for(task, timeout=5)
        assert received[-1]["version"] == r.json()["version"] and len(received[-1]["moves"]) == 1
        assert received[-1]["legalMoves"], "vue calculée pour Bruno, à qui c'est le tour"
        assert time.time() - t0 < 2

        # Bot : partie créée sur A ; une des instances joue pour lui.
        bg = (await c.post(f"{a_url}/api/games", json={"mode": "bot", "botLevel": 1, "side": 2},
                           headers=alice)).json()

        async def bot_played():
            v = (await c.get(f"{b_url}/api/games/{bg['id']}", headers=alice)).json()
            return v if v["moves"] else None

        v = await wait_for(bot_played, timeout=5)
        assert v and len(v["moves"]) == 1 and v["legalMoves"]

        # Matchmaking : Alice cherche sur A, Bruno sur B.
        r = (await c.post(f"{a_url}/api/lobby/seek", json={"type": "classic"}, headers=alice)).json()
        assert r["status"] == "searching"
        lobby = (await c.get(f"{b_url}/api/lobby", headers=KEY)).json()
        assert lobby["seeking"]["classic"] == 1
        r = (await c.post(f"{b_url}/api/lobby/seek", json={"type": "classic"}, headers=bruno)).json()
        assert r["status"] == "matched"
        ra = (await c.get(f"{a_url}/api/lobby/seek", headers=alice)).json()
        assert ra == r


async def _true(lst):
    return bool(lst)


async def test_spectators_counted_across_instances(instances):
    a_url, b_url = instances
    async with httpx.AsyncClient(timeout=10) as c:
        alice, bruno, carla = await _player(c, a_url), await _player(c, b_url), await _player(c, a_url)
        g = (await c.post(f"{a_url}/api/games", json={"mode": "online", "side": 1}, headers=alice)).json()
        await c.post(f"{b_url}/api/games/{g['id']}/join", headers=bruno)
        got: list[str] = []

        async def watch():  # Carla regarde depuis l'instance A
            async with c.stream("GET", f"{a_url}/api/games/{g['id']}/stream", headers=carla) as r:
                async for line in r.aiter_lines():
                    got.append(line)

        task = asyncio.create_task(watch())

        async def counted():  # Alice le voit depuis l'instance B
            v = (await c.get(f"{b_url}/api/games/{g['id']}", headers=alice)).json()
            return v["spectators"] == 1

        assert await wait_for(counted, timeout=6)
        task.cancel()

        async def gone():
            v = (await c.get(f"{b_url}/api/games/{g['id']}", headers=alice)).json()
            return v["spectators"] == 0

        assert await wait_for(gone, timeout=6)
        assert any(line.startswith("event: spectators") for line in got)  # poussé au spectateur aussi
