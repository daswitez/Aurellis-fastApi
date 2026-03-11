"""Add commercial insight fields

Revision ID: ee67f0f0d1b6
Revises: dd56f0f0d1b5
Create Date: 2026-03-11 20:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ee67f0f0d1b6"
down_revision: Union[str, Sequence[str], None] = "dd56f0f0d1b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("prospects", sa.Column("observed_signals", sa.JSON(), nullable=True))
    op.add_column("prospects", sa.Column("inferred_opportunities", sa.JSON(), nullable=True))

    op.add_column("job_prospects", sa.Column("observed_signals", sa.JSON(), nullable=True))
    op.add_column("job_prospects", sa.Column("inferred_opportunities", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("job_prospects", "inferred_opportunities")
    op.drop_column("job_prospects", "observed_signals")

    op.drop_column("prospects", "inferred_opportunities")
    op.drop_column("prospects", "observed_signals")
