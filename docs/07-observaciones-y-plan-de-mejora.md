# Observaciones y Plan de Mejora

**Fecha:** 2026-03-10  
**Objetivo:** dejar documentadas las observaciones técnicas, funcionales y operativas detectadas en el MVP para convertir este proyecto en un servicio más confiable, mantenible y escalable.

---

## 1. Resumen ejecutivo

El proyecto tiene una base correcta para validar la idea: separa bien API, scraping, servicios y persistencia, y ya resuelve el flujo principal de crear un job, procesarlo y guardar prospectos.

Sin embargo, hoy el sistema todavía está más cerca de un **MVP de validación** que de un servicio listo para operar sin supervisión. Hay varias inconsistencias entre:

- Lo que la documentación dice que el sistema hace.
- Lo que los modelos y esquemas definen como contrato.
- Lo que efectivamente ejecuta el código.

La mejora no pasa por reescribir todo. Pasa por **cerrar huecos concretos** en cinco áreas:

1. Dependencias y setup reproducible.
2. Consistencia del contrato de datos.
3. Confiabilidad del procesamiento en background.
4. Calidad real del scraping y descubrimiento.
5. Observabilidad, testing y operación.

---

## 2. Dependencias y entorno

### Observación

La integración con DeepSeek usa el SDK compatible de OpenAI, pero la dependencia `openai` no está declarada en `requirements.txt`.

### Por qué importa

Esto rompe la reproducibilidad del proyecto. En una instalación limpia, aunque alguien siga el quickstart y ejecute `pip install -r requirements.txt`, la importación del servicio de IA puede fallar. Eso significa que el proyecto depende de estado manual del entorno y no solo del repositorio.

### Mejora recomendada

- Agregar explícitamente `openai` a `requirements.txt`.
- Revisar si todas las librerías actuales se usan realmente.
- Congelar una estrategia mínima de versiones para evitar drift entre entornos.
- Validar el arranque del servidor en una instalación limpia como parte del checklist del proyecto.

### Acción concreta sugerida

1. Añadir la dependencia faltante.
2. Probar `pip install -r requirements.txt`.
3. Levantar `uvicorn app.main:app --reload` en un entorno limpio.
4. Dejar documentado el resultado esperado.

---

## 3. Contrato de datos y consistencia entre capas

### Observación

Hay campos que no están alineados entre modelo, schema, documentación y salida real del servicio.

El caso más claro es `confidence_level`:

- En algunos lugares está tratado como etiqueta semántica (`low`, `medium`, `high`).
- En otros aparece como número decimal (`0.0` a `1.0`).
- En base de datos está guardado como string.

### Por qué importa

Cuando el contrato cambia según la capa, aparecen problemas silenciosos:

- Datos inconsistentes en la tabla.
- Serialización ambigua en la API.
- Documentación que engaña al integrador.
- Bugs difíciles de detectar porque “a veces funciona”.

### Mejora recomendada

Definir una única verdad para cada campo crítico.

#### Opción A evaluada: contrato numérico total

- `score`: `float` entre `0.0` y `1.0`
- `confidence_level`: `float` entre `0.0` y `1.0`

Ventaja: es más útil para ranking, ordenamiento y reglas futuras.

#### Opción B evaluada: contrato mixto

- `score`: `float`
- `confidence_level`: enum `low | medium | high`

Ventaja: es más legible para consumidores humanos.

### Recomendación

La opción más sólida es:

- Mantener `score` como `float`.
- Convertir `confidence_level` en enum semántico derivado del score o de otra métrica.

Así el sistema conserva señal cuantitativa y también un resumen legible.

### Decisión aplicada

Desde la estabilización inicial del contrato:

- `score` se define como `float` entre `0.0` y `1.0`.
- `confidence_level` se define como enum semántico: `low | medium | high`.
- El payload de creación de jobs ya no inyecta defaults de negocio implícitos si el consumidor omite contexto comercial.

### Otros problemas de contrato

- El payload tenía defaults muy opinionados (`Editor de Video`, `YouTubers`, `España`). Eso contaminaba resultados cuando el consumidor olvidaba mandar campos.
- El `job_context` no propaga todo lo que el modelo captura. Se guardan datos del vendedor que luego no se usan efectivamente en la evaluación.
- Algunos documentos describen respuestas y comportamientos más “cerrados” de lo que hoy implementa el código.

### Acción concreta sugerida

1. Definir un contrato oficial por escrito para cada campo expuesto.
2. Ajustar SQLAlchemy, Pydantic y documentación al mismo contrato.
3. Eliminar defaults de negocio innecesarios o reemplazarlos por `None`.
4. Validar con tests de serialización que la API responde exactamente lo documentado.

---

## 4. Modelo de persistencia

### Observación

Hoy `prospects.domain` es único a nivel global y cada prospecto tiene un solo `job_id`.

### Por qué importa

Esto simplifica la deduplicación, pero introduce un problema estructural importante:

- Si el mismo dominio aparece en dos jobs distintos, el `upsert` actual actualiza el registro existente.
- Como `job_id` también se actualiza, el prospecto queda asociado al último job.
- Eso hace que jobs anteriores puedan “perder” resultados o mostrar menos datos de los que realmente procesaron.

En otras palabras: el sistema mezcla dos conceptos distintos en una sola tabla:

1. La **entidad canónica** del prospecto.
2. La **participación de ese prospecto dentro de un job**.

### Mejora recomendada

Separar modelo canónico de modelo transaccional.

#### Diseño sugerido

- `prospects`: entidad única por dominio.
- `job_prospects` o `scraping_job_results`: tabla pivote entre `job_id` y `prospect_id`.
- En esa tabla pivote guardar score, señales, source_url, timestamps de descubrimiento y cualquier dato contextual específico del job.

### Beneficios

- Un dominio puede aparecer en muchos jobs sin sobrescribir historial.
- La deduplicación sigue existiendo.
- Cada job conserva sus resultados reales.
- La analítica posterior mejora muchísimo.

### Acción concreta sugerida

1. Diseñar tabla pivote.
2. Migrar consultas de resultados a esa tabla.
3. Dejar `prospects` como repositorio canónico.
4. Reservar los datos “por corrida” para la relación job-prospect.

---

## 5. Ciclo de vida del job

### Observación

Este punto ya quedó corregido en la implementación actual: el worker actualiza `started_at`, `finished_at`, contadores operativos y escribe eventos en `scraping_logs`.

### Estado resuelto

- El job deja timestamps útiles al pasar a `running`, `completed` o `failed`.
- La API resume el estado con métricas reales de procesamiento.
- El parámetro muerto `db_url` fue eliminado del worker.
- El sistema deja traza persistente por job en `scraping_logs`.

### Por qué importa

Si el servicio corre en background, el job es el centro del control operativo. Si el job no deja trazabilidad fuerte, luego no puedes responder preguntas básicas:

- ¿Cuándo empezó?
- ¿Cuándo terminó?
- ¿Cuántas URLs procesó realmente?
- ¿Cuántas fallaron?
- ¿Qué parte del pipeline rompió?

### Implementación aplicada

Al convertir un job en `running`, se registra `started_at`.  
Al terminar, se registra `finished_at`.  
Si falla, se guarda también el error resumido y el contexto de la URL afectada cuando aplica.

### Resultado actual

1. Se registran timestamps al iniciar y finalizar.
2. Se cuentan `procesadas`, `guardadas`, `fallidas`, `omitidas`.
3. Se guarda motivo resumido de fallo por URL en `scraping_logs`.
4. `GET /jobs/{id}` ya resume el estado; sigue pendiente un endpoint específico de logs.

---

## 6. Procesamiento en background

### Observación

Para MVP, usar `BackgroundTasks` es razonable. El propio repositorio ya lo plantea como solución temporal.

### Limitación real

`BackgroundTasks` sirve para validar flujo, pero no es un sistema de ejecución robusto:

- Si se reinicia el proceso de FastAPI, se pierden trabajos en curso.
- No hay reintentos reales.
- No hay cola persistente.
- No hay control serio de concurrencia.
- No hay aislamiento claro entre API y workers.

### Mejora recomendada

Mantener `BackgroundTasks` solo mientras el uso sea manual o muy pequeño. En cuanto el servicio procese volumen real, migrar a workers independientes.

### Opciones razonables

- Redis + RQ
- Redis + Celery
- BullMQ del lado NestJS y Python como worker especializado

### Recomendación pragmática

Si el backend principal ya vive en NestJS, tiene sentido evaluar si la coordinación de colas debe quedar allí y dejar a Python concentrado en scraping, parsing y scoring.

---

## 7. Descubrimiento de URLs y calidad del scraping

### Observación

Este punto ya quedó corregido: el buscador intenta usar DDG HTML y, si falla, ya no inyecta dominios hardcodeados en silencio.

### Por qué importa

Ese fallback hace que el sistema parezca “funcionar” incluso cuando la búsqueda real fracasó. Eso es peligroso porque:

- Distorsiona pruebas.
- Distorsiona métricas de calidad.
- Hace más difícil depurar anti-bot o bloqueos de red.
- Puede devolver prospectos que no tienen relación con la intención del usuario.

### Estado resuelto

No se mezcla más modo demo con modo real.

### Implementación aplicada

- Si la búsqueda real falla: la API responde con error claro.
- Si se quiere mantener modo demo: se controla con `DEMO_MODE=true`.
- Cualquier resultado de fallback demo queda etiquetado como `source_type=mock_search`.

### Limitaciones adicionales del scraping actual

- Se scrapea esencialmente la página inicial y no una exploración más rica del sitio.
- Ya existe crawling limitado de páginas clave (`contact`, `about`, `nosotros`, `equipo`, `careers`) sobre el mismo dominio.
- La normalización de URLs internas ya usa `urljoin`; sigue pendiente ampliar ese crawling sin convertirlo en un crawler profundo.

### Resultado actual

1. Se quitó el fallback silencioso.
2. Se implementó un modo demo explícito.
3. Los resultados del job exponen `source_type`, `discovery_method`, `search_query_snapshot` y `rank_position`.
4. La normalización de links internos ya no concatena URLs manualmente.
5. El scraper ahora visita homepage + hasta 3 páginas clave para mejorar contacto y señales sin hacer crawling profundo.
4. Sigue pendiente mejorar normalización de links internos.

---

## 8. Robustez HTTP y seguridad

### Observación

Este punto ya quedó corregido: el cliente HTTP vuelve a validar TLS por defecto.

### Estado resuelto

- Ya no se aceptan certificados inválidos por defecto.
- Se recuperó una capa básica de confianza sobre los datos descargados.
- El bypass quedó aislado a debugging explícito y deja warning operativo.

### Implementación aplicada

- `HTTP_VERIFY_TLS=true` por defecto.
- Si se necesita bypass puntual, se usa `HTTP_VERIFY_TLS=false`.
- El cliente emite un warning explícito cuando TLS se desactiva.

### Resultado actual

- Los errores HTTP y de red ya salen tipificados como `timeout`, `dns_error`, `tls_error`, `http_403`, `http_429`, `http_5xx` u otros equivalentes.
- `scraping_logs` guarda `stage`, `error_type`, `status_code` y `retryable` por URL fallida.
- El cliente HTTP ya aplica retries con backoff exponencial solo sobre fallos recuperables.
- `403`, `DNS` y `TLS` no se reintentan; `timeout`, `429`, `5xx` y algunos errores de red sí.

### Pendiente relacionado

- Delays más inteligentes.
- Ajustar la política exacta de qué errores son recuperables vs no recuperables.

---

## 9. Integración con IA

### Observación

La integración con DeepSeek es útil para el MVP, pero todavía necesita más estructura para ser confiable.

### Problemas principales

- El prompt pide un JSON muy estricto, pero mezcla ejemplo de JSON con comentarios semánticos dentro del bloque, algo que conceptualmente no es JSON válido.
- No hay una validación fuerte de la respuesta más allá del `json.loads`.
- Parte del contexto de negocio que se captura no siempre llega al prompt final.
- La caída al modo heurístico es correcta como idea, pero falta medir cuándo, cuánto y por qué se activa.

### Mejora recomendada

- Validar la salida contra un schema explícito.
- Loggear respuestas truncadas y sanitizadas para debugging.
- Versionar el prompt.
- Medir costo, latencia, ratio de fallback, score promedio y tasa de respuestas inválidas.

### Recomendación de diseño

La IA debería comportarse como un componente observable, no como una caja negra.  
Eso significa registrar:

- modelo usado,
- tokens aproximados,
- duración,
- resultado válido/inválido,
- causa de fallback.

---

## 10. Cobertura funcional del extractor

### Observación

El sistema detecta algunas señales útiles, pero todavía hay oportunidades claras de aumentar valor con poco costo técnico.

### Mejoras de corto plazo

- Buscar emails en texto visible además de `mailto:`.
- Detectar páginas de contacto reales.
- Detectar formularios.
- Guardar más de un canal de contacto en estructura normalizada.
- Separar mejor señales comerciales de datos descriptivos.

### Mejoras de mediano plazo

- Añadir score heurístico local independiente de la IA.
- Cruzar señales de contratación, ads, stack y madurez del sitio.
- Guardar evidencia de cada señal detectada.

Esto permitiría que la IA complemente, pero no monopolice, la calidad del enriquecimiento.

---

## 11. Testing y calidad

### Observación

Hoy existe un script manual de validación E2E, pero no una suite automatizada real.

### Por qué importa

Sin tests automáticos, cada cambio importante obliga a validar a mano y aumenta el riesgo de romper:

- el contrato API,
- el parsing,
- el upsert,
- la compatibilidad con migraciones.

### Mínimo recomendable

- Tests unitarios para parser, extractor heurístico y utilidades.
- Tests de integración para endpoints principales.
- Tests de persistencia para el `upsert`.
- Tests de regresión para payloads y respuesta de schemas.

### Acción concreta sugerida

1. Incorporar `pytest`.
2. Crear fixtures de HTML reales y simplificados.
3. Mockear la llamada a DeepSeek.
4. Validar que un job pase por `pending -> running -> completed/failed`.

---

## 12. Observabilidad y operación

### Observación

El proyecto usa logging básico, pero todavía no tiene una estrategia completa de observabilidad.

### Faltantes importantes

- Logs estructurados con `job_id`, `domain`, `stage`.
- Métricas de éxito/fallo por etapa.
- Health checks más útiles que el simple “estoy vivo”.
- Diferenciación entre readiness y liveness.

### Mejora recomendada

Agregar al menos:

- `GET /health/live`
- `GET /health/ready`
- verificación de conexión a base de datos
- métricas simples de jobs

Esto facilita despliegue, debugging y operación diaria.

---

## 13. Documentación

### Observación

La documentación es buena en intención, pero algunas partes ya no están totalmente alineadas con el código real.

### Ejemplos típicos de desalineación

- Se afirma un estado de funcionamiento más sólido del que hoy se garantiza.
- Algunos nombres de archivo o comportamientos no coinciden exactamente.
- La documentación mezcla comportamiento real con comportamiento deseado.

### Mejora recomendada

Separar claramente:

- **estado actual comprobado**, y
- **estado objetivo / roadmap**

Cuando esos dos planos se mezclan, el repo parece más maduro de lo que realmente es.

---

## 14. Plan de priorización sugerido

### Prioridad 0: estabilizar base técnica

1. Corregir dependencias y arranque reproducible.
2. Unificar contrato de `score` y `confidence_level`.
3. Eliminar el fallback silencioso de DDG o aislarlo en modo demo.
4. Revisar el modelo de persistencia para no perder historial entre jobs.

### Prioridad 1: mejorar confiabilidad del pipeline

1. Reforzar manejo de errores HTTP.
2. Mejorar follow-up de páginas internas clave.
3. Agregar tests unitarios e integración.
4. Exponer logs y métricas básicas por job.

### Prioridad 2: preparar escalabilidad

1. Migrar de `BackgroundTasks` a workers reales.
2. Separar claramente API de ejecución.
3. Añadir control de concurrencia y reintentos.

### Prioridad 3: mejorar inteligencia comercial

1. Refinar score híbrido heurístico + IA.
2. Guardar evidencia de señales detectadas.
3. Afinar segmentación por nicho, stack y señales de compra.

---

## 15. Conclusión

La base del proyecto es buena. No hay señales de que haya que tirar el trabajo hecho.  
Sí hay señales claras de que la siguiente etapa debe enfocarse menos en agregar features nuevas y más en:

- cerrar inconsistencias,
- endurecer contratos,
- mejorar trazabilidad,
- y separar mejor lo que hoy es demo de lo que debe ser comportamiento real.

Si esas mejoras se aplican en orden, este repo puede pasar de MVP prometedor a servicio técnicamente defendible sin una reescritura total.

---

## 16. Backlog ejecutable asociado

Para llevar estas observaciones a ejecución concreta, revisar:

- [backlog/plan-detallado-estabilizacion-y-mejora.md](backlog/plan-detallado-estabilizacion-y-mejora.md)

Ese documento traduce esta revisión en fases, tareas, prioridad, criterio de cierre y orden sugerido de implementación.
