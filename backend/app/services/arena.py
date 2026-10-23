"""Arène des bots : les joueurs envoient un bot WebAssembly, il est classé contre les autres.

Vue d'ensemble (détails dans `ARENA.md`) :

1. **Envoi** (`submit`) : un joueur inscrit envoie un `.wasm`. Une nouvelle version
   (`arena_bots`, joueur bot à part) est créée « en attente », avec une tâche de
   **validation** dans la file `arena_jobs`.
2. **Runner** (`traversal-arena work`, Serverless Job à part, sans accès à la base) :
   réclame les tâches (`claim`), télécharge les modules, joue en bac à sable (fuel,
   mémoire bornée, aucun accès au système), renvoie les coups (`report`).
3. **Vérification** : chaque partie est REJOUÉE ici par le moteur Python (référence) ;
   le runner ne dit jamais qui a gagné. Un coup illégal = résultat refusé.
4. **Placement** : un bot validé joue 10 parties contre les 5 bots maison (chaque carte
   deux fois, couleurs inversées), puis l'**échelle** : quand la file est vide, de
   nouvelles paires de parties sont tirées entre bots de niveau proche.
5. **Classement** (`recompute`) : Bradley-Terry (Elo) sur toutes les parties de
   l'arène, ancré sur Galet = 920 comme le classement des bots du site.
6. **Bilans** (`queue_analysis`) : le bilan d'une partie du site est fait par le runner,
   avant les parties de l'échelle : le n°1 du classement propose le meilleur coup de
   chaque position, orque note ce coup et le coup joué. Les coups du bot sont vérifiés
   ici, le bilan est rangé sur la partie (`report`).
"""

import base64
import hashlib
import logging
import math
import os
import random
import re
import time

from sqlalchemy import and_, delete, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app import bot, db
from app.analysis import ANALYSIS_NODES, PositionResult, analyse_game
from app.bot.native import pack, to_move
from app.engine import Move, apply_move, end_game, generate_terrain, legal_moves, new_game
from app.engine import config as C
from app.services import limits, ranks
from app.services.games import _record
from app.services.store import Game, Player, _game_row, _id, _move_row, store

log = logging.getLogger("traversal.arena")

# Fuel par coup (≈ instructions WebAssembly) : même budget pour tous les bots. Mont Blanc
# en utilise ~0,8 milliard ; ~30 ms sur un Mac M, ~0,2 s sur un vCPU Scaleway.
# `traversal-arena` a la même valeur par défaut pour les essais en local.
FUEL_PER_MOVE = 2_000_000_000
MAX_WASM_BYTES = 1024 * 1024  # « 1 Mo » dans les messages
MEMORY_MB = 64
MAX_LIVE_BOTS = 2  # bots en lice (ou en validation) par joueur
UPLOADS_PER_DAY = 5  # envois par joueur et par 24 h (nouvelles versions comprises)
PLACEMENT_LEVELS = (1, 2, 3, 4, 5)  # une paire de parties contre chaque bot maison
PROVISIONAL_GAMES = 10
DAILY_GAMES_PER_BOT = 40  # parties d'échelle par bot et par 24 h (coût du runner borné)
BATCH_PAIRS = 6  # paires tirées quand la file est vide
CALIBRATION_GAMES = 20  # parties entre bots maison voisins (une fois) pour caler l'échelle
NEIGHBOURS = 3  # adversaire tiré parmi les N bots de classement le plus proche
STALE_CLAIM_S = 300  # tâche d'un runner disparu : remise en file
STALE_ANALYSIS_S = 1300  # un bilan peut durer 1200 s (`isolate::timeout_for`)
MAX_ATTEMPTS = 3
RECOMPUTE_EVERY_S = 60
ANCHOR = ("bot1", 920.0)  # Galet, comme `bot.LEVELS`
PRIOR_RATING = 1500.0  # adversaire fictif (1 victoire, 1 défaite) : classement fini dès 1 partie
MAX_RATED_GAMES = 50_000

NAME_RE = re.compile(r"^[\w][\w .\-]{1,22}[\w]$", re.UNICODE)
HOUSE = {f"bot{lv}": lv for lv in bot.LEVELS}
_LOCK_SCHEDULE = 727301  # verrous consultatifs Postgres
_LOCK_RATINGS = 727302

a, j, r_, g = db.arena_bots.c, db.arena_jobs.c, db.arena_ratings.c, db.games.c
_last_recompute = 0.0


class ArenaError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def runner_token() -> str:
    """Jeton du runner (`ARENA_TOKEN`). Vide : l'API du runner est fermée."""
    return os.environ.get("ARENA_TOKEN", "")


def replays_open() -> bool:
    """Parties de l'arène consultables (relecture, bilan) ? Fermé par défaut
    (`ARENA_REPLAYS=1` pour ouvrir) : on voit les résultats, pas les parties. Seule
    exception : la partie choisie pour l'accueil (`showcase`)."""
    return os.environ.get("ARENA_REPLAYS") == "1"


def info() -> dict:
    return {"replays": replays_open(), "fuelPerMove": FUEL_PER_MOVE, "maxWasmKb": MAX_WASM_BYTES // 1024, "memoryMb": MEMORY_MB,
            "maxLiveBots": MAX_LIVE_BOTS, "placementGames": 2 * len(PLACEMENT_LEVELS),
            "dailyGames": DAILY_GAMES_PER_BOT}


# --- Envoi d'un bot ----------------------------------------------------------------------


def _new_job(kind: str, red: str, blue: str, terrain: tuple | None = None) -> dict:
    mode, seed, heights = terrain or generate_terrain("random")
    return {"id": _id(10), "kind": kind, "red_id": red, "blue_id": blue, "terrain": mode, "seed": seed,
            "heights": list(heights), "status": "queued", "attempts": 0, "created_at": time.time(),
            "claimed_at": None}


def _pair(x: str, y: str) -> list[dict]:
    """Deux parties sur la même carte, couleurs inversées : la carte ne favorise personne."""
    terrain = generate_terrain("random")
    return [_new_job("game", x, y, terrain), _new_job("game", y, x, terrain)]


async def submit(owner: Player, name: str, wasm_b64: str, replaces: str | None = None) -> dict:
    """Nouveau bot (`name`), ou nouvelle version d'un bot du joueur (`replaces` : l'id d'une
    de ses versions, le nom vient de là)."""
    if owner.is_guest:
        raise ArenaError(403, "Crée un compte pour inscrire un bot.")
    if not owner.email_verified_at:
        # Une adresse confirmée par compte : multiplier les comptes (et donc les bots en
        # lice, les envois, les ententes entre bots) demande autant de vraies adresses.
        raise ArenaError(403, "Confirme ton adresse email pour inscrire un bot.")
    if replaces:
        async with store.engine.connect() as conn:
            row = (await conn.execute(select(a.owner_id, a.name).where(a.id == replaces))).first()
        if row is None or row.owner_id != owner.id:
            raise ArenaError(404, "Bot introuvable.")
        name = row.name
    name = (name or "").strip()
    if not NAME_RE.match(name):
        raise ArenaError(422, "Nom de bot invalide (3 à 24 caractères).")
    try:
        wasm = base64.b64decode(wasm_b64, validate=True)
    except ValueError as exc:
        raise ArenaError(422, "Fichier illisible.") from exc
    if len(wasm) > MAX_WASM_BYTES:
        raise ArenaError(413, "Fichier trop gros (1 Mo au plus).")
    if wasm[:4] != b"\0asm":
        raise ArenaError(422, "Ce n'est pas un module WebAssembly (.wasm).")
    # Seuls les envois acceptés comptent : un refus (nom pris, trop de bots) ou un nouvel
    # essai après le 429 ne mangent pas le quota.
    upload_key = f"arena-upload:{owner.id}"
    if await limits.count(upload_key, 86400) >= UPLOADS_PER_DAY:
        raise ArenaError(429, "Trop d'envois aujourd'hui. Réessaie demain.")
    async with store.engine.begin() as conn:
        # Un nom = un bot, d'un seul auteur (ses versions se suivent sous ce nom).
        taken = (await conn.execute(select(a.owner_id).where(
            func.lower(a.name) == name.lower(), a.owner_id != owner.id, a.status != "rejected").limit(1))).first()
        if taken or name.lower() in {lv.name.lower() for lv in bot.LEVELS.values()}:
            raise ArenaError(409, "Ce nom de bot est déjà pris.")
        live = (await conn.execute(select(func.count(func.distinct(a.name))).where(
            a.owner_id == owner.id, a.status.in_(("pending", "active")), a.name != name))).scalar()
        if live >= MAX_LIVE_BOTS:
            raise ArenaError(409, "Trop de bots en lice : retires-en un d'abord.")
        version = (await conn.execute(select(func.max(a.version)).where(
            a.owner_id == owner.id, a.name == name))).scalar() or 0
        if version and not replaces:
            raise ArenaError(409, "Tu as déjà un bot de ce nom : envoie le fichier comme mise à jour.")
        bot_id = "ar" + _id(10)  # jamais « bot… » : réservé aux bots maison (`_bot_to_move`)
        now = time.time()
        await conn.execute(pg_insert(db.players).values(
            id=bot_id, name=name, is_bot=True, created_at=now, last_seen=now))
        await conn.execute(pg_insert(db.arena_bots).values(
            id=bot_id, owner_id=owner.id, name=name, version=version + 1, status="pending",
            wasm=wasm, sha256=hashlib.sha256(wasm).hexdigest(), size=len(wasm), created_at=now))
        await conn.execute(pg_insert(db.arena_jobs).values(**_new_job("check", bot_id, "bot1")))
    await limits.hit(upload_key, UPLOADS_PER_DAY, 86400)
    return await bot_view(bot_id)


async def retire(owner: Player, bot_id: str) -> dict:
    async with store.engine.begin() as conn:
        row = (await conn.execute(select(a.owner_id, a.status).where(a.id == bot_id))).first()
        if row is None or row.owner_id != owner.id:
            raise ArenaError(404, "Bot introuvable.")
        if row.status in ("pending", "active"):
            await _retire(conn, [bot_id])
    return await bot_view(bot_id)


async def _retire(conn, ids: list[str], status: str = "retired", error: str | None = None) -> None:
    """La version ne joue plus : module effacé, ses parties en attente annulées."""
    if not ids:
        return
    await conn.execute(update(db.arena_bots).where(a.id.in_(ids)).values(status=status, wasm=None, error=error))
    await conn.execute(delete(db.arena_jobs).where(or_(j.red_id.in_(ids), j.blue_id.in_(ids))))


# --- File du runner ----------------------------------------------------------------------


def _side(pid: str, sha: str | None) -> dict:
    return {"id": pid, "house": HOUSE[pid]} if pid in HOUSE else {"id": pid, "sha256": sha}


async def claim() -> dict | None:
    """Prochaine tâche pour un runner (les validations, puis les bilans, d'abord) ; None si
    rien à faire."""
    for attempt in range(3):
        now = time.time()
        async with store.engine.begin() as conn:
            # Runner disparu en pleine partie : la tâche repart (ou abandonne après 3 essais).
            stale = j.claimed_at < now - STALE_CLAIM_S
            stale = or_(and_(j.kind != "analyse", stale), j.claimed_at < now - STALE_ANALYSIS_S)
            await conn.execute(delete(db.arena_jobs).where(j.status == "running", stale, j.attempts >= MAX_ATTEMPTS))
            await conn.execute(update(db.arena_jobs).where(j.status == "running", stale).values(status="queued"))
            row = (await conn.execute(
                select(db.arena_jobs).where(j.status == "queued")
                .order_by((j.kind == "check").desc(), (j.kind == "analyse").desc(), j.created_at)
                .limit(1).with_for_update(skip_locked=True)
            )).mappings().first()
            if row is not None:
                await conn.execute(update(db.arena_jobs).where(j.id == row["id"]).values(
                    status="running", claimed_at=now, attempts=row["attempts"] + 1))
                shas = dict((await conn.execute(select(a.id, a.sha256).where(
                    a.id.in_((row["red_id"], row["blue_id"]))))).all())
                if row["kind"] == "analyse":
                    game = await store.get_game(row["game_id"])
                    if game is None:  # partie effacée entre-temps : tâche suivante
                        await conn.execute(delete(db.arena_jobs).where(j.id == row["id"]))
                        continue
                    side = _side(row["red_id"], shas.get(row["red_id"]))
                    return {"id": row["id"], "kind": "analyse", "fuel": FUEL_PER_MOVE, "nodes": ANALYSIS_NODES,
                            "positions": _positions(game), "red": side, "blue": side}
                return {
                    "id": row["id"], "kind": row["kind"], "seed": row["seed"], "heights": row["heights"],
                    "moveLimit": new_game(tuple(row["heights"])).move_limit, "fuel": FUEL_PER_MOVE,
                    "red": _side(row["red_id"], shas.get(row["red_id"])),
                    "blue": _side(row["blue_id"], shas.get(row["blue_id"])),
                }
        if attempt == 0:
            await recompute(force=True)  # fin d'un lot : classement à jour avant le suivant
            if not await schedule():
                return None
    return None


async def wasm_of(sha: str) -> bytes | None:
    async with store.engine.connect() as conn:
        return (await conn.execute(select(a.wasm).where(a.sha256 == sha, a.wasm.is_not(None)).limit(1))).scalar()


async def report(job_id: str, body: dict) -> None:
    refused = None
    async with store.engine.begin() as conn:
        job = (await conn.execute(select(db.arena_jobs).where(j.id == job_id).with_for_update())).mappings().first()
        if job is None or job["status"] != "running":
            raise ArenaError(404, "Tâche inconnue ou déjà rendue.")
        await conn.execute(delete(db.arena_jobs).where(j.id == job_id))
        if job["kind"] == "check":
            await _checked(conn, job["red_id"], bool(body.get("ok")), body.get("error"))
            return
        if job["kind"] != "analyse":
            try:
                game = replay(job, body)
            except (ValueError, IndexError, KeyError, TypeError, StopIteration) as exc:
                # Le runner et le moteur Python ne sont pas d'accord : partie écartée (la
                # tâche aussi), à investiguer — une règle changée d'un seul côté ?
                log.error("partie d'arène %s refusée : %s", job_id, exc)
                refused = str(exc) or type(exc).__name__
            else:
                await conn.execute(pg_insert(db.games).values(**_game_row(game)))
                if game.moves:
                    await conn.execute(pg_insert(db.moves), [_move_row(game.id, m) for m in game.moves])
    if job["kind"] == "analyse":
        await _analysed(job, body)
        return
    if refused:
        raise ArenaError(422, "Partie refusée.")
    await recompute()


async def _checked(conn, bot_id: str, ok: bool, error: str | None) -> None:
    row = (await conn.execute(select(a.owner_id, a.name, a.status).where(a.id == bot_id))).first()
    if row is None or row.status != "pending":
        return
    if not ok:
        await _retire(conn, [bot_id], status="rejected", error=(error or "validation échouée")[:300])
        return
    older = (await conn.execute(select(a.id).where(
        a.owner_id == row.owner_id, a.name == row.name, a.id != bot_id, a.status.in_(("pending", "active")))
    )).scalars().all()
    await _retire(conn, list(older))  # la nouvelle version remplace l'ancienne
    await conn.execute(update(db.arena_bots).where(a.id == bot_id).values(status="active", activated_at=time.time()))
    jobs = [job for lv in PLACEMENT_LEVELS for job in _pair(bot_id, f"bot{lv}")]
    await conn.execute(pg_insert(db.arena_jobs), jobs)


def replay(job, body: dict) -> Game:
    """Rejoue la partie rendue par le runner avec le moteur Python. Le résultat vient du
    rejeu (ou de la faute déclarée, qui doit tomber sur le camp au trait)."""
    heights = tuple(job["heights"])
    game = Game(
        id=store.new_game_id(), mode="arena", terrain_mode=job["terrain"], seed=job["seed"],
        players=[job["red_id"], job["blue_id"]], created_by=job["red_id"], states=[new_game(heights)],
        status="finished", time_class="arena",
    )
    for piece, kind, to in body.get("moves") or []:
        before = game.state
        if before.over:
            raise ValueError("coups après la fin de la partie")
        move = to_move(before, int(piece), str(kind), int(to))
        game.moves.append(_record(game, move, before))
        game.states.append(apply_move(before, move))
    fault = body.get("fault")
    if fault:
        side = int(fault["side"])
        if game.state.over or side not in (1, 2) or (game.moves and side != game.state.to_move):
            raise ValueError("faute incohérente")
        reason = "timeout" if fault.get("kind") == "fuel" else "forfeit"
        game.states[-1] = end_game(game.state, 3 - side, reason)
    elif not game.state.over:
        raise ValueError("partie inachevée")
    game.ended_at = time.time()
    return game


# --- Bilans de partie par le n°1 de l'arène ----------------------------------------------


def analyses_enabled() -> bool:
    """Bilans par le runner (`ARENA_ANALYSES=1`, avec un runner configuré) ; sinon, orque
    seul dans le backend."""
    return bool(runner_token()) and os.environ.get("ARENA_ANALYSES") == "1"


async def analysis_bot() -> dict | None:
    """Le bot qui fait les bilans : le premier du classement de l'arène (placement fini)."""
    return next((b for b in await leaderboard() if b["rating"] is not None and not b["provisional"]), None)


async def queue_analysis(game: Game, bot_id: str) -> None:
    job = {**_new_job("analyse", bot_id, bot_id, ("analysis", 0, game.state.heights)), "game_id": game.id}
    async with store.engine.begin() as conn:
        await conn.execute(pg_insert(db.arena_jobs).values(**job))


def _positions(game: Game) -> list[dict]:
    """Chaque position avant un coup, au format du moteur Rust, et le coup joué."""
    out = []
    for i, rec in enumerate(game.moves):
        s = game.states[i]
        piece = next((k for k, p in enumerate(s.pieces) if p.id == rec.piece_id), -1)
        out.append({"state": pack(s), "played": [piece, rec.kind, -1 if rec.to is None else rec.to], "seed": i + 1})
    return out


def analysis_results(game: Game, positions: list) -> list[PositionResult | None]:
    """Notes rendues par le runner -> résultats du bilan. Chaque coup du bot est vérifié
    (coup légal de la position) ; ValueError & co. si le rendu ne colle pas à la partie."""
    if len(positions) != len(game.moves):
        raise ValueError("nombre de positions")
    out: list[PositionResult | None] = []
    for state, rec, pos in zip(game.states, game.moves, positions):
        if rec.kind == "pass":
            out.append(None)  # passe forcée : le bilan ne la note pas
            continue
        played = Move(rec.piece_id, rec.kind, rec.to, tuple(rec.path), 0, rec.special)
        piece, kind, to = pos["bot"]
        best = to_move(state, int(piece), str(kind), int(to))
        bot_score, played_score = float(pos["botScore"]), float(pos["playedScore"])
        if played_score >= bot_score or (best.piece_id, best.kind, best.to) == (rec.piece_id, rec.kind, rec.to):
            best, bot_score = played, max(bot_score, played_score)
        forced = len([m for m in legal_moves(state) if m.kind != "pass"]) <= 1
        out.append(PositionResult(best, bot_score, played_score, int(pos.get("depth") or 0), forced))
    return out


async def _analysed(job, body: dict) -> None:
    from app.services import analysis_jobs

    game = await store.get_game(job["game_id"])
    if game is None:
        return
    try:
        results = analysis_results(game, body["positions"])
    except (ValueError, IndexError, KeyError, TypeError, StopIteration) as exc:
        log.error("bilan de %s par l'arène refusé : %s (%s)", game.id, exc, body.get("error"))
        await analysis_jobs.fall_back(game.id)
        raise ArenaError(422, "Bilan refusé.") from exc
    bot_row = next((b for b in await leaderboard() if b["id"] == job["red_id"]), None)
    engine = {"bot": {"id": job["red_id"], "name": bot_row["name"] if bot_row else job["red_id"],
                      "rating": bot_row["rating"] if bot_row else None}, "eval": "orque"}
    await store.set_analysis(game.id, analyse_game(list(game.states), list(game.moves), None, results, engine))


# --- Échelle : quelles parties jouer ensuite ? ------------------------------------------


async def schedule() -> bool:
    """File vide : tire un nouveau lot de paires. False s'il n'y a rien à jouer."""
    since = time.time() - 86400
    async with store.engine.begin() as conn:
        if not (await conn.execute(text(f"SELECT pg_try_advisory_xact_lock({_LOCK_SCHEDULE})"))).scalar():
            return False
        if (await conn.execute(select(func.count()).select_from(db.arena_jobs))).scalar():
            return True  # un autre runner vient de remplir la file
        active = list((await conn.execute(select(a.id).where(a.status == "active"))).scalars())
        ratings = dict((await conn.execute(select(r_.player_id, r_.rating))).all())
        recent = {pid: n for pid, n in (await conn.execute(text(
            "SELECT p, count(*) FROM (SELECT p1_id AS p FROM games WHERE mode = 'arena' AND ended_at > :s "
            "UNION ALL SELECT p2_id FROM games WHERE mode = 'arena' AND ended_at > :s) t GROUP BY p"),
            {"s": since})).all()}
        jobs = plan_batch(active, ratings, recent)
        jobs += await _calibration(conn)
        if jobs:
            await conn.execute(pg_insert(db.arena_jobs), jobs)
    return bool(jobs)


def plan_batch(active: list[str], ratings: dict[str, float], recent: dict[str, int]) -> list[dict]:
    """Les bots qui ont le moins joué ces dernières 24 h d'abord ; chacun contre un des
    `NEIGHBOURS` participants (bots maison compris) de classement le plus proche — deux
    bots du même joueur compris."""
    pool = active + list(HOUSE)
    hungry = sorted((b for b in active if recent.get(b, 0) < DAILY_GAMES_PER_BOT), key=lambda b: recent.get(b, 0))
    jobs, busy = [], set()
    for b in hungry[:BATCH_PAIRS]:
        mine = ratings.get(b, PRIOR_RATING)
        others = sorted((o for o in pool if o != b and o not in busy),
                        key=lambda o: abs(ratings.get(o, PRIOR_RATING) - mine))[:NEIGHBOURS]
        if not others:
            continue
        rival = random.choice(others)
        busy.add(b)
        jobs += _pair(b, rival)
    return jobs


async def _calibration(conn) -> list[dict]:
    """Une fois pour toutes : assez de parties entre bots maison voisins pour que
    l'échelle tienne debout même avant les premiers bots de la communauté."""
    jobs = []
    levels = sorted(bot.LEVELS)
    for lo, hi in zip(levels, levels[1:]):
        x, y = f"bot{lo}", f"bot{hi}"
        n = (await conn.execute(select(func.count()).select_from(db.games).where(
            g.mode == "arena", or_(and_(g.p1_id == x, g.p2_id == y), and_(g.p1_id == y, g.p2_id == x))))).scalar()
        if n < CALIBRATION_GAMES:
            jobs += _pair(x, y)
    return jobs


async def round_robin(games: int = 20) -> tuple[int, int]:
    """À la main seulement (`make arena-round-robin`) : `games` parties de plus entre
    chaque paire de bots des joueurs en lice (bots maison exclus), couleurs inversées.
    Ronde par ronde (une paire de parties par duel et par ronde) : le classement reste
    équilibré pendant que la file se vide. Renvoie (bots, parties mises en file)."""
    if games < 2 or games % 2:
        raise ValueError("games doit être pair (chaque carte est jouée deux fois, couleurs inversées)")
    async with store.engine.begin() as conn:
        active = sorted((await conn.execute(select(a.id).where(a.status == "active"))).scalars())
        duels = [(x, y) for i, x in enumerate(active) for y in active[i + 1:]]
        jobs = [job for _ in range(games // 2) for x, y in duels for job in _pair(x, y)]
        if jobs:
            await conn.execute(pg_insert(db.arena_jobs), jobs)
    return len(active), len(jobs)


# --- Classement --------------------------------------------------------------------------

ELO = 400 / math.log(10)


def fit(results: list[tuple[str, str, float]], anchor: tuple[str, float] = ANCHOR,
        iters: int = 500) -> dict[str, tuple[float, float]]:
    """Bradley-Terry (échelle Elo) par l'algorithme MM de Hunter, sur des parties
    `(rouge, bleu, score du rouge)` (nulle = 0,5). Chaque joueur a en plus une victoire et
    une défaite contre un adversaire fictif à `PRIOR_RATING` : un bot invaincu garde un
    classement fini. Renvoie `{joueur: (classement, marge à 95 %)}`, ancré sur `anchor`."""
    wins: dict[str, float] = {}
    pairs: dict[tuple[str, str], int] = {}
    for x, y, s in results:
        wins[x] = wins.get(x, 0.0) + s
        wins[y] = wins.get(y, 0.0) + 1 - s
        key = (x, y) if x < y else (y, x)
        pairs[key] = pairs.get(key, 0) + 1
    players = sorted(wins)
    if not players:
        return {}
    opp: dict[str, list[tuple[str, int]]] = {p: [] for p in players}
    for (x, y), n in pairs.items():
        opp[x].append((y, n))
        opp[y].append((x, n))
    prior = 10 ** (PRIOR_RATING / 400)
    gamma = {p: prior for p in players}
    for _ in range(iters):
        delta = 0.0
        new = {}
        for p in players:
            denom = sum(n / (gamma[p] + gamma[o]) for o, n in opp[p]) + 2 / (gamma[p] + prior)
            new[p] = (wins[p] + 1) / denom
            delta = max(delta, abs(math.log(new[p] / gamma[p])))
        gamma = new
        if delta < 1e-6:
            break
    rating = {p: 400 * math.log10(gamma[p]) for p in players}
    shift = anchor[1] - rating[anchor[0]] if anchor[0] in rating else 0.0
    out = {}
    for p in players:
        info_ = sum(n * gamma[p] * gamma[o] / (gamma[p] + gamma[o]) ** 2 for o, n in opp[p])
        info_ += 2 * gamma[p] * prior / (gamma[p] + prior) ** 2
        out[p] = (rating[p] + shift, 1.96 * ELO / math.sqrt(info_))
    return out


async def recompute(force: bool = False) -> None:
    """Recalcule tout le classement (au plus une instance à la fois)."""
    global _last_recompute
    if not force and time.time() - _last_recompute < RECOMPUTE_EVERY_S:
        return
    _last_recompute = time.time()
    async with store.engine.begin() as conn:
        if not (await conn.execute(text(f"SELECT pg_try_advisory_xact_lock({_LOCK_RATINGS})"))).scalar():
            return
        rows = (await conn.execute(select(g.p1_id, g.p2_id, g.winner).where(g.mode == "arena", g.status == "finished")
                                   .order_by(g.ended_at.desc()).limit(MAX_RATED_GAMES))).all()
        results = [(p1, p2, 0.5 if w is None else 1.0 if w == 1 else 0.0) for p1, p2, w in rows]
        fitted = fit(results)
        tally: dict[str, list[int]] = {}
        for x, y, s in results:
            for p, sc in ((x, s), (y, 1 - s)):
                t = tally.setdefault(p, [0, 0, 0])
                t[0 if sc == 1 else 1 if sc == 0 else 2] += 1
        now = time.time()
        await conn.execute(delete(db.arena_ratings))
        if fitted:
            await conn.execute(pg_insert(db.arena_ratings), [
                {"player_id": p, "rating": rt, "margin": mg, "games": sum(tally[p]), "wins": tally[p][0],
                 "losses": tally[p][1], "draws": tally[p][2], "updated_at": now}
                for p, (rt, mg) in fitted.items()])


# --- Lecture -----------------------------------------------------------------------------


def division(rating: float | None, games: int) -> dict | None:
    """Rang affiché (mêmes paliers et divisions que les joueurs : Ardoise IV … Maître). En
    placement tant que le bot n'a pas joué ses `PROVISIONAL_GAMES` premières parties."""
    if rating is None:
        return None
    if games < PROVISIONAL_GAMES:
        return {"tier": None, "name": "Placement", "division": None,
                "label": f"Placement {games}/{PROVISIONAL_GAMES}", "lp": 0,
                "placement": {"played": games, "total": PROVISIONAL_GAMES}, "next": None}
    return ranks.rank_from(rating, games)


def _rating_json(row, house: bool = False) -> dict:
    """`house` : bot du site, repère de l'échelle — sa division s'affiche toujours (comme les
    bots du classement des joueurs), sans placement."""
    if row is None or row["rating"] is None:
        return {"rating": None, "margin": None, "games": 0, "wins": 0, "losses": 0, "draws": 0, "provisional": True,
                "tier": None}
    return {"rating": round(row["rating"]), "margin": round(row["margin"]), "games": row["games"],
            "wins": row["wins"], "losses": row["losses"], "draws": row["draws"],
            "provisional": row["games"] < PROVISIONAL_GAMES,
            "tier": division(row["rating"], max(row["games"], PROVISIONAL_GAMES) if house else row["games"])}


async def leaderboard() -> list[dict]:
    """Bots en lice (dernière version de chacun) et bots maison, du meilleur au moins bon ;
    les bots encore sans partie à la fin."""
    owner = db.players.alias("owner")
    async with store.engine.connect() as conn:
        rows = (await conn.execute(
            select(a.id, a.name, a.version, owner.c.id.label("author_id"), owner.c.name.label("author"),
                   owner.c.country, r_.rating, r_.margin, r_.games, r_.wins, r_.losses, r_.draws)
            .join(owner, owner.c.id == a.owner_id).outerjoin(db.arena_ratings, r_.player_id == a.id)
            .where(a.status == "active"))).mappings().all()
        house = (await conn.execute(select(db.arena_ratings).where(r_.player_id.in_(list(HOUSE))))).mappings().all()
    out = [{"id": row["id"], "name": row["name"], "version": row["version"], "house": None,
            "author": {"id": row["author_id"], "name": row["author"], "country": row["country"]},
            **_rating_json(row)} for row in rows]
    by_house = {row["player_id"]: row for row in house}
    out += [{"id": pid, "name": bot.LEVELS[lv].name, "version": None, "house": lv, "author": None,
             **_rating_json(by_house.get(pid), house=True)} for pid, lv in HOUSE.items()]
    out.sort(key=lambda x: (x["rating"] is None, -(x["rating"] or 0)))
    for i, row in enumerate(out):
        row["rank"] = i + 1 if row["rating"] is not None else None
    return out


async def _games_of(conn, pid: str, limit: int = 30) -> list[dict]:
    rows = (await conn.execute(
        select(g.id, g.p1_id, g.p2_id, g.winner, g.reason, g.ply, g.ended_at, g.terrain_mode, g.setup)
        .where(g.mode == "arena", or_(g.p1_id == pid, g.p2_id == pid)).order_by(g.ended_at.desc()).limit(limit)
    )).mappings().all()
    names = await _names(conn, {row["p1_id"] for row in rows} | {row["p2_id"] for row in rows})
    out = []
    for row in rows:
        side = 1 if row["p1_id"] == pid else 2
        rival = row["p2_id"] if side == 1 else row["p1_id"]
        out.append({"id": row["id"], "side": side, "opponent": {"id": rival, **names.get(rival, {})},
                    "result": "draw" if row["winner"] is None else "win" if row["winner"] == side else "loss",
                    "reason": row["reason"], "ply": row["ply"], "endedAt": row["ended_at"],
                    "terrain": row["terrain_mode"],
                    # Jouée avec la mise en place actuelle (les anciennes gardent la leur).
                    "currentSetup": (row["setup"] or "classic") == C.SETUP})
    return out


async def _names(conn, ids: set[str]) -> dict[str, dict]:
    if not ids:
        return {}
    pl = db.players.c
    rows = (await conn.execute(select(pl.id, pl.name, a.version).outerjoin(db.arena_bots, a.id == pl.id)
                               .where(pl.id.in_(list(ids))))).all()
    return {pid: {"name": name, "version": version, "house": HOUSE.get(pid)} for pid, name, version in rows}


async def bot_view(bot_id: str) -> dict:
    async with store.engine.connect() as conn:
        rating = (await conn.execute(select(db.arena_ratings).where(r_.player_id == bot_id))).mappings().first()
        if bot_id in HOUSE:
            lv = HOUSE[bot_id]
            return {"id": bot_id, "name": bot.LEVELS[lv].name, "house": lv, "version": None, "status": "active",
                    "author": None, "versions": [], **_rating_json(rating, house=True),
                    "recent": await _games_of(conn, bot_id)}
        row = (await conn.execute(select(a.id, a.owner_id, a.name, a.version, a.status, a.error, a.size, a.sha256,
                                         a.created_at, a.activated_at).where(a.id == bot_id))).mappings().first()
        if row is None:
            raise ArenaError(404, "Bot introuvable.")
        author = await store.get_player(row["owner_id"])
        versions = (await conn.execute(
            select(a.id, a.version, a.status, a.created_at, r_.rating, r_.games)
            .outerjoin(db.arena_ratings, r_.player_id == a.id)
            .where(a.owner_id == row["owner_id"], a.name == row["name"]).order_by(a.version.desc()))).mappings().all()
        queued = (await conn.execute(select(func.count()).select_from(db.arena_jobs).where(
            or_(j.red_id == bot_id, j.blue_id == bot_id)))).scalar()
        games = await _games_of(conn, bot_id)
    return {
        "id": bot_id, "name": row["name"], "house": None, "version": row["version"], "status": row["status"],
        "error": row["error"], "size": row["size"], "sha256": row["sha256"], "createdAt": row["created_at"],
        "activatedAt": row["activated_at"], "queued": queued,
        "author": {"id": author.id, "name": author.name, "country": author.country} if author else None,
        "versions": [{"id": v["id"], "version": v["version"], "status": v["status"], "createdAt": v["created_at"],
                      "rating": round(v["rating"]) if v["rating"] is not None else None, "games": v["games"] or 0}
                     for v in versions],
        **_rating_json(rating), "recent": games,
    }


SHOWCASE_MIN_PLIES = 12  # une partie trop courte ne montre pas grand-chose


async def showcase() -> dict | None:
    """La partie rejouée sur l'accueil : une partie récente du meilleur bot (de la
    communauté de préférence), avec la mise en place actuelle. C'est la seule partie de
    l'arène visible quand la relecture est fermée : le serveur la choisit, le visiteur ne
    peut pas en demander une autre."""
    from app.services.views import game_view, position_json

    board = await leaderboard()
    ranked = [r for r in board if r["rating"] is not None and r["games"] > 0]
    best = next((r for r in ranked if not r["house"]), ranked[0] if ranked else None)
    if best is None:
        return None
    async with store.engine.connect() as conn:
        recent = [g for g in await _games_of(conn, best["id"]) if g["currentSetup"]]
    pick = next((g for g in recent if g["ply"] >= SHOWCASE_MIN_PLIES), recent[0] if recent else None)
    game = await store.get_game(pick["id"]) if pick else None
    if game is None or len(game.states) < 2:
        return None
    return {**game_view(game, None), "positions": [position_json(s) for s in game.states]}


async def mine(owner: Player) -> list[dict]:
    """Les bots du joueur : dernière version de chaque nom."""
    async with store.engine.connect() as conn:
        rows = (await conn.execute(
            select(a.id, a.name, a.version, a.status, a.error, a.created_at, r_.rating, r_.margin, r_.games,
                   r_.wins, r_.losses, r_.draws)
            .outerjoin(db.arena_ratings, r_.player_id == a.id)
            .where(a.owner_id == owner.id).order_by(a.name, a.version.desc()))).mappings().all()
    out, seen = [], set()
    for row in rows:
        if row["name"] in seen:
            continue
        seen.add(row["name"])
        out.append({"id": row["id"], "name": row["name"], "version": row["version"], "status": row["status"],
                    "error": row["error"], "createdAt": row["created_at"], **_rating_json(row)})
    return out
