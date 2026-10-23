"""Round-robin de l'arène : N parties entre chaque paire de bots des joueurs en lice.

Pas de route d'API : seulement `make arena-round-robin [GAMES=20]` (base de dev) ou
`make arena-round-robin-prod`. Les parties passent par la file habituelle (le runner les
joue à ses prochains passages, le backend les rejoue et les vérifie) ; elles échappent
au plafond quotidien de l'échelle, qui ne vaut que pour `arena.schedule()`.

    python -m app.arena_round_robin [parties par duel, 20 par défaut]
"""

import asyncio
import sys

from revkit.settings import get_settings
from sqlalchemy.ext.asyncio import create_async_engine

from app.services import arena
from app.services.store import store


async def main(games: int) -> None:
    settings = get_settings()
    if not settings.database_url:
        sys.exit("DATABASE_URL manquant")
    # Pas de `store.start()` : ni migrations, ni écoute, ni workers — juste la base.
    store.engine = create_async_engine(settings.sqlalchemy_url, connect_args=settings.db_connect_args)
    try:
        bots, jobs = await arena.round_robin(games)
    finally:
        await store.engine.dispose()
    duels = bots * (bots - 1) // 2
    print(f"{bots} bots en lice, {duels} duels × {games} parties : {jobs} parties mises en file"
          f" (≈ {jobs * 5 / 3600:.1f} h de runner à 5 s la partie)")


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 20))
