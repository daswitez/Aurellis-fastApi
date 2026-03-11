from typing import Any, Dict

SCORE_STRATEGY_VERSION = "hybrid_v1"


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def _confidence_to_numeric(level: str | None) -> float:
    mapping = {
        "low": 0.35,
        "medium": 0.6,
        "high": 0.85,
    }
    return mapping.get((level or "").strip().lower(), 0.35)


def _numeric_to_confidence(value: float) -> str:
    if value >= 0.78:
        return "high"
    if value >= 0.5:
        return "medium"
    return "low"


def _base_ai_weight(ai_confidence_level: str | None) -> float:
    mapping = {
        "low": 0.45,
        "medium": 0.6,
        "high": 0.75,
    }
    return mapping.get((ai_confidence_level or "").strip().lower(), 0.45)


def _agreement_band(delta: float) -> str:
    if delta <= 0.15:
        return "high"
    if delta <= 0.3:
        return "medium"
    return "low"


def _build_fit_summary(
    *,
    strategy: str,
    final_score: float,
    ai_score: float | None,
    heuristic_score: float,
    agreement_band: str,
    heuristic_summary: str | None,
) -> str:
    if strategy == "heuristic_only":
        return heuristic_summary or "Score heuristico aplicado por falta de score IA utilizable."

    if final_score >= 0.7:
        prefix = "Score hibrido fuerte"
    elif final_score >= 0.45:
        prefix = "Score hibrido moderado"
    else:
        prefix = "Score hibrido conservador"

    if agreement_band == "high":
        return f"{prefix}; IA y heuristica son consistentes."
    if ai_score is not None and ai_score > heuristic_score:
        return f"{prefix}; la IA empuja el score por encima del baseline heuristico."
    return f"{prefix}; la heuristica modera una evaluacion IA mas optimista."


def build_final_score(
    *,
    ai_data: Dict[str, Any],
    ai_trace: Dict[str, Any],
    heuristic_data: Dict[str, Any],
) -> Dict[str, Any]:
    heuristic_score = float(heuristic_data.get("score") or 0.0)
    heuristic_confidence = str(heuristic_data.get("confidence_level") or "low")
    heuristic_summary = heuristic_data.get("fit_summary")

    if ai_trace.get("selected_method") != "ai":
        return {
            "score": round(heuristic_score, 4),
            "confidence_level": heuristic_confidence,
            "fit_summary": _build_fit_summary(
                strategy="heuristic_only",
                final_score=heuristic_score,
                ai_score=None,
                heuristic_score=heuristic_score,
                agreement_band="n/a",
                heuristic_summary=heuristic_summary,
            ),
            "scoring_trace": {
                "strategy": "heuristic_only",
                "strategy_version": SCORE_STRATEGY_VERSION,
                "ai_score": None,
                "ai_confidence_level": None,
                "ai_weight": 0.0,
                "heuristic_score": round(heuristic_score, 4),
                "heuristic_confidence_level": heuristic_confidence,
                "heuristic_weight": 1.0,
                "agreement_delta": None,
                "agreement_band": None,
                "final_score": round(heuristic_score, 4),
                "final_confidence_level": heuristic_confidence,
            },
        }

    ai_score = float(ai_data.get("score") or 0.0)
    ai_confidence_level = str(ai_data.get("confidence_level") or "low")
    delta = abs(ai_score - heuristic_score)
    ai_weight = _base_ai_weight(ai_confidence_level)

    if delta <= 0.15:
        ai_weight += 0.1
    elif delta >= 0.4:
        ai_weight -= 0.15

    ai_weight = _clamp(ai_weight, 0.35, 0.85)
    heuristic_weight = round(1.0 - ai_weight, 4)
    final_score = round((ai_score * ai_weight) + (heuristic_score * heuristic_weight), 4)

    agreement_band = _agreement_band(delta)
    blended_confidence_numeric = (
        _confidence_to_numeric(ai_confidence_level) * ai_weight
        + _confidence_to_numeric(heuristic_confidence) * heuristic_weight
    )
    if agreement_band == "low":
        blended_confidence_numeric = min(blended_confidence_numeric, 0.68)

    final_confidence_level = _numeric_to_confidence(blended_confidence_numeric)

    return {
        "score": final_score,
        "confidence_level": final_confidence_level,
        "fit_summary": _build_fit_summary(
            strategy="hybrid",
            final_score=final_score,
            ai_score=ai_score,
            heuristic_score=heuristic_score,
            agreement_band=agreement_band,
            heuristic_summary=heuristic_summary,
        ),
        "scoring_trace": {
            "strategy": "hybrid",
            "strategy_version": SCORE_STRATEGY_VERSION,
            "ai_score": round(ai_score, 4),
            "ai_confidence_level": ai_confidence_level,
            "ai_weight": round(ai_weight, 4),
            "heuristic_score": round(heuristic_score, 4),
            "heuristic_confidence_level": heuristic_confidence,
            "heuristic_weight": heuristic_weight,
            "agreement_delta": round(delta, 4),
            "agreement_band": agreement_band,
            "final_score": final_score,
            "final_confidence_level": final_confidence_level,
        },
    }
