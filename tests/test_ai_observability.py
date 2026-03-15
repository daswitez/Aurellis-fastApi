import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

if "openai" not in sys.modules:
    openai_stub = types.ModuleType("openai")
    openai_stub.AsyncOpenAI = object
    sys.modules["openai"] = openai_stub

from app.api.jobs import _parse_results_quality_filter, _summarize_ai_usage, _summarize_capture_usage, _summarize_quality_usage
from app.scraper.engine import scrape_single_prospect
from app.services.ai_extractor import AIExtractionFallbackError


class AISummaryTestCase(unittest.TestCase):
    def test_summarizes_fallback_ratio_and_reasons(self) -> None:
        summary = _summarize_ai_usage(
            [
                {
                    "ai_trace": {
                        "status": "success",
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
                        "status": "fallback",
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
                        "status": "fallback",
                        "selected_method": "heuristic",
                        "fallback_reason": "provider_error",
                        "latency_ms": 300,
                    }
                },
                {
                    "ai_trace": {
                        "status": "fallback",
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
                {"ai_trace": {"status": "skipped", "selected_method": "heuristic", "fallback_reason": "quality_rejected"}},
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

    def test_summarizes_quality_distribution(self) -> None:
        summary = _summarize_quality_usage(
            [
                ("accepted", None),
                ("rejected", "geo_mismatch"),
                ("rejected", "geo_mismatch"),
                ("needs_review", "geo_unknown"),
                ("rejected", "low_contact_quality"),
                (None, None),
            ]
        )

        self.assertEqual(summary.accepted, 1)
        self.assertEqual(summary.needs_review, 1)
        self.assertEqual(summary.rejected, 3)
        self.assertEqual(summary.rejection_reasons["geo_mismatch"], 2)
        self.assertEqual(summary.rejection_reasons["geo_unknown"], 1)
        self.assertEqual(summary.rejection_reasons["low_contact_quality"], 1)

    def test_parses_results_quality_filter(self) -> None:
        self.assertEqual(_parse_results_quality_filter(None), ["accepted"])
        self.assertEqual(_parse_results_quality_filter("accepted,needs_review"), ["accepted", "needs_review"])
        self.assertEqual(_parse_results_quality_filter("all"), ["accepted", "needs_review", "rejected"])

    def test_rejects_partially_invalid_results_quality_filter(self) -> None:
        with self.assertRaises(HTTPException):
            _parse_results_quality_filter("accepted,foo")

    def test_summarizes_capture_distribution(self) -> None:
        summary = _summarize_capture_usage(
            rows=[
                ("accepted", None, "accepted_target"),
                ("needs_review", "geo_unknown", "rejected_low_confidence"),
                ("rejected", "geo_mismatch", "rejected_low_confidence"),
                ("rejected", "low_contact_quality", "rejected_low_confidence"),
            ],
            total_processed=6,
            total_found=8,
            total_failed=1,
            total_skipped=1,
            target_accepted_results=3,
            max_candidates_to_process=12,
            stopped_reason="candidate_cap_reached",
        )

        self.assertEqual(summary.accepted_count, 1)
        self.assertEqual(summary.needs_review_count, 1)
        self.assertEqual(summary.rejected_count, 2)
        self.assertEqual(summary.candidates_processed, 6)
        self.assertEqual(summary.candidates_discovered, 8)
        self.assertEqual(summary.acceptance_rate, 0.1667)
        self.assertEqual(summary.candidate_dropoff_by_reason["rejected_low_confidence"], 3)
        self.assertEqual(summary.candidate_dropoff_by_reason["processing_failed"], 1)
        self.assertEqual(summary.candidate_dropoff_by_reason["processing_skipped"], 1)


class AIScrapeObservabilityTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_scrape_resolves_identity_surfaces_from_internal_page_entry(self) -> None:
        metadata = {
            "title": "Brand Studio | Caso de exito",
            "description": "Agencia creativa para ecommerce y marcas personales",
            "emails": ["hola@brandstudio.com"],
            "phones": [],
            "social_links": [],
            "social_profiles": [],
            "internal_links": [
                "https://brandstudio.com/contacto",
                "https://brandstudio.com/servicios",
                "https://brandstudio.com/precios",
            ],
            "external_links": [],
            "form_detected": True,
            "contact_channels": [
                {"type": "contact_form", "value": "https://brandstudio.com/contacto"},
                {"type": "email", "value": "hola@brandstudio.com"},
            ],
            "addresses": [],
            "map_links": [],
            "cta_candidates": ["contact_form"],
            "primary_cta": "contact_form",
            "pricing_page_url": "https://brandstudio.com/precios",
            "service_page_url": "https://brandstudio.com/servicios",
            "structured_data_evidence": [],
            "structured_data": [],
        }
        heuristic_result = {
            "company_name": "Brand Studio",
            "category": "Agencia",
            "description": "Agencia creativa",
            "inferred_tech_stack": ["WordPress"],
            "inferred_niche": "Agencias",
            "hiring_signals": False,
            "estimated_revenue_signal": "medium",
            "has_active_ads": False,
            "score": 0.66,
            "confidence_level": "medium",
            "fit_summary": "Buena identidad comercial y contacto visible.",
            "heuristic_trace": {"component_scores": {"business_identity": 0.8}, "signals": {}},
            "generic_attributes": {
                "evaluation_method": "Heuristic Code (No LLM)",
                "observed_signals": [],
                "inferred_opportunities": [],
                "pain_points_detected": [],
            },
            "observed_signals": [],
            "inferred_opportunities": [],
        }

        with patch("app.scraper.engine.fetch_html", new=AsyncMock(return_value="<html></html>")):
            with patch("app.scraper.engine.parse_html_basic", return_value=("x" * 250, metadata)):
                with patch(
                    "app.scraper.engine._crawl_key_pages",
                    new=AsyncMock(return_value=("", metadata, [])),
                ):
                    with patch(
                        "app.scraper.engine.extract_business_entity_heuristic",
                        new=AsyncMock(return_value=heuristic_result),
                    ):
                        with patch("app.scraper.engine.should_call_ai", return_value=(False, "unit_test")):
                            result = await scrape_single_prospect(
                                "https://brandstudio.com/blog/caso-de-exito",
                                {"job_id": 9, "target_language": "es"},
                            )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["canonical_identity"], "brandstudio.com")
        self.assertEqual(result["primary_identity_url"], "https://brandstudio.com/")
        self.assertEqual(result["website_url"], "https://brandstudio.com/")
        self.assertEqual(
            result["generic_attributes"]["surface_resolution"]["entry_surface"]["surface_type"],
            "website_page",
        )
        self.assertEqual(
            result["generic_attributes"]["surface_resolution"]["identity_surface"]["surface_type"],
            "website_home",
        )

    async def test_blends_ai_score_with_heuristic_baseline_on_success(self) -> None:
        metadata = {
            "title": "Dental Home",
            "description": "Clinica dental",
            "emails": ["hola@example.com"],
            "phones": [],
            "social_links": [],
            "internal_links": [],
            "form_detected": True,
            "contact_channels": [
                {"type": "contact_form", "value": "https://example.com/contacto"},
                {"type": "email", "value": "hola@example.com"},
            ],
            "addresses": [],
            "map_links": [],
            "cta_candidates": [],
            "structured_data_evidence": [],
            "structured_data": [],
        }
        heuristic_result = {
            "company_name": "Dental Home",
            "category": "Clinica",
            "location": "Madrid",
            "description": "Clinica dental",
            "inferred_tech_stack": ["WordPress"],
            "inferred_niche": "Dental",
            "hiring_signals": False,
            "estimated_revenue_signal": "medium",
            "has_active_ads": False,
            "score": 0.7,
            "confidence_level": "medium",
            "fit_summary": "Fit heuristico fuerte; destacan stack, contacto.",
            "heuristic_trace": {"component_scores": {"stack_fit": 0.8}, "signals": {}},
            "generic_attributes": {
                "evaluation_method": "Heuristic Code (No LLM)",
                "observed_signals": [],
                "inferred_opportunities": [],
                "pain_points_detected": [],
            },
            "observed_signals": [],
            "inferred_opportunities": [],
        }
        ai_result = {
            "inferred_tech_stack": ["WordPress", "Google Analytics"],
            "inferred_niche": "Dental",
            "generic_attributes": {
                "evaluation_method": "DeepSeek API (deepseek_prospect_v3)",
                "observed_signals": [],
                "inferred_opportunities": [],
                "pain_points_detected": [],
            },
            "observed_signals": [],
            "inferred_opportunities": [],
            "hiring_signals": False,
            "estimated_revenue_signal": "high",
            "score": 0.8,
            "confidence_level": "high",
            "_ai_metrics": {},
        }

        with patch("app.scraper.engine.fetch_html", new=AsyncMock(return_value="<html></html>")):
            with patch("app.scraper.engine.parse_html_basic", return_value=("x" * 250, metadata)):
                with patch(
                    "app.scraper.engine._crawl_key_pages",
                    new=AsyncMock(return_value=("", metadata, [])),
                ):
                    with patch(
                        "app.scraper.engine.extract_business_entity_heuristic",
                        new=AsyncMock(return_value=heuristic_result),
                    ):
                        with patch(
                            "app.scraper.engine.extract_business_entity_ai",
                            new=AsyncMock(return_value=ai_result),
                        ):
                            result = await scrape_single_prospect(
                                "https://example.com",
                                {"job_id": 9},
                            )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["score"], 0.785)
        self.assertEqual(result["confidence_level"], "high")
        self.assertEqual(result["scoring_trace"]["strategy"], "hybrid")
        self.assertEqual(result["scoring_trace"]["ai_weight"], 0.85)
        self.assertEqual(result["scoring_trace"]["heuristic_weight"], 0.15)
        self.assertEqual(result["quality_status"], "accepted")
        self.assertEqual(result["acceptance_decision"], "accepted_target")
        self.assertEqual(result["taxonomy_top_level"], "health")
        self.assertEqual(result["taxonomy_business_type"], "dental_clinic")

    async def test_prefers_normalized_location_over_ai_or_heuristic_raw_location(self) -> None:
        metadata = {
            "title": "Clinica Dental Madrid",
            "description": "Clinica dental en Madrid",
            "emails": ["hola@clinicamadrid.es"],
            "phones": ["+34911111111"],
            "social_links": [],
            "internal_links": ["https://clinicamadrid.es/contacto"],
            "form_detected": True,
            "contact_channels": [
                {"type": "contact_form", "value": "https://clinicamadrid.es/contacto"},
                {"type": "email", "value": "hola@clinicamadrid.es"},
            ],
            "addresses": ["Calle Mayor 1, 28013 Madrid, ES"],
            "map_links": ["https://google.com/maps?q=Madrid"],
            "cta_candidates": ["booking"],
            "primary_cta": "booking",
            "booking_url": "https://clinicamadrid.es/reservas",
            "structured_data_evidence": ["json_ld_detected", "structured_address_detected"],
            "structured_data": [
                {
                    "@type": "Dentist",
                    "address": {
                        "streetAddress": "Calle Mayor 1",
                        "postalCode": "28013",
                        "addressLocality": "Madrid",
                        "addressCountry": "ES",
                    },
                }
            ],
            "html_lang": "es",
            "meta_locale": "es_es",
            "website_url": "https://clinicamadrid.es",
        }
        heuristic_result = {
            "company_name": "Clinica Dental Madrid",
            "category": "Clinica",
            "location": "Calle Mayor 1, Madrid, ES | Tel +34 911 111 111",
            "description": "Clinica dental",
            "inferred_tech_stack": ["WordPress"],
            "inferred_niche": "Dental",
            "hiring_signals": False,
            "estimated_revenue_signal": "medium",
            "has_active_ads": False,
            "score": 0.64,
            "confidence_level": "medium",
            "fit_summary": "Fit heuristico fuerte; destacan contacto y reservas.",
            "heuristic_trace": {"component_scores": {"stack_fit": 0.8}, "signals": {}},
            "generic_attributes": {
                "evaluation_method": "Heuristic Code (No LLM)",
                "observed_signals": [],
                "inferred_opportunities": [],
                "pain_points_detected": [],
            },
            "observed_signals": [],
            "inferred_opportunities": [],
        }
        ai_result = {
            "location": "Madrid | Horarios 9:00-18:00",
            "inferred_tech_stack": ["WordPress", "Google Analytics"],
            "inferred_niche": "Dental",
            "generic_attributes": {
                "evaluation_method": "DeepSeek API (deepseek_prospect_v3)",
                "observed_signals": ["No se detectan testimonios visibles"],
                "inferred_opportunities": ["Posible oportunidad: destacar prueba social visible"],
                "pain_points_detected": ["Posible oportunidad: destacar prueba social visible"],
            },
            "observed_signals": ["No se detectan testimonios visibles"],
            "inferred_opportunities": ["Posible oportunidad: destacar prueba social visible"],
            "hiring_signals": False,
            "estimated_revenue_signal": "high",
            "score": 0.78,
            "confidence_level": "high",
            "_ai_metrics": {},
        }

        with patch("app.scraper.engine.fetch_html", new=AsyncMock(return_value="<html></html>")):
            with patch("app.scraper.engine.parse_html_basic", return_value=("x" * 250, metadata)):
                with patch(
                    "app.scraper.engine._crawl_key_pages",
                    new=AsyncMock(return_value=("", metadata, [])),
                ):
                    with patch(
                        "app.scraper.engine.extract_business_entity_heuristic",
                        new=AsyncMock(return_value=heuristic_result),
                    ):
                        with patch(
                            "app.scraper.engine.extract_business_entity_ai",
                            new=AsyncMock(return_value=ai_result),
                        ):
                            result = await scrape_single_prospect(
                                "https://clinicamadrid.es",
                                {"job_id": 9, "target_location": "Madrid", "target_language": "es"},
                            )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["location"], "28013 Madrid, España")
        self.assertEqual(result["validated_location"], "28013 Madrid, España")
        self.assertEqual(result["raw_location_text"], "Calle Mayor 1, 28013 Madrid, ES")
        self.assertEqual(result["city"], "Madrid")
        self.assertEqual(result["country"], "España")
        self.assertEqual(result["observed_signals"], ["No se detectan testimonios visibles"])
        self.assertEqual(result["inferred_opportunities"], ["Posible oportunidad: destacar prueba social visible"])
        self.assertEqual(result["taxonomy_business_type"], "dental_clinic")

    async def test_uses_heuristic_and_attaches_ai_trace_on_fallback(self) -> None:
        metadata = {
            "title": "Dental Home",
            "description": "Clinica dental",
            "emails": ["hola@example.com"],
            "phones": [],
            "social_links": [],
            "internal_links": [],
            "form_detected": True,
            "contact_channels": [
                {"type": "contact_form", "value": "https://example.com/contacto"},
                {"type": "email", "value": "hola@example.com"},
            ],
            "addresses": [],
            "map_links": [],
            "cta_candidates": [],
            "structured_data_evidence": [],
            "structured_data": [],
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
                "observed_signals": [],
                "inferred_opportunities": [],
                "pain_points_detected": [],
            },
            "observed_signals": [],
            "inferred_opportunities": [],
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

    async def test_skips_ai_for_rejected_geo_mismatch(self) -> None:
        metadata = {
            "title": "Clinica Dental Barcelona",
            "description": "Clinica dental en Barcelona",
            "emails": [],
            "phones": [],
            "social_links": [],
            "internal_links": [],
            "form_detected": False,
            "addresses": ["Carrer Mallorca 1, Barcelona, ES"],
            "map_links": ["https://google.com/maps?q=Barcelona"],
            "html_lang": "es",
            "contact_channels": [],
            "cta_candidates": [],
            "structured_data_evidence": [],
            "structured_data": [],
        }
        heuristic_result = {
            "company_name": "Dental Home",
            "category": "Clinica",
            "location": "Barcelona",
            "description": "Clinica dental",
            "inferred_tech_stack": ["WordPress"],
            "inferred_niche": "Dental",
            "hiring_signals": False,
            "estimated_revenue_signal": "medium",
            "has_active_ads": False,
            "score": 0.7,
            "confidence_level": "medium",
            "fit_summary": "Fit heuristico fuerte; destacan stack, contacto.",
            "heuristic_trace": {"component_scores": {"stack_fit": 0.8}, "signals": {}},
            "generic_attributes": {
                "evaluation_method": "Heuristic Code (No LLM)",
                "observed_signals": [],
                "inferred_opportunities": [],
                "pain_points_detected": [],
            },
            "observed_signals": [],
            "inferred_opportunities": [],
        }

        with patch("app.scraper.engine.fetch_html", new=AsyncMock(return_value="<html></html>")):
            with patch("app.scraper.engine.parse_html_basic", return_value=("x" * 250, metadata)):
                with patch(
                    "app.scraper.engine._crawl_key_pages",
                    new=AsyncMock(return_value=("", metadata, [])),
                ):
                    with patch(
                        "app.scraper.engine.extract_business_entity_heuristic",
                        new=AsyncMock(return_value=heuristic_result),
                    ):
                        with patch(
                            "app.scraper.engine.extract_business_entity_ai",
                            new=AsyncMock(side_effect=AssertionError("AI no deberia ejecutarse")),
                        ):
                            result = await scrape_single_prospect(
                                "https://example.com",
                                {"job_id": 9, "target_location": "Madrid", "target_language": "es"},
                            )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["quality_status"], "rejected")
        self.assertEqual(result["rejection_reason"], "geo_mismatch")
        self.assertEqual(result["acceptance_decision"], "rejected_low_confidence")
        self.assertEqual(result["ai_trace"]["status"], "skipped")
        self.assertEqual(result["ai_trace"]["fallback_reason"], "quality_rejected")
        self.assertEqual(result["taxonomy_business_type"], "dental_clinic")


if __name__ == "__main__":
    unittest.main()
