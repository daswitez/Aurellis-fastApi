# Diseño del Prompt de DeepSeek

**Versión activa:** `deepseek_prospect_v2`  
**Archivo fuente:** `app/services/ai_extractor.py`

---

## 1. Objetivo del prompt

El prompt no busca “describir una web” en abstracto.  
Busca evaluar un prospecto B2B desde una lógica comercial concreta:

- quién es el vendedor,
- qué ofrece,
- a qué nicho apunta,
- qué pains dice resolver,
- y qué tan compatible parece el prospecto con ese contexto.

Por eso el prompt debe producir una salida útil para priorización comercial, no una simple clasificación temática.

---

## 2. Problemas del prompt anterior

El prompt previo tenía varios problemas de diseño:

- mezclaba descripción semántica con ejemplo de JSON dentro del mismo bloque;
- era demasiado corto para guiar inferencias consistentes;
- no incorporaba todo el contexto capturado del job;
- pedía estructura estricta, pero sin reglas claras de evidencia;
- no definía bien la semántica de `score`;
- no versionaba el prompt, lo que hacía difícil auditar cambios.

Eso volvía al extractor más frágil y más opaco de lo necesario.

---

## 3. Qué cambió en `deepseek_prospect_v2`

### 3.1. Prompt versionado

Ahora el prompt tiene una constante explícita:

- `PROMPT_VERSION = "deepseek_prospect_v2"`

Eso permite:

- saber qué versión generó una evaluación,
- comparar resultados entre versiones,
- auditar cambios de calidad más adelante.

### 3.2. Contexto del vendedor más completo

Antes el prompt consumía un subconjunto del contexto.

Ahora incorpora:

- profesión,
- tecnologías o servicios del vendedor,
- propuesta de valor,
- casos de éxito,
- métricas de ROI,
- nicho objetivo,
- ubicación objetivo,
- idioma objetivo,
- tamaño de empresa objetivo,
- pains que el vendedor dice resolver,
- señales de presupuesto deseadas.

Esto hace que el `score` tenga una base comercial más coherente.

### 3.3. Reglas de evidencia

El prompt ahora obliga a un comportamiento más conservador:

- no inventar datos,
- usar `Desconocido` cuando no hay evidencia,
- devolver lista vacía si no detecta stack,
- limitar `pain_points_detected`,
- evitar consejos genéricos,
- marcar `hiring_signals` solo con evidencia real.

Esto reduce la tentación del modelo de “completar por intuición”.

### 3.4. Semántica de score y confianza

Se definió una heurística explícita:

- `0.0 - 0.2`: casi sin fit o sin evidencia,
- `0.3 - 0.5`: fit débil o parcial,
- `0.6 - 0.8`: fit claro,
- `0.9 - 1.0`: fit excepcional.

Y para `confidence_level`:

- `low`: poca evidencia o señales contradictorias,
- `medium`: evidencia suficiente pero no concluyente,
- `high`: múltiples señales claras y consistentes.

Eso no garantiza perfección, pero reduce arbitrariedad.

### 3.5. Stack tecnológico mejor guiado

El prompt ahora prioriza tecnologías concretas si hay evidencia:

- WordPress
- WooCommerce
- Shopify
- Wix
- Webflow
- Elementor
- React
- Next.js
- Google Analytics
- Google Tag Manager
- Meta Pixel
- Stripe
- HubSpot

No obliga al modelo a inventarlas; solo le da un espacio de detección mejor definido.

### 3.6. Salida estructurada más consistente

La estructura esperada se genera desde código como JSON válido real, no como pseudo-ejemplo mezclado con comentarios informales.

Además:

- `evaluation_method` ahora queda ligado a la versión del prompt,
- se normalizan listas de tecnologías y pains,
- `estimated_revenue_signal` se normaliza a `low|medium|high`.

---

## 4. Contrato esperado de salida

El prompt sigue produciendo esta estructura lógica:

```json
{
  "inferred_niche": "Desconocido",
  "inferred_tech_stack": [],
  "generic_attributes": {
    "evaluation_method": "DeepSeek API (deepseek_prospect_v2)",
    "pain_points_detected": []
  },
  "hiring_signals": false,
  "estimated_revenue_signal": "low",
  "score": 0.0,
  "confidence_level": "low"
}
```

La idea no es pedir creatividad, sino consistencia.

---

## 5. Qué mejora concretamente este diseño

Con este rediseño, el extractor IA queda mejor orientado para:

- reducir salidas ambiguas,
- reducir inferencias inventadas,
- usar más contexto comercial real,
- producir scores más defendibles,
- facilitar comparación entre versiones,
- preparar el terreno para validación por schema en `C-002`.

---

## 6. Qué no resuelve todavía

Este cambio mejora mucho el prompt, pero no resuelve todo.

Sigue pendiente:

- validar la respuesta con schema fuerte,
- medir latencia/costo/fallback,
- guardar observabilidad específica de IA,
- definir score híbrido con heurística local,
- revisar si conviene agregar más campos de salida.

Eso corresponde a:

- `C-002`
- `C-004`
- `C-005`
- `C-006`
- `C-007`

---

## 7. Criterio de calidad para futuras versiones

Una nueva versión del prompt solo debería reemplazar a la actual si mejora al menos uno de estos puntos sin degradar los otros:

- precisión del nicho,
- utilidad comercial de `pain_points_detected`,
- consistencia de `score`,
- consistencia de `confidence_level`,
- capacidad de detectar stack real,
- tasa de respuestas inválidas.

Si no mejora algo medible o discutible con evidencia, cambiar el prompt solo agrega ruido.
