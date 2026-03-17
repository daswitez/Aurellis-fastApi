import asyncio
import logging
import random
from typing import Any
from urllib.parse import quote_plus, urlparse

import httpx
from bs4 import BeautifulSoup

from app.services.discovery_ranker import (
    clean_text,
    is_blocked_result,
    score_business_likeness,
)
from app.services.discovery_types import SearchDiscoveryEntry, SearchDiscoveryResult
from app.services.search_providers.base import SearchProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# User-Agent pool (same diverse set as DDG)
# ---------------------------------------------------------------------------

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]

ACCEPT_LANGUAGES = [
    "es-ES,es;q=0.9,en;q=0.8",
    "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7",
    "es,en-US;q=0.9,en;q=0.8",
    "en-US,en;q=0.9,es;q=0.8",
]

# ---------------------------------------------------------------------------
# Evasion constants
# ---------------------------------------------------------------------------

GOOGLE_INTER_QUERY_DELAY_MIN = 3.0
GOOGLE_INTER_QUERY_DELAY_MAX = 7.0
GOOGLE_RETRY_DELAY_MIN = 10.0
GOOGLE_RETRY_DELAY_MAX = 25.0
GOOGLE_MAX_RETRIES_PER_QUERY = 1

# CAPTCHA / block detection patterns
GOOGLE_BLOCK_PATTERNS = (
    "/sorry/",
    "detected unusual traffic",
    "captcha",
    "recaptcha",
    "Our systems have detected unusual traffic",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_random_headers() -> dict[str, str]:
    ua = random.choice(USER_AGENTS)
    lang = random.choice(ACCEPT_LANGUAGES)
    return {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": lang,
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "DNT": "1",
    }


def _detect_google_block(status_code: int, html: str) -> bool:
    """Detect Google CAPTCHA or block page."""
    if status_code == 429:
        return True
    lowered = (html or "").lower()
    return any(pattern.lower() in lowered for pattern in GOOGLE_BLOCK_PATTERNS)


def _extract_google_results(html: str, query: str, allow_social_profiles: bool = False) -> tuple[list[SearchDiscoveryEntry], list[dict[str, Any]]]:
    """Parse Google SERP HTML and extract results."""
    soup = BeautifulSoup(html, "html.parser")
    entries: list[SearchDiscoveryEntry] = []
    excluded: list[dict[str, Any]] = []

    # Google wraps each result in a <div class="g"> or similar structures
    result_containers = soup.select("div.g")
    if not result_containers:
        # Fallback: try to find links in the main content area
        result_containers = soup.select("div[data-sokoban-container]")

    for node in result_containers:
        # Extract URL
        link_tag = node.find("a", href=True)
        if not link_tag:
            continue
        url = link_tag["href"]
        if not url.startswith("http"):
            continue
        # Skip Google's own internal links
        parsed = urlparse(url)
        if parsed.hostname and "google" in parsed.hostname:
            continue

        # Extract title
        title_tag = node.find("h3")
        title = clean_text(title_tag.get_text(" ", strip=True) if title_tag else "")

        # Extract snippet - Google uses various containers for snippets
        snippet = ""
        # Try data-sncf attribute divs (common in modern Google)
        snippet_candidates = node.select("div[data-sncf], span[class*='st'], div.VwiC3b, div[style*='line-clamp']")
        for candidate in snippet_candidates:
            text = clean_text(candidate.get_text(" ", strip=True))
            if len(text) > len(snippet):
                snippet = text

        # If still no snippet, try the second or third block-level element
        if not snippet:
            for el in node.find_all(["div", "span"], recursive=True):
                text = clean_text(el.get_text(" ", strip=True))
                if text and text != title and len(text) > 20:
                    snippet = text
                    break

        # Apply same filters as DDG
        blocked_reason = is_blocked_result(url, allow_social_profiles=allow_social_profiles)
        if blocked_reason:
            excluded.append({"url": url, "reason": blocked_reason, "query": query, "title": title, "snippet": snippet})
            continue

        business_score, business_reasons, exclusion_reason = score_business_likeness(url, title, snippet, allow_social_profiles=allow_social_profiles)
        if exclusion_reason:
            excluded.append({
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
                "candidate_screening_stage": classified.get("candidate_screening_stage"),
                "candidate_screening_reason": classified.get("candidate_screening_reason"),
            })
            continue

        discovery_confidence = "medium"
        lowered_blob = f"{title} {snippet}".lower()
        if "oficial" in lowered_blob or "official" in lowered_blob or business_score >= 0.45:
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
                candidate_screening_stage=classified.get("candidate_screening_stage"),
                candidate_screening_reason=classified.get("candidate_screening_reason"),
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
# Single query with retry
# ---------------------------------------------------------------------------

async def _search_single_query(
    query: str,
    client: httpx.AsyncClient,
    num_results: int = 15,
    allow_social_profiles: bool = False,
) -> tuple[list[SearchDiscoveryEntry], list[dict[str, Any]], str | None, str | None]:
    """Execute a single Google search query with retry on block detection."""
    last_warning: str | None = None

    for attempt in range(1, GOOGLE_MAX_RETRIES_PER_QUERY + 2):
        client.headers.update(_build_random_headers())

        try:
            params = {
                "q": query,
                "hl": "es",
                "num": str(num_results),
            }
            response = await client.get("https://www.google.com/search", params=params)

            if _detect_google_block(response.status_code, response.text):
                last_warning = f"Google bloqueo la query '{query}' con CAPTCHA/rate-limit."
                logger.warning("[Google] %s (intento %s/%s)", last_warning, attempt, GOOGLE_MAX_RETRIES_PER_QUERY + 1)
                if attempt <= GOOGLE_MAX_RETRIES_PER_QUERY:
                    retry_delay = random.uniform(GOOGLE_RETRY_DELAY_MIN, GOOGLE_RETRY_DELAY_MAX)
                    await asyncio.sleep(retry_delay)
                    continue
                return [], [], last_warning, "google_captcha"

            response.raise_for_status()
            entries, excluded = _extract_google_results(response.text, query, allow_social_profiles=allow_social_profiles)
            return entries, excluded, None, None

        except httpx.HTTPError as exc:
            last_warning = f"Busqueda Google fallida para '{query}': {exc}"
            logger.warning("[Google] %s", last_warning)
            return [], [], last_warning, "http_error"
        except Exception as exc:
            last_warning = f"Error inesperado en Google para '{query}': {exc}"
            logger.error("[Google] %s", last_warning)
            return [], [], last_warning, "unexpected_error"

    return [], [], last_warning, "google_captcha"


# ---------------------------------------------------------------------------
# Public provider
# ---------------------------------------------------------------------------

class GoogleHtmlSearchProvider(SearchProvider):
    provider_name = "google_html"
    source_type = "google_search"

    async def search(self, queries: list[str], allow_social_profiles: bool = False, max_results: int = 10) -> SearchDiscoveryResult:
        return await find_prospect_urls_via_google(queries, max_results=max_results, allow_social_profiles=allow_social_profiles)


async def find_prospect_urls_via_google(queries: list[str], max_results: int = 10, allow_social_profiles: bool = False) -> SearchDiscoveryResult:
    logger.info("Buscador Google HTML: ejecutando %s queries", len(queries))
    entries: list[SearchDiscoveryEntry] = []
    excluded_results: list[dict[str, Any]] = []
    warning_messages: list[str] = []
    seen_urls: set[str] = set()
    failure_reason: str | None = None
    provider_status = "ok"

    initial_headers = _build_random_headers()
    async with httpx.AsyncClient(
        headers=initial_headers,
        timeout=15.0,
        follow_redirects=True,
    ) as client:

        # Warm-up: get Google homepage cookies
        try:
            await client.get("https://www.google.com/")
            await asyncio.sleep(random.uniform(1.0, 2.5))
        except Exception as exc:
            logger.warning("[Google] Warm-up fallido (no fatal): %s", exc)

        for query_index, query in enumerate(queries):
            if query_index > 0:
                inter_delay = random.uniform(GOOGLE_INTER_QUERY_DELAY_MIN, GOOGLE_INTER_QUERY_DELAY_MAX)
                logger.debug("[Google] Delay inter-query: %.1fs", inter_delay)
                await asyncio.sleep(inter_delay)

            query_entries, query_excluded, warning, query_failure = await _search_single_query(query, client, num_results=max_results, allow_social_profiles=allow_social_profiles)
            excluded_results.extend(query_excluded)

            if warning:
                warning_messages.append(warning)
            if query_failure == "google_captcha":
                if failure_reason is None:
                    failure_reason = "google_captcha"
                extra_delay = random.uniform(GOOGLE_RETRY_DELAY_MIN, GOOGLE_RETRY_DELAY_MAX)
                await asyncio.sleep(extra_delay)
                continue
            if query_failure and failure_reason is None:
                failure_reason = query_failure

            for position, entry in enumerate(query_entries, start=1):
                if entry.url in seen_urls:
                    excluded_results.append({
                        "url": entry.url,
                        "reason": "duplicate_url",
                        "query": query,
                        "title": entry.title,
                        "snippet": entry.snippet,
                    })
                    continue
                seen_urls.add(entry.url)
                entry.position = len(entries) + 1
                entries.append(entry)
                logger.debug("[Google] Lead valido: %s | query=%s | rank=%s", entry.url, query, position)
                if len(entries) >= max_results:
                    return SearchDiscoveryResult(
                        entries=entries,
                        source_type="google_search",
                        discovery_method="search_query",
                        warning_message="; ".join(warning_messages) if warning_messages else None,
                        queries=queries,
                        excluded_results=excluded_results,
                        provider_name="google_html",
                        provider_status=provider_status,
                        failure_reason=failure_reason,
                    )

    if entries:
        logger.info("Busqueda Google finalizada. %s prospectos generados.", len(entries))
        return SearchDiscoveryResult(
            entries=entries,
            source_type="google_search",
            discovery_method="search_query",
            warning_message="; ".join(warning_messages) if warning_messages else None,
            queries=queries,
            excluded_results=excluded_results,
            provider_name="google_html",
            provider_status=provider_status,
            failure_reason=failure_reason,
        )

    if failure_reason in ("google_captcha",):
        no_results_message = "; ".join(warning_messages) if warning_messages else "Google bloqueo el scraping con CAPTCHA."
        provider_status = "blocked"
    else:
        no_results_message = "; ".join(warning_messages) if warning_messages else f"Google no devolvio resultados para queries: {queries!r}."
        provider_status = "no_results"
        failure_reason = failure_reason or "no_results"

    logger.warning("Busqueda Google sin resultados reales para %s.", queries)
    return SearchDiscoveryResult(
        entries=[],
        source_type="google_search",
        discovery_method="search_query",
        warning_message=no_results_message,
        queries=queries,
        excluded_results=excluded_results,
        provider_name="google_html",
        provider_status=provider_status,
        failure_reason=failure_reason,
    )
