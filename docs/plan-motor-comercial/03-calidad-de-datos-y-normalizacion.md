# Calidad de Datos y Normalizacion

**Objetivo:** hacer mas confiable la data de contacto, ubicacion y presencia publica sin mezclar confianza con validez real.

---

## 1. Problemas actuales

### Contacto

- hay telefonos dudosos que todavia pueden verse demasiado confiables;
- falta distinguir validez vs confianza;
- falta inferencia de pais y plausibilidad local del numero.

### Ubicacion

- el parser todavia puede tomar calles como ciudad;
- puede tomar zonas institucionales como region;
- falta parseo conservador por componentes;
- falta inteligencia postal local.

### Presencia publica

- la extraccion social todavia es debil;
- faltan schemas y paginas auxiliares que mejoren contexto.

---

## 2. Objetivos funcionales

### Objetivo A

Separar validez del contacto de la confianza de extraccion.

### Objetivo B

Separar mejor direccion callejera, ciudad, provincia, region y pais.

### Objetivo C

Enriquecer presencia social y schema sin disparar ruido.

---

## 3. Backlog propuesto

### D-001 Agregar estados de validez de contacto

Nuevos campos:

- `contact_validity_status`
- `email_validity_status`
- `phone_validity_status`

Valores:

- `valid`
- `suspicious`
- `invalid`
- `unknown`

**Criterio de cierre:** un telefono puede ser `medium confidence` pero `invalid`, y eso queda visible.

### D-002 Integrar validacion seria de telefono

Usar una libreria tipo `phonenumbers` para:

- parseo regional;
- validacion por pais;
- chequeo de longitud plausible;
- normalizacion E.164 cuando aplique;
- inferencia de pais probable.

Nuevos campos:

- `phone_country_inferred`
- `phone_normalization_source`

**Criterio de cierre:** IDs, fechas y basura numerica dejan de verse como telefonos medianamente validos.

### D-003 Endurecer validacion de email

Cruzar:

- match de dominio;
- fuente de extraccion;
- ubicacion de pagina (`contact`, footer, structured data, texto libre);
- genericidad del mailbox;
- si es visible o estructurado.

**Criterio de cierre:** mejor separacion entre email util, sospechoso y basura.

### D-004 Redefinir parseo de ubicacion

Pasar de un parseo compacto a componentes mas conservadores:

- `street_address`
- `city`
- `province_or_state`
- `region`
- `country`
- `postal_code`
- `location_source`
- `location_parse_confidence`

**Criterio de cierre:** una calle no vuelve a terminar en `city`.

### D-005 Integrar inteligencia postal local

Empezar por Espana si es mercado prioritario:

- mapping postcode -> ciudad;
- mapping postcode -> provincia;
- reglas de consistencia postcode / provincia.

**Criterio de cierre:** el postcode ayuda a corregir ambiguedades reales en ubicacion.

### D-006 Mejorar extraccion de social presence

Buscar en:

- header;
- footer;
- about;
- contact;
- OG metadata;
- JSON-LD;
- icon links;
- widgets embebidos.

Guardar:

- `platform`
- `url`
- `confidence`
- `source_page`

**Criterio de cierre:** menos falsos "sin redes visibles" cuando si habia evidencia razonable.

### D-007 Ampliar deteccion de schema types

Agregar soporte fuerte para:

- `MedicalClinic`
- `LocalBusiness`
- `Physician`
- `BeautySalon`
- `ItemList`
- `FAQPage`
- `Product`
- `Service`
- `AggregateRating`
- `Review`

**Criterio de cierre:** mejor entidad, mejor taxonomia y mejor deteccion de directorios.

### D-008 Agregar `page_roles_detected`

Clasificar paginas observadas como:

- `homepage`
- `about`
- `services`
- `contact`
- `booking`
- `pricing`
- `testimonials`
- `blog_article`
- `directory_listing`

**Criterio de cierre:** el pipeline sabe mejor que tipo de contenido vio realmente.

---

## 4. Modulos probablemente afectados

- `app/scraper/parser.py`
- `app/services/prospect_quality.py`
- `app/scraper/engine.py`
- `app/services/db_upsert.py`
- `app/models.py`
- `app/api/schemas.py`
- `tests/test_parser_and_quality.py`
- `tests/test_commercial_fixtures.py`

---

## 5. Orden interno sugerido

1. `D-001`
2. `D-002`
3. `D-003`
4. `D-004`
5. `D-005`
6. `D-006`
7. `D-007`
8. `D-008`

---

## 6. Casos de validacion minimos

- `10508037` no debe terminar como telefono util;
- `Calle Edgar Neville` no debe terminar en `city`;
- una zona institucional no debe terminar en `region` por defecto;
- un social link en footer debe poder ser detectado con confianza razonable.
