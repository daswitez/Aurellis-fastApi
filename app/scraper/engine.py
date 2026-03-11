import logging
from typing import Dict, Any, Optional
from urllib.parse import urlparse

from app.scraper.http_client import FetchHtmlError, fetch_html
from app.scraper.parser import parse_html_basic
from app.services.ai_extractor import extract_business_entity_ai
from app.services.heuristic_extractor import extract_business_entity_heuristic

logger = logging.getLogger(__name__)

MAX_KEY_PAGES_TO_CRAWL = 3
KEY_PAGE_PRIORITY = {
    "contact": 0,
    "about": 1,
    "careers": 2,
    "other": 3,
}


def _classify_page_type(url: str) -> str:
    lowered = url.lower()
    if "contact" in lowered or "contacto" in lowered:
        return "contact"
    if "about" in lowered or "nosotros" in lowered or "equipo" in lowered:
        return "about"
    if "career" in lowered or "trabajo" in lowered or "empleo" in lowered:
        return "careers"
    return "other"


def _select_key_internal_links(internal_links: list[str], max_pages: int = MAX_KEY_PAGES_TO_CRAWL) -> list[dict[str, str]]:
    unique_links: list[str] = []
    for link in internal_links:
        if link not in unique_links:
            unique_links.append(link)

    sorted_links = sorted(
        unique_links,
        key=lambda link: (KEY_PAGE_PRIORITY.get(_classify_page_type(link), 99), link),
    )
    return [
        {"url": link, "page_type": _classify_page_type(link)}
        for link in sorted_links[:max_pages]
    ]


def _merge_html_metadata(base_metadata: Dict[str, Any], incoming_metadata: Dict[str, Any]) -> Dict[str, Any]:
    merged_metadata = {
        "title": base_metadata.get("title") or incoming_metadata.get("title") or "",
        "description": base_metadata.get("description") or incoming_metadata.get("description") or "",
        "emails": sorted(set(base_metadata.get("emails", [])) | set(incoming_metadata.get("emails", []))),
        "phones": sorted(set(base_metadata.get("phones", [])) | set(incoming_metadata.get("phones", []))),
        "social_links": sorted(set(base_metadata.get("social_links", [])) | set(incoming_metadata.get("social_links", []))),
        "internal_links": sorted(set(base_metadata.get("internal_links", [])) | set(incoming_metadata.get("internal_links", []))),
        "form_detected": bool(base_metadata.get("form_detected") or incoming_metadata.get("form_detected")),
    }
    return merged_metadata


def _select_contact_page_url(internal_links: list[str]) -> str | None:
    for priority_keywords in (["contact", "contacto"], ["about", "nosotros", "equipo"]):
        for link in internal_links:
            lowered = link.lower()
            if any(keyword in lowered for keyword in priority_keywords):
                return link
    return None


async def _crawl_key_pages(root_metadata: Dict[str, Any]) -> tuple[str, Dict[str, Any], list[dict[str, str]]]:
    selected_pages = _select_key_internal_links(root_metadata.get("internal_links", []))
    merged_text_parts: list[str] = []
    merged_metadata: Dict[str, Any] = {
        "title": "",
        "description": "",
        "emails": [],
        "phones": [],
        "social_links": [],
        "internal_links": [],
        "form_detected": False,
    }
    crawled_pages: list[dict[str, str]] = []

    for page in selected_pages:
        page_url = page["url"]
        page_type = page["page_type"]
        try:
            html = await fetch_html(page_url)
        except FetchHtmlError as exc:
            logger.warning(
                "No se pudo crawlear página clave %s (%s): %s [%s]",
                page_url,
                page_type,
                exc.message,
                exc.error_type,
            )
            continue

        page_text, page_metadata = parse_html_basic(html, base_url=page_url)
        if page_text:
            merged_text_parts.append(f"[{page_type.upper()}] {page_text}")
        merged_metadata = _merge_html_metadata(merged_metadata, page_metadata)
        crawled_pages.append({"url": page_url, "page_type": page_type})

    return "\n\n".join(merged_text_parts), merged_metadata, crawled_pages

def extract_domain(url: str) -> str:
    """Extrae midominio.com a partir de https://www.midominio.com/contacto"""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path
        if domain.startswith("www."):
            domain = domain[4:]
        return domain.lower()
    except Exception:
        return url

async def scrape_single_prospect(target_url: str, job_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Función orquestadora que toma la URL de un prospecto, la descarga, limpia su HTML,
    la pasa por el extractor heurístico preconfigurado y devuelve el diccionario estructurado.
    
    Args:
        target_url: Endpoint público del prospecto (ej. https://apple.com)
        job_context: Variables del usuario obtenidas del ScrapingJob (para análisis de contexto local).
        
    Returns:
        Diccionario listo para inyectar en la tabla Prospects.
    """
    domain = extract_domain(target_url)
    logger.info(f"==> Iniciando scraping de dominio: {domain} <==")
    
    # 1. Obtener HTML crudo
    html_raw = await fetch_html(target_url)
    
    if not html_raw:
        logger.warning(f"No se pudo obtener HTML para {target_url}")
        return None
        
    # 2. Parsear el HTML puro
    clean_text, html_metadata = parse_html_basic(html_raw, base_url=target_url)
    key_pages_text, key_pages_metadata, crawled_pages = await _crawl_key_pages(html_metadata)
    combined_text = clean_text if not key_pages_text else f"{clean_text}\n\n{key_pages_text}"
    merged_metadata = _merge_html_metadata(html_metadata, key_pages_metadata)
    
    # 3. Extracción de Lógica de Negocio mediante Heurística de Código
    # [FASE 5] Invocación a Inteligencia Artificial para comprensión profunda (DeepSeek)
    # Fallback a heurística rápida si ocurre alguna excepción de red/API
    try:
        extracted_data = await extract_business_entity_ai(domain, combined_text, job_context)
    except Exception as ai_e:
        logger.error(f"Error AI para {target_url}. Usando heurística fallback: {ai_e}")
        extracted_data = await extract_business_entity_heuristic(combined_text, html_raw, merged_metadata, job_context)
    
    # 4. Fusionar Data Fuerte (Metadatos reales de bs4 como correos visibles y links) 
    # con Data Deductiva (Adivinada por el Heurístico)
    internal_links = merged_metadata.get("internal_links", [])
    contact_page_url = _select_contact_page_url(internal_links)

    final_prospect = {
        "domain": domain,
        "website_url": target_url,
        "company_name": extracted_data.get("company_name", domain),
        "category": extracted_data.get("category"),
        "location": extracted_data.get("location"),
        "description": extracted_data.get("description"),
        
        # Metadatos seguros de HTML (BeautifulSoup y Regex son asertivos)
        "email": merged_metadata.get("emails")[0] if merged_metadata.get("emails") else None,
        "phone": merged_metadata.get("phones")[0] if merged_metadata.get("phones") else None,
        "contact_page_url": contact_page_url,
        "form_detected": merged_metadata.get("form_detected", False),
        "linkedin_url": next((s for s in merged_metadata.get("social_links", []) if "linkedin.com" in s), None),
        "instagram_url": next((s for s in merged_metadata.get("social_links", []) if "instagram.com" in s), None),
        "facebook_url": next((s for s in merged_metadata.get("social_links", []) if "facebook.com" in s), None),
        
        # Deducciones del algoritmo heurístico basado en el contexto del vendedor
        "inferred_tech_stack": extracted_data.get("inferred_tech_stack"),
        "inferred_niche": extracted_data.get("inferred_niche"),
        "generic_attributes": extracted_data.get("generic_attributes"),
        "estimated_revenue_signal": extracted_data.get("estimated_revenue_signal"),
        "has_active_ads": extracted_data.get("has_active_ads"),
        "hiring_signals": extracted_data.get("hiring_signals", False),
        "score": extracted_data.get("score", 0.0),
        "confidence_level": extracted_data.get("confidence_level", "low"),
        
        # Auditoría de origen
        "source": "HTTPX_Scraper",
        "source_url": target_url,
        "job_id": job_context.get("job_id"),  # Será asociado a la métrica padre
        "internal_links": internal_links,
        "crawled_pages": crawled_pages,
    }
    
    logger.info(f"Terminado el procesamiento para {domain}. Fusión de datos exitosa.")
    return final_prospect
