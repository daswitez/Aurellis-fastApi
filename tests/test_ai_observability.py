import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

if "openai" not in sys.modules:
    openai_stub = types.ModuleType("openai")
    openai_stub.AsyncOpenAI = object
    sys.modules["openai"] = openai_stub

from app.api.jobs import _summarize_ai_usage
from app.scraper.engine import scrape_single_prospect
from app.services.ai_extractor import AIExtractionFallbackError


class AISummaryTestCase(unittest.TestCase):
    def test_summarizes_fallback_ratio_and_reasons(self) -> None:
        summary = _summarize_ai_usage(
            [
                {
                    "ai_trace": {
                        "selected_method": "ai",
                        "prompt_tokens": 100,
                        "completion_tokens": 20,
                        "total_tokens": 120,
                        "latency_ms": 900,
                        "estimated_cost_usd": 0.00002,
                    }
                },
                {
                    "ai_trace": {
                        "selected_method": "heuristic",
                        "fallback_reason": "invalid_schema",
                        "prompt_tokens": 80,
                        "completion_tokens": 10,
                        "total_tokens": 90,
                        "latency_ms": 700,
                        "estimated_cost_usd": 0.00001,
                    }
                },
                {
                    "ai_trace": {
                        "selected_method": "heuristic",
                        "fallback_reason": "provider_error",
                        "latency_ms": 300,
                    }
                },
                {
                    "ai_trace": {
                        "selected_method": "heuristic",
                        "fallback_reason": "invalid_schema",
                        "prompt_tokens": 60,
                        "completion_tokens": 5,
                        "total_tokens": 65,
                        "latency_ms": 500,
                    }
                },
                None,
                {"other": "ignored"},
            ]
        )

        self.assertEqual(summary.attempts, 4)
        self.assertEqual(summary.successes, 1)
        self.assertEqual(summary.fallbacks, 3)
        self.assertEqual(summary.fallback_ratio, 0.75)
        self.assertEqual(summary.fallback_reasons["invalid_schema"], 2)
        self.assertEqual(summary.fallback_reasons["provider_error"], 1)
        self.assertEqual(summary.total_prompt_tokens, 240)
        self.assertEqual(summary.total_completion_tokens, 35)
        self.assertEqual(summary.total_tokens, 275)
        self.assertEqual(summary.total_latency_ms, 2400)
        self.assertEqual(summary.average_latency_ms, 600.0)
        self.assertEqual(summary.estimated_cost_usd, 0.00003)


class AIScrapeObservabilityTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_uses_heuristic_and_attaches_ai_trace_on_fallback(self) -> None:
        metadata = {
            "title": "Dental Home",
            "description": "Clinica dental",
            "emails": [],
            "phones": [],
            "social_links": [],
            "internal_links": [],
            "form_detected": False,
        }
        heuristic_result = {
            "company_name": "Dental Home",
            "category": "Clinica",
            "location": "Madrid",
            "description": "Clinica dental",
            "inferred_tech_stack": ["WordPress"],
            "inferred_niche": "Dental",
            "hiring_signals": False,
            "estimated_revenue_signal": "low",
            "has_active_ads": False,
            "score": 0.0,
            "confidence_level": "low",
            "generic_attributes": {
                "evaluation_method": "Heuristic Code (No LLM)",
                "pain_points_detected": [],
            },
        }

        with patch("app.scraper.engine.fetch_html", new=AsyncMock(return_value="<html></html>")):
            with patch("app.scraper.engine.parse_html_basic", return_value=("x" * 250, metadata)):
                with patch(
                    "app.scraper.engine._crawl_key_pages",
                    new=AsyncMock(return_value=("", metadata, [])),
                ):
                    with patch(
                        "app.scraper.engine.extract_business_entity_ai",
                        new=AsyncMock(
                            side_effect=AIExtractionFallbackError(
                                "invalid_schema",
                                "schema invalido",
                                error_type="invalid_response",
                            )
                        ),
                    ):
                        with patch(
                            "app.scraper.engine.extract_business_entity_heuristic",
                            new=AsyncMock(return_value=heuristic_result),
                        ):
                            result = await scrape_single_prospect(
                                "https://example.com",
                                {"job_id": 9},
                            )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["ai_trace"]["selected_method"], "heuristic")
        self.assertEqual(result["ai_trace"]["fallback_reason"], "invalid_schema")
        self.assertEqual(result["ai_trace"]["error_type"], "invalid_response")
        self.assertEqual(result["generic_attributes"]["fallback_reason"], "invalid_schema")
        self.assertEqual(result["generic_attributes"]["ai_error_type"], "invalid_response")


if __name__ == "__main__":
    unittest.main()
