# Fase 4: Validación Empírica, Ajustes y Evasión

**Objetivo:** Esta es la verdadera "Prueba de Fuego". Pondremos la API a sacar prospectos de la vida real (directorios, listados comerciales, páginas variadas) para evaluar bloqueos (WAFs, Cloudflare, Captchas) y la calidad comercial de la data obtenida.

## 4.1. Creación de Scripts de Prueba ("Runners")
- [ ] Armar sets de pruebas masivas (ej. un JSON con 100 URLs variadas de PYMES o agencias locales).
- [ ] Disparar Jobs contra estos sets usando la API.

## 4.2. Evaluación de Calidad (Data Cleaning final)
- [ ] Revisar qué % de emails se consiguieron.
- [ ] Ajustar las Expresiones Regulares si estamos trayendo *"emails"* falsos (ej. `example@example.com`, `sentry@...`).
- [ ] Evaluar tiempos: ¿Está tardando mucho el job? Implementar llamadas asíncronas concurrentes (ej. `asyncio.gather`) limitando la cantidad en paralelo con Semáforos (`asyncio.Semaphore(10)`) para no matar nuestra propia red local.

## 4.3. Implementación de Técnicas Evasivas y Sitios Dinámicos
Si experimentamos altas tasas de error (Código 403 Forbidden, 429 Too Many Requests):

- [ ] **Renderizado de Javascript:** Sitios SPA (React/Vue/Angular) no mostrarán su HTMl puro. De ser estrictamente necesario para nuestras fuentes, instalar y configurar **Playwright** para ejecutar un navegador *headless* que renderice la página antes de extraer datos.
- [ ] **Control de Tasa (Rate Limiting):** Introducir demoras arbitrarias (`asyncio.sleep(1 a 3 segundos)`) entre petición y petición al mismo dominio principal.
- [ ] **Discusión de Proxies:** Si las medidas anteriores fallan porque nuestra IP local es bloqueada, realizar un informe sugiriendo la contratación de Proxies Rotativos comerciales y documentar cómo se introducirían en este script.

## 4.4. Cierre del MVP
- [ ] Demostración local: Hacer un ciclo completo de Búsqueda -> Jobs -> Extracción -> Upserts -> Visualización del JSON.
- [ ] Refinar los esquemas JSON de salida (Pydantic Models) asegurando que este es el formato definitivo que NestJS recibirá.
