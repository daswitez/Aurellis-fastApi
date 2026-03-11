from __future__ import annotations

import logging

from app.config import get_settings
from app.scraper.search_engines.ddg_search import DuckDuckGoHtmlSearchProvider
from app.scraper.search_engines.google_search import GoogleHtmlSearchProvider
from app.services.discovery_types import SearchDiscoveryEntry, SearchDiscoveryResult
from app.services.search_providers import BraveSearchProvider, SearchProvider

logger = logging.getLogger(__name__)

DEMO_FALLBACK_URLS = [
    "https://www.clinicaveterinariamiraflores.pe/",
    "https://www.veterinariarondon.com/",
    "https://www.veterinariaanimalpolis.pe/",
]
DEFAULT_SEARCH_PROVIDER_ORDER = ("duckduckgo_html", "google_html")


def _parse_provider_order(raw_value: str | None) -> list[str]:
    if not raw_value:
        return list(DEFAULT_SEARCH_PROVIDER_ORDER)
    return [item.strip().lower() for item in raw_value.split(",") if item.strip()]


def _build_providers() -> list[SearchProvider]:
    settings = get_settings()
    provider_order = _parse_provider_order(settings.SEARCH_PROVIDER_ORDER)
    providers: list[SearchProvider] = []

    for provider_name in provider_order:
        if provider_name == "brave_api":
            providers.append(BraveSearchProvider())
        elif provider_name in {"duckduckgo_html", "ddg_html", "duckduckgo"}:
            providers.append(DuckDuckGoHtmlSearchProvider())
        elif provider_name in {"google_html", "google"}:
            providers.append(GoogleHtmlSearchProvider())
        else:
            logger.warning("Proveedor de discovery desconocido: %s", provider_name)

    return providers


def _build_demo_result(queries: list[str], max_results: int, warning_message: str | None, excluded_results: list[dict]) -> SearchDiscoveryResult:
    demo_message = warning_message or f"No hubo resultados reales para queries: {queries!r}."
    return SearchDiscoveryResult(
        entries=[
            SearchDiscoveryEntry(
                url=url,
                query=queries[0] if queries else None,
                position=index,
                title="Demo result",
                snippet=demo_message,
                discovery_confidence="low",
            )
            for index, url in enumerate(DEMO_FALLBACK_URLS[:max_results], start=1)
        ],
        source_type="mock_search",
        discovery_method="search_query",
        warning_message=f"{demo_message} Se activo fallback demo.",
        queries=queries,
        excluded_results=excluded_results,
        provider_name="demo_fallback",
        provider_status="ok",
    )


async def discover_prospect_urls_by_queries(queries: list[str], max_results: int = 10) -> SearchDiscoveryResult:
    if not queries:
        return SearchDiscoveryResult(
            entries=[],
            source_type="duckduckgo_search",
            discovery_method="search_query",
            warning_message="No se enviaron queries de discovery.",
            queries=[],
            provider_name=None,
            provider_status="invalid_request",
            failure_reason="missing_queries",
        )

    settings = get_settings()
    warning_messages: list[str] = []
    excluded_results: list[dict] = []
    last_result: SearchDiscoveryResult | None = None
    providers = [provider for provider in _build_providers() if provider.is_available()]

    if not providers:
        provider_warning = "No hay proveedores de discovery disponibles."
        if settings.DEMO_MODE:
            return _build_demo_result(queries, max_results, provider_warning, excluded_results)
        return SearchDiscoveryResult(
            entries=[],
            source_type="duckduckgo_search",
            discovery_method="search_query",
            warning_message=provider_warning,
            queries=queries,
            excluded_results=[],
            provider_name=None,
            provider_status="unavailable",
            failure_reason="no_providers_available",
        )

    for provider in providers:
        result = await provider.search(queries, max_results=max_results)
        last_result = result
        excluded_results.extend(result.excluded_results)
        if result.warning_message:
            warning_messages.append(result.warning_message)

        if result.entries:
            result.excluded_results = excluded_results
            result.warning_message = "; ".join(warning_messages) if warning_messages else None
            return result

    combined_warning = "; ".join(warning_messages) if warning_messages else None
    if settings.DEMO_MODE:
        return _build_demo_result(queries, max_results, combined_warning, excluded_results)

    if last_result is None:
        return SearchDiscoveryResult(
            entries=[],
            source_type="duckduckgo_search",
            discovery_method="search_query",
            warning_message=combined_warning or f"No hubo resultados reales para queries: {queries!r}.",
            queries=queries,
            excluded_results=excluded_results,
            provider_name=None,
            provider_status="no_results",
            failure_reason="no_results",
        )

    last_result.excluded_results = excluded_results
    last_result.warning_message = combined_warning or last_result.warning_message
    return last_result
