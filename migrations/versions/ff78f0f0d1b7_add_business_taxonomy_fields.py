"""Add business taxonomy fields

Revision ID: ff78f0f0d1b7
Revises: ee67f0f0d1b6
Create Date: 2026-03-11 20:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ff78f0f0d1b7"
down_revision: Union[str, Sequence[str], None] = "ee67f0f0d1b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("prospects", sa.Column("taxonomy_top_level", sa.String(), nullable=True))
    op.add_column("prospects", sa.Column("taxonomy_business_type", sa.String(), nullable=True))

    op.add_column("job_prospects", sa.Column("taxonomy_top_level", sa.String(), nullable=True))
    op.add_column("job_prospects", sa.Column("taxonomy_business_type", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("job_prospects", "taxonomy_business_type")
    op.drop_column("job_prospects", "taxonomy_top_level")

    op.drop_column("prospects", "taxonomy_business_type")
    op.drop_column("prospects", "taxonomy_top_level")
