"""Matchmaking en base (table `seeks`) : partagé entre toutes les instances.

Un joueur « cherche » une partie d'un type (bullet, classique, tactique), classée ou non ;
dès qu'un autre cherche la même chose (en classé : dans sa fourchette de classement), la
partie (ou, en tactique, le match) est créée dans la MÊME transaction que l'appariement, et
les deux le voient au prochain sondage. En classé, la carte n'est pas choisie : elle est
tirée au sort à la création de la partie (le client anime ce tirage). En non classé, chacun
choisit un type de carte (ou « aléatoire ») : deux choix compatibles s'apparient. La colonne `time_control` contient le type ; `game_id` vaut l'id de la
partie, ou `m:<id>` pour un match tactique.
Un verrou consultatif par cadence sérialise les appariements : un joueur ne peut pas être
apparié deux fois. Une recherche non sondée depuis SEEK_TTL_S est oubliée.
"""

import random
import time
from dataclasses import dataclass

from sqlalchemy import and_, delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app import db
from app.engine import TERRAIN_MODES
from app.services import games as svc
from app.services import matches
from app.services.gametypes import RATED_CLASSES
from app.services.store import Player, store

SEEK_TTL_S = 12
# Fourchette de classement acceptée, élargie avec l'attente.
BASE_WINDOW = 200
WINDOW_GROWTH_PER_10S = 100
LOCK_NS = 727275  # espace des verrous consultatifs du matchmaking

s = db.seeks.c


@dataclass
class Seek:
    player_id: str
    time_control: str
    terrain: str
    created_at: float
    game_id: str | None = None
    rated: bool = True


def _seek(row) -> Seek:
    return Seek(row["player_id"], row["time_control"], row["terrain"], row["created_at"], row["game_id"],
                row["rated"])


def _compatible(a, b, now: float) -> bool:
    if not a["rated"]:  # non classé : pas de fourchette, mais des cartes compatibles
        return "random" in (a["terrain"], b["terrain"]) or a["terrain"] == b["terrain"]
    waited = now - min(a["created_at"], b["created_at"])
    return abs(a["rating"] - b["rating"]) <= BASE_WINDOW + WINDOW_GROWTH_PER_10S * (waited // 10)


async def _try_match(conn: AsyncConnection, pid: str) -> str | None:
    """Apparie la recherche de `pid` (transaction `conn`). Renvoie l'id de la partie."""
    mine = (await conn.execute(select(db.seeks).where(s.player_id == pid))).mappings().first()
    if mine is None or mine["game_id"]:
        return mine["game_id"] if mine else None
    await conn.execute(text("SELECT pg_advisory_xact_lock(:ns, hashtext(:tc))"),
                       {"ns": LOCK_NS, "tc": mine["time_control"]})
    now = time.time()
    others = (await conn.execute(
        select(db.seeks).where(s.time_control == mine["time_control"], s.rated == mine["rated"],
                               s.player_id != pid, s.game_id.is_(None), s.polled_at > now - SEEK_TTL_S)
        .order_by(s.created_at))).mappings().all()
    # Relue sous le verrou : un autre a pu nous apparier entre-temps.
    mine = (await conn.execute(select(db.seeks).where(s.player_id == pid))).mappings().first()
    if mine is None or mine["game_id"]:
        return mine["game_id"] if mine else None
    for other in others:
        if not _compatible(mine, other, now):
            continue
        if mine["time_control"] == "tactic":
            p1, p2 = random.sample([pid, other["player_id"]], 2)  # qui ouvre le veto : au sort
            target = "m:" + (await matches.create_online(conn, p1, p2, rated=mine["rated"])).id
        else:
            me = await store.get_player(pid)
            # Non classé : le choix précis l'emporte sur « aléatoire ».
            terrain = mine["terrain"] if mine["terrain"] != "random" else other["terrain"]
            game = svc.build_game(
                me, "online", terrain, mine["time_control"],
                side=random.choice((1, 2)), opponent_id=other["player_id"], rated=mine["rated"],
            )
            await store.insert_game(game, conn)
            target = game.id
        await conn.execute(update(db.seeks).where(s.player_id.in_([pid, other["player_id"]]))
                           .values(game_id=target))
        return target
    return None


async def seek(me: Player, time_control: str, rated: bool = True, terrain: str = "random") -> Seek:
    if time_control not in RATED_CLASSES:
        raise svc.GameError(422, "Type de partie inconnu.")
    if terrain not in TERRAIN_MODES:
        raise svc.GameError(422, "Terrain inconnu.")
    if rated or time_control == "tactic":  # classé : carte au sort ; tactique : cartes par bans
        terrain = "random"
    now = time.time()
    row = {"player_id": me.id, "time_control": time_control, "terrain": terrain, "rated": rated,
           "rating": me.rating(time_control).rating, "created_at": now,
           "polled_at": now, "game_id": None}
    async with store.engine.begin() as conn:
        await conn.execute(delete(db.seeks).where(s.polled_at < now - SEEK_TTL_S))
        await conn.execute(pg_insert(db.seeks).values(**row).on_conflict_do_update(
            index_elements=["player_id"], set_={k: v for k, v in row.items() if k != "player_id"}))
        gid = await _try_match(conn, me.id)
    if gid:
        await _consume(me.id)
    return Seek(me.id, time_control, terrain, now, gid, rated)


async def poll(me: Player) -> Seek | None:
    now = time.time()
    async with store.engine.begin() as conn:
        row = (await conn.execute(
            update(db.seeks).where(s.player_id == me.id, s.polled_at >= now - SEEK_TTL_S)
            .values(polled_at=now).returning(*db.seeks.c))).mappings().first()
        if row is None:
            return None
        found = _seek(row)
        if not found.game_id:  # la fourchette de classement s'élargit avec l'attente
            found.game_id = await _try_match(conn, me.id)
    if found.game_id:
        await _consume(me.id)  # récupérée : la recherche est terminée
    return found


async def _consume(pid: str) -> None:
    async with store.engine.begin() as conn:
        await conn.execute(delete(db.seeks).where(s.player_id == pid, s.game_id.is_not(None)))


async def cancel(me: Player) -> None:
    async with store.engine.begin() as conn:
        await conn.execute(delete(db.seeks).where(s.player_id == me.id, s.game_id.is_(None)))


async def stats() -> dict:
    now = time.time()
    async with store.engine.connect() as conn:
        rows = (await conn.execute(
            select(s.time_control, func.count()).where(
                and_(s.game_id.is_(None), s.polled_at > now - SEEK_TTL_S)).group_by(s.time_control)
        )).all()
    waiting = dict(rows)
    return {**await store.counts(),
            "seeking": {tc: waiting.get(tc, 0) for tc in RATED_CLASSES}}
