"""Stockage : Postgres (Lampion) est la source de vérité ; le backend est SANS ÉTAT.

Plusieurs instances du backend peuvent tourner en même temps (`max_scale > 1`) :

- **Toute modification d'une partie** passe par `locked_game()` : une transaction qui
  verrouille la ligne de la partie (`SELECT … FOR UPDATE`), applique le changement, écrit
  les nouveaux coups et la partie, puis émet un `NOTIFY`. Deux coups simultanés, même
  reçus par deux instances différentes, sont donc sérialisés par Postgres.
- **Temps réel entre instances** : chaque instance garde une connexion qui écoute le
  canal `traversal` (`LISTEN`). Une notification réveille les flux SSE de cette instance
  et invalide ses caches.
- **Caches locaux** (parties, joueurs, sessions) : de simples accélérateurs. Une partie
  en cache n'est réutilisée que si sa version correspond à la base ; joueurs et sessions
  sont invalidés par notification.
- **Travail de fond partagé** (coups des bots, bilans, pendules, matchmaking) : files en
  base consommées avec `FOR UPDATE SKIP LOCKED` — une tâche n'est prise que par une
  seule instance.
"""

import asyncio
import contextlib
import dataclasses
import hashlib
import json
import logging
import secrets
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field

import asyncpg
from sqlalchemy import and_, delete, exists, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app import db
from app.engine import GameState, Move, apply_move, end_game, new_game
from app.engine import config as C
from app.services.rating import Rating

log = logging.getLogger("traversal.store")

CHANNEL = "traversal"
INSTANCE = uuid.uuid4().hex[:8]  # identifie l'émetteur d'une notification

# Fins de partie qui ne viennent pas d'un coup : à réappliquer après le rejeu.
# « forfeit » : bot de l'arène perdant sur faute (plantage, coup inexistant).
OFF_BOARD_REASONS = {"resign", "timeout", "agreement", "aborted", "abandon", "forfeit"}
MAX_CACHED_GAMES = 500
MAX_CACHED_PLAYERS = 5000
# `last_seen` réécrit au plus toutes les minutes (sert au compteur « en ligne »).
SEEN_PERSIST_S = 60
ONLINE_WINDOW_S = 150
# Sessions : expiration après 60 jours sans utilisation (glissante).
SESSION_TTL_S = 60 * 86400
SESSION_TOUCH_S = 3600  # « dernière utilisation » réécrite au plus une fois par heure
# Lien de réinitialisation du mot de passe : 1 heure, usage unique.
RESET_TTL_S = 3600
VERIFY_TTL_S = 48 * 3600  # lien de confirmation d'adresse
# Invités jamais revenus et sans aucune partie : supprimés après 30 jours.
GUEST_TTL_S = 30 * 86400
LEGENDS_TTL_S = 30
STARTUP_RETRIES = 8  # ~45 s au total


def _id(n: int = 8) -> str:
    return secrets.token_urlsafe(n)[:n].replace("-", "x").replace("_", "y")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass
class Player:
    id: str
    name: str
    created_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    ratings: dict[str, Rating] = field(default_factory=dict)
    is_bot: bool = False
    email: str | None = None
    password_hash: str | None = None
    seen_saved: float = 0.0
    country: str | None = None  # ISO 3166-1 alpha-2 (drapeau)
    email_verified_at: float | None = None  # adresse confirmée (lien reçu par email)

    @property
    def is_guest(self) -> bool:
        return self.email is None and not self.is_bot

    def rating(self, time_class: str) -> Rating:
        return self.ratings.setdefault(time_class, Rating())


@dataclass
class Session:
    player_id: str
    last_used: float
    saved: float  # dernière écriture de last_used en base


@dataclass
class MoveRecord:
    ply: int
    side: int
    piece_id: str
    kind: str
    special: str | None
    frm: int | None
    to: int | None
    path: tuple[int, ...]
    notation: str
    combat: dict | None
    captured_id: str | None
    remaining_ms: int | None


@dataclass
class Game:
    id: str
    mode: str  # local | bot | online
    terrain_mode: str
    seed: int
    players: list[str | None]  # index 0 = joueur 1 (rouge)
    created_by: str
    states: list[GameState]
    bot_level: int | None = None
    initial_ms: int | None = None
    increment_ms: int = 0
    remaining: list[int] = field(default_factory=lambda: [0, 0])
    turn_started_at: float | None = None
    moves: list[MoveRecord] = field(default_factory=list)
    status: str = "active"  # waiting | active | finished | aborted
    version: int = 1
    rated: bool = False
    time_class: str = "casual"
    draw_offer: int | None = None
    rematch_offer: int | None = None
    rematch_id: str | None = None
    rating_before: list[float] | None = None
    rating_after: list[float] | None = None
    created_at: float = field(default_factory=time.time)
    ended_at: float | None = None
    analysis: dict | None = None  # bilan de partie (calculé à la demande, une seule fois)
    # Rang avant/après la partie, figé à la fin (promotions, relégations, placement).
    rank_change: list | None = None
    # Échéance de la pendule ou du premier coup (balayée par toutes les instances).
    deadline_at: float | None = None
    # Quand le bot doit jouer (None = pas au bot de jouer). Écrit dans `bot_jobs`.
    bot_due_at: float | None = None
    # Manche d'un match tactique (sinon None).
    match_id: str | None = None
    round: int | None = None
    # Mise en place des pièces au début (`C.SETUPS`) : celle du moment pour une nouvelle partie.
    setup: str = C.SETUP

    @property
    def state(self) -> GameState:
        return self.states[-1]

    def sides_of(self, player_id: str | None) -> list[int]:
        if player_id is None:
            return []
        if self.mode == "local":
            return [1, 2] if self.created_by == player_id else []
        return [i + 1 for i, p in enumerate(self.players) if p == player_id]

    @property
    def timed(self) -> bool:
        return self.initial_ms is not None

    def clone(self) -> "Game":
        """Copie modifiable : un échec de transaction ne doit pas abîmer le cache."""
        return dataclasses.replace(
            self, states=list(self.states), moves=list(self.moves), players=list(self.players),
            remaining=list(self.remaining),
        )


@dataclass
class GameSummary:
    """Ce qu'il faut pour lister une partie, sans la rejouer."""

    id: str
    mode: str
    status: str
    terrain_mode: str
    initial_ms: int | None
    increment_ms: int
    players: list[str | None]
    created_by: str
    winner: int | None
    reason: str | None
    scores: tuple[int, int]
    ply: int
    created_at: float

    def sides_of(self, player_id: str | None) -> list[int]:
        if player_id is None:
            return []
        if self.mode == "local":
            return [1, 2] if self.created_by == player_id else []
        return [i + 1 for i, p in enumerate(self.players) if p == player_id]


# --- Lignes SQL <-> objets -------------------------------------------------------------


def _player_row(p: Player) -> dict:
    return {"id": p.id, "name": p.name, "email": p.email, "password_hash": p.password_hash,
            "is_bot": p.is_bot, "created_at": p.created_at, "last_seen": p.last_seen, "country": p.country,
            "email_verified_at": p.email_verified_at}


def _game_row(g: Game) -> dict:
    s = g.state
    return {
        "id": g.id, "mode": g.mode, "status": g.status, "terrain_mode": g.terrain_mode,
        "seed": g.seed, "heights": list(s.heights), "move_limit": s.move_limit,
        "p1_id": g.players[0], "p2_id": g.players[1], "created_by": g.created_by,
        "bot_level": g.bot_level, "initial_ms": g.initial_ms, "increment_ms": g.increment_ms,
        "remaining": list(g.remaining), "turn_started_at": g.turn_started_at,
        "version": g.version, "rated": g.rated, "time_class": g.time_class,
        "draw_offer": g.draw_offer, "rematch_offer": g.rematch_offer, "rematch_id": g.rematch_id,
        "rating_before": g.rating_before, "rating_after": g.rating_after,
        "ply": s.ply, "score1": s.scores[0], "score2": s.scores[1],
        "winner": s.winner if s.over else None, "reason": s.reason if s.over else None,
        "created_at": g.created_at, "ended_at": g.ended_at,
        "rank_change": g.rank_change, "deadline_at": g.deadline_at,
        "match_id": g.match_id, "round": g.round, "setup": g.setup,
    }


def _move_row(game_id: str, r: MoveRecord) -> dict:
    return {"game_id": game_id, "ply": r.ply, "side": r.side, "piece_id": r.piece_id,
            "kind": r.kind, "special": r.special, "frm": r.frm, "to": r.to, "path": list(r.path),
            "notation": r.notation, "combat": r.combat, "captured_id": r.captured_id,
            "remaining_ms": r.remaining_ms}


def _rating_row(pid: str, time_class: str, r: Rating) -> dict:
    return {"player_id": pid, "time_class": time_class, "rating": r.rating, "rd": r.rd,
            "vol": r.vol, "games": r.games, "wins": r.wins, "losses": r.losses, "draws": r.draws}


def _upsert(table, row: dict, keys: list[str]):
    stmt = pg_insert(table).values(**row)
    return stmt.on_conflict_do_update(
        index_elements=keys, set_={k: v for k, v in row.items() if k not in keys}
    )


def _bot_to_move(row, state: GameState) -> bool:
    mover = row["p1_id"] if state.to_move == 1 else row["p2_id"]
    return row["status"] == "active" and row["mode"] == "bot" and (mover or "").startswith("bot")


def _notify_expr(kind: str, **data):
    """`pg_notify(...)` à glisser dans le RETURNING d'une écriture (un aller-retour de moins)."""
    return func.pg_notify(CHANNEL, json.dumps({"k": kind, "o": INSTANCE, **data}))


def replay(heights, move_limit: int, records: list[MoveRecord], winner, reason, setup: str = "classic") -> list[GameState]:
    """Reconstruit tous les états d'une partie à partir de sa mise en place et de ses coups."""
    states = [new_game(tuple(heights), move_limit, setup)]
    for r in records:
        move = Move(r.piece_id, r.kind, r.to, tuple(r.path), 0, r.special)
        states.append(apply_move(states[-1], move))
    if reason in OFF_BOARD_REASONS and not states[-1].over:
        states[-1] = end_game(states[-1], winner, reason)
    return states


class Store:
    def __init__(self) -> None:
        self.engine: AsyncEngine | None = None
        self.games: OrderedDict[str, Game] = OrderedDict()
        self.players: OrderedDict[str, Player] = OrderedDict()
        self.sessions: dict[str, Session] = {}
        self._legends: dict[str, tuple[float, set[str]]] = {}
        self._open_tx: dict[str, AsyncConnection] = {}
        self._loading: dict[str, asyncio.Task] = {}
        self._dsn: tuple[str, object] | None = None
        self._listen_task: asyncio.Task | None = None
        self._touch_queue: asyncio.Queue | None = None
        self._touch_task: asyncio.Task | None = None
        self.listening = asyncio.Event()
        # Abonnés aux notifications (hub temps réel, réveil des workers…).
        self.subscribers: list = []
        # Appelés DANS la transaction quand une manche de match se termine (`matches.py`).
        self.round_hooks: list = []

    # --- Cycle de vie ------------------------------------------------------------------

    async def start(self, settings) -> None:
        """Connexion, migrations, écoute des notifications, bots en base."""
        self.engine = create_async_engine(
            # Petit pool : N instances × (5 + 5) + 1 connexion d'écoute chacune.
            settings.sqlalchemy_url, pool_pre_ping=True, pool_size=5, max_overflow=5,
            connect_args=settings.db_connect_args,
        )
        # Lampion suspend la base au repos : son réveil peut refuser les premières
        # connexions. On réessaie au lieu de faire échouer le démarrage.
        for attempt in range(STARTUP_RETRIES):
            try:
                await migrate(self.engine)
                break
            except (OSError, asyncpg.PostgresError, SQLAlchemyError) as exc:
                if attempt == STARTUP_RETRIES - 1:
                    raise
                log.warning("base indisponible (%s), nouvel essai", exc.__class__.__name__)
                await asyncio.sleep(min(2 ** attempt, 10))
        url = settings.sqlalchemy_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        self._dsn = (url, settings.db_connect_args.get("ssl"))
        self.listening.clear()
        self._listen_task = asyncio.get_running_loop().create_task(self._listen())
        self._touch_queue = asyncio.Queue()
        self._touch_task = asyncio.get_running_loop().create_task(self._toucher())
        await asyncio.wait_for(self.listening.wait(), timeout=30)
        log.info("Postgres actif (instance %s)", INSTANCE)

    async def stop(self) -> None:
        if self._touch_queue is not None:
            await self._touch_queue.join()
        for task in (self._touch_task, self._listen_task):
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        if self.engine:
            await self.engine.dispose()
        self.engine = None

    def clear_caches(self) -> None:
        self.games.clear()
        self.players.clear()
        self.sessions.clear()
        self._legends.clear()

    # --- Notifications (LISTEN / NOTIFY) -----------------------------------------------

    async def _listen(self) -> None:
        """Connexion dédiée à l'écoute du canal, reconnectée en cas de coupure."""
        assert self._dsn
        dsn, ssl = self._dsn
        while True:
            conn = None
            try:
                conn = await asyncpg.connect(dsn, ssl=ssl)
                await conn.add_listener(CHANNEL, self._on_notify)
                if self.listening.is_set():  # reconnexion : des évènements ont pu manquer
                    self._broadcast({"k": "reconnect"})
                self.listening.set()
                while True:  # garde la connexion vivante et détecte une coupure
                    await asyncio.sleep(30)
                    await conn.fetchval("select 1")
            except asyncio.CancelledError:
                raise
            except Exception:
                log.warning("écoute Postgres interrompue, reconnexion", exc_info=True)
                # Pendant la coupure on a pu rater des notifications : on vide les caches.
                self.clear_caches()
                await asyncio.sleep(1)
            finally:
                if conn is not None:
                    with contextlib.suppress(Exception):
                        await conn.close()

    def _on_notify(self, _conn, _pid, _channel, payload: str) -> None:
        try:
            ev = json.loads(payload)
        except ValueError:
            return
        mine = ev.get("o") == INSTANCE
        kind = ev.get("k")
        if kind == "game" and not mine:
            g = self.games.get(ev["id"])
            if g is not None and g.version < ev.get("v", 0):
                self.games.pop(ev["id"], None)
        elif kind == "player" and not mine:
            for pid in ev.get("ids", []):
                self.players.pop(pid, None)
        elif kind == "sessions" and not mine:
            pid, th = ev.get("pid"), ev.get("th")
            for key in [k for k, s in self.sessions.items() if k == th or (pid and s.player_id == pid)]:
                self.sessions.pop(key, None)
        self._broadcast(ev)

    def _broadcast(self, ev: dict) -> None:
        for fn in self.subscribers:
            try:
                fn(ev)
            except Exception:
                log.exception("abonné de notification en erreur")

    async def notify(self, conn: AsyncConnection, kind: str, **data) -> None:
        """Émise dans la transaction : délivrée à toutes les instances au COMMIT."""
        payload = json.dumps({"k": kind, "o": INSTANCE, **data})
        await conn.execute(text("SELECT pg_notify(:ch, :p)"), {"ch": CHANNEL, "p": payload})

    # --- Écritures « au passage » (non critiques : dernière visite, session utilisée) ---

    def _touch(self, stmt) -> None:
        if self._touch_queue is not None:
            self._touch_queue.put_nowait(stmt)

    async def _toucher(self) -> None:
        assert self._touch_queue is not None
        while True:
            batch = [await self._touch_queue.get()]
            while not self._touch_queue.empty() and len(batch) < 100:
                batch.append(self._touch_queue.get_nowait())
            try:
                async with self.engine.begin() as conn:
                    for stmt in batch:
                        await conn.execute(stmt)
            except Exception:
                log.warning("écriture de présence échouée", exc_info=True)
            for _ in batch:
                self._touch_queue.task_done()

    async def flush(self) -> None:
        if self._touch_queue is not None:
            await self._touch_queue.join()

    # --- Joueurs -----------------------------------------------------------------------

    async def ensure_bots(self, levels: dict) -> None:
        """Joueurs bots (`bot.LEVELS`) et leur classement de départ contre les joueurs."""
        from app.services.gametypes import BOT_CLASS, BOT_START_RD

        async with self.engine.begin() as conn:
            for level, lv in levels.items():
                # Le nom suit `bot.LEVELS` (un bot renommé l'est aussi en base).
                await conn.execute(pg_insert(db.players).values(
                    id=f"bot{level}", name=lv.name, is_bot=True, created_at=time.time(),
                    last_seen=time.time()).on_conflict_do_update(index_elements=["id"], set_={"name": lv.name}))
                await conn.execute(pg_insert(db.ratings).values(**_rating_row(
                    f"bot{level}", BOT_CLASS, Rating(rating=lv.start_rating, rd=BOT_START_RD))).on_conflict_do_nothing())

    async def create_player(self, name: str) -> tuple[Player, str]:
        """Nouvel invité + sa première session, en une transaction."""
        player = Player(id=_id(10), name=name)
        async with self.engine.begin() as conn:
            await conn.execute(pg_insert(db.players).values(**_player_row(player)))
            token = await self._insert_session(conn, player.id)
        self._cache_player_obj(player)
        return player, token

    async def save_player(self, p: Player) -> None:
        """Pseudo, email, mot de passe… : écrit tout de suite, invalide les autres caches."""
        p.seen_saved = time.time()
        async with self.engine.begin() as conn:
            await conn.execute(_upsert(db.players, _player_row(p), ["id"]))
            await self.notify(conn, "player", ids=[p.id])

    def _cache_player_obj(self, p: Player) -> Player:
        self.players[p.id] = p
        self.players.move_to_end(p.id)
        while len(self.players) > MAX_CACHED_PLAYERS:
            self.players.popitem(last=False)
        return p

    async def get_player(self, pid: str | None) -> Player | None:
        if not pid:
            return None
        p = self.players.get(pid)
        if p is not None:
            return p
        async with self.engine.connect() as conn:
            row = (await conn.execute(select(db.players).where(db.players.c.id == pid))).mappings().first()
            if row is None:
                return None
            rows = (await conn.execute(select(db.ratings).where(db.ratings.c.player_id == pid))).mappings().all()
        return self._cache_player(row, rows)

    def _cache_player(self, row, rating_rows) -> Player:
        p = Player(id=row["id"], name=row["name"], created_at=row["created_at"],
                   last_seen=row["last_seen"], is_bot=row["is_bot"], email=row["email"],
                   password_hash=row["password_hash"], seen_saved=time.time(), country=row["country"],
                   email_verified_at=row["email_verified_at"])
        for r in rating_rows:
            p.ratings[r["time_class"]] = Rating(r["rating"], r["rd"], r["vol"], r["games"],
                                                r["wins"], r["losses"], r["draws"])
        return self._cache_player_obj(p)

    async def player_by_email(self, email: str) -> Player | None:
        async with self.engine.connect() as conn:
            pid = (await conn.execute(select(db.players.c.id).where(db.players.c.email == email))).scalar()
        return await self.get_player(pid)

    async def email_taken(self, email: str) -> bool:
        return await self.player_by_email(email) is not None

    # --- Sessions ----------------------------------------------------------------------

    async def _insert_session(self, conn: AsyncConnection, player_id: str) -> str:
        token = secrets.token_urlsafe(32)
        th = hash_token(token)
        now = time.time()
        await conn.execute(pg_insert(db.sessions).values(
            token_hash=th, player_id=player_id, created_at=now, last_used=now))
        self.sessions[th] = Session(player_id, now, now)
        return token

    async def new_session(self, player: Player) -> str:
        async with self.engine.begin() as conn:
            return await self._insert_session(conn, player.id)

    async def end_session(self, token: str) -> None:
        th = hash_token(token)
        self.sessions.pop(th, None)
        async with self.engine.begin() as conn:
            await conn.execute(delete(db.sessions).where(db.sessions.c.token_hash == th))
            await self.notify(conn, "sessions", th=th)

    async def end_sessions_of(self, player_id: str, keep_token: str | None = None) -> None:
        """Déconnecte un joueur de tous ses appareils (sauf, éventuellement, le courant)."""
        keep = hash_token(keep_token) if keep_token else None
        for th in [th for th, s in self.sessions.items() if s.player_id == player_id and th != keep]:
            del self.sessions[th]
        c = db.sessions.c
        stmt = delete(db.sessions).where(c.player_id == player_id)
        if keep:
            stmt = stmt.where(c.token_hash != keep)
        async with self.engine.begin() as conn:
            await conn.execute(stmt)
            await self.notify(conn, "sessions", pid=player_id)

    async def player_by_token(self, token: str) -> Player | None:
        if not token:
            return None
        th = hash_token(token)
        now = time.time()
        sess = self.sessions.get(th)
        if sess is None:
            c = db.sessions.c
            async with self.engine.connect() as conn:
                row = (await conn.execute(
                    select(c.player_id, c.created_at, c.last_used).where(c.token_hash == th))).first()
            if row is None:
                return None
            sess = Session(row[0], row[2] or row[1], now)
            self.sessions[th] = sess
        if now - sess.last_used > SESSION_TTL_S:
            await self.end_session(token)  # expirée : le relais du front recrée un invité
            return None
        sess.last_used = now
        if now - sess.saved > SESSION_TOUCH_S:
            sess.saved = now
            self._touch(update(db.sessions).where(db.sessions.c.token_hash == th).values(last_used=now))
        player = await self.get_player(sess.player_id)
        if player:
            player.last_seen = now
            if now - player.seen_saved > SEEN_PERSIST_S:
                player.seen_saved = now
                self._touch(update(db.players).where(db.players.c.id == player.id).values(last_seen=now))
        return player

    # --- Réinitialisation du mot de passe ------------------------------------------------

    async def create_reset(self, player: Player) -> str:
        """Nouveau lien de réinitialisation ; les précédents du joueur sont annulés."""
        token = secrets.token_urlsafe(32)
        now = time.time()
        async with self.engine.begin() as conn:
            await conn.execute(delete(db.password_resets).where(db.password_resets.c.player_id == player.id))
            await conn.execute(pg_insert(db.password_resets).values(
                token_hash=hash_token(token), player_id=player.id, created_at=now,
                expires_at=now + RESET_TTL_S))
        return token

    async def consume_reset(self, token: str) -> Player | None:
        """Valide un lien (non expiré) et le détruit : usage unique, même entre instances."""
        if not token:
            return None
        r = db.password_resets.c
        async with self.engine.begin() as conn:
            row = (await conn.execute(
                delete(db.password_resets).where(r.token_hash == hash_token(token))
                .returning(r.player_id, r.expires_at))).first()
        if row is None or row[1] < time.time():
            return None
        self.players.pop(row[0], None)  # relu frais (mot de passe sur le point de changer)
        return await self.get_player(row[0])

    async def create_verification(self, player: Player) -> str:
        """Nouveau lien de confirmation de l'adresse actuelle ; les précédents sont annulés."""
        token = secrets.token_urlsafe(32)
        now = time.time()
        v = db.email_verifications
        async with self.engine.begin() as conn:
            await conn.execute(delete(v).where(v.c.player_id == player.id))
            await conn.execute(pg_insert(v).values(
                token_hash=hash_token(token), player_id=player.id, email=player.email, created_at=now,
                expires_at=now + VERIFY_TTL_S))
        return token

    async def consume_verification(self, token: str) -> Player | None:
        """Confirme l'adresse visée par le lien (usage unique), si c'est toujours celle du
        compte et que le lien n'a pas expiré."""
        if not token:
            return None
        v = db.email_verifications.c
        async with self.engine.begin() as conn:
            row = (await conn.execute(
                delete(db.email_verifications).where(v.token_hash == hash_token(token))
                .returning(v.player_id, v.email, v.expires_at))).first()
        if row is None or row[2] < time.time():
            return None
        self.players.pop(row[0], None)  # relu frais
        player = await self.get_player(row[0])
        if player is None or player.email != row[1]:
            return None
        if player.email_verified_at is None:
            player.email_verified_at = time.time()
            await self.save_player(player)
        return player

    # --- Parties : lecture -------------------------------------------------------------

    def _cache_game(self, g: Game) -> None:
        self.games[g.id] = g
        self.games.move_to_end(g.id)
        while len(self.games) > MAX_CACHED_GAMES:
            self.games.popitem(last=False)

    async def _load_game(self, conn: AsyncConnection, row) -> Game:
        mrows = (await conn.execute(
            select(db.moves).where(db.moves.c.game_id == row["id"]).order_by(db.moves.c.ply)
        )).mappings().all()
        records = [MoveRecord(m["ply"], m["side"], m["piece_id"], m["kind"], m["special"],
                              m["frm"], m["to"], tuple(m["path"]), m["notation"], m["combat"],
                              m["captured_id"], m["remaining_ms"]) for m in mrows]
        setup = row["setup"] or "classic"
        states = replay(row["heights"], row["move_limit"], records, row["winner"], row["reason"], setup)
        return Game(
            id=row["id"], mode=row["mode"], terrain_mode=row["terrain_mode"], seed=row["seed"],
            players=[row["p1_id"], row["p2_id"]], created_by=row["created_by"], states=states,
            bot_level=row["bot_level"], initial_ms=row["initial_ms"],
            increment_ms=row["increment_ms"], remaining=list(row["remaining"]),
            turn_started_at=row["turn_started_at"], moves=records, status=row["status"],
            version=row["version"], rated=row["rated"], time_class=row["time_class"],
            draw_offer=row["draw_offer"], rematch_offer=row["rematch_offer"],
            rematch_id=row["rematch_id"], rating_before=row["rating_before"],
            rating_after=row["rating_after"], created_at=row["created_at"],
            ended_at=row["ended_at"], analysis=row["analysis"], rank_change=row["rank_change"],
            deadline_at=row["deadline_at"],
            match_id=row["match_id"], round=row["round"], setup=setup,
            # Au bot de jouer : une tâche `bot_jobs` existe (cf. `_write_bot_job`).
            bot_due_at=row["turn_started_at"] if _bot_to_move(row, states[-1]) else None,
        )

    async def _ensure_players(self, g: Game) -> None:
        for pid in {g.players[0], g.players[1], g.created_by}:
            await self.get_player(pid)

    async def get_game(self, gid: str, known_version: int | None = None) -> Game | None:
        """Partie à jour : le cache n'est utilisé que si sa version est celle de la base."""
        cached = self.games.get(gid)
        if cached is not None and known_version is not None and cached.version >= known_version:
            await self._ensure_players(cached)
            return cached
        async with self.engine.connect() as conn:
            if cached is not None:
                v = (await conn.execute(select(db.games.c.version).where(db.games.c.id == gid))).scalar()
                if v is None:
                    self.games.pop(gid, None)
                    return None
                if v == cached.version:
                    await self._ensure_players(cached)
                    return cached
        # Plusieurs flux d'une même partie se réveillent ensemble : un seul chargement.
        task = self._loading.get(gid)
        if task is None:
            task = asyncio.get_running_loop().create_task(self._fetch_game(gid))
            self._loading[gid] = task
            task.add_done_callback(lambda _t: self._loading.pop(gid, None))
        game = await asyncio.shield(task)
        if game is not None and known_version is not None and game.version < known_version:
            game = await self._fetch_game(gid)  # chargement commencé avant cette version
        if game is not None:
            await self._ensure_players(game)
        return game

    async def _fetch_game(self, gid: str) -> Game | None:
        async with self.engine.connect() as conn:
            row = (await conn.execute(select(db.games).where(db.games.c.id == gid))).mappings().first()
            if row is None:
                return None
            game = await self._load_game(conn, row)
        cached = self.games.get(gid)
        if cached is None or cached.version <= game.version:
            self._cache_game(game)
        return game

    # --- Parties : écriture ------------------------------------------------------------

    @contextlib.asynccontextmanager
    async def locked_game(self, gid: str, skip_locked: bool = False):
        """Partie verrouillée pour modification. Rend une COPIE : en cas d'erreur la
        transaction est annulée et le cache reste intact. `None` si la partie n'existe pas
        (ou est déjà verrouillée ailleurs, avec `skip_locked`)."""
        async with self.engine.begin() as conn:
            q = select(db.games).where(db.games.c.id == gid).with_for_update(skip_locked=skip_locked)
            row = (await conn.execute(q)).mappings().first()
            if row is None:
                yield None
                return
            cached = self.games.get(gid)
            game = cached.clone() if cached is not None and cached.version == row["version"] \
                else await self._load_game(conn, row)
            game.deadline_at = row["deadline_at"]  # l'échéance en base fait foi
            await self._ensure_players(game)
            before = (game.version, len(game.moves), game.status, game.bot_due_at is not None)
            self._open_tx[gid] = conn
            try:
                yield game
            finally:
                self._open_tx.pop(gid, None)
            if game.version != before[0]:
                await self._persist(conn, game, *before[1:])
        if game.version != before[0] or gid not in self.games:
            self._cache_game(game)

    def _conn_of(self, game: Game) -> AsyncConnection:
        """Transaction de `locked_game` en cours sur cette partie."""
        return self._open_tx[game.id]

    async def insert_game(self, game: Game, conn: AsyncConnection | None = None) -> None:
        """Nouvelle partie (dans la transaction `conn` si fournie : matchmaking)."""
        if conn is None:
            async with self.engine.begin() as conn:
                await self._insert_game(conn, game)
        else:
            await self._insert_game(conn, game)
        self._cache_game(game)

    # Chaque aller-retour vers la base compte (un coup = une transaction) : les
    # notifications partent dans le RETURNING de l'écriture qu'elles accompagnent.

    async def _insert_game(self, conn: AsyncConnection, game: Game) -> None:
        await conn.execute(pg_insert(db.games).values(**_game_row(game)).returning(
            _notify_expr("game", id=game.id, v=game.version, d=game.deadline_at)))
        await self._write_bot_job(conn, game, had_job=False)

    async def _write_bot_job(self, conn: AsyncConnection, g: Game, had_job: bool) -> None:
        if g.bot_due_at is not None and g.status == "active":
            await conn.execute(_upsert(db.bot_jobs, {
                "game_id": g.id, "version": g.version, "run_after": g.bot_due_at, "claimed_at": None,
            }, ["game_id"]).returning(_notify_expr("bot", id=g.id, t=g.bot_due_at)))
        elif had_job:
            await conn.execute(delete(db.bot_jobs).where(db.bot_jobs.c.game_id == g.id))

    async def _persist(self, conn: AsyncConnection, g: Game, n_moves_before: int, status_before: str,
                       had_job: bool) -> None:
        new_moves = [_move_row(g.id, rec) for rec in g.moves[n_moves_before:]]
        if new_moves:
            await conn.execute(pg_insert(db.moves), new_moves)
        if status_before != "finished" and g.status == "finished" and g.rated and all(g.players):
            await self._apply_ratings(conn, g)
        elif status_before != "finished" and g.status == "finished" and g.mode == "bot" and g.timed:
            await self._rate_bot(conn, g)
        await conn.execute(update(db.games).where(db.games.c.id == g.id).values(**_game_row(g)).returning(
            _notify_expr("game", id=g.id, v=g.version, d=g.deadline_at)))
        await self._write_bot_job(conn, g, had_job)
        if g.match_id and status_before not in ("finished", "aborted") and g.status in ("finished", "aborted"):
            for hook in self.round_hooks:
                await hook(conn, g)

    async def _apply_ratings(self, conn: AsyncConnection, g: Game) -> None:
        s1 = 0.5 if g.state.winner is None else 1.0 if g.state.winner == 1 else 0.0
        g.rating_before, g.rating_after, g.rank_change = await self.rate_pair(conn, list(g.players), g.time_class, s1)

    async def _rate_bot(self, conn: AsyncConnection, g: Game) -> None:
        """Partie avec pendule contre un bot : seul le classement du BOT bouge (Glicko-2,
        face au classement du joueur dans cette cadence) ; le joueur reste non classé. Pas
        de partie trop courte, et au plus `BOT_DAILY_CAP` parties comptées par joueur et par
        bot sur 24 h : perdre exprès en boucle ne fait pas s'effondrer un bot."""
        from app.services import rating
        from app.services.gametypes import BOT_CLASS, BOT_DAILY_CAP, BOT_MIN_PLY

        if g.state.ply < BOT_MIN_PLY:
            return
        bot_id = f"bot{g.bot_level}"
        if bot_id not in g.players:
            return
        bot_side = g.players.index(bot_id)
        human = g.players[1 - bot_side]
        if human is None or human == bot_id:
            return
        c = db.games.c
        recent = (await conn.execute(select(func.count()).select_from(db.games).where(
            c.id != g.id, c.mode == "bot", c.status == "finished", c.initial_ms.is_not(None),
            c.ply >= BOT_MIN_PLY, c.created_at > time.time() - 86_400,
            or_(and_(c.p1_id == human, c.p2_id == bot_id), and_(c.p1_id == bot_id, c.p2_id == human))))).scalar()
        if recent >= BOT_DAILY_CAP:
            return
        r = db.ratings.c
        row = (await conn.execute(select(db.ratings).where(
            r.player_id == bot_id, r.time_class == BOT_CLASS).with_for_update())).mappings().first()
        if row is None:
            return  # bot inconnu (ensure_bots pas passé) : rien à mettre à jour
        bot_r = Rating(row["rating"], row["rd"], row["vol"], row["games"], row["wins"], row["losses"], row["draws"])
        h = (await conn.execute(select(db.ratings).where(
            r.player_id == human, r.time_class == g.time_class))).mappings().first()
        human_r = Rating(h["rating"], h["rd"], h["vol"]) if h else Rating()
        winner = g.state.winner
        score = 0.5 if winner is None else 1.0 if winner == bot_side + 1 else 0.0
        new = rating.update(bot_r, human_r, score)
        await conn.execute(_upsert(db.ratings, _rating_row(bot_id, BOT_CLASS, new), ["player_id", "time_class"]))
        if bot_id in self.players:
            self.players[bot_id].ratings[BOT_CLASS] = new
        await self.notify(conn, "player", ids=[bot_id])

    async def rate_pair(self, conn: AsyncConnection, pids: list[str], time_class: str,
                        s1: float) -> tuple[list[float], list[float], list[dict]]:
        """Glicko-2 sur les classements LUS EN BASE et verrouillés : deux parties (ou
        matchs) qui se terminent en même temps sur deux instances ne s'écrasent pas.
        `s1` = score du premier joueur (1, 0,5 ou 0). Renvoie avant / après / rangs."""
        from app.services import ranks, rating

        r = db.ratings.c
        current: dict[str, Rating] = {}
        for pid in sorted(set(pids)):  # ordre fixe : pas d'interblocage
            await conn.execute(pg_insert(db.ratings).values(
                **_rating_row(pid, time_class, Rating())).on_conflict_do_nothing())
            row = (await conn.execute(
                select(db.ratings).where(r.player_id == pid, r.time_class == time_class).with_for_update()
            )).mappings().first()
            current[pid] = Rating(row["rating"], row["rd"], row["vol"], row["games"],
                                  row["wins"], row["losses"], row["draws"])
        r1, r2 = current[pids[0]], current[pids[1]]
        n1, n2 = rating.update(r1, r2, s1), rating.update(r2, r1, 1 - s1)
        for pid, new in ((pids[0], n1), (pids[1], n2)):
            await conn.execute(_upsert(db.ratings, _rating_row(pid, time_class, new), ["player_id", "time_class"]))
            if pid in self.players:
                self.players[pid].ratings[time_class] = new
        legends = await self.refresh_legends(time_class)
        rank_change = [
            {"before": ranks.rank_from(before.rating, before.games, legend=pid in legends),
             "after": ranks.rank_from(after.rating, after.games, legend=pid in legends)}
            for pid, before, after in ((pids[0], r1, n1), (pids[1], r2, n2))
        ]
        self._legends.pop(time_class, None)  # le top 3 a pu changer
        await self.notify(conn, "player", ids=pids)
        return [r1.rating, r2.rating], [n1.rating, n2.rating], rank_change

    async def set_analysis(self, gid: str, analysis: dict) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(update(db.games).where(db.games.c.id == gid).values(analysis=analysis))
            await conn.execute(delete(db.analysis_jobs).where(db.analysis_jobs.c.game_id == gid))
            await self.notify(conn, "analysis", id=gid)
        if gid in self.games:
            self.games[gid].analysis = analysis

    async def get_analysis(self, gid: str) -> dict | None:
        async with self.engine.connect() as conn:
            return (await conn.execute(select(db.games.c.analysis).where(db.games.c.id == gid))).scalar()

    def new_game_id(self) -> str:
        return _id(8)

    # --- Listes, classements -----------------------------------------------------------

    async def games_of(self, pid: str, online_only: bool = False, limit: int = 30) -> list[GameSummary]:
        c = db.games.c
        q = select(db.games).where(or_(c.p1_id == pid, c.p2_id == pid, c.created_by == pid))
        if online_only:
            q = q.where(c.mode == "online")
        q = q.order_by(c.created_at.desc()).limit(limit)
        async with self.engine.connect() as conn:
            rows = (await conn.execute(q)).mappings().all()
        out = [GameSummary(r["id"], r["mode"], r["status"], r["terrain_mode"], r["initial_ms"],
                           r["increment_ms"], [r["p1_id"], r["p2_id"]], r["created_by"], r["winner"],
                           r["reason"], (r["score1"], r["score2"]), r["ply"], r["created_at"]) for r in rows]
        for s in out:
            for p in s.players:
                await self.get_player(p)
        return out

    async def leaderboard(self, time_class: str, limit: int = 100) -> list[tuple[Player, Rating]]:
        r, p = db.ratings.c, db.players.c
        async with self.engine.connect() as conn:
            rows = (await conn.execute(
                select(db.ratings, p.name, p.is_bot, p.email, p.country)
                .join(db.players, p.id == r.player_id)
                .where(r.time_class == time_class, r.games > 0, p.is_bot.is_(False))
                .order_by(r.rating.desc()).limit(limit))).mappings().all()
        out = []
        for row in rows:
            rt = Rating(row["rating"], row["rd"], row["vol"], row["games"], row["wins"], row["losses"], row["draws"])
            player = self.players.get(row["player_id"]) or Player(
                id=row["player_id"], name=row["name"], is_bot=row["is_bot"], email=row["email"],
                country=row["country"])
            player.ratings[time_class] = rt
            out.append((player, rt))
        return out

    def legends(self, time_class: str) -> set[str]:
        """Légendes en cache (rafraîchies au plus toutes les LEGENDS_TTL_S)."""
        hit = self._legends.get(time_class)
        return hit[1] if hit else set()

    async def refresh_legends(self, time_class: str, force: bool = False) -> set[str]:
        """Les 3 premiers d'une cadence, s'ils sont Maîtres."""
        from app.services.ranks import LEGEND_SLOTS, MASTER, PLACEMENT_GAMES

        hit = self._legends.get(time_class)
        if hit and not force and time.time() - hit[0] < LEGENDS_TTL_S:
            return hit[1]
        rows = await self.leaderboard(time_class, limit=LEGEND_SLOTS)
        ids = {p.id for p, r in rows if r.rating >= MASTER.floor and r.games >= PLACEMENT_GAMES}
        self._legends[time_class] = (time.time(), ids)
        return ids

    async def refresh_all_legends(self) -> None:
        from app.services.gametypes import RATED_CLASSES

        for tc in RATED_CLASSES:
            await self.refresh_legends(tc)

    async def rating_history(self, pid: str, time_class: str, limit: int = 300) -> list[dict]:
        """Parties classées terminées d'un joueur dans une cadence, de la plus ancienne à la
        plus récente, avec son classement avant/après chacune."""
        c = db.games.c
        q = (select(c.id, c.p1_id, c.p2_id, c.rating_before, c.rating_after, c.winner, c.ended_at)
             .where(c.rated.is_(True), c.status == "finished", c.time_class == time_class,
                    or_(c.p1_id == pid, c.p2_id == pid), c.rating_after.is_not(None))
             .order_by(c.ended_at.desc()).limit(limit))
        async with self.engine.connect() as conn:
            rows = list((await conn.execute(q)).mappings())
        out = []
        for r in sorted(rows, key=lambda r: r["ended_at"] or 0):
            side = 1 if r["p1_id"] == pid else 2
            opp = await self.get_player(r["p2_id"] if side == 1 else r["p1_id"])
            out.append({
                "gameId": r["id"],
                "t": r["ended_at"],
                "before": round(r["rating_before"][side - 1]),
                "rating": round(r["rating_after"][side - 1]),
                "result": "draw" if r["winner"] is None else "win" if r["winner"] == side else "loss",
                "opponent": opp.name if opp else "?",
            })
        return out

    async def live_games(self, limit: int = 30) -> list[dict]:
        """Parties en ligne en cours, triées par niveau (somme des classements des deux
        joueurs dans la cadence de la partie), puis les plus récentes."""
        g = db.games.c
        r1, r2 = db.ratings.alias("r1"), db.ratings.alias("r2")
        strength = func.coalesce(r1.c.rating, 1500) + func.coalesce(r2.c.rating, 1500)
        q = (select(g.id, g.p1_id, g.p2_id, g.time_class, g.initial_ms, g.increment_ms, g.ply,
                    g.terrain_mode, g.rated, g.created_at, g.match_id, g.round)
             .select_from(db.games
                          .outerjoin(r1, (r1.c.player_id == g.p1_id) & (r1.c.time_class == g.time_class))
                          .outerjoin(r2, (r2.c.player_id == g.p2_id) & (r2.c.time_class == g.time_class)))
             .where(g.status == "active", g.mode == "online")
             .order_by(strength.desc(), g.created_at.desc()).limit(limit))
        async with self.engine.connect() as conn:
            return [dict(r) for r in (await conn.execute(q)).mappings()]

    async def counts(self) -> dict:
        """Joueurs vus récemment et parties en ligne en cours (toutes instances)."""
        now = time.time()
        p, g = db.players.c, db.games.c
        async with self.engine.connect() as conn:
            online = (await conn.execute(select(func.count()).select_from(db.players).where(
                p.is_bot.is_(False), p.last_seen > now - ONLINE_WINDOW_S))).scalar()
            playing = (await conn.execute(select(func.count()).select_from(db.games).where(
                g.status == "active", g.mode == "online"))).scalar()
        return {"online": online or 0, "playing": playing or 0}

    # --- Ménage ------------------------------------------------------------------------

    async def maintenance(self) -> dict[str, int]:
        """Sessions expirées, liens périmés, invités jamais revenus et sans partie."""
        now = time.time()
        s, g, pl = db.sessions.c, db.games.c, db.players.c
        async with self.engine.begin() as conn:
            r = await conn.execute(delete(db.sessions).where(
                func.coalesce(s.last_used, s.created_at) < now - SESSION_TTL_S))
            stats = {"sessions": r.rowcount}
            await conn.execute(delete(db.password_resets).where(db.password_resets.c.expires_at < now))
            await conn.execute(delete(db.email_verifications).where(db.email_verifications.c.expires_at < now))
            has_game = exists().where(or_(g.p1_id == pl.id, g.p2_id == pl.id, g.created_by == pl.id))
            r = await conn.execute(
                delete(db.players)
                .where(pl.email.is_(None), pl.is_bot.is_(False), pl.last_seen < now - GUEST_TTL_S, ~has_game)
                .returning(pl.id))
            deleted = [row[0] for row in r]
            if deleted:
                await self.notify(conn, "player", ids=deleted)
        stats["guests"] = len(deleted)
        for pid in deleted:
            self.players.pop(pid, None)
        for th in [th for th, sess in self.sessions.items() if sess.player_id in set(deleted)]:
            del self.sessions[th]
        return stats


async def migrate(engine: AsyncEngine) -> None:
    """Applique les migrations Alembic (paquet `migrations`) jusqu'à la dernière version.

    Plusieurs instances peuvent démarrer ensemble : un verrou consultatif Postgres fait
    passer les migrations une instance à la fois.
    """
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    import migrations

    cfg = Config()
    cfg.set_main_option("script_location", str(Path(migrations.__file__).parent))

    def upgrade(sync_conn) -> None:
        cfg.attributes["connection"] = sync_conn
        command.upgrade(cfg, "head")

    async with engine.begin() as conn:
        await conn.execute(text("SELECT pg_advisory_xact_lock(727274)"))
        await conn.run_sync(upgrade)


store = Store()
