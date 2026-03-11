# Prioridades y Fases

**Objetivo:** ordenar la siguiente fase de trabajo con dependencias claras y sin mezclar mejoras de alto retorno con ideas todavia prematuras.

---

## 1. Tesis de priorizacion

No conviene empezar por ML, snapshots visuales o nuevas senales de madurez si el motor todavia confunde:

- negocio directo vs agregador/directorio;
- taxonomia final vs taxonomias duplicadas;
- confianza de contacto vs validez real del dato;
- fit comercial vs calidad de datos.

Primero hay que estabilizar el juicio base del motor.

---

## 2. Fases recomendadas

### Fase 1. Precision de entidad

Foco:

- bajar falsos `accepted_target`;
- endurecer rechazo de directorios, agregadores y media;
- crear salida segura para ambiguedad.

Entregables:

- `rejected_aggregator`
- `rejected_ambiguous_entity`
- reglas nuevas de `directory` / `aggregator` / `media`
- criterio de empate para no promover target dudoso

Motivo de prioridad:

- es la mejora con mayor impacto comercial inmediato;
- reduce ruido en datasets, dashboards y revisiones manuales;
- baja trabajo inutil del resto del pipeline.

### Fase 2. Taxonomia unica

Foco:

- una sola fuente de verdad taxonomica;
- eliminar duplicacion entre root fields y `generic_attributes`.

Entregables:

- estructura `taxonomy.top_level`
- `taxonomy.industry`
- `taxonomy.business_type`
- `taxonomy.confidence`
- `taxonomy.evidence`

Motivo de prioridad:

- sin esto, cualquier filtro o score posterior se rompe por inconsistencia;
- simplifica API, persistencia y UI.

### Fase 3. Calidad dura de datos

Foco:

- validacion fuerte de telefono;
- mejor validacion de email;
- parsing conservador de ubicacion;
- inteligencia local por postcode cuando aplique.

Entregables:

- `phone_validity_status`
- `email_validity_status`
- `contact_validity_status`
- `phone_country_inferred`
- `street_address`
- `province_or_state`
- `location_parse_confidence`

Motivo de prioridad:

- un buen target con data mala sigue siendo mala salida para outreach;
- mejora directamente la confianza del usuario final.

### Fase 4. Scores separados y readiness

Foco:

- dejar de mezclar fit del negocio con calidad del dato;
- medir readiness accionable.

Entregables:

- `target_fit_score`
- `data_quality_score`
- `opportunity_score`
- `outreach_readiness_score`
- `outreach_ready`
- `blocking_reasons`

Motivo de prioridad:

- permite ordenar leads mejor;
- destraba futuros tableros y flujos de CRM/outreach.

### Fase 5. Gaps, evidencia y explicabilidad

Foco:

- `detected_gaps`;
- `signal_evidence`;
- `evidence_snippets`;
- `page_roles_detected`.

Motivo de prioridad:

- hace al sistema auditable;
- mejora debugging y confianza del consumidor;
- prepara terreno para UI y review humana.

### Fase 6. Enrichment avanzado

Foco:

- `business_model_detected`;
- chain / multi-location detection;
- social extraction mas robusta;
- digital maturity signals;
- schema coverage mas rica.

Motivo de prioridad:

- agrega valor comercial extra;
- pero depende de tener estable la base de precision y data quality.

### Fase 7. Calibracion y escalado

Foco:

- dataset etiquetado;
- metricas historicas;
- snapshots de debug;
- pipeline por etapas mas explicito.

Motivo de prioridad:

- solo tiene sentido cuando la taxonomia, la salida y las metricas ya son estables;
- sigue siendo una fase sin ML obligatorio.

### Fase 8. Exploracion de muy largo plazo

Foco:

- evaluar si un enfoque hibrido realmente agrega valor;
- probarlo solo como ayuda de ranking o desempate;
- no usarlo como reemplazo del motor deterministico base.

Entregables:

- benchmark contra reglas actuales;
- criterios de adopcion;
- decision explicita de "vale la pena" o "no vale la pena".

Motivo de prioridad:

- es opcional;
- depende de tener dataset confiable, taxonomia estable y metricas historicas suficientes;
- hoy no es el cuello de botella principal.

---

## 3. Lista maestra de prioridades

### Prioridad 1

Corregir directorios/agregadores/media.

### Prioridad 2

Unificar taxonomia.

### Prioridad 3

Validacion fuerte de contacto.

### Prioridad 4

Separar score global en sub-scores.

### Prioridad 5

Agregar `detected_gaps` y `blocking_reasons`.

### Prioridad 6

Mejorar parsing de ubicacion.

### Prioridad 7

Guardar evidencia y roles de pagina.

### Prioridad 8

Agregar business model, chain detection y digital maturity.

### Prioridad 9

Preparar dataset, calibracion y observabilidad para decisiones futuras.

### Prioridad 10

Explorar ML solo a muy largo plazo y solo si los datos muestran que hace falta.

---

## 4. Lo que no conviene hacer primero

- no empezar por ML antes de tener dataset etiquetado;
- no asumir que ML va a arreglar errores que hoy son de reglas y taxonomia;
- no agregar decenas de nuevas senales si `entity_type_detected` sigue fallando;
- no redisenar el objeto final sin definir antes taxonomia y scores base;
- no abrir demasiadas features UI si todavia falta evidencia explicable.

---

## 5. Criterio de exito global

Este plan va bien encaminado si se logra:

- menos `accepted_target` incorrectos;
- taxonomia sin duplicados ni contradicciones;
- contacto y ubicacion con estados de validez claros;
- leads con readiness accionable;
- evidencia suficiente para explicar cada decision;
- mejor priorizacion en dashboards y CRM.
