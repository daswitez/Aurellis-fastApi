# v1.02 - Cambios y Decisiones

## Estado de la version

- Version: `v1.02`
- Estado: `planificada`
- Objetivo principal: mejorar calidad de prospeccion para primer contacto sin cambiar DDG ni la filosofia social-first.

## Alcance

Incluye:

- identidad comercial
- limpieza de redes y hubs
- readiness para outreach
- mejores señales para angulo comercial
- exclusiones mas alineadas al ICP

No incluye:

- cambio de motor de busqueda
- rediseño completo del contrato API
- automatizacion de copy final de outreach
- expansion a todas las redes sociales posibles

## Decisiones tomadas

### D-001 Mantener DDG como base fija

Decision:

- `DuckDuckGo` se mantiene como unico proveedor de discovery.

Razon:

- ya existe infraestructura evasiva y conocimiento operativo alrededor de ese motor
- el problema actual no es el proveedor, sino la calidad de lo que hacemos despues

### D-002 Priorizar precision sobre recall

Decision:

- en esta version se privilegia calidad del prospecto sobre cantidad.

Razon:

- un lead menos pero mejor contextualizado vale mas para outreach real que una lista inflada de relacionados

### D-003 Social-first sigue siendo parte del core

Decision:

- perfiles sociales siguen siendo activos de primer nivel, no enriquecimiento secundario.

Razon:

- en rubros creativos muchas marcas venden casi todo desde redes

### D-003.1 La calidad social debe medirse explicitamente

Decision:

- la presencia social no se tratara solo como enlace detectado; se tratara como superficie evaluable.

Razon:

- para muchas marcas personales, coaches, tiendas y pymes, la mejor señal comercial visible esta en la red y no en la web
- si no medimos calidad social, terminamos premiando solo al que tiene sitio aunque venda peor

### D-004 La unidad real de trabajo es la identidad comercial

Decision:

- la entidad central ya no es la URL descubierta sino la identidad comercial resoluble.

Razon:

- discovery puede entrar por un post, un hub o un article, pero el outreach necesita llegar a la marca o persona correcta

### D-004.1 La mejor superficie depende del negocio, no de una regla fija

Decision:

- no se prioriza por defecto web sobre red social ni red social sobre web.

Razon:

- una coach puede vender desde Instagram
- una pyme puede cerrar desde WhatsApp
- una agencia puede vender desde su sitio
- un ecommerce puede necesitar ambas superficies

Implicacion:

- la version debe evaluar `best_surface_for_identity`, `best_surface_for_contact` y `best_surface_for_offer`

### D-005 Separar relevancia de readiness

Decision:

- no mezclar "habla del nicho" con "esta listo para contactar".

Razon:

- muchos falsos positivos actuales vienen de esa mezcla

### D-005.1 Separar existencia de superficie de calidad de superficie

Decision:

- tener red social o tener web no suma mucho por si solo; debe pesar la calidad observable de esa superficie.

Razon:

- evita sesgos arbitrarios
- mejora la adaptabilidad a coaches, tiendas y pymes de servicios

### D-006 Alinear el sistema con la filosofia comercial del producto

Decision:

- no todo lo comercialmente relacionado debe quedar aceptado si no es buen fit para el tipo de cliente buscado.

Razon:

- la base debe ayudar a vender mejor, no solo a encontrar coincidencias semanticas

## Riesgos conocidos

- Sobre-filtrar y perder prospectos validos que viven en hubs o superficies mixtas.
- Inferir demasiado en `pain_hypotheses` y producir outreach artificial.
- Generar demasiados campos sin mejorar realmente la calidad de contacto.
- sobre-premiar perfiles sociales activos pero poco comerciales
- sobre-premiar webs bien montadas pero con poca capacidad real de contacto o venta

## Mitigaciones

- separar siempre observacion de inferencia
- usar estados intermedios como `needs_enrichment`
- medir errores por familia de fallos, no solo por score global
- comparar siempre calidad de superficie y no solo presencia de superficie
- hacer fixtures con casos `social > web`, `web > social` y `social + web`

## Criterios de exito

- menos identidades canonicas incorrectas
- menos redes falsas o share links guardados como perfiles reales
- menos institucionales y hubs basura en resultados finales
- mejor deteccion de perfiles sociales fuertes aunque no tengan web
- mejor consolidacion de marcas con web y redes al mismo tiempo
- mas prospectos con:
  - canal de contacto recomendado
  - mejor superficie comercial detectada
  - oferta detectada
  - hipotesis de dolor
  - razon de contacto

## Cambios planificados por bloque

### Bloque 1. Higiene estructural

- resolver identidad
- limpiar social
- tratar hubs
- limpiar location/phone
- endurecer exclusiones

### Bloque 2. Prospeccion accionable

- detectar oferta
- detectar canal recomendado
- generar pain hypotheses
- detectar why-now
- generar outreach readiness

### Bloque 3. Precision comercial

- separar scores
- recalibrar `accepted_target`
- definir politica de fit

### Bloque 4. Trazabilidad

- prospect brief
- decision trace
- dataset de regresion

## Registro de cambios

### 2026-03-14

- Se crea la carpeta `versions/v1.02`.
- Se congela la base conceptual de la version.
- Se documenta backlog priorizado.
- Se documentan decisiones iniciales de alcance y filosofia.

## Notas para ejecucion

- Esta version debe implementarse por capas, no en un solo salto.
- Primero se limpia identidad y datos.
- Luego se enriquece para outreach.
- Al final se recalibra scoring y salida.
