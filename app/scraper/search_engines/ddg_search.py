import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

from app.scraper.http_client import FetchHtmlError, fetch_html
from app.services.discovery_ranker import (
    classify_discovery_candidate,
    clean_text,
    extract_official_site_from_seed_html as ranker_extract_official_site_from_seed_html,
    get_directory_seed_token,
    is_blocked_result,
    is_same_root_domain,
    looks_like_social_or_marketplace,
    score_business_likeness,
)
from app.services.discovery_types import SearchDiscoveryEntry, SearchDiscoveryResult
from app.services.search_providers.base import SearchProvider

logger = logging.getLogger(__name__)

# Thread pool for running synchronous duckduckgo-search in async context
_ddg_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ddg")


# ---------------------------------------------------------------------------
# Legacy HTML parsing (kept for offline fixture tests)
# ---------------------------------------------------------------------------

def _resolve_ddg_url(raw_url: str) -> str:
    url = raw_url.strip()
    if url.startswith("//duckduckgo.com"):
        query_string = parse_qs(urlparse(url).query)
        if "uddg" in query_string:
            return query_string["uddg"][0]
    return url


def _extract_result_url(result_node: Any) -> str:
    url_tag = result_node.find("a", class_="result__url")
    if url_tag and url_tag.get("href"):
        return _resolve_ddg_url(url_tag["href"])
    title_link = result_node.select_one(".result__title a")
    if title_link and title_link.get("href"):
        return _resolve_ddg_url(title_link["href"])
    return ""


def _extract_search_results(html: str, query: str, allow_social_profiles: bool = False) -> tuple[list[SearchDiscoveryEntry], list[dict[str, Any]]]:
    """Parse raw DDG HTML SERP page. Used by offline fixture tests."""
    soup = BeautifulSoup(html, "html.parser")
    entries: list[SearchDiscoveryEntry] = []
    excluded: list[dict[str, Any]] = []

    result_nodes = soup.select(".result")
    if not result_nodes:
        result_nodes = soup.find_all("div", class_="result results_links results_links_deep web-result")

    for result_node in result_nodes:
        title_tag = result_node.select_one(".result__title")
        snippet_tag = result_node.select_one(".result__snippet")
        url = _extract_result_url(result_node)
        title = clean_text(title_tag.get_text(" ", strip=True) if title_tag else "")
        snippet = clean_text(snippet_tag.get_text(" ", strip=True) if snippet_tag else "")

        if not url.startswith("http"):
            excluded.append({"url": url or None, "reason": "invalid_url", "query": query, "title": title, "snippet": snippet})
            continue

        blocked_reason = is_blocked_result(url, allow_social_profiles=allow_social_profiles)
        if blocked_reason:
            excluded.append({"url": url, "reason": blocked_reason, "query": query, "title": title, "snippet": snippet})
            continue

        classified = classify_discovery_candidate(url, title, snippet, allow_social_profiles=allow_social_profiles)
        business_score = classified["score"]
        business_reasons = classified["reasons"]
        exclusion_reason = classified["exclusion_reason"]
        if exclusion_reason:
            excluded.append(
                {
                    "url": url,
                    "reason": exclusion_reason,
                    "query": query,
                    "title": title,
                    "snippet": snippet,
                    "business_likeness_score": business_score,
                    "website_result_score": classified["website_result_score"],
                    "social_profile_score": classified["social_profile_score"],
                    "result_kind": classified["result_kind"],
                    "discovery_reasons": business_reasons,
                }
            )
            continue

        discovery_confidence = "medium"
        lowered_blob = f"{title} {snippet}".lower()
        if (
            "oficial" in lowered_blob
            or "official" in lowered_blob
            or classified["result_kind"] == "social_profile"
            or business_score >= 0.45
        ):
            discovery_confidence = "high"
        elif business_score <= 0.2:
            discovery_confidence = "low"

        entries.append(
            SearchDiscoveryEntry(
                url=url,
                query=query,
                title=title or None,
                snippet=snippet or None,
                discovery_confidence=discovery_confidence,
                business_likeness_score=business_score,
                website_result_score=classified["website_result_score"],
                social_profile_score=classified["social_profile_score"],
                result_kind=classified["result_kind"],
                discovery_reasons=business_reasons,
            )
        )

    entries.sort(
        key=lambda entry: (
            -(entry.business_likeness_score or 0.0),
            0 if entry.discovery_confidence == "high" else 1,
            len(entry.url),
        )
    )
    return entries, excluded


# ---------------------------------------------------------------------------
# Result processing (reuses existing business scoring pipeline)
# ---------------------------------------------------------------------------

def _process_ddg_results(
    raw_results: list[dict[str, Any]],
    query: str,
    allow_social_profiles: bool = False,
) -> tuple[list[SearchDiscoveryEntry], list[dict[str, Any]]]:
    """Process raw DDG API results through the business scoring pipeline."""
    entries: list[SearchDiscoveryEntry] = []
    excluded: list[dict[str, Any]] = []

    for raw in raw_results:
        url = (raw.get("href") or "").strip()
        title = clean_text(raw.get("title") or "")
        snippet = clean_text(raw.get("body") or "")

        if not url.startswith("http"):
            excluded.append({"url": url or None, "reason": "invalid_url", "query": query, "title": title, "snippet": snippet})
            continue

        blocked_reason = is_blocked_result(url, allow_social_profiles=allow_social_profiles)
        if blocked_reason:
            excluded.append({"url": url, "reason": blocked_reason, "query": query, "title": title, "snippet": snippet})
            continue

        classified = classify_discovery_candidate(url, title, snippet, allow_social_profiles=allow_social_profiles)
        business_score = classified["score"]
        business_reasons = classified["reasons"]
        exclusion_reason = classified["exclusion_reason"]
        if exclusion_reason:
            excluded.append(
                {
                    "url": url,
                    "reason": exclusion_reason,
                    "query": query,
                    "title": title,
                    "snippet": snippet,
                    "business_likeness_score": business_score,
                    "website_result_score": classified["website_result_score"],
                    "social_profile_score": classified["social_profile_score"],
                    "result_kind": classified["result_kind"],
                    "discovery_reasons": business_reasons,
                }
            )
            continue

        discovery_confidence = "medium"
        lowered_blob = f"{title} {snippet}".lower()
        if (
            "oficial" in lowered_blob
            or "official" in lowered_blob
            or classified["result_kind"] == "social_profile"
            or business_score >= 0.45
        ):
            discovery_confidence = "high"
        elif business_score <= 0.2:
            discovery_confidence = "low"

        entries.append(
            SearchDiscoveryEntry(
                url=url,
                query=query,
                title=title or None,
                snippet=snippet or None,
                discovery_confidence=discovery_confidence,
                business_likeness_score=business_score,
                website_result_score=classified["website_result_score"],
                social_profile_score=classified["social_profile_score"],
                result_kind=classified["result_kind"],
                discovery_reasons=business_reasons,
            )
        )

    entries.sort(
        key=lambda entry: (
            -(entry.business_likeness_score or 0.0),
            0 if entry.discovery_confidence == "high" else 1,
            len(entry.url),
        )
    )
    return entries, excluded


# ---------------------------------------------------------------------------
# Anti-bot detection (kept for backward compatibility with tests)
# ---------------------------------------------------------------------------

ANTI_BOT_PATTERNS = (
    "anomaly.js",
    "challenge-form",
    "cc=botnet",
    'id="challenge-form"',
)


def _detect_antibot_challenge(status_code: int, html: str) -> bool:
    """Detect DDG anti-bot challenge page (kept for tests)."""
    lowered_html = (html or "").lower()
    return status_code == 202 and any(pattern in lowered_html for pattern in ANTI_BOT_PATTERNS)


# ---------------------------------------------------------------------------
# Single query via duckduckgo-search library
# ---------------------------------------------------------------------------

def _search_single_query_sync(
    query: str,
    max_results: int = 15,
    region: str = "es-es",
) -> tuple[list[dict[str, Any]], str | None, str | None]:
    """
    Synchronous DDG search using the duckduckgo-search library.
    Uses primp/curl_cffi internally for real browser TLS fingerprinting.
    Returns (raw_results, warning_message, failure_reason).
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results, region=region))
        if not results:
            return [], f"DDG no devolvio resultados para '{query}'.", "no_results"
        return results, None, None
    except Exception as exc:
        error_str = str(exc).lower()
        if "ratelimit" in error_str or "429" in error_str:
            warning = f"DDG rate-limit para '{query}': {exc}"
            logger.warning("[DDG] %s", warning)
            return [], warning, "rate_limit"
        if "timeout" in error_str:
            warning = f"DDG timeout para '{query}': {exc}"
            logger.warning("[DDG] %s", warning)
            return [], warning, "timeout"
        warning = f"Error DDG para '{query}': {exc}"
        logger.error("[DDG] %s", warning)
        return [], warning, "unexpected_error"


async def _search_single_query_async(
    query: str,
    max_results: int = 15,
    region: str = "es-es",
    allow_social_profiles: bool = False,
) -> tuple[list[SearchDiscoveryEntry], list[dict[str, Any]], str | None, str | None]:
    """Async wrapper: runs DDG search in thread pool + processes results."""
    loop = asyncio.get_running_loop()
    raw_results, warning, failure = await loop.run_in_executor(
        _ddg_executor,
        _search_single_query_sync,
        query,
        max_results,
        region,
    )
    if failure:
        return [], [], warning, failure

    entries, excluded = _process_ddg_results(raw_results, query, allow_social_profiles=allow_social_profiles)
    return entries, excluded, warning, None


# ---------------------------------------------------------------------------
# Directory seed expansion (unchanged)
# ---------------------------------------------------------------------------

def _extract_official_site_from_seed_html(seed_url: str, html: str) -> tuple[str | None, list[str]]:
    return ranker_extract_official_site_from_seed_html(seed_url, html)


async def _expand_directory_seed_entry(entry: SearchDiscoveryEntry, allow_social_profiles: bool = False) -> tuple[SearchDiscoveryEntry | None, dict[str, Any] | None]:
    directory_token = get_directory_seed_token(entry.url)
    if not directory_token:
        return entry, None

    seed_excluded = {
        "url": entry.url,
        "reason": f"excluded_as_directory_seed:{directory_token}",
        "query": entry.query,
        "title": entry.title,
        "snippet": entry.snippet,
        "business_likeness_score": entry.business_likeness_score,
        "discovery_reasons": entry.discovery_reasons,
    }

    try:
        html = await fetch_html(entry.url, timeout=10)
    except FetchHtmlError as exc:
        seed_excluded["seed_resolution_error"] = exc.error_type
        return None, seed_excluded
    except Exception as exc:
        seed_excluded["seed_resolution_error"] = str(exc)
        return None, seed_excluded

    official_url, official_reasons = _extract_official_site_from_seed_html(entry.url, html)
    if not official_url:
        seed_excluded["seed_resolution_error"] = "official_site_not_found"
        seed_excluded["discovery_reasons"] = (entry.discovery_reasons or []) + official_reasons
        return None, seed_excluded

    official_score, official_business_reasons, exclusion_reason = score_business_likeness(
        official_url,
        entry.title or "",
        entry.snippet or "",
        allow_social_profiles=allow_social_profiles,
    )
    if exclusion_reason:
        seed_excluded["seed_resolution_error"] = exclusion_reason
        seed_excluded["resolved_official_url"] = official_url
        return None, seed_excluded

    return (
        SearchDiscoveryEntry(
            url=official_url,
            query=entry.query,
            title=entry.title,
            snippet=entry.snippet,
            discovery_confidence="high" if official_score >= 0.3 else entry.discovery_confidence,
            business_likeness_score=round(official_score + 0.15, 4),
            discovery_reasons=(entry.discovery_reasons or []) + official_business_reasons + official_reasons + ["official_site_from_directory_seed"],
            seed_source_url=entry.url,
            seed_source_type="directory_seed",
        ),
        seed_excluded,
    )


# ---------------------------------------------------------------------------
# Public search provider
# ---------------------------------------------------------------------------

class DuckDuckGoHtmlSearchProvider(SearchProvider):
    provider_name = "duckduckgo_html"
    source_type = "duckduckgo_search"

    async def search(self, queries: list[str], allow_social_profiles: bool = False, max_results: int = 10) -> SearchDiscoveryResult:
        return await find_prospect_urls_by_queries(queries, max_results=max_results, allow_social_profiles=allow_social_profiles)


async def find_prospect_urls_by_queries(queries: list[str], max_results: int = 10, allow_social_profiles: bool = False) -> SearchDiscoveryResult:
    logger.info("Buscador DDG: ejecutando %s queries canonicas", len(queries))
    entries: list[SearchDiscoveryEntry] = []
    excluded_results: list[dict[str, Any]] = []
    warning_messages: list[str] = []
    seen_urls: set[str] = set()
    failure_reason: str | None = None
    provider_status = "ok"

    for query in queries:
        query_entries, query_excluded, warning_message, query_failure_reason = await _search_single_query_async(query, allow_social_profiles=allow_social_profiles)
        excluded_results.extend(query_excluded)

        if warning_message:
            warning_messages.append(warning_message)
        if query_failure_reason and failure_reason is None:
            failure_reason = query_failure_reason

        for query_position, entry in enumerate(query_entries, start=1):
            expanded_entry, seed_excluded = await _expand_directory_seed_entry(entry, allow_social_profiles=allow_social_profiles)
            if seed_excluded:
                excluded_results.append(seed_excluded)
            if expanded_entry is None:
                continue
            entry = expanded_entry

            if entry.url in seen_urls:
                excluded_results.append(
                    {
                        "url": entry.url,
                        "reason": "duplicate_url",
                        "query": query,
                        "title": entry.title,
                        "snippet": entry.snippet,
                        "business_likeness_score": entry.business_likeness_score,
                        "discovery_reasons": entry.discovery_reasons,
                        "seed_source_url": entry.seed_source_url,
                    }
                )
                continue
            seen_urls.add(entry.url)
            entry.position = len(entries) + 1
            entries.append(entry)
            logger.debug("[DDG] Lead valido: %s | query=%s | rank=%s", entry.url, query, query_position)
            if len(entries) >= max_results:
                warning_message = "; ".join(warning_messages) if warning_messages else None
                return SearchDiscoveryResult(
                    entries=entries,
                    source_type="duckduckgo_search",
                    discovery_method="search_query",
                    warning_message=warning_message,
                    queries=queries,
                    excluded_results=excluded_results,
                    provider_name="duckduckgo_html",
                    provider_status=provider_status,
                    failure_reason=failure_reason,
                )

    if entries:
        logger.info("Busqueda DDG finalizada. %s prospectos generados.", len(entries))
        return SearchDiscoveryResult(
            entries=entries,
            source_type="duckduckgo_search",
            discovery_method="search_query",
            warning_message="; ".join(warning_messages) if warning_messages else None,
            queries=queries,
            excluded_results=excluded_results,
            provider_name="duckduckgo_html",
            provider_status=provider_status,
            failure_reason=failure_reason,
        )

    if failure_reason in ("rate_limit", "anti_bot_challenge"):
        no_results_message = "; ".join(warning_messages) if warning_messages else "DDG bloqueo el scraping."
        provider_status = "blocked"
    else:
        no_results_message = "; ".join(warning_messages) if warning_messages else f"DDG no devolvio resultados para queries: {queries!r}."
        provider_status = "no_results"
        failure_reason = failure_reason or "no_results"
    logger.warning("Busqueda DDG sin resultados reales para %s.", queries)
    return SearchDiscoveryResult(
        entries=[],
        source_type="duckduckgo_search",
        discovery_method="search_query",
        warning_message=no_results_message,
        queries=queries,
        excluded_results=excluded_results,
        provider_name="duckduckgo_html",
        provider_status=provider_status,
        failure_reason=failure_reason,
    )


async def find_prospect_urls_by_query(query: str, max_results: int = 10, allow_social_profiles: bool = False) -> SearchDiscoveryResult:
    return await find_prospect_urls_by_queries([query], max_results=max_results, allow_social_profiles=allow_social_profiles)
