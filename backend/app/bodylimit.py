"""Taille maximale d'une requête, vérifiée AVANT de lire le corps en entier.

Sans elle, FastAPI lit tout le corps en mémoire avant de valider quoi que ce soit (même
la clé d'API) : un envoi de plusieurs Go suffirait à faire tomber une instance. Le plus
gros corps légitime est un bot de l'arène (1 Mo, ~1,4 Mo en base64).
"""

from fastapi import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.i18n import lang_of, translate

MAX_BODY_BYTES = 2 * 1024 * 1024
TOO_LARGE = "Requête trop volumineuse."


class BodyLimit:
    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        declared = headers.get(b"content-length", b"")
        if declared.isdigit() and int(declared) > self.max_bytes:
            detail = translate(TOO_LARGE, lang_of(headers.get(b"x-lang", b"").decode("latin-1")))
            await JSONResponse({"detail": detail}, status_code=413)(scope, receive, send)
            return
        seen = 0

        async def limited() -> dict:
            # Corps envoyé par morceaux sans longueur annoncée : compté au fil de l'eau.
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max_bytes:
                    raise HTTPException(413, TOO_LARGE)
            return message

        await self.app(scope, limited, send)
