"""Expiration des sessions, réinitialisation du mot de passe, index de nettoyage.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("last_used", sa.Float(), nullable=True))
    op.execute("UPDATE sessions SET last_used = created_at WHERE last_used IS NULL")
    op.create_index("ix_sessions_last_used", "sessions", ["last_used"])
    op.create_index("ix_players_last_seen", "players", ["last_seen"])
    op.create_table(
        "password_resets",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("player_id", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_hash"),
    )


def downgrade() -> None:
    op.drop_table("password_resets")
    op.drop_index("ix_players_last_seen", table_name="players")
    op.drop_index("ix_sessions_last_used", table_name="sessions")
    op.drop_column("sessions", "last_used")
