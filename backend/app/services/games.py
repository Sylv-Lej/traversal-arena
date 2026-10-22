"""Cycle de vie des parties : création, coups, pendules, fin, bot, revanche.

Sans état : chaque modification passe par `store.locked_game()` (transaction + verrou de
ligne). Pendules et bot ne sont plus des tâches en mémoire mais des échéances en base
(`games.deadline_at`, table `bot_jobs`) traitées par les workers (`workers.py`) de
n'importe quelle instance.
"""

import asyncio
import logging
import random
import time

from sqlalchemy import delete

from app import bot, db
from app.engine import (
    IllegalMove,
    apply_move,
    end_game,
    find_move,
    generate_terrain,
    legal_moves,
    new_game,
    notation,
)
from app.services.gametypes import CASUAL, GAME_TYPES, clock_label, clock_of
from app.services.store import Game, MoveRecord, Player, store

log = logging.getLogger("traversal.games")

# Délai max pour jouer son tout premier coup en ligne (sinon partie annulée).
FIRST_MOVE_TIMEOUT_S = 45
# Pause avant que le bot ne joue : laisse le temps à l'animation du coup précédent.
BOT_DELAY_S = 0.7

# Types jouables en partie simple (le tactique se joue en match : `matches.py`).
SINGLE_TYPES = ("bullet", "classic")


class GameError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def parse_type(game_type: str | None) -> str | None:
    """Type d'une partie simple : bullet, classique, ou None (sans pendule)."""
    if not game_type:
        return None
    if game_type == "tactic":
        raise GameError(422, "Le mode Tactique se joue en match.")
    if game_type not in SINGLE_TYPES:
        raise GameError(422, "Type de partie inconnu.")
    return game_type


def time_control_label(game: Game) -> str | None:
    return clock_label(game.initial_ms, game.increment_ms)


# --- Création --------------------------------------------------------------------------


def build_game(
    me: Player,
    mode: str,
    terrain: str = "random",
    game_type: str | None = None,
    bot_level: int | None = None,
    side: int | None = None,
    opponent_id: str | None = None,
    rated: bool | None = None,
) -> Game:
    """Construit une partie simple (pas encore en base)."""
    if mode not in ("local", "bot", "online"):
        raise GameError(422, "Mode inconnu.")
    game_type = parse_type(game_type)
    initial_ms, increment_ms = clock_of(game_type)
    is_rated = mode == "online" and initial_ms is not None and (rated if rated is not None else True)
    if is_rated:
        terrain = "random"  # en classé, la carte est toujours tirée au sort
    try:
        effective, seed, heights = generate_terrain(terrain)
    except ValueError as exc:
        raise GameError(422, str(exc)) from exc
    if side not in (1, 2):
        side = random.choice((1, 2))

    players: list[str | None] = [None, None]
    status = "active"
    if mode == "local":
        players = [me.id, me.id]
    elif mode == "bot":
        if bot_level not in bot.LEVELS:
            raise GameError(422, "Niveau de bot inconnu.")
        players[side - 1] = me.id
        players[2 - side] = f"bot{bot_level}"
    else:
        players[side - 1] = me.id
        if opponent_id:
            players[2 - side] = opponent_id
        else:
            status = "waiting"

    game = Game(
        id=store.new_game_id(),
        mode=mode,
        terrain_mode=effective,
        seed=seed,
        players=players,
        created_by=me.id,
        states=[new_game(heights)],
        bot_level=bot_level if mode == "bot" else None,
        initial_ms=initial_ms,
        increment_ms=increment_ms,
        remaining=[initial_ms or 0, initial_ms or 0],
        status=status,
        rated=is_rated,
        time_class=game_type or CASUAL,
    )
    if status == "active":
        _start_turn(game)
    return game


def build_round_game(match, red_id: str, blue_id: str, terrain: str, clock_type: str, round_no: int) -> Game:
    """Manche d'un match tactique : jamais classée seule (c'est le match qui compte)."""
    try:
        effective, seed, heights = generate_terrain(terrain)
    except ValueError as exc:
        raise GameError(422, str(exc)) from exc
    initial_ms, increment_ms = GAME_TYPES[clock_type]
    game = Game(
        id=store.new_game_id(), mode=match.mode, terrain_mode=effective, seed=seed,
        players=[red_id, blue_id], created_by=match.created_by, states=[new_game(heights)],
        bot_level=match.bot_level, initial_ms=initial_ms, increment_ms=increment_ms,
        remaining=[initial_ms, initial_ms], status="active", rated=False, time_class="tactic",
        match_id=match.id, round=round_no,
    )
    _start_turn(game)
    return game


async def create_game(me: Player, mode: str, terrain: str = "random", game_type: str | None = None,
                      bot_level: int | None = None, side: int | None = None,
                      opponent_id: str | None = None, rated: bool | None = None) -> Game:
    game = build_game(me, mode, terrain, game_type, bot_level, side, opponent_id, rated)
    await store.insert_game(game)
    await store._ensure_players(game)
    return game


class _Locked:
    """`async with _locked(gid) as game` : partie verrouillée, 404 si elle n'existe pas."""

    def __init__(self, gid: str) -> None:
        self.cm = store.locked_game(gid)

    async def __aenter__(self) -> Game:
        game = await self.cm.__aenter__()
        if game is None:
            await self.cm.__aexit__(None, None, None)
            raise GameError(404, "Partie introuvable.")
        return game

    async def __aexit__(self, *exc):
        return await self.cm.__aexit__(*exc)


_locked = _Locked


async def join_game(gid: str, me: Player) -> Game:
    async with _locked(gid) as game:
        if game.status != "waiting":
            raise GameError(409, "La partie a déjà commencé.")
        if me.id in game.players:
            raise GameError(409, "Tu es déjà dans cette partie.")
        game.players = [p if p is not None else me.id for p in game.players]
        game.status = "active"
        _changed(game, start_turn=True)
    await store._ensure_players(game)
    return game


# --- Pendule ---------------------------------------------------------------------------


def clock_running(game: Game) -> bool:
    # Comme sur chess.com : la pendule ne tourne qu'après le premier coup de chacun.
    return game.timed and game.status == "active" and game.state.ply >= 2


def remaining_now(game: Game) -> list[int]:
    out = list(game.remaining)
    if clock_running(game) and game.turn_started_at is not None:
        side = game.state.to_move
        out[side - 1] -= int((time.time() - game.turn_started_at) * 1000)
    return [max(0, v) for v in out]


def _bot_to_move(game: Game) -> bool:
    return game.mode == "bot" and (game.players[game.state.to_move - 1] or "").startswith("bot")


def _start_turn(game: Game) -> None:
    """Nouveau tour : échéance de la pendule (ou du 1er coup) et, si besoin, coup du bot."""
    now = time.time()
    game.turn_started_at = now
    game.deadline_at = None
    game.bot_due_at = None
    if game.status != "active":
        return
    if clock_running(game):
        game.deadline_at = now + game.remaining[game.state.to_move - 1] / 1000
    elif game.mode == "online" and game.state.ply < 2:
        game.deadline_at = now + FIRST_MOVE_TIMEOUT_S
    if _bot_to_move(game):
        game.bot_due_at = now + BOT_DELAY_S


async def expire(gid: str) -> bool:
    """Échéance dépassée (appelé par le balayeur) : perte au temps ou partie abandonnée.
    Ignore une partie verrouillée ailleurs (un coup en cours) : elle sera revue."""
    async with store.locked_game(gid, skip_locked=True) as game:
        if game is None or game.status != "active" or not game.deadline_at:
            return False
        if game.deadline_at > time.time():
            return False
        if clock_running(game):
            loser = game.state.to_move
            if remaining_now(game)[loser - 1] > 0:
                _start_turn_keep_clock(game)
                return False
            game.remaining[loser - 1] = 0
            _finish(game, 3 - loser, "timeout")
        elif game.mode == "online" and game.state.ply < 2:
            game.status = "aborted"
            game.ended_at = time.time()
            game.states[-1] = end_game(game.state, None, "abandon")
            _changed(game)
        else:
            game.deadline_at = None
            _changed(game)
    return True


def _start_turn_keep_clock(game: Game) -> None:
    """Échéance mal calée (horloges des instances) : on la recale sans toucher au tour."""
    game.deadline_at = (game.turn_started_at or time.time()) + game.remaining[game.state.to_move - 1] / 1000
    _changed(game)


# --- Coups -----------------------------------------------------------------------------


def _record(game: Game, move, before) -> MoveRecord:
    piece = before.piece(move.piece_id) if move.piece_id else None
    combat = None
    if move.combat:
        combat = {
            "attack": move.combat.attack,
            "defense": move.combat.defense,
            "attackTerms": [{"label": t.label, "value": t.value} for t in move.combat.attack_terms],
            "defenseTerms": [{"label": t.label, "value": t.value} for t in move.combat.defense_terms],
        }
    captured = before.occupancy().get(move.to) if move.kind == "attack" else None
    return MoveRecord(
        ply=before.ply + 1,
        side=before.to_move,
        piece_id=move.piece_id,
        kind=move.kind,
        special=move.special,
        frm=piece.sq if piece else None,
        to=move.to,
        path=move.path,
        notation=notation(before, move),
        combat=combat,
        captured_id=captured.id if captured else None,
        remaining_ms=None,
    )


def _apply(game: Game, move) -> None:
    before = game.state
    side = before.to_move
    rec = _record(game, move, before)
    if clock_running(game):
        spent = int((time.time() - (game.turn_started_at or time.time())) * 1000)
        game.remaining[side - 1] = max(0, game.remaining[side - 1] - spent) + game.increment_ms
        rec.remaining_ms = game.remaining[side - 1]
    after = apply_move(before, move)
    game.states.append(after)
    game.moves.append(rec)
    game.draw_offer = None
    if after.over:
        _finish(game, after.winner, after.reason, already_over=True)
    else:
        _changed(game, start_turn=True)


async def play(gid: str, me: Player | None, piece_id: str, kind: str, to: int | None,
               version: int | None) -> Game:
    timed_out = False
    async with _locked(gid) as game:
        if game.status != "active":
            raise GameError(409, "La partie n'est pas en cours.")
        if version is not None and version != game.version:
            raise GameError(409, "Position périmée : rafraîchis la partie.")
        side = game.state.to_move
        if me is None or side not in game.sides_of(me.id):
            raise GameError(403, "Ce n'est pas ton tour.")
        if clock_running(game) and remaining_now(game)[side - 1] <= 0:
            game.remaining[side - 1] = 0
            _finish(game, 3 - side, "timeout")  # enregistré, puis on répond 409
            timed_out = True
        else:
            try:
                move = find_move(game.state, piece_id, kind, to)
            except IllegalMove as exc:
                raise GameError(422, str(exc)) from exc
            _apply(game, move)
    if timed_out:
        raise GameError(409, "Temps écoulé.")
    return game


async def bot_turn(gid: str, version: int) -> None:
    """Tâche `bot_jobs` réclamée par un worker : calcule et joue le coup du bot."""
    game = await store.get_game(gid, known_version=version)
    if game is None or game.version != version or game.status != "active" or not _bot_to_move(game):
        if game is None or game.version == version:
            async with store.engine.begin() as conn:
                await conn.execute(delete(db.bot_jobs).where(
                    db.bot_jobs.c.game_id == gid, db.bot_jobs.c.version == version))
        return  # sinon la partie a bougé : la tâche a été réécrite pour la nouvelle version
    state = game.state
    try:
        move = await asyncio.to_thread(bot.choose_move, state, game.bot_level or 3)
    except Exception:  # un bug du bot ne doit jamais figer la partie
        log.exception("bot crash, coup aléatoire")
        move = random.choice(legal_moves(state))
    async with store.locked_game(gid) as game:
        if game is None or game.version != version or game.status != "active":
            return
        _apply(game, move)


# --- Fin de partie ---------------------------------------------------------------------


def _finish(game: Game, winner: int | None, reason: str, already_over: bool = False) -> None:
    """Fin de partie. Le classement (Glicko-2) est mis à jour à l'écriture, dans la même
    transaction, sur les notes lues en base (`store._apply_ratings`)."""
    if not already_over:
        game.states[-1] = end_game(game.state, winner, reason)
    game.status = "finished"
    game.ended_at = time.time()
    game.draw_offer = None
    _changed(game)


def _changed(game: Game, start_turn: bool = False) -> None:
    """Nouvelle version de la partie : écrite et notifiée à la sortie de `locked_game`."""
    game.version += 1
    if start_turn:
        _start_turn(game)
    elif game.status != "active":
        game.deadline_at = None
        game.bot_due_at = None


async def resign(gid: str, me: Player) -> Game:
    async with _locked(gid) as game:
        sides = game.sides_of(me.id)
        if game.status != "active" or not sides:
            raise GameError(409, "Impossible d'abandonner.")
        # En local, c'est le camp au trait qui abandonne.
        side = game.state.to_move if len(sides) == 2 else sides[0]
        _finish(game, 3 - side, "resign")
    return game


async def abort(gid: str, me: Player) -> Game:
    async with _locked(gid) as game:
        if game.match_id and (game.round or 1) > 1:
            raise GameError(409, "Annulation impossible.")  # en match, on abandonne la manche
        if game.status == "waiting" and game.created_by == me.id:
            game.status = "aborted"
        elif game.status == "active" and game.sides_of(me.id) and game.state.ply < 2:
            game.status = "aborted"
        else:
            raise GameError(409, "Annulation impossible.")
        game.ended_at = time.time()
        game.states[-1] = end_game(game.state, None, "aborted")
        _changed(game)
    return game


async def draw(gid: str, me: Player, action: str) -> Game:
    async with _locked(gid) as game:
        sides = game.sides_of(me.id)
        if game.status != "active" or not sides:
            raise GameError(409, "Pas de nulle possible.")
        if game.mode == "local":
            _finish(game, None, "agreement")
        elif game.mode == "bot":
            raise GameError(409, "Le bot refuse la nulle.")
        else:
            side = sides[0]
            if action == "offer":
                if game.draw_offer == 3 - side:
                    _finish(game, None, "agreement")
                else:
                    game.draw_offer = side
                    _changed(game)
            elif action == "accept" and game.draw_offer == 3 - side:
                _finish(game, None, "agreement")
            elif action == "decline" and game.draw_offer == 3 - side:
                game.draw_offer = None
                _changed(game)
            else:
                raise GameError(409, "Aucune proposition de nulle.")
    return game


async def rematch(gid: str, me: Player) -> Game:
    """Revanche : couleurs inversées, même cadence et même type de terrain demandé."""
    new: Game | None = None
    async with _locked(gid) as game:
        if game.status not in ("finished", "aborted"):
            raise GameError(409, "La partie n'est pas terminée.")
        if game.match_id:
            raise GameError(409, "Pas de revanche pendant un match : lance un nouveau match.")
        if game.rematch_id:
            existing_id = game.rematch_id
        else:
            existing_id = None
            sides = game.sides_of(me.id)
            if not sides:
                raise GameError(403, "Tu ne joues pas cette partie.")
            tc = game.time_class if game.time_class in SINGLE_TYPES else None
            if game.mode in ("local", "bot"):
                new = build_game(me, game.mode, "random", tc, game.bot_level,
                                 side=3 - sides[0] if game.mode == "bot" else None)
            else:
                side = sides[0]
                if game.rematch_offer != 3 - side:
                    game.rematch_offer = side
                    _changed(game)
                    return game
                new = build_game(me, "online", "random", tc, side=3 - side,
                                 opponent_id=game.players[2 - side], rated=game.rated)
            # Même transaction : la revanche n'existe que si le lien vers elle est écrit.
            await store._insert_game(store._conn_of(game), new)
            game.rematch_id = new.id
            _changed(game)
    if existing_id:
        existing = await store.get_game(existing_id)
        if existing:
            return existing
        raise GameError(404, "Revanche introuvable.")
    assert new is not None
    store._cache_game(new)
    await store._ensure_players(new)
    return new
