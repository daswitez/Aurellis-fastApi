# Plan de Refinamiento de Captura y Recall

**Fecha:** 2026-03-11  
**Objetivo:** aumentar la cantidad de prospectos útiles capturados sin degradar la precisión del quality gate ni disparar el costo de scraping o IA.

---

## 1. Problema actual

El pipeline mejoró mucho en calidad, pero hoy tiene una limitación operativa clara:

- puede procesar correctamente un job;
- puede rechazar leads de forma legítima por geografía o baja calidad;
- pero aun así devolver `[]` en `/jobs/{id}/results` cuando no hubo `accepted`.

Eso no siempre es un bug. Muchas veces es una consecuencia de:

1. `strict geo` funcionando correctamente;
2. discovery todavía con recall bajo;
3. `max_results` actuando como límite de URLs intentadas, no de leads aceptados;
4. consultas de usuario demasiado amplias para que DDG encuentre sitios oficiales bien alineados;
5. filtros de calidad visibles solo al consultar `GET /jobs/{id}` y no al pedir resultados.

El objetivo de este plan es corregir ese desbalance: **capturar más prospectos reales sin bajar el estándar de calidad**.

### Estado de implementación 2026-03-11

Ya quedó implementado el primer bloque operativo del plan:

- `H-001` semántica nueva de captura (`target_accepted_results`, `max_candidates_to_process`);
- `H-002` estrategia de parada por objetivo de aceptados o cap de candidatos;
- `H-003` expansión sistemática de queries;
- `H-004` exclusiones negativas en queries de discovery;
- `H-005` pre-ranking de business-likeness en resultados SERP;
- `H-006` persistencia de exclusiones tempranas en logs del job;
- `H-007` uso de directorios solo como semilla para resolver sitio oficial;
- `H-008` refuerzo de priorización para dominios oficiales;
- `H-009` endurecimiento adicional contra contenido editorial no prospectable;
- `H-010` filtro `quality` en `/results` para auditoría controlada;
- `H-011` `capture_summary` expuesto en `GET /jobs/{id}`;
- `H-012` refuerzo geo con `areaServed`, TLD y prefijos telefónicos.
- `H-013` procesamiento de candidatos por tandas con control de batch;
- `H-014` reapertura incremental de discovery cuando faltan aceptados;
- `H-015` ratio mínimo objetivo/candidatos con default operativo `4x` y piso `5`.
- `H-016` fixtures SERP offline para validar discovery y pre-ranking sin internet;
- `H-017` métricas operativas por job y agregadas para seguir recall/precision;
- `H-018` rollout documentado por etapas con validación incremental del contrato.

---

## 2. Principios de diseño

### 2.1. Precision first

No conviene “resolver” el problema mostrando basura.  
El sistema debe seguir priorizando:

- sitio oficial antes que directorio;
- negocio real antes que artículo o listicle;
- match geográfico fuerte antes que coincidencia textual débil;
- evidencia de contacto y CTA antes que contenido genérico.

### 2.2. Recall controlado

El pipeline no debe detenerse demasiado pronto.  
Si el usuario pide 5 prospectos, el sistema debe intentar suficientes candidatos como para tener probabilidad real de entregar 5 aceptados.

### 2.3. Transparencia operativa

Cuando no haya resultados visibles, la API debe dejar claro si ocurrió alguna de estas situaciones:

- no se encontraron candidatos;
- se encontraron candidatos, pero fueron rechazados;
- hubo `needs_review`, pero el endpoint visible no los muestra;
- hubo fallos de red o anti-bot.

### 2.4. Cost discipline

Para subir recall no hace falta disparar IA ni crawling profundo sobre todo.  
Primero se debe mejorar:

- discovery;
- pre-ranking;
- gating;
- estrategia de parada.

---

## 3. Metas funcionales

### Meta 1

Evitar jobs vacíos por falta de recall cuando el mercado objetivo sí tiene sitios elegibles.

### Meta 2

Separar claramente:

- cuántos candidatos se intentaron;
- cuántos quedaron aceptados;
- cuántos quedaron en revisión;
- cuántos se rechazaron y por qué.

### Meta 3

Permitir que el usuario pida una cantidad objetivo de leads aceptados, no solo una cantidad máxima de URLs a probar.

### Meta 4

Mejorar la calidad del discovery para que el pipeline priorice negocios oficiales y descarte artículos, medios, agregadores y resultados “informativos”.

---

## 4. Cambios de producto y contrato

### 4.1. Semántica nueva del job

Agregar al payload de creación:

- `target_accepted_results: int | null`
- `max_candidates_to_process: int | null`

Regla recomendada:

- `target_accepted_results` = cuántos prospectos `accepted` quiere el usuario;
- `max_candidates_to_process` = tope duro de URLs a intentar para no disparar costo.

Compatibilidad:

- `max_results` puede mantenerse temporalmente como alias legacy de `target_accepted_results` o de `max_candidates_to_process`, pero no debería seguir siendo ambiguo.

### 4.2. Contrato de resultados

Extender `GET /jobs/{id}/results` con filtro de calidad:

- `quality=accepted` por defecto;
- `quality=accepted,needs_review`;
- `quality=all` para auditoría controlada.

Extender `GET /jobs/{id}` con métricas más explícitas de captura:

- `quality_summary` ya existe;
- agregar luego `capture_summary` con:
  - `target_accepted_results`
  - `accepted_so_far`
  - `candidates_processed`
  - `acceptance_rate`
  - `stopped_reason`

### 4.3. Semántica de “job exitoso”

`status=completed` debe seguir significando que el job terminó técnicamente.

Pero el consumidor debe poder distinguir:

- job completado con resultados aceptados;
- job completado sin aceptados;
- job completado con solo `needs_review`.

---

## 5. Arquitectura objetivo

Flujo deseado:

1. Normalizar intención del usuario.
2. Construir queries candidatas.
3. Hacer discovery.
4. Pre-rankear resultados SERP antes de scrapear.
5. Procesar candidatos por tandas.
6. Aceptar, revisar o rechazar.
7. Si todavía no se alcanzó `target_accepted_results`, expandir queries y seguir.
8. Detenerse por objetivo logrado o por límite de candidatos.

---

## 6. Backlog detallado

### H.1. Cambio de semántica de cantidad pedida

- [ ] **H-001 Separar “resultado objetivo” de “candidatos máximos”**
  - Agregar `target_accepted_results` y `max_candidates_to_process` al contrato del job.
  - Mantener compatibilidad temporal con `max_results`.
  - Documentar precedencia y fallback.
  - **Criterio de cierre:** el usuario puede pedir “quiero 5 aceptados” sin asumir que solo se procesarán 5 URLs.

- [ ] **H-002 Cambiar la estrategia de parada del worker**
  - El job no debe frenarse al alcanzar `N` candidatos intentados si todavía no llega a `N` aceptados, salvo que alcance el tope duro.
  - Persistir `stopped_reason` (`target_reached`, `candidate_cap_reached`, `discovery_exhausted`, `fatal_error`).
  - **Criterio de cierre:** la cantidad pedida se interpreta como objetivo de captura, no solo como tope operativo.

### H.2. Discovery con mayor recall útil

- [ ] **H-003 Implementar expansión sistemática de queries**
  - Construir familias de queries:
    - query base;
    - query geo;
    - query comercial;
    - query “sitio oficial”;
    - query con CTA/contacto;
    - query por variante léxica del nicho.
  - **Criterio de cierre:** un mismo job ya no depende de una sola redacción del query.

- [ ] **H-004 Agregar exclusiones negativas por tipo de ruido**
  - Inyectar términos negativos como:
    - `-blog`
    - `-ideas`
    - `-noticias`
    - `-revista`
    - `-g2`
    - `-pinterest`
    - `-linkedin`
  - Hacerlo configurable por dominio y tipo de nicho.
  - **Criterio de cierre:** baja la proporción de artículos y agregadores entre los primeros candidatos.

- [ ] **H-005 Construir ranking previo de “business-likeness”**
  - Puntuar por `title`, `snippet`, `url`, path y dominio:
    - sitio oficial;
    - negocio real;
    - presencia de contacto;
    - palabras comerciales;
    - geografía compatible;
    - exclusión de medios y listicles.
  - **Criterio de cierre:** el sistema prioriza scrapear primero los candidatos con mayor probabilidad de terminar en `accepted`.

- [ ] **H-006 Guardar razones de exclusión en discovery**
  - Persistir por candidato:
    - `excluded_as_directory`
    - `excluded_as_article`
    - `excluded_as_social`
    - `low_business_likeness`
  - **Criterio de cierre:** el descarte temprano deja trazabilidad, no desaparece silenciosamente.

### H.3. Mejor selección del dominio oficial

- [ ] **H-007 Permitir directorios solo como fuente de semilla**
  - Un directorio puede ayudar a encontrar el dominio oficial.
  - El directorio no debe convertirse en prospecto final.
  - **Criterio de cierre:** se aprovecha recall sin contaminar resultados.

- [ ] **H-008 Detectar y priorizar “sitio oficial”**
  - Favorecer dominios con:
    - marca consistente en title y URL;
    - `/contact`, `/contacto`, `/about`, `/nosotros`;
    - datos de contacto propios;
    - structured data de organización.
  - **Criterio de cierre:** sube la proporción de negocios reales frente a contenido informativo.

- [ ] **H-009 Añadir heurística de exclusión de contenido editorial**
  - Detectar blog posts, comparativas, listicles, revistas, medios y páginas educativas.
  - Señales: año en slug, patrones tipo `/blog/`, `/ideas/`, `/que-es/`, `/guia/`, `/categories/`.
  - **Criterio de cierre:** baja la tasa de URLs que jamás podrían terminar en lead.

### H.4. Quality gate y auditabilidad sin perder precisión

- [ ] **H-010 Exponer filtro de calidad en `/results`**
  - Soportar `quality=accepted`, `quality=accepted,needs_review` y `quality=all`.
  - Mantener `accepted` como default.
  - **Criterio de cierre:** el consumidor puede auditar sin entrar a la base.

- [ ] **H-011 Persistir resumen de captura por job**
  - Agregar agregados:
    - `accepted_count`
    - `needs_review_count`
    - `rejected_count`
    - `acceptance_rate`
    - `candidate_dropoff_by_reason`
  - **Criterio de cierre:** los jobs vacíos quedan explicados desde API.

- [ ] **H-012 Afinar geo strict con mejor evidencia previa**
  - Mantener `strict geo`, pero apoyarlo mejor con:
    - snippet;
    - TLD;
    - prefijo telefónico;
    - `areaServed`;
    - `PostalAddress`;
    - mapa;
    - páginas `locations`.
  - **Criterio de cierre:** siguen cayendo los mismatches reales, pero baja el rechazo por evidencia insuficiente.

### H.5. Estrategia incremental de procesamiento

- [x] **H-013 Procesar candidatos por tandas**
  - No lanzar de golpe toda la lista.
  - Hacer lotes, medir aceptación y decidir si hace falta abrir más queries.
  - **Criterio de cierre:** mejor control de costo y mejor adaptación al job.

- [x] **H-014 Reabrir discovery si no hay aceptados suficientes**
  - Si tras una tanda no se alcanza el objetivo:
    - probar queries alternativas;
    - usar nuevas variantes del nicho;
    - relanzar con refuerzo comercial o geográfico.
  - **Criterio de cierre:** el pipeline intenta recuperar recall antes de rendirse.

- [x] **H-015 Definir ratio mínimo entre objetivo y candidatos**
  - Regla inicial sugerida:
    - si piden 1 aceptado, intentar hasta 5 candidatos;
    - si piden 5 aceptados, intentar 15-25 candidatos;
    - ajustar por nicho y calidad histórica.
  - **Criterio de cierre:** ya no existe la falsa expectativa de “5 candidatos = 5 leads”.

### H.6. Testing, medición y rollout

- [x] **H-016 Crear fixtures SERP y casos de nicho**
  - Fixtures con:
    - artículos;
    - directorios;
    - sitios oficiales;
    - negocios de otro país;
    - negocios con CTA/contacto.
  - **Criterio de cierre:** discovery y pre-ranking se validan offline.

- [x] **H-017 Medir recall y precision operativa**
  - KPIs mínimos:
    - acceptance rate por job;
    - candidatos procesados por lead aceptado;
    - ratio de artículos/directorios entre candidatos;
    - jobs completados con `accepted=0`.
  - **Criterio de cierre:** el refinamiento deja métricas verificables, no solo percepción subjetiva.

- [x] **H-018 Hacer rollout por etapas**
  - Etapa 1: filtro `quality` en `/results` y summary ampliado.
  - Etapa 2: nueva semántica `target_accepted_results`.
  - Etapa 3: expansión de queries + pre-ranking.
  - Etapa 4: directorio como semilla + reintento de discovery por tandas.
  - **Criterio de cierre:** el cambio se puede validar sin romper el contrato de golpe.

### Estado del rollout 2026-03-11

- Etapa 1 cerrada: `quality` en `/results`, `capture_summary` y `operational_summary` expuestos por API.
- Etapa 2 cerrada: `target_accepted_results` y `max_candidates_to_process` ya gobiernan la semántica de captura.
- Etapa 3 cerrada: query expansion, negativas y pre-ranking de business-likeness ya están activos.
- Etapa 4 cerrada: directorio como seed, batches de candidatos y reapertura incremental de discovery ya están activos.

---

## 7. Orden recomendado de implementación

### Etapa 1. Transparencia

Primero hay que evitar que el sistema “parezca roto” cuando en realidad completó el job sin aceptados.

Implementar:

1. `H-010`
2. `H-011`
3. `H-018` etapa 1

### Etapa 2. Semántica correcta de cantidad

Después hay que corregir la expectativa del usuario.

Implementar:

1. `H-001`
2. `H-002`
3. `H-015`

### Etapa 3. Recall útil

Una vez corregida la estrategia de parada, mejorar discovery.

Implementar:

1. `H-003`
2. `H-004`
3. `H-005`
4. `H-009`

### Etapa 4. Captura incremental

Con mejor discovery, pasar a búsqueda adaptativa por tandas.

Implementar:

1. `H-013`
2. `H-014`
3. `H-018` etapa 4

### Etapa 5. Ajuste fino

Por último, profundizar geo y seeds externas controladas.

Implementar:

1. `H-007`
2. `H-008`
3. `H-012`
4. `H-016`
5. `H-017`

---

## 8. Definición de éxito

Se considerará exitoso este refinamiento cuando se cumplan, al menos, estas condiciones:

- baja la cantidad de jobs completados con `accepted=0` en búsquedas donde sí existen negocios elegibles;
- sube la proporción de dominios oficiales frente a artículos y agregadores;
- el usuario puede pedir una cantidad objetivo de leads aceptados;
- la API permite auditar `needs_review` y rechazados sin entrar a la base;
- el costo de IA no sube de forma proporcional al aumento de recall;
- los jobs vacíos quedan explicados con métricas, no solo con un array vacío.
