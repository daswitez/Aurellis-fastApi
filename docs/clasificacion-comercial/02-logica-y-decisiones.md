# Logica y Decisiones

Este documento explica la logica funcional que quedo implementada alrededor del plan comercial.

---

## 1. Clasificacion de entidad

La clasificacion ya no depende de texto libre ni de intuicion posterior al score.

Se resuelve primero con `app/services/entity_classifier.py` usando:

- host y path del dominio;
- `title` y `description`;
- snippet o metadata de discovery;
- `structured_data` tipo `LocalBusiness`, `Dentist`, `ItemList`, `Article`, etc.;
- presencia de contacto, direccion, maps, booking, pricing y servicios;
- patrones editoriales, de directorio, comparador, medio o asociacion.

### Tipos soportados

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

### Regla funcional

- `direct_business`, `agency` y `consultant` se consideran objetivo potencial.
- `directory`, `aggregator`, `marketplace`, `media`, `blog_post` y `association` se consideran no objetivo.

Esto produce:

- `entity_type_detected`
- `entity_type_confidence`
- `entity_type_evidence`
- `is_target_entity`

---

## 2. Calidad tecnica vs decision comercial

La logica actual separa dos capas:

### `quality_status`

Describe si el prospecto es tecnicamente usable:

- `accepted`
- `needs_review`
- `rejected`

La decide `app/services/prospect_quality.py` usando:

- contacto;
- consistencia de email;
- confianza de telefono;
- geografia;
- idioma;
- coverage minimo de evidencia.

### `acceptance_decision`

Describe si comercialmente debe quedar como lead principal, relacionado o rechazado:

- `accepted_target`
- `accepted_related`
- `rejected_directory`
- `rejected_media`
- `rejected_article`
- `rejected_low_confidence`

### Regla importante

Un resultado puede quedar:

- tecnicamente `accepted`
- pero comercialmente `accepted_related` o `rejected_*`

Eso evita que un sitio bien scrapeable pase como prospecto objetivo solo por tener buena estructura.

---

## 3. Contacto y consistencia

La calidad de contacto ya no se limita a detectar si existe un email o un telefono.

`app/services/prospect_quality.py` ahora resuelve:

- `primary_email`
- `primary_phone`
- `contact_consistency_status`
- `primary_email_confidence`
- `primary_phone_confidence`
- `primary_contact_source`

### Regla de consistencia

- si el email coincide con el dominio del sitio, sube a `consistent`;
- si el email parece externo al negocio, baja a `inconsistent`;
- si no hay suficiente evidencia, queda `unknown`.

Esto impacta directo en `quality_status` y en `rejection_reason`.

---

## 4. Telefonos falsos y ruido numerico

`app/scraper/parser.py` filtra telefonos invalidos antes de persistirlos.

Casos filtrados:

- fechas tipo `20260311`;
- secuencias tipo `999999999`;
- formatos con `+` invalido;
- longitudes fuera de rango.

Ahora tambien se contabiliza ese ruido con:

- `phone_validation_rejections`
- `invalid_phone_candidates_count`

Ese dato viaja por:

1. parser;
2. metadata consolidada en `engine`;
3. `raw_extraction_json` y `evidence_json`;
4. metricas comerciales agregadas.

---

## 5. Ubicacion visible vs ubicacion validada

La ubicacion ya no mezcla texto crudo con el campo visible final.

### Campos separados

- `raw_location_text`: evidencia cruda detectada.
- `parsed_location`: estructura parseada.
- `location`: valor visible y normalizado.
- `validated_location`: valor tecnico usado para matching geografico.

### Componentes disponibles

- `city`
- `region`
- `country`
- `postal_code`

### Regla funcional

- `location` es el campo apto para UI.
- `validated_location` solo debe leerse como soporte de matching.
- si no hay target geo o la evidencia no alcanza, puede existir `location` visible sin `validated_location`.

---

## 6. Observado vs inferido

Antes `pain_points_detected` mezclaba hechos con hipotesis.

Ahora se separa en:

- `observed_signals`: observaciones defendibles con evidencia visible;
- `inferred_opportunities`: hipotesis comerciales plausibles.

`app/services/commercial_insights.py` normaliza ambas listas y deja compatibilidad transitoria con `pain_points_detected`.

### Regla de lenguaje

Toda oportunidad inferida debe quedar formulada como posibilidad y no como hecho.

Ejemplo correcto:

- `Posible oportunidad: reforzar CTA principal visible`

---

## 7. Taxonomia de negocio

`app/services/business_taxonomy.py` consolida una taxonomia cerrada comun para heuristica, IA y engine.

Campos visibles:

- `taxonomy_top_level`
- `taxonomy_business_type`

### Objetivo

Evitar que `inferred_niche` quede como texto libre sin control y permitir agrupacion consistente por:

- salud;
- retail;
- food;
- services;
- media;
- marketplace;
- etc.

### Regla funcional

El `engine` recalcula una taxonomia final unica antes de persistir, incluso si heuristica e IA trajeron textos distintos.

---

## 8. Decision final del pipeline

La secuencia funcional actual es:

1. parser extrae metadata;
2. clasificador decide tipo de entidad;
3. quality gate decide calidad tecnica;
4. gate IA decide si vale la pena enriquecer;
5. heuristica o IA aportan senales y taxonomia;
6. scoring aplica score, cap y multiplicadores;
7. persistencia separa entidad canonica y contexto del job;
8. API expone resultado visible y metricas agregadas.

---

## 9. Documentos relacionados

- [01-estado-implementado.md](01-estado-implementado.md)
- [03-contrato-y-metricas.md](03-contrato-y-metricas.md)
- [04-fixtures-tests-y-rollout.md](04-fixtures-tests-y-rollout.md)
