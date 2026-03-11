import unittest

from app.services.heuristic_extractor import build_heuristic_trace, extract_business_entity_heuristic


class HeuristicExtractorTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_builds_strong_heuristic_score_with_explainable_breakdown(self) -> None:
        clean_text = (
            "Clinica dental en Madrid con precios claros, testimonios de pacientes y portfolio de tratamientos. "
            "Agenda tu cita online. Estamos contratando odontologos. Servicios para implantes y ortodoncia."
        )
        html_raw = """
        <html>
          <head>
            <title>Clinica Sonrisa Madrid</title>
            <meta name="description" content="Clinica dental en Madrid especializada en implantes" />
            <script src="https://cdn.shopify.com/example.js"></script>
            <script>fbq('init', '123'); gtag('config', 'GA-123');</script>
          </head>
          <body></body>
        </html>
        """
        metadata = {
            "title": "Clinica Sonrisa Madrid",
            "description": "Clinica dental en Madrid especializada en implantes",
            "emails": ["hola@clinica.com"],
            "phones": ["+34911111111"],
            "social_links": ["https://instagram.com/clinica", "https://facebook.com/clinica"],
            "internal_links": [
                "https://clinica.com/contacto",
                "https://clinica.com/nosotros",
                "https://clinica.com/careers",
            ],
            "form_detected": True,
        }
        context = {
            "target_niche": "Clinica dental",
            "target_location": "Madrid",
            "target_language": "es",
            "user_technologies": ["Shopify", "SEO"],
            "target_pain_points": ["Sin reservas online"],
            "target_budget_signals": ["Estamos contratando"],
        }

        result = await extract_business_entity_heuristic(clean_text, html_raw, metadata, context)

        self.assertGreaterEqual(result["score"], 0.65)
        self.assertIn(result["confidence_level"], {"medium", "high"})
        self.assertEqual(result["estimated_revenue_signal"], "high")
        self.assertTrue(result["hiring_signals"])
        self.assertTrue(result["has_active_ads"])
        self.assertIn("Meta Pixel", result["inferred_tech_stack"])
        self.assertIn("Shopify", result["inferred_tech_stack"])
        self.assertIn("heuristic_score_breakdown", result["generic_attributes"])
        self.assertIn("contact_availability", result["generic_attributes"]["heuristic_score_breakdown"])
        self.assertIn("contactabilidad", result["fit_summary"])
        self.assertIn("stack_fit", result["heuristic_trace"]["component_scores"])
        self.assertEqual(result["taxonomy_top_level"], "health")
        self.assertEqual(result["taxonomy_business_type"], "dental_clinic")
        self.assertEqual(result["inferred_niche"], "Dental")
        self.assertEqual(result["observed_signals"], [])
        self.assertEqual(result["inferred_opportunities"], [])

    async def test_returns_low_score_when_evidence_is_weak(self) -> None:
        clean_text = "Sitio simple de servicios generales."
        html_raw = "<html><head><title>Servicios ABC</title></head><body></body></html>"
        metadata = {
            "title": "Servicios ABC",
            "description": "",
            "emails": [],
            "phones": [],
            "social_links": [],
            "internal_links": [],
            "form_detected": False,
        }
        context = {
            "target_niche": "Clinica dental",
            "target_location": "Madrid",
            "target_language": "es",
            "target_pain_points": ["Sin reservas online"],
        }

        trace = build_heuristic_trace(clean_text, html_raw, metadata, context)

        self.assertLessEqual(trace["score"], 0.3)
        self.assertEqual(trace["confidence_level"], "low")
        self.assertEqual(trace["estimated_revenue_signal"], "low")
        self.assertIn("No muestra contacto directo visible", trace["observed_signals"])
        self.assertIn("Meta description ausente", trace["observed_signals"])
        self.assertTrue(
            any(item.startswith("Posible oportunidad: ") for item in trace["inferred_opportunities"])
        )
        self.assertEqual(trace["pain_points_detected"], trace["inferred_opportunities"])
        self.assertEqual(trace["taxonomy_business_type"], "local_business")
        self.assertIn("Fit heuristico debil", trace["fit_summary"])


if __name__ == "__main__":
    unittest.main()
