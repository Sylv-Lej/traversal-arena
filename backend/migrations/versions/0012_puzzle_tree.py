"""Puzzles : arbre des variantes acceptées, et ligne réellement jouée par tentative.

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("puzzles", sa.Column("tree", sa.JSON(), nullable=True))
    op.add_column("puzzle_attempts", sa.Column("line", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("puzzle_attempts", "line")
    op.drop_column("puzzles", "tree")
