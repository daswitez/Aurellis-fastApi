# Guía Rápida de Endpoints (API)

Este documento detalla cómo levantar el servicio localmente y cómo usar los endpoints principales desde Postman, cURL o el futuro backend de NestJS.

---

## 1. Levantar el Servicio Localmente

Asegúrate de tener la base de datos de Docker corriendo:
```bash
docker-compose up -d
```

Luego, activa tu entorno y levanta el servidor uvicorn:
```bash
source venv/bin/activate
uvicorn app.main:app --reload
```
La API estará viva en `http://localhost:8000` y la documentación interactiva Swagger estará en `http://localhost:8000/docs`.

---

## 2. Endpoints Principales

### 2.1. Crear un Trabajo de Scraping (POST)
**Endpoint:** `POST /api/v1/jobs/scrape`

Este es> **Nota de Errores Comunes:**
> Si al invocar la API recibes un error tipo:
> `{"detail": [{"type": "int_parsing", "loc": ["path","job_id"], "msg": "Input should be a valid integer..."}]}`
> ¡Es porque estás accediendo al endpoint `POST /scrape` realizando un request **`GET`** (ej. poniendo la URL en la barra del navegador de Google Chrome)! Para usar endpoints POST, debes usar Terminal (cURL) o Postman.

### Flujo de Uso
La arquitectura no es "Solicitud Síncrona -> Respuesta con datos". Es un sistema de **Scraping Diferido**.nmediatamente que ha encolado el trabajo. 

**Modo 1: Modo Búsqueda Automática (Recomendado)**
Le pides a la API que **busque prospectos en Google/DuckDuckGo** basados en un término#### B. Búsqueda Automática por Query (Buscador DDG)
Si envías `search_query` y NO envías `urls`, la API buscará orgánicamente los dominios para ti.

**Comando `curl` exacto para Copiar y Pegar en la terminal:**
```bash
curl -X POST http://localhost:8000/api/v1/jobs/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "search_query": "Clínicas dentales en Madrid",
    "user_profession": "Desarrollador Web",
    "user_technologies": ["WordPress", "SEO"],
    "user_value_proposition": "Ayudo a clínicas a conseguir pacientes con webs rápidas.",
    "target_niche": "Salud Dental",
    "target_company_size": "15",
    "max_results": 5
  }'
```

*(Importante: `target_company_size` debe enviarse envuelto en comillas como string `"15"`)*

**Respuesta Exitosa (HTTP 202 Accepted):**
```json
{
  "job_id": 1,
  "status": "pending",
  "message": "Trabajo encolado. Procesando 5 dominios encontrados."
}
```

**Modo 2: Modo URLs Precisas ("Semillas")**
Le pides a la API que extraiga información **SÓLO de los dominios específicos** que tú ya conoces. 

**Payload JSON de Ejemplo:**
```json
{
  "urls": ["https://apple.com", "https://ejemplo.com"],
  "user_profession": "Agencia B2B"
}
```

**Respuesta Esperada (`202 Accepted`):**
```json
{
    "job_id": 14,
    "status": "pending",
    "message": "El trabajo ha sido encolado y el scraping iniciará de inmediato."
}
```

---

### 2.2. Consultar Estado del Trabajo (GET)
Como el scraping de 50 sitios demora, tu cliente (NestJS) debe hacer *polling* a este endpoint usando el `job_id` que recibió en el paso anterior.

**Endpoint:** `GET /api/v1/jobs/{job_id}`

**Respuesta Esperada (`200 OK`):**
```json
{
    "job_id": 14,
    "status": "completed", 
    "message": "Terminó en 2026-03-09T23:55:00"
}
```
*(Si sigue trabajando, `status` será `"running"`).*

---

### 2.3. Obtener los Prospectos Guardados (GET)
Una vez el Job esté `"completed"`, visitas este endpoint para descargar el listado estructurado de empresas que nuestro motor dedujo y enriqueció.

**Endpoint:** `GET /api/v1/jobs/{job_id}/results`

**Respuesta Esperada (`200 OK`):**
```json
[
  {
    "id": 150,
    "company_name": "Clínica Sonrisas",
    "domain": "sonrisas-madrid.es",
    "email": "contacto@sonrisas-madrid.es",
    "inferred_niche": "Salud Dental",
    "inferred_tech_stack": ["WordPress", "Google Analytics"],
    "has_active_ads": true
  }
]
```
