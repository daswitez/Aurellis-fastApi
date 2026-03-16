import unittest
from unittest.mock import AsyncMock, patch

from app.services.ai_search_planner import initial_search_plan, refine_search_plan


class AISearchPlannerTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_initial_plan_enforces_spain_geo_and_negative_terms(self) -> None:
        with patch(
            "app.services.ai_search_planner._call_planner",
            new=AsyncMock(
                return_value={
                    "optimal_dork_queries": [
                        'site:instagram.com "coach de negocios" Madrid',
                        'site:tiktok.com "marca personal" Buenos Aires',
                        '"coach ejecutivo" contacto',
                    ],
                    "dynamic_negative_terms": ["blog", "-directorio"],
                    "target_entity_hints": ["coach final", "marca personal"],
                    "exclusion_entity_hints": ["escuela", "directorio"],
                    "refinement_goal": "Encontrar coaches finales con presencia comercial",
                }
            ),
        ):
            plan = await initial_search_plan(
                {
                    "search_query": "marcas personales y coaches de negocios España",
                    "target_niche": "Marcas Personales y Coaches",
                    "target_location": "España",
                }
            )

        self.assertTrue(all("buenos aires" not in query.lower() for query in plan["optimal_dork_queries"]))
        self.assertTrue(all("españa" in query.lower() for query in plan["optimal_dork_queries"]))
        self.assertEqual(plan["dynamic_negative_terms"], ["-blog", "-directorio"])
        self.assertEqual(plan["refinement_goal"], "Encontrar coaches finales con presencia comercial")

    async def test_refinement_plan_dedupes_queries_and_keeps_spain_scope(self) -> None:
        with patch(
            "app.services.ai_search_planner._call_planner",
            new=AsyncMock(
                return_value={
                    "optimal_dork_queries": [
                        'site:instagram.com "coach de negocios" España "linktree"',
                        'site:instagram.com "coach de negocios" España "linktree"',
                        'site:instagram.com "coach de negocios" "programa"',
                    ],
                    "dynamic_negative_terms": ["escuela", "listado"],
                    "target_entity_hints": ["coach final"],
                    "exclusion_entity_hints": ["escuela", "listado de coaches"],
                    "refinement_goal": "Reducir ruido de escuelas y listados",
                }
            ),
        ):
            plan = await refine_search_plan(
                {
                    "search_query": "marcas personales ecommerce y coaches de negocios España",
                    "target_niche": "Marcas Personales y Coaches",
                    "target_location": "España",
                },
                {
                    "trigger_reason": "high_noise_window",
                    "queries_already_executed": ["coaches españa"],
                    "false_positive_samples": [{"domain": "dafont.com"}],
                },
            )

        self.assertEqual(
            plan["optimal_dork_queries"],
            [
                'site:instagram.com "coach de negocios" España "linktree"',
                'site:instagram.com "coach de negocios" "programa" España',
            ],
        )
        self.assertEqual(plan["dynamic_negative_terms"], ["-escuela", "-listado"])


if __name__ == "__main__":
    unittest.main()
