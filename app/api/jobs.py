import asyncio
import logging
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import JobProspect, Prospect, ScrapingJob, ScrapingLog
from app.api.schemas import (
    JobAISummary,
    JobCaptureSummary,
    JobCommercialSummary,
    JobCreateRequest,
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
from app.scraper.search_engines.ddg_search import SearchDiscoveryEntry, SearchDiscoveryResult, find_prospect_urls_by_queries
from app.services.discovery import (
    build_discovery_query_batches,
    determine_capture_stop_reason,
    resolve_candidate_batch_size,
    resolve_capture_targets,
    resolve_discovery_batch_budget,
)
from app.services.db_upsert import save_scraped_prospect
from app.services.source_metadata import normalize_discovery_method, normalize_source_type

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


def _build_job_context(
    job: ScrapingJob,
    *,
    search_query: str | None,
    discovery_method: str | None,
    source_type: str | None,
    search_warning: str | None,
) -> dict:
    return {
        "job_id": job.id,
        "workspace_id": job.workspace_id,
        "user_profession": job.user_profession,
        "user_technologies": job.user_technologies,
        "user_value_proposition": job.user_value_proposition,
        "user_past_successes": job.user_past_successes,
        "user_roi_metrics": job.user_roi_metrics,
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
        "search_warning": search_warning,
        "target_accepted_results": (job.filters_json or {}).get("target_accepted_results"),
        "max_candidates_to_process": (job.filters_json or {}).get("max_candidates_to_process"),
    }


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


def _summarize_quality_usage(rows: list[tuple[str | None, str | None]]) -> JobQualitySummary:
    accepted = 0
    needs_review = 0
    rejected = 0
    rejection_reasons: dict[str, int] = {}

    for quality_status, rejection_reason in rows:
        if quality_status == "accepted":
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
        select(JobProspect.quality_status, JobProspect.rejection_reason)
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
    quality_summary = _summarize_quality_usage([(quality_status, rejection_reason) for quality_status, rejection_reason, _ in rows])
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
    next_batch_index: int,
    target_accepted_results: int,
    candidate_cap: int,
    remaining_budget: int,
    seen_urls: set[str],
) -> tuple[list[SearchDiscoveryEntry], int, list[str], list[dict], str | None]:
    warnings: list[str] = []
    excluded_results: list[dict] = []
    used_queries: list[str] = []

    while next_batch_index < len(query_batches):
        batch_queries = [query for query in query_batches[next_batch_index] if query]
        next_batch_index += 1
        if not batch_queries:
            continue

        batch_budget = resolve_discovery_batch_budget(
            target_accepted_results=target_accepted_results,
            candidate_cap=candidate_cap,
            remaining_budget=remaining_budget,
        )
        if batch_budget <= 0:
            break

        discovery_result = await find_prospect_urls_by_queries(batch_queries, max_results=batch_budget)
        used_queries.extend(batch_queries)
        excluded_results.extend(discovery_result.excluded_results)
        if discovery_result.warning_message:
            warnings.append(discovery_result.warning_message)

        fresh_entries: list[SearchDiscoveryEntry] = []
        for entry in discovery_result.entries:
            if entry.url in seen_urls:
                excluded_results.append(
                    {
                        "url": entry.url,
                        "reason": "duplicate_url_reopened",
                        "query": entry.query,
                        "title": entry.title,
                        "snippet": entry.snippet,
                        "business_likeness_score": entry.business_likeness_score,
                        "discovery_reasons": entry.discovery_reasons,
                        "seed_source_url": entry.seed_source_url,
                    }
                )
                continue
            seen_urls.add(entry.url)
            fresh_entries.append(entry)

        if fresh_entries:
            return fresh_entries, next_batch_index, used_queries, excluded_results, "; ".join(warnings) if warnings else None

    return [], next_batch_index, used_queries, excluded_results, "; ".join(warnings) if warnings else None


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
            candidate_queue = list(urls)[:max_candidates_to_process]
            query_batches = [batch for batch in (job_context.get("discovery_query_batches") or []) if isinstance(batch, list)]
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
            accepted_results = 0
            stopped_reason: str | None = None

            job.status = "running"
            job.started_at = _utcnow()
            job.finished_at = None
            job.error_message = None
            job.total_found = len(candidate_queue)
            job.total_processed = 0
            job.total_saved = 0
            job.total_failed = 0
            job.total_skipped = 0
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
                    "target_accepted_results": target_accepted_results,
                    "max_candidates_to_process": max_candidates_to_process,
                    "candidate_batch_size": candidate_batch_size,
                    "pending_discovery_batches": max(len(query_batches) - next_discovery_batch_index, 0),
                },
            )
            await db.commit()
            batch_number = 0

            while job.total_processed < max_candidates_to_process:
                if accepted_results >= target_accepted_results:
                    stopped_reason = "target_reached"
                    break

                if not candidate_queue:
                    remaining_budget = max_candidates_to_process - int(job.total_found or 0)
                    if remaining_budget <= 0 or next_discovery_batch_index >= len(query_batches):
                        break

                    new_entries, next_discovery_batch_index, used_queries, excluded_results, warning_message = await _discover_next_candidate_batch(
                        query_batches=query_batches,
                        next_batch_index=next_discovery_batch_index,
                        target_accepted_results=target_accepted_results,
                        candidate_cap=max_candidates_to_process,
                        remaining_budget=remaining_budget,
                        seen_urls=seen_candidate_urls,
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
                                "excluded_reason_counts": _summarize_excluded_reason_counts(excluded_results),
                                "excluded_results_preview": excluded_results[:20],
                            },
                        )

                    if not new_entries:
                        await db.commit()
                        break

                    for index, entry in enumerate(new_entries, start=int(job.total_found or 0) + 1):
                        entry.position = index
                    candidate_queue.extend(new_entries)
                    job.total_found += len(new_entries)
                    await _append_job_log(
                        db,
                        job_id,
                        "INFO",
                        "Discovery reabierto por captura insuficiente",
                        source_name="discovery",
                        context_json={
                            "queries": used_queries,
                            "new_candidates": len(new_entries),
                            "total_found": job.total_found,
                            "accepted_results_so_far": accepted_results,
                        },
                    )
                    await db.commit()

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
                            "position": entry.position or (int(job.total_processed or 0) + 1),
                            "title": entry.title,
                            "snippet": entry.snippet,
                            "discovery_confidence": entry.discovery_confidence,
                            "business_likeness_score": entry.business_likeness_score,
                            "discovery_reasons": entry.discovery_reasons,
                            "seed_source_url": entry.seed_source_url,
                            "seed_source_type": entry.seed_source_type,
                        }
                    elif isinstance(entry, dict):
                        discovery_entry = dict(entry)
                    else:
                        discovery_entry = {"url": str(entry)}

                    rank_position = int(discovery_entry.get("position") or (int(job.total_processed or 0) + 1))
                    url = str(discovery_entry.get("url"))
                    job.total_processed += 1
                    try:
                        prospect_dict = await scrape_single_prospect(
                            url,
                            {**job_context, "discovery_entry": discovery_entry},
                        )

                        if not prospect_dict:
                            job.total_skipped += 1
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
                            job.total_saved += 1
                            if prospect_dict.get("acceptance_decision") == "accepted_target":
                                accepted_results += 1
                            await _append_job_log(
                                db,
                                job_id,
                                "INFO",
                                "Prospecto persistido",
                                source_name="worker",
                                context_json={
                                    "url": url,
                                    "domain": saved_prospect.domain,
                                    "rank_position": rank_position,
                                    "quality_status": prospect_dict.get("quality_status"),
                                    "acceptance_decision": prospect_dict.get("acceptance_decision"),
                                    "rejection_reason": prospect_dict.get("rejection_reason"),
                                    "accepted_results_so_far": accepted_results,
                                },
                            )
                        else:
                            job.total_failed += 1
                            await _append_job_log(
                                db,
                                job_id,
                                "ERROR",
                                "No se pudo persistir el prospecto",
                                source_name="worker",
                                context_json={"url": url, "rank_position": rank_position},
                            )
                        await db.commit()

                        if accepted_results >= target_accepted_results:
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
                                    "processed_candidates": job.total_processed,
                                    "batch_number": batch_number,
                                },
                            )
                            await db.commit()
                            break
                    except Exception as e:
                        job.total_failed += 1
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
                        await db.commit()

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

                if stopped_reason == "target_reached":
                    break

            if not stopped_reason:
                stopped_reason = determine_capture_stop_reason(
                    accepted_count=accepted_results,
                    target_accepted_results=target_accepted_results,
                    processed_count=job.total_processed,
                    candidate_cap=max_candidates_to_process,
                    discovered_candidates=int(job.total_found or 0),
                )

            job.status = "completed"
            job.finished_at = _utcnow()
            await _append_job_log(
                db,
                job_id,
                "INFO",
                "Job finalizado",
                source_name="worker",
                context_json={
                    "total_found": job.total_found,
                    "total_processed": job.total_processed,
                    "total_saved": job.total_saved,
                    "total_failed": job.total_failed,
                    "total_skipped": job.total_skipped,
                    "target_accepted_results": target_accepted_results,
                    "accepted_results": accepted_results,
                    "max_candidates_to_process": max_candidates_to_process,
                    "stopped_reason": stopped_reason,
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
            
            logger.info(f"Worker finalizado para Job {job_id} | Insertados: {job.total_saved}")
            
        except Exception as e:
            logger.error(f"Falla total en Worker del Job {job_id}: {str(e)}")
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
    final_urls = [
        SearchDiscoveryEntry(url=str(u), position=index, discovery_confidence="high")
        for index, u in enumerate((payload.urls or [])[: capture_targets["max_candidates_to_process"]], start=1)
    ]
    discovery_result = SearchDiscoveryResult(
        entries=final_urls,
        source_type=normalize_source_type("seed_url") or "seed_url",
        discovery_method=normalize_discovery_method("seed_url") or "seed_url",
    )
    
    discovery_query_batches = build_discovery_query_batches(
        search_query=payload.search_query,
        target_niche=payload.target_niche,
        target_location=payload.target_location,
        target_language=payload.target_language,
    )
    canonical_queries = _flatten_query_batches(discovery_query_batches)
    next_discovery_batch_index = 0

    if not final_urls and discovery_query_batches:
        # Modo Búsqueda: Descubrir una tanda inicial antes de guardar el Job.
        logger.info("Modo Buscador Activado para query batches: %s", discovery_query_batches)
        warning_messages: list[str] = []
        excluded_results: list[dict] = []
        executed_queries: list[str] = []
        initial_discovery_budget = resolve_discovery_batch_budget(
            target_accepted_results=capture_targets["target_accepted_results"],
            candidate_cap=capture_targets["max_candidates_to_process"],
            remaining_budget=capture_targets["max_candidates_to_process"],
        )

        for batch_index, query_batch in enumerate(discovery_query_batches, start=1):
            batch_result = await find_prospect_urls_by_queries(
                query_batch,
                max_results=initial_discovery_budget,
            )
            executed_queries.extend(query_batch)
            excluded_results.extend(batch_result.excluded_results)
            if batch_result.warning_message:
                warning_messages.append(batch_result.warning_message)

            if batch_result.entries:
                final_urls = batch_result.entries
                next_discovery_batch_index = batch_index
                discovery_result = SearchDiscoveryResult(
                    entries=final_urls,
                    source_type=batch_result.source_type,
                    discovery_method=batch_result.discovery_method,
                    warning_message="; ".join(warning_messages) if warning_messages else None,
                    queries=executed_queries,
                    excluded_results=excluded_results,
                )
                break
        else:
            no_results_message = (
                "; ".join(warning_messages)
                if warning_messages
                else f"DDG no devolvio resultados para queries: {canonical_queries!r}."
            )
            discovery_result = SearchDiscoveryResult(
                entries=[],
                source_type="duckduckgo_search",
                discovery_method="search_query",
                warning_message=no_results_message,
                queries=executed_queries or canonical_queries,
                excluded_results=excluded_results,
            )
        final_urls = discovery_result.entries
        
    if not final_urls:
        raise HTTPException(
            status_code=400,
            detail=discovery_result.warning_message
            or "No se encontraron URLs con ese query, o no enviaste ni 'urls' ni 'search_query'.",
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
        target_location=payload.target_location,
        target_language=payload.target_language,
        target_company_size=payload.target_company_size,
        target_pain_points=payload.target_pain_points,
        target_budget_signals=payload.target_budget_signals,
        source_type=normalize_source_type(discovery_result.source_type),
        filters_json={
            "max_results": payload.max_results,
            "target_accepted_results": capture_targets["target_accepted_results"],
            "max_candidates_to_process": capture_targets["max_candidates_to_process"],
        },
    )
    
    db.add(new_job)
    await db.commit()
    await db.refresh(new_job)
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
            "discovery_method": normalize_discovery_method(discovery_result.discovery_method),
            "source_type": normalize_source_type(discovery_result.source_type),
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
                    "discovery_reasons": entry.discovery_reasons,
                    "seed_source_url": entry.seed_source_url,
                    "seed_source_type": entry.seed_source_type,
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
        search_warning=discovery_result.warning_message,
    )
    job_context["discovery_queries"] = discovery_result.queries or canonical_queries
    job_context["discovery_query_batches"] = (
        discovery_query_batches
        if normalize_discovery_method(discovery_result.discovery_method) == "search_query"
        else []
    )
    job_context["next_discovery_batch_index"] = next_discovery_batch_index
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
            f"Trabajo encolado. Objetivo: {capture_targets['target_accepted_results']} aceptados; "
            f"candidatos a procesar: {len(final_urls)}."
            if not discovery_result.warning_message
            else (
                f"Trabajo encolado. Objetivo: {capture_targets['target_accepted_results']} aceptados; "
                f"candidatos a procesar: {len(final_urls)}. Aviso: {discovery_result.warning_message}"
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
    result = await db.execute(query)
    rows = result.all()

    return [
        ProspectOut(
            id=prospect.id,
            company_name=prospect.company_name,
            domain=prospect.domain,
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
            facebook_url=prospect.facebook_url,
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
        for job_prospect, prospect in rows
    ]


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
