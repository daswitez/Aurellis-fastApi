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

from app.services.ai_extractor import AIExtractionFallbackError, extract_business_entity_ai


class _FakeCompletions:
    def __init__(self, payload: str) -> None:
        self.payload = payload

    async def create(self, **kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.payload))]
        )


class _FakeClient:
    def __init__(self, payload: str) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions(payload))


class ExtractBusinessEntityAITestCase(unittest.IsolatedAsyncioTestCase):
    async def test_normalizes_valid_ai_payload(self) -> None:
        payload = json.dumps(
            {
                "inferred_niche": "  Dental Clinic  ",
                "inferred_tech_stack": [" WordPress ", "", "WordPress", 99, "React"],
                "generic_attributes": {
                    "pain_points_detected": [
                        " Sin CTA clara ",
                        "",
                        "Sin CTA clara",
                        7,
                        "No muestra reservas",
                        "Carga lenta",
                        "Formulario confuso",
                        "Sin prueba social",
                        "Extra pain",
                    ]
                },
                "hiring_signals": "yes",
                "estimated_revenue_signal": " HIGH ",
                "score": "1.2",
                "confidence_level": "0.82",
            }
        )

        with patch("app.services.ai_extractor._get_deepseek_api_key", return_value="test-key"):
            with patch(
                "app.services.ai_extractor._build_deepseek_client",
                return_value=_FakeClient(payload),
            ):
                result = await extract_business_entity_ai("example.com", "x" * 200, {})

        self.assertEqual(result["inferred_niche"], "Dental Clinic")
        self.assertEqual(result["inferred_tech_stack"], ["WordPress", "React"])
        self.assertEqual(
            result["generic_attributes"]["pain_points_detected"],
            [
                "Sin CTA clara",
                "No muestra reservas",
                "Carga lenta",
                "Formulario confuso",
                "Sin prueba social",
            ],
        )
        self.assertEqual(result["estimated_revenue_signal"], "high")
        self.assertEqual(result["score"], 1.0)
        self.assertEqual(result["confidence_level"], "high")
        self.assertTrue(result["hiring_signals"])

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


if __name__ == "__main__":
    unittest.main()
