"""Travail de fond, sur CHAQUE instance, coordonné par la base.

- **Pendules** : balaie les parties dont l'échéance (`games.deadline_at`) est passée.
- **Bots** : réclame les tâches `bot_jobs` échues (`FOR UPDATE SKIP LOCKED`) et joue.
- **Analyses** : réclame les tâches `analysis_jobs` (une à la fois par instance).
- **Ménage** : sessions expirées, invités inactifs… (toutes les 6 h, idempotent).

Pas de sondage serré (la base Lampion doit pouvoir se suspendre) : chaque worker dort
jusqu'à sa prochaine échéance connue, et est réveillé par les notifications Postgres
(une échéance plus proche, une nouvelle tâche). Un réveil de secours toutes les
`FALLBACK_S` rattrape une notification manquée ou une instance disparue.
"""

import asyncio
import contextlib
import logging
import time

from sqlalchemy import func, select, text

from app import db
from app.services import analysis_jobs, limits, matches, spectators
from app.services import games as svc
from app.services.store import store

log = logging.getLogger("traversal.workers")

FALLBACK_S = 60
BOT_SLOTS = 2  # coups de bot calculés en parallèle par instance
BOT_STALE_CLAIM_S = 30  # tâche réclamée par une instance disparue : reprise
MAINTENANCE_EVERY_S = 6 * 3600
MIN_SLEEP_S = 0.05


class Waker:
    """Réveil d'un worker : au plus tard à `at`, plus tôt si une notification le demande."""

    def __init__(self) -> None:
        self.event = asyncio.Event()
        self.at: float | None = None

    def wake(self, at: float | None = None) -> None:
        if at is None or self.at is None or at < self.at:
            self.at = at
            self.event.set()

    async def sleep_until(self, at: float | None) -> None:
        self.at = at
        delay = FALLBACK_S if at is None else min(FALLBACK_S, max(MIN_SLEEP_S, at - time.time()))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self.event.wait(), timeout=delay)
        self.event.clear()
        self.at = None


clocks = Waker()
bots = Waker()
analyses = Waker()


def on_event(ev: dict) -> None:
    kind = ev.get("k")
    if kind in ("game", "match") and ev.get("d"):
        clocks.wake(ev["d"])
    elif kind == "bot":
        bots.wake(ev.get("t"))
    elif kind == "ajob":
        analyses.wake()
    elif kind == "reconnect":
        for w in (clocks, bots, analyses):
            w.wake()


async def _guard(name: str, fn) -> None:
    """Un worker ne meurt jamais : on journalise et on reprend."""
    while True:
        try:
            await fn()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("worker %s en erreur", name)
            await asyncio.sleep(2)


# --- Pendules --------------------------------------------------------------------------

g = db.games.c
mt = db.matches.c


async def sweep_clocks() -> float | None:
    """Traite les échéances passées ; renvoie la prochaine échéance connue."""
    now = time.time()
    async with store.engine.connect() as conn:
        due = (await conn.execute(select(g.id).where(g.deadline_at <= now).order_by(g.deadline_at)
                                  .limit(100))).scalars().all()
        due_matches = (await conn.execute(select(mt.id).where(mt.deadline_at <= now).order_by(mt.deadline_at)
                                          .limit(100))).scalars().all()
    for gid in due:
        await svc.expire(gid)
    for mid in due_matches:  # ban / choix de carte non fait à temps (ou tour du bot)
        await matches.expire(mid)
    async with store.engine.connect() as conn:
        nxt = (await conn.execute(select(func.min(g.deadline_at)))).scalar()
        nxt_m = (await conn.execute(select(func.min(mt.deadline_at)))).scalar()
    nxt = min((t for t in (nxt, nxt_m) if t is not None), default=None)
    if nxt is not None and nxt <= time.time():
        nxt = time.time() + 0.25  # partie verrouillée (coup en cours) : on repasse vite
    return nxt


async def _clock_loop() -> None:
    while True:
        clocks.event.clear()
        nxt = await sweep_clocks()
        await clocks.sleep_until(nxt + 0.02 if nxt else None)


# --- Bots ------------------------------------------------------------------------------

_bot_slots = asyncio.Semaphore(BOT_SLOTS)


async def claim_bot() -> tuple[str, int] | None:
    now = time.time()
    async with store.engine.begin() as conn:
        row = (await conn.execute(text("""
            UPDATE bot_jobs SET claimed_at = :now
            WHERE game_id = (
                SELECT game_id FROM bot_jobs
                WHERE run_after <= :now AND (claimed_at IS NULL OR claimed_at < :stale)
                ORDER BY run_after LIMIT 1 FOR UPDATE SKIP LOCKED)
            RETURNING game_id, version"""), {"now": now, "stale": now - BOT_STALE_CLAIM_S})).first()
    return (row[0], row[1]) if row else None


async def next_bot_due() -> float | None:
    now = time.time()
    b = db.bot_jobs.c
    async with store.engine.connect() as conn:
        free = (await conn.execute(select(func.min(b.run_after)).where(b.claimed_at.is_(None)))).scalar()
        stale = (await conn.execute(select(func.min(b.claimed_at)).where(b.claimed_at.is_not(None)))).scalar()
    candidates = [t for t in (free, stale + BOT_STALE_CLAIM_S if stale else None) if t is not None]
    return max(min(candidates), now) if candidates else None


async def _run_bot(gid: str, version: int) -> None:
    try:
        await svc.bot_turn(gid, version)
    except Exception:
        log.exception("coup du bot %s échoué", gid)
    finally:
        _bot_slots.release()
        bots.wake()  # un créneau se libère


async def _bot_loop() -> None:
    while True:
        bots.event.clear()
        await _bot_slots.acquire()
        job = await claim_bot()
        if job:
            asyncio.get_running_loop().create_task(_run_bot(*job))
            continue
        _bot_slots.release()
        await bots.sleep_until(await next_bot_due())


# --- Analyses --------------------------------------------------------------------------


async def _analysis_loop() -> None:
    while True:
        analyses.event.clear()
        gid = await analysis_jobs.claim()
        if gid:
            await analysis_jobs.run(gid)
            continue
        # Rien à prendre ; une analyse en cours ailleurs pourrait être reprise (instance
        # disparue) : on revérifie au réveil de secours.
        await analyses.sleep_until(None)


# --- Ménage ----------------------------------------------------------------------------


async def _maintenance_loop() -> None:
    while True:
        stats = await store.maintenance()
        stats["rate_hits"] = await limits.prune()
        stats["watchers"] = await spectators.prune()
        if any(stats.values()):
            log.warning("ménage : %s", stats)
        await asyncio.sleep(MAINTENANCE_EVERY_S)


_tasks: list[asyncio.Task] = []


def start() -> None:
    if on_event not in store.subscribers:
        store.subscribers.append(on_event)
    loop = asyncio.get_running_loop()
    for name, fn in (("pendules", _clock_loop), ("bots", _bot_loop), ("analyses", _analysis_loop),
                     ("ménage", _maintenance_loop), ("spectateurs", spectators.loop)):
        _tasks.append(loop.create_task(_guard(name, fn)))


async def stop() -> None:
    with contextlib.suppress(Exception):
        await spectators.forget_instance()
    for t in _tasks:
        t.cancel()
    for t in _tasks:
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await t
    _tasks.clear()
