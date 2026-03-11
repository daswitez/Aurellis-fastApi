from __future__ import annotations

import re
from typing import Any

MAX_OBSERVED_SIGNALS = 6
MAX_INFERRED_OPPORTUNITIES = 5
_LEADING_PUNCTUATION = "-*0123456789.)] "
_CAUTIOUS_PREFIX = "Posible oportunidad: "
_CAUTIOUS_MARKERS = (
    "posible oportunidad:",
    "oportunidad probable:",
    "podria ",
    "podría ",
    "convendria ",
    "convendría ",
    "seria valioso ",
    "sería valioso ",
)


def _normalize_list_items(raw_value: Any, *, max_items: int) -> list[str]:
    if not isinstance(raw_value, list):
        return []

    cleaned_items: list[str] = []
    seen: set[str] = set()
    for item in raw_value:
        if not isinstance(item, str):
            continue
        normalized = item.strip().strip(_LEADING_PUNCTUATION).strip()
        normalized = re.sub(r"\s+", " ", normalized).strip(" .,:;")
        if not normalized:
            continue
        dedupe_token = normalized.casefold()
        if dedupe_token in seen:
            continue
        seen.add(dedupe_token)
        cleaned_items.append(normalized)
        if len(cleaned_items) >= max_items:
            break
    return cleaned_items


def normalize_observed_signals(raw_value: Any, *, max_items: int = MAX_OBSERVED_SIGNALS) -> list[str]:
    return _normalize_list_items(raw_value, max_items=max_items)


def normalize_inferred_opportunities(raw_value: Any, *, max_items: int = MAX_INFERRED_OPPORTUNITIES) -> list[str]:
    opportunities = _normalize_list_items(raw_value, max_items=max_items)
    normalized_opportunities: list[str] = []

    for item in opportunities:
        lowered = item.casefold()
        if any(lowered.startswith(marker) for marker in _CAUTIOUS_MARKERS):
            normalized_opportunities.append(item)
            continue
        normalized_opportunities.append(f"{_CAUTIOUS_PREFIX}{item[:1].lower()}{item[1:]}")

    return normalized_opportunities


def build_legacy_pain_points(
    *,
    inferred_opportunities: list[str] | None = None,
    fallback_pain_points: Any = None,
) -> list[str]:
    normalized_inferred = normalize_inferred_opportunities(inferred_opportunities or [])
    if normalized_inferred:
        return normalized_inferred
    return normalize_inferred_opportunities(fallback_pain_points or [])
