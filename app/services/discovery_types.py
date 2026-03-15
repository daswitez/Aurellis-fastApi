from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SearchDiscoveryEntry:
    url: str
    query: str | None = None
    position: int | None = None
    title: str | None = None
    snippet: str | None = None
    discovery_confidence: str | None = None
    business_likeness_score: float | None = None
    website_result_score: float | None = None
    social_profile_score: float | None = None
    result_kind: str | None = None
    discovery_reasons: list[str] = field(default_factory=list)
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
    provider_name: str | None = None
    provider_status: str | None = None
    failure_reason: str | None = None

    @property
    def urls(self) -> list[str]:
        return [entry.url for entry in self.entries]
