import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import get_settings

logger = logging.getLogger(__name__)

DEMO_FALLBACK_URLS = [
    "https://www.clinicaveterinariamiraflores.pe/",
    "https://www.veterinariarondon.com/",
    "https://www.veterinariaanimalpolis.pe/",
]

BLOCKED_DOMAIN_TOKENS = [
    "yelp",
    "tripadvisor",
    "paginasamarillas",
    "mercadolibre",
    "linkedin",
    "facebook",
    "instagram",
    "tiktok",
    "youtube",
    "twitter",
    "x.com",
    "doctoralia",
    "topdoctors",
    "infoisinfo",
    "habitissimo",
    "guiatelefonica",
    "foursquare",
    "yellowpages",
    "google.com",
    "googleusercontent",
]


@dataclass
class SearchDiscoveryEntry:
    url: str
    query: str | None = None
    position: int | None = None
    title: str | None = None
    snippet: str | None = None
    discovery_confidence: str | None = None


@dataclass
class SearchDiscoveryResult:
    entries: list[SearchDiscoveryEntry]
    source_type: str
    discovery_method: str
    warning_message: str | None = None
    queries: list[str] = field(default_factory=list)
    excluded_results: list[dict[str, Any]] = field(default_factory=list)

    @property
    def urls(self) -> list[str]:
        return [entry.url for entry in self.entries]


def _clean_text(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def _resolve_ddg_url(raw_url: str) -> str:
    url = raw_url.strip()
    if url.startswith("//duckduckgo.com"):
        query_string = parse_qs(urlparse(url).query)
        if "uddg" in query_string:
            return query_string["uddg"][0]
    return url


def _is_blocked_result(url: str) -> str | None:
    lowered_url = url.lower()
    for blocked_token in BLOCKED_DOMAIN_TOKENS:
        if blocked_token in lowered_url:
            return f"blocked_domain:{blocked_token}"
    return None


def _extract_result_url(result_node: Any) -> str:
    url_tag = result_node.find("a", class_="result__url")
    if url_tag and url_tag.get("href"):
        return _resolve_ddg_url(url_tag["href"])

    title_link = result_node.select_one(".result__title a")
    if title_link and title_link.get("href"):
        return _resolve_ddg_url(title_link["href"])

    return ""


def _extract_search_results(html: str, query: str) -> tuple[list[SearchDiscoveryEntry], list[dict[str, Any]]]:
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
        title = _clean_text(title_tag.get_text(" ", strip=True) if title_tag else "")
        snippet = _clean_text(snippet_tag.get_text(" ", strip=True) if snippet_tag else "")

        if not url.startswith("http"):
            excluded.append({"url": url or None, "reason": "invalid_url", "query": query, "title": title, "snippet": snippet})
            continue

        blocked_reason = _is_blocked_result(url)
        if blocked_reason:
            excluded.append({"url": url, "reason": blocked_reason, "query": query, "title": title, "snippet": snippet})
            continue

        discovery_confidence = "medium"
        lowered_blob = f"{title} {snippet}".lower()
        if "oficial" in lowered_blob or "official" in lowered_blob:
            discovery_confidence = "high"

        entries.append(
            SearchDiscoveryEntry(
                url=url,
                query=query,
                title=title or None,
                snippet=snippet or None,
                discovery_confidence=discovery_confidence,
            )
        )

    return entries, excluded


async def _search_single_query(query: str) -> tuple[list[SearchDiscoveryEntry], list[dict[str, Any]], str | None]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Referer": "https://duckduckgo.com/",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    try:
        async with httpx.AsyncClient(headers=headers, timeout=10.0, follow_redirects=True) as client:
            response = await client.post("https://html.duckduckgo.com/html/", data={"q": query})
            response.raise_for_status()
            return (*_extract_search_results(response.text, query), None)
    except httpx.HTTPError as exc:
        warning_message = f"Busqueda DDG fallida para '{query}': {exc}"
        logger.warning("[DDG] %s", warning_message)
        return [], [], warning_message
    except Exception as exc:
        warning_message = f"Error inesperado en DDG para '{query}': {exc}"
        logger.error("[DDG] %s", warning_message)
        return [], [], warning_message


async def find_prospect_urls_by_queries(queries: list[str], max_results: int = 10) -> SearchDiscoveryResult:
    logger.info("Buscador: ejecutando %s queries canonicas", len(queries))
    entries: list[SearchDiscoveryEntry] = []
    excluded_results: list[dict[str, Any]] = []
    warning_messages: list[str] = []
    seen_urls: set[str] = set()

    for query in queries:
        query_entries, query_excluded, warning_message = await _search_single_query(query)
        excluded_results.extend(query_excluded)
        if warning_message:
            warning_messages.append(warning_message)

        for query_position, entry in enumerate(query_entries, start=1):
            if entry.url in seen_urls:
                excluded_results.append(
                    {
                        "url": entry.url,
                        "reason": "duplicate_url",
                        "query": query,
                        "title": entry.title,
                        "snippet": entry.snippet,
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
                )

    if entries:
        logger.info("Busqueda finalizada. %s prospectos generados.", len(entries))
        return SearchDiscoveryResult(
            entries=entries,
            source_type="duckduckgo_search",
            discovery_method="search_query",
            warning_message="; ".join(warning_messages) if warning_messages else None,
            queries=queries,
            excluded_results=excluded_results,
        )

    settings = get_settings()
    warning_message = "; ".join(warning_messages) if warning_messages else None
    if settings.DEMO_MODE:
        demo_message = warning_message or f"DDG no devolvio resultados para queries: {queries!r}."
        logger.warning("DEMO_MODE activo. Se devuelven resultados mock para %s.", queries)
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
        )

    no_results_message = warning_message or f"DDG no devolvio resultados para queries: {queries!r}."
    logger.warning("Busqueda sin resultados reales para %s.", queries)
    return SearchDiscoveryResult(
        entries=[],
        source_type="duckduckgo_search",
        discovery_method="search_query",
        warning_message=no_results_message,
        queries=queries,
        excluded_results=excluded_results,
    )


async def find_prospect_urls_by_query(query: str, max_results: int = 10) -> SearchDiscoveryResult:
    return await find_prospect_urls_by_queries([query], max_results=max_results)
