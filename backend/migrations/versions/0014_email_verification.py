"""Confirmation d'adresse email (exigée pour inscrire un bot dans l'arène).

Revision ID: 0014
Revises: 0013
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("players", sa.Column("email_verified_at", sa.Float(), nullable=True))
    op.create_table(
        "email_verifications",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("player_id", sa.String(length=16), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_hash"),
    )


def downgrade() -> None:
    op.drop_table("email_verifications")
    op.drop_column("players", "email_verified_at")
