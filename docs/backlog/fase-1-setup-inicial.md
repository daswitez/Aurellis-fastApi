# Fase 1: Setup Inicial y Modelado (MVP)

**Objetivo:** Tener la base del código, las dependencias y la base de datos temporal listas para recibir datos.

## Tareas Completadas ✅
- [x] **Setup de Python:** Creación de entorno virtual e instalación de dependencias base (`FastAPI`, `SQLAlchemy`, `Alembic`, `BeautifulSoup4`, `httpx`).
- [x] **Infraestructura MVP:** Creación del `docker-compose.yml` para levantar PostgreSQL y pgAdmin localmente.
- [x] **Modelado de Datos (SQLAlchemy):** Definición de las entidades `ScrapingJob`, `Prospect`, `ProspectSignal` y `ScrapingLog`.
- [x] **Configuración de Migraciones:** Configurar Alembic para funcionar de manera asíncrona (`asyncpg`) e integrarlo con los modelos.
- [x] **API Base:** Creación de `app/main.py` con endpoint de diagnóstico (`GET /health`).
- [x] **Documentación Quickstart:** Guía paso a paso para que cualquier desarrollador pueda clonar y levantar el proyecto.

## Tareas Pendientes o Bloqueadas 🚧
- [ ] **Levantar Base de Datos Local:** Resolver problema de la máquina host con Docker (`docker compose up -d postgres`).
- [ ] **Correr Migraciones:** Ejecutar `alembic upgrade head` exitosamente para que las 4 tablas principales existan en la BD local.

> **Nota Crítica:** Hasta que las tablas no existan físicamente en Postgres, no podemos iniciar la persistencia de la **Fase 2**.

---
*Transición: Una vez la base de datos local reciba conexiones de FastAPI, pasamos directamente a construir el motor de Scraping empírico.*
