# API, Reglas y Futuro

## Endpoints internos sugeridos

- **`POST /scrape/prospects`**: Recibe criterios de búsqueda y dispara un job de scraping.
- **`GET /jobs/{job_id}`**: Devuelve estado del job y métricas básicas.
- **`GET /jobs/{job_id}/results`**: Devuelve prospectos asociados al job.
- **`POST /scrape/enrich`**: Permite enriquecer un prospecto existente o un dominio concreto.
- **`GET /health`**: Estado básico del servicio.

## Reglas y límites iniciales

- no scrapear sin criterios definidos
- no ejecutar crawls excesivos por defecto
- limitar profundidad de navegación
- respetar timeouts
- registrar errores por fuente
- guardar solo datos útiles
- evitar duplicados desde el inicio
- mantener el modelo de datos simple
- no mezclar lógica de negocio principal dentro de este servicio

## Qué se considera éxito en esta fase

Este servicio será exitoso en su primera etapa si logra:

- producir prospectos estructurados y utilizables
- mantener trazabilidad de cada job
- integrarse sin fricción con la API principal
- soportar crecimiento por nuevas fuentes
- permitir al sistema principal mostrar leads útiles
- servir como base para scoring y personalización posterior

El foco no es aún la escala masiva, sino la calidad, consistencia y utilidad comercial de los datos.

## Visión a futuro

A futuro, este servicio podrá evolucionar para incorporar:

- nuevas fuentes de prospección
- mejores reglas de scoring
- detección más inteligente de señales de oportunidad
- enriquecimiento con IA en casos concretos
- colas y workers distribuidos
- mayor observabilidad
- scraping más robusto y paralelo
- validación adicional de correos o contactos
- integración con sistemas de recomendación de prospectos

La prioridad actual, sin embargo, es construir una base sólida y modular que sirva como motor inicial de descubrimiento de prospectos para el producto principal.
