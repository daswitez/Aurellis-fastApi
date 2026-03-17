import unittest
from unittest.mock import AsyncMock, patch

from app.services import ai_search_planner
from app.services.ai_search_planner import initial_search_plan, refine_search_plan


class AISearchPlannerTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        ai_search_planner._PLANNER_CACHE.clear()

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
        self.assertEqual(plan["planner_profile"], "creator_coach")
        self.assertEqual(plan["geo_scope"], "España")

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
        self.assertEqual(plan["planner_profile"], "creator_coach")

    async def test_initial_plan_enforces_supported_country_geo_for_ecommerce_profile(self) -> None:
        with patch(
            "app.services.ai_search_planner._call_planner",
            new=AsyncMock(
                return_value={
                    "optimal_dork_queries": [
                        'site:myshopify.com "shop now" "small brand"',
                        'site:instagram.com "small ecommerce brand" "product launch"',
                        'site:tiktok.com "shopify store" Canada',
                        '"dropshipping store" "official site"',
                    ],
                    "dynamic_negative_terms": ["blog", "theme"],
                    "target_entity_hints": ["product brand"],
                    "exclusion_entity_hints": ["directory"],
                    "refinement_goal": "Encontrar tiendas ecommerce activas con contenido constante",
                }
            ),
        ):
            plan = await initial_search_plan(
                {
                    "search_query": "small ecommerce brands shopify dropshipping stores instagram tiktok active content",
                    "user_profession": "Editor de Video",
                    "target_niche": "Pequeñas marcas ecommerce, tiendas online, dropshipping y pymes digitales",
                    "target_location": "USA",
                    "target_language": "en",
                    "target_budget_signals": [
                        "Tienda online activa",
                        "Presencia en Instagram o TikTok",
                        "Corren anuncios o muestran señales de ads",
                    ],
                }
            )

        self.assertEqual(
            plan["optimal_dork_queries"],
            [
                'site:instagram.com "small ecommerce brand" "product launch" USA',
                '"dropshipping store" "official site" USA',
            ],
        )
        self.assertEqual(plan["dynamic_negative_terms"], ["-blog", "-theme"])
        self.assertIn("ecommerce activo", plan["target_entity_hints"])
        self.assertIn("shopify store", plan["target_entity_hints"])
        self.assertIn("theme", plan["exclusion_entity_hints"])
        self.assertEqual(plan["planner_profile"], "ecommerce_content")
        self.assertEqual(plan["geo_scope"], "USA")

    async def test_multi_location_option_string_does_not_force_invalid_geo_suffix(self) -> None:
        planner_mock = AsyncMock(
            return_value={
                "optimal_dork_queries": ['site:instagram.com "shopify store" "product video"'],
                "dynamic_negative_terms": ["blog"],
                "target_entity_hints": [],
                "exclusion_entity_hints": [],
                "refinement_goal": "Encontrar tiendas activas con contenido frecuente",
            }
        )
        with patch("app.services.ai_search_planner._call_planner", new=planner_mock):
            plan = await initial_search_plan(
                {
                    "search_query": "small ecommerce brands shopify dropshipping stores instagram tiktok active content",
                    "user_profession": "Editor de Video",
                    "target_niche": "Pequeñas marcas ecommerce, tiendas online, dropshipping y pymes digitales",
                    "target_location": "USA/UK/Canada/Australia/España/México/Colombia/Argentina",
                    "target_language": "en",
                }
            )

        self.assertEqual(
            plan["optimal_dork_queries"],
            ['site:instagram.com "shopify store" "product video"'],
        )
        self.assertIsNone(plan["geo_scope"])
        self.assertEqual(plan["planner_profile"], "ecommerce_content")
        awaited_kwargs = planner_mock.await_args.kwargs
        self.assertIn("Perfil activo: ecommerce_content", awaited_kwargs["user_prompt"])
        self.assertIn("Flexible o multiple opciones", awaited_kwargs["user_prompt"])
        self.assertIn("paginas de producto o coleccion", awaited_kwargs["system_prompt"])


if __name__ == "__main__":
    unittest.main()
