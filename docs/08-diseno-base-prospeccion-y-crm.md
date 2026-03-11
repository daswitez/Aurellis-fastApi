# Diseño Base para Prospección y CRM

**Fecha:** 2026-03-10  
**Estado:** diseño objetivo previo a migraciones

---

## 1. Objetivo

Este documento define la base de datos objetivo para que el servicio de scraping no solo encuentre prospectos, sino que también alimente correctamente flujos posteriores de:

- priorización comercial,
- generación de propuestas,
- primer contacto personalizado,
- sincronización con CRM,
- y re-enriquecimiento futuro.

El foco está puesto en un producto para:

- freelancers,
- agencias pequeñas,
- consultores,
- y perfiles que necesitan prospectar empresas con contexto suficiente para vender mejor.

---

## 2. Problema del modelo actual

Hoy el modelo mezcla en `prospects` dos cosas diferentes:

1. la entidad canónica del prospecto,
2. y el resultado específico de un job.

Eso genera problemas cuando:

- el mismo dominio aparece en múltiples jobs,
- distintos workspaces prospectan la misma empresa,
- cambian los scores según el perfil del usuario,
- o queremos conservar historial para CRM y automatizaciones posteriores.

Para una plataforma de prospección seria, esos conceptos deben separarse.

---

## 3. Principio de diseño

La base debe dividir claramente:

- **dato canónico del prospecto**: lo que sabemos de la empresa o dominio independientemente de quién la scrapeó,
- **dato contextual por job**: cómo calzó ese prospecto para un usuario, una búsqueda o un workspace específico,
- **dato operacional**: páginas visitadas, contactos detectados, señales y evidencias.

Esto permite:

- deduplicar sin perder historial,
- recalcular score por usuario o nicho,
- usar los mismos prospectos en varios pipelines,
- enriquecer con nuevos scrapers sin destruir modelos previos,
- y conectar más fácil con CRM o flujos de outreach.

---

## 4. Entidades recomendadas

### 4.1. `prospects`

Entidad canónica de la empresa, marca o dominio.

Debe contener solo información relativamente estable:

- dominio principal,
- nombre de empresa,
- URL canónica,
- descripción,
- ubicación,
- redes sociales principales,
- nicho inferido base,
- stack tecnológico inferido,
- idioma principal,
- timestamps de creación/actualización.

No debería almacenar directamente score por usuario o resultado de una búsqueda puntual.

### 4.2. `job_prospects`

Tabla pivote entre `scraping_jobs` y `prospects`.

Esta tabla es la pieza central para escalar bien el producto.

Debe guardar información específica de una corrida:

- `job_id`
- `prospect_id`
- `workspace_id`
- `source_url`
- `source_type`
- `discovery_method`
- `search_query_snapshot`
- `rank_position`
- `processing_status`
- `match_score`
- `confidence_level`
- `fit_summary`
- `pain_points_json`
- `outreach_angles_json`
- `evidence_json`
- `raw_extraction_json`
- `error_message`
- `created_at`
- `updated_at`

Con esto el mismo prospecto puede aparecer en muchos jobs sin sobrescribir historial.

### 4.3. `prospect_contacts`

Tabla normalizada de puntos de contacto detectados.

Campos recomendados:

- `prospect_id`
- `contact_type` (`email`, `phone`, `form`, `linkedin`, `instagram`, `facebook`, `whatsapp`, `booking`, `other`)
- `contact_value`
- `label`
- `is_primary`
- `is_public`
- `contact_person_name`
- `contact_person_role`
- `confidence`
- `source_url`
- `created_at`
- `updated_at`

Esto es importante para CRM porque una empresa puede tener múltiples canales válidos, y no queremos perderlos por meter todo en columnas fijas.

### 4.4. `prospect_pages`

Inventario mínimo de páginas descubiertas y útiles para seguimiento.

Campos recomendados:

- `prospect_id`
- `url`
- `page_type` (`home`, `contact`, `about`, `pricing`, `services`, `portfolio`, `careers`, `blog`, `other`)
- `http_status`
- `title`
- `meta_description`
- `detected_language`
- `text_hash`
- `content_signals_json`
- `last_seen_at`
- `last_scraped_at`

Esta tabla sirve para:

- guardar evidencia,
- no reprocesar siempre las mismas URLs,
- detectar páginas clave,
- y alimentar futuros pipelines de análisis.

---

## 5. Qué datos conviene scrapear además de lo actual

Si el objetivo final es mejorar prospección, propuesta y primer contacto, conviene empezar a capturar más contexto útil para venta y personalización.

### 5.1. Datos de contacto y CTA

- emails visibles en texto, no solo `mailto:`
- teléfonos visibles
- formularios de contacto
- enlace a WhatsApp
- booking links (`Calendly`, `YouCanBookMe`, etc.)
- CTA principal del sitio
- texto del botón principal
- página de contacto real

### 5.2. Datos comerciales del negocio

- servicios ofrecidos
- especialidades detectadas
- industrias o tipos de clientes atendidos
- ubicación o mercados atendidos
- idioma principal
- señales de pricing
- si muestran precios o planes
- si tienen portfolio o case studies
- si muestran testimonios
- si muestran logos de clientes

### 5.3. Datos de madurez digital

- CMS o framework detectado
- analytics / pixel / ads stack
- si tiene newsletter
- si tiene blog
- fecha aparente de contenido reciente
- si tiene SEO básico visible
- si tiene reservas online o automatizaciones
- si tiene ecommerce o checkout

### 5.4. Datos para primer contacto personalizado

- pain points detectables
- propuesta de valor del prospecto
- tono del sitio
- foco principal del negocio
- tipo de CTA dominante
- oportunidad visible de mejora
- evidencia concreta para justificar outreach

### 5.5. Datos para CRM y seguimiento

- fecha del último scrape
- fuente y query de descubrimiento
- score del job
- resumen de fit
- señales detectadas con evidencia
- errores parciales del scrape

---

## 6. Qué debe quedar estructurado y qué puede seguir en JSON

### Conviene estructurar como columnas o tablas

- dominios
- URLs canónicas
- score
- confidence level
- source URL
- tipo de contacto
- valor del contacto
- page type
- rank de búsqueda
- processing status
- revenue signal
- hiring signal
- flags de portfolio, pricing, booking

### Conviene mantener flexible en JSON

- pain points detectados
- evidencia textual
- señales de oportunidad complejas
- ángulos de outreach
- resumen raw de extracción
- metadatos experimentales todavía inestables

La estrategia correcta es híbrida:  
**estructurar lo que se va a filtrar, ordenar o consultar mucho**, y dejar en JSON lo que todavía está evolucionando.

---

## 7. Decisiones de arquitectura para no complicarnos después

### 7.1. Score por job, no por prospecto global

El score depende del perfil del usuario y del job.  
Por eso debe vivir en `job_prospects`, no en `prospects` como valor definitivo de negocio.

### 7.2. Contactos como tabla aparte

No alcanza con columnas fijas de `email`, `phone`, `linkedin_url`, etc.  
Sirven para MVP, pero a mediano plazo la tabla `prospect_contacts` es más correcta.

### 7.3. Evidencia guardada desde el principio

Si después vamos a generar mensajes o propuestas, hace falta saber de dónde salió cada señal.  
No alcanza con guardar solo el resultado final.

### 7.4. Multi-tenant real

Como distintos usuarios pueden prospectar el mismo dominio, la base debe soportar:

- prospecto canónico compartido,
- resultados por workspace/job,
- y futura sincronización con CRM externo por workspace.

---

## 8. Estrategia recomendada para la siguiente etapa

Antes de migrar:

1. Definir nuevas entidades base.
2. Mantener compatibilidad temporal con el modelo actual.
3. Preparar migraciones sin romper el flujo activo.
4. Recién después mover queries y servicios al nuevo modelo.

Eso permite una transición ordenada:

- primero diseño,
- después esquema,
- después persistencia,
- después lectura desde endpoints.

---

## 9. Próximo paso técnico

El siguiente paso de implementación es:

- agregar las nuevas entidades ORM (`job_prospects`, `prospect_contacts`, `prospect_pages`),
- dejar relaciones preparadas,
- y luego construir migraciones y adaptación del flujo de persistencia.

Todavía no conviene cambiar el endpoint de resultados hasta que la migración esté lista.

---

## 10. Estado de implementación actual

La base ya quedó parcialmente activada en el runtime:

- las tablas `job_prospects`, `prospect_contacts` y `prospect_pages` existen,
- el flujo de guardado ya persiste resultados contextuales por job,
- y `GET /jobs/{id}/results` ya lee desde `job_prospects` en vez de depender solo de `prospects.job_id`.

La siguiente mejora importante será desacoplar aún más el modelo canónico del snapshot legado en `prospects` y empezar a mover más señales hacia las tablas nuevas.
