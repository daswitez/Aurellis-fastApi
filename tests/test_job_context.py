import unittest

from app.api.jobs import _build_job_context
from app.models import ScrapingJob


class BuildJobContextTestCase(unittest.TestCase):
    def test_includes_all_commercial_context_fields(self) -> None:
        job = ScrapingJob(
            id=17,
            workspace_id="ws_123",
            user_profession="Desarrollador Web",
            user_technologies=["WordPress", "SEO"],
            user_value_proposition="Mejoro conversiones del sitio",
            user_past_successes=["Subimos leads 30%"],
            user_roi_metrics=["ROI 3x"],
            target_niche="Clinicas dentales",
            target_location="Madrid",
            target_language="es",
            target_company_size="5-20 empleados",
            target_pain_points=["Sin reservas online"],
            target_budget_signals=["Google Ads activos"],
            filters_json={
                "discovery_profile": {
                    "user_service_offers": ["Creativos para redes sociales", "Videos de venta"],
                    "user_service_constraints": ["No motion graphics complejos"],
                    "user_target_offer_focus": "Negocios que vendan productos digitales o hagan ecommerce",
                    "user_ticket_size": "1500 USD",
                }
            },
        )

        context = _build_job_context(
            job,
            search_query="clinicas dentales madrid",
            discovery_method="search_query",
            source_type="duckduckgo_search",
            search_warning="sin warning",
        )

        self.assertEqual(context["job_id"], 17)
        self.assertEqual(context["workspace_id"], "ws_123")
        self.assertEqual(context["user_profession"], "Desarrollador Web")
        self.assertEqual(context["user_technologies"], ["WordPress", "SEO"])
        self.assertEqual(context["user_value_proposition"], "Mejoro conversiones del sitio")
        self.assertEqual(context["user_past_successes"], ["Subimos leads 30%"])
        self.assertEqual(context["user_roi_metrics"], ["ROI 3x"])
        self.assertEqual(context["target_niche"], "Clinicas dentales")
        self.assertEqual(context["target_location"], "Madrid")
        self.assertEqual(context["target_language"], "es")
        self.assertEqual(context["target_company_size"], "5-20 empleados")
        self.assertEqual(context["target_pain_points"], ["Sin reservas online"])
        self.assertEqual(context["target_budget_signals"], ["Google Ads activos"])
        self.assertEqual(context["user_service_offers"], ["Creativos para redes sociales", "Videos de venta"])
        self.assertEqual(context["user_service_constraints"], ["No motion graphics complejos"])
        self.assertEqual(context["user_target_offer_focus"], "Negocios que vendan productos digitales o hagan ecommerce")
        self.assertEqual(context["user_ticket_size"], "1500 USD")
        self.assertEqual(context["search_query"], "clinicas dentales madrid")
        self.assertEqual(context["discovery_method"], "search_query")
        self.assertEqual(context["source_type"], "duckduckgo_search")
        self.assertEqual(context["search_warning"], "sin warning")


if __name__ == "__main__":
    unittest.main()
