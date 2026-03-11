from __future__ import annotations

import logging

import httpx

from app.config import get_settings
from app.services.discovery_ranker import clean_text, is_blocked_result, score_business_likeness
from app.services.discovery_types import SearchDiscoveryEntry, SearchDiscoveryResult
from app.services.search_providers.base import SearchProvider

logger = logging.getLogger(__name__)


class BraveSearchProvider(SearchProvider):
    provider_name = "brave_api"
    source_type = "brave_search"

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.BRAVE_SEARCH_API_KEY
        self._base_url = settings.BRAVE_SEARCH_API_BASE_URL.rstrip("/")

    def is_available(self) -> bool:
        return bool(self._api_key)

    async def search(self, queries: list[str], max_results: int = 10) -> SearchDiscoveryResult:
        if not self.is_available():
            return SearchDiscoveryResult(
                entries=[],
                source_type=self.source_type,
                discovery_method="search_query",
                warning_message="Proveedor Brave deshabilitado: falta BRAVE_SEARCH_API_KEY.",
                queries=queries,
                provider_name=self.provider_name,
                provider_status="unavailable",
                failure_reason="missing_api_key",
            )

        entries: list[SearchDiscoveryEntry] = []
        excluded_results: list[dict] = []
        seen_urls: set[str] = set()
        warning_messages: list[str] = []

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self._api_key,
        }

        async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
            for query in queries:
                try:
                    response = await client.get(
                        f"{self._base_url}/web/search",
                        params={"q": query, "count": max_results},
                    )
                    response.raise_for_status()
                    payload = response.json()
                except httpx.HTTPStatusError as exc:
                    warning = f"Brave fallo para '{query}': HTTP {exc.response.status_code}"
                    logger.warning("[Brave] %s", warning)
                    warning_messages.append(warning)
                    continue
                except httpx.HTTPError as exc:
                    warning = f"Brave fallo para '{query}': {exc}"
                    logger.warning("[Brave] %s", warning)
                    warning_messages.append(warning)
                    continue
                except ValueError as exc:
                    warning = f"Brave devolvio JSON invalido para '{query}': {exc}"
                    logger.warning("[Brave] %s", warning)
                    warning_messages.append(warning)
                    continue

                web_results = (((payload or {}).get("web") or {}).get("results") or [])
                for raw_item in web_results:
                    url = str(raw_item.get("url") or "").strip()
                    title = clean_text(raw_item.get("title"))
                    snippet = clean_text(raw_item.get("description"))
                    if not url.startswith("http"):
                        excluded_results.append({"url": url or None, "reason": "invalid_url", "query": query, "title": title, "snippet": snippet})
                        continue

                    blocked_reason = is_blocked_result(url)
                    if blocked_reason:
                        excluded_results.append({"url": url, "reason": blocked_reason, "query": query, "title": title, "snippet": snippet})
                        continue

                    business_score, business_reasons, exclusion_reason = score_business_likeness(url, title, snippet)
                    if exclusion_reason:
                        excluded_results.append(
                            {
                                "url": url,
                                "reason": exclusion_reason,
                                "query": query,
                                "title": title,
                                "snippet": snippet,
                                "business_likeness_score": business_score,
                                "discovery_reasons": business_reasons,
                            }
                        )
                        continue

                    if url in seen_urls:
                        excluded_results.append({"url": url, "reason": "duplicate_url", "query": query, "title": title, "snippet": snippet})
                        continue

                    seen_urls.add(url)
                    lowered_blob = f"{title} {snippet}".lower()
                    discovery_confidence = "medium"
                    if "oficial" in lowered_blob or "official" in lowered_blob or business_score >= 0.45:
                        discovery_confidence = "high"
                    elif business_score <= 0.2:
                        discovery_confidence = "low"

                    entries.append(
                        SearchDiscoveryEntry(
                            url=url,
                            query=query,
                            title=title or None,
                            snippet=snippet or None,
                            discovery_confidence=discovery_confidence,
                            business_likeness_score=business_score,
                            discovery_reasons=business_reasons,
                        )
                    )
                    if len(entries) >= max_results:
                        return SearchDiscoveryResult(
                            entries=entries,
                            source_type=self.source_type,
                            discovery_method="search_query",
                            warning_message="; ".join(warning_messages) if warning_messages else None,
                            queries=queries,
                            excluded_results=excluded_results,
                            provider_name=self.provider_name,
                            provider_status="ok",
                        )

        return SearchDiscoveryResult(
            entries=entries,
            source_type=self.source_type,
            discovery_method="search_query",
            warning_message="; ".join(warning_messages) if warning_messages else None,
            queries=queries,
            excluded_results=excluded_results,
            provider_name=self.provider_name,
            provider_status="ok" if entries else "no_results",
            failure_reason=None if entries else "no_results",
        )
