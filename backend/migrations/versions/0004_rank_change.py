"""Rang avant/après figé en fin de partie classée (promotions, relégations, placement).

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("games", sa.Column("rank_change", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("games", "rank_change")
