import asyncio
import logging
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import JobProspect, Prospect, ScrapingJob, ScrapingLog
from app.api.schemas import JobAISummary, JobCreateRequest, JobLogOut, JobLogsResponse, JobQualitySummary, JobResponse, ProspectOut, ScrapingLogLevel
from app.scraper.engine import scrape_single_prospect
from app.scraper.http_client import FetchHtmlError
from app.scraper.search_engines.ddg_search import SearchDiscoveryEntry, SearchDiscoveryResult, find_prospect_urls_by_queries
from app.services.discovery import build_discovery_queries
from app.services.db_upsert import save_scraped_prospect
from app.services.source_metadata import normalize_discovery_method, normalize_source_type

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["Jobs"])


def _utcnow() -> datetime:
    return datetime.utcnow()


async def _append_job_log(
    db: AsyncSession,
    job_id: int,
    level: str,
    message: str,
    *,
    source_name: str | None = None,
    context_json: dict | None = None,
) -> None:
    db.add(
        ScrapingLog(
            job_id=job_id,
            level=level,
            message=message,
            source_name=source_name,
            context_json=context_json,
        )
    )


def _job_summary_message(job: ScrapingJob) -> str:
    if job.status == "completed":
        return (
            f"Completado en {job.finished_at} | "
            f"Procesadas: {job.total_processed}, guardadas: {job.total_saved}, "
            f"omitidas: {job.total_skipped}, fallidas: {job.total_failed}"
        )
    if job.status == "failed":
        return f"Falló en {job.finished_at} | {job.error_message or 'Error no especificado'}"
    if job.status == "running":
        return (
            f"En ejecución desde {job.started_at} | "
            f"Procesadas: {job.total_processed}, guardadas: {job.total_saved}, "
            f"omitidas: {job.total_skipped}, fallidas: {job.total_failed}"
        )
    return "Pendiente"


def _build_job_context(
    job: ScrapingJob,
    *,
    search_query: str | None,
    discovery_method: str | None,
    source_type: str | None,
    search_warning: str | None,
) -> dict:
    return {
        "job_id": job.id,
        "workspace_id": job.workspace_id,
        "user_profession": job.user_profession,
        "user_technologies": job.user_technologies,
        "user_value_proposition": job.user_value_proposition,
        "user_past_successes": job.user_past_successes,
        "user_roi_metrics": job.user_roi_metrics,
        "target_niche": job.target_niche,
        "target_location": job.target_location,
        "target_language": job.target_language,
        "target_company_size": job.target_company_size,
        "target_pain_points": job.target_pain_points,
        "target_budget_signals": job.target_budget_signals,
        "search_query": search_query,
        "discovery_queries": [],
        "discovery_method": normalize_discovery_method(discovery_method),
        "source_type": normalize_source_type(source_type),
        "search_warning": search_warning,
    }


def _serialize_job_log(log: ScrapingLog) -> JobLogOut:
    context = log.context_json or {}
    return JobLogOut(
        id=log.id,
        created_at=log.created_at,
        level=log.level,
        message=log.message,
        source_name=log.source_name,
        context_json=context or None,
        stage=context.get("stage"),
        error_type=context.get("error_type"),
        status_code=context.get("status_code"),
        retryable=context.get("retryable"),
        attempts_made=context.get("attempts_made"),
        url=context.get("url"),
        rank_position=context.get("rank_position"),
        error=context.get("error"),
    )


def _summarize_ai_usage(raw_extractions: list[dict | None]) -> JobAISummary:
    attempts = 0
    successes = 0
    fallbacks = 0
    fallback_reasons: dict[str, int] = {}
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_tokens = 0
    total_latency_ms = 0
    estimated_cost_usd = 0.0
    cost_samples = 0

    for raw_extraction in raw_extractions:
        if not isinstance(raw_extraction, dict):
            continue

        ai_trace = raw_extraction.get("ai_trace")
        if not isinstance(ai_trace, dict):
            continue
        if ai_trace.get("status") == "skipped":
            continue

        attempts += 1
        total_prompt_tokens += int(ai_trace.get("prompt_tokens") or 0)
        total_completion_tokens += int(ai_trace.get("completion_tokens") or 0)
        total_tokens += int(ai_trace.get("total_tokens") or 0)
        total_latency_ms += int(ai_trace.get("latency_ms") or 0)
        if ai_trace.get("estimated_cost_usd") is not None:
            estimated_cost_usd += float(ai_trace.get("estimated_cost_usd") or 0.0)
            cost_samples += 1
        if ai_trace.get("selected_method") == "heuristic":
            fallbacks += 1
            fallback_reason = ai_trace.get("fallback_reason")
            if isinstance(fallback_reason, str) and fallback_reason:
                fallback_reasons[fallback_reason] = fallback_reasons.get(fallback_reason, 0) + 1
        else:
            successes += 1

    fallback_ratio = round((fallbacks / attempts), 4) if attempts else 0.0
    return JobAISummary(
        attempts=attempts,
        successes=successes,
        fallbacks=fallbacks,
        fallback_ratio=fallback_ratio,
        fallback_reasons=fallback_reasons,
        total_prompt_tokens=total_prompt_tokens,
        total_completion_tokens=total_completion_tokens,
        total_tokens=total_tokens,
        total_latency_ms=total_latency_ms,
        average_latency_ms=round((total_latency_ms / attempts), 2) if attempts else 0.0,
        estimated_cost_usd=round(estimated_cost_usd, 8) if cost_samples else None,
    )


async def _get_job_ai_summary(db: AsyncSession, job_id: int) -> JobAISummary:
    result = await db.execute(
        select(JobProspect.raw_extraction_json).where(JobProspect.job_id == job_id)
    )
    raw_extractions = list(result.scalars().all())
    return _summarize_ai_usage(raw_extractions)


def _summarize_quality_usage(rows: list[tuple[str | None, str | None]]) -> JobQualitySummary:
    accepted = 0
    needs_review = 0
    rejected = 0
    rejection_reasons: dict[str, int] = {}

    for quality_status, rejection_reason in rows:
        if quality_status == "accepted":
            accepted += 1
        elif quality_status == "needs_review":
            needs_review += 1
        elif quality_status == "rejected":
            rejected += 1

        if isinstance(rejection_reason, str) and rejection_reason:
            rejection_reasons[rejection_reason] = rejection_reasons.get(rejection_reason, 0) + 1

    return JobQualitySummary(
        accepted=accepted,
        needs_review=needs_review,
        rejected=rejected,
        rejection_reasons=rejection_reasons,
    )


async def _get_job_quality_summary(db: AsyncSession, job_id: int) -> JobQualitySummary:
    result = await db.execute(
        select(JobProspect.quality_status, JobProspect.rejection_reason)
        .where(JobProspect.job_id == job_id)
    )
    rows = list(result.all())
    return _summarize_quality_usage(rows)


async def _get_recent_job_errors(db: AsyncSession, job_id: int, limit: int = 3) -> list[JobLogOut]:
    result = await db.execute(
        select(ScrapingLog)
        .where(ScrapingLog.job_id == job_id, ScrapingLog.level == "ERROR")
        .order_by(desc(ScrapingLog.created_at))
        .limit(limit)
    )
    return [_serialize_job_log(log) for log in result.scalars().all()]


async def background_scraping_worker(job_id: int, urls: list, job_context: dict):
    """
    Simulación de la cola que procesará los dominios solicitados en segundo plano
    sin colgar la API principal. 
    Nota: Redefinimos el engine aca o pasamos session_maker por seguridad de hilos,
    pero para este MVP podemos instanciar una nueva AsyncSession aquí dentro.
    """
    from app.database import AsyncSessionLocal
    
    logger.info(f"Worker Iniciado. Lanzando Scraping para Job {job_id}")
    
    async with AsyncSessionLocal() as db:
        try:
            job = await db.get(ScrapingJob, job_id)
            if not job:
                return

            job.status = "running"
            job.started_at = _utcnow()
            job.finished_at = None
            job.error_message = None
            job.total_found = len(urls)
            job.total_processed = 0
            job.total_saved = 0
            job.total_failed = 0
            job.total_skipped = 0
            ai_attempts = 0
            ai_successes = 0
            ai_fallbacks = 0
            ai_fallback_reasons: dict[str, int] = {}
            ai_prompt_tokens = 0
            ai_completion_tokens = 0
            ai_total_tokens = 0
            ai_total_latency_ms = 0
            ai_estimated_cost_usd = 0.0
            ai_cost_samples = 0
            await _append_job_log(
                db,
                job_id,
                "INFO",
                "Job iniciado",
                source_name="worker",
                context_json={
                    "total_urls": len(urls),
                    "discovery_method": job_context.get("discovery_method"),
                    "search_query": job_context.get("search_query"),
                },
            )
            await db.commit()
            
            for rank_position, entry in enumerate(urls, start=1):
                if isinstance(entry, SearchDiscoveryEntry):
                    discovery_entry = {
                        "url": entry.url,
                        "query": entry.query,
                        "position": entry.position or rank_position,
                        "title": entry.title,
                        "snippet": entry.snippet,
                        "discovery_confidence": entry.discovery_confidence,
                    }
                elif isinstance(entry, dict):
                    discovery_entry = dict(entry)
                else:
                    discovery_entry = {"url": str(entry)}

                url = str(discovery_entry.get("url"))
                job.total_processed += 1
                try:
                    prospect_dict = await scrape_single_prospect(
                        url,
                        {**job_context, "discovery_entry": discovery_entry},
                    )

                    if not prospect_dict:
                        job.total_skipped += 1
                        await _append_job_log(
                            db,
                            job_id,
                            "WARNING",
                            "URL omitida por falta de contenido scrapeable",
                            source_name="worker",
                            context_json={"url": url, "rank_position": rank_position, "discovery_query": discovery_entry.get("query")},
                        )
                        await db.commit()
                        await asyncio.sleep(2)
                        continue

                    prospect_dict["job_id"] = job_id
                    prospect_dict["rank_position"] = rank_position
                    ai_trace = prospect_dict.get("ai_trace")
                    if isinstance(ai_trace, dict):
                        if ai_trace.get("status") != "skipped":
                            ai_attempts += 1
                            ai_prompt_tokens += int(ai_trace.get("prompt_tokens") or 0)
                            ai_completion_tokens += int(ai_trace.get("completion_tokens") or 0)
                            ai_total_tokens += int(ai_trace.get("total_tokens") or 0)
                            ai_total_latency_ms += int(ai_trace.get("latency_ms") or 0)
                            if ai_trace.get("estimated_cost_usd") is not None:
                                ai_estimated_cost_usd += float(ai_trace.get("estimated_cost_usd") or 0.0)
                                ai_cost_samples += 1
                        fallback_reason = ai_trace.get("fallback_reason")
                        if ai_trace.get("status") == "skipped":
                            await _append_job_log(
                                db,
                                job_id,
                                "INFO",
                                "Enriquecimiento IA omitido por gate de calidad",
                                source_name="ai_enrichment",
                                context_json={
                                    "stage": "ai_enrichment",
                                    "url": url,
                                    "domain": prospect_dict.get("domain"),
                                    "rank_position": rank_position,
                                    "selected_method": ai_trace.get("selected_method"),
                                    "evaluation_method": ai_trace.get("evaluation_method"),
                                    "fallback_reason": fallback_reason,
                                    "quality_status": prospect_dict.get("quality_status"),
                                },
                            )
                        elif ai_trace.get("selected_method") == "heuristic":
                            ai_fallbacks += 1
                            if isinstance(fallback_reason, str) and fallback_reason:
                                ai_fallback_reasons[fallback_reason] = ai_fallback_reasons.get(fallback_reason, 0) + 1
                            await _append_job_log(
                                db,
                                job_id,
                                "WARNING",
                                "Fallback heurístico activado para enriquecimiento IA",
                                source_name="ai_enrichment",
                                context_json={
                                    "stage": "ai_enrichment",
                                    "url": url,
                                    "domain": prospect_dict.get("domain"),
                                    "rank_position": rank_position,
                                    "provider": ai_trace.get("provider"),
                                    "selected_method": ai_trace.get("selected_method"),
                                    "evaluation_method": ai_trace.get("evaluation_method"),
                                    "fallback_reason": fallback_reason,
                                    "error_type": ai_trace.get("error_type"),
                                    "retryable": ai_trace.get("retryable"),
                                    "latency_ms": ai_trace.get("latency_ms"),
                                    "prompt_tokens": ai_trace.get("prompt_tokens"),
                                    "completion_tokens": ai_trace.get("completion_tokens"),
                                    "total_tokens": ai_trace.get("total_tokens"),
                                    "estimated_cost_usd": ai_trace.get("estimated_cost_usd"),
                                },
                            )
                        else:
                            ai_successes += 1
                            await _append_job_log(
                                db,
                                job_id,
                                "INFO",
                                "Enriquecimiento IA completado",
                                source_name="ai_enrichment",
                                context_json={
                                    "stage": "ai_enrichment",
                                    "url": url,
                                    "domain": prospect_dict.get("domain"),
                                    "rank_position": rank_position,
                                    "provider": ai_trace.get("provider"),
                                    "selected_method": ai_trace.get("selected_method"),
                                    "evaluation_method": ai_trace.get("evaluation_method"),
                                    "latency_ms": ai_trace.get("latency_ms"),
                                    "prompt_tokens": ai_trace.get("prompt_tokens"),
                                    "completion_tokens": ai_trace.get("completion_tokens"),
                                    "total_tokens": ai_trace.get("total_tokens"),
                                    "estimated_cost_usd": ai_trace.get("estimated_cost_usd"),
                                },
                            )

                    saved_prospect = await save_scraped_prospect(db, prospect_dict, job_context)
                    if saved_prospect:
                        job.total_saved += 1
                        await _append_job_log(
                            db,
                            job_id,
                            "INFO",
                            "Prospecto persistido",
                            source_name="worker",
                            context_json={
                                "url": url,
                                "domain": saved_prospect.domain,
                                "rank_position": rank_position,
                                "quality_status": prospect_dict.get("quality_status"),
                                "rejection_reason": prospect_dict.get("rejection_reason"),
                            },
                        )
                    else:
                        job.total_failed += 1
                        await _append_job_log(
                            db,
                            job_id,
                            "ERROR",
                            "No se pudo persistir el prospecto",
                            source_name="worker",
                            context_json={"url": url, "rank_position": rank_position},
                        )
                    await db.commit()
                except Exception as e:
                    job.total_failed += 1
                    logger.error(f"Error procesando prospect {url}: {e}")
                    error_context = {
                        "url": url,
                        "rank_position": rank_position,
                        "error": str(e),
                    }
                    if isinstance(e, FetchHtmlError):
                        error_context.update({"stage": "fetch_html", **e.to_context()})
                    else:
                        error_context["stage"] = "processing"
                    await _append_job_log(
                        db,
                        job_id,
                        "ERROR",
                        "Fallo procesando URL",
                        source_name="worker",
                        context_json=error_context,
                    )
                    await db.commit()

                await asyncio.sleep(2) 

            job.status = "completed"
            job.finished_at = _utcnow()
            await _append_job_log(
                db,
                job_id,
                "INFO",
                "Job finalizado",
                source_name="worker",
                context_json={
                    "total_found": job.total_found,
                    "total_processed": job.total_processed,
                    "total_saved": job.total_saved,
                    "total_failed": job.total_failed,
                    "total_skipped": job.total_skipped,
                    "ai_attempts": ai_attempts,
                    "ai_successes": ai_successes,
                    "ai_fallbacks": ai_fallbacks,
                    "ai_fallback_ratio": round((ai_fallbacks / ai_attempts), 4) if ai_attempts else 0.0,
                    "ai_fallback_reasons": ai_fallback_reasons,
                    "ai_prompt_tokens": ai_prompt_tokens,
                    "ai_completion_tokens": ai_completion_tokens,
                    "ai_total_tokens": ai_total_tokens,
                    "ai_total_latency_ms": ai_total_latency_ms,
                    "ai_average_latency_ms": round((ai_total_latency_ms / ai_attempts), 2) if ai_attempts else 0.0,
                    "ai_estimated_cost_usd": round(ai_estimated_cost_usd, 8) if ai_cost_samples else None,
                },
            )
            await db.commit()
            
            logger.info(f"Worker finalizado para Job {job_id} | Insertados: {job.total_saved}")
            
        except Exception as e:
            logger.error(f"Falla total en Worker del Job {job_id}: {str(e)}")
            job = await db.get(ScrapingJob, job_id)
            if job:
                job.status = "failed"
                job.finished_at = _utcnow()
                job.error_message = str(e)
                await _append_job_log(
                    db,
                    job_id,
                    "ERROR",
                    "Falla total del worker",
                    source_name="worker",
                    context_json={"error": str(e)},
                )
                await db.commit()


@router.post("/scrape", response_model=JobResponse, response_model_exclude_none=True, status_code=202)
async def create_scraping_job(
    payload: JobCreateRequest, 
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Recibe la intención de búsqueda desde NestJS.
    Si trae `search_query` y NO trae `urls`, buscará en DDG automáticamente.
    Guarda el Job con PENDING y delega el scraping a una BackgroundTask.
    """
    
    # 0. Lógica de "Buscador Automático" vs "URLs Directas"
    final_urls = [SearchDiscoveryEntry(url=str(u), position=index, discovery_confidence="high") for index, u in enumerate(payload.urls or [], start=1)]
    discovery_result = SearchDiscoveryResult(
        entries=final_urls,
        source_type=normalize_source_type("seed_url") or "seed_url",
        discovery_method=normalize_discovery_method("seed_url") or "seed_url",
    )
    
    canonical_queries = build_discovery_queries(
        search_query=payload.search_query,
        target_niche=payload.target_niche,
        target_location=payload.target_location,
        target_language=payload.target_language,
    )

    if not final_urls and canonical_queries:
        # Modo Búsqueda: Descubrir URLs asíncronamente antes de guardar el Job
        logger.info("Modo Buscador Activado para queries canonicas: %s", canonical_queries)
        discovery_result = await find_prospect_urls_by_queries(canonical_queries, max_results=payload.max_results)
        final_urls = discovery_result.entries
        
    if not final_urls:
        raise HTTPException(
            status_code=400,
            detail=discovery_result.warning_message
            or "No se encontraron URLs con ese query, o no enviaste ni 'urls' ni 'search_query'.",
        )
    
    # Armar la entidad en BD mapeando los atributos de Pydantic al modelo de SQLAlchemy
    new_job = ScrapingJob(
        status="pending",
        user_profession=payload.user_profession,
        user_technologies=payload.user_technologies,
        user_value_proposition=payload.user_value_proposition,
        user_past_successes=payload.user_past_successes,
        user_roi_metrics=payload.user_roi_metrics,
        target_niche=payload.target_niche,
        target_location=payload.target_location,
        target_language=payload.target_language,
        target_company_size=payload.target_company_size,
        target_pain_points=payload.target_pain_points,
        target_budget_signals=payload.target_budget_signals,
        source_type=normalize_source_type(discovery_result.source_type),
        filters_json={"max_results": payload.max_results}
    )
    
    db.add(new_job)
    await db.commit()
    await db.refresh(new_job)
    await _append_job_log(
        db,
        new_job.id,
        "INFO",
        "Job creado y encolado",
        source_name="api",
        context_json={
            "search_query": payload.search_query,
            "urls_count": len(final_urls),
            "discovery_queries": discovery_result.queries or canonical_queries,
            "discovery_method": normalize_discovery_method(discovery_result.discovery_method),
            "source_type": normalize_source_type(discovery_result.source_type),
            "warning_message": discovery_result.warning_message,
            "excluded_results_count": len(discovery_result.excluded_results),
        },
    )
    await db.commit()
    
    job_context = _build_job_context(
        new_job,
        search_query=payload.search_query,
        discovery_method=discovery_result.discovery_method,
        source_type=discovery_result.source_type,
        search_warning=discovery_result.warning_message,
    )
    job_context["discovery_queries"] = discovery_result.queries or canonical_queries
    
    # Encolar la tarea en FastAPI usando las URLs finales descubiertas
    background_tasks.add_task(
        background_scraping_worker, 
        job_id=new_job.id, 
        urls=final_urls,
        job_context=job_context,
    )
    
    return JobResponse(
        job_id=new_job.id,
        status=new_job.status,
        message=(
            f"Trabajo encolado. Procesando {len(final_urls)} dominios encontrados."
            if not discovery_result.warning_message
            else f"Trabajo encolado. Procesando {len(final_urls)} dominios encontrados. Aviso: {discovery_result.warning_message}"
        ),
        source_type=normalize_source_type(new_job.source_type),
        created_at=new_job.created_at,
        updated_at=new_job.updated_at,
        total_found=len(final_urls),
    )

@router.get("/{job_id}", response_model=JobResponse, response_model_exclude_none=True)
async def get_job_status(job_id: int, db: AsyncSession = Depends(get_db)):
    """Permite saber a NestJS u otro servicio si el Job terminó de scrapear"""
    job = await db.get(ScrapingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado.")
    recent_errors = await _get_recent_job_errors(db, job_id)
    ai_summary = await _get_job_ai_summary(db, job_id)
    quality_summary = await _get_job_quality_summary(db, job_id)
        
    return JobResponse(
        job_id=job.id,
        status=job.status,
        message=_job_summary_message(job),
        source_type=normalize_source_type(job.source_type),
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        total_found=job.total_found,
        total_processed=job.total_processed,
        total_saved=job.total_saved,
        total_failed=job.total_failed,
        total_skipped=job.total_skipped,
        error_message=job.error_message,
        ai_summary=ai_summary,
        quality_summary=quality_summary,
        recent_errors=recent_errors,
    )
    
@router.get("/{job_id}/results", response_model=List[ProspectOut])
async def get_job_results(job_id: int, limit: int = 50, offset: int = 0, db: AsyncSession = Depends(get_db)):
    """Devuelve la lista paginada de prospectos obtenidos por un Job"""
    job = await db.get(ScrapingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado.")

    query = (
        select(JobProspect, Prospect)
        .join(Prospect, Prospect.id == JobProspect.prospect_id)
        .where(JobProspect.job_id == job_id, JobProspect.quality_status == "accepted")
        .order_by(JobProspect.rank_position.asc(), JobProspect.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    rows = result.all()

    return [
        ProspectOut(
            id=prospect.id,
            company_name=prospect.company_name,
            domain=prospect.domain,
            website_url=prospect.website_url,
            source_url=job_prospect.source_url or prospect.source_url,
            source_type=normalize_source_type(job_prospect.source_type),
            discovery_method=normalize_discovery_method(job_prospect.discovery_method),
            search_query_snapshot=job_prospect.search_query_snapshot,
            rank_position=job_prospect.rank_position,
            email=prospect.email,
            phone=prospect.phone,
            linkedin_url=prospect.linkedin_url,
            instagram_url=prospect.instagram_url,
            facebook_url=prospect.facebook_url,
            score=job_prospect.match_score if job_prospect.match_score is not None else prospect.score,
            confidence_level=job_prospect.confidence_level or prospect.confidence_level,
            inferred_niche=prospect.inferred_niche,
            inferred_tech_stack=prospect.inferred_tech_stack,
            generic_attributes=prospect.generic_attributes,
            estimated_revenue_signal=prospect.estimated_revenue_signal,
            has_active_ads=prospect.has_active_ads,
            hiring_signals=prospect.hiring_signals,
            description=prospect.description,
            location=prospect.location,
            validated_location=prospect.validated_location,
            location_match_status=prospect.location_match_status,
            location_confidence=prospect.location_confidence,
            detected_language=prospect.detected_language,
            language_match_status=prospect.language_match_status,
            primary_cta=prospect.primary_cta,
            booking_url=prospect.booking_url,
            pricing_page_url=prospect.pricing_page_url,
            category=prospect.category,
        )
        for job_prospect, prospect in rows
    ]


@router.get("/{job_id}/logs", response_model=JobLogsResponse, response_model_exclude_none=True)
async def get_job_logs(
    job_id: int,
    limit: int = 50,
    offset: int = 0,
    level: ScrapingLogLevel | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Devuelve logs persistidos del job para debugging operativo."""
    job = await db.get(ScrapingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado.")

    base_filters = [ScrapingLog.job_id == job_id]
    if level:
        base_filters.append(ScrapingLog.level == level)

    total = await db.scalar(
        select(func.count())
        .select_from(ScrapingLog)
        .where(*base_filters)
    )

    result = await db.execute(
        select(ScrapingLog)
        .where(*base_filters)
        .order_by(desc(ScrapingLog.created_at))
        .offset(offset)
        .limit(limit)
    )
    logs = result.scalars().all()

    return JobLogsResponse(
        job_id=job_id,
        total=total or 0,
        limit=limit,
        offset=offset,
        items=[_serialize_job_log(log) for log in logs],
    )
