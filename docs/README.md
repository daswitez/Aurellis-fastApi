# Documentación del Servicio de Scraping y Enriquecimiento de Prospectos

Bienvenido a la documentación del servicio de scraping y enriquecimiento desarrollado en FastAPI. Este servicio se encarga de extraer, limpiar y enriquecer prospectos B2B para integrarlos de forma asíncrona con el backend principal de la plataforma.

A continuación, puedes encontrar la información de forma estructurada:

## Definiciones Básicas
- [01. Contexto y Objetivos](01-contexto-y-objetivos.md) - Por qué existe el servicio y su rol.
- [02. Funcionalidades Core](02-funcionalidades-core.md) - El detalle del ciclo de recolección y enriquecimiento.
- [03. Arquitectura Técnica (Resumen Base)](03-arquitectura-tecnica.md) - Principios base, stack y capas lógicas principales.
- [04. Modelo de Datos](04-modelo-datos.md) - Datos a extraer sobre prospectos y las entidades SQL a considerar.
- [05. API y Reglas](05-api-y-reglas.md) - Endpoints propuestos, límites iniciales de operación y visión a futuro.
- [06. Quickstart / Setup](06-quickstart.md) - Cómo clonar y levantar este proyecto localmente.

## Planeación y Backlog
- [Backlog MVP de Scraping](backlog/01-fase-scraping-mvp.md) - Pasos específicos para validar y construir la primera versión funcional de este servicio.

## Arquitectura por Fases
- [Arquitectura Temporal (Validación/Docker)](arquitectura-temporal/01-vision-general.md) - Diseño aislado usando un contenedor local de Postgres para probar viabilidad libremente.
- [Arquitectura Oficial (Producción/Supabase)](arquitectura-oficial/01-vision-general.md) - Diseño final, acoplado al backend de NestJS mediante asincronía y apuntando a Supabase.
