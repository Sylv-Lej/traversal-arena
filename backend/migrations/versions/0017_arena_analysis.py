"""Bilans de partie faits par le runner de l'arène (le n°1 des bots propose, orque note) :
une tâche `analyse` de la file `arena_jobs` désigne la partie analysée.

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("arena_jobs", sa.Column("game_id", sa.String(length=16), nullable=True))
    op.create_foreign_key("arena_jobs_game_id_fkey", "arena_jobs", "games", ["game_id"], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    op.drop_constraint("arena_jobs_game_id_fkey", "arena_jobs", type_="foreignkey")
    op.drop_column("arena_jobs", "game_id")
