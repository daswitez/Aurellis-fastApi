from __future__ import annotations

import re
import unicodedata
from typing import Any
from urllib.parse import urlparse

ENTITY_CLASSIFIER_VERSION = "entity_classifier_v1"
ENTITY_TYPE_VALUES = (
    "direct_business",
    "directory",
    "aggregator",
    "marketplace",
    "media",
    "blog_post",
    "association",
    "agency",
    "consultant",
    "unknown",
)
ENTITY_TYPE_DESCRIPTIONS = {
    "direct_business": "Empresa o proveedor que vende directamente sus propios servicios o productos.",
    "directory": "Listado o directorio que agrupa multiples negocios o proveedores.",
    "aggregator": "Comparador, ranking o pagina que resume multiples opciones del nicho.",
    "marketplace": "Marketplace que conecta multiples vendedores/proveedores con compradores.",
    "media": "Publisher, revista, newsroom o medio editorial.",
    "blog_post": "Articulo o post editorial individual dentro de un blog o medio.",
    "association": "Camara, asociacion, federacion o entidad gremial.",
    "agency": "Agencia o estudio que presta servicios profesionales.",
    "consultant": "Consultor o consultora independiente/especializada.",
    "unknown": "Tipo de entidad no concluyente con la evidencia disponible.",
}
TARGET_ENTITY_TYPES = frozenset({"direct_business", "agency", "consultant"})
NON_TARGET_ENTITY_TYPES = frozenset(
    {"directory", "aggregator", "marketplace", "media", "blog_post", "association"}
)
BUSINESS_SCHEMA_TYPES = {
    "accountingservice",
    "attorney",
    "automotivbusiness",
    "beautysalon",
    "dentalclinic",
    "dentist",
    "employmentagency",
    "financialservice",
    "healthandbeautybusiness",
    "homeandconstructionbusiness",
    "legalservice",
    "localbusiness",
    "medicalbusiness",
    "medicalclinic",
    "organization",
    "professionalservice",
    "realestateagent",
    "store",
}
ARTICLE_SCHEMA_TYPES = {"article", "blogposting", "newsarticle", "reportagearticle"}
LISTING_SCHEMA_TYPES = {"collectionpage", "itemlist", "searchresultspage"}
AGENCY_KEYWORDS = (
    "agency",
    "agencia",
    "creative studio",
    "digital studio",
    "estudio",
    "web studio",
    "marketing agency",
    "seo agency",
    "design agency",
)
CONSULTANT_KEYWORDS = (
    "consultant",
    "consultancy",
    "consulting",
    "consultor",
    "consultora",
    "advisor",
    "asesor",
    "asesoria",
)
ASSOCIATION_KEYWORDS = (
    "association",
    "asociacion",
    "asociación",
    "chamber",
    "camara",
    "cámara",
    "federation",
    "federacion",
    "federación",
    "guild",
    "society",
    "colegio profesional",
)
DIRECTORY_KEYWORDS = (
    "directory",
    "directorio",
    "listing",
    "listado",
    "business directory",
    "company directory",
    "provider directory",
    "find a",
    "encuentra",
)
AGGREGATOR_KEYWORDS = (
    "best",
    "top ",
    "top-",
    "compare",
    "comparison",
    "alternatives",
    "ranking",
    "rankings",
    "review",
    "reviews",
    "mejores",
    "comparador",
    "comparativa",
)
MARKETPLACE_KEYWORDS = (
    "marketplace",
    "vendors",
    "seller",
    "sellers",
    "buy and sell",
    "compra y vende",
    "multiple providers",
)
MEDIA_KEYWORDS = (
    "news",
    "newspaper",
    "newsroom",
    "press",
    "magazine",
    "revista",
    "journal",
    "diario",
    "media",
)
BLOG_PATH_KEYWORDS = ("/blog", "/article", "/articles", "/post", "/posts", "/news", "/noticias")
DIRECTORY_PATH_KEYWORDS = ("/directory", "/directorio", "/listing", "/companies", "/empresas", "/providers")
AGGREGATOR_PATH_KEYWORDS = ("/best-", "/compare", "/comparador", "/ranking", "/reviews", "/top-")
MARKETPLACE_PATH_KEYWORDS = ("/marketplace", "/vendors", "/seller", "/tienda", "/shop")
MEDIA_PATH_KEYWORDS = ("/newsroom", "/press", "/revista", "/magazine")


def _normalize_text(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = re.sub(r"\s+", " ", ascii_only.strip().lower())
    return lowered


def _contains_keyword(text: str, keywords: tuple[str, ...] | set[str]) -> list[str]:
    normalized_text = f" {_normalize_text(text)} "
    matches: list[str] = []
    for keyword in keywords:
        normalized_keyword = _normalize_text(keyword)
        if not normalized_keyword:
            continue
        if f" {normalized_keyword} " in normalized_text or normalized_keyword in normalized_text:
            matches.append(keyword)
    return matches


def _append_signal(
    scores: dict[str, int],
    evidence: dict[str, list[str]],
    entity_type: str,
    points: int,
    signal: str,
) -> None:
    scores[entity_type] += points
    evidence[entity_type].append(signal)


def _structured_types(metadata: dict[str, Any]) -> set[str]:
    detected: set[str] = set()
    for node in metadata.get("structured_data", []):
        if not isinstance(node, dict):
            continue
        node_type = node.get("@type")
        if isinstance(node_type, list):
            detected.update(_normalize_text(value) for value in node_type if value)
        elif isinstance(node_type, str):
            detected.add(_normalize_text(node_type))
    return {value for value in detected if value}


def classify_entity_type(
    *,
    target_url: str,
    clean_text: str,
    metadata: dict[str, Any],
    discovery_metadata: dict[str, Any],
) -> dict[str, Any]:
    scores = {entity_type: 0 for entity_type in ENTITY_TYPE_VALUES}
    evidence = {entity_type: [] for entity_type in ENTITY_TYPE_VALUES}

    website_url = str(metadata.get("website_url") or target_url or "")
    parsed_url = urlparse(website_url)
    host = (parsed_url.netloc or "").lower().removeprefix("www.")
    path = _normalize_text(parsed_url.path or "/")
    title = str(metadata.get("title") or "")
    description = str(metadata.get("description") or "")
    discovery_title = str(discovery_metadata.get("title") or "")
    discovery_snippet = str(discovery_metadata.get("snippet") or "")
    summary_text = " ".join(
        [
            title,
            description,
            discovery_title,
            discovery_snippet,
            " ".join(str(link) for link in metadata.get("internal_links", [])[:8]),
            clean_text[:1200],
        ]
    )
    normalized_summary = _normalize_text(summary_text)
    internal_links = [str(link) for link in metadata.get("internal_links", []) if str(link).strip()]
    structured_types = _structured_types(metadata)

    has_contact_signal = bool(metadata.get("emails") or metadata.get("phones") or metadata.get("form_detected"))
    has_address_signal = bool(metadata.get("addresses") or metadata.get("map_links"))
    has_service_page = any(any(token in link.lower() for token in ("service", "servicio")) for link in internal_links)
    has_about_page = any(any(token in link.lower() for token in ("about", "nosotros", "equipo")) for link in internal_links)
    has_contact_page = any(any(token in link.lower() for token in ("contact", "contacto")) for link in internal_links)
    has_pricing_or_booking = any(
        any(token in link.lower() for token in ("pricing", "precio", "precios", "book", "booking", "reserv", "agenda"))
        for link in internal_links
    ) or bool(metadata.get("booking_url") or metadata.get("pricing_page_url"))
    social_profile = metadata.get("social_profile") or {}
    social_offer_signals = social_profile.get("offer_signals") if isinstance(social_profile, dict) else []
    social_ctas = social_profile.get("platform_ctas") if isinstance(social_profile, dict) else []
    social_handle = social_profile.get("handle") if isinstance(social_profile, dict) else None

    if has_service_page:
        _append_signal(scores, evidence, "direct_business", 2, "service_navigation_detected")
    if has_about_page:
        _append_signal(scores, evidence, "direct_business", 1, "about_page_detected")
    if has_contact_page and has_contact_signal:
        _append_signal(scores, evidence, "direct_business", 2, "contact_page_and_channels_detected")
    elif has_contact_page or has_contact_signal:
        _append_signal(scores, evidence, "direct_business", 1, "contact_identity_signal_detected")
    if has_address_signal:
        _append_signal(scores, evidence, "direct_business", 2, "location_identity_signal_detected")
    if has_pricing_or_booking:
        _append_signal(scores, evidence, "direct_business", 1, "commercial_conversion_path_detected")
    if structured_types & BUSINESS_SCHEMA_TYPES:
        _append_signal(
            scores,
            evidence,
            "direct_business",
            3,
            f"business_schema_detected:{sorted(structured_types & BUSINESS_SCHEMA_TYPES)[0]}",
        )
    if metadata.get("primary_identity_type") == "social_profile" and social_handle:
        _append_signal(scores, evidence, "direct_business", 2, "social_handle_detected")
    if metadata.get("primary_identity_type") == "social_profile" and social_offer_signals:
        _append_signal(scores, evidence, "direct_business", 3, "social_offer_signals_detected")
    if metadata.get("primary_identity_type") == "social_profile" and social_ctas:
        _append_signal(scores, evidence, "direct_business", 2, "social_cta_detected")

    for keyword in _contains_keyword(normalized_summary, AGENCY_KEYWORDS):
        _append_signal(scores, evidence, "agency", 3, f"agency_keyword:{_normalize_text(keyword)}")
    for keyword in _contains_keyword(normalized_summary, CONSULTANT_KEYWORDS):
        _append_signal(scores, evidence, "consultant", 3, f"consultant_keyword:{_normalize_text(keyword)}")
    for keyword in _contains_keyword(normalized_summary, ASSOCIATION_KEYWORDS):
        _append_signal(scores, evidence, "association", 4, f"association_keyword:{_normalize_text(keyword)}")
    for keyword in _contains_keyword(normalized_summary, DIRECTORY_KEYWORDS):
        _append_signal(scores, evidence, "directory", 3, f"directory_keyword:{_normalize_text(keyword)}")
    for keyword in _contains_keyword(normalized_summary, AGGREGATOR_KEYWORDS):
        _append_signal(scores, evidence, "aggregator", 2, f"aggregator_keyword:{_normalize_text(keyword)}")
    for keyword in _contains_keyword(normalized_summary, MARKETPLACE_KEYWORDS):
        _append_signal(scores, evidence, "marketplace", 3, f"marketplace_keyword:{_normalize_text(keyword)}")
    for keyword in _contains_keyword(normalized_summary, MEDIA_KEYWORDS):
        _append_signal(scores, evidence, "media", 2, f"media_keyword:{_normalize_text(keyword)}")

    if any(token in path for token in BLOG_PATH_KEYWORDS):
        _append_signal(scores, evidence, "blog_post", 5, f"editorial_path:{path}")
    if any(token in path for token in DIRECTORY_PATH_KEYWORDS):
        _append_signal(scores, evidence, "directory", 4, f"directory_path:{path}")
    if any(token in path for token in AGGREGATOR_PATH_KEYWORDS):
        _append_signal(scores, evidence, "aggregator", 4, f"aggregator_path:{path}")
    if any(token in path for token in MARKETPLACE_PATH_KEYWORDS):
        _append_signal(scores, evidence, "marketplace", 4, f"marketplace_path:{path}")
    if any(token in path for token in MEDIA_PATH_KEYWORDS):
        _append_signal(scores, evidence, "media", 4, f"media_path:{path}")

    normalized_host = _normalize_text(host)
    if any(token in normalized_host for token in ("news", "revista", "magazine", "journal", "diario", "press")):
        _append_signal(scores, evidence, "media", 3, f"media_host:{normalized_host}")
    if any(token in normalized_host for token in ("directory", "directorio", "listing", "listings")):
        _append_signal(scores, evidence, "directory", 3, f"directory_host:{normalized_host}")
    if any(token in normalized_host for token in ("agency", "agencia", "studio", "estudio")):
        _append_signal(scores, evidence, "agency", 2, f"agency_host:{normalized_host}")
    if any(token in normalized_host for token in ("consult", "advisor", "asesor")):
        _append_signal(scores, evidence, "consultant", 2, f"consultant_host:{normalized_host}")

    if structured_types & ARTICLE_SCHEMA_TYPES:
        _append_signal(
            scores,
            evidence,
            "blog_post",
            4,
            f"article_schema_detected:{sorted(structured_types & ARTICLE_SCHEMA_TYPES)[0]}",
        )
    if structured_types & LISTING_SCHEMA_TYPES:
        _append_signal(
            scores,
            evidence,
            "directory",
            3,
            f"listing_schema_detected:{sorted(structured_types & LISTING_SCHEMA_TYPES)[0]}",
        )

    listicle_pattern = re.search(r"\b(top|best|mejores)\s+\d+\b", normalized_summary)
    if listicle_pattern:
        _append_signal(scores, evidence, "aggregator", 3, f"listicle_pattern:{listicle_pattern.group(0)}")

    business_identity_score = scores["direct_business"] + max(scores["agency"], scores["consultant"])
    non_target_score = max(scores[entity_type] for entity_type in NON_TARGET_ENTITY_TYPES)

    ranked_scores = sorted(
        ((entity_type, score) for entity_type, score in scores.items() if entity_type != "unknown"),
        key=lambda item: item[1],
        reverse=True,
    )
    top_entity_type, top_score = ranked_scores[0]
    runner_up_score = ranked_scores[1][1] if len(ranked_scores) > 1 else 0

    if top_score <= 0:
        if business_identity_score >= 3:
            top_entity_type = "direct_business"
            top_score = business_identity_score
            evidence["direct_business"].append("fallback_business_identity")
        else:
            top_entity_type = "unknown"
            top_score = 0

    editorial_evidence_present = bool(structured_types & ARTICLE_SCHEMA_TYPES) or any(token in path for token in BLOG_PATH_KEYWORDS)
    if (
        editorial_evidence_present
        and top_entity_type in {"directory", "aggregator", "media"}
        and scores["blog_post"] >= 4
    ):
        top_entity_type = "blog_post"
        top_score = scores["blog_post"]
        evidence["blog_post"].append("editorial_evidence_overrides_listing_signals")

    if top_entity_type in NON_TARGET_ENTITY_TYPES and business_identity_score >= top_score + 3:
        top_entity_type = "direct_business"
        top_score = scores["direct_business"]
        evidence["direct_business"].append("business_identity_overrides_non_target")

    margin = max(top_score - runner_up_score, 0)
    if top_entity_type == "unknown":
        entity_confidence = "low"
    elif top_score >= 7 and margin >= 2:
        entity_confidence = "high"
    elif top_score >= 4:
        entity_confidence = "medium"
    else:
        entity_confidence = "low"

    if top_entity_type in TARGET_ENTITY_TYPES:
        is_target_entity = True
        target_reason = f"target_entity_type:{top_entity_type}"
    elif top_entity_type in NON_TARGET_ENTITY_TYPES:
        is_target_entity = False
        target_reason = f"non_target_entity_type:{top_entity_type}"
    else:
        is_target_entity = business_identity_score >= 4 and non_target_score <= 2
        target_reason = (
            "fallback_business_identity_target"
            if is_target_entity
            else "fallback_unknown_entity_non_target"
        )

    evidence_payload = {
        "classifier_version": ENTITY_CLASSIFIER_VERSION,
        "entity_type_descriptions": ENTITY_TYPE_DESCRIPTIONS,
        "matched_rules": evidence.get(top_entity_type, [])[:8],
        "score_by_entity_type": {key: value for key, value in ranked_scores if value > 0},
        "business_identity_signals": {
            "has_contact_signal": has_contact_signal,
            "has_address_signal": has_address_signal,
            "has_service_page": has_service_page,
            "has_about_page": has_about_page,
            "has_contact_page": has_contact_page,
            "has_pricing_or_booking": has_pricing_or_booking,
            "structured_business_types": sorted(structured_types & BUSINESS_SCHEMA_TYPES),
        },
        "structured_types": sorted(structured_types),
        "target_reason": target_reason,
    }

    return {
        "entity_type_detected": top_entity_type,
        "entity_type_confidence": entity_confidence,
        "entity_type_evidence": evidence_payload,
        "is_target_entity": is_target_entity,
    }
