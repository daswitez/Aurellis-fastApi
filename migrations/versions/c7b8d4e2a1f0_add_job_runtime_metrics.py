"""Add job runtime metrics

Revision ID: c7b8d4e2a1f0
Revises: 6f41c9b2d7aa
Create Date: 2026-03-10 12:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c7b8d4e2a1f0"
down_revision: Union[str, Sequence[str], None] = "6f41c9b2d7aa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("scraping_jobs", sa.Column("total_processed", sa.Integer(), nullable=True, server_default="0"))
    op.add_column("scraping_jobs", sa.Column("total_failed", sa.Integer(), nullable=True, server_default="0"))
    op.add_column("scraping_jobs", sa.Column("total_skipped", sa.Integer(), nullable=True, server_default="0"))

    op.execute(
        """
        UPDATE scraping_jobs
        SET total_processed = COALESCE(total_saved, 0),
            total_failed = 0,
            total_skipped = GREATEST(COALESCE(total_found, 0) - COALESCE(total_saved, 0), 0)
        """
    )

    op.alter_column("scraping_jobs", "total_processed", server_default=None)
    op.alter_column("scraping_jobs", "total_failed", server_default=None)
    op.alter_column("scraping_jobs", "total_skipped", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("scraping_jobs", "total_skipped")
    op.drop_column("scraping_jobs", "total_failed")
    op.drop_column("scraping_jobs", "total_processed")
