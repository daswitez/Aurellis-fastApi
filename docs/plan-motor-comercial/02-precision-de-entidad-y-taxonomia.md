# Precision de Entidad y Taxonomia

**Objetivo:** corregir el principal problema comercial actual: el motor sigue aceptando como target sitios que en realidad son directorios, comparadores o agregadores, y ademas mantiene taxonomias inconsistentes.

---

## 1. Problema principal

Los casos `todoestetica.com` y `comparaclinic.com` muestran que el sistema todavia puede producir:

- `entity_type_detected = direct_business`
- `acceptance_decision = accepted_target`

cuando la evidencia sugiere mas bien:

- `directory`
- `aggregator`
- `accepted_related`
- `rejected_aggregator`
- `rejected_ambiguous_entity`

Ese error es mas caro que perder algun lead dudoso.

---

## 2. Objetivos funcionales

### Objetivo A

No aceptar por defecto como target una entidad empatada entre `direct_business` y `aggregator` / `directory`.

### Objetivo B

Separar mejor:

- entidad;
- modelo de negocio;
- taxonomia de industria.

### Objetivo C

Eliminar taxonomias duplicadas entre root fields y `generic_attributes`.

---

## 3. Backlog propuesto

### E-001 Endurecer deteccion de directorio/agregador/media

Agregar reglas con mas peso para:

- `compara`
- `directorio`
- `mejores`
- `ranking`
- `lista`
- `encuentra clinicas`
- `opiniones`
- `valoraciones`
- `presupuestos sin compromiso`

Y senales estructurales como:

- `ItemList`
- `CollectionPage`
- `BreadcrumbList`
- repeticion de multiples nombres de negocios;
- repeticion de multiples ubicaciones;
- multiples enlaces a terceros;
- copy del nicho en general y no de una empresa concreta.

**Criterio de cierre:** los comparadores y directorios frecuentes dejan de caer en `direct_business`.

### E-002 Regla de empate conservadora

Si `score_by_entity_type` queda muy cerca entre `direct_business` y `aggregator` o `directory`:

- no promover a `accepted_target`;
- degradar a `accepted_related` o `rejected_ambiguous_entity`.

**Criterio de cierre:** los casos ambiguos no entran como target por defecto.

### E-003 Endurecer `acceptance_decision`

Expandir la semantica de aceptacion a:

- `accepted_target`
- `accepted_related`
- `review_needed`
- `rejected_directory`
- `rejected_aggregator`
- `rejected_media`
- `rejected_invalid_contact`
- `rejected_ambiguous_entity`

**Criterio de cierre:** la API comunica mejor por que algo no paso como lead principal.

### E-004 Agregar `review_reason` y `blocking_reasons`

Separar claramente:

- razon de revision;
- bloqueadores duros.

Ejemplos:

- `entity_ambiguous`
- `invalid_phone`
- `missing_email`
- `weak_location`
- `taxonomy_conflict`

**Criterio de cierre:** no todo cae en un solo `rejection_reason`.

### E-005 Unificar taxonomia en una sola fuente de verdad

Migrar desde:

- `taxonomy_top_level`
- `taxonomy_business_type`
- duplicados dentro de `generic_attributes`

hacia una forma unificada:

- `taxonomy.top_level`
- `taxonomy.industry`
- `taxonomy.business_type`
- `taxonomy.confidence`
- `taxonomy.evidence`

**Criterio de cierre:** no hay dos taxonomias compitiendo en el mismo prospecto.

### E-006 Eliminar taxonomia duplicada en `generic_attributes`

Mantener `generic_attributes` solo para enrichment no estructural.

**Criterio de cierre:** la taxonomia visible y persistida sale de un solo resolvedor.

### E-007 Agregar `business_model_detected`

Nuevo clasificador comercial:

- `direct_service_provider`
- `directory_platform`
- `affiliate_comparison`
- `publisher_media`
- `marketplace_connector`
- `agency_service`
- `clinic_chain`
- `single_location_clinic`

Campos:

- `business_model_detected`
- `business_model_confidence`
- `business_model_evidence`

**Criterio de cierre:** el modelo de negocio ya no depende solo de `entity_type_detected`.

---

## 4. Modulos probablemente afectados

- `app/services/entity_classifier.py`
- `app/services/prospect_quality.py`
- `app/services/business_taxonomy.py`
- `app/services/heuristic_extractor.py`
- `app/services/ai_extractor.py`
- `app/scraper/engine.py`
- `app/api/schemas.py`
- `app/api/jobs.py`
- `tests/test_entity_classifier.py`
- `tests/test_commercial_fixtures.py`

---

## 5. Orden interno sugerido

1. `E-001`
2. `E-002`
3. `E-003`
4. `E-004`
5. `E-005`
6. `E-006`
7. `E-007`

---

## 6. Casos de validacion minimos

- `todoestetica.com` no debe quedar `accepted_target`;
- `comparaclinic.com` no debe quedar `accepted_target`;
- un sitio real tipo clinica directa debe seguir pudiendo quedar `accepted_target`;
- taxonomia root y taxonomia interna no deben contradecirse.
