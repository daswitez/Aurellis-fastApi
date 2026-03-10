# Contexto y Objetivos

## Contexto del proyecto principal

Este servicio forma parte de una plataforma SaaS orientada a freelancers, consultores, emprendedores y pequeñas agencias que necesitan centralizar y optimizar su proceso comercial. El objetivo del producto principal es reducir la fricción operativa desde la prospección de clientes hasta la gestión inicial posterior al cierre de una venta.

La plataforma principal busca integrar en un solo entorno digital las siguientes capacidades:

- descubrimiento de prospectos
- filtrado y priorización de clientes potenciales
- generación de correos personalizados
- seguimiento comercial tipo CRM
- métricas del embudo de ventas
- automatizaciones posteriores al cierre
- organización de interacciones y tareas relevantes

Actualmente, muchos de estos procesos suelen estar dispersos entre distintas herramientas, hojas de cálculo, correos, CRMs parciales y flujos manuales. El producto principal busca convertir ese proceso fragmentado en un flujo más estructurado, automatizado y medible.

Dentro de esa arquitectura general, este servicio en Python tiene una responsabilidad específica: **encontrar, extraer, limpiar y enriquecer información de prospectos a partir de fuentes digitales públicas**.

## Rol de este servicio dentro del sistema

Este servicio de FastAPI no es el sistema principal ni el backend central del producto. Su función es actuar como un **servicio especializado de scraping y procesamiento de datos comerciales**, desacoplado de la API principal.

La API principal del producto, desarrollada en NestJS, será responsable de:

- autenticación y usuarios
- workspaces
- lógica de negocio principal
- campañas
- templates
- pipeline comercial
- dashboard
- integraciones de producto
- gestión de clientes y postventa

Por su parte, este servicio en FastAPI será responsable de:

- recibir solicitudes de scraping
- buscar prospectos en fuentes digitales públicas
- visitar sitios web relevantes
- extraer datos estructurados
- limpiar y normalizar resultados
- enriquecer información básica del prospecto
- detectar señales comerciales útiles
- actualizar la base de datos compartida
- registrar estado y trazabilidad de cada job

En términos simples, este servicio transforma información pública dispersa en una base estructurada de prospectos sobre la cual el sistema principal puede operar.

## Objetivo funcional de esta API

El objetivo de esta API es permitir que el sistema principal pueda lanzar búsquedas de prospectos y obtener resultados utilizables para acciones comerciales posteriores.

Eso implica que esta API debe ser capaz de:

1. recibir una solicitud con filtros o criterios de búsqueda
2. ejecutar scraping o crawling sobre fuentes seleccionadas
3. identificar empresas, profesionales o negocios potencialmente relevantes
4. extraer información útil para contacto y segmentación
5. normalizar esa información
6. deduplicar resultados
7. guardar la información procesada
8. reportar el estado del proceso

El valor de este servicio no está en scrapear por scrapear, sino en producir datos con suficiente calidad como para que el sistema principal pueda:

- mostrar prospectos relevantes al usuario
- ayudar a priorizarlos
- generar mensajes personalizados
- medir oportunidades comerciales
- alimentar el embudo de seguimiento

## Alcance inicial esperado

La primera versión de este servicio no debe intentar cubrir todo internet ni resolver scraping masivo desde el inicio. Su foco debe ser controlado, modular y escalable.

### Alcance inicial sugerido

- trabajar con una o pocas fuentes específicas
- recibir parámetros simples de búsqueda
- procesar una cantidad acotada de resultados
- visitar sitios públicos y páginas de contacto
- capturar datos básicos de prospectos
- registrar jobs con estados claros
- evitar duplicados
- devolver resultados consistentes

### Lo que no debe priorizarse al inicio

- scraping distribuido a gran escala
- crawling agresivo de múltiples dominios
- procesamiento complejo en tiempo real
- clasificación avanzada con IA desde el primer día
- automatizaciones excesivamente sofisticadas
- paneles internos complejos innecesarios
