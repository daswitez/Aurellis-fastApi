# Mapa de Módulos y Lógica Actual

Este documento explica qué hace cada módulo importante del proyecto, qué lógica concentra y cómo se conecta con el resto del pipeline.

Complementa:

- [03-arquitectura-tecnica.md](03-arquitectura-tecnica.md)
- [05-api-y-reglas.md](05-api-y-reglas.md)
- [13-estado-actual-foda-y-pendientes.md](13-estado-actual-foda-y-pendientes.md)

---

## 1. Vista rápida del pipeline

El flujo actual es:

1. `POST /api/v1/jobs/scrape` recibe intención de búsqueda.
2. `app/services/discovery.py` normaliza objetivo, ratio y batches de queries.
3. `app/scraper/search_engines/ddg_search.py` ejecuta discovery, filtra ruido y pre-rankea resultados.
4. `app/api/jobs.py` crea el job y lanza el worker.
5. `app/scraper/engine.py` scrapea homepage y páginas clave del dominio.
6. `app/scraper/parser.py` extrae metadata estructurada y señales visibles.
7. `app/services/entity_classifier.py` clasifica tipo de entidad.
8. `app/services/prospect_quality.py` decide calidad técnica y decisión comercial.
9. `app/services/heuristic_extractor.py` construye baseline comercial.
10. `app/services/ai_extractor.py` enriquece solo si el gate lo permite.
11. `app/services/scoring.py` combina heurística, IA y calidad.
12. `app/services/db_upsert.py` persiste en `prospects`, `job_prospects`, contactos y páginas.
13. `app/services/business_taxonomy.py` resuelve taxonomía cerrada.
14. `GET /jobs/...` expone estado, resultados, logs, métricas operativas y métricas comerciales.

---

## 2. API y orquestación

### `app/main.py`

Responsabilidad:

- arrancar FastAPI;
- registrar routers;
- exponer `/health`.

Lógica:

- no contiene reglas de scraping;
- sirve como punto de entrada y smoke check mínimo.

### `app/api/jobs.py`

Responsabilidad:

- exponer el contrato HTTP principal;
- crear jobs;
- coordinar discovery inicial;
- ejecutar el worker de scraping en background;
- resumir métricas y observabilidad;
- servir resultados, logs y KPIs operativos.

Lógica importante:

- resuelve la semántica nueva de captura con `target_accepted_results` y `max_candidates_to_process`;
- arranca el worker con `job_context` explícito, sin defaults comerciales silenciosos;
- procesa candidatos por tandas;
- reabre discovery si faltan aceptados y todavía hay presupuesto;
- consolida `ai_summary`, `quality_summary`, `capture_summary` y `operational_summary`;
- expone `GET /jobs/metrics/operational` para seguimiento agregado;
- expone `GET /jobs/metrics/commercial` para medir precision comercial, contactos inconsistentes, ruido telefonico filtrado y rollout.

Qué cambio reciente consolidó:

- filtro `quality` robusto en `/results`;
- resumen de captura y métricas operativas;
- resumen de métricas comerciales;
- reapertura incremental de discovery;
- trazabilidad de exclusiones tempranas y batches procesados.

### `app/api/schemas.py`

Responsabilidad:

- definir el contrato de entrada y salida;
- tipar los resúmenes operativos del job;
- estabilizar el contrato visible hacia consumidores.

Lógica importante:

- `JobCreateRequest` modela el job desde intención comercial, nicho y objetivos de captura;
- `ProspectOut` expone el resultado visible por job;
- `JobCaptureSummary` y `JobOperationalSummary` explican por qué un job terminó con o sin aceptados;
- `JobsOperationalMetricsResponse` resume recall y precisión en agregado;
- `JobsCommercialMetricsResponse` resume precision comercial, contactos inconsistentes y telefonos falsos filtrados.

---

## 3. Persistencia y modelo de datos

### `app/models.py`

Responsabilidad:

- definir el esquema SQLAlchemy del runtime.

Lógica estructural:

- `ScrapingJob` representa la corrida;
- `Prospect` representa la entidad canónica por dominio;
- `JobProspect` representa la participación de un prospecto dentro de un job;
- `ProspectContact` separa canales de contacto detectados;
- `ProspectPage` conserva páginas visitadas o inferidas;
- `ScrapingLog` guarda trazabilidad operativa.

Por qué importa:

- evita sobrescribir el historial cuando un mismo dominio aparece en múltiples jobs;
- permite que el contrato visible salga por job sin perder entidad canónica.

### `app/services/db_upsert.py`

Responsabilidad:

- persistir prospectos y resultados sin duplicación accidental.

Lógica importante:

- separa dato canónico de dato contextual del job;
- hace `upsert` por dominio en `Prospect`;
- guarda `quality_status`, `rejection_reason`, evidence packs, AI trace y scoring trace en `JobProspect`;
- persiste `acceptance_decision`, taxonomia, consistencia de contacto y evidencia comercial;
- persiste contactos y páginas deduplicadas.

Qué habilita:

- reusar un prospecto en varios jobs;
- mantener trazabilidad de la decisión de calidad por corrida;
- dejar base lista para CRM o historial analítico.

---

## 4. Discovery y búsqueda

### `app/services/discovery.py`

Responsabilidad:

- construir la estrategia de discovery antes de tocar DDG.

Lógica importante:

- normaliza `search_query`, nicho, ubicación e idioma;
- genera familias de queries;
- aplica negativas para bajar ruido editorial;
- define el ratio objetivo/candidatos;
- define tamaño de batches de candidatos;
- construye batches de queries canónicas y de reintento.

Qué resolvió:

- `H-001` / `H-002`: semántica correcta de captura;
- `H-003` / `H-004`: query expansion y negativas;
- `H-013` / `H-014` / `H-015`: batches, reapertura y ratio operativo.

### `app/scraper/search_engines/ddg_search.py`

Responsabilidad:

- ejecutar discovery real sobre DuckDuckGo HTML.

Lógica importante:

- parsea resultados SERP;
- bloquea dominios claramente inútiles;
- puntúa `business_likeness`;
- excluye artículos y resultados demasiado informativos;
- conserva metadata útil del hallazgo;
- puede usar directorios como seed para resolver el sitio oficial.

Señales que usa:

- `title`;
- `snippet`;
- `path`;
- profundidad de URL;
- hints de contacto, servicios y “sitio oficial”;
- patrones editoriales;
- directorios conocidos.

Por qué es crítico:

- es la frontera entre “recall útil” y “ruido caro”.

---

## 5. Scraping, parsing y crawl

### `app/scraper/http_client.py`

Responsabilidad:

- descargar HTML con control básico de retries y headers.

Lógica importante:

- rota user agents;
- clasifica errores HTTP/red;
- soporta verificación TLS configurable;
- no pretende resolver anti-bot avanzado todavía.

### `app/scraper/parser.py`

Responsabilidad:

- convertir HTML en texto limpio y metadata estructurada.

Lógica importante:

- extrae `title`, `description`, idioma y locale;
- parsea JSON-LD;
- detecta direcciones, teléfonos, emails y mapas;
- detecta CTA principal, booking, pricing, servicios y páginas internas;
- consolida canales de contacto visibles y estructurados;
- filtra telefonos falsos y cuenta `phone_validation_rejections`.

Resultado:

- un `clean_text` útil para heurística/IA;
- un `metadata` rico para quality gate y scoring;
- evidencia util para metricas comerciales y limpieza de telefonos.

### `app/scraper/engine.py`

Responsabilidad:

- orquestar el scrape completo de un dominio.

Lógica importante:

- scrapea homepage;
- selecciona páginas clave internas;
- hace crawl limitado con early stop;
- fusiona metadata de páginas relevantes;
- corre baseline heurístico;
- corre quality gate;
- decide si llamar o no a IA;
- recalcula taxonomia final;
- construye el payload final persistible.

Por qué importa:

- es el punto donde discovery se convierte en prospecto evaluado.

---

## 6. Calidad, heurística y scoring

### `app/services/prospect_quality.py`

Responsabilidad:

- validar si el candidato tiene valor visible y si coincide con el target.

Lógica importante:

- detecta idioma principal;
- construye evidencia geográfica desde `address`, `areaServed`, `PostalAddress`, TLD, prefijos telefónicos, mapa, title y snippet;
- calcula calidad de contacto;
- clasifica `accepted`, `needs_review` o `rejected`;
- define `rejection_reason`, `quality_flags` y `score_multiplier`;
- separa `location` visible de `validated_location`;
- construye `parsed_location`, `city`, `region`, `country` y `postal_code`;
- define `acceptance_decision` como capa comercial separada;
- arma el `evidence pack` compacto para IA.

### `app/services/entity_classifier.py`

Responsabilidad:

- clasificar tipo de entidad antes del score final.

Lógica importante:

- distingue negocio real, directorio, comparador, marketplace, medio, artículo, asociación, agencia y consultor;
- produce `entity_type_detected`, `entity_type_confidence`, `entity_type_evidence` e `is_target_entity`;
- evita que el score final tenga que inferir solo por relevancia semántica si un sitio es target real.

### `app/services/commercial_insights.py`

Responsabilidad:

- normalizar la frontera entre observación e inferencia comercial.

Lógica importante:

- normaliza `observed_signals`;
- normaliza `inferred_opportunities`;
- mantiene compatibilidad transitoria con `pain_points_detected`.

### `app/services/business_taxonomy.py`

Responsabilidad:

- resolver una taxonomía cerrada de negocio reutilizable por heurística, IA y engine.

Lógica importante:

- emite `taxonomy_top_level`;
- emite `taxonomy_business_type`;
- evita depender de `inferred_niche` libre para decisiones de agrupación.

Qué resolvió:

- geo strict usable sin depender solo de coincidencia textual;
- rechazo temprano de leads pobres;
- ahorro de tokens cuando el lead no vale la pena.

### `app/services/heuristic_extractor.py`

Responsabilidad:

- producir una lectura comercial local del sitio sin LLM.

Lógica importante:

- mide intención comercial, presencia de contacto, señales de madurez y contexto del negocio;
- produce baseline aun cuando IA falle o se omita;
- entrega trazas y atributos útiles para fallback.

### `app/services/scoring.py`

Responsabilidad:

- mezclar resultado heurístico, calidad y enriquecimiento IA.

Lógica importante:

- penaliza leads de baja calidad;
- pondera distinto según confianza y método usado;
- deja `scoring_trace` para explicar el score final.

---

## 7. IA y optimización de costo

### `app/services/ai_extractor.py`

Responsabilidad:

- encapsular la llamada a DeepSeek a través del SDK compatible.

Lógica importante:

- recibe un `evidence pack` compacto;
- valida schema de salida;
- mide tokens, latencia y costo;
- aplica cache por firma de contenido y versión de prompt;
- cae a fallback heurístico si la IA falla o responde mal.

Qué evita:

- gastar tokens en leads rechazados;
- meter texto innecesario en el prompt;
- aceptar respuestas de IA sin shape controlado.

### `docs/10-diseno-prompt-deepseek.md`

Aunque no es código, funciona como contrato de esa capa.

Describe:

- qué contexto entra al modelo;
- qué salida se espera;
- qué decisiones siguen siendo determinísticas y no del LLM.

---

## 8. Observabilidad y pruebas

### `tests/test_discovery.py`

Qué cubre:

- construcción de queries;
- ratio objetivo/candidatos;
- batches de discovery;
- fixtures SERP offline;
- exclusión editorial y prioridad comercial;
- directorios usados como seed.

### `tests/test_parser_and_quality.py`

Qué cubre:

- parser estructurado;
- `areaServed`, `PostalAddress`, TLD, prefijos y mapas;
- clasificación geo/idioma/contacto;
- filtrado de teléfonos falsos;
- precedencia entre `location`, `raw_location_text` y `validated_location`.

### `tests/test_commercial_fixtures.py`

Qué cubre:

- negocio real;
- directorio;
- comparador;
- medio;
- asociación;
- contacto inconsistente;
- ubicación contaminada;
- teléfono falso tipo fecha o secuencia.

### `tests/test_commercial_metrics.py`

Qué cubre:

- `accepted_target_precision`;
- `accepted_non_target_rate`;
- conteo de contactos inconsistentes;
- agregación de teléfonos falsos filtrados;
- `rollout_stage` y `rollout_layers_completed`.

### `tests/test_ai_observability.py`

Qué cubre:

- `quality` filter;
- `capture_summary`;
- skips y fallbacks IA;
- métricas de observabilidad del enrich.

### `tests/test_operational_metrics.py`

Qué cubre:

- conteo de exclusiones tempranas;
- `operational_summary`;
- agregación de métricas tipo `accepted=0`, candidatos por aceptado y ratio de ruido.

---

## 9. Documentos que explican el sistema desde distintos ángulos

| Documento | Uso |
|----------|-----|
| [03-arquitectura-tecnica.md](03-arquitectura-tecnica.md) | visión de capas |
| [05-api-y-reglas.md](05-api-y-reglas.md) | contrato consumible |
| [06-estado-del-sistema.md](06-estado-del-sistema.md) | estado operativo resumido |
| [07-observaciones-y-plan-de-mejora.md](07-observaciones-y-plan-de-mejora.md) | deuda técnica y backlog |
| [09-cambios-implementados-hasta-fase-b.md](09-cambios-implementados-hasta-fase-b.md) | histórico de cambios ejecutados |
| [12-plan-refinamiento-captura-y-recall.md](12-plan-refinamiento-captura-y-recall.md) | plan y estado de recall/captura |
| [13-estado-actual-foda-y-pendientes.md](13-estado-actual-foda-y-pendientes.md) | lectura ejecutiva de fortalezas, debilidades, amenazas y próximos pasos |
| [clasificacion-comercial/README.md](clasificacion-comercial/README.md) | implementación consolidada del plan comercial |

---

## 10. Lectura recomendada por perfil

Si eres integrador:

1. [05-api-y-reglas.md](05-api-y-reglas.md)
2. [06-quickstart.md](06-quickstart.md)
3. [06-estado-del-sistema.md](06-estado-del-sistema.md)

Si vas a tocar scraping o quality:

1. [03-arquitectura-tecnica.md](03-arquitectura-tecnica.md)
2. [clasificacion-comercial/README.md](clasificacion-comercial/README.md)
3. [12-plan-refinamiento-captura-y-recall.md](12-plan-refinamiento-captura-y-recall.md)
4. este documento

Si vas a planificar siguientes fases:

1. [13-estado-actual-foda-y-pendientes.md](13-estado-actual-foda-y-pendientes.md)
2. [clasificacion-comercial/01-estado-implementado.md](clasificacion-comercial/01-estado-implementado.md)
3. [07-observaciones-y-plan-de-mejora.md](07-observaciones-y-plan-de-mejora.md)
4. [docs/backlog/plan-detallado-estabilizacion-y-mejora.md](backlog/plan-detallado-estabilizacion-y-mejora.md)
