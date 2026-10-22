import logging

from fastapi import HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from revkit.app import create_app
from revkit.settings import get_settings

from app import bot
from app.bodylimit import BodyLimit
from app.i18n import lang_of, translate
from app.routes import router
from app.routes_arena import public as arena_public, runner as arena_runner
from app.services import matches, training, workers  # noqa: F401  (matches : crochet de fin de manche)
from app.services.realtime import hub
from app.services.store import store

settings = get_settings()
settings.app_name = "traversal"
log = logging.getLogger("traversal")


async def _startup() -> None:
    # Backend sans état : Postgres (Lampion) est obligatoire, y compris en local et en
    # test. Toutes les instances partagent la base et se parlent par LISTEN/NOTIFY.
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL manquant : Traversal a besoin de Postgres.")
    await store.start(settings)
    if hub.on_event not in store.subscribers:
        store.subscribers.append(hub.on_event)
    await store.ensure_bots(bot.LEVELS)
    await store.refresh_all_legends()
    seeded = await training.seed()  # puzzles livrés avec le site
    if seeded:
        log.warning("%s puzzle(s) chargé(s)", seeded)
    workers.start()
    log.warning("Postgres actif, workers démarrés, bot %s", "Rust" if bot.native.ENABLED else "Python")


async def _shutdown() -> None:
    await workers.stop()
    await store.stop()


app = create_app(settings=settings, routers=[router, arena_public, arena_runner], on_startup=_startup,
                 on_shutdown=_shutdown)
app.add_middleware(BodyLimit)


@app.exception_handler(HTTPException)
async def _localized_errors(request: Request, exc: HTTPException):
    """Messages d'erreur dans la langue du joueur (`x-lang`, posé par le relais du front)."""
    lang = lang_of(request.headers.get("x-lang"))
    if lang != "fr" and isinstance(exc.detail, str):
        exc = HTTPException(exc.status_code, translate(exc.detail, lang), headers=exc.headers)
    return await http_exception_handler(request, exc)
