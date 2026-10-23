"""Parties importées d'un autre site (traversalgame.com) pour leur bilan : référence
d'origine (unique : une partie n'est importée qu'une fois) et pseudos/classements gardés.

Revision ID: 0016
Revises: 0015
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("games", sa.Column("import_ref", sa.String(length=64), nullable=True))
    op.add_column("games", sa.Column("imported", sa.JSON(), nullable=True))
    op.create_unique_constraint("games_import_ref_key", "games", ["import_ref"])


def downgrade() -> None:
    op.drop_constraint("games_import_ref_key", "games", type_="unique")
    op.drop_column("games", "imported")
    op.drop_column("games", "import_ref")
