"""Types de partie Bullet / Classique / Tactique, matchs tactiques (Bo2 + bans).

Les classements repartent de zéro (bullet / classic / tactic remplacent bullet / blitz /
rapid) ; les recherches de partie en cours sont oubliées.

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "matches",
        sa.Column("id", sa.String(length=16), nullable=False),
        sa.Column("mode", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("p1_id", sa.String(length=16), nullable=True),
        sa.Column("p2_id", sa.String(length=16), nullable=True),
        sa.Column("created_by", sa.String(length=16), nullable=False),
        sa.Column("bot_level", sa.Integer(), nullable=True),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("rounds", sa.JSON(), nullable=False),
        sa.Column("score", sa.JSON(), nullable=False),
        sa.Column("winner", sa.Integer(), nullable=True),
        sa.Column("rated", sa.Boolean(), nullable=False),
        sa.Column("rating_before", sa.JSON(), nullable=True),
        sa.Column("rating_after", sa.JSON(), nullable=True),
        sa.Column("rank_change", sa.JSON(), nullable=True),
        sa.Column("deadline_at", sa.Float(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("ended_at", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["players.id"]),
        sa.ForeignKeyConstraint(["p1_id"], ["players.id"]),
        sa.ForeignKeyConstraint(["p2_id"], ["players.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_matches_p1", "matches", ["p1_id", "created_at"])
    op.create_index("ix_matches_p2", "matches", ["p2_id", "created_at"])
    op.create_index("ix_matches_deadline", "matches", ["deadline_at"])
    op.add_column("games", sa.Column("match_id", sa.String(length=16), nullable=True))
    op.add_column("games", sa.Column("round", sa.Integer(), nullable=True))
    op.create_foreign_key("games_match_id_fkey", "games", "matches", ["match_id"], ["id"], ondelete="CASCADE")
    # Nouveaux classements : on repart de zéro.
    op.execute("DELETE FROM ratings")
    op.execute("DELETE FROM seeks")


def downgrade() -> None:
    op.drop_constraint("games_match_id_fkey", "games", type_="foreignkey")
    op.drop_column("games", "round")
    op.drop_column("games", "match_id")
    op.drop_index("ix_matches_deadline", table_name="matches")
    op.drop_index("ix_matches_p2", table_name="matches")
    op.drop_index("ix_matches_p1", table_name="matches")
    op.drop_table("matches")
