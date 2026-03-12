from __future__ import annotations

from abc import ABC, abstractmethod

from app.services.discovery_types import SearchDiscoveryResult


class SearchProvider(ABC):
    provider_name = "unknown"
    source_type = "duckduckgo_search"

    @abstractmethod
    async def search(self, queries: list[str], allow_social_profiles: bool = False, max_results: int = 10) -> SearchDiscoveryResult:
        raise NotImplementedError

    def is_available(self) -> bool:
        return True
