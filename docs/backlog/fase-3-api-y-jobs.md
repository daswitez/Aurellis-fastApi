# Fase 3: API REST y Gestión Asíncrona de Jobs

**Objetivo:** Orquestar el motor de scraping (Fase 2) mediante Endpoints HTTP para que sea controlable externamente.

## 3.1. Endpoints de Scraping
- [ ] `POST /api/v1/jobs/scrape`: 
  - Recibe un JSON (payload) con parámetros como: listado de dominios semilla, o un término de búsqueda en una fuente específica.
  - Crea un registro en la tabla `scraping_jobs` en estado `PENDING` o `RUNNING`.
  - Dispara la ejecución del motor de scraping pasándole el "Job ID".
- [ ] Opcional: `POST /api/v1/jobs/enrich`: 
  - Recibe un solo dominio, hace el scraping al instante y devuelve el JSON enriquecido (endpoint síncrono para pruebas rápidas).

## 3.2. Gestión del Trabajo en Background (`BackgroundTasks`)
- [x] Implementar el orquestador usando la utilidad nativa `BackgroundTasks` de FastAPI.
- [x] La función orquestadora itera sobre la lista de prospectos objetivos.
- [x] Actualizar periódicamente estado y contadores (`total_found`, `total_processed`, `total_saved`, `total_failed`, `total_skipped`) en la tabla `scraping_jobs`.
- [x] Al finalizar, actualizar estado del job a `COMPLETED`. En caso de fallo crítico general, a `FAILED`, e insertar el log de error.
- [x] Implementar escritura de eventos a la tabla `scraping_logs`.

## 3.3. Endpoints de Resultados y Monitoreo
- [ ] `GET /api/v1/jobs/{job_id}`: Devuelve los metadatos y estatus del job (para que veamos si sigue corriendo).
- [ ] `GET /api/v1/jobs/{job_id}/results`: Devuelve el listado JSON de prospectos generados en ese trabajo.
- [ ] Paginación básica para el endpoint de resultados (limit, offset) para no colapsar si un job extrae 1,000 registros.
