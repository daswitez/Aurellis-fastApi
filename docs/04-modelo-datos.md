# Modelo de Datos

## Datos mínimos necesarios

Para que este servicio sea útil, cada prospecto debería intentar capturar como mínimo los siguientes campos.

### Datos básicos del prospecto

- nombre de empresa o negocio
- dominio principal
- URL del sitio web
- categoría o nicho aparente
- ubicación si está disponible
- ubicación validada por evidencia
- match de ubicación (`match`, `mismatch`, `unknown`)
- idioma detectado
- match de idioma (`match`, `mismatch`, `unknown`)
- descripción breve del negocio si es detectable

### Datos de contacto

- email visible
- página de contacto
- formulario de contacto detectado
- teléfono si está disponible
- redes sociales relevantes
- CTA principal
- URL de reservas
- URL de precios
- canal de WhatsApp público si existe
- score de calidad de contacto

### Datos de contexto comercial

- servicios aparentes
- tipo de negocio estimado
- tamaño aparente o señales de escala
- idioma principal del sitio
- resumen corto del negocio
- keywords de servicios detectados
- estado de calidad del lead

### Señales de oportunidad

- sitio desactualizado
- falta de automatización visible
- presencia digital débil
- formulario/contacto incompleto
- oportunidades detectables según reglas del nicho

### Metadatos técnicos

- fuente de origen
- fecha de scraping
- estado de validación
- estado de calidad (`accepted`, `needs_review`, `rejected`)
- razón de rechazo si aplica
- score inicial *(numérico entre `0.0` y `1.0`)*
- nivel de confianza del dato *(semántico: `low`, `medium`, `high`)*
- flags de deduplicación

## Entidades actuales

### scraping_jobs
Representa cada solicitud de scraping lanzada por el sistema principal.

**Campos actuales relevantes:**
- id
- workspace_id
- requested_by
- status
- user_profession *(ej. Editor de Video)*
- user_technologies *(ej. ["Premiere Pro", "Motion Graphics"])*
- user_value_proposition *(ej. Aumento de retención de audiencia)*
- user_past_successes *(NUEVO: Casos de éxito previos para generar autoridad)*
- user_roi_metrics *(NUEVO: Métricas tangibles de ROI que se le prometen al prospecto)*
- target_niche *(ej. Creadores de Contenido)*
- target_location *(ej. España, USA)*
- target_language *(ej. es, en)*
- target_company_size *(ej. Solopreneur, 10-50 empleados)*
- target_pain_points *(ej. ["Baja retención", "Mala edición"])*
- target_budget_signals *(NUEVO: Qué pistas nos dicen que tienen dinero para invertir)*
- source_type
- filters_json
- started_at
- finished_at
- error_message
- total_found
- total_processed
- total_saved
- total_failed
- total_skipped
- created_at
- updated_at

### prospects
Registro principal del prospecto ya normalizado.

**Campos actuales relevantes:**
- id
- workspace_id
- company_name
- domain
- website_url
- category
- location
- validated_location
- location_match_status
- location_confidence
- detected_language
- language_match_status
- description
- email
- phone
- contact_page_url
- form_detected
- primary_cta
- booking_url
- pricing_page_url
- whatsapp_url
- contact_channels_json
- contact_quality_score
- company_size_signal
- service_keywords
- linkedin_url
- instagram_url
- facebook_url
- inferred_tech_stack *(Tecnologías detectadas en el prospecto)*
- inferred_niche *(Nicho deducido de la empresa)*
- generic_attributes *(JSON con info estructurada adaptada al rubro)*
- hiring_signals *(NUEVO: True/False si buscan contratar o tienen "Careers")*
- estimated_revenue_signal *(NUEVO: low/medium/high según apariencia del negocio)*
- has_active_ads *(NUEVO: True/False si deducimos que pagan anuncios)*
- source
- source_url
- score *(float entre `0.0` y `1.0`)*
- confidence_level *(`low`, `medium`, `high`)*
- created_at
- updated_at

### job_prospects
Resultado contextual del prospecto dentro de un job.

**Campos actuales relevantes:**
- id
- job_id
- prospect_id
- source_url
- source_type
- discovery_method
- search_query_snapshot
- rank_position
- processing_status
- quality_status
- quality_flags_json
- rejection_reason
- discovery_confidence
- match_score
- confidence_level
- fit_summary
- pain_points_json
- evidence_json
- raw_extraction_json
- error_message
- created_at
- updated_at

### prospect_contacts
Canales de contacto detectados y normalizados.

**Campos actuales relevantes:**
- id
- prospect_id
- contact_type
- contact_value
- label
- is_primary
- is_public
- confidence
- source_url
- created_at
- updated_at

### prospect_pages
Inventario de páginas visitadas o inferidas durante el crawl.

**Campos actuales relevantes:**
- id
- prospect_id
- url
- page_type
- http_status
- title
- meta_description
- detected_language
- text_hash
- content_signals_json
- last_seen_at
- last_scraped_at
- created_at
- updated_at

### prospect_signals
Señales detectadas durante el análisis del prospecto o reservadas para etapas posteriores.

**Campos actuales relevantes:**
- id
- prospect_id
- signal_type
- signal_value
- confidence
- notes
- created_at

### scraping_logs
Eventos técnicos o mensajes relevantes por job.

**Campos actuales relevantes:**
- id
- job_id
- level
- message
- source_name
- context_json
- created_at

---

## Estado actual del modelo

La evolución propuesta ya está parcialmente aplicada:

- `prospects` funciona como entidad canónica del dominio;
- `job_prospects` conserva score, evidencia, discovery y calidad por corrida;
- `prospect_contacts` normaliza canales detectados;
- `prospect_pages` registra páginas vistas o inferidas.

La justificación completa y el diseño objetivo siguen documentados en [08-diseno-base-prospeccion-y-crm.md](08-diseno-base-prospeccion-y-crm.md).
