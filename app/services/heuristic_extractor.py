import logging
import re
import unicodedata
from typing import Any, Dict, List

from app.services.business_taxonomy import resolve_business_taxonomy
from app.services.commercial_insights import (
    build_legacy_pain_points,
    normalize_inferred_opportunities,
    normalize_observed_signals,
)

logger = logging.getLogger(__name__)

TECH_SIGNATURES = {
    "WordPress": ["wp-content", "wp-includes", 'generator" content="wordpress', "wordpress"],
    "WooCommerce": ["woocommerce"],
    "Shopify": ["cdn.shopify", "shopify.com", "shopify-section"],
    "Wix": ["wixstatic.com", "wix.com"],
    "Webflow": ["webflow", "data-wf-page"],
    "Elementor": ["elementor"],
    "React": ["data-reactroot", "_react_", "react-dom"],
    "Next.js": ["_next/static", "__next"],
    "Google Analytics": ["google-analytics.com/analytics.js", "gtag(", "googletagmanager.com/gtag"],
    "Google Tag Manager": ["googletagmanager.com/gtm.js", "gtm.start"],
    "Meta Pixel": ["fbevents.js", "fbq("],
    "HubSpot": ["js.hs-scripts.com", "hubspot"],
    "Stripe": ["js.stripe.com", "stripe.com/payments"],
}
LANGUAGE_HINTS = {
    "es": [" de ", " la ", " que ", " en ", " para ", " con ", " clinica ", " nosotros "],
    "en": [" the ", " and ", " for ", " with ", " services ", " about ", " contact "],
}
PRICING_KEYWORDS = ["precios", "pricing", "planes", "plan", "tarifas", "quote", "cotizacion"]
TESTIMONIAL_KEYWORDS = ["testimonios", "testimonial", "testimonials", "case study", "casos de exito", "clientes"]
PORTFOLIO_KEYWORDS = ["portfolio", "portafolio", "proyectos", "work", "casos", "portfolio"]
BOOKING_KEYWORDS = ["reserva", "reservas", "book", "booking", "agenda", "cita", "appointment", "schedule"]
PAIN_POINT_BOOKING_HINTS = ["reserva", "reservas", "booking", "agenda", "cita", "appointment"]
BUSINESS_SCHEMA_TYPES = {
    "accountingservice",
    "attorney",
    "beautysalon",
    "dentalclinic",
    "dentist",
    "employmentagency",
    "financialservice",
    "localbusiness",
    "medicalbusiness",
    "medicalclinic",
    "organization",
    "professionalservice",
    "realestateagent",
    "store",
}


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    return f" {ascii_only.lower()} "


def _normalize_context_list(raw_value: Any) -> list[str]:
    if not isinstance(raw_value, list):
        return []

    normalized_items: list[str] = []
    for item in raw_value:
        normalized = str(item).strip()
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in normalized_items:
            continue
        normalized_items.append(lowered)
    return normalized_items


def _contains_any(normalized_text: str, keywords: list[str]) -> bool:
    return any(_normalize_text(keyword).strip() in normalized_text for keyword in keywords if keyword)


def _extract_keywords(value: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]{3,}", _normalize_text(value))
    stopwords = {"para", "with", "from", "your", "this", "that", "los", "las", "del", "con"}
    unique_tokens: list[str] = []
    for token in tokens:
        if token in stopwords or token in unique_tokens:
            continue
        unique_tokens.append(token)
    return unique_tokens


def _contains_phrase(normalized_text: str, phrase: str) -> bool:
    return _normalize_text(phrase).strip() in normalized_text


def _build_content_profile(
    text_content: str,
    metadata: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    normalized_text = _normalize_text(
        " ".join(
            [
                str(text_content or ""),
                str(metadata.get("title") or ""),
                str(metadata.get("description") or ""),
                ((metadata.get("social_profile") or {}).get("bio") or ""),
            ]
        )
    )
    offer_signals: list[str] = list((metadata.get("social_profile") or {}).get("offer_signals", []))
    audience_signals: list[str] = list((metadata.get("social_profile") or {}).get("audience_signals", []))
    platform_ctas: list[str] = list((metadata.get("social_profile") or {}).get("platform_ctas", []))
    social_activity_signals: list[str] = list((metadata.get("social_profile") or {}).get("activity_signals", []))
    content_themes: list[str] = []
    budget_signal_matches: list[str] = []

    theme_candidates = {
        "video_content": ["reels", "shorts", "ugc", "video", "edicion", "edición"],
        "personal_brand": ["marca personal", "coach", "founder", "creator", "creador"],
        "ecommerce": ["ecommerce", "tienda online", "shop", "shopify"],
        "agency_services": ["agencia", "estudio", "marketing", "servicios"],
        "education_info": ["curso", "cursos", "mentoria", "mentoría", "infoproductos"],
    }
    for theme, keywords in theme_candidates.items():
        if any(_contains_phrase(normalized_text, keyword) for keyword in keywords):
            content_themes.append(theme)

    if any(_contains_phrase(normalized_text, keyword) for keyword in ["servicios", "trabajemos", "book", "agenda", "contacto", "dm"]):
        platform_ctas.append("commercial_cta_detected")
    if any(_contains_phrase(normalized_text, keyword) for keyword in ["curso", "programa", "coaching", "agencia", "edicion", "marketing", "shop"]):
        offer_signals.append("offer_detected")
    if any(_contains_phrase(normalized_text, keyword) for keyword in ["clientes", "marcas", "negocios", "founders", "coaches"]):
        audience_signals.append("buyer_audience_detected")
    if (metadata.get("social_profile") or {}).get("external_links"):
        platform_ctas.append("external_link_present")
    if metadata.get("whatsapp_url"):
        platform_ctas.append("whatsapp_cta_present")
    if metadata.get("emails") or metadata.get("phones"):
        platform_ctas.append("public_contact_present")

    for signal in _normalize_context_list(context.get("target_budget_signals")):
        if _contains_phrase(normalized_text, signal):
            budget_signal_matches.append(signal)
        elif "instagram" in signal and metadata.get("instagram_url"):
            budget_signal_matches.append(signal)
        elif "tiktok" in signal and metadata.get("tiktok_url"):
            budget_signal_matches.append(signal)
        elif "linktree" in signal and any("linktr.ee" in link for link in metadata.get("external_links", [])):
            budget_signal_matches.append(signal)

    return {
        "content_themes": sorted(set(content_themes)),
        "offer_signals": sorted(set(offer_signals)),
        "audience_signals": sorted(set(audience_signals)),
        "platform_ctas": sorted(set(platform_ctas)),
        "external_links": list((metadata.get("social_profile") or {}).get("external_links", []))[:5],
        "social_activity_signals": sorted(set(social_activity_signals)),
        "budget_signal_matches": sorted(set(budget_signal_matches)),
    }


def detect_technologies(html_content: str) -> List[str]:
    """
    Busca firmas básicas en HTML para deducir herramientas comunes
    sin depender de librerías externas pesadas.
    """
    html_lower = html_content.lower()
    tech_stack: list[str] = []

    for tech, sigs in TECH_SIGNATURES.items():
        if any(sig in html_lower for sig in sigs):
            tech_stack.append(tech)

    return tech_stack


def has_hiring_signals(text_content: str, metadata: Dict[str, Any]) -> bool:
    """Busca en texto y links internos señales de vacantes activas."""
    text_lower = text_content.lower()
    keywords = [
        "trabaja con nosotros",
        "unete al equipo",
        "vacantes",
        "careers",
        "we are hiring",
        "open positions",
    ]

    if any(keyword in text_lower for keyword in keywords):
        return True

    for link in metadata.get("internal_links", []):
        link_lower = link.lower()
        if any(keyword in link_lower for keyword in ["career", "trabajo", "empleo", "join-us"]):
            return True

    return False


def _detect_language_hint(text_content: str) -> str | None:
    normalized_text = _normalize_text(text_content)
    scores = {
        language: sum(normalized_text.count(token) for token in tokens)
        for language, tokens in LANGUAGE_HINTS.items()
    }
    detected_language, detected_score = max(scores.items(), key=lambda item: item[1])
    return detected_language if detected_score > 1 else None


def _infer_niche(text_content: str, metadata: Dict[str, Any], context: Dict[str, Any]) -> str | None:
    target_niche = str(context.get("target_niche") or "").strip()
    if not target_niche:
        return None

    searchable_text = _normalize_text(
        " ".join([str(text_content or ""), str(metadata.get("title") or ""), str(metadata.get("description") or "")])
    )
    normalized_niche = _normalize_text(target_niche).strip()
    if normalized_niche and normalized_niche in searchable_text:
        return target_niche

    niche_tokens = _extract_keywords(target_niche)
    if len(niche_tokens) >= 2:
        matches = sum(1 for token in niche_tokens if f" {token} " in searchable_text)
        if matches >= 2:
            return target_niche

    return None


def _component(normalized_score: float, evidence: list[str], details: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "normalized_score": round(max(0.0, min(normalized_score, 1.0)), 4),
        "evidence": evidence,
        "details": details,
    }


def _score_contact_availability(metadata: Dict[str, Any], content_profile: Dict[str, Any]) -> Dict[str, Any]:
    points = 0
    evidence: list[str] = []
    email_count = len(metadata.get("emails", []))
    phone_count = len(metadata.get("phones", []))
    social_count = len(metadata.get("social_links", []))
    has_contact_page = any("contact" in link.lower() or "contacto" in link.lower() for link in metadata.get("internal_links", []))
    form_detected = bool(metadata.get("form_detected"))

    if email_count:
        points += 4
        evidence.append("email_visible")
    if phone_count:
        points += 3
        evidence.append("phone_visible")
    if form_detected or has_contact_page:
        points += 2
        evidence.append("contact_path_detected")
    if social_count:
        points += 1
        evidence.append("social_presence_visible")
    if content_profile.get("platform_ctas"):
        points += 2
        evidence.append("social_cta_or_link_visible")

    return _component(
        points / 10,
        evidence,
        {
            "email_count": email_count,
            "phone_count": phone_count,
            "social_count": social_count,
            "form_detected": form_detected,
            "has_contact_page": has_contact_page,
            "social_cta_count": len(content_profile.get("platform_ctas", [])),
        },
    )


def _score_commercial_intent(
    normalized_text: str,
    *,
    has_active_ads: bool,
    hiring_signals: bool,
    content_profile: Dict[str, Any],
) -> Dict[str, Any]:
    points = 0
    evidence: list[str] = []
    has_pricing = _contains_any(normalized_text, PRICING_KEYWORDS)
    has_testimonials = _contains_any(normalized_text, TESTIMONIAL_KEYWORDS)
    has_portfolio = _contains_any(normalized_text, PORTFOLIO_KEYWORDS)

    if has_active_ads:
        points += 4
        evidence.append("ads_stack_detected")
    if hiring_signals:
        points += 3
        evidence.append("hiring_signal_detected")
    if has_pricing:
        points += 1
        evidence.append("pricing_keywords_visible")
    if has_testimonials:
        points += 1
        evidence.append("testimonials_visible")
    if has_portfolio:
        points += 1
        evidence.append("portfolio_or_case_studies_visible")
    if content_profile.get("offer_signals"):
        points += 2
        evidence.append("social_offer_signal_detected")
    if content_profile.get("budget_signal_matches"):
        points += 1
        evidence.append("budget_signal_match_detected")

    return _component(
        points / 10,
        evidence,
        {
            "has_active_ads": has_active_ads,
            "hiring_signals": hiring_signals,
            "has_pricing": has_pricing,
            "has_testimonials": has_testimonials,
            "has_portfolio": has_portfolio,
            "offer_signal_count": len(content_profile.get("offer_signals", [])),
            "budget_signal_match_count": len(content_profile.get("budget_signal_matches", [])),
        },
    )


def _score_digital_maturity(
    text_content: str,
    metadata: Dict[str, Any],
    inferred_tech_stack: list[str],
    content_profile: Dict[str, Any],
) -> Dict[str, Any]:
    points = 0
    evidence: list[str] = []
    clean_text_length = len(text_content.strip())
    internal_links = metadata.get("internal_links", [])
    key_page_count = len(internal_links)
    social_count = len(metadata.get("social_links", []))
    title_present = bool(metadata.get("title"))
    description_present = bool(metadata.get("description"))

    if title_present:
        points += 1
        evidence.append("title_present")
    if description_present:
        points += 1
        evidence.append("meta_description_present")
    if clean_text_length >= 300:
        points += 1
        evidence.append("minimum_content_detected")
    if clean_text_length >= 1200:
        points += 1
        evidence.append("substantial_content_detected")
    if key_page_count >= 1:
        points += 1
        evidence.append("key_internal_page_detected")
    if key_page_count >= 2:
        points += 1
        evidence.append("multiple_key_pages_detected")
    if inferred_tech_stack:
        points += 2
        evidence.append("tech_stack_detected")
    if len(inferred_tech_stack) >= 3:
        points += 1
        evidence.append("rich_tech_footprint_detected")
    if social_count:
        points += 1
        evidence.append("social_presence_detected")
    if any("about" in link.lower() or "nosotros" in link.lower() or "equipo" in link.lower() for link in internal_links):
        points += 1
        evidence.append("about_page_detected")
    if metadata.get("primary_identity_type") == "social_profile":
        if content_profile.get("social_activity_signals"):
            points += 2
            evidence.append("social_activity_detected")
        if content_profile.get("external_links"):
            points += 1
            evidence.append("external_link_in_profile")

    return _component(
        points / 10,
        evidence,
        {
            "clean_text_length": clean_text_length,
            "key_page_count": key_page_count,
            "social_count": social_count,
            "tech_stack_count": len(inferred_tech_stack),
            "title_present": title_present,
            "description_present": description_present,
            "social_activity_count": len(content_profile.get("social_activity_signals", [])),
        },
    )


def _score_business_identity(metadata: Dict[str, Any], content_profile: Dict[str, Any]) -> Dict[str, Any]:
    points = 0
    evidence: list[str] = []
    internal_links = metadata.get("internal_links", [])
    has_email = bool(metadata.get("emails"))
    has_phone = bool(metadata.get("phones"))
    has_form = bool(metadata.get("form_detected"))
    has_address = bool(metadata.get("addresses") or metadata.get("map_links"))
    has_service_page = any("service" in link.lower() or "servicio" in link.lower() for link in internal_links)
    has_about_page = any(
        any(keyword in link.lower() for keyword in ["about", "nosotros", "equipo"])
        for link in internal_links
    )
    has_contact_page = any("contact" in link.lower() or "contacto" in link.lower() for link in internal_links)
    has_pricing_or_booking = any(
        any(keyword in link.lower() for keyword in ["pricing", "precio", "precios", "book", "booking", "reserv", "agenda"])
        for link in internal_links
    ) or bool(metadata.get("booking_url") or metadata.get("pricing_page_url"))

    structured_business_types: set[str] = set()
    for node in metadata.get("structured_data", []):
        if not isinstance(node, dict):
            continue
        node_type = node.get("@type")
        values = node_type if isinstance(node_type, list) else [node_type]
        for value in values:
            if not value:
                continue
            normalized = _normalize_text(str(value)).strip().replace(" ", "")
            if normalized in BUSINESS_SCHEMA_TYPES:
                structured_business_types.add(normalized)

    if has_email or has_phone:
        points += 2
        evidence.append("owned_contact_channel_visible")
    if has_form and has_contact_page:
        points += 2
        evidence.append("contact_flow_visible")
    elif has_form or has_contact_page:
        points += 1
        evidence.append("contact_surface_visible")
    if has_address:
        points += 2
        evidence.append("owned_location_signal_visible")
    if has_service_page:
        points += 2
        evidence.append("service_navigation_visible")
    if has_about_page:
        points += 1
        evidence.append("about_identity_page_visible")
    if has_pricing_or_booking:
        points += 1
        evidence.append("conversion_path_visible")
    if structured_business_types:
        points += 2
        evidence.append("business_structured_data_visible")
    if metadata.get("primary_identity_type") == "social_profile":
        if (metadata.get("social_profile") or {}).get("handle"):
            points += 2
            evidence.append("social_profile_identity_visible")
        if content_profile.get("offer_signals"):
            points += 2
            evidence.append("social_offer_identity_visible")
        if content_profile.get("platform_ctas"):
            points += 1
            evidence.append("social_conversion_path_visible")

    return _component(
        points / 12,
        evidence,
        {
            "has_email": has_email,
            "has_phone": has_phone,
            "has_form": has_form,
            "has_address": has_address,
            "has_service_page": has_service_page,
            "has_about_page": has_about_page,
            "has_contact_page": has_contact_page,
            "has_pricing_or_booking": has_pricing_or_booking,
            "structured_business_types": sorted(structured_business_types),
            "primary_identity_type": metadata.get("primary_identity_type"),
        },
    )


def _score_context_fit(
    text_content: str,
    metadata: Dict[str, Any],
    context: Dict[str, Any],
    *,
    inferred_niche: str | None,
    content_profile: Dict[str, Any],
) -> Dict[str, Any]:
    points = 0
    evidence: list[str] = []
    searchable_text = _normalize_text(
        " ".join([str(text_content or ""), str(metadata.get("title") or ""), str(metadata.get("description") or "")])
    )
    target_niche = str(context.get("target_niche") or "").strip()
    target_location = str(context.get("target_location") or "").strip()
    target_language = str(context.get("target_language") or "").strip().lower()
    budget_signals = _normalize_context_list(context.get("target_budget_signals"))
    pain_points = _normalize_context_list(context.get("target_pain_points"))
    detected_language = _detect_language_hint(text_content)

    if inferred_niche:
        points += 5
        evidence.append("target_niche_match")
    elif target_niche:
        niche_tokens = _extract_keywords(target_niche)
        token_matches = sum(1 for token in niche_tokens if f" {token} " in searchable_text)
        if token_matches >= 2:
            points += 3
            evidence.append("partial_niche_match")

    if target_location and _normalize_text(target_location).strip() in searchable_text:
        points += 2
        evidence.append("target_location_match")

    if target_language and detected_language and target_language == detected_language:
        points += 1
        evidence.append("target_language_match")

    if budget_signals and any(_normalize_text(signal).strip() in searchable_text for signal in budget_signals):
        points += 1
        evidence.append("budget_signal_keyword_match")

    if pain_points and any(_normalize_text(signal).strip() in searchable_text for signal in pain_points):
        points += 1
        evidence.append("pain_point_keyword_match")
    if content_profile.get("offer_signals"):
        points += 1
        evidence.append("offer_signal_match")
    if content_profile.get("budget_signal_matches"):
        points += 1
        evidence.append("budget_signal_match")

    return _component(
        points / 10,
        evidence,
        {
            "target_niche": target_niche or None,
            "target_location": target_location or None,
            "target_language": target_language or None,
            "detected_language": detected_language,
            "budget_signal_matches": "budget_signal_keyword_match" in evidence,
            "pain_point_matches": "pain_point_keyword_match" in evidence,
            "content_profile_budget_matches": content_profile.get("budget_signal_matches", []),
        },
    )


def _score_stack_fit(context: Dict[str, Any], inferred_tech_stack: list[str]) -> Dict[str, Any]:
    points = 0
    evidence: list[str] = []
    normalized_user_technologies = {
        _normalize_text(str(item)).strip()
        for item in (context.get("user_technologies") or [])
        if str(item).strip()
    }
    normalized_stack = {_normalize_text(tech).strip() for tech in inferred_tech_stack}

    if inferred_tech_stack:
        points += 2
        evidence.append("stack_detected")

    stack_overlap = normalized_user_technologies & normalized_stack
    if stack_overlap:
        points += 5
        evidence.append("seller_stack_matches_prospect_stack")

    if any(tech in inferred_tech_stack for tech in ["WordPress", "WooCommerce", "Shopify", "Wix", "Webflow", "Elementor"]):
        points += 2
        evidence.append("cms_or_builder_detected")

    if any(tech in inferred_tech_stack for tech in ["Google Analytics", "Google Tag Manager", "Meta Pixel", "HubSpot", "Stripe"]):
        points += 1
        evidence.append("marketing_or_conversion_stack_detected")

    return _component(
        points / 10,
        evidence,
        {
            "inferred_tech_stack": inferred_tech_stack,
            "stack_overlap": sorted(stack_overlap),
        },
    )


def _derive_confidence_level(
    components: Dict[str, Dict[str, Any]],
    *,
    clean_text_length: int,
) -> str:
    evidence_count = sum(len(component["evidence"]) for component in components.values())
    strong_components = sum(1 for component in components.values() if component["normalized_score"] >= 0.6)

    if (
        (clean_text_length >= 800 and evidence_count >= 8 and strong_components >= 3)
        or (evidence_count >= 12 and strong_components >= 4)
    ):
        return "high"
    if (
        (clean_text_length >= 250 and evidence_count >= 4 and strong_components >= 1)
        or (evidence_count >= 8 and strong_components >= 2)
    ):
        return "medium"
    return "low"


def _derive_revenue_signal(
    *,
    heuristic_score: float,
    has_active_ads: bool,
    hiring_signals: bool,
    commercial_intent_score: float,
) -> str:
    if has_active_ads and (hiring_signals or heuristic_score >= 0.7 or commercial_intent_score >= 0.7):
        return "high"
    if has_active_ads or hiring_signals or heuristic_score >= 0.45 or commercial_intent_score >= 0.45:
        return "medium"
    return "low"


def _build_fit_summary(score: float, components: Dict[str, Dict[str, Any]]) -> str:
    labels = {
        "business_identity": "identidad empresarial",
        "contact_availability": "contactabilidad",
        "commercial_intent": "intencion comercial",
        "digital_maturity": "madurez digital",
        "context_fit": "ajuste con el contexto",
        "stack_fit": "ajuste de stack",
    }
    ordered_components = sorted(
        components.items(),
        key=lambda item: item[1]["normalized_score"],
        reverse=True,
    )
    strong_labels = [labels[name] for name, component in ordered_components if component["normalized_score"] >= 0.5][:2]

    if score >= 0.7:
        prefix = "Fit heuristico fuerte"
    elif score >= 0.45:
        prefix = "Fit heuristico moderado"
    else:
        prefix = "Fit heuristico debil"

    if strong_labels:
        return f"{prefix}; destacan {', '.join(strong_labels)}."
    return f"{prefix}; evidencia local limitada."


def _build_observed_signals(
    text_content: str,
    metadata: Dict[str, Any],
    context: Dict[str, Any],
    inferred_tech_stack: list[str],
    content_profile: Dict[str, Any],
) -> list[str]:
    observed_signals: list[str] = []
    normalized_text = _normalize_text(text_content)
    has_email = bool(metadata.get("emails"))
    has_phone = bool(metadata.get("phones"))
    has_form = bool(metadata.get("form_detected"))
    has_contact_page = any("contact" in link.lower() or "contacto" in link.lower() for link in metadata.get("internal_links", []))

    if not has_email and not has_phone and not has_form:
        observed_signals.append("No muestra contacto directo visible")
    elif not has_contact_page and not has_form:
        observed_signals.append("No se detecta pagina o formulario de contacto")

    if not metadata.get("description"):
        observed_signals.append("Meta description ausente")

    if not metadata.get("social_links"):
        observed_signals.append("Sin redes sociales visibles")
    if metadata.get("primary_identity_type") == "social_profile" and not content_profile.get("offer_signals"):
        observed_signals.append("Perfil social sin oferta comercial clara")
    if metadata.get("primary_identity_type") == "social_profile" and not content_profile.get("platform_ctas"):
        observed_signals.append("Perfil social sin CTA comercial visible")

    pain_point_hints = _normalize_context_list(context.get("target_pain_points"))
    wants_booking = any(any(hint in pain_point for hint in PAIN_POINT_BOOKING_HINTS) for pain_point in pain_point_hints)
    if wants_booking and not _contains_any(normalized_text, BOOKING_KEYWORDS):
        observed_signals.append("No muestra reservas online visibles")

    if len(text_content.strip()) >= 300 and not _contains_any(normalized_text, TESTIMONIAL_KEYWORDS + PORTFOLIO_KEYWORDS):
        observed_signals.append("No muestra prueba social visible")

    if not inferred_tech_stack:
        observed_signals.append("No se detectan herramientas visibles de analitica o marketing")

    return normalize_observed_signals(observed_signals)


def _build_inferred_opportunities(observed_signals: list[str]) -> list[str]:
    opportunities_map = {
        "No muestra contacto directo visible": "reforzar canales de contacto visibles",
        "No se detecta pagina o formulario de contacto": "habilitar una ruta de contacto mas clara",
        "Meta description ausente": "mejorar metadata publica para captacion organica",
        "Sin redes sociales visibles": "reforzar presencia social visible",
        "Perfil social sin oferta comercial clara": "aclarar oferta principal y servicios del perfil",
        "Perfil social sin CTA comercial visible": "sumar CTA comercial y link de conversion visible",
        "No muestra reservas online visibles": "incorporar reservas online visibles",
        "No muestra prueba social visible": "destacar testimonios o casos de exito",
        "No se detectan herramientas visibles de analitica o marketing": "mejorar instrumentacion digital visible",
    }
    raw_opportunities = [opportunities_map[signal] for signal in observed_signals if signal in opportunities_map]
    return normalize_inferred_opportunities(raw_opportunities)


def build_heuristic_trace(
    clean_text: str,
    html_raw: str,
    metadata: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    normalized_text = _normalize_text(clean_text)
    inferred_tech_stack = detect_technologies(html_raw)
    has_active_ads = "Meta Pixel" in inferred_tech_stack
    hiring_signals = has_hiring_signals(clean_text, metadata)
    inferred_niche = _infer_niche(clean_text, metadata, context)
    content_profile = _build_content_profile(clean_text, metadata, context)

    components = {
        "business_identity": _score_business_identity(metadata, content_profile),
        "contact_availability": _score_contact_availability(metadata, content_profile),
        "commercial_intent": _score_commercial_intent(
            normalized_text,
            has_active_ads=has_active_ads,
            hiring_signals=hiring_signals,
            content_profile=content_profile,
        ),
        "digital_maturity": _score_digital_maturity(clean_text, metadata, inferred_tech_stack, content_profile),
        "context_fit": _score_context_fit(
            clean_text,
            metadata,
            context,
            inferred_niche=inferred_niche,
            content_profile=content_profile,
        ),
        "stack_fit": _score_stack_fit(context, inferred_tech_stack),
    }
    component_weights = {
        "business_identity": 0.30,
        "contact_availability": 0.22,
        "commercial_intent": 0.18,
        "digital_maturity": 0.15,
        "context_fit": 0.10,
        "stack_fit": 0.05,
    }
    heuristic_score = round(
        sum(components[name]["normalized_score"] * weight for name, weight in component_weights.items()),
        4,
    )
    confidence_level = _derive_confidence_level(components, clean_text_length=len(clean_text.strip()))
    estimated_revenue_signal = _derive_revenue_signal(
        heuristic_score=heuristic_score,
        has_active_ads=has_active_ads,
        hiring_signals=hiring_signals,
        commercial_intent_score=components["commercial_intent"]["normalized_score"],
    )
    taxonomy_data = resolve_business_taxonomy(
        clean_text=clean_text,
        metadata=metadata,
        entity_type_detected="direct_business",
        inferred_niche=inferred_niche,
        target_niche=context.get("target_niche"),
    )
    inferred_niche = taxonomy_data["inferred_niche"]
    fit_summary = _build_fit_summary(heuristic_score, components)
    observed_signals = _build_observed_signals(clean_text, metadata, context, inferred_tech_stack, content_profile)
    inferred_opportunities = _build_inferred_opportunities(observed_signals)
    legacy_pain_points = build_legacy_pain_points(inferred_opportunities=inferred_opportunities)

    return {
        "score": heuristic_score,
        "confidence_level": confidence_level,
        "estimated_revenue_signal": estimated_revenue_signal,
        "has_active_ads": has_active_ads,
        "hiring_signals": hiring_signals,
        "inferred_niche": inferred_niche,
        "taxonomy_top_level": taxonomy_data["taxonomy_top_level"],
        "taxonomy_business_type": taxonomy_data["taxonomy_business_type"],
        "display_category": taxonomy_data["display_category"],
        "taxonomy_evidence": taxonomy_data["taxonomy_evidence"],
        "inferred_tech_stack": inferred_tech_stack,
        "fit_summary": fit_summary,
        "observed_signals": observed_signals,
        "inferred_opportunities": inferred_opportunities,
        "pain_points_detected": legacy_pain_points,
        "heuristic_trace": {
            "baseline_score": heuristic_score,
            "component_weights": component_weights,
            "component_scores": {
                name: component["normalized_score"]
                for name, component in components.items()
            },
            "signals": {
                name: component["evidence"]
                for name, component in components.items()
            },
            "details": {
                name: component["details"]
                for name, component in components.items()
            },
            "detected_language": _detect_language_hint(clean_text),
            "fit_summary": fit_summary,
            "content_profile": content_profile,
        },
    }


async def extract_business_entity_heuristic(
    clean_text: str,
    html_raw: str,
    metadata: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Extrae una evaluacion local del prospecto sin consumir APIs externas.
    """
    logger.info("Procesando extraccion heuristica offline.")

    heuristic_trace = build_heuristic_trace(clean_text, html_raw, metadata, context)
    inferred_niche = heuristic_trace["inferred_niche"]

    return {
        "company_name": (
            ((metadata.get("social_profile") or {}).get("display_name"))
            or str(metadata.get("title") or "").split("|")[0].strip()
        ),
        "category": heuristic_trace.get("display_category") or inferred_niche or "Desconocido",
        "location": metadata.get("addresses", [None])[0] if metadata.get("addresses") else None,
        "description": str(metadata.get("description") or "Sin descripcion META encontrada."),
        "inferred_tech_stack": heuristic_trace["inferred_tech_stack"],
        "inferred_niche": inferred_niche,
        "taxonomy_top_level": heuristic_trace.get("taxonomy_top_level"),
        "taxonomy_business_type": heuristic_trace.get("taxonomy_business_type"),
        "hiring_signals": heuristic_trace["hiring_signals"],
        "estimated_revenue_signal": heuristic_trace["estimated_revenue_signal"],
        "has_active_ads": heuristic_trace["has_active_ads"],
        "score": heuristic_trace["score"],
        "confidence_level": heuristic_trace["confidence_level"],
        "fit_summary": heuristic_trace["fit_summary"],
        "observed_signals": heuristic_trace["observed_signals"],
        "inferred_opportunities": heuristic_trace["inferred_opportunities"],
        "heuristic_trace": heuristic_trace["heuristic_trace"],
        "generic_attributes": {
            "evaluation_method": "Heuristic Code (No LLM)",
            "observed_signals": heuristic_trace["observed_signals"],
            "inferred_opportunities": heuristic_trace["inferred_opportunities"],
            "pain_points_detected": heuristic_trace["pain_points_detected"],
            "content_profile": heuristic_trace["heuristic_trace"].get("content_profile"),
            "budget_signal_matches": heuristic_trace["heuristic_trace"].get("content_profile", {}).get("budget_signal_matches", []),
            "taxonomy_top_level": heuristic_trace.get("taxonomy_top_level"),
            "taxonomy_business_type": heuristic_trace.get("taxonomy_business_type"),
            "taxonomy_evidence": heuristic_trace.get("taxonomy_evidence", []),
            "heuristic_score_breakdown": heuristic_trace["heuristic_trace"]["component_scores"],
            "heuristic_signals": heuristic_trace["heuristic_trace"]["signals"],
        },
    }
