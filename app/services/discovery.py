from __future__ import annotations

from typing import Any

DEFAULT_CANDIDATE_MULTIPLIER = 4
DEFAULT_MIN_CANDIDATES = 5
MAX_DISCOVERY_QUERIES = 6
DEFAULT_QUERY_BATCH_SIZE = 2
DEFAULT_CANDIDATE_BATCH_SIZE = 5
NEGATIVE_DISCOVERY_TERMS = (
    "-blog",
    "-ideas",
    "-noticias",
    "-revista",
    "-g2",
    "-pinterest",
    "-linkedin",
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


def _normalize_space(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def _query_contains_token(query: str, token: str) -> bool:
    normalized_query = f" {_normalize_space(query).lower()} "
    normalized_token = f" {_normalize_space(token).lower()} "
    return bool(token) and normalized_token in normalized_query


def _append_query(queries: list[str], candidate: str | None) -> None:
    normalized = _normalize_space(candidate)
    if normalized and normalized not in queries:
        queries.append(normalized)


def _chunk_queries(queries: list[str], batch_size: int) -> list[list[str]]:
    if batch_size <= 0:
        return [queries] if queries else []
    return [queries[index : index + batch_size] for index in range(0, len(queries), batch_size)]


def _apply_negative_terms(query: str) -> str:
    normalized_query = _normalize_space(query)
    if not normalized_query:
        return ""

    lowered_query = normalized_query.lower()
    suffix_parts = [term for term in NEGATIVE_DISCOVERY_TERMS if term.lower() not in lowered_query]
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

    _append_query(queries, base_query)
    _append_query(queries, niche_location_query)
    _append_query(queries, geo_base_query)

    language_hints = LANGUAGE_DISCOVERY_HINTS.get(language or "es", LANGUAGE_DISCOVERY_HINTS["es"])
    intent_seed = niche_location_query or geo_base_query or base_query

    _append_query(queries, _apply_negative_terms(f"{intent_seed} {language_hints['official']}"))
    _append_query(queries, _apply_negative_terms(f"{intent_seed} {language_hints['contact']}"))
    _append_query(queries, _apply_negative_terms(f"{intent_seed} {language_hints['services']}"))

    if niche and not _query_contains_token(base_query, niche):
        _append_query(queries, _apply_negative_terms(f"{base_query} {niche}"))

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
) -> list[str]:
    base_query = _normalize_space(search_query)
    niche = _normalize_space(target_niche)
    location = _normalize_space(target_location)
    language = _normalize_space(target_language).lower()
    language_hints = LANGUAGE_DISCOVERY_HINTS.get(language or "es", LANGUAGE_DISCOVERY_HINTS["es"])

    intent_seed = _normalize_space(f"{niche} {location}") or niche or _normalize_space(f"{base_query} {location}") or base_query
    if not intent_seed:
        return []

    retry_queries: list[str] = []

    for hint in language_hints.get("commercial", []):
        _append_query(retry_queries, _apply_negative_terms(f"{intent_seed} {hint}"))

    for hint in language_hints.get("locations", []):
        _append_query(retry_queries, _apply_negative_terms(f"{intent_seed} {hint}"))

    if niche and base_query and not _query_contains_token(base_query, niche):
        _append_query(retry_queries, _apply_negative_terms(f"{niche} {location} {language_hints['official']}"))
        _append_query(retry_queries, _apply_negative_terms(f"{niche} {location} {language_hints['contact']}"))

    if location and base_query and not _query_contains_token(base_query, location):
        _append_query(retry_queries, _apply_negative_terms(f"{base_query} {location}"))

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
    query_batch_size: int = DEFAULT_QUERY_BATCH_SIZE,
) -> list[list[str]]:
    canonical_queries = build_discovery_queries(
        search_query=search_query,
        target_niche=target_niche,
        target_location=target_location,
        target_language=target_language,
    )
    retry_queries = build_retry_discovery_queries(
        search_query=search_query,
        target_niche=target_niche,
        target_location=target_location,
        target_language=target_language,
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
