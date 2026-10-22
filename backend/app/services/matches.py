"""Match tactique : 2 manches de 2 min par joueur, bans et choix de carte avant chaque manche.

Déroulé (joueurs 1 et 2 ; le joueur 1 est Rouge à la 1re manche) :

- **Manche 1** : le joueur 1 bannit un type de carte, puis le joueur 2, puis le joueur 1
  choisit parmi les cartes restantes. Il joue Rouge.
- **Manche 2** : idem en inversant les rôles (le joueur 2 bannit, le 1 bannit, le 2
  choisit et joue Rouge). Une carte déjà jouée ne revient pas.
- **1-1 (ou deux nulles)** : manche décisive en bullet (1 min + 1 s), sur une carte non
  jouée tirée au sort, couleurs tirées au sort. Nulle à la décisive : match nul.

Chaque ban / choix a un délai (`VETO_S`) : à l'échéance, une carte est tirée au sort.
Le bot (et donc les matchs contre lui) passe par le même chemin avec un délai court.
Un match en ligne est classé (classement « tactic ») sur son résultat ; les manches,
elles, ne sont jamais classées seules.

Comme les parties : état en base, modifications sous verrou de ligne, notification
`match` à chaque changement (flux SSE de toutes les instances, réveil du balayeur).
"""

import contextlib
import copy
import random
import time
from dataclasses import dataclass, field

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app import bot, db
from app.services import games as svc
from app.services.gametypes import DECIDER_TYPE
from app.services.store import Game, Player, _id, _notify_expr, store

MAPS = ("mountains", "valleys", "highlands", "woodlands", "desert")
VETO_S = 20  # délai d'un ban / d'un choix
BOT_VETO_S = 1.2  # le bot « réfléchit » un instant, le temps de voir son choix
ROUNDS = 2

m_c = db.matches.c


class MatchError(svc.GameError):
    pass


@dataclass
class Match:
    id: str
    mode: str  # online | bot | local
    players: list[str | None]  # joueur 1, joueur 2
    created_by: str
    bot_level: int | None = None
    status: str = "veto"  # waiting | veto | playing | finished | aborted
    round: int = 1
    step: int = 0  # étape du veto de la manche en cours
    rounds: list[dict] = field(default_factory=list)
    score: list[float] = field(default_factory=lambda: [0.0, 0.0])
    winner: int | None = None  # 1, 2, ou None (nul / pas fini)
    rated: bool = False
    rating_before: list[float] | None = None
    rating_after: list[float] | None = None
    rank_change: list | None = None
    deadline_at: float | None = None
    version: int = 1
    created_at: float = field(default_factory=time.time)
    ended_at: float | None = None

    def sides_of(self, pid: str | None) -> list[int]:
        if pid is None:
            return []
        if self.mode == "local":
            return [1, 2] if self.created_by == pid else []
        return [i + 1 for i, p in enumerate(self.players) if p == pid]

    @property
    def current(self) -> dict | None:
        return self.rounds[-1] if self.rounds else None


def _row(m: Match) -> dict:
    return {
        "id": m.id, "mode": m.mode, "status": m.status, "p1_id": m.players[0], "p2_id": m.players[1],
        "created_by": m.created_by, "bot_level": m.bot_level, "round": m.round, "step": m.step,
        "rounds": m.rounds, "score": m.score, "winner": m.winner, "rated": m.rated,
        "rating_before": m.rating_before, "rating_after": m.rating_after, "rank_change": m.rank_change,
        "deadline_at": m.deadline_at, "version": m.version, "created_at": m.created_at, "ended_at": m.ended_at,
    }


def _from_row(r) -> Match:
    return Match(
        id=r["id"], mode=r["mode"], players=[r["p1_id"], r["p2_id"]], created_by=r["created_by"],
        bot_level=r["bot_level"], status=r["status"], round=r["round"], step=r["step"],
        rounds=list(r["rounds"]), score=list(r["score"]), winner=r["winner"], rated=r["rated"],
        rating_before=r["rating_before"], rating_after=r["rating_after"], rank_change=r["rank_change"],
        deadline_at=r["deadline_at"], version=r["version"], created_at=r["created_at"], ended_at=r["ended_at"],
    )


# --- Règles du veto --------------------------------------------------------------------


def picker_of(round_no: int) -> int:
    return 1 if round_no == 1 else 2


def steps_of(round_no: int) -> list[tuple[str, int]]:
    """Bans puis choix : le joueur qui choisit bannit en premier."""
    p = picker_of(round_no)
    return [("ban", p), ("ban", 3 - p), ("pick", p)]


def played(m: Match) -> list[str]:
    return [r["pick"] for r in m.rounds if r.get("gameId")]


def available(m: Match) -> list[str]:
    cur = m.current
    if m.status != "veto" or cur is None:
        return []
    banned = {b["map"] for b in cur["bans"]}
    return [x for x in MAPS if x not in banned and x not in played(m)]


def next_step(m: Match) -> tuple[str, int] | None:
    if m.status != "veto":
        return None
    return steps_of(m.round)[m.step]


def _is_bot(m: Match, idx: int) -> bool:
    return (m.players[idx - 1] or "").startswith("bot")


def _arm_deadline(m: Match) -> None:
    st = next_step(m)
    m.deadline_at = None if st is None else time.time() + (BOT_VETO_S if _is_bot(m, st[1]) else VETO_S)


def _begin_veto(m: Match, round_no: int) -> None:
    m.round, m.step, m.status = round_no, 0, "veto"
    p = picker_of(round_no)
    m.rounds.append({"round": round_no, "picker": p, "red": p, "bans": [], "pick": None,
                     "gameId": None, "winner": None, "done": False})
    _arm_deadline(m)


async def _start_round(conn: AsyncConnection, m: Match, clock_type: str) -> Game:
    cur = m.current
    red = cur["red"]
    game = svc.build_round_game(m, m.players[red - 1], m.players[2 - red], cur["pick"], clock_type, m.round)
    await store._insert_game(conn, game)
    cur["gameId"] = game.id
    m.status, m.deadline_at = "playing", None
    return game


async def _apply_veto(conn: AsyncConnection, m: Match, choice: str) -> None:
    action, by = next_step(m)
    cur = m.current
    if action == "ban":
        cur["bans"].append({"by": by, "map": choice})
        m.step += 1
        _arm_deadline(m)
    else:
        cur["pick"] = choice
        m.step += 1
        await _start_round(conn, m, "tactic")


async def _finish(conn: AsyncConnection, m: Match) -> None:
    a, b = m.score
    m.winner = 1 if a > b else 2 if b > a else None
    m.status, m.ended_at, m.deadline_at = "finished", time.time(), None
    if m.rated and all(m.players):
        s1 = 0.5 if m.winner is None else 1.0 if m.winner == 1 else 0.0
        m.rating_before, m.rating_after, m.rank_change = await store.rate_pair(conn, list(m.players), "tactic", s1)


# --- Accès en base ---------------------------------------------------------------------


async def _save(conn: AsyncConnection, m: Match, insert: bool = False) -> None:
    notify = _notify_expr("match", id=m.id, v=m.version, d=m.deadline_at)
    if insert:
        await conn.execute(pg_insert(db.matches).values(**_row(m)).returning(notify))
    else:
        await conn.execute(update(db.matches).where(m_c.id == m.id).values(**_row(m)).returning(notify))


@contextlib.asynccontextmanager
async def locked(mid: str, conn: AsyncConnection | None = None, skip_locked: bool = False):
    """Match verrouillé ; écrit (version + 1, notification) s'il a été modifié."""
    async with contextlib.AsyncExitStack() as stack:
        if conn is None:
            conn = await stack.enter_async_context(store.engine.begin())
        row = (await conn.execute(
            select(db.matches).where(m_c.id == mid).with_for_update(skip_locked=skip_locked))).mappings().first()
        if row is None:
            yield None, conn
            return
        m = _from_row(row)
        before = copy.deepcopy(_row(m))
        yield m, conn
        if _row(m) != before:
            m.version += 1
            await _save(conn, m)


async def get(mid: str) -> Match | None:
    async with store.engine.connect() as conn:
        row = (await conn.execute(select(db.matches).where(m_c.id == mid))).mappings().first()
    return _from_row(row) if row else None


# --- Actions ---------------------------------------------------------------------------


def _new(mode: str, players: list[str | None], created_by: str, bot_level: int | None,
         rated: bool = True) -> Match:
    m = Match(id=_id(8), mode=mode, players=players, created_by=created_by,
              bot_level=bot_level if mode == "bot" else None, rated=mode == "online" and rated)
    if all(players):
        _begin_veto(m, 1)
    else:
        m.status = "waiting"
    return m


async def create(me: Player, mode: str, bot_level: int | None = None, side: int | None = None,
                 rated: bool = True) -> Match:
    if mode not in ("local", "bot", "online"):
        raise MatchError(422, "Mode inconnu.")
    if side not in (1, 2):
        side = random.choice((1, 2))
    if mode == "local":
        players = [me.id, me.id]
    elif mode == "bot":
        if bot_level not in bot.LEVELS:
            raise MatchError(422, "Niveau de bot inconnu.")
        players = [me.id, f"bot{bot_level}"] if side == 1 else [f"bot{bot_level}", me.id]
    else:
        players = [me.id, None] if side == 1 else [None, me.id]
    m = _new(mode, players, me.id, bot_level, rated)
    async with store.engine.begin() as conn:
        await _save(conn, m, insert=True)
    return m


async def create_online(conn: AsyncConnection, p1: str, p2: str, rated: bool = True) -> Match:
    """Matchmaking : match entre deux joueurs, dans la transaction de l'appariement."""
    m = _new("online", [p1, p2], p1, None, rated)
    await _save(conn, m, insert=True)
    return m


async def join(mid: str, me: Player) -> Match:
    async with locked(mid) as (m, conn):
        if m is None:
            raise MatchError(404, "Match introuvable.")
        if m.status != "waiting":
            raise MatchError(409, "Le match a déjà commencé.")
        if me.id in m.players:
            raise MatchError(409, "Tu es déjà dans ce match.")
        m.players = [p if p is not None else me.id for p in m.players]
        _begin_veto(m, 1)
    return m


async def veto(mid: str, me: Player, choice: str) -> Match:
    async with locked(mid) as (m, conn):
        if m is None:
            raise MatchError(404, "Match introuvable.")
        st = next_step(m)
        if st is None:
            raise MatchError(409, "Ce n'est pas le moment de choisir une carte.")
        if st[1] not in m.sides_of(me.id):
            raise MatchError(403, "Ce n'est pas ton tour.")
        if choice not in available(m):
            raise MatchError(422, "Carte indisponible.")
        await _apply_veto(conn, m, choice)
    return m


async def abort(mid: str, me: Player) -> Match:
    async with locked(mid) as (m, conn):
        if m is None:
            raise MatchError(404, "Match introuvable.")
        ok = (m.status == "waiting" and m.created_by == me.id) or (
            m.status == "veto" and m.round == 1 and m.sides_of(me.id))
        if not ok:
            raise MatchError(409, "Annulation impossible.")
        m.status, m.ended_at, m.deadline_at = "aborted", time.time(), None
    return m


async def expire(mid: str) -> bool:
    """Échéance d'un ban / choix : carte tirée au sort (c'est aussi le « coup » du bot)."""
    async with locked(mid, skip_locked=True) as (m, conn):
        if m is None or m.status != "veto" or not m.deadline_at or m.deadline_at > time.time():
            return False
        await _apply_veto(conn, m, random.choice(available(m)))
    return True


async def on_round_end(conn: AsyncConnection, g: Game) -> None:
    """Fin d'une manche (dans la transaction de la partie) : score, puis manche suivante,
    décisive, ou fin du match."""
    async with locked(g.match_id, conn=conn) as (m, _):
        if m is None:
            return
        cur = next((r for r in m.rounds if r["round"] == g.round), None)
        if cur is None or cur["done"] or m.status != "playing":
            return
        if g.status == "aborted":
            if g.round == 1:  # personne n'a joué : le match n'a pas vraiment commencé
                m.status, m.ended_at = "aborted", time.time()
                cur["done"] = True
                return
            # Plus tard : le joueur qui n'a pas joué son premier coup perd la manche.
            side_won = 3 - g.state.to_move
        else:
            side_won = g.state.winner  # 1 = Rouge, 2 = Bleu, None = nulle
        red = cur["red"]
        idx = None if side_won is None else red if side_won == 1 else 3 - red
        cur["winner"], cur["done"] = idx or 0, True
        if idx is None:
            m.score = [m.score[0] + 0.5, m.score[1] + 0.5]
        else:
            m.score[idx - 1] += 1
        if m.round < ROUNDS:
            _begin_veto(m, m.round + 1)
        elif m.round == ROUNDS and m.score[0] == m.score[1]:
            m.round = ROUNDS + 1
            left = [x for x in MAPS if x not in played(m)]
            m.rounds.append({"round": m.round, "picker": None, "red": random.choice((1, 2)), "bans": [],
                             "pick": random.choice(left), "gameId": None, "winner": None, "done": False})
            await _start_round(conn, m, DECIDER_TYPE)
        else:
            await _finish(conn, m)


store.round_hooks.append(on_round_end)


# --- Listes ----------------------------------------------------------------------------


async def rating_history(pid: str, limit: int = 300) -> list[dict]:
    """Courbe du classement tactique : un point par match classé terminé."""
    q = (select(db.matches).where(m_c.rated.is_(True), m_c.status == "finished",
                                  or_(m_c.p1_id == pid, m_c.p2_id == pid), m_c.rating_after.is_not(None))
         .order_by(m_c.ended_at.desc()).limit(limit))
    async with store.engine.connect() as conn:
        rows = list((await conn.execute(q)).mappings())
    out = []
    for r in sorted(rows, key=lambda r: r["ended_at"] or 0):
        side = 1 if r["p1_id"] == pid else 2
        opp = await store.get_player(r["p2_id"] if side == 1 else r["p1_id"])
        out.append({
            "gameId": r["id"], "matchId": r["id"], "t": r["ended_at"],
            "before": round(r["rating_before"][side - 1]), "rating": round(r["rating_after"][side - 1]),
            "result": "draw" if r["winner"] is None else "win" if r["winner"] == side else "loss",
            "opponent": opp.name if opp else "?",
        })
    return out


async def summaries(mids: list[str]) -> dict[str, Match]:
    if not mids:
        return {}
    async with store.engine.connect() as conn:
        rows = (await conn.execute(select(db.matches).where(m_c.id.in_(mids)))).mappings().all()
    return {r["id"]: _from_row(r) for r in rows}
