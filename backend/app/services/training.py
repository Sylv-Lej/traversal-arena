"""Puzzles (comme sur chess.com) : puzzles classés, puzzle du jour, Puzzle Rush.

- **Classés** : chaque joueur a un classement puzzles (Glicko-2, `ratings.time_class =
  "puzzle"`) ; chaque puzzle a le sien. On propose un puzzle jamais tenté, proche du
  niveau du joueur. Réussi au premier essai : le joueur gagne des points, le puzzle en
  perd (et inversement). Indice ou solution demandés : compté comme raté. Un puzzle
  classé en cours est repris tel quel (recharger la page ne le fait pas changer).
  **Raté, il bloque la suite** : on le rejoue (non classé) jusqu'à le réussir.
- **Variantes** : à certaines étapes d'un gain, quelques coups gagnent aussi vite ; tous
  sont acceptés (arbre `puzzles.tree`), et la tentative garde la ligne jouée (`line`).
- **Explications** : une fois le puzzle fini, chaque coup de la solution dit ce qu'il
  enseigne (charge, hauteur, soutien, parade, double menace…), voir `puzzles.explain`.
- **Rejouer** un puzzle déjà vu : jamais classé.
- **Puzzle du jour** : le même pour tout le monde, non classé.
- **Puzzle Rush** : 3 min, 5 min ou Survie ; 20 puzzles au plus, la difficulté monte vite
  (du plus facile au plus dur du catalogue), 3 erreurs et c'est fini. Meilleur score par
  mode, classement des Rush.

Le serveur vérifie chaque coup (la solution ne part jamais au navigateur avant la fin).
Un coup est bon s'il est celui de la solution, ou s'il gagne la partie immédiatement.
"""

import datetime as dt
import hashlib
import time

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app import db, puzzles
from app.engine import IllegalMove, apply_move, find_move, legal_moves
from app.services import games as svc
from app.services import ranks, rating
from app.services.rating import Rating
from app.services.store import Player, _id, store
from app.services.views import move_json, position_json, record_json

PUZZLE_CLASS = "puzzle"
PLAYER_START = Rating(rating=1200.0, rd=200.0)  # premier classement puzzles (variations modérées)
PUZZLE_RD = 150.0  # un puzzle neuf part avec une note déjà assez sûre
WINDOW = 200  # puzzle proposé : ± cette marge autour du classement du joueur
DAILY_RANGE = (1050, 1700)
RUSH_MODES = {"3min": 180, "5min": 300, "survival": None}
RUSH_STRIKES, RUSH_MAX = 3, 20
# Difficulté du n-ième puzzle du Rush (réussi ou raté) : ~700 → ~1850 en 20 puzzles.
RUSH_START, RUSH_STEP = 700, 60
RUSH_WINDOWS = (30, 100, 300, 10_000)  # serré : la montée reste régulière

p_c, a_c, r_c = db.puzzles.c, db.puzzle_attempts.c, db.puzzle_rushes.c


class PuzzleError(svc.GameError):
    pass


# --- Chargement ---------------------------------------------------------------------------


async def seed() -> int:
    """Charge les puzzles livrés avec le site (sans toucher aux notes déjà acquises)."""
    data = puzzles.load()
    if not data:
        return 0
    ids = {p["id"] for p in data}
    async with store.engine.begin() as conn:
        have = set((await conn.execute(select(p_c.id))).scalars().all())
        if have == ids:
            return 0
        # Nouveau jeu livré : les puzzles retirés partent (avec leurs tentatives) ; ceux qui
        # restent gardent leur classement et leurs statistiques.
        await conn.execute(db.puzzles.delete().where(p_c.id.not_in(ids)))
        now = time.time()
        rows = [{"id": p["id"], "terrain": p["terrain"], "start": p["start"], "solution": p["solution"],
                 "tree": p.get("tree"), "themes": p["themes"], "side": p["side"], "rating": p["rating"],
                 "rd": PUZZLE_RD, "vol": 0.06, "plays": 0, "solves": 0, "created_at": now} for p in data]
        for i in range(0, len(rows), 200):
            await conn.execute(pg_insert(db.puzzles).values(rows[i:i + 200]).on_conflict_do_nothing())
    return len(ids - have)


# --- Position d'une tentative ------------------------------------------------------------


def _tree(pz) -> list[dict]:
    """Arbre des variantes ; à défaut, la solution en ligne droite."""
    if pz.get("tree"):
        return pz["tree"]
    sol, node = pz["solution"], None
    last = len(sol) - 1 if len(sol) % 2 == 0 else len(sol) - 2  # dernier coup du joueur (indice impair)
    for i in range(last, 0, -2):
        opt = {"m": sol[i]}
        if node is not None:
            opt.update(r=sol[i + 1], next=node)
        node = [opt]
    return node or []


def _node(pz, played: list[dict]) -> list[dict]:
    """Coups acceptés à ce point de la ligne jouée (coup adverse initial compris)."""
    node = _tree(pz)
    for d in played[1::2]:
        opt = next((o for o in node if o["m"]["pieceId"] == d["pieceId"] and o["m"]["kind"] == d["kind"]
                    and o["m"]["to"] == d["to"]), None)
        node = opt.get("next", []) if opt else []
    return node


def _played(att: dict, pz) -> list[dict]:
    return att["line"] if att.get("line") else pz["solution"][: att["step"]]


def _complete(pz, played: list[dict]) -> list[dict]:
    """La ligne jouée, prolongée par la ligne principale de l'arbre jusqu'au bout."""
    out, node = list(played), _node(pz, played)
    while node:
        out.append(node[0]["m"])
        if "next" not in node[0]:
            break
        out.append(node[0]["r"])
        node = node[0]["next"]
    return out


def _replay(pz, moves: list[dict], positions: list | None = None):
    """État de départ, puis les coups `moves` ; avec leur notation (et, si demandé, la
    position après chacun : le front anime coup par coup)."""
    s = puzzles.state_from_json(pz["start"])
    records = []
    if positions is not None:
        positions.append(position_json(s))
    for d in moves:
        m = find_move(s, d["pieceId"], d["kind"], d["to"])
        records.append(record_json(svc._record(None, m, s)))
        s = apply_move(s, m)
        if positions is not None:
            positions.append(position_json(s))
    return s, records


async def _puzzle(conn: AsyncConnection, pid: str, lock: bool = False):
    q = select(db.puzzles).where(p_c.id == pid)
    if lock:
        q = q.with_for_update()
    return (await conn.execute(q)).mappings().first()


async def _attempt(conn: AsyncConnection, aid: str, me: Player, lock: bool = False):
    q = select(db.puzzle_attempts).where(a_c.id == aid)
    if lock:
        q = q.with_for_update()
    row = (await conn.execute(q)).mappings().first()
    if row is None or row["player_id"] != me.id:
        raise PuzzleError(404, "Puzzle introuvable.")
    return dict(row)


async def _player_rating(conn: AsyncConnection, pid: str, lock: bool = False) -> Rating:
    await conn.execute(pg_insert(db.ratings).values(
        player_id=pid, time_class=PUZZLE_CLASS, rating=PLAYER_START.rating, rd=PLAYER_START.rd,
        vol=PLAYER_START.vol, games=0, wins=0, losses=0, draws=0).on_conflict_do_nothing())
    q = select(db.ratings).where(db.ratings.c.player_id == pid, db.ratings.c.time_class == PUZZLE_CLASS)
    if lock:
        q = q.with_for_update()
    r = (await conn.execute(q)).mappings().first()
    return Rating(r["rating"], r["rd"], r["vol"], r["games"], r["wins"], r["losses"], r["draws"])


# --- Vue ----------------------------------------------------------------------------------


async def view(conn: AsyncConnection, att: dict, me: Player) -> dict:
    pz = await _puzzle(conn, att["puzzle_id"])
    done = att["status"] != "playing"
    positions: list = []
    line = _played(att, pz)
    s, played = _replay(pz, line, positions)
    themes = pz["themes"]
    out = {
        "id": att["id"], "puzzleId": pz["id"], "mode": att["mode"], "status": att["status"],
        "rated": att["rated"], "hinted": att["hinted"], "revealed": att["revealed"], "side": pz["side"],
        "terrain": {"mode": pz["terrain"], "heights": pz["start"]["heights"]},
        "start": position_json(puzzles.state_from_json(pz["start"])),
        "moves": played, "positions": positions, "position": position_json(s),
        "legalMoves": [move_json(m) for m in legal_moves(s)] if not done and not s.over else [],
        "playerMoves": len(pz["solution"][1::2]),
        # Consigne (avant de jouer) : gagner, sauver la partie ou prendre l'avantage.
        "goal": "win" if any(t.startswith("winIn") for t in themes) else "save" if "save" in themes else "advantage",
        "wrong": att["wrong"],
        "playerRating": round((await _player_rating(conn, me.id)).rating),
        "daily": att["daily"],
    }
    if att["wrong"]:  # position après le coup raté (affichée avant la solution)
        try:
            out["wrongPosition"] = position_json(apply_move(s, find_move(
                s, att["wrong"]["pieceId"], att["wrong"]["kind"], att["wrong"]["to"])))
        except IllegalMove:
            pass
    if done or att["revealed"]:
        sol_positions: list = []
        full_line = _complete(pz, line)
        _, full = _replay(pz, full_line, sol_positions)
        out["solution"] = full
        out["solutionPositions"] = sol_positions
        out["notes"] = _notes(pz, full_line)
        out["puzzle"] = {"rating": round(pz["rating"]), "themes": pz["themes"], "plays": pz["plays"],
                         "solves": pz["solves"]}
    if att["rating_after"] is not None:
        out["ratingChange"] = {"before": round(att["rating_before"]), "after": round(att["rating_after"])}
    if att["rush_id"]:
        out["rushId"] = att["rush_id"]
    return out


def _notes(pz, line: list[dict]) -> list[list[dict] | None]:
    """Explication de chaque coup du joueur dans `line` (None pour les coups adverses)."""
    s = puzzles.state_from_json(pz["start"])
    out: list[list[dict] | None] = []
    for i, d in enumerate(line):
        m = find_move(s, d["pieceId"], d["kind"], d["to"])
        out.append(puzzles.explain(s, m) if i % 2 == 1 else None)
        s = apply_move(s, m)
    return out


# --- Tentatives ---------------------------------------------------------------------------


async def _new_attempt(conn: AsyncConnection, me: Player, pz, mode: str, rated: bool,
                       rush_id: str | None = None, daily: str | None = None) -> dict:
    row = {"id": _id(10), "player_id": me.id, "puzzle_id": pz["id"], "mode": mode, "rush_id": rush_id,
           "step": 1, "status": "playing", "rated": rated, "hinted": False, "revealed": False, "wrong": None,
           "rating_before": None, "rating_after": None, "daily": daily, "started_at": time.time(),
           "ended_at": None, "line": None}
    await conn.execute(pg_insert(db.puzzle_attempts).values(**row))
    return row


async def _finish(conn: AsyncConnection, att: dict, solved: bool) -> None:
    """Fin d'une tentative : statut, et classements si elle était classée."""
    # En classé, un indice ou la solution demandés font compter le puzzle comme raté.
    success = solved and not (att["mode"] == "rated" and (att["hinted"] or att["revealed"]))
    att["status"] = "solved" if success else "failed"
    att["ended_at"] = time.time()
    pz = await _puzzle(conn, att["puzzle_id"], lock=True)
    await conn.execute(update(db.puzzles).where(p_c.id == pz["id"]).values(
        plays=pz["plays"] + 1, solves=pz["solves"] + int(success)))
    if att["rated"]:
        me_r = await _player_rating(conn, att["player_id"], lock=True)
        pz_r = Rating(pz["rating"], pz["rd"], pz["vol"])
        s = 1.0 if success else 0.0
        new_me, new_pz = rating.update(me_r, pz_r, s), rating.update(pz_r, me_r, 1 - s)
        await conn.execute(update(db.ratings).where(
            db.ratings.c.player_id == att["player_id"], db.ratings.c.time_class == PUZZLE_CLASS).values(
            rating=new_me.rating, rd=new_me.rd, vol=new_me.vol, games=new_me.games, wins=new_me.wins,
            losses=new_me.losses, draws=new_me.draws))
        await conn.execute(update(db.puzzles).where(p_c.id == pz["id"]).values(
            rating=new_pz.rating, rd=new_pz.rd, vol=new_pz.vol))
        att["rating_before"], att["rating_after"] = me_r.rating, new_me.rating
    await conn.execute(update(db.puzzle_attempts).where(a_c.id == att["id"]).values(
        status=att["status"], ended_at=att["ended_at"], rating_before=att["rating_before"],
        rating_after=att["rating_after"], step=att["step"], wrong=att["wrong"],
        hinted=att["hinted"], revealed=att["revealed"], line=att.get("line")))
    if att["rush_id"]:
        await _rush_after(conn, att, success)


async def _pick(conn: AsyncConnection, me: Player, target: float, exclude_rush: str | None = None,
                windows: tuple[int, ...] = (WINDOW, WINDOW * 2, WINDOW * 5, 10_000)):
    """Puzzle jamais tenté (ou pas dans ce Rush), au plus près de `target`."""
    if exclude_rush:
        seen = select(a_c.puzzle_id).where(a_c.rush_id == exclude_rush)
    else:
        seen = select(a_c.puzzle_id).where(a_c.player_id == me.id)
    for width in windows:
        rows = (await conn.execute(
            select(db.puzzles).where(p_c.rating.between(target - width, target + width), p_c.id.not_in(seen))
            .order_by(func.random()).limit(1))).mappings().first()
        if rows:
            return rows
    # Tout a été vu : on reprend le plus proche (non classé, voir `next_rated`).
    return (await conn.execute(select(db.puzzles).order_by(func.abs(p_c.rating - target)).limit(1))).mappings().first()


async def _blocking(conn: AsyncConnection, me: Player):
    """Dernier puzzle classé raté et pas encore réussi depuis : il bloque la suite."""
    last = (await conn.execute(select(db.puzzle_attempts).where(
        a_c.player_id == me.id, a_c.mode == "rated", a_c.status != "playing")
        .order_by(a_c.started_at.desc()).limit(1))).mappings().first()
    if last is None or last["status"] == "solved":
        return None
    solved_since = (await conn.execute(select(func.count()).select_from(db.puzzle_attempts).where(
        a_c.player_id == me.id, a_c.puzzle_id == last["puzzle_id"], a_c.status == "solved",
        a_c.started_at > last["started_at"]))).scalar()
    return None if solved_since else last


async def next_rated(me: Player) -> dict:
    async with store.engine.begin() as conn:
        # Un puzzle classé en cours est repris : on ne peut pas en changer pour éviter un dur.
        current = (await conn.execute(select(db.puzzle_attempts).where(
            a_c.player_id == me.id, a_c.mode == "rated", a_c.status == "playing")
            .order_by(a_c.started_at.desc()).limit(1))).mappings().first()
        if current:
            return await view(conn, dict(current), me)
        # Puzzle raté : on le rejoue (non classé) jusqu'à le réussir, pas de puzzle suivant.
        blocked = await _blocking(conn, me)
        if blocked:
            again = (await conn.execute(select(db.puzzle_attempts).where(
                a_c.player_id == me.id, a_c.puzzle_id == blocked["puzzle_id"], a_c.mode == "retry",
                a_c.status == "playing").order_by(a_c.started_at.desc()).limit(1))).mappings().first()
            if again:
                return await view(conn, dict(again), me)
            pz = await _puzzle(conn, blocked["puzzle_id"])
            return await view(conn, await _new_attempt(conn, me, pz, "retry", rated=False), me)
        target = (await _player_rating(conn, me.id)).rating
        pz = await _pick(conn, me, target)
        if pz is None:
            raise PuzzleError(404, "Aucun puzzle disponible.")
        seen = (await conn.execute(select(func.count()).select_from(db.puzzle_attempts).where(
            a_c.player_id == me.id, a_c.puzzle_id == pz["id"]))).scalar()
        att = await _new_attempt(conn, me, pz, "rated" if not seen else "retry", rated=not seen)
        return await view(conn, att, me)


async def get(aid: str, me: Player) -> dict:
    async with store.engine.begin() as conn:
        return await view(conn, await _attempt(conn, aid, me), me)


async def play(aid: str, me: Player, piece_id: str, kind: str, to: int | None) -> dict:
    async with store.engine.begin() as conn:
        att = await _attempt(conn, aid, me, lock=True)
        if att["status"] != "playing":
            raise PuzzleError(409, "Ce puzzle est terminé.")
        if att["rush_id"]:
            await _rush_check_time(conn, att["rush_id"])
            att = await _attempt(conn, aid, me, lock=True)
            if att["status"] != "playing":
                return await view(conn, att, me)
        pz = await _puzzle(conn, att["puzzle_id"])
        line = _played(att, pz)
        s, _ = _replay(pz, line)
        try:
            move = find_move(s, piece_id, kind, to)
        except IllegalMove as exc:
            raise PuzzleError(422, str(exc)) from exc
        after = apply_move(s, move)
        # Bon coup : l'un des coups acceptés à cette étape (variantes comprises), ou toute
        # victoire immédiate.
        opt = next((o for o in _node(pz, line) if puzzles.same(move, o["m"])), None)
        if opt is None and not (after.over and after.winner == pz["side"]):
            att["wrong"] = record_json(svc._record(None, move, s))
            await _finish(conn, att, solved=False)
            return await view(conn, att, me)
        line = line + [puzzles.move_key(move)]
        last = after.over or opt is None or "next" not in opt
        if not last:
            line.append(opt["r"])  # la réponse de l'adversaire est jouée d'office
        att["line"], att["step"] = line, len(line)
        if last:
            await _finish(conn, att, solved=True)
        else:
            await conn.execute(update(db.puzzle_attempts).where(a_c.id == aid).values(step=att["step"], line=line))
        return await view(conn, att, me)


async def hint(aid: str, me: Player) -> dict:
    """Pièce à jouer (compte comme raté en classé)."""
    async with store.engine.begin() as conn:
        att = await _attempt(conn, aid, me, lock=True)
        if att["status"] != "playing":
            raise PuzzleError(409, "Ce puzzle est terminé.")
        pz = await _puzzle(conn, att["puzzle_id"])
        line = _played(att, pz)
        s, _ = _replay(pz, line)
        piece = s.piece(_node(pz, line)[0]["m"]["pieceId"])
        await conn.execute(update(db.puzzle_attempts).where(a_c.id == aid).values(hinted=True))
        return {"pieceId": piece.id, "sq": piece.sq}


async def reveal(aid: str, me: Player) -> dict:
    """Montre la solution : la tentative est perdue."""
    async with store.engine.begin() as conn:
        att = await _attempt(conn, aid, me, lock=True)
        if att["status"] == "playing":
            att["revealed"] = True
            await _finish(conn, att, solved=False)
        return await view(conn, att, me)


async def retry(pid: str, me: Player) -> dict:
    async with store.engine.begin() as conn:
        pz = await _puzzle(conn, pid)
        if pz is None:
            raise PuzzleError(404, "Puzzle introuvable.")
        att = await _new_attempt(conn, me, pz, "retry", rated=False)
        return await view(conn, att, me)


def daily_key(day: dt.date | None = None) -> str:
    return (day or dt.date.today()).isoformat()


async def daily(me: Player) -> dict:
    """Puzzle du jour : le même pour tout le monde, choisi par la date."""
    key = daily_key()
    async with store.engine.begin() as conn:
        row = (await conn.execute(select(db.puzzle_attempts).where(
            a_c.player_id == me.id, a_c.daily == key).order_by(a_c.started_at.desc()).limit(1))).mappings().first()
        if row:
            return await view(conn, dict(row), me)
        ids = (await conn.execute(select(p_c.id).where(p_c.rating.between(*DAILY_RANGE)).order_by(p_c.id))).scalars().all()
        if not ids:
            ids = (await conn.execute(select(p_c.id).order_by(p_c.id))).scalars().all()
        if not ids:
            raise PuzzleError(404, "Aucun puzzle disponible.")
        pick = ids[int(hashlib.sha256(key.encode()).hexdigest(), 16) % len(ids)]
        att = await _new_attempt(conn, me, await _puzzle(conn, pick), "daily", rated=False, daily=key)
        return await view(conn, att, me)


async def stats(me: Player) -> dict:
    async with store.engine.begin() as conn:
        r = await _player_rating(conn, me.id)
        solved = (await conn.execute(select(func.count()).select_from(db.puzzle_attempts).where(
            a_c.player_id == me.id, a_c.status == "solved"))).scalar()
        tried = (await conn.execute(select(func.count()).select_from(db.puzzle_attempts).where(
            a_c.player_id == me.id, a_c.status != "playing"))).scalar()
        best = dict((await conn.execute(select(r_c.mode, func.max(r_c.score)).where(
            r_c.player_id == me.id, r_c.status == "over").group_by(r_c.mode))).all())
        total = (await conn.execute(select(func.count()).select_from(db.puzzles))).scalar()
    return {"rating": round(r.rating), "provisional": r.rd > 110, "rated": r.games, "solved": solved,
            "rank": ranks.rank_from(r.rating, r.games), "tried": tried, "rushBest": {m: best.get(m, 0) for m in RUSH_MODES}, "total": total}


# --- Puzzle Rush --------------------------------------------------------------------------


async def rush_start(me: Player, mode: str) -> dict:
    if mode not in RUSH_MODES:
        raise PuzzleError(422, "Mode de Rush inconnu.")
    now = time.time()
    rid = _id(10)
    secs = RUSH_MODES[mode]
    async with store.engine.begin() as conn:
        await conn.execute(update(db.puzzle_rushes).where(r_c.player_id == me.id, r_c.status == "running")
                           .values(status="over", ended_at=now))
        await conn.execute(pg_insert(db.puzzle_rushes).values(
            id=rid, player_id=me.id, mode=mode, status="running", score=0, strikes=0, attempt_id=None,
            started_at=now, deadline_at=now + secs if secs else None, ended_at=None))
        await _rush_next(conn, me, rid, 0)
    return await rush_view(rid, me)


async def _rush_next(conn: AsyncConnection, me: Player, rid: str, done: int) -> None:
    """Puzzle suivant : la difficulté suit le nombre de puzzles joués, pas le score."""
    pz = await _pick(conn, me, RUSH_START + RUSH_STEP * done, exclude_rush=rid, windows=RUSH_WINDOWS)
    att = await _new_attempt(conn, me, pz, "rush", rated=False, rush_id=rid)
    await conn.execute(update(db.puzzle_rushes).where(r_c.id == rid).values(attempt_id=att["id"]))


async def _rush_after(conn: AsyncConnection, att: dict, success: bool) -> None:
    rush = (await conn.execute(select(db.puzzle_rushes).where(r_c.id == att["rush_id"]).with_for_update())).mappings().first()
    if rush is None or rush["status"] != "running":
        return
    score, strikes = rush["score"] + int(success), rush["strikes"] + int(not success)
    over = (strikes >= RUSH_STRIKES or score + strikes >= RUSH_MAX
            or (rush["deadline_at"] and time.time() > rush["deadline_at"]))
    await conn.execute(update(db.puzzle_rushes).where(r_c.id == rush["id"]).values(
        score=score, strikes=strikes, status="over" if over else "running", ended_at=time.time() if over else None))
    if not over:
        me = Player(id=rush["player_id"], name="")
        await _rush_next(conn, me, rush["id"], score + strikes)


async def _rush_check_time(conn: AsyncConnection, rid: str) -> None:
    """Temps écoulé : le Rush s'arrête (la tentative en cours ne compte pas)."""
    rush = (await conn.execute(select(db.puzzle_rushes).where(r_c.id == rid).with_for_update())).mappings().first()
    if rush and rush["status"] == "running" and rush["deadline_at"] and time.time() > rush["deadline_at"]:
        await conn.execute(update(db.puzzle_rushes).where(r_c.id == rid).values(status="over", ended_at=time.time()))
        await conn.execute(update(db.puzzle_attempts).where(a_c.rush_id == rid, a_c.status == "playing")
                           .values(status="failed", ended_at=time.time()))


async def rush_view(rid: str, me: Player) -> dict:
    async with store.engine.begin() as conn:
        await _rush_check_time(conn, rid)
        rush = (await conn.execute(select(db.puzzle_rushes).where(r_c.id == rid))).mappings().first()
        if rush is None or rush["player_id"] != me.id:
            raise PuzzleError(404, "Rush introuvable.")
        history = (await conn.execute(
            select(a_c.status, p_c.rating, a_c.puzzle_id).join(db.puzzles, p_c.id == a_c.puzzle_id)
            .where(a_c.rush_id == rid, a_c.status != "playing").order_by(a_c.started_at))).all()
        best = (await conn.execute(select(func.max(r_c.score)).where(
            r_c.player_id == me.id, r_c.mode == rush["mode"], r_c.status == "over"))).scalar() or 0
        current = None
        if rush["status"] == "running" and rush["attempt_id"]:
            current = await view(conn, await _attempt(conn, rush["attempt_id"], me), me)
        return {
            "id": rush["id"], "mode": rush["mode"], "status": rush["status"], "score": rush["score"],
            "strikes": rush["strikes"], "maxStrikes": RUSH_STRIKES, "maxPuzzles": RUSH_MAX,
            "remainingMs": max(0, int((rush["deadline_at"] - time.time()) * 1000)) if rush["deadline_at"] else None,
            "attempt": current, "best": max(best, rush["score"] if rush["status"] == "over" else 0),
            "history": [{"solved": st == "solved", "rating": round(rt), "puzzleId": pid} for st, rt, pid in history],
        }


async def rush_leaderboard(mode: str, limit: int = 20) -> list[dict]:
    if mode not in RUSH_MODES:
        raise PuzzleError(422, "Mode de Rush inconnu.")
    pl = db.players.c
    async with store.engine.connect() as conn:
        rows = (await conn.execute(
            select(r_c.player_id, func.max(r_c.score).label("best"), pl.name, pl.country)
            .join(db.players, pl.id == r_c.player_id)
            .where(r_c.mode == mode, r_c.status == "over", r_c.score > 0)
            .group_by(r_c.player_id, pl.name, pl.country).order_by(func.max(r_c.score).desc()).limit(limit))).all()
    return [{"rank": i + 1, "id": pid, "name": name, "country": country, "score": best}
            for i, (pid, best, name, country) in enumerate(rows)]


async def puzzle_leaderboard(limit: int = 50) -> list[dict]:
    r, pl = db.ratings.c, db.players.c
    async with store.engine.connect() as conn:
        rows = (await conn.execute(
            select(r.player_id, r.rating, r.games, pl.name, pl.country).join(db.players, pl.id == r.player_id)
            .where(r.time_class == PUZZLE_CLASS, r.games > 0).order_by(r.rating.desc()).limit(limit))).all()
    return [{"rank": i + 1, "id": pid, "name": name, "country": country, "rating": round(rt), "games": g,
             "tier": ranks.rank_from(rt, g)} for i, (pid, rt, g, name, country) in enumerate(rows)]

