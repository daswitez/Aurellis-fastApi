import asyncio
import logging
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import JobProspect, Prospect, ScrapingJob, ScrapingLog
from app.api.schemas import JobCreateRequest, JobLogOut, JobLogsResponse, JobResponse, ProspectOut, ScrapingLogLevel
from app.scraper.engine import scrape_single_prospect
from app.scraper.http_client import FetchHtmlError
from app.scraper.search_engines.ddg_search import SearchDiscoveryResult, find_prospect_urls_by_query
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
            
            for rank_position, url in enumerate(urls, start=1):
                job.total_processed += 1
                try:
                    prospect_dict = await scrape_single_prospect(str(url), job_context)

                    if not prospect_dict:
                        job.total_skipped += 1
                        await _append_job_log(
                            db,
                            job_id,
                            "WARNING",
                            "URL omitida por falta de contenido scrapeable",
                            source_name="worker",
                            context_json={"url": str(url), "rank_position": rank_position},
                        )
                        await db.commit()
                        await asyncio.sleep(2)
                        continue

                    prospect_dict["job_id"] = job_id
                    prospect_dict["rank_position"] = rank_position

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
                                "url": str(url),
                                "domain": saved_prospect.domain,
                                "rank_position": rank_position,
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
                            context_json={"url": str(url), "rank_position": rank_position},
                        )
                    await db.commit()
                except Exception as e:
                    job.total_failed += 1
                    logger.error(f"Error procesando prospect {url}: {e}")
                    error_context = {
                        "url": str(url),
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
    final_urls = [str(u) for u in payload.urls] if payload.urls else []
    discovery_result = SearchDiscoveryResult(
        urls=final_urls,
        source_type=normalize_source_type("seed_url") or "seed_url",
        discovery_method=normalize_discovery_method("seed_url") or "seed_url",
    )
    
    if not final_urls and payload.search_query:
        # Modo Búsqueda: Descubrir URLs asíncronamente antes de guardar el Job
        logger.info(f"Modo Buscador Activado para: {payload.search_query}")
        discovery_result = await find_prospect_urls_by_query(payload.search_query, max_results=payload.max_results)
        final_urls = discovery_result.urls
        
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
            "discovery_method": normalize_discovery_method(discovery_result.discovery_method),
            "source_type": normalize_source_type(discovery_result.source_type),
            "warning_message": discovery_result.warning_message,
        },
    )
    await db.commit()
    
    job_context = {
        "job_id": new_job.id,
        "workspace_id": new_job.workspace_id,
        "user_profession": new_job.user_profession,
        "user_technologies": new_job.user_technologies,
        "user_value_proposition": new_job.user_value_proposition,
        "user_past_successes": new_job.user_past_successes,
        "user_roi_metrics": new_job.user_roi_metrics,
        "target_niche": new_job.target_niche,
        "target_pain_points": new_job.target_pain_points,
        "target_budget_signals": new_job.target_budget_signals,
        "search_query": payload.search_query,
        "discovery_method": normalize_discovery_method(discovery_result.discovery_method),
        "source_type": normalize_source_type(discovery_result.source_type),
        "search_warning": discovery_result.warning_message,
    }
    
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
        .where(JobProspect.job_id == job_id)
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
