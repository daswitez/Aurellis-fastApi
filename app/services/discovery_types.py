from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SearchDiscoveryEntry:
    url: str
    query: str | None = None
    query_context: dict[str, Any] = field(default_factory=dict)
    position: int | None = None
    title: str | None = None
    snippet: str | None = None
    discovery_confidence: str | None = None
    business_likeness_score: float | None = None
    website_result_score: float | None = None
    social_profile_score: float | None = None
    result_kind: str | None = None
    discovery_reasons: list[str] = field(default_factory=list)
    candidate_screening_stage: str | None = None
    candidate_screening_reason: str | None = None
    quick_ai_verdict: str | None = None
    quick_ai_confidence: str | None = None
    quick_ai_reason_code: str | None = None
    rescued_by_quick_ai: bool = False
    seed_source_url: str | None = None
    seed_source_type: str | None = None


@dataclass
class SearchDiscoveryResult:
    entries: list[SearchDiscoveryEntry]
    source_type: str
    discovery_method: str
    warning_message: str | None = None
    queries: list[str] = field(default_factory=list)
    excluded_results: list[dict[str, Any]] = field(default_factory=list)
    query_reports: list[dict[str, Any]] = field(default_factory=list)
    provider_name: str | None = None
    provider_status: str | None = None
    failure_reason: str | None = None

    @property
    def urls(self) -> list[str]:
        return [entry.url for entry in self.entries]
