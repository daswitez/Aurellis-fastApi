from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Any, Dict

class JobCreateRequest(BaseModel):
    """Payload entrante para crear un Job de Scraping desde NestJS"""
    
    # 1. Target general opcional
    urls: Optional[List[HttpUrl]] = [] # Links específicos a scrapear ("Semillas")
    search_query: Optional[str] = None # En vez de URLs, un termino ej: "Dentistas en Madrid"
    
    # 2. Contexto del Vendedor (Para matching de similitud local)
    user_profession: Optional[str] = "Editor de Video"
    user_technologies: Optional[List[str]] = ["Premiere"]
    user_value_proposition: Optional[str] = "Retención de audiencia"
    user_past_successes: Optional[List[str]] = []
    user_roi_metrics: Optional[List[str]] = []
    
    # 3. Contexto del Prospecto / Comprador Ideal
    target_niche: Optional[str] = "YouTubers"
    target_location: Optional[str] = "España"
    target_language: Optional[str] = "es"
    target_company_size: Optional[str] = "Solopreneur"
    target_pain_points: Optional[List[str]] = ["Mala calidad de video"]
    target_budget_signals: Optional[List[str]] = ["Anuncios activos"]
    
    # 4. Meta del Trabajo (Opcional, previene que se desborde al inicio)
    max_results: int = 10 
    
    
class JobResponse(BaseModel):
    """Estructura de la respuesta al crear o consultar un Job"""
    job_id: int
    status: str
    message: str 
    
class ProspectOut(BaseModel):
    """Salida estandarizada de un Prospecto estructurado para JSON"""
    # Identificación
    id: int
    company_name: Optional[str]
    domain: str
    website_url: Optional[str]
    source_url: Optional[str]

    # Contacto
    email: Optional[str]
    phone: Optional[str]
    linkedin_url: Optional[str]
    instagram_url: Optional[str]
    facebook_url: Optional[str]

    # Análisis IA (DeepSeek)
    score: Optional[float]               # Match score 0-100 con el perfil del vendedor
    confidence_level: Optional[str]      # Confianza del análisis: low / medium / high
    inferred_niche: Optional[str]        # Nicho detectado por IA
    inferred_tech_stack: Optional[List[str]]  # Stack tecnológico detectado
    generic_attributes: Optional[Any]   # Pain points y metadata del análisis IA

    # Señales de negocio
    estimated_revenue_signal: Optional[str]  # low / medium / high
    has_active_ads: Optional[bool]
    hiring_signals: Optional[bool]       # ¿Está contratando activamente?

    # Descripción y ubicación
    description: Optional[str]
    location: Optional[str]
    category: Optional[str]

    class Config:
        from_attributes = True
