"""Add social-first identity fields

Revision ID: 0a91c5d4e8f2
Revises: ff78f0f0d1b7
Create Date: 2026-03-14 14:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0a91c5d4e8f2"
down_revision: Union[str, Sequence[str], None] = "ff78f0f0d1b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("prospects", sa.Column("canonical_identity", sa.String(), nullable=True))
    op.add_column("prospects", sa.Column("primary_identity_type", sa.String(), nullable=True))
    op.add_column("prospects", sa.Column("primary_identity_url", sa.String(), nullable=True))
    op.add_column("prospects", sa.Column("tiktok_url", sa.String(), nullable=True))
    op.add_column("prospects", sa.Column("social_profiles", sa.JSON(), nullable=True))

    op.execute("UPDATE prospects SET canonical_identity = domain WHERE canonical_identity IS NULL")
    op.alter_column("prospects", "canonical_identity", existing_type=sa.String(), nullable=False)
    op.alter_column("prospects", "domain", existing_type=sa.String(), nullable=True)
    op.create_unique_constraint("uq_prospects_canonical_identity", "prospects", ["canonical_identity"])


def downgrade() -> None:
    op.drop_constraint("uq_prospects_canonical_identity", "prospects", type_="unique")
    op.alter_column("prospects", "domain", existing_type=sa.String(), nullable=False)
    op.drop_column("prospects", "social_profiles")
    op.drop_column("prospects", "tiktok_url")
    op.drop_column("prospects", "primary_identity_url")
    op.drop_column("prospects", "primary_identity_type")
    op.drop_column("prospects", "canonical_identity")
