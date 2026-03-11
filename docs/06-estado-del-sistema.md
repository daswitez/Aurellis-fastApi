# Estado del Sistema — Aurellis FastAPI MVP

**Última actualización:** 2026-03-11 | **Versión:** MVP 1.1

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
[Usuario] → POST /scrape → [Discovery Normalizer] → [DuckDuckGo]
→ [HTTP Scraper + Parser Estructurado] → [Quality Gate]
→ [DeepSeek AI opcional] → [PostgreSQL]
```

| Componente | Estado | Notas |
|---|---|---|
| **API FastAPI** | ✅ OK | `http://localhost:8000` · Swagger en `/docs` |
| **Postgres local (Docker)** | ✅ OK | Requiere `docker compose up -d postgres` |
| **Buscador DuckDuckGo** | ✅ OK | Usa queries canónicas, bloquea agregadores y conserva metadata SERP |
| **Scraper HTTP** | ✅ OK | Descarga homepage + hasta 5 páginas clave del mismo dominio |
| **Parser Estructurado** | ✅ OK | Extrae JSON-LD, idioma, direcciones, CTAs, booking, pricing, WhatsApp y mapas |
| **Quality Gate** | ✅ OK | Valida ubicación/idioma/contacto y clasifica `accepted`, `needs_review`, `rejected` |
| **DeepSeek AI** | ✅ **ACTIVO** | Solo se invoca cuando el lead pasa el gate heurístico y de calidad |
| **Parser de Respuesta IA** | ✅ OK | JSON parseado, validado con schema y cacheado por firma de contenido |
| **DB Upsert (PostgreSQL)** | ✅ OK | `ON CONFLICT` — nunca duplica por dominio |
| **Endpoint `GET /jobs/{id}`** | ✅ OK | Polling asíncrono con timestamps, métricas y resumen de errores recientes |
| **Endpoint `GET /jobs/{id}/results`** | ✅ OK | Lista de prospectos guardados |
| **Endpoint `GET /jobs/{id}/logs`** | ✅ OK | Logs paginados por job con filtro opcional por nivel |
| **Lifecycle de jobs** | ✅ OK | Guarda `started_at`, `finished_at`, `total_processed`, `total_failed`, `total_skipped` |
| **Logging persistente** | ✅ OK | Guarda eventos y errores en `scraping_logs` por `job_id` |

---

## ⚠️ Limitaciones Actuales (pendientes de mejora)

### 1. Validación geográfica estricta sigue siendo heurística
**Estado actual:** `target_location` ya actúa como criterio duro de aceptación usando evidencia del sitio, mapas, snippets y structured data.

**Limitación real:** si el sitio no publica ubicación clara, el lead puede quedar como `needs_review` o rechazado aunque el negocio sí opere allí.

### 2. Sitios con bloqueo Anti-bot (403 Forbidden)
Algunos sitios (ej: `vetivet.pe`) bloquean scrapers básicos.

**Comportamiento actual:** Se loggea un `WARNING` y se salta el sitio — correcto.

**Mejora futura:** Agregar rotación de proxies o delays aleatorios más agresivos.

### 3. Cache IA actual es local al proceso
**Estado actual:** el cache evita reconsumo de tokens dentro del proceso actual usando firma por dominio + contenido + versión de prompt.

**Mejora futura:** moverlo a persistencia compartida si se pasa a múltiples workers.

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
│   │   ├── engine.py            # Orquestador principal con quality gate y AI gating
│   │   ├── http_client.py       # Cliente HTTP con User-Agent rotatorio
│   │   ├── parser.py            # HTML → texto + metadata estructurada
│   │   └── search_engines/
│   │       └── ddg_search.py    # Discovery DDG con metadata SERP y exclusiones
│   └── services/
│       ├── ai_extractor.py      # ⭐ Integración DeepSeek API con schema, cache y métricas
│       ├── db_upsert.py         # Guardado en PostgreSQL con upsert
│       ├── discovery.py         # Construcción de queries canónicas
│       ├── heuristic_extractor.py # Baseline heurístico comercial
│       ├── prospect_quality.py  # Validación geo/idioma/contacto
│       └── scoring.py           # Score híbrido final
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

1. **Persistir cache IA compartido:** mover cache de memoria local a una capa común si se migra a workers reales.
2. **Mejorar validación geo:** añadir reglas por prefijos telefónicos, TLD y diccionarios de ciudades/países.
3. **Fix pgAdmin:** cambiar el email en `docker-compose.yml` a uno con dominio válido (ej. `admin@example.com`).
4. **Observabilidad avanzada:** agregar métricas resumidas de `accepted`, `needs_review`, `rejected` por job.
5. **Dataset offline de scraping:** ampliar fixtures HTML para validar parser y quality gate sin depender de internet.

## Nota de alcance

Este documento resume el estado operativo del MVP, pero no reemplaza la revisión técnica detallada.  
Para decisiones de arquitectura, endurecimiento del contrato de datos y plan de estabilización, tomar como referencia principal el documento de observaciones y mejora.
