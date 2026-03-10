# Guía de Inicio Rápido (Quickstart)

Bienvenido compañero! Si acabas de clonar el repositorio del **Servicio de Scraping y Enriquecimiento de Prospectos**, este es el documento que debes leer para levantar el proyecto localmente.

### Contexto Rápido
Este repositorio contiene un servicio en **FastAPI** especializado en buscar prospectos B2B en internet, limpiar los datos estructurados, enriquecerlos y dejarlos listos en una base de datos para consumo del Backend principal (NestJS).

---

## 🚀 Requisitos Previos

Asegúrate de tener instalados en tu computadora:

1. **Python 3.10+** (Se recomienda 3.12).
2. **Docker y Docker Compose** (Para la base de datos local).
3. **Manejador de entornos de Python** (como `venv`).

---

## 🛠️ Pasos para Iniciar el Proyecto

### 1. Clona y entra al repositorio
```bash
git clone <url-del-repositorio>
cd aurellis-fastApi
```

### 2. Configura tu Entorno Virtual
Crea y activa tu entorno virtual para evitar que las dependencias choquen con tu sistema.
```bash
python3 -m venv venv

# En Linux o macOS:
source venv/bin/activate

# En Windows (Git Bash / PowerShell):
.\venv\Scripts\activate
```

### 3. Instala las Dependencias
Con el entorno virtual activado (`(venv)` en tu consola), instala todas las librerías necesarias:
```bash
pip install -r requirements.txt
```

### 4. Configurar Variables de Entorno
Copia el archivo base y ajusta las variables de entorno de ser necesario (para la BD local los valores por defecto funcionarán).
```bash
cp .env.example .env
```
*(Si `.env.example` no existe, crea un archivo `.env` vacío o usa la URI predeterminada definida en `app.config`)*.

### 5. Levanta la Base de Datos con Docker
Para las pruebas de aislamiento estamos usando una base de datos PostgreSQL temporal y la interfaz pgAdmin, levantadas vía Docker.
```bash
docker-compose up -d
```
*(Esto descargará la imagen de Postgres y la dejará trabajando en el puerto `5432`)*.

### 6. Aplica las Migraciones de la Base de Datos
Necesitamos construir las tablas (`scraping_jobs`, `prospects`, etc.) en la base de datos levantada usando *Alembic*.
```bash
alembic upgrade head
```

### 7. Inicia el Servidor de Desarrollo
Finalmente, lanza uvicorn en modo de recarga.
```bash
uvicorn app.main:app --reload
```

---

## ✅ Verifica que Funcione

Abre tu navegador (o Postman) y accede a:

- **Health Check:** `http://localhost:8000/health` (Deberías ver un JSON `{"status": "ok"}`).
- **Documentación Interactiva Swagger:** `http://localhost:8000/docs`.

---

## 📚 Siguiente Paso
Si quieres entender cómo funciona exactamente la lógica, ve a la carpeta principal `/docs/README.md`, allí explicamos la arquitectura, el modelado y las fases del proyecto con mayor detalle.
