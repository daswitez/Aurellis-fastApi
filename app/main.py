from fastapi import FastAPI
import logging
from app.api.jobs import router as jobs_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

app = FastAPI(
    title="Aurellis Scraping Service API",
    description="Servicio interno de scraping y enriquecimiento de prospectos.",
    version="1.0.0",
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
