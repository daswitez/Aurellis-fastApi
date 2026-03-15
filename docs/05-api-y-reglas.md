# Documentación de Endpoints — Aurellis FastAPI

**Base URL local:** `http://localhost:8000`  
**Swagger:** `http://localhost:8000/docs`

---

## 1. Puesta en marcha

```bash
cp .env.example .env
docker compose up -d postgres
source venv/bin/activate
python3 -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Chequeo rápido:

```bash
curl http://localhost:8000/health
```

Respuesta esperada:

```json
{
  "status": "ok",
  "message": "Scraping service is running"
}
```

---

## 2. Flujo real recomendado

El flujo normal del servicio es:

1. Crear un job con `POST /api/v1/jobs/scrape`.
2. Hacer polling con `GET /api/v1/jobs/{job_id}` hasta que `status` sea `completed` o `failed`.
3. Pedir los resultados visibles con `GET /api/v1/jobs/{job_id}/results`.
4. Si hace falta auditar, revisar `GET /api/v1/jobs/{job_id}/logs`, `GET /api/v1/jobs/metrics/operational` y `GET /api/v1/jobs/metrics/commercial`.

---

## 2.1. Cambios recientes del contrato

Se mantiene el caso de uso orientado a `Diseñador Gráfico`.

Cambió esto:

- `GET /api/v1/jobs/{job_id}/results` ahora expone clasificación comercial y normalización de ubicación:
  - `entity_type_detected`
  - `entity_type_confidence`
  - `entity_type_evidence`
  - `is_target_entity`
  - `acceptance_decision`
  - `contact_consistency_status`
  - `primary_email_confidence`
  - `primary_phone_confidence`
  - `raw_location_text`
  - `parsed_location`
  - `city`
  - `region`
  - `country`
  - `postal_code`
  - `observed_signals`
  - `inferred_opportunities`
  - `taxonomy_top_level`
  - `taxonomy_business_type`
- Nuevo endpoint agregado:
  - `GET /api/v1/jobs/metrics/commercial`
- No cambió esto:
  - `POST /api/v1/jobs/scrape`
  - `GET /api/v1/jobs/{job_id}`
  - `GET /api/v1/jobs/{job_id}/logs`
  - `GET /api/v1/jobs/metrics/operational`

---

## 3. Ejemplos reales con `curl`

### 3.1. Caso real: Diseñador gráfico buscando negocios con necesidad visual

Ejemplo orientado a un diseñador gráfico que busca clínicas estéticas en Madrid con señales de contacto y posibilidad de mejora visual.

```bash
curl -X POST http://localhost:8000/api/v1/jobs/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "search_query": "clinicas esteticas madrid",
    "user_profession": "Diseñador Gráfico",
    "user_technologies": ["Adobe Illustrator", "Photoshop", "Figma"],
    "user_value_proposition": "Ayudo a negocios de salud y belleza a mejorar su identidad visual, creatividades de anuncios y materiales comerciales.",
    "user_past_successes": ["Rediseñe la identidad visual de una clinica dental y mejoró la conversion de sus campañas"],
    "user_roi_metrics": ["Mejor CTR en anuncios", "Mayor coherencia visual de marca"],
    "target_niche": "Clinicas Esteticas",
    "target_location": "España",
    "target_language": "es",
    "target_company_size": "5-25 empleados",
    "target_pain_points": ["Marca visual inconsistente", "Creatividades pobres", "Landing desactualizada"],
    "target_budget_signals": ["Anuncios activos", "Reservas online", "Sitio con multiples servicios"],
    "target_accepted_results": 5,
    "max_candidates_to_process": 20
  }'
```

Respuesta típica:

```json
{
  "job_id": 41,
  "status": "pending",
  "message": "Trabajo encolado. Objetivo: 5 aceptados; candidatos a procesar: 10.",
  "source_type": "duckduckgo_search",
  "created_at": "2026-03-11T19:12:03.120000",
  "updated_at": "2026-03-11T19:12:03.120000",
  "total_found": 10,
  "recent_errors": []
}
```

Luego haces polling:

```bash
curl http://localhost:8000/api/v1/jobs/41
```

Y cuando termine:

```bash
curl "http://localhost:8000/api/v1/jobs/41/results?quality=accepted"
```

Para ver también los casos dudosos:

```bash
curl "http://localhost:8000/api/v1/jobs/41/results?quality=accepted,needs_review"
```

Para revisar la clasificación comercial agregada del sistema:

```bash
curl "http://localhost:8000/api/v1/jobs/metrics/commercial"
curl "http://localhost:8000/api/v1/jobs/metrics/commercial?limit=200"
```

### 3.2. Caso real: Diseñador gráfico buscando restaurantes premium

```bash
curl -X POST http://localhost:8000/api/v1/jobs/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "search_query": "restaurantes gourmet lima",
    "user_profession": "Diseñador Gráfico",
    "user_technologies": ["Adobe Illustrator", "InDesign", "Figma"],
    "user_value_proposition": "Diseño identidad visual, menus, piezas promocionales y contenido grafico para marcas gastronomicas.",
    "target_niche": "Restaurantes Gourmet",
    "target_location": "Perú",
    "target_language": "es",
    "target_pain_points": ["Marca poco memorable", "Material comercial improvisado"],
    "target_budget_signals": ["Reservas online", "Varias sedes", "Presencia en redes"],
    "target_accepted_results": 3
  }'
```

### 3.3. Caso real: Diseñador gráfico con URLs semilla

Cuando ya conoces dominios concretos y no quieres depender de discovery:

```bash
curl -X POST http://localhost:8000/api/v1/jobs/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "urls": [
      "https://www.clinicabaviera.com/",
      "https://www.dorsia.es/",
      "https://www.clinicasdh.com/"
    ],
    "user_profession": "Diseñador Gráfico",
    "user_technologies": ["Photoshop", "Illustrator", "After Effects"],
    "user_value_proposition": "Ayudo a clinicas con branding, diseno publicitario y creatividades digitales.",
    "target_niche": "Clinicas",
    "target_location": "España",
    "target_language": "es",
    "target_accepted_results": 2
  }'
```

### 3.4. Caso real: Desarrollador web buscando clínicas dentales

```bash
curl -X POST http://localhost:8000/api/v1/jobs/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "search_query": "clinicas dentales madrid",
    "user_profession": "Desarrollador Web",
    "user_technologies": ["WordPress", "SEO", "Core Web Vitals"],
    "user_value_proposition": "Ayudo a clinicas a conseguir mas pacientes con sitios web mas rapidos y orientados a conversion.",
    "target_niche": "Salud Dental",
    "target_location": "España",
    "target_language": "es",
    "target_company_size": "5-20 empleados",
    "target_pain_points": ["Sitio lento", "Sin reservas online", "Mala conversion"],
    "target_budget_signals": ["Anuncios activos", "Multiples servicios"],
    "target_accepted_results": 5,
    "max_candidates_to_process": 20
  }'
```

### 3.5. Caso real: Editor de Video buscando marcas personales y coaches

Gracias al parámetro `allow_social_profiles` derivado de la profesión, este job no bloqueará perfiles de Instagram ni TikTok y buscará explícitamente en esas redes:

```bash
curl -X POST http://localhost:8000/api/v1/jobs/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "search_query": "marcas personales ecommerce y coaches de negocios España",
    "user_profession": "Editor de Video",
    "user_technologies": ["Adobe Premiere Pro", "After Effects", "DaVinci Resolve"],
    "user_value_proposition": "Ayudo a marcas personales, tiendas online y coaches a escalar su facturación con videos cortos de alta retención para Reels, TikTok y YouTube Shorts.",
    "user_past_successes": ["Escale un coach de 5k a 50k seguidores en 2 meses con reels dinamicos y capte clientes de alto valor"],
    "target_niche": "Marcas Personales y Coaches",
    "target_location": "España",
    "target_language": "es",
    "target_pain_points": ["Reels sin alcance", "Falta de consistencia en redes", "Mala retención de audiencia en el inicio de los videos"],
    "target_budget_signals": ["Venden cursos o infoproductos", "Activos en Instagram o TikTok con mas de 10k seguidores", "Tienen linktree/tienda oficial"],
    "target_accepted_results": 5,
    "max_candidates_to_process": 25
  }'
```

---

## 4. Endpoints disponibles

### 4.1. `POST /api/v1/jobs/scrape`

Crea un job y responde `202 Accepted`. El procesamiento ocurre en background.

#### Payload soportado

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `search_query` | `string` | No* | Query para discovery orgánico |
| `urls` | `string[]` | No* | URLs semilla directas |
| `user_profession` | `string` | No | Perfil del vendedor |
| `user_technologies` | `string[]` | No | Herramientas o stack |
| `user_value_proposition` | `string` | No | Propuesta de valor |
| `user_past_successes` | `string[]` | No | Casos de éxito |
| `user_roi_metrics` | `string[]` | No | Métricas comerciales |
| `target_niche` | `string` | No | Nicho objetivo |
| `target_location` | `string` | No | País o ciudad objetivo |
| `target_language` | `string` | No | Idioma objetivo |
| `target_company_size` | `string` | No | Rango de tamaño |
| `target_pain_points` | `string[]` | No | Problemas del prospecto ideal |
| `target_budget_signals` | `string[]` | No | Señales de presupuesto |
| `max_results` | `int` | No | Alias legacy del objetivo |
| `target_accepted_results` | `int` | No | Meta de prospectos `accepted` |
| `max_candidates_to_process` | `int` | No | Tope duro de candidatos procesados |

\* Debes enviar al menos `search_query` o `urls`.

#### Reglas operativas actuales

- Si omites `target_accepted_results`, se usa `max_results`.
- Si omites `max_candidates_to_process`, el sistema deriva un cap aproximado de `4x` el objetivo, con piso de `5`.
- El discovery usa batches de queries y reapertura incremental si faltan aceptados.
- `search_query` no recibe defaults silenciosos de nicho o profesión.

#### Errores comunes

| Código | Causa |
|--------|-------|
| `400` | No enviaste `search_query` ni `urls` |
| `400` | Discovery no encontró URLs válidas |
| `422` | Algún campo no cumple el schema |

---

### 4.2. `GET /api/v1/jobs/{job_id}`

Devuelve el estado operativo del job y sus resúmenes.

```bash
curl http://localhost:8000/api/v1/jobs/41
```

Campos importantes:

- `ai_summary`: uso de IA, fallbacks, tokens y costo estimado.
- `quality_summary`: distribución `accepted` / `needs_review` / `rejected`.
- `capture_summary`: objetivo, procesados, acceptance rate y motivos de caída.
- `operational_summary`: `accepted=0`, candidatos por aceptado y ruido de discovery.
- `recent_errors`: últimos errores resumidos del job.

Interpretación rápida:

- `status=completed` no significa necesariamente que haya aceptados.
- Si `results` devuelve `[]`, revisa `quality_summary`, `capture_summary` y `operational_summary`.
- Si `stopped_reason=discovery_exhausted`, el pipeline agotó queries/candidatos antes de llegar al objetivo.

---

### 4.3. `GET /api/v1/jobs/{job_id}/results`

Devuelve prospectos del job desde `job_prospects`.

```bash
curl "http://localhost:8000/api/v1/jobs/41/results"
curl "http://localhost:8000/api/v1/jobs/41/results?limit=10&offset=0"
curl "http://localhost:8000/api/v1/jobs/41/results?quality=accepted,needs_review"
curl "http://localhost:8000/api/v1/jobs/41/results?quality=all"
curl "http://localhost:8000/api/v1/jobs/41/results?quality=rejected"
```

#### Query params

| Param | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `limit` | `int` | `50` | Tamaño de página |
| `offset` | `int` | `0` | Desplazamiento |
| `quality` | `string` | `accepted` | `accepted`, `accepted,needs_review`, `rejected`, `all` |

#### Regla importante

Si `quality` contiene un valor inválido, el endpoint responde `422`.  
Ejemplo inválido:

```bash
curl "http://localhost:8000/api/v1/jobs/41/results?quality=accepted,foo"
```

#### Campos comerciales y de normalización visibles

Campos nuevos o relevantes que ahora conviene leer en cada resultado:

| Campo | Qué significa |
|-------|----------------|
| `acceptance_decision` | Decisión comercial final: `accepted_target`, `accepted_related`, `rejected_directory`, `rejected_media`, `rejected_article`, `rejected_low_confidence` |
| `entity_type_detected` | Tipo de entidad detectado: `direct_business`, `directory`, `aggregator`, `marketplace`, `media`, `blog_post`, `association`, `agency`, `consultant`, `unknown` |
| `is_target_entity` | Si el sitio representa una entidad objetivo real o solo contexto relacionado |
| `canonical_identity` | Identidad canónica estable del prospecto. Puede ser dominio o `instagram:handle` / `tiktok:handle` |
| `primary_identity_type` | Superficie principal del lead: `website` o `social_profile` |
| `primary_identity_url` | URL principal del lead. Puede ser el sitio o el perfil social |
| `entry_surface` | Superficie exacta por la que entró el lead: artículo, home, perfil social o hub |
| `identity_surface` | Superficie que el sistema toma como identidad comercial real |
| `contact_surface` | Mejor superficie visible para iniciar contacto |
| `offer_surface` | Superficie donde la oferta se entiende mejor |
| `identity_resolution_reason` | Razón compacta de cómo se resolvió la identidad |
| `contact_consistency_status` | Si el email principal parece consistente con el dominio del sitio |
| `primary_email_confidence` | Confianza del email principal elegido |
| `primary_phone_confidence` | Confianza del teléfono principal elegido |
| `tiktok_url` | Perfil de TikTok detectado si existe |
| `social_profiles` | Lista normalizada de perfiles sociales detectados con plataforma, handle y confianza |
| `location` | Ubicación visible ya normalizada para consumo |
| `raw_location_text` | Texto crudo de ubicación antes de normalización |
| `parsed_location` | Ubicación parseada en piezas |
| `city`, `region`, `country`, `postal_code` | Componentes normalizados de ubicación |
| `validated_location` | Campo técnico de validación geográfica |
| `observed_signals` | Señales observadas directamente en el sitio |
| `inferred_opportunities` | Hipótesis u oportunidades inferidas, no hechos observados |
| `taxonomy_top_level` | Taxonomía cerrada de alto nivel |
| `taxonomy_business_type` | Tipo de negocio normalizado dentro de la taxonomía |

Ejemplo rápido:

```bash
curl "http://localhost:8000/api/v1/jobs/41/results?quality=accepted,needs_review"
```

Qué mirar en la respuesta:

- `accepted_target` = negocio alineado con el ICP.
- `accepted_related` = contexto útil, pero no lead principal.
- `rejected_directory`, `rejected_media`, `rejected_article` = ruido comercial no objetivo.
- `location` = valor limpio para UI.
- `validated_location` = evidencia técnica de matching geográfico.
- `entry_surface` vs `identity_surface` = diferencia entre dónde apareció el lead y quién es realmente.

---

### 4.4. `GET /api/v1/jobs/{job_id}/logs`

Logs persistidos del job para debugging operativo.

```bash
curl "http://localhost:8000/api/v1/jobs/41/logs"
curl "http://localhost:8000/api/v1/jobs/41/logs?limit=20&offset=0"
curl "http://localhost:8000/api/v1/jobs/41/logs?level=ERROR"
curl "http://localhost:8000/api/v1/jobs/41/logs?level=WARNING"
```

#### Query params

| Param | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `limit` | `int` | `50` | Tamaño de página |
| `offset` | `int` | `0` | Desplazamiento |
| `level` | `INFO \| WARNING \| ERROR` | `null` | Filtro opcional por nivel |

Qué mirar aquí:

- exclusiones tempranas de discovery;
- reaperturas incrementales de discovery;
- fallos HTTP o anti-bot;
- motivos de rechazo por URL;
- fallbacks de IA.

---

### 4.5. `GET /api/v1/jobs/metrics/operational`

KPIs agregados de jobs recientes para auditar recall y precisión operativa.

```bash
curl "http://localhost:8000/api/v1/jobs/metrics/operational"
curl "http://localhost:8000/api/v1/jobs/metrics/operational?limit=200"
```

#### Query params

| Param | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `limit` | `int` | `100` | Cantidad de jobs recientes a agregar |

#### Qué expone

- `completed_jobs_with_zero_accepted`
- `completed_jobs_with_zero_accepted_ratio`
- `average_acceptance_rate`
- `average_candidates_per_accepted`
- `average_article_directory_exclusion_ratio`
- `total_article_exclusions`
- `total_directory_exclusions`

Esto sirve para validar si el refinamiento está mejorando recall sin degradar precisión.

---

### 4.6. `GET /api/v1/jobs/metrics/commercial`

KPIs agregados de clasificación comercial y calidad de contacto.

```bash
curl "http://localhost:8000/api/v1/jobs/metrics/commercial"
curl "http://localhost:8000/api/v1/jobs/metrics/commercial?limit=200"
```

#### Query params

| Param | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `limit` | `int` | `100` | Cantidad de jobs recientes a agregar |

#### Qué expone

- `total_accepted_target`
- `total_accepted_related`
- `total_rejected_non_target`
- `accepted_non_target_rate`
- `inconsistent_contact_count`
- `inconsistent_contact_rate`
- `false_phone_filtered_count`
- `false_phone_filtered_rate`
- `accepted_target_precision`
- `rollout_stage`
- `rollout_layers_completed`

Esto sirve para medir:

- baja de `accepted` no objetivo;
- baja de emails inconsistentes;
- baja de teléfonos falsos;
- mayor precisión de `accepted_target`.

Ejemplo de lectura:

- si sube `accepted_target_precision`, la clasificación comercial está más limpia;
- si baja `accepted_non_target_rate`, están entrando menos relacionados como aceptados;
- si sube `false_phone_filtered_count`, el parser está detectando más ruido numérico antes de persistirlo.

---

### 4.7. `GET /health`

```bash
curl http://localhost:8000/health
```

Útil para probes simples de disponibilidad.

---

## 5. Lectura operativa de respuestas

### 5.1. Cómo distinguir un job sano de un job “vacío”

Un job puede estar técnicamente bien y aun así devolver pocos o ningún `accepted`.

Revisa:

- `quality_summary.accepted`
- `quality_summary.needs_review`
- `capture_summary.stopped_reason`
- `operational_summary.completed_with_zero_accepted`
- `operational_summary.article_directory_exclusion_ratio`

### 5.2. Cómo interpretar `stopped_reason`

| Valor | Significado |
|-------|-------------|
| `target_reached` | Se alcanzó la meta de aceptados |
| `candidate_cap_reached` | Se consumió el presupuesto máximo de candidatos |
| `discovery_exhausted` | Se agotaron batches de discovery útiles |
| `fatal_error` | El worker terminó por un error global |

### 5.3. Qué significa cada estado de calidad

| Estado | Significado |
|--------|-------------|
| `accepted` | Lead suficientemente alineado para ser visible por defecto |
| `needs_review` | Hay valor potencial, pero falta evidencia o hay ambigüedad |
| `rejected` | El sitio no cumple la calidad mínima o está fuera de objetivo |

---

## 6. Reglas de negocio visibles en la API

- El endpoint de resultados usa `accepted` por defecto.
- El quality gate puede rechazar por geografía, idioma o contacto pobre.
- Discovery prioriza sitios oficiales y puede usar directorios como semilla, no como resultado final.
- El sistema intenta ahorrar IA: no todos los leads pasan por DeepSeek.
- Los resultados están ligados al job por `job_prospects`, no solo por el prospecto canónico.

---

## 7. Qué sigue pendiente

Pendientes más relevantes fuera del contrato actual:

- seguridad interna tipo `X-Internal-Token` o `Bearer` fijo para producción;
- workers persistentes fuera de `BackgroundTasks`;
- cache IA compartido entre procesos;
- métricas históricas persistidas más allá del agregado “últimos N jobs”;
- fuentes adicionales además de DDG cuando el mercado lo requiera.

Para backlog vivo:

- [07-observaciones-y-plan-de-mejora.md](07-observaciones-y-plan-de-mejora.md)
- [12-plan-refinamiento-captura-y-recall.md](12-plan-refinamiento-captura-y-recall.md)
- [13-estado-actual-foda-y-pendientes.md](13-estado-actual-foda-y-pendientes.md)
