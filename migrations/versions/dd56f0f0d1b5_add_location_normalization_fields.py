"""Add location normalization fields

Revision ID: dd56f0f0d1b5
Revises: cc34f0f0d1b4
Create Date: 2026-03-11 19:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "dd56f0f0d1b5"
down_revision: Union[str, Sequence[str], None] = "cc34f0f0d1b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("prospects", sa.Column("raw_location_text", sa.String(), nullable=True))
    op.add_column("prospects", sa.Column("parsed_location", sa.JSON(), nullable=True))
    op.add_column("prospects", sa.Column("city", sa.String(), nullable=True))
    op.add_column("prospects", sa.Column("region", sa.String(), nullable=True))
    op.add_column("prospects", sa.Column("country", sa.String(), nullable=True))
    op.add_column("prospects", sa.Column("postal_code", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("prospects", "postal_code")
    op.drop_column("prospects", "country")
    op.drop_column("prospects", "region")
    op.drop_column("prospects", "city")
    op.drop_column("prospects", "parsed_location")
    op.drop_column("prospects", "raw_location_text")
