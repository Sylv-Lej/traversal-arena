"""API HTTP. Le navigateur n'y accède jamais directement : il passe par le relais
serveur du front (`app/api/[...path]/route.ts`), qui détient la clé d'API et relaie le
jeton de session du joueur (`x-session`)."""

import asyncio
import json
import random
import re
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from revkit.auth import require_api_key
from revkit.ratelimit import RateLimiter, rate_limit

from app.bot import LEVELS
from app.engine import (
    TERRAIN_MODES,
    GameState,
    IllegalMove,
    Piece,
    apply_move,
    find_move,
    generate_terrain,
    legal_moves,
    notation,
)
from app.services import games as svc
from app.countries import normalize_country
from app.i18n import lang_of
from app.services import accounts, analysis_jobs, arena, limits, lobby, matches, ranks, spectators, training
from app.services.gametypes import BOT_CLASS, DEFAULT_CLASS, RATED_CLASSES, display_class
from app.services.realtime import hub
from app.services.store import Game, Player, store
from app.services.views import (
    match_brief,
    match_view,
    SPECTATOR_DELAY_PLIES,
    spectator_delay,
    game_summary,
    rank_json,
    game_view,
    me_json,
    move_json,
    player_json,
    position_json,
)

router = APIRouter(prefix="/api", dependencies=[Depends(require_api_key())])

# Fort trafic (chaque coup) : en mémoire, par instance — pas d'aller-retour en base.
ACTION_LIMITER = RateLimiter(limit=300, window_seconds=60)
SANDBOX_LIMITER = RateLimiter(limit=240, window_seconds=60)
_action_limit = rate_limit(ACTION_LIMITER)
_sandbox_limit = rate_limit(SANDBOX_LIMITER)
# Sensible ou coûteux : compté en base, commun à toutes les instances.
_signup_limit = limits.shared_limit("guest", 20, 60)  # création d'invités
_login_limit = limits.shared_limit("auth", 10, 60)  # connexions, mots de passe
_analysis_limit = limits.shared_limit("analysis", 20, 600)  # bilans : calcul coûteux


def reset_limiters() -> None:
    """Tests : remet les compteurs EN MÉMOIRE à zéro (ceux en base sont vidés avec elle)."""
    for limiter in (ACTION_LIMITER, SANDBOX_LIMITER):
        limiter._hits.clear()

# Pseudo d'invité : un animal de montagne, dans la langue du joueur.
ANIMALS = {
    "fr": ("Chamois", "Bouquetin", "Marmotte", "Aigle", "Lynx", "Gypaète", "Hermine",
           "Lagopède", "Isard", "Tétras", "Choucas", "Renard"),
    "en": ("Chamois", "Ibex", "Marmot", "Eagle", "Lynx", "Vulture", "Stoat",
           "Ptarmigan", "Pika", "Grouse", "Jackdaw", "Fox"),
}
NAME_RE = re.compile(r"^[\w][\w .\-']{1,18}[\w]$", re.UNICODE)


# --- Session -------------------------------------------------------------------------


async def current_player(x_session: str = Header(default="")) -> Player:
    player = await store.player_by_token(x_session)
    if player is None:
        # Code stable : le relais du front recrée alors une session invité.
        raise HTTPException(401, "session")
    await store.refresh_all_legends()  # rangs affichés : Légendes à jour (cache 30 s)
    return player


async def optional_player(x_session: str = Header(default="")) -> Player | None:
    await store.refresh_all_legends()
    return await store.player_by_token(x_session)


async def _game(game_id: str) -> Game:
    game = await store.get_game(game_id)
    # Parties de l'arène : pas de relecture tant que ce n'est pas ouvert (`ARENA_REPLAYS`).
    if game is None or (game.mode == "arena" and not arena.replays_open()):
        raise HTTPException(404, "Partie introuvable.")
    return game


async def _view(game: Game, player: Player | None, watchers: int = 0) -> dict:
    """Vue d'une partie (avec le résumé de son match tactique, s'il y en a un)."""
    brief = None
    if game.match_id:
        m = await matches.get(game.match_id)
        brief = match_brief(m) if m else None
    return game_view(game, player, watchers, brief)


def _http(exc: svc.GameError) -> HTTPException:
    return HTTPException(exc.status, exc.detail)


class NewPlayer(BaseModel):
    name: str | None = None


@router.post("/players", dependencies=[Depends(_signup_limit)])
async def create_player(body: NewPlayer, x_lang: str = Header(default="fr")):
    animals = ANIMALS[lang_of(x_lang)]
    name = (body.name or "").strip() or f"{random.choice(animals)}{random.randint(100, 999)}"
    if not NAME_RE.match(name):
        raise HTTPException(422, "Pseudo invalide (3 à 20 caractères).")
    player, token = await store.create_player(name)
    return {"player": me_json(player), "token": token}


@router.get("/me")
async def me(player: Player = Depends(current_player)):
    return me_json(player)


class ProfileUpdate(BaseModel):
    name: str | None = None
    country: str | None = Field(default=None, max_length=8)


@router.patch("/me", dependencies=[Depends(_action_limit)])
async def update_profile(body: ProfileUpdate, player: Player = Depends(current_player)):
    """Pseudo et/ou pays représenté."""
    if body.name is not None:
        name = body.name.strip()
        if not NAME_RE.match(name):
            raise HTTPException(422, "Pseudo invalide : 3 à 20 lettres, chiffres, espaces ou - . '")
        player.name = name
    if body.country is not None:
        code = normalize_country(body.country)
        if code is None:
            raise HTTPException(422, "Pays inconnu.")
        player.country = code
    await store.save_player(player)
    return me_json(player)


@router.get("/me/games")
async def my_games(player: Player = Depends(current_player)):
    return [game_summary(g, player.id) for g in await store.games_of(player.id)]


# --- Parties -------------------------------------------------------------------------


class NewGame(BaseModel):
    mode: Literal["local", "bot", "online"]
    terrain: str = "random"
    type: Literal["bullet", "classic"] | None = None  # None : sans pendule (tactique : /matches)
    botLevel: int | None = Field(default=None, ge=1, le=5)
    side: int | None = None
    rated: bool = True  # en ligne : classée (carte au sort) ou non (carte au choix)


@router.post("/games", dependencies=[Depends(_action_limit)])
async def create_game(body: NewGame, player: Player = Depends(current_player)):
    try:
        game = await svc.create_game(
            player, body.mode, body.terrain, body.type, body.botLevel, body.side, rated=body.rated
        )
    except svc.GameError as exc:
        raise _http(exc) from exc
    return await _view(game, player)


@router.get("/games/live")
async def live_games(limit: int = 30):
    """Parties en ligne en cours, les plus relevées d'abord (page « Regarder »)."""
    rows = await store.live_games(min(max(limit, 1), 50))
    watching = await spectators.counts([r["id"] for r in rows])
    in_match = await matches.summaries([r["match_id"] for r in rows if r["match_id"]])
    out = []
    for r in rows:
        m = in_match.get(r["match_id"]) if r["match_id"] else None
        rated = m.rated if m else r["rated"]
        players = [player_json(await store.get_player(pid), display_class(r["time_class"]))
                   for pid in (r["p1_id"], r["p2_id"])]
        if not rated:
            for pj in players:
                if pj:
                    pj["rank"] = None
        out.append({
            "id": r["id"],
            "players": players,
            "timeControl": f"{r['initial_ms'] // 60_000}+{r['increment_ms'] // 1000}" if r["initial_ms"] else None,
            "timeClass": r["time_class"],
            "rated": rated,
            "match": match_brief(m) if m else None,
            "terrain": r["terrain_mode"],
            "ply": max(0, r["ply"] - SPECTATOR_DELAY_PLIES),  # même retard que la vue spectateur
            "spectators": watching.get(r["id"], 0),
            "createdAt": r["created_at"],
        })
    return out


@router.get("/games/{game_id}")
async def get_game(game_id: str, player: Player | None = Depends(optional_player)):
    game = await _game(game_id)
    return await _view(game, player, await spectators.count(game.id))


@router.get("/games/{game_id}/history")
async def history(game_id: str, player: Player | None = Depends(optional_player)):
    game = await _game(game_id)
    shown = len(game.states) - spectator_delay(game, player)  # spectateur : pas les derniers coups
    return {"positions": [position_json(s) for s in game.states[:shown]]}


class PlayMove(BaseModel):
    pieceId: str
    kind: Literal["move", "attack", "exit", "pass"]
    to: int | None = None
    version: int | None = None


@router.post("/games/{game_id}/moves", dependencies=[Depends(_action_limit)])
async def play_move(game_id: str, body: PlayMove, player: Player = Depends(current_player)):
    try:
        game = await svc.play(game_id, player, body.pieceId, body.kind, body.to, body.version)
    except svc.GameError as exc:
        raise _http(exc) from exc
    return await _view(game, player)


class Action(BaseModel):
    action: Literal["offer", "accept", "decline"] = "offer"


@router.get("/games/{game_id}/analysis")
async def get_analysis(game_id: str):
    return await analysis_jobs.status(await _game(game_id))


@router.post("/games/{game_id}/analysis", dependencies=[Depends(_analysis_limit)])
async def start_analysis(game_id: str):
    """Lance le bilan d'une partie terminée (une fois pour toutes ; file d'attente)."""
    game = await _game(game_id)
    if game.status != "finished" or not game.moves:
        raise HTTPException(409, "Seule une partie terminée peut être analysée.")
    return await analysis_jobs.start(game)


@router.get("/games/{game_id}/analysis/stream")
async def analysis_stream(game_id: str, request: Request):
    """SSE : avancement de l'analyse, puis le bilan complet."""
    slot = limits.check_stream(request)
    game = await _game(game_id)
    key = f"analysis:{game.id}"

    async def events():
        queue = hub.subscribe(key)
        try:
            with limits.stream_slot(slot):
                while True:
                    st = await analysis_jobs.status(game)
                    yield f"event: analysis\ndata: {json.dumps(st)}\n\n"
                    if st["status"] in ("done", "error", "none"):
                        break
                    try:
                        await asyncio.wait_for(queue.get(), timeout=15)
                    except TimeoutError:
                        if await request.is_disconnected():
                            break
        finally:
            hub.unsubscribe(key, queue)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache, no-transform", "x-accel-buffering": "no"},
    )


@router.post("/games/{game_id}/{verb}", dependencies=[Depends(_action_limit)])
async def game_action(game_id: str, verb: str, body: Action | None = None,
                      player: Player = Depends(current_player)):
    try:
        if verb == "join":
            game = await svc.join_game(game_id, player)
        elif verb == "resign":
            game = await svc.resign(game_id, player)
        elif verb == "abort":
            game = await svc.abort(game_id, player)
        elif verb == "draw":
            game = await svc.draw(game_id, player, (body or Action()).action)
        elif verb == "rematch":
            game = await svc.rematch(game_id, player)
        else:
            raise HTTPException(404, "Action inconnue.")
    except svc.GameError as exc:
        raise _http(exc) from exc
    return await _view(game, player)


@router.get("/games/{game_id}/stream")
async def stream(game_id: str, request: Request, player: Player | None = Depends(optional_player)):
    """SSE : un évènement `state` (vue complète) à chaque changement de la partie, quelle
    que soit l'instance qui l'a modifiée (notification Postgres)."""
    slot = limits.check_stream(request)
    # Abonné AVANT la première lecture : aucun changement ne passe entre les deux.
    queue = hub.subscribe(game_id)
    try:
        game = await _game(game_id)
    except HTTPException:
        hub.unsubscribe(game_id, queue)
        raise

    # Un non-joueur qui ouvre le flux est un spectateur : il est compté (toutes instances).
    watching = not game.sides_of(player.id if player else None)

    async def events():
        nonlocal game
        sent = 0
        if watching:
            spectators.join(game_id)
        try:
            with limits.stream_slot(slot):
                while True:
                    if game.version > sent:
                        view = await _view(game, player, await spectators.count(game_id))
                        sent = game.version
                        yield f"id: {view['version']}\nevent: state\ndata: {json.dumps(view)}\n\n"
                    try:
                        version = await asyncio.wait_for(queue.get(), timeout=15)
                    except TimeoutError:
                        if await request.is_disconnected():
                            break
                        yield ": ping\n\n"
                        continue
                    if version == "watch":  # nombre de spectateurs changé (pas la partie)
                        n = await spectators.count(game_id)
                        yield f"event: spectators\ndata: {json.dumps({'count': n})}\n\n"
                        continue
                    if version is not None and version <= sent:
                        continue
                    game = await store.get_game(game_id, known_version=version) or game
        finally:
            hub.unsubscribe(game_id, queue)
            if watching:
                spectators.leave(game_id)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache, no-transform", "x-accel-buffering": "no"},
    )


# --- Matchs tactiques ----------------------------------------------------------------


class NewMatch(BaseModel):
    mode: Literal["local", "bot", "online"]
    botLevel: int | None = Field(default=None, ge=1, le=5)
    side: int | None = None
    rated: bool = True


class VetoBody(BaseModel):
    map: str = Field(max_length=16)


async def _match(match_id: str):
    m = await matches.get(match_id)
    if m is None:
        raise HTTPException(404, "Match introuvable.")
    return m


async def _match_view(m, player: Player | None) -> dict:
    for pid in m.players:
        await store.get_player(pid)
    return match_view(m, player)


@router.post("/matches", dependencies=[Depends(_action_limit)])
async def create_match(body: NewMatch, player: Player = Depends(current_player)):
    try:
        m = await matches.create(player, body.mode, body.botLevel, body.side, body.rated)
    except svc.GameError as exc:
        raise _http(exc) from exc
    return await _match_view(m, player)


@router.get("/matches/{match_id}")
async def get_match(match_id: str, player: Player | None = Depends(optional_player)):
    return await _match_view(await _match(match_id), player)


@router.post("/matches/{match_id}/{verb}", dependencies=[Depends(_action_limit)])
async def match_action(match_id: str, verb: str, body: VetoBody | None = None,
                       player: Player = Depends(current_player)):
    try:
        if verb == "join":
            m = await matches.join(match_id, player)
        elif verb == "veto":
            if body is None:
                raise HTTPException(422, "Carte indisponible.")
            m = await matches.veto(match_id, player, body.map)
        elif verb == "abort":
            m = await matches.abort(match_id, player)
        else:
            raise HTTPException(404, "Action inconnue.")
    except svc.GameError as exc:
        raise _http(exc) from exc
    return await _match_view(m, player)


@router.get("/matches/{match_id}/stream")
async def match_stream(match_id: str, request: Request, player: Player | None = Depends(optional_player)):
    """SSE : un évènement `match` (vue complète) à chaque changement du match."""
    slot = limits.check_stream(request)
    key = f"match:{match_id}"
    queue = hub.subscribe(key)
    try:
        m = await _match(match_id)
    except HTTPException:
        hub.unsubscribe(key, queue)
        raise

    async def events():
        nonlocal m
        sent = 0
        try:
            with limits.stream_slot(slot):
                while True:
                    if m.version > sent:
                        view = await _match_view(m, player)
                        sent = m.version
                        yield f"id: {m.version}\nevent: match\ndata: {json.dumps(view)}\n\n"
                    try:
                        await asyncio.wait_for(queue.get(), timeout=15)
                    except TimeoutError:
                        if await request.is_disconnected():
                            break
                        yield ": ping\n\n"
                        continue
                    m = await matches.get(match_id) or m
        finally:
            hub.unsubscribe(key, queue)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache, no-transform", "x-accel-buffering": "no"},
    )


# --- Puzzles ---------------------------------------------------------------------------


class PuzzleMove(BaseModel):
    # Champs facultatifs : le relais envoie `{}` pour l'indice et la solution (sans coup).
    pieceId: str = Field(default="", max_length=8)
    kind: Literal["move", "attack", "exit", "pass"] = "move"
    to: int | None = None


class RushBody(BaseModel):
    mode: Literal["3min", "5min", "survival"]


async def _puzzle_call(coro):
    try:
        return await coro
    except svc.GameError as exc:
        raise _http(exc) from exc


@router.get("/puzzles/next")
async def puzzle_next(player: Player = Depends(current_player)):
    """Puzzle classé suivant (un puzzle classé laissé en cours compte comme raté)."""
    return await _puzzle_call(training.next_rated(player))


@router.get("/puzzles/daily")
async def puzzle_daily(player: Player = Depends(current_player)):
    return await _puzzle_call(training.daily(player))


@router.get("/puzzles/stats")
async def puzzle_stats(player: Player = Depends(current_player)):
    return await training.stats(player)


@router.get("/puzzles/leaderboard")
async def puzzle_board():
    return await training.puzzle_leaderboard()


@router.get("/puzzles/attempts/{attempt_id}")
async def puzzle_attempt(attempt_id: str, player: Player = Depends(current_player)):
    return await _puzzle_call(training.get(attempt_id, player))


@router.post("/puzzles/attempts/{attempt_id}/{verb}", dependencies=[Depends(_action_limit)])
async def puzzle_action(attempt_id: str, verb: str, body: PuzzleMove | None = None,
                        player: Player = Depends(current_player)):
    if verb == "move":
        if body is None:
            raise HTTPException(422, "Coup illégal.")
        return await _puzzle_call(training.play(attempt_id, player, body.pieceId, body.kind, body.to))
    if verb == "hint":
        return await _puzzle_call(training.hint(attempt_id, player))
    if verb == "solution":
        return await _puzzle_call(training.reveal(attempt_id, player))
    raise HTTPException(404, "Action inconnue.")


@router.post("/puzzles/rush", dependencies=[Depends(_action_limit)])
async def rush_start(body: RushBody, player: Player = Depends(current_player)):
    return await _puzzle_call(training.rush_start(player, body.mode))


@router.get("/puzzles/rush/leaderboard")
async def rush_board(mode: str = "5min"):
    return await _puzzle_call(training.rush_leaderboard(mode))


@router.get("/puzzles/rush/{rush_id}")
async def rush_get(rush_id: str, player: Player = Depends(current_player)):
    return await _puzzle_call(training.rush_view(rush_id, player))


@router.post("/puzzles/{puzzle_id}/retry", dependencies=[Depends(_action_limit)])
async def puzzle_retry(puzzle_id: str, player: Player = Depends(current_player)):
    return await _puzzle_call(training.retry(puzzle_id, player))


# --- Lobby / matchmaking -------------------------------------------------------------


class SeekBody(BaseModel):
    type: Literal["bullet", "classic", "tactic"]
    rated: bool = True  # classée : carte tirée au sort ; non classée : `terrain` au choix
    terrain: str = Field(default="random", max_length=16)


def _seek_json(s) -> dict:
    if s is None:
        return {"status": "idle"}
    if s.game_id:
        kind, _, target = s.game_id.partition(":")
        return {"status": "matched", **({"matchId": target} if kind == "m" else {"gameId": s.game_id})}
    return {"status": "searching", "type": s.time_control, "rated": s.rated, "terrain": s.terrain,
            "since": s.created_at}


@router.post("/lobby/seek", dependencies=[Depends(_action_limit)])
async def seek(body: SeekBody, player: Player = Depends(current_player)):
    try:
        return _seek_json(await lobby.seek(player, body.type, body.rated, body.terrain))
    except svc.GameError as exc:
        raise _http(exc) from exc


@router.get("/lobby/seek")
async def poll_seek(player: Player = Depends(current_player)):
    return _seek_json(await lobby.poll(player))


@router.delete("/lobby/seek")
async def cancel_seek(player: Player = Depends(current_player)):
    await lobby.cancel(player)
    return {"status": "idle"}


@router.get("/lobby")
async def lobby_info():
    return {
        **await lobby.stats(),
        "types": list(RATED_CLASSES),
        "terrains": list(TERRAIN_MODES),
        "bots": [await _bot_json(k, v.name) for k, v in LEVELS.items()],
    }


async def _bot_json(level: int, name: str) -> dict:
    """Bot et son classement contre les joueurs (il bouge avec ses résultats)."""
    p = await store.get_player(f"bot{level}")
    r = p.ratings.get(BOT_CLASS) if p else None
    return {"level": level, "name": name, "rating": round(r.rating) if r else None,
            "games": r.games if r else 0, "rank": rank_json(p, BOT_CLASS) if p else None}


@router.get("/terrain")
async def terrain_preview(mode: str = "random", seed: int | None = None):
    """Aperçu d'un plateau (accueil, choix du terrain). Aucune partie n'est créée."""
    try:
        effective, seed, heights = generate_terrain(mode, seed)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"mode": effective, "seed": seed, "heights": list(heights)}


# --- Bac à sable (situations de jeu des règles) --------------------------------------


class SandboxPiece(BaseModel):
    id: str = Field(min_length=1, max_length=8)
    owner: Literal[1, 2]
    kind: Literal["explorer", "vanguard", "sentinel"]
    sq: int = Field(ge=0, le=99)


class SandboxMove(BaseModel):
    pieceId: str
    kind: Literal["move", "attack", "exit", "pass"]
    to: int | None = None


class Sandbox(BaseModel):
    heights: list[int] = Field(min_length=100, max_length=100)
    pieces: list[SandboxPiece] = Field(max_length=12)
    side: Literal[1, 2] = 1
    ply: int = Field(default=0, ge=0, le=10_000)
    move: SandboxMove | None = None


@router.post("/sandbox", dependencies=[Depends(_sandbox_limit)])
async def sandbox(body: Sandbox):
    """Position libre -> coups légaux du camp `side` (et coup appliqué si fourni).

    Sert aux situations de jeu interactives de la page Règles : c'est le vrai moteur qui
    calcule, mais rien n'est enregistré. Le camp reste le même après un coup, pour
    pouvoir enchaîner les essais.
    """
    if any(not 0 <= h <= 6 for h in body.heights):
        raise HTTPException(422, "Hauteurs hors limites.")
    if len({p.id for p in body.pieces}) != len(body.pieces) or len({p.sq for p in body.pieces}) != len(body.pieces):
        raise HTTPException(422, "Pièces en double.")
    state = GameState(
        heights=tuple(body.heights),
        pieces=tuple(Piece(p.id, p.owner, p.kind, p.sq) for p in body.pieces),
        to_move=body.side,
        ply=body.ply,
        move_limit=10_000,
    )
    last = None
    if body.move:
        try:
            move = find_move(state, body.move.pieceId, body.move.kind, body.move.to)
        except IllegalMove as exc:
            raise HTTPException(422, str(exc)) from exc
        captured = state.occupancy().get(move.to) if move.kind == "attack" else None
        mover = state.piece(move.piece_id)
        last = {
            "ply": state.ply + 1, "side": body.side, "pieceId": move.piece_id, "kind": move.kind,
            "special": move.special, "from": mover.sq if mover else None, "to": move.to,
            "path": list(move.path), "notation": notation(state, move), "combat": None,
            "capturedId": captured.id if captured else None, "remainingMs": None,
        }
        after = apply_move(state, move)
        # On rend la main au même camp (bac à sable), sans fin de partie.
        state = GameState(heights=after.heights, pieces=after.pieces, to_move=body.side,
                          ply=after.ply, scores=after.scores, finished=after.finished,
                          captured=after.captured, move_limit=10_000)
    return {
        "position": position_json(state),
        "legalMoves": [move_json(m) for m in legal_moves(state) if m.kind != "pass"],
        "lastMove": last,
    }


# --- Classement & profils ------------------------------------------------------------


@router.get("/leaderboard")
async def leaderboard(timeClass: str = DEFAULT_CLASS):
    rows = await store.leaderboard(timeClass)
    await store.refresh_legends(timeClass)
    return [
        {"rank": i + 1, "id": p.id, "name": p.name, "country": p.country, "rating": round(r.rating), "games": r.games,
         "wins": r.wins, "losses": r.losses, "draws": r.draws, "provisional": r.rd > 110,
         "tier": rank_json(p, timeClass)}
        for i, (p, r) in enumerate(rows)
    ]


@router.get("/ranks")
async def rank_ladder():
    """Paliers du classement (page d'explication)."""
    return {"ladder": ranks.ladder(), "placementGames": ranks.PLACEMENT_GAMES,
            "divisionWidth": ranks.DIVISION_WIDTH, "legendSlots": ranks.LEGEND_SLOTS}


@router.get("/players/{player_id}")
async def profile(player_id: str):
    p = await store.get_player(player_id)
    if p is None or p.is_bot:
        raise HTTPException(404, "Joueur introuvable.")
    me = me_json(p)
    me.pop("email", None)  # profil public : jamais l'email
    return {
        **me,
        "card": player_json(p),
        "games": [game_summary(g, p.id) for g in await store.games_of(p.id, online_only=True)],
    }


@router.get("/players/{player_id}/history")
async def rating_history(player_id: str, timeClass: str = DEFAULT_CLASS):
    """Courbe d'évolution du classement (une cadence)."""
    p = await store.get_player(player_id)
    if p is None or p.is_bot:
        raise HTTPException(404, "Joueur introuvable.")
    if timeClass == "tactic":  # classé au match, pas à la partie
        return await matches.rating_history(player_id)
    return await store.rating_history(player_id, timeClass)


# --- Comptes -------------------------------------------------------------------------



class Credentials(BaseModel):
    email: str
    password: str


class SignupBody(Credentials):
    country: str | None = Field(default=None, max_length=8)


@router.post("/auth/signup", dependencies=[Depends(_login_limit)])
async def signup(body: SignupBody, player: Player = Depends(current_player), x_lang: str = Header(default="fr")):
    try:
        await accounts.signup(player, body.email, body.password, body.country, lang_of(x_lang))
    except accounts.AccountError as exc:
        raise HTTPException(exc.status, exc.detail) from exc
    return me_json(player)


@router.post("/auth/login", dependencies=[Depends(_login_limit)])
async def login(body: Credentials):
    """Renvoie un NOUVEAU jeton de session : le relais du front le pose en cookie."""
    try:
        player, token = await accounts.login(body.email, body.password)
    except accounts.AccountError as exc:
        raise HTTPException(exc.status, exc.detail) from exc
    return {"player": me_json(player), "token": token}


class ForgotBody(BaseModel):
    email: str = Field(max_length=300)


@router.post("/auth/forgot", dependencies=[Depends(_login_limit)])
async def forgot(body: ForgotBody, x_lang: str = Header(default="fr")):
    """Toujours la même réponse : on ne révèle pas si l'adresse a un compte. L'email part
    dans la langue du joueur."""
    await accounts.forgot_password(body.email, lang_of(x_lang))
    return {"ok": True}


class ResetBody(BaseModel):
    token: str = Field(max_length=200)
    password: str


@router.post("/auth/reset", dependencies=[Depends(_login_limit)])
async def reset(body: ResetBody):
    """Comme le login : renvoie un nouveau jeton que le relais pose en cookie."""
    try:
        player, token = await accounts.reset_password(body.token, body.password)
    except accounts.AccountError as exc:
        raise HTTPException(exc.status, exc.detail) from exc
    return {"player": me_json(player), "token": token}


class PasswordBody(BaseModel):
    current: str
    new: str


@router.post("/auth/password", dependencies=[Depends(_login_limit)])
async def change_password(body: PasswordBody, x_session: str = Header(default=""),
                          player: Player = Depends(current_player)):
    try:
        await accounts.change_password(player, body.current, body.new, x_session)
    except accounts.AccountError as exc:
        raise HTTPException(exc.status, exc.detail) from exc
    return {"ok": True}


class VerifyBody(BaseModel):
    token: str = Field(max_length=200)


@router.post("/auth/verify", dependencies=[Depends(_login_limit)])
async def verify_email(body: VerifyBody):
    """Lien de confirmation reçu par email (fonctionne même sur un autre appareil)."""
    try:
        player = await accounts.verify_email(body.token)
    except accounts.AccountError as exc:
        raise HTTPException(exc.status, exc.detail) from exc
    return {"ok": True, "name": player.name}


@router.post("/auth/resend", dependencies=[Depends(_login_limit)])
async def resend_verification(player: Player = Depends(current_player), x_lang: str = Header(default="fr")):
    try:
        await accounts.resend_verification(player, lang_of(x_lang))
    except accounts.AccountError as exc:
        raise HTTPException(exc.status, exc.detail) from exc
    return {"ok": True}


@router.post("/auth/logout")
async def logout(x_session: str = Header(default="")):
    await store.end_session(x_session)
    return {"ok": True}
