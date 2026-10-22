"""Limites de débit et de connexions.

- **Partagées** (en base, table `rate_hits`) : routes sensibles et peu fréquentes
  (connexion, inscription, création d'invité, bilans, emails). Avec N instances, une IP
  ne gagne rien à tomber sur des instances différentes.
- **Flux SSE** : nombre de flux ouverts en même temps par IP (par instance). Sans ce
  plafond, une seule IP occuperait les 80 places d'une instance avec des connexions
  longues.

Les limites à fort trafic (coups, 300/min) restent en mémoire (`revkit.ratelimit`) : un
aller-retour à la base de plus par coup ne vaut pas la précision gagnée.
"""

import contextlib
import time
from collections import defaultdict

from fastapi import HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from revkit.ratelimit import client_key

from app import db
from app.services.store import store

RETENTION_S = 86400  # compteurs plus vieux supprimés par le ménage


def _window(window_s: int) -> float:
    return float(int(time.time() // window_s) * window_s)


async def count(key: str, window_s: int) -> int:
    """Passages déjà comptés pour `key` dans la fenêtre courante."""
    r = db.rate_hits.c
    async with store.engine.connect() as conn:
        n = (await conn.execute(select(r.count).where(r.key == key[:200], r.window_start == _window(window_s)))).scalar()
    return n or 0


async def forget(key: str) -> None:
    async with store.engine.begin() as conn:
        await conn.execute(delete(db.rate_hits).where(db.rate_hits.c.key == key[:200]))


async def hit(key: str, limit: int, window_s: int) -> bool:
    """Compte un passage ; False si `limit` est dépassée dans la fenêtre courante."""
    stmt = pg_insert(db.rate_hits).values(key=key[:200], window_start=_window(window_s), count=1)
    stmt = stmt.on_conflict_do_update(
        index_elements=["key", "window_start"], set_={"count": db.rate_hits.c.count + 1}
    ).returning(db.rate_hits.c.count)
    async with store.engine.begin() as conn:
        count = (await conn.execute(stmt)).scalar()
    return count <= limit


def shared_limit(name: str, limit: int, window_s: int):
    """Dépendance FastAPI : limite par IP, commune à toutes les instances (429 au-delà)."""

    async def dependency(request: Request) -> None:
        if not await hit(f"{name}:{client_key(request)}", limit, window_s):
            raise HTTPException(429, "Trop de requêtes. Réessaie dans un instant.")

    return dependency


async def prune() -> int:
    async with store.engine.begin() as conn:
        r = await conn.execute(delete(db.rate_hits).where(db.rate_hits.c.window_start < time.time() - RETENTION_S))
    return r.rowcount


# --- Flux SSE ouverts ------------------------------------------------------------------

MAX_STREAMS_PER_IP = 12  # quelques onglets + spectateurs ; largement assez pour un humain
_streams: dict[str, int] = defaultdict(int)


def check_stream(request: Request) -> str:
    """À l'ouverture d'un flux : 429 si l'IP a déjà trop de flux ouverts."""
    key = client_key(request)
    if _streams.get(key, 0) >= MAX_STREAMS_PER_IP:
        raise HTTPException(429, "Trop de parties ouvertes en même temps.")
    return key


@contextlib.contextmanager
def stream_slot(key: str):
    """Occupe une place pendant toute la vie du flux (dans le générateur SSE : la place
    n'est prise que si le flux démarre vraiment, et rendue quand il se termine)."""
    _streams[key] += 1
    try:
        yield
    finally:
        _streams[key] -= 1
        if _streams[key] <= 0:
            del _streams[key]
