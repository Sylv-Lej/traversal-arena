"""Pays représenté par le joueur (drapeau à côté du pseudo).

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("players", sa.Column("country", sa.String(length=2), nullable=True))


def downgrade() -> None:
    op.drop_column("players", "country")
