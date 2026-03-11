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
- [09. Cambios Implementados Hasta Fase B](09-cambios-implementados-hasta-fase-b.md) - Resumen ejecutivo y técnico de todo lo implementado hasta este punto.
- [10. Diseño del Prompt de DeepSeek](10-diseno-prompt-deepseek.md) - Reglas, versión activa y criterio de calidad del extractor IA.

## Planeación y Backlog
- [Plan de Trabajo por Fases](backlog/README.md) - Desglose detallado de todos los pasos, desde el Setup inicial (Fase 1) hasta la Integración Oficial en producción con Supabase y NestJS (Fase 5).

## Arquitectura por Fases
- [Arquitectura Temporal (Validación/Docker)](arquitectura-temporal/01-vision-general.md) - Diseño aislado usando un contenedor local de Postgres para probar viabilidad libremente.
- [Arquitectura Oficial (Producción/Supabase)](arquitectura-oficial/01-vision-general.md) - Diseño final, acoplado al backend de NestJS mediante asincronía y apuntando a Supabase.
