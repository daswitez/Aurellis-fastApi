from __future__ import annotations

import logging
import re

from app.config import get_settings
from app.scraper.search_engines.ddg_search import DuckDuckGoHtmlSearchProvider
from app.scraper.search_engines.google_search import GoogleHtmlSearchProvider
from app.services.discovery_types import SearchDiscoveryEntry, SearchDiscoveryResult
from app.services.search_providers import BraveSearchProvider, SearchProvider

logger = logging.getLogger(__name__)

DEMO_FALLBACK_URLS = [
    "https://www.clinicaveterinariamiraflores.pe/",
    "https://www.veterinariarondon.com/",
    "https://www.veterinariaanimalpolis.pe/",
]
DEFAULT_SEARCH_PROVIDER_ORDER = ("duckduckgo_html",)
DISCOVERY_PROVIDER_OVERFETCH_MULTIPLIER = 3
DISCOVERY_PROVIDER_OVERFETCH_CAP = 30
DISCOVERY_LANGUAGE_HINTS = {
    "es": [" el ", " la ", " de ", " para ", " con ", " coach ", " coaches ", " marca personal ", " cursos ", " programa ", " negocios "],
    "en": [" the ", " and ", " for ", " with ", " official ", " schedule ", " shop ", " discover ", " article ", " causes "],
    "pt": [" do ", " da ", " em ", " artigo ", " confira ", " historia ", " historia - ", " politica "],
    "zh": [" 知道 ", " 百度 ", " 问答 ", " 官方 ", " 全球领先 "],
}
DISCOVERY_TARGET_TOPIC_HINTS = {
    "personal_brand": ["marca personal", "marcas personales", "personal brand", "branding personal"],
    "coaching": ["coach", "coaches", "coaching", "mentor", "mentora", "mentoria", "mentoría", "mentoring", "negocios", "emprendedores"],
    "education": ["curso", "cursos", "programa", "masterclass", "infoproducto", "infoproductos", "academia", "formacion", "formación"],
    "social_short_form": ["instagram", "tiktok", "reels", "shorts", "youtube shorts", "linktree", "link in bio"],
}
DISCOVERY_OFF_TARGET_HINTS = {
    "sports": [" schedule ", " hockey ", " nhl ", " tickets ", " ticket ", " calendar ", " game "],
    "media": [" broadcasting ", " newsroom ", " radio ", " latest news ", " trusted news ", " worldatlas ", " atlas ", " oscar ", " casual "],
    "reference": [" crimea ", " peninsula ", " geography ", " encyclopedia ", " enciclopedia ", " historia ", " artigo ", " article ", " zhihu ", " q&a ", " question ", " preguntas y respuestas "],
    "retail": [" polo ", " polos ", " shirt ", " shirts ", " collar ", " vitamins ", " supplements ", " collection "],
    "academic_editorial": [" que es el ecommerce ", " qué es el ecommerce ", " posgrado ", " instituto ", ".edu.", " universidad "],
    "search_utility": [" bing ", " imagenes ", " imágenes ", " wallpaper ", " fondos de pantalla ", "/images/feed", "duckduckgo", "search.yahoo.com"],
    "quiz_trivia": [" quiz ", " trivia ", " entertainment quiz ", " daily quiz ", " microsoft rewards "],
    "health": [" kidney ", " creatinine ", " injury ", " disease ", " causes ", " health ", " medical "],
}
DISCOVERY_LOCATION_HINTS = {
    "espana": [" espana ", " madrid ", " barcelona ", ".es"],
}


def _parse_provider_order(raw_value: str | None) -> list[str]:
    if not raw_value:
        return list(DEFAULT_SEARCH_PROVIDER_ORDER)
    return [item.strip().lower() for item in raw_value.split(",") if item.strip()]


def _build_providers() -> list[SearchProvider]:
    settings = get_settings()
    provider_order = _parse_provider_order(settings.SEARCH_PROVIDER_ORDER)
    providers: list[SearchProvider] = []

    for provider_name in provider_order:
        if provider_name == "brave_api":
            providers.append(BraveSearchProvider())
        elif provider_name in {"duckduckgo_html", "ddg_html", "duckduckgo"}:
            providers.append(DuckDuckGoHtmlSearchProvider())
        elif provider_name in {"google_html", "google"}:
            providers.append(GoogleHtmlSearchProvider())
        else:
            logger.warning("Proveedor de discovery desconocido: %s", provider_name)

    return providers


def _build_demo_result(queries: list[str], max_results: int, warning_message: str | None, excluded_results: list[dict]) -> SearchDiscoveryResult:
    demo_message = warning_message or f"No hubo resultados reales para queries: {queries!r}."
    return SearchDiscoveryResult(
        entries=[
            SearchDiscoveryEntry(
                url=url,
                query=queries[0] if queries else None,
                position=index,
                title="Demo result",
                snippet=demo_message,
                discovery_confidence="low",
            )
            for index, url in enumerate(DEMO_FALLBACK_URLS[:max_results], start=1)
        ],
        source_type="mock_search",
        discovery_method="search_query",
        warning_message=f"{demo_message} Se activo fallback demo.",
        queries=queries,
        excluded_results=excluded_results,
        provider_name="demo_fallback",
        provider_status="ok",
    )


def _should_allow_social_profiles(user_profession: str | None) -> bool:
    if not user_profession:
        return False
    prof = user_profession.lower()
    creative_roles = [
        "editor", "video", "videographer", "creative", "creador", "designer",
        "diseñador", "developer", "desarrollador", "marketing", "web", "seo",
        "fotograf", "photograph", "community manager", "social media"
    ]
    return any(role in prof for role in creative_roles)


def _normalize_discovery_blob(*parts: str | None) -> str:
    cleaned = " ".join(str(part or "").strip() for part in parts if str(part or "").strip())
    ascii_blob = cleaned.encode("ascii", "ignore").decode("ascii").lower()
    normalized = re.sub(r"\s+", " ", ascii_blob)
    return f" {normalized} "


def _extract_context_keywords(target_niche: str | None, target_budget_signals: list[str] | None) -> set[str]:
    raw_keywords = re.findall(
        r"[a-z0-9]{4,}",
        _normalize_discovery_blob(target_niche, " ".join(target_budget_signals or [])),
    )
    stopwords = {
        "para",
        "with",
        "from",
        "this",
        "that",
        "target",
        "activos",
        "tienen",
        "mas",
        "seguidores",
        "tienda",
        "oficial",
    }
    return {keyword for keyword in raw_keywords if keyword not in stopwords}


def _detect_discovery_language(title: str | None, snippet: str | None) -> str | None:
    raw_blob = " ".join(str(part or "") for part in [title, snippet])
    if re.search(r"[\u4e00-\u9fff]", raw_blob):
        return "zh"
    blob = _normalize_discovery_blob(title, snippet)
    scores = {
        language: sum(blob.count(token) for token in tokens)
        for language, tokens in DISCOVERY_LANGUAGE_HINTS.items()
    }
    detected_language, detected_score = max(scores.items(), key=lambda item: item[1])
    return detected_language if detected_score > 1 else None


def _resolve_context_topics(target_niche: str | None, target_budget_signals: list[str] | None) -> set[str]:
    searchable = _normalize_discovery_blob(target_niche, " ".join(target_budget_signals or []))
    topics: set[str] = set()
    if any(token in searchable for token in [" marca personal ", " marcas personales ", " personal brand ", " branding personal "]):
        topics.add("personal_brand")
    if any(token in searchable for token in [" coach ", " coaches ", " coaching ", " mentor ", " mentoria ", " mentoring "]):
        topics.add("coaching")
    if any(token in searchable for token in [" curso ", " cursos ", " programa ", " infoproducto ", " infoproductos ", " academia "]):
        topics.add("education")
    if any(token in searchable for token in [" instagram ", " tiktok ", " reels ", " shorts ", " linktree ", " link in bio "]):
        topics.add("social_short_form")
    return topics


def _score_discovery_entry_context(
    entry: SearchDiscoveryEntry,
    *,
    target_niche: str | None,
    target_language: str | None,
    target_location: str | None,
    target_budget_signals: list[str] | None,
    user_profession: str | None,
) -> tuple[float, list[str], str | None]:
    reasons: list[str] = []
    score = 0.0
    blob = _normalize_discovery_blob(entry.title, entry.snippet, entry.url)
    target_lang = str(target_language or "").strip().lower()
    detected_language = _detect_discovery_language(entry.title, entry.snippet)
    context_keywords = _extract_context_keywords(target_niche, target_budget_signals)

    if target_lang and detected_language and detected_language != target_lang:
        return -3.0, ["discovery_target_language_mismatch"], "excluded_discovery_language_mismatch"
    if target_lang and detected_language and detected_language == target_lang:
        score += 1.0
        reasons.append("discovery_target_language_match")

    matched_topics: list[str] = []
    for topic in sorted(_resolve_context_topics(target_niche, target_budget_signals)):
        if any(token in blob for token in DISCOVERY_TARGET_TOPIC_HINTS.get(topic, [])):
            matched_topics.append(topic)
            score += 1.5
            reasons.append(f"discovery_topic_{topic}")

    if len(matched_topics) >= 2:
        score += 1.0
        reasons.append("discovery_multi_topic_match")

    if _should_allow_social_profiles(user_profession):
        if any(token in blob for token in [" instagram ", " tiktok ", " reels ", " shorts ", " linktree ", " link in bio "]):
            score += 1.0
            reasons.append("discovery_social_first_match")

    direct_keyword_hits = sum(1 for keyword in context_keywords if f" {keyword} " in blob)
    if direct_keyword_hits >= 2:
        score += 1.0
        reasons.append("discovery_context_keyword_overlap")
    elif direct_keyword_hits == 1:
        score += 0.4
        reasons.append("discovery_context_keyword_partial")

    normalized_location = _normalize_discovery_blob(target_location)
    if normalized_location.strip():
        location_hints = DISCOVERY_LOCATION_HINTS.get(normalized_location.strip(), [normalized_location.strip()])
        if any(hint in blob for hint in location_hints):
            score += 0.75
            reasons.append("discovery_target_location_match")

    off_target_hits = [
        bucket
        for bucket, hints in DISCOVERY_OFF_TARGET_HINTS.items()
        if any(hint in blob for hint in hints)
    ]
    if off_target_hits and not matched_topics:
        score -= min(2.0, float(len(off_target_hits)))
        reasons.extend([f"discovery_off_target:{bucket}" for bucket in off_target_hits])

    has_positive_alignment = bool(matched_topics) or direct_keyword_hits >= 2 or "discovery_social_first_match" in reasons
    if target_niche and not has_positive_alignment:
        reasons.append("discovery_no_target_alignment")
        return score, reasons, "excluded_discovery_context_mismatch"
    if target_niche and not matched_topics and off_target_hits:
        return score, reasons, "excluded_discovery_context_mismatch"
    return score, reasons, None


def _filter_entries_by_context(
    entries: list[SearchDiscoveryEntry],
    *,
    target_niche: str | None,
    target_language: str | None,
    target_location: str | None,
    target_budget_signals: list[str] | None,
    user_profession: str | None,
) -> tuple[list[SearchDiscoveryEntry], list[dict]]:
    filtered_entries: list[SearchDiscoveryEntry] = []
    excluded_results: list[dict] = []
    scored_entries: list[tuple[float, SearchDiscoveryEntry]] = []

    for entry in entries:
        context_score, context_reasons, exclusion_reason = _score_discovery_entry_context(
            entry,
            target_niche=target_niche,
            target_language=target_language,
            target_location=target_location,
            target_budget_signals=target_budget_signals,
            user_profession=user_profession,
        )
        entry.discovery_reasons = [*(entry.discovery_reasons or []), *context_reasons]
        if exclusion_reason:
            excluded_results.append(
                {
                    "url": entry.url,
                    "reason": exclusion_reason,
                    "query": entry.query,
                    "title": entry.title,
                    "snippet": entry.snippet,
                    "business_likeness_score": entry.business_likeness_score,
                    "website_result_score": entry.website_result_score,
                    "social_profile_score": entry.social_profile_score,
                    "result_kind": entry.result_kind,
                    "discovery_reasons": entry.discovery_reasons,
                }
            )
            continue
        scored_entries.append((context_score, entry))

    scored_entries.sort(
        key=lambda item: (
            -item[0],
            -(item[1].business_likeness_score or 0.0),
            0 if item[1].discovery_confidence == "high" else 1,
            len(item[1].url),
        )
    )
    filtered_entries = [entry for _, entry in scored_entries]
    return filtered_entries, excluded_results


async def discover_prospect_urls_by_queries(
    queries: list[str],
    max_results: int = 10,
    user_profession: str | None = None,
    target_niche: str | None = None,
    target_language: str | None = None,
    target_location: str | None = None,
    target_budget_signals: list[str] | None = None,
) -> SearchDiscoveryResult:
    if not queries:
        return SearchDiscoveryResult(
            entries=[],
            source_type="duckduckgo_search",
            discovery_method="search_query",
            warning_message="No se enviaron queries de discovery.",
            queries=[],
            provider_name=None,
            provider_status="invalid_request",
            failure_reason="missing_queries",
        )

    settings = get_settings()
    warning_messages: list[str] = []
    excluded_results: list[dict] = []
    last_result: SearchDiscoveryResult | None = None
    providers = [provider for provider in _build_providers() if provider.is_available()]

    if not providers:
        provider_warning = "No hay proveedores de discovery disponibles."
        if settings.DEMO_MODE:
            return _build_demo_result(queries, max_results, provider_warning, excluded_results)
        return SearchDiscoveryResult(
            entries=[],
            source_type="duckduckgo_search",
            discovery_method="search_query",
            warning_message=provider_warning,
            queries=queries,
            excluded_results=[],
            provider_name=None,
            provider_status="unavailable",
            failure_reason="no_providers_available",
        )

    allow_social_profiles = _should_allow_social_profiles(user_profession)
    provider_fetch_limit = max(
        int(max_results or 0),
        min(DISCOVERY_PROVIDER_OVERFETCH_CAP, max(int(max_results or 0), 1) * DISCOVERY_PROVIDER_OVERFETCH_MULTIPLIER),
    )

    for provider in providers:
        result = await provider.search(
            queries,
            max_results=provider_fetch_limit,
            allow_social_profiles=allow_social_profiles,
        )
        last_result = result
        filtered_entries, context_excluded = _filter_entries_by_context(
            result.entries,
            target_niche=target_niche,
            target_language=target_language,
            target_location=target_location,
            target_budget_signals=target_budget_signals,
            user_profession=user_profession,
        )
        excluded_results.extend(result.excluded_results)
        excluded_results.extend(context_excluded)
        if result.warning_message:
            warning_messages.append(result.warning_message)

        if filtered_entries:
            result.entries = filtered_entries[:max_results]
            result.excluded_results = excluded_results
            result.warning_message = "; ".join(warning_messages) if warning_messages else None
            return result

    combined_warning = "; ".join(warning_messages) if warning_messages else None
    if settings.DEMO_MODE:
        return _build_demo_result(queries, max_results, combined_warning, excluded_results)

    if last_result is None:
        return SearchDiscoveryResult(
            entries=[],
            source_type="duckduckgo_search",
            discovery_method="search_query",
            warning_message=combined_warning or f"No hubo resultados reales para queries: {queries!r}.",
            queries=queries,
            excluded_results=excluded_results,
            provider_name=None,
            provider_status="no_results",
            failure_reason="no_results",
        )

    last_result.excluded_results = excluded_results
    last_result.warning_message = combined_warning or last_result.warning_message
    return last_result
