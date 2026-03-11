# Plan de Clasificación de Entidad y Normalización Comercial

**Fecha:** 2026-03-11  
**Objetivo:** mejorar la precisión comercial del pipeline separando negocio objetivo real de ruido semántico, limpiando mejor contactos/ubicación y distinguiendo observaciones de inferencias.

---

## 1. Problema actual

El sistema ya extrae mucho contexto útil, pero todavía puede mezclar:

- negocio objetivo real;
- directorio;
- comparador;
- agregador;
- artículo editorial;
- asociación;
- marketplace;
- página de listado.

Eso produce un problema de fondo:

**el pipeline ya encuentra “vecindad semántica del nicho”, pero aún no separa lo suficiente quién pertenece al ICP comercial y quién solo habla del nicho.**

---

## 2. Diagnóstico resumido

### 2.1. Clasificación de entidad insuficiente

Hoy faltan señales explícitas para distinguir:

- proveedor real del servicio;
- medio o publisher;
- directorio/listado;
- comparador/agregador;
- asociación o cámara;
- agencia/consultora.

### 2.2. Score todavía permisivo para falsos positivos

El score ya tiene gradación, pero aún puede premiar demasiado:

- keywords del nicho;
- estructura web razonable;
- presencia de CTA;
- stack tecnológico;
- señales superficiales del sitio.

Y castiga poco:

- intención informativa;
- naturaleza editorial;
- estructura de listados;
- ausencia de identidad empresarial propia.

### 2.3. Contaminación de campos

Todavía pueden colarse:

- emails de dominios ajenos;
- teléfonos que en realidad son fechas o ruido numérico;
- textos crudos en `location` o `validated_location`;
- contactos sin validación fuerte de consistencia.

### 2.4. Mezcla de observación e inferencia

`pain_points_detected` es útil, pero hoy mezcla demasiado:

- observaciones defendibles;
- hipótesis comerciales;
- inferencias plausibles pero no directamente observables.

### 2.5. Taxonomía todavía abierta

`inferred_niche` sirve, pero necesita una taxonomía más controlada para que el filtrado comercial sea consistente.

---

## 3. Objetivos de este plan

### Objetivo 1

Separar explícitamente tipo de entidad y dejar de tratar todos los hallazgos semánticamente relevantes como si fueran el mismo tipo de oportunidad.

### Objetivo 2

Endurecer la validez de contactos, ubicación y señales comerciales antes de aceptarlas como datos “finales”.

### Objetivo 3

Hacer más honesto el enriquecimiento separando lo observado de lo inferido.

### Objetivo 4

Dejar trazabilidad fina para explicar por qué un prospecto fue aceptado, aceptado como relacionado o rechazado.

---

## 4. Cambios de producto y contrato recomendados

### 4.1. Nuevos campos sugeridos por prospecto/job result

- `entity_type_detected`
- `entity_type_confidence`
- `is_target_entity`
- `entity_type_evidence`
- `contact_consistency_status`
- `primary_email_confidence`
- `primary_phone_confidence`
- `raw_location_text`
- `parsed_location`
- `city`
- `region`
- `country`
- `postal_code`
- `observed_signals`
- `inferred_opportunities`
- `taxonomy_top_level`
- `taxonomy_business_type`
- `acceptance_decision`

### 4.2. Valores sugeridos para `entity_type_detected`

- `direct_business`
- `directory`
- `aggregator`
- `marketplace`
- `media`
- `blog_post`
- `association`
- `agency`
- `consultant`
- `unknown`

### 4.3. Valores sugeridos para `acceptance_decision`

- `accepted_target`
- `accepted_related`
- `rejected_directory`
- `rejected_media`
- `rejected_article`
- `rejected_low_confidence`
- `rejected_contact_inconsistent`

---

## 5. Principios de diseño

### 5.1. No premiar solo relevancia semántica

Que una página hable del nicho no significa que sea un prospecto objetivo.

### 5.2. No convertir texto crudo en dato final

Los campos extraídos deben pasar por limpieza y validación antes de usarse como `location`, `email` o `phone` principal.

### 5.3. No vender inferencia como hecho

Las observaciones y las hipótesis comerciales deben separarse.

### 5.4. Mantener trazabilidad

Toda clasificación fuerte debe poder explicarse con señales y razones visibles.

---

## 6. Backlog detallado

### I.1. Clasificación explícita del tipo de entidad

- [x] **I-001 Definir taxonomía cerrada de tipo de entidad**
  - Crear enum corto y estable para `entity_type_detected`.
  - Documentar cada tipo y cuándo aplica.
  - **Criterio de cierre:** el sistema deja de depender de categorías libres o implícitas.

- [x] **I-002 Crear clasificador determinístico de tipo de entidad**
  - Basarse en dominio, path, title, snippet, estructura de navegación y señales visibles.
  - Detectar medios, listados, comparadores, asociaciones y negocios directos.
  - **Criterio de cierre:** páginas como medios, directorios y agregadores se distinguen del negocio objetivo antes del score final.

- [x] **I-003 Persistir `entity_type_detected`, confianza y evidencia**
  - Guardar `entity_type_confidence` y `entity_type_evidence`.
  - Hacerlo visible por job result.
  - **Criterio de cierre:** la clasificación se puede auditar sin ir al código.

- [x] **I-004 Incorporar `is_target_entity` como decisión explícita**
  - No limitarse a score o quality status.
  - Separar “resultado relacionado” de “resultado objetivo”.
  - **Criterio de cierre:** un agregador relevante puede conservarse como contexto sin pasar como prospecto directo.

**Notas de implementación 2026-03-11**

- La taxonomía cerrada y su documentación operativa quedaron centralizadas en `app/services/entity_classifier.py`.
- El pipeline ahora clasifica tipo de entidad antes de la evaluación final y persiste:
  - `entity_type_detected`
  - `entity_type_confidence`
  - `entity_type_evidence`
  - `is_target_entity`
- Los resultados no objetivo dejan de pasar como `accepted` aunque sigan siendo visibles como contexto relacionado.

### I.2. Penalización estructural de ruido comercial

- [x] **I-005 Añadir penalizaciones fuertes para medios, listados y comparadores**
  - Bajar score o rechazar según el tipo detectado.
  - Tratar publishers, top lists, comparadores y directorios como ruido comercial salvo uso como seed.
  - **Criterio de cierre:** baja la tasa de `accepted` que no representan negocio objetivo real.

- [x] **I-006 Separar `quality_status` de `acceptance_decision`**
  - Mantener calidad técnica y decisión comercial como cosas distintas.
  - **Criterio de cierre:** un resultado puede ser técnicamente scrapeable y aun así quedar rechazado como entidad no objetivo.

- [x] **I-007 Rebalancear pesos del score**
  - Mantener `tech_stack`, CTA y keywords como señales secundarias.
  - Dar más peso a identidad empresarial y menos a coincidencia superficial.
  - **Criterio de cierre:** directorios y comparadores no compiten con negocios reales solo por tener estructura rica.

**Notas de implementación 2026-03-11**

- `quality_status` ahora refleja calidad técnica de extracción/consistencia, mientras `acceptance_decision` refleja decisión comercial final.
- Se añadió rechazo comercial estructural con multiplicadores y `score_cap` para:
  - `rejected_directory`
  - `rejected_media`
  - `rejected_article`
  - `rejected_low_confidence`
- El score heurístico fue reponderado para priorizar `business_identity` y bajar el peso de `stack_fit` y coincidencia superficial de contexto.
- El conteo de captura del job ahora suma solo `accepted_target`, no cualquier resultado técnicamente aceptado.

### I.3. Validación fuerte de contacto

- [x] **I-008 Validar consistencia entre dominio del sitio y dominio del email**
  - Penalizar o rechazar emails claramente ajenos.
  - Marcar `contact_consistency_status`.
  - **Criterio de cierre:** emails de dominios no relacionados no salen como contacto primario confiable.

- [x] **I-009 Endurecer validación de teléfono**
  - Rechazar fechas, secuencias improbables y cadenas numéricas inválidas.
  - Validar longitud mínima, patrón país y plausibilidad.
  - **Criterio de cierre:** baja la tasa de teléfonos falsos aceptados.

- [x] **I-010 Añadir confianza por canal de contacto**
  - `primary_email_confidence`
  - `primary_phone_confidence`
  - `primary_contact_source`
  - **Criterio de cierre:** el consumidor puede distinguir entre contacto fuerte y contacto dudoso.

**Notas de implementación 2026-03-11**

- El parser ahora rechaza teléfonos con forma de fecha o secuencia artificial antes de persistirlos.
- La selección de contacto primario pasó a `prospect_quality`, donde se calcula:
  - `contact_consistency_status`
  - `primary_email_confidence`
  - `primary_phone_confidence`
  - `primary_contact_source`
- Emails de dominios externos al sitio dejan de salir como `primary_email` confiable y degradan o rechazan la calidad del contacto según el resto de canales disponibles.
- `ProspectContact.confidence` ahora se alimenta desde la confianza calculada por canal, en vez de usar un `1.0` fijo.

### I.4. Normalización de ubicación

- [ ] **I-011 Separar ubicación cruda de ubicación parseada**
  - No usar texto contaminado como `location` final.
  - Guardar `raw_location_text`.
  - **Criterio de cierre:** el campo visible no mezcla dirección, teléfono, horarios y texto residual.

- [ ] **I-012 Parsear componentes de ubicación**
  - `city`
  - `region`
  - `country`
  - `postal_code`
  - **Criterio de cierre:** la ubicación puede usarse para filtros y scoring con menos ruido.

- [ ] **I-013 Revisar precedencia entre `location`, `validated_location` y componentes**
  - Documentar cuál es el campo visible principal y cuál es el técnico.
  - **Criterio de cierre:** no hay ambigüedad entre texto detectado, texto validado y ubicación normalizada.

### I.5. Separar observaciones de inferencias

- [ ] **I-014 Reemplazar o complementar `pain_points_detected` con dos capas**
  - `observed_signals`
  - `inferred_opportunities`
  - **Criterio de cierre:** el sistema diferencia claramente evidencia observada de hipótesis comerciales.

- [ ] **I-015 Acotar el lenguaje de inferencia**
  - Evitar afirmaciones demasiado agresivas o no defendibles.
  - Etiquetar todo insight hipotético como oportunidad o riesgo probable, no como hecho.
  - **Criterio de cierre:** el output comercial es más honesto y menos “inventado con elegancia”.

### I.6. Taxonomía comercial controlada

- [ ] **I-016 Definir taxonomía cerrada para nicho y tipo de negocio**
  - `taxonomy_top_level`
  - `taxonomy_business_type`
  - **Criterio de cierre:** `inferred_niche` deja de ser solo texto libre y se vuelve filtrable.

- [ ] **I-017 Alinear parser, heurística, IA y API con la taxonomía**
  - Evitar etiquetas distintas para el mismo tipo de entidad.
  - **Criterio de cierre:** negocio, directorio y medio quedan clasificados con consistencia entre capas.

### I.7. Testing, fixtures y rollout

- [ ] **I-018 Crear fixtures de casos reales problemáticos**
  - Negocio real.
  - Directorio.
  - Comparador.
  - Medio.
  - Asociación/listado.
  - Contacto inconsistente.
  - Ubicación contaminada.
  - Teléfono falso tipo fecha.
  - **Criterio de cierre:** los percances observados quedan cubiertos por tests reproducibles.

- [ ] **I-019 Medir impacto de la nueva clasificación**
  - KPIs:
    - baja de `accepted` no objetivo;
    - baja de emails inconsistentes;
    - baja de teléfonos falsos;
    - mayor precisión de `accepted_target`.
  - **Criterio de cierre:** la mejora se valida con métricas, no solo con impresiones.

- [ ] **I-020 Hacer rollout por capas**
  - Etapa 1: solo clasificar y observar.
  - Etapa 2: penalizar score.
  - Etapa 3: rechazar duro ciertos tipos.
  - Etapa 4: exponer nuevos campos en API pública.
  - **Criterio de cierre:** el cambio se despliega sin romper compatibilidad ni sorprender al consumidor.

---

## 7. Orden recomendado de implementación

### Etapa 1. Ver sin romper

1. `I-001`
2. `I-002`
3. `I-003`
4. `I-018`

### Etapa 2. Endurecer calidad de datos

1. `I-008`
2. `I-009`
3. `I-010`
4. `I-011`
5. `I-012`
6. `I-013`

### Etapa 3. Afinar decisión comercial

1. `I-004`
2. `I-005`
3. `I-006`
4. `I-007`
5. `I-019`

### Etapa 4. Hacer más honesto el enriquecimiento

1. `I-014`
2. `I-015`
3. `I-016`
4. `I-017`
5. `I-020`

---

## 8. Ejemplos de clasificación deseada

### Negocio real

- `entity_type_detected = direct_business`
- `is_target_entity = true`
- `acceptance_decision = accepted_target`

### Directorio / listado

- `entity_type_detected = directory`
- `is_target_entity = false`
- `acceptance_decision = rejected_directory`

### Comparador / agregador

- `entity_type_detected = aggregator`
- `is_target_entity = false`
- `acceptance_decision = rejected_directory` o `accepted_related` según uso interno

### Medio / artículo

- `entity_type_detected = media` o `blog_post`
- `is_target_entity = false`
- `acceptance_decision = rejected_media` o `rejected_article`

---

## 9. Definición de éxito

Se considerará exitoso este plan cuando:

- el sistema deje de aceptar como prospecto objetivo páginas que solo hablan del nicho;
- los contactos principales tengan validación fuerte y menos contaminación;
- `location` y `validated_location` ya no mezclen texto crudo con dato limpio;
- el consumidor pueda distinguir observaciones de inferencias;
- exista taxonomía cerrada suficiente para filtrar por tipo de entidad;
- los casos problemáticos actuales estén cubiertos por fixtures y tests.
