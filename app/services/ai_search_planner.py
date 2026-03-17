import json
import logging
import re
import unicodedata
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Dict, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.services.ai_extractor import (
    _build_buyer_persona,
    _build_deepseek_client,
    _get_deepseek_api_key,
)
from app.services.discovery import GLOBAL_LOCATION_TOKENS, LOCATION_ALIAS_RULES

logger = logging.getLogger(__name__)

PlannerMode = Literal["initial", "refinement"]
PlannerProfileKey = Literal["generic_business", "creator_coach", "ecommerce_content"]
MULTI_LOCATION_SPLIT_PATTERN = re.compile(r"\s*(?:/|,|\||;)\s*")
CREATOR_COACH_HINTS = (
    "coach",
    "coaches",
    "coaching",
    "marca personal",
    "marcas personales",
    "personal brand",
    "mentor",
    "mentoria",
    "mentoría",
    "creator",
    "creador",
)
ECOMMERCE_HINTS = (
    "ecommerce",
    "e-commerce",
    "tienda online",
    "shopify",
    "dropshipping",
    "online store",
    "product brand",
    "d2c",
    "direct to consumer",
    "shop",
    "store",
)
ECOMMERCE_BLOCKED_QUERY_HINTS = (
    "site:*.com",
    "site:myshopify.com",
    "site:shopify.com",
    "help.shopify.com",
    "accounts.shopify.com",
    "inurl:collections",
    "inurl:products",
    "\"active on instagram\"",
    "\"tiktok shop\"",
)
_PLANNER_CACHE: dict[str, Dict[str, Any]] = {}


@dataclass(frozen=True)
class SearchPlannerProfile:
    key: PlannerProfileKey
    label: str
    target_description: str
    priority_signals: tuple[str, ...]
    exclusion_focus: tuple[str, ...]
    default_target_entity_hints: tuple[str, ...]
    default_exclusion_entity_hints: tuple[str, ...]


class AISearchPlanPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    optimal_dork_queries: list[str] = Field(default_factory=list)
    dynamic_negative_terms: list[str] = Field(default_factory=list)
    target_entity_hints: list[str] = Field(default_factory=list)
    exclusion_entity_hints: list[str] = Field(default_factory=list)
    refinement_goal: str | None = None
    planner_profile: str | None = None
    geo_scope: str | None = None
    search_strategy: str | None = None
    subsegment_hypotheses: list[dict[str, Any]] = Field(default_factory=list)
    segment_hypotheses: list[dict[str, Any]] = Field(default_factory=list)
    dynamic_priority_signals: list[str] = Field(default_factory=list)
    dynamic_negative_signals: list[str] = Field(default_factory=list)
    query_families: list[dict[str, Any]] = Field(default_factory=list)
    platform_priority: list[str] = Field(default_factory=list)
    commercial_validation_signals: list[str] = Field(default_factory=list)
    initial_wave: list[dict[str, Any] | str] = Field(default_factory=list)
    query_actions: list[dict[str, Any]] = Field(default_factory=list)
    segment_action_plan: list[dict[str, Any]] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
    refinement_hypotheses: list[dict[str, Any]] = Field(default_factory=list)
    segment_rotation_rules: list[str] = Field(default_factory=list)
    next_segments_to_try: list[str] = Field(default_factory=list)
    segments_to_pause: list[str] = Field(default_factory=list)
    candidate_evaluation_policy: dict[str, Any] = Field(default_factory=dict)


def _normalize_space(value: str | None) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_ascii(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", _normalize_space(value))
    return normalized.encode("ascii", "ignore").decode("ascii").lower()


_GLOBAL_LOCATION_ALIASES = {_normalize_ascii(token) for token in GLOBAL_LOCATION_TOKENS}


PLANNER_PROFILES: dict[PlannerProfileKey, SearchPlannerProfile] = {
    "generic_business": SearchPlannerProfile(
        key="generic_business",
        label="general_business",
        target_description="negocios finales con oferta comercial clara y canal de contacto usable",
        priority_signals=(
            "sitio oficial",
            "pagina de contacto",
            "pagina de servicios o productos",
            "CTA comercial visible",
        ),
        exclusion_focus=(
            "blogs",
            "medios",
            "directorios",
            "listados",
            "software",
            "assets",
            "paginas informativas",
        ),
        default_target_entity_hints=("negocio final", "sitio oficial", "contacto comercial"),
        default_exclusion_entity_hints=("blog", "directorio", "medio", "software"),
    ),
    "creator_coach": SearchPlannerProfile(
        key="creator_coach",
        label="creator_coach",
        target_description="coaches finales, marcas personales finales y negocios finales con oferta propia",
        priority_signals=(
            "instagram o tiktok activos",
            "link in bio o linktree",
            "programas o mentorias",
            "pagina de contacto",
            "CTA comercial visible",
        ),
        exclusion_focus=(
            "escuelas",
            "directorios",
            "listados",
            "blogs",
            "medios",
            "assets",
            "tools",
        ),
        default_target_entity_hints=("coach final", "marca personal", "contacto comercial"),
        default_exclusion_entity_hints=("escuela", "directorio", "listado de coaches"),
    ),
    "ecommerce_content": SearchPlannerProfile(
        key="ecommerce_content",
        label="ecommerce_content",
        target_description="pequenas marcas ecommerce, tiendas online, negocios Shopify y pymes digitales que venden productos",
        priority_signals=(
            "sitio oficial o storefront activo",
            "paginas de producto o coleccion",
            "shopify o checkout visible",
            "instagram o tiktok activos",
            "branding, ads o landing comercial",
        ),
        exclusion_focus=(
            "agencias",
            "freelancers",
            "apps",
            "themes",
            "tutoriales",
            "marketplaces",
            "directorios",
            "proveedores o mayoristas",
        ),
        default_target_entity_hints=("ecommerce activo", "shopify store", "marca de producto"),
        default_exclusion_entity_hints=("agencia", "theme", "app", "tutorial", "supplier", "marketplace"),
    ),
}

DEFAULT_PLATFORM_PRIORITY = ("instagram", "tiktok", "website")
DEFAULT_QUICK_AI_INPUTS = (
    "url",
    "domain",
    "title",
    "snippet",
    "result_kind",
    "platform",
    "handle",
    "meta_title",
    "meta_description",
    "social_bio",
    "link_in_bio_present",
    "cta_tokens",
)
DEFAULT_HARD_REJECT_REASONS = (
    "blocked_domain",
    "blocked_binary_document",
    "excluded_social_post",
    "excluded_reference_page",
    "excluded_auth_or_help_page",
    "excluded_as_article",
    "excluded_large_enterprise",
    "excluded_as_product_page",
)
DEFAULT_BORDERLINE_RESCUE_RULES = (
    "canonical_social_profile",
    "canonical_handle_detected",
    "brand_title_overlap",
    "commercial_snippet_hint",
    "brandable_domain_match",
    "short_branded_title",
)

PROFILE_SEGMENT_CATALOGS: dict[PlannerProfileKey, dict[str, tuple[dict[str, Any], ...]]] = {
    "generic_business": {
        "default": (
            {
                "segment_id": "local_service_business",
                "label": "local service business",
                "buyer_type": "business_owner",
                "why_relevant": "Negocio final con necesidad comercial visible y decision rapida.",
                "product_or_offer_examples": ["servicios profesionales", "servicios recurrentes"],
                "social_patterns": ["before and after", "testimonials", "book now"],
                "website_patterns": ["contact", "services", "about"],
                "negative_signals": ["directory", "news", "association"],
                "seed_terms": ["local business", "service business"],
            },
            {
                "segment_id": "digital_small_business",
                "label": "digital small business",
                "buyer_type": "founder_led_business",
                "why_relevant": "Pymes digitales con venta activa y necesidad de contenido.",
                "product_or_offer_examples": ["digital studio", "online service"],
                "social_patterns": ["instagram", "tiktok", "link in bio"],
                "website_patterns": ["contact", "services", "pricing"],
                "negative_signals": ["blog", "directory", "jobs"],
                "seed_terms": ["small business", "digital business"],
            },
        ),
    },
    "creator_coach": {
        "es": (
            {
                "segment_id": "coach_negocios",
                "label": "coach de negocios",
                "buyer_type": "coach",
                "why_relevant": "Oferta clara, CTA comercial y necesidad constante de contenido.",
                "product_or_offer_examples": ["mentoria", "programa", "asesoria premium"],
                "social_patterns": ["DM", "link in bio", "testimonios", "aplica"],
                "website_patterns": ["book call", "programa", "aplicar"],
                "negative_signals": ["escuela", "certificacion", "directorio"],
                "seed_terms": ["coach de negocios", "coach para emprendedores"],
            },
            {
                "segment_id": "coach_vida",
                "label": "coach de vida",
                "buyer_type": "coach",
                "why_relevant": "Marca personal intensiva en reels y prueba social.",
                "product_or_offer_examples": ["sesiones", "programa de transformacion"],
                "social_patterns": ["reels", "link in bio", "DM"],
                "website_patterns": ["contacto", "programa", "agendar"],
                "negative_signals": ["frases", "blog", "escuela"],
                "seed_terms": ["coach de vida", "life coach"],
            },
            {
                "segment_id": "coach_finanzas",
                "label": "coach de finanzas",
                "buyer_type": "coach",
                "why_relevant": "Suele vender mentoring, comunidad o consultoria grupal.",
                "product_or_offer_examples": ["mentoria financiera", "programa premium"],
                "social_patterns": ["book call", "DM", "casos de exito"],
                "website_patterns": ["aplica", "mentoria", "servicios"],
                "negative_signals": ["medio", "news", "blog"],
                "seed_terms": ["coach financiero", "coach de finanzas"],
            },
            {
                "segment_id": "coach_fitness",
                "label": "coach fitness",
                "buyer_type": "coach",
                "why_relevant": "Contenido corto, frecuencia alta y CTA a llamada o DM.",
                "product_or_offer_examples": ["coaching 1:1", "programa online"],
                "social_patterns": ["transformacion", "DM", "link in bio"],
                "website_patterns": ["programa", "agendar", "contacto"],
                "negative_signals": ["gimnasio", "directorio", "blog"],
                "seed_terms": ["coach fitness", "coach de fitness"],
            },
            {
                "segment_id": "coach_mindset",
                "label": "coach de mindset",
                "buyer_type": "coach",
                "why_relevant": "Marca personal con oferta de mentoring y contenido diario.",
                "product_or_offer_examples": ["mentoria", "comunidad", "sesiones"],
                "social_patterns": ["reels", "link in bio", "aplica"],
                "website_patterns": ["book call", "programa", "about"],
                "negative_signals": ["quotes", "frases", "blog"],
                "seed_terms": ["coach mindset", "mindset coach"],
            },
            {
                "segment_id": "creator_mentor",
                "label": "creator con mentoring",
                "buyer_type": "personal_brand",
                "why_relevant": "Creador con oferta propia y embudo social-first.",
                "product_or_offer_examples": ["mentoring", "curso", "programa"],
                "social_patterns": ["link in bio", "DM", "masterclass"],
                "website_patterns": ["programa", "apply", "contacto"],
                "negative_signals": ["agencia", "template", "blog"],
                "seed_terms": ["marca personal", "creador con mentoring"],
            },
        ),
        "default": (
            {
                "segment_id": "business_coach",
                "label": "business coach",
                "buyer_type": "coach",
                "why_relevant": "Offer-led coach with visible CTA and outreach potential.",
                "product_or_offer_examples": ["mentoring", "group program", "strategy call"],
                "social_patterns": ["DM", "link in bio", "book call"],
                "website_patterns": ["book call", "program", "apply"],
                "negative_signals": ["directory", "academy", "certification"],
                "seed_terms": ["business coach", "coach for founders"],
            },
            {
                "segment_id": "life_coach",
                "label": "life coach",
                "buyer_type": "coach",
                "why_relevant": "High social posting cadence and direct-response profile.",
                "product_or_offer_examples": ["1:1 coaching", "transformational program"],
                "social_patterns": ["reels", "DM", "link in bio"],
                "website_patterns": ["book call", "program", "about"],
                "negative_signals": ["quotes", "directory", "blog"],
                "seed_terms": ["life coach", "mindset coach"],
            },
            {
                "segment_id": "finance_coach",
                "label": "finance coach",
                "buyer_type": "coach",
                "why_relevant": "Sells mentoring, education, community or advisory.",
                "product_or_offer_examples": ["finance mentoring", "money program"],
                "social_patterns": ["book call", "case study", "link in bio"],
                "website_patterns": ["apply", "services", "program"],
                "negative_signals": ["news", "media", "directory"],
                "seed_terms": ["finance coach", "money coach"],
            },
            {
                "segment_id": "fitness_coach",
                "label": "fitness coach",
                "buyer_type": "coach",
                "why_relevant": "Usually social-first and CTA-heavy.",
                "product_or_offer_examples": ["online coaching", "fitness program"],
                "social_patterns": ["transformation", "DM", "link in bio"],
                "website_patterns": ["program", "book call", "contact"],
                "negative_signals": ["gym", "directory", "blog"],
                "seed_terms": ["fitness coach", "online fitness coach"],
            },
            {
                "segment_id": "mindset_coach",
                "label": "mindset coach",
                "buyer_type": "coach",
                "why_relevant": "Personal brand with recurring content and conversion CTA.",
                "product_or_offer_examples": ["mentorship", "community", "private coaching"],
                "social_patterns": ["reels", "apply", "link in bio"],
                "website_patterns": ["book call", "program", "contact"],
                "negative_signals": ["quotes", "blog", "academy"],
                "seed_terms": ["mindset coach", "personal growth coach"],
            },
            {
                "segment_id": "creator_mentor",
                "label": "creator selling mentoring",
                "buyer_type": "personal_brand",
                "why_relevant": "Creator-led info business with social-first funnel.",
                "product_or_offer_examples": ["mentoring", "course", "mastermind"],
                "social_patterns": ["link in bio", "DM", "masterclass"],
                "website_patterns": ["program", "apply", "contact"],
                "negative_signals": ["agency", "template", "blog"],
                "seed_terms": ["personal brand mentor", "creator mentor"],
            },
        ),
    },
    "ecommerce_content": {
        "default": (
            {
                "segment_id": "small_skincare_brand",
                "label": "small skincare brand",
                "buyer_type": "product_brand",
                "why_relevant": "Alta frecuencia de UGC, lanzamientos y necesidad de creatives.",
                "product_or_offer_examples": ["serums", "bundles", "skin care kits"],
                "social_patterns": ["ugc", "routine", "shop now", "before and after"],
                "website_patterns": ["shop", "products", "bundles"],
                "negative_signals": ["wholesale", "supplier", "private label"],
                "seed_terms": ["skincare brand", "beauty brand"],
            },
            {
                "segment_id": "fashion_boutique",
                "label": "fashion boutique",
                "buyer_type": "product_brand",
                "why_relevant": "Contenido corto, drops y catalogo visual continuo.",
                "product_or_offer_examples": ["new drop", "tops", "dresses"],
                "social_patterns": ["new drop", "shop now", "try on", "reels"],
                "website_patterns": ["shop", "collections", "new arrivals"],
                "negative_signals": ["wholesale", "marketplace", "supplier"],
                "seed_terms": ["fashion boutique", "clothing brand"],
            },
            {
                "segment_id": "jewelry_accessories_brand",
                "label": "jewelry accessories brand",
                "buyer_type": "product_brand",
                "why_relevant": "Marca visual con anuncios, catalogo y contenido de producto.",
                "product_or_offer_examples": ["necklaces", "earrings", "rings"],
                "social_patterns": ["product video", "ugc", "shop now"],
                "website_patterns": ["shop", "products", "gift guide"],
                "negative_signals": ["wholesale", "supplier", "marketplace"],
                "seed_terms": ["jewelry brand", "accessories brand"],
            },
            {
                "segment_id": "home_decor_store",
                "label": "home decor store",
                "buyer_type": "product_brand",
                "why_relevant": "Necesita contenido aspiracional y de producto con frecuencia.",
                "product_or_offer_examples": ["home decor", "wall art", "kitchen accessories"],
                "social_patterns": ["shop now", "product video", "ugc"],
                "website_patterns": ["shop", "collections", "best sellers"],
                "negative_signals": ["wholesale", "marketplace", "supplier"],
                "seed_terms": ["home decor store", "home decor brand"],
            },
            {
                "segment_id": "pet_brand",
                "label": "pet brand",
                "buyer_type": "product_brand",
                "why_relevant": "Alta capacidad de social-first y demos visuales.",
                "product_or_offer_examples": ["pet accessories", "dog products", "pet toys"],
                "social_patterns": ["product video", "ugc", "shop now"],
                "website_patterns": ["shop", "products", "best sellers"],
                "negative_signals": ["wholesale", "supplier", "directory"],
                "seed_terms": ["pet brand", "pet store"],
            },
            {
                "segment_id": "supplement_wellness_brand",
                "label": "supplement wellness brand",
                "buyer_type": "product_brand",
                "why_relevant": "Depende de creatives, proof and conversion content.",
                "product_or_offer_examples": ["supplements", "wellness products", "vitamins"],
                "social_patterns": ["ugc", "shop now", "product video"],
                "website_patterns": ["shop", "products", "subscribe"],
                "negative_signals": ["marketplace", "wholesale", "supplier"],
                "seed_terms": ["supplement brand", "wellness brand"],
            },
            {
                "segment_id": "gift_gadget_brand",
                "label": "gift gadget brand",
                "buyer_type": "product_brand",
                "why_relevant": "Vive de demos cortas, hooks y anuncios.",
                "product_or_offer_examples": ["gift brand", "gadgets", "viral products"],
                "social_patterns": ["viral product", "shop now", "product demo"],
                "website_patterns": ["shop", "products", "best sellers"],
                "negative_signals": ["supplier", "aliexpress", "wholesale"],
                "seed_terms": ["gift brand", "gadget brand"],
            },
        ),
    },
}


def _build_location_alias_index() -> dict[str, str]:
    alias_index: dict[str, str] = {}
    for canonical_location, aliases in LOCATION_ALIAS_RULES.items():
        for alias in (canonical_location, *aliases):
            normalized_alias = _normalize_ascii(alias)
            if normalized_alias:
                alias_index[normalized_alias] = canonical_location
    return alias_index


LOCATION_ALIAS_INDEX = _build_location_alias_index()


def _collect_profile_context_blob(job_context: Dict[str, Any]) -> str:
    context_parts: list[str] = [
        str(job_context.get("search_query") or ""),
        str(job_context.get("target_niche") or ""),
        str(job_context.get("user_target_offer_focus") or ""),
        str(job_context.get("user_profession") or ""),
        str(job_context.get("target_company_size") or ""),
    ]
    context_parts.extend(str(item) for item in (job_context.get("target_budget_signals") or []))
    context_parts.extend(str(item) for item in (job_context.get("target_pain_points") or []))
    return _normalize_ascii(" ".join(context_parts))


def _count_profile_hint_matches(searchable_blob: str, hints: tuple[str, ...]) -> int:
    return sum(1 for hint in hints if _normalize_ascii(hint) in searchable_blob)


def _resolve_planner_profile(job_context: Dict[str, Any]) -> SearchPlannerProfile:
    explicit_profile = _normalize_ascii(str(job_context.get("planner_profile") or job_context.get("search_mode") or ""))
    explicit_aliases = {
        "generic": "generic_business",
        "generic_business": "generic_business",
        "coach": "creator_coach",
        "creator": "creator_coach",
        "creator_coach": "creator_coach",
        "coach_creator": "creator_coach",
        "ecommerce": "ecommerce_content",
        "ecommerce_content": "ecommerce_content",
        "shopify": "ecommerce_content",
    }
    selected_key = explicit_aliases.get(explicit_profile)
    if selected_key:
        return PLANNER_PROFILES[selected_key]  # type: ignore[index]

    searchable_blob = _collect_profile_context_blob(job_context)
    creator_score = _count_profile_hint_matches(searchable_blob, CREATOR_COACH_HINTS)
    ecommerce_score = _count_profile_hint_matches(searchable_blob, ECOMMERCE_HINTS)

    if ecommerce_score > creator_score and ecommerce_score >= 1:
        return PLANNER_PROFILES["ecommerce_content"]
    if creator_score >= 1:
        return PLANNER_PROFILES["creator_coach"]
    if ecommerce_score >= 1:
        return PLANNER_PROFILES["ecommerce_content"]
    return PLANNER_PROFILES["generic_business"]


def _split_location_candidates(raw_location: str | None) -> list[str]:
    normalized_location = _normalize_space(raw_location)
    if not normalized_location:
        return []
    if _normalize_ascii(normalized_location) in _GLOBAL_LOCATION_ALIASES:
        return []
    if not MULTI_LOCATION_SPLIT_PATTERN.search(normalized_location):
        return [normalized_location]
    return [
        candidate
        for candidate in (_normalize_space(part) for part in MULTI_LOCATION_SPLIT_PATTERN.split(normalized_location))
        if candidate
    ]


def _resolve_geo_scope(job_context: Dict[str, Any]) -> dict[str, Any] | None:
    location_candidates = _split_location_candidates(job_context.get("target_location"))
    if len(location_candidates) != 1:
        return None

    raw_location = location_candidates[0]
    canonical_location = LOCATION_ALIAS_INDEX.get(_normalize_ascii(raw_location), raw_location)
    aliases = LOCATION_ALIAS_RULES.get(canonical_location, (raw_location,))
    normalized_aliases = tuple(
        normalized_alias
        for normalized_alias in (_normalize_ascii(alias) for alias in (canonical_location, *aliases))
        if normalized_alias
    )
    return {
        "label": canonical_location,
        "canonical": canonical_location,
        "aliases": normalized_aliases,
    }


def _dedupe_strings(values: list[str] | None) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        cleaned = _normalize_space(value)
        lowered = cleaned.lower()
        if not cleaned or lowered in seen:
            continue
        deduped.append(cleaned)
        seen.add(lowered)
    return deduped


def _normalize_platforms(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        cleaned = _normalize_ascii(value)
        if not cleaned or cleaned in seen:
            continue
        normalized.append(cleaned)
        seen.add(cleaned)
    return normalized


def _normalize_candidate_evaluation_policy(raw_value: Any) -> dict[str, Any]:
    if not isinstance(raw_value, dict):
        return {}

    identity_priority = _normalize_ascii(str(raw_value.get("identity_priority") or ""))
    if identity_priority not in {"social_first", "hybrid"}:
        identity_priority = ""

    contact_requirement = _normalize_ascii(str(raw_value.get("contact_requirement") or ""))
    if contact_requirement not in {"soft"}:
        contact_requirement = ""

    quick_ai_stage = _normalize_ascii(str(raw_value.get("quick_ai_stage") or ""))
    if quick_ai_stage not in {"hybrid"}:
        quick_ai_stage = ""

    return {
        "identity_priority": identity_priority or None,
        "contact_requirement": contact_requirement or None,
        "quick_ai_stage": quick_ai_stage or None,
        "quick_ai_inputs": _normalize_platforms(raw_value.get("quick_ai_inputs")),
        "hard_reject_reasons": _dedupe_strings(raw_value.get("hard_reject_reasons")),
        "borderline_rescue_rules": _dedupe_strings(raw_value.get("borderline_rescue_rules")),
    }


def _enforce_geo_policy(
    queries: list[str],
    *,
    geo_scope: dict[str, Any] | None,
) -> list[str]:
    if not geo_scope:
        return _dedupe_strings(queries)

    filtered: list[str] = []
    for query in _dedupe_strings(queries):
        normalized_query = _normalize_ascii(query)
        has_conflicting_location = False
        for canonical_location, aliases in LOCATION_ALIAS_RULES.items():
            if canonical_location == geo_scope["canonical"]:
                continue
            normalized_candidates = [_normalize_ascii(canonical_location), *(_normalize_ascii(alias) for alias in aliases)]
            if any(candidate and candidate in normalized_query for candidate in normalized_candidates):
                has_conflicting_location = True
                break
        if has_conflicting_location:
            continue
        if not any(alias in normalized_query for alias in geo_scope["aliases"]):
            query = _normalize_space(f"{query} {geo_scope['label']}")
        filtered.append(query)
    return _dedupe_strings(filtered)


def _normalize_negative_terms(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for value in _dedupe_strings(values):
        prefixed = value if value.startswith("-") else f"-{value}"
        normalized.append(prefixed)
    return normalized


def _segment_language_key(job_context: Dict[str, Any]) -> str:
    language = _normalize_ascii(str(job_context.get("target_language") or ""))
    return language if language in {"es"} else "default"


def _default_segment_catalog(
    profile: SearchPlannerProfile,
    job_context: Dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    profile_catalog = PROFILE_SEGMENT_CATALOGS.get(profile.key, {})
    return profile_catalog.get(_segment_language_key(job_context)) or profile_catalog.get("default", ())


def _extract_segment_performance_map(iteration_memory: Dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    raw_map = (iteration_memory or {}).get("segment_performance")
    return raw_map if isinstance(raw_map, dict) else {}


def _score_segment_priority(
    segment: dict[str, Any],
    *,
    iteration_memory: Dict[str, Any] | None,
) -> tuple[int, int, int, int, float]:
    performance_map = _extract_segment_performance_map(iteration_memory)
    segment_stats = performance_map.get(str(segment.get("segment_id") or ""), {})
    accepted = int(segment_stats.get("accepted") or 0)
    zero_result_queries = int(segment_stats.get("zero_result_queries") or 0)
    query_count = int(segment_stats.get("query_count") or 0)
    rejected = int(segment_stats.get("rejected") or 0)
    confidence = float(segment.get("confidence") or 0.0)
    return (-accepted, zero_result_queries, query_count, rejected, -confidence)


def _build_segment_hypotheses(
    profile: SearchPlannerProfile,
    job_context: Dict[str, Any],
    *,
    planner_segments: list[dict[str, Any]] | None,
    geo_scope: dict[str, Any] | None,
    iteration_memory: Dict[str, Any] | None,
) -> list[dict[str, Any]]:
    normalized_segments: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    paused_segments = {
        _normalize_ascii(segment_id)
        for segment_id in ((iteration_memory or {}).get("segments_to_pause") or [])
        if _normalize_ascii(segment_id)
    }

    for raw_segment in [*(planner_segments or []), *_default_segment_catalog(profile, job_context)]:
        if not isinstance(raw_segment, dict):
            continue
        segment_id = _normalize_space(str(raw_segment.get("segment_id") or ""))
        label = _normalize_space(str(raw_segment.get("label") or segment_id.replace("_", " ")))
        normalized_id = _normalize_ascii(segment_id or label.replace(" ", "_"))
        if not normalized_id or normalized_id in seen_ids or normalized_id in paused_segments:
            continue
        segment = {
            "segment_id": normalized_id,
            "label": label or normalized_id.replace("_", " "),
            "why_relevant": _normalize_space(raw_segment.get("why_relevant")),
            "buyer_type": _normalize_space(raw_segment.get("buyer_type")),
            "product_or_offer_examples": _dedupe_strings(raw_segment.get("product_or_offer_examples") or []),
            "social_patterns": _dedupe_strings(raw_segment.get("social_patterns") or []),
            "website_patterns": _dedupe_strings(raw_segment.get("website_patterns") or []),
            "geo_signals": _dedupe_strings(raw_segment.get("geo_signals") or ([geo_scope["label"]] if geo_scope else [])),
            "language_signals": _dedupe_strings(raw_segment.get("language_signals") or [str(job_context.get("target_language") or "")]),
            "negative_signals": _dedupe_strings(raw_segment.get("negative_signals") or []),
            "seed_terms": _dedupe_strings(raw_segment.get("seed_terms") or [label]),
            "confidence": max(0.1, min(float(raw_segment.get("confidence") or 0.72), 0.99)),
        }
        normalized_segments.append(segment)
        seen_ids.add(normalized_id)

    normalized_segments.sort(key=lambda item: _score_segment_priority(item, iteration_memory=iteration_memory))
    return normalized_segments[:8]


def _derive_dynamic_priority_signals(
    *,
    profile: SearchPlannerProfile,
    job_context: Dict[str, Any],
    segment_hypotheses: list[dict[str, Any]],
) -> list[str]:
    signals: list[str] = [*profile.priority_signals]
    signals.extend(str(item) for item in (job_context.get("target_budget_signals") or []))
    signals.extend(str(item) for item in (job_context.get("target_pain_points") or []))
    for segment in segment_hypotheses:
        signals.extend(segment.get("social_patterns") or [])
        signals.extend(segment.get("website_patterns") or [])
    return _dedupe_strings(signals)[:18]


def _derive_dynamic_negative_signals(
    *,
    profile: SearchPlannerProfile,
    segment_hypotheses: list[dict[str, Any]],
    iteration_memory: Dict[str, Any] | None,
) -> list[str]:
    negatives = [*profile.exclusion_focus]
    for segment in segment_hypotheses:
        negatives.extend(segment.get("negative_signals") or [])
    for sample in (iteration_memory or {}).get("false_positive_samples", []) or []:
        if not isinstance(sample, dict):
            continue
        title = _normalize_space(str(sample.get("title") or ""))
        domain = _normalize_space(str(sample.get("domain") or ""))
        if title:
            negatives.append(title)
        if domain:
            negatives.append(domain)
    return _dedupe_strings(negatives)[:16]


def _derive_platform_priority(
    profile: SearchPlannerProfile,
    job_context: Dict[str, Any],
    planner_platform_priority: list[str] | None,
) -> list[str]:
    explicit = _normalize_platforms(planner_platform_priority)
    if explicit:
        return explicit

    profession = _normalize_ascii(str(job_context.get("user_profession") or ""))
    social_first_roles = ("video", "editor", "community", "social", "designer", "creador")
    if profile.key in {"creator_coach", "ecommerce_content"} or any(token in profession for token in social_first_roles):
        return list(DEFAULT_PLATFORM_PRIORITY)
    return ["website", "instagram", "tiktok"]


def _build_candidate_evaluation_policy(
    *,
    profile: SearchPlannerProfile,
    job_context: Dict[str, Any],
    platform_priority: list[str],
    dynamic_priority_signals: list[str],
    planner_policy: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized_policy = _normalize_candidate_evaluation_policy(planner_policy)
    social_priority = profile.key in {"creator_coach", "ecommerce_content"} or any(
        token in _normalize_ascii(str(job_context.get("user_profession") or ""))
        for token in ("video", "editor", "community", "social", "designer", "creador")
    )
    identity_priority = normalized_policy.get("identity_priority") or ("social_first" if social_priority else "hybrid")
    quick_ai_inputs = normalized_policy.get("quick_ai_inputs") or list(DEFAULT_QUICK_AI_INPUTS)

    cta_tokens = [
        signal
        for signal in dynamic_priority_signals
        if any(token in _normalize_ascii(signal) for token in ("dm", "agenda", "book", "contact", "shop", "apply", "link"))
    ][:6]

    return {
        "identity_priority": identity_priority,
        "contact_requirement": normalized_policy.get("contact_requirement") or "soft",
        "quick_ai_stage": normalized_policy.get("quick_ai_stage") or "hybrid",
        "quick_ai_inputs": quick_ai_inputs,
        "hard_reject_reasons": normalized_policy.get("hard_reject_reasons") or list(DEFAULT_HARD_REJECT_REASONS),
        "borderline_rescue_rules": normalized_policy.get("borderline_rescue_rules") or list(DEFAULT_BORDERLINE_RESCUE_RULES),
        "platform_priority": platform_priority[:3],
        "cta_tokens": cta_tokens,
    }


def _build_query_families(
    *,
    segment_hypotheses: list[dict[str, Any]],
    platform_priority: list[str],
) -> list[dict[str, Any]]:
    query_families: list[dict[str, Any]] = []
    for priority_index, segment in enumerate(segment_hypotheses, start=1):
        query_families.extend(
            [
                {
                    "segment_id": segment["segment_id"],
                    "family": "social_profile_queries",
                    "platforms": platform_priority[:2],
                    "intent_terms": segment.get("seed_terms", [])[:3],
                    "commercial_hints": segment.get("social_patterns", [])[:3],
                    "priority": priority_index,
                },
                {
                    "segment_id": segment["segment_id"],
                    "family": "social_commercial_queries",
                    "platforms": platform_priority[:2],
                    "intent_terms": segment.get("seed_terms", [])[:2],
                    "commercial_hints": segment.get("social_patterns", [])[:4],
                    "priority": priority_index,
                },
                {
                    "segment_id": segment["segment_id"],
                    "family": "website_validation_queries",
                    "platforms": ["website"],
                    "intent_terms": segment.get("seed_terms", [])[:2],
                    "commercial_hints": segment.get("website_patterns", [])[:4],
                    "priority": priority_index,
                },
                {
                    "segment_id": segment["segment_id"],
                    "family": "rescue_queries",
                    "platforms": platform_priority[:2],
                    "intent_terms": segment.get("seed_terms", [])[:2],
                    "commercial_hints": segment.get("social_patterns", [])[:2],
                    "priority": priority_index + 20,
                },
            ]
        )
    return query_families


def _looks_social_first(profile: SearchPlannerProfile, job_context: Dict[str, Any]) -> bool:
    profession = _normalize_ascii(str(job_context.get("user_profession") or ""))
    social_first_roles = ("video", "editor", "community", "social", "designer", "creador")
    return profile.key in {"creator_coach", "ecommerce_content"} or any(token in profession for token in social_first_roles)


def _with_geo_suffix(query: str, geo_scope: dict[str, Any] | None) -> str:
    normalized_query = _normalize_space(query)
    if not normalized_query or not geo_scope:
        return normalized_query
    if any(alias in _normalize_ascii(normalized_query) for alias in geo_scope["aliases"]):
        return normalized_query
    return _normalize_space(f"{normalized_query} {geo_scope['label']}")


def _build_initial_wave(
    *,
    job_context: Dict[str, Any],
    profile: SearchPlannerProfile,
    geo_scope: dict[str, Any] | None,
    segment_hypotheses: list[dict[str, Any]],
    platform_priority: list[str],
) -> list[dict[str, Any]]:
    wave: list[dict[str, Any]] = []
    seen_queries: set[str] = set()

    def _push(query: str, *, segment_id: str, platform: str, family: str, reason: str) -> None:
        normalized_query = _normalize_space(query)
        if not normalized_query:
            return
        lowered_query = normalized_query.lower()
        if lowered_query in seen_queries:
            return
        wave.append(
            {
                "query": normalized_query,
                "segment_id": segment_id,
                "platform": platform,
                "family": family,
                "reason": reason,
            }
        )
        seen_queries.add(lowered_query)

    base_anchor = _normalize_space(str(job_context.get("target_niche") or job_context.get("search_query") or ""))
    raw_search_query = _normalize_space(str(job_context.get("search_query") or ""))
    if base_anchor:
        _push(
            _with_geo_suffix(base_anchor, geo_scope),
            segment_id="broad_niche",
            platform="website",
            family="rescue_queries",
            reason="broad_niche_probe",
        )
    if raw_search_query and _normalize_ascii(raw_search_query) != _normalize_ascii(base_anchor):
        _push(
            _with_geo_suffix(raw_search_query, geo_scope),
            segment_id="broad_search_query",
            platform="website",
            family="rescue_queries",
            reason="raw_request_probe",
        )

    for segment in segment_hypotheses[:3]:
        seed_terms = _dedupe_strings(segment.get("seed_terms") or [segment.get("label") or segment.get("segment_id")])
        if not seed_terms:
            continue
        _push(
            _with_geo_suffix(seed_terms[0], geo_scope),
            segment_id=segment["segment_id"],
            platform="website",
            family="website_validation_queries",
            reason="segment_probe",
        )

    if _looks_social_first(profile, job_context) and segment_hypotheses:
        top_segment = segment_hypotheses[0]
        seed_terms = _dedupe_strings(top_segment.get("seed_terms") or [top_segment.get("label") or top_segment.get("segment_id")])
        social_patterns = _dedupe_strings(top_segment.get("social_patterns") or [])
        top_platform = next((platform for platform in platform_priority if platform in {"instagram", "tiktok"}), "instagram")
        if seed_terms:
            social_query = _with_geo_suffix(seed_terms[0], geo_scope)
            site_clause = "site:instagram.com" if top_platform == "instagram" else "site:tiktok.com"
            hint = social_patterns[0] if social_patterns else ""
            _push(
                _normalize_space(f"{social_query} {hint} {site_clause}"),
                segment_id=top_segment["segment_id"],
                platform=top_platform,
                family="social_profile_queries",
                reason="social_first_probe",
            )

    return wave[:6]


def _normalize_initial_wave_items(
    initial_wave: list[dict[str, Any] | str] | None,
    *,
    fallback_wave: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized_wave: list[dict[str, Any]] = []
    seen_queries: set[str] = set()
    for raw_item in initial_wave or []:
        if isinstance(raw_item, dict):
            query = _normalize_space(str(raw_item.get("query") or ""))
            item = {
                "query": query,
                "segment_id": _normalize_space(str(raw_item.get("segment_id") or "generic_segment")) or "generic_segment",
                "platform": _normalize_space(str(raw_item.get("platform") or "website")) or "website",
                "family": _normalize_space(str(raw_item.get("family") or "rescue_queries")) or "rescue_queries",
                "reason": _normalize_space(str(raw_item.get("reason") or "initial_probe")) or "initial_probe",
            }
        else:
            query = _normalize_space(str(raw_item or ""))
            item = {
                "query": query,
                "segment_id": "generic_segment",
                "platform": "website",
                "family": "rescue_queries",
                "reason": "initial_probe",
            }
        if not query or query.lower() in seen_queries:
            continue
        normalized_wave.append(item)
        seen_queries.add(query.lower())
    for fallback_item in fallback_wave:
        query = _normalize_space(str(fallback_item.get("query") or ""))
        if not query or query.lower() in seen_queries:
            continue
        normalized_wave.append(dict(fallback_item))
        seen_queries.add(query.lower())
    return normalized_wave[:6]


def _derive_query_actions(
    *,
    segment_hypotheses: list[dict[str, Any]],
    iteration_memory: Dict[str, Any] | None,
    platform_priority: list[str],
) -> list[dict[str, Any]]:
    performance_map = _extract_segment_performance_map(iteration_memory)
    actions: list[dict[str, Any]] = []
    fallback_platform = platform_priority[0] if platform_priority else "website"

    for segment in segment_hypotheses[:5]:
        stats = performance_map.get(segment["segment_id"], {})
        accepted = int(stats.get("accepted") or 0)
        rejected = int(stats.get("rejected") or 0)
        geo_failures = int(stats.get("geo_failures") or 0)
        language_failures = int(stats.get("language_failures") or 0)
        zero_result_queries = int(stats.get("zero_result_queries") or 0)
        serp_noise_ratio = float(stats.get("serp_noise_ratio") or 0.0)

        if zero_result_queries >= 2:
            action = "pivot"
            reason = "segment_zero_recall"
        elif serp_noise_ratio >= 0.6 or (accepted == 0 and rejected >= 2):
            action = "pause"
            reason = "high_noise"
        elif geo_failures or language_failures:
            action = "tighten_geo" if geo_failures else "switch_platform"
            reason = "geo_or_language_mismatch"
        elif accepted > 0:
            action = "deepen"
            reason = "positive_yield"
        else:
            action = "expand"
            reason = "needs_more_coverage"

        actions.append(
            {
                "segment_id": segment["segment_id"],
                "action": action,
                "reason": reason,
                "target_platform": stats.get("best_platform") or fallback_platform,
            }
        )
    return actions


def _derive_segment_action_plan(query_actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "segment_id": action.get("segment_id"),
            "action": action.get("action"),
            "reason": action.get("reason"),
            "target_platform": action.get("target_platform"),
        }
        for action in query_actions
        if action.get("segment_id")
    ]


def _derive_evidence_gaps(iteration_memory: Dict[str, Any] | None) -> list[str]:
    if not isinstance(iteration_memory, dict):
        return ["Validar recall inicial por subsegmento.", "Confirmar mejor plataforma por nicho."]
    gaps: list[str] = []
    if not iteration_memory.get("accepted_samples"):
        gaps.append("Aun no hay ejemplos aceptados para fijar patron ganador.")
    if not iteration_memory.get("query_reports"):
        gaps.append("Falta evidencia SERP rica por query para decidir expansion o pivote.")
    if not iteration_memory.get("top_false_positive_patterns"):
        gaps.append("Faltan patrones claros de ruido para endurecer exclusiones.")
    return gaps[:4]


def _derive_refinement_hypotheses(
    segment_hypotheses: list[dict[str, Any]],
    iteration_memory: Dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[str], list[str], list[str]]:
    performance_map = _extract_segment_performance_map(iteration_memory)
    refinement_hypotheses: list[dict[str, Any]] = []
    next_segments_to_try: list[str] = []
    segments_to_pause: list[str] = []

    for segment in segment_hypotheses:
        stats = performance_map.get(segment["segment_id"], {})
        processed = int(stats.get("processed") or 0)
        accepted = int(stats.get("accepted") or 0)
        rejected = int(stats.get("rejected") or 0)
        geo_failures = int(stats.get("geo_failures") or 0)
        language_failures = int(stats.get("language_failures") or 0)
        zero_result_queries = int(stats.get("zero_result_queries") or 0)
        serp_noise_ratio = float(stats.get("serp_noise_ratio") or 0.0)
        if zero_result_queries >= 2:
            refinement_hypotheses.append(
                {
                    "segment_id": segment["segment_id"],
                    "action": "pivot",
                    "reason": "segment_zero_recall",
                }
            )
            continue
        if processed >= 3 and accepted == 0 and rejected >= 2:
            segments_to_pause.append(segment["segment_id"])
            refinement_hypotheses.append(
                {
                    "segment_id": segment["segment_id"],
                    "action": "pause",
                    "reason": "low_yield_noise",
                }
            )
            continue
        next_segments_to_try.append(segment["segment_id"])
        if serp_noise_ratio >= 0.6:
            action = "expand"
            reason = "broaden_after_serp_noise"
        elif geo_failures:
            action = "tighten_geo"
            reason = "geo_or_language_noise"
        elif language_failures:
            action = "switch_platform"
            reason = "geo_or_language_noise"
        elif accepted > 0:
            action = "deepen"
            reason = "positive_yield"
        else:
            action = "expand"
            reason = "social_first_scale"
        refinement_hypotheses.append(
            {
                "segment_id": segment["segment_id"],
                "action": action,
                "reason": reason,
            }
        )

    segment_rotation_rules = [
        "Mantener olas cortas y abrir el wording cuando una query muera en SERP.",
        "Pausar segmentos con >=3 procesados, 0 aceptados y ruido dominante.",
        "Pivotear subsegmento si acumula 2 queries seguidas con zero recall.",
        "Profundizar el segmento ganador antes de abrir nuevos dorks finos.",
    ]
    return refinement_hypotheses[:8], next_segments_to_try[:6], segments_to_pause[:6], segment_rotation_rules


def _sanitize_profile_queries(queries: list[str], profile: SearchPlannerProfile) -> list[str]:
    sanitized_queries = _dedupe_strings(queries)
    if profile.key != "ecommerce_content":
        return sanitized_queries

    filtered_queries: list[str] = []
    for query in sanitized_queries:
        normalized_query = _normalize_ascii(query)
        if any(blocked_hint in normalized_query for blocked_hint in ECOMMERCE_BLOCKED_QUERY_HINTS):
            continue
        filtered_queries.append(query)
    return filtered_queries


def _render_numbered_rules(*rule_groups: tuple[str, ...]) -> str:
    lines: list[str] = []
    counter = 1
    for rule_group in rule_groups:
        for rule in rule_group:
            lines.append(f"{counter}. {rule}")
            counter += 1
    return "\n".join(lines)


def _build_initial_system_prompt(profile: SearchPlannerProfile) -> str:
    base_rules = (
        "Piensa primero en hipotesis de subsegmentos y en una primera ola corta.",
        "Genera una primera ola de 4 a 6 queries maximo.",
        "Busca clientes finales exactos para outreach, no proveedores ni intermediarios.",
        "Evita blogs, medios, escuelas, directorios, listados, software, assets, fuentes, tools y paginas informativas.",
        "Si existe una ubicacion objetivo unica, no abras geografia fuera de esa ubicacion.",
        "Devuelve terminos negativos utiles, gaps de evidencia y hints para el clasificador final.",
    )
    profile_rules = (
        f"Trabaja en modo {profile.label} y prioriza: {', '.join(profile.priority_signals)}.",
        f"Rechaza especialmente: {', '.join(profile.exclusion_focus)}.",
    )
    return f"""Eres un experto mundial en OSINT, Growth Hacking y prospeccion comercial.

Tu tarea es disenar un Search Plan para encontrar CLIENTES FINALES EXACTOS para outreach.

REGLAS:
{_render_numbered_rules(base_rules, profile_rules)}

SALIDA JSON:
{{
  "optimal_dork_queries": ["..."],
  "dynamic_negative_terms": ["-blog"],
  "target_entity_hints": ["..."],
  "exclusion_entity_hints": ["..."],
  "refinement_goal": "...",
  "search_strategy": "social_first",
  "subsegment_hypotheses": [],
  "segment_hypotheses": [
    {{
      "segment_id": "business_coach",
      "label": "business coach",
      "why_relevant": "...",
      "buyer_type": "coach",
      "product_or_offer_examples": ["..."],
      "social_patterns": ["..."],
      "website_patterns": ["..."],
      "geo_signals": ["..."],
      "language_signals": ["..."],
      "negative_signals": ["..."],
      "seed_terms": ["..."],
      "confidence": 0.85
    }}
  ],
  "initial_wave": [
    {{"query": "...", "segment_id": "business_coach", "platform": "website", "family": "website_validation_queries", "reason": "segment_probe"}}
  ],
  "query_actions": [
    {{"segment_id": "business_coach", "action": "expand", "reason": "needs_more_coverage", "target_platform": "instagram"}}
  ],
  "segment_action_plan": [
    {{"segment_id": "business_coach", "action": "expand", "reason": "needs_more_coverage", "target_platform": "instagram"}}
  ],
  "evidence_gaps": ["..."],
  "dynamic_priority_signals": ["..."],
  "dynamic_negative_signals": ["..."],
  "query_families": [
    {{
      "segment_id": "business_coach",
      "family": "social_profile_queries",
      "platforms": ["instagram", "tiktok"],
      "intent_terms": ["business coach"],
      "commercial_hints": ["link in bio", "book call"],
      "priority": 1
    }}
  ],
  "platform_priority": ["instagram", "tiktok", "website"],
  "commercial_validation_signals": ["..."],
  "candidate_evaluation_policy": {{
    "identity_priority": "social_first",
    "contact_requirement": "soft",
    "quick_ai_stage": "hybrid",
    "quick_ai_inputs": ["url", "domain", "title", "snippet", "result_kind", "platform", "handle", "meta_title", "meta_description", "social_bio", "link_in_bio_present", "cta_tokens"],
    "hard_reject_reasons": ["blocked_domain", "excluded_social_post", "excluded_reference_page"],
    "borderline_rescue_rules": ["canonical_social_profile", "commercial_snippet_hint", "brandable_domain_match"]
  }},
  "refinement_hypotheses": [],
  "segment_rotation_rules": ["..."],
  "next_segments_to_try": ["business_coach"],
  "segments_to_pause": []
}}
"""


def _build_refinement_system_prompt(profile: SearchPlannerProfile) -> str:
    base_rules = (
        "Aumenta prospectos finales validos.",
        "Reduce ruido y falsos positivos.",
        "No repitas queries ya usadas.",
        "Si una query muere en SERP, abre wording o cambia de subsegmento antes de endurecerla.",
        "Si existe una ubicacion objetivo unica, no abras geografia fuera de esa ubicacion.",
        "Excluye directorios, listados, blogs, medios, assets y paginas oportunistas por keyword.",
    )
    profile_rules = (
        f"Trabaja en modo {profile.label} y prioriza: {', '.join(profile.priority_signals)}.",
        f"Endurece exclusiones para: {', '.join(profile.exclusion_focus)}.",
    )
    return f"""Eres un experto en iteracion de discovery comercial.

Debes revisar los resultados previos de un job y proponer nuevas acciones por hipotesis: expand, deepen, pause, pivot, broaden_geo, tighten_geo o switch_platform.

OBJETIVO:
{_render_numbered_rules(base_rules, profile_rules)}

Si viste falsos positivos, usalos para endurecer terminos negativos y exclusiones.
Si viste bajo recall, abre la busqueda.

SALIDA JSON:
{{
  "optimal_dork_queries": ["..."],
  "dynamic_negative_terms": ["-blog"],
  "target_entity_hints": ["..."],
  "exclusion_entity_hints": ["..."],
  "refinement_goal": "...",
  "search_strategy": "social_first",
  "subsegment_hypotheses": [{{"segment_id": "...", "label": "...", "seed_terms": ["..."]}}],
  "segment_hypotheses": [{{"segment_id": "...", "label": "...", "seed_terms": ["..."]}}],
  "initial_wave": [{{"query": "...", "segment_id": "...", "platform": "website", "family": "rescue_queries", "reason": "broaden_probe"}}],
  "query_actions": [{{"segment_id": "...", "action": "pivot", "reason": "segment_zero_recall", "target_platform": "instagram"}}],
  "segment_action_plan": [{{"segment_id": "...", "action": "deepen", "reason": "positive_yield", "target_platform": "website"}}],
  "evidence_gaps": ["..."],
  "dynamic_priority_signals": ["..."],
  "dynamic_negative_signals": ["..."],
  "query_families": [{{"segment_id": "...", "family": "social_profile_queries", "platforms": ["instagram"], "intent_terms": ["..."], "commercial_hints": ["..."], "priority": 1}}],
  "platform_priority": ["instagram", "tiktok", "website"],
  "commercial_validation_signals": ["..."],
  "candidate_evaluation_policy": {{
    "identity_priority": "social_first",
    "contact_requirement": "soft",
    "quick_ai_stage": "hybrid",
    "quick_ai_inputs": ["url", "domain", "title", "snippet", "result_kind", "platform", "handle", "meta_title", "meta_description", "social_bio", "link_in_bio_present", "cta_tokens"],
    "hard_reject_reasons": ["blocked_domain", "excluded_social_post", "excluded_reference_page"],
    "borderline_rescue_rules": ["canonical_social_profile", "commercial_snippet_hint", "brandable_domain_match"]
  }},
  "refinement_hypotheses": [{{"segment_id": "...", "action": "pause", "reason": "noise"}}],
  "segment_rotation_rules": ["..."],
  "next_segments_to_try": ["..."],
  "segments_to_pause": ["..."]
}}
"""


def _compact_iteration_memory(iteration_memory: Dict[str, Any] | None) -> str:
    if not isinstance(iteration_memory, dict):
        return "Sin memoria previa."

    payload = {
        "trigger_reason": iteration_memory.get("trigger_reason"),
        "window_stats": iteration_memory.get("window_stats"),
        "top_rejection_reasons": iteration_memory.get("top_rejection_reasons"),
        "segment_performance": iteration_memory.get("segment_performance"),
        "queries_by_segment": iteration_memory.get("queries_by_segment"),
        "accepted_by_segment": iteration_memory.get("accepted_by_segment"),
        "needs_review_by_segment": iteration_memory.get("needs_review_by_segment"),
        "rejected_by_segment": iteration_memory.get("rejected_by_segment"),
        "platform_yield": iteration_memory.get("platform_yield"),
        "query_reports": iteration_memory.get("query_reports", [])[:12],
        "query_performance": iteration_memory.get("query_performance"),
        "query_zero_result_count": iteration_memory.get("query_zero_result_count"),
        "high_noise_queries": iteration_memory.get("high_noise_queries"),
        "repeated_domains": iteration_memory.get("repeated_domains"),
        "geo_failures_by_segment": iteration_memory.get("geo_failures_by_segment"),
        "language_failures_by_segment": iteration_memory.get("language_failures_by_segment"),
        "top_false_positive_patterns": iteration_memory.get("top_false_positive_patterns"),
        "queries_already_executed": iteration_memory.get("queries_already_executed", [])[:20],
        "seen_domains": iteration_memory.get("seen_domains", [])[:20],
        "false_positive_samples": iteration_memory.get("false_positive_samples", [])[:8],
        "accepted_samples": iteration_memory.get("accepted_samples", [])[:4],
    }
    return json.dumps(payload, ensure_ascii=False)


def _build_mode_summary_lines(profile: SearchPlannerProfile, geo_scope: dict[str, Any] | None) -> list[str]:
    geo_label = geo_scope["label"] if geo_scope else "Flexible o multiple opciones"
    return [
        "MODO DE BUSQUEDA:",
        f"- Perfil activo: {profile.label}",
        f"- Ubicacion operativa: {geo_label}",
        f"- Target valido: {profile.target_description}",
        f"- Priorizar: {', '.join(profile.priority_signals)}",
        f"- Rechazar: {', '.join(profile.exclusion_focus)}",
    ]


def _build_initial_user_prompt(
    job_context: Dict[str, Any],
    profile: SearchPlannerProfile,
    geo_scope: dict[str, Any] | None,
) -> str:
    buyer_persona = _build_buyer_persona(job_context)
    return "\n".join(
        [
            "PERFIL DEL VENDEDOR:",
            buyer_persona,
            "",
            *_build_mode_summary_lines(profile, geo_scope),
        ]
    )


def _build_refinement_user_prompt(
    job_context: Dict[str, Any],
    iteration_memory: Dict[str, Any] | None,
    profile: SearchPlannerProfile,
    geo_scope: dict[str, Any] | None,
) -> str:
    buyer_persona = _build_buyer_persona(job_context)
    geo_policy = geo_scope["label"] if geo_scope else "Flexible o multiple opciones"
    return "\n".join(
        [
            "REQUEST ORIGINAL DEL USUARIO:",
            buyer_persona,
            "",
            *_build_mode_summary_lines(profile, geo_scope),
            "",
            "POLITICA FIJA:",
            f"- Ubicacion operativa: {geo_policy}",
            f"- Target valido: {profile.target_description}",
            f"- Rechazar: {', '.join(profile.exclusion_focus)}",
            "",
            "MEMORIA DEL JOB:",
            _compact_iteration_memory(iteration_memory),
        ]
    )


def _build_planner_cache_key(
    job_context: Dict[str, Any],
    *,
    mode: PlannerMode,
    iteration_memory: Dict[str, Any] | None,
) -> str:
    profile = _resolve_planner_profile(job_context)
    base_parts = [
        mode,
        profile.key,
        str(job_context.get("search_query", "")),
        str(job_context.get("user_profession", "")),
        str(job_context.get("target_niche", "")),
        str(job_context.get("target_location", "")),
    ]
    if mode == "refinement":
        memory_fingerprint = sha256(
            json.dumps(iteration_memory or {}, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        base_parts.append(memory_fingerprint)
    return "|".join(base_parts).lower()


def _coerce_plan_payload(
    parsed_data: Dict[str, Any],
    *,
    job_context: Dict[str, Any],
    profile: SearchPlannerProfile,
    geo_scope: dict[str, Any] | None,
    iteration_memory: Dict[str, Any] | None,
) -> Dict[str, Any]:
    payload = AISearchPlanPayload.model_validate(parsed_data)
    result = payload.model_dump()
    planner_segments = result.get("subsegment_hypotheses") or result.get("segment_hypotheses")
    segment_hypotheses = _build_segment_hypotheses(
        profile,
        job_context=job_context,
        planner_segments=planner_segments,
        geo_scope=geo_scope,
        iteration_memory=iteration_memory,
    )
    platform_priority = _derive_platform_priority(
        profile,
        job_context,
        result.get("platform_priority"),
    )
    dynamic_priority_signals = _dedupe_strings(
        [
            *(result.get("dynamic_priority_signals") or []),
            *_derive_dynamic_priority_signals(
                profile=profile,
                job_context=job_context,
                segment_hypotheses=segment_hypotheses,
            ),
        ]
    )
    dynamic_negative_signals = _dedupe_strings(
        [
            *(result.get("dynamic_negative_signals") or []),
            *_derive_dynamic_negative_signals(
                profile=profile,
                segment_hypotheses=segment_hypotheses,
                iteration_memory=iteration_memory,
            ),
        ]
    )
    refinement_hypotheses, next_segments_to_try, segments_to_pause, segment_rotation_rules = _derive_refinement_hypotheses(
        segment_hypotheses,
        iteration_memory,
    )
    sanitized_queries = _sanitize_profile_queries(result.get("optimal_dork_queries", []), profile)
    result["optimal_dork_queries"] = _enforce_geo_policy(
        sanitized_queries,
        geo_scope=geo_scope,
    )
    result["dynamic_negative_terms"] = _normalize_negative_terms(result.get("dynamic_negative_terms", []))
    result["target_entity_hints"] = _dedupe_strings(
        [*profile.default_target_entity_hints, *(result.get("target_entity_hints", []) or [])]
    )
    result["exclusion_entity_hints"] = _dedupe_strings(
        [*profile.default_exclusion_entity_hints, *(result.get("exclusion_entity_hints", []) or [])]
    )
    result["refinement_goal"] = _normalize_space(result.get("refinement_goal"))
    result["planner_profile"] = profile.key
    result["geo_scope"] = geo_scope["label"] if geo_scope else None
    result["search_strategy"] = _normalize_space(result.get("search_strategy")) or (
        "social_first" if profile.key in {"creator_coach", "ecommerce_content"} else "hybrid"
    )
    initial_wave_fallback = _build_initial_wave(
        job_context=job_context,
        profile=profile,
        geo_scope=geo_scope,
        segment_hypotheses=segment_hypotheses,
        platform_priority=platform_priority,
    )
    query_actions = result.get("query_actions") or _derive_query_actions(
        segment_hypotheses=segment_hypotheses,
        iteration_memory=iteration_memory,
        platform_priority=platform_priority,
    )
    result["segment_hypotheses"] = segment_hypotheses
    result["subsegment_hypotheses"] = segment_hypotheses
    result["initial_wave"] = _normalize_initial_wave_items(
        result.get("initial_wave"),
        fallback_wave=initial_wave_fallback,
    )
    result["query_actions"] = query_actions[:8]
    result["segment_action_plan"] = result.get("segment_action_plan") or _derive_segment_action_plan(query_actions)
    result["evidence_gaps"] = _dedupe_strings(result.get("evidence_gaps") or _derive_evidence_gaps(iteration_memory))
    result["dynamic_priority_signals"] = dynamic_priority_signals[:20]
    result["dynamic_negative_signals"] = dynamic_negative_signals[:18]
    result["platform_priority"] = platform_priority
    result["query_families"] = result.get("query_families") or _build_query_families(
        segment_hypotheses=segment_hypotheses,
        platform_priority=platform_priority,
    )
    result["commercial_validation_signals"] = _dedupe_strings(
        [*(result.get("commercial_validation_signals") or []), *(profile.priority_signals or ()), *dynamic_priority_signals[:6]]
    )[:12]
    result["candidate_evaluation_policy"] = _build_candidate_evaluation_policy(
        profile=profile,
        job_context=job_context,
        platform_priority=platform_priority,
        dynamic_priority_signals=dynamic_priority_signals,
        planner_policy=result.get("candidate_evaluation_policy"),
    )
    result["refinement_hypotheses"] = result.get("refinement_hypotheses") or refinement_hypotheses
    result["segment_rotation_rules"] = result.get("segment_rotation_rules") or segment_rotation_rules
    result["next_segments_to_try"] = _dedupe_strings(result.get("next_segments_to_try") or next_segments_to_try)
    result["segments_to_pause"] = _dedupe_strings(result.get("segments_to_pause") or segments_to_pause)
    return result


def _empty_plan(
    job_context: Dict[str, Any] | None = None,
    *,
    profile: SearchPlannerProfile | None = None,
    geo_scope: dict[str, Any] | None = None,
    iteration_memory: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    resolved_profile = profile or _resolve_planner_profile(job_context or {})
    return _coerce_plan_payload(
        {},
        job_context=job_context or {},
        profile=resolved_profile,
        geo_scope=geo_scope or _resolve_geo_scope(job_context or {}),
        iteration_memory=iteration_memory,
    )


async def _call_planner(
    *,
    system_prompt: str,
    user_prompt: str,
) -> Dict[str, Any]:
    deepseek_api_key = _get_deepseek_api_key()
    if not deepseek_api_key:
        logger.warning("DEEPSEEK_API_KEY no encontrada. Generando plan vacío por defecto.")
        return AISearchPlanPayload().model_dump()

    client = _build_deepseek_client(deepseek_api_key)
    response = await client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        max_tokens=1400,
        response_format={"type": "json_object"},
    )
    raw_output = response.choices[0].message.content
    return json.loads(raw_output)


async def generate_dynamic_search_plan(
    job_context: Dict[str, Any],
    *,
    mode: PlannerMode = "initial",
    iteration_memory: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    cache_key = _build_planner_cache_key(job_context, mode=mode, iteration_memory=iteration_memory)
    if cache_key in _PLANNER_CACHE:
        logger.info("Retornando AI Search Plan desde caché en memoria.")
        return deepcopy(_PLANNER_CACHE[cache_key])

    profile = _resolve_planner_profile(job_context)
    geo_scope = _resolve_geo_scope(job_context)
    if mode == "refinement":
        system_prompt = _build_refinement_system_prompt(profile)
        user_prompt = _build_refinement_user_prompt(job_context, iteration_memory, profile, geo_scope)
    else:
        system_prompt = _build_initial_system_prompt(profile)
        user_prompt = _build_initial_user_prompt(job_context, profile, geo_scope)

    try:
        parsed_data = await _call_planner(system_prompt=system_prompt, user_prompt=user_prompt)
        result_dict = _coerce_plan_payload(
            parsed_data,
            job_context=job_context,
            profile=profile,
            geo_scope=geo_scope,
            iteration_memory=iteration_memory,
        )
        _PLANNER_CACHE[cache_key] = deepcopy(result_dict)
        logger.info("Plan AI de búsqueda generado exitosamente en modo %s.", mode)
        return result_dict
    except (ValidationError, json.JSONDecodeError) as exc:
        logger.error("Fallo validando plan de búsqueda con IA: %s", exc)
        return _empty_plan(
            job_context,
            profile=profile,
            geo_scope=geo_scope,
            iteration_memory=iteration_memory,
        )
    except Exception as exc:
        logger.error("Fallo al generar plan de búsqueda con IA: %s", exc)
        return _empty_plan(
            job_context,
            profile=profile,
            geo_scope=geo_scope,
            iteration_memory=iteration_memory,
        )


async def initial_search_plan(job_context: Dict[str, Any]) -> Dict[str, Any]:
    return await generate_dynamic_search_plan(job_context, mode="initial")


async def refine_search_plan(job_context: Dict[str, Any], iteration_memory: Dict[str, Any]) -> Dict[str, Any]:
    return await generate_dynamic_search_plan(
        job_context,
        mode="refinement",
        iteration_memory=iteration_memory,
    )
