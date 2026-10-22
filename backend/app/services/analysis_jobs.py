"""File d'analyses en base (table `analysis_jobs`), consommée par les workers.

Chaque instance analyse au plus une partie à la fois (CPU limité). Le résultat est rangé
sur la partie (`games.analysis`) : une partie n'est analysée qu'une fois, pour tout le
monde. L'avancement passe par la base et une notification (flux SSE de toute instance).
"""

import asyncio
import logging
import time

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app import db
from app.analysis import VERSION, analyse_game
from app.services.store import Game, store

log = logging.getLogger("traversal.analysis")

# Une analyse prise par une instance qui a disparu est reprise après ce délai.
STALE_CLAIM_S = 180
PROGRESS_EVERY_S = 0.4

j = db.analysis_jobs.c


def _current(analysis: dict | None) -> dict | None:
    """Un bilan d'une version antérieure de l'analyse ne compte pas : il sera recalculé."""
    return analysis if analysis and analysis.get("version") == VERSION else None


async def status(game: Game) -> dict:
    analysis = _current(game.analysis or await store.get_analysis(game.id))
    total = len(game.moves)
    if analysis:
        game.analysis = analysis
        return {"status": "done", "done": total, "total": total, "result": analysis}
    async with store.engine.connect() as conn:
        row = (await conn.execute(select(db.analysis_jobs).where(j.game_id == game.id))).mappings().first()
    if row is None:
        return {"status": "none", "done": 0, "total": total}
    return {"status": row["status"], "done": row["done"], "total": row["total"] or total}


async def start(game: Game) -> dict:
    """Met la partie en file (une seule fois ; une analyse en erreur est relancée)."""
    if _current(game.analysis or await store.get_analysis(game.id)):
        return await status(game)
    row = {"game_id": game.id, "status": "queued", "done": 0, "total": len(game.moves),
           "created_at": time.time(), "claimed_at": None}
    async with store.engine.begin() as conn:
        await conn.execute(pg_insert(db.analysis_jobs).values(**row).on_conflict_do_update(
            index_elements=["game_id"], set_={"status": "queued", "claimed_at": None, "done": 0},
            where=j.status == "error"))
        await store.notify(conn, "ajob", id=game.id)
    return await status(game)


async def claim() -> str | None:
    now = time.time()
    async with store.engine.begin() as conn:
        return (await conn.execute(text("""
            UPDATE analysis_jobs SET status = 'running', claimed_at = :now
            WHERE game_id = (
                SELECT game_id FROM analysis_jobs
                WHERE status = 'queued' OR (status = 'running' AND claimed_at < :stale)
                ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED)
            RETURNING game_id"""), {"now": now, "stale": now - STALE_CLAIM_S})).scalar()


async def pending() -> bool:
    async with store.engine.connect() as conn:
        return bool((await conn.execute(select(j.game_id).where(j.status.in_(("queued", "running")))
                                         .limit(1))).first())


async def run(gid: str) -> None:
    game = await store.get_game(gid)
    if game is None:
        return
    await _notify(gid)
    loop = asyncio.get_running_loop()
    last = [0.0]

    def progress(done: int, total: int) -> None:
        now = time.time()
        if now - last[0] >= PROGRESS_EVERY_S:
            last[0] = now
            asyncio.run_coroutine_threadsafe(_progress(gid, done, total), loop)

    try:
        result = await asyncio.to_thread(analyse_game, list(game.states), list(game.moves), progress)
    except Exception:
        log.exception("analyse de %s échouée", gid)
        async with store.engine.begin() as conn:
            await conn.execute(update(db.analysis_jobs).where(j.game_id == gid).values(status="error"))
            await store.notify(conn, "analysis", id=gid)
        return
    await store.set_analysis(gid, result)


async def _progress(gid: str, done: int, total: int) -> None:
    try:
        async with store.engine.begin() as conn:
            await conn.execute(update(db.analysis_jobs).where(j.game_id == gid, j.status == "running")
                               .values(done=done, total=total, claimed_at=time.time()))
            await store.notify(conn, "analysis", id=gid)
    except Exception:
        log.warning("avancement de l'analyse non écrit", exc_info=True)


async def _notify(gid: str) -> None:
    async with store.engine.begin() as conn:
        await store.notify(conn, "analysis", id=gid)
