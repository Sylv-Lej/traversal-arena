import asyncio
import contextlib

from conftest import KEY, new_player

from app.services import games as svc


async def test_api_key_required(client):
    r = await client.post("/api/players", json={})
    assert r.status_code == 401


async def test_unknown_session_is_401_session(client):
    r = await client.get("/api/me", headers={**KEY, "x-session": "nope"})
    assert r.status_code == 401 and r.json()["detail"] == "session"


async def test_guest_and_rename(client):
    h = await new_player(client)
    me = (await client.get("/api/me", headers=h)).json()
    assert me["name"]
    r = await client.patch("/api/me", json={"name": "Alpiniste"}, headers=h)
    assert r.json()["name"] == "Alpiniste"
    assert (await client.patch("/api/me", json={"name": "x"}, headers=h)).status_code == 422


async def test_local_game_full_flow(client):
    h = await new_player(client)
    g = (await client.post("/api/games", json={"mode": "local"}, headers=h)).json()
    assert g["you"] == [1, 2] and g["status"] == "active" and g["legalMoves"]
    for _ in range(6):
        m = g["legalMoves"][0]
        r = await client.post(
            f"/api/games/{g['id']}/moves",
            json={"pieceId": m["pieceId"], "kind": m["kind"], "to": m["to"], "version": g["version"]},
            headers=h,
        )
        assert r.status_code == 200, r.text
        g = r.json()
    assert len(g["moves"]) == 6
    # Version périmée -> 409.
    m = g["legalMoves"][0]
    r = await client.post(
        f"/api/games/{g['id']}/moves",
        json={"pieceId": m["pieceId"], "kind": m["kind"], "to": m["to"], "version": 1},
        headers=h,
    )
    assert r.status_code == 409
    hist = (await client.get(f"/api/games/{g['id']}/history", headers=KEY)).json()
    assert len(hist["positions"]) == 7


async def test_illegal_move_rejected(client):
    h = await new_player(client)
    g = (await client.post("/api/games", json={"mode": "local"}, headers=h)).json()
    r = await client.post(
        f"/api/games/{g['id']}/moves", json={"pieceId": "rs1", "kind": "move", "to": 99}, headers=h
    )
    assert r.status_code == 422


async def test_bot_replies(client, monkeypatch):
    monkeypatch.setattr(svc, "BOT_DELAY_S", 0)
    h = await new_player(client)
    g = (await client.post("/api/games", json={"mode": "bot", "botLevel": 2, "side": 1},
                           headers=h)).json()
    assert g["you"] == [1] and g["players"][1]["isBot"]
    m = g["legalMoves"][0]
    await client.post(f"/api/games/{g['id']}/moves",
                      json={"pieceId": m["pieceId"], "kind": m["kind"], "to": m["to"]}, headers=h)
    for _ in range(50):
        await asyncio.sleep(0.05)
        g = (await client.get(f"/api/games/{g['id']}", headers=h)).json()
        if len(g["moves"]) == 2:
            break
    assert len(g["moves"]) == 2 and g["position"]["toMove"] == 1 and g["legalMoves"]


async def _play_vs_bot(client, h, level: int, plies: int) -> dict:
    """Partie avec pendule contre un bot : on joue jusqu'à `plies` demi-coups, puis on abandonne."""
    g = (await client.post("/api/games", json={"mode": "bot", "botLevel": level, "side": 1, "type": "classic"},
                           headers=h)).json()
    for _ in range(400):
        if len(g["moves"]) >= plies:
            break
        if g["position"]["toMove"] == 1 and g["legalMoves"]:
            m = next(m for m in g["legalMoves"] if m["kind"] != "exit")
            g = (await client.post(f"/api/games/{g['id']}/moves",
                                   json={"pieceId": m["pieceId"], "kind": m["kind"], "to": m["to"]}, headers=h)).json()
        else:
            await asyncio.sleep(0.02)
            g = (await client.get(f"/api/games/{g['id']}", headers=h)).json()
    return (await client.post(f"/api/games/{g['id']}/resign", headers=h)).json()


async def _bot_rating(client, level: int) -> dict:
    return next(b for b in (await client.get("/api/lobby", headers=KEY)).json()["bots"] if b["level"] == level)


async def test_bot_rating_moves_with_its_results_against_players(client, monkeypatch):
    from app.services import gametypes

    monkeypatch.setattr(svc, "BOT_DELAY_S", 0)
    monkeypatch.setattr(gametypes, "BOT_DAILY_CAP", 2)
    start = await _bot_rating(client, 1)
    assert start["rating"] == 920 and start["games"] == 0 and start["rank"]["tier"] == "slate"
    h = await new_player(client)
    g = await _play_vs_bot(client, h, 1, plies=2)  # trop court : ne compte pas
    assert g["result"]["winner"] == 2 and not g["rated"]
    assert (await _bot_rating(client, 1))["games"] == 0
    await _play_vs_bot(client, h, 1, plies=6)  # le bot gagne (abandon) : il monte
    won = await _bot_rating(client, 1)
    assert won["games"] == 1 and won["rating"] > 920
    g = (await client.get(f"/api/games/{g['id']}", headers=h)).json()
    assert g["players"][1]["rating"] == won["rating"] and g["players"][1]["rank"]
    me = (await client.get("/api/me", headers=h)).json()
    assert not any(r["games"] for r in me["ratings"].values())  # le joueur, lui, reste non classé
    await _play_vs_bot(client, h, 1, plies=6)
    await _play_vs_bot(client, h, 1, plies=6)  # au-delà de 2 parties par 24 h : plus compté
    assert (await _bot_rating(client, 1))["games"] == 2


async def test_online_invite_resign_updates_ratings(client):
    a, b = await new_player(client, "Alice"), await new_player(client, "Bruno")
    g = (await client.post("/api/games", json={"mode": "online", "type": "classic", "side": 1},
                           headers=a)).json()
    assert g["status"] == "waiting" and g["rated"]
    # Bruno n'est pas encore joueur : pas de coups légaux, pas de jeu.
    assert (await client.get(f"/api/games/{g['id']}", headers=b)).json()["you"] == []
    g = (await client.post(f"/api/games/{g['id']}/join", headers=b)).json()
    assert g["status"] == "active" and g["you"] == [2] and g["legalMoves"] == []
    # Bruno ne peut pas jouer à la place d'Alice.
    r = await client.post(f"/api/games/{g['id']}/moves",
                          json={"pieceId": "rs1", "kind": "pass"}, headers=b)
    assert r.status_code == 403
    g = (await client.post(f"/api/games/{g['id']}/resign", headers=b)).json()
    assert g["result"] == {"winner": 1, "reason": "resign"}
    assert g["ratingChange"][0] > 0 > g["ratingChange"][1]
    lb = (await client.get("/api/leaderboard?timeClass=classic", headers=KEY)).json()
    assert [row["name"] for row in lb] == ["Alice", "Bruno"]


async def test_draw_by_agreement(client):
    a, b = await new_player(client), await new_player(client)
    g = (await client.post("/api/games", json={"mode": "online", "side": 1}, headers=a)).json()
    await client.post(f"/api/games/{g['id']}/join", headers=b)
    g = (await client.post(f"/api/games/{g['id']}/draw", json={"action": "offer"}, headers=a)).json()
    assert g["drawOffer"] == 1
    g = (await client.post(f"/api/games/{g['id']}/draw", json={"action": "accept"}, headers=b)).json()
    assert g["result"] == {"winner": None, "reason": "agreement"}


async def test_matchmaking_pairs_two_seekers(client):
    a, b = await new_player(client), await new_player(client)
    r = (await client.post("/api/lobby/seek", json={"type": "classic"}, headers=a)).json()
    assert r["status"] == "searching"
    r = (await client.post("/api/lobby/seek", json={"type": "classic"}, headers=b)).json()
    assert r["status"] == "matched"
    ra = (await client.get("/api/lobby/seek", headers=a)).json()
    assert ra == r
    g = (await client.get(f"/api/games/{r['gameId']}", headers=a)).json()
    assert g["status"] == "active" and sorted(g["you"] + (await client.get(
        f"/api/games/{r['gameId']}", headers=b)).json()["you"]) == [1, 2]


async def test_unrated_seek_uses_chosen_map(client):
    a, b, c = await new_player(client), await new_player(client), await new_player(client)
    seek = lambda h, **kw: client.post("/api/lobby/seek", json={"type": "classic", **kw}, headers=h)
    r = (await seek(a, rated=False, terrain="desert")).json()
    assert r["status"] == "searching" and r["rated"] is False and r["terrain"] == "desert"
    # Un joueur en classé n'est pas apparié avec une recherche non classée…
    assert (await (seek(b))).json()["status"] == "searching"
    # … ni une carte incompatible ; « aléatoire » accepte le choix de l'autre.
    await client.delete("/api/lobby/seek", headers=b)
    assert (await seek(c, rated=False, terrain="valleys")).json()["status"] == "searching"
    await client.delete("/api/lobby/seek", headers=c)
    r = (await seek(b, rated=False, terrain="random")).json()
    assert r["status"] == "matched"
    g = (await client.get(f"/api/games/{r['gameId']}", headers=a)).json()
    assert g["terrain"]["mode"] == "desert" and not g["rated"]


async def test_rated_seek_ignores_map_choice(client):
    a = await new_player(client)
    r = (await client.post("/api/lobby/seek", json={"type": "classic", "terrain": "desert"}, headers=a)).json()
    assert r["rated"] is True and r["terrain"] == "random"
    await client.delete("/api/lobby/seek", headers=a)
    r = (await client.post("/api/lobby/seek", json={"type": "classic", "rated": False, "terrain": "lava"},
                           headers=a))
    assert r.status_code == 422


async def test_rematch_online_needs_both(client):
    a, b = await new_player(client), await new_player(client)
    g = (await client.post("/api/games", json={"mode": "online", "side": 1}, headers=a)).json()
    await client.post(f"/api/games/{g['id']}/join", headers=b)
    await client.post(f"/api/games/{g['id']}/resign", headers=a)
    g1 = (await client.post(f"/api/games/{g['id']}/rematch", headers=a)).json()
    assert g1["id"] == g["id"] and g1["rematchOffer"] == 1
    g2 = (await client.post(f"/api/games/{g['id']}/rematch", headers=b)).json()
    assert g2["id"] != g["id"] and g2["you"] == [1]  # Bruno passe rouge


async def test_sandbox_computes_and_applies_moves(client):
    flat = [1] * 100
    body = {"heights": flat, "pieces": [
        {"id": "rv", "owner": 1, "kind": "vanguard", "sq": 51},
        {"id": "bs", "owner": 2, "kind": "sentinel", "sq": 55},
    ]}
    r = (await client.post("/api/sandbox", json=body, headers=KEY)).json()
    atk = [m for m in r["legalMoves"] if m["kind"] == "attack"]
    assert atk and atk[0]["combat"]["attack"] == 3  # charge de 4 pas : 2 + 1
    r = (await client.post("/api/sandbox", json={**body, "move": {
        "pieceId": "rv", "kind": "attack", "to": 55}}, headers=KEY)).json()
    assert r["lastMove"]["capturedId"] == "bs"
    assert [p["id"] for p in r["position"]["pieces"]] == ["rv"]
    assert r["legalMoves"]  # toujours au même camp
    bad = await client.post("/api/sandbox", json={**body, "move": {
        "pieceId": "rv", "kind": "move", "to": 99}}, headers=KEY)
    assert bad.status_code == 422


async def test_rating_history(client):
    a, b = await new_player(client, "Hist-A"), await new_player(client, "Hist-B")
    me_a = (await client.get("/api/me", headers=a)).json()
    for loser in (b, b, a):
        g = (await client.post("/api/games", json={"mode": "online", "type": "classic", "side": 1},
                               headers=a)).json()
        await client.post(f"/api/games/{g['id']}/join", headers=b)
        await client.post(f"/api/games/{g['id']}/resign", headers=loser)
    h = (await client.get(f"/api/players/{me_a['id']}/history?timeClass=classic", headers=KEY)).json()
    assert [p["result"] for p in h] == ["win", "win", "loss"]
    assert h[0]["before"] == 1500 and h[0]["rating"] > 1500
    assert h[1]["before"] == h[0]["rating"] and h[2]["rating"] < h[2]["before"]
    assert h[0]["opponent"] == "Hist-B"
    assert (await client.get(f"/api/players/{me_a['id']}/history?timeClass=bullet", headers=KEY)).json() == []


async def test_open_streams_are_capped_per_ip(client):
    from fastapi import HTTPException
    from starlette.requests import Request

    from app.services import limits

    req = Request({"type": "http", "headers": [(b"x-client-ip", b"10.9.9.9")], "client": ("1.2.3.4", 1)})
    key = limits.check_stream(req)
    with contextlib.ExitStack() as stack:
        for _ in range(limits.MAX_STREAMS_PER_IP):
            stack.enter_context(limits.stream_slot(key))
        try:
            limits.check_stream(req)
            raise AssertionError("pas de 429")
        except HTTPException as exc:
            assert exc.status_code == 429
    assert limits.check_stream(req) == key  # places rendues à la fermeture des flux
    assert "10.9.9.9" not in limits._streams
