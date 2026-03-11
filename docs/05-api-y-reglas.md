# Documentación de Endpoints — Aurellis FastAPI

**Base URL:** `http://localhost:8000`  
**Docs interactivos (Swagger):** `http://localhost:8000/docs`

---

## Cómo Levantar el Servidor

```bash
# 1. Base de datos (Docker)
cp .env.example .env
docker compose up -d postgres

# 2. Entorno y servidor
source venv/bin/activate
python3 -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

---

## Cambios de Endpoints Respecto al MVP Inicial

Esta documentación ya no describe endpoints “propuestos”, sino el contrato actual del servicio después de las mejoras de estabilización y confiabilidad.

Los cambios más importantes fueron:

- `POST /api/v1/jobs/scrape`
  - dejó de inyectar defaults de negocio silenciosos;
  - distingue explícitamente resultados reales vs demo/mock;
  - guarda mejor el origen del job desde su creación.
- `GET /api/v1/jobs/{job_id}`
  - pasó de ser un polling mínimo a un endpoint de monitoreo;
  - ahora expone timestamps, métricas, resumen de calidad y errores recientes.
- `GET /api/v1/jobs/{job_id}/results`
  - ahora lee desde `job_prospects`, no desde la vieja asociación simple por `job_id`;
  - expone trazabilidad de origen por resultado.
- `GET /api/v1/jobs/{job_id}/logs`
  - es nuevo;
  - permite debugging operativo sin consultar Postgres manualmente.

Si querés ver el resumen técnico más amplio de todo lo implementado hasta acá, está en [09-cambios-implementados-hasta-fase-b.md](09-cambios-implementados-hasta-fase-b.md).

---

## Endpoints

### 1. `POST /api/v1/jobs/scrape` — Crear un Job de Scraping

Crea un trabajo de prospección. Retorna inmediatamente (`202 Accepted`) y procesa en segundo plano.

**Hay dos modos de uso:**

#### Modo A — Búsqueda Automática (recomendado)
Le das un término de búsqueda y la API busca URLs en DuckDuckGo sola.

```bash
curl -X POST http://localhost:8000/api/v1/jobs/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "search_query": "Clínicas dentales en Madrid",
    "user_profession": "Desarrollador Web",
    "user_technologies": ["WordPress", "SEO"],
    "user_value_proposition": "Ayudo a clínicas a conseguir más pacientes con webs rápidas.",
    "target_niche": "Salud Dental",
    "target_location": "España",
    "target_language": "es",
    "target_company_size": "5-20 empleados",
    "target_pain_points": ["Sin web profesional", "Sin reservas online"],
    "target_budget_signals": ["Anuncios activos en Google"],
    "max_results": 5
  }'
```

#### Modo B — URLs Directas ("Semillas")
Le das los dominios exactos a scrapear.

```bash
curl -X POST http://localhost:8000/api/v1/jobs/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://clinicadental.es", "https://smiledentist.es"],
    "user_profession": "Desarrollador Web",
    "user_value_proposition": "Ayudo a clínicas a conseguir más pacientes.",
    "target_niche": "Salud Dental"
  }'
```

**Respuesta `202 Accepted`:**
```json
{
  "job_id": 1,
  "status": "pending",
  "message": "Trabajo encolado. Procesando 5 dominios encontrados.",
  "source_type": "duckduckgo_search",
  "created_at": "2026-03-10T21:10:30",
  "updated_at": "2026-03-10T21:10:30",
  "total_found": 5,
  "recent_errors": []
}
```

**Qué cambió en este endpoint:**

- antes el payload podía heredar contexto comercial ficticio por default; ahora solo usa lo que realmente envías;
- la búsqueda automática ya no “simula éxito” con fallback silencioso;
- la respuesta ya devuelve parte del contexto operativo inicial del job.

**Errores posibles:**

| Código | Causa |
|--------|-------|
| `400` | No enviaste `urls` ni `search_query` |
| `400` | DuckDuckGo no encontró resultados reales para tu query |
| `422` | Algún campo tiene el tipo incorrecto (ej: `target_company_size` debe ser string `"15"`, no número) |

**Nota sobre modo demo:** si activas `DEMO_MODE=true`, la búsqueda automática puede devolver URLs mock cuando DDG falla. En ese caso, el job queda etiquetado internamente con `source_type=mock_search`. Con `DEMO_MODE=false`, la API responde `400` y no mezcla resultados falsos con datos reales.

---

#### Campos del Payload — Referencia Completa

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `search_query` | `string` | No* | Término para buscar en DuckDuckGo. Ej: `"Veterinarias en Lima"` |
| `urls` | `string[]` | No* | Lista de URLs directas a scrapear |
| `user_profession` | `string` | No | Tu profesión. Ej: `"Desarrollador Web"` |
| `user_technologies` | `string[]` | No | Tus herramientas. Ej: `["WordPress", "Shopify"]` |
| `user_value_proposition` | `string` | No | Tu propuesta de valor. DeepSeek la usa para calcular el match score |
| `user_past_successes` | `string[]` | No | Casos de éxito anteriores |
| `user_roi_metrics` | `string[]` | No | Métricas de ROI que ofreces |
| `target_niche` | `string` | No | Nicho objetivo. Ej: `"Salud Dental"` |
| `target_location` | `string` | No | País/ciudad. Ej: `"España"` |
| `target_language` | `string` | No | Idioma. Ej: `"es"` |
| `target_company_size` | `string` | No | Tamaño. Ej: `"5-20 empleados"`, `"Solopreneur"` |
| `target_pain_points` | `string[]` | No | Problemas que tiene el prospecto ideal |
| `target_budget_signals` | `string[]` | No | Señales de que tiene presupuesto |
| `max_results` | `int` | No | Máximo de URLs a procesar. Default: `10` |

*Debes enviar **al menos uno** de los dos: `search_query` o `urls`.

**Nota de contrato:** Si omites los campos de contexto comercial (`user_*`, `target_*`), la API no inyecta defaults de negocio. Esos campos quedan `null` y el job se procesa con el contexto realmente enviado.

---

### 2. `GET /api/v1/jobs/{job_id}` — Estado del Job

Consulta si el job terminó. Úsalo con polling cada 2-3 segundos hasta que `status` sea `"completed"`.

```bash
curl http://localhost:8000/api/v1/jobs/1
```

**Estados posibles:**

| `status` | Significado |
|----------|-------------|
| `pending` | En cola, aún no arrancó |
| `running` | Scrapeando activamente |
| `completed` | Terminó bien — ya podés pedir los resultados |
| `failed` | Error irrecuperable — revisar `error_message` |

**Respuesta `200 OK`:**
```json
{
  "job_id": 1,
  "status": "completed",
  "message": "Completado en 2026-03-10 21:10:50 | Procesadas: 5, guardadas: 4, omitidas: 1, fallidas: 0",
  "source_type": "duckduckgo_search",
  "created_at": "2026-03-10T21:10:30",
  "updated_at": "2026-03-10T21:10:50",
  "started_at": "2026-03-10T21:10:31",
  "finished_at": "2026-03-10T21:10:50",
  "total_found": 5,
  "total_processed": 5,
  "total_saved": 4,
  "total_failed": 0,
  "total_skipped": 1,
  "ai_summary": {
    "attempts": 4,
    "successes": 3,
    "fallbacks": 1,
    "fallback_ratio": 0.25,
    "total_prompt_tokens": 1820,
    "total_completion_tokens": 320,
    "total_tokens": 2140,
    "total_latency_ms": 8420,
    "average_latency_ms": 2105.0,
    "estimated_cost_usd": 0.0003912,
    "fallback_reasons": {
      "invalid_schema": 1
    }
  },
  "quality_summary": {
    "accepted": 3,
    "needs_review": 1,
    "rejected": 0,
    "rejection_reasons": {}
  },
  "recent_errors": []
}
```

**Qué cambió en este endpoint:**

- antes devolvía esencialmente un string de estado;
- ahora sirve para monitoreo real del job;
- incluye métricas operativas, resumen de uso de IA, distribución de calidad y errores recientes resumidos sin ir a `/logs`.

**Nota sobre costo estimado:** `estimated_cost_usd` depende de que el entorno tenga configuradas `DEEPSEEK_INPUT_COST_PER_1M_TOKENS` y `DEEPSEEK_OUTPUT_COST_PER_1M_TOKENS`. Si no están definidas, ese campo puede venir como `null`.

**Respuesta `404`:**
```json
{ "detail": "Job no encontrado." }
```

---

### 3. `GET /api/v1/jobs/{job_id}/results` — Resultados del Job

Devuelve la lista paginada de prospectos analizados por DeepSeek y guardados en PostgreSQL.

```bash
# Primeros 50 resultados (default)
curl http://localhost:8000/api/v1/jobs/1/results

# Con paginación
curl "http://localhost:8000/api/v1/jobs/1/results?limit=10&offset=20"
```

**Query params:**

| Param | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `limit` | `int` | `50` | Máximo de resultados por página |
| `offset` | `int` | `0` | Desde qué posición paginar |

**Respuesta `200 OK`:**
```json
[
  {
    "id": 42,
    "company_name": "Clínica Sonrisas",
    "domain": "clinica-sonrisas.es",
    "source_type": "duckduckgo_search",
    "discovery_method": "search_query",
    "search_query_snapshot": "Clínicas dentales en Madrid",
    "rank_position": 1,
    "email": "contacto@clinica-sonrisas.es",
    "score": 0.82,
    "confidence_level": "high",
    "validated_location": "Madrid",
    "location_match_status": "match",
    "location_confidence": "high",
    "detected_language": "es",
    "language_match_status": "match",
    "primary_cta": "booking",
    "booking_url": "https://clinica-sonrisas.es/reservas",
    "pricing_page_url": "https://clinica-sonrisas.es/precios",
    "inferred_niche": "Salud Dental",
    "inferred_tech_stack": ["WordPress", "Google Analytics"],
    "has_active_ads": true
  },
  {
    "id": 43,
    "company_name": null,
    "domain": "dentistamadrid.com",
    "source_type": "seed_url",
    "discovery_method": "seed_url",
    "search_query_snapshot": null,
    "rank_position": 2,
    "email": null,
    "score": 0.55,
    "confidence_level": "medium",
    "validated_location": "Madrid",
    "location_match_status": "match",
    "location_confidence": "medium",
    "detected_language": "es",
    "language_match_status": "unknown",
    "primary_cta": "contact_form",
    "booking_url": null,
    "pricing_page_url": null,
    "inferred_niche": "Salud Dental",
    "inferred_tech_stack": [],
    "has_active_ads": false
  }
]
```

**Qué cambió en este endpoint:**

- ahora los resultados se leen desde la relación contextual `job_prospects`;
- cada resultado conserva trazabilidad del origen del lead;
- solo se devuelven prospectos con `quality_status=accepted`;
- si el array sale vacío, no implica necesariamente fallo del job: revisar `GET /jobs/{id}` y su `quality_summary` para ver cuántos leads quedaron `rejected` o `needs_review`;
- el payload ahora incluye validación de ubicación/idioma y CTAs accionables (`validated_location`, `location_match_status`, `detected_language`, `primary_cta`, `booking_url`, `pricing_page_url`);
- deja de depender del último `upsert` sobre el dominio para reconstruir una corrida.

---

### 4. `GET /api/v1/jobs/{job_id}/logs` — Logs del Job

Devuelve logs persistidos del job para debugging operativo, sin entrar a la base.

```bash
# Todos los logs
curl "http://localhost:8000/api/v1/jobs/1/logs"

# Solo errores, paginados
curl "http://localhost:8000/api/v1/jobs/1/logs?level=ERROR&limit=10&offset=0"
```

**Query params:**

| Param | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `limit` | `int` | `50` | Máximo de logs por página |
| `offset` | `int` | `0` | Desde qué posición paginar |
| `level` | `INFO \| WARNING \| ERROR` | `null` | Filtra por nivel de log |

**Respuesta `200 OK`:**
```json
{
  "job_id": 1,
  "total": 3,
  "limit": 50,
  "offset": 0,
  "items": [
    {
      "id": 150,
      "created_at": "2026-03-10T21:10:50",
      "level": "ERROR",
      "message": "Fallo procesando URL",
      "source_name": "worker",
      "stage": "fetch_html",
      "error_type": "http_429",
      "status_code": 429,
      "retryable": true,
      "attempts_made": 3,
      "url": "https://example.com/contact",
      "rank_position": 2,
      "error": "HTTP 429 Too Many Requests al visitar https://example.com/contact"
    }
  ]
}
```

**Qué cambió en este endpoint:**

- este endpoint no existía en el MVP inicial;
- ahora expone `scraping_logs` por API;
- sirve para inspección operativa y debugging rápido por job.

---

## Flujo Completo de Uso (para NestJS)

```
1. POST /scrape          → Recibir { job_id: N }
2. GET  /jobs/N          → Polling hasta { status: "completed" }
3. GET  /jobs/N/results  → Descargar prospectos enriquecidos con IA
4. GET  /jobs/N/logs     → Inspeccionar eventos y fallos si hace falta
```

---

## Notas Técnicas

- **El scraping es asíncrono.** La API nunca bloquea — siempre retorna `202` de inmediato.
- **`GET /jobs/{id}` enriquecido:** además del estado y mensaje, ahora devuelve timestamps, métricas, `quality_summary` y hasta 3 errores recientes resumidos.
- **`GET /jobs/{id}/logs`:** expone `scraping_logs` paginados, con filtro por `INFO`, `WARNING` o `ERROR`.
- **Hay un delay de 2 segundos entre cada URL** para no saturar los sitios objetivo.
- **Contrato de scoring:** `score` es un `float` entre `0.0` y `1.0`; `confidence_level` es `low`, `medium` o `high`.
- **Semántica actual del score:** el valor expuesto ya no es "solo IA". Si DeepSeek responde bien, el sistema combina score IA + baseline heurístico usando pesos por confianza y ajuste por nivel de acuerdo; si la IA falla, cae a `heuristic_only`.
- **Trazabilidad interna del score:** cada prospecto persiste `scoring_trace` con `strategy`, `strategy_version`, pesos, delta de acuerdo y score final, aunque ese detalle no forme parte del payload resumido de `/results`.
- **Filtro de calidad por defecto:** `GET /jobs/{id}/results` solo lista leads aceptados. Los rechazados o `needs_review` se conservan internamente con `quality_status`, `quality_flags_json` y `rejection_reason`.
- **Resumen de calidad por job:** `GET /jobs/{id}` devuelve `quality_summary` con conteos de `accepted`, `needs_review`, `rejected` y `rejection_reasons`. Eso permite distinguir entre "job vacío" y "job completado sin leads aceptados".
- **Ubicación validada:** `location` ya no replica automáticamente `target_location`. La salida visible usa `validated_location` y `location_match_status` según evidencia del sitio, mapas, structured data o snippet de discovery.
- **Contrato de revenue signal:** `estimated_revenue_signal` usa `low`, `medium` o `high`.
- **Trazabilidad de origen:** `source_type` distingue `duckduckgo_search`, `mock_search`, `seed_url`, `manual` o `enrichment`. `discovery_method` indica cómo entró ese lead al pipeline.
- **TLS seguro por defecto:** el scraper valida certificados SSL/TLS por defecto. Solo desactívalo con `HTTP_VERIFY_TLS=false` en debugging controlado.
- **Errores de red clasificados:** los fallos de scraping distinguen `timeout`, `dns_error`, `tls_error`, `http_403`, `http_429` y `http_5xx` en los logs persistidos del job.
- **Retries controlados:** el cliente HTTP reintenta solo errores recuperables. Se parametriza con `HTTP_MAX_RETRIES` y `HTTP_BACKOFF_BASE_SECONDS`.
- **Links internos normalizados:** el parser resuelve rutas relativas con `urljoin` y evita persistir links externos o no navegables como parte del sitio.
- **Crawling limitado:** además de la homepage, el scraper puede visitar hasta 5 páginas clave del mismo dominio (`contact`, `about`, `services`, `pricing`, `book`, `locations`, `careers`) con early stop cuando ya obtuvo contacto, ubicación y CTA.
- **Extracción de contacto mejorada:** además de `mailto:` y `tel:`, el parser busca emails visibles en texto, normaliza teléfonos y conserva detección de formularios.
- **DeepSeek AI** ya no consume HTML crudo completo por defecto; recibe un `evidence pack` compacto con señales estructuradas, snippets y contexto heurístico.
- **Los resultados por job** se leen desde la relación contextual `job_prospects`, no solo desde el snapshot canónico del prospecto.
- **Si un sitio devuelve 403 (anti-bot)**, se loggea un warning y se salta — no rompe el job.
- **Los prospectos se guardan con `ON CONFLICT (domain)`** — nunca se duplican por dominio.
