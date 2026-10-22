"""Sécurité : limites de débit partagées entre instances (dont échecs de connexion par
adresse email).

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rate_hits",
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("window_start", sa.Float(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("key", "window_start"),
    )
    op.create_index("ix_rate_hits_window", "rate_hits", ["window_start"])


def downgrade() -> None:
    op.drop_index("ix_rate_hits_window", table_name="rate_hits")
    op.drop_table("rate_hits")
