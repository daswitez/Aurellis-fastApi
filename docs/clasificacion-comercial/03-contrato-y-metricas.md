# Contrato y Metricas

Este documento aterriza que ve un consumidor de API despues de la implementacion comercial.

---

## 1. Resultados por job

`GET /api/v1/jobs/{job_id}/results` expone ahora campos comerciales y de normalizacion que antes no existian o no estaban estabilizados.

### Campos clave

- `acceptance_decision`
- `entity_type_detected`
- `entity_type_confidence`
- `entity_type_evidence`
- `is_target_entity`
- `contact_consistency_status`
- `primary_email_confidence`
- `primary_phone_confidence`
- `location`
- `raw_location_text`
- `parsed_location`
- `city`
- `region`
- `country`
- `postal_code`
- `validated_location`
- `observed_signals`
- `inferred_opportunities`
- `taxonomy_top_level`
- `taxonomy_business_type`

### Lectura recomendada

- `quality_status` responde si es tecnicamente usable.
- `acceptance_decision` responde si comercialmente debe tratarse como lead principal, relacionado o descartado.
- `entity_type_detected` explica por que el sistema lo considera negocio real, directorio, medio, articulo, etc.

---

## 2. Semantica de los campos

### `quality_status`

- `accepted`
- `needs_review`
- `rejected`

### `acceptance_decision`

- `accepted_target`
- `accepted_related`
- `rejected_directory`
- `rejected_media`
- `rejected_article`
- `rejected_low_confidence`

### `entity_type_detected`

- `direct_business`
- `directory`
- `aggregator`
- `marketplace`
- `media`
- `blog_post`
- `association`
- `agency`
- `consultant`
- `unknown`

### `contact_consistency_status`

- `consistent`
- `inconsistent`
- `unknown`

### `location_match_status` y `language_match_status`

- `match`
- `mismatch`
- `unknown`

---

## 3. Metricas operativas vs metricas comerciales

La API ahora separa dos vistas agregadas:

### `GET /api/v1/jobs/metrics/operational`

Sirve para medir:

- jobs completados sin aceptados;
- acceptance rate;
- ruido de discovery por articulos y directorios;
- candidatos por aceptado.

### `GET /api/v1/jobs/metrics/commercial`

Sirve para medir:

- `accepted_target` reales;
- `accepted_related`;
- rechazos de no objetivo;
- contactos inconsistentes;
- telefonos falsos filtrados;
- precision de `accepted_target`;
- etapa de rollout aplicada.

---

## 4. Campos del endpoint comercial

`GET /api/v1/jobs/metrics/commercial` expone:

- `total_jobs`
- `total_results_processed`
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

### Interpretacion

- si baja `accepted_non_target_rate`, estan entrando menos relacionados como aceptados;
- si sube `accepted_target_precision`, la clasificacion comercial esta mas limpia;
- si sube `false_phone_filtered_count`, el parser esta detectando mas ruido numerico antes de persistirlo;
- si sube `inconsistent_contact_count`, hay mas dominios o emails sospechosos en el conjunto procesado.

---

## 5. Persistencia asociada

La implementacion persiste estos datos entre `Prospect` y `JobProspect`.

### Canonico por dominio

En `Prospect` quedan:

- ubicacion visible;
- ubicacion parseada;
- taxonomia de negocio;
- tipo de entidad;
- contacto principal;
- senales observadas e inferidas.

### Contextual por job

En `JobProspect` quedan:

- `quality_status`
- `rejection_reason`
- `acceptance_decision`
- `contact_consistency_status`
- confianza de contacto;
- evidencia de entidad;
- taxonomia por corrida;
- `evidence_json`
- `raw_extraction_json`

Esto permite que el mismo dominio exista como entidad canonica y al mismo tiempo deje trazabilidad distinta por job.

---

## 6. Compatibilidad

El cambio se hizo sin romper el contrato principal de jobs.

Se mantiene:

- `POST /api/v1/jobs/scrape`
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/jobs/{job_id}/logs`
- `GET /api/v1/jobs/metrics/operational`

Se agrega:

- `GET /api/v1/jobs/metrics/commercial`

Y se enriquecen:

- `GET /api/v1/jobs/{job_id}/results`

---

## 7. Documentos relacionados

- [../05-api-y-reglas.md](../05-api-y-reglas.md)
- [01-estado-implementado.md](01-estado-implementado.md)
- [02-logica-y-decisiones.md](02-logica-y-decisiones.md)
- [04-fixtures-tests-y-rollout.md](04-fixtures-tests-y-rollout.md)
