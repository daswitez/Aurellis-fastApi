# Arquitectura Temporal (Fase de Validación)

Durante el paso de investigación y validación del scraping (MVP), la arquitectura estará deliberadamente simplificada. El objetivo no es escalar ni soportar tráfico de usuarios reales, sino maximizar la agilidad para iterar sobre las herramientas de extracción y probar qué datos podemos obtener fiablemente.

## Diagrama de Componentes MVP

1. **Cliente de Prueba (Desarrollador)**
   - Herramientas locales como Postman, cURL, o scripts Python/Jupyter Notebooks.
   - Envían peticiones directas de extracción a los endpoints expuestos en FastAPI.

2. **Backend FastAPI (Standalone)**
   - Todo el proceso corre dentro de este servicio.
   - Las rutas exponen la iniciación de los trabajos de recolección.
   - Por ahora, los trabajos de scraping pueden ejecutarse utilizando `BackgroundTasks` nativos de FastAPI para no bloquear la respuesta HTTP. No se introduce todavía Celery/Redis para mantener la configuración simple.
   - Modulos internos: Parsing (BeautifulSoup/lxml), Networking (httpx / Playwright).

3. **Base de Datos Temporal Diferida (Docker)**
   - Contenedor de PostgreSQL (y posiblemente pgAdmin) orquestado por un `docker-compose.yml`.
   - Se encarga de emular la estructura de tablas para guardar los prospectos, jobs y logs generados.
   - Los datos recogidos aquí son únicamente de pruebas.

## Flujo de Ejecución Temporal
1. El desarrollador lanza un Request al API local: `POST /scrape/prospects` con unos filtros simples.
2. El API de FastAPI crea un registro "job" en la base de datos Docker.
3. Se encola la función de scraping en segundo plano (`BackgroundTask`).
4. FastAPI responde al momento con un `{"job_id": 123, "status": "running"}`.
5. El job en segundo plano va hacia las fuentes externas, descarga el HTML, parsea la info, limpia los datos.
6. El job guarda los `prospects` logrados en PostgreSQL Docker y marca el job como `completed`.
7. El desarrollador revisa los resultados en DB o a través de `GET /jobs/123/results` para verificar su eficacia.

## Decisiones Técnicas Transitorias
- **No Supabase todavía**: Permite equivocarse y rehacer la base de datos rompiéndola repetidas veces mediante Docker muy rápidamente.
- **BackgroundTasks vs Colas (Worker)**: Para la fase de experimentación con un nivel bajo de concurrencia, `BackgroundTasks` es suficiente y evita la configuración de un broker externo.
- **Sin Autenticación**: Los endpoints estarán abiertos internamente (localhost) para facilitar la experimentación rápida.
