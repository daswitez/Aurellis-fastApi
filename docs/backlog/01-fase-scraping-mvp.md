# Backlog: Fase de Validación del Scraping (MVP)

El objetivo de esta fase inicial es construir el servicio de FastAPI de manera aislada para validar su **alcance real**, la calidad de la extracción de datos y sortear los bloqueos (anti-scraping) antes de integrarlo con el backend corporativo en NestJS y la base de datos de producción (Supabase).

## Hito 1: Infraestructura y Setup Base
- [ ] Inicializar el proyecto base (`FastAPI`, `Uvicorn`, `Pydantic`).
- [ ] Configurar el entorno virtual y gestor de dependencias (ej. `Poetry` o `pip`).
- [ ] Crear un archivo `docker-compose.yml` temporal para levantar una base de datos PostgreSQL en un contenedor local.
- [ ] Configurar el ORM (`SQLAlchemy` o `SQLModel`) y las migraciones de esquemas (`Alembic`) conectando a la base de datos local de Docker.
- [ ] Implementar un par de endpoints de diagnóstico (ej. `GET /health`).

## Hito 2: Modelado Inicial de Datos (Local)
- [ ] Crear tablas principales para esta fase: `scraping_jobs`, `prospects`, `prospect_signals` y `scraping_logs`.
- [ ] Configurar relaciones y restricciones (ej. unicidad de dominio) para empezar a testear el comportamiento de la deduplicación a nivel BD.

## Hito 3: Motor de Scraping Básico
- [ ] Seleccionar **1 o 2 fuentes o formatos estáticos objetivo** (ej. lectura directa de páginas About/Contact de listas de dominios).
- [ ] Implementar cliente HTTP con `httpx` (y headers rotativos básicos para evitar bloqueos rápidos).
- [ ] Implementar lógica de parseo básico con `BeautifulSoup` para extraer información como: nombre, correos visibles, teléfonos, enlaces a redes sociales (LinkedIn, Instagram).
- [ ] Crear endpoint de prueba (ej. `POST /scrape/test`) que reciba una URL o un término de búsqueda simple e invoque síncronamente el scraper.

## Hito 4: Limpieza, Normalización y Guardado
- [ ] Desarrollar capa de limpieza de URLs (quitar parámetros, estandarizar "www", cambiar a minúsculas).
- [ ] Desarrollar validación de correos encontrados mediante expresiones regulares.
- [ ] Crear la lógica para insertar o actualizar en la base de datos de Docker evitando duplicar prospectos (`upsert` lógico).
- [ ] Registrar en `scraping_logs` y `scraping_jobs` el éxito o los errores (ej. "Timeout", "Bloqueo por Captcha").

## Hito 5: Scrapers Avanzados y Evaluación de Alcance
- [ ] Probar el scraping contra directorios o fuentes dinámicas (fuentes que cargan mediante JS).
- [ ] Si es necesario, introducir y configurar `Playwright` en el backend para renderizado de JS.
- [ ] **Análisis de factibilidad**: Evaluar los tiempos de ejecución, tasas de acierto/bloqueo, y decidir si se requieren proxies comerciales u otras técnicas de evasión, definiendo así el alcance real del proyecto para la versión de producción.

## Hito 6: Finalización de MVP
- [ ] Crear informe de viabilidad y calidad de datos (qué funciona y qué no).
- [ ] Refactorizar el código para asegurar que los "Scrapers específicos por fuente" están bien modularizados.
- [ ] Definir los contratos (JSON schemas de la request/response) que finalmente consumirá NestJS.
