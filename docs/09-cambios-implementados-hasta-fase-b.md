# Cambios Implementados Hasta Fase B

**Fecha de corte:** 2026-03-10  
**Alcance:** tareas ejecutadas desde la estabilización base (`Fase A`) hasta confiabilidad del pipeline (`Fase B`).

---

## 1. Qué se corrigió a nivel general

Hasta este punto el proyecto dejó de ser solo un MVP funcional “manual” y pasó a tener una base bastante más consistente para operar scraping y prospección con trazabilidad.

Los cambios más relevantes fueron:

- contrato unificado de `score` y `confidence_level`,
- setup y variables de entorno más realistas,
- persistencia rediseñada para separar prospecto canónico de resultado por job,
- lifecycle de jobs con métricas reales,
- logs persistidos y consultables por API,
- búsqueda DDG sin fallback silencioso,
- cliente HTTP más seguro y con retries controlados,
- crawling limitado de páginas clave,
- extracción de contacto más útil,
- endpoints enriquecidos para monitoreo real.

---

## 2. Cambios de datos y persistencia

### Separación entre prospecto y resultado por job

Antes, el sistema dependía demasiado de `prospects.job_id`, lo que era frágil cuando un mismo dominio aparecía en múltiples jobs.

Ahora el modelo quedó orientado a:

- `prospects`: entidad canónica del dominio/empresa,
- `job_prospects`: relación contextual por job,
- `prospect_contacts`: contactos detectados,
- `prospect_pages`: páginas vistas o inferidas.

Esto permite:

- conservar historial por corrida,
- no perder trazabilidad del score por job,
- preparar mejor la futura integración con CRM.

### Nuevas tablas ya operativas

- `job_prospects`
- `prospect_contacts`
- `prospect_pages`

Ya existe migración aplicada y el runtime actual ya usa este esquema para persistencia y lectura.

---

## 3. Cambios en jobs y observabilidad

### Lifecycle del job

Antes, el job podía terminar sin timestamps ni contadores coherentes.

Ahora cada job registra:

- `created_at`
- `started_at`
- `finished_at`
- `total_found`
- `total_processed`
- `total_saved`
- `total_failed`
- `total_skipped`
- `error_message`

### Logging persistente

Los eventos importantes ahora se escriben en `scraping_logs`:

- creación del job,
- inicio del worker,
- persistencia de prospectos,
- omisiones,
- fallos por URL,
- fallo total del worker,
- fin del job.

Además, los errores de scraping ya guardan contexto operativo:

- `stage`
- `error_type`
- `status_code`
- `retryable`
- `attempts_made`
- `url`
- `rank_position`

---

## 4. Cambios en scraping y descubrimiento

### Descubrimiento de URLs

Se eliminó el fallback silencioso de DuckDuckGo.

Comportamiento actual:

- con `DEMO_MODE=false`: si DDG falla o no encuentra resultados, la API responde error real;
- con `DEMO_MODE=true`: se habilita fallback mock explícito, etiquetado como `mock_search`.

### Fuente y trazabilidad del resultado

Los resultados por job ahora exponen:

- `source_type`
- `discovery_method`
- `search_query_snapshot`
- `rank_position`

Esto permite distinguir entre:

- búsqueda orgánica,
- mock demo,
- URLs semilla,
- flujos manuales,
- futuros enriquecimientos.

### Robustez HTTP

Se corrigió el cliente HTTP para:

- validar TLS por defecto,
- permitir bypass solo con `HTTP_VERIFY_TLS=false`,
- clasificar errores de red y HTTP,
- aplicar retries solo sobre fallos recuperables,
- usar backoff parametrizable.

Variables nuevas relevantes:

- `HTTP_VERIFY_TLS`
- `HTTP_MAX_RETRIES`
- `HTTP_BACKOFF_BASE_SECONDS`

### Parsing y crawling

Se mejoró el parser para:

- resolver URLs con `urljoin`,
- filtrar links externos/no navegables,
- detectar mejor páginas internas clave.

Y el engine ahora hace crawling limitado:

- homepage,
- hasta 3 páginas clave del mismo dominio (`contact`, `about`, `nosotros`, `equipo`, `careers`).

Esto mejora:

- emails,
- teléfonos,
- formularios,
- redes,
- señales de contratación.

### Extracción de contacto

Ya no depende solo de `mailto:` y `tel:`.

Ahora también:

- busca emails visibles en texto,
- normaliza teléfonos,
- filtra placeholders obvios,
- conserva `form_detected`,
- prioriza mejor `contact_page_url`.

---

## 5. Cambios en endpoints

La documentación detallada de endpoints actualizados vive en [05-api-y-reglas.md](05-api-y-reglas.md).  
Acá se resume qué cambió respecto al MVP original.

### `POST /api/v1/jobs/scrape`

Cambios principales:

- ya no inyecta defaults de negocio en el payload;
- distingue mejor entre `search_query` y `urls`;
- si DDG falla con `DEMO_MODE=false`, devuelve error real;
- guarda `source_type` desde el momento de creación del job;
- devuelve una respuesta más informativa desde la creación.

### `GET /api/v1/jobs/{job_id}`

Antes devolvía esencialmente estado y mensaje.

Ahora devuelve además:

- timestamps,
- métricas operativas,
- `source_type`,
- `error_message`,
- `recent_errors`.

Esto lo convierte en un endpoint de monitoreo real, no solo de polling básico.

### `GET /api/v1/jobs/{job_id}/results`

Antes dependía del modelo viejo y no distinguía bien el contexto por corrida.

Ahora:

- lee desde `job_prospects`,
- respeta la corrida real,
- expone trazabilidad de origen,
- devuelve mejor contexto para CRM/prospección.

Campos nuevos relevantes:

- `source_type`
- `discovery_method`
- `search_query_snapshot`
- `rank_position`

### `GET /api/v1/jobs/{job_id}/logs`

Este endpoint no existía.

Ahora permite:

- ver logs del job sin entrar a la base,
- paginar resultados,
- filtrar por `INFO`, `WARNING` o `ERROR`.

Es la base mínima para debugging operativo.

---

## 6. Estado del proyecto después de estos cambios

Después de `Fase A` y `Fase B`, el sistema ya tiene:

- arranque más reproducible,
- contrato más claro,
- persistencia más sólida,
- scraping más robusto,
- observabilidad suficiente para debugging básico,
- mejor base para CRM y scoring por contexto.

Lo que sigue ya entra en otra categoría:

- endurecimiento de IA,
- validación de schema de salida del modelo,
- estrategia de scoring híbrido,
- tests automatizados,
- seguridad e integración productiva.

---

## 7. Siguiente bloque natural

El siguiente frente lógico es **Fase C**:

- `C-001 Revisar el prompt de DeepSeek`
- `C-002 Validar respuesta de IA con schema`
- `C-003 Propagar mejor el contexto útil al extractor`

Ese bloque ya no trata de “que funcione” sino de que la calidad del enriquecimiento sea defendible.
