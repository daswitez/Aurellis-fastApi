# Arquitectura Técnica

## Principios técnicos

### 1. Servicio especializado
Este backend debe mantenerse enfocado en scraping, parsing, normalización y enriquecimiento. No debe asumir la lógica principal de negocio del producto.

### 2. Procesamiento desacoplado
Las operaciones de scraping no deben bloquear a la API principal ni depender de respuestas síncronas largas.

### 3. Modularidad
Cada fuente, parser y capa de limpieza debe estar separada en componentes reutilizables.

### 4. Tolerancia a fallos
Las fuentes externas son inestables. El sistema debe manejar errores parciales sin comprometer toda la ejecución.

### 5. Persistencia estructurada
La salida debe ser útil para el sistema principal. No se deben almacenar blobs caóticos sin estructura.

### 6. Escalabilidad progresiva
La primera versión debe ser simple, pero diseñada para permitir agregar workers, colas y nuevas fuentes sin reescritura total.

## Arquitectura recomendada

### Stack sugerido

- **FastAPI** para exponer endpoints internos
- **Uvicorn** como servidor ASGI
- **Pydantic** para validación y esquemas
- **httpx** para requests HTTP
- **BeautifulSoup / lxml** para parseo HTML
- **Playwright** para sitios dinámicos cuando sea necesario
- **Redis** para colas o coordinación futura
- **Celery o RQ** para tareas asíncronas si el volumen lo requiere
- **PostgreSQL** como base de datos compartida del sistema
- **SQLAlchemy** o acceso directo bien controlado para persistencia
- **Render** para despliegue inicial

## Arquitectura lógica

- **API Layer**: Recibe solicitudes, valida payloads, expone endpoints internos y devuelve estados.
- **Job Layer**: Coordina la ejecución de trabajos de scraping, controla estados y errores.
- **Discovery Layer**: Normaliza intención de búsqueda, construye queries canónicas y clasifica hallazgos SERP.
- **Source Layer**: Contiene conectores o scrapers específicos por fuente.
- **Parsing Layer**: Extrae datos relevantes de HTML, páginas de contacto, metadatos, JSON-LD y contenido visible.
- **Normalization Layer**: Limpia y estandariza los datos recolectados.
- **Quality Layer**: Valida ubicación, idioma, calidad de contacto y clasifica el lead.
- **Enrichment Layer**: Agrega señales comerciales y decide si vale llamar a IA.
- **AI Layer**: Consume un `evidence pack` compacto, aplica cache por firma y devuelve enriquecimiento solo cuando pasa el gate heurístico.
- **Persistence Layer**: Guarda resultados, logs y estados en la base de datos.

## Flujo general

1. La API principal solicita una búsqueda de prospectos.
2. Este servicio recibe los criterios de scraping.
3. Se crea o valida un job.
4. El servicio normaliza la intención de discovery y construye hasta 3 queries canónicas.
5. Consulta fuentes relevantes y conserva metadata SERP del hallazgo.
6. Identifica sitios y páginas internas a visitar.
7. Extrae datos útiles de cada prospecto.
8. Limpia, normaliza y valida ubicación/idioma/contacto.
9. Calcula baseline heurístico y gate de calidad.
10. Solo si el lead lo amerita, llama a IA con un `evidence pack` compacto.
11. Guarda resultados, evidencia y estado de calidad en la base de datos.
12. El sistema principal consulta o consume los resultados aceptados.

## Módulos clave actuales

- `app/api/jobs.py`: creación de jobs, discovery normalizado, worker y filtros de `/results`.
- `app/api/schemas.py`: contrato Pydantic de entrada/salida y campos públicos de calidad.
- `app/models.py`: persistencia SQLAlchemy de prospectos, jobs y quality status.
- `app/services/discovery.py`: normalización de intención y construcción de queries canónicas.
- `app/scraper/search_engines/ddg_search.py`: discovery DDG con metadata SERP y exclusiones de ruido.
- `app/scraper/parser.py`: HTML a texto + metadata estructurada (`html lang`, JSON-LD, direcciones, CTA, booking, pricing, WhatsApp, mapas).
- `app/scraper/engine.py`: crawl limitado, evaluación de calidad, gate IA y score final.
- `app/services/prospect_quality.py`: validación geo/idioma/contacto, clasificación de calidad y armado del `evidence pack`.
- `app/services/heuristic_extractor.py`: baseline heurístico comercial reutilizable incluso sin IA.
- `app/services/scoring.py`: combinación estable de heurística, IA y señales de calidad.
- `app/services/ai_extractor.py`: integración DeepSeek con schema, métricas, cache y respuesta compacta.
- `app/services/db_upsert.py`: persistencia de evidencia, canales de contacto, quality status y resultados por job.

Para un inventario más detallado de cambios por archivo, ver [11-mapa-de-modulos-y-cambios-recientes.md](11-mapa-de-modulos-y-cambios-recientes.md).
