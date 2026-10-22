"""Arène des bots : modules WebAssembly envoyés par les joueurs, file de parties, classement.

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_games_mode_ended", "games", ["mode", "ended_at"])
    op.create_table(
        "arena_bots",
        sa.Column("id", sa.String(length=16), nullable=False),
        sa.Column("owner_id", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("error", sa.String(length=300), nullable=True),
        sa.Column("wasm", sa.LargeBinary(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("activated_at", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["id"], ["players.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_arena_bots_owner", "arena_bots", ["owner_id", "name", "version"], unique=True)
    op.create_index("ix_arena_bots_status", "arena_bots", ["status"])
    op.create_index("ix_arena_bots_sha", "arena_bots", ["sha256"])
    op.create_table(
        "arena_jobs",
        sa.Column("id", sa.String(length=16), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("red_id", sa.String(length=16), nullable=False),
        sa.Column("blue_id", sa.String(length=16), nullable=False),
        sa.Column("terrain", sa.String(length=16), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("heights", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("claimed_at", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["red_id"], ["players.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["blue_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_arena_jobs_queue", "arena_jobs", ["status", "created_at"])
    op.create_table(
        "arena_ratings",
        sa.Column("player_id", sa.String(length=16), nullable=False),
        sa.Column("rating", sa.Float(), nullable=False),
        sa.Column("margin", sa.Float(), nullable=False),
        sa.Column("games", sa.Integer(), nullable=False),
        sa.Column("wins", sa.Integer(), nullable=False),
        sa.Column("losses", sa.Integer(), nullable=False),
        sa.Column("draws", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("player_id"),
    )


def downgrade() -> None:
    op.drop_table("arena_ratings")
    op.drop_index("ix_arena_jobs_queue", table_name="arena_jobs")
    op.drop_table("arena_jobs")
    op.drop_index("ix_arena_bots_sha", table_name="arena_bots")
    op.drop_index("ix_arena_bots_status", table_name="arena_bots")
    op.drop_index("ix_arena_bots_owner", table_name="arena_bots")
    op.drop_table("arena_bots")
    op.drop_index("ix_games_mode_ended", table_name="games")
