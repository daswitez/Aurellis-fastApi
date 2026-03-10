# Fase 2: Motor de Extracción, Parsing y Guardado

**Objetivo:** Desarrollar los algoritmos core en Python que van a descargar el HTML, limpiarlo, extraer los datos del prospecto y guardarlos sin duplicar en la base de datos temporal.

## 2.1. Clientes HTTP Básicos
- [ ] Construir un cliente HTTP asíncrono genérico usando `httpx.AsyncClient`.
- [ ] Implementar rotación básica de *User-Agents* aleatorios (Desktop/Mobile) en los headers para reducir bloqueos inmediatos.
- [ ] Implementar manejo de errores de conexión (Timeouts, DNS errors) que no rompan la aplicación, sino que los logueen en la consola.

## 2.2. Parseo de HTML (BeautifulSoup)
- [ ] **Extractor de Metadatos:** Scrapear `<title>`, `<meta name="description">` y deducir idioma principal de la página.
- [ ] **Búsqueda de Datos de Contacto:**
  - Encontrar enlaces `mailto:` para extraer correos.
  - Buscar menciones literales de emails mediante Expresiones Regulares (Regex).
  - Encontrar números de teléfono aparentes mediante Regex en el tag `<footer>` o `<header>`.
- [ ] **Detección de Redes Sociales:**
  - Extraer perfiles buscando enlaces de `linkedin.com/company`, `instagram.com`, o `facebook.com`.
- [ ] **Crawler Interno Ligero:**
  - Detectar si la página actual tiene enlaces apuntando a secciones de contacto (ej. `/contacto`, `/about-us`).
  - Visitar esa página de contacto adicional si no se encontró email en la principal.

## 2.3. Extracción de Atributos Genéricos por Industria (Patrones Heurísticos / Código Puro)
Para este MVP de arquitectura temporal, mantendremos los costos en 0, logrando un scraper totalmente en código Python (sin LLMs).
- [ ] **Detección de Stack Tecnológico:** Configurar listas de reglas manuales y regex buscando en el tag `<head>` librerías comunes (Shopify, WordPress, FB Pixel) para llenar el `inferred_tech_stack` y deducir `has_active_ads`.
- [ ] **Búsqueda de Señales de Contratación:** Buscar keywords estáticas en los links y textos como "Careers", "Trabaja con nosotros", "We are hiring" para setear `hiring_signals`.
- [ ] **Matching de Nichos Opcional:** Comparar las palabras pasadas en el context del Job (`target_niche`, `target_pain_points`) con el contenido total del sitio.
- [ ] Guardar las comprobaciones en un JSON en el campo `generic_attributes` (Ej: `{"evaluation_method": "Heuristic Code"}`).

## 2.4. Limpieza y Normalización
- [ ] **Normalizador de URLs:** Convertir URLs absolutas (ej: `https://WWW.EjeMPLo.com/home/?ref=ads`) a un formato limpio y seguro (ej: `ejemplo.com`). 
- [ ] **Limpiador de Textos:** Remover saltos de línea y espacios dobles de las descripciones extraídas.

## 2.5. Integración con Base de Datos (CRUD local)
- [ ] Construir función para guardar/actualizar un `Prospect`. 
- [ ] Implementar **Upsert**: Si el `domain` ya existe en la tabla `prospects`, no debe fallar ni duplicarse, sino actualizar los campos faltantes.
- [ ] Construir funciones para crear registros de `ProspectSignals` asociadas al prospecto encontrado (ej. "Tiene página de contacto: Sí/No").
