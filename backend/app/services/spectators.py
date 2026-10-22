"""Spectateurs des parties.

Chaque instance compte les flux SSE ouverts par des non-joueurs (`join` / `leave`) et
écrit son total par partie dans `game_watchers` (au plus une fois par seconde, puis un
battement toutes les minutes). Le nombre affiché est la somme des lignes fraîches : une
instance arrêtée brutalement cesse de compter après `STALE_S`. Chaque changement émet
une notification « watch » : les flux de toutes les instances renvoient le nouveau total.
"""

import asyncio
import logging
import time
from collections import defaultdict

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app import db
from app.services.store import INSTANCE, store

log = logging.getLogger("traversal.spectators")

FLUSH_S = 1.0
HEARTBEAT_S = 60
STALE_S = 180
CACHE_S = 1.0

w = db.game_watchers.c
_local: dict[str, int] = defaultdict(int)
_dirty: set[str] = set()
_wake = asyncio.Event()
_cache: dict[str, tuple[float, int]] = {}


def join(gid: str) -> None:
    _local[gid] += 1
    _dirty.add(gid)
    _wake.set()


def leave(gid: str) -> None:
    _local[gid] = max(0, _local[gid] - 1)
    _dirty.add(gid)
    _wake.set()


async def counts(gids: list[str]) -> dict[str, int]:
    """Spectateurs par partie, toutes instances confondues."""
    now = time.time()
    out, missing = {}, []
    for g in gids:
        hit = _cache.get(g)
        if hit and now - hit[0] < CACHE_S:
            out[g] = hit[1]
        else:
            missing.append(g)
    if missing:
        async with store.engine.connect() as conn:
            rows = dict((await conn.execute(
                select(w.game_id, func.sum(w.count)).where(w.game_id.in_(missing), w.updated_at > now - STALE_S)
                .group_by(w.game_id))).all())
        for g in missing:
            out[g] = int(rows.get(g) or 0)
            _cache[g] = (now, out[g])
    return out


async def count(gid: str) -> int:
    return (await counts([gid]))[gid]


async def _flush(gids: set[str], notify: bool) -> None:
    now = time.time()
    async with store.engine.begin() as conn:
        for gid in gids:
            n = _local.get(gid, 0)
            if n:
                await conn.execute(pg_insert(db.game_watchers).values(
                    game_id=gid, instance=INSTANCE, count=n, updated_at=now).on_conflict_do_update(
                    index_elements=["game_id", "instance"], set_={"count": n, "updated_at": now}))
            else:
                _local.pop(gid, None)
                await conn.execute(delete(db.game_watchers).where(w.game_id == gid, w.instance == INSTANCE))
            if notify:
                await store.notify(conn, "watch", id=gid)
    for gid in gids:
        _cache.pop(gid, None)


async def loop() -> None:
    """Écrit les changements (regroupés à la seconde) et le battement de cœur."""
    last_beat = time.time()
    while True:
        try:
            await asyncio.wait_for(_wake.wait(), timeout=HEARTBEAT_S)
        except TimeoutError:
            pass
        _wake.clear()
        await asyncio.sleep(FLUSH_S)  # regroupe les arrivées / départs proches
        batch = set(_dirty)
        _dirty.clear()
        try:
            if batch:
                await _flush(batch, notify=True)
            if time.time() - last_beat >= HEARTBEAT_S and _local:
                await _flush(set(_local) - batch, notify=False)  # « toujours là »
                last_beat = time.time()
        except Exception:
            _dirty.update(batch)  # on réessaiera
            raise


async def prune() -> int:
    async with store.engine.begin() as conn:
        r = await conn.execute(delete(db.game_watchers).where(w.updated_at < time.time() - STALE_S))
    return r.rowcount


async def forget_instance() -> None:
    """Arrêt propre : cette instance ne compte plus personne."""
    _local.clear()
    async with store.engine.begin() as conn:
        await conn.execute(delete(db.game_watchers).where(w.instance == INSTANCE))
