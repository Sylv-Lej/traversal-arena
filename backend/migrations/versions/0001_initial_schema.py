"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-10-20 15:50:25.534975
"""

from alembic import op
import sqlalchemy as sa


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('players',
    sa.Column('id', sa.String(length=16), nullable=False),
    sa.Column('name', sa.String(length=32), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=True),
    sa.Column('password_hash', sa.String(length=255), nullable=True),
    sa.Column('is_bot', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('last_seen', sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('games',
    sa.Column('id', sa.String(length=16), nullable=False),
    sa.Column('mode', sa.String(length=8), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('terrain_mode', sa.String(length=16), nullable=False),
    sa.Column('seed', sa.BigInteger(), nullable=False),
    sa.Column('heights', sa.JSON(), nullable=False),
    sa.Column('move_limit', sa.Integer(), nullable=False),
    sa.Column('p1_id', sa.String(length=16), nullable=True),
    sa.Column('p2_id', sa.String(length=16), nullable=True),
    sa.Column('created_by', sa.String(length=16), nullable=False),
    sa.Column('bot_level', sa.Integer(), nullable=True),
    sa.Column('initial_ms', sa.Integer(), nullable=True),
    sa.Column('increment_ms', sa.Integer(), nullable=False),
    sa.Column('remaining', sa.JSON(), nullable=False),
    sa.Column('turn_started_at', sa.Float(), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('rated', sa.Boolean(), nullable=False),
    sa.Column('time_class', sa.String(length=16), nullable=False),
    sa.Column('draw_offer', sa.Integer(), nullable=True),
    sa.Column('rematch_offer', sa.Integer(), nullable=True),
    sa.Column('rematch_id', sa.String(length=16), nullable=True),
    sa.Column('rating_before', sa.JSON(), nullable=True),
    sa.Column('rating_after', sa.JSON(), nullable=True),
    sa.Column('ply', sa.Integer(), nullable=False),
    sa.Column('score1', sa.Integer(), nullable=False),
    sa.Column('score2', sa.Integer(), nullable=False),
    sa.Column('winner', sa.Integer(), nullable=True),
    sa.Column('reason', sa.String(length=16), nullable=True),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('ended_at', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['players.id'], ),
    sa.ForeignKeyConstraint(['p1_id'], ['players.id'], ),
    sa.ForeignKeyConstraint(['p2_id'], ['players.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_games_creator', 'games', ['created_by', 'created_at'], unique=False)
    op.create_index('ix_games_p1', 'games', ['p1_id', 'created_at'], unique=False)
    op.create_index('ix_games_p2', 'games', ['p2_id', 'created_at'], unique=False)
    op.create_index('ix_games_status', 'games', ['status'], unique=False)
    op.create_table('ratings',
    sa.Column('player_id', sa.String(length=16), nullable=False),
    sa.Column('time_class', sa.String(length=16), nullable=False),
    sa.Column('rating', sa.Float(), nullable=False),
    sa.Column('rd', sa.Float(), nullable=False),
    sa.Column('vol', sa.Float(), nullable=False),
    sa.Column('games', sa.Integer(), nullable=False),
    sa.Column('wins', sa.Integer(), nullable=False),
    sa.Column('losses', sa.Integer(), nullable=False),
    sa.Column('draws', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['player_id'], ['players.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('player_id', 'time_class')
    )
    op.create_index('ix_ratings_board', 'ratings', ['time_class', 'rating'], unique=False)
    op.create_table('sessions',
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('player_id', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['player_id'], ['players.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('token_hash')
    )
    op.create_index('ix_sessions_player', 'sessions', ['player_id'], unique=False)
    op.create_table('moves',
    sa.Column('game_id', sa.String(length=16), nullable=False),
    sa.Column('ply', sa.Integer(), nullable=False),
    sa.Column('side', sa.Integer(), nullable=False),
    sa.Column('piece_id', sa.String(length=8), nullable=False),
    sa.Column('kind', sa.String(length=8), nullable=False),
    sa.Column('special', sa.String(length=8), nullable=True),
    sa.Column('frm', sa.Integer(), nullable=True),
    sa.Column('to', sa.Integer(), nullable=True),
    sa.Column('path', sa.JSON(), nullable=False),
    sa.Column('notation', sa.String(length=24), nullable=False),
    sa.Column('combat', sa.JSON(), nullable=True),
    sa.Column('captured_id', sa.String(length=8), nullable=True),
    sa.Column('remaining_ms', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['game_id'], ['games.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('game_id', 'ply')
    )


def downgrade() -> None:
    op.drop_table('moves')
    op.drop_index('ix_sessions_player', table_name='sessions')
    op.drop_table('sessions')
    op.drop_index('ix_ratings_board', table_name='ratings')
    op.drop_table('ratings')
    op.drop_index('ix_games_status', table_name='games')
    op.drop_index('ix_games_p2', table_name='games')
    op.drop_index('ix_games_p1', table_name='games')
    op.drop_index('ix_games_creator', table_name='games')
    op.drop_table('games')
    op.drop_table('players')
