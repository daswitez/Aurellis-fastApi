# Documentación del Servicio de Scraping y Enriquecimiento de Prospectos

Bienvenido a la documentación del servicio de scraping y enriquecimiento desarrollado en FastAPI. Este servicio se encarga de extraer, limpiar y enriquecer prospectos B2B para integrarlos de forma asíncrona con el backend principal de la plataforma.

A continuación, puedes encontrar la información de forma estructurada:

## Definiciones Básicas
- [01. Contexto y Objetivos](01-contexto-y-objetivos.md) - Por qué existe el servicio y su rol.
- [02. Funcionalidades Core](02-funcionalidades-core.md) - El detalle del ciclo de recolección y enriquecimiento.
- [03. Arquitectura Técnica (Resumen Base)](03-arquitectura-tecnica.md) - Principios base, stack y capas lógicas principales.
- [04. Modelo de Datos](04-modelo-datos.md) - Datos a extraer sobre prospectos y las entidades SQL a considerar.
- [05. API y Reglas](05-api-y-reglas.md) - Contrato actual de endpoints, ejemplos de uso y cambios relevantes respecto al MVP inicial.
- [06. Quickstart / Setup](06-quickstart.md) - Cómo clonar y levantar este proyecto localmente.
- [07. Observaciones y Plan de Mejora](07-observaciones-y-plan-de-mejora.md) - Revisión técnica detallada del MVP, inconsistencias detectadas y prioridades de mejora.
- [08. Diseño Base Prospección y CRM](08-diseno-base-prospeccion-y-crm.md) - Modelo objetivo para escalar prospección, scoring, contactos y futura integración con CRM.
- [09. Cambios Implementados Hasta Fase B](09-cambios-implementados-hasta-fase-b.md) - Resumen ejecutivo y técnico de la estabilización inicial y de la mejora posterior del scraping/calidad.
- [10. Diseño del Prompt de DeepSeek](10-diseno-prompt-deepseek.md) - Reglas, versión activa y criterio de calidad del extractor IA.
- [11. Mapa de Módulos y Cambios Recientes](11-mapa-de-modulos-y-cambios-recientes.md) - Inventario módulo por módulo de los cambios recientes en discovery, parsing, quality gate, IA, persistencia y tests.
- [12. Plan de Refinamiento de Captura y Recall](12-plan-refinamiento-captura-y-recall.md) - Plan específico para aumentar prospectos útiles, mejorar discovery y evitar jobs vacíos por falta de recall.
- [13. Estado Actual, FODA y Pendientes](13-estado-actual-foda-y-pendientes.md) - Resumen ejecutivo del estado real del sistema, fortalezas, debilidades, oportunidades, amenazas y próximos pasos.
- [14. Plan de Clasificación de Entidad y Normalización Comercial](14-plan-clasificacion-entidad-y-normalizacion-comercial.md) - Backlog específico para separar negocio real de directorios, medios, agregadores y limpiar contactos, ubicación e inferencias.

## Clasificacion Comercial Implementada
- [Clasificacion Comercial / README](clasificacion-comercial/README.md) - Indice consolidado de la implementacion real del plan comercial.
- [Clasificacion Comercial / Estado Implementado](clasificacion-comercial/01-estado-implementado.md) - Matriz `I-001` a `I-020` aterrizada a runtime, persistencia, API y tests.
- [Clasificacion Comercial / Logica y Decisiones](clasificacion-comercial/02-logica-y-decisiones.md) - Reglas de clasificacion, calidad, contacto, ubicacion, inferencia y taxonomia.
- [Clasificacion Comercial / Contrato y Metricas](clasificacion-comercial/03-contrato-y-metricas.md) - Campos visibles, endpoint comercial y lectura del contrato.
- [Clasificacion Comercial / Fixtures, Tests y Rollout](clasificacion-comercial/04-fixtures-tests-y-rollout.md) - Cobertura de fixtures reales, tests y despliegue por capas.

## Siguiente Fase Comercial
- [Plan Motor Comercial / README](plan-motor-comercial/README.md) - Indice de la siguiente fase para mejorar precision, readiness y explicabilidad.
- [Plan Motor Comercial / Prioridades y Fases](plan-motor-comercial/01-prioridades-y-fases.md) - Orden recomendado de implementacion y dependencias.
- [Plan Motor Comercial / Precision de Entidad y Taxonomia](plan-motor-comercial/02-precision-de-entidad-y-taxonomia.md) - Endurecimiento de directorios/agregadores, acceptance y taxonomia unica.
- [Plan Motor Comercial / Calidad de Datos y Normalizacion](plan-motor-comercial/03-calidad-de-datos-y-normalizacion.md) - Contacto, ubicacion, sociales, schema y roles de pagina.
- [Plan Motor Comercial / Scoring, Readiness y Objeto](plan-motor-comercial/04-scoring-readiness-y-objeto.md) - Sub-scores, blockers, readiness y shape futuro del prospect object.
- [Plan Motor Comercial / Evidencia, Enriquecimiento y Pipeline](plan-motor-comercial/05-evidencia-enriquecimiento-y-pipeline.md) - Snippets, evidencia, business model, chain detection y pipeline por etapas.
- [Plan Motor Comercial / Rollout, Metricas y Dataset](plan-motor-comercial/06-rollout-metricas-y-dataset.md) - Despliegue incremental, metricas y base de calibracion futura.

## Documentos clave para el estado actual
- [05. API y Reglas](05-api-y-reglas.md) - Contrato visible para integradores y resultados aceptados por calidad.
- [06. Estado del Sistema](06-estado-del-sistema.md) - Resumen operativo del pipeline actual.
- [09. Cambios Implementados](09-cambios-implementados-hasta-fase-b.md) - Qué se cambió realmente en scraping, quality gate, IA y persistencia.
- [11. Mapa de Módulos](11-mapa-de-modulos-y-cambios-recientes.md) - Dónde vive cada comportamiento en el código actual.
- [12. Plan de Captura y Recall](12-plan-refinamiento-captura-y-recall.md) - Qué falta para capturar más leads sin bajar calidad.
- [13. Estado Actual y FODA](13-estado-actual-foda-y-pendientes.md) - Qué está fuerte, qué falta y cuáles son los riesgos y oportunidades actuales.
- [14. Clasificación y Normalización Comercial](14-plan-clasificacion-entidad-y-normalizacion-comercial.md) - Qué falta para separar prospectos reales del ruido semántico y endurecer la calidad comercial.
- [Clasificación Comercial Implementada](clasificacion-comercial/README.md) - Qué quedó realmente implementado desde `I-001` hasta `I-020`.
- [Plan Motor Comercial](plan-motor-comercial/README.md) - Que conviene implementar despues para mejorar precision comercial, data quality y readiness.

## Planeación y Backlog
- [Plan de Trabajo por Fases](backlog/README.md) - Desglose detallado de todos los pasos, desde el Setup inicial (Fase 1) hasta la Integración Oficial en producción con Supabase y NestJS (Fase 5).

## Arquitectura por Fases
- [Arquitectura Temporal (Validación/Docker)](arquitectura-temporal/01-vision-general.md) - Diseño aislado usando un contenedor local de Postgres para probar viabilidad libremente.
- [Arquitectura Oficial (Producción/Supabase)](arquitectura-oficial/01-vision-general.md) - Diseño final, acoplado al backend de NestJS mediante asincronía y apuntando a Supabase.
