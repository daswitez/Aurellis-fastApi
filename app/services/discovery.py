from __future__ import annotations

from typing import Any


def _normalize_space(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def _query_contains_token(query: str, token: str) -> bool:
    normalized_query = f" {_normalize_space(query).lower()} "
    normalized_token = f" {_normalize_space(token).lower()} "
    return bool(token) and normalized_token in normalized_query


def build_discovery_queries(
    *,
    search_query: str | None,
    target_niche: str | None,
    target_location: str | None,
    target_language: str | None,
    max_queries: int = 3,
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

    queries: list[str] = [base_query]

    if location and not _query_contains_token(base_query, location):
        queries.append(_normalize_space(f"{base_query} {location}"))

    if language and language in {"es", "en", "pt", "fr", "de", "it"}:
        language_hints = {
            "es": "sitio oficial",
            "en": "official site",
            "pt": "site oficial",
            "fr": "site officiel",
            "de": "offizielle website",
            "it": "sito ufficiale",
        }
        queries.append(_normalize_space(f"{queries[0]} {language_hints[language]}"))
    elif niche and not _query_contains_token(base_query, niche):
        queries.append(_normalize_space(f"{queries[0]} {niche}"))

    deduped_queries: list[str] = []
    for query in queries:
        normalized = _normalize_space(query)
        if not normalized or normalized in deduped_queries:
            continue
        deduped_queries.append(normalized)
        if len(deduped_queries) >= max_queries:
            break

    return deduped_queries


def build_discovery_metadata(entry: dict[str, Any] | None, queries: list[str]) -> dict[str, Any]:
    entry = entry or {}
    return {
        "source_query": entry.get("query"),
        "serp_position": entry.get("position"),
        "title": entry.get("title"),
        "snippet": entry.get("snippet"),
        "discovery_confidence": entry.get("discovery_confidence"),
        "queries": queries,
    }
