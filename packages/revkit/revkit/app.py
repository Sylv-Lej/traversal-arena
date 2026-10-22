from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from revkit.settings import Settings, get_settings


def create_app(
    settings: Settings | None = None,
    routers: list[APIRouter] | None = None,
    on_startup=None,
    on_shutdown=None,
) -> FastAPI:
    """Build a FastAPI app with the shared cross-cutting concerns wired in:
    CORS, /healthz, and the OpenAPI surface.

    Choix de sécurité par défaut :
    - **/docs, /redoc et /openapi.json désactivés** sauf `EXPOSE_DOCS=1` (dev). Ils
      décrivent toute la surface d'API ; inutile de l'offrir en production.
    - **CORS fermé** par défaut (`frontend_origin` vide). Le navigateur passe par la
      route serveur du front, il n'appelle jamais l'API directement.
    - **Pas de service de fichiers** : les uploads ne sont jamais exposés en HTTP.
      Un montage `/media` existait ici pour le confort en dev — il servait les photos
      sans aucune authentification.
    """
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if on_startup:
            await on_startup()
        yield
        if on_shutdown:
            await on_shutdown()

    docs = settings.expose_docs
    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )

    # Liste vide = aucune origine autorisée. `*` reste possible mais doit être choisi
    # explicitement : ce n'est plus le défaut.
    if settings.frontend_origin:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[settings.frontend_origin],
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
        )

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok", "app": settings.app_name}

    for router in routers or []:
        app.include_router(router)

    return app
