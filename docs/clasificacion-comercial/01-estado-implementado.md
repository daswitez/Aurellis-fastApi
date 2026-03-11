# Estado Implementado `I-001` a `I-020`

**Fecha de consolidacion:** 2026-03-11

Este documento resume que cambio realmente en runtime, persistencia, API y tests para cada item del plan comercial.

---

## 1. Resumen ejecutivo

El pipeline ya no trata todo hallazgo semantico como si fuera un lead directo.

Ahora separa:

- tipo de entidad;
- decision comercial;
- calidad tecnica;
- observaciones vs inferencias;
- ubicacion visible normalizada vs validacion geografica;
- negocio objetivo vs contexto relacionado;
- ruido telefonico filtrado vs telefono persistido.

---

## 2. Matriz de implementacion

| Item | Estado | Cambio real |
|------|--------|-------------|
| `I-001` | OK | Taxonomia cerrada para `entity_type_detected` |
| `I-002` | OK | Clasificador deterministico por dominio, path, title, snippet, schema y navegacion |
| `I-003` | OK | Persistencia de `entity_type_detected`, confianza y evidencia |
| `I-004` | OK | `is_target_entity` como decision explicita |
| `I-005` | OK | Penalizacion fuerte o rechazo de directorios, medios, agregadores y articulos |
| `I-006` | OK | Separacion entre `quality_status` y `acceptance_decision` |
| `I-007` | OK | Rebalanceo del score con peso mayor a identidad empresarial |
| `I-008` | OK | Consistencia de email por dominio del sitio |
| `I-009` | OK | Filtrado de telefonos falsos, fechas y secuencias |
| `I-010` | OK | `validated_location` deja de ser texto crudo de fallback |
| `I-011` | OK | `raw_location_text` separado de `location` visible |
| `I-012` | OK | `parsed_location`, `city`, `region`, `country`, `postal_code` |
| `I-013` | OK | `location` visible normalizada con precedencia limpia |
| `I-014` | OK | Separacion entre `observed_signals` e `inferred_opportunities` |
| `I-015` | OK | Lenguaje hipotetico obligatorio para oportunidades inferidas |
| `I-016` | OK | Taxonomia cerrada de negocio: `taxonomy_top_level` y `taxonomy_business_type` |
| `I-017` | OK | Heuristica, IA y engine convergen a la misma taxonomia final |
| `I-018` | OK | Fixtures HTML reproducibles para casos problematicos reales |
| `I-019` | OK | KPIs agregados via `GET /api/v1/jobs/metrics/commercial` |
| `I-020` | OK | Rollout por capas explicitado en API y docs |

---

## 3. Donde vive cada bloque

### Clasificacion de entidad

- `app/services/entity_classifier.py`
- `app/services/prospect_quality.py`

### Decision comercial y score final

- `app/services/prospect_quality.py`
- `app/services/scoring.py`

### Contacto, ubicacion y parser

- `app/scraper/parser.py`
- `app/services/prospect_quality.py`
- `app/scraper/engine.py`

### Observacion vs inferencia

- `app/services/commercial_insights.py`
- `app/services/heuristic_extractor.py`
- `app/services/ai_extractor.py`

### Taxonomia de negocio

- `app/services/business_taxonomy.py`
- `app/scraper/engine.py`

### Persistencia y API

- `app/models.py`
- `app/services/db_upsert.py`
- `app/api/schemas.py`
- `app/api/jobs.py`

### Tests, fixtures y metricas

- `tests/test_entity_classifier.py`
- `tests/test_parser_and_quality.py`
- `tests/test_heuristic_extractor.py`
- `tests/test_ai_extractor.py`
- `tests/test_ai_observability.py`
- `tests/test_business_taxonomy.py`
- `tests/test_commercial_fixtures.py`
- `tests/test_commercial_metrics.py`
- `tests/fixtures/commercial/`

---

## 4. Campos visibles que nacen de este plan

Por resultado:

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

Por metricas agregadas:

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

---

## 5. Documentos relacionados

- [02-logica-y-decisiones.md](02-logica-y-decisiones.md)
- [03-contrato-y-metricas.md](03-contrato-y-metricas.md)
- [04-fixtures-tests-y-rollout.md](04-fixtures-tests-y-rollout.md)
- [../05-api-y-reglas.md](../05-api-y-reglas.md)
- [../14-plan-clasificacion-entidad-y-normalizacion-comercial.md](../14-plan-clasificacion-entidad-y-normalizacion-comercial.md)
