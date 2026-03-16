import json
import logging
import re
import unicodedata
from copy import deepcopy
from hashlib import sha256
from typing import Any, Dict, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.services.ai_extractor import (
    _build_buyer_persona,
    _build_deepseek_client,
    _get_deepseek_api_key,
)

logger = logging.getLogger(__name__)

PlannerMode = Literal["initial", "refinement"]
STRICT_SPAIN_ALIASES = ("espana", "españa", "spain")
NON_SPAIN_GEO_TOKENS = (
    "argentina",
    "mexico",
    "méxico",
    "peru",
    "perú",
    "colombia",
    "chile",
    "uruguay",
    "bolivia",
    "buenos aires",
    "lima",
    "bogota",
    "bogotá",
    "cdmx",
)
_PLANNER_CACHE: dict[str, Dict[str, Any]] = {}


class AISearchPlanPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    optimal_dork_queries: list[str] = Field(default_factory=list)
    dynamic_negative_terms: list[str] = Field(default_factory=list)
    target_entity_hints: list[str] = Field(default_factory=list)
    exclusion_entity_hints: list[str] = Field(default_factory=list)
    refinement_goal: str | None = None


def _normalize_space(value: str | None) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_ascii(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", _normalize_space(value))
    return normalized.encode("ascii", "ignore").decode("ascii").lower()


def _is_strict_spain_job(job_context: Dict[str, Any]) -> bool:
    target_location = _normalize_ascii(str(job_context.get("target_location") or ""))
    return target_location in STRICT_SPAIN_ALIASES


def _dedupe_strings(values: list[str] | None) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        cleaned = _normalize_space(value)
        lowered = cleaned.lower()
        if not cleaned or lowered in seen:
            continue
        deduped.append(cleaned)
        seen.add(lowered)
    return deduped


def _enforce_geo_policy(
    queries: list[str],
    *,
    strict_spain: bool,
) -> list[str]:
    if not strict_spain:
        return _dedupe_strings(queries)

    filtered: list[str] = []
    for query in _dedupe_strings(queries):
        normalized = _normalize_ascii(query)
        if any(token in normalized for token in NON_SPAIN_GEO_TOKENS):
            continue
        if not any(alias in normalized for alias in STRICT_SPAIN_ALIASES):
            query = _normalize_space(f"{query} España")
        filtered.append(query)
    return _dedupe_strings(filtered)


def _normalize_negative_terms(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for value in _dedupe_strings(values):
        prefixed = value if value.startswith("-") else f"-{value}"
        normalized.append(prefixed)
    return normalized


def _build_initial_system_prompt() -> str:
    return """Eres un experto mundial en OSINT, Growth Hacking y prospeccion comercial.

Tu tarea es disenar un Search Plan para encontrar CLIENTES FINALES EXACTOS para outreach.

REGLAS:
1. Genera 3 a 6 queries comerciales, especificas y accionables.
2. Evita blogs, medios, escuelas, directorios, listados, software, assets, fuentes, tools y paginas informativas.
3. Si el target incluye coaches o marcas personales, prioriza huellas de oferta final, redes, link in bio, programas, mentorias y contacto comercial.
4. Si la ubicacion objetivo es España, no abras geografia fuera de España.
5. Devuelve terminos negativos utiles y hints para el clasificador final.

SALIDA JSON:
{
  "optimal_dork_queries": ["..."],
  "dynamic_negative_terms": ["-blog"],
  "target_entity_hints": ["..."],
  "exclusion_entity_hints": ["..."],
  "refinement_goal": "..."
}
"""


def _build_refinement_system_prompt() -> str:
    return """Eres un experto en iteracion de discovery comercial.

Debes revisar los resultados previos de un job y proponer nuevas queries MAS ESPECIFICAS.

OBJETIVO:
- aumentar prospectos finales validos,
- reducir ruido,
- no repetir queries ya usadas,
- no abrir geografia fuera de España,
- excluir escuelas, directorios, listados, blogs, medios, assets y paginas oportunistas por keyword.

Si viste falsos positivos, usalos para endurecer terminos negativos y exclusiones.

SALIDA JSON:
{
  "optimal_dork_queries": ["..."],
  "dynamic_negative_terms": ["-blog"],
  "target_entity_hints": ["..."],
  "exclusion_entity_hints": ["..."],
  "refinement_goal": "..."
}
"""


def _compact_iteration_memory(iteration_memory: Dict[str, Any] | None) -> str:
    if not isinstance(iteration_memory, dict):
        return "Sin memoria previa."

    payload = {
        "trigger_reason": iteration_memory.get("trigger_reason"),
        "window_stats": iteration_memory.get("window_stats"),
        "top_rejection_reasons": iteration_memory.get("top_rejection_reasons"),
        "queries_already_executed": iteration_memory.get("queries_already_executed", [])[:20],
        "seen_domains": iteration_memory.get("seen_domains", [])[:20],
        "false_positive_samples": iteration_memory.get("false_positive_samples", [])[:8],
        "accepted_samples": iteration_memory.get("accepted_samples", [])[:4],
    }
    return json.dumps(payload, ensure_ascii=False)


def _build_refinement_user_prompt(job_context: Dict[str, Any], iteration_memory: Dict[str, Any] | None) -> str:
    buyer_persona = _build_buyer_persona(job_context)
    return "\n".join(
        [
            "REQUEST ORIGINAL DEL USUARIO:",
            buyer_persona,
            "",
            "POLITICA FIJA:",
            "- Ubicacion estricta: España",
            "- Target valido: coaches finales, marcas personales finales y negocios finales",
            "- Rechazar: escuelas, directorios, listados, blogs, medios, assets, fuentes, tools",
            "",
            "MEMORIA DEL JOB:",
            _compact_iteration_memory(iteration_memory),
        ]
    )


def _build_planner_cache_key(
    job_context: Dict[str, Any],
    *,
    mode: PlannerMode,
    iteration_memory: Dict[str, Any] | None,
) -> str:
    base_parts = [
        mode,
        str(job_context.get("search_query", "")),
        str(job_context.get("user_profession", "")),
        str(job_context.get("target_niche", "")),
        str(job_context.get("target_location", "")),
    ]
    if mode == "refinement":
        memory_fingerprint = sha256(
            json.dumps(iteration_memory or {}, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        base_parts.append(memory_fingerprint)
    return "|".join(base_parts).lower()


def _coerce_plan_payload(
    parsed_data: Dict[str, Any],
    *,
    strict_spain: bool,
) -> Dict[str, Any]:
    payload = AISearchPlanPayload.model_validate(parsed_data)
    result = payload.model_dump()
    result["optimal_dork_queries"] = _enforce_geo_policy(
        result.get("optimal_dork_queries", []),
        strict_spain=strict_spain,
    )
    result["dynamic_negative_terms"] = _normalize_negative_terms(result.get("dynamic_negative_terms", []))
    result["target_entity_hints"] = _dedupe_strings(result.get("target_entity_hints", []))
    result["exclusion_entity_hints"] = _dedupe_strings(result.get("exclusion_entity_hints", []))
    result["refinement_goal"] = _normalize_space(result.get("refinement_goal"))
    return result


def _empty_plan() -> Dict[str, Any]:
    return AISearchPlanPayload().model_dump()


async def _call_planner(
    *,
    system_prompt: str,
    user_prompt: str,
) -> Dict[str, Any]:
    deepseek_api_key = _get_deepseek_api_key()
    if not deepseek_api_key:
        logger.warning("DEEPSEEK_API_KEY no encontrada. Generando plan vacío por defecto.")
        return _empty_plan()

    client = _build_deepseek_client(deepseek_api_key)
    response = await client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        max_tokens=700,
        response_format={"type": "json_object"},
    )
    raw_output = response.choices[0].message.content
    return json.loads(raw_output)


async def generate_dynamic_search_plan(
    job_context: Dict[str, Any],
    *,
    mode: PlannerMode = "initial",
    iteration_memory: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    cache_key = _build_planner_cache_key(job_context, mode=mode, iteration_memory=iteration_memory)
    if cache_key in _PLANNER_CACHE:
        logger.info("Retornando AI Search Plan desde caché en memoria.")
        return deepcopy(_PLANNER_CACHE[cache_key])

    strict_spain = _is_strict_spain_job(job_context)
    if mode == "refinement":
        system_prompt = _build_refinement_system_prompt()
        user_prompt = _build_refinement_user_prompt(job_context, iteration_memory)
    else:
        system_prompt = _build_initial_system_prompt()
        user_prompt = f"PERFIL DEL VENDEDOR:\n\n{_build_buyer_persona(job_context)}"

    try:
        parsed_data = await _call_planner(system_prompt=system_prompt, user_prompt=user_prompt)
        result_dict = _coerce_plan_payload(parsed_data, strict_spain=strict_spain)
        _PLANNER_CACHE[cache_key] = deepcopy(result_dict)
        logger.info("Plan AI de búsqueda generado exitosamente en modo %s.", mode)
        return result_dict
    except (ValidationError, json.JSONDecodeError) as exc:
        logger.error("Fallo validando plan de búsqueda con IA: %s", exc)
        return _empty_plan()
    except Exception as exc:
        logger.error("Fallo al generar plan de búsqueda con IA: %s", exc)
        return _empty_plan()


async def initial_search_plan(job_context: Dict[str, Any]) -> Dict[str, Any]:
    return await generate_dynamic_search_plan(job_context, mode="initial")


async def refine_search_plan(job_context: Dict[str, Any], iteration_memory: Dict[str, Any]) -> Dict[str, Any]:
    return await generate_dynamic_search_plan(
        job_context,
        mode="refinement",
        iteration_memory=iteration_memory,
    )
