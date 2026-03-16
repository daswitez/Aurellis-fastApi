from contextlib import asynccontextmanager

from fastapi import FastAPI
import logging
from app.api.jobs import router as jobs_router
from app.database import Base, engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(
    title="Aurellis Scraping Service API",
    description="Servicio interno de scraping y enriquecimiento de prospectos.",
    version="1.0.0",
    lifespan=lifespan,
)

# Integración del módulo de Scraping Jobs
app.include_router(jobs_router, prefix="/api/v1")

@app.get("/health", tags=["Health"])
async def health_check():
    """
    Endpoint de diagnóstico para asegurar que el servicio está vivo.
    """
    return {
        "status": "ok", 
        "message": "Scraping service is running"
    }
