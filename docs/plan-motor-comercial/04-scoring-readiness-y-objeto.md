# Scoring, Readiness y Objeto Final

**Objetivo:** separar mejor fit comercial, calidad de datos y accionabilidad del lead, y aterrizar un shape de objeto mas util para backend, UI y priorizacion.

---

## 1. Problema actual

Hoy el motor todavia mezcla demasiado:

- calidad del negocio;
- calidad de los datos;
- potencial de oportunidad;
- readiness para outreach.

Eso hace que un prospecto pueda tener buen score general sin que quede claro:

- si realmente es buen target;
- si tiene contacto usable;
- si la oportunidad esta bien sustentada;
- si esta listo para accion.

---

## 2. Objetivos funcionales

### Objetivo A

Separar score global en sub-scores interpretables.

### Objetivo B

Agregar una capa de readiness accionable.

### Objetivo C

Limpiar el shape del objeto para evitar redundancias.

---

## 3. Backlog propuesto

### S-001 Separar score global

Agregar:

- `target_fit_score`
- `data_quality_score`
- `opportunity_score`
- `overall_score`

**Criterio de cierre:** el sistema puede explicar si un lead bajo fue por mal fit o por data incompleta.

### S-002 Agregar capa de outreach readiness

Agregar:

- `outreach_readiness_score`
- `outreach_ready`
- `blocking_reasons`

Ejemplos de blockers:

- `missing_email`
- `invalid_phone`
- `entity_ambiguous`
- `weak_location`
- `insufficient_business_context`

**Criterio de cierre:** el consumidor puede filtrar leads listos para accion.

### S-003 Separar `detected_gaps`

Dejar tres capas:

- `observed_signals`
- `detected_gaps`
- `inferred_opportunities`

**Criterio de cierre:** `pain_points_detected` deja de duplicar oportunidades inferidas.

### S-004 Deprecar `pain_points_detected`

Mantenerlo solo como alias transitorio hasta migrar consumidores.

**Criterio de cierre:** la semantica principal ya vive en las tres capas nuevas.

### S-005 Redefinir objeto ideal del prospecto

Agrupar campos por dominios:

- `entity`
- `taxonomy`
- `contact`
- `location`
- `signals`
- `scores`
- `readiness`
- `evidence`

**Criterio de cierre:** el objeto deja de mezclar campos planos con redundancias faciles de romper.

### S-006 Agregar `lead_priority_tier`

Tier de uso practico:

- `high`
- `medium`
- `low`
- `review`

Basado en:

- fit;
- data quality;
- readiness;
- decision comercial.

**Criterio de cierre:** se puede priorizar sin obligar al consumidor a interpretar 15 campos.

---

## 4. Shape recomendado de alto nivel

```json
{
  "entity": {},
  "taxonomy": {},
  "contact": {},
  "location": {},
  "signals": {},
  "scores": {},
  "readiness": {},
  "evidence": {}
}
```

### Minimo recomendado

- `entity.type`
- `entity.is_target`
- `entity.acceptance_decision`
- `taxonomy.top_level`
- `taxonomy.industry`
- `taxonomy.business_type`
- `contact.email`
- `contact.email_validity_status`
- `contact.phone`
- `contact.phone_validity_status`
- `location.city`
- `location.country`
- `location.location_parse_confidence`
- `signals.observed_signals`
- `signals.detected_gaps`
- `signals.inferred_opportunities`
- `scores.target_fit_score`
- `scores.data_quality_score`
- `scores.opportunity_score`
- `scores.overall_score`
- `readiness.outreach_ready`
- `readiness.outreach_readiness_score`
- `readiness.blocking_reasons`

---

## 5. Modulos probablemente afectados

- `app/services/scoring.py`
- `app/services/prospect_quality.py`
- `app/services/commercial_insights.py`
- `app/services/heuristic_extractor.py`
- `app/services/ai_extractor.py`
- `app/services/db_upsert.py`
- `app/api/schemas.py`
- `app/api/jobs.py`

---

## 6. Orden interno sugerido

1. `S-001`
2. `S-002`
3. `S-003`
4. `S-004`
5. `S-005`
6. `S-006`

---

## 7. Criterio de exito

Se considera bien ejecutado si:

- un lead puede ser gran target pero mala data, y eso queda claro;
- un lead puede ser buen fit pero no outreach-ready, y eso queda claro;
- el objeto se vuelve mas util para UI, dashboards y CRM;
- disminuye la dependencia de interpretar campos tecnicos sueltos.
