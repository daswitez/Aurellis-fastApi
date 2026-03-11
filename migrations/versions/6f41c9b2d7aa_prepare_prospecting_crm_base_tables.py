"""Prepare prospecting CRM base tables

Revision ID: 6f41c9b2d7aa
Revises: 98b488db594e
Create Date: 2026-03-10 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6f41c9b2d7aa"
down_revision: Union[str, Sequence[str], None] = "98b488db594e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "job_prospects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("prospect_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=True),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("source_type", sa.String(), nullable=True),
        sa.Column("discovery_method", sa.String(), nullable=True),
        sa.Column("search_query_snapshot", sa.Text(), nullable=True),
        sa.Column("rank_position", sa.Integer(), nullable=True),
        sa.Column("processing_status", sa.String(), nullable=True),
        sa.Column("match_score", sa.Float(), nullable=True),
        sa.Column("confidence_level", sa.String(), nullable=True),
        sa.Column("fit_summary", sa.Text(), nullable=True),
        sa.Column("pain_points_json", sa.JSON(), nullable=True),
        sa.Column("outreach_angles_json", sa.JSON(), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=True),
        sa.Column("raw_extraction_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["scraping_jobs.id"]),
        sa.ForeignKeyConstraint(["prospect_id"], ["prospects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "prospect_id", name="uq_job_prospects_job_prospect"),
    )
    op.create_index(op.f("ix_job_prospects_id"), "job_prospects", ["id"], unique=False)
    op.create_index(op.f("ix_job_prospects_workspace_id"), "job_prospects", ["workspace_id"], unique=False)

    op.create_table(
        "prospect_contacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("prospect_id", sa.Integer(), nullable=False),
        sa.Column("contact_type", sa.String(), nullable=False),
        sa.Column("contact_value", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=True),
        sa.Column("contact_person_name", sa.String(), nullable=True),
        sa.Column("contact_person_role", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["prospect_id"], ["prospects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prospect_id", "contact_type", "contact_value", name="uq_prospect_contacts_value"),
    )
    op.create_index(op.f("ix_prospect_contacts_id"), "prospect_contacts", ["id"], unique=False)

    op.create_table(
        "prospect_pages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("prospect_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("page_type", sa.String(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("meta_description", sa.Text(), nullable=True),
        sa.Column("detected_language", sa.String(), nullable=True),
        sa.Column("text_hash", sa.String(), nullable=True),
        sa.Column("content_signals_json", sa.JSON(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("last_scraped_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["prospect_id"], ["prospects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prospect_id", "url", name="uq_prospect_pages_url"),
    )
    op.create_index(op.f("ix_prospect_pages_id"), "prospect_pages", ["id"], unique=False)

    # Backfill contextual prospect results from the legacy single job_id stored in prospects.
    op.execute(
        """
        INSERT INTO job_prospects (
            job_id,
            prospect_id,
            workspace_id,
            source_url,
            source_type,
            discovery_method,
            processing_status,
            match_score,
            confidence_level,
            raw_extraction_json,
            created_at,
            updated_at
        )
        SELECT
            p.job_id,
            p.id,
            p.workspace_id,
            p.source_url,
            p.source,
            'legacy_prospect_backfill',
            'processed',
            COALESCE(p.score, 0.0),
            p.confidence_level,
            '{"migrated_from_legacy_prospect": true}'::json,
            COALESCE(p.created_at, CURRENT_TIMESTAMP),
            COALESCE(p.updated_at, CURRENT_TIMESTAMP)
        FROM prospects p
        WHERE p.job_id IS NOT NULL
        ON CONFLICT ON CONSTRAINT uq_job_prospects_job_prospect DO NOTHING
        """
    )

    # Backfill the contact channels that already exist as columns in prospects.
    op.execute(
        """
        INSERT INTO prospect_contacts (
            prospect_id,
            contact_type,
            contact_value,
            label,
            is_primary,
            is_public,
            confidence,
            source_url,
            created_at,
            updated_at
        )
        SELECT
            p.id,
            'email',
            p.email,
            'primary_email',
            TRUE,
            TRUE,
            1.0,
            p.source_url,
            COALESCE(p.created_at, CURRENT_TIMESTAMP),
            COALESCE(p.updated_at, CURRENT_TIMESTAMP)
        FROM prospects p
        WHERE p.email IS NOT NULL
        ON CONFLICT ON CONSTRAINT uq_prospect_contacts_value DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO prospect_contacts (
            prospect_id,
            contact_type,
            contact_value,
            label,
            is_primary,
            is_public,
            confidence,
            source_url,
            created_at,
            updated_at
        )
        SELECT
            p.id,
            'phone',
            p.phone,
            'primary_phone',
            TRUE,
            TRUE,
            1.0,
            p.source_url,
            COALESCE(p.created_at, CURRENT_TIMESTAMP),
            COALESCE(p.updated_at, CURRENT_TIMESTAMP)
        FROM prospects p
        WHERE p.phone IS NOT NULL
        ON CONFLICT ON CONSTRAINT uq_prospect_contacts_value DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO prospect_contacts (
            prospect_id,
            contact_type,
            contact_value,
            label,
            is_primary,
            is_public,
            confidence,
            source_url,
            created_at,
            updated_at
        )
        SELECT
            p.id,
            'linkedin',
            p.linkedin_url,
            'linkedin_profile',
            FALSE,
            TRUE,
            1.0,
            p.source_url,
            COALESCE(p.created_at, CURRENT_TIMESTAMP),
            COALESCE(p.updated_at, CURRENT_TIMESTAMP)
        FROM prospects p
        WHERE p.linkedin_url IS NOT NULL
        ON CONFLICT ON CONSTRAINT uq_prospect_contacts_value DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO prospect_contacts (
            prospect_id,
            contact_type,
            contact_value,
            label,
            is_primary,
            is_public,
            confidence,
            source_url,
            created_at,
            updated_at
        )
        SELECT
            p.id,
            'instagram',
            p.instagram_url,
            'instagram_profile',
            FALSE,
            TRUE,
            1.0,
            p.source_url,
            COALESCE(p.created_at, CURRENT_TIMESTAMP),
            COALESCE(p.updated_at, CURRENT_TIMESTAMP)
        FROM prospects p
        WHERE p.instagram_url IS NOT NULL
        ON CONFLICT ON CONSTRAINT uq_prospect_contacts_value DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO prospect_contacts (
            prospect_id,
            contact_type,
            contact_value,
            label,
            is_primary,
            is_public,
            confidence,
            source_url,
            created_at,
            updated_at
        )
        SELECT
            p.id,
            'facebook',
            p.facebook_url,
            'facebook_profile',
            FALSE,
            TRUE,
            1.0,
            p.source_url,
            COALESCE(p.created_at, CURRENT_TIMESTAMP),
            COALESCE(p.updated_at, CURRENT_TIMESTAMP)
        FROM prospects p
        WHERE p.facebook_url IS NOT NULL
        ON CONFLICT ON CONSTRAINT uq_prospect_contacts_value DO NOTHING
        """
    )

    # Backfill at least one canonical page per prospect so future crawls have a starting point.
    op.execute(
        """
        INSERT INTO prospect_pages (
            prospect_id,
            url,
            page_type,
            last_seen_at,
            last_scraped_at,
            created_at,
            updated_at
        )
        SELECT
            p.id,
            p.website_url,
            'home',
            COALESCE(p.updated_at, CURRENT_TIMESTAMP),
            COALESCE(p.updated_at, CURRENT_TIMESTAMP),
            COALESCE(p.created_at, CURRENT_TIMESTAMP),
            COALESCE(p.updated_at, CURRENT_TIMESTAMP)
        FROM prospects p
        WHERE p.website_url IS NOT NULL
        ON CONFLICT ON CONSTRAINT uq_prospect_pages_url DO NOTHING
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_prospect_pages_id"), table_name="prospect_pages")
    op.drop_table("prospect_pages")

    op.drop_index(op.f("ix_prospect_contacts_id"), table_name="prospect_contacts")
    op.drop_table("prospect_contacts")

    op.drop_index(op.f("ix_job_prospects_workspace_id"), table_name="job_prospects")
    op.drop_index(op.f("ix_job_prospects_id"), table_name="job_prospects")
    op.drop_table("job_prospects")
