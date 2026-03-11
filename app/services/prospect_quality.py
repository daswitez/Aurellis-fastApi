from __future__ import annotations

import hashlib
import re
from typing import Any


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


def _normalize_text(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    return f" {normalized} " if normalized else " "


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


def _extract_geo_evidence(metadata: dict[str, Any], discovery_metadata: dict[str, Any]) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    for address in metadata.get("addresses", []):
        evidence.append({"source": "address", "value": address})
    for map_link in metadata.get("map_links", []):
        evidence.append({"source": "map", "value": map_link})
    for field_name in ["title", "description"]:
        field_value = metadata.get(field_name)
        if field_value:
            evidence.append({"source": field_name, "value": str(field_value)})
    if discovery_metadata.get("title"):
        evidence.append({"source": "discovery_title", "value": str(discovery_metadata["title"])})
    if discovery_metadata.get("snippet"):
        evidence.append({"source": "discovery_snippet", "value": str(discovery_metadata["snippet"])})
    return evidence


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
        if source in {"address", "map"} and _looks_like_specific_location(value):
            return True
    return False


def _assess_location(target_location: str | None, geo_evidence: list[dict[str, str]]) -> dict[str, Any]:
    if not target_location:
        return {
            "validated_location": None,
            "location_match_status": "unknown",
            "location_confidence": "low",
            "geo_evidence": geo_evidence,
        }

    normalized_target = _normalize_text(target_location)
    for evidence in geo_evidence:
        if normalized_target.strip() and normalized_target in _normalize_text(evidence["value"]):
            confidence = "high" if evidence["source"] in {"address", "map"} else "medium"
            return {
                "validated_location": evidence["value"][:160],
                "location_match_status": "match",
                "location_confidence": confidence,
                "geo_evidence": geo_evidence,
            }

    if _has_strong_geo_evidence(geo_evidence):
        for evidence in geo_evidence:
            if evidence.get("source") in {"address", "map"} and _looks_like_specific_location(str(evidence.get("value") or "")):
                candidate = str(evidence["value"])[:160]
                break
        else:
            candidate = str(geo_evidence[0]["value"])[:160]
        return {
            "validated_location": candidate,
            "location_match_status": "mismatch",
            "location_confidence": "medium",
            "geo_evidence": geo_evidence,
        }

    return {
        "validated_location": None,
        "location_match_status": "unknown",
        "location_confidence": "low",
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


def _build_contact_quality(metadata: dict[str, Any]) -> tuple[float, list[dict[str, str]]]:
    score = 0.0
    channels = metadata.get("contact_channels", [])
    if any(channel.get("type") == "email" for channel in channels):
        score += 0.35
    if any(channel.get("type") == "phone" for channel in channels):
        score += 0.25
    if metadata.get("form_detected"):
        score += 0.15
    if metadata.get("whatsapp_url"):
        score += 0.15
    if metadata.get("booking_url"):
        score += 0.10
    return round(min(score, 1.0), 4), channels


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

    if contact_quality_score < 0.25 and heuristic_confidence == "low":
        flags.append("weak_contactability")
        return "rejected", "low_contact_quality", flags, 0.75

    return "accepted", None, flags, score_multiplier


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
        "validated_location": quality_data.get("validated_location"),
        "location_match_status": quality_data.get("location_match_status"),
        "detected_language": quality_data.get("detected_language"),
        "language_match_status": quality_data.get("language_match_status"),
        "primary_cta": quality_data.get("primary_cta"),
        "booking_url": quality_data.get("booking_url"),
        "pricing_page_url": quality_data.get("pricing_page_url"),
        "contact_channels": quality_data.get("contact_channels_json"),
        "heuristic_score": heuristic_data.get("score"),
        "heuristic_confidence": heuristic_data.get("confidence_level"),
        "heuristic_pain_points": heuristic_data.get("generic_attributes", {}).get("pain_points_detected", []),
        "inferred_tech_stack": heuristic_data.get("inferred_tech_stack", []),
        "inferred_niche": heuristic_data.get("inferred_niche"),
        "discovery": discovery_metadata,
        "service_keywords": quality_data.get("service_keywords"),
    }


def should_call_ai(heuristic_data: dict[str, Any], quality_data: dict[str, Any]) -> tuple[bool, str]:
    quality_status = quality_data.get("quality_status")
    heuristic_score = float(heuristic_data.get("score") or 0.0)
    heuristic_confidence = str(heuristic_data.get("confidence_level") or "low")

    if quality_status == "rejected":
        return False, "quality_rejected"
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
) -> dict[str, Any]:
    detected_language = _detect_language(clean_text, metadata)
    language_data = _assess_language(context.get("target_language"), detected_language)
    geo_evidence = _extract_geo_evidence(metadata, discovery_metadata)
    location_data = _assess_location(context.get("target_location"), geo_evidence)
    contact_quality_score, contact_channels = _build_contact_quality(metadata)
    company_size_signal = _infer_company_size_signal(metadata, heuristic_data)
    service_keywords = _extract_service_keywords(clean_text)
    quality_status, rejection_reason, quality_flags, score_multiplier = _classify_quality_status(
        has_target_location=bool(str(context.get("target_location") or "").strip()),
        heuristic_score=float(heuristic_data.get("score") or 0.0),
        heuristic_confidence=str(heuristic_data.get("confidence_level") or "low"),
        location_match_status=location_data["location_match_status"],
        language_match_status=language_data["language_match_status"],
        contact_quality_score=contact_quality_score,
    )

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
        "has_location": bool(location_data["geo_evidence"]),
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
        "contact_channels_json": contact_channels,
        "contact_quality_score": contact_quality_score,
        "company_size_signal": company_size_signal,
        "service_keywords": service_keywords,
        "quality_status": quality_status,
        "quality_flags": quality_flags,
        "rejection_reason": rejection_reason,
        "discovery_confidence": discovery_metadata.get("discovery_confidence"),
        "discovery_evidence": discovery_metadata,
        "cta_evidence": metadata.get("cta_candidates", []),
        "structured_data_evidence": metadata.get("structured_data_evidence", []),
        "content_coverage": content_coverage,
        "score_multiplier": score_multiplier,
    }
