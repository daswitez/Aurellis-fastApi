from __future__ import annotations

import re
from typing import Any

DEFAULT_CANDIDATE_MULTIPLIER = 4
DEFAULT_MIN_CANDIDATES = 5
MAX_DISCOVERY_QUERIES = 12
DEFAULT_QUERY_BATCH_SIZE = 2
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
        "commercial": ["empresa", "negocio", "servicios"],
        "locations": ["ubicaciones", "sedes"],
    },
    "en": {
        "official": "official site",
        "contact": "contact",
        "services": "services",
        "commercial": ["business", "company", "services"],
        "locations": ["locations", "branches"],
    },
    "pt": {
        "official": "site oficial",
        "contact": "contato",
        "services": "servicos",
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


def _normalize_space(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def _query_contains_token(query: str, token: str) -> bool:
    normalized_query = f" {_normalize_space(query).lower()} "
    normalized_token = f" {_normalize_space(token).lower()} "
    return bool(token) and normalized_token in normalized_query


def _strip_generic_prefixes(value: str) -> str:
    normalized = _normalize_space(value)
    lowered = normalized.lower()
    for prefix in GENERIC_QUERY_PREFIXES:
        if lowered.startswith(prefix):
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
        cleaned_value = _strip_generic_prefixes(_remove_location_tokens(raw_value, location))
        if not cleaned_value:
            continue

        fragments = [fragment for fragment in INTENT_SPLIT_PATTERN.split(cleaned_value) if _normalize_space(fragment)]
        if not fragments:
            fragments = [cleaned_value]

        for fragment in fragments:
            variants: list[str] = []
            for variant in _expand_intent_variants(fragment):
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
    return [queries[index : index + batch_size] for index in range(0, len(queries), batch_size)]


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


def _derive_contextual_negative_terms(
    *,
    target_niche: str | None,
    user_target_offer_focus: str | None,
    user_service_offers: list[str] | None,
    user_service_constraints: list[str] | None,
) -> tuple[str, ...]:
    searchable_text = " ".join(
        [
            _normalize_space(target_niche),
            _normalize_space(user_target_offer_focus),
            " ".join(_normalize_context_list(user_service_offers)),
            " ".join(_normalize_context_list(user_service_constraints)),
        ]
    ).lower()

    extra_terms: list[str] = []
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

    deduped_terms: list[str] = []
    for term in [*NEGATIVE_DISCOVERY_TERMS, *extra_terms]:
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
) -> str:
    if target_accepted_results > 0 and accepted_count >= target_accepted_results:
        return "target_reached"
    if processed_count >= candidate_cap and discovered_candidates >= candidate_cap:
        return "candidate_cap_reached"
    return "discovery_exhausted"


def build_discovery_queries(
    *,
    search_query: str | None,
    target_niche: str | None,
    target_location: str | None,
    target_language: str | None,
    user_service_offers: list[str] | None = None,
    user_service_constraints: list[str] | None = None,
    user_target_offer_focus: str | None = None,
    max_queries: int = MAX_DISCOVERY_QUERIES,
) -> list[str]:
    base_query = _normalize_space(search_query)
    niche = _normalize_space(target_niche)
    location = _normalize_space(target_location)
    language = _normalize_space(target_language).lower()

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
        user_target_offer_focus=user_target_offer_focus,
        user_service_offers=user_service_offers,
        user_service_constraints=user_service_constraints,
    )

    _append_query(queries, base_query)
    _append_query(queries, niche_location_query)
    _append_query(queries, geo_base_query)
    for localized_intent_seed in localized_intent_seeds[:3]:
        _append_query(queries, localized_intent_seed)

    language_hints = LANGUAGE_DISCOVERY_HINTS.get(language or "es", LANGUAGE_DISCOVERY_HINTS["es"])
    primary_intent_seed = niche_location_query or geo_base_query or base_query

    _append_query(queries, _apply_negative_terms(f"{primary_intent_seed} {language_hints['official']}", negative_terms))
    _append_query(queries, _apply_negative_terms(f"{primary_intent_seed} {language_hints['contact']}", negative_terms))
    _append_query(queries, _apply_negative_terms(f"{primary_intent_seed} {language_hints['services']}", negative_terms))
    for intent_seed in intent_seeds[:2]:
        localized_seed = _normalize_space(f"{intent_seed} {location}") if location else intent_seed
        _append_query(queries, _apply_negative_terms(f"{localized_seed} {language_hints['official']}", negative_terms))
        _append_query(queries, _apply_negative_terms(f"{localized_seed} {language_hints['contact']}", negative_terms))
    for localized_intent_seed in localized_intent_seeds[3:]:
        _append_query(queries, localized_intent_seed)

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
    target_niche: str | None,
    target_location: str | None,
    target_language: str | None,
    user_service_offers: list[str] | None = None,
    user_service_constraints: list[str] | None = None,
    user_target_offer_focus: str | None = None,
) -> list[str]:
    base_query = _normalize_space(search_query)
    niche = _normalize_space(target_niche)
    location = _normalize_space(target_location)
    language = _normalize_space(target_language).lower()
    language_hints = LANGUAGE_DISCOVERY_HINTS.get(language or "es", LANGUAGE_DISCOVERY_HINTS["es"])
    intent_seeds = _derive_intent_seeds(search_query=base_query, target_niche=niche, location=location)
    negative_terms = _derive_contextual_negative_terms(
        target_niche=niche,
        user_target_offer_focus=user_target_offer_focus,
        user_service_offers=user_service_offers,
        user_service_constraints=user_service_constraints,
    )

    intent_seed = _normalize_space(f"{niche} {location}") or niche or _normalize_space(f"{base_query} {location}") or base_query
    if not intent_seed:
        return []

    retry_queries: list[str] = []

    for hint in language_hints.get("commercial", []):
        _append_query(retry_queries, _apply_negative_terms(f"{intent_seed} {hint}", negative_terms))

    for hint in language_hints.get("locations", []):
        _append_query(retry_queries, _apply_negative_terms(f"{intent_seed} {hint}", negative_terms))

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


def build_discovery_query_batches(
    *,
    search_query: str | None,
    target_niche: str | None,
    target_location: str | None,
    target_language: str | None,
    user_service_offers: list[str] | None = None,
    user_service_constraints: list[str] | None = None,
    user_target_offer_focus: str | None = None,
    query_batch_size: int = DEFAULT_QUERY_BATCH_SIZE,
) -> list[list[str]]:
    canonical_queries = build_discovery_queries(
        search_query=search_query,
        target_niche=target_niche,
        target_location=target_location,
        target_language=target_language,
        user_service_offers=user_service_offers,
        user_service_constraints=user_service_constraints,
        user_target_offer_focus=user_target_offer_focus,
    )
    retry_queries = build_retry_discovery_queries(
        search_query=search_query,
        target_niche=target_niche,
        target_location=target_location,
        target_language=target_language,
        user_service_offers=user_service_offers,
        user_service_constraints=user_service_constraints,
        user_target_offer_focus=user_target_offer_focus,
    )

    deduped_retry_queries = [query for query in retry_queries if query not in canonical_queries]
    return _chunk_queries(canonical_queries, query_batch_size) + _chunk_queries(deduped_retry_queries, query_batch_size)


def build_discovery_metadata(entry: dict[str, Any] | None, queries: list[str]) -> dict[str, Any]:
    entry = entry or {}
    return {
        "source_query": entry.get("query"),
        "serp_position": entry.get("position"),
        "title": entry.get("title"),
        "snippet": entry.get("snippet"),
        "discovery_confidence": entry.get("discovery_confidence"),
        "business_likeness_score": entry.get("business_likeness_score"),
        "discovery_reasons": entry.get("discovery_reasons"),
        "seed_source_url": entry.get("seed_source_url"),
        "seed_source_type": entry.get("seed_source_type"),
        "queries": queries,
    }
