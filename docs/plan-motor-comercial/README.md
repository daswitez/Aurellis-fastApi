# Plan Motor Comercial

Este folder organiza la siguiente fase de mejoras para llevar el sistema desde una buena base de clasificacion comercial a un motor mas confiable para priorizacion y outreach.

La pregunta de esta fase ya no es "puedo extraer datos", sino:

- puedo distinguir mejor target real vs ruido comercial;
- puedo medir la confiabilidad de los datos por separado del fit;
- puedo decir si el lead esta listo para accion;
- puedo explicar con evidencia por que el sistema decidio eso.

## Orden recomendado

1. [01-prioridades-y-fases.md](01-prioridades-y-fases.md)
2. [02-precision-de-entidad-y-taxonomia.md](02-precision-de-entidad-y-taxonomia.md)
3. [03-calidad-de-datos-y-normalizacion.md](03-calidad-de-datos-y-normalizacion.md)
4. [04-scoring-readiness-y-objeto.md](04-scoring-readiness-y-objeto.md)
5. [05-evidencia-enriquecimiento-y-pipeline.md](05-evidencia-enriquecimiento-y-pipeline.md)
6. [06-rollout-metricas-y-dataset.md](06-rollout-metricas-y-dataset.md)

## Prioridad ejecutiva

La prioridad mas rentable no es "mas scraping". Es bajar errores de decision comercial.

ML no es parte de la siguiente fase inmediata. Queda como posibilidad de largo plazo, solo despues de estabilizar:

- precision de entidad;
- taxonomia unica;
- calidad de contacto;
- parsing de ubicacion;
- readiness;
- evidencia y metricas.

Orden propuesto:

1. endurecer `entity_type_detected` y `acceptance_decision`;
2. unificar taxonomia en una sola fuente de verdad;
3. endurecer validacion de contacto y parseo de ubicacion;
4. separar `target_fit_score`, `data_quality_score` y `outreach_readiness_score`;
5. agregar `detected_gaps`, `blocking_reasons` y `outreach_ready`;
6. agregar evidencia textual y roles de pagina;
7. ampliar enrichment de business model, chain detection y madurez digital.

## Casos guia

Este plan toma como referencia errores o senales observadas en:

- `todoestetica.com`
- `comparaclinic.com`
- `clinicaslove.com`

## Resultado esperado

Al cerrar este plan, el sistema deberia:

- equivocarse menos al decidir quien es un prospecto real;
- separar mejor fit comercial, calidad de datos y readiness;
- dejar mejor evidencia para debugging y UI;
- tener una base mas solida para scoring y, recien a largo plazo, evaluar enfoques hibridos si realmente hicieran falta.
