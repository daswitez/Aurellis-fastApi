# Fase 5: Integración Oficial (Producción)

**Objetivo:** Transicionar el motor de validación local (Docker + MVP aislado) a la arquitectura definitiva de la plataforma SaaS SaaS, conectándose a la base de datos real en Supabase y orquestándose desde NestJS.

## 5.1. Conexión a Supabase (PostgreSQL)
- [ ] Eliminar el archivo `docker-compose.yml` local.
- [ ] Obtener del equipo el `DATABASE_URL` del pooler de conexiones de Supabase (modo Transaction / IPv4).
- [ ] Ajustar el archivo `.env` oficial del proyecto.
- [ ] Actualizar en Supabase los esquemas para que las 4 tablas de scraping (`scraping_jobs`, `prospects`, etc.) coexistan o pertenezcan a un esquema específico (`scraping_schema` u `public`).
- [ ] Ejecutar las migraciones finales de Alembic dirigiéndolas hacia Supabase.

## 5.2. Seguridad HTTP (S2S: Server-to-Server)
- [ ] Implementar un *Middleware* o dependencia de seguridad rápida en FastAPI que exija un header `X-Internal-Token` o `Authorization: Bearer <static_token>` en todos los endpoints, para rechazar que usuarios públicos invoquen nuestro motor de scraping. Este token solo lo tendrá NestJS.

## 5.3. Comunicación NestJS -> FastAPI
- [ ] Desarrollar en NestJS el controlador/servicio que al requerir prospectos haga una petición síncrona/asíncrona a `POST fastapi-url.com/api/v1/jobs/scrape`.
- [ ] Manejar la respuesta del Job ID del lado de NestJS.

## 5.4. Polling o Webhooks para Resultados
Actualmente FastAPI hace el trabajo en background. NestJS necesita saber cuándo terminó para mostrarle los datos al usuario de la plataforma SaaS.

- [ ] **Opción A (Polling):** NestJS llama a `GET /api/v1/jobs/{job_id}` cada 5-10 segundos hasta que diga `COMPLETED`.
- [ ] **Opción B (Webhooks):** FastAPI, al terminar el background task, hace un `POST nestjs-url.com/webhooks/scraping-done` pasándole el Job ID y notificando el éxito de la tarea. *(Recomendado para producción)*.

## 5.5. Escalabilidad (Opcional post-lanzamiento)
- [ ] Si las `BackgroundTasks` saturan la RAM del propio servidor de FastAPI al tener 50 clientes scrapeando al mismo tiempo, migrar el "Motor de Scraping" de FastAPI a *Celery Workers* o construir un worker en Node con *BullMQ* gestionado desde NestJS directamente, dejando a Python solo las funciones puras de extracción de texto.

---
🍾 **Con esta fase terminada, el Servicio de Scraping habrá completado su propósito dentro de la arquitectura corporativa.**
