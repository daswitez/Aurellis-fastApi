import json
import logging
from time import perf_counter
from typing import Any, Dict, Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from app.config import get_settings

logger = logging.getLogger(__name__)

# DeepSeek es compatible con el SDK de OpenAI. Solo cambiamos la base_url
# y pasamos la API key
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
PROMPT_VERSION = "deepseek_prospect_v2"
MAX_INPUT_CHARS = 10000
RevenueSignal = Literal["low", "medium", "high"]
ConfidenceLevel = Literal["low", "medium", "high"]


class AIExtractionFallbackError(Exception):
    def __init__(
        self,
        reason: str,
        message: str,
        *,
        error_type: str,
        retryable: bool = False,
        usage: Dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.error_type = error_type
        self.retryable = retryable
        self.usage = usage or {}


def _get_deepseek_api_key() -> str:
    return get_settings().DEEPSEEK_API_KEY.strip()


def _build_deepseek_client(api_key: str) -> AsyncOpenAI:
    return AsyncOpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)


def _build_ai_usage(
    *,
    latency_ms: int | None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
) -> Dict[str, Any]:
    if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
        total_tokens = prompt_tokens + completion_tokens

    settings = get_settings()
    estimated_cost_usd: float | None = None
    if prompt_tokens is not None and completion_tokens is not None:
        input_cost_rate = max(settings.DEEPSEEK_INPUT_COST_PER_1M_TOKENS, 0.0)
        output_cost_rate = max(settings.DEEPSEEK_OUTPUT_COST_PER_1M_TOKENS, 0.0)
        if input_cost_rate > 0 or output_cost_rate > 0:
            estimated_cost_usd = round(
                ((prompt_tokens * input_cost_rate) + (completion_tokens * output_cost_rate)) / 1_000_000,
                8,
            )

    return {
        "latency_ms": latency_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": estimated_cost_usd,
    }


def _extract_usage_metrics(response: Any, *, latency_ms: int | None) -> Dict[str, Any]:
    usage = getattr(response, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", None)
    completion_tokens = getattr(usage, "completion_tokens", None)
    total_tokens = getattr(usage, "total_tokens", None)
    return _build_ai_usage(
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )


def _normalize_string_list(raw_value: Any, *, max_items: int = 10) -> list[str]:
    if not isinstance(raw_value, list):
        return []

    cleaned_items: list[str] = []
    for item in raw_value:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if not normalized or normalized in cleaned_items:
            continue
        cleaned_items.append(normalized)
        if len(cleaned_items) >= max_items:
            break
    return cleaned_items


def _coerce_bool(raw_value: Any) -> bool:
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, (int, float)) and raw_value in {0, 1}:
        return bool(raw_value)
    if isinstance(raw_value, str):
        normalized = raw_value.strip().lower()
        if normalized in {"true", "1", "yes", "si", "sí"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    raise ValueError("Valor booleano inválido")


def _parse_revenue_signal(raw_signal: Any) -> RevenueSignal:
    if not isinstance(raw_signal, str):
        raise ValueError("estimated_revenue_signal debe ser string")

    normalized = raw_signal.strip().lower()
    if normalized not in {"low", "medium", "high"}:
        raise ValueError("estimated_revenue_signal inválido")
    return normalized


def _parse_confidence_level(raw_confidence: Any) -> ConfidenceLevel:
    if isinstance(raw_confidence, str):
        normalized = raw_confidence.strip().lower()
        if normalized in {"low", "medium", "high"}:
            return normalized

    try:
        confidence_score = float(raw_confidence)
    except (TypeError, ValueError):
        raise ValueError("confidence_level inválido") from None

    if confidence_score >= 0.8:
        return "high"
    if confidence_score >= 0.5:
        return "medium"
    return "low"


class _AIGenericAttributesPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pain_points_detected: list[str]

    @field_validator("pain_points_detected", mode="before")
    @classmethod
    def _validate_pain_points(cls, raw_value: Any) -> list[str]:
        if not isinstance(raw_value, list):
            raise ValueError("pain_points_detected debe ser lista")
        return _normalize_string_list(raw_value, max_items=5)


class _AIResponsePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    inferred_niche: str
    inferred_tech_stack: list[str]
    generic_attributes: _AIGenericAttributesPayload
    hiring_signals: bool
    estimated_revenue_signal: RevenueSignal
    score: float
    confidence_level: ConfidenceLevel

    @field_validator("inferred_niche", mode="before")
    @classmethod
    def _validate_inferred_niche(cls, raw_value: Any) -> str:
        if raw_value is None:
            raise ValueError("inferred_niche es requerido")
        normalized = str(raw_value).strip()
        return normalized or "Desconocido"

    @field_validator("inferred_tech_stack", mode="before")
    @classmethod
    def _validate_inferred_tech_stack(cls, raw_value: Any) -> list[str]:
        if not isinstance(raw_value, list):
            raise ValueError("inferred_tech_stack debe ser lista")
        return _normalize_string_list(raw_value, max_items=10)

    @field_validator("hiring_signals", mode="before")
    @classmethod
    def _validate_hiring_signals(cls, raw_value: Any) -> bool:
        return _coerce_bool(raw_value)

    @field_validator("estimated_revenue_signal", mode="before")
    @classmethod
    def _validate_estimated_revenue_signal(cls, raw_value: Any) -> RevenueSignal:
        return _parse_revenue_signal(raw_value)

    @field_validator("score", mode="before")
    @classmethod
    def _validate_score(cls, raw_value: Any) -> float:
        try:
            score = float(raw_value)
        except (TypeError, ValueError):
            raise ValueError("score inválido") from None
        return max(0.0, min(score, 1.0))

    @field_validator("confidence_level", mode="before")
    @classmethod
    def _validate_confidence_level(cls, raw_value: Any) -> ConfidenceLevel:
        return _parse_confidence_level(raw_value)


def _format_context_value(value: Any, *, empty: str = "No especificado") -> str:
    if value is None:
        return empty
    if isinstance(value, list):
        normalized_items = [str(item).strip() for item in value if str(item).strip()]
        return ", ".join(normalized_items) if normalized_items else empty
    normalized = str(value).strip()
    return normalized or empty


def _build_buyer_persona(job_context: Dict[str, Any]) -> str:
    return "\n".join(
        [
            f"- Profesion del vendedor: {_format_context_value(job_context.get('user_profession'))}",
            f"- Tecnologias/servicios del vendedor: {_format_context_value(job_context.get('user_technologies'))}",
            f"- Propuesta de valor: {_format_context_value(job_context.get('user_value_proposition'))}",
            f"- Casos de exito previos: {_format_context_value(job_context.get('user_past_successes'))}",
            f"- Metricas o ROI ofrecido: {_format_context_value(job_context.get('user_roi_metrics'))}",
            f"- Nicho objetivo: {_format_context_value(job_context.get('target_niche'), empty='General')}",
            f"- Ubicacion objetivo: {_format_context_value(job_context.get('target_location'))}",
            f"- Idioma objetivo: {_format_context_value(job_context.get('target_language'))}",
            f"- Tamano de empresa objetivo: {_format_context_value(job_context.get('target_company_size'))}",
            f"- Pains que el vendedor dice resolver: {_format_context_value(job_context.get('target_pain_points'))}",
            f"- Senales de presupuesto deseadas: {_format_context_value(job_context.get('target_budget_signals'))}",
        ]
    )


def _build_expected_output_schema() -> str:
    schema = {
        "inferred_niche": "Desconocido",
        "inferred_tech_stack": ["WordPress", "Google Analytics"],
        "generic_attributes": {
            "evaluation_method": f"DeepSeek API ({PROMPT_VERSION})",
            "pain_points_detected": [
                "No muestra CTA clara",
                "No tiene reservas online visibles",
            ],
        },
        "hiring_signals": False,
        "estimated_revenue_signal": "low",
        "score": 0.0,
        "confidence_level": "low",
    }
    return json.dumps(schema, ensure_ascii=False, indent=2)


def _build_system_prompt(domain: str, job_context: Dict[str, Any]) -> str:
    buyer_persona = _build_buyer_persona(job_context)
    expected_schema = _build_expected_output_schema()

    return f"""Eres un analista senior de prospeccion B2B para freelancers y agencias pequenas.
Tu tarea es evaluar el sitio '{domain}' usando UNICAMENTE el texto extraido del sitio y el contexto comercial del vendedor.

Version de prompt: {PROMPT_VERSION}

CONTEXTO DEL VENDEDOR
{buyer_persona}

OBJETIVO
1. Inferir el nicho real del prospecto.
2. Detectar tecnologias visibles o altamente probables solo si hay evidencia textual.
3. Detectar problemas comerciales o de sitio que el vendedor podria atacar.
4. Estimar si el prospecto parece tener capacidad de compra.
5. Dar un score de match entre 0.0 y 1.0 respecto al contexto del vendedor.

REGLAS DE EVIDENCIA
- No inventes datos. Si no hay evidencia suficiente, usa valores conservadores.
- Si no puedes inferir el nicho con claridad, usa "Desconocido".
- Si no detectas tecnologias concretas, devuelve una lista vacia.
- `pain_points_detected` debe contener entre 0 y 5 strings breves y accionables.
- Solo incluye pain points observables en el texto o deducibles con mucha fuerza del contenido.
- No pongas frases genéricas como "necesita marketing" o "puede mejorar todo".
- `hiring_signals` es true solo si hay evidencia de vacantes, careers, equipo en expansion o contratacion.
- `estimated_revenue_signal` debe ser `low`, `medium` o `high`.
- `score` debe ser un float entre 0.0 y 1.0.
- `confidence_level` debe ser `low`, `medium` o `high`.

HEURISTICA DE SCORE
- 0.0 a 0.2: casi no hay fit o falta evidencia.
- 0.3 a 0.5: fit debil o parcial.
- 0.6 a 0.8: fit claro y util comercialmente.
- 0.9 a 1.0: fit excepcional y muy evidente.

HEURISTICA DE CONFIANZA
- `low`: poco texto, señales contradictorias o inferencias débiles.
- `medium`: evidencia suficiente pero no concluyente.
- `high`: múltiples señales consistentes y claras.

TECNOLOGIAS A PRIORIZAR SI HAY EVIDENCIA
WordPress, WooCommerce, Shopify, Wix, Webflow, Elementor, React, Next.js,
Google Analytics, Google Tag Manager, Meta Pixel, Stripe, HubSpot.

SALIDA
Responde EXCLUSIVAMENTE con un JSON valido.
No uses markdown.
No agregues texto antes ni despues.
La estructura esperada es:
{expected_schema}
"""


def _validate_ai_response_payload(parsed_data: Any) -> Dict[str, Any]:
    payload = _AIResponsePayload.model_validate(parsed_data)
    return {
        "inferred_tech_stack": payload.inferred_tech_stack,
        "inferred_niche": payload.inferred_niche,
        "generic_attributes": {
            "evaluation_method": f"DeepSeek API ({PROMPT_VERSION})",
            "pain_points_detected": payload.generic_attributes.pain_points_detected,
        },
        "hiring_signals": payload.hiring_signals,
        "estimated_revenue_signal": payload.estimated_revenue_signal,
        "score": payload.score,
        "confidence_level": payload.confidence_level,
    }


async def extract_business_entity_ai(
    domain: str, 
    clean_text: str, 
    job_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Usa DeepSeek-Chat (V3) para analizar el texto de la web y devolver un JSON estricto
    con la perfilación del prospecto y un Match Score, optimizando el uso de tokens.
    """
    
    # 1. OPTIMIZACIÓN DE TOKENS
    # El texto ya viene limpio y enriquecido por crawling limitado.
    # Conservamos una ventana razonable para no disparar costo ni ruido.
    truncated_text = clean_text[:MAX_INPUT_CHARS] if clean_text else ""
    
    if not truncated_text or len(truncated_text) < 100:
        logger.warning(f"Texto insuficiente para IA en {domain}. Activando heurística.")
        raise AIExtractionFallbackError(
            "insufficient_text",
            f"Texto insuficiente para IA en {domain}",
            error_type="input_validation",
            retryable=False,
        )

    deepseek_api_key = _get_deepseek_api_key()
    if not deepseek_api_key:
        logger.error("DEEPSEEK_API_KEY no encontrada. Por favor agrégala al archivo .env")
        raise AIExtractionFallbackError(
            "missing_api_key",
            "DEEPSEEK_API_KEY no encontrada",
            error_type="configuration",
            retryable=False,
        )

    client = _build_deepseek_client(deepseek_api_key)

    sys_prompt = _build_system_prompt(domain, job_context)
    response = None
    request_started_at = perf_counter()

    try:
        # Llamada a IA
        # Usamos deepseek-chat por ser ridículamente barato ($0.14 / 1M input tokens) 
        # y suficientemente inteligente para JSON
        response = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": f"TEXTO EXTRAIDO DE {domain}:\n\n{truncated_text}"}
            ],
            temperature=0.1, # Baja temperatura para JSON predecible
            max_tokens=500,  # Respuesta JSON debe ser corta (menos coste salida)
            response_format={"type": "json_object"} # Fuerza a DeepSeek a escupir JSON puro
        )
        usage_metrics = _extract_usage_metrics(
            response,
            latency_ms=int((perf_counter() - request_started_at) * 1000),
        )
        
        raw_output = response.choices[0].message.content
        logger.info(f"Respuesta IA para {domain} completada. Parseando JSON.")
        
        # Intentar parsear
        parsed_data = json.loads(raw_output)
        validated_payload = _validate_ai_response_payload(parsed_data)
        validated_payload["_ai_metrics"] = usage_metrics
        return validated_payload

    except json.JSONDecodeError as je:
        logger.error(f"DeepSeek no devolvió un JSON válido para {domain}: {str(je)}")
        raise AIExtractionFallbackError(
            "json_parse_error",
            f"DeepSeek no devolvió JSON válido para {domain}",
            error_type="invalid_response",
            retryable=False,
            usage=_extract_usage_metrics(
                response,
                latency_ms=int((perf_counter() - request_started_at) * 1000),
            ),
        ) from je
    except ValidationError as ve:
        logger.error(f"DeepSeek devolvió schema inválido para {domain}: {ve.errors()}")
        raise AIExtractionFallbackError(
            "invalid_schema",
            f"DeepSeek devolvió schema inválido para {domain}",
            error_type="invalid_response",
            retryable=False,
            usage=_extract_usage_metrics(
                response,
                latency_ms=int((perf_counter() - request_started_at) * 1000),
            ),
        ) from ve
    except Exception as e:
        logger.error(f"Fallo en API de DeepSeek para {domain}: {str(e)}")
        raise AIExtractionFallbackError(
            "provider_error",
            f"Fallo en API de DeepSeek para {domain}: {str(e)}",
            error_type="provider_error",
            retryable=True,
            usage=_build_ai_usage(
                latency_ms=int((perf_counter() - request_started_at) * 1000),
            ),
        ) from e
