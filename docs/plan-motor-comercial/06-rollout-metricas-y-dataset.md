# Rollout, Metricas y Dataset

**Objetivo:** implementar las mejoras sin romper el contrato, con medicion clara y base para calibracion futura.

---

## 1. Principio

No conviene meter todas las mejoras en un unico salto.

Hay que desplegar por capas:

- primero precision base;
- despues calidad de datos;
- luego scores y readiness;
- luego evidencia y enrichment;
- luego calibracion y metricas historicas;
- y solo a muy largo plazo evaluar si ML tiene sentido.

---

## 2. Rollout recomendado

### R-1 Observacion y dataset

Antes de endurecer decisiones:

- guardar nuevos campos en traces o evidence;
- ampliar fixtures;
- etiquetar casos reales;
- medir baseline actual.

### R-2 Modo dual

Calcular nuevas decisiones y scores sin hacerlas todavia definitivas para API publica.

Ejemplos:

- `entity_type_detected_v2`
- `acceptance_decision_v2`
- `taxonomy_v2`
- `readiness_v1`

### R-3 Activacion parcial

Activar primero:

- rechazo de agregadores claros;
- taxonomia unica;
- estados de validez de contacto;
- parseo de ubicacion mejorado.

### R-4 Activacion publica

Exponer:

- readiness;
- blockers;
- sub-scores;
- evidencia resumida;
- business model.

### R-5 Calibracion continua

- ajustar thresholds;
- revisar falsos positivos y falsos negativos;
- preparar dataset y metricas para decisiones futuras.

### R-6 Exploracion opcional de largo plazo

- evaluar benchmarks contra el motor actual;
- usar ML solo para ranking o desempate si demuestra mejora real;
- no reemplazar la logica deterministica de acceptance mientras no exista evidencia fuerte.

---

## 3. Metricas que deberian agregarse

### Precision comercial

- `accepted_target_precision`
- `accepted_non_target_rate`
- `ambiguous_entity_rate`
- `aggregator_escape_rate`

### Calidad de datos

- `valid_phone_rate`
- `invalid_phone_rate`
- `suspicious_phone_rate`
- `valid_email_rate`
- `invalid_email_rate`
- `location_parse_success_rate`
- `location_parse_conflict_rate`

### Readiness

- `outreach_ready_rate`
- `blocked_by_contact_rate`
- `blocked_by_entity_rate`
- `blocked_by_location_rate`

### Explicabilidad

- `% with signal_evidence`
- `% with source_pages`
- `% with page_roles_detected`

---

## 4. Dataset recomendado

Crear un dataset etiquetado con columnas como:

- `domain`
- `expected_entity_type`
- `expected_acceptance_decision`
- `expected_taxonomy_top_level`
- `expected_business_type`
- `expected_business_model`
- `expected_phone_validity_status`
- `expected_email_validity_status`
- `expected_outreach_ready`

Y clases minimas:

- direct business real;
- directory;
- aggregator;
- media;
- association;
- chain;
- single location;
- ambiguous.

---

## 5. Fixtures que conviene ampliar

Agregar fixtures reales o sinteticos para:

- directorio con schema `ItemList`;
- comparador con textos de ranking;
- clinica real con booking y pricing;
- cadena multi-location;
- pagina con telefono invalido pero contacto valido;
- pagina con postcode espanol corregible;
- pagina con redes solo en footer;
- pagina con testimonials claros;
- pagina media / article bien marcada.

---

## 6. Criterios de cierre por capa

### Capa 1. Precision de entidad

- baja clara de falsos `accepted_target`;
- `todoestetica.com` y `comparaclinic.com` ya no pasan como target.

### Capa 2. Taxonomia

- no hay duplicados entre root y `generic_attributes`;
- taxonomia visible sale de una sola fuente.

### Capa 3. Calidad de datos

- telefonos sospechosos o invalidos quedan marcados;
- parseo de ciudad/provincia mejora en casos reales.

### Capa 4. Readiness

- existe filtro usable por `outreach_ready`;
- `blocking_reasons` explica por que un lead bueno no esta listo.

### Capa 5. Evidencia

- inferencias importantes tienen snippets o source pages;
- debugging depende menos de inspeccion manual del HTML.

---

## 7. Relacion con ML futuro

ML no forma parte del plan inmediato.

Primero cerrar:

- etiquetas;
- taxonomia estable;
- criterios de aceptacion claros;
- dataset con errores historicos;
- metricas de precision y recall comercial.

Cuando eso exista, y solo si sigue habiendo un problema que las reglas no resuelven bien, recien vale la pena evaluar:

- clasificador hibrido de entidad;
- predictor de contactabilidad;
- ranking de prioridad comercial.

Regla recomendada:

- no usar ML para decidir aceptacion dura en esta etapa;
- si se explora, empezar por ranking, desempate o scoring auxiliar;
- mantener siempre una version explicable y auditable basada en reglas.
