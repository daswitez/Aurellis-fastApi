import asyncio
import logging
import math
from datetime import datetime
from typing import Any, List
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import JobDiscoveryIteration, JobProspect, Prospect, ScrapingJob, ScrapingLog
from app.api.schemas import (
    JobAdaptiveSummary,
    JobAISummary,
    JobCaptureSummary,
    JobCommercialSummary,
    JobCreateRequest,
    JobDiscoveryIterationOut,
    JobDiscoveryIterationsResponse,
    JobLogOut,
    JobLogsResponse,
    JobOperationalSummary,
    JobQualitySummary,
    JobResponse,
    JobsCommercialMetricsResponse,
    JobsOperationalMetricsResponse,
    ProspectOut,
    ScrapingLogLevel,
)
from app.scraper.engine import scrape_single_prospect
from app.scraper.http_client import FetchHtmlError
from app.services.discovery import (
    build_discovery_query_plan,
    determine_capture_stop_reason,
    resolve_discovery_target_location,
    resolve_candidate_batch_size,
    resolve_capture_targets,
    resolve_discovery_batch_budget,
)
from app.services.discovery_orchestrator import discover_prospect_urls_by_queries
from app.services.discovery_types import SearchDiscoveryEntry, SearchDiscoveryResult
from app.services.db_upsert import save_scraped_prospect
from app.services.source_metadata import normalize_discovery_method, normalize_source_type
from app.services.ai_search_planner import initial_search_plan, refine_search_plan

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["Jobs"])

COMMERCIAL_REJECTION_DECISIONS = frozenset({"rejected_directory", "rejected_media", "rejected_article"})
COMMERCIAL_ROLLOUT_LAYERS = [
    "stage_1_classify_observe",
    "stage_2_score_penalty",
    "stage_3_hard_rejection",
    "stage_4_public_api",
]
COMMERCIAL_ROLLOUT_STAGE = COMMERCIAL_ROLLOUT_LAYERS[-1]
DEFAULT_ADAPTIVE_REFINEMENT_WINDOW = 10
MAX_REFINEMENT_DISCOVERY_BUDGET = 20
INITIAL_DISCOVERY_SEED_MULTIPLIER = 3
COACH_DIRECTORY_HINTS = (
    "directorio",
    "directory",
    "listado de coaches",
    "escuela de coaching",
    "escuela",
    "instituto",
    "academy",
)
ADAPTIVE_NOISE_DECISIONS = frozenset({"rejected_low_confidence", "rejected_media", "rejected_directory", "rejected_article"})


def _utcnow() -> datetime:
    return datetime.utcnow()


async def _append_job_log(
    db: AsyncSession,
    job_id: int,
    level: str,
    message: str,
    *,
    source_name: str | None = None,
    context_json: dict | None = None,
) -> None:
    db.add(
        ScrapingLog(
            job_id=job_id,
            level=level,
            message=message,
            source_name=source_name,
            context_json=context_json,
        )
    )


def _job_summary_message(job: ScrapingJob) -> str:
    if job.status == "completed":
        return (
            f"Completado en {job.finished_at} | "
            f"Procesadas: {job.total_processed}, guardadas: {job.total_saved}, "
            f"omitidas: {job.total_skipped}, fallidas: {job.total_failed}"
        )
    if job.status == "failed":
        return f"Falló en {job.finished_at} | {job.error_message or 'Error no especificado'}"
    if job.status == "running":
        return (
            f"En ejecución desde {job.started_at} | "
            f"Procesadas: {job.total_processed}, guardadas: {job.total_saved}, "
            f"omitidas: {job.total_skipped}, fallidas: {job.total_failed}"
        )
    return "Pendiente"


def _extract_surface_resolution(generic_attributes: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(generic_attributes, dict):
        return {}
    surface_resolution = generic_attributes.get("surface_resolution")
    return surface_resolution if isinstance(surface_resolution, dict) else {}


def _build_job_context(
    job: ScrapingJob,
    *,
    search_query: str | None,
    discovery_method: str | None,
    source_type: str | None,
    provider_name: str | None = None,
    search_warning: str | None,
) -> dict:
    filters_json = job.filters_json or {}
    discovery_profile = filters_json.get("discovery_profile") if isinstance(filters_json, dict) else {}
    if not isinstance(discovery_profile, dict):
        discovery_profile = {}

    return {
        "job_id": job.id,
        "workspace_id": job.workspace_id,
        "user_profession": job.user_profession,
        "user_technologies": job.user_technologies,
        "user_value_proposition": job.user_value_proposition,
        "user_past_successes": job.user_past_successes,
        "user_roi_metrics": job.user_roi_metrics,
        "user_service_offers": discovery_profile.get("user_service_offers"),
        "user_service_constraints": discovery_profile.get("user_service_constraints"),
        "user_target_offer_focus": discovery_profile.get("user_target_offer_focus"),
        "user_ticket_size": discovery_profile.get("user_ticket_size"),
        "target_niche": job.target_niche,
        "target_location": job.target_location,
        "target_language": job.target_language,
        "target_company_size": job.target_company_size,
        "target_pain_points": job.target_pain_points,
        "target_budget_signals": job.target_budget_signals,
        "search_query": search_query,
        "discovery_queries": [],
        "discovery_method": normalize_discovery_method(discovery_method),
        "source_type": normalize_source_type(source_type),
        "provider_name": provider_name,
        "search_warning": search_warning,
        "target_accepted_results": filters_json.get("target_accepted_results"),
        "max_candidates_to_process": filters_json.get("max_candidates_to_process"),
        "adaptive_discovery": filters_json.get("adaptive_discovery"),
        "adaptive_refinement_every_processed": filters_json.get("adaptive_refinement_every_processed"),
        "max_query_refinements": filters_json.get("max_query_refinements"),
    }


def _apply_job_runtime_totals(
    job: ScrapingJob,
    *,
    total_found: int,
    total_processed: int,
    total_saved: int,
    total_failed: int,
    total_skipped: int,
) -> None:
    job.total_found = total_found
    job.total_processed = total_processed
    job.total_saved = total_saved
    job.total_failed = total_failed
    job.total_skipped = total_skipped


def _serialize_job_log(log: ScrapingLog) -> JobLogOut:
    context = log.context_json or {}
    return JobLogOut(
        id=log.id,
        created_at=log.created_at,
        level=log.level,
        message=log.message,
        source_name=log.source_name,
        context_json=context or None,
        stage=context.get("stage"),
        error_type=context.get("error_type"),
        status_code=context.get("status_code"),
        retryable=context.get("retryable"),
        attempts_made=context.get("attempts_made"),
        url=context.get("url"),
        rank_position=context.get("rank_position"),
        error=context.get("error"),
    )


def _extract_domain_from_url(url: str | None) -> str | None:
    parsed = urlparse(str(url or "").strip())
    hostname = (parsed.hostname or "").strip().lower()
    return hostname or None


def _compute_default_max_query_refinements(max_candidates_to_process: int) -> int:
    candidate_target = max(int(max_candidates_to_process or 0), 1)
    return max(3, min(10, math.ceil(candidate_target / 5)))


def _resolve_adaptive_refinement_window(max_candidates_to_process: int) -> int:
    candidate_target = max(int(max_candidates_to_process or 0), 1)
    return 5 if candidate_target <= 25 else 10


def _resolve_query_plan_limit(*, max_candidates_to_process: int, target_accepted_results: int) -> int:
    return max(
        MAX_REFINEMENT_DISCOVERY_BUDGET + 4,
        min(72, max(int(max_candidates_to_process or 0) * 2, int(target_accepted_results or 0) * 4, 24)),
    )


def _resolve_iteration_query_limit(
    *,
    iteration_index: int,
    max_candidates_to_process: int,
    target_accepted_results: int,
) -> int:
    if int(iteration_index or 0) <= 0:
        return min(6, _resolve_query_plan_limit(
            max_candidates_to_process=max_candidates_to_process,
            target_accepted_results=target_accepted_results,
        ))
    refinement_cap = 8 if int(max_candidates_to_process or 0) <= 25 else 10
    return min(
        refinement_cap,
        _resolve_query_plan_limit(
            max_candidates_to_process=max_candidates_to_process,
            target_accepted_results=target_accepted_results,
        ),
    )


def _resolve_initial_seed_target(*, target_accepted_results: int, max_candidates_to_process: int) -> int:
    base_batch_size = resolve_candidate_batch_size(
        target_accepted_results=target_accepted_results,
        candidate_cap=max_candidates_to_process,
    )
    return min(
        max_candidates_to_process,
        max(base_batch_size * INITIAL_DISCOVERY_SEED_MULTIPLIER, target_accepted_results * 2, 8),
    )


def _serialize_discovery_entry(entry: SearchDiscoveryEntry | dict[str, Any]) -> dict[str, Any]:
    if isinstance(entry, SearchDiscoveryEntry):
        return {
            "url": entry.url,
            "query": entry.query,
            "query_context": entry.query_context,
            "title": entry.title,
            "snippet": entry.snippet,
            "position": entry.position,
            "discovery_confidence": entry.discovery_confidence,
            "business_likeness_score": entry.business_likeness_score,
            "result_kind": entry.result_kind,
            "discovery_reasons": entry.discovery_reasons,
        }
    entry_dict = dict(entry)
    return {
        "url": entry_dict.get("url"),
        "query": entry_dict.get("query"),
        "query_context": entry_dict.get("query_context"),
        "title": entry_dict.get("title"),
        "snippet": entry_dict.get("snippet"),
        "position": entry_dict.get("position"),
        "discovery_confidence": entry_dict.get("discovery_confidence"),
        "business_likeness_score": entry_dict.get("business_likeness_score"),
        "result_kind": entry_dict.get("result_kind"),
        "discovery_reasons": entry_dict.get("discovery_reasons"),
    }


def _build_false_positive_samples(processed_window: list[dict[str, Any]]) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for item in processed_window:
        normalized_decision = str(item.get("acceptance_decision") or "").strip().lower()
        if normalized_decision not in {
            "rejected_low_confidence",
            "rejected_directory",
            "rejected_media",
            "rejected_article",
        }:
            continue
        samples.append(
            {
                "url": item.get("url"),
                "domain": item.get("domain"),
                "title": item.get("title"),
                "query": item.get("query"),
                "acceptance_decision": item.get("acceptance_decision"),
                "rejection_reason": item.get("rejection_reason"),
            }
        )
        if len(samples) >= 8:
            break
    return samples


def _build_accepted_samples(processed_window: list[dict[str, Any]]) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for item in processed_window:
        if str(item.get("acceptance_decision") or "").strip().lower() != "accepted_target":
            continue
        samples.append(
            {
                "url": item.get("url"),
                "domain": item.get("domain"),
                "title": item.get("title"),
                "query": item.get("query"),
                "company_name": item.get("company_name"),
            }
        )
        if len(samples) >= 4:
            break
    return samples


def _summarize_processed_window(processed_window: list[dict[str, Any]]) -> dict[str, Any]:
    accepted_target_delta = 0
    rejected_reasons: dict[str, int] = {}
    acceptance_decisions: dict[str, int] = {}

    for item in processed_window:
        decision = str(item.get("acceptance_decision") or "").strip().lower()
        rejection_reason = str(item.get("rejection_reason") or "").strip().lower()
        if decision == "accepted_target":
            accepted_target_delta += 1
        if decision:
            acceptance_decisions[decision] = acceptance_decisions.get(decision, 0) + 1
        if rejection_reason:
            rejected_reasons[rejection_reason] = rejected_reasons.get(rejection_reason, 0) + 1

    noise_count = sum(
        acceptance_decisions.get(reason, 0)
        for reason in ("rejected_low_confidence", "rejected_media", "rejected_directory", "rejected_article")
    )
    processed_count = len(processed_window)
    return {
        "processed_count": processed_count,
        "accepted_target_delta": accepted_target_delta,
        "acceptance_decisions": acceptance_decisions,
        "rejection_reasons": rejected_reasons,
        "noise_count": noise_count,
        "noise_ratio": round((noise_count / processed_count), 4) if processed_count else 0.0,
    }


def _should_trigger_adaptive_refinement(
    *,
    window_stats: dict[str, Any],
    candidate_queue_empty: bool,
    refinement_window: int,
    search_evidence: dict[str, Any] | None = None,
) -> tuple[bool, str | None]:
    processed_count = int(window_stats.get("processed_count") or 0)
    accepted_target_delta = int(window_stats.get("accepted_target_delta") or 0)
    noise_ratio = float(window_stats.get("noise_ratio") or 0.0)
    evidence = search_evidence or {}
    if candidate_queue_empty:
        return True, "queue_exhausted"
    for segment_stats in (evidence.get("segment_performance") or {}).values():
        if int(segment_stats.get("zero_result_queries") or 0) >= 2:
            return True, "segment_zero_recall"
    current_wave_noise_ratio = float(evidence.get("current_wave_noise_ratio") or 0.0)
    if int(evidence.get("queries_observed") or 0) >= 2 and current_wave_noise_ratio >= 0.6:
        return True, "high_serp_noise"
    if processed_count >= refinement_window and accepted_target_delta == 0:
        return True, "low_acceptance_window"
    if processed_count >= refinement_window and noise_ratio >= 0.5:
        return True, "high_noise_window"
    return False, None


def _prepend_query_batches(
    *,
    existing_batches: list[list[str]],
    next_batch_index: int,
    new_batches: list[list[str]],
) -> tuple[list[list[str]], int]:
    pending_existing = [batch for batch in existing_batches[next_batch_index:] if batch]
    prepended = [batch for batch in new_batches if batch]
    return prepended + pending_existing, 0


def _select_query_context_map(
    query_batches: list[list[str]],
    *,
    query_context_map: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    selected_queries = set(_flatten_query_batches(query_batches))
    return {
        query: dict(context)
        for query, context in (query_context_map or {}).items()
        if query in selected_queries
    }


def _filter_new_queries(
    query_batches: list[list[str]],
    *,
    seen_queries: set[str],
) -> list[list[str]]:
    filtered_batches: list[list[str]] = []
    for batch in query_batches:
        filtered_batch: list[str] = []
        for query in batch:
            normalized = " ".join(str(query or "").strip().split())
            lowered = normalized.lower()
            if not normalized or lowered in seen_queries:
                continue
            seen_queries.add(lowered)
            filtered_batch.append(normalized)
        if filtered_batch:
            filtered_batches.append(filtered_batch)
    return filtered_batches


def _empty_segment_stats() -> dict[str, Any]:
    return {
        "processed": 0,
        "accepted": 0,
        "needs_review": 0,
        "rejected": 0,
        "geo_failures": 0,
        "language_failures": 0,
        "platforms": {},
        "top_rejection_reasons": {},
        "zero_result_queries": 0,
        "query_count": 0,
        "serp_noise_ratio_sum": 0.0,
        "serp_noise_samples": 0,
        "best_platform": None,
    }


def _summarize_segment_window(
    processed_window: list[dict[str, Any]],
    query_reports: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    segment_performance: dict[str, dict[str, Any]] = {}
    queries_by_segment: dict[str, list[str]] = {}
    accepted_by_segment: dict[str, int] = {}
    needs_review_by_segment: dict[str, int] = {}
    rejected_by_segment: dict[str, int] = {}
    geo_failures_by_segment: dict[str, int] = {}
    language_failures_by_segment: dict[str, int] = {}
    platform_yield: dict[str, dict[str, int]] = {}
    false_positive_patterns: dict[str, int] = {}

    for item in processed_window:
        segment_id = str(item.get("segment_id") or "generic_segment").strip()
        query = str(item.get("query") or "").strip()
        platform = str(item.get("query_platform") or "website").strip()
        decision = str(item.get("acceptance_decision") or "").strip().lower()
        rejection_reason = str(item.get("rejection_reason") or "").strip().lower()
        quality_status = str(item.get("quality_status") or "").strip().lower()
        location_match_status = str(item.get("location_match_status") or "").strip().lower()
        language_match_status = str(item.get("language_match_status") or "").strip().lower()

        segment_stats = segment_performance.setdefault(
            segment_id,
            _empty_segment_stats(),
        )
        segment_stats["processed"] += 1
        segment_stats["platforms"][platform] = int(segment_stats["platforms"].get(platform, 0)) + 1
        queries_by_segment.setdefault(segment_id, [])
        if query and query not in queries_by_segment[segment_id]:
            queries_by_segment[segment_id].append(query)

        platform_stats = platform_yield.setdefault(
            platform,
            {"processed": 0, "accepted": 0, "needs_review": 0, "rejected": 0},
        )
        platform_stats["processed"] += 1

        if decision == "accepted_target":
            segment_stats["accepted"] += 1
            accepted_by_segment[segment_id] = accepted_by_segment.get(segment_id, 0) + 1
            platform_stats["accepted"] += 1
        elif quality_status == "needs_review":
            segment_stats["needs_review"] += 1
            needs_review_by_segment[segment_id] = needs_review_by_segment.get(segment_id, 0) + 1
            platform_stats["needs_review"] += 1
        else:
            segment_stats["rejected"] += 1
            rejected_by_segment[segment_id] = rejected_by_segment.get(segment_id, 0) + 1
            platform_stats["rejected"] += 1

        if location_match_status in {"mismatch", "unknown"}:
            segment_stats["geo_failures"] += 1
            geo_failures_by_segment[segment_id] = geo_failures_by_segment.get(segment_id, 0) + 1
        if language_match_status == "mismatch":
            segment_stats["language_failures"] += 1
            language_failures_by_segment[segment_id] = language_failures_by_segment.get(segment_id, 0) + 1
        if rejection_reason:
            segment_stats["top_rejection_reasons"][rejection_reason] = (
                int(segment_stats["top_rejection_reasons"].get(rejection_reason, 0)) + 1
            )
        if decision in ADAPTIVE_NOISE_DECISIONS or rejection_reason in {"processing_failed", "geo_mismatch", "language_mismatch"}:
            pattern_key = str(item.get("domain") or item.get("query_family") or rejection_reason or "noise").strip()
            if pattern_key:
                false_positive_patterns[pattern_key] = false_positive_patterns.get(pattern_key, 0) + 1

    top_false_positive_patterns = [
        {"pattern": pattern, "count": count}
        for pattern, count in sorted(false_positive_patterns.items(), key=lambda item: (-int(item[1]), str(item[0])))[:8]
    ]

    for report in query_reports or []:
        segment_id = str(report.get("segment_id") or "generic_segment").strip()
        query = str(report.get("query") or "").strip()
        platform = str(report.get("platform") or "website").strip()
        returned_count = int(report.get("returned_count") or 0)
        kept_count = int(report.get("kept_count") or 0)
        zero_results = bool(report.get("zero_results"))
        excluded_reason_counts = report.get("excluded_reason_counts") or {}
        excluded_total = sum(int(count or 0) for count in excluded_reason_counts.values())
        denominator = max(returned_count + excluded_total, 1)
        serp_noise_ratio = round(excluded_total / denominator, 4)

        segment_stats = segment_performance.setdefault(
            segment_id,
            _empty_segment_stats(),
        )
        segment_stats["query_count"] += 1
        segment_stats["serp_noise_ratio_sum"] += serp_noise_ratio
        segment_stats["serp_noise_samples"] += 1
        if zero_results or (returned_count == 0 and kept_count == 0):
            segment_stats["zero_result_queries"] += 1
        if query and query not in queries_by_segment.setdefault(segment_id, []):
            queries_by_segment[segment_id].append(query)

        platform_stats = platform_yield.setdefault(
            platform,
            {"processed": 0, "accepted": 0, "needs_review": 0, "rejected": 0, "query_kept": 0},
        )
        platform_stats["query_kept"] = int(platform_stats.get("query_kept", 0)) + kept_count
        segment_stats["platforms"][platform] = int(segment_stats["platforms"].get(platform, 0)) + kept_count

    for segment_stats in segment_performance.values():
        serp_noise_samples = int(segment_stats.get("serp_noise_samples") or 0)
        serp_noise_ratio_sum = float(segment_stats.get("serp_noise_ratio_sum") or 0.0)
        segment_stats["serp_noise_ratio"] = round((serp_noise_ratio_sum / serp_noise_samples), 4) if serp_noise_samples else 0.0
        segment_stats["best_platform"] = (
            max((segment_stats.get("platforms") or {}).items(), key=lambda item: int(item[1] or 0))[0]
            if segment_stats.get("platforms")
            else None
        )

    return {
        "segment_performance": segment_performance,
        "queries_by_segment": {segment: queries[:8] for segment, queries in queries_by_segment.items()},
        "accepted_by_segment": accepted_by_segment,
        "needs_review_by_segment": needs_review_by_segment,
        "rejected_by_segment": rejected_by_segment,
        "geo_failures_by_segment": geo_failures_by_segment,
        "language_failures_by_segment": language_failures_by_segment,
        "platform_yield": platform_yield,
        "top_false_positive_patterns": top_false_positive_patterns,
    }


def _attach_query_context_reports(
    query_reports: list[dict[str, Any]],
    query_context_map: dict[str, dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    attached_reports: list[dict[str, Any]] = []
    for report in query_reports or []:
        query = " ".join(str(report.get("query") or "").strip().split())
        context = dict((query_context_map or {}).get(query, {}))
        attached_reports.append(
            {
                **report,
                "query": query,
                "segment_id": context.get("segment_id"),
                "platform": context.get("platform") or report.get("platform"),
                "query_family": context.get("family"),
                "iteration_index": context.get("iteration_index"),
                "segment_label": context.get("segment_label"),
            }
        )
    return attached_reports


def _summarize_query_evidence(query_reports: list[dict[str, Any]]) -> dict[str, Any]:
    query_performance: dict[str, dict[str, Any]] = {}
    repeated_domains: dict[str, int] = {}
    high_noise_queries: list[dict[str, Any]] = []
    query_zero_result_count = 0
    current_wave_noise_ratio = 0.0

    for report in query_reports:
        query = str(report.get("query") or "").strip()
        returned_count = int(report.get("returned_count") or 0)
        kept_count = int(report.get("kept_count") or 0)
        excluded_reason_counts = report.get("excluded_reason_counts") or {}
        excluded_total = sum(int(count or 0) for count in excluded_reason_counts.values())
        denominator = max(returned_count + excluded_total, 1)
        noise_ratio = round(excluded_total / denominator, 4)
        zero_results = bool(report.get("zero_results")) or (returned_count == 0 and kept_count == 0)
        if zero_results:
            query_zero_result_count += 1
        if noise_ratio >= 0.6:
            high_noise_queries.append(
                {
                    "query": query,
                    "segment_id": report.get("segment_id"),
                    "platform": report.get("platform"),
                    "noise_ratio": noise_ratio,
                }
            )
        query_performance[query] = {
            "segment_id": report.get("segment_id"),
            "platform": report.get("platform"),
            "returned_count": returned_count,
            "kept_count": kept_count,
            "zero_results": zero_results,
            "noise_ratio": noise_ratio,
            "excluded_reason_counts": excluded_reason_counts,
        }
        current_wave_noise_ratio += noise_ratio
        for domain in report.get("top_domains") or []:
            normalized_domain = str(domain or "").strip().lower()
            if normalized_domain:
                repeated_domains[normalized_domain] = repeated_domains.get(normalized_domain, 0) + 1

    ordered_repeated_domains = [
        {"domain": domain, "count": count}
        for domain, count in sorted(repeated_domains.items(), key=lambda item: (-int(item[1]), str(item[0])))[:8]
    ]
    return {
        "query_reports": query_reports[-12:],
        "query_performance": query_performance,
        "query_zero_result_count": query_zero_result_count,
        "high_noise_queries": high_noise_queries[:8],
        "repeated_domains": ordered_repeated_domains,
        "queries_observed": len(query_reports),
        "current_wave_noise_ratio": round((current_wave_noise_ratio / len(query_reports)), 4) if query_reports else 0.0,
    }


def _summarize_search_evidence_window(
    *,
    processed_window: list[dict[str, Any]],
    query_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        **_summarize_processed_window(processed_window),
        **_summarize_segment_window(processed_window, query_reports),
        **_summarize_query_evidence(query_reports),
    }


async def _append_discovery_iteration(
    db: AsyncSession,
    *,
    job_id: int,
    iteration_index: int,
    phase: str,
    trigger_reason: str,
    input_context_json: dict[str, Any] | None,
    planner_output_json: dict[str, Any] | None,
    executed_queries_json: list[str] | None,
    batch_stats_json: dict[str, Any] | None,
    excluded_reason_counts_json: dict[str, int] | None,
    sample_results_json: list[dict[str, Any]] | None,
) -> None:
    db.add(
        JobDiscoveryIteration(
            job_id=job_id,
            iteration_index=iteration_index,
            phase=phase,
            trigger_reason=trigger_reason,
            input_context_json=input_context_json,
            planner_output_json=planner_output_json,
            executed_queries_json=executed_queries_json,
            batch_stats_json=batch_stats_json,
            excluded_reason_counts_json=excluded_reason_counts_json,
            sample_results_json=sample_results_json,
        )
    )


def _serialize_discovery_iteration(iteration: JobDiscoveryIteration) -> JobDiscoveryIterationOut:
    return JobDiscoveryIterationOut(
        id=iteration.id,
        iteration_index=iteration.iteration_index,
        phase=iteration.phase,
        trigger_reason=iteration.trigger_reason,
        input_context_json=iteration.input_context_json,
        planner_output_json=iteration.planner_output_json,
        executed_queries_json=iteration.executed_queries_json,
        batch_stats_json=iteration.batch_stats_json,
        excluded_reason_counts_json=iteration.excluded_reason_counts_json,
        sample_results_json=iteration.sample_results_json,
        created_at=iteration.created_at,
    )


def _summarize_ai_usage(raw_extractions: list[dict | None]) -> JobAISummary:
    attempts = 0
    successes = 0
    fallbacks = 0
    fallback_reasons: dict[str, int] = {}
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_tokens = 0
    total_latency_ms = 0
    estimated_cost_usd = 0.0
    cost_samples = 0

    for raw_extraction in raw_extractions:
        if not isinstance(raw_extraction, dict):
            continue

        ai_trace = raw_extraction.get("ai_trace")
        if not isinstance(ai_trace, dict):
            continue
        if ai_trace.get("status") == "skipped":
            continue

        attempts += 1
        total_prompt_tokens += int(ai_trace.get("prompt_tokens") or 0)
        total_completion_tokens += int(ai_trace.get("completion_tokens") or 0)
        total_tokens += int(ai_trace.get("total_tokens") or 0)
        total_latency_ms += int(ai_trace.get("latency_ms") or 0)
        if ai_trace.get("estimated_cost_usd") is not None:
            estimated_cost_usd += float(ai_trace.get("estimated_cost_usd") or 0.0)
            cost_samples += 1
        if ai_trace.get("selected_method") == "heuristic":
            fallbacks += 1
            fallback_reason = ai_trace.get("fallback_reason")
            if isinstance(fallback_reason, str) and fallback_reason:
                fallback_reasons[fallback_reason] = fallback_reasons.get(fallback_reason, 0) + 1
        else:
            successes += 1

    fallback_ratio = round((fallbacks / attempts), 4) if attempts else 0.0
    return JobAISummary(
        attempts=attempts,
        successes=successes,
        fallbacks=fallbacks,
        fallback_ratio=fallback_ratio,
        fallback_reasons=fallback_reasons,
        total_prompt_tokens=total_prompt_tokens,
        total_completion_tokens=total_completion_tokens,
        total_tokens=total_tokens,
        total_latency_ms=total_latency_ms,
        average_latency_ms=round((total_latency_ms / attempts), 2) if attempts else 0.0,
        estimated_cost_usd=round(estimated_cost_usd, 8) if cost_samples else None,
    )


async def _get_job_ai_summary(db: AsyncSession, job_id: int) -> JobAISummary:
    result = await db.execute(
        select(JobProspect.raw_extraction_json).where(JobProspect.job_id == job_id)
    )
    raw_extractions = list(result.scalars().all())
    return _summarize_ai_usage(raw_extractions)


def _summarize_quality_usage(
    rows: list[tuple[str | None, str | None] | tuple[str | None, str | None, str | None]]
) -> JobQualitySummary:
    accepted = 0
    needs_review = 0
    rejected = 0
    rejection_reasons: dict[str, int] = {}

    for row in rows:
        quality_status = row[0] if len(row) >= 1 else None
        rejection_reason = row[1] if len(row) >= 2 else None
        acceptance_decision = row[2] if len(row) >= 3 else None
        normalized_decision = str(acceptance_decision or "").strip().lower()

        if normalized_decision.startswith("rejected_"):
            rejected += 1
        elif quality_status == "accepted":
            accepted += 1
        elif quality_status == "needs_review":
            needs_review += 1
        elif quality_status == "rejected":
            rejected += 1

        if isinstance(rejection_reason, str) and rejection_reason:
            rejection_reasons[rejection_reason] = rejection_reasons.get(rejection_reason, 0) + 1

    return JobQualitySummary(
        accepted=accepted,
        needs_review=needs_review,
        rejected=rejected,
        rejection_reasons=rejection_reasons,
    )


def _parse_results_quality_filter(value: str | None) -> list[str]:
    normalized = (value or "accepted").strip().lower()
    if normalized == "all":
        return ["accepted", "needs_review", "rejected"]

    raw_parts = [part.strip().lower() for part in normalized.split(",") if part.strip()]
    allowed = {"accepted", "needs_review", "rejected"}
    invalid_parts = [part for part in raw_parts if part not in allowed]
    if not raw_parts or invalid_parts:
        raise HTTPException(
            status_code=422,
            detail="Parametro 'quality' invalido. Usa accepted, needs_review, rejected o all.",
        )
    parsed = [part for part in raw_parts if part in allowed]
    return list(dict.fromkeys(parsed))


async def _get_job_quality_summary(db: AsyncSession, job_id: int) -> JobQualitySummary:
    result = await db.execute(
        select(JobProspect.quality_status, JobProspect.rejection_reason, JobProspect.acceptance_decision)
        .where(JobProspect.job_id == job_id)
    )
    rows = list(result.all())
    return _summarize_quality_usage(rows)


def _decision_dropoff_reason(rejection_reason: str | None, acceptance_decision: str | None) -> str | None:
    normalized_decision = (acceptance_decision or "").strip().lower()
    if normalized_decision.startswith("rejected_"):
        return normalized_decision
    if isinstance(rejection_reason, str) and rejection_reason:
        return rejection_reason
    return None


def _summarize_capture_usage(
    *,
    rows: list[tuple[str | None, str | None, str | None]],
    total_processed: int,
    total_found: int,
    total_failed: int,
    total_skipped: int,
    target_accepted_results: int,
    max_candidates_to_process: int,
    stopped_reason: str | None,
) -> JobCaptureSummary:
    quality_summary = _summarize_quality_usage(rows)
    dropoff: dict[str, int] = {}
    accepted_count = 0
    for quality_status, rejection_reason, acceptance_decision in rows:
        if acceptance_decision == "accepted_target":
            accepted_count += 1
        reason = _decision_dropoff_reason(rejection_reason, acceptance_decision)
        if reason:
            dropoff[reason] = dropoff.get(reason, 0) + 1
    if total_failed:
        dropoff["processing_failed"] = int(total_failed)
    if total_skipped:
        dropoff["processing_skipped"] = int(total_skipped)

    return JobCaptureSummary(
        target_accepted_results=target_accepted_results,
        max_candidates_to_process=max_candidates_to_process,
        accepted_count=accepted_count,
        needs_review_count=quality_summary.needs_review,
        rejected_count=quality_summary.rejected,
        candidates_processed=int(total_processed or 0),
        candidates_discovered=int(total_found or 0),
        acceptance_rate=round((accepted_count / total_processed), 4) if total_processed else 0.0,
        candidate_dropoff_by_reason=dropoff,
        stopped_reason=stopped_reason,
    )


async def _get_job_capture_summary(db: AsyncSession, job: ScrapingJob) -> JobCaptureSummary:
    result = await db.execute(
        select(JobProspect.quality_status, JobProspect.rejection_reason, JobProspect.acceptance_decision)
        .where(JobProspect.job_id == job.id)
    )
    rows = list(result.all())
    filters_json = job.filters_json or {}
    target_accepted_results = int(filters_json.get("target_accepted_results") or filters_json.get("max_results") or 0)
    max_candidates_to_process = int(filters_json.get("max_candidates_to_process") or job.total_found or 0)
    stopped_reason = None
    final_log = (
        await db.execute(
            select(ScrapingLog)
            .where(ScrapingLog.job_id == job.id, ScrapingLog.message == "Job finalizado")
            .order_by(desc(ScrapingLog.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    if final_log and isinstance(final_log.context_json, dict):
        stopped_reason = final_log.context_json.get("stopped_reason")

    return _summarize_capture_usage(
        rows=rows,
        total_processed=int(job.total_processed or 0),
        total_found=int(job.total_found or 0),
        total_failed=int(job.total_failed or 0),
        total_skipped=int(job.total_skipped or 0),
        target_accepted_results=target_accepted_results,
        max_candidates_to_process=max_candidates_to_process,
        stopped_reason=stopped_reason,
    )


async def _get_job_operational_summary(
    db: AsyncSession,
    job: ScrapingJob,
    capture_summary: JobCaptureSummary,
) -> JobOperationalSummary:
    result = await db.execute(
        select(ScrapingLog.context_json).where(
            ScrapingLog.job_id == job.id,
            ScrapingLog.message.in_(
                [
                    "Job creado y encolado",
                    "Discovery incremental registro exclusiones tempranas",
                ]
            ),
        )
    )
    excluded_reason_counts: dict[str, int] = {}
    for context_json in result.scalars().all():
        if not isinstance(context_json, dict):
            continue
        reason_counts = context_json.get("excluded_reason_counts")
        if isinstance(reason_counts, dict):
            excluded_reason_counts = _merge_reason_counts(excluded_reason_counts, reason_counts)

    return _build_job_operational_summary(
        job=job,
        capture_summary=capture_summary,
        excluded_reason_counts=excluded_reason_counts,
    )


async def _get_job_adaptive_summary(db: AsyncSession, job: ScrapingJob) -> JobAdaptiveSummary:
    filters_json = job.filters_json or {}
    adaptive_enabled = bool(filters_json.get("adaptive_discovery"))
    if not adaptive_enabled:
        return JobAdaptiveSummary(adaptive_enabled=False)

    iteration_rows = (
        await db.execute(
            select(JobDiscoveryIteration)
            .where(JobDiscoveryIteration.job_id == job.id)
            .order_by(JobDiscoveryIteration.iteration_index.asc(), JobDiscoveryIteration.created_at.asc())
        )
    ).scalars().all()
    final_log = (
        await db.execute(
            select(ScrapingLog)
            .where(ScrapingLog.job_id == job.id, ScrapingLog.message == "Job finalizado")
            .order_by(desc(ScrapingLog.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    final_context = final_log.context_json if final_log and isinstance(final_log.context_json, dict) else {}

    queries_executed: list[str] = []
    unique_queries: set[str] = set()
    last_refinement_reason: str | None = None
    for iteration in iteration_rows:
        for query in iteration.executed_queries_json or []:
            normalized = " ".join(str(query or "").strip().split())
            if not normalized:
                continue
            queries_executed.append(normalized)
            unique_queries.add(normalized.lower())
        if iteration.phase == "refinement":
            last_refinement_reason = iteration.trigger_reason

    return JobAdaptiveSummary(
        adaptive_enabled=adaptive_enabled,
        iteration_count=len(iteration_rows),
        last_refinement_reason=last_refinement_reason,
        queries_executed_count=len(queries_executed),
        unique_queries_generated_count=len(unique_queries),
        accepted_since_last_refinement=int(final_context.get("accepted_since_last_refinement") or 0),
        stopped_by=final_context.get("stopped_reason"),
    )


async def _get_recent_job_errors(db: AsyncSession, job_id: int, limit: int = 3) -> list[JobLogOut]:
    result = await db.execute(
        select(ScrapingLog)
        .where(ScrapingLog.job_id == job_id, ScrapingLog.level == "ERROR")
        .order_by(desc(ScrapingLog.created_at))
        .limit(limit)
    )
    return [_serialize_job_log(log) for log in result.scalars().all()]


def _summarize_operational_metrics(job_summaries: list[tuple[ScrapingJob, JobCaptureSummary, JobOperationalSummary]]) -> JobsOperationalMetricsResponse:
    total_jobs = len(job_summaries)
    completed_jobs = 0
    completed_jobs_with_zero_accepted = 0
    total_acceptance_rate = 0.0
    total_candidates_per_accepted = 0.0
    candidates_per_accepted_samples = 0
    total_article_directory_ratio = 0.0
    total_candidates_processed = 0
    total_accepted = 0
    total_article_exclusions = 0
    total_directory_exclusions = 0

    for job, capture_summary, operational_summary in job_summaries:
        total_candidates_processed += int(capture_summary.candidates_processed or 0)
        total_accepted += int(capture_summary.accepted_count or 0)
        total_article_exclusions += int(operational_summary.article_exclusion_count or 0)
        total_directory_exclusions += int(operational_summary.directory_exclusion_count or 0)
        total_article_directory_ratio += float(operational_summary.article_directory_exclusion_ratio or 0.0)

        if job.status == "completed":
            completed_jobs += 1
            total_acceptance_rate += float(capture_summary.acceptance_rate or 0.0)
            if operational_summary.completed_with_zero_accepted:
                completed_jobs_with_zero_accepted += 1
            if operational_summary.candidates_per_accepted is not None:
                total_candidates_per_accepted += float(operational_summary.candidates_per_accepted)
                candidates_per_accepted_samples += 1

    return JobsOperationalMetricsResponse(
        total_jobs=total_jobs,
        completed_jobs=completed_jobs,
        completed_jobs_with_zero_accepted=completed_jobs_with_zero_accepted,
        completed_jobs_with_zero_accepted_ratio=round((completed_jobs_with_zero_accepted / completed_jobs), 4)
        if completed_jobs
        else 0.0,
        average_acceptance_rate=round((total_acceptance_rate / completed_jobs), 4) if completed_jobs else 0.0,
        average_candidates_per_accepted=round((total_candidates_per_accepted / candidates_per_accepted_samples), 4)
        if candidates_per_accepted_samples
        else 0.0,
        average_article_directory_exclusion_ratio=round((total_article_directory_ratio / total_jobs), 4)
        if total_jobs
        else 0.0,
        total_candidates_processed=total_candidates_processed,
        total_accepted=total_accepted,
        total_article_exclusions=total_article_exclusions,
        total_directory_exclusions=total_directory_exclusions,
    )


def _extract_false_phone_filtered_count(raw_extraction_json: dict | None) -> int:
    if not isinstance(raw_extraction_json, dict):
        return 0
    explicit_count = raw_extraction_json.get("invalid_phone_candidates_count")
    if explicit_count is not None:
        return int(explicit_count or 0)

    rejection_counts = raw_extraction_json.get("phone_validation_rejections")
    if not isinstance(rejection_counts, dict):
        return 0
    return sum(int(count or 0) for count in rejection_counts.values())


def _summarize_commercial_usage(rows: list[tuple[str | None, str | None, dict | None]]) -> JobCommercialSummary:
    accepted_target_count = 0
    accepted_related_count = 0
    rejected_non_target_count = 0
    inconsistent_contact_count = 0
    false_phone_filtered_count = 0

    for acceptance_decision, contact_consistency_status, raw_extraction_json in rows:
        normalized_decision = str(acceptance_decision or "").strip().lower()
        normalized_contact_status = str(contact_consistency_status or "").strip().lower()

        if normalized_decision == "accepted_target":
            accepted_target_count += 1
        elif normalized_decision == "accepted_related":
            accepted_related_count += 1
        elif normalized_decision in COMMERCIAL_REJECTION_DECISIONS:
            rejected_non_target_count += 1

        if normalized_contact_status == "inconsistent":
            inconsistent_contact_count += 1

        false_phone_filtered_count += _extract_false_phone_filtered_count(raw_extraction_json)

    total_accepted = accepted_target_count + accepted_related_count
    return JobCommercialSummary(
        accepted_target_count=accepted_target_count,
        accepted_related_count=accepted_related_count,
        rejected_non_target_count=rejected_non_target_count,
        inconsistent_contact_count=inconsistent_contact_count,
        false_phone_filtered_count=false_phone_filtered_count,
        accepted_target_precision=round((accepted_target_count / total_accepted), 4) if total_accepted else 0.0,
    )


async def _get_job_commercial_summary(db: AsyncSession, job: ScrapingJob) -> JobCommercialSummary:
    result = await db.execute(
        select(
            JobProspect.acceptance_decision,
            JobProspect.contact_consistency_status,
            JobProspect.raw_extraction_json,
        ).where(JobProspect.job_id == job.id)
    )
    return _summarize_commercial_usage(list(result.all()))


def _summarize_commercial_metrics(
    job_summaries: list[tuple[ScrapingJob, JobCommercialSummary]],
) -> JobsCommercialMetricsResponse:
    total_jobs = len(job_summaries)
    total_results_processed = 0
    total_accepted_target = 0
    total_accepted_related = 0
    total_rejected_non_target = 0
    inconsistent_contact_count = 0
    false_phone_filtered_count = 0

    for job, commercial_summary in job_summaries:
        total_results_processed += int(job.total_processed or 0)
        total_accepted_target += int(commercial_summary.accepted_target_count or 0)
        total_accepted_related += int(commercial_summary.accepted_related_count or 0)
        total_rejected_non_target += int(commercial_summary.rejected_non_target_count or 0)
        inconsistent_contact_count += int(commercial_summary.inconsistent_contact_count or 0)
        false_phone_filtered_count += int(commercial_summary.false_phone_filtered_count or 0)

    total_accepted = total_accepted_target + total_accepted_related
    return JobsCommercialMetricsResponse(
        total_jobs=total_jobs,
        total_results_processed=total_results_processed,
        total_accepted_target=total_accepted_target,
        total_accepted_related=total_accepted_related,
        total_rejected_non_target=total_rejected_non_target,
        accepted_non_target_rate=round((total_accepted_related / total_results_processed), 4)
        if total_results_processed
        else 0.0,
        inconsistent_contact_count=inconsistent_contact_count,
        inconsistent_contact_rate=round((inconsistent_contact_count / total_results_processed), 4)
        if total_results_processed
        else 0.0,
        false_phone_filtered_count=false_phone_filtered_count,
        false_phone_filtered_rate=round((false_phone_filtered_count / total_results_processed), 4)
        if total_results_processed
        else 0.0,
        accepted_target_precision=round((total_accepted_target / total_accepted), 4) if total_accepted else 0.0,
        rollout_stage=COMMERCIAL_ROLLOUT_STAGE,
        rollout_layers_completed=list(COMMERCIAL_ROLLOUT_LAYERS),
    )


def _flatten_query_batches(query_batches: list[list[str]]) -> list[str]:
    flattened: list[str] = []
    for batch in query_batches:
        for query in batch:
            if query and query not in flattened:
                flattened.append(query)
    return flattened


def _summarize_excluded_reason_counts(excluded_results: list[dict]) -> dict[str, int]:
    reason_counts: dict[str, int] = {}
    for item in excluded_results:
        reason = item.get("reason") if isinstance(item, dict) else None
        if isinstance(reason, str) and reason:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
    return reason_counts


def _merge_reason_counts(*reason_maps: dict[str, int]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for reason_map in reason_maps:
        for reason, count in (reason_map or {}).items():
            merged[reason] = merged.get(reason, 0) + int(count or 0)
    return merged


def _classify_discovery_noise(reason_counts: dict[str, int]) -> tuple[int, int]:
    article_count = 0
    directory_count = 0
    for reason, count in (reason_counts or {}).items():
        if not isinstance(reason, str):
            continue
        normalized_reason = reason.strip().lower()
        if normalized_reason.startswith("excluded_as_article"):
            article_count += int(count or 0)
        elif normalized_reason.startswith("excluded_as_directory"):
            directory_count += int(count or 0)
    return article_count, directory_count


def _build_job_operational_summary(
    *,
    job: ScrapingJob,
    capture_summary: JobCaptureSummary,
    excluded_reason_counts: dict[str, int],
) -> JobOperationalSummary:
    accepted_count = int(capture_summary.accepted_count or 0)
    candidates_processed = int(capture_summary.candidates_processed or 0)
    article_count, directory_count = _classify_discovery_noise(excluded_reason_counts)
    total_considered = int(capture_summary.candidates_discovered or 0) + article_count + directory_count

    return JobOperationalSummary(
        completed_with_zero_accepted=job.status == "completed" and accepted_count == 0,
        candidates_per_accepted=round((candidates_processed / accepted_count), 4) if accepted_count else None,
        article_exclusion_count=article_count,
        directory_exclusion_count=directory_count,
        article_directory_exclusion_ratio=round(((article_count + directory_count) / total_considered), 4)
        if total_considered
        else 0.0,
    )


async def _discover_next_candidate_batch(
    *,
    query_batches: list[list[str]],
    query_context_map: dict[str, dict[str, Any]] | None,
    next_batch_index: int,
    target_accepted_results: int,
    candidate_cap: int,
    remaining_budget: int,
    seen_urls: set[str],
    user_profession: str | None = None,
    target_niche: str | None = None,
    target_language: str | None = None,
    target_location: str | None = None,
    target_budget_signals: list[str] | None = None,
    batch_budget_override: int | None = None,
) -> tuple[list[SearchDiscoveryEntry], int, list[str], list[dict], list[dict[str, Any]], str | None]:
    warnings: list[str] = []
    excluded_results: list[dict] = []
    query_reports: list[dict[str, Any]] = []
    used_queries: list[str] = []

    while next_batch_index < len(query_batches):
        batch_queries = [query for query in query_batches[next_batch_index] if query]
        next_batch_index += 1
        if not batch_queries:
            continue

        batch_budget = (
            int(batch_budget_override)
            if batch_budget_override is not None
            else resolve_discovery_batch_budget(
                target_accepted_results=target_accepted_results,
                candidate_cap=candidate_cap,
                remaining_budget=remaining_budget,
            )
        )
        if batch_budget <= 0:
            break

        discovery_result = await discover_prospect_urls_by_queries(
            batch_queries,
            max_results=batch_budget,
            user_profession=user_profession,
            target_niche=target_niche,
            target_language=target_language,
            target_location=target_location,
            target_budget_signals=target_budget_signals,
        )
        used_queries.extend(batch_queries)
        excluded_results.extend(discovery_result.excluded_results)
        query_reports.extend(discovery_result.query_reports or [])
        if discovery_result.warning_message:
            warnings.append(discovery_result.warning_message)

        fresh_entries: list[SearchDiscoveryEntry] = []
        for entry in discovery_result.entries:
            entry.query_context = dict((query_context_map or {}).get(str(entry.query or "").strip(), {}))
            if entry.url in seen_urls:
                excluded_results.append(
                    {
                        "url": entry.url,
                        "reason": "duplicate_url_reopened",
                        "query": entry.query,
                        "query_context": entry.query_context,
                        "title": entry.title,
                        "snippet": entry.snippet,
                        "business_likeness_score": entry.business_likeness_score,
                        "website_result_score": entry.website_result_score,
                        "social_profile_score": entry.social_profile_score,
                        "result_kind": entry.result_kind,
                        "discovery_reasons": entry.discovery_reasons,
                        "seed_source_url": entry.seed_source_url,
                        "seed_source_type": entry.seed_source_type,
                    }
                )
                continue
            seen_urls.add(entry.url)
            fresh_entries.append(entry)
        attached_query_reports = _attach_query_context_reports(query_reports, query_context_map)
        return fresh_entries, next_batch_index, used_queries, excluded_results, attached_query_reports, "; ".join(warnings) if warnings else None

    attached_query_reports = _attach_query_context_reports(query_reports, query_context_map)
    return [], next_batch_index, used_queries, excluded_results, attached_query_reports, "; ".join(warnings) if warnings else None


async def background_scraping_worker(job_id: int, urls: list, job_context: dict):
    """
    Simulación de la cola que procesará los dominios solicitados en segundo plano
    sin colgar la API principal. 
    Nota: Redefinimos el engine aca o pasamos session_maker por seguridad de hilos,
    pero para este MVP podemos instanciar una nueva AsyncSession aquí dentro.
    """
    from app.database import AsyncSessionLocal

    logger.info(f"Worker Iniciado. Lanzando Scraping para Job {job_id}")

    async with AsyncSessionLocal() as db:
        try:
            job = await db.get(ScrapingJob, job_id)
            if not job:
                return

            target_accepted_results = int(job_context.get("target_accepted_results") or 1)
            max_candidates_to_process = int(job_context.get("max_candidates_to_process") or len(urls) or 1)
            exhaustive_candidate_scan = bool(job_context.get("exhaustive_candidate_scan"))
            candidate_queue = list(urls)[:max_candidates_to_process]
            query_batches = [batch for batch in (job_context.get("discovery_query_batches") or []) if isinstance(batch, list)]
            query_context_map = (
                dict(job_context.get("discovery_query_context_map"))
                if isinstance(job_context.get("discovery_query_context_map"), dict)
                else {}
            )
            next_discovery_batch_index = int(job_context.get("next_discovery_batch_index") or 0)
            candidate_batch_size = int(
                job_context.get("candidate_batch_size")
                or resolve_candidate_batch_size(
                    target_accepted_results=target_accepted_results,
                    candidate_cap=max_candidates_to_process,
                )
            )
            seen_candidate_urls = {
                entry.url
                for entry in candidate_queue
                if isinstance(entry, SearchDiscoveryEntry) and entry.url
            }
            seen_candidate_urls.update(
                str(entry.get("url"))
                for entry in candidate_queue
                if isinstance(entry, dict) and entry.get("url")
            )
            seen_candidate_urls.update(
                str(entry)
                for entry in candidate_queue
                if not isinstance(entry, (SearchDiscoveryEntry, dict))
            )
            total_found = len(candidate_queue)
            total_processed = 0
            total_saved = 0
            total_failed = 0
            total_skipped = 0
            accepted_results = 0
            stopped_reason: str | None = None
            adaptive_discovery = bool(
                job_context.get("adaptive_discovery")
                and normalize_discovery_method(job_context.get("discovery_method")) == "search_query"
            )
            adaptive_refinement_every_processed = int(
                job_context.get("adaptive_refinement_every_processed")
                or _resolve_adaptive_refinement_window(max_candidates_to_process)
            )
            max_query_refinements = int(job_context.get("max_query_refinements") or 0)
            refinement_count = 0
            last_refinement_reason: str | None = None
            accepted_since_last_refinement = 0
            processed_window: list[dict[str, Any]] = []
            query_reports_window: list[dict[str, Any]] = []
            window_excluded_reason_counts: dict[str, int] = {}
            executed_queries_history = [
                " ".join(str(query or "").strip().split())
                for query in (job_context.get("discovery_queries") or [])
                if " ".join(str(query or "").strip().split())
            ]
            seen_queries = {query.lower() for query in executed_queries_history}
            seen_domains = {
                domain
                for domain in (
                    _extract_domain_from_url(entry.url) if isinstance(entry, SearchDiscoveryEntry) else _extract_domain_from_url(entry.get("url")) if isinstance(entry, dict) else _extract_domain_from_url(str(entry))
                    for entry in candidate_queue
                )
                if domain
            }

            if (
                not candidate_queue
                and str(job_context.get("search_query") or "").strip()
                and normalize_discovery_method(job_context.get("discovery_method")) == "search_query"
            ):
                ai_search_plan = await initial_search_plan(
                    {
                        **job_context,
                        "target_location": job_context.get("target_location"),
                    }
                )
                discovery_query_plan = build_discovery_query_plan(
                    search_query=job_context.get("search_query"),
                    user_profession=job_context.get("user_profession"),
                    user_technologies=job_context.get("user_technologies"),
                    target_niche=job_context.get("target_niche"),
                    target_location=job_context.get("target_location"),
                    target_language=job_context.get("target_language"),
                    user_service_offers=job_context.get("user_service_offers"),
                    user_service_constraints=job_context.get("user_service_constraints"),
                    user_target_offer_focus=job_context.get("user_target_offer_focus"),
                    target_budget_signals=job_context.get("target_budget_signals"),
                    planner_output=ai_search_plan,
                    ai_dork_queries=ai_search_plan.get("optimal_dork_queries"),
                    ai_negative_terms=ai_search_plan.get("dynamic_negative_terms"),
                    max_queries=_resolve_iteration_query_limit(
                        iteration_index=0,
                        max_candidates_to_process=max_candidates_to_process,
                        target_accepted_results=target_accepted_results,
                    ),
                    iteration_index=0,
                )
                query_batches = discovery_query_plan["batches"]
                query_context_map = discovery_query_plan["query_context_map"]
                job_context["discovery_queries"] = []
                job_context["discovery_query_batches"] = query_batches
                job_context["discovery_query_context_map"] = query_context_map
                job_context["target_entity_hints"] = ai_search_plan.get("target_entity_hints", [])
                job_context["exclusion_entity_hints"] = ai_search_plan.get("exclusion_entity_hints", [])
                job_context["refinement_goal"] = ai_search_plan.get("refinement_goal")
                await _append_discovery_iteration(
                    db,
                    job_id=job_id,
                    iteration_index=0,
                    phase="initial",
                    trigger_reason="initial_plan",
                    input_context_json={
                        "search_query": job_context.get("search_query"),
                        "target_niche": job_context.get("target_niche"),
                        "target_location": job_context.get("target_location"),
                        "target_language": job_context.get("target_language"),
                        "target_budget_signals": job_context.get("target_budget_signals"),
                        "initial_wave": ai_search_plan.get("initial_wave"),
                        "query_actions": ai_search_plan.get("query_actions"),
                        "query_plan_family_distribution": discovery_query_plan.get("family_distribution"),
                    },
                    planner_output_json=ai_search_plan,
                    executed_queries_json=[],
                    batch_stats_json={
                        "planned_queries_count": len(discovery_query_plan.get("queries") or []),
                        "planned_batches_count": len(query_batches),
                        "query_plan_family_distribution": discovery_query_plan.get("family_distribution"),
                    },
                    excluded_reason_counts_json={},
                    sample_results_json=[],
                )
                await _append_job_log(
                    db,
                    job_id,
                    "INFO",
                    "Discovery inicial preparado en background",
                    source_name="discovery",
                    context_json={
                        "planned_queries_count": len(discovery_query_plan.get("queries") or []),
                        "planned_batches_count": len(query_batches),
                        "initial_wave_size": len(ai_search_plan.get("initial_wave") or []),
                        "query_plan_family_distribution": discovery_query_plan.get("family_distribution"),
                        "planner_profile": ai_search_plan.get("planner_profile"),
                    },
                )
                await db.commit()

            job.status = "running"
            job.started_at = _utcnow()
            job.finished_at = None
            job.error_message = None
            _apply_job_runtime_totals(
                job,
                total_found=total_found,
                total_processed=total_processed,
                total_saved=total_saved,
                total_failed=total_failed,
                total_skipped=total_skipped,
            )
            ai_attempts = 0
            ai_successes = 0
            ai_fallbacks = 0
            ai_fallback_reasons: dict[str, int] = {}
            ai_prompt_tokens = 0
            ai_completion_tokens = 0
            ai_total_tokens = 0
            ai_total_latency_ms = 0
            ai_estimated_cost_usd = 0.0
            ai_cost_samples = 0
            await _append_job_log(
                db,
                job_id,
                "INFO",
                "Job iniciado",
                source_name="worker",
                context_json={
                    "total_urls": len(candidate_queue),
                    "discovery_method": job_context.get("discovery_method"),
                    "search_query": job_context.get("search_query"),
                    "provider_name": job_context.get("provider_name"),
                    "target_accepted_results": target_accepted_results,
                    "max_candidates_to_process": max_candidates_to_process,
                    "candidate_batch_size": candidate_batch_size,
                    "pending_discovery_batches": max(len(query_batches) - next_discovery_batch_index, 0),
                    "adaptive_discovery": adaptive_discovery,
                    "adaptive_refinement_every_processed": adaptive_refinement_every_processed,
                    "max_query_refinements": max_query_refinements,
                },
            )
            await db.commit()
            batch_number = 0

            while total_processed < max_candidates_to_process:
                if not exhaustive_candidate_scan and accepted_results >= target_accepted_results:
                    stopped_reason = "target_reached"
                    break

                if not candidate_queue:
                    remaining_budget = max_candidates_to_process - total_found
                    if remaining_budget <= 0:
                        break

                    discovery_opened = False
                    while remaining_budget > 0:
                        if next_discovery_batch_index >= len(query_batches):
                            if not adaptive_discovery:
                                break

                            search_evidence_window = _summarize_search_evidence_window(
                                processed_window=processed_window,
                                query_reports=query_reports_window,
                            )
                            window_stats = _summarize_processed_window(processed_window)
                            should_refine, trigger_reason = _should_trigger_adaptive_refinement(
                                window_stats=window_stats,
                                candidate_queue_empty=True,
                                refinement_window=adaptive_refinement_every_processed,
                                search_evidence=search_evidence_window,
                            )
                            if (
                                not should_refine
                                or refinement_count >= max_query_refinements
                            ):
                                if refinement_count >= max_query_refinements:
                                    stopped_reason = "refinement_limit_reached"
                                break

                            false_positive_samples = _build_false_positive_samples(processed_window)
                            accepted_samples = _build_accepted_samples(processed_window)
                            top_rejection_reasons = dict(
                                sorted(
                                    (window_stats.get("rejection_reasons") or {}).items(),
                                    key=lambda item: (-int(item[1] or 0), str(item[0])),
                                )[:5]
                            )
                            iteration_memory = {
                                "trigger_reason": trigger_reason,
                                "window_stats": window_stats,
                                "top_rejection_reasons": top_rejection_reasons,
                                "queries_already_executed": executed_queries_history[-25:],
                                "seen_domains": sorted(seen_domains)[:40],
                                "false_positive_samples": false_positive_samples,
                                "accepted_samples": accepted_samples,
                                **search_evidence_window,
                            }
                            refined_plan = await refine_search_plan(job_context, iteration_memory)
                            refined_query_plan = build_discovery_query_plan(
                                search_query=job_context.get("search_query"),
                                user_profession=job_context.get("user_profession"),
                                user_technologies=job_context.get("user_technologies"),
                                target_niche=job_context.get("target_niche"),
                                target_location=job_context.get("target_location"),
                                target_language=job_context.get("target_language"),
                                user_service_offers=job_context.get("user_service_offers"),
                                user_service_constraints=job_context.get("user_service_constraints"),
                                user_target_offer_focus=job_context.get("user_target_offer_focus"),
                                target_budget_signals=job_context.get("target_budget_signals"),
                                planner_output=refined_plan,
                                ai_dork_queries=refined_plan.get("optimal_dork_queries"),
                                ai_negative_terms=refined_plan.get("dynamic_negative_terms"),
                                max_queries=_resolve_iteration_query_limit(
                                    iteration_index=refinement_count + 1,
                                    max_candidates_to_process=max_candidates_to_process,
                                    target_accepted_results=target_accepted_results,
                                ),
                                iteration_index=refinement_count + 1,
                            )
                            refined_batches = _filter_new_queries(refined_query_plan["batches"], seen_queries=seen_queries)
                            refined_query_context_map = _select_query_context_map(
                                refined_batches,
                                query_context_map=refined_query_plan["query_context_map"],
                            )
                            if not refined_batches:
                                stopped_reason = "refinement_limit_reached" if refinement_count >= max_query_refinements else "discovery_exhausted"
                                break

                            appended_queries = _flatten_query_batches(refined_batches)
                            query_batches, next_discovery_batch_index = _prepend_query_batches(
                                existing_batches=query_batches,
                                next_batch_index=next_discovery_batch_index,
                                new_batches=refined_batches,
                            )
                            query_context_map.update(refined_query_context_map)
                            refinement_count += 1
                            last_refinement_reason = trigger_reason
                            accepted_since_last_refinement = 0
                            await _append_discovery_iteration(
                                db,
                                job_id=job_id,
                                iteration_index=refinement_count,
                                phase="refinement",
                                trigger_reason=trigger_reason or "queue_exhausted",
                                input_context_json=iteration_memory,
                                planner_output_json=refined_plan,
                                executed_queries_json=appended_queries,
                                batch_stats_json=window_stats,
                                excluded_reason_counts_json=window_excluded_reason_counts or {},
                                sample_results_json=(query_reports_window[:6] or false_positive_samples or accepted_samples),
                            )
                            await _append_job_log(
                                db,
                                job_id,
                                "INFO",
                                "Discovery refinado con DeepSeek",
                                source_name="discovery",
                                context_json={
                                    "iteration_index": refinement_count,
                                    "trigger_reason": trigger_reason,
                                    "refinement_goal": refined_plan.get("refinement_goal"),
                                    "queries": appended_queries,
                                    "planned_query_count": len(appended_queries),
                                    "window_stats": window_stats,
                                    "search_evidence_window": search_evidence_window,
                                    "top_rejection_reasons": top_rejection_reasons,
                                    "next_segments_to_try": refined_plan.get("next_segments_to_try"),
                                    "segments_to_pause": refined_plan.get("segments_to_pause"),
                                },
                            )
                            await db.commit()
                            processed_window = []
                            query_reports_window = []
                            window_excluded_reason_counts = {}
                            remaining_budget = max_candidates_to_process - total_found
                            continue

                        discovery_budget_override = None
                        if adaptive_discovery and refinement_count > 0:
                            discovery_budget_override = min(MAX_REFINEMENT_DISCOVERY_BUDGET, remaining_budget)
                        new_entries, next_discovery_batch_index, used_queries, excluded_results, batch_query_reports, warning_message = await _discover_next_candidate_batch(
                            query_batches=query_batches,
                            query_context_map=query_context_map,
                            next_batch_index=next_discovery_batch_index,
                            target_accepted_results=target_accepted_results,
                            candidate_cap=max_candidates_to_process,
                            remaining_budget=remaining_budget,
                            seen_urls=seen_candidate_urls,
                            user_profession=job_context.get("user_profession"),
                            target_niche=job_context.get("target_niche"),
                            target_language=job_context.get("target_language"),
                            target_location=job_context.get("target_location"),
                            target_budget_signals=job_context.get("target_budget_signals"),
                            batch_budget_override=discovery_budget_override,
                        )
                        query_reports_window.extend(batch_query_reports)

                        if used_queries:
                            for query in used_queries:
                                normalized_query = " ".join(str(query or "").strip().split())
                                if not normalized_query:
                                    continue
                                executed_queries_history.append(normalized_query)
                                seen_queries.add(normalized_query.lower())

                        excluded_reason_counts = _summarize_excluded_reason_counts(excluded_results)
                        if excluded_reason_counts:
                            window_excluded_reason_counts = _merge_reason_counts(
                                window_excluded_reason_counts,
                                excluded_reason_counts,
                            )

                        if warning_message:
                            await _append_job_log(
                                db,
                                job_id,
                                "WARNING",
                                "Discovery incremental devolvio avisos",
                                source_name="discovery",
                                context_json={
                                    "queries": used_queries,
                                    "warning_message": warning_message,
                                    "query_reports": batch_query_reports[:6],
                                },
                            )

                        if excluded_results:
                            await _append_job_log(
                                db,
                                job_id,
                                "INFO",
                                "Discovery incremental registro exclusiones tempranas",
                                source_name="discovery",
                                context_json={
                                    "queries": used_queries,
                                    "excluded_results_count": len(excluded_results),
                                    "excluded_reason_counts": excluded_reason_counts,
                                    "query_reports": batch_query_reports[:6],
                                    "excluded_results_preview": excluded_results[:20],
                                },
                            )

                        if not new_entries:
                            await db.commit()
                            if adaptive_discovery:
                                search_evidence_window = _summarize_search_evidence_window(
                                    processed_window=processed_window,
                                    query_reports=query_reports_window,
                                )
                                should_refine, _ = _should_trigger_adaptive_refinement(
                                    window_stats=_summarize_processed_window(processed_window),
                                    candidate_queue_empty=False,
                                    refinement_window=adaptive_refinement_every_processed,
                                    search_evidence=search_evidence_window,
                                )
                                continue
                            break

                        for index, entry in enumerate(new_entries, start=total_found + 1):
                            entry.position = index
                            if entry.url:
                                domain = _extract_domain_from_url(entry.url)
                                if domain:
                                    seen_domains.add(domain)
                        candidate_queue.extend(new_entries)
                        total_found += len(new_entries)
                        _apply_job_runtime_totals(
                            job,
                            total_found=total_found,
                            total_processed=total_processed,
                            total_saved=total_saved,
                            total_failed=total_failed,
                            total_skipped=total_skipped,
                        )
                        await _append_job_log(
                            db,
                            job_id,
                            "INFO",
                            "Discovery reabierto por captura insuficiente",
                            source_name="discovery",
                            context_json={
                                "queries": used_queries,
                                "new_candidates": len(new_entries),
                                "total_found": total_found,
                                "accepted_results_so_far": accepted_results,
                                "iteration_budget": discovery_budget_override,
                            },
                        )
                        await db.commit()
                        discovery_opened = True
                        break

                    if not candidate_queue:
                        await db.commit()
                        break
                    if discovery_opened:
                        remaining_budget = max_candidates_to_process - total_found

                current_batch = candidate_queue[:candidate_batch_size]
                candidate_queue = candidate_queue[candidate_batch_size:]
                if not current_batch:
                    break

                batch_number += 1
                accepted_before_batch = accepted_results
                await _append_job_log(
                    db,
                    job_id,
                    "INFO",
                    "Procesando tanda de candidatos",
                    source_name="worker",
                    context_json={
                        "batch_number": batch_number,
                        "batch_size": len(current_batch),
                        "accepted_results_before_batch": accepted_results,
                        "remaining_buffered_candidates": len(candidate_queue),
                    },
                )
                await db.commit()

                for entry in current_batch:
                    if isinstance(entry, SearchDiscoveryEntry):
                        discovery_entry = {
                            "url": entry.url,
                            "query": entry.query,
                            "query_context": entry.query_context,
                            "position": entry.position or (total_processed + 1),
                            "title": entry.title,
                            "snippet": entry.snippet,
                            "discovery_confidence": entry.discovery_confidence,
                            "business_likeness_score": entry.business_likeness_score,
                            "website_result_score": entry.website_result_score,
                            "social_profile_score": entry.social_profile_score,
                            "result_kind": entry.result_kind,
                            "discovery_reasons": entry.discovery_reasons,
                            "seed_source_url": entry.seed_source_url,
                            "seed_source_type": entry.seed_source_type,
                        }
                    elif isinstance(entry, dict):
                        discovery_entry = dict(entry)
                    else:
                        discovery_entry = {"url": str(entry)}

                    rank_position = int(discovery_entry.get("position") or (total_processed + 1))
                    url = str(discovery_entry.get("url"))
                    total_processed += 1
                    _apply_job_runtime_totals(
                        job,
                        total_found=total_found,
                        total_processed=total_processed,
                        total_saved=total_saved,
                        total_failed=total_failed,
                        total_skipped=total_skipped,
                    )
                    try:
                        prospect_dict = await scrape_single_prospect(
                            url,
                            {**job_context, "discovery_entry": discovery_entry},
                        )

                        if not prospect_dict:
                            total_skipped += 1
                            _apply_job_runtime_totals(
                                job,
                                total_found=total_found,
                                total_processed=total_processed,
                                total_saved=total_saved,
                                total_failed=total_failed,
                                total_skipped=total_skipped,
                            )
                            await _append_job_log(
                                db,
                                job_id,
                                "WARNING",
                                "URL omitida por falta de contenido scrapeable",
                                source_name="worker",
                                context_json={"url": url, "rank_position": rank_position, "discovery_query": discovery_entry.get("query")},
                            )
                            await db.commit()
                            await asyncio.sleep(2)
                            continue

                        prospect_dict["job_id"] = job_id
                        prospect_dict["rank_position"] = rank_position
                        ai_trace = prospect_dict.get("ai_trace")
                        if isinstance(ai_trace, dict):
                            if ai_trace.get("status") != "skipped":
                                ai_attempts += 1
                                ai_prompt_tokens += int(ai_trace.get("prompt_tokens") or 0)
                                ai_completion_tokens += int(ai_trace.get("completion_tokens") or 0)
                                ai_total_tokens += int(ai_trace.get("total_tokens") or 0)
                                ai_total_latency_ms += int(ai_trace.get("latency_ms") or 0)
                                if ai_trace.get("estimated_cost_usd") is not None:
                                    ai_estimated_cost_usd += float(ai_trace.get("estimated_cost_usd") or 0.0)
                                    ai_cost_samples += 1
                            fallback_reason = ai_trace.get("fallback_reason")
                            if ai_trace.get("status") == "skipped":
                                await _append_job_log(
                                    db,
                                    job_id,
                                    "INFO",
                                    "Enriquecimiento IA omitido por gate de calidad",
                                    source_name="ai_enrichment",
                                    context_json={
                                        "stage": "ai_enrichment",
                                        "url": url,
                                        "domain": prospect_dict.get("domain"),
                                        "rank_position": rank_position,
                                        "selected_method": ai_trace.get("selected_method"),
                                        "evaluation_method": ai_trace.get("evaluation_method"),
                                        "fallback_reason": fallback_reason,
                                        "quality_status": prospect_dict.get("quality_status"),
                                        "acceptance_decision": prospect_dict.get("acceptance_decision"),
                                    },
                                )
                            elif ai_trace.get("selected_method") == "heuristic":
                                ai_fallbacks += 1
                                if isinstance(fallback_reason, str) and fallback_reason:
                                    ai_fallback_reasons[fallback_reason] = ai_fallback_reasons.get(fallback_reason, 0) + 1
                                await _append_job_log(
                                    db,
                                    job_id,
                                    "WARNING",
                                    "Fallback heurístico activado para enriquecimiento IA",
                                    source_name="ai_enrichment",
                                    context_json={
                                        "stage": "ai_enrichment",
                                        "url": url,
                                        "domain": prospect_dict.get("domain"),
                                        "rank_position": rank_position,
                                        "provider": ai_trace.get("provider"),
                                        "selected_method": ai_trace.get("selected_method"),
                                        "evaluation_method": ai_trace.get("evaluation_method"),
                                        "fallback_reason": fallback_reason,
                                        "error_type": ai_trace.get("error_type"),
                                        "retryable": ai_trace.get("retryable"),
                                        "latency_ms": ai_trace.get("latency_ms"),
                                        "prompt_tokens": ai_trace.get("prompt_tokens"),
                                        "completion_tokens": ai_trace.get("completion_tokens"),
                                        "total_tokens": ai_trace.get("total_tokens"),
                                        "estimated_cost_usd": ai_trace.get("estimated_cost_usd"),
                                    },
                                )
                            else:
                                ai_successes += 1
                                await _append_job_log(
                                    db,
                                    job_id,
                                    "INFO",
                                    "Enriquecimiento IA completado",
                                    source_name="ai_enrichment",
                                    context_json={
                                        "stage": "ai_enrichment",
                                        "url": url,
                                        "domain": prospect_dict.get("domain"),
                                        "rank_position": rank_position,
                                        "provider": ai_trace.get("provider"),
                                        "selected_method": ai_trace.get("selected_method"),
                                        "evaluation_method": ai_trace.get("evaluation_method"),
                                        "latency_ms": ai_trace.get("latency_ms"),
                                        "prompt_tokens": ai_trace.get("prompt_tokens"),
                                        "completion_tokens": ai_trace.get("completion_tokens"),
                                        "total_tokens": ai_trace.get("total_tokens"),
                                        "estimated_cost_usd": ai_trace.get("estimated_cost_usd"),
                                    },
                                )

                        saved_prospect = await save_scraped_prospect(db, prospect_dict, job_context)
                        if saved_prospect:
                            total_saved += 1
                            if prospect_dict.get("acceptance_decision") == "accepted_target":
                                accepted_results += 1
                                accepted_since_last_refinement += 1
                            prospect_domain = str(saved_prospect.domain or prospect_dict.get("domain") or "").strip().lower()
                            if prospect_domain:
                                seen_domains.add(prospect_domain)
                            _apply_job_runtime_totals(
                                job,
                                total_found=total_found,
                                total_processed=total_processed,
                                total_saved=total_saved,
                                total_failed=total_failed,
                                total_skipped=total_skipped,
                            )
                            await _append_job_log(
                                db,
                                job_id,
                                "INFO",
                                "Prospecto persistido",
                                source_name="worker",
                                context_json={
                                    "url": url,
                                    "domain": saved_prospect.domain,
                                    "canonical_identity": saved_prospect.canonical_identity,
                                    "rank_position": rank_position,
                                    "quality_status": prospect_dict.get("quality_status"),
                                    "acceptance_decision": prospect_dict.get("acceptance_decision"),
                                    "rejection_reason": prospect_dict.get("rejection_reason"),
                                    "accepted_results_so_far": accepted_results,
                                },
                            )
                        else:
                            total_failed += 1
                            _apply_job_runtime_totals(
                                job,
                                total_found=total_found,
                                total_processed=total_processed,
                                total_saved=total_saved,
                                total_failed=total_failed,
                                total_skipped=total_skipped,
                            )
                            await _append_job_log(
                                db,
                                job_id,
                                "ERROR",
                                "No se pudo persistir el prospecto",
                                source_name="worker",
                                context_json={"url": url, "rank_position": rank_position},
                            )
                        processed_window.append(
                            {
                                "url": url,
                                "domain": str(saved_prospect.domain if saved_prospect else prospect_dict.get("domain") or ""),
                                "title": str(prospect_dict.get("company_name") or discovery_entry.get("title") or ""),
                                "company_name": prospect_dict.get("company_name"),
                                "query": discovery_entry.get("query"),
                                "segment_id": (discovery_entry.get("query_context") or {}).get("segment_id"),
                                "query_family": (discovery_entry.get("query_context") or {}).get("family"),
                                "query_platform": (discovery_entry.get("query_context") or {}).get("platform"),
                                "quality_status": prospect_dict.get("quality_status"),
                                "acceptance_decision": prospect_dict.get("acceptance_decision"),
                                "rejection_reason": prospect_dict.get("rejection_reason"),
                                "location_match_status": prospect_dict.get("location_match_status"),
                                "language_match_status": prospect_dict.get("language_match_status"),
                            }
                        )
                        await db.commit()

                        if accepted_results >= target_accepted_results:
                            if exhaustive_candidate_scan:
                                await _append_job_log(
                                    db,
                                    job_id,
                                    "INFO",
                                    "Objetivo aceptado alcanzado, pero se mantiene captura exhaustiva",
                                    source_name="worker",
                                    context_json={
                                        "target_accepted_results": target_accepted_results,
                                        "accepted_results": accepted_results,
                                        "processed_candidates": total_processed,
                                        "max_candidates_to_process": max_candidates_to_process,
                                        "batch_number": batch_number,
                                    },
                                )
                                await db.commit()
                            else:
                                stopped_reason = "target_reached"
                                await _append_job_log(
                                    db,
                                    job_id,
                                    "INFO",
                                    "Objetivo de prospectos aceptados alcanzado",
                                    source_name="worker",
                                    context_json={
                                        "target_accepted_results": target_accepted_results,
                                        "accepted_results": accepted_results,
                                        "processed_candidates": total_processed,
                                        "batch_number": batch_number,
                                    },
                                )
                                await db.commit()
                                break
                    except Exception as e:
                        await db.rollback()
                        job = await db.get(ScrapingJob, job_id)
                        if not job:
                            raise
                        total_failed += 1
                        job.status = "running"
                        _apply_job_runtime_totals(
                            job,
                            total_found=total_found,
                            total_processed=total_processed,
                            total_saved=total_saved,
                            total_failed=total_failed,
                            total_skipped=total_skipped,
                        )
                        logger.error(f"Error procesando prospect {url}: {e}")
                        error_context = {
                            "url": url,
                            "rank_position": rank_position,
                            "error": str(e),
                        }
                        if isinstance(e, FetchHtmlError):
                            error_context.update({"stage": "fetch_html", **e.to_context()})
                        else:
                            error_context["stage"] = "processing"
                        await _append_job_log(
                            db,
                            job_id,
                            "ERROR",
                            "Fallo procesando URL",
                            source_name="worker",
                            context_json=error_context,
                        )
                        processed_window.append(
                            {
                                "url": url,
                                "domain": _extract_domain_from_url(url),
                                "title": str(discovery_entry.get("title") or ""),
                                "query": discovery_entry.get("query"),
                                "segment_id": (discovery_entry.get("query_context") or {}).get("segment_id"),
                                "query_family": (discovery_entry.get("query_context") or {}).get("family"),
                                "query_platform": (discovery_entry.get("query_context") or {}).get("platform"),
                                "acceptance_decision": "rejected_low_confidence",
                                "rejection_reason": "processing_failed",
                                "location_match_status": None,
                                "language_match_status": None,
                            }
                        )
                        await db.commit()
                        if isinstance(e, SQLAlchemyError):
                            raise

                    await asyncio.sleep(2)

                await _append_job_log(
                    db,
                    job_id,
                    "INFO",
                    "Tanda procesada",
                    source_name="worker",
                    context_json={
                        "batch_number": batch_number,
                        "batch_size": len(current_batch),
                        "accepted_in_batch": accepted_results - accepted_before_batch,
                        "accepted_results_so_far": accepted_results,
                        "remaining_buffered_candidates": len(candidate_queue),
                    },
                )
                await db.commit()

                if adaptive_discovery and stopped_reason != "target_reached":
                    search_evidence_window = _summarize_search_evidence_window(
                        processed_window=processed_window,
                        query_reports=query_reports_window,
                    )
                    window_stats = _summarize_processed_window(processed_window)
                    should_refine, trigger_reason = _should_trigger_adaptive_refinement(
                        window_stats=window_stats,
                        candidate_queue_empty=not candidate_queue,
                        refinement_window=adaptive_refinement_every_processed,
                        search_evidence=search_evidence_window,
                    )
                    if should_refine and refinement_count < max_query_refinements:
                        false_positive_samples = _build_false_positive_samples(processed_window)
                        accepted_samples = _build_accepted_samples(processed_window)
                        top_rejection_reasons = dict(
                            sorted(
                                (window_stats.get("rejection_reasons") or {}).items(),
                                key=lambda item: (-int(item[1] or 0), str(item[0])),
                            )[:5]
                        )
                        iteration_memory = {
                            "trigger_reason": trigger_reason,
                            "window_stats": window_stats,
                            "top_rejection_reasons": top_rejection_reasons,
                            "queries_already_executed": executed_queries_history[-25:],
                            "seen_domains": sorted(seen_domains)[:40],
                            "false_positive_samples": false_positive_samples,
                            "accepted_samples": accepted_samples,
                            **search_evidence_window,
                        }
                        refined_plan = await refine_search_plan(job_context, iteration_memory)
                        refined_query_plan = build_discovery_query_plan(
                            search_query=job_context.get("search_query"),
                            user_profession=job_context.get("user_profession"),
                            user_technologies=job_context.get("user_technologies"),
                            target_niche=job_context.get("target_niche"),
                            target_location=job_context.get("target_location"),
                            target_language=job_context.get("target_language"),
                            user_service_offers=job_context.get("user_service_offers"),
                            user_service_constraints=job_context.get("user_service_constraints"),
                            user_target_offer_focus=job_context.get("user_target_offer_focus"),
                            target_budget_signals=job_context.get("target_budget_signals"),
                            planner_output=refined_plan,
                            ai_dork_queries=refined_plan.get("optimal_dork_queries"),
                            ai_negative_terms=refined_plan.get("dynamic_negative_terms"),
                            max_queries=_resolve_iteration_query_limit(
                                iteration_index=refinement_count + 1,
                                max_candidates_to_process=max_candidates_to_process,
                                target_accepted_results=target_accepted_results,
                            ),
                            iteration_index=refinement_count + 1,
                        )
                        refined_batches = _filter_new_queries(refined_query_plan["batches"], seen_queries=seen_queries)
                        if refined_batches:
                            refined_query_context_map = _select_query_context_map(
                                refined_batches,
                                query_context_map=refined_query_plan["query_context_map"],
                            )
                            appended_queries = _flatten_query_batches(refined_batches)
                            query_batches, next_discovery_batch_index = _prepend_query_batches(
                                existing_batches=query_batches,
                                next_batch_index=next_discovery_batch_index,
                                new_batches=refined_batches,
                            )
                            query_context_map.update(refined_query_context_map)
                            refinement_count += 1
                            last_refinement_reason = trigger_reason
                            accepted_since_last_refinement = 0
                            await _append_discovery_iteration(
                                db,
                                job_id=job_id,
                                iteration_index=refinement_count,
                                phase="refinement",
                                trigger_reason=trigger_reason or "high_noise_window",
                                input_context_json=iteration_memory,
                                planner_output_json=refined_plan,
                                executed_queries_json=appended_queries,
                                batch_stats_json=window_stats,
                                excluded_reason_counts_json=window_excluded_reason_counts or {},
                                sample_results_json=(query_reports_window[:6] or false_positive_samples or accepted_samples),
                            )
                            await _append_job_log(
                                db,
                                job_id,
                                "INFO",
                                "Discovery refinado con DeepSeek",
                                source_name="discovery",
                                context_json={
                                    "iteration_index": refinement_count,
                                    "trigger_reason": trigger_reason,
                                    "refinement_goal": refined_plan.get("refinement_goal"),
                                    "queries": appended_queries,
                                    "planned_query_count": len(appended_queries),
                                    "window_stats": window_stats,
                                    "search_evidence_window": search_evidence_window,
                                    "top_rejection_reasons": top_rejection_reasons,
                                    "next_segments_to_try": refined_plan.get("next_segments_to_try"),
                                    "segments_to_pause": refined_plan.get("segments_to_pause"),
                                },
                            )
                            await db.commit()
                            processed_window = []
                            query_reports_window = []
                            window_excluded_reason_counts = {}
                        elif not candidate_queue and next_discovery_batch_index >= len(query_batches):
                            stopped_reason = "refinement_limit_reached" if refinement_count >= max_query_refinements else "discovery_exhausted"
                            break
                    elif should_refine and refinement_count >= max_query_refinements and not candidate_queue:
                        stopped_reason = "refinement_limit_reached"
                        break

                if stopped_reason == "target_reached":
                    break

            if not stopped_reason:
                stopped_reason = determine_capture_stop_reason(
                    accepted_count=accepted_results,
                    target_accepted_results=target_accepted_results,
                    processed_count=total_processed,
                    candidate_cap=max_candidates_to_process,
                    discovered_candidates=total_found,
                    exhaustive_candidate_scan=exhaustive_candidate_scan,
                )

            job.status = "completed"
            job.finished_at = _utcnow()
            _apply_job_runtime_totals(
                job,
                total_found=total_found,
                total_processed=total_processed,
                total_saved=total_saved,
                total_failed=total_failed,
                total_skipped=total_skipped,
            )
            await _append_job_log(
                db,
                job_id,
                "INFO",
                "Job finalizado",
                source_name="worker",
                context_json={
                    "total_found": total_found,
                    "total_processed": total_processed,
                    "total_saved": total_saved,
                    "total_failed": total_failed,
                    "total_skipped": total_skipped,
                    "target_accepted_results": target_accepted_results,
                    "accepted_results": accepted_results,
                    "max_candidates_to_process": max_candidates_to_process,
                    "stopped_reason": stopped_reason,
                    "adaptive_enabled": adaptive_discovery,
                    "refinement_count": refinement_count,
                    "last_refinement_reason": last_refinement_reason,
                    "accepted_since_last_refinement": accepted_since_last_refinement,
                    "queries_executed_count": len(executed_queries_history),
                    "unique_queries_generated_count": len({query.lower() for query in executed_queries_history}),
                    "ai_attempts": ai_attempts,
                    "ai_successes": ai_successes,
                    "ai_fallbacks": ai_fallbacks,
                    "ai_fallback_ratio": round((ai_fallbacks / ai_attempts), 4) if ai_attempts else 0.0,
                    "ai_fallback_reasons": ai_fallback_reasons,
                    "ai_prompt_tokens": ai_prompt_tokens,
                    "ai_completion_tokens": ai_completion_tokens,
                    "ai_total_tokens": ai_total_tokens,
                    "ai_total_latency_ms": ai_total_latency_ms,
                    "ai_average_latency_ms": round((ai_total_latency_ms / ai_attempts), 2) if ai_attempts else 0.0,
                    "ai_estimated_cost_usd": round(ai_estimated_cost_usd, 8) if ai_cost_samples else None,
                },
            )
            await db.commit()
            
            logger.info(f"Worker finalizado para Job {job_id} | Insertados: {total_saved}")
            
        except Exception as e:
            logger.exception("Falla total en Worker del Job %s", job_id)
            await db.rollback()
            job = await db.get(ScrapingJob, job_id)
            if job:
                job.status = "failed"
                job.finished_at = _utcnow()
                job.error_message = str(e)
                await _append_job_log(
                    db,
                    job_id,
                    "ERROR",
                    "Falla total del worker",
                    source_name="worker",
                    context_json={"error": str(e)},
                )
                await db.commit()


@router.post("/scrape", response_model=JobResponse, response_model_exclude_none=True, status_code=202)
async def create_scraping_job(
    payload: JobCreateRequest, 
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Recibe la intención de búsqueda desde NestJS.
    Si trae `search_query` y NO trae `urls`, buscará en DDG automáticamente.
    Guarda el Job con PENDING y delega el scraping a una BackgroundTask.
    """
    
    # 0. Lógica de "Buscador Automático" vs "URLs Directas"
    capture_targets = resolve_capture_targets(
        max_results_legacy=payload.max_results,
        target_accepted_results=payload.target_accepted_results,
        max_candidates_to_process=payload.max_candidates_to_process,
        seed_urls_count=len(payload.urls or []),
    )
    exhaustive_candidate_scan = bool(
        payload.max_candidates_to_process is not None
        and capture_targets["max_candidates_to_process"] > capture_targets["target_accepted_results"]
    )
    final_urls = [
        SearchDiscoveryEntry(url=str(u), position=index, discovery_confidence="high")
        for index, u in enumerate((payload.urls or [])[: capture_targets["max_candidates_to_process"]], start=1)
    ]
    effective_target_location = resolve_discovery_target_location(
        search_query=payload.search_query,
        target_location=payload.target_location,
        target_niche=payload.target_niche,
    )
    adaptive_discovery = bool(payload.adaptive_discovery and payload.search_query and not payload.urls)
    requested_refinement_window = int(payload.adaptive_refinement_every_processed or 0)
    adaptive_refinement_every_processed = (
        _resolve_adaptive_refinement_window(capture_targets["max_candidates_to_process"])
        if requested_refinement_window in {0, DEFAULT_ADAPTIVE_REFINEMENT_WINDOW}
        else requested_refinement_window
    )
    max_query_refinements = (
        int(payload.max_query_refinements)
        if payload.max_query_refinements is not None
        else _compute_default_max_query_refinements(capture_targets["max_candidates_to_process"])
    )
    ai_search_plan: dict[str, Any] = {}
    discovery_query_plan: dict[str, Any] = {
        "batches": [],
        "query_context_map": {},
        "queries": [],
        "family_distribution": {},
    }
    discovery_query_batches: list[list[str]] = []
    discovery_query_context_map: dict[str, dict[str, Any]] = {}
    canonical_queries: list[str] = []
    next_discovery_batch_index = 0

    if final_urls:
        discovery_result = SearchDiscoveryResult(
            entries=final_urls,
            source_type=normalize_source_type("seed_url") or "seed_url",
            discovery_method=normalize_discovery_method("seed_url") or "seed_url",
        )
    elif payload.search_query:
        discovery_result = SearchDiscoveryResult(
            entries=[],
            source_type="duckduckgo_search",
            discovery_method="search_query",
            warning_message=None,
            queries=[],
            excluded_results=[],
            provider_name=None,
            provider_status="queued",
            failure_reason=None,
        )
    else:
        raise HTTPException(
            status_code=400,
            detail="No enviaste ni 'urls' ni 'search_query'.",
        )
    
    # Armar la entidad en BD mapeando los atributos de Pydantic al modelo de SQLAlchemy
    new_job = ScrapingJob(
        status="pending",
        user_profession=payload.user_profession,
        user_technologies=payload.user_technologies,
        user_value_proposition=payload.user_value_proposition,
        user_past_successes=payload.user_past_successes,
        user_roi_metrics=payload.user_roi_metrics,
        target_niche=payload.target_niche,
        target_location=effective_target_location,
        target_language=payload.target_language,
        target_company_size=payload.target_company_size,
        target_pain_points=payload.target_pain_points,
        target_budget_signals=payload.target_budget_signals,
        source_type=normalize_source_type(
            discovery_result.source_type or ("seed_url" if final_urls else "duckduckgo_search")
        ),
        filters_json={
            "max_results": payload.max_results,
            "target_accepted_results": capture_targets["target_accepted_results"],
            "max_candidates_to_process": capture_targets["max_candidates_to_process"],
            "exhaustive_candidate_scan": exhaustive_candidate_scan,
            "adaptive_discovery": adaptive_discovery,
            "adaptive_refinement_every_processed": adaptive_refinement_every_processed,
            "max_query_refinements": max_query_refinements,
            "discovery_profile": {
                "user_service_offers": payload.user_service_offers,
                "user_service_constraints": payload.user_service_constraints,
                "user_target_offer_focus": payload.user_target_offer_focus,
                "user_ticket_size": payload.user_ticket_size,
            },
        },
    )
    
    db.add(new_job)
    await db.commit()
    await db.refresh(new_job)
    if adaptive_discovery and normalize_discovery_method(discovery_result.discovery_method) == "search_query" and final_urls:
        await _append_discovery_iteration(
            db,
            job_id=new_job.id,
            iteration_index=0,
            phase="initial",
            trigger_reason="initial_plan",
            input_context_json={
                "search_query": payload.search_query,
                "target_niche": payload.target_niche,
                "target_location": effective_target_location,
                "target_language": payload.target_language,
                "target_budget_signals": payload.target_budget_signals,
                "query_plan_family_distribution": discovery_query_plan.get("family_distribution"),
            },
            planner_output_json=ai_search_plan,
            executed_queries_json=discovery_result.queries or canonical_queries[:10],
            batch_stats_json={
                "selected_candidates_count": len(final_urls),
                "excluded_results_count": len(discovery_result.excluded_results),
                "query_plan_family_distribution": discovery_query_plan.get("family_distribution"),
            },
            excluded_reason_counts_json=_summarize_excluded_reason_counts(discovery_result.excluded_results),
            sample_results_json=[_serialize_discovery_entry(entry) for entry in final_urls[:8]],
        )
        await db.commit()
    await _append_job_log(
        db,
        new_job.id,
        "INFO",
        "Job creado y encolado",
        source_name="api",
        context_json={
            "search_query": payload.search_query,
            "urls_count": len(final_urls),
            "discovery_queries": discovery_result.queries or canonical_queries,
            "query_plan_family_distribution": discovery_query_plan.get("family_distribution"),
            "discovery_method": normalize_discovery_method(discovery_result.discovery_method),
            "source_type": normalize_source_type(discovery_result.source_type),
            "provider_name": discovery_result.provider_name,
            "provider_status": discovery_result.provider_status,
            "provider_failure_reason": discovery_result.failure_reason,
            "warning_message": discovery_result.warning_message,
            "excluded_results_count": len(discovery_result.excluded_results),
            "excluded_reason_counts": _summarize_excluded_reason_counts(discovery_result.excluded_results),
            "excluded_results_preview": discovery_result.excluded_results[:20],
            "selected_candidates_preview": [
                {
                    "url": entry.url,
                    "query": entry.query,
                    "position": entry.position,
                    "title": entry.title,
                    "discovery_confidence": entry.discovery_confidence,
                    "business_likeness_score": entry.business_likeness_score,
                    "website_result_score": entry.website_result_score,
                    "social_profile_score": entry.social_profile_score,
                    "result_kind": entry.result_kind,
                    "discovery_reasons": entry.discovery_reasons,
                    "seed_source_url": entry.seed_source_url,
                    "seed_source_type": entry.seed_source_type,
                    "query_context": entry.query_context,
                }
                for entry in final_urls[:10]
            ],
            "target_accepted_results": capture_targets["target_accepted_results"],
            "max_candidates_to_process": capture_targets["max_candidates_to_process"],
        },
    )
    await db.commit()
    
    job_context = _build_job_context(
        new_job,
        search_query=payload.search_query,
        discovery_method=discovery_result.discovery_method,
        source_type=discovery_result.source_type,
        provider_name=discovery_result.provider_name,
        search_warning=discovery_result.warning_message,
    )
    job_context["discovery_queries"] = discovery_result.queries or canonical_queries
    job_context["discovery_query_batches"] = (
        discovery_query_batches
        if normalize_discovery_method(discovery_result.discovery_method) == "search_query"
        else []
    )
    job_context["discovery_query_context_map"] = (
        discovery_query_context_map
        if normalize_discovery_method(discovery_result.discovery_method) == "search_query"
        else {}
    )
    job_context["next_discovery_batch_index"] = next_discovery_batch_index
    job_context["target_entity_hints"] = ai_search_plan.get("target_entity_hints", [])
    job_context["exclusion_entity_hints"] = ai_search_plan.get("exclusion_entity_hints", [])
    job_context["refinement_goal"] = ai_search_plan.get("refinement_goal")
    job_context["exhaustive_candidate_scan"] = exhaustive_candidate_scan
    job_context["adaptive_discovery"] = adaptive_discovery
    job_context["adaptive_refinement_every_processed"] = adaptive_refinement_every_processed
    job_context["max_query_refinements"] = max_query_refinements
    job_context["candidate_batch_size"] = resolve_candidate_batch_size(
        target_accepted_results=capture_targets["target_accepted_results"],
        candidate_cap=capture_targets["max_candidates_to_process"],
    )
    
    # Encolar la tarea en FastAPI usando las URLs finales descubiertas
    background_tasks.add_task(
        background_scraping_worker, 
        job_id=new_job.id, 
        urls=final_urls,
        job_context=job_context,
    )
    
    return JobResponse(
        job_id=new_job.id,
        status=new_job.status,
        message=(
            (
                f"Trabajo encolado. Objetivo: {capture_targets['target_accepted_results']} aceptados; "
                f"candidatos seed: {len(final_urls)}."
            )
            if final_urls
            else (
                f"Trabajo encolado. Objetivo: {capture_targets['target_accepted_results']} aceptados; "
                "discovery inicial se ejecutara en background."
            )
        ),
        source_type=normalize_source_type(new_job.source_type),
        created_at=new_job.created_at,
        updated_at=new_job.updated_at,
        total_found=len(final_urls),
    )

@router.get("/metrics/operational", response_model=JobsOperationalMetricsResponse)
async def get_operational_metrics(
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ScrapingJob)
        .order_by(desc(ScrapingJob.created_at))
        .limit(limit)
    )
    jobs = list(result.scalars().all())

    summaries: list[tuple[ScrapingJob, JobCaptureSummary, JobOperationalSummary]] = []
    for job in jobs:
        capture_summary = await _get_job_capture_summary(db, job)
        operational_summary = await _get_job_operational_summary(db, job, capture_summary)
        summaries.append((job, capture_summary, operational_summary))

    return _summarize_operational_metrics(summaries)


@router.get("/metrics/commercial", response_model=JobsCommercialMetricsResponse)
async def get_commercial_metrics(
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ScrapingJob)
        .order_by(desc(ScrapingJob.created_at))
        .limit(limit)
    )
    jobs = list(result.scalars().all())

    summaries: list[tuple[ScrapingJob, JobCommercialSummary]] = []
    for job in jobs:
        commercial_summary = await _get_job_commercial_summary(db, job)
        summaries.append((job, commercial_summary))

    return _summarize_commercial_metrics(summaries)


@router.get("/{job_id}", response_model=JobResponse, response_model_exclude_none=True)
async def get_job_status(job_id: int, db: AsyncSession = Depends(get_db)):
    """Permite saber a NestJS u otro servicio si el Job terminó de scrapear"""
    job = await db.get(ScrapingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado.")
    recent_errors = await _get_recent_job_errors(db, job_id)
    ai_summary = await _get_job_ai_summary(db, job_id)
    quality_summary = await _get_job_quality_summary(db, job_id)
    capture_summary = await _get_job_capture_summary(db, job)
    operational_summary = await _get_job_operational_summary(db, job, capture_summary)
    adaptive_summary = await _get_job_adaptive_summary(db, job)
        
    return JobResponse(
        job_id=job.id,
        status=job.status,
        message=_job_summary_message(job),
        source_type=normalize_source_type(job.source_type),
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        total_found=job.total_found,
        total_processed=job.total_processed,
        total_saved=job.total_saved,
        total_failed=job.total_failed,
        total_skipped=job.total_skipped,
        error_message=job.error_message,
        ai_summary=ai_summary,
        quality_summary=quality_summary,
        capture_summary=capture_summary,
        operational_summary=operational_summary,
        adaptive_summary=adaptive_summary,
        recent_errors=recent_errors,
    )
    
@router.get("/{job_id}/results", response_model=List[ProspectOut])
async def get_job_results(
    job_id: int,
    limit: int = 50,
    offset: int = 0,
    quality: str = Query(default="accepted"),
    db: AsyncSession = Depends(get_db),
):
    """Devuelve la lista paginada de prospectos obtenidos por un Job"""
    job = await db.get(ScrapingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado.")

    allowed_quality_statuses = _parse_results_quality_filter(quality)

    query = (
        select(JobProspect, Prospect)
        .join(Prospect, Prospect.id == JobProspect.prospect_id)
        .where(JobProspect.job_id == job_id, JobProspect.quality_status.in_(allowed_quality_statuses))
        .order_by(JobProspect.rank_position.asc(), JobProspect.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if allowed_quality_statuses == ["accepted"]:
        query = query.where(
            (JobProspect.acceptance_decision.is_(None))
            | (~JobProspect.acceptance_decision.like("rejected_%"))
        )
    result = await db.execute(query)
    rows = result.all()

    serialized_rows: list[ProspectOut] = []
    for job_prospect, prospect in rows:
        surface_resolution = _extract_surface_resolution(prospect.generic_attributes)
        serialized_rows.append(
            ProspectOut(
            id=prospect.id,
            company_name=prospect.company_name,
            domain=prospect.domain,
            canonical_identity=prospect.canonical_identity,
            primary_identity_type=prospect.primary_identity_type,
            primary_identity_url=prospect.primary_identity_url,
            website_url=prospect.website_url,
            source_url=job_prospect.source_url or prospect.source_url,
            source_type=normalize_source_type(job_prospect.source_type),
            discovery_method=normalize_discovery_method(job_prospect.discovery_method),
            search_query_snapshot=job_prospect.search_query_snapshot,
            rank_position=job_prospect.rank_position,
            quality_status=job_prospect.quality_status,
            rejection_reason=job_prospect.rejection_reason,
            acceptance_decision=job_prospect.acceptance_decision,
            email=prospect.email,
            phone=prospect.phone,
            contact_consistency_status=job_prospect.contact_consistency_status or prospect.contact_consistency_status,
            primary_email_confidence=job_prospect.primary_email_confidence or prospect.primary_email_confidence,
            primary_phone_confidence=job_prospect.primary_phone_confidence or prospect.primary_phone_confidence,
            primary_contact_source=job_prospect.primary_contact_source or prospect.primary_contact_source,
            linkedin_url=prospect.linkedin_url,
            instagram_url=prospect.instagram_url,
            tiktok_url=prospect.tiktok_url,
            facebook_url=prospect.facebook_url,
            social_profiles=prospect.social_profiles,
            social_quality=(
                prospect.generic_attributes.get("social_quality")
                if isinstance(prospect.generic_attributes, dict)
                else None
            ),
            entry_surface=surface_resolution.get("entry_surface"),
            identity_surface=surface_resolution.get("identity_surface"),
            contact_surface=surface_resolution.get("contact_surface"),
            offer_surface=surface_resolution.get("offer_surface"),
            identity_resolution_reason=surface_resolution.get("identity_resolution_reason"),
            score=job_prospect.match_score if job_prospect.match_score is not None else prospect.score,
            confidence_level=job_prospect.confidence_level or prospect.confidence_level,
            entity_type_detected=job_prospect.entity_type_detected or prospect.entity_type_detected,
            entity_type_confidence=job_prospect.entity_type_confidence or prospect.entity_type_confidence,
            entity_type_evidence=job_prospect.entity_type_evidence or prospect.entity_type_evidence,
            is_target_entity=(
                job_prospect.is_target_entity
                if job_prospect.is_target_entity is not None
                else prospect.is_target_entity
            ),
            inferred_niche=prospect.inferred_niche,
            taxonomy_top_level=job_prospect.taxonomy_top_level or prospect.taxonomy_top_level,
            taxonomy_business_type=job_prospect.taxonomy_business_type or prospect.taxonomy_business_type,
            inferred_tech_stack=prospect.inferred_tech_stack,
            generic_attributes=prospect.generic_attributes,
            observed_signals=job_prospect.observed_signals or prospect.observed_signals,
            inferred_opportunities=job_prospect.inferred_opportunities or prospect.inferred_opportunities,
            estimated_revenue_signal=prospect.estimated_revenue_signal,
            has_active_ads=prospect.has_active_ads,
            hiring_signals=prospect.hiring_signals,
            description=prospect.description,
            location=prospect.location,
            raw_location_text=prospect.raw_location_text,
            parsed_location=prospect.parsed_location,
            city=prospect.city,
            region=prospect.region,
            country=prospect.country,
            postal_code=prospect.postal_code,
            validated_location=prospect.validated_location,
            location_match_status=prospect.location_match_status,
            location_confidence=prospect.location_confidence,
            detected_language=prospect.detected_language,
            language_match_status=prospect.language_match_status,
            primary_cta=prospect.primary_cta,
            booking_url=prospect.booking_url,
            pricing_page_url=prospect.pricing_page_url,
            category=prospect.category,
        )
        )
    return serialized_rows


@router.get("/{job_id}/discovery-iterations", response_model=JobDiscoveryIterationsResponse, response_model_exclude_none=True)
async def get_job_discovery_iterations(job_id: int, db: AsyncSession = Depends(get_db)):
    job = await db.get(ScrapingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado.")

    result = await db.execute(
        select(JobDiscoveryIteration)
        .where(JobDiscoveryIteration.job_id == job_id)
        .order_by(JobDiscoveryIteration.iteration_index.asc(), JobDiscoveryIteration.created_at.asc())
    )
    iterations = list(result.scalars().all())
    return JobDiscoveryIterationsResponse(
        job_id=job_id,
        total=len(iterations),
        items=[_serialize_discovery_iteration(item) for item in iterations],
    )


@router.get("/{job_id}/logs", response_model=JobLogsResponse, response_model_exclude_none=True)
async def get_job_logs(
    job_id: int,
    limit: int = 50,
    offset: int = 0,
    level: ScrapingLogLevel | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Devuelve logs persistidos del job para debugging operativo."""
    job = await db.get(ScrapingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado.")

    base_filters = [ScrapingLog.job_id == job_id]
    if level:
        base_filters.append(ScrapingLog.level == level)

    total = await db.scalar(
        select(func.count())
        .select_from(ScrapingLog)
        .where(*base_filters)
    )

    result = await db.execute(
        select(ScrapingLog)
        .where(*base_filters)
        .order_by(desc(ScrapingLog.created_at))
        .offset(offset)
        .limit(limit)
    )
    logs = result.scalars().all()

    return JobLogsResponse(
        job_id=job_id,
        total=total or 0,
        limit=limit,
        offset=offset,
        items=[_serialize_job_log(log) for log in logs],
    )
