# Mapa de Módulos y Cambios Recientes

Este documento aterriza, módulo por módulo, qué cambió en el refinamiento reciente del pipeline de scraping, calidad de datos y ahorro de tokens.

Sirve como complemento de:

- [03-arquitectura-tecnica.md](03-arquitectura-tecnica.md) para entender las capas;
- [05-api-y-reglas.md](05-api-y-reglas.md) para el contrato visible;
- [09-cambios-implementados-hasta-fase-b.md](09-cambios-implementados-hasta-fase-b.md) para el resumen ejecutivo del rollout.

## 1. API y Contratos

### `app/api/jobs.py`
- centraliza la creación del `job_context`;
- normaliza discovery y arma queries canónicas;
- conserva metadata SERP del hallazgo;
- coordina el worker de scraping;
- agrega métricas de IA y trazas por job;
- filtra `GET /jobs/{id}/results` para devolver solo prospectos `accepted`.

### `app/api/schemas.py`
- amplía `ProspectOut` con campos públicos de calidad y accionabilidad:
  - `validated_location`
  - `location_match_status`
  - `location_confidence`
  - `detected_language`
  - `language_match_status`
  - `primary_cta`
  - `booking_url`
  - `pricing_page_url`
- tipa resúmenes y métricas nuevas del job.

## 2. Persistencia

### `app/models.py`
- agrega columnas nuevas en `prospects` para ubicación validada, idioma detectado, CTA, booking, pricing, canales de contacto y señales ICP;
- agrega columnas en `job_prospects` para `quality_status`, `quality_flags_json`, `rejection_reason` y `discovery_confidence`;
- deja el modelo preparado para distinguir entre dato visible del prospecto y calidad interna del hallazgo.

### `app/services/db_upsert.py`
- persiste evidencia estructurada y resultados enriquecidos sin duplicar por dominio;
- guarda `quality_status`, `rejection_reason`, `quality_flags_json` y metadata de discovery;
- conserva `contact_channels_json`, `contact_quality_score`, `service_keywords`, `heuristic_trace`, `ai_trace` y `scoring_trace`.

### `migrations/versions/1f9e6b5c2a10_refine_scraping_quality_and_results.py`
- crea el cambio de esquema para los campos nuevos;
- backfillea `quality_status='accepted'` para registros previos donde aplica;
- deja lista la base para exponer los resultados refinados sin romper compatibilidad.

## 3. Discovery y Búsqueda

### `app/services/discovery.py`
- normaliza `search_query`, `target_location` y `target_language`;
- sintetiza consultas cuando el usuario no manda un query explícito;
- construye hasta 3 queries canónicas;
- mantiene consistencia entre intención del usuario y consultas ejecutadas contra DDG.

### `app/scraper/search_engines/ddg_search.py`
- transforma DDG en una capa de discovery menos ruidosa;
- devuelve `query`, `position`, `title`, `snippet` y `discovery_confidence`;
- endurece exclusiones de agregadores, directorios y redes;
- permite usar el snippet como evidencia temprana para validación geo.

## 4. Parsing y Crawl

### `app/scraper/parser.py`
- amplía el parsing determinístico más allá del texto plano;
- extrae `html lang`, `meta locale`, JSON-LD, direcciones, mapas, horarios, WhatsApp, booking, pricing, servicios y CTAs;
- consolida `structured_data_evidence`, `cta_evidence`, `language_evidence` y `geo_evidence`;
- prepara un output más compacto y accionable para heurística, scoring e IA.

### `app/scraper/engine.py`
- orquesta el crawl de homepage y hasta 5 páginas internas prioritarias;
- aplica early stop cuando ya se cubrió contacto, ubicación y CTA;
- ejecuta parser, baseline heurístico, quality gate, IA opcional y score final;
- construye el prospecto persistible con trazas completas (`heuristic_trace`, `ai_trace`, `scoring_trace`);
- evita llamar IA si el lead ya fue rechazado o si el baseline resolvió con suficiente confianza.

## 5. Calidad, Heurística y Scoring

### `app/services/prospect_quality.py`
- valida ubicación, idioma, contacto y señales mínimas del sitio;
- clasifica el lead como `accepted`, `needs_review` o `rejected`;
- define `rejection_reason`, `quality_flags` y `score_multiplier`;
- arma el `evidence pack` compacto para IA;
- implementa el `heuristic gate` que reduce gasto de tokens.

### `app/services/heuristic_extractor.py`
- mantiene el baseline comercial no dependiente de IA;
- puntúa intención comercial, madurez digital, disponibilidad de contacto y ajuste contextual;
- ahora no rellena ubicación copiando el target del usuario;
- entrega señales reutilizables incluso cuando la IA se omite.

### `app/services/scoring.py`
- mezcla score heurístico e IA de forma estable;
- incorpora `quality_data` para penalizar leads dudosos o fuera de objetivo;
- deja trazabilidad del peso aplicado por confianza, acuerdo y calidad.

## 6. IA y Optimización de Tokens

### `app/services/ai_extractor.py`
- valida la salida del proveedor con schema interno;
- usa payload compacto basado en evidencia, no texto crudo de gran tamaño;
- mide latencia, tokens y costo estimado;
- cachea respuestas por firma de contenido y versión de prompt;
- devuelve motivos explícitos cuando cae a fallback o cuando se decide `skipped`.

## 7. Documentación relacionada

### `docs/02-funcionalidades-core.md`
- describe el comportamiento funcional del pipeline actual, incluyendo quality gate, crawl ampliado y enriquecimiento opcional.

### `docs/03-arquitectura-tecnica.md`
- documenta capas, flujo y responsabilidades técnicas.

### `docs/04-modelo-datos.md`
- baja el contrato de datos a entidades y campos persistidos.

### `docs/05-api-y-reglas.md`
- documenta el contrato consumible por integradores y el filtro de resultados aceptados.

### `docs/06-estado-del-sistema.md`
- resume el estado operativo real del MVP refinado.

### `docs/07-observaciones-y-plan-de-mejora.md`
- distingue lo ya resuelto de los riesgos o gaps que todavía quedan.

### `docs/09-cambios-implementados-hasta-fase-b.md`
- resume el rollout completo de estabilización y del refinamiento de scraping/calidad.

### `docs/10-diseno-prompt-deepseek.md`
- deja explícito el cambio de prompt hacia `evidence pack` compacto y runtime con cache/gating.

## 8. Tests de referencia

### `tests/test_discovery.py`
- verifica queries canónicas, normalización y exclusiones básicas del discovery.

### `tests/test_parser_and_quality.py`
- cubre extracción estructurada de parser y reglas de calidad geo/idioma/contacto.

### `tests/test_ai_extractor.py`
- valida schema, normalización y cache del extractor IA.

### `tests/test_ai_observability.py`
- verifica observabilidad, resúmenes IA y skips por reglas de calidad.

## 9. Lectura recomendada

Si necesitas seguir el flujo completo sin leer todo el código:

1. Lee [05-api-y-reglas.md](05-api-y-reglas.md).
2. Luego revisa [03-arquitectura-tecnica.md](03-arquitectura-tecnica.md).
3. Después usa este documento para ubicar el archivo exacto que implementa cada comportamiento.
