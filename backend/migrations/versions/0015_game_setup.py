"""Mise en place des pièces enregistrée par partie (la plus rapide au centre désormais) :
les parties déjà jouées gardent l'ancienne pour être rejouées à l'identique.

Revision ID: 0015
Revises: 0014
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("games", sa.Column("setup", sa.String(length=8), nullable=True))
    op.execute("UPDATE games SET setup = 'classic'")


def downgrade() -> None:
    op.drop_column("games", "setup")
