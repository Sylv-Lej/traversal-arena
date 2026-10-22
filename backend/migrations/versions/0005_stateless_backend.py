"""Backend sans état : échéances en base, files bot/analyse et matchmaking partagés.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("games", sa.Column("deadline_at", sa.Float(), nullable=True))
    op.create_index("ix_games_deadline", "games", ["deadline_at"])
    op.create_table(
        "bot_jobs",
        sa.Column("game_id", sa.String(length=16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("run_after", sa.Float(), nullable=False),
        sa.Column("claimed_at", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("game_id"),
    )
    op.create_index("ix_bot_jobs_run_after", "bot_jobs", ["run_after"])
    op.create_table(
        "analysis_jobs",
        sa.Column("game_id", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("done", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("claimed_at", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("game_id"),
    )
    op.create_table(
        "seeks",
        sa.Column("player_id", sa.String(length=16), nullable=False),
        sa.Column("time_control", sa.String(length=8), nullable=False),
        sa.Column("terrain", sa.String(length=16), nullable=False),
        sa.Column("rating", sa.Float(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("polled_at", sa.Float(), nullable=False),
        sa.Column("game_id", sa.String(length=16), nullable=True),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("player_id"),
    )
    op.create_index("ix_seeks_tc", "seeks", ["time_control", "created_at"])

    # Parties en cours : pendules et bots étaient des tâches en mémoire. On repart d'un
    # tour neuf (comme l'ancien redémarrage) et on écrit échéances et tâches de bot.
    # Camp au trait : 1 si `ply` est pair (le joueur 1 commence, on alterne).
    now = "extract(epoch from now())"
    side = "(CASE WHEN ply % 2 = 0 THEN 0 ELSE 1 END)"
    op.execute(f"""
        UPDATE games SET turn_started_at = {now},
          deadline_at = CASE
            WHEN initial_ms IS NOT NULL AND ply >= 2
              THEN {now} + (remaining->>{side})::float / 1000
            WHEN mode = 'online' AND ply < 2 THEN {now} + 45
          END
        WHERE status = 'active'""")
    op.execute(f"""
        INSERT INTO bot_jobs (game_id, version, run_after, claimed_at)
        SELECT id, version, {now}, NULL FROM games
        WHERE status = 'active' AND mode = 'bot'
          AND ((ply % 2 = 0 AND p1_id LIKE 'bot%') OR (ply % 2 = 1 AND p2_id LIKE 'bot%'))""")


def downgrade() -> None:
    op.drop_index("ix_seeks_tc", table_name="seeks")
    op.drop_table("seeks")
    op.drop_table("analysis_jobs")
    op.drop_index("ix_bot_jobs_run_after", table_name="bot_jobs")
    op.drop_table("bot_jobs")
    op.drop_index("ix_games_deadline", table_name="games")
    op.drop_column("games", "deadline_at")
