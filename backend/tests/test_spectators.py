"""Spectateurs : diffusion en différé (anti-triche), liste des parties en cours, compteur."""

import asyncio

from conftest import KEY, new_player

from app.services import spectators


async def play(client, h, gid, n=1):
    for _ in range(n):
        v = (await client.get(f"/api/games/{gid}", headers=h)).json()
        m = v["legalMoves"][0]
        r = await client.post(f"/api/games/{gid}/moves", json={"pieceId": m["pieceId"], "kind": m["kind"], "to": m["to"]},
                              headers=h)
        assert r.status_code == 200, r.text


async def online_game(client, a, b, tc="classic"):
    g = (await client.post("/api/games", json={"mode": "online", "type": tc, "side": 1}, headers=a)).json()
    await client.post(f"/api/games/{g['id']}/join", headers=b)
    return g["id"]


async def test_spectators_see_the_game_one_full_turn_late(client):
    a, b, c = await new_player(client), await new_player(client), await new_player(client)
    gid = await online_game(client, a, b)
    for h in (a, b, a):
        await play(client, h, gid)
    player = (await client.get(f"/api/games/{gid}", headers=b)).json()
    watcher = (await client.get(f"/api/games/{gid}", headers=c)).json()
    anonymous = (await client.get(f"/api/games/{gid}", headers=KEY)).json()
    assert len(player["moves"]) == 3 and player["delay"] == 0
    for v in (watcher, anonymous):
        assert len(v["moves"]) == 1 and v["position"]["ply"] == 1 and v["delay"] == 2
        assert v["legalMoves"] == [] and v["you"] == [] and v["clock"]["running"] is None
        assert v["position"] == (await client.get(f"/api/games/{gid}/history", headers=b)).json()["positions"][1]
    # L'historique aussi s'arrête au dernier coup montré.
    assert len((await client.get(f"/api/games/{gid}/history", headers=c)).json()["positions"]) == 2
    assert len((await client.get(f"/api/games/{gid}/history", headers=b)).json()["positions"]) == 4
    # Fin de partie : tout est dévoilé.
    await client.post(f"/api/games/{gid}/resign", headers=b)
    done = (await client.get(f"/api/games/{gid}", headers=c)).json()
    assert len(done["moves"]) == 3 and done["delay"] == 0 and done["result"]["reason"] == "resign"


async def test_no_delay_for_bot_and_local_games(client):
    a, c = await new_player(client), await new_player(client)
    g = (await client.post("/api/games", json={"mode": "local"}, headers=a)).json()
    await play(client, a, g["id"], 3)
    assert len((await client.get(f"/api/games/{g['id']}", headers=c)).json()["moves"]) == 3


async def test_live_games_strongest_first(client):
    a, b, c, d = [await new_player(client, n) for n in ("Alpha", "Bravo", "Charlie", "Delta")]
    weak = await online_game(client, a, b)
    # Charlie et Delta gagnent du classement en classique avant leur partie.
    for _ in range(2):
        g = await online_game(client, c, a)
        await client.post(f"/api/games/{g}/resign", headers=a)
        g = await online_game(client, d, b)
        await client.post(f"/api/games/{g}/resign", headers=b)
    strong = await online_game(client, c, d)
    for h in (c, d, c):
        await play(client, h, strong)
    await client.post("/api/games", json={"mode": "bot", "botLevel": 1}, headers=a)  # pas listée
    live = (await client.get("/api/games/live", headers=KEY)).json()
    assert [g["id"] for g in live] == [strong, weak]
    assert live[0]["ply"] == 1  # retard des spectateurs
    assert {p["name"] for p in live[0]["players"]} == {"Charlie", "Delta"} and live[0]["timeControl"] == "5+0"


async def test_spectator_count_is_shared(client):
    a, b = await new_player(client), await new_player(client)
    gid = await online_game(client, a, b)
    spectators.join(gid)
    spectators.join(gid)
    await asyncio.sleep(spectators.FLUSH_S + 0.5)
    assert (await client.get(f"/api/games/{gid}", headers=a)).json()["spectators"] == 2
    assert (await client.get("/api/games/live", headers=KEY)).json()[0]["spectators"] == 2
    spectators.leave(gid)
    spectators.leave(gid)
    await asyncio.sleep(spectators.FLUSH_S + 0.5)
    assert (await client.get(f"/api/games/{gid}", headers=a)).json()["spectators"] == 0
