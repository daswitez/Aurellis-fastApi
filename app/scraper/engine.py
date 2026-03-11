import logging
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from app.scraper.http_client import FetchHtmlError, fetch_html
from app.scraper.parser import parse_html_basic
from app.services.ai_extractor import AIExtractionFallbackError, PROMPT_VERSION, extract_business_entity_ai
from app.services.discovery import build_discovery_metadata
from app.services.entity_classifier import classify_entity_type
from app.services.heuristic_extractor import extract_business_entity_heuristic
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
    "internal_links",
    "map_links",
    "addresses",
    "opening_hours",
    "cta_candidates",
    "structured_data",
    "structured_data_evidence",
    "contact_channels",
}


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


async def _crawl_key_pages(root_metadata: Dict[str, Any]) -> tuple[str, Dict[str, Any], list[dict[str, str]]]:
    selected_pages = _select_key_internal_links(root_metadata.get("internal_links", []))
    merged_text_parts: list[str] = []
    merged_metadata: Dict[str, Any] = {
        "title": "",
        "description": "",
        "emails": [],
        "phones": [],
        "social_links": [],
        "internal_links": [],
        "map_links": [],
        "addresses": [],
        "structured_data": [],
        "structured_data_evidence": [],
        "contact_channels": [],
        "cta_candidates": [],
        "form_detected": False,
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


def extract_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path
        if domain.startswith("www."):
            domain = domain[4:]
        return domain.lower()
    except Exception:
        return url


async def scrape_single_prospect(target_url: str, job_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    domain = extract_domain(target_url)
    logger.info("==> Iniciando scraping de dominio: %s <==", domain)

    html_raw = await fetch_html(target_url)
    if not html_raw:
        logger.warning("No se pudo obtener HTML para %s", target_url)
        return None

    clean_text, html_metadata = parse_html_basic(html_raw, base_url=target_url)
    key_pages_text, key_pages_metadata, crawled_pages = await _crawl_key_pages(html_metadata)
    combined_text = clean_text if not key_pages_text else f"{clean_text}\n\n{key_pages_text}"
    merged_metadata = _merge_html_metadata(html_metadata, key_pages_metadata)
    merged_metadata["website_url"] = target_url
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
                domain=domain,
                clean_text=combined_text,
                metadata=merged_metadata,
                heuristic_data=heuristic_baseline,
                quality_data=quality_data,
                discovery_metadata=discovery_metadata,
            )
            extracted_data = await extract_business_entity_ai(
                domain,
                combined_text,
                job_context,
                evidence_pack=evidence_pack,
                cache_key=build_ai_cache_signature(domain, combined_text[:2500], PROMPT_VERSION),
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
        generic_attributes.setdefault("service_keywords", quality_data.get("service_keywords"))
        generic_attributes.setdefault("company_size_signal", quality_data.get("company_size_signal"))

    final_prospect = {
        "domain": domain,
        "website_url": target_url,
        "company_name": _pick_first_defined(extracted_data.get("company_name"), heuristic_baseline.get("company_name"), domain),
        "category": _pick_first_defined(extracted_data.get("category"), heuristic_baseline.get("category")),
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
        "instagram_url": next((s for s in merged_metadata.get("social_links", []) if "instagram.com" in s), None),
        "facebook_url": next((s for s in merged_metadata.get("social_links", []) if "facebook.com" in s), None),
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
        "inferred_niche": _pick_first_defined(extracted_data.get("inferred_niche"), heuristic_baseline.get("inferred_niche")),
        "generic_attributes": generic_attributes,
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
    }

    logger.info(
        "Terminado el procesamiento para %s. quality_status=%s",
        domain,
        final_prospect.get("quality_status"),
    )
    return final_prospect
