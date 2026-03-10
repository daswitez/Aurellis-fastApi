# Modelo de Datos

## Datos mínimos necesarios

Para que este servicio sea útil, cada prospecto debería intentar capturar como mínimo los siguientes campos.

### Datos básicos del prospecto

- nombre de empresa o negocio
- dominio principal
- URL del sitio web
- categoría o nicho aparente
- ubicación si está disponible
- descripción breve del negocio si es detectable

### Datos de contacto

- email visible
- página de contacto
- formulario de contacto detectado
- teléfono si está disponible
- redes sociales relevantes

### Datos de contexto comercial

- servicios aparentes
- tipo de negocio estimado
- tamaño aparente o señales de escala
- idioma principal del sitio
- resumen corto del negocio

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
- score inicial
- nivel de confianza del dato
- flags de deduplicación

## Entidades sugeridas

### scraping_jobs
Representa cada solicitud de scraping lanzada por el sistema principal.

**Campos sugeridos:**
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
- total_saved
- created_at
- updated_at

### prospects
Registro principal del prospecto ya normalizado.

**Campos sugeridos:**
- id
- workspace_id
- company_name
- domain
- website_url
- category
- location
- description
- email
- phone
- contact_page_url
- form_detected
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
- score
- confidence_level
- created_at
- updated_at

### prospect_signals
Señales detectadas durante el análisis del prospecto.

**Campos sugeridos:**
- id
- prospect_id
- signal_type
- signal_value
- confidence
- notes
- created_at

### scraping_logs
Eventos técnicos o mensajes relevantes por job.

**Campos sugeridos:**
- id
- job_id
- level
- message
- source_name
- context_json
- created_at
