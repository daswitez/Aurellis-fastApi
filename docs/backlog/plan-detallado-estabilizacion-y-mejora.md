# Plan Detallado de Estabilización y Mejora

**Fecha:** 2026-03-10  
**Propósito:** convertir las observaciones técnicas del documento principal en un backlog accionable, priorizado y verificable.

---

## 1. Cómo usar este backlog

Este backlog no reemplaza las fases originales del MVP. Las complementa.  
Las fases originales explican el camino general del proyecto. Este documento, en cambio, baja ese camino a tareas concretas para corregir inconsistencias, estabilizar el sistema y preparar la siguiente etapa.

### Regla de ejecución

No conviene avanzar a optimizaciones o features nuevas si la base técnica sigue inestable.  
Por eso el orden recomendado es:

1. **Estabilizar contrato, setup y persistencia**
2. **Mejorar confiabilidad operativa**
3. **Subir calidad del enriquecimiento**
4. **Escalar e integrar a producción**

---

## 2. Prioridades globales

### Prioridad P0

Bloqueantes o problemas que hoy degradan confianza, reproducibilidad o consistencia del sistema.

### Prioridad P1

Mejoras que aumentan robustez operativa y reducen riesgo de fallos silenciosos.

### Prioridad P2

Mejoras que suben la calidad de los datos y del scoring comercial.

### Prioridad P3

Cambios de escalabilidad, integración oficial y endurecimiento de producción.

---

## 3. Fase A — Estabilización de base técnica (P0)

**Objetivo:** dejar el proyecto reproducible, consistente y sin contradicciones graves entre código, datos y documentación.

### A.1. Dependencias reproducibles

- [x] **A-001 Agregar dependencias faltantes al proyecto**
  - Incluir `openai` si se mantiene la integración compatible con DeepSeek.
  - Revisar dependencias no utilizadas y decidir si se eliminan o justifican.
  - Verificar compatibilidad entre `fastapi`, `pydantic`, `sqlalchemy`, `httpx` y `asyncpg`.
  - **Criterio de cierre:** una instalación limpia con `pip install -r requirements.txt` permite arrancar el servidor sin imports faltantes.

- [x] **A-002 Crear `.env.example` mínimo y realista**
  - Documentar `DATABASE_URL`, `DEEPSEEK_API_KEY`, flags de modo demo y cualquier token futuro.
  - Evitar valores falsos que parezcan válidos en producción.
  - **Criterio de cierre:** un desarrollador nuevo puede levantar el servicio sin depender de variables “mágicas” no documentadas.

- [x] **A-003 Corregir documentación de setup**
  - Unificar uso de `python3`, `docker compose` o `docker-compose`, según lo que el equipo decida como estándar.
  - Alinear quickstart, manuales y backlog.
  - **Criterio de cierre:** el flujo de instalación documentado coincide con el flujo real de arranque.

### A.2. Contrato de datos

- [x] **A-004 Definir contrato oficial para `score` y `confidence_level`**
  - `score` queda definido como `float` entre `0.0` y `1.0`.
  - `confidence_level` queda definido como semántico: `low | medium | high`.
  - Documentar la decisión en API, modelo y docs.
  - **Criterio de cierre:** no existen contradicciones entre SQLAlchemy, Pydantic, persistencia y documentación.

- [x] **A-005 Eliminar defaults de negocio peligrosos del payload**
  - Revisar defaults como profesión, nicho, país, pain points y budget signals.
  - Reemplazar por `None` o defaults neutrales.
  - **Criterio de cierre:** una request incompleta no inyecta contexto comercial arbitrario sin intención del usuario.

- [x] **A-006 Alinear schemas, modelos y docs**
  - Revisar tipos, nullabilidad y comentarios.
  - Corregir documentación que hoy describe mejorías deseadas como si fueran estado actual.
  - **Criterio de cierre:** cada campo expuesto por la API tiene una sola definición válida en todo el proyecto.

### A.3. Persistencia y modelo relacional

- [x] **A-007 Rediseñar relación entre jobs y prospects**
  - Separar entidad canónica del prospecto y relación transaccional por job.
  - Diseñar tabla pivote `job_prospects` o equivalente.
  - Definir qué campos viven en `prospects` y cuáles dependen del job.
  - Diseño objetivo documentado en `docs/08-diseno-base-prospeccion-y-crm.md`.
  - Entidades ORM base agregadas sin migración todavía: `job_prospects`, `prospect_contacts`, `prospect_pages`.
  - **Criterio de cierre:** un mismo dominio puede participar en múltiples jobs sin perder historial.

- [x] **A-008 Preparar migraciones para el nuevo modelo**
  - Crear migración de Alembic.
  - Evaluar si hace falta migración de datos o si alcanza con reset de entorno MVP.
  - Migración implementada: `6f41c9b2d7aa_prepare_prospecting_crm_base_tables.py`.
  - Incluye backfill inicial desde `prospects` hacia `job_prospects`, `prospect_contacts` y `prospect_pages`.
  - **Criterio de cierre:** el esquema nuevo se puede aplicar de punta a punta sin intervención manual ad hoc.

- [x] **A-009 Ajustar consultas de resultados**
  - Reescribir `GET /jobs/{id}/results` para usar la nueva tabla de relación.
  - Persistencia adaptada para escribir en `job_prospects`, `prospect_contacts` y `prospect_pages`.
  - Confirmar que el job devuelve exactamente los prospectos encontrados en esa corrida.
  - **Criterio de cierre:** consultar resultados de jobs históricos no depende del último `upsert` sobre un dominio.

### A.4. Ciclo de vida del job

- [x] **A-010 Registrar timestamps y métricas reales**
  - Guardar `started_at` al entrar en `running`.
  - Guardar `finished_at` al terminar.
  - Guardar contadores de procesadas, guardadas, fallidas y omitidas.
  - Implementado en `app/api/jobs.py` y migrado en `c7b8d4e2a1f0_add_job_runtime_metrics.py`.
  - **Criterio de cierre:** cada job deja una traza temporal y numérica coherente.

- [x] **A-011 Eliminar parámetros muertos o placeholders**
  - Revisar argumentos no usados como `db_url`.
  - Limpiar interfaces internas del worker.
  - El worker quedó reducido a `job_id`, `urls` y `job_context`.
  - **Criterio de cierre:** no quedan parámetros sin efecto en los puntos críticos del pipeline.

- [x] **A-012 Implementar logging persistente de errores por job**
  - Usar `scraping_logs` para registrar fallos relevantes.
  - Incluir `job_id`, etapa, dominio y mensaje resumido.
  - El flujo ya registra eventos de inicio, persistencia, omisión, error por URL y cierre de job.
  - **Criterio de cierre:** un fallo de scraping o persistencia deja evidencia consultable.

---

## 4. Fase B — Confiabilidad del pipeline (P1)

**Objetivo:** reducir fallos silenciosos y hacer que el comportamiento del pipeline sea más trazable y predecible.

### B.1. Descubrimiento de URLs

- [x] **B-001 Eliminar el fallback silencioso de DDG**
  - Quitar los dominios hardcodeados del flujo normal.
  - Si se necesita modo demo, activarlo mediante flag explícita.
  - Implementado con `DEMO_MODE`: sin demo, la búsqueda falla explícitamente; con demo, los resultados mock salen etiquetados como `mock_search`.
  - **Criterio de cierre:** cuando la búsqueda real falla, el sistema lo informa como fallo real o lo etiqueta explícitamente como demo/mock.

- [x] **B-002 Etiquetar origen de resultados**
  - Distinguir entre resultados orgánicos, mock, semillas directas y futuras integraciones externas.
  - `GET /jobs/{id}/results` ahora expone `source_type`, `discovery_method`, `search_query_snapshot` y `rank_position`.
  - La persistencia normaliza aliases históricos para no propagar strings libres fuera del contrato.
  - **Criterio de cierre:** cada prospecto o resultado tiene trazabilidad clara de origen.

### B.2. Cliente HTTP

- [x] **B-003 Rehabilitar verificación TLS por defecto**
  - Usar `verify=True` por defecto.
  - Permitir bypass solo mediante configuración controlada.
  - Implementado con `HTTP_VERIFY_TLS=true` por defecto y warning explícito cuando se desactiva.
  - **Criterio de cierre:** el servicio no acepta certificados inválidos salvo en modo de debugging explícito.

- [x] **B-004 Clasificar errores HTTP y de red**
  - Diferenciar timeout, DNS, TLS, 403, 429 y 5xx.
  - Mejorar mensajes de log y métricas de error.
  - El worker persiste `stage`, `error_type`, `status_code` y `retryable` en `scraping_logs.context_json`.
  - **Criterio de cierre:** la telemetría permite entender por qué falló una URL.

- [x] **B-005 Implementar retries y backoff**
  - Aplicar reintentos solo a fallos recuperables.
  - Evitar reintentar errores no recuperables sin sentido.
  - Implementado con `HTTP_MAX_RETRIES` y `HTTP_BACKOFF_BASE_SECONDS`, usando `retryable` como criterio de reintento.
  - **Criterio de cierre:** caídas transitorias bajan sin disparar comportamientos agresivos ni duplicar requests innecesariamente.

### B.3. Parsing y crawling interno

- [x] **B-006 Normalizar construcción de URLs**
  - Reemplazar concatenación manual por utilidades robustas como `urljoin`.
  - Implementado en el parser para resolver relativos, absolutos y filtrar externos/no navegables antes de persistir `internal_links`.
  - **Criterio de cierre:** links internos relativos y absolutos se resuelven correctamente.

- [x] **B-007 Seguir páginas clave del sitio**
  - Visitar `contact`, `about`, `nosotros`, `careers`, `equipo` cuando sea útil.
  - Limitar profundidad para no transformar el scraper en crawler amplio.
  - Implementado como crawling acotado: homepage + hasta `3` páginas clave del mismo dominio.
  - **Criterio de cierre:** el sistema mejora extracción de contacto y señales sin disparar costos o ruido excesivo.

- [x] **B-008 Mejorar extracción de contacto**
  - Buscar emails en texto visible además de `mailto:`.
  - Detectar teléfonos con mayor precisión.
  - Detectar formularios y páginas de contacto.
  - El parser ya extrae emails visibles, normaliza teléfonos y filtra placeholders obvios.
  - **Criterio de cierre:** sube la tasa de contacto útil y baja la tasa de falsos positivos.

### B.4. Job observability

- [x] **B-009 Enriquecer `GET /jobs/{id}`**
  - Incluir timestamps, métricas y resumen de errores.
  - Mantener compatibilidad razonable con integradores.
  - El endpoint ahora devuelve timestamps, contadores operativos, `source_type`, `error_message` y hasta 3 errores recientes resumidos.
  - **Criterio de cierre:** el estado del job permite monitoreo operativo real.

- [x] **B-010 Crear endpoint o vista de logs por job**
  - Permitir inspección rápida de fallos sin entrar a la base manualmente.
  - Implementado como `GET /jobs/{id}/logs` con paginación y filtro opcional por nivel.
  - **Criterio de cierre:** debugging básico posible vía API o documentación clara.

---

## 5. Fase C — Endurecimiento de IA y scoring (P1/P2)

**Objetivo:** hacer que la capa de enriquecimiento por IA sea más confiable, auditable y útil para priorización comercial.

### C.1. Calidad del prompt y validación

- [x] **C-001 Revisar el prompt de DeepSeek**
  - Quitar ejemplos ambiguos o contradictorios.
  - Pedir campos de manera más precisa.
  - Incorporar detección de stack y señales si se decide mantenerlas en IA.
  - Prompt rediseñado y versionado como `deepseek_prospect_v2`.
  - Diseño documentado en `docs/10-diseno-prompt-deepseek.md`.
  - **Criterio de cierre:** el prompt está versionado y su salida esperada es consistente.

- [x] **C-002 Validar respuesta de IA con schema**
  - No depender solo de `json.loads`.
  - Rechazar o normalizar respuestas incompletas.
  - Implementado con schema interno Pydantic en `app/services/ai_extractor.py`.
  - Se exige estructura mínima obligatoria y se normalizan valores compatibles (`score`, `confidence_level`, listas y booleanos); si faltan campos clave o la forma es inválida, cae a fallback `Invalid AI Schema`.
  - Cubierto con pruebas en `tests/test_ai_extractor.py`.
  - **Criterio de cierre:** la respuesta del modelo entra al sistema solo si cumple estructura mínima válida.

- [x] **C-003 Propagar todo el contexto útil al extractor**
  - Incluir tecnologías, éxitos previos, métricas ROI y demás señales del vendedor si realmente se van a usar.
  - El armado de `job_context` quedó centralizado en `app/api/jobs.py` para evitar desalineaciones entre payload, modelo y extractor.
  - Ahora también se propagan `target_location`, `target_language` y `target_company_size`, que el prompt `deepseek_prospect_v2` ya consume.
  - Cubierto con prueba de contrato en `tests/test_job_context.py`.
  - **Criterio de cierre:** no se almacenan campos “de adorno” que jamás alimentan la evaluación.

### C.2. Observabilidad de IA

- [x] **C-004 Registrar fallback y fallos de IA**
  - Medir cuántas veces entra la heurística por caída del proveedor o respuesta inválida.
  - El extractor IA ahora emite motivos explícitos de fallback (`missing_api_key`, `invalid_schema`, `provider_error`, etc.) y el engine activa la heurística de forma trazable.
  - Cada prospecto persistido guarda `ai_trace` en `job_prospects.raw_extraction_json`, y el worker escribe eventos `ai_enrichment` en `scraping_logs`.
  - `GET /jobs/{id}` ahora devuelve `ai_summary` con `attempts`, `successes`, `fallbacks`, `fallback_ratio` y desglose por motivo.
  - Cubierto con pruebas en `tests/test_ai_extractor.py` y `tests/test_ai_observability.py`.
  - **Criterio de cierre:** existe trazabilidad clara del ratio de fallback.

- [ ] **C-005 Medir latencia y costo estimado**
  - Registrar duración y, si es posible, tokens aproximados por request.
  - **Criterio de cierre:** el equipo puede estimar costo operativo de usar IA en producción.

### C.3. Scoring híbrido

- [ ] **C-006 Diseñar score base heurístico**
  - Crear una señal local independiente de la IA.
  - Usar factores como hiring, ads, stack, contacto disponible y madurez del sitio.
  - **Criterio de cierre:** el sistema conserva valor aunque la IA falle o se limite.

- [ ] **C-007 Definir fórmula final de score**
  - Decidir si el score final será solo IA, solo heurística o combinación ponderada.
  - **Criterio de cierre:** el score tiene una semántica documentada y estable.

---

## 6. Fase D — Testing y calidad continua (P1)

**Objetivo:** dejar de depender exclusivamente de pruebas manuales.

### D.1. Suite mínima automatizada

- [ ] **D-001 Incorporar `pytest` y estructura de tests**
  - Crear carpeta de tests y fixtures base.
  - **Criterio de cierre:** el repositorio tiene un comando estándar de test automatizado.

- [ ] **D-002 Tests unitarios del parser**
  - Cubrir extracción de metadatos, redes, contacto y links internos.
  - **Criterio de cierre:** cambios en parseo rompen tests si alteran comportamiento esperado.

- [ ] **D-003 Tests del extractor heurístico**
  - Validar detección de tecnologías, hiring signals y revenue heurístico.
  - **Criterio de cierre:** señales básicas quedan protegidas contra regresiones.

- [ ] **D-004 Tests del `upsert` y modelo de persistencia**
  - Verificar deduplicación, relación por job y consistencia histórica.
  - **Criterio de cierre:** no se puede romper la relación job-prospect sin que el test falle.

- [ ] **D-005 Tests de endpoints principales**
  - Cubrir creación de jobs, consulta de estado y consulta de resultados.
  - Mockear servicios externos.
  - **Criterio de cierre:** el contrato HTTP principal está protegido por tests.

### D.2. Validación E2E controlada

- [ ] **D-006 Crear dataset de HTMLs de prueba**
  - Guardar fixtures reales anonimizados o simplificados.
  - **Criterio de cierre:** el pipeline puede probarse sin depender siempre de internet.

- [ ] **D-007 Mantener runner E2E manual, pero no como única validación**
  - Dejar `test_mvp.py` como herramienta auxiliar.
  - **Criterio de cierre:** el proyecto no depende de una prueba manual para validar cambios frecuentes.

---

## 7. Fase E — Observabilidad y operación (P1/P2)

**Objetivo:** facilitar despliegue, monitoreo y troubleshooting.

### E.1. Health checks y readiness

- [ ] **E-001 Separar liveness y readiness**
  - Mantener un endpoint simple de vida.
  - Agregar verificación de conexión a base de datos en readiness.
  - **Criterio de cierre:** el sistema informa si solo está “vivo” o si realmente está listo para procesar jobs.

### E.2. Logging estructurado

- [ ] **E-002 Estandarizar logs**
  - Incluir `job_id`, `domain`, `stage`, `status`, `source_type`.
  - **Criterio de cierre:** buscar un incidente por logs deja de ser una tarea manual confusa.

- [ ] **E-003 Definir niveles de severidad**
  - Diferenciar warning recuperable, error parcial y error crítico.
  - **Criterio de cierre:** los logs permiten priorizar atención sin leer todo a mano.

### E.3. Métricas operativas

- [ ] **E-004 Diseñar métricas base**
  - Jobs creados, jobs completados, jobs fallidos.
  - URLs procesadas, URLs fallidas, ratio de fallback IA.
  - Tiempos promedio por etapa.
  - **Criterio de cierre:** existe un set mínimo de KPIs técnicos del scraper.

---

## 8. Fase F — Mejora funcional del enriquecimiento (P2)

**Objetivo:** subir valor comercial de los prospectos generados.

### F.1. Señales comerciales

- [ ] **F-001 Guardar evidencia de señales**
  - No solo marcar `has_active_ads` o `hiring_signals`, sino registrar por qué.
  - **Criterio de cierre:** cada señal importante tiene rastro verificable.

- [ ] **F-002 Mejorar taxonomía de `generic_attributes`**
  - Evitar que sea un “cajón de sastre”.
  - Definir estructura mínima por rubro o por tipo de señal.
  - **Criterio de cierre:** el campo sigue siendo flexible, pero no caótico.

- [ ] **F-003 Expandir cobertura de tecnologías detectadas**
  - Añadir Wix, Elementor, HubSpot, GTM, Meta Pixel, Shopify apps, etc.
  - **Criterio de cierre:** mejora sensible en la detección del stack real del sitio.

### F.2. Calidad del matching comercial

- [ ] **F-004 Afinar relación entre perfil del vendedor y prospecto**
  - Definir mejor cómo impactan profesión, nicho, pain points, ROI y stack.
  - **Criterio de cierre:** el score refleja mejor intención comercial real y no solo presencia de keywords.

---

## 9. Fase G — Escalabilidad e integración oficial (P3)

**Objetivo:** preparar el paso de MVP local a servicio de producción.

### G.1. Seguridad S2S

- [ ] **G-001 Proteger endpoints internos**
  - Implementar token interno o mecanismo equivalente.
  - **Criterio de cierre:** el servicio no queda expuesto libremente a terceros.

### G.2. Worker real

- [ ] **G-002 Migrar de `BackgroundTasks` a cola persistente**
  - Elegir tecnología de colas.
  - Separar API de ejecución de jobs.
  - **Criterio de cierre:** un reinicio del servidor no destruye trabajo en curso ni pendientes.

### G.3. Integración con NestJS / arquitectura oficial

- [ ] **G-003 Definir patrón final de orquestación**
  - Polling, webhook o cola compartida.
  - **Criterio de cierre:** existe contrato claro entre NestJS y FastAPI.

- [ ] **G-004 Adaptar despliegue a entorno oficial**
  - Supabase o base final.
  - Variables seguras.
  - Migraciones y readiness real.
  - **Criterio de cierre:** el servicio puede desplegarse fuera del entorno local con comportamiento controlado.

---

## 10. Orden sugerido de ejecución

### Sprint 1

- A-001 a A-006
- A-010 a A-012
- B-001
- B-003

### Sprint 2

- A-007 a A-009
- B-004 a B-010
- C-001 a C-004

### Sprint 3

- C-005 a C-007
- D-001 a D-007
- E-001 a E-004

### Sprint 4

- F-001 a F-004
- G-001 a G-004

---

## 11. Definición de cierre del plan

Se puede considerar que este plan está correctamente ejecutado cuando:

- El proyecto arranca limpio desde cero.
- El contrato de la API no tiene contradicciones.
- Un dominio puede participar en múltiples jobs sin corromper historial.
- Los jobs tienen trazabilidad completa.
- El pipeline falla de forma explícita y observable.
- Existen tests automáticos para los puntos críticos.
- El sistema puede operar localmente con confianza y tiene camino claro a producción.
