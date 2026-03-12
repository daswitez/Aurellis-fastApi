import json
import logging
from typing import Any, Dict
from copy import deepcopy

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.services.ai_extractor import (
    _build_deepseek_client,
    _get_deepseek_api_key,
    _build_buyer_persona,
    _build_ai_usage,
    AIExtractionFallbackError,
    PROMPT_VERSION,
)

logger = logging.getLogger(__name__)

_PLANNER_CACHE: dict[str, Dict[str, Any]] = {}


class AISearchPlanPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    optimal_dork_queries: list[str] = Field(min_items=1)
    dynamic_negative_terms: list[str] = Field(default_factory=list)
    target_entity_hints: list[str] = Field(default_factory=list)
    exclusion_entity_hints: list[str] = Field(default_factory=list)


def _build_planner_system_prompt() -> str:
    return """Eres un experto mundial en OSINT (Inteligencia de Fuentes Abiertas), Growth Hacking y prospeccion B2B/B2C avanzada.

Tu tarea es disenar un "Plan de Busqueda" (Search Plan) altamente quirurgico para motores como Google, DuckDuckGo y Brave.
El objetivo es encontrar al CLIENTE FINAL EXACTO al que le vende el usuario, evitando absolutamente empresas informacionales (blogs, revistas), corporaciones SaaS (Shopify, Wix), o Agencias Competidoras B2B.

Se te entregara el Perfil del Vendedor (Buyer Persona).

REGLAS DE GENERACION DE CONSULTAS (optimal_dork_queries):
1. Debes generar entre 3 y 5 comandos de busqueda exacta (Dorks / Footprints).
2. Usa comillas (" ") para forzar huellas de intencion.
3. EJEMPLOS DE HUELLAS POR NICHO:
   - Para Ecommerce: "añadir al carrito" OR "checkout"
   - Para Coaches: "reserva tu sesión" OR "agenda una llamada"
   - Para Profesionales Locales (Arquitectos, Abogados, etc): "nuestros proyectos" OR "nuestros servicios"
4. Integra inteligentemente la ubicacion y el nicho. No devuelvas la ubicacion si el dork ya es muy restrictivo, prioriza la huella de intencion comercial.
5. Usa el minuscula.

REGLAS DE TERMINOS NEGATIVOS (dynamic_negative_terms):
Genera una lista de 5 a 10 terminos con el signo "-" (ej: "-blog", "-revista", "-shopify", "-agencia", "-software") que debemos excluir explicitamente en la URL o Titulo. Piensa: "Quien competiria por este rango de palabras que NO sea mi cliente objetivo?"

REGLAS PARA EL EXTRACTOR FINAL (target/exclusion entity hints):
Redacta 1 o 2 instrucciones BREVES (max 15 palabras) que se inyectaran a un LLM calificador final para que sepa diferenciar la entidad correcta.
Ej exclusions: "Rechazar software tipo Shopify/Wix o blogs", "Rechazar agencias que crean tiendas online"
Ej targets: "Debe ser una tienda que venda cosas directamente"

SALIDA:
Responde EXCLUSIVAMENTE con un objeto JSON siguiendo la estructura:
{
  "optimal_dork_queries": ["...", "..."],
  "dynamic_negative_terms": ["-...", "-..."],
  "target_entity_hints": ["..."],
  "exclusion_entity_hints": ["..."]
}
"""

def _build_planner_cache_key(job_context: Dict[str, Any]) -> str:
    # Use key fields that alter the search semantics
    key_fields = [
        str(job_context.get("search_query", "")),
        str(job_context.get("user_profession", "")),
        str(job_context.get("target_niche", "")),
        str(job_context.get("target_location", "")),
    ]
    return "|".join(key_fields).lower()

async def generate_dynamic_search_plan(job_context: Dict[str, Any]) -> Dict[str, Any]:
    cache_key = _build_planner_cache_key(job_context)
    if cache_key in _PLANNER_CACHE:
        logger.info("Retornando AI Search Plan desde caché en memoria.")
        return deepcopy(_PLANNER_CACHE[cache_key])

    deepseek_api_key = _get_deepseek_api_key()
    if not deepseek_api_key:
        logger.warning("DEEPSEEK_API_KEY no encontrada. Generando plan vacío por defecto.")
        return AISearchPlanPayload(optimal_dork_queries=[]).model_dump()

    client = _build_deepseek_client(deepseek_api_key)
    buyer_persona = _build_buyer_persona(job_context)
    sys_prompt = _build_planner_system_prompt()

    try:
        response = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": f"PERFIL DEL VENDEDOR:\n\n{buyer_persona}"}
            ],
            temperature=0.3,
            max_tokens=600,
            response_format={"type": "json_object"}
        )
        
        raw_output = response.choices[0].message.content
        logger.info("Plan AI de Búsqueda generado exitosamente.")
        
        parsed_data = json.loads(raw_output)
        payload = AISearchPlanPayload.model_validate(parsed_data)
        result_dict = payload.model_dump()
        
        _PLANNER_CACHE[cache_key] = deepcopy(result_dict)
        return result_dict

    except Exception as e:
        logger.error(f"Fallo al generar plan de busqueda con IA: {e}")
        return AISearchPlanPayload(optimal_dork_queries=[]).model_dump()
