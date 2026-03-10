import logging
from typing import Dict, Any, Optional
from urllib.parse import urlparse

from app.scraper.http_client import fetch_html
from app.scraper.parser import parse_html_basic
from app.services.ai_extractor import extract_business_entity_ai
from app.services.heuristic_extractor import extract_business_entity_heuristic

logger = logging.getLogger(__name__)

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
    
    # 3. Extracción de Lógica de Negocio mediante Heurística de Código
    # [FASE 5] Invocación a Inteligencia Artificial para comprensión profunda (DeepSeek)
    # Fallback a heurística rápida si ocurre alguna excepción de red/API
    try:
        extracted_data = await extract_business_entity_ai(domain, clean_text, job_context)
    except Exception as ai_e:
        logger.error(f"Error AI para {target_url}. Usando heurística fallback: {ai_e}")
        extracted_data = await extract_business_entity_heuristic(clean_text, html_raw, html_metadata, job_context)
    
    # 4. Fusionar Data Fuerte (Metadatos reales de bs4 como correos visibles y links) 
    # con Data Deductiva (Adivinada por el Heurístico)
    final_prospect = {
        "domain": domain,
        "website_url": target_url,
        "company_name": extracted_data.get("company_name", domain),
        "category": extracted_data.get("category"),
        "location": extracted_data.get("location"),
        "description": extracted_data.get("description"),
        
        # Metadatos seguros de HTML (BeautifulSoup y Regex son asertivos)
        "email": html_metadata.get("emails")[0] if html_metadata.get("emails") else None,
        "phone": html_metadata.get("phones")[0] if html_metadata.get("phones") else None,
        "linkedin_url": next((s for s in html_metadata.get("social_links", []) if "linkedin.com" in s), None),
        "instagram_url": next((s for s in html_metadata.get("social_links", []) if "instagram.com" in s), None),
        "facebook_url": next((s for s in html_metadata.get("social_links", []) if "facebook.com" in s), None),
        
        # Deducciones del algoritmo heurístico basado en el contexto del vendedor
        "inferred_tech_stack": extracted_data.get("inferred_tech_stack"),
        "inferred_niche": extracted_data.get("inferred_niche"),
        "generic_attributes": extracted_data.get("generic_attributes"),
        "estimated_revenue_signal": extracted_data.get("estimated_revenue_signal"),
        "has_active_ads": extracted_data.get("has_active_ads"),
        "hiring_signals": extracted_data.get("hiring_signals", False),
        
        # Auditoría de origen
        "source": "HTTPX_Scraper",
        "source_url": target_url,
        "job_id": job_context.get("job_id")  # Será asociado a la métrica padre
    }
    
    logger.info(f"Terminado el procesamiento para {domain}. Fusión de datos exitosa.")
    return final_prospect
