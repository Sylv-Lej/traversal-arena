"""Tests : le backend est sans état, il lui faut un vrai Postgres.

TEST_DATABASE_URL doit pointer vers une base JETABLE locale (le schéma est effacé) :

    docker run -d --rm --name trav-pg -e POSTGRES_PASSWORD=pg -e POSTGRES_DB=trav \\
        -p 55432:5432 postgres:17
    TEST_DATABASE_URL=postgresql://postgres:pg@localhost:55432/trav pytest

Sans elle, seuls les tests du moteur (sans base) tournent.
"""

import os

URL = os.environ.get("TEST_DATABASE_URL", "")
LOCAL = bool(URL) and any(h in URL for h in ("localhost", "127.0.0.1"))
os.environ.setdefault("API_KEY", "test-key")
os.environ.setdefault("ARENA_TOKEN", "test-arena")
if LOCAL:
    os.environ["DATABASE_URL"] = URL

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import text  # noqa: E402

KEY = {"x-api-key": "test-key"}
NEEDS_DB = pytest.mark.skipif(not LOCAL, reason="TEST_DATABASE_URL (base locale jetable) non fourni")


def pytest_collection_modifyitems(items):
    for item in items:
        if {"client", "backend"} & set(getattr(item, "fixturenames", ())):
            item.add_marker(NEEDS_DB)


@pytest_asyncio.fixture(scope="session")
async def backend():
    """Démarre le backend (migrations, écoute NOTIFY, workers) une fois pour la session."""
    from sqlalchemy.ext.asyncio import create_async_engine

    from app import main
    from app.services import workers
    from app.services.store import store

    engine = create_async_engine(main.settings.sqlalchemy_url)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await engine.dispose()
    await main._startup()
    yield main.app
    await workers.stop()
    await store.stop()


TABLES = ("moves, bot_jobs, analysis_jobs, seeks, sessions, password_resets, ratings, games, "
          "players, rate_hits, game_watchers, matches, puzzle_attempts, puzzle_rushes, puzzles, "
          "arena_bots, arena_jobs, arena_ratings, email_verifications")


async def reset_db() -> None:
    """Base vide (sauf les bots) et caches vidés : chaque test part de zéro."""
    from app import bot
    from app.routes import reset_limiters
    from app.services import accounts, mailer
    from app.services.store import store

    # Emails encore en cours d'envoi (tâches de fond qui écrivent en base) : terminés
    # AVANT de vider les tables, sinon ils se bloquent mutuellement avec le TRUNCATE.
    await accounts.flush_mails()
    async with store.engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {TABLES} CASCADE"))
    store.clear_caches()
    from app.services import spectators

    spectators._local.clear()
    spectators._dirty.clear()
    spectators._cache.clear()
    await store.ensure_bots(bot.LEVELS)
    reset_limiters()
    await accounts.flush_mails()
    mailer.outbox.clear()


@pytest_asyncio.fixture
async def client(backend):
    await reset_db()
    transport = httpx.ASGITransport(app=backend)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


async def new_player(client, name=None):
    r = await client.post("/api/players", json={"name": name}, headers=KEY)
    assert r.status_code == 200, r.text
    return {**KEY, "x-session": r.json()["token"]}
