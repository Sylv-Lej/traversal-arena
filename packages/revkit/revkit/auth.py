"""Authentification serveur-à-serveur entre le front et l'API.

POURQUOI UNE ROUTE SERVEUR, ET PAS UNE CLÉ DANS LE NAVIGATEUR
-------------------------------------------------------------
Le front est un site public sans login. Tout secret livré au navigateur (variable
`NEXT_PUBLIC_*`, jeton dans le bundle JS) est lisible par quiconque ouvre les
outils de développement : ce n'est pas une authentification, juste un ralentisseur.

Le seul montage où le secret reste secret est donc : le navigateur parle à une
route **serveur** du front (`/api/score`), et c'est ce serveur — pas le navigateur —
qui détient la clé et appelle l'API. La clé ne quitte jamais l'infra.

Conséquence utile : le navigateur n'appelle plus jamais l'API directement, donc
il n'y a plus de requête cross-origin du tout.
"""

import hmac

from fastapi import Header, HTTPException

from revkit.settings import Settings, get_settings

API_KEY_HEADER = "x-api-key"


def require_api_key(settings: Settings | None = None):
    """Dépendance FastAPI : exige la clé partagée, en comparaison à temps constant.

    Fail-closed : si aucune clé n'est configurée côté serveur, tout est refusé. Une
    clé vide qui laisserait passer serait le pire des deux mondes — l'API paraîtrait
    protégée sans l'être.
    """

    async def dependency(x_api_key: str = Header(default="")) -> None:
        expected = (settings or get_settings()).api_key
        if not expected:
            raise HTTPException(
                503,
                "API non configurée : clé d'authentification absente côté serveur.",
            )
        # compare_digest évite de fuiter la clé par le temps de comparaison.
        if not hmac.compare_digest(x_api_key, expected):
            raise HTTPException(401, "Authentification requise.")

    return dependency
