"""Limitation de débit en mémoire, sans dépendance externe.

Adaptée à l'infra visée (Serverless Container, `max_scale = 1`) : un seul process
sert les requêtes, un compteur en mémoire suffit donc à plafonner l'abus.

LIMITES ASSUMÉES
----------------
- Le compteur est **perdu à chaque réveil** du container (scale-to-zero). Un
  attaquant patient peut donc dépasser le quota en espaçant ses rafales.
- Il n'est **pas partagé** entre instances : passer `max_scale > 1` multiplie le
  quota effectif par le nombre d'instances.

C'est suffisant contre l'abus courant et l'amplification de coût. Pour un quota
strict, il faut un store partagé (Redis, ou une table Postgres).
"""

import time
from collections import deque

from fastapi import HTTPException, Request


class RateLimiter:
    """Fenêtre glissante : au plus `limit` évènements par `window_seconds` et par clé."""

    def __init__(self, limit: int, window_seconds: float, max_keys: int = 10_000):
        self.limit = limit
        self.window = window_seconds
        self.max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        self._prune(now)

        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] > self.window:
            hits.popleft()

        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True

    def _prune(self, now: float) -> None:
        """Borne la mémoire : sans ça, le dict de compteurs serait lui-même un DoS."""
        if len(self._hits) <= self.max_keys:
            return
        for key in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window]:
            del self._hits[key]
        if len(self._hits) > self.max_keys:
            # Dernier recours : repartir à vide plutôt que de grossir sans fin.
            self._hits.clear()


CLIENT_IP_HEADER = "x-client-ip"


def client_key(request: Request) -> str:
    """Identifie l'appelant par son IP.

    1. `X-Client-IP` : l'IP du vrai visiteur, relayée par la route serveur du front.
       Sans elle, tous les visiteurs partageraient le compteur du front (qui est le
       seul appelant direct de l'API) et le quota deviendrait global. Cet en-tête
       n'est digne de confiance QUE parce que la route qui l'utilise exige aussi la
       clé d'API : un appelant non authentifié est rejeté avant d'arriver ici.
    2. Sinon `X-Forwarded-For`, dont on prend la **dernière** entrée : c'est celle
       ajoutée par le proxy de la plateforme, la seule que l'appelant ne peut pas
       falsifier. Prendre la première (l'usage naïf) laisserait n'importe qui
       contourner le quota en forgeant l'en-tête.
    3. Sinon l'IP de la connexion.
    """
    relayed = request.headers.get(CLIENT_IP_HEADER)
    if relayed:
        return relayed.strip()
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(limiter: RateLimiter):
    """Dépendance FastAPI : refuse en 429 au-delà du quota."""

    async def dependency(request: Request) -> None:
        if not limiter.allow(client_key(request)):
            raise HTTPException(429, "Trop de requêtes. Réessaie dans un instant.")

    return dependency
