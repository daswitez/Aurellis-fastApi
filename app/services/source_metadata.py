VALID_SOURCE_TYPES = {
    "duckduckgo_search",
    "mock_search",
    "seed_url",
    "manual",
    "enrichment",
}

VALID_DISCOVERY_METHODS = {
    "search_query",
    "seed_url",
    "manual",
    "enrichment",
}

SOURCE_TYPE_ALIASES = {
    "mock": "mock_search",
    "verification": "manual",
    "url_list": "seed_url",
    "ddg": "duckduckgo_search",
}

DISCOVERY_METHOD_ALIASES = {
    "verification": "manual",
    "url_list": "seed_url",
    "ddg": "search_query",
}


def normalize_source_type(value: str | None) -> str | None:
    if not value:
        return None
    normalized = SOURCE_TYPE_ALIASES.get(value, value)
    return normalized if normalized in VALID_SOURCE_TYPES else None


def normalize_discovery_method(value: str | None) -> str | None:
    if not value:
        return None
    normalized = DISCOVERY_METHOD_ALIASES.get(value, value)
    return normalized if normalized in VALID_DISCOVERY_METHODS else None
