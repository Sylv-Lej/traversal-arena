"""Puzzles : puzzles, tentatives, Puzzle Rush.

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "puzzles",
        sa.Column("id", sa.String(length=16), nullable=False),
        sa.Column("terrain", sa.String(length=16), nullable=False),
        sa.Column("start", sa.JSON(), nullable=False),
        sa.Column("solution", sa.JSON(), nullable=False),
        sa.Column("themes", sa.JSON(), nullable=False),
        sa.Column("side", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Float(), nullable=False),
        sa.Column("rd", sa.Float(), nullable=False),
        sa.Column("vol", sa.Float(), nullable=False),
        sa.Column("plays", sa.Integer(), nullable=False),
        sa.Column("solves", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_puzzles_rating", "puzzles", ["rating"])
    op.create_table(
        "puzzle_rushes",
        sa.Column("id", sa.String(length=16), nullable=False),
        sa.Column("player_id", sa.String(length=16), nullable=False),
        sa.Column("mode", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("strikes", sa.Integer(), nullable=False),
        sa.Column("attempt_id", sa.String(length=16), nullable=True),
        sa.Column("started_at", sa.Float(), nullable=False),
        sa.Column("deadline_at", sa.Float(), nullable=True),
        sa.Column("ended_at", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rushes_board", "puzzle_rushes", ["mode", "score"])
    op.create_index("ix_rushes_player", "puzzle_rushes", ["player_id", "started_at"])
    op.create_table(
        "puzzle_attempts",
        sa.Column("id", sa.String(length=16), nullable=False),
        sa.Column("player_id", sa.String(length=16), nullable=False),
        sa.Column("puzzle_id", sa.String(length=16), nullable=False),
        sa.Column("mode", sa.String(length=8), nullable=False),
        sa.Column("rush_id", sa.String(length=16), nullable=True),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("rated", sa.Boolean(), nullable=False),
        sa.Column("hinted", sa.Boolean(), nullable=False),
        sa.Column("revealed", sa.Boolean(), nullable=False),
        sa.Column("wrong", sa.JSON(), nullable=True),
        sa.Column("rating_before", sa.Float(), nullable=True),
        sa.Column("rating_after", sa.Float(), nullable=True),
        sa.Column("daily", sa.String(length=10), nullable=True),
        sa.Column("started_at", sa.Float(), nullable=False),
        sa.Column("ended_at", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["puzzle_id"], ["puzzles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rush_id"], ["puzzle_rushes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_attempts_player", "puzzle_attempts", ["player_id", "started_at"])
    op.create_index("ix_attempts_player_puzzle", "puzzle_attempts", ["player_id", "puzzle_id"])


def downgrade() -> None:
    op.drop_table("puzzle_attempts")
    op.drop_table("puzzle_rushes")
    op.drop_table("puzzles")
