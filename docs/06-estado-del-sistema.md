# Estado del Sistema — Aurellis FastAPI MVP

**Última actualización:** 2026-03-10 | **Versión:** MVP 1.0

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
| **Pokemon (Docker Postgres)** | ✅ OK | Requiere `docker-compose up -d postgres` |
| **Buscador DuckDuckGo** | ✅ OK | Encuentra URLs reales para cualquier búsqueda |
| **Scraper HTTP** | ✅ OK | Descarga página completa con `httpx` + rotación de User-Agents |
| **DeepSeek AI** | ✅ **ACTIVO** | HTTP 200 en producción · ~2-3s por URL |
| **Parser de Respuesta IA** | ✅ OK | JSON parseado y mapeado a los campos del modelo |
| **DB Upsert (PostgreSQL)** | ✅ OK | `ON CONFLICT` — nunca duplica por dominio |
| **Endpoint `GET /jobs/{id}`** | ✅ OK | Polling asíncrono del estado del Job |
| **Endpoint `GET /jobs/{id}/results`** | ✅ OK | Lista de prospectos guardados |

---

## ⚠️ Limitaciones Actuales (pendientes de mejora)

### 1. Score siempre = `0.0`
**Causa probable:** El prompt enviado a DeepSeek no está incluyendo correctamente el perfil del vendedor (`user_profession`, `user_value_proposition`) en la petición al modelo, o el modelo retorna el score en un campo con nombre diferente al que se mapea.

**Archivo a revisar:** `app/services/ai_extractor.py`

**Solución sugerida:** Loggear la respuesta JSON cruda de DeepSeek para ver qué campo está devolviendo para el score (puede que lo llame `match_score` o `compatibility`).

### 2. `inferred_tech_stack` vacío `[]`
**Causa probable:** El prompt no pide explícitamente detectar tecnologías web (WordPress, Shopify, etc.).

**Solución sugerida:** Añadir al prompt: *"Detecta en el HTML si usa WordPress (wp-content), Shopify, Wix, Elementor, Google Analytics, Meta Pixel u otras tecnologías. Devuelve como array en `inferred_tech_stack`."*

### 3. Sitios con bloqueo Anti-bot (403 Forbidden)
Algunos sitios (ej: `vetivet.pe`) bloquean scrapers básicos.

**Comportamiento actual:** Se loggea un `WARNING` y se salta el sitio — correcto.

**Mejora futura:** Agregar rotación de proxies o delays aleatorios más agresivos.

### 4. pgAdmin crashea al iniciar
**Causa:** El email `admin@aurellis.local` no es válido según la nueva validación de pgAdmin.

**Fix temporal:** `docker-compose up -d postgres` — solo levanta PostgreSQL sin pgAdmin.

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
│   │   ├── html_parser.py       # BeautifulSoup → texto limpio
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
docker-compose up -d postgres

# 2. Activar entorno virtual
source venv/bin/activate

# 3. Levantar el servidor
uvicorn app.main:app --reload

# 4. Probar con el script E2E
python3 test_mvp.py
```

---

## 🔜 Próximos Pasos Sugeridos

1. **Arreglar el Score (prioritario):** Loggear respuesta raw de DeepSeek y ajustar el mapeo de campos.
2. **Mejorar el Prompt:** Incluir detección de stack tecnológico.
3. **Fix pgAdmin:** Cambiar el email en `docker-compose.yml` a uno con dominio válido (ej. `admin@example.com`).
4. **Rate Limiting:** Añadir un delay de 0.5-1s entre llamadas a DeepSeek para evitar throttling.
