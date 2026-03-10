import asyncio
import logging
from typing import List
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models import ScrapingJob
from app.api.schemas import JobCreateRequest, JobResponse, ProspectOut
from app.scraper.engine import scrape_single_prospect
from app.scraper.search_engines.ddg_search import find_prospect_urls_by_query
from app.services.db_upsert import upsert_prospect

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["Jobs"])

async def background_scraping_worker(job_id: int, urls: list, job_context: dict, db_url: str):
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
            # 1. Marcar el job como RUNNING
            job = await db.get(ScrapingJob, job_id)
            if not job:
                return
            job.status = "running"
            await db.commit()
            
            # 2. Ejecutar cada scrape
            total_saved = 0
            for url in urls:
                prospect_dict = await scrape_single_prospect(str(url), job_context)
                
                if prospect_dict:
                    # Inyectar el ID real
                    prospect_dict["job_id"] = job_id
                    
                    # 3. Guardar en Base de Datos (Upsert ASYNC)
                    try:
                        saved_prospect = await upsert_prospect(db, prospect_dict)
                        if saved_prospect:
                            total_saved += 1
                    except Exception as e:
                        logger.error(f"Error upserting prospect {url}: {e}")
                        
                # Simulamos control de taza para no fundir los targets (Rate Limiting básico)
                await asyncio.sleep(2) 

            # 4. Actualizar métricas finales
            job.total_saved = total_saved
            job.total_found = len(urls)
            job.status = "completed"
            await db.commit()
            
            logger.info(f"Worker finalizado para Job {job_id} | Insertados: {total_saved}")
            
        except Exception as e:
            logger.error(f"Falla total en Worker del Job {job_id}: {str(e)}")
            job = await db.get(ScrapingJob, job_id)
            if job:
                job.status = "failed"
                job.error_message = str(e)
                await db.commit()


@router.post("/scrape", response_model=JobResponse, status_code=202)
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
    
    if not final_urls and payload.search_query:
        # Modo Búsqueda: Descubrir URLs asíncronamente antes de guardar el Job
        logger.info(f"Modo Buscador Activado para: {payload.search_query}")
        final_urls = await find_prospect_urls_by_query(payload.search_query, max_results=payload.max_results)
        
    if not final_urls:
        raise HTTPException(status_code=400, detail="No se encontraron URLs con ese query, o no enviaste ni 'urls' ni 'search_query'.")
    
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
        filters_json={"max_results": payload.max_results}
    )
    
    db.add(new_job)
    await db.commit()
    await db.refresh(new_job)
    
    # Preparar el contexto diccionario para el motor de Python puro (evitar problemas de sesión ORM en background)
    job_context = {
        "job_id": new_job.id,
        "user_profession": new_job.user_profession,
        "user_value_proposition": new_job.user_value_proposition,
        "target_niche": new_job.target_niche,
        "target_pain_points": new_job.target_pain_points
    }
    
    # Encolar la tarea en FastAPI usando las URLs finales descubiertas
    background_tasks.add_task(
        background_scraping_worker, 
        job_id=new_job.id, 
        urls=final_urls, 
        job_context=job_context,
        db_url="internal"
    )
    
    # Retornar ID rápido para que NestJS sepa a quién consultar o referenciar
    return JobResponse(
        job_id=new_job.id,
        status=new_job.status,
        message=f"Trabajo encolado. Procesando {len(final_urls)} dominios encontrados."
    )

@router.get("/{job_id}", response_model=JobResponse)
async def get_job_status(job_id: int, db: AsyncSession = Depends(get_db)):
    """Permite saber a NestJS u otro servicio si el Job terminó de scrapear"""
    job = await db.get(ScrapingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado.")
        
    return JobResponse(
        job_id=job.id,
        status=job.status,
        message=f"Terminó en {job.finished_at}" if job.status == "completed" else "Ejecutándose o pendiente"
    )
    
@router.get("/{job_id}/results", response_model=List[ProspectOut])
async def get_job_results(job_id: int, limit: int = 50, offset: int = 0, db: AsyncSession = Depends(get_db)):
    """Devuelve la lista paginada de prospectos obtenidos por un Job"""
    from app.models import Prospect
    
    # 1. Verificar existencia de job
    job = await db.get(ScrapingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado.")
        
    # 2. Query con paginación nativa de SQL
    query = select(Prospect).where(Prospect.job_id == job_id).offset(offset).limit(limit)
    result = await db.execute(query)
    prospects = result.scalars().all()
    
    return prospects
