import json
import logging
import re
import unicodedata
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Dict, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.services.ai_extractor import (
    _build_buyer_persona,
    _build_deepseek_client,
    _get_deepseek_api_key,
)
from app.services.discovery import GLOBAL_LOCATION_TOKENS, LOCATION_ALIAS_RULES

logger = logging.getLogger(__name__)

PlannerMode = Literal["initial", "refinement"]
PlannerProfileKey = Literal["generic_business", "creator_coach", "ecommerce_content"]
MULTI_LOCATION_SPLIT_PATTERN = re.compile(r"\s*(?:/|,|\||;)\s*")
CREATOR_COACH_HINTS = (
    "coach",
    "coaches",
    "coaching",
    "marca personal",
    "marcas personales",
    "personal brand",
    "mentor",
    "mentoria",
    "mentoría",
    "creator",
    "creador",
)
ECOMMERCE_HINTS = (
    "ecommerce",
    "e-commerce",
    "tienda online",
    "shopify",
    "dropshipping",
    "online store",
    "product brand",
    "d2c",
    "direct to consumer",
    "shop",
    "store",
)
ECOMMERCE_BLOCKED_QUERY_HINTS = (
    "site:*.com",
    "site:myshopify.com",
    "site:shopify.com",
    "help.shopify.com",
    "accounts.shopify.com",
    "inurl:collections",
    "inurl:products",
    "\"active on instagram\"",
    "\"tiktok shop\"",
)
_PLANNER_CACHE: dict[str, Dict[str, Any]] = {}


@dataclass(frozen=True)
class SearchPlannerProfile:
    key: PlannerProfileKey
    label: str
    target_description: str
    priority_signals: tuple[str, ...]
    exclusion_focus: tuple[str, ...]
    default_target_entity_hints: tuple[str, ...]
    default_exclusion_entity_hints: tuple[str, ...]


class AISearchPlanPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    optimal_dork_queries: list[str] = Field(default_factory=list)
    dynamic_negative_terms: list[str] = Field(default_factory=list)
    target_entity_hints: list[str] = Field(default_factory=list)
    exclusion_entity_hints: list[str] = Field(default_factory=list)
    refinement_goal: str | None = None
    planner_profile: str | None = None
    geo_scope: str | None = None


def _normalize_space(value: str | None) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_ascii(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", _normalize_space(value))
    return normalized.encode("ascii", "ignore").decode("ascii").lower()


_GLOBAL_LOCATION_ALIASES = {_normalize_ascii(token) for token in GLOBAL_LOCATION_TOKENS}


PLANNER_PROFILES: dict[PlannerProfileKey, SearchPlannerProfile] = {
    "generic_business": SearchPlannerProfile(
        key="generic_business",
        label="general_business",
        target_description="negocios finales con oferta comercial clara y canal de contacto usable",
        priority_signals=(
            "sitio oficial",
            "pagina de contacto",
            "pagina de servicios o productos",
            "CTA comercial visible",
        ),
        exclusion_focus=(
            "blogs",
            "medios",
            "directorios",
            "listados",
            "software",
            "assets",
            "paginas informativas",
        ),
        default_target_entity_hints=("negocio final", "sitio oficial", "contacto comercial"),
        default_exclusion_entity_hints=("blog", "directorio", "medio", "software"),
    ),
    "creator_coach": SearchPlannerProfile(
        key="creator_coach",
        label="creator_coach",
        target_description="coaches finales, marcas personales finales y negocios finales con oferta propia",
        priority_signals=(
            "instagram o tiktok activos",
            "link in bio o linktree",
            "programas o mentorias",
            "pagina de contacto",
            "CTA comercial visible",
        ),
        exclusion_focus=(
            "escuelas",
            "directorios",
            "listados",
            "blogs",
            "medios",
            "assets",
            "tools",
        ),
        default_target_entity_hints=("coach final", "marca personal", "contacto comercial"),
        default_exclusion_entity_hints=("escuela", "directorio", "listado de coaches"),
    ),
    "ecommerce_content": SearchPlannerProfile(
        key="ecommerce_content",
        label="ecommerce_content",
        target_description="pequenas marcas ecommerce, tiendas online, negocios Shopify y pymes digitales que venden productos",
        priority_signals=(
            "sitio oficial o storefront activo",
            "paginas de producto o coleccion",
            "shopify o checkout visible",
            "instagram o tiktok activos",
            "branding, ads o landing comercial",
        ),
        exclusion_focus=(
            "agencias",
            "freelancers",
            "apps",
            "themes",
            "tutoriales",
            "marketplaces",
            "directorios",
            "proveedores o mayoristas",
        ),
        default_target_entity_hints=("ecommerce activo", "shopify store", "marca de producto"),
        default_exclusion_entity_hints=("agencia", "theme", "app", "tutorial", "supplier", "marketplace"),
    ),
}


def _build_location_alias_index() -> dict[str, str]:
    alias_index: dict[str, str] = {}
    for canonical_location, aliases in LOCATION_ALIAS_RULES.items():
        for alias in (canonical_location, *aliases):
            normalized_alias = _normalize_ascii(alias)
            if normalized_alias:
                alias_index[normalized_alias] = canonical_location
    return alias_index


LOCATION_ALIAS_INDEX = _build_location_alias_index()


def _collect_profile_context_blob(job_context: Dict[str, Any]) -> str:
    context_parts: list[str] = [
        str(job_context.get("search_query") or ""),
        str(job_context.get("target_niche") or ""),
        str(job_context.get("user_target_offer_focus") or ""),
        str(job_context.get("user_profession") or ""),
        str(job_context.get("target_company_size") or ""),
    ]
    context_parts.extend(str(item) for item in (job_context.get("target_budget_signals") or []))
    context_parts.extend(str(item) for item in (job_context.get("target_pain_points") or []))
    return _normalize_ascii(" ".join(context_parts))


def _count_profile_hint_matches(searchable_blob: str, hints: tuple[str, ...]) -> int:
    return sum(1 for hint in hints if _normalize_ascii(hint) in searchable_blob)


def _resolve_planner_profile(job_context: Dict[str, Any]) -> SearchPlannerProfile:
    explicit_profile = _normalize_ascii(str(job_context.get("planner_profile") or job_context.get("search_mode") or ""))
    explicit_aliases = {
        "generic": "generic_business",
        "generic_business": "generic_business",
        "coach": "creator_coach",
        "creator": "creator_coach",
        "creator_coach": "creator_coach",
        "coach_creator": "creator_coach",
        "ecommerce": "ecommerce_content",
        "ecommerce_content": "ecommerce_content",
        "shopify": "ecommerce_content",
    }
    selected_key = explicit_aliases.get(explicit_profile)
    if selected_key:
        return PLANNER_PROFILES[selected_key]  # type: ignore[index]

    searchable_blob = _collect_profile_context_blob(job_context)
    creator_score = _count_profile_hint_matches(searchable_blob, CREATOR_COACH_HINTS)
    ecommerce_score = _count_profile_hint_matches(searchable_blob, ECOMMERCE_HINTS)

    if ecommerce_score > creator_score and ecommerce_score >= 1:
        return PLANNER_PROFILES["ecommerce_content"]
    if creator_score >= 1:
        return PLANNER_PROFILES["creator_coach"]
    if ecommerce_score >= 1:
        return PLANNER_PROFILES["ecommerce_content"]
    return PLANNER_PROFILES["generic_business"]


def _split_location_candidates(raw_location: str | None) -> list[str]:
    normalized_location = _normalize_space(raw_location)
    if not normalized_location:
        return []
    if _normalize_ascii(normalized_location) in _GLOBAL_LOCATION_ALIASES:
        return []
    if not MULTI_LOCATION_SPLIT_PATTERN.search(normalized_location):
        return [normalized_location]
    return [
        candidate
        for candidate in (_normalize_space(part) for part in MULTI_LOCATION_SPLIT_PATTERN.split(normalized_location))
        if candidate
    ]


def _resolve_geo_scope(job_context: Dict[str, Any]) -> dict[str, Any] | None:
    location_candidates = _split_location_candidates(job_context.get("target_location"))
    if len(location_candidates) != 1:
        return None

    raw_location = location_candidates[0]
    canonical_location = LOCATION_ALIAS_INDEX.get(_normalize_ascii(raw_location), raw_location)
    aliases = LOCATION_ALIAS_RULES.get(canonical_location, (raw_location,))
    normalized_aliases = tuple(
        normalized_alias
        for normalized_alias in (_normalize_ascii(alias) for alias in (canonical_location, *aliases))
        if normalized_alias
    )
    return {
        "label": canonical_location,
        "canonical": canonical_location,
        "aliases": normalized_aliases,
    }


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
    geo_scope: dict[str, Any] | None,
) -> list[str]:
    if not geo_scope:
        return _dedupe_strings(queries)

    filtered: list[str] = []
    for query in _dedupe_strings(queries):
        normalized_query = _normalize_ascii(query)
        has_conflicting_location = False
        for canonical_location, aliases in LOCATION_ALIAS_RULES.items():
            if canonical_location == geo_scope["canonical"]:
                continue
            normalized_candidates = [_normalize_ascii(canonical_location), *(_normalize_ascii(alias) for alias in aliases)]
            if any(candidate and candidate in normalized_query for candidate in normalized_candidates):
                has_conflicting_location = True
                break
        if has_conflicting_location:
            continue
        if not any(alias in normalized_query for alias in geo_scope["aliases"]):
            query = _normalize_space(f"{query} {geo_scope['label']}")
        filtered.append(query)
    return _dedupe_strings(filtered)


def _normalize_negative_terms(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for value in _dedupe_strings(values):
        prefixed = value if value.startswith("-") else f"-{value}"
        normalized.append(prefixed)
    return normalized


def _sanitize_profile_queries(queries: list[str], profile: SearchPlannerProfile) -> list[str]:
    sanitized_queries = _dedupe_strings(queries)
    if profile.key != "ecommerce_content":
        return sanitized_queries

    filtered_queries: list[str] = []
    for query in sanitized_queries:
        normalized_query = _normalize_ascii(query)
        if any(blocked_hint in normalized_query for blocked_hint in ECOMMERCE_BLOCKED_QUERY_HINTS):
            continue
        filtered_queries.append(query)
    return filtered_queries


def _render_numbered_rules(*rule_groups: tuple[str, ...]) -> str:
    lines: list[str] = []
    counter = 1
    for rule_group in rule_groups:
        for rule in rule_group:
            lines.append(f"{counter}. {rule}")
            counter += 1
    return "\n".join(lines)


def _build_initial_system_prompt(profile: SearchPlannerProfile) -> str:
    base_rules = (
        "Genera 3 a 6 queries comerciales, especificas y accionables.",
        "Busca clientes finales exactos para outreach, no proveedores ni intermediarios.",
        "Evita blogs, medios, escuelas, directorios, listados, software, assets, fuentes, tools y paginas informativas.",
        "Si existe una ubicacion objetivo unica, no abras geografia fuera de esa ubicacion.",
        "Devuelve terminos negativos utiles y hints para el clasificador final.",
    )
    profile_rules = (
        f"Trabaja en modo {profile.label} y prioriza: {', '.join(profile.priority_signals)}.",
        f"Rechaza especialmente: {', '.join(profile.exclusion_focus)}.",
    )
    return f"""Eres un experto mundial en OSINT, Growth Hacking y prospeccion comercial.

Tu tarea es disenar un Search Plan para encontrar CLIENTES FINALES EXACTOS para outreach.

REGLAS:
{_render_numbered_rules(base_rules, profile_rules)}

SALIDA JSON:
{{
  "optimal_dork_queries": ["..."],
  "dynamic_negative_terms": ["-blog"],
  "target_entity_hints": ["..."],
  "exclusion_entity_hints": ["..."],
  "refinement_goal": "..."
}}
"""


def _build_refinement_system_prompt(profile: SearchPlannerProfile) -> str:
    base_rules = (
        "Aumenta prospectos finales validos.",
        "Reduce ruido y falsos positivos.",
        "No repitas queries ya usadas.",
        "Si existe una ubicacion objetivo unica, no abras geografia fuera de esa ubicacion.",
        "Excluye directorios, listados, blogs, medios, assets y paginas oportunistas por keyword.",
    )
    profile_rules = (
        f"Trabaja en modo {profile.label} y prioriza: {', '.join(profile.priority_signals)}.",
        f"Endurece exclusiones para: {', '.join(profile.exclusion_focus)}.",
    )
    return f"""Eres un experto en iteracion de discovery comercial.

Debes revisar los resultados previos de un job y proponer nuevas queries MAS ESPECIFICAS.

OBJETIVO:
{_render_numbered_rules(base_rules, profile_rules)}

Si viste falsos positivos, usalos para endurecer terminos negativos y exclusiones.

SALIDA JSON:
{{
  "optimal_dork_queries": ["..."],
  "dynamic_negative_terms": ["-blog"],
  "target_entity_hints": ["..."],
  "exclusion_entity_hints": ["..."],
  "refinement_goal": "..."
}}
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


def _build_mode_summary_lines(profile: SearchPlannerProfile, geo_scope: dict[str, Any] | None) -> list[str]:
    geo_label = geo_scope["label"] if geo_scope else "Flexible o multiple opciones"
    return [
        "MODO DE BUSQUEDA:",
        f"- Perfil activo: {profile.label}",
        f"- Ubicacion operativa: {geo_label}",
        f"- Target valido: {profile.target_description}",
        f"- Priorizar: {', '.join(profile.priority_signals)}",
        f"- Rechazar: {', '.join(profile.exclusion_focus)}",
    ]


def _build_initial_user_prompt(
    job_context: Dict[str, Any],
    profile: SearchPlannerProfile,
    geo_scope: dict[str, Any] | None,
) -> str:
    buyer_persona = _build_buyer_persona(job_context)
    return "\n".join(
        [
            "PERFIL DEL VENDEDOR:",
            buyer_persona,
            "",
            *_build_mode_summary_lines(profile, geo_scope),
        ]
    )


def _build_refinement_user_prompt(
    job_context: Dict[str, Any],
    iteration_memory: Dict[str, Any] | None,
    profile: SearchPlannerProfile,
    geo_scope: dict[str, Any] | None,
) -> str:
    buyer_persona = _build_buyer_persona(job_context)
    geo_policy = geo_scope["label"] if geo_scope else "Flexible o multiple opciones"
    return "\n".join(
        [
            "REQUEST ORIGINAL DEL USUARIO:",
            buyer_persona,
            "",
            *_build_mode_summary_lines(profile, geo_scope),
            "",
            "POLITICA FIJA:",
            f"- Ubicacion operativa: {geo_policy}",
            f"- Target valido: {profile.target_description}",
            f"- Rechazar: {', '.join(profile.exclusion_focus)}",
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
    profile = _resolve_planner_profile(job_context)
    base_parts = [
        mode,
        profile.key,
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
    profile: SearchPlannerProfile,
    geo_scope: dict[str, Any] | None,
) -> Dict[str, Any]:
    payload = AISearchPlanPayload.model_validate(parsed_data)
    result = payload.model_dump()
    sanitized_queries = _sanitize_profile_queries(result.get("optimal_dork_queries", []), profile)
    result["optimal_dork_queries"] = _enforce_geo_policy(
        sanitized_queries,
        geo_scope=geo_scope,
    )
    result["dynamic_negative_terms"] = _normalize_negative_terms(result.get("dynamic_negative_terms", []))
    result["target_entity_hints"] = _dedupe_strings(
        [*profile.default_target_entity_hints, *(result.get("target_entity_hints", []) or [])]
    )
    result["exclusion_entity_hints"] = _dedupe_strings(
        [*profile.default_exclusion_entity_hints, *(result.get("exclusion_entity_hints", []) or [])]
    )
    result["refinement_goal"] = _normalize_space(result.get("refinement_goal"))
    result["planner_profile"] = profile.key
    result["geo_scope"] = geo_scope["label"] if geo_scope else None
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

    profile = _resolve_planner_profile(job_context)
    geo_scope = _resolve_geo_scope(job_context)
    if mode == "refinement":
        system_prompt = _build_refinement_system_prompt(profile)
        user_prompt = _build_refinement_user_prompt(job_context, iteration_memory, profile, geo_scope)
    else:
        system_prompt = _build_initial_system_prompt(profile)
        user_prompt = _build_initial_user_prompt(job_context, profile, geo_scope)

    try:
        parsed_data = await _call_planner(system_prompt=system_prompt, user_prompt=user_prompt)
        result_dict = _coerce_plan_payload(parsed_data, profile=profile, geo_scope=geo_scope)
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
