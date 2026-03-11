from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl

JobStatus = Literal["pending", "running", "completed", "failed"]
RevenueSignal = Literal["low", "medium", "high"]
ConfidenceLevel = Literal["low", "medium", "high"]
MatchStatus = Literal["match", "mismatch", "unknown"]
ProspectQualityStatus = Literal["accepted", "needs_review", "rejected"]
ResultSourceType = Literal["duckduckgo_search", "mock_search", "seed_url", "manual", "enrichment"]
DiscoveryMethod = Literal["search_query", "seed_url", "manual", "enrichment"]
ScrapingLogLevel = Literal["INFO", "WARNING", "ERROR"]

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
    target_accepted_results: Optional[int] = Field(default=None, ge=1, le=100)
    max_candidates_to_process: Optional[int] = Field(default=None, ge=1, le=300)
    
    
class JobLogOut(BaseModel):
    id: int
    created_at: datetime
    level: ScrapingLogLevel
    message: str
    source_name: Optional[str] = None
    context_json: Optional[Dict[str, Any]] = None
    stage: Optional[str] = None
    error_type: Optional[str] = None
    status_code: Optional[int] = None
    retryable: Optional[bool] = None
    attempts_made: Optional[int] = None
    url: Optional[str] = None
    rank_position: Optional[int] = None
    error: Optional[str] = None


class JobLogsResponse(BaseModel):
    job_id: int
    total: int
    limit: int
    offset: int
    items: List[JobLogOut] = Field(default_factory=list)


class JobAISummary(BaseModel):
    attempts: int = 0
    successes: int = 0
    fallbacks: int = 0
    fallback_ratio: float = 0.0
    fallback_reasons: Dict[str, int] = Field(default_factory=dict)
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_latency_ms: int = 0
    average_latency_ms: float = 0.0
    estimated_cost_usd: Optional[float] = None


class JobQualitySummary(BaseModel):
    accepted: int = 0
    needs_review: int = 0
    rejected: int = 0
    rejection_reasons: Dict[str, int] = Field(default_factory=dict)


class JobCaptureSummary(BaseModel):
    target_accepted_results: int = 0
    max_candidates_to_process: int = 0
    accepted_count: int = 0
    needs_review_count: int = 0
    rejected_count: int = 0
    candidates_processed: int = 0
    candidates_discovered: int = 0
    acceptance_rate: float = 0.0
    candidate_dropoff_by_reason: Dict[str, int] = Field(default_factory=dict)
    stopped_reason: Optional[str] = None


class JobOperationalSummary(BaseModel):
    completed_with_zero_accepted: bool = False
    candidates_per_accepted: Optional[float] = None
    article_exclusion_count: int = 0
    directory_exclusion_count: int = 0
    article_directory_exclusion_ratio: float = 0.0


class JobsOperationalMetricsResponse(BaseModel):
    total_jobs: int = 0
    completed_jobs: int = 0
    completed_jobs_with_zero_accepted: int = 0
    completed_jobs_with_zero_accepted_ratio: float = 0.0
    average_acceptance_rate: float = 0.0
    average_candidates_per_accepted: float = 0.0
    average_article_directory_exclusion_ratio: float = 0.0
    total_candidates_processed: int = 0
    total_accepted: int = 0
    total_article_exclusions: int = 0
    total_directory_exclusions: int = 0


class JobResponse(BaseModel):
    """Estructura de la respuesta al crear o consultar un Job"""
    job_id: int
    status: JobStatus
    message: str
    source_type: Optional[ResultSourceType] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    total_found: Optional[int] = None
    total_processed: Optional[int] = None
    total_saved: Optional[int] = None
    total_failed: Optional[int] = None
    total_skipped: Optional[int] = None
    error_message: Optional[str] = None
    ai_summary: Optional[JobAISummary] = None
    quality_summary: Optional[JobQualitySummary] = None
    capture_summary: Optional[JobCaptureSummary] = None
    operational_summary: Optional[JobOperationalSummary] = None
    recent_errors: List[JobLogOut] = Field(default_factory=list)
    
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
    quality_status: Optional[ProspectQualityStatus]
    rejection_reason: Optional[str]

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
    validated_location: Optional[str]
    location_match_status: Optional[MatchStatus]
    location_confidence: Optional[ConfidenceLevel]
    detected_language: Optional[str]
    language_match_status: Optional[MatchStatus]
    primary_cta: Optional[str]
    booking_url: Optional[str]
    pricing_page_url: Optional[str]
    category: Optional[str]

    class Config:
        from_attributes = True
