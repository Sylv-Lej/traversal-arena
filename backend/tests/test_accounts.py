"""Comptes : mot de passe oublié, changement de mot de passe, expiration des sessions,
ménage des invités."""

import re
import time

from conftest import KEY
from sqlalchemy import update

from app import db
from app.services import accounts, mailer
from app.services import store as store_mod
from app.services.store import hash_token, store

PW = "motdepasse-solide"


async def sql(stmt) -> None:
    async with store.engine.begin() as conn:
        await conn.execute(stmt)


async def registered(client, email):
    r = await client.post("/api/players", json={}, headers=KEY)
    h = {**KEY, "x-session": r.json()["token"]}
    r = await client.post("/api/auth/signup", json={"email": email, "password": PW, "country": "FR"}, headers=h)
    assert r.status_code == 200, r.text
    await accounts.flush_mails()  # l'email de confirmation est parti avant la suite du test
    return h


def token_from_mail() -> str:
    assert mailer.outbox, "aucun email"
    m = re.search(r"/reset\?token=([\w-]+)", mailer.outbox[-1]["text"])
    assert m
    return m.group(1)


async def test_forgot_and_reset_flow(client):
    h = await registered(client, "reset@example.com")
    h_other = {**KEY, "x-session": (await client.post("/api/auth/login", json={
        "email": "reset@example.com", "password": PW}, headers=KEY)).json()["token"]}

    r = await client.post("/api/auth/forgot", json={"email": "RESET@example.com"}, headers=KEY)

    await accounts.flush_mails()  # l'email part en arrière-plan
    assert r.json() == {"ok": True} and mailer.outbox[-1]["to"] == "reset@example.com"
    assert mailer.outbox[-1]["text"].count("http://localhost:3000/reset?token=") == 1
    token = token_from_mail()

    assert (await client.post("/api/auth/reset", json={"token": token, "password": "court"},
                              headers=KEY)).status_code == 422
    r = await client.post("/api/auth/reset", json={"token": token, "password": "nouveau-mdp-123"}, headers=KEY)
    assert r.status_code == 200 and r.json()["token"]
    new = {**KEY, "x-session": r.json()["token"]}
    assert (await client.get("/api/me", headers=new)).json()["email"] == "reset@example.com"
    # Tous les anciens appareils sont déconnectés.
    assert (await client.get("/api/me", headers=h)).status_code == 401
    assert (await client.get("/api/me", headers=h_other)).status_code == 401
    # Lien à usage unique ; ancien mot de passe refusé, nouveau accepté.
    assert (await client.post("/api/auth/reset", json={"token": token, "password": "encore-un-autre"},
                              headers=KEY)).status_code == 400
    assert (await client.post("/api/auth/login", json={"email": "reset@example.com", "password": PW},
                              headers=KEY)).status_code == 401
    assert (await client.post("/api/auth/login", json={"email": "reset@example.com",
                              "password": "nouveau-mdp-123"}, headers=KEY)).status_code == 200


async def test_forgot_never_reveals_accounts(client):
    for email in ("inconnu@example.com", "pas-un-email"):
        r = await client.post("/api/auth/forgot", json={"email": email}, headers=KEY)
        await accounts.flush_mails()  # l'email part en arrière-plan
        assert r.status_code == 200 and r.json() == {"ok": True}
    assert mailer.outbox == []


async def test_forgot_is_throttled_and_link_expires(client):
    await registered(client, "lent@example.com")
    await accounts.flush_mails()
    mailer.outbox.clear()  # l'email de confirmation de l'inscription
    await client.post("/api/auth/forgot", json={"email": "lent@example.com"}, headers=KEY)
    await accounts.flush_mails()  # l'email part en arrière-plan
    await client.post("/api/auth/forgot", json={"email": "lent@example.com"}, headers=KEY)
    assert len(mailer.outbox) == 1  # un seul email par minute et par adresse
    token = token_from_mail()
    await sql(update(db.password_resets).values(expires_at=time.time() - 1))  # lien périmé
    r = await client.post("/api/auth/reset", json={"token": token, "password": "nouveau-mdp-123"}, headers=KEY)
    assert r.status_code == 400


async def test_change_password_keeps_current_session_only(client):
    h = await registered(client, "change@example.com")
    other = {**KEY, "x-session": (await client.post("/api/auth/login", json={
        "email": "change@example.com", "password": PW}, headers=KEY)).json()["token"]}
    bad = await client.post("/api/auth/password", json={"current": "faux-faux-faux", "new": "nouveau-mdp-123"},
                            headers=h)
    assert bad.status_code == 401
    ok = await client.post("/api/auth/password", json={"current": PW, "new": "nouveau-mdp-123"}, headers=h)
    assert ok.status_code == 200
    assert (await client.get("/api/me", headers=h)).status_code == 200
    assert (await client.get("/api/me", headers=other)).status_code == 401


async def test_sessions_expire_after_inactivity(client):
    r = await client.post("/api/players", json={}, headers=KEY)
    token = r.json()["token"]
    h = {**KEY, "x-session": token}
    assert (await client.get("/api/me", headers=h)).status_code == 200
    await sql(update(db.sessions).where(db.sessions.c.token_hash == hash_token(token))
              .values(last_used=time.time() - store_mod.SESSION_TTL_S - 1))
    store.sessions.clear()  # comme une autre instance, qui relit la base
    r = await client.get("/api/me", headers=h)
    assert r.status_code == 401 and r.json()["detail"] == "session"  # le relais recrée un invité


async def test_maintenance_removes_idle_guests_without_games(client):
    idle = (await client.post("/api/players", json={"name": "Fantome"}, headers=KEY)).json()
    player_h = {**KEY, "x-session": (await client.post("/api/players", json={"name": "Joueur"},
                                                       headers=KEY)).json()["token"]}
    await client.post("/api/games", json={"mode": "local"}, headers=player_h)
    me = (await client.get("/api/me", headers=player_h)).json()
    old = time.time() - store_mod.GUEST_TTL_S - 10
    await store.flush()
    await sql(update(db.players).where(db.players.c.id.in_([idle["player"]["id"], me["id"]]))
              .values(last_seen=old))
    stats = await store.maintenance()
    assert stats["guests"] >= 1
    assert await store.get_player(idle["player"]["id"]) is None  # invité inactif, sans partie
    assert await store.get_player(me["id"]) is not None  # a joué : on garde


async def test_login_locked_per_address_after_failures(client):
    await registered(client, "cible@example.com")
    for ip in range(5):  # 5 échecs depuis 5 IP différentes : la limite par IP ne voit rien
        r = await client.post("/api/auth/login", json={"email": "cible@example.com", "password": "faux-faux-faux"},
                              headers={**KEY, "x-client-ip": f"10.0.0.{ip}"})
        assert r.status_code == 401
    # Même le bon mot de passe est refusé pendant le blocage…
    r = await client.post("/api/auth/login", json={"email": "cible@example.com", "password": PW},
                          headers={**KEY, "x-client-ip": "10.0.0.99"})
    assert r.status_code == 429
    # … et une adresse sans compte se bloque pareil : le blocage ne révèle rien.
    for _ in range(5):
        await client.post("/api/auth/login", json={"email": "personne@example.com", "password": "faux-faux-faux"},
                          headers={**KEY, "x-client-ip": "10.0.1.1"})
    r = await client.post("/api/auth/login", json={"email": "personne@example.com", "password": "faux-faux-faux"},
                          headers={**KEY, "x-client-ip": "10.0.1.2"})
    assert r.status_code == 429


async def test_success_resets_failures(client):
    await registered(client, "distrait@example.com")
    for _ in range(4):
        await client.post("/api/auth/login", json={"email": "distrait@example.com", "password": "faux-faux-faux"},
                          headers=KEY)
    ok = await client.post("/api/auth/login", json={"email": "distrait@example.com", "password": PW}, headers=KEY)
    assert ok.status_code == 200
    for _ in range(4):
        await client.post("/api/auth/login", json={"email": "distrait@example.com", "password": "faux-faux-faux"},
                          headers={**KEY, "x-client-ip": "10.0.2.1"})
    ok = await client.post("/api/auth/login", json={"email": "distrait@example.com", "password": PW},
                           headers={**KEY, "x-client-ip": "10.0.2.2"})
    assert ok.status_code == 200


async def test_auth_limit_is_shared_in_database(client, monkeypatch):
    from app.services import limits

    monkeypatch.setattr(limits, "_window", lambda window_s: 0.0)  # pas de changement de minute en plein test
    h = {**KEY, "x-client-ip": "10.0.3.1"}
    codes = [(await client.post("/api/auth/forgot", json={"email": f"x{i}@example.com"}, headers=h)).status_code
             for i in range(11)]
    assert codes[:10] == [200] * 10 and codes[10] == 429
    # Le compteur vit en base : une autre instance (caches vides) le voit aussi.
    store.clear_caches()
    assert await limits.count("auth:10.0.3.1", 60) == 11
    await accounts.flush_mails()


async def test_signup_requires_a_country_shown_everywhere(client):
    r = await client.post("/api/players", json={"name": "Drapeau"}, headers=KEY)
    h = {**KEY, "x-session": r.json()["token"]}
    pid = r.json()["player"]["id"]
    bad = await client.post("/api/auth/signup", json={"email": "pays@example.com", "password": PW}, headers=h)
    assert bad.status_code == 422 and bad.json()["detail"] == "Choisis le pays que tu représentes."
    bad = await client.post("/api/auth/signup", json={"email": "pays@example.com", "password": PW, "country": "ZZ"},
                            headers=h)
    assert bad.status_code == 422
    ok = await client.post("/api/auth/signup", json={"email": "pays@example.com", "password": PW, "country": "be"},
                           headers=h)
    assert ok.status_code == 200 and ok.json()["country"] == "BE"
    # Changement dans les réglages ; pays inconnu refusé.
    assert (await client.patch("/api/me", json={"country": "ca"}, headers=h)).json()["country"] == "CA"
    assert (await client.patch("/api/me", json={"country": "XX"}, headers=h)).status_code == 422
    assert (await client.patch("/api/me", json={"name": "Drapeau2"}, headers=h)).json()["country"] == "CA"
    # Vu par les autres : partie, profil public (relu en base, comme une autre instance).
    g = (await client.post("/api/games", json={"mode": "online", "side": 1}, headers=h)).json()
    assert g["players"][0]["country"] == "CA"
    store.clear_caches()
    assert (await client.get(f"/api/players/{pid}", headers=KEY)).json()["country"] == "CA"


def verify_link() -> str:
    assert mailer.outbox, "aucun email"
    m = re.search(r"/verify\?token=([\w-]+)", mailer.outbox[-1]["text"])
    assert m
    return m.group(1)


async def test_email_confirmation_flow(client):
    h = await registered(client, "confirme@example.com")
    await accounts.flush_mails()
    assert mailer.outbox[-1]["to"] == "confirme@example.com"
    assert (await client.get("/api/me", headers=h)).json()["emailVerified"] is False
    token = verify_link()
    # Lien faux ou déjà utilisé : refusé.
    assert (await client.post("/api/auth/verify", json={"token": "faux"}, headers=KEY)).status_code == 400
    r = await client.post("/api/auth/verify", json={"token": token}, headers=KEY)  # sans session : autre appareil
    assert r.status_code == 200, r.text
    assert (await client.get("/api/me", headers=h)).json()["emailVerified"] is True
    assert (await client.post("/api/auth/verify", json={"token": token}, headers=KEY)).status_code == 400
    # Déjà confirmée : pas de renvoi.
    assert (await client.post("/api/auth/resend", json={}, headers=h)).status_code == 409


async def test_resend_confirmation_is_rate_limited_and_replaces_the_link(client):
    h = await registered(client, "renvoi@example.com")
    await accounts.flush_mails()
    first = verify_link()
    from app.services import limits
    await limits.forget("verifymail:" + (await client.get("/api/me", headers=h)).json()["id"])
    assert (await client.post("/api/auth/resend", json={}, headers=h)).status_code == 200
    await accounts.flush_mails()
    second = verify_link()
    assert second != first
    assert (await client.post("/api/auth/resend", json={}, headers=h)).status_code == 429
    # Le nouveau lien remplace l'ancien.
    assert (await client.post("/api/auth/verify", json={"token": first}, headers=KEY)).status_code == 400
    assert (await client.post("/api/auth/verify", json={"token": second}, headers=KEY)).status_code == 200
    # Un invité n'a rien à confirmer.
    guest = {**KEY, "x-session": (await client.post("/api/players", json={}, headers=KEY)).json()["token"]}
    assert (await client.post("/api/auth/resend", json={}, headers=guest)).status_code == 409
