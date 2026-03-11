import logging
from datetime import datetime
from typing import Dict, Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models import JobProspect, Prospect, ProspectContact, ProspectPage
from app.services.source_metadata import normalize_discovery_method, normalize_source_type

logger = logging.getLogger(__name__)

def _extract_canonical_prospect_data(prospect_data: Dict[str, Any]) -> Dict[str, Any]:
    prospect_columns = {col.name for col in Prospect.__table__.columns}
    excluded_columns = {"id", "created_at", "job_id"}
    return {
        key: value
        for key, value in prospect_data.items()
        if key in prospect_columns and key not in excluded_columns
    }


def _extract_job_prospect_data(
    prospect: Prospect,
    prospect_data: Dict[str, Any],
    job_context: Dict[str, Any],
) -> Dict[str, Any]:
    now = datetime.utcnow()
    pain_points_detected = []
    generic_attributes = prospect_data.get("generic_attributes")
    if isinstance(generic_attributes, dict):
        raw_pain_points = generic_attributes.get("pain_points_detected", [])
        if isinstance(raw_pain_points, list):
            pain_points_detected = raw_pain_points

    return {
        "job_id": job_context["job_id"],
        "prospect_id": prospect.id,
        "workspace_id": job_context.get("workspace_id") or prospect.workspace_id,
        "source_url": prospect_data.get("source_url"),
        "source_type": normalize_source_type(job_context.get("source_type") or prospect_data.get("source")),
        "discovery_method": normalize_discovery_method(job_context.get("discovery_method")),
        "search_query_snapshot": job_context.get("search_query"),
        "rank_position": prospect_data.get("rank_position"),
        "processing_status": "processed",
        "match_score": prospect_data.get("score", 0.0),
        "confidence_level": prospect_data.get("confidence_level"),
        "pain_points_json": pain_points_detected or None,
        "evidence_json": {
            "source_type": normalize_source_type(job_context.get("source_type") or prospect_data.get("source")),
            "discovery_method": normalize_discovery_method(job_context.get("discovery_method")),
            "search_query": job_context.get("search_query"),
            "emails": [value for value in [prospect_data.get("email")] if value],
            "phones": [value for value in [prospect_data.get("phone")] if value],
            "socials": [
                value
                for value in [
                    prospect_data.get("linkedin_url"),
                    prospect_data.get("instagram_url"),
                    prospect_data.get("facebook_url"),
                ]
                if value
            ],
            "contact_page_url": prospect_data.get("contact_page_url"),
            "form_detected": prospect_data.get("form_detected", False),
        },
        "raw_extraction_json": {
            "inferred_niche": prospect_data.get("inferred_niche"),
            "inferred_tech_stack": prospect_data.get("inferred_tech_stack"),
            "generic_attributes": prospect_data.get("generic_attributes"),
            "estimated_revenue_signal": prospect_data.get("estimated_revenue_signal"),
            "has_active_ads": prospect_data.get("has_active_ads"),
            "hiring_signals": prospect_data.get("hiring_signals"),
            "ai_trace": prospect_data.get("ai_trace"),
        },
        "created_at": now,
        "updated_at": now,
    }


def _build_contact_rows(prospect: Prospect, prospect_data: Dict[str, Any]) -> list[Dict[str, Any]]:
    now = datetime.utcnow()
    contacts = []
    candidates = [
        ("email", prospect_data.get("email"), "primary_email", True),
        ("phone", prospect_data.get("phone"), "primary_phone", True),
        ("linkedin", prospect_data.get("linkedin_url"), "linkedin_profile", False),
        ("instagram", prospect_data.get("instagram_url"), "instagram_profile", False),
        ("facebook", prospect_data.get("facebook_url"), "facebook_profile", False),
    ]
    if prospect_data.get("form_detected"):
        candidates.append(("form", prospect_data.get("contact_page_url") or prospect_data.get("website_url"), "contact_form", False))

    for contact_type, contact_value, label, is_primary in candidates:
        if not contact_value:
            continue
        contacts.append(
            {
                "prospect_id": prospect.id,
                "contact_type": contact_type,
                "contact_value": contact_value,
                "label": label,
                "is_primary": is_primary,
                "is_public": True,
                "confidence": 1.0,
                "source_url": prospect_data.get("source_url"),
                "created_at": now,
                "updated_at": now,
            }
        )

    return contacts


def _build_page_rows(prospect: Prospect, prospect_data: Dict[str, Any]) -> list[Dict[str, Any]]:
    now = datetime.utcnow()
    pages: dict[str, Dict[str, Any]] = {}

    def add_page(url: str | None, page_type: str) -> None:
        if not url:
            return
        pages[url] = {
            "prospect_id": prospect.id,
            "url": url,
            "page_type": page_type,
            "last_seen_at": prospect.updated_at or now,
            "last_scraped_at": prospect.updated_at or now,
            "created_at": now,
            "updated_at": now,
        }

    add_page(prospect_data.get("website_url"), "home")
    add_page(prospect_data.get("contact_page_url"), "contact")

    for crawled_page in prospect_data.get("crawled_pages", []):
        if not isinstance(crawled_page, dict):
            continue
        add_page(crawled_page.get("url"), crawled_page.get("page_type") or "other")

    for link in prospect_data.get("internal_links", []):
        lowered = link.lower()
        page_type = "other"
        if "contact" in lowered or "contacto" in lowered:
            page_type = "contact"
        elif "about" in lowered or "nosotros" in lowered or "equipo" in lowered:
            page_type = "about"
        elif "career" in lowered or "trabajo" in lowered or "empleo" in lowered:
            page_type = "careers"
        pages.setdefault(
            link,
            {
                "prospect_id": prospect.id,
                "url": link,
                "page_type": page_type,
                "last_seen_at": prospect.updated_at or now,
                "last_scraped_at": prospect.updated_at or now,
                "created_at": now,
                "updated_at": now,
            },
        )

    return list(pages.values())


async def _upsert_contacts(db: AsyncSession, contacts: list[Dict[str, Any]]) -> None:
    for contact_data in contacts:
        stmt = insert(ProspectContact).values(**contact_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["prospect_id", "contact_type", "contact_value"],
            set_={
                "label": stmt.excluded.label,
                "is_primary": stmt.excluded.is_primary,
                "is_public": stmt.excluded.is_public,
                "confidence": stmt.excluded.confidence,
                "source_url": stmt.excluded.source_url,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await db.execute(stmt)


async def _upsert_pages(db: AsyncSession, pages: list[Dict[str, Any]]) -> None:
    for page_data in pages:
        stmt = insert(ProspectPage).values(**page_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["prospect_id", "url"],
            set_={
                "page_type": stmt.excluded.page_type,
                "last_seen_at": stmt.excluded.last_seen_at,
                "last_scraped_at": stmt.excluded.last_scraped_at,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await db.execute(stmt)


async def save_scraped_prospect(
    db: AsyncSession,
    prospect_data: Dict[str, Any],
    job_context: Dict[str, Any],
) -> Prospect | None:
    """Persist canonical prospect data and contextual job/contact/page data."""

    domain = prospect_data.get("domain")
    if not domain:
        logger.error(f"No se puede guardar el prospecto sin dominio válido: {prospect_data}")
        return None

    canonical_prospect_data = _extract_canonical_prospect_data(prospect_data)
    stmt = insert(Prospect).values(**canonical_prospect_data)

    update_dict = {
        col.name: getattr(stmt.excluded, col.name)
        for col in Prospect.__table__.columns
        if col.name not in ["id", "domain", "created_at", "job_id"] and col.name in canonical_prospect_data
    }

    if update_dict:
        stmt = stmt.on_conflict_do_update(
            index_elements=["domain"],
            set_=update_dict
        )
    else:
        stmt = stmt.on_conflict_do_nothing(index_elements=["domain"])

    await db.execute(stmt)

    query = select(Prospect).where(Prospect.domain == domain)
    prospect_obj = await db.execute(query)
    prospect = prospect_obj.scalars().first()
    if not prospect:
        return None

    job_prospect_data = _extract_job_prospect_data(prospect, prospect_data, job_context)
    job_stmt = insert(JobProspect).values(**job_prospect_data)
    job_stmt = job_stmt.on_conflict_do_update(
        index_elements=["job_id", "prospect_id"],
        set_={
            "workspace_id": job_stmt.excluded.workspace_id,
            "source_url": job_stmt.excluded.source_url,
            "source_type": job_stmt.excluded.source_type,
            "discovery_method": job_stmt.excluded.discovery_method,
            "search_query_snapshot": job_stmt.excluded.search_query_snapshot,
            "rank_position": job_stmt.excluded.rank_position,
            "processing_status": job_stmt.excluded.processing_status,
            "match_score": job_stmt.excluded.match_score,
            "confidence_level": job_stmt.excluded.confidence_level,
            "pain_points_json": job_stmt.excluded.pain_points_json,
            "evidence_json": job_stmt.excluded.evidence_json,
            "raw_extraction_json": job_stmt.excluded.raw_extraction_json,
            "updated_at": job_stmt.excluded.updated_at,
        },
    )
    await db.execute(job_stmt)

    await _upsert_contacts(db, _build_contact_rows(prospect, prospect_data))
    await _upsert_pages(db, _build_page_rows(prospect, prospect_data))

    await db.commit()
    await db.refresh(prospect)
    logger.info(f"Persistencia completa para dominio: {domain}")
    return prospect
