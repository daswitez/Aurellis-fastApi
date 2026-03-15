import logging
from typing import Any, Dict, Optional

from app.scraper.http_client import FetchHtmlError, fetch_html
from app.scraper.parser import parse_html_basic
from app.services.ai_extractor import AIExtractionFallbackError, PROMPT_VERSION, extract_business_entity_ai
from app.services.business_taxonomy import resolve_business_taxonomy
from app.services.discovery import build_discovery_metadata
from app.services.entity_classifier import classify_entity_type
from app.services.heuristic_extractor import extract_business_entity_heuristic
from app.services.identity_resolution import extract_domain, normalize_social_profile_url, resolve_identity_surfaces
from app.services.prospect_quality import (
    build_ai_cache_signature,
    build_ai_evidence_pack,
    evaluate_prospect_quality,
    should_call_ai,
)
from app.services.scoring import build_final_score

logger = logging.getLogger(__name__)

MAX_KEY_PAGES_TO_CRAWL = 5
KEY_PAGE_PRIORITY = {
    "contact": 0,
    "locations": 1,
    "pricing": 2,
    "booking": 3,
    "services": 4,
    "about": 5,
    "careers": 6,
    "other": 7,
}
LIST_METADATA_FIELDS = {
    "emails",
    "phones",
    "social_links",
    "social_profiles",
    "internal_links",
    "external_links",
    "map_links",
    "addresses",
    "opening_hours",
    "cta_candidates",
    "structured_data",
    "structured_data_evidence",
    "contact_channels",
}
COUNT_METADATA_FIELDS = {
    "phone_validation_rejections",
}


def _merge_count_dicts(base_value: dict[str, int] | None, incoming_value: dict[str, int] | None) -> dict[str, int]:
    merged: dict[str, int] = {}
    for source in (base_value or {}, incoming_value or {}):
        for key, value in source.items():
            merged[str(key)] = merged.get(str(key), 0) + int(value or 0)
    return merged


def _classify_page_type(url: str) -> str:
    lowered = url.lower()
    if "contact" in lowered or "contacto" in lowered:
        return "contact"
    if "location" in lowered or "ubicacion" in lowered or "locations" in lowered or "sede" in lowered:
        return "locations"
    if "pricing" in lowered or "precio" in lowered or "precios" in lowered or "cotiza" in lowered:
        return "pricing"
    if "book" in lowered or "booking" in lowered or "reserv" in lowered or "agenda" in lowered or "cita" in lowered:
        return "booking"
    if "service" in lowered or "servicio" in lowered:
        return "services"
    if "about" in lowered or "nosotros" in lowered or "equipo" in lowered:
        return "about"
    if "career" in lowered or "trabajo" in lowered or "empleo" in lowered:
        return "careers"
    return "other"


def _select_key_internal_links(internal_links: list[str], max_pages: int = MAX_KEY_PAGES_TO_CRAWL) -> list[dict[str, str]]:
    unique_links: list[str] = []
    for link in internal_links:
        if link not in unique_links:
            unique_links.append(link)

    sorted_links = sorted(
        unique_links,
        key=lambda link: (KEY_PAGE_PRIORITY.get(_classify_page_type(link), 99), link),
    )
    return [{"url": link, "page_type": _classify_page_type(link)} for link in sorted_links[:max_pages]]


def _dedupe_json_like_items(items: list[Any]) -> list[Any]:
    deduped: list[Any] = []
    seen_tokens: set[str] = set()
    for item in items:
        token = repr(item)
        if token in seen_tokens:
            continue
        seen_tokens.add(token)
        deduped.append(item)
    return deduped


def _merge_html_metadata(base_metadata: Dict[str, Any], incoming_metadata: Dict[str, Any]) -> Dict[str, Any]:
    merged_metadata: Dict[str, Any] = {}
    all_keys = set(base_metadata.keys()) | set(incoming_metadata.keys())

    for key in all_keys:
        base_value = base_metadata.get(key)
        incoming_value = incoming_metadata.get(key)
        if key in LIST_METADATA_FIELDS:
            merged_metadata[key] = _dedupe_json_like_items(list(base_value or []) + list(incoming_value or []))
        elif key in COUNT_METADATA_FIELDS and (isinstance(base_value, dict) or isinstance(incoming_value, dict)):
            merged_metadata[key] = _merge_count_dicts(
                base_value if isinstance(base_value, dict) else {},
                incoming_value if isinstance(incoming_value, dict) else {},
            )
        elif isinstance(base_value, dict) or isinstance(incoming_value, dict):
            merged_metadata[key] = incoming_value or base_value
        elif (
            isinstance(base_value, (int, float))
            or isinstance(incoming_value, (int, float))
        ) and not isinstance(base_value, bool) and not isinstance(incoming_value, bool):
            merged_metadata[key] = int(base_value or 0) + int(incoming_value or 0)
        elif isinstance(base_value, bool) or isinstance(incoming_value, bool):
            merged_metadata[key] = bool(base_value or incoming_value)
        else:
            merged_metadata[key] = base_value or incoming_value

    return merged_metadata


def _select_contact_page_url(internal_links: list[str]) -> str | None:
    for priority_keywords in (["contact", "contacto"], ["about", "nosotros", "equipo"]):
        for link in internal_links:
            lowered = link.lower()
            if any(keyword in lowered for keyword in priority_keywords):
                return link
    return None


def _has_enough_crawl_signals(metadata: Dict[str, Any]) -> bool:
    return bool(
        (metadata.get("emails") or metadata.get("phones") or metadata.get("form_detected"))
        and metadata.get("addresses")
        and (metadata.get("primary_cta") or metadata.get("booking_url") or metadata.get("pricing_page_url"))
    )


def _build_ai_trace(
    *,
    status: str,
    selected_method: str,
    evaluation_method: str,
    fallback_reason: str | None = None,
    error_type: str | None = None,
    retryable: bool | None = None,
    message: str | None = None,
    latency_ms: int | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    estimated_cost_usd: float | None = None,
    cache_hit: bool | None = None,
) -> Dict[str, Any]:
    return {
        "provider": "deepseek",
        "prompt_version": PROMPT_VERSION,
        "status": status,
        "selected_method": selected_method,
        "evaluation_method": evaluation_method,
        "fallback_reason": fallback_reason,
        "error_type": error_type,
        "retryable": retryable,
        "message": message,
        "latency_ms": latency_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": estimated_cost_usd,
        "cache_hit": cache_hit,
    }


def _pick_first_defined(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _pick_signal_list(*containers: Any, key: str) -> list[str]:
    for container in containers:
        if isinstance(container, dict):
            value = container.get(key)
            if isinstance(value, list):
                return value
            generic_attributes = container.get("generic_attributes")
            if isinstance(generic_attributes, dict) and isinstance(generic_attributes.get(key), list):
                return generic_attributes[key]
    return []


def _mark_primary_social_profile(
    social_profiles: list[dict[str, Any]] | None,
    *,
    primary_identity_type: str,
    primary_identity_url: str | None,
) -> list[dict[str, Any]]:
    normalized_profiles: list[dict[str, Any]] = []
    primary_url = normalize_social_profile_url(primary_identity_url) or str(primary_identity_url or "").strip()

    for profile in social_profiles or []:
        if not isinstance(profile, dict):
            continue
        normalized_profile = dict(profile)
        normalized_profile_url = normalize_social_profile_url(normalized_profile.get("url")) or str(normalized_profile.get("url") or "").strip()
        normalized_profile["url"] = normalized_profile_url
        normalized_profile["is_primary"] = bool(
            primary_identity_type == "social_profile" and primary_url and normalized_profile_url == primary_url
        )
        normalized_profiles.append(normalized_profile)

    return normalized_profiles


async def _crawl_key_pages(root_metadata: Dict[str, Any]) -> tuple[str, Dict[str, Any], list[dict[str, str]]]:
    selected_pages = _select_key_internal_links(root_metadata.get("internal_links", []))
    merged_text_parts: list[str] = []
    merged_metadata: Dict[str, Any] = {
        "title": "",
        "description": "",
        "emails": [],
        "phones": [],
        "social_links": [],
        "social_profiles": [],
        "internal_links": [],
        "external_links": [],
        "map_links": [],
        "addresses": [],
        "structured_data": [],
        "structured_data_evidence": [],
        "contact_channels": [],
        "cta_candidates": [],
        "form_detected": False,
        "phone_validation_rejections": {},
        "invalid_phone_candidates_count": 0,
        "primary_identity_type": "website",
        "primary_identity_url": None,
    }
    crawled_pages: list[dict[str, str]] = []

    for page in selected_pages:
        page_url = page["url"]
        page_type = page["page_type"]
        try:
            html = await fetch_html(page_url)
        except FetchHtmlError as exc:
            logger.warning(
                "No se pudo crawlear pagina clave %s (%s): %s [%s]",
                page_url,
                page_type,
                exc.message,
                exc.error_type,
            )
            continue

        page_text, page_metadata = parse_html_basic(html, base_url=page_url)
        if page_text:
            merged_text_parts.append(f"[{page_type.upper()}] {page_text[:1200]}")
        merged_metadata = _merge_html_metadata(merged_metadata, page_metadata)
        crawled_pages.append({"url": page_url, "page_type": page_type})

        if _has_enough_crawl_signals(merged_metadata):
            break

    return "\n\n".join(merged_text_parts), merged_metadata, crawled_pages


async def scrape_single_prospect(target_url: str, job_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    domain = extract_domain(target_url)
    logger.info("==> Iniciando scraping de dominio: %s <==", domain)

    html_raw = await fetch_html(target_url)
    if not html_raw:
        logger.warning("No se pudo obtener HTML para %s", target_url)
        return None

    clean_text, html_metadata = parse_html_basic(html_raw, base_url=target_url)
    if str(html_metadata.get("primary_identity_type") or "website") == "social_profile":
        key_pages_text, key_pages_metadata, crawled_pages = "", {}, []
    else:
        key_pages_text, key_pages_metadata, crawled_pages = await _crawl_key_pages(html_metadata)
    combined_text = clean_text if not key_pages_text else f"{clean_text}\n\n{key_pages_text}"
    merged_metadata = _merge_html_metadata(html_metadata, key_pages_metadata)
    surface_resolution = resolve_identity_surfaces(target_url, merged_metadata)
    canonical_identity = surface_resolution["canonical_identity"]
    primary_identity_type = surface_resolution["primary_identity_type"]
    primary_identity_url = surface_resolution["primary_identity_url"]
    merged_metadata["website_url"] = surface_resolution.get("website_url")
    merged_metadata["primary_identity_type"] = primary_identity_type
    merged_metadata["primary_identity_url"] = primary_identity_url
    merged_metadata["entry_surface"] = surface_resolution.get("entry_surface")
    merged_metadata["identity_surface"] = surface_resolution.get("identity_surface")
    merged_metadata["contact_surface"] = surface_resolution.get("contact_surface")
    merged_metadata["offer_surface"] = surface_resolution.get("offer_surface")
    merged_metadata["identity_resolution_reason"] = surface_resolution.get("identity_resolution_reason")
    merged_metadata["social_profiles"] = _mark_primary_social_profile(
        merged_metadata.get("social_profiles"),
        primary_identity_type=primary_identity_type,
        primary_identity_url=primary_identity_url,
    )
    identity_key = canonical_identity
    heuristic_baseline = await extract_business_entity_heuristic(combined_text, html_raw, merged_metadata, job_context)

    discovery_metadata = build_discovery_metadata(
        job_context.get("discovery_entry"),
        job_context.get("discovery_queries", []),
    )
    entity_data = classify_entity_type(
        target_url=target_url,
        clean_text=combined_text,
        metadata=merged_metadata,
        discovery_metadata=discovery_metadata,
    )
    quality_data = evaluate_prospect_quality(
        clean_text=combined_text,
        metadata=merged_metadata,
        context=job_context,
        heuristic_data=heuristic_baseline,
        discovery_metadata=discovery_metadata,
        entity_data=entity_data,
    )

    use_ai, gate_reason = should_call_ai(heuristic_baseline, quality_data)
    ai_trace: Dict[str, Any]

    if not use_ai:
        extracted_data = heuristic_baseline
        generic_attributes = extracted_data.get("generic_attributes")
        if isinstance(generic_attributes, dict):
            generic_attributes["ai_gate_reason"] = gate_reason
        ai_trace = _build_ai_trace(
            status="skipped",
            selected_method="heuristic",
            evaluation_method="Heuristic Code (AI gated)",
            fallback_reason=gate_reason,
            error_type="ai_skipped",
            retryable=False,
            message=f"IA omitida por gate: {gate_reason}",
        )
    else:
        try:
            evidence_pack = build_ai_evidence_pack(
                domain=identity_key,
                clean_text=combined_text,
                metadata=merged_metadata,
                heuristic_data=heuristic_baseline,
                quality_data=quality_data,
                discovery_metadata=discovery_metadata,
            )
            extracted_data = await extract_business_entity_ai(
                identity_key,
                combined_text,
                job_context,
                evidence_pack=evidence_pack,
                cache_key=build_ai_cache_signature(identity_key, combined_text[:2500], PROMPT_VERSION),
            )
            ai_metrics = extracted_data.pop("_ai_metrics", {})
            evaluation_method = "DeepSeek API ({})".format(PROMPT_VERSION)
            generic_attributes = extracted_data.get("generic_attributes")
            if isinstance(generic_attributes, dict):
                evaluation_method = str(generic_attributes.get("evaluation_method") or evaluation_method)
            ai_trace = _build_ai_trace(
                status="success",
                selected_method="ai",
                evaluation_method=evaluation_method,
                latency_ms=ai_metrics.get("latency_ms"),
                prompt_tokens=ai_metrics.get("prompt_tokens"),
                completion_tokens=ai_metrics.get("completion_tokens"),
                total_tokens=ai_metrics.get("total_tokens"),
                estimated_cost_usd=ai_metrics.get("estimated_cost_usd"),
                cache_hit=ai_metrics.get("cache_hit"),
            )
        except AIExtractionFallbackError as ai_e:
            logger.warning("Fallback heuristico para %s por %s [%s]", target_url, ai_e.reason, ai_e.error_type)
            extracted_data = heuristic_baseline
            evaluation_method = "Heuristic Code (No LLM)"
            generic_attributes = extracted_data.get("generic_attributes")
            if isinstance(generic_attributes, dict):
                generic_attributes["fallback_reason"] = ai_e.reason
                generic_attributes["ai_error_type"] = ai_e.error_type
                evaluation_method = str(generic_attributes.get("evaluation_method") or evaluation_method)
            ai_trace = _build_ai_trace(
                status="fallback",
                selected_method="heuristic",
                evaluation_method=evaluation_method,
                fallback_reason=ai_e.reason,
                error_type=ai_e.error_type,
                retryable=ai_e.retryable,
                message=str(ai_e),
                latency_ms=ai_e.usage.get("latency_ms"),
                prompt_tokens=ai_e.usage.get("prompt_tokens"),
                completion_tokens=ai_e.usage.get("completion_tokens"),
                total_tokens=ai_e.usage.get("total_tokens"),
                estimated_cost_usd=ai_e.usage.get("estimated_cost_usd"),
                cache_hit=ai_e.usage.get("cache_hit"),
            )
        except Exception as ai_e:
            logger.error("Error AI inesperado para %s. Usando heuristica fallback: %s", target_url, ai_e)
            extracted_data = heuristic_baseline
            evaluation_method = "Heuristic Code (No LLM)"
            generic_attributes = extracted_data.get("generic_attributes")
            if isinstance(generic_attributes, dict):
                generic_attributes["fallback_reason"] = "unexpected_exception"
                generic_attributes["ai_error_type"] = "unexpected_exception"
                evaluation_method = str(generic_attributes.get("evaluation_method") or evaluation_method)
            ai_trace = _build_ai_trace(
                status="fallback",
                selected_method="heuristic",
                evaluation_method=evaluation_method,
                fallback_reason="unexpected_exception",
                error_type="unexpected_exception",
                retryable=False,
                message=str(ai_e),
            )

    final_scoring = build_final_score(
        ai_data=extracted_data,
        ai_trace=ai_trace,
        heuristic_data=heuristic_baseline,
        quality_data=quality_data,
    )

    internal_links = merged_metadata.get("internal_links", [])
    contact_page_url = _select_contact_page_url(internal_links)
    generic_attributes = _pick_first_defined(extracted_data.get("generic_attributes"), heuristic_baseline.get("generic_attributes"), {})
    if isinstance(generic_attributes, dict):
        generic_attributes.setdefault(
            "surface_resolution",
            {
                "entry_surface": merged_metadata.get("entry_surface"),
                "identity_surface": merged_metadata.get("identity_surface"),
                "contact_surface": merged_metadata.get("contact_surface"),
                "offer_surface": merged_metadata.get("offer_surface"),
                "identity_resolution_reason": merged_metadata.get("identity_resolution_reason"),
                "owned_website_candidates": surface_resolution.get("owned_website_candidates", []),
                "identity_hub_evidence": surface_resolution.get("identity_hub_evidence"),
            },
        )
        generic_attributes.setdefault("social_quality", quality_data.get("social_quality"))
        generic_attributes.setdefault("service_keywords", quality_data.get("service_keywords"))
        generic_attributes.setdefault("company_size_signal", quality_data.get("company_size_signal"))
        heuristic_generic_attributes = heuristic_baseline.get("generic_attributes") if isinstance(heuristic_baseline, dict) else {}
        if isinstance(heuristic_generic_attributes, dict):
            generic_attributes.setdefault("content_profile", heuristic_generic_attributes.get("content_profile"))
            generic_attributes.setdefault("budget_signal_matches", heuristic_generic_attributes.get("budget_signal_matches", []))
        generic_attributes.setdefault(
            "observed_signals",
            _pick_signal_list(extracted_data, heuristic_baseline, key="observed_signals"),
        )
        generic_attributes.setdefault(
            "inferred_opportunities",
            _pick_signal_list(extracted_data, heuristic_baseline, key="inferred_opportunities"),
        )
        generic_attributes.setdefault(
            "pain_points_detected",
            generic_attributes.get("inferred_opportunities"),
        )

    observed_signals = _pick_signal_list(extracted_data, heuristic_baseline, key="observed_signals")
    inferred_opportunities = _pick_signal_list(extracted_data, heuristic_baseline, key="inferred_opportunities")
    taxonomy_data = resolve_business_taxonomy(
        clean_text=combined_text,
        metadata=merged_metadata,
        entity_type_detected=quality_data.get("entity_type_detected"),
        inferred_niche=_pick_first_defined(extracted_data.get("inferred_niche"), heuristic_baseline.get("inferred_niche")),
        category=_pick_first_defined(extracted_data.get("category"), heuristic_baseline.get("category")),
        target_niche=job_context.get("target_niche"),
    )
    if isinstance(generic_attributes, dict):
        generic_attributes.setdefault("taxonomy_top_level", taxonomy_data.get("taxonomy_top_level"))
        generic_attributes.setdefault("taxonomy_business_type", taxonomy_data.get("taxonomy_business_type"))
        generic_attributes.setdefault("taxonomy_evidence", taxonomy_data.get("taxonomy_evidence"))

    final_prospect = {
        "canonical_identity": canonical_identity,
        "domain": extract_domain(merged_metadata["website_url"]) if merged_metadata.get("website_url") else None,
        "primary_identity_type": primary_identity_type,
        "primary_identity_url": primary_identity_url,
        "website_url": merged_metadata.get("website_url"),
        "company_name": _pick_first_defined(
            extracted_data.get("company_name"),
            heuristic_baseline.get("company_name"),
            (merged_metadata.get("social_profile") or {}).get("display_name"),
            domain,
        ),
        "category": taxonomy_data.get("display_category") or _pick_first_defined(extracted_data.get("category"), heuristic_baseline.get("category")),
        "location": quality_data.get("location"),
        "raw_location_text": quality_data.get("raw_location_text"),
        "parsed_location": quality_data.get("parsed_location"),
        "city": quality_data.get("city"),
        "region": quality_data.get("region"),
        "country": quality_data.get("country"),
        "postal_code": quality_data.get("postal_code"),
        "validated_location": quality_data.get("validated_location"),
        "location_match_status": quality_data.get("location_match_status"),
        "location_confidence": quality_data.get("location_confidence"),
        "detected_language": quality_data.get("detected_language"),
        "language_match_status": quality_data.get("language_match_status"),
        "description": _pick_first_defined(extracted_data.get("description"), heuristic_baseline.get("description")),
        "email": quality_data.get("email"),
        "phone": quality_data.get("phone"),
        "contact_page_url": contact_page_url,
        "form_detected": merged_metadata.get("form_detected", False),
        "linkedin_url": next((s for s in merged_metadata.get("social_links", []) if "linkedin.com" in s), None),
        "instagram_url": next(
            (
                s
                for s in [primary_identity_url, *merged_metadata.get("social_links", [])]
                if s and "instagram.com" in s
            ),
            None,
        ),
        "tiktok_url": next(
            (
                s
                for s in [primary_identity_url, *merged_metadata.get("social_links", [])]
                if s and "tiktok.com" in s
            ),
            None,
        ),
        "facebook_url": next((s for s in merged_metadata.get("social_links", []) if "facebook.com" in s), None),
        "social_profiles": quality_data.get("social_profiles_enriched") or merged_metadata.get("social_profiles"),
        "social_quality": quality_data.get("social_quality"),
        "primary_cta": quality_data.get("primary_cta"),
        "booking_url": quality_data.get("booking_url"),
        "pricing_page_url": quality_data.get("pricing_page_url"),
        "whatsapp_url": quality_data.get("whatsapp_url"),
        "contact_channels_json": quality_data.get("contact_channels_json"),
        "contact_quality_score": quality_data.get("contact_quality_score"),
        "contact_consistency_status": quality_data.get("contact_consistency_status"),
        "primary_email_confidence": quality_data.get("primary_email_confidence"),
        "primary_phone_confidence": quality_data.get("primary_phone_confidence"),
        "primary_contact_source": quality_data.get("primary_contact_source"),
        "company_size_signal": quality_data.get("company_size_signal"),
        "service_keywords": quality_data.get("service_keywords"),
        "inferred_tech_stack": _pick_first_defined(extracted_data.get("inferred_tech_stack"), heuristic_baseline.get("inferred_tech_stack")),
        "inferred_niche": taxonomy_data.get("inferred_niche"),
        "taxonomy_top_level": taxonomy_data.get("taxonomy_top_level"),
        "taxonomy_business_type": taxonomy_data.get("taxonomy_business_type"),
        "generic_attributes": generic_attributes,
        "observed_signals": observed_signals,
        "inferred_opportunities": inferred_opportunities,
        "estimated_revenue_signal": _pick_first_defined(extracted_data.get("estimated_revenue_signal"), heuristic_baseline.get("estimated_revenue_signal")),
        "has_active_ads": _pick_first_defined(extracted_data.get("has_active_ads"), heuristic_baseline.get("has_active_ads")),
        "hiring_signals": _pick_first_defined(extracted_data.get("hiring_signals"), heuristic_baseline.get("hiring_signals"), False),
        "score": final_scoring["score"],
        "confidence_level": final_scoring["confidence_level"],
        "entity_type_detected": quality_data.get("entity_type_detected"),
        "entity_type_confidence": quality_data.get("entity_type_confidence"),
        "entity_type_evidence": quality_data.get("entity_type_evidence"),
        "is_target_entity": quality_data.get("is_target_entity"),
        "acceptance_decision": quality_data.get("acceptance_decision"),
        "fit_summary": final_scoring["fit_summary"],
        "heuristic_trace": heuristic_baseline.get("heuristic_trace"),
        "scoring_trace": final_scoring["scoring_trace"],
        "quality_status": quality_data.get("quality_status"),
        "quality_flags": quality_data.get("quality_flags"),
        "rejection_reason": quality_data.get("rejection_reason"),
        "discovery_confidence": quality_data.get("discovery_confidence"),
        "source": "HTTPX_Scraper",
        "source_url": target_url,
        "surface_resolution": generic_attributes.get("surface_resolution") if isinstance(generic_attributes, dict) else None,
        "job_id": job_context.get("job_id"),
        "internal_links": internal_links,
        "crawled_pages": crawled_pages,
        "ai_trace": ai_trace,
        "geo_evidence": quality_data.get("geo_evidence"),
        "language_evidence": quality_data.get("language_evidence"),
        "cta_evidence": quality_data.get("cta_evidence"),
        "structured_data_evidence": quality_data.get("structured_data_evidence"),
        "discovery_evidence": quality_data.get("discovery_evidence"),
        "content_coverage": quality_data.get("content_coverage"),
        "phone_validation_rejections": merged_metadata.get("phone_validation_rejections"),
        "invalid_phone_candidates_count": merged_metadata.get("invalid_phone_candidates_count", 0),
    }

    logger.info(
        "Terminado el procesamiento para %s. quality_status=%s",
        domain,
        final_prospect.get("quality_status"),
    )
    return final_prospect
