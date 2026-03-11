# Fixtures, Tests y Rollout

Este documento resume como se valida y despliega la capa comercial implementada.

---

## 1. Fixtures de regresion

Se agrego `tests/fixtures/commercial/` para cubrir casos problematicos reales.

Casos cubiertos:

- negocio real;
- directorio;
- comparador;
- medio;
- asociacion o listado;
- contacto inconsistente;
- ubicacion contaminada;
- telefono falso tipo fecha o secuencia.

El objetivo no es solo probar funciones aisladas, sino dejar ejemplos reproducibles del comportamiento comercial esperado.

---

## 2. Tests relevantes

### Clasificacion y quality

- `tests/test_entity_classifier.py`
- `tests/test_parser_and_quality.py`
- `tests/test_commercial_fixtures.py`

### Heuristica e IA

- `tests/test_heuristic_extractor.py`
- `tests/test_ai_extractor.py`
- `tests/test_ai_observability.py`

### Taxonomia

- `tests/test_business_taxonomy.py`

### Metricas

- `tests/test_operational_metrics.py`
- `tests/test_commercial_metrics.py`

---

## 3. Que valida cada grupo

### Fixtures comerciales

Validan que:

- un negocio real quede `accepted_target`;
- un directorio quede `rejected_directory`;
- un medio o asociacion no pasen como target;
- la consistencia de contacto afecte `quality_status`;
- la ubicacion visible quede normalizada;
- los telefonos falsos no se persistan como telefonos reales;
- el ruido filtrado quede medible.

### Tests de parser y quality

Validan que:

- JSON-LD, CTAs y contactos se extraigan bien;
- fechas y secuencias no se tomen como telefonos;
- `location` y `validated_location` respeten su precedencia;
- emails externos se marquen como inconsistentes.

### Tests de metricas

Validan que:

- `accepted_target_precision` se calcule bien;
- `accepted_non_target_rate` refleje relacionados aceptados;
- `false_phone_filtered_count` sume desde `raw_extraction_json`;
- `rollout_stage` y `rollout_layers_completed` salgan por API.

---

## 4. Rollout por capas

La implementacion consolidada responde a las cuatro capas del plan:

### Etapa 1. Clasificar y observar

- clasificacion de entidad;
- persistencia de evidencia;
- `is_target_entity`.

### Etapa 2. Penalizar score

- multiplicadores y caps por tipo de entidad;
- separacion entre calidad tecnica y decision comercial.

### Etapa 3. Rechazar duro ciertos tipos

- `rejected_directory`
- `rejected_media`
- `rejected_article`

### Etapa 4. Exponer contrato publico

- campos nuevos por resultado;
- metricas comerciales agregadas;
- docs y fixtures para consumidores y mantenimiento.

---

## 5. Estado actual del rollout

La API comercial actual expone:

- `rollout_stage = stage_4_public_api`
- `rollout_layers_completed = ["stage_1_classify_observe", "stage_2_score_penalty", "stage_3_hard_rejection", "stage_4_public_api"]`

Eso deja explicitado que el cambio ya no esta solo en observacion interna.

---

## 6. Comandos de verificacion usados

Validaciones ejecutadas durante la implementacion:

```bash
PYTHONPATH=. venv/bin/python -m unittest tests.test_parser_and_quality tests.test_commercial_fixtures tests.test_commercial_metrics tests.test_operational_metrics
PYTHONPATH=. venv/bin/python -m unittest tests.test_ai_observability
PYTHONPATH=. venv/bin/python -m compileall app tests
```

---

## 7. Documentos relacionados

- [01-estado-implementado.md](01-estado-implementado.md)
- [02-logica-y-decisiones.md](02-logica-y-decisiones.md)
- [03-contrato-y-metricas.md](03-contrato-y-metricas.md)
- [../14-plan-clasificacion-entidad-y-normalizacion-comercial.md](../14-plan-clasificacion-entidad-y-normalizacion-comercial.md)
