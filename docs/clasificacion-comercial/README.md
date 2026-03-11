# Clasificacion Comercial

Esta carpeta consolida la implementacion real del plan de clasificacion de entidad y normalizacion comercial ejecutado en [14-plan-clasificacion-entidad-y-normalizacion-comercial.md](../14-plan-clasificacion-entidad-y-normalizacion-comercial.md).

Sirve para responder tres preguntas:

1. Que se implemento realmente desde `I-001` hasta `I-020`.
2. Donde vive la logica en el codigo.
3. Que contrato, metricas y fixtures quedaron visibles para consumidores y para el equipo tecnico.

## Indice

- [01-estado-implementado.md](01-estado-implementado.md)
- [02-logica-y-decisiones.md](02-logica-y-decisiones.md)
- [03-contrato-y-metricas.md](03-contrato-y-metricas.md)
- [04-fixtures-tests-y-rollout.md](04-fixtures-tests-y-rollout.md)

## Modulos principales

- `app/services/entity_classifier.py`
- `app/services/prospect_quality.py`
- `app/services/commercial_insights.py`
- `app/services/business_taxonomy.py`
- `app/services/heuristic_extractor.py`
- `app/services/ai_extractor.py`
- `app/scraper/parser.py`
- `app/scraper/engine.py`
- `app/services/db_upsert.py`
- `app/api/jobs.py`
- `app/api/schemas.py`

## Lectura recomendada

Si quieres entender la implementacion end-to-end:

1. [01-estado-implementado.md](01-estado-implementado.md)
2. [02-logica-y-decisiones.md](02-logica-y-decisiones.md)
3. [03-contrato-y-metricas.md](03-contrato-y-metricas.md)

Si quieres revisar cobertura y rollout:

1. [04-fixtures-tests-y-rollout.md](04-fixtures-tests-y-rollout.md)
2. [../05-api-y-reglas.md](../05-api-y-reglas.md)
3. [../11-mapa-de-modulos-y-cambios-recientes.md](../11-mapa-de-modulos-y-cambios-recientes.md)

## Siguiente fase recomendada

Para planificar la siguiente capa de mejoras:

- [../plan-motor-comercial/README.md](../plan-motor-comercial/README.md)
