import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import get_settings
from app.scraper.http_client import FetchHtmlError, fetch_html

logger = logging.getLogger(__name__)

DEMO_FALLBACK_URLS = [
    "https://www.clinicaveterinariamiraflores.pe/",
    "https://www.veterinariarondon.com/",
    "https://www.veterinariaanimalpolis.pe/",
]

BLOCKED_DOMAIN_TOKENS = [
    "mercadolibre",
    "linkedin",
    "facebook",
    "instagram",
    "tiktok",
    "youtube",
    "twitter",
    "x.com",
    "infoisinfo",
    "habitissimo",
    "foursquare",
    "google.com",
    "googleusercontent",
]
DIRECTORY_SEED_DOMAIN_TOKENS = [
    "doctoralia",
    "topdoctors",
    "paginasamarillas",
    "guiatelefonica",
    "yellowpages",
    "yelp",
    "tripadvisor",
]
SOCIAL_DOMAIN_TOKENS = [
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "youtube.com",
    "twitter.com",
    "x.com",
]
DIRECTORY_CTA_HINTS = [
    "sitio web",
    "website",
    "web oficial",
    "official site",
    "pagina web",
    "página web",
    "visitar web",
    "visitar sitio",
    "homepage",
]
EDITORIAL_PATH_TOKENS = [
    "/blog/",
    "/ideas/",
    "/noticias/",
    "/news/",
    "/categories/",
    "/category/",
    "/guia/",
    "/guía/",
    "/article/",
    "/articulo/",
    "/artículos/",
    "/tag/",
]
EDITORIAL_TITLE_TOKENS = [
    "100 ideas",
    "ideas de negocio",
    "qué vender",
    "que vender",
    "guia",
    "guía",
    "categorías",
    "categories",
    "tendencias",
    "mejores",
    "top ",
    "lista de",
]


@dataclass
class SearchDiscoveryEntry:
    url: str
    query: str | None = None
    position: int | None = None
    title: str | None = None
    snippet: str | None = None
    discovery_confidence: str | None = None
    business_likeness_score: float | None = None
    discovery_reasons: list[str] = field(default_factory=list)
    seed_source_url: str | None = None
    seed_source_type: str | None = None


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


def _get_directory_seed_token(url: str) -> str | None:
    lowered_url = url.lower()
    for token in DIRECTORY_SEED_DOMAIN_TOKENS:
        if token in lowered_url:
            return token
    return None


def _extract_brand_tokens(value: str) -> set[str]:
    cleaned = "".join(char.lower() if char.isalnum() else " " for char in value)
    tokens = {
        token
        for token in cleaned.split()
        if len(token) >= 4 and token not in {"http", "https", "www", "site", "oficial", "official", "contacto", "contact"}
    }
    return tokens


def _domain_brand_tokens(url: str) -> set[str]:
    hostname = urlparse(url).netloc.lower().removeprefix("www.")
    primary = hostname.split(":")[0].split(".")[0]
    return _extract_brand_tokens(primary)


def _is_same_root_domain(left_url: str, right_url: str) -> bool:
    left_parts = urlparse(left_url).netloc.lower().removeprefix("www.").split(".")
    right_parts = urlparse(right_url).netloc.lower().removeprefix("www.").split(".")
    return len(left_parts) >= 2 and len(right_parts) >= 2 and left_parts[-2:] == right_parts[-2:]


def _looks_like_social_or_marketplace(url: str) -> bool:
    lowered_url = url.lower()
    return any(token in lowered_url for token in SOCIAL_DOMAIN_TOKENS + BLOCKED_DOMAIN_TOKENS)


def _score_directory_official_link(seed_url: str, candidate_url: str, anchor_text: str) -> float:
    score = 0.0
    lowered_anchor = anchor_text.lower()
    if any(hint in lowered_anchor for hint in DIRECTORY_CTA_HINTS):
        score += 0.45
    if urlparse(candidate_url).path in {"", "/"}:
        score += 0.2
    if not _looks_like_social_or_marketplace(candidate_url):
        score += 0.15
    if not _is_same_root_domain(seed_url, candidate_url):
        score += 0.15
    if len(urlparse(candidate_url).path.split("/")) <= 2:
        score += 0.05
    return round(score, 4)


def _extract_official_site_from_seed_html(seed_url: str, html: str) -> tuple[str | None, list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    best_url: str | None = None
    best_score = 0.0
    best_reasons: list[str] = []

    for link in soup.find_all("a", href=True):
        href = link.get("href", "").strip()
        if not href:
            continue
        candidate_url = urljoin(seed_url, href)
        if not candidate_url.startswith("http"):
            continue
        if _is_same_root_domain(seed_url, candidate_url):
            continue
        if _looks_like_social_or_marketplace(candidate_url):
            continue

        anchor_text = " ".join(link.get_text(" ", strip=True).split())
        score = _score_directory_official_link(seed_url, candidate_url, anchor_text)
        reasons: list[str] = ["directory_seed_resolved"]
        if any(hint in anchor_text.lower() for hint in DIRECTORY_CTA_HINTS):
            reasons.append("official_link_label")
        if urlparse(candidate_url).path in {"", "/"}:
            reasons.append("root_domain_candidate")

        if score > best_score:
            best_url = candidate_url
            best_score = score
            best_reasons = reasons

    if best_url and best_score >= 0.45:
        return best_url, best_reasons
    return None, ["directory_seed_without_official_site"]


def _score_business_likeness(url: str, title: str, snippet: str) -> tuple[float, list[str], str | None]:
    score = 0.0
    reasons: list[str] = []
    lowered_blob = f"{title} {snippet}".lower()
    path = urlparse(url).path.lower()
    title_tokens = _extract_brand_tokens(title)
    domain_tokens = _domain_brand_tokens(url)

    positive_rules = [
        ("official_site_hint", 0.35, ["oficial", "official", "sitio oficial"]),
        ("contact_or_services_hint", 0.18, ["contacto", "contact", "servicios", "services", "nosotros", "about"]),
        ("conversion_cta_hint", 0.18, ["reserva", "booking", "agenda", "cotiza", "quote"]),
        ("business_category_hint", 0.12, ["clinica", "clínica", "estudio", "agencia", "tienda", "retail", "consultora"]),
    ]
    negative_rules = [
        ("editorial_path", -0.35, EDITORIAL_PATH_TOKENS),
        ("editorial_title", -0.28, EDITORIAL_TITLE_TOKENS),
        ("marketplace_or_listing", -0.25, ["marketplace", "listing", "directory", "directorio"]),
    ]

    for reason, delta, tokens in positive_rules:
        if any(token in lowered_blob for token in tokens):
            score += delta
            reasons.append(reason)

    for reason, delta, tokens in negative_rules:
        if any(token in lowered_blob or token in path for token in tokens):
            score += delta
            reasons.append(reason)

    depth = len([segment for segment in path.split("/") if segment])
    if depth <= 1:
        score += 0.12
        reasons.append("shallow_url")
    elif depth >= 3:
        score -= 0.15
        reasons.append("deep_url")

    if path.endswith(".html") or path.endswith(".php"):
        score -= 0.05
        reasons.append("document_like_path")

    if title and len(title.split()) <= 10:
        score += 0.08
        reasons.append("concise_title")

    if domain_tokens and title_tokens and domain_tokens & title_tokens:
        score += 0.22
        reasons.append("brand_domain_match")
    if path in {"", "/"}:
        score += 0.08
        reasons.append("root_domain_url")
    if _get_directory_seed_token(url):
        score -= 0.2
        reasons.append("directory_seed_candidate")

    exclusion_reason = None
    if any(reason in reasons for reason in {"editorial_path", "editorial_title"}):
        exclusion_reason = "excluded_as_article"
    elif score < 0.15:
        exclusion_reason = "low_business_likeness"

    return round(score, 4), reasons, exclusion_reason


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

        business_score, business_reasons, exclusion_reason = _score_business_likeness(url, title, snippet)
        if exclusion_reason:
            excluded.append(
                {
                    "url": url,
                    "reason": exclusion_reason,
                    "query": query,
                    "title": title,
                    "snippet": snippet,
                    "business_likeness_score": business_score,
                    "discovery_reasons": business_reasons,
                }
            )
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


async def _expand_directory_seed_entry(entry: SearchDiscoveryEntry) -> tuple[SearchDiscoveryEntry | None, dict[str, Any] | None]:
    directory_token = _get_directory_seed_token(entry.url)
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

    official_score, official_business_reasons, exclusion_reason = _score_business_likeness(
        official_url,
        entry.title or "",
        entry.snippet or "",
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
            expanded_entry, seed_excluded = await _expand_directory_seed_entry(entry)
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
