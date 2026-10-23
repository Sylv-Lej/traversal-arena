"""API de l'arène des bots (`app/services/arena.py`).

- `public` : pour le navigateur, via le relais du front (clé d'API + session), comme le
  reste de l'API.
- `runner` : pour `traversal-arena work` seulement, authentifié par `ARENA_TOKEN` (pas la
  clé d'API : le runner ne peut rien faire d'autre que prendre des parties et en rendre).
"""

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from revkit.auth import require_api_key

from app.routes import current_player
from app.services import arena
from app.services.store import Player

public = APIRouter(prefix="/api/arena", dependencies=[Depends(require_api_key())])


def _http(exc: arena.ArenaError) -> HTTPException:
    return HTTPException(exc.status, exc.detail)


@public.get("/info")
async def info():
    return arena.info()


@public.get("/showcase")
async def showcase():
    """Partie rejouée sur l'accueil (toujours visible, même relecture fermée)."""
    return {"game": await arena.showcase()}


@public.get("/leaderboard")
async def leaderboard():
    return await arena.leaderboard()


@public.get("/mine")
async def mine(me: Player = Depends(current_player)):
    return await arena.mine(me)


class NewBot(BaseModel):
    name: str = Field(default="", max_length=24)
    # Le .wasm en base64 (1 Mo au plus, soit ~1,4 Mo encodé).
    wasm: str = Field(max_length=(arena.MAX_WASM_BYTES * 4) // 3 + 8)
    # Mise à jour : id d'une version du bot à remplacer (le nom vient de là).
    replaces: str | None = Field(default=None, max_length=16)


@public.post("/bots")
async def submit(body: NewBot, me: Player = Depends(current_player)):
    try:
        return await arena.submit(me, body.name, body.wasm, body.replaces)
    except arena.ArenaError as exc:
        raise _http(exc) from exc


@public.get("/bots/{bot_id}")
async def bot_view(bot_id: str):
    try:
        return await arena.bot_view(bot_id)
    except arena.ArenaError as exc:
        raise _http(exc) from exc


@public.post("/bots/{bot_id}/retire")
async def retire(bot_id: str, me: Player = Depends(current_player)):
    try:
        return await arena.retire(me, bot_id)
    except arena.ArenaError as exc:
        raise _http(exc) from exc


# --- Runner ------------------------------------------------------------------------------


async def require_runner(x_arena_token: str = Header(default="")) -> None:
    expected = arena.runner_token()
    if not expected:  # fermé tant que le jeton n'est pas configuré
        raise HTTPException(503, "Arène non configurée.")
    if not hmac.compare_digest(x_arena_token, expected):
        raise HTTPException(401, "Authentification requise.")


runner = APIRouter(prefix="/api/arena/runner", dependencies=[Depends(require_runner)])


@runner.post("/claim")
async def claim():
    return {"job": await arena.claim()}


@runner.get("/wasm/{sha}")
async def wasm(sha: str):
    data = await arena.wasm_of(sha)
    if data is None:
        raise HTTPException(404, "Module introuvable.")
    return Response(data, media_type="application/wasm")


@runner.post("/jobs/{job_id}")
async def report(job_id: str, request: Request):
    try:
        await arena.report(job_id, await request.json())
    except arena.ArenaError as exc:
        raise _http(exc) from exc
    return {"ok": True}
