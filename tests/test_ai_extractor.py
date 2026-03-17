import json
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch

if "openai" not in sys.modules:
    openai_stub = types.ModuleType("openai")
    openai_stub.AsyncOpenAI = object
    sys.modules["openai"] = openai_stub

from app.services.ai_extractor import AIExtractionFallbackError, _AI_CACHE, extract_business_entity_ai, screen_candidate_quick_ai


class _FakeCompletions:
    def __init__(self, payload: str) -> None:
        self.payload = payload

    async def create(self, **kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.payload))],
            usage=SimpleNamespace(prompt_tokens=120, completion_tokens=45, total_tokens=165),
        )


class _FakeClient:
    def __init__(self, payload: str) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions(payload))


class ExtractBusinessEntityAITestCase(unittest.IsolatedAsyncioTestCase):
    def tearDown(self) -> None:
        _AI_CACHE.clear()

    async def test_normalizes_valid_ai_payload(self) -> None:
        payload = json.dumps(
            {
                "inferred_niche": "  Dental Clinic  ",
                "inferred_tech_stack": [" WordPress ", "", "WordPress", 99, "React"],
                "generic_attributes": {
                    "observed_signals": [
                        " Sin CTA clara ",
                        "No se detectan testimonios visibles",
                        "",
                        "Sin CTA clara",
                    ],
                    "inferred_opportunities": [
                        " reforzar CTA principal visible ",
                        "",
                        "reforzar CTA principal visible",
                        7,
                        "destacar testimonios visibles",
                        "mejorar reservas online visibles",
                        "mejorar formulario de contacto",
                        "reforzar prueba social visible",
                        "extra oportunidad",
                    ],
                    "pain_points_detected": [
                        "",
                        "No muestra reservas",
                    ]
                },
                "hiring_signals": "yes",
                "estimated_revenue_signal": " HIGH ",
                "score": "1.2",
                "confidence_level": "0.82",
            }
        )

        settings_stub = SimpleNamespace(
            DEEPSEEK_INPUT_COST_PER_1M_TOKENS=0.14,
            DEEPSEEK_OUTPUT_COST_PER_1M_TOKENS=0.28,
        )

        with patch("app.services.ai_extractor._get_deepseek_api_key", return_value="test-key"):
            with patch("app.services.ai_extractor.get_settings", return_value=settings_stub):
                with patch(
                    "app.services.ai_extractor._build_deepseek_client",
                    return_value=_FakeClient(payload),
                ):
                    result = await extract_business_entity_ai("example.com", "x" * 200, {})

        self.assertEqual(result["inferred_niche"], "Dental")
        self.assertEqual(result["taxonomy_top_level"], "health")
        self.assertEqual(result["taxonomy_business_type"], "dental_clinic")
        self.assertEqual(result["inferred_tech_stack"], ["WordPress", "React"])
        self.assertEqual(
            result["generic_attributes"]["observed_signals"],
            [
                "Sin CTA clara",
                "No se detectan testimonios visibles",
            ],
        )
        self.assertEqual(
            result["generic_attributes"]["inferred_opportunities"],
            [
                "Posible oportunidad: reforzar CTA principal visible",
                "Posible oportunidad: destacar testimonios visibles",
                "Posible oportunidad: mejorar reservas online visibles",
                "Posible oportunidad: mejorar formulario de contacto",
                "Posible oportunidad: reforzar prueba social visible",
            ],
        )
        self.assertEqual(
            result["generic_attributes"]["pain_points_detected"],
            result["generic_attributes"]["inferred_opportunities"],
        )
        self.assertEqual(result["observed_signals"], result["generic_attributes"]["observed_signals"])
        self.assertEqual(result["inferred_opportunities"], result["generic_attributes"]["inferred_opportunities"])
        self.assertEqual(result["estimated_revenue_signal"], "high")
        self.assertEqual(result["score"], 1.0)
        self.assertEqual(result["confidence_level"], "high")
        self.assertTrue(result["hiring_signals"])
        self.assertEqual(result["_ai_metrics"]["prompt_tokens"], 120)
        self.assertEqual(result["_ai_metrics"]["completion_tokens"], 45)
        self.assertEqual(result["_ai_metrics"]["total_tokens"], 165)
        self.assertEqual(result["_ai_metrics"]["estimated_cost_usd"], 0.0000294)

    async def test_reuses_cached_payload_without_reconsuming_tokens(self) -> None:
        payload = json.dumps(
            {
                "inferred_niche": "Clinica",
                "inferred_tech_stack": ["WordPress"],
                "generic_attributes": {
                    "observed_signals": ["Sin CTA clara"],
                    "inferred_opportunities": ["reforzar CTA principal visible"],
                },
                "hiring_signals": False,
                "estimated_revenue_signal": "medium",
                "score": 0.7,
                "confidence_level": "medium",
            }
        )

        with patch("app.services.ai_extractor._get_deepseek_api_key", return_value="test-key"):
            with patch(
                "app.services.ai_extractor._build_deepseek_client",
                return_value=_FakeClient(payload),
            ) as client_builder:
                first = await extract_business_entity_ai("example.com", "x" * 200, {}, cache_key="cache-key")
                second = await extract_business_entity_ai("example.com", "x" * 200, {}, cache_key="cache-key")

        self.assertEqual(first["inferred_niche"], second["inferred_niche"])
        self.assertEqual(first["taxonomy_business_type"], second["taxonomy_business_type"])
        self.assertEqual(second["_ai_metrics"]["total_tokens"], 0)
        self.assertTrue(second["_ai_metrics"]["cache_hit"])
        self.assertEqual(client_builder.call_count, 1)

    async def test_accepts_legacy_pain_points_payload_as_inferred_opportunities(self) -> None:
        payload = json.dumps(
            {
                "inferred_niche": "Clinica",
                "inferred_tech_stack": ["WordPress"],
                "generic_attributes": {"pain_points_detected": ["Sin CTA clara"]},
                "hiring_signals": False,
                "estimated_revenue_signal": "medium",
                "score": 0.7,
                "confidence_level": "medium",
            }
        )

        with patch("app.services.ai_extractor._get_deepseek_api_key", return_value="test-key"):
            with patch(
                "app.services.ai_extractor._build_deepseek_client",
                return_value=_FakeClient(payload),
            ):
                result = await extract_business_entity_ai("example.com", "x" * 200, {})

        self.assertEqual(result["observed_signals"], [])
        self.assertEqual(result["inferred_opportunities"], ["Posible oportunidad: sin CTA clara"])
        self.assertEqual(result["generic_attributes"]["pain_points_detected"], result["inferred_opportunities"])
        self.assertEqual(result["taxonomy_business_type"], "medical_clinic")

    async def test_rejects_incomplete_ai_payload(self) -> None:
        payload = json.dumps(
            {
                "inferred_niche": "Clinica",
                "inferred_tech_stack": ["WordPress"],
                "hiring_signals": False,
                "estimated_revenue_signal": "medium",
                "score": 0.7,
                "confidence_level": "medium",
            }
        )

        with patch("app.services.ai_extractor._get_deepseek_api_key", return_value="test-key"):
            with patch(
                "app.services.ai_extractor._build_deepseek_client",
                return_value=_FakeClient(payload),
            ):
                with self.assertRaises(AIExtractionFallbackError) as ctx:
                    await extract_business_entity_ai("example.com", "x" * 200, {})

        self.assertEqual(ctx.exception.reason, "invalid_schema")
        self.assertEqual(ctx.exception.error_type, "invalid_response")

    async def test_quick_screen_accepts_social_first_candidate_without_phone(self) -> None:
        payload = json.dumps(
            {
                "verdict": "keep_target",
                "confidence_level": "high",
                "reason_code": "social_offer_with_cta",
                "reasoning": ["Marca personal con oferta clara y link-in-bio."],
            }
        )

        with patch("app.services.ai_extractor._get_deepseek_api_key", return_value="test-key"):
            with patch(
                "app.services.ai_extractor._build_deepseek_client",
                return_value=_FakeClient(payload),
            ):
                result = await screen_candidate_quick_ai(
                    "instagram:mentorpro",
                    {
                        "target_niche": "Coaches y Asesores",
                        "candidate_evaluation_policy": {
                            "identity_priority": "social_first",
                            "contact_requirement": "soft",
                            "quick_ai_stage": "hybrid",
                        },
                    },
                    evidence_pack={
                        "title": "MentorPro",
                        "snippet": "Mentoria para coaches. Aplica en bio.",
                        "result_kind": "social_profile",
                        "platform": "instagram",
                        "handle": "mentorpro",
                        "link_in_bio_present": True,
                        "cta_tokens": ["apply", "link in bio"],
                    },
                )

        self.assertEqual(result["verdict"], "keep_target")
        self.assertEqual(result["confidence_level"], "high")
        self.assertEqual(result["reason_code"], "social_offer_with_cta")


if __name__ == "__main__":
    unittest.main()
