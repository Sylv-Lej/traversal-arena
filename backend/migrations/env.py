"""Environnement Alembic.

Deux usages :
- au démarrage du backend : app/persist.py passe une connexion (déjà ouverte sur le
  moteur async) via `config.attributes["connection"]` ;
- en ligne de commande (autogenerate) : on se connecte à DATABASE_URL.
"""

import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.db import metadata
from revkit.settings import get_settings

config = context.config
target_metadata = metadata


def run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_cli() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.sqlalchemy_url, connect_args=settings.db_connect_args)
    async with engine.connect() as conn:
        await conn.run_sync(run)
    await engine.dispose()


connection = config.attributes.get("connection")
if connection is not None:
    run(connection)
else:
    asyncio.run(run_cli())
