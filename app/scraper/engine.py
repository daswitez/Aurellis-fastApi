import logging
from typing import Dict, Any, Optional
from urllib.parse import urlparse

from app.scraper.http_client import FetchHtmlError, fetch_html
from app.scraper.parser import parse_html_basic
from app.services.ai_extractor import AIExtractionFallbackError, PROMPT_VERSION, extract_business_entity_ai
from app.services.heuristic_extractor import extract_business_entity_heuristic
from app.services.scoring import build_final_score

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


def _build_ai_trace(
    *,
    status: str,
    selected_method: str,
    evaluation_method: str,
    fallback_reason: str | None = None,
    error_type: str | None = None,
    retryable: bool | None = None,
    message: str | None = None,
    latency_ms: int | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    estimated_cost_usd: float | None = None,
) -> Dict[str, Any]:
    return {
        "provider": "deepseek",
        "prompt_version": PROMPT_VERSION,
        "status": status,
        "selected_method": selected_method,
        "evaluation_method": evaluation_method,
        "fallback_reason": fallback_reason,
        "error_type": error_type,
        "retryable": retryable,
        "message": message,
        "latency_ms": latency_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": estimated_cost_usd,
    }


def _pick_first_defined(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
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
    heuristic_baseline = await extract_business_entity_heuristic(combined_text, html_raw, merged_metadata, job_context)
    
    # 3. Extracción de Lógica de Negocio mediante Heurística de Código
    # [FASE 5] Invocación a Inteligencia Artificial para comprensión profunda (DeepSeek)
    # Fallback a heurística rápida si ocurre alguna excepción de red/API
    ai_trace: Dict[str, Any]
    try:
        extracted_data = await extract_business_entity_ai(domain, combined_text, job_context)
        ai_metrics = extracted_data.pop("_ai_metrics", {})
        evaluation_method = "DeepSeek API ({})".format(PROMPT_VERSION)
        generic_attributes = extracted_data.get("generic_attributes")
        if isinstance(generic_attributes, dict):
            evaluation_method = str(generic_attributes.get("evaluation_method") or evaluation_method)
        ai_trace = _build_ai_trace(
            status="success",
            selected_method="ai",
            evaluation_method=evaluation_method,
            latency_ms=ai_metrics.get("latency_ms"),
            prompt_tokens=ai_metrics.get("prompt_tokens"),
            completion_tokens=ai_metrics.get("completion_tokens"),
            total_tokens=ai_metrics.get("total_tokens"),
            estimated_cost_usd=ai_metrics.get("estimated_cost_usd"),
        )
    except AIExtractionFallbackError as ai_e:
        logger.warning(
            "Fallback heurístico para %s por %s [%s]",
            target_url,
            ai_e.reason,
            ai_e.error_type,
        )
        extracted_data = heuristic_baseline
        evaluation_method = "Heuristic Code (No LLM)"
        generic_attributes = extracted_data.get("generic_attributes")
        if isinstance(generic_attributes, dict):
            generic_attributes["fallback_reason"] = ai_e.reason
            generic_attributes["ai_error_type"] = ai_e.error_type
            evaluation_method = str(generic_attributes.get("evaluation_method") or evaluation_method)
        ai_trace = _build_ai_trace(
            status="fallback",
            selected_method="heuristic",
            evaluation_method=evaluation_method,
            fallback_reason=ai_e.reason,
            error_type=ai_e.error_type,
            retryable=ai_e.retryable,
            message=str(ai_e),
            latency_ms=ai_e.usage.get("latency_ms"),
            prompt_tokens=ai_e.usage.get("prompt_tokens"),
            completion_tokens=ai_e.usage.get("completion_tokens"),
            total_tokens=ai_e.usage.get("total_tokens"),
            estimated_cost_usd=ai_e.usage.get("estimated_cost_usd"),
        )
    except Exception as ai_e:
        logger.error(f"Error AI inesperado para {target_url}. Usando heurística fallback: {ai_e}")
        extracted_data = heuristic_baseline
        evaluation_method = "Heuristic Code (No LLM)"
        generic_attributes = extracted_data.get("generic_attributes")
        if isinstance(generic_attributes, dict):
            generic_attributes["fallback_reason"] = "unexpected_exception"
            generic_attributes["ai_error_type"] = "unexpected_exception"
            evaluation_method = str(generic_attributes.get("evaluation_method") or evaluation_method)
        ai_trace = _build_ai_trace(
            status="fallback",
            selected_method="heuristic",
            evaluation_method=evaluation_method,
            fallback_reason="unexpected_exception",
            error_type="unexpected_exception",
            retryable=False,
            message=str(ai_e),
        )

    final_scoring = build_final_score(
        ai_data=extracted_data,
        ai_trace=ai_trace,
        heuristic_data=heuristic_baseline,
    )
    
    # 4. Fusionar Data Fuerte (Metadatos reales de bs4 como correos visibles y links) 
    # con Data Deductiva (Adivinada por el Heurístico)
    internal_links = merged_metadata.get("internal_links", [])
    contact_page_url = _select_contact_page_url(internal_links)

    final_prospect = {
        "domain": domain,
        "website_url": target_url,
        "company_name": _pick_first_defined(extracted_data.get("company_name"), heuristic_baseline.get("company_name"), domain),
        "category": _pick_first_defined(extracted_data.get("category"), heuristic_baseline.get("category")),
        "location": _pick_first_defined(extracted_data.get("location"), heuristic_baseline.get("location")),
        "description": _pick_first_defined(extracted_data.get("description"), heuristic_baseline.get("description")),
        
        # Metadatos seguros de HTML (BeautifulSoup y Regex son asertivos)
        "email": merged_metadata.get("emails")[0] if merged_metadata.get("emails") else None,
        "phone": merged_metadata.get("phones")[0] if merged_metadata.get("phones") else None,
        "contact_page_url": contact_page_url,
        "form_detected": merged_metadata.get("form_detected", False),
        "linkedin_url": next((s for s in merged_metadata.get("social_links", []) if "linkedin.com" in s), None),
        "instagram_url": next((s for s in merged_metadata.get("social_links", []) if "instagram.com" in s), None),
        "facebook_url": next((s for s in merged_metadata.get("social_links", []) if "facebook.com" in s), None),
        
        # Deducciones del algoritmo heurístico basado en el contexto del vendedor
        "inferred_tech_stack": _pick_first_defined(extracted_data.get("inferred_tech_stack"), heuristic_baseline.get("inferred_tech_stack")),
        "inferred_niche": _pick_first_defined(extracted_data.get("inferred_niche"), heuristic_baseline.get("inferred_niche")),
        "generic_attributes": _pick_first_defined(extracted_data.get("generic_attributes"), heuristic_baseline.get("generic_attributes")),
        "estimated_revenue_signal": _pick_first_defined(extracted_data.get("estimated_revenue_signal"), heuristic_baseline.get("estimated_revenue_signal")),
        "has_active_ads": _pick_first_defined(extracted_data.get("has_active_ads"), heuristic_baseline.get("has_active_ads")),
        "hiring_signals": _pick_first_defined(extracted_data.get("hiring_signals"), heuristic_baseline.get("hiring_signals"), False),
        "score": final_scoring["score"],
        "confidence_level": final_scoring["confidence_level"],
        "fit_summary": final_scoring["fit_summary"],
        "heuristic_trace": heuristic_baseline.get("heuristic_trace"),
        "scoring_trace": final_scoring["scoring_trace"],
        
        # Auditoría de origen
        "source": "HTTPX_Scraper",
        "source_url": target_url,
        "job_id": job_context.get("job_id"),  # Será asociado a la métrica padre
        "internal_links": internal_links,
        "crawled_pages": crawled_pages,
        "ai_trace": ai_trace,
    }
    
    logger.info(f"Terminado el procesamiento para {domain}. Fusión de datos exitosa.")
    return final_prospect
