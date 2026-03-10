# Funcionalidades Principales

Esta sección detalla qué debe hacer la API para cumplir su objetivo.

## 1. Recibir solicitudes de scraping

La API debe aceptar solicitudes provenientes del backend principal. Cada solicitud representará una búsqueda de prospectos o un job de exploración sobre un segmento concreto.

La solicitud puede incluir criterios como:

- nicho o categoría de negocio
- ubicación geográfica
- palabras clave
- tipo de empresa
- tamaño aparente
- cantidad máxima de resultados
- fuentes permitidas
- filtros opcionales

La API debe crear o reconocer un job de scraping y procesarlo de forma asíncrona o desacoplada del flujo principal.

## 2. Ejecutar scraping sobre fuentes públicas

La API debe ser capaz de consultar fuentes digitales públicas relevantes, tales como:

- sitios web corporativos
- directorios empresariales
- listados públicos
- portfolios
- marketplaces
- páginas de contacto
- perfiles públicos relevantes
- otras fuentes que el producto autorice según el nicho

La extracción debe enfocarse en información visible y utilizable, evitando depender de datos altamente inestables o estructuras demasiado frágiles sin necesidad.

## 3. Visitar y analizar sitios web encontrados

Una vez detectados posibles prospectos, la API debe visitar sus sitios web y extraer información relevante.

Debe poder analizar, cuando sea posible:

- página principal
- página de contacto
- página "about"
- footer
- metadatos básicos
- links externos relevantes
- señales visibles de negocio

El objetivo es enriquecer el perfil del prospecto con contexto suficiente para segmentación y outreach.

## 4. Extraer datos estructurados

La API debe transformar contenido no estructurado en registros consistentes. No basta con recolectar HTML o texto crudo. El servicio debe identificar, separar y mapear datos útiles.

## 5. Limpiar y normalizar la información

Los datos obtenidos de la web suelen llegar incompletos, desordenados o redundantes. La API debe normalizarlos antes de persistirlos.

Ejemplos:

- estandarizar dominios
- limpiar URLs
- normalizar correos
- limpiar nombres de empresa
- convertir cadenas vacías en nulos
- unificar categorías
- deduplicar redes sociales
- normalizar ubicación si es posible

## 6. Deduplicar prospectos

La API debe evitar crear múltiples registros para la misma empresa o contacto cuando eso sea razonablemente detectable.

La deduplicación puede basarse en:

- dominio principal
- email
- nombre de empresa + dominio
- URL canonical
- hash de ciertos campos clave

## 7. Enriquecer prospectos

Además de extraer datos básicos, esta API puede aportar una capa ligera de enriquecimiento para mejorar el valor comercial del registro.

Por ejemplo:

- detectar si tiene formulario de contacto
- detectar si tiene email visible
- detectar si tiene redes sociales
- detectar si tiene sitio moderno o muy desactualizado
- detectar servicios aparentes
- detectar señales de oportunidad comercial
- resumir de forma breve la actividad del negocio

Este enriquecimiento debe ser inicialmente simple y basado en reglas claras. La IA puede incorporarse después en casos concretos.

## 8. Persistir resultados y actualizar estado de jobs

La API debe poder escribir en la base de datos compartida, pero únicamente en el conjunto de tablas o entidades permitidas para su dominio.

Debe registrar:

- estado del job
- tiempo de inicio y fin
- errores
- cantidad de prospectos encontrados
- cantidad de prospectos válidos
- detalles de fuentes consultadas
- resultados finales

## 9. Exponer estado y trazabilidad

La API debe permitir que el backend principal o futuros servicios puedan conocer qué ocurrió durante un scraping.

Eso implica registrar:

- job creado
- job iniciado
- job finalizado
- job fallido
- causas de error
- métricas básicas de ejecución
- logs relevantes por fuente
