# Estado Actual, FODA y Pendientes

**Fecha:** 2026-03-11  
**Objetivo:** dejar una lectura ejecutiva del estado del sistema, qué se hizo, qué falta y cuáles son los principales riesgos y oportunidades.

---

## 1. Resumen ejecutivo

El servicio ya no está en estado de MVP “ciego”. Hoy tiene:

- contrato API más estable;
- persistencia por job y por prospecto;
- discovery con pre-ranking y exclusiones tempranas;
- quality gate con geo strict mejorado;
- clasificación comercial explícita de tipo de entidad;
- decisión comercial separada de calidad técnica;
- ahorro de IA mediante gate heurístico;
- observabilidad por job, logs, métricas operativas y métricas comerciales;
- tests automáticos de discovery, parsing, quality, IA y métricas.

En términos prácticos, el sistema ya puede:

- crear jobs con objetivo de capturar aceptados;
- intentar recuperar recall con batches y reapertura de discovery;
- explicar por qué un job terminó vacío;
- auditar ruido editorial/directorios sin ir a SQL manualmente;
- distinguir negocio real de medios, listados y agregadores;
- medir precision de `accepted_target`, contactos inconsistentes y telefonos falsos filtrados.

---

## 2. Cambios importantes ya implementados

### API y contrato

- `POST /api/v1/jobs/scrape` ya no inyecta defaults comerciales silenciosos.
- `GET /api/v1/jobs/{id}` ahora expone `ai_summary`, `quality_summary`, `capture_summary` y `operational_summary`.
- `GET /api/v1/jobs/{id}/results` filtra por `quality` y expone campos comerciales, taxonomía y normalización de ubicación.
- `GET /api/v1/jobs/{id}/logs` expone trazabilidad operativa.
- `GET /api/v1/jobs/metrics/operational` resume recall y precisión agregada.
- `GET /api/v1/jobs/metrics/commercial` resume precision comercial y calidad de contacto.

### Captura y recall

- separación entre `target_accepted_results` y `max_candidates_to_process`;
- ratio inicial objetivo/candidatos;
- procesamiento por tandas;
- reapertura incremental de discovery;
- queries canónicas y queries de reintento;
- uso de directorios como seed para resolver sitio oficial;
- exclusiones tempranas persistidas en logs.

### Calidad y enriquecimiento

- parser estructurado con JSON-LD, CTAs, booking, pricing, mapas y canales de contacto;
- quality gate con `accepted`, `needs_review`, `rejected`;
- clasificador determinístico de entidad con evidencia y confianza;
- `acceptance_decision` separada de `quality_status`;
- geo strict reforzado con `areaServed`, `PostalAddress`, TLD y prefijos;
- normalización de `location`, `raw_location_text`, `parsed_location` y componentes geo;
- separación entre `observed_signals` e `inferred_opportunities`;
- taxonomía cerrada de negocio;
- IA opcional y condicionada por calidad;
- métricas de IA y fallback.

### Testing

- fixtures SERP offline;
- fixtures HTML comerciales para casos problemáticos reales;
- tests para query expansion, ranking y exclusiones;
- tests para parser y quality;
- tests para observabilidad, taxonomía y métricas operativas/comerciales.

---

## 3. Estado funcional actual

### Lo que está fuerte hoy

- discovery bastante más limpio que el MVP inicial;
- mejor trazabilidad de por qué un candidato entra o sale;
- menor ambigüedad entre “job completado” y “job útil”;
- menor dependencia de IA para clasificación básica;
- documentación de endpoints ya usable por integradores;
- contrato comercial visible y auditable para consumidores de API.

### Lo que todavía no es producción plena

- el worker sigue usando `BackgroundTasks`;
- no hay cola persistente ni reintentos fuera del proceso;
- no hay autenticación interna fuerte en los endpoints;
- la capa de discovery sigue apoyándose solo en DDG;
- el cache IA sigue local al proceso.

---

## 4. Pendientes principales

### Pendientes técnicos

- migrar background processing a workers persistentes;
- agregar seguridad server-to-server para los endpoints;
- persistir cache IA compartido;
- endurecer manejo de anti-bot para sitios más hostiles;
- ampliar catálogo de señales geo y compatibilidad internacional;
- incorporar métricas históricas persistidas, no solo cálculo “on demand”.

### Pendientes de producto

- definir qué hacer con `needs_review` desde el consumidor;
- decidir umbrales por nicho para ajustar mejor recall y costo;
- establecer estrategia de fuentes alternativas a DDG;
- definir cómo se consumen estos resultados en CRM/outreach downstream.

### Pendientes de operación

- checklist de despliegue y monitoreo productivo;
- estrategia de rotación de IP/proxy si sube el volumen;
- definición de límites de concurrencia;
- observabilidad externa tipo Prometheus/Grafana o equivalente.

---

## 5. Fortalezas

- arquitectura modular clara entre API, discovery, parser, quality, IA y persistencia;
- contrato visible bastante mejor alineado con el runtime;
- trazabilidad fuerte por job;
- bajo costo incremental de IA gracias al gate determinístico;
- buena base para CRM y scoring por contexto;
- suite de tests que cubre puntos críticos del pipeline;
- mejor honestidad semántica entre lead real, relacionado y ruido no objetivo.

---

## 6. Oportunidades

- sumar más fuentes de discovery sin rediseñar todo el pipeline;
- convertir `operational_summary` en tablero operativo real;
- convertir `metrics/commercial` en tablero histórico persistido;
- usar historial por job para ajustar ratios y batches por nicho;
- incorporar un modo de review humana sobre `needs_review`;
- llevar la capa de scoring a un sistema más orientado a conversión comercial.

---

## 7. Debilidades

- dependencia actual de `BackgroundTasks`;
- discovery todavía concentrado en una sola fuente pública principal;
- algunas heurísticas geo y comerciales siguen siendo aproximaciones;
- falta de seguridad interna obligatoria en endpoints;
- métricas agregadas se calculan consultando jobs recientes, no desde una tabla de analítica dedicada.

---

## 8. Amenazas

- cambios en DuckDuckGo HTML o bloqueos anti-bot;
- variabilidad de calidad de sitios web del mercado objetivo;
- costos crecientes si la llamada a IA deja de estar bien gateada;
- aumento de volumen sin migrar a workers persistentes;
- falsa sensación de precisión si el consumidor solo mira `results` y no los summaries.

---

## 9. Qué revisar primero según el objetivo

Si quieres integrar el servicio:

1. [05-api-y-reglas.md](05-api-y-reglas.md)
2. [06-quickstart.md](06-quickstart.md)
3. [06-estado-del-sistema.md](06-estado-del-sistema.md)

Si quieres seguir fortaleciendo scraping/calidad:

1. [11-mapa-de-modulos-y-cambios-recientes.md](11-mapa-de-modulos-y-cambios-recientes.md)
2. [clasificacion-comercial/README.md](clasificacion-comercial/README.md)
3. [12-plan-refinamiento-captura-y-recall.md](12-plan-refinamiento-captura-y-recall.md)
4. [07-observaciones-y-plan-de-mejora.md](07-observaciones-y-plan-de-mejora.md)

Si quieres planificar roadmap:

1. este documento;
2. [docs/backlog/plan-detallado-estabilizacion-y-mejora.md](backlog/plan-detallado-estabilizacion-y-mejora.md);
3. [14-plan-clasificacion-entidad-y-normalizacion-comercial.md](14-plan-clasificacion-entidad-y-normalizacion-comercial.md).
