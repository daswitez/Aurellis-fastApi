from fastapi import FastAPI

app = FastAPI(
    title="Aurellis Scraping Service API",
    description="Servicio interno de scraping y enriquecimiento de prospectos.",
    version="1.0.0",
)

@app.get("/health", tags=["Health"])
async def health_check():
    """
    Endpoint de diagnóstico para asegurar que el servicio está vivo.
    """
    return {
        "status": "ok", 
        "message": "Scraping service is running"
    }
