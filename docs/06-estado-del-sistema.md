# Estado del Sistema — Aurellis FastAPI MVP

**Última actualización:** 2026-03-10 | **Versión:** MVP 1.0

---

## 📌 Revisión Técnica Complementaria

Además de este estado resumido, existe una revisión más rigurosa del proyecto en:

- [07-observaciones-y-plan-de-mejora.md](07-observaciones-y-plan-de-mejora.md)

Ese documento detalla problemas de contrato, persistencia, procesamiento en background, calidad de scraping, seguridad, testing y operación.

---

## ✅ Componentes Funcionando

### Core del Pipeline E2E
El flujo completo de prospección automática está operativo:

```
[Usuario] → POST /scrape → [DuckDuckGo] → [HTTP Scraper] → [DeepSeek AI] → [PostgreSQL]
```

| Componente | Estado | Notas |
|---|---|---|
| **API FastAPI** | ✅ OK | `http://localhost:8000` · Swagger en `/docs` |
| **Postgres local (Docker)** | ✅ OK | Requiere `docker compose up -d postgres` |
| **Buscador DuckDuckGo** | ✅ OK | Encuentra URLs reales para cualquier búsqueda |
| **Scraper HTTP** | ✅ OK | Descarga página completa con `httpx` + rotación de User-Agents |
| **DeepSeek AI** | ✅ **ACTIVO** | HTTP 200 en producción · ~2-3s por URL |
| **Parser de Respuesta IA** | ✅ OK | JSON parseado y mapeado a los campos del modelo |
| **DB Upsert (PostgreSQL)** | ✅ OK | `ON CONFLICT` — nunca duplica por dominio |
| **Endpoint `GET /jobs/{id}`** | ✅ OK | Polling asíncrono con timestamps, métricas y resumen de errores recientes |
| **Endpoint `GET /jobs/{id}/results`** | ✅ OK | Lista de prospectos guardados |
| **Endpoint `GET /jobs/{id}/logs`** | ✅ OK | Logs paginados por job con filtro opcional por nivel |
| **Lifecycle de jobs** | ✅ OK | Guarda `started_at`, `finished_at`, `total_processed`, `total_failed`, `total_skipped` |
| **Logging persistente** | ✅ OK | Guarda eventos y errores en `scraping_logs` por `job_id` |

---

## ⚠️ Limitaciones Actuales (pendientes de mejora)

### 1. El score puede quedar en `0.0`
**Causa probable:** si DeepSeek falla, no hay `DEEPSEEK_API_KEY`, o el contexto comercial del job es demasiado pobre, el sistema cae al extractor heurístico y hoy ese fallback devuelve `score=0.0`.

**Archivo a revisar:** `app/services/ai_extractor.py`

**Solución sugerida:** mejorar el score heurístico base, medir el ratio de fallback y validar la respuesta cruda del proveedor IA para detectar respuestas incompletas o inconsistentes.

### 2. `inferred_tech_stack` vacío `[]`
**Causa probable:** El prompt no pide explícitamente detectar tecnologías web (WordPress, Shopify, etc.).

**Solución sugerida:** Añadir al prompt: *"Detecta en el HTML si usa WordPress (wp-content), Shopify, Wix, Elementor, Google Analytics, Meta Pixel u otras tecnologías. Devuelve como array en `inferred_tech_stack`."*

### 3. Sitios con bloqueo Anti-bot (403 Forbidden)
Algunos sitios (ej: `vetivet.pe`) bloquean scrapers básicos.

**Comportamiento actual:** Se loggea un `WARNING` y se salta el sitio — correcto.

**Mejora futura:** Agregar rotación de proxies o delays aleatorios más agresivos.

### 4. pgAdmin crashea al iniciar
**Causa:** El email `admin@aurellis.local` no es válido según la nueva validación de pgAdmin.

**Fix temporal:** `docker compose up -d postgres` — solo levanta PostgreSQL sin pgAdmin.

---

## 🏗️ Arquitectura de Archivos Clave

```
aurellis-fastApi/
├── app/
│   ├── main.py                  # Punto de entrada FastAPI
│   ├── config.py                # Variables de entorno (DEEPSEEK_API_KEY, DB_URL)
│   ├── models.py                # Modelos SQLAlchemy (ScrapingJob, Prospect)
│   ├── api/
│   │   ├── jobs.py              # Endpoints REST (POST /scrape, GET /jobs/...)
│   │   └── schemas.py           # Schemas Pydantic de entrada/salida
│   ├── scraper/
│   │   ├── engine.py            # Orquestador principal del pipeline
│   │   ├── http_client.py       # Cliente HTTP con User-Agent rotatorio
│   │   ├── parser.py            # BeautifulSoup → texto limpio
│   │   └── search_engines/
│   │       └── ddg_search.py    # Buscador DuckDuckGo automático
│   └── services/
│       ├── ai_extractor.py      # ⭐ Integración DeepSeek API
│       └── db_upsert.py         # Guardado en PostgreSQL con upsert
├── docs/
│   ├── 05-api-y-reglas.md       # Endpoints y cURLs para usar la API
│   └── 06-estado-del-sistema.md # Este archivo
├── .env                         # API Keys y secrets (NO subir a git)
├── docker-compose.yml           # PostgreSQL + pgAdmin
└── test_mvp.py                  # Script de prueba E2E
```

---

## 🚀 Cómo Correr el Sistema

```bash
# 1. Levantar la base de datos
cp .env.example .env
docker compose up -d postgres

# 2. Activar entorno virtual
source venv/bin/activate

# 3. Instalar dependencias
python3 -m pip install -r requirements.txt

# 4. Levantar el servidor
uvicorn app.main:app --reload

# 5. Probar con el script E2E
python3 test_mvp.py
```

---

## 🔜 Próximos Pasos Sugeridos

1. **Arreglar el Score (prioritario):** Loggear respuesta raw de DeepSeek y ajustar el mapeo de campos.
2. **Mejorar el Prompt:** Incluir detección de stack tecnológico.
3. **Fix pgAdmin:** Cambiar el email en `docker-compose.yml` a uno con dominio válido (ej. `admin@example.com`).
4. **Rate Limiting:** Añadir un delay de 0.5-1s entre llamadas a DeepSeek para evitar throttling.
5. **Observabilidad avanzada:** si hace falta, extender `GET /jobs/{id}/logs` con agregados o métricas resumidas por etapa.

## Nota de alcance

Este documento resume el estado operativo del MVP, pero no reemplaza la revisión técnica detallada.  
Para decisiones de arquitectura, endurecimiento del contrato de datos y plan de estabilización, tomar como referencia principal el documento de observaciones y mejora.
