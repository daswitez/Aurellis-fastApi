import logging
from dataclasses import dataclass
from typing import List
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


@dataclass
class SearchDiscoveryResult:
    urls: List[str]
    source_type: str
    discovery_method: str
    warning_message: str | None = None


async def find_prospect_urls_by_query(query: str, max_results: int = 10) -> SearchDiscoveryResult:
    """
    Busca resultados orgánicos en DDG HTML clásico.
    Si no encuentra resultados, solo usa fallback mock cuando DEMO_MODE=true.
    """
    logger.info("Buscador: buscando %s resultados para '%s'", max_results, query)
    discovered_urls: List[str] = []

    blocked_domains = [
        "yelp", "tripadvisor", "paginasamarillas", "mercadolibre",
        "linkedin", "facebook", "instagram", "tiktok", "youtube", "twitter", "x.com",
        "doctoralia", "topdoctors", "infoisinfo", "habitissimo",
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Referer": "https://duckduckgo.com/",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    warning_message = None

    try:
        async with httpx.AsyncClient(headers=headers, timeout=10.0, follow_redirects=True) as client:
            response = await client.post("https://html.duckduckgo.com/html/", data={"q": query})
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            for a_tag in soup.find_all("a", class_="result__url"):
                url = a_tag.get("href", "").strip()
                if url.startswith("//duckduckgo.com"):
                    query_string = parse_qs(urlparse(url).query)
                    if "uddg" in query_string:
                        url = query_string["uddg"][0]

                if not url.startswith("http"):
                    continue
                if any(blocked in url.lower() for blocked in blocked_domains):
                    continue
                if url in discovered_urls:
                    continue

                discovered_urls.append(url)
                logger.debug("[DDG] Lead válido: %s", url)
                if len(discovered_urls) >= max_results:
                    break
    except httpx.HTTPError as exc:
        warning_message = f"Busqueda DDG fallida: {exc}"
        logger.warning("[DDG] %s", warning_message)
    except Exception as exc:
        warning_message = f"Error inesperado en DDG: {exc}"
        logger.error("[DDG] %s", warning_message)

    if discovered_urls:
        logger.info("Búsqueda finalizada. %s prospectos generados.", len(discovered_urls))
        return SearchDiscoveryResult(
            urls=discovered_urls,
            source_type="duckduckgo_search",
            discovery_method="search_query",
            warning_message=warning_message,
        )

    settings = get_settings()
    if settings.DEMO_MODE:
        demo_message = (
            warning_message
            or f"DDG no devolvió resultados para '{query}'."
        )
        logger.warning(
            "DEMO_MODE activo. Se devuelven resultados mock para '%s' en lugar de fallar.",
            query,
        )
        return SearchDiscoveryResult(
            urls=DEMO_FALLBACK_URLS[:max_results],
            source_type="mock_search",
            discovery_method="search_query",
            warning_message=f"{demo_message} Se activó fallback demo.",
        )

    no_results_message = warning_message or f"DDG no devolvió resultados para '{query}'."
    logger.warning("Búsqueda sin resultados reales para '%s'.", query)
    return SearchDiscoveryResult(
        urls=[],
        source_type="duckduckgo_search",
        discovery_method="search_query",
        warning_message=no_results_message,
    )
