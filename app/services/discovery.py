from __future__ import annotations

import re
from typing import Any

DEFAULT_CANDIDATE_MULTIPLIER = 4
DEFAULT_MIN_CANDIDATES = 5
MAX_DISCOVERY_QUERIES = 24
DEFAULT_QUERY_BATCH_SIZE = 3
DEFAULT_CANDIDATE_BATCH_SIZE = 5
NEGATIVE_DISCOVERY_TERMS = (
    "-blog",
    "-ideas",
    "-noticias",
    "-prensa",
    "-informe",
    "-report",
    "-revista",
    "-g2",
    "-pinterest",
    "-linkedin",
)
SERVICE_PROVIDER_EXCLUSION_TERMS = (
    "-asesoria",
    "-asesoría",
    "-consultoria",
    "-consultoría",
    "-consultor",
    "-consultora",
    "-coach",
    "-coaching",
    "-mentor",
    "-mentoria",
    "-mentoría",
    "-agencia",
    "-freelance",
    "-freelancer",
)

LANGUAGE_DISCOVERY_HINTS = {
    "es": {
        "official": "sitio oficial",
        "contact": "contacto",
        "services": "servicios",
        "shop": "tienda",
        "products": "productos",
        "collections": "colecciones",
        "commercial": ["empresa", "negocio", "servicios"],
        "locations": ["ubicaciones", "sedes"],
    },
    "en": {
        "official": "official site",
        "contact": "contact",
        "services": "services",
        "shop": "shop",
        "products": "products",
        "collections": "collections",
        "commercial": ["business", "company", "services"],
        "locations": ["locations", "branches"],
    },
    "pt": {
        "official": "site oficial",
        "contact": "contato",
        "services": "servicos",
        "shop": "loja",
        "products": "produtos",
        "collections": "colecoes",
        "commercial": ["empresa", "negocio", "servicos"],
        "locations": ["localizacoes", "unidades"],
    },
}

INTENT_SPLIT_PATTERN = re.compile(r"\s*(?:,|/|&|\by\b|\be\b)\s*", re.IGNORECASE)
GENERIC_QUERY_PREFIXES = (
    "empresas ",
    "marcas ",
    "negocios ",
    "sitios ",
)
SOCIAL_PLATFORM_QUERY_HINTS = (
    "instagram",
    "tiktok",
    "link in bio",
    "linktree",
    "reels",
    "shorts",
)
SOCIAL_COMMERCIAL_HINTS = (
    "marca personal",
    "coach",
    "coaches",
    "ecommerce",
    "tienda online",
    "agencia",
    "curso",
    "cursos",
    "infoproductos",
)
DISCOVERY_PROFILE_HINTS = {
    "creator_coach": ("coach", "coaches", "coaching", "marca personal", "marcas personales", "personal brand"),
    "ecommerce": ("ecommerce", "shopify", "tienda online", "tiendas online", "dropshipping", "online store", "online stores"),
}
PROFILE_SOCIAL_HINTS = {
    "generic": ("link in bio", "linktree"),
    "creator_coach": ("link in bio", "linktree", "programa", "mentoria", "coach"),
    "ecommerce": ("shop now", "product video", "product content", "new drop", "online store", "shopify"),
}
PROFILE_RETRY_SOCIAL_HINTS = {
    "generic": ("link in bio",),
    "creator_coach": ("link in bio", "marca personal", "coach"),
    "ecommerce": ("shop now", "product video", "new drop", "shopify"),
}
PROFILE_BIO_HUB_DOMAINS = {
    "generic": ("site:linktr.ee", "site:beacons.ai"),
    "creator_coach": ("site:linktr.ee", "site:beacons.ai", "site:stan.store"),
    "ecommerce": ("site:linktr.ee", "site:beacons.ai"),
}
QUERY_LOCALIZATION_MAP = {
    "en": (
        ("pequeñas marcas ecommerce", "small ecommerce brands"),
        ("pequenas marcas ecommerce", "small ecommerce brands"),
        ("marcas ecommerce", "ecommerce brands"),
        ("tiendas online", "online stores"),
        ("tienda online", "online store"),
        ("pymes digitales", "digital businesses"),
        ("pyme digital", "digital business"),
        ("marca personal", "personal brand"),
        ("marcas personales", "personal brands"),
        ("cursos online", "online courses"),
        ("productos digitales", "digital products"),
        ("infoproductos", "digital products"),
    ),
}
NICHE_VARIANTS = {
    "ecommerce": ["ecommerce", "tienda online", "shopify"],
    "tienda online": ["tienda online", "ecommerce", "shopify"],
    "shopify": ["shopify", "tienda online", "ecommerce"],
    "academia online": ["academia online", "cursos online", "escuela online", "formacion online"],
    "academias online": ["academia online", "cursos online", "escuela online", "formacion online"],
    "cursos online": ["cursos online", "academia online", "escuela online"],
    "escuela online": ["escuela online", "academia online", "cursos online"],
    "productos digitales": ["productos digitales", "infoproductos", "cursos online"],
    "infoproductos": ["infoproductos", "productos digitales", "cursos online"],
}
INTENT_FAMILY_HINTS = {
    "personal_brand": ["marca personal", "marcas personales", "personal brand", "branding personal"],
    "coaching": ["coach", "coaches", "coaching", "mentor", "mentoria", "mentoría"],
    "ecommerce": ["ecommerce", "tienda online", "shopify"],
    "education": ["academia online", "academias online", "cursos online", "escuela online", "infoproductos", "productos digitales"],
}
ECOMMERCE_NEGATIVE_TERMS = (
    "-theme",
    "-themes",
    "-template",
    "-templates",
    "-app",
    "-apps",
    "-tutorial",
    "-guide",
    "-supplier",
    "-suppliers",
    "-wholesale",
    "-marketplace",
    "-directory",
    "-help",
    "-docs",
    "-documentation",
)
GLOBAL_LOCATION_TOKENS = {
    "global",
    "globales",
    "worldwide",
    "mundial",
    "internacional",
    "remote",
    "remoto",
    "remota",
    "anywhere",
}
LOCATION_ALIAS_RULES = {
    "USA": ("usa", "united states", "estados unidos", "eeuu"),
    "UK": ("uk", "united kingdom", "reino unido", "great britain"),
    "Canada": ("canada",),
    "Australia": ("australia",),
    "España": ("espana", "españa", "spain"),
    "México": ("mexico", "méxico", "cdmx", "ciudad de mexico", "ciudad de méxico"),
    "Argentina": ("argentina", "buenos aires"),
    "Colombia": ("colombia", "bogota", "bogotá"),
    "Perú": ("peru", "perú", "lima"),
    "Chile": ("chile",),
    "Uruguay": ("uruguay",),
    "Bolivia": ("bolivia",),
}


def _normalize_space(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def _is_global_target_location(value: str | None) -> bool:
    normalized = _normalize_space(value).lower()
    return normalized in GLOBAL_LOCATION_TOKENS


def _effective_target_location(value: str | None) -> str:
    normalized = _normalize_space(value)
    return "" if _is_global_target_location(normalized) else normalized


def resolve_discovery_target_location(
    *,
    search_query: str | None,
    target_location: str | None,
    target_niche: str | None = None,
) -> str:
    explicit_location = _effective_target_location(target_location)
    if explicit_location:
        return explicit_location

    searchable = f" {_normalize_space(search_query)} {_normalize_space(target_niche)} ".lower()
    for canonical_location, aliases in LOCATION_ALIAS_RULES.items():
        if any(f" {alias.lower()} " in searchable for alias in aliases):
            return canonical_location
    return ""


def _query_contains_token(query: str, token: str) -> bool:
    normalized_query = f" {_normalize_space(query).lower()} "
    normalized_token = f" {_normalize_space(token).lower()} "
    return bool(token) and normalized_token in normalized_query


def _resolve_discovery_profile(
    *,
    search_query: str | None,
    target_niche: str | None,
    user_target_offer_focus: str | None,
    target_budget_signals: list[str] | None,
) -> str:
    searchable = _normalize_space(
        " ".join(
            [
                str(search_query or ""),
                str(target_niche or ""),
                str(user_target_offer_focus or ""),
                " ".join(str(item) for item in (target_budget_signals or [])),
            ]
        )
    ).lower()

    profile_scores = {
        profile_name: sum(1 for hint in hints if hint in searchable)
        for profile_name, hints in DISCOVERY_PROFILE_HINTS.items()
    }
    if profile_scores["ecommerce"] > profile_scores["creator_coach"] and profile_scores["ecommerce"] >= 1:
        return "ecommerce"
    if profile_scores["creator_coach"] >= 1:
        return "creator_coach"
    if profile_scores["ecommerce"] >= 1:
        return "ecommerce"
    return "generic"


def _localize_query_fragment(value: str | None, language: str | None) -> str:
    normalized_value = _normalize_space(value)
    if not normalized_value:
        return ""
    replacements = QUERY_LOCALIZATION_MAP.get(_normalize_space(language).lower(), ())
    localized_value = normalized_value
    lowered_value = localized_value.lower()
    for source, target in replacements:
        if source in lowered_value:
            localized_value = re.sub(re.escape(source), target, localized_value, flags=re.IGNORECASE)
            lowered_value = localized_value.lower()
    if _normalize_space(language).lower() == "en":
        localized_value = re.sub(r"\s+y\s+", " and ", localized_value, flags=re.IGNORECASE)
    return _normalize_space(localized_value)


def _extract_keywords(value: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]{3,}", _normalize_space(value).lower())
    stopwords = {"para", "con", "los", "las", "del", "por", "que"}
    return [token for token in tokens if token not in stopwords]


def _extract_intent_family_tags(value: str) -> set[str]:
    normalized_value = f" {_normalize_space(value).lower()} "
    matched_tags: set[str] = set()
    for tag, hints in INTENT_FAMILY_HINTS.items():
        if any(f" {hint.lower()} " in normalized_value for hint in hints):
            matched_tags.add(tag)
    return matched_tags


def _fragment_matches_target_niche(fragment: str, target_niche: str) -> bool:
    fragment_tokens = set(_extract_keywords(fragment))
    target_tokens = set(_extract_keywords(target_niche))
    if fragment_tokens & target_tokens:
        return True

    fragment_tags = _extract_intent_family_tags(fragment)
    target_tags = _extract_intent_family_tags(target_niche)
    return bool(fragment_tags & target_tags)


def _strip_generic_prefixes(value: str) -> str:
    normalized = _normalize_space(value)
    lowered = normalized.lower()
    for prefix in GENERIC_QUERY_PREFIXES:
        if lowered.startswith(prefix):
            stripped = _normalize_space(normalized[len(prefix) :])
            if prefix == "marcas " and stripped.lower() == "personales":
                return normalized
            return _normalize_space(normalized[len(prefix) :])
    return normalized


def _remove_location_tokens(value: str, location: str) -> str:
    normalized_value = _normalize_space(value)
    normalized_location = _normalize_space(location)
    if not normalized_value or not normalized_location:
        return normalized_value

    pattern = re.compile(rf"\b{re.escape(normalized_location)}\b", re.IGNORECASE)
    return _normalize_space(pattern.sub(" ", normalized_value))


def _expand_intent_variants(intent: str) -> list[str]:
    normalized_intent = _normalize_space(intent)
    lowered_intent = normalized_intent.lower()
    variants: list[str] = []

    for key, candidate_variants in NICHE_VARIANTS.items():
        if key in lowered_intent:
            for candidate in candidate_variants:
                _append_query(variants, candidate)

    if not variants:
        _append_query(variants, normalized_intent)
    return variants


def _derive_intent_seeds(*, search_query: str, target_niche: str, location: str) -> list[str]:
    seeds: list[str] = []
    grouped_variants: list[list[str]] = []

    for raw_value in (target_niche, search_query):
        base_value = _remove_location_tokens(raw_value, location)
        if not base_value:
            continue

        fragments = [fragment for fragment in INTENT_SPLIT_PATTERN.split(base_value) if _normalize_space(fragment)]
        if not fragments:
            fragments = [base_value]

        if raw_value == search_query and _normalize_space(target_niche):
            matching_fragments = [fragment for fragment in fragments if _fragment_matches_target_niche(fragment, target_niche)]
            if matching_fragments:
                fragments = matching_fragments

        for fragment in fragments:
            cleaned_fragment = _strip_generic_prefixes(fragment)
            if not cleaned_fragment:
                continue
            variants: list[str] = []
            for variant in _expand_intent_variants(cleaned_fragment):
                if raw_value == search_query and _normalize_space(target_niche):
                    if not _fragment_matches_target_niche(variant, target_niche):
                        continue
                _append_query(variants, variant)
            if variants:
                grouped_variants.append(variants)

    max_variants = max((len(group) for group in grouped_variants), default=0)
    for variant_index in range(max_variants):
        for group in grouped_variants:
            if variant_index < len(group):
                _append_query(seeds, group[variant_index])

    return seeds


def _append_query(queries: list[str], candidate: str | None) -> None:
    normalized = _normalize_space(candidate)
    if normalized and normalized not in queries:
        queries.append(normalized)


def _chunk_queries(queries: list[str], batch_size: int) -> list[list[str]]:
    if batch_size <= 0:
        return [queries] if queries else []
    
    result: list[list[str]] = []
    for index in range(0, len(queries), batch_size):
        chunk: list[str] = queries[index : index + batch_size]
        result.append(chunk)
    return result


def _normalize_context_list(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        cleaned = _normalize_space(value)
        lowered = cleaned.lower()
        if not cleaned or lowered in seen:
            continue
        normalized.append(cleaned)
        seen.add(lowered)
    return normalized


def _build_budget_signal_keywords(
    target_budget_signals: list[str] | None,
    *,
    target_language: str | None,
    discovery_profile: str,
) -> list[str]:
    keywords: list[str] = []
    language = _normalize_space(target_language).lower()
    for signal in _normalize_context_list(target_budget_signals):
        lowered = signal.lower()
        if "instagram" in lowered or "tiktok" in lowered:
            keywords.extend(["instagram", "tiktok"])
            if discovery_profile == "ecommerce":
                keywords.extend(["product video", "product content"])
        if "linktree" in lowered or "tienda oficial" in lowered or "tienda" in lowered or "store" in lowered or "shopify" in lowered:
            keywords.extend(["link in bio", "linktree"])
            if language == "en":
                keywords.extend(["online store", "shop now", "shopify"])
            else:
                keywords.extend(["tienda online", "shopify"])
        if "curso" in lowered or "infoproducto" in lowered:
            keywords.extend(["course", "digital products"] if language == "en" else ["curso", "infoproductos"])
        if "anuncio" in lowered or "ads" in lowered:
            keywords.extend(["meta ads", "facebook ads"] if language == "en" else ["anuncios", "meta ads"])
        if "producto" in lowered:
            keywords.extend(["product video", "product content"] if language == "en" else ["contenido de producto", "productos"])
        if "seguidores" in lowered and discovery_profile == "creator_coach":
            keywords.extend(["creador", "marca personal"])
        if "branding" in lowered or "landing" in lowered:
            keywords.extend(["brand", "landing page"] if language == "en" else ["branding", "landing"])

    deduped: list[str] = []
    for keyword in keywords:
        if keyword not in deduped:
            deduped.append(keyword)

    priority_order = [
        "shop now",
        "product video",
        "product content",
        "link in bio",
        "linktree",
        "online store",
        "tienda online",
        "shopify",
        "curso",
        "course",
        "digital products",
        "infoproductos",
        "instagram",
        "tiktok",
        "meta ads",
        "facebook ads",
        "anuncios",
        "creador",
        "marca personal",
    ]
    priority_map = {keyword: index for index, keyword in enumerate(priority_order)}
    return sorted(deduped, key=lambda keyword: priority_map.get(keyword, len(priority_order)))


def _filter_budget_signal_keywords_for_niche(keywords: list[str], target_niche: str | None) -> list[str]:
    niche = _normalize_space(target_niche)
    if not niche:
        return keywords

    generic_social_keywords = {
        "instagram",
        "tiktok",
        "link in bio",
        "linktree",
        "meta ads",
        "facebook ads",
        "anuncios",
        "creador",
        "product video",
        "product content",
        "shop now",
    }
    filtered = [
        keyword
        for keyword in keywords
        if keyword in generic_social_keywords or _fragment_matches_target_niche(keyword, niche)
    ]
    return filtered or keywords


def _derive_contextual_negative_terms(
    *,
    user_profession: str | None,
    target_niche: str | None,
    user_target_offer_focus: str | None,
    user_service_offers: list[str] | None,
    user_service_constraints: list[str] | None,
    ai_negative_terms: list[str] | None = None,
) -> tuple[str, ...]:
    searchable_text = " ".join(
        [
            _normalize_space(target_niche),
            _normalize_space(user_target_offer_focus),
            " ".join(_normalize_context_list(user_service_offers)),
            " ".join(_normalize_context_list(user_service_constraints)),
        ]
    ).lower()

    profession = _normalize_space(user_profession).lower()
    is_creative_role = any(
        role in profession 
        for role in ["video", "editor", "community", "social", "creador", "diseñador", "designer", "web", "desarrollador", "developer", "seo", "cro"]
    )

    extra_terms: list[str] = list(ai_negative_terms) if ai_negative_terms else []
    if any(
        token in searchable_text
        for token in (
            "ecommerce",
            "tienda online",
            "shopify",
            "academia online",
            "cursos online",
            "productos digitales",
            "infoproductos",
        )
    ):
        extra_terms.extend(SERVICE_PROVIDER_EXCLUSION_TERMS)
    if any(token in searchable_text for token in ("ecommerce", "tienda online", "shopify", "dropshipping")):
        extra_terms.extend(ECOMMERCE_NEGATIVE_TERMS)

    deduped_terms: list[str] = []
    for term in [*NEGATIVE_DISCOVERY_TERMS, *extra_terms]:
        # If it's a creative role, don't exclude social media or visual platforms
        if is_creative_role and term in ("-pinterest", "-linkedin", "-instagram", "-tiktok", "-youtube"):
            continue
        if term not in deduped_terms:
            deduped_terms.append(term)
    return tuple(deduped_terms)


def _apply_negative_terms(query: str, negative_terms: tuple[str, ...] = NEGATIVE_DISCOVERY_TERMS) -> str:
    normalized_query = _normalize_space(query)
    if not normalized_query:
        return ""

    lowered_query = normalized_query.lower()
    suffix_parts = [term for term in negative_terms if term.lower() not in lowered_query]
    if not suffix_parts:
        return normalized_query
    return _normalize_space(f"{normalized_query} {' '.join(suffix_parts)}")


def recommend_candidate_cap(target_accepted_results: int) -> int:
    accepted_target = max(int(target_accepted_results or 1), 1)
    return max(DEFAULT_MIN_CANDIDATES, accepted_target * DEFAULT_CANDIDATE_MULTIPLIER)


def resolve_candidate_batch_size(*, target_accepted_results: int, candidate_cap: int) -> int:
    if candidate_cap <= 0:
        return 0
    proposed = max(3, min(DEFAULT_CANDIDATE_BATCH_SIZE, int(target_accepted_results or 1) + 1))
    return min(candidate_cap, proposed)


def resolve_discovery_batch_budget(*, target_accepted_results: int, candidate_cap: int, remaining_budget: int) -> int:
    if remaining_budget <= 0 or candidate_cap <= 0:
        return 0
    candidate_batch_size = resolve_candidate_batch_size(
        target_accepted_results=target_accepted_results,
        candidate_cap=candidate_cap,
    )
    proposed = max(DEFAULT_MIN_CANDIDATES, candidate_batch_size * 2)
    return min(remaining_budget, proposed)


def resolve_capture_targets(
    *,
    max_results_legacy: int,
    target_accepted_results: int | None,
    max_candidates_to_process: int | None,
    seed_urls_count: int = 0,
) -> dict[str, int]:
    accepted_target = int(target_accepted_results or max_results_legacy or 1)

    if max_candidates_to_process is not None:
        candidate_cap = int(max_candidates_to_process)
    elif seed_urls_count > 0:
        candidate_cap = seed_urls_count
    else:
        candidate_cap = recommend_candidate_cap(accepted_target)

    candidate_cap = max(candidate_cap, min(seed_urls_count, accepted_target) if seed_urls_count else accepted_target)

    return {
        "target_accepted_results": accepted_target,
        "max_candidates_to_process": candidate_cap,
    }


def determine_capture_stop_reason(
    *,
    accepted_count: int,
    target_accepted_results: int,
    processed_count: int,
    candidate_cap: int,
    discovered_candidates: int,
    exhaustive_candidate_scan: bool = False,
) -> str:
    if not exhaustive_candidate_scan and target_accepted_results > 0 and accepted_count >= target_accepted_results:
        return "target_reached"
    if processed_count >= candidate_cap and discovered_candidates >= candidate_cap:
        return "candidate_cap_reached"
    return "discovery_exhausted"


def build_discovery_queries(
    *,
    search_query: str | None,
    user_profession: str | None = None,
    user_technologies: list[str] | None = None,
    target_niche: str | None,
    target_location: str | None,
    target_language: str | None,
    user_service_offers: list[str] | None = None,
    user_service_constraints: list[str] | None = None,
    user_target_offer_focus: str | None = None,
    target_budget_signals: list[str] | None = None,
    ai_dork_queries: list[str] | None = None,
    ai_negative_terms: list[str] | None = None,
    max_queries: int = MAX_DISCOVERY_QUERIES,
) -> list[str]:
    raw_base_query = _normalize_space(search_query)
    raw_niche = _normalize_space(target_niche)
    location = resolve_discovery_target_location(
        search_query=raw_base_query,
        target_location=target_location,
        target_niche=raw_niche,
    )
    language = _normalize_space(target_language).lower()
    discovery_profile = _resolve_discovery_profile(
        search_query=raw_base_query,
        target_niche=raw_niche,
        user_target_offer_focus=user_target_offer_focus,
        target_budget_signals=target_budget_signals,
    )
    base_query = _localize_query_fragment(raw_base_query, language)
    niche = _localize_query_fragment(raw_niche, language)

    if not base_query and niche and location:
        base_query = f"{niche} {location}"
    elif not base_query and niche:
        base_query = niche
    elif not base_query and location:
        base_query = location

    if not base_query:
        return []

    queries: list[str] = []
    niche_location_query = _normalize_space(f"{niche} {location}") if niche and location else niche or location or ""
    geo_base_query = _normalize_space(f"{base_query} {location}") if location and not _query_contains_token(base_query, location) else base_query
    intent_seeds = _derive_intent_seeds(search_query=base_query, target_niche=niche, location=location)
    localized_intent_seeds = [_normalize_space(f"{intent_seed} {location}") if location else intent_seed for intent_seed in intent_seeds]
    negative_terms = _derive_contextual_negative_terms(
        target_niche=niche,
        user_profession=user_profession,
        user_target_offer_focus=user_target_offer_focus,
        user_service_offers=user_service_offers,
        user_service_constraints=user_service_constraints,
        ai_negative_terms=ai_negative_terms,
    )
    budget_signal_keywords = _filter_budget_signal_keywords_for_niche(
        _build_budget_signal_keywords(
            target_budget_signals,
            target_language=language,
            discovery_profile=discovery_profile,
        ),
        niche,
    )

    if ai_dork_queries:
        for dork in ai_dork_queries:
            _append_query(queries, _apply_negative_terms(dork, negative_terms))

    if base_query and niche and _normalize_space(base_query).lower() == niche.lower():
        _append_query(queries, base_query)
    _append_query(queries, niche_location_query)
    for localized_intent_seed in localized_intent_seeds[:3]:
        _append_query(queries, localized_intent_seed)

    language_hints = LANGUAGE_DISCOVERY_HINTS.get(language or "es", LANGUAGE_DISCOVERY_HINTS["es"])
    primary_intent_seed = niche_location_query or geo_base_query or base_query

    profession = _normalize_space(user_profession).lower()
    needs_social_profiles = any(
        role in profession 
        for role in ["video", "editor", "community", "social", "creador", "diseño", "designer"]
    )
    
    if needs_social_profiles:
        social_intent_hints = [*budget_signal_keywords[:3], *PROFILE_SOCIAL_HINTS.get(discovery_profile, PROFILE_SOCIAL_HINTS["generic"])]
        for intent_seed in intent_seeds[:2]:
            localized_seed = _normalize_space(f"{intent_seed} {location}") if location else intent_seed
            _append_query(queries, _apply_negative_terms(f"{localized_seed} site:instagram.com", negative_terms))
            _append_query(queries, _apply_negative_terms(f"{localized_seed} site:tiktok.com", negative_terms))
            for hint in social_intent_hints[:3]:
                _append_query(
                    queries,
                    _apply_negative_terms(f"{localized_seed} {hint} site:instagram.com", negative_terms),
                )
                _append_query(
                    queries,
                    _apply_negative_terms(f"{localized_seed} {hint} site:tiktok.com", negative_terms),
                )
        _append_query(queries, _apply_negative_terms(f"{primary_intent_seed} site:instagram.com", negative_terms))
        _append_query(queries, _apply_negative_terms(f"{primary_intent_seed} site:tiktok.com", negative_terms))
        for hint in [*budget_signal_keywords[:2], *SOCIAL_PLATFORM_QUERY_HINTS[:2]]:
            _append_query(
                queries,
                _apply_negative_terms(f"{primary_intent_seed} {hint} site:instagram.com", negative_terms),
            )
            _append_query(
                queries,
                _apply_negative_terms(f"{primary_intent_seed} {hint} site:tiktok.com", negative_terms),
            )

    if discovery_profile == "ecommerce":
        _append_query(queries, _apply_negative_terms(f"{primary_intent_seed} {language_hints['shop']}", negative_terms))
        _append_query(queries, _apply_negative_terms(f"{primary_intent_seed} {language_hints['products']}", negative_terms))
        _append_query(queries, _apply_negative_terms(f"{primary_intent_seed} {language_hints['collections']}", negative_terms))

    if user_technologies:
        tech_string = " ".join(_normalize_context_list(user_technologies)).lower()
        if "shopify" in tech_string and discovery_profile == "ecommerce":
            _append_query(queries, _apply_negative_terms(f"{primary_intent_seed} \"powered by shopify\"", negative_terms))
        if "wordpress" in tech_string:
            _append_query(queries, _apply_negative_terms(f"{primary_intent_seed} \"creado con wordpress\"", negative_terms))

    _append_query(queries, _apply_negative_terms(f"{primary_intent_seed} {language_hints['official']}", negative_terms))
    _append_query(queries, _apply_negative_terms(f"{primary_intent_seed} {language_hints['contact']}", negative_terms))
    _append_query(queries, _apply_negative_terms(f"{primary_intent_seed} {language_hints['services']}", negative_terms))
    for intent_seed in intent_seeds[:2]:
        localized_seed = _normalize_space(f"{intent_seed} {location}") if location else intent_seed
        _append_query(queries, _apply_negative_terms(f"{localized_seed} {language_hints['official']}", negative_terms))
        _append_query(queries, _apply_negative_terms(f"{localized_seed} {language_hints['contact']}", negative_terms))
    for localized_intent_seed in localized_intent_seeds[3:]:
        _append_query(queries, localized_intent_seed)

    if geo_base_query:
        _append_query(queries, geo_base_query)
    if base_query and len(intent_seeds) <= 1:
        _append_query(queries, base_query)

    if niche and not _query_contains_token(base_query, niche):
        _append_query(queries, _apply_negative_terms(f"{base_query} {niche}", negative_terms))

    deduped_queries: list[str] = []
    for query in queries:
        normalized = _normalize_space(query)
        if not normalized or normalized in deduped_queries:
            continue
        deduped_queries.append(normalized)
        if len(deduped_queries) >= max_queries:
            break

    return deduped_queries


def build_retry_discovery_queries(
    *,
    search_query: str | None,
    user_profession: str | None = None,
    user_technologies: list[str] | None = None,
    target_niche: str | None,
    target_location: str | None,
    target_language: str | None,
    user_service_offers: list[str] | None = None,
    user_service_constraints: list[str] | None = None,
    user_target_offer_focus: str | None = None,
    target_budget_signals: list[str] | None = None,
) -> list[str]:
    raw_base_query = _normalize_space(search_query)
    raw_niche = _normalize_space(target_niche)
    location = resolve_discovery_target_location(
        search_query=raw_base_query,
        target_location=target_location,
        target_niche=raw_niche,
    )
    language = _normalize_space(target_language).lower()
    discovery_profile = _resolve_discovery_profile(
        search_query=raw_base_query,
        target_niche=raw_niche,
        user_target_offer_focus=user_target_offer_focus,
        target_budget_signals=target_budget_signals,
    )
    base_query = _localize_query_fragment(raw_base_query, language)
    niche = _localize_query_fragment(raw_niche, language)
    language_hints = LANGUAGE_DISCOVERY_HINTS.get(language or "es", LANGUAGE_DISCOVERY_HINTS["es"])
    intent_seeds = _derive_intent_seeds(search_query=base_query, target_niche=niche, location=location)
    negative_terms = _derive_contextual_negative_terms(
        user_profession=user_profession,
        target_niche=niche,
        user_target_offer_focus=user_target_offer_focus,
        user_service_offers=user_service_offers,
        user_service_constraints=user_service_constraints,
    )
    budget_signal_keywords = _filter_budget_signal_keywords_for_niche(
        _build_budget_signal_keywords(
            target_budget_signals,
            target_language=language,
            discovery_profile=discovery_profile,
        ),
        niche,
    )

    intent_seed = _normalize_space(f"{niche} {location}") or niche or _normalize_space(f"{base_query} {location}") or base_query
    if not intent_seed:
        return []

    retry_queries: list[str] = []

    for hint in language_hints.get("commercial", []):
        _append_query(retry_queries, _apply_negative_terms(f"{intent_seed} {hint}", negative_terms))

    profession = _normalize_space(user_profession).lower()
    needs_social_profiles = any(
        role in profession 
        for role in ["video", "editor", "community", "social", "creador", "diseño", "designer"]
    )
    if needs_social_profiles:
        _append_query(retry_queries, _apply_negative_terms(f"{intent_seed} site:instagram.com", negative_terms))
        _append_query(retry_queries, _apply_negative_terms(f"{intent_seed} site:tiktok.com", negative_terms))
        for hint in [*budget_signal_keywords[:2], *PROFILE_RETRY_SOCIAL_HINTS.get(discovery_profile, PROFILE_RETRY_SOCIAL_HINTS["generic"])]:
            _append_query(
                retry_queries,
                _apply_negative_terms(f"{intent_seed} {hint} site:instagram.com", negative_terms),
            )
            _append_query(
                retry_queries,
                _apply_negative_terms(f"{intent_seed} {hint} site:tiktok.com", negative_terms),
            )

    for hint in language_hints.get("locations", []):
        _append_query(retry_queries, _apply_negative_terms(f"{intent_seed} {hint}", negative_terms))

    if discovery_profile == "ecommerce":
        _append_query(retry_queries, _apply_negative_terms(f"{intent_seed} {language_hints['shop']}", negative_terms))
        _append_query(retry_queries, _apply_negative_terms(f"{intent_seed} {language_hints['products']}", negative_terms))

    for derived_seed in intent_seeds[:4]:
        localized_seed = _normalize_space(f"{derived_seed} {location}") if location else derived_seed
        for hint in language_hints.get("commercial", []):
            _append_query(retry_queries, _apply_negative_terms(f"{localized_seed} {hint}", negative_terms))

    if niche and base_query and not _query_contains_token(base_query, niche):
        _append_query(retry_queries, _apply_negative_terms(f"{niche} {location} {language_hints['official']}", negative_terms))
        _append_query(retry_queries, _apply_negative_terms(f"{niche} {location} {language_hints['contact']}", negative_terms))

    if location and base_query and not _query_contains_token(base_query, location):
        _append_query(retry_queries, _apply_negative_terms(f"{base_query} {location}", negative_terms))

    deduped_queries: list[str] = []
    for query in retry_queries:
        normalized = _normalize_space(query)
        if normalized and normalized not in deduped_queries:
            deduped_queries.append(normalized)

    return deduped_queries


def _infer_query_platform(query: str) -> str:
    normalized_query = _normalize_space(query).lower()
    if "site:instagram.com" in normalized_query:
        return "instagram"
    if "site:tiktok.com" in normalized_query:
        return "tiktok"
    if any(domain in normalized_query for domain in ("site:linktr.ee", "site:beacons.ai", "site:stan.store")):
        return "bio_hub"
    return "website"


def _normalize_query_context(query: str, context: dict[str, Any]) -> dict[str, Any]:
    return {
        "query": _normalize_space(query),
        "segment_id": _normalize_space(str(context.get("segment_id") or "generic_segment")) or "generic_segment",
        "family": _normalize_space(str(context.get("family") or "canonical_queries")) or "canonical_queries",
        "platform": _normalize_space(str(context.get("platform") or _infer_query_platform(query))) or "website",
        "iteration_index": int(context.get("iteration_index") or 0),
        "priority_bucket": _normalize_space(str(context.get("priority_bucket") or "")) or None,
        "segment_label": _normalize_space(str(context.get("segment_label") or "")) or None,
    }


def _append_query_item(query_items: list[dict[str, Any]], query: str | None, **context: Any) -> None:
    normalized_query = _normalize_space(query)
    if not normalized_query:
        return
    query_items.append(_normalize_query_context(normalized_query, context))


def _dedupe_query_items(query_items: list[dict[str, Any]], max_queries: int) -> list[dict[str, Any]]:
    deduped_items: list[dict[str, Any]] = []
    seen_queries: set[str] = set()
    for item in query_items:
        query = _normalize_space(str(item.get("query") or ""))
        lowered_query = query.lower()
        if not query or lowered_query in seen_queries:
            continue
        deduped_items.append({**item, "query": query})
        seen_queries.add(lowered_query)
        if len(deduped_items) >= max_queries:
            break
    return deduped_items


def _bucket_query_items(query_items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {
        "social_profile_queries": [],
        "social_commercial_queries": [],
        "website_validation_queries": [],
        "rescue_queries": [],
    }
    for item in query_items:
        family = str(item.get("family") or "rescue_queries").strip()
        if family not in buckets:
            buckets["rescue_queries"].append(item)
            continue
        buckets[family].append(item)
    return buckets


def _take_bucket_items(
    *,
    buckets: dict[str, list[dict[str, Any]]],
    family: str,
    limit: int,
) -> list[dict[str, Any]]:
    items = buckets.get(family, [])
    if limit <= 0:
        return []
    selected = items[:limit]
    buckets[family] = items[limit:]
    return selected


def _build_structured_query_context_map(query_items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        item["query"]: {
            "segment_id": item.get("segment_id"),
            "family": item.get("family"),
            "platform": item.get("platform"),
            "iteration_index": int(item.get("iteration_index") or 0),
            "priority_bucket": item.get("priority_bucket"),
            "segment_label": item.get("segment_label"),
        }
        for item in query_items
        if item.get("query")
    }


def _segment_query_seed_terms(segment: dict[str, Any]) -> list[str]:
    return _normalize_context_list(segment.get("seed_terms") or [segment.get("label") or ""])


def _segment_query_social_patterns(segment: dict[str, Any], dynamic_priority_signals: list[str]) -> list[str]:
    hints = [*(_normalize_context_list(segment.get("social_patterns") or [])), *dynamic_priority_signals]
    return _normalize_context_list(hints)


def _segment_query_website_patterns(segment: dict[str, Any], commercial_validation_signals: list[str]) -> list[str]:
    hints = [*(_normalize_context_list(segment.get("website_patterns") or [])), *commercial_validation_signals]
    return _normalize_context_list(hints)


def _segment_query_bio_hub_domains(discovery_profile: str) -> list[str]:
    return list(PROFILE_BIO_HUB_DOMAINS.get(discovery_profile, PROFILE_BIO_HUB_DOMAINS["generic"]))


def _soft_social_platform_hints(discovery_profile: str, language: str) -> list[str]:
    hints = ["instagram", "tiktok", "linktree"]
    if discovery_profile == "creator_coach":
        hints.extend(["mentoria", "programa", "contacto"] if language != "en" else ["mentoring", "program", "contact"])
    elif discovery_profile == "ecommerce":
        hints.extend(["shop now", "product video", "online store"] if language == "en" else ["tienda online", "contenido de producto", "shopify"])
    return _normalize_context_list(hints)


def _legacy_query_family(query: str) -> tuple[str, str]:
    normalized_query = _normalize_space(query).lower()
    platform = _infer_query_platform(query)
    if "site:" in normalized_query:
        return "social_commercial_queries", platform
    if any(token in normalized_query for token in ("contacto", "contact", "programa", "program", "oficial", "official", "mentoria", "mentoring")):
        return "website_validation_queries", platform
    return "rescue_queries", platform


def _apply_plan_negative_terms(
    query: str,
    *,
    ai_negative_terms: list[str] | None,
    dynamic_negative_signals: list[str] | None,
    base_negative_terms: tuple[str, ...],
) -> str:
    query_with_base = _apply_negative_terms(query, base_negative_terms)
    extra_negative_terms: list[str] = []
    seen_negative_terms: set[str] = set()
    for raw_term in [*(ai_negative_terms or []), *(dynamic_negative_signals or [])]:
        normalized_term = _normalize_space(raw_term)
        if not normalized_term:
            continue
        negative_term = normalized_term if normalized_term.startswith("-") else f"-{normalized_term}"
        lowered_term = negative_term.lower()
        if lowered_term in seen_negative_terms:
            continue
        extra_negative_terms.append(negative_term)
        seen_negative_terms.add(lowered_term)
        if len(extra_negative_terms) >= 6:
            break
    return _apply_negative_terms(query_with_base, tuple(extra_negative_terms)) if extra_negative_terms else query_with_base


def build_discovery_query_plan(
    *,
    search_query: str | None,
    user_profession: str | None = None,
    user_technologies: list[str] | None = None,
    target_niche: str | None,
    target_location: str | None,
    target_language: str | None,
    user_service_offers: list[str] | None = None,
    user_service_constraints: list[str] | None = None,
    user_target_offer_focus: str | None = None,
    target_budget_signals: list[str] | None = None,
    planner_output: dict[str, Any] | None = None,
    ai_dork_queries: list[str] | None = None,
    ai_negative_terms: list[str] | None = None,
    query_batch_size: int = DEFAULT_QUERY_BATCH_SIZE,
    max_queries: int = MAX_DISCOVERY_QUERIES,
    iteration_index: int = 0,
) -> dict[str, Any]:
    if not planner_output:
        canonical_queries = build_discovery_queries(
            search_query=search_query,
            user_profession=user_profession,
            user_technologies=user_technologies,
            target_niche=target_niche,
            target_location=target_location,
            target_language=target_language,
            user_service_offers=user_service_offers,
            user_service_constraints=user_service_constraints,
            user_target_offer_focus=user_target_offer_focus,
            target_budget_signals=target_budget_signals,
            ai_dork_queries=ai_dork_queries,
            ai_negative_terms=ai_negative_terms,
            max_queries=max_queries,
        )
        retry_queries = build_retry_discovery_queries(
            search_query=search_query,
            user_profession=user_profession,
            user_technologies=user_technologies,
            target_niche=target_niche,
            target_location=target_location,
            target_language=target_language,
            user_service_offers=user_service_offers,
            user_service_constraints=user_service_constraints,
            user_target_offer_focus=user_target_offer_focus,
            target_budget_signals=target_budget_signals,
        )
        query_items: list[dict[str, Any]] = []
        for query in canonical_queries:
            _append_query_item(
                query_items,
                query,
                segment_id="generic_segment",
                family="canonical_queries",
                platform=_infer_query_platform(query),
                iteration_index=iteration_index,
                priority_bucket="fallback",
                segment_label=_normalize_space(target_niche or search_query or "generic"),
            )
        for query in retry_queries:
            if query in canonical_queries:
                continue
            _append_query_item(
                query_items,
                query,
                segment_id="generic_segment",
                family="rescue_queries",
                platform=_infer_query_platform(query),
                iteration_index=iteration_index,
                priority_bucket="fallback",
                segment_label=_normalize_space(target_niche or search_query or "generic"),
            )
        deduped_items = _dedupe_query_items(query_items, max_queries)
        return {
            "queries": [item["query"] for item in deduped_items],
            "batches": _chunk_queries([item["query"] for item in deduped_items], query_batch_size),
            "query_items": deduped_items,
            "query_context_map": _build_structured_query_context_map(deduped_items),
            "family_distribution": {"fallback": len(deduped_items)},
        }

    raw_base_query = _normalize_space(search_query)
    raw_niche = _normalize_space(target_niche)
    location = resolve_discovery_target_location(
        search_query=raw_base_query,
        target_location=target_location,
        target_niche=raw_niche,
    )
    language = _normalize_space(target_language).lower()
    discovery_profile = _resolve_discovery_profile(
        search_query=raw_base_query,
        target_niche=raw_niche,
        user_target_offer_focus=user_target_offer_focus,
        target_budget_signals=target_budget_signals,
    )
    base_query = _localize_query_fragment(raw_base_query, language)
    niche = _localize_query_fragment(raw_niche, language)
    negative_terms = _derive_contextual_negative_terms(
        target_niche=niche,
        user_profession=user_profession,
        user_target_offer_focus=user_target_offer_focus,
        user_service_offers=user_service_offers,
        user_service_constraints=user_service_constraints,
        ai_negative_terms=ai_negative_terms,
    )
    language_hints = LANGUAGE_DISCOVERY_HINTS.get(language or "es", LANGUAGE_DISCOVERY_HINTS["es"])
    platform_priority = _normalize_context_list(planner_output.get("platform_priority") or ["instagram", "tiktok", "website"])
    segment_hypotheses = [
        segment
        for segment in (planner_output.get("segment_hypotheses") or [])
        if isinstance(segment, dict) and _normalize_space(str(segment.get("segment_id") or ""))
    ]
    dynamic_priority_signals = _normalize_context_list(planner_output.get("dynamic_priority_signals") or [])
    dynamic_negative_signals = _normalize_context_list(planner_output.get("dynamic_negative_signals") or [])
    commercial_validation_signals = _normalize_context_list(planner_output.get("commercial_validation_signals") or [])
    initial_wave_items: list[dict[str, Any]] = []
    query_items: list[dict[str, Any]] = []

    for initial_wave_item in (planner_output.get("initial_wave") or [])[:6]:
        if isinstance(initial_wave_item, dict):
            initial_query = initial_wave_item.get("query")
            initial_segment_id = initial_wave_item.get("segment_id")
            initial_family = initial_wave_item.get("family")
            initial_platform = initial_wave_item.get("platform")
            initial_segment_label = initial_wave_item.get("segment_label")
        else:
            initial_query = initial_wave_item
            initial_segment_id = "initial_wave"
            initial_family = "rescue_queries"
            initial_platform = _infer_query_platform(str(initial_wave_item or ""))
            initial_segment_label = _normalize_space(target_niche or search_query or "initial wave")
        _append_query_item(
            initial_wave_items,
            _apply_plan_negative_terms(
                str(initial_query or ""),
                ai_negative_terms=ai_negative_terms,
                dynamic_negative_signals=dynamic_negative_signals,
                base_negative_terms=negative_terms,
            ),
            segment_id=_normalize_space(str(initial_segment_id or "initial_wave")) or "initial_wave",
            family=_normalize_space(str(initial_family or "rescue_queries")) or "rescue_queries",
            platform=_normalize_space(str(initial_platform or _infer_query_platform(str(initial_query or "")))) or "website",
            iteration_index=iteration_index,
            priority_bucket="initial_wave",
            segment_label=_normalize_space(str(initial_segment_label or target_niche or search_query or "initial wave")),
        )

    for segment in segment_hypotheses[:8]:
        segment_id = _normalize_space(str(segment.get("segment_id") or "generic_segment"))
        segment_label = _normalize_space(str(segment.get("label") or segment_id.replace("_", " ")))
        seed_terms = _segment_query_seed_terms(segment)
        social_patterns = _segment_query_social_patterns(segment, dynamic_priority_signals)
        website_patterns = _segment_query_website_patterns(segment, commercial_validation_signals)
        geo_seed = _normalize_space(f"{seed_terms[0]} {location}") if seed_terms and location else (seed_terms[0] if seed_terms else "")

        for platform in platform_priority[:2]:
            site_clause = "site:instagram.com" if platform == "instagram" else "site:tiktok.com"
            for seed_term in seed_terms[:2]:
                localized_seed = _normalize_space(f"{seed_term} {location}") if location else seed_term
                _append_query_item(
                    query_items,
                    _apply_plan_negative_terms(
                        f"{localized_seed} {site_clause}",
                        ai_negative_terms=ai_negative_terms,
                        dynamic_negative_signals=dynamic_negative_signals,
                        base_negative_terms=negative_terms,
                    ),
                    segment_id=segment_id,
                    family="social_profile_queries",
                    platform=platform,
                    iteration_index=iteration_index,
                    priority_bucket="social",
                    segment_label=segment_label,
                )
                for hint in social_patterns[:2]:
                    _append_query_item(
                        query_items,
                        _apply_plan_negative_terms(
                            f"{localized_seed} {hint} {site_clause}",
                            ai_negative_terms=ai_negative_terms,
                            dynamic_negative_signals=dynamic_negative_signals,
                            base_negative_terms=negative_terms,
                        ),
                        segment_id=segment_id,
                        family="social_commercial_queries",
                        platform=platform,
                        iteration_index=iteration_index,
                        priority_bucket="social",
                        segment_label=segment_label,
                    )

        for hint in _soft_social_platform_hints(discovery_profile, language)[:3]:
            for seed_term in seed_terms[:2]:
                localized_seed = _normalize_space(f"{seed_term} {location}") if location else seed_term
                platform = "instagram" if hint == "instagram" else "tiktok" if hint == "tiktok" else "website"
                family = "rescue_queries" if platform != "website" else "website_validation_queries"
                _append_query_item(
                    query_items,
                    _apply_plan_negative_terms(
                        f"{localized_seed} {hint}",
                        ai_negative_terms=ai_negative_terms,
                        dynamic_negative_signals=dynamic_negative_signals,
                        base_negative_terms=negative_terms,
                    ),
                    segment_id=segment_id,
                    family=family,
                    platform=platform,
                    iteration_index=iteration_index,
                    priority_bucket="broad_social",
                    segment_label=segment_label,
                )

        for hub_domain in _segment_query_bio_hub_domains(discovery_profile):
            for seed_term in seed_terms[:2]:
                localized_seed = _normalize_space(f"{seed_term} {location}") if location else seed_term
                _append_query_item(
                    query_items,
                    _apply_plan_negative_terms(
                        f"{localized_seed} {hub_domain}",
                        ai_negative_terms=ai_negative_terms,
                        dynamic_negative_signals=dynamic_negative_signals,
                        base_negative_terms=negative_terms,
                    ),
                    segment_id=segment_id,
                    family="social_profile_queries",
                    platform="bio_hub",
                    iteration_index=iteration_index,
                    priority_bucket="social",
                    segment_label=segment_label,
                )
                for hint in social_patterns[:2]:
                    _append_query_item(
                        query_items,
                        _apply_plan_negative_terms(
                            f"{localized_seed} {hint} {hub_domain}",
                            ai_negative_terms=ai_negative_terms,
                            dynamic_negative_signals=dynamic_negative_signals,
                            base_negative_terms=negative_terms,
                        ),
                        segment_id=segment_id,
                        family="social_commercial_queries",
                        platform="bio_hub",
                        iteration_index=iteration_index,
                        priority_bucket="social",
                        segment_label=segment_label,
                    )

        for website_hint in website_patterns[:2]:
            _append_query_item(
                query_items,
                _apply_plan_negative_terms(
                    f"{geo_seed or segment_label} {website_hint}",
                    ai_negative_terms=ai_negative_terms,
                    dynamic_negative_signals=dynamic_negative_signals,
                    base_negative_terms=negative_terms,
                ),
                segment_id=segment_id,
                family="website_validation_queries",
                platform="website",
                iteration_index=iteration_index,
                priority_bucket="validation",
                segment_label=segment_label,
            )

        if discovery_profile == "ecommerce":
            for platform in platform_priority[:2]:
                site_clause = "site:instagram.com" if platform == "instagram" else "site:tiktok.com"
                ecommerce_hint = "shop now" if language == "en" else "tienda online"
                _append_query_item(
                    query_items,
                    _apply_plan_negative_terms(
                        f"{geo_seed or segment_label} {ecommerce_hint} {site_clause}",
                        ai_negative_terms=ai_negative_terms,
                        dynamic_negative_signals=dynamic_negative_signals,
                        base_negative_terms=negative_terms,
                    ),
                    segment_id=segment_id,
                    family="social_commercial_queries",
                    platform=platform,
                    iteration_index=iteration_index,
                    priority_bucket="social",
                    segment_label=segment_label,
                )
        if discovery_profile == "creator_coach":
            for platform in platform_priority[:2]:
                site_clause = "site:instagram.com" if platform == "instagram" else "site:tiktok.com"
                coach_hint = "book call" if language == "en" else "agendar"
                _append_query_item(
                    query_items,
                    _apply_plan_negative_terms(
                        f"{geo_seed or segment_label} {coach_hint} {site_clause}",
                        ai_negative_terms=ai_negative_terms,
                        dynamic_negative_signals=dynamic_negative_signals,
                        base_negative_terms=negative_terms,
                    ),
                    segment_id=segment_id,
                    family="social_commercial_queries",
                    platform=platform,
                    iteration_index=iteration_index,
                    priority_bucket="social",
                    segment_label=segment_label,
                )

    rescue_queries: list[str] = []
    rescue_queries.extend(ai_dork_queries or planner_output.get("optimal_dork_queries") or [])
    rescue_queries.extend(
        build_retry_discovery_queries(
            search_query=search_query,
            user_profession=user_profession,
            user_technologies=user_technologies,
            target_niche=target_niche,
            target_location=target_location,
            target_language=target_language,
            user_service_offers=user_service_offers,
            user_service_constraints=user_service_constraints,
            user_target_offer_focus=user_target_offer_focus,
            target_budget_signals=target_budget_signals,
        )[:6]
    )
    legacy_canonical_queries = build_discovery_queries(
        search_query=search_query,
        user_profession=user_profession,
        user_technologies=user_technologies,
        target_niche=target_niche,
        target_location=target_location,
        target_language=target_language,
        user_service_offers=user_service_offers,
        user_service_constraints=user_service_constraints,
        user_target_offer_focus=user_target_offer_focus,
        target_budget_signals=target_budget_signals,
        ai_dork_queries=None,
        ai_negative_terms=ai_negative_terms,
        max_queries=min(max_queries, 18),
    )
    for legacy_query in legacy_canonical_queries:
        family, platform = _legacy_query_family(legacy_query)
        _append_query_item(
            query_items,
            legacy_query,
            segment_id="legacy_backfill",
            family=family,
            platform=platform,
            iteration_index=iteration_index,
            priority_bucket="legacy",
            segment_label=_normalize_space(target_niche or search_query or "legacy"),
        )
    for rescue_query in rescue_queries:
        _append_query_item(
            query_items,
            _apply_plan_negative_terms(
                rescue_query,
                ai_negative_terms=ai_negative_terms,
                dynamic_negative_signals=dynamic_negative_signals,
                base_negative_terms=negative_terms,
            ),
            segment_id="adaptive_rescue",
            family="rescue_queries",
            platform=_infer_query_platform(rescue_query),
            iteration_index=iteration_index,
            priority_bucket="rescue",
            segment_label=_normalize_space(niche or base_query or "adaptive rescue"),
        )

    deduped_initial_wave = _dedupe_query_items(initial_wave_items, 6)
    initial_wave_queries = {str(item.get("query") or "").lower() for item in deduped_initial_wave}
    deduped_items = _dedupe_query_items(query_items, max_queries * 2)
    buckets = _bucket_query_items(
        [
            item
            for item in deduped_items
            if str(item.get("query") or "").lower() not in initial_wave_queries
        ]
    )
    selected_items = list(deduped_initial_wave)
    remaining_capacity = max(max_queries - len(selected_items), 0)
    if discovery_profile == "creator_coach":
        social_limit = max(1, int(remaining_capacity * 0.25)) if remaining_capacity else 0
        social_commercial_limit = max(1, int(remaining_capacity * 0.25)) if remaining_capacity else 0
        validation_limit = max(1, int(remaining_capacity * 0.25)) if remaining_capacity else 0
        rescue_limit = max(1, remaining_capacity - (social_limit + social_commercial_limit + validation_limit)) if remaining_capacity else 0
    else:
        social_limit = max(1, int(remaining_capacity * 0.35)) if remaining_capacity else 0
        social_commercial_limit = max(1, int(remaining_capacity * 0.35)) if remaining_capacity else 0
        validation_limit = max(1, int(remaining_capacity * 0.2)) if remaining_capacity else 0
        rescue_limit = max(1, remaining_capacity - (social_limit + social_commercial_limit + validation_limit)) if remaining_capacity else 0
    selected_items.extend(
        [
            *_take_bucket_items(buckets=buckets, family="social_profile_queries", limit=social_limit),
            *_take_bucket_items(buckets=buckets, family="social_commercial_queries", limit=social_commercial_limit),
            *_take_bucket_items(buckets=buckets, family="website_validation_queries", limit=validation_limit),
            *_take_bucket_items(buckets=buckets, family="rescue_queries", limit=rescue_limit),
        ]
    )
    if len(selected_items) < max_queries:
        for family in ("social_profile_queries", "social_commercial_queries", "website_validation_queries", "rescue_queries"):
            for item in buckets.get(family, []):
                selected_items.append(item)
                if len(selected_items) >= max_queries:
                    break
            if len(selected_items) >= max_queries:
                break
    selected_items = _dedupe_query_items(selected_items, max_queries)
    return {
        "queries": [item["query"] for item in selected_items],
        "batches": _chunk_queries([item["query"] for item in selected_items], query_batch_size),
        "query_items": selected_items,
        "query_context_map": _build_structured_query_context_map(selected_items),
        "family_distribution": {
            family: len([item for item in selected_items if item.get("family") == family])
            for family in ("social_profile_queries", "social_commercial_queries", "website_validation_queries", "rescue_queries")
        },
        "search_strategy": planner_output.get("search_strategy"),
    }


def build_discovery_query_batches(
    *,
    search_query: str | None,
    user_profession: str | None = None,
    user_technologies: list[str] | None = None,
    target_niche: str | None,
    target_location: str | None,
    target_language: str | None,
    user_service_offers: list[str] | None = None,
    user_service_constraints: list[str] | None = None,
    user_target_offer_focus: str | None = None,
    target_budget_signals: list[str] | None = None,
    planner_output: dict[str, Any] | None = None,
    ai_dork_queries: list[str] | None = None,
    ai_negative_terms: list[str] | None = None,
    query_batch_size: int = DEFAULT_QUERY_BATCH_SIZE,
) -> list[list[str]]:
    query_plan = build_discovery_query_plan(
        search_query=search_query,
        user_profession=user_profession,
        user_technologies=user_technologies,
        target_niche=target_niche,
        target_location=target_location,
        target_language=target_language,
        user_service_offers=user_service_offers,
        user_service_constraints=user_service_constraints,
        user_target_offer_focus=user_target_offer_focus,
        target_budget_signals=target_budget_signals,
        planner_output=planner_output,
        ai_dork_queries=ai_dork_queries,
        ai_negative_terms=ai_negative_terms,
        query_batch_size=query_batch_size,
    )
    return query_plan["batches"]


def build_discovery_metadata(entry: dict[str, Any] | None, queries: list[str]) -> dict[str, Any]:
    entry = entry or {}
    query_context = entry.get("query_context") if isinstance(entry.get("query_context"), dict) else {}
    return {
        "source_query": entry.get("query"),
        "serp_position": entry.get("position"),
        "title": entry.get("title"),
        "snippet": entry.get("snippet"),
        "discovery_confidence": entry.get("discovery_confidence"),
        "business_likeness_score": entry.get("business_likeness_score"),
        "website_result_score": entry.get("website_result_score"),
        "social_profile_score": entry.get("social_profile_score"),
        "result_kind": entry.get("result_kind"),
        "discovery_reasons": entry.get("discovery_reasons"),
        "seed_source_url": entry.get("seed_source_url"),
        "seed_source_type": entry.get("seed_source_type"),
        "query_context": query_context,
        "segment_id": query_context.get("segment_id"),
        "query_family": query_context.get("family"),
        "query_platform": query_context.get("platform"),
        "query_iteration_index": query_context.get("iteration_index"),
        "queries": queries,
    }
