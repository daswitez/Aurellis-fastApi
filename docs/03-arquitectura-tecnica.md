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
- **Source Layer**: Contiene conectores o scrapers específicos por fuente.
- **Parsing Layer**: Extrae datos relevantes de HTML, páginas de contacto, metadatos y contenido visible.
- **Normalization Layer**: Limpia y estandariza los datos recolectados.
- **Enrichment Layer**: Agrega señales adicionales útiles para priorización o contexto comercial.
- **Persistence Layer**: Guarda resultados, logs y estados en la base de datos.

## Flujo general

1. La API principal solicita una búsqueda de prospectos.
2. Este servicio recibe los criterios de scraping.
3. Se crea o valida un job.
4. El servicio consulta fuentes relevantes.
5. Se identifican sitios y páginas a visitar.
6. Se extraen datos útiles de cada prospecto.
7. La información se limpia y normaliza.
8. Se eliminan o reducen duplicados.
9. Se guardan resultados en la base de datos.
10. Se actualiza el estado final del job.
11. El sistema principal consulta o consume los resultados.
