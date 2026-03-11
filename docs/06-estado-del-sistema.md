# Estado del Sistema

**Última actualización:** 2026-03-11  
**Versión operativa:** MVP refinado 1.2

---

## 1. Estado general

El pipeline actual funciona de punta a punta:

```text
POST /jobs/scrape
  -> discovery normalizado
  -> búsqueda DDG con pre-ranking
  -> scraping de dominio y páginas clave
  -> parser estructurado
  -> quality gate
  -> IA opcional con cache y fallback
  -> persistencia por prospecto y por job
  -> endpoints de estado, resultados, logs y métricas
```

El sistema ya puede explicar no solo si un job terminó, sino también:

- cuántos candidatos descubrió;
- cuántos procesó;
- cuántos quedaron `accepted`, `needs_review` o `rejected`;
- por qué terminó sin aceptados cuando eso ocurre;
- cuánto ruido editorial/directorio está apareciendo en discovery.

---

## 2. Componentes operativos

| Componente | Estado | Notas |
|-----------|--------|-------|
| API FastAPI | OK | Router principal estable |
| PostgreSQL local | OK | `docker compose up -d postgres` |
| Discovery DDG | OK | Queries canónicas, negativas, pre-ranking y seeds de directorio |
| Scraper HTTP | OK | Homepage + páginas clave |
| Parser HTML | OK | JSON-LD, idioma, CTAs, booking, pricing, mapas, contactos |
| Quality Gate | OK | `accepted`, `needs_review`, `rejected` |
| Geo strict reforzado | OK | `areaServed`, `PostalAddress`, TLD, prefijos telefónicos |
| IA DeepSeek | OK | Gateada por calidad/heurística |
| Cache IA local | OK | Útil mientras siga siendo proceso único |
| Persistencia canónica + por job | OK | `prospects`, `job_prospects`, `prospect_contacts`, `prospect_pages` |
| Logs persistidos | OK | Visibles por API |
| Métricas operativas agregadas | OK | `GET /jobs/metrics/operational` |
| Tests automatizados | OK | `pytest` corriendo en el `venv` del repo |

---

## 3. Capacidades clave ya disponibles

- crear jobs con objetivo de aceptados;
- limitar costo con `max_candidates_to_process`;
- reabrir discovery si el primer batch no alcanza;
- auditar resultados por calidad;
- consultar logs de ejecución;
- revisar KPIs agregados de recall/precisión;
- validar discovery offline con fixtures SERP;
- correr suite automatizada local.

---

## 4. Limitaciones actuales

### Procesamiento

- el worker sigue usando `BackgroundTasks`;
- si cae el proceso, no hay cola persistente ni reintento externo.

### Discovery

- la fuente principal sigue siendo DDG;
- un cambio fuerte en la SERP o bloqueo anti-bot puede afectar recall.

### Infraestructura

- no hay autenticación interna obligatoria para los endpoints;
- no existe todavía tablero externo de métricas;
- el cache de IA sigue siendo local al proceso.

### Scraping hostil

- algunos sitios con protección anti-bot avanzada seguirán fallando con 403 o timeouts;
- hoy eso se registra bien, pero no se resuelve con proxies/crawling más sofisticado.

---

## 5. Estado de pruebas

Comando actual:

```bash
./venv/bin/python -m pytest -q
```

Estado verificado:

- discovery;
- parser y quality;
- IA y observabilidad;
- métricas operativas.

---

## 6. Qué documento mirar según la necesidad

- API usable: [05-api-y-reglas.md](05-api-y-reglas.md)
- lógica de módulos: [11-mapa-de-modulos-y-cambios-recientes.md](11-mapa-de-modulos-y-cambios-recientes.md)
- backlog técnico: [07-observaciones-y-plan-de-mejora.md](07-observaciones-y-plan-de-mejora.md)
- captura y recall: [12-plan-refinamiento-captura-y-recall.md](12-plan-refinamiento-captura-y-recall.md)
- resumen ejecutivo y FODA: [13-estado-actual-foda-y-pendientes.md](13-estado-actual-foda-y-pendientes.md)
