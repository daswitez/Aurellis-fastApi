"""Add entity classification fields

Revision ID: aa12f0f0d1b2
Revises: 1f9e6b5c2a10
Create Date: 2026-03-11 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "aa12f0f0d1b2"
down_revision: Union[str, Sequence[str], None] = "1f9e6b5c2a10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("prospects", sa.Column("entity_type_detected", sa.String(), nullable=True))
    op.add_column("prospects", sa.Column("entity_type_confidence", sa.String(), nullable=True))
    op.add_column("prospects", sa.Column("entity_type_evidence", sa.JSON(), nullable=True))
    op.add_column("prospects", sa.Column("is_target_entity", sa.Boolean(), nullable=True))

    op.add_column("job_prospects", sa.Column("entity_type_detected", sa.String(), nullable=True))
    op.add_column("job_prospects", sa.Column("entity_type_confidence", sa.String(), nullable=True))
    op.add_column("job_prospects", sa.Column("entity_type_evidence", sa.JSON(), nullable=True))
    op.add_column("job_prospects", sa.Column("is_target_entity", sa.Boolean(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("job_prospects", "is_target_entity")
    op.drop_column("job_prospects", "entity_type_evidence")
    op.drop_column("job_prospects", "entity_type_confidence")
    op.drop_column("job_prospects", "entity_type_detected")

    op.drop_column("prospects", "is_target_entity")
    op.drop_column("prospects", "entity_type_evidence")
    op.drop_column("prospects", "entity_type_confidence")
    op.drop_column("prospects", "entity_type_detected")
