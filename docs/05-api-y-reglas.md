# Documentación de Endpoints — Aurellis FastAPI

**Base URL:** `http://localhost:8000`  
**Docs interactivos (Swagger):** `http://localhost:8000/docs`

---

## Cómo Levantar el Servidor

```bash
# 1. Base de datos (Docker)
docker-compose up -d postgres

# 2. Entorno y servidor
source venv/bin/activate
uvicorn app.main:app --reload
```

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
  "message": "Trabajo encolado. Procesando 5 dominios encontrados."
}
```

**Errores posibles:**

| Código | Causa |
|--------|-------|
| `400` | No enviaste `urls` ni `search_query` |
| `400` | DuckDuckGo no encontró resultados para tu query |
| `422` | Algún campo tiene el tipo incorrecto (ej: `target_company_size` debe ser string `"15"`, no número) |

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
  "message": "Terminó en 2026-03-10 21:10:50"
}
```

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
    "email": "contacto@clinica-sonrisas.es",
    "inferred_niche": "Salud Dental",
    "inferred_tech_stack": ["WordPress", "Google Analytics"],
    "has_active_ads": true
  },
  {
    "id": 43,
    "company_name": null,
    "domain": "dentistamadrid.com",
    "email": null,
    "inferred_niche": "Salud Dental",
    "inferred_tech_stack": [],
    "has_active_ads": false
  }
]
```

---

## Flujo Completo de Uso (para NestJS)

```
1. POST /scrape          → Recibir { job_id: N }
2. GET  /jobs/N          → Polling hasta { status: "completed" }
3. GET  /jobs/N/results  → Descargar prospectos enriquecidos con IA
```

---

## Notas Técnicas

- **El scraping es asíncrono.** La API nunca bloquea — siempre retorna `202` de inmediato.
- **Hay un delay de 2 segundos entre cada URL** para no saturar los sitios objetivo.
- **DeepSeek AI** analiza el HTML de cada sitio para extraer `inferred_niche`, `pain_points` y `score`.
- **Si un sitio devuelve 403 (anti-bot)**, se loggea un warning y se salta — no rompe el job.
- **Los prospectos se guardan con `ON CONFLICT (domain)`** — nunca se duplican por dominio.
