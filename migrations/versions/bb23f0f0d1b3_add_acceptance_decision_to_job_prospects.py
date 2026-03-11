"""Add acceptance decision to job prospects

Revision ID: bb23f0f0d1b3
Revises: aa12f0f0d1b2
Create Date: 2026-03-11 17:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "bb23f0f0d1b3"
down_revision: Union[str, Sequence[str], None] = "aa12f0f0d1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("job_prospects", sa.Column("acceptance_decision", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("job_prospects", "acceptance_decision")
