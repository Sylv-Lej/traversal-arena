"""Matchs tactiques : bans / choix de carte, manches, décisive, classement."""

import asyncio
import time

from conftest import KEY, new_player
from sqlalchemy import update

from app import db
from app.services import matches, workers
from app.services.store import store


async def wait_for(fn, timeout=5.0, every=0.05):
    end = time.time() + timeout
    while True:
        value = await fn()
        if value or time.time() > end:
            return value
        await asyncio.sleep(every)


async def veto(client, h, mid, choice):
    r = await client.post(f"/api/matches/{mid}/veto", json={"map": choice}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


async def test_local_match_full_flow_with_decider(client):
    h = await new_player(client)
    m = (await client.post("/api/matches", json={"mode": "local"}, headers=h)).json()
    assert m["status"] == "veto" and m["you"] == [1, 2] and m["step"] == {"action": "ban", "by": 1}
    assert m["available"] == list(matches.MAPS)
    m = await veto(client, h, m["id"], "desert")  # joueur 1 bannit
    assert m["step"] == {"action": "ban", "by": 2} and "desert" not in m["available"]
    m = await veto(client, h, m["id"], "woodlands")  # joueur 2 bannit
    m = await veto(client, h, m["id"], "valleys")  # joueur 1 choisit
    assert m["status"] == "playing" and m["currentGameId"]
    g = (await client.get(f"/api/games/{m['currentGameId']}", headers=h)).json()
    assert g["terrain"]["mode"] == "valleys" and g["timeControl"] == "2+0" and g["timeClass"] == "tactic"
    assert g["match"]["round"] == 1 and not g["rated"]
    # Manche 1 : Rouge (joueur 1) abandonne -> le joueur 2 mène.
    await client.post(f"/api/games/{g['id']}/resign", headers=h)
    m = (await client.get(f"/api/matches/{m['id']}", headers=h)).json()
    assert m["score"] == [0, 1] and m["status"] == "veto" and m["round"] == 2
    assert m["step"] == {"action": "ban", "by": 2}  # en manche 2, le joueur 2 ouvre et choisit
    assert "valleys" not in m["available"]  # carte déjà jouée
    for choice in ("mountains", "highlands"):
        m = await veto(client, h, m["id"], choice)
    bad = await client.post(f"/api/matches/{m['id']}/veto", json={"map": "valleys"}, headers=h)
    assert bad.status_code == 422
    m = await veto(client, h, m["id"], "desert")  # banni à la manche 1, libre à la 2
    g2 = (await client.get(f"/api/games/{m['currentGameId']}", headers=h)).json()
    assert g2["terrain"]["mode"] == "desert" and g2["match"]["round"] == 2
    # Manche 2 : Rouge (joueur 2 cette fois) abandonne -> 1-1 -> manche décisive en bullet.
    await client.post(f"/api/games/{g2['id']}/resign", headers=h)
    m = (await client.get(f"/api/matches/{m['id']}", headers=h)).json()
    assert m["score"] == [1, 1] and m["round"] == 3 and m["status"] == "playing"
    g3 = (await client.get(f"/api/games/{m['currentGameId']}", headers=h)).json()
    assert g3["timeControl"] == "1+1" and g3["terrain"]["mode"] not in ("valleys", "desert")
    await client.post(f"/api/games/{g3['id']}/draw", json={"action": "offer"}, headers=h)  # nulle (local)
    m = (await client.get(f"/api/matches/{m['id']}", headers=h)).json()
    assert m["status"] == "finished" and m["winner"] is None and m["score"] == [1.5, 1.5]
    assert m["ratingChange"] is None  # local : jamais classé


async def test_online_match_turns_and_rating(client):
    a, b, c = await new_player(client, "Alpha"), await new_player(client, "Bravo"), await new_player(client)
    m = (await client.post("/api/matches", json={"mode": "online", "side": 1}, headers=a)).json()
    assert m["status"] == "waiting"
    m = (await client.post(f"/api/matches/{m['id']}/join", headers=b)).json()
    assert m["status"] == "veto" and m["you"] == [2]
    # Chacun son tour ; un spectateur ne choisit rien.
    assert (await client.post(f"/api/matches/{m['id']}/veto", json={"map": "desert"}, headers=b)).status_code == 403
    assert (await client.post(f"/api/matches/{m['id']}/veto", json={"map": "desert"}, headers=c)).status_code == 403
    assert (await client.post(f"/api/matches/{m['id']}/veto", json={"map": "volcan"}, headers=a)).status_code == 422
    await veto(client, a, m["id"], "desert")
    await veto(client, b, m["id"], "woodlands")
    m = await veto(client, a, m["id"], "mountains")
    g = (await client.get(f"/api/games/{m['currentGameId']}", headers=a)).json()
    assert g["you"] == [1] and g["match"]["rated"]
    assert (await client.post(f"/api/games/{g['id']}/rematch", headers=a)).status_code == 409
    await client.post(f"/api/games/{g['id']}/resign", headers=b)  # Alpha gagne la manche 1
    await veto(client, b, m["id"], "valleys")
    await veto(client, a, m["id"], "highlands")
    m = await veto(client, b, m["id"], "woodlands")
    g2 = (await client.get(f"/api/games/{m['currentGameId']}", headers=b)).json()
    assert g2["you"] == [1]  # Bravo joue Rouge en manche 2
    assert (await client.post(f"/api/games/{g2['id']}/abort", headers=b)).status_code == 409
    await client.post(f"/api/games/{g2['id']}/resign", headers=b)  # 2-0 pour Alpha
    m = (await client.get(f"/api/matches/{m['id']}", headers=a)).json()
    assert m["status"] == "finished" and m["winner"] == 1 and m["score"] == [2, 0]
    assert m["ratingChange"][0] > 0 > m["ratingChange"][1]
    assert m["rankChange"][0]["after"]["placement"] == {"played": 1, "total": 5}
    lb = (await client.get("/api/leaderboard?timeClass=tactic", headers=KEY)).json()
    assert [r["name"] for r in lb] == ["Alpha", "Bravo"]
    pid = (await client.get("/api/me", headers=a)).json()["id"]
    hist = (await client.get(f"/api/players/{pid}/history?timeClass=tactic", headers=KEY)).json()
    assert len(hist) == 1 and hist[0]["result"] == "win" and hist[0]["opponent"] == "Bravo"
    # Les manches ne comptent pas en classique.
    assert (await client.get(f"/api/players/{pid}/history?timeClass=classic", headers=KEY)).json() == []


async def test_veto_timeout_picks_at_random(client):
    h = await new_player(client)
    m = (await client.post("/api/matches", json={"mode": "local"}, headers=h)).json()
    async with store.engine.begin() as conn:
        await conn.execute(update(db.matches).where(db.matches.c.id == m["id"]).values(deadline_at=time.time() - 1))
    workers.clocks.wake()

    async def banned():
        v = (await client.get(f"/api/matches/{m['id']}", headers=h)).json()
        return v if v["rounds"][0]["bans"] else None

    v = await wait_for(banned)
    assert v and len(v["rounds"][0]["bans"]) == 1 and v["step"] == {"action": "ban", "by": 2}
    assert v["deadlineMs"] > 15_000  # nouveau délai pour le ban suivant


async def test_bot_vetoes_on_its_own(client):
    h = await new_player(client)
    m = (await client.post("/api/matches", json={"mode": "bot", "botLevel": 1, "side": 2}, headers=h)).json()
    assert m["step"] == {"action": "ban", "by": 1}  # le bot (joueur 1) ouvre

    async def my_turn():
        v = (await client.get(f"/api/matches/{m['id']}", headers=h)).json()
        return v if v["step"] and v["step"]["by"] == 2 else None

    v = await wait_for(my_turn)
    assert v and len(v["rounds"][0]["bans"]) == 1
    v = await veto(client, h, m["id"], v["available"][0])  # mon ban -> le bot choisit

    async def started():
        x = (await client.get(f"/api/matches/{m['id']}", headers=h)).json()
        return x if x["status"] == "playing" else None

    v = await wait_for(started)
    assert v and v["rounds"][0]["pick"] in matches.MAPS


async def test_first_round_abort_cancels_the_match(client):
    a, b = await new_player(client), await new_player(client)
    m = (await client.post("/api/matches", json={"mode": "online", "side": 1}, headers=a)).json()
    await client.post(f"/api/matches/{m['id']}/join", headers=b)
    await veto(client, a, m["id"], "desert")
    await veto(client, b, m["id"], "woodlands")
    m = await veto(client, a, m["id"], "mountains")
    await client.post(f"/api/games/{m['currentGameId']}/abort", headers=a)
    m = (await client.get(f"/api/matches/{m['id']}", headers=a)).json()
    assert m["status"] == "aborted"


async def test_matchmaking_tactic_creates_a_match(client):
    a, b = await new_player(client), await new_player(client)
    r = (await client.post("/api/lobby/seek", json={"type": "tactic"}, headers=a)).json()
    assert r["status"] == "searching"
    r = (await client.post("/api/lobby/seek", json={"type": "tactic"}, headers=b)).json()
    assert r["status"] == "matched" and r["matchId"] and "gameId" not in r
    assert (await client.get("/api/lobby/seek", headers=a)).json() == r
    m = (await client.get(f"/api/matches/{r['matchId']}", headers=a)).json()
    assert m["status"] == "veto" and m["rated"]
    assert (await client.post("/api/games", json={"mode": "online", "type": "tactic"}, headers=a)).status_code == 422
