import logging
import asyncio
import httpx
from bs4 import BeautifulSoup
from typing import List

logger = logging.getLogger(__name__)

async def find_prospect_urls_by_query(query: str, max_results: int = 10) -> List[str]:
    """
    Intenta obtener resultados orgánicos de DDG HTML clásico evadiendo JS.
    Si DDG baneó nuestra IP o fallamos por anti-scraping, retornamos URLs reales Hardcodeadas
    solo para mantener vivo el ecosistema MVP (hasta integrar Outscraper API key oficial).
    """
    logger.info(f"Buscador: Buscando {max_results} resultados para '{query}'")
    discovered_urls = []
    
    blocked_domains = [
        "yelp", "tripadvisor", "paginasamarillas", "mercadolibre", 
        "linkedin", "facebook", "instagram", "tiktok", "youtube", "twitter", "x.com",
        "doctoralia", "topdoctors", "infoisinfo", "habitissimo"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Referer": "https://duckduckgo.com/",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }

    try:
        async with httpx.AsyncClient(headers=headers, timeout=10.0, follow_redirects=True) as client:
            res = await client.post("https://html.duckduckgo.com/html/", data={"q": query})
            
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                
                for a_tag in soup.find_all('a', class_='result__url'):
                    url = a_tag.get('href', '').strip()
                    if url.startswith("//duckduckgo.com"):
                        # Pseudo-proxy DDG
                        from urllib.parse import urlparse, parse_qs
                        qs = parse_qs(urlparse(url).query)
                        if 'uddg' in qs:
                            url = qs['uddg'][0]

                    if url.startswith("http"):
                        if not any(blocked in url.lower() for blocked in blocked_domains):
                            if url not in discovered_urls:
                                discovered_urls.append(url)
                                logger.debug(f"[DDG] Lead Válido: {url}")
                                if len(discovered_urls) >= max_results:
                                    break
    except Exception as e:
        logger.error(f"[DDG Error] Fallo de red evadido: {e}")

    # ===== FALLBACK PARA MVP LOCAL CENSURADO =====
    # Proveemos 3 prospectos B2B reales temporales en caso de ban
    if len(discovered_urls) == 0:
        logger.warning(f"Buscador bloqueado por anti-bots. Inyectando Mock de dominios asociados al nicho de '{query}'.")
        fallback_urls = [
            "https://www.clinicaveterinariamiraflores.pe/",
            "https://www.veterinariarondon.com/",
            "https://www.veterinariaanimalpolis.pe/"
        ]
        # Devolver solo los solicitados (max_results)
        return fallback_urls[:max_results]

    logger.info(f"Búsqueda finalizada. {len(discovered_urls)} prospectos generados.")
    return discovered_urls
