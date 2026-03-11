from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any
from urllib.parse import urlparse


LANGUAGE_HINTS = {
    "es": [" el ", " la ", " clinica ", " contacto ", " servicios ", " nosotros "],
    "en": [" the ", " contact ", " services ", " about ", " booking "],
    "pt": [" o ", " a ", " servicos ", " serviços ", " contato "],
}
STOPWORDS = {
    "de",
    "la",
    "el",
    "y",
    "para",
    "con",
    "una",
    "que",
    "los",
    "las",
    "por",
    "our",
    "your",
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "site",
    "home",
    "about",
    "contact",
    "servicios",
    "service",
    "services",
    "clinica",
    "clinic",
}
LOCATION_SIGNAL_RULES = {
    "argentina": {
        "display_name": "Argentina",
        "target_aliases": ["argentina"],
        "country_codes": ["ar"],
        "match_aliases": ["argentina", "buenos aires"],
        "tlds": [".ar"],
        "phone_prefixes": ["+54"],
    },
    "espana": {
        "display_name": "España",
        "target_aliases": ["espana", "españa", "spain"],
        "country_codes": ["es"],
        "match_aliases": ["espana", "españa", "spain", "madrid", "barcelona", "valencia"],
        "tlds": [".es"],
        "phone_prefixes": ["+34"],
    },
    "mexico": {
        "display_name": "México",
        "target_aliases": ["mexico", "méxico"],
        "country_codes": ["mx"],
        "match_aliases": ["mexico", "méxico", "cdmx", "ciudad de mexico", "ciudad de méxico"],
        "tlds": [".mx"],
        "phone_prefixes": ["+52"],
    },
    "peru": {
        "display_name": "Perú",
        "target_aliases": ["peru", "perú"],
        "country_codes": ["pe"],
        "match_aliases": ["peru", "perú", "lima"],
        "tlds": [".pe"],
        "phone_prefixes": ["+51"],
    },
    "colombia": {
        "display_name": "Colombia",
        "target_aliases": ["colombia"],
        "country_codes": ["co"],
        "match_aliases": ["colombia", "bogota", "bogotá"],
        "tlds": [".co"],
        "phone_prefixes": ["+57"],
    },
    "chile": {
        "display_name": "Chile",
        "target_aliases": ["chile"],
        "country_codes": ["cl"],
        "match_aliases": ["chile", "santiago"],
        "tlds": [".cl"],
        "phone_prefixes": ["+56"],
    },
    "uruguay": {
        "display_name": "Uruguay",
        "target_aliases": ["uruguay"],
        "country_codes": ["uy"],
        "match_aliases": ["uruguay", "montevideo"],
        "tlds": [".uy"],
        "phone_prefixes": ["+598"],
    },
    "bolivia": {
        "display_name": "Bolivia",
        "target_aliases": ["bolivia"],
        "country_codes": ["bo"],
        "match_aliases": ["bolivia", "la paz", "santa cruz", "cochabamba"],
        "tlds": [".bo"],
        "phone_prefixes": ["+591"],
    },
}
HIGH_CONFIDENCE_GEO_SOURCES = {"address", "map", "phone_prefix", "tld"}
MEDIUM_CONFIDENCE_GEO_SOURCES = {
    "area_served",
    "postal_address_country",
    "title",
    "description",
    "discovery_title",
    "discovery_snippet",
}
LOCATION_STREET_HINTS = (
    "calle",
    "avenida",
    "av",
    "street",
    "st",
    "road",
    "rd",
    "plaza",
    "paseo",
    "carrera",
    "camino",
    "suite",
    "ste",
    "oficina",
    "office",
    "local",
    "piso",
)
LOCATION_NOISE_HINTS = (
    "tel",
    "telefono",
    "telefono:",
    "teléfono",
    "phone",
    "whatsapp",
    "horario",
    "horarios",
    "hours",
    "lunes",
    "martes",
    "miercoles",
    "miércoles",
    "jueves",
    "viernes",
    "sabado",
    "sábado",
    "domingo",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
POSTAL_CODE_REGEX = re.compile(r"\b[A-Z]{0,2}\d{4,6}[A-Z]{0,3}\b", re.IGNORECASE)
URL_REGEX = re.compile(r"https?://\S+", re.IGNORECASE)
DIRECTORY_ENTITY_TYPES = {"directory", "aggregator", "marketplace"}
MEDIA_ENTITY_TYPES = {"media", "association"}
ARTICLE_ENTITY_TYPES = {"blog_post"}
GENERIC_EMAIL_DOMAINS = {
    "gmail.com",
    "outlook.com",
    "hotmail.com",
    "yahoo.com",
    "icloud.com",
    "proton.me",
    "protonmail.com",
    "live.com",
}
COMMON_SECOND_LEVEL_TLDS = {"com", "net", "org", "gov", "edu", "co"}
CONTACT_SOURCE_CONFIDENCE = {
    "structured_data": "high",
    "mailto_link": "high",
    "tel_link": "high",
    "visible_text": "medium",
    "metadata_list": "medium",
    "html_form": "medium",
    "whatsapp_link": "medium",
    "booking_link": "medium",
    "unknown": "medium",
}
CONTACT_CONFIDENCE_TO_SCORE = {
    "low": 0.35,
    "medium": 0.65,
    "high": 0.9,
}
TARGET_ECOMMERCE_HINTS = ("ecommerce", "tienda online", "shopify")
TARGET_EDUCATION_HINTS = ("academia online", "cursos online", "escuela online", "formacion online", "productos digitales", "infoproductos")
SERVICE_PROVIDER_HINTS = (
    "asesoria",
    "asesoría",
    "consultoria",
    "consultoría",
    "consultor",
    "consultora",
    "coach",
    "coaching",
    "mentor",
    "mentoria",
    "mentoría",
    "agencia",
    "servicios para empresas",
    "presupuesto",
)
ECOMMERCE_BUSINESS_HINTS = (
    "tienda online",
    "ecommerce",
    "shopify",
    "carrito",
    "checkout",
    "comprar",
    "añadir al carrito",
    "anadir al carrito",
    "coleccion",
    "colección",
    "catalogo",
    "catálogo",
)
EDUCATION_BUSINESS_HINTS = (
    "academia",
    "curso",
    "cursos",
    "masterclass",
    "programa",
    "formacion",
    "formación",
    "alumnos",
    "inscripcion",
    "inscripción",
    "campus",
    "clases",
)
PRODUCT_PAGE_HINTS = (
    "añadir al carrito",
    "anadir al carrito",
    "carrito",
    "sku",
    "referencia",
    "serie completa",
    "distribuidor oficial",
    "catalogo",
    "catálogo",
)


def _build_country_alias_lookup() -> dict[str, str]:
    lookup: dict[str, str] = {}
    for canonical_name, rule in LOCATION_SIGNAL_RULES.items():
        display_name = str(rule.get("display_name") or canonical_name)
        for candidate in [
            canonical_name,
            display_name,
            *rule.get("target_aliases", []),
            *rule.get("match_aliases", []),
            *rule.get("country_codes", []),
        ]:
            normalized_candidate = _normalize_geo_token(candidate)
            if normalized_candidate:
                lookup[normalized_candidate] = display_name
    return lookup


def _normalize_text(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    return f" {normalized} " if normalized else " "


def _normalize_geo_token(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    normalized = normalized.encode("ascii", "ignore").decode("ascii").strip().lower()
    return re.sub(r"\s+", " ", normalized)


COUNTRY_ALIAS_LOOKUP = _build_country_alias_lookup()


def _derive_target_business_models(context: dict[str, Any]) -> set[str]:
    searchable = " ".join(
        [
            str(context.get("target_niche") or ""),
            str(context.get("user_target_offer_focus") or ""),
        ]
    ).lower()
    models: set[str] = set()
    if any(token in searchable for token in TARGET_ECOMMERCE_HINTS):
        models.add("ecommerce_business")
    if any(token in searchable for token in TARGET_EDUCATION_HINTS):
        models.add("education_business")
    return models


def _detect_observed_business_model(
    clean_text: str,
    metadata: dict[str, Any],
    entity_type_detected: str | None,
) -> str | None:
    searchable = " ".join(
        [
            clean_text[:2400],
            str(metadata.get("title") or ""),
            str(metadata.get("description") or ""),
            " ".join(str(link) for link in metadata.get("internal_links", [])[:8]),
            str(metadata.get("website_url") or ""),
        ]
    ).lower()
    normalized_entity_type = str(entity_type_detected or "").strip().lower()

    if normalized_entity_type in {"consultant", "agency"} or any(token in searchable for token in SERVICE_PROVIDER_HINTS):
        return "service_provider"
    if any(token in searchable for token in PRODUCT_PAGE_HINTS):
        return "product_page"
    if any(token in searchable for token in EDUCATION_BUSINESS_HINTS):
        return "education_business"
    if any(token in searchable for token in ECOMMERCE_BUSINESS_HINTS):
        return "ecommerce_business"
    return None


def _assess_business_model_fit(
    *,
    clean_text: str,
    metadata: dict[str, Any],
    context: dict[str, Any],
    entity_type_detected: str | None,
) -> dict[str, Any]:
    target_models = _derive_target_business_models(context)
    observed_model = _detect_observed_business_model(clean_text, metadata, entity_type_detected)

    if not target_models:
        return {
            "target_business_models": [],
            "observed_business_model": observed_model,
            "business_model_fit_status": "unknown",
        }
    if observed_model in target_models:
        fit_status = "match"
    elif observed_model in {"service_provider", "product_page"}:
        fit_status = "mismatch"
    else:
        fit_status = "unknown"
    return {
        "target_business_models": sorted(target_models),
        "observed_business_model": observed_model,
        "business_model_fit_status": fit_status,
    }


def _resolve_location_signal_rule(target_location: str | None) -> dict[str, Any] | None:
    normalized_target = _normalize_geo_token(target_location)
    if not normalized_target:
        return None

    for rule in LOCATION_SIGNAL_RULES.values():
        target_aliases = {
            _normalize_geo_token(alias)
            for alias in [*rule.get("target_aliases", []), *rule.get("country_codes", [])]
        }
        if normalized_target in target_aliases:
            return rule
    return None


def _normalize_country_evidence(value: str | None) -> str | None:
    normalized_value = _normalize_geo_token(value)
    if not normalized_value:
        return None

    for canonical_name, rule in LOCATION_SIGNAL_RULES.items():
        candidates = {
            canonical_name,
            *(_normalize_geo_token(alias) for alias in rule.get("target_aliases", [])),
            *(_normalize_geo_token(code) for code in rule.get("country_codes", [])),
        }
        if normalized_value in candidates:
            return str(rule.get("display_name") or canonical_name)
    return normalized_value


def _rule_match_aliases(rule: dict[str, Any]) -> set[str]:
    aliases = {
        _normalize_geo_token(alias)
        for alias in [*rule.get("match_aliases", []), *rule.get("target_aliases", [])]
    }
    return {alias for alias in aliases if alias}


def _detect_language(clean_text: str, metadata: dict[str, Any]) -> str | None:
    html_lang = str(metadata.get("html_lang") or "").strip().lower()
    if html_lang:
        return html_lang.split("-")[0]

    meta_locale = str(metadata.get("meta_locale") or "").strip().lower()
    if meta_locale:
        return meta_locale.split("_")[0].split("-")[0]

    searchable = _normalize_text(clean_text)
    scores = {
        language: sum(searchable.count(token) for token in tokens)
        for language, tokens in LANGUAGE_HINTS.items()
    }
    detected_language, score = max(scores.items(), key=lambda item: item[1], default=(None, 0))
    return detected_language if score > 1 else None


def _extract_geo_evidence(
    metadata: dict[str, Any],
    discovery_metadata: dict[str, Any],
    target_location: str | None,
) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    for address in metadata.get("addresses", []):
        evidence.append({"source": "address", "value": address})
    for map_link in metadata.get("map_links", []):
        evidence.append({"source": "map", "value": map_link})
    for node in metadata.get("structured_data", []):
        area_served = node.get("areaServed") if isinstance(node, dict) else None
        if isinstance(area_served, list):
            for item in area_served:
                if isinstance(item, dict) and item.get("name"):
                    evidence.append({"source": "area_served", "value": str(item["name"])})
                elif isinstance(item, str):
                    evidence.append({"source": "area_served", "value": item})
        elif isinstance(area_served, dict) and area_served.get("name"):
            evidence.append({"source": "area_served", "value": str(area_served["name"])})
        elif isinstance(area_served, str):
            evidence.append({"source": "area_served", "value": area_served})
        if isinstance(node, dict):
            address = node.get("address")
            if isinstance(address, dict) and address.get("addressCountry"):
                normalized_country = _normalize_country_evidence(str(address["addressCountry"]))
                evidence.append({"source": "postal_address_country", "value": normalized_country or str(address["addressCountry"])})
    normalized_target = _normalize_geo_token(target_location)
    signal_rule = _resolve_location_signal_rule(target_location)
    website_url = str(metadata.get("website_url") or "")
    hostname = urlparse(website_url).netloc.lower().removeprefix("www.")
    if signal_rule and hostname:
        if any(hostname.endswith(tld) for tld in signal_rule["tlds"]):
            evidence.append({"source": "tld", "value": str(signal_rule.get("display_name") or normalized_target)})
    if signal_rule:
        for phone in metadata.get("phones", []):
            normalized_phone = str(phone or "").strip()
            if any(normalized_phone.startswith(prefix) for prefix in signal_rule["phone_prefixes"]):
                evidence.append({"source": "phone_prefix", "value": str(signal_rule.get("display_name") or normalized_target)})
    for field_name in ["title", "description"]:
        field_value = metadata.get(field_name)
        if field_value:
            evidence.append({"source": field_name, "value": str(field_value)})
    if discovery_metadata.get("title"):
        evidence.append({"source": "discovery_title", "value": str(discovery_metadata["title"])})
    if discovery_metadata.get("snippet"):
        evidence.append({"source": "discovery_snippet", "value": str(discovery_metadata["snippet"])})
    return evidence


def _sanitize_location_text(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None

    normalized = URL_REGEX.sub(" ", normalized)
    normalized = re.sub(r"[\n\r\t|;]+", ", ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip(" ,.-")
    return normalized[:240] or None


def _country_from_text(value: str | None) -> str | None:
    normalized_value = _normalize_geo_token(value)
    if not normalized_value:
        return None
    if normalized_value in COUNTRY_ALIAS_LOOKUP:
        return COUNTRY_ALIAS_LOOKUP[normalized_value]

    padded_value = f" {normalized_value} "
    for alias in sorted(COUNTRY_ALIAS_LOOKUP, key=len, reverse=True):
        if len(alias) <= 2:
            continue
        if f" {alias} " in padded_value:
            return COUNTRY_ALIAS_LOOKUP[alias]
    return None


def _is_country_token(value: str | None, country: str | None) -> bool:
    normalized_value = _normalize_geo_token(value)
    normalized_country = _normalize_geo_token(country)
    if not normalized_value or not normalized_country:
        return False

    for canonical_name, rule in LOCATION_SIGNAL_RULES.items():
        display_name = str(rule.get("display_name") or canonical_name)
        if _normalize_geo_token(display_name) != normalized_country:
            continue
        allowed_tokens = {
            _normalize_geo_token(candidate)
            for candidate in [canonical_name, display_name, *rule.get("target_aliases", []), *rule.get("country_codes", [])]
        }
        return normalized_value in allowed_tokens
    return False


def _normalize_location_fragment(value: str | None) -> str | None:
    normalized = " ".join(str(value or "").strip().split())
    return normalized[:120] or None


def _extract_postal_code(value: str | None) -> str | None:
    match = POSTAL_CODE_REGEX.search(str(value or ""))
    return match.group(0).upper() if match else None


def _remove_postal_code(value: str | None) -> str:
    return " ".join(POSTAL_CODE_REGEX.sub(" ", str(value or "")).split()).strip(" ,.-")


def _looks_like_street_fragment(value: str | None) -> bool:
    normalized = _normalize_geo_token(value)
    return bool(normalized) and any(
        normalized == hint
        or normalized.startswith(f"{hint} ")
        or f" {hint} " in f" {normalized} "
        for hint in LOCATION_STREET_HINTS
    )


def _looks_like_noise_fragment(value: str | None) -> bool:
    raw_value = str(value or "").strip()
    if not raw_value:
        return True
    normalized = _normalize_geo_token(raw_value)
    if not normalized:
        return True
    if "@" in raw_value or raw_value.lower().startswith(("http://", "https://", "www.")):
        return True
    if any(hint in f" {normalized} " for hint in LOCATION_NOISE_HINTS):
        return True
    digits_only = re.sub(r"\D", "", raw_value)
    return len(digits_only) >= 8 and not re.search(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]", raw_value)


def _structured_address_components(metadata: dict[str, Any]) -> dict[str, Any]:
    for node in metadata.get("structured_data", []):
        if not isinstance(node, dict):
            continue
        address = node.get("address")
        if isinstance(address, dict):
            city = _normalize_location_fragment(address.get("addressLocality"))
            region = _normalize_location_fragment(address.get("addressRegion"))
            postal_code = _extract_postal_code(address.get("postalCode"))
            country = _country_from_text(address.get("addressCountry")) or _normalize_location_fragment(address.get("addressCountry"))
            if not any([city, region, country, postal_code]):
                continue
            raw_parts = [
                _normalize_location_fragment(address.get("streetAddress")),
                city,
                region,
                postal_code,
                country,
            ]
            return {
                "city": city,
                "region": region,
                "country": country,
                "postal_code": postal_code,
                "raw_location_text": ", ".join(part for part in raw_parts if part)[:240] or None,
                "source": "structured_address",
            }
        if isinstance(address, str):
            parsed = _parse_location_text(address, source="structured_address")
            if any(parsed.get(field) for field in ("city", "region", "country", "postal_code")):
                return parsed
    return {}


def _parse_location_text(value: str | None, *, source: str) -> dict[str, Any]:
    sanitized_value = _sanitize_location_text(value)
    if not sanitized_value:
        return {"source": source}

    city: str | None = None
    region: str | None = None
    country = _country_from_text(sanitized_value)
    postal_code = _extract_postal_code(sanitized_value)
    locality_candidates: list[str] = []

    for raw_chunk in re.split(r"[,\n]", sanitized_value):
        chunk = _normalize_location_fragment(raw_chunk)
        if not chunk or _looks_like_noise_fragment(chunk):
            continue

        if not country:
            country = _country_from_text(chunk) or country
        cleaned_chunk = _normalize_location_fragment(_remove_postal_code(chunk))
        if not cleaned_chunk:
            continue
        if country and _normalize_geo_token(cleaned_chunk) == _normalize_geo_token(country):
            continue
        if country and _is_country_token(cleaned_chunk, country):
            continue
        locality_candidates.append(cleaned_chunk)

    if locality_candidates:
        filtered_candidates = [chunk for chunk in locality_candidates if not _looks_like_street_fragment(chunk)]
        ordered_candidates = filtered_candidates or locality_candidates
        city = ordered_candidates[-1]
        if len(ordered_candidates) > 1:
            candidate_region = ordered_candidates[-2]
            if _normalize_geo_token(candidate_region) != _normalize_geo_token(city):
                region = candidate_region

    return {
        "city": city,
        "region": region,
        "country": country,
        "postal_code": postal_code,
        "raw_location_text": sanitized_value,
        "source": source,
    }


def _merge_location_components(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for field in ("city", "region", "country", "postal_code"):
        if not merged.get(field) and incoming.get(field):
            if field == "region" and merged.get("city"):
                if _normalize_geo_token(incoming.get("region")) == _normalize_geo_token(merged.get("city")):
                    continue
            merged[field] = incoming[field]
    if not merged.get("raw_location_text") and incoming.get("raw_location_text"):
        merged["raw_location_text"] = incoming["raw_location_text"]
    if incoming.get("source"):
        merged.setdefault("source", incoming["source"])
    return merged


def _select_raw_location_text(metadata: dict[str, Any], geo_evidence: list[dict[str, str]]) -> str | None:
    for address in metadata.get("addresses", []):
        sanitized = _sanitize_location_text(address)
        if sanitized:
            return sanitized
    for evidence in geo_evidence:
        if evidence.get("source") in {"address", "area_served", "postal_address_country"}:
            sanitized = _sanitize_location_text(str(evidence.get("value") or ""))
            if sanitized:
                return sanitized
    return None


def _build_location_components(metadata: dict[str, Any], geo_evidence: list[dict[str, str]]) -> dict[str, Any]:
    components = _structured_address_components(metadata)

    raw_location_text = _select_raw_location_text(metadata, geo_evidence)
    if raw_location_text:
        components = _merge_location_components(
            components,
            _parse_location_text(raw_location_text, source="raw_location_text"),
        )
        components["raw_location_text"] = raw_location_text

    for evidence in geo_evidence:
        if evidence.get("source") not in {"address", "area_served", "postal_address_country", "tld", "phone_prefix"}:
            continue
        components = _merge_location_components(
            components,
            _parse_location_text(str(evidence.get("value") or ""), source=str(evidence.get("source") or "geo_evidence")),
        )

    return components


def _format_location_components(components: dict[str, Any]) -> str | None:
    city = _normalize_location_fragment(components.get("city"))
    region = _normalize_location_fragment(components.get("region"))
    country = _normalize_location_fragment(components.get("country"))
    postal_code = _normalize_location_fragment(components.get("postal_code"))

    locality_parts: list[str] = []
    if postal_code and city:
        locality_parts.append(f"{postal_code} {city}")
    elif city:
        locality_parts.append(city)
    elif postal_code:
        locality_parts.append(postal_code)

    if region and _normalize_geo_token(region) not in {
        _normalize_geo_token(part) for part in locality_parts + ([country] if country else [])
    }:
        locality_parts.append(region)
    if country and _normalize_geo_token(country) not in {
        _normalize_geo_token(part) for part in locality_parts
    }:
        locality_parts.append(country)

    return ", ".join(part for part in locality_parts if part)[:160] or None


def _finalize_parsed_location(components: dict[str, Any]) -> dict[str, Any] | None:
    formatted = _format_location_components(components)
    if not formatted:
        return None
    return {
        "formatted": formatted,
        "city": _normalize_location_fragment(components.get("city")),
        "region": _normalize_location_fragment(components.get("region")),
        "country": _normalize_location_fragment(components.get("country")),
        "postal_code": _normalize_location_fragment(components.get("postal_code")),
        "source": components.get("source"),
    }


def _best_geo_confidence(geo_evidence: list[dict[str, str]], parsed_location: dict[str, Any] | None) -> str:
    if any(evidence.get("source") in HIGH_CONFIDENCE_GEO_SOURCES for evidence in geo_evidence):
        return "high"
    if any(evidence.get("source") in MEDIUM_CONFIDENCE_GEO_SOURCES for evidence in geo_evidence) or parsed_location:
        return "medium"
    return "low"


def _looks_like_specific_location(value: str) -> bool:
    normalized = " ".join((value or "").split()).strip()
    if not normalized:
        return False

    lowered = normalized.lower()
    if len(normalized) < 6 or len(normalized) > 180:
        return False

    location_hints = (
        " argentina",
        " madrid",
        " mexico",
        " méxico",
        " españa",
        " spain",
        " buenos aires",
        " valencia",
        " barcelona",
        " cdmx",
        " ciudad de mexico",
        " ciudad de méxico",
        " paris",
        " jal",
        " calle ",
        " avenida ",
        " av. ",
        " street ",
        " road ",
        " rd. ",
        " plaza ",
        " paseo ",
        " carrera ",
        " camino ",
    )
    has_digit = any(char.isdigit() for char in normalized)
    return has_digit or any(hint in f" {lowered} " for hint in location_hints)


def _has_strong_geo_evidence(geo_evidence: list[dict[str, str]]) -> bool:
    for evidence in geo_evidence:
        source = evidence.get("source")
        value = str(evidence.get("value") or "")
        if source in HIGH_CONFIDENCE_GEO_SOURCES and _looks_like_specific_location(value):
            return True
    return False


def _assess_location(
    target_location: str | None,
    geo_evidence: list[dict[str, str]],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    components = _build_location_components(metadata, geo_evidence)
    parsed_location = _finalize_parsed_location(components)
    visible_location = parsed_location["formatted"] if parsed_location else None
    geo_confidence = _best_geo_confidence(geo_evidence, parsed_location)

    if not target_location:
        return {
            "location": visible_location,
            "raw_location_text": components.get("raw_location_text"),
            "parsed_location": parsed_location,
            "city": parsed_location.get("city") if parsed_location else None,
            "region": parsed_location.get("region") if parsed_location else None,
            "country": parsed_location.get("country") if parsed_location else None,
            "postal_code": parsed_location.get("postal_code") if parsed_location else None,
            "validated_location": None,
            "location_match_status": "unknown",
            "location_confidence": geo_confidence,
            "geo_evidence": geo_evidence,
        }

    normalized_target = _normalize_geo_token(target_location)
    signal_rule = _resolve_location_signal_rule(target_location)
    signal_aliases = _rule_match_aliases(signal_rule) if signal_rule else set()
    for evidence in geo_evidence:
        normalized_value = _normalize_geo_token(evidence["value"])
        matches_target = bool(normalized_target) and (
            normalized_value == normalized_target or f" {normalized_target} " in f" {normalized_value} "
        )
        if not matches_target and signal_rule:
            matches_target = any(f" {alias} " in f" {normalized_value} " for alias in signal_aliases)
        if matches_target:
            confidence = "high" if evidence["source"] in HIGH_CONFIDENCE_GEO_SOURCES else "medium"
            return {
                "location": visible_location,
                "raw_location_text": components.get("raw_location_text"),
                "parsed_location": parsed_location,
                "city": parsed_location.get("city") if parsed_location else None,
                "region": parsed_location.get("region") if parsed_location else None,
                "country": parsed_location.get("country") if parsed_location else None,
                "postal_code": parsed_location.get("postal_code") if parsed_location else None,
                "validated_location": visible_location or str(evidence["value"])[:160],
                "location_match_status": "match",
                "location_confidence": confidence,
                "geo_evidence": geo_evidence,
            }

    if _has_strong_geo_evidence(geo_evidence):
        return {
            "location": visible_location,
            "raw_location_text": components.get("raw_location_text"),
            "parsed_location": parsed_location,
            "city": parsed_location.get("city") if parsed_location else None,
            "region": parsed_location.get("region") if parsed_location else None,
            "country": parsed_location.get("country") if parsed_location else None,
            "postal_code": parsed_location.get("postal_code") if parsed_location else None,
            "validated_location": visible_location,
            "location_match_status": "mismatch",
            "location_confidence": geo_confidence,
            "geo_evidence": geo_evidence,
        }

    return {
        "location": visible_location,
        "raw_location_text": components.get("raw_location_text"),
        "parsed_location": parsed_location,
        "city": parsed_location.get("city") if parsed_location else None,
        "region": parsed_location.get("region") if parsed_location else None,
        "country": parsed_location.get("country") if parsed_location else None,
        "postal_code": parsed_location.get("postal_code") if parsed_location else None,
        "validated_location": None,
        "location_match_status": "unknown",
        "location_confidence": geo_confidence,
        "geo_evidence": geo_evidence,
    }


def _assess_language(target_language: str | None, detected_language: str | None) -> dict[str, Any]:
    normalized_target = str(target_language or "").strip().lower()
    normalized_detected = str(detected_language or "").strip().lower()

    if not normalized_target:
        return {
            "detected_language": normalized_detected or None,
            "language_match_status": "unknown",
            "language_evidence": [{"source": "content", "value": normalized_detected}] if normalized_detected else [],
        }
    if not normalized_detected:
        return {
            "detected_language": None,
            "language_match_status": "unknown",
            "language_evidence": [],
        }
    if normalized_target == normalized_detected:
        return {
            "detected_language": normalized_detected,
            "language_match_status": "match",
            "language_evidence": [{"source": "content", "value": normalized_detected}],
        }
    return {
        "detected_language": normalized_detected,
        "language_match_status": "mismatch",
        "language_evidence": [{"source": "content", "value": normalized_detected}],
    }


def _normalize_host_root(hostname: str | None) -> str:
    parts = [part for part in str(hostname or "").lower().split(".") if part]
    if len(parts) <= 2:
        return ".".join(parts)
    if parts[-2] in COMMON_SECOND_LEVEL_TLDS and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _email_domain(email: str | None) -> str:
    _, _, domain = str(email or "").strip().lower().partition("@")
    return domain


def _same_business_domain(email_domain: str, site_root: str) -> bool:
    return bool(email_domain and site_root) and (
        email_domain == site_root or email_domain.endswith(f".{site_root}")
    )


def _score_channel_confidence(source: str | None, *, boost: bool = False, penalize: bool = False) -> str:
    confidence = CONTACT_SOURCE_CONFIDENCE.get(str(source or "").strip().lower(), "medium")
    if penalize:
        return "low"
    if boost and confidence == "medium":
        return "high"
    return confidence


def _build_contact_quality(metadata: dict[str, Any]) -> dict[str, Any]:
    channels = [dict(channel) for channel in metadata.get("contact_channels", []) if isinstance(channel, dict)]
    seen_pairs = {
        (str(channel.get("type") or "").strip().lower(), str(channel.get("value") or "").strip())
        for channel in channels
    }
    for email in metadata.get("emails", []):
        pair = ("email", str(email).strip())
        if pair not in seen_pairs and pair[1]:
            channels.append({"type": "email", "value": pair[1], "source": "metadata_list"})
            seen_pairs.add(pair)
    for phone in metadata.get("phones", []):
        pair = ("phone", str(phone).strip())
        if pair not in seen_pairs and pair[1]:
            channels.append({"type": "phone", "value": pair[1], "source": "metadata_list"})
            seen_pairs.add(pair)
    site_host = urlparse(str(metadata.get("website_url") or "")).netloc.lower().removeprefix("www.")
    site_root = _normalize_host_root(site_host)

    enriched_channels: list[dict[str, Any]] = []
    primary_email: str | None = None
    primary_phone: str | None = None
    primary_email_confidence = "low"
    primary_phone_confidence = "low"
    contact_consistency_status = "unknown"
    primary_contact_source: str | None = None
    score = 0.0

    best_email_rank = -1
    for channel in channels:
        channel_type = str(channel.get("type") or "").strip().lower()
        channel_value = str(channel.get("value") or "").strip()
        channel_source = str(channel.get("source") or "unknown").strip().lower()
        if not channel_type or not channel_value:
            continue

        enriched_channel = {
            "type": channel_type,
            "value": channel_value,
            "source": channel_source,
            "confidence": "low",
            "is_primary": False,
        }

        if channel_type == "email":
            email_domain = _email_domain(channel_value)
            same_domain = _same_business_domain(email_domain, site_root)
            is_generic_domain = email_domain in GENERIC_EMAIL_DOMAINS
            if not site_root:
                confidence = _score_channel_confidence(channel_source)
                rank = 2
                relation = "unknown_site_domain"
            elif same_domain:
                confidence = _score_channel_confidence(channel_source, boost=True)
                rank = 3
                relation = "same_business_domain"
            elif is_generic_domain:
                confidence = _score_channel_confidence(channel_source)
                rank = 2
                relation = "generic_domain"
            else:
                confidence = _score_channel_confidence(channel_source, penalize=True)
                rank = 1
                relation = "external_domain"
            enriched_channel["confidence"] = confidence
            enriched_channel["domain_relation"] = relation
            if rank > best_email_rank:
                best_email_rank = rank
                primary_email = channel_value if relation != "external_domain" else None
                primary_email_confidence = confidence
                if same_domain:
                    contact_consistency_status = "consistent"
                elif relation == "external_domain":
                    contact_consistency_status = "inconsistent"
                elif contact_consistency_status != "consistent":
                    contact_consistency_status = "unknown"
                if primary_email:
                    primary_contact_source = f"email:{channel_source}"
            enriched_channels.append(enriched_channel)
            continue

        if channel_type == "phone":
            confidence = _score_channel_confidence(channel_source)
            if channel_value.startswith("+"):
                confidence = "high" if confidence == "medium" else confidence
            enriched_channel["confidence"] = confidence
            if CONTACT_CONFIDENCE_TO_SCORE[confidence] > CONTACT_CONFIDENCE_TO_SCORE[primary_phone_confidence]:
                primary_phone = channel_value
                primary_phone_confidence = confidence
                if not primary_contact_source:
                    primary_contact_source = f"phone:{channel_source}"
            enriched_channels.append(enriched_channel)
            continue

        if channel_type == "contact_form":
            enriched_channel["confidence"] = "medium"
            if not primary_contact_source:
                primary_contact_source = f"form:{channel_source}"
        elif channel_type in {"whatsapp", "booking"}:
            enriched_channel["confidence"] = "medium"
            if not primary_contact_source:
                primary_contact_source = f"{channel_type}:{channel_source}"
        else:
            enriched_channel["confidence"] = "low"
        enriched_channels.append(enriched_channel)

    for channel in enriched_channels:
        if channel["type"] == "email" and primary_email and channel["value"] == primary_email:
            channel["is_primary"] = True
        if channel["type"] == "phone" and primary_phone and channel["value"] == primary_phone:
            channel["is_primary"] = True

    if primary_email:
        score += 0.35 * CONTACT_CONFIDENCE_TO_SCORE.get(primary_email_confidence, 0.35)
    if primary_phone:
        score += 0.25 * CONTACT_CONFIDENCE_TO_SCORE.get(primary_phone_confidence, 0.35)
    if metadata.get("form_detected"):
        score += 0.15
    if metadata.get("whatsapp_url"):
        score += 0.10
    if metadata.get("booking_url"):
        score += 0.10

    return {
        "contact_quality_score": round(min(score, 1.0), 4),
        "contact_channels": enriched_channels,
        "primary_email": primary_email,
        "primary_phone": primary_phone,
        "contact_consistency_status": contact_consistency_status,
        "primary_email_confidence": primary_email_confidence if primary_email else "low",
        "primary_phone_confidence": primary_phone_confidence if primary_phone else "low",
        "primary_contact_source": primary_contact_source,
    }


def _infer_company_size_signal(metadata: dict[str, Any], heuristic_data: dict[str, Any]) -> str:
    locations = len(metadata.get("addresses", []))
    social_count = len(metadata.get("social_links", []))
    hiring_signals = bool(heuristic_data.get("hiring_signals"))
    internal_links = metadata.get("internal_links", [])

    if hiring_signals or locations >= 2:
        return "medium"
    if any("equipo" in link.lower() or "team" in link.lower() for link in internal_links) or social_count >= 2:
        return "small"
    if heuristic_data.get("score", 0.0) <= 0.25 and not metadata.get("form_detected") and social_count <= 1:
        return "solo"
    return "unknown"


def _extract_service_keywords(clean_text: str, *, limit: int = 5) -> list[str]:
    frequencies: dict[str, int] = {}
    for token in re.findall(r"[a-zA-ZáéíóúñÁÉÍÓÚÑ]{4,}", clean_text.lower()):
        if token in STOPWORDS:
            continue
        frequencies[token] = frequencies.get(token, 0) + 1
    ordered = sorted(frequencies.items(), key=lambda item: (-item[1], item[0]))
    return [token for token, _ in ordered[:limit]]


def _classify_quality_status(
    *,
    has_target_location: bool,
    heuristic_score: float,
    heuristic_confidence: str,
    location_match_status: str,
    language_match_status: str,
    contact_quality_score: float,
    contact_consistency_status: str,
    primary_email_confidence: str,
    primary_phone_confidence: str,
) -> tuple[str, str | None, list[str], float]:
    flags: list[str] = []
    score_multiplier = 1.0

    if has_target_location and location_match_status == "mismatch":
        flags.append("geo_mismatch")
        return "rejected", "geo_mismatch", flags, 0.35
    if has_target_location and location_match_status == "unknown":
        flags.append("geo_unknown")
        if heuristic_score < 0.45:
            return "rejected", "geo_unknown_low_score", flags, 0.8
        return "needs_review", "geo_unknown", flags, 0.9

    if language_match_status == "mismatch":
        flags.append("language_mismatch")
        score_multiplier = 0.75
        if heuristic_score < 0.6:
            return "rejected", "language_mismatch", flags, score_multiplier
        return "needs_review", "language_mismatch", flags, score_multiplier

    if contact_consistency_status == "inconsistent":
        flags.append("contact_inconsistent")
        if primary_phone_confidence == "low" and contact_quality_score < 0.15:
            return "rejected", "contact_inconsistent", flags, 0.55
        return "needs_review", "contact_inconsistent", flags, 0.75

    if primary_email_confidence == "low" and primary_phone_confidence == "low" and contact_quality_score < 0.3:
        flags.append("weak_primary_contact")
        return "rejected", "low_contact_quality", flags, 0.7

    if contact_quality_score < 0.25 and heuristic_confidence == "low":
        flags.append("weak_contactability")
        return "rejected", "low_contact_quality", flags, 0.75

    return "accepted", None, flags, score_multiplier


def _derive_acceptance_decision(
    *,
    quality_status: str,
    rejection_reason: str | None,
    entity_type_detected: str | None,
    entity_type_confidence: str | None,
    is_target_entity: bool | None,
    heuristic_score: float,
    target_niche: str | None,
    context_fit_score: float | None,
    business_model_fit_status: str | None,
) -> tuple[str, float, float | None]:
    normalized_entity_type = str(entity_type_detected or "unknown").strip().lower()
    normalized_confidence = str(entity_type_confidence or "low").strip().lower()
    has_target_niche = bool(str(target_niche or "").strip())
    normalized_context_fit = max(0.0, min(float(context_fit_score or 0.0), 1.0))
    normalized_business_model_fit = str(business_model_fit_status or "unknown").strip().lower()

    if normalized_entity_type in DIRECTORY_ENTITY_TYPES:
        return "rejected_directory", 0.2, 0.25
    if normalized_entity_type in MEDIA_ENTITY_TYPES:
        return "rejected_media", 0.25, 0.3
    if normalized_entity_type in ARTICLE_ENTITY_TYPES:
        return "rejected_article", 0.15, 0.2

    if quality_status == "accepted" and is_target_entity:
        if has_target_niche and normalized_business_model_fit == "mismatch":
            return "accepted_related", 0.5, 0.55
        if has_target_niche and normalized_context_fit < 0.3:
            return "accepted_related", 0.65, 0.65
        return "accepted_target", 1.0, None

    if quality_status == "accepted" and normalized_entity_type == "unknown":
        if heuristic_score >= 0.55 and normalized_confidence in {"medium", "high"}:
            return "accepted_related", 0.75, 0.7
        return "rejected_low_confidence", 0.45, 0.45

    if quality_status == "accepted":
        return "accepted_related", 0.7, 0.65

    if rejection_reason == "low_contact_quality":
        return "rejected_low_confidence", 0.5, 0.45

    return "rejected_low_confidence", 0.55 if quality_status == "needs_review" else 0.45, 0.5 if quality_status == "needs_review" else 0.4


def build_ai_cache_signature(domain: str, clean_text: str, prompt_version: str) -> str:
    signature = hashlib.sha256(f"{domain}|{prompt_version}|{clean_text}".encode("utf-8")).hexdigest()
    return signature


def build_ai_evidence_pack(
    *,
    domain: str,
    clean_text: str,
    metadata: dict[str, Any],
    heuristic_data: dict[str, Any],
    quality_data: dict[str, Any],
    discovery_metadata: dict[str, Any],
) -> dict[str, Any]:
    compact_text = " ".join(clean_text.split())[:1800]
    return {
        "domain": domain,
        "summary_text": compact_text,
        "title": metadata.get("title"),
        "description": metadata.get("description"),
        "location": quality_data.get("location"),
        "raw_location_text": quality_data.get("raw_location_text"),
        "parsed_location": quality_data.get("parsed_location"),
        "city": quality_data.get("city"),
        "region": quality_data.get("region"),
        "country": quality_data.get("country"),
        "postal_code": quality_data.get("postal_code"),
        "validated_location": quality_data.get("validated_location"),
        "location_match_status": quality_data.get("location_match_status"),
        "detected_language": quality_data.get("detected_language"),
        "language_match_status": quality_data.get("language_match_status"),
        "primary_cta": quality_data.get("primary_cta"),
        "booking_url": quality_data.get("booking_url"),
        "pricing_page_url": quality_data.get("pricing_page_url"),
        "contact_channels": quality_data.get("contact_channels_json"),
        "contact_consistency_status": quality_data.get("contact_consistency_status"),
        "primary_email_confidence": quality_data.get("primary_email_confidence"),
        "primary_phone_confidence": quality_data.get("primary_phone_confidence"),
        "primary_contact_source": quality_data.get("primary_contact_source"),
        "heuristic_score": heuristic_data.get("score"),
        "heuristic_confidence": heuristic_data.get("confidence_level"),
        "observed_signals": heuristic_data.get("observed_signals")
        or heuristic_data.get("generic_attributes", {}).get("observed_signals", []),
        "inferred_opportunities": heuristic_data.get("inferred_opportunities")
        or heuristic_data.get("generic_attributes", {}).get("inferred_opportunities", []),
        "heuristic_pain_points": heuristic_data.get("generic_attributes", {}).get("pain_points_detected", []),
        "inferred_tech_stack": heuristic_data.get("inferred_tech_stack", []),
        "inferred_niche": heuristic_data.get("inferred_niche"),
        "taxonomy_top_level": heuristic_data.get("taxonomy_top_level")
        or heuristic_data.get("generic_attributes", {}).get("taxonomy_top_level"),
        "taxonomy_business_type": heuristic_data.get("taxonomy_business_type")
        or heuristic_data.get("generic_attributes", {}).get("taxonomy_business_type"),
        "entity_type_detected": quality_data.get("entity_type_detected"),
        "entity_type_confidence": quality_data.get("entity_type_confidence"),
        "is_target_entity": quality_data.get("is_target_entity"),
        "acceptance_decision": quality_data.get("acceptance_decision"),
        "observed_business_model": quality_data.get("observed_business_model"),
        "business_model_fit_status": quality_data.get("business_model_fit_status"),
        "discovery": discovery_metadata,
        "service_keywords": quality_data.get("service_keywords"),
    }


def should_call_ai(heuristic_data: dict[str, Any], quality_data: dict[str, Any]) -> tuple[bool, str]:
    quality_status = quality_data.get("quality_status")
    acceptance_decision = str(quality_data.get("acceptance_decision") or "").strip().lower()
    heuristic_score = float(heuristic_data.get("score") or 0.0)
    heuristic_confidence = str(heuristic_data.get("confidence_level") or "low")

    if quality_status == "rejected":
        return False, "quality_rejected"
    if acceptance_decision.startswith("rejected_"):
        return False, "commercial_rejected"
    if acceptance_decision == "accepted_related":
        return False, "commercial_related_only"
    if heuristic_confidence == "high" and quality_status == "accepted" and heuristic_score >= 0.7:
        return False, "heuristic_high_confidence"
    if heuristic_confidence == "high" and heuristic_score <= 0.2:
        return False, "low_value_heuristic"
    return True, "ai_required"


def evaluate_prospect_quality(
    *,
    clean_text: str,
    metadata: dict[str, Any],
    context: dict[str, Any],
    heuristic_data: dict[str, Any],
    discovery_metadata: dict[str, Any],
    entity_data: dict[str, Any],
) -> dict[str, Any]:
    detected_language = _detect_language(clean_text, metadata)
    language_data = _assess_language(context.get("target_language"), detected_language)
    geo_evidence = _extract_geo_evidence(metadata, discovery_metadata, context.get("target_location"))
    location_data = _assess_location(context.get("target_location"), geo_evidence, metadata)
    contact_data = _build_contact_quality(metadata)
    contact_quality_score = float(contact_data["contact_quality_score"])
    company_size_signal = _infer_company_size_signal(metadata, heuristic_data)
    service_keywords = _extract_service_keywords(clean_text)
    business_model_data = _assess_business_model_fit(
        clean_text=clean_text,
        metadata=metadata,
        context=context,
        entity_type_detected=entity_data.get("entity_type_detected"),
    )
    context_fit_score = None
    heuristic_trace = heuristic_data.get("heuristic_trace")
    if isinstance(heuristic_trace, dict):
        component_scores = heuristic_trace.get("component_scores")
        if isinstance(component_scores, dict) and component_scores.get("context_fit") is not None:
            context_fit_score = float(component_scores.get("context_fit") or 0.0)
    if context_fit_score is None:
        generic_attributes = heuristic_data.get("generic_attributes")
        if isinstance(generic_attributes, dict):
            score_breakdown = generic_attributes.get("heuristic_score_breakdown")
            if isinstance(score_breakdown, dict) and score_breakdown.get("context_fit") is not None:
                context_fit_score = float(score_breakdown.get("context_fit") or 0.0)
    quality_status, rejection_reason, quality_flags, technical_score_multiplier = _classify_quality_status(
        has_target_location=bool(str(context.get("target_location") or "").strip()),
        heuristic_score=float(heuristic_data.get("score") or 0.0),
        heuristic_confidence=str(heuristic_data.get("confidence_level") or "low"),
        location_match_status=location_data["location_match_status"],
        language_match_status=language_data["language_match_status"],
        contact_quality_score=contact_quality_score,
        contact_consistency_status=str(contact_data["contact_consistency_status"]),
        primary_email_confidence=str(contact_data["primary_email_confidence"]),
        primary_phone_confidence=str(contact_data["primary_phone_confidence"]),
    )
    is_target_entity = entity_data.get("is_target_entity")
    if is_target_entity is False:
        quality_flags.append("non_target_entity")
    acceptance_decision, commercial_score_multiplier, score_cap = _derive_acceptance_decision(
        quality_status=quality_status,
        rejection_reason=rejection_reason,
        entity_type_detected=entity_data.get("entity_type_detected"),
        entity_type_confidence=entity_data.get("entity_type_confidence"),
        is_target_entity=is_target_entity,
        heuristic_score=float(heuristic_data.get("score") or 0.0),
        target_niche=context.get("target_niche"),
        context_fit_score=context_fit_score,
        business_model_fit_status=business_model_data.get("business_model_fit_status"),
    )
    score_multiplier = round(technical_score_multiplier * commercial_score_multiplier, 4)

    content_coverage = {
        "page_types_detected": sorted(
            {
                page_type
                for page_type, url in [
                    ("contact", metadata.get("booking_url")),
                    ("pricing", metadata.get("pricing_page_url")),
                    ("services", metadata.get("service_page_url")),
                ]
                if url
            }
        ),
        "has_contact": contact_quality_score > 0,
        "has_location": bool(location_data.get("location") or location_data["geo_evidence"]),
        "has_cta": bool(metadata.get("primary_cta")),
        "has_structured_data": bool(metadata.get("structured_data")),
    }

    return {
        **location_data,
        **language_data,
        "primary_cta": metadata.get("primary_cta") or ("contact_form" if metadata.get("form_detected") else "none"),
        "booking_url": metadata.get("booking_url"),
        "pricing_page_url": metadata.get("pricing_page_url"),
        "whatsapp_url": metadata.get("whatsapp_url"),
        "contact_channels_json": contact_data["contact_channels"],
        "contact_quality_score": contact_quality_score,
        "email": contact_data["primary_email"],
        "phone": contact_data["primary_phone"],
        "contact_consistency_status": contact_data["contact_consistency_status"],
        "primary_email_confidence": contact_data["primary_email_confidence"],
        "primary_phone_confidence": contact_data["primary_phone_confidence"],
        "primary_contact_source": contact_data["primary_contact_source"],
        "company_size_signal": company_size_signal,
        "context_fit_score": context_fit_score,
        "target_business_models": business_model_data.get("target_business_models"),
        "observed_business_model": business_model_data.get("observed_business_model"),
        "business_model_fit_status": business_model_data.get("business_model_fit_status"),
        "service_keywords": service_keywords,
        "entity_type_detected": entity_data.get("entity_type_detected"),
        "entity_type_confidence": entity_data.get("entity_type_confidence"),
        "entity_type_evidence": entity_data.get("entity_type_evidence"),
        "is_target_entity": is_target_entity,
        "acceptance_decision": acceptance_decision,
        "quality_status": quality_status,
        "quality_flags": quality_flags,
        "rejection_reason": rejection_reason,
        "discovery_confidence": discovery_metadata.get("discovery_confidence"),
        "discovery_evidence": discovery_metadata,
        "cta_evidence": metadata.get("cta_candidates", []),
        "structured_data_evidence": metadata.get("structured_data_evidence", []),
        "content_coverage": content_coverage,
        "score_multiplier": score_multiplier,
        "technical_score_multiplier": technical_score_multiplier,
        "commercial_score_multiplier": commercial_score_multiplier,
        "score_cap": score_cap,
    }
