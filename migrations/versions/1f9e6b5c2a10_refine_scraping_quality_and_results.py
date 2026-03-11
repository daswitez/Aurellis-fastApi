"""Refine scraping quality and result fields

Revision ID: 1f9e6b5c2a10
Revises: c7b8d4e2a1f0
Create Date: 2026-03-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1f9e6b5c2a10"
down_revision: Union[str, Sequence[str], None] = "c7b8d4e2a1f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("prospects", sa.Column("validated_location", sa.String(), nullable=True))
    op.add_column("prospects", sa.Column("location_match_status", sa.String(), nullable=True))
    op.add_column("prospects", sa.Column("location_confidence", sa.String(), nullable=True))
    op.add_column("prospects", sa.Column("detected_language", sa.String(), nullable=True))
    op.add_column("prospects", sa.Column("language_match_status", sa.String(), nullable=True))
    op.add_column("prospects", sa.Column("primary_cta", sa.String(), nullable=True))
    op.add_column("prospects", sa.Column("booking_url", sa.String(), nullable=True))
    op.add_column("prospects", sa.Column("pricing_page_url", sa.String(), nullable=True))
    op.add_column("prospects", sa.Column("whatsapp_url", sa.String(), nullable=True))
    op.add_column("prospects", sa.Column("contact_channels_json", sa.JSON(), nullable=True))
    op.add_column("prospects", sa.Column("contact_quality_score", sa.Float(), nullable=True))
    op.add_column("prospects", sa.Column("company_size_signal", sa.String(), nullable=True))
    op.add_column("prospects", sa.Column("service_keywords", sa.JSON(), nullable=True))

    op.add_column("job_prospects", sa.Column("quality_status", sa.String(), nullable=True))
    op.add_column("job_prospects", sa.Column("quality_flags_json", sa.JSON(), nullable=True))
    op.add_column("job_prospects", sa.Column("rejection_reason", sa.String(), nullable=True))
    op.add_column("job_prospects", sa.Column("discovery_confidence", sa.String(), nullable=True))

    op.execute("UPDATE job_prospects SET quality_status = 'accepted' WHERE quality_status IS NULL")


def downgrade() -> None:
    op.drop_column("job_prospects", "discovery_confidence")
    op.drop_column("job_prospects", "rejection_reason")
    op.drop_column("job_prospects", "quality_flags_json")
    op.drop_column("job_prospects", "quality_status")

    op.drop_column("prospects", "service_keywords")
    op.drop_column("prospects", "company_size_signal")
    op.drop_column("prospects", "contact_quality_score")
    op.drop_column("prospects", "contact_channels_json")
    op.drop_column("prospects", "whatsapp_url")
    op.drop_column("prospects", "pricing_page_url")
    op.drop_column("prospects", "booking_url")
    op.drop_column("prospects", "primary_cta")
    op.drop_column("prospects", "language_match_status")
    op.drop_column("prospects", "detected_language")
    op.drop_column("prospects", "location_confidence")
    op.drop_column("prospects", "location_match_status")
    op.drop_column("prospects", "validated_location")
