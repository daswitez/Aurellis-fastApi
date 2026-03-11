# Evidencia, Enriquecimiento y Pipeline

**Objetivo:** mejorar explicabilidad, debugging y valor comercial del pipeline sin volverlo opaco ni fragil.

---

## 1. Problema actual

Las inferencias ya son mas honestas que antes, pero todavia falta responder mejor:

- que pagina disparo una senal;
- que texto o estructura la sustenta;
- que tipo de pagina fue;
- si el sitio parece single-location, cadena, comparador o media.

---

## 2. Objetivos funcionales

### Objetivo A

Agregar evidencia textual y estructural util para auditoria.

### Objetivo B

Explicitar el pipeline por etapas para que crezca sin mezclas.

### Objetivo C

Capturar enrichment comercial adicional solo cuando la base ya sea confiable.

---

## 3. Backlog propuesto

### P-001 Agregar `signal_evidence`

Estructura sugerida:

- `signal`
- `evidence_type`
- `page`
- `snippet`
- `confidence`

**Criterio de cierre:** cada senal importante puede trazarse a una fuente visible.

### P-002 Agregar `evidence_snippets`

Guardar snippets cortos y relevantes, no dumps enormes.

**Criterio de cierre:** debugging y UI pueden mostrar evidencia textual concreta.

### P-003 Agregar `source_pages`

Listar paginas que aportaron evidencia:

- homepage
- contact
- services
- booking
- pricing
- about

**Criterio de cierre:** se sabe donde se construyo el perfil del prospecto.

### P-004 Clasificador de roles de pagina

Relacionarlo con `page_roles_detected` y usarlo para:

- contacto;
- pricing;
- booking;
- testimonials;
- content editorial;
- listing.

**Criterio de cierre:** no tratar igual una homepage y una pagina de articulo.

### P-005 Deteccion de business model

Complementar `entity_type_detected` con un clasificador de modelo de negocio.

**Criterio de cierre:** el sistema distingue tipo de entidad de modelo comercial.

### P-006 Deteccion de chain / multi-location

Agregar:

- `location_count_detected`
- `chain_size_signal`
- `multi_location_status`

Valores sugeridos:

- `single_location`
- `multi_location`
- `chain_like`
- `national_presence`

**Criterio de cierre:** el sistema puede personalizar mejor outreach para cadenas o sedes multiples.

### P-007 Madurez digital

Senales iniciales:

- `has_reviews_or_testimonials`
- `has_booking_flow`
- `has_pricing_page`
- `has_whatsapp_cta`
- `has_meta_ads_pixel`
- `has_google_analytics`
- `has_gtm`
- `has_chat_widget`
- `has_online_shop`
- `has_instagram_presence`
- `has_before_after_content`
- `has_video_content`
- `has_multilocation_structure`

Scores futuros:

- `social_presence_score`
- `digital_maturity_score`
- `conversion_maturity_score`

**Criterio de cierre:** el motor ya no solo dice "que es", tambien "que tan madura parece la presencia digital".

### P-008 Pipeline por etapas explicito

Separar mental y tecnicamente:

1. discovery
2. entity classification
3. contact extraction
4. business enrichment
5. opportunity inference
6. action readiness

**Criterio de cierre:** el crecimiento del pipeline deja de depender de un unico payload monolitico.

### P-009 Snapshots de debug internos

Para uso interno, no publico por defecto:

- screenshot homepage
- screenshot contact page
- DOM summary
- text summary por pagina

**Criterio de cierre:** debugging visual y analisis de errores complejos mejoran sin depender solo de logs.

---

## 4. Modulos probablemente afectados

- `app/scraper/engine.py`
- `app/scraper/parser.py`
- `app/services/prospect_quality.py`
- `app/services/heuristic_extractor.py`
- `app/services/ai_extractor.py`
- `app/services/db_upsert.py`
- `app/models.py`
- `tests/test_ai_observability.py`

---

## 5. Orden interno sugerido

1. `P-001`
2. `P-002`
3. `P-003`
4. `P-004`
5. `P-005`
6. `P-006`
7. `P-007`
8. `P-008`
9. `P-009`

---

## 6. Criterio de exito

Se considera bien ejecutado si:

- cada inferencia importante puede mostrarse con evidencia;
- el sistema sabe mejor que paginas aportaron valor;
- aparecen señales de madurez digital utiles para segmentacion;
- el pipeline queda mas escalable para futuras etapas.
