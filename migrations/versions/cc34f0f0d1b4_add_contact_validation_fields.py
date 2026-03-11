"""Add contact validation fields

Revision ID: cc34f0f0d1b4
Revises: bb23f0f0d1b3
Create Date: 2026-03-11 18:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "cc34f0f0d1b4"
down_revision: Union[str, Sequence[str], None] = "bb23f0f0d1b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("prospects", sa.Column("contact_consistency_status", sa.String(), nullable=True))
    op.add_column("prospects", sa.Column("primary_email_confidence", sa.String(), nullable=True))
    op.add_column("prospects", sa.Column("primary_phone_confidence", sa.String(), nullable=True))
    op.add_column("prospects", sa.Column("primary_contact_source", sa.String(), nullable=True))

    op.add_column("job_prospects", sa.Column("contact_consistency_status", sa.String(), nullable=True))
    op.add_column("job_prospects", sa.Column("primary_email_confidence", sa.String(), nullable=True))
    op.add_column("job_prospects", sa.Column("primary_phone_confidence", sa.String(), nullable=True))
    op.add_column("job_prospects", sa.Column("primary_contact_source", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("job_prospects", "primary_contact_source")
    op.drop_column("job_prospects", "primary_phone_confidence")
    op.drop_column("job_prospects", "primary_email_confidence")
    op.drop_column("job_prospects", "contact_consistency_status")

    op.drop_column("prospects", "primary_contact_source")
    op.drop_column("prospects", "primary_phone_confidence")
    op.drop_column("prospects", "primary_email_confidence")
    op.drop_column("prospects", "contact_consistency_status")
