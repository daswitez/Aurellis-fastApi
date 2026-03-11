import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

def detect_technologies(html_content: str) -> List[str]:
    """
    Busca firmas muy básicas en el HTML (clases, scripts, meta tags)
    para deducir herramientas comunes, sin depender de librerías pesadas 
    en esta fase MVP.
    """
    html_lower = html_content.lower()
    tech_stack = []
    
    signatures = {
        "WordPress": ["wp-content", "wp-includes", "generator\" content=\"wordpress"],
        "Shopify": ["cdn.shopify", "shopify.com"],
        "React": ["data-reactroot", "_react_"],
        "Next.js": ["_next/static", "__next"],
        "Google Analytics": ["google-analytics.com/analytics.js", "gtag("],
        "Facebook Pixel": ["fbevents.js"],
        "Stripe": ["js.stripe.com"],
    }
    
    for tech, sigs in signatures.items():
        if any(sig in html_lower for sig in sigs):
            tech_stack.append(tech)
            
    return tech_stack

def has_hiring_signals(text_content: str, metadata: Dict) -> bool:
    """Busca en el texto y links internos señales de vacantes activas."""
    text_lower = text_content.lower()
    keywords = ["trabaja con nosotros", "únete al equipo", "vacantes", "careers", "we are hiring", "open positions"]
    
    # Check en texto
    if any(kw in text_lower for kw in keywords):
        return True
    
    # Check en links url detectados por BS4
    for link in metadata.get("internal_links", []):
        link_lower = link.lower()
        if any(kw in link_lower for kw in ["career", "trabajo", "empleo", "join-us"]):
            return True
            
    return False

async def extract_business_entity_heuristic(clean_text: str, html_raw: str, metadata: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extrae la entidad de negocio utilizando RegEx, palabras clave y heurísticas en código puro.
    NO consume APIs externas ni gasta dinero. Funciona analizando los patrones guardados.
    """
    
    logger.info(f"Procesando extración heurística offline.")
    
    # 1. Detección de Tecnologías
    inferred_tech_stack = detect_technologies(html_raw)
    
    # 2. Señales de pago / Inversión publicitaria
    # Si tienen FB Pixel o Google Ads Tag, es alta probabilidad de active_ads
    has_active_ads = "Facebook Pixel" in inferred_tech_stack
    
    # 3. Señales de Contratación
    hiring_signals = has_hiring_signals(clean_text, metadata)
    
    # 4. Estimación cruda de Niche basado en keywords del target_niche provisto
    # En el MVP, si el cliente busca "Restaurantes", comprobamos si esa palabra aparece.
    niche_lower = context.get("target_niche", "").lower()
    inferred_niche = None
    if niche_lower and (niche_lower in clean_text.lower() or niche_lower in metadata.get("title", "").lower()):
        inferred_niche = context.get("target_niche")
    
    # 5. Armado de la respuesta estructurada sin IA
    heuristic_response = {
        # Usamos el titulo original como nombre de empresa por defecto si es MVP manual
        "company_name": metadata.get("title", "").split("|")[0].strip(),
        "category": inferred_niche or "Desconocido",
        "location": "No disponible sin API", 
        "description": metadata.get("description", "Sin descripción META encontrada."),
        "inferred_tech_stack": inferred_tech_stack,
        "inferred_niche": inferred_niche,
        "hiring_signals": hiring_signals,
        "estimated_revenue_signal": "medium" if has_active_ads or hiring_signals else "low",
        "has_active_ads": has_active_ads,
        "score": 0.0,
        "confidence_level": "low",
        "generic_attributes": {
            "evaluation_method": "Heuristic Code (No LLM)",
            "pain_points_detected": [] # Aquí se podrían meter RegEx de los dolores del cliente
        }
    }
    
    return heuristic_response
