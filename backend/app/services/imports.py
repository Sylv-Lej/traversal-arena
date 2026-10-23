"""Import d'une partie jouée sur traversalgame.com, pour en faire le bilan.

Le joueur colle le lien de la partie (`…/game/<uuid>`, y compris sous la forme
`/signup?redirect=/game/<uuid>`). Le site ne montre une partie qu'à un compte connecté :
le backend se connecte avec le compte de `TRAVERSAL_LOGIN` / `TRAVERSAL_PASSWORD` (vide :
import fermé), lit `/api/games/<uuid>/full-state`, puis rejoue chaque coup avec NOTRE
moteur. Un coup illégal chez nous (règle tranchée autrement, voir `RULES.md`) refuse
l'import. La partie devient une partie `import` terminée, non classée, sans comptes
(pseudos et classements d'origine gardés dans `imported`) : le bilan existant s'y applique.
Une même partie n'est importée qu'une fois (`import_ref`), son bilan sert à tout le monde.

Format d'origine : une grille `board[row][col]` de hauteurs, les pièces au départ
(`p1_5`, type, case) et les coups `{pieceId, fromRow, fromCol, toRow, toCol, isCapture,
isFinish, player}`. Leur joueur 1 part de la rangée 9, notre rouge de y = 0.
"""

import asyncio
import logging
import os
import re
import time

import httpx
from sqlalchemy import select

from app import db
from app.engine import IllegalMove, apply_move, end_game, find_move, new_game
from app.engine import config as C
from app.engine.types import sq
from app.services.games import GameError, _record
from app.services.store import Game, Player, store

log = logging.getLogger("traversal.imports")

API = "https://api.traversalgame.com"
SITE = "traversalgame.com"
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
# Leur raison de fin -> la nôtre (une fin « sur le plateau » est retrouvée par le rejeu).
REASONS = {"resign": "resign", "resignation": "resign", "timeout": "timeout", "time": "timeout",
           "agreement": "agreement", "draw_agreement": "agreement"}

ILLEGAL = "Un coup de cette partie est illégal selon nos règles : partie non importée."
DOWN = "traversalgame.com ne répond pas : réessaie plus tard."

_client: httpx.AsyncClient | None = None
_login_lock = asyncio.Lock()


def enabled() -> bool:
    return bool(os.environ.get("TRAVERSAL_LOGIN") and os.environ.get("TRAVERSAL_PASSWORD"))


def parse_ref(link: str) -> str:
    """Identifiant de la partie dans un lien traversalgame.com (ou l'identifiant seul)."""
    link = link.strip()
    m = _UUID.search(link)
    if m is None or (link != m.group(0) and SITE not in link):
        raise GameError(422, "Lien de partie traversalgame.com invalide.")
    return m.group(0).lower()


async def _login(client: httpx.AsyncClient) -> None:
    r = await client.post("/auth/login", json={
        "email": os.environ["TRAVERSAL_LOGIN"], "password": os.environ["TRAVERSAL_PASSWORD"]})
    if r.status_code != 200:
        log.error("connexion à %s refusée : %s", SITE, r.status_code)
        raise GameError(502, DOWN)


async def fetch(ref: str) -> dict:
    """État complet de la partie, avec la session du compte d'import (reconnecté si besoin)."""
    global _client
    if not enabled():
        raise GameError(503, "L'import de parties n'est pas configuré.")
    async with _login_lock:
        if _client is None:
            _client = httpx.AsyncClient(base_url=API, timeout=15, headers={"Origin": f"https://www.{SITE}"})
            await _login(_client)
    try:
        r = await _client.get(f"/api/games/{ref}/full-state")
        if r.status_code in (401, 403):
            async with _login_lock:
                await _login(_client)
            r = await _client.get(f"/api/games/{ref}/full-state")
    except httpx.HTTPError as exc:
        log.warning("lecture de la partie %s sur %s : %s", ref, SITE, exc)
        raise GameError(502, DOWN) from exc
    if r.status_code in (404, 422):
        raise GameError(404, "Partie introuvable sur traversalgame.com.")
    if r.status_code != 200:
        log.error("lecture de la partie %s sur %s : %s", ref, SITE, r.status_code)
        raise GameError(502, DOWN)
    return r.json()


def convert(data: dict, ref: str, importer_id: str) -> Game:
    """Partie d'origine -> partie `import` terminée, rejouée et vérifiée par notre moteur."""
    if data.get("status") != "finished" or not data.get("game_over"):
        raise GameError(409, "Cette partie n'est pas terminée.")
    board = data["board"]
    n = len(board)
    if n != C.SIZE or any(len(row) != C.SIZE for row in board):
        raise GameError(422, "Plateau non pris en charge.")

    def square(row: int, col: int) -> int:
        return sq(col, n - 1 - row)

    heights = [0] * C.SQUARES
    for r, line in enumerate(board):
        for c, h in enumerate(line):
            heights[square(r, c)] = int(h)
    state = new_game(tuple(heights), C.MOVE_LIMIT, C.SETUP)
    # Leurs pièces -> les nôtres, par la case de départ (même mise en place exigée).
    by_sq = {p.sq: p for p in state.pieces}
    ids: dict[str, str] = {}
    for p in data.get("initial_pieces") or []:
        ours = by_sq.get(square(p["row"], p["col"]))
        if ours is None or ours.owner != p["player"] or ours.kind != p["type"]:
            raise GameError(422, "Mise en place des pièces non prise en charge.")
        ids[p["id"]] = ours.id
    if len(ids) != len(state.pieces):
        raise GameError(422, "Mise en place des pièces non prise en charge.")

    game = Game(
        id=store.new_game_id(), mode="import", terrain_mode=str(data.get("terrain_selected") or "random")[:16],
        seed=0, players=[None, None], created_by=importer_id, states=[state], status="finished",
        time_class="import", import_ref=ref,
    )
    for i, m in enumerate(data.get("move_history") or []):
        before = game.state
        pid = ids.get(m.get("pieceId"))
        if before.over or pid is None or m.get("player") != before.to_move:
            log.warning("partie %s : coup %d incohérent (%s)", ref, i + 1, m)
            raise GameError(422, ILLEGAL)
        if m.get("isFinish"):
            kind, to = "exit", None
        else:
            kind, to = ("attack" if m.get("isCapture") else "move"), square(m["toRow"], m["toCol"])
        try:
            move = find_move(before, pid, kind, to)
        except IllegalMove as exc:
            log.warning("partie %s : coup %d (%s) illégal chez nous", ref, i + 1, m.get("notation"))
            raise GameError(422, ILLEGAL) from exc
        game.moves.append(_record(game, move, before))
        game.states.append(apply_move(before, move))

    if not game.state.over:
        winner = data.get("winner") if data.get("winner") in (1, 2) else None
        reason = REASONS.get(str(data.get("result_reason") or data.get("win_reason") or ""))
        if reason is None:
            reason = "agreement" if winner is None else "resign"
        game.states[-1] = end_game(game.state, winner, reason)
    if not game.moves:
        raise GameError(409, "Seule une partie terminée peut être analysée.")
    game.imported = {
        "site": SITE,
        "url": f"https://www.{SITE}/game/{ref}",
        "names": [str(data.get(f"player{i}_username") or "?")[:32] for i in (1, 2)],
        "ratings": [data.get(f"player{i}_rating") for i in (1, 2)],
        "timeControl": data.get("time_control"),
    }
    game.ended_at = time.time()
    return game


async def import_game(link: str, me: Player) -> Game:
    """La partie importée (déjà importée : la même, avec son bilan éventuel)."""
    ref = parse_ref(link)
    existing = await _by_ref(ref)
    if existing:
        return existing
    game = convert(await fetch(ref), ref, me.id)
    try:
        await store.insert_finished(game)
    except Exception:
        existing = await _by_ref(ref)  # importée au même moment par quelqu'un d'autre
        if existing:
            return existing
        raise
    return game


async def _by_ref(ref: str) -> Game | None:
    async with store.engine.connect() as conn:
        gid = (await conn.execute(select(db.games.c.id).where(db.games.c.import_ref == ref))).scalar()
    return await store.get_game(gid) if gid else None
