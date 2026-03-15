# v1.02 - Backlog Priorizado

## Criterio de priorizacion

- `P0`: bloquea calidad base o produce leads enganiosos.
- `P1`: mejora directamente el valor del primer contacto.
- `P2`: mejora scoring, precision fina y politicas comerciales.
- `P3`: mejora trazabilidad, QA y salida para consumo humano y comercial.

## P0 - Higiene de identidad y datos

### 1. Resolver identidad comercial real

Objetivo:

- Que `canonical_identity` represente a la marca/persona real, no a la pagina donde fue descubierta.

Implementacion:

- Crear reglas de resolucion de identidad para:
  - web propia
  - perfil social primario
  - hubs de terceros como `Linktree`
  - posts o articulos que enlazan a una oferta o perfil principal
- Agregar concepto operativo de:
  - `entry_surface`
  - `identity_surface`
  - `contact_surface`
  - `offer_surface`

Salida esperada:

- Prospecto con identidad estable aunque haya sido descubierto por un articulo o hub externo.

Aceptacion:

- `Linktree` deja de ser identidad canonica.
- Una pagina de articulo no queda como mejor superficie si existe una pagina comercial mejor.

### 2. Normalizar perfiles sociales reales

Objetivo:

- Guardar solo perfiles utiles para outreach.

Implementacion:

- Excluir `share`, `intent`, `shareArticle`, `sharer.php`, `company`, `in` y variantes equivalentes como handles validos.
- Distinguir:
  - perfil oficial
  - share link
  - intent link
  - social post
- Marcar `is_primary` cuando el perfil sea la mejor puerta de contacto o marca principal.

Salida esperada:

- `social_profiles` limpios y accionables.

Aceptacion:

- No se guardan perfiles de share como redes reales.
- Handles basura desaparecen del output final.

### 2.1. Construir una capa de `social_quality`

Objetivo:

- Medir calidad social real para que las redes puedan competir limpiamente con una web cuando el negocio vive ahi.

Implementacion:

- Crear un objeto por perfil social con señales observables y reutilizables en cualquier rubro:
  - `platform`
  - `handle`
  - `display_name`
  - `bio`
  - `category`
  - `link_in_bio`
  - `contact_options`
  - `visible_ctas`
  - `activity_evidence`
  - `offer_evidence`
  - `audience_evidence`
  - `profile_completeness`
  - `profile_commerciality`
- Calcular puntajes parciales:
  - `identity_quality`
  - `activity_quality`
  - `commercial_quality`
  - `contact_quality`
  - `audience_fit_quality`
- Consolidar un `social_quality_score`.

Datos a extraer o reforzar:

- si existe bio o tagline clara
- si hay CTA de DM, WhatsApp, link, agenda o compra
- si hay link-in-bio a oferta, calendario, tienda o lead magnet
- si el perfil parece activo
- si la oferta se entiende desde el perfil
- si la audiencia a la que vende se entiende
- si hay consistencia entre nombre, handle y tema

Salida esperada:

- Los perfiles sociales dejan de ser solo enlaces y pasan a ser superficies evaluadas.

Aceptacion:

- Un prospecto social-first puede ser fuerte aunque no tenga web.
- Un perfil decorativo o vacio no empuja demasiado el score solo por existir.

### 3. Tratar hubs de terceros como contenedores, no como negocio

Objetivo:

- Evitar que `Linktree`, agregadores o superficies puente deformen la base.

Implementacion:

- Crear tipo de superficie `identity_hub`.
- Extraer enlaces salientes relevantes y resolver identidad real.
- Solo mantener el hub como evidencia secundaria si aporta CTA o contacto.

Salida esperada:

- Mejor calidad en personal brands y coaches que viven en redes.

Aceptacion:

- Hubs de terceros no quedan como `website` principal salvo ausencia total de mejor identidad.

### 4. Reforzar limpieza de contacto y ubicacion

Objetivo:

- Evitar datos inutiles o falsos en outreach.

Implementacion:

- Endurecer validacion de telefonos cortos, timestamps, IDs y secuencias ambiguas.
- Separar:
  - `phone_detected`
  - `phone_validated`
- Rehacer parsing de location con mas conservadurismo.
- Si la ubicacion no es confiable, dejar `unknown` en vez de inventarla.

Salida esperada:

- Menos ruido en telefono, ciudad, region y booking.

Aceptacion:

- No se aceptan telefonos obvios invalidos.
- No se elevan ubicaciones desde texto narrativo.

### 5. Exclusion mas fuerte de institucionales y no prospectables

Objetivo:

- Evitar casos como policia, gobierno, portales institucionales y similares.

Implementacion:

- Agregar familia de exclusiones por:
  - gobierno
  - instituciones
  - entidades publicas
  - portales judiciales
  - academicos no comerciales
- Integrar esta exclusion antes del scrape pesado y tambien en scoring final.

Salida esperada:

- Menos `needs_review` absurdos.

Aceptacion:

- Casos institucionales deben caer en exclusion temprana o rechazo duro.

## P1 - Enriquecimiento para primer contacto

### 6. Evaluacion multi-superficie flexible

Objetivo:

- Evitar discriminacion arbitraria entre web y social.

Implementacion:

- Crear capa de evaluacion por superficies:
  - `website_surface`
  - `social_surfaces`
  - `best_surface_for_identity`
  - `best_surface_for_contact`
  - `best_surface_for_offer`
- Construir logica de pesos adaptativos:
  - marcas personales y creadores: social puede tener mas peso
  - pymes de servicios con funnel: web puede tener mas peso
  - ecommerce con tienda y redes: ambas pueden ser necesarias
- Basar la decision en evidencia real:
  - claridad de oferta
  - facilidad de contacto
  - CTA visibles
  - pruebas de actividad
  - consistencia de marca

Salida esperada:

- Campo `best_surface` y decision trazable de por que esa superficie es la mejor.

Aceptacion:

- No se asume que tener web siempre es mejor.
- No se asume que tener Instagram siempre es suficiente.

### 6. Detectar modelo de oferta

Objetivo:

- Saber que vende realmente el prospecto.

Implementacion:

- Clasificar oferta principal:
  - servicio 1:1
  - coaching
  - consultoria
  - agencia
  - curso
  - membresia
  - infoproducto
  - ecommerce
  - done-for-you creativo
- Permitir multiples ofertas, pero marcar una `primary_offer_model`.

Salida esperada:

- El prospecto deja de ser solo "servicio profesional" y pasa a tener modelo comercial detectable.

Aceptacion:

- Casos de coaches y marcas personales salen con oferta mas precisa.

### 7. Detectar canal recomendado de contacto

Objetivo:

- Saber por donde conviene entrar.

Implementacion:

- Crear `recommended_contact_channel` con prioridades como:
  - Instagram DM
  - email
  - WhatsApp
  - formulario
  - LinkedIn
- Ponderar por visibilidad, calidad del canal, cercania al decisor y friccion esperada.

Salida esperada:

- Cada prospecto tiene un canal primario sugerido para outreach.

Aceptacion:

- Los social-first no quedan forzados a email si el mejor canal es Instagram o WhatsApp.

### 8. Generar hipotesis de dolor comercial

Objetivo:

- Producir un primer contacto mas especifico.

Implementacion:

- Convertir señales detectadas en hipotesis concretas:
  - tienen oferta pero poca prueba social visible
  - tienen CTA fuerte pero contenido debil
  - tienen ads pero poca evidencia de assets de conversión
  - tienen presencia pero no sistema de contenido visible
- Separar observacion de inferencia para no exagerar.

Salida esperada:

- `pain_hypotheses` accionables para personalizar mensajes.

Aceptacion:

- Cada prospecto aceptado debe tener al menos 1 hipotesis valida o quedar como `insufficient_outreach_context`.

### 9. Detectar `why now`

Objetivo:

- Encontrar disparadores de contacto inmediatos.

Implementacion:

- Detectar:
  - sesion gratis
  - descuento
  - lead magnet
  - pricing visible
  - booking activo
  - ads stack
  - novedades o campaña aparente

Salida esperada:

- Campo `why_now_signals`.

Aceptacion:

- Prospectos con CTA comercial fuerte deben reflejar una razon de timing.

### 10. Detectar audiencia compradora principal

Objetivo:

- Saber a quien le venden ellos.

Implementacion:

- Crear `buyer_audience_profile`:
  - coaches
  - marcas personales
  - ecommerce
  - creadores
  - negocios locales
  - B2B de servicios
- Inferir desde copy, CTA, servicios, bio y blog.

Salida esperada:

- Mejor match entre el prospecto y la propuesta del usuario.

Aceptacion:

- El sistema debe poder distinguir "vende a coaches" de "es coach".

### 11. Crear `outreach_readiness`

Objetivo:

- Separar prospectos validos de prospectos listos para contacto.

Implementacion:

- Nuevo estado o score con factores:
  - identidad limpia
  - canal de contacto usable
  - oferta detectable
  - una razon concreta para hablarle
  - fit con ICP
- Salidas sugeridas:
  - `ready`
  - `needs_enrichment`
  - `related_only`

Salida esperada:

- Lista mas util para equipo comercial.

Aceptacion:

- No todos los `accepted_related` pasan automaticamente a outreach.

## P2 - Precision comercial y filosofia de producto

### 12. Separar relevancia tematica de prospectabilidad

Objetivo:

- Que el score no mezcle "habla del tema" con "vale la pena contactar".

Implementacion:

- Crear dos lecturas separadas:
  - `topic_relevance_score`
  - `commercial_prospect_score`
- Mantener score final derivado, pero trazable.

Salida esperada:

- Mejor razonamiento en accepted vs related vs review.

### 13. Agregar ranking compuesto por calidad de superficie

Objetivo:

- Que el score final refleje calidad real de presencia y capacidad de contacto.

Implementacion:

- Introducir sub-scores trazables:
  - `website_quality_score`
  - `social_quality_score`
  - `surface_consistency_score`
  - `identity_confidence_score`
  - `outreach_readiness_score`
- El score final debe poder componerse distinto segun el caso:
  - social-first
  - website-first
  - mixed-surface
- Mantener trazabilidad de pesos aplicados.

Salida esperada:

- Mejor ranking cuando el mejor prospecto no es el que tiene mas web sino el que tiene mejor presencia comercial total.

### 14. Recalibrar `accepted_target` vs `accepted_related`

Objetivo:

- Elevar la calidad del bucket mas importante.

Implementacion:

- `accepted_target` debe exigir:
  - identidad limpia
  - oferta clara
  - canal de contacto usable
  - fit razonable con el ICP
- `accepted_related` queda para casos tematicamente utiles pero mas debiles.

### 15. Definir politica de fit no deseado

Objetivo:

- Alinear la base con la filosofia del negocio.

Implementacion:

- Definir exclusiones o penalizaciones para:
  - negocios institucionales
  - spammy growth
  - compra de seguidores
  - modelos dudosos
  - empresas gigantes fuera del ICP

Salida esperada:

- El sistema no solo filtra por palabra clave, tambien por calidad comercial y compatibilidad.

### 16. Recalibrar query/result families con aprendizaje real

Objetivo:

- Ajustar discovery con base en los errores observados, no por intuicion.

Implementacion:

- Etiquetar fallos recurrentes por familia:
  - articulo valido pero mala superficie
  - share links
  - hubs
  - institucional
  - social confuso
- Reafinar negative terms y penalizaciones sin tocar DDG.

## P3 - Salida, trazabilidad y QA

### 17. Construir un `prospect_brief`

Objetivo:

- Entregar algo util para SDR/outreach, no solo JSON tecnico.

Implementacion:

- Objeto resumido con:
  - quien es
  - que vende
  - cual es su mejor superficie
  - mejor canal
  - señal de presupuesto
  - hipotesis de dolor
  - angulo sugerido de mensaje
  - por que ahora

Salida esperada:

- Cada prospecto tiene un resumen humano reutilizable en UI, revision comercial y export.

Aceptacion:

- El brief permite entender el caso sin leer el JSON completo.

### 18. Documentar `decision_trace`

Objetivo:

- Entender por que el sistema acepto o rechazo.

Implementacion:

- Guardar razones compactas de:
  - identidad
  - mejor superficie
  - oferta
  - canal
  - fit
  - readiness

Salida esperada:

- Trazabilidad suficiente para explicar por que un lead entro, salio o quedo debil.

Aceptacion:

- El equipo puede auditar decisiones sin reconstruir el flujo manualmente.

### 19. Crear endpoint nuevo de exportacion `.xls`

Objetivo:

- Entregar un archivo `.xls` ya cargado, legible y accionable sin alterar el `GET` actual de aceptados o `needs_review`.

Implementacion:

- Crear un endpoint nuevo y separado para exportacion.
- Mantener sin cambios semanticos el `GET` actual de resultados aceptados y `needs_review`.
- Hacer que el endpoint de export use el resultado final enriquecido y no una vista parcial.
- Permitir exportar al menos los conjuntos relevantes para operacion comercial:
  - aceptados
  - `needs_review`
  - subconjuntos filtrados si ya existen criterios de consulta
- Incluir como base columnas de alto valor comercial y operativo:
  - `query`
  - `prospect_name`
  - `canonical_identity`
  - `primary_identity_type`
  - `entry_surface`
  - `best_surface_for_identity`
  - `best_surface_for_contact`
  - `best_surface_for_offer`
  - `website_url`
  - `primary_social_platform`
  - `primary_social_url`
  - `recommended_contact_channel`
  - `contact_email`
  - `contact_phone`
  - `location`
  - `primary_offer_model`
  - `offer_summary`
  - `buyer_audience_profile`
  - `why_now_signals`
  - `pain_hypotheses`
  - `estimated_revenue_signal`
  - `pricing_page_url`
  - `booking_url`
  - `has_active_ads`
  - `outreach_readiness`
  - `topic_relevance_score`
  - `commercial_prospect_score`
  - `accepted_bucket`
  - `decision_summary`
- Agregar al menos una hoja principal de trabajo comercial y, si aplica, una hoja secundaria con:
  - `decision_trace`
  - evidencia resumida
  - datos utiles para QA
- Aplicar diseno funcional para uso real en Excel:
  - encabezados claros
  - filtros automaticos
  - fila superior congelada
  - anchos de columna ajustados
  - wrap en campos largos
  - colores sobrios por estado o bucket
  - orden inicial por prioridad comercial o readiness
- Asegurar que los detalles importantes de la respuesta de busqueda queden visibles en el export:
  - identidad resuelta
  - oferta detectada
  - mejor canal
  - mejor superficie
  - razon de contacto
  - senales de timing
  - senales de presupuesto o madurez

Salida esperada:

- Endpoint nuevo que devuelve un `.xls` listo para abrir en Excel, filtrar y usar como lista operativa de prospeccion.

Aceptacion:

- El `.xls` no sale del `GET` actual de aceptados ni del flujo actual de `needs_review`.
- El usuario no necesita abrir el JSON para trabajar los leads exportados.
- Cada fila tiene contexto suficiente para decidir si contactar, por donde entrar y con que angulo.
- El archivo abre con estructura legible, filtros activos y campos clave visibles desde la primera pantalla.

### 20. Crear dataset de regresion comercial

Objetivo:

- Proteger la precision lograda.

Implementacion:

- Armar fixtures reales con:
  - buen target
  - accepted_related valido
  - social-first sin web
  - social-first fuerte que supera a una web debil
  - web fuerte que supera a una red debil
  - superficie mixta bien consolidada
  - Linktree bien resuelto
  - institucional rechazado
  - share links excluidos

## Orden de ejecucion recomendado

1. Tareas `1` a `5`
2. Tareas `6` a `11`
3. Tareas `12` a `16`
4. Tareas `17` y `18`
5. Tarea `19`
6. Tarea `20`
