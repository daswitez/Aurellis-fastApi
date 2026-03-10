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
