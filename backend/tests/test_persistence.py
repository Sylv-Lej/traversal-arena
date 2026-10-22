"""Persistance : tout est relu en base après un « redémarrage » (caches vidés), comme le
ferait une autre instance du backend."""

import asyncio

from conftest import KEY, new_player

from app.routes import reset_limiters
from app.services import games as svc
from app.services import workers
from app.services.store import store


def restart() -> None:
    """Simule un redémarrage du backend (ou une autre instance) : caches mémoire vidés."""
    store.clear_caches()
    reset_limiters()


async def play_n(client, h, gid, n):
    g = (await client.get(f"/api/games/{gid}", headers=h)).json()
    for _ in range(n):
        m = g["legalMoves"][0]
        r = await client.post(f"/api/games/{gid}/moves",
                              json={"pieceId": m["pieceId"], "kind": m["kind"], "to": m["to"]},
                              headers=h)
        assert r.status_code == 200, r.text
        g = r.json()
    return g


async def test_game_survives_restart(client):
    h = await new_player(client, "Persistant")
    g = (await client.post("/api/games", json={"mode": "local", "terrain": "valleys"}, headers=h)).json()
    before = await play_n(client, h, g["id"], 9)
    await store.flush()
    restart()

    after = (await client.get(f"/api/games/{g['id']}", headers=h)).json()
    assert after["you"] == [1, 2], "la session et le joueur sont relus en base"
    for key in ("position", "moves", "version", "terrain", "legalMoves", "status"):
        assert after[key] == before[key], key
    # On peut continuer à jouer après la reprise.
    await play_n(client, h, g["id"], 1)
    hist = (await client.get(f"/api/games/{g['id']}/history", headers=KEY)).json()
    assert len(hist["positions"]) == 11


async def test_ratings_leaderboard_and_history_persist(client):
    a, b = await new_player(client, "Alice"), await new_player(client, "Bruno")
    g = (await client.post("/api/games", json={"mode": "online", "type": "classic", "side": 1},
                           headers=a)).json()
    await client.post(f"/api/games/{g['id']}/join", headers=b)
    await client.post(f"/api/games/{g['id']}/resign", headers=b)
    await store.flush()
    restart()

    lb = (await client.get("/api/leaderboard?timeClass=classic", headers=KEY)).json()
    assert [r["name"] for r in lb] == ["Alice", "Bruno"]
    assert lb[0]["rating"] > 1500 > lb[1]["rating"] and lb[0]["games"] == 1
    me = (await client.get("/api/me/games", headers=a)).json()
    assert me[0]["id"] == g["id"] and me[0]["result"] == {"winner": 1, "reason": "resign"}
    view = (await client.get(f"/api/games/{g['id']}", headers=a)).json()
    assert view["result"] == {"winner": 1, "reason": "resign"} and view["ratingChange"][0] > 0
    prof = (await client.get(f"/api/players/{lb[0]['id']}", headers=KEY)).json()
    assert "email" not in prof and prof["games"][0]["id"] == g["id"]
    hist = (await client.get(f"/api/players/{lb[0]['id']}/history?timeClass=classic", headers=KEY)).json()
    assert len(hist) == 1 and hist[0]["result"] == "win" and hist[0]["opponent"] == "Bruno"


async def test_active_bot_game_resumes(client, monkeypatch):
    monkeypatch.setattr(svc, "BOT_DELAY_S", 0)
    h = await new_player(client)
    await workers.stop()  # « serveur éteint » : personne ne joue pour le bot
    try:
        g = (await client.post("/api/games", json={"mode": "bot", "botLevel": 1, "side": 2},
                               headers=h)).json()
        await asyncio.sleep(0.2)
        assert (await client.get(f"/api/games/{g['id']}", headers=h)).json()["moves"] == []
        restart()
    finally:
        workers.start()  # la tâche du bot est en base : n'importe quelle instance la reprend
    for _ in range(60):
        await asyncio.sleep(0.05)
        view = (await client.get(f"/api/games/{g['id']}", headers=h)).json()
        if view["moves"]:
            break
    assert len(view["moves"]) == 1 and view["legalMoves"], "le bot a rejoué après reprise"


async def test_accounts_signup_login_logout(client):
    h = await new_player(client, "Grimpeur")
    r = await client.post("/api/auth/signup", json={"email": "G@Example.com ", "password": "court"},
                          headers=h)
    assert r.status_code == 422
    r = await client.post("/api/auth/signup",
                          json={"email": "G@Example.com", "password": "motdepasse-solide", "country": "FR"}, headers=h)
    assert r.status_code == 200 and r.json()["isGuest"] is False and r.json()["email"] == "g@example.com"
    assert (await client.post("/api/auth/signup", json={"email": "g@example.com",
                              "password": "motdepasse-solide", "country": "FR"}, headers=h)).status_code == 409
    other = await new_player(client)
    r = await client.post("/api/auth/signup", json={"email": "g@example.com",
                          "password": "motdepasse-solide", "country": "FR"}, headers=other)
    assert r.status_code == 409  # email déjà pris

    await store.flush()
    restart()
    bad = await client.post("/api/auth/login", json={"email": "g@example.com", "password": "faux-faux-faux"},
                            headers=KEY)
    assert bad.status_code == 401
    ok = await client.post("/api/auth/login", json={"email": "g@example.com", "password": "motdepasse-solide"},
                           headers=KEY)
    assert ok.status_code == 200
    h2 = {**KEY, "x-session": ok.json()["token"]}
    me = (await client.get("/api/me", headers=h2)).json()
    assert me["name"] == "Grimpeur" and me["isGuest"] is False

    await client.post("/api/auth/logout", headers=h2)
    await store.flush()
    restart()
    assert (await client.get("/api/me", headers=h2)).status_code == 401
    # L'ancienne session (celle de l'inscription) reste valide : déconnexion par appareil.
    assert (await client.get("/api/me", headers=h)).status_code == 200


async def test_password_reset_survives_restart_and_logs_out_everywhere(client):
    import re

    from app.services import accounts, mailer

    h = await new_player(client, "Oublieux")
    await client.post("/api/auth/signup", json={"email": "oubli@example.com", "password": "motdepasse-solide", "country": "FR"},
                      headers=h)
    await client.post("/api/auth/forgot", json={"email": "oubli@example.com"}, headers=KEY)
    await accounts.flush_mails()  # l'email part en arrière-plan
    token = re.search(r"token=([\w-]+)", mailer.outbox[-1]["text"]).group(1)
    await store.flush()
    restart()  # le lien vit en base, pas seulement en mémoire
    r = await client.post("/api/auth/reset", json={"token": token, "password": "tout-nouveau-123"}, headers=KEY)
    assert r.status_code == 200
    await store.flush()
    restart()
    assert (await client.get("/api/me", headers=h)).status_code == 401  # ancienne session supprimée en base
    assert (await client.post("/api/auth/reset", json={"token": token, "password": "encore-autre-1"},
                              headers=KEY)).status_code == 400


async def test_expiry_and_cleanup_in_database(client):
    import time

    from sqlalchemy import update

    from app import db
    from app.services import store as store_mod
    from app.services.store import hash_token

    old = time.time() - store_mod.GUEST_TTL_S - 100
    idle = (await client.post("/api/players", json={"name": "Fantome"}, headers=KEY)).json()
    idle_tok = idle["token"]
    active_tok = (await client.post("/api/players", json={"name": "Actif"}, headers=KEY)).json()["token"]
    ah = {**KEY, "x-session": active_tok}
    await client.post("/api/games", json={"mode": "local"}, headers=ah)
    active_id = (await client.get("/api/me", headers=ah)).json()["id"]
    await store.flush()
    async with store.engine.begin() as conn:
        # Session d'Actif expirée ; Fantome et Actif inactifs depuis plus de 30 jours.
        await conn.execute(update(db.sessions).where(db.sessions.c.token_hash == hash_token(active_tok))
                           .values(last_used=time.time() - store_mod.SESSION_TTL_S - 100))
        await conn.execute(update(db.players).where(db.players.c.id.in_([idle["player"]["id"], active_id]))
                           .values(last_seen=old))
    restart()
    assert (await client.get("/api/me", headers=ah)).status_code == 401  # session expirée (lue en base)
    stats = await store.maintenance()
    assert stats["guests"] == 1  # Fantome supprimé ; Actif gardé car il a une partie
    restart()
    assert (await client.get("/api/me", headers={**KEY, "x-session": idle_tok})).status_code == 401
    assert await store.get_player(active_id) is not None


async def test_analysis_is_persisted(client):
    h = await new_player(client)
    g = (await client.post("/api/games", json={"mode": "local"}, headers=h)).json()
    await play_n(client, h, g["id"], 4)
    await client.post(f"/api/games/{g['id']}/resign", headers=h)
    await client.post(f"/api/games/{g['id']}/analysis", headers=KEY)
    for _ in range(100):
        await asyncio.sleep(0.05)
        st = (await client.get(f"/api/games/{g['id']}/analysis", headers=KEY)).json()
        if st["status"] == "done":
            break
    assert st["status"] == "done"
    await store.flush()
    restart()
    again = (await client.get(f"/api/games/{g['id']}/analysis", headers=KEY)).json()
    assert again["status"] == "done" and again["result"] == st["result"]
