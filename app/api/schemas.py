from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl

JobStatus = Literal["pending", "running", "completed", "failed"]
RevenueSignal = Literal["low", "medium", "high"]
ConfidenceLevel = Literal["low", "medium", "high"]
ResultSourceType = Literal["duckduckgo_search", "mock_search", "seed_url", "manual", "enrichment"]
DiscoveryMethod = Literal["search_query", "seed_url", "manual", "enrichment"]

class JobCreateRequest(BaseModel):
    """Payload entrante para crear un Job de Scraping desde NestJS"""
    
    # 1. Target general opcional
    urls: Optional[List[HttpUrl]] = None  # Links específicos a scrapear ("Semillas")
    search_query: Optional[str] = None  # En vez de URLs, un termino ej: "Dentistas en Madrid"
    
    # 2. Contexto del Vendedor (Para matching de similitud local)
    user_profession: Optional[str] = None
    user_technologies: Optional[List[str]] = None
    user_value_proposition: Optional[str] = None
    user_past_successes: Optional[List[str]] = None
    user_roi_metrics: Optional[List[str]] = None
    
    # 3. Contexto del Prospecto / Comprador Ideal
    target_niche: Optional[str] = None
    target_location: Optional[str] = None
    target_language: Optional[str] = None
    target_company_size: Optional[str] = None
    target_pain_points: Optional[List[str]] = None
    target_budget_signals: Optional[List[str]] = None
    
    # 4. Meta del Trabajo (Opcional, previene que se desborde al inicio)
    max_results: int = Field(default=10, ge=1, le=100)
    
    
class JobResponse(BaseModel):
    """Estructura de la respuesta al crear o consultar un Job"""
    job_id: int
    status: JobStatus
    message: str 
    
class ProspectOut(BaseModel):
    """Salida estandarizada de un Prospecto estructurado para JSON"""
    # Identificación
    id: int
    company_name: Optional[str]
    domain: str
    website_url: Optional[str]
    source_url: Optional[str]
    source_type: Optional[ResultSourceType]
    discovery_method: Optional[DiscoveryMethod]
    search_query_snapshot: Optional[str]
    rank_position: Optional[int]

    # Contacto
    email: Optional[str]
    phone: Optional[str]
    linkedin_url: Optional[str]
    instagram_url: Optional[str]
    facebook_url: Optional[str]

    # Análisis IA (DeepSeek)
    score: Optional[float]  # Match score 0.0-1.0 con el perfil del vendedor
    confidence_level: Optional[ConfidenceLevel]
    inferred_niche: Optional[str]        # Nicho detectado por IA
    inferred_tech_stack: Optional[List[str]]  # Stack tecnológico detectado
    generic_attributes: Optional[Dict[str, Any]]

    # Señales de negocio
    estimated_revenue_signal: Optional[RevenueSignal]
    has_active_ads: Optional[bool]
    hiring_signals: Optional[bool]       # ¿Está contratando activamente?

    # Descripción y ubicación
    description: Optional[str]
    location: Optional[str]
    category: Optional[str]

    class Config:
        from_attributes = True
