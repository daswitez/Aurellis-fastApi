import logging
import re
from datetime import datetime
from typing import Dict, Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models import JobProspect, Prospect, ProspectContact, ProspectPage
from app.services.source_metadata import normalize_discovery_method, normalize_source_type

logger = logging.getLogger(__name__)
UNSAFE_CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _confidence_label_to_score(value: str | None) -> float:
    mapping = {
        "low": 0.35,
        "medium": 0.65,
        "high": 0.9,
    }
    return mapping.get(str(value or "").strip().lower(), 0.5)


def _sanitize_string_for_db(value: str | None) -> str | None:
    if value is None:
        return None
    sanitized = str(value).replace("\x00", "")
    sanitized = UNSAFE_CONTROL_CHAR_PATTERN.sub(" ", sanitized)
    return sanitized


def _sanitize_value_for_db(value: Any) -> Any:
    if isinstance(value, str):
        return _sanitize_string_for_db(value)
    if isinstance(value, list):
        return [_sanitize_value_for_db(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_value_for_db(item) for item in value]
    if isinstance(value, dict):
        sanitized_dict: dict[str, Any] = {}
        for key, nested_value in value.items():
            sanitized_key = _sanitize_string_for_db(key) if isinstance(key, str) else str(key)
            sanitized_dict[sanitized_key] = _sanitize_value_for_db(nested_value)
        return sanitized_dict
    return value

def _extract_canonical_prospect_data(prospect_data: Dict[str, Any]) -> Dict[str, Any]:
    prospect_columns = {col.name for col in Prospect.__table__.columns}
    excluded_columns = {"id", "created_at", "job_id"}
    return _sanitize_value_for_db({
        key: value
        for key, value in prospect_data.items()
        if key in prospect_columns and key not in excluded_columns
    })


def _extract_signal_list(prospect_data: Dict[str, Any], key: str) -> list[str]:
    raw_value = prospect_data.get(key)
    if isinstance(raw_value, list):
        return raw_value

    generic_attributes = prospect_data.get("generic_attributes")
    if isinstance(generic_attributes, dict) and isinstance(generic_attributes.get(key), list):
        return generic_attributes[key]
    return []


def _extract_job_prospect_data(
    prospect: Prospect,
    prospect_data: Dict[str, Any],
    job_context: Dict[str, Any],
) -> Dict[str, Any]:
    now = datetime.utcnow()
    observed_signals = _extract_signal_list(prospect_data, "observed_signals")
    inferred_opportunities = _extract_signal_list(prospect_data, "inferred_opportunities")
    pain_points_detected = inferred_opportunities or _extract_signal_list(prospect_data, "pain_points_detected")

    return _sanitize_value_for_db({
        "job_id": job_context["job_id"],
        "prospect_id": prospect.id,
        "workspace_id": job_context.get("workspace_id") or prospect.workspace_id,
        "source_url": prospect_data.get("source_url"),
        "source_type": normalize_source_type(job_context.get("source_type") or prospect_data.get("source")),
        "discovery_method": normalize_discovery_method(job_context.get("discovery_method")),
        "search_query_snapshot": job_context.get("search_query"),
        "rank_position": prospect_data.get("rank_position"),
        "processing_status": "processed",
        "quality_status": prospect_data.get("quality_status") or "accepted",
        "quality_flags_json": prospect_data.get("quality_flags"),
        "rejection_reason": prospect_data.get("rejection_reason"),
        "acceptance_decision": prospect_data.get("acceptance_decision"),
        "contact_consistency_status": prospect_data.get("contact_consistency_status"),
        "primary_email_confidence": prospect_data.get("primary_email_confidence"),
        "primary_phone_confidence": prospect_data.get("primary_phone_confidence"),
        "primary_contact_source": prospect_data.get("primary_contact_source"),
        "discovery_confidence": prospect_data.get("discovery_confidence"),
        "entity_type_detected": prospect_data.get("entity_type_detected"),
        "entity_type_confidence": prospect_data.get("entity_type_confidence"),
        "entity_type_evidence": prospect_data.get("entity_type_evidence"),
        "is_target_entity": prospect_data.get("is_target_entity"),
        "taxonomy_top_level": prospect_data.get("taxonomy_top_level"),
        "taxonomy_business_type": prospect_data.get("taxonomy_business_type"),
        "match_score": prospect_data.get("score", 0.0),
        "confidence_level": prospect_data.get("confidence_level"),
        "fit_summary": prospect_data.get("fit_summary"),
        "pain_points_json": pain_points_detected or None,
        "observed_signals": observed_signals or None,
        "inferred_opportunities": inferred_opportunities or None,
        "evidence_json": {
            "source_type": normalize_source_type(job_context.get("source_type") or prospect_data.get("source")),
            "discovery_method": normalize_discovery_method(job_context.get("discovery_method")),
            "search_query": job_context.get("search_query"),
            "canonical_identity": prospect_data.get("canonical_identity"),
            "primary_identity_type": prospect_data.get("primary_identity_type"),
            "primary_identity_url": prospect_data.get("primary_identity_url"),
            "emails": [value for value in [prospect_data.get("email")] if value],
            "phones": [value for value in [prospect_data.get("phone")] if value],
            "socials": [
                value
                for value in [
                    prospect_data.get("linkedin_url"),
                    prospect_data.get("instagram_url"),
                    prospect_data.get("tiktok_url"),
                    prospect_data.get("facebook_url"),
                ]
                if value
            ],
            "social_profiles": prospect_data.get("social_profiles"),
            "social_quality": prospect_data.get("social_quality"),
            "surface_resolution": prospect_data.get("surface_resolution"),
            "contact_page_url": prospect_data.get("contact_page_url"),
            "form_detected": prospect_data.get("form_detected", False),
            "contact_consistency_status": prospect_data.get("contact_consistency_status"),
            "primary_email_confidence": prospect_data.get("primary_email_confidence"),
            "primary_phone_confidence": prospect_data.get("primary_phone_confidence"),
            "primary_contact_source": prospect_data.get("primary_contact_source"),
            "geo_evidence": prospect_data.get("geo_evidence"),
            "raw_location_text": prospect_data.get("raw_location_text"),
            "parsed_location": prospect_data.get("parsed_location"),
            "city": prospect_data.get("city"),
            "region": prospect_data.get("region"),
            "country": prospect_data.get("country"),
            "postal_code": prospect_data.get("postal_code"),
            "language_evidence": prospect_data.get("language_evidence"),
            "cta_evidence": prospect_data.get("cta_evidence"),
            "structured_data_evidence": prospect_data.get("structured_data_evidence"),
            "discovery_evidence": prospect_data.get("discovery_evidence"),
            "observed_signals": observed_signals,
            "inferred_opportunities": inferred_opportunities,
            "acceptance_decision": prospect_data.get("acceptance_decision"),
            "entity_type_detected": prospect_data.get("entity_type_detected"),
            "entity_type_confidence": prospect_data.get("entity_type_confidence"),
            "entity_type_evidence": prospect_data.get("entity_type_evidence"),
            "is_target_entity": prospect_data.get("is_target_entity"),
            "taxonomy_top_level": prospect_data.get("taxonomy_top_level"),
            "taxonomy_business_type": prospect_data.get("taxonomy_business_type"),
            "content_coverage": prospect_data.get("content_coverage"),
            "heuristic_signals": (
                prospect_data.get("heuristic_trace", {}).get("signals")
                if isinstance(prospect_data.get("heuristic_trace"), dict)
                else None
            ),
            "scoring_trace": prospect_data.get("scoring_trace"),
            "phone_validation_rejections": prospect_data.get("phone_validation_rejections"),
            "invalid_phone_candidates_count": prospect_data.get("invalid_phone_candidates_count"),
        },
        "raw_extraction_json": {
            "inferred_niche": prospect_data.get("inferred_niche"),
            "taxonomy_top_level": prospect_data.get("taxonomy_top_level"),
            "taxonomy_business_type": prospect_data.get("taxonomy_business_type"),
            "inferred_tech_stack": prospect_data.get("inferred_tech_stack"),
            "generic_attributes": prospect_data.get("generic_attributes"),
            "observed_signals": observed_signals,
            "inferred_opportunities": inferred_opportunities,
            "estimated_revenue_signal": prospect_data.get("estimated_revenue_signal"),
            "has_active_ads": prospect_data.get("has_active_ads"),
            "hiring_signals": prospect_data.get("hiring_signals"),
            "raw_location_text": prospect_data.get("raw_location_text"),
            "parsed_location": prospect_data.get("parsed_location"),
            "city": prospect_data.get("city"),
            "region": prospect_data.get("region"),
            "country": prospect_data.get("country"),
            "postal_code": prospect_data.get("postal_code"),
            "validated_location": prospect_data.get("validated_location"),
            "location_match_status": prospect_data.get("location_match_status"),
            "location_confidence": prospect_data.get("location_confidence"),
            "detected_language": prospect_data.get("detected_language"),
            "language_match_status": prospect_data.get("language_match_status"),
            "primary_cta": prospect_data.get("primary_cta"),
            "booking_url": prospect_data.get("booking_url"),
            "pricing_page_url": prospect_data.get("pricing_page_url"),
            "whatsapp_url": prospect_data.get("whatsapp_url"),
            "contact_channels_json": prospect_data.get("contact_channels_json"),
            "contact_quality_score": prospect_data.get("contact_quality_score"),
            "contact_consistency_status": prospect_data.get("contact_consistency_status"),
            "primary_email_confidence": prospect_data.get("primary_email_confidence"),
            "primary_phone_confidence": prospect_data.get("primary_phone_confidence"),
            "primary_contact_source": prospect_data.get("primary_contact_source"),
            "primary_identity_type": prospect_data.get("primary_identity_type"),
            "primary_identity_url": prospect_data.get("primary_identity_url"),
            "social_profiles": prospect_data.get("social_profiles"),
            "social_quality": prospect_data.get("social_quality"),
            "surface_resolution": prospect_data.get("surface_resolution"),
            "company_size_signal": prospect_data.get("company_size_signal"),
            "service_keywords": prospect_data.get("service_keywords"),
            "acceptance_decision": prospect_data.get("acceptance_decision"),
            "entity_type_detected": prospect_data.get("entity_type_detected"),
            "entity_type_confidence": prospect_data.get("entity_type_confidence"),
            "entity_type_evidence": prospect_data.get("entity_type_evidence"),
            "is_target_entity": prospect_data.get("is_target_entity"),
            "ai_trace": prospect_data.get("ai_trace"),
            "heuristic_trace": prospect_data.get("heuristic_trace"),
            "scoring_trace": prospect_data.get("scoring_trace"),
            "phone_validation_rejections": prospect_data.get("phone_validation_rejections"),
            "invalid_phone_candidates_count": prospect_data.get("invalid_phone_candidates_count"),
        },
        "created_at": now,
        "updated_at": now,
    })


def _build_contact_rows(prospect: Prospect, prospect_data: Dict[str, Any]) -> list[Dict[str, Any]]:
    now = datetime.utcnow()
    contacts = []
    channel_index = {
        (str(channel.get("type") or "").strip().lower(), str(channel.get("value") or "").strip()): channel
        for channel in prospect_data.get("contact_channels_json", [])
        if isinstance(channel, dict)
    }
    candidates = [
        ("email", prospect_data.get("email"), "primary_email", True),
        ("phone", prospect_data.get("phone"), "primary_phone", True),
        ("whatsapp", prospect_data.get("whatsapp_url"), "whatsapp", False),
        ("booking", prospect_data.get("booking_url"), "booking_link", False),
        ("linkedin", prospect_data.get("linkedin_url"), "linkedin_profile", False),
        ("instagram", prospect_data.get("instagram_url"), "instagram_profile", False),
        ("tiktok", prospect_data.get("tiktok_url"), "tiktok_profile", False),
        ("facebook", prospect_data.get("facebook_url"), "facebook_profile", False),
    ]
    if prospect_data.get("form_detected"):
        candidates.append(("form", prospect_data.get("contact_page_url") or prospect_data.get("website_url"), "contact_form", False))

    for contact_type, contact_value, label, is_primary in candidates:
        if not contact_value:
            continue
        channel_data = channel_index.get((contact_type, str(contact_value).strip()), {})
        contacts.append(
            {
                "prospect_id": prospect.id,
                "contact_type": contact_type,
                "contact_value": contact_value,
                "label": label,
                "is_primary": is_primary,
                "is_public": True,
                "confidence": _confidence_label_to_score(channel_data.get("confidence")),
                "source_url": prospect_data.get("source_url"),
                "created_at": now,
                "updated_at": now,
            }
        )

    return _sanitize_value_for_db(contacts)


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

    add_page(
        prospect_data.get("primary_identity_url") or prospect_data.get("website_url"),
        "social_profile" if prospect_data.get("primary_identity_type") == "social_profile" else "home",
    )
    add_page(prospect_data.get("contact_page_url"), "contact")
    add_page(prospect_data.get("booking_url"), "booking")
    add_page(prospect_data.get("pricing_page_url"), "pricing")

    for crawled_page in prospect_data.get("crawled_pages", []):
        if not isinstance(crawled_page, dict):
            continue
        add_page(crawled_page.get("url"), crawled_page.get("page_type") or "other")

    for link in prospect_data.get("internal_links", []):
        lowered = link.lower()
        page_type = "other"
        if "contact" in lowered or "contacto" in lowered:
            page_type = "contact"
        elif "book" in lowered or "reserv" in lowered or "agenda" in lowered:
            page_type = "booking"
        elif "pricing" in lowered or "precio" in lowered or "precios" in lowered or "cotiza" in lowered:
            page_type = "pricing"
        elif "service" in lowered or "servicio" in lowered:
            page_type = "services"
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

    return _sanitize_value_for_db(list(pages.values()))


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

    canonical_identity = prospect_data.get("canonical_identity") or prospect_data.get("domain")
    if not canonical_identity:
        logger.error(f"No se puede guardar el prospecto sin identidad canónica válida: {prospect_data}")
        return None

    prospect_data = _sanitize_value_for_db(dict(prospect_data))
    prospect_data["canonical_identity"] = _sanitize_string_for_db(canonical_identity)
    canonical_prospect_data = _extract_canonical_prospect_data(prospect_data)
    stmt = insert(Prospect).values(**canonical_prospect_data)

    update_dict = {
        col.name: getattr(stmt.excluded, col.name)
        for col in Prospect.__table__.columns
        if col.name not in ["id", "canonical_identity", "created_at", "job_id"] and col.name in canonical_prospect_data
    }

    if update_dict:
        stmt = stmt.on_conflict_do_update(
            index_elements=["canonical_identity"],
            set_=update_dict
        )
    else:
        stmt = stmt.on_conflict_do_nothing(index_elements=["canonical_identity"])

    await db.execute(stmt)

    query = select(Prospect).where(Prospect.canonical_identity == canonical_identity)
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
            "quality_status": job_stmt.excluded.quality_status,
            "quality_flags_json": job_stmt.excluded.quality_flags_json,
            "rejection_reason": job_stmt.excluded.rejection_reason,
            "acceptance_decision": job_stmt.excluded.acceptance_decision,
            "contact_consistency_status": job_stmt.excluded.contact_consistency_status,
            "primary_email_confidence": job_stmt.excluded.primary_email_confidence,
            "primary_phone_confidence": job_stmt.excluded.primary_phone_confidence,
            "primary_contact_source": job_stmt.excluded.primary_contact_source,
            "discovery_confidence": job_stmt.excluded.discovery_confidence,
            "entity_type_detected": job_stmt.excluded.entity_type_detected,
            "entity_type_confidence": job_stmt.excluded.entity_type_confidence,
            "entity_type_evidence": job_stmt.excluded.entity_type_evidence,
            "is_target_entity": job_stmt.excluded.is_target_entity,
            "taxonomy_top_level": job_stmt.excluded.taxonomy_top_level,
            "taxonomy_business_type": job_stmt.excluded.taxonomy_business_type,
            "match_score": job_stmt.excluded.match_score,
            "confidence_level": job_stmt.excluded.confidence_level,
            "fit_summary": job_stmt.excluded.fit_summary,
            "pain_points_json": job_stmt.excluded.pain_points_json,
            "observed_signals": job_stmt.excluded.observed_signals,
            "inferred_opportunities": job_stmt.excluded.inferred_opportunities,
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
    logger.info(f"Persistencia completa para identidad: {canonical_identity}")
    return prospect
