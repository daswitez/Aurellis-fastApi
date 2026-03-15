# v1.02 - Base Congelada y Plan Pragmatico

## Objetivo

Pasar de un sistema que ya encuentra prospectos comercialmente relacionados a un sistema que entregue prospectos mas listos para outreach, con mejor identidad, mejor limpieza y mejores angulos para el primer contacto.

## Lo que ya tenemos y funciona bien

- `DDG` como unico motor de discovery.
- Discovery `website-first` y `social-first` sin tocar la base anti-bot actual.
- Mejor filtro temprano contra ruido editorial, reference pages y finance.
- Soporte para `canonical_identity`, `primary_identity_type`, `primary_identity_url` y `social_profiles`.
- Mejores señales comerciales:
  - `primary_cta`
  - `booking_url`
  - `pricing_page_url`
  - `has_active_ads`
  - `estimated_revenue_signal`
  - `service_keywords`
  - `content_profile`
  - `inferred_tech_stack`
- Aceptacion de leads social-first como primera clase.
- Mejor ajuste a rubros creativos sin cerrar la puerta a otros rubros.
- Filosofia actual correcta:
  - precision antes que volumen
  - buscar prospectos comprables, no solo paginas relacionadas
  - aprovechar redes sociales como superficie real del negocio
  - no asumir que la web propia siempre vale mas que la red social

## Lo que se hace bien y no se debe cambiar en v1.02

- No cambiar `DuckDuckGo` por otro motor.
- No desarmar el enfoque `social-first`.
- No volver a una logica basada solo en `domain`.
- No perder los campos nuevos de identidad y redes.
- No volver a un scoring orientado a "negocio generico"; debe seguir comercial y orientado a prospeccion.
- No bajar la vara de precision para inflar volumen.
- No romper la adaptabilidad a otros rubros; los cambios deben nacer desde creativo pero mantenerse genericos.

## Lectura pragmatica del estado actual

El sistema ya mejoro mucho en discovery y en separacion de ruido grueso. El siguiente cuello de botella ya no es "encontrar URLs", sino:

- resolver mejor la identidad comercial real
- limpiar datos engañosos o inutiles para outreach
- convertir señales tecnicas y comerciales en angulos de primer contacto
- distinguir mejor entre "tema relacionado" y "prospecto listo para contactar"

## Problemas prioritarios detectados

### 1. Confusion entre identidad y superficie encontrada

- Se descubren leads por posts, articulos o hubs de terceros, pero se tratan como identidad principal.
- Ejemplos tipicos:
  - posts de blog como superficie primaria
  - `Linktree` como identidad canonica
  - share links como si fueran perfiles reales

### 2. Calidad social todavia irregular

- Entran URLs de share o intent:
  - `facebook sharer`
  - `linkedin shareArticle`
  - `twitter intent`
- Se normalizan handles inutiles:
  - `in`
  - `company`
  - `share`
- Aun no existe una capa suficientemente fuerte para medir calidad social real.
- Todavia falta distinguir entre:
  - perfil oficial
  - perfil activo
  - perfil comercial
  - perfil con audiencia compradora
  - perfil solo decorativo o de presencia minima
- Todavia falta extraer mejor datos sociales utiles para outreach incluso cuando no existe web.

### 3. Datos utiles para outreach aun incompletos

Hoy sabemos que un prospecto es comercial, pero no siempre sabemos:

- cual es su oferta principal
- que angulo de mensaje conviene
- cual es el mejor canal de contacto
- por que contactarlo ahora
- cual es el dolor mas probable
- que red social es realmente la principal
- que tan activa y comercial es esa red
- si la marca vende desde redes, desde web o desde ambas

### 4. Persisten falsos positivos o casos no deseables

- institucionales o gobierno
- hubs de terceros
- negocios de fit dudoso con la filosofia comercial deseada

### 5. Limpieza de contacto y ubicacion todavia debil

- telefonos falsos o incompletos
- ubicaciones parseadas desde texto irrelevante
- booking URLs que no representan una reserva real

### 6. Falta una evaluacion flexible entre web y social

- Hoy todavia puede quedar implícito que una web pesa mas por defecto.
- En otros casos puede pasar lo contrario y una red visible empuja demasiado aunque no sea buena.
- Eso no sirve para el objetivo real.
- La calidad debe evaluarse segun el negocio y segun la intencion del usuario:
  - si el prospecto vende por Instagram o TikTok, la red debe poder pesar mas
  - si el prospecto tiene una web comercial fuerte, la web debe poder pesar mas
  - si ambas superficies existen, deben consolidarse, no competir de forma arbitraria

## Cambios que propone v1.02

### Prioridad 1. Limpiar identidad y superficies

- Distinguir estrictamente:
  - `entry_url`
  - `commercial_identity`
  - `best_contact_surface`
  - `best_offer_surface`
- Resolver mejor cuando el discovery entra por:
  - post
  - pagina de servicio
  - Linktree
  - perfil social

### Prioridad 2. Hacer el output mas util para outreach

- Generar una lectura operativa del prospecto:
  - que vende
  - como vende
  - donde conviene contactarlo
  - por que puede comprar
  - que hipotesis de dolor tiene mas sentido

### Prioridad 2.1. Medir calidad social de forma util para prospeccion

- Extraer señales de calidad social independientemente del rubro:
  - handle canonico
  - nombre visible
  - bio
  - categoria visible
  - link-in-bio
  - CTA visibles
  - contacto publico
  - actividad visible
  - consistencia tematica
  - plataforma principal
  - evidencia de oferta
  - evidencia de audiencia compradora
- Evaluar perfiles sociales por calidad comercial, no por vanidad ni por cantidad bruta de links.
- Permitir que un prospecto sin web sea fuerte si su superficie social es buena.
- Permitir que un prospecto con web debil pero red fuerte siga siendo valido.

### Prioridad 3. Endurecer exclusion y limpieza

- Bloquear share links, intent links y hubs no propios como identidad primaria.
- Penalizar o excluir institucionales y no prospectables.
- Corregir parsing de telefono, handle y ubicacion.

### Prioridad 4. Separar relevancia de readiness

- Un lead puede ser:
  - relevante para el nicho
  - comercialmente valido
  - listo para contactar
- Esas tres cosas no deben quedar mezcladas en un solo score.

### Prioridad 5. Ranking multi-superficie y no arbitrario

- No priorizar automaticamente web sobre redes ni redes sobre web.
- Introducir una evaluacion por superficies:
  - `website_quality`
  - `social_quality`
  - `identity_confidence`
  - `contact_reachability`
  - `offer_clarity`
- El ranking final debe adaptarse al caso:
  - coach o marca personal sin web: social puede ser la mejor base
  - pyme de servicios con web fuerte: web puede pesar mas
  - ecommerce con tienda y redes: ambas deben consolidarse
- El peso entre superficies debe responder al tipo de negocio y al objetivo del usuario.

## Resultado esperado de v1.02

Al cerrar esta version, cada prospecto deberia poder responder de forma confiable estas preguntas:

- Quien es realmente.
- Que vende realmente.
- Cual es su canal comercial principal.
- Cual es su superficie comercial mas fuerte.
- Que señal concreta sugiere presupuesto o madurez.
- Cual seria el mejor primer angulo de contacto.
- Si esta listo para outreach o necesita mas enriquecimiento.

Y ademas el sistema deberia ofrecer un endpoint nuevo y separado para exportar un archivo `.xls` util para trabajo comercial real:

- sin cambiar el comportamiento del `GET` actual de aceptados o `needs_review`
- con los datos ya cargados
- con los detalles importantes de la respuesta de busqueda ya resumidos
- con columnas legibles para filtrar, revisar y asignar
- con un formato suficientemente claro para usarlo sin depender del JSON

## Lista priorizada de trabajo

1. Corregir identidad canonica, superficie principal y superficies utiles de contacto.
2. Limpiar redes sociales falsas, share links, handles basura y hubs de terceros.
3. Corregir calidad de telefono, ubicacion y CTA mal inferidos.
4. Construir una capa fuerte de calidad social y actividad comercial por perfil.
5. Detectar modelo de oferta y forma de monetizacion.
6. Generar `outreach readiness`, `recommended_contact_channel` y `best_surface`.
7. Generar hipotesis de dolor y angulo de primer contacto.
8. Separar score de relevancia tematica vs score de prospectabilidad.
9. Implementar ranking multi-superficie flexible y no arbitrario.
10. Definir politica de exclusiones por fit comercial y filosofia de negocio.
11. Construir un `prospect_brief` y `decision_trace` legibles para revision humana y comercial.
12. Crear un endpoint nuevo de exportacion `.xls`, separado del `GET` actual de aceptados o `needs_review`, con los datos importantes de la busqueda ya cargados y buena presentacion para Excel.
