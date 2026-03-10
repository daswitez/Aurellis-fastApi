# Estado Actual: Motor de Prospección Aurelius (MVP)

Este documento resume el estado actual de la **API de Scraping de Aurelius**, qué funcionalidades ya están operativas, cómo funciona por debajo, cómo levantar el proyecto localmente y dónde se guardan los datos.

---

## 🚀 1. ¿Qué tenemos ahora y qué hace?
Actualmente contamos con el **MVP (Producto Mínimo Viable)** del motor de extracción de datos, construido enteramente en Python con FastAPI. Su propósito es actuar como un **microservicio de prospección** que NestJS puede consultar de forma asíncrona.

**Funcionalidades Principales Operativas:**
1. **Modo Búsqueda Automática (Prospección):** Le pasas un rubro (ej. `"clínicas dentales miami"`) y la API usa DuckDuckGo de manera encubierta (evadiendo restricciones anti-bot) para descubrir dominios de B2B potenciales automáticamente.
2. **Modo URLs Directas:** Le pasas una lista de sitios web (ej. `["https://apple.com", "https://tesla.com"]`) y procesa esos dominios específicamente.
3. **Scraping Asíncrono no bloqueante:** La API devuelve un `job_id` inmediatamente (HTTP 202) y lanza el recolector web en una tarea de fondo (Background Task) para no colgar la conexión HTTP.
4. **Extracción Heurística (Filtro Inteligente):** *No usamos LLMs costosos para leer HTML*. En su lugar, el motor descarga la página nativa, busca patrones en el código y el texto (palabras como "carrera", "trabaja con nosotros", rastros de "Google Tag Manager", "WordPress", estimador crudo de ingresos basado en sofisticación web) para predecir:
   - Nicho inferido.
   - Stack tecnológico del prospecto.
   - Señales de contratación (hiring signals).
   - Inversión en publicidad (has_active_ads).

---

## ⚙️ 2. ¿Cómo funciona la arquitectura?
El ciclo de vida completo de una solicitud ("Job") es el siguiente:

1. **Ingreso (NestJS -> FastAPI):** Llega una petición `POST /api/v1/jobs/scrape`.
2. **Resolución de Dominio (`ddg_search.py`):** Si NestJS manda un `search_query` crudo en lugar de links, Python falsifica su perfil web, busca localmente en DuckDuckGo, descifra los enlaces censurados y crea la lista de prospectos.
3. **Gestión de Cola (`jobs.py`):** Se inserta en la base de datos el "Job" con estado `pending` y la API responde inmediatamente `{"job_id": X, "status": "pending"}`.
4. **Ejecución Background (`engine.py`):** Un hilo secundario visita URL por URL asíncronamente (usando `httpx` y `BeautifulSoup`).
5. **Evaluación de Datos (`heuristic_extractor.py`):** Todo el texto y código visible de ese dominio pasa por filtros RegEx nativos.
6. **Almacenamiento (PostgreSQL):** Cuando la extracción de un prospecto finaliza, se hace un `UPSERT` (Si ya existe el dominio lo actualiza, si no, lo inserta).

---

## 💾 3. ¿Dónde se guarda la información?
Absolutamente toda la data scrapeada se persiste en nuestra **Base de Datos Relacional (PostgreSQL)** alojada en un contenedor de Docker local.

- **URL de Conexión:** `postgresql+asyncpg://postgres:postgres@localhost:5432/aurelius_scraper`

### Tablas Principales:
1. **`scraping_jobs`**: Registra la intención, parámetros de búsqueda enviados desde NestJS, y estado general de todo el lote (`pending`, `running`, `completed`, `failed`).
2. **`prospects`**: Es la tabla de oro. Guarda a cada prospecto y empresa descubierta de forma atómica.
   - Campos guardados: `domain`, `website_url`, `company_name`, `email`, `phone`, `linkedin_url`, `inferred_tech_stack` (JSON), `hiring_signals` (Booleano), `has_active_ads` (Booleano).

---

## 💻 4. ¿Cómo correr todo el proyecto localmente?
Para que el ecosistema funcione (API + Base de Datos), necesitas ambos prendidos en la terminal.

### Paso A: Levantar la Base de Datos
Asegúrate de tener Docker prendido y en la raíz del proyecto ejecuta:
```bash
# Iniciar contenedor Postgres en segundo plano (puerto 5432)
docker compose up -d

# Validar que está prendido
docker ps
```

### Paso B: Activar el Entorno e Instalar
```bash
# 1. Entrar al virtual environment
source venv/bin/activate

# 2. (Opcional) Si hay nuevas dependencias en tu equipo:
pip install -r requirements.txt
```

### Paso C: Migraciones de la BD (Alembic)
Para construir las tablas `scraping_jobs` y `prospects` automáticamente en el Docker:
```bash
alembic upgrade head
```

### Paso D: Iniciar el Servidor API de Extracción (FastAPI)
```bash
uvicorn app.main:app --reload
```
La consola avisará que el servicio arrancó en `http://127.0.0.1:8000`.

---

## 🧪 5. ¿Cómo testearlo rápidamente?
En vez de usar Postman, dejé un script maestro llamado `test_mvp.py` que emula el comportamiento asíncrono que NestJS haría, en tiempo real de la línea de comandos.

Abre una **NUEVA pestaña en la terminal**, activa el entorno y corre el simulador:
```bash
source venv/bin/activate
python test_mvp.py
```

El simulador enviará una consulta como *"clínicas veterinarias en lima"*, luego consultará periódicamente a FastAPI usando GET (`Polling`) hasta que FastAPI en background cambie el Job a "Completed", imprimiendo al final la lista pura extraída por la IA heurística.
