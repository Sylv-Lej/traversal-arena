"""Messages de l'API en anglais (`x-lang: en`, posé par le relais du front)."""

import re
from pathlib import Path

from conftest import KEY, new_player

from app.i18n import EN
from app.services import accounts, mailer

APP = Path(__file__).resolve().parents[1] / "app"
RAISE = re.compile(r'(?:HTTPException|GameError|AccountError|ArenaError|IllegalMove)\(\s*(?:\d+,\s*)?f?"([^"]+)"(?:\s*\n?\s*f?"([^"]*)")?')


def test_every_error_message_has_an_english_translation():
    from app.services.accounts import LOGIN_LOCK_S, MIN_PASSWORD

    missing = []
    for path in APP.rglob("*.py"):
        for m in RAISE.finditer(path.read_text()):
            msg = (m.group(1) + (m.group(2) or "")).replace("{LOGIN_LOCK_S // 60}", str(LOGIN_LOCK_S // 60))
            msg = msg.replace("{MIN_PASSWORD}", str(MIN_PASSWORD))
            if msg != "session" and msg not in EN:
                missing.append(f"{path.name}: {msg}")
    assert not missing, "\n".join(missing)


async def test_errors_follow_the_player_language(client):
    h = await new_player(client)
    r = await client.get("/api/games/nope", headers={**h, "x-lang": "en"})
    assert r.status_code == 404 and r.json()["detail"] == "Game not found."
    r = await client.get("/api/games/nope", headers=h)
    assert r.json()["detail"] == "Partie introuvable."
    r = await client.post("/api/auth/signup", json={"email": "x@example.com", "password": "court"},
                          headers={**h, "x-lang": "en"})
    assert r.json()["detail"] == "Password is too short (8 characters minimum)."
    assert (await client.get("/api/me", headers={**KEY, "x-session": "nope", "x-lang": "en"})).json()["detail"] == "session"


async def test_reset_email_in_english(client):
    h = await new_player(client)
    await client.post("/api/auth/signup", json={"email": "en@example.com", "password": "motdepasse-solide", "country": "FR"}, headers=h)
    await client.post("/api/auth/forgot", json={"email": "en@example.com"}, headers={**KEY, "x-lang": "en"})
    await accounts.flush_mails()
    assert mailer.outbox[-1]["subject"] == "Reset your Traversal password"
    assert "Choose a new password" in mailer.outbox[-1]["html"]


async def test_guest_names_follow_the_language(client):
    from app.routes import ANIMALS

    r = await client.post("/api/players", json={}, headers={**KEY, "x-lang": "en"})
    assert r.json()["player"]["name"].rstrip("0123456789") in ANIMALS["en"]
