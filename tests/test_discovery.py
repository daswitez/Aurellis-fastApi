import unittest

from app.services.discovery import build_discovery_queries


class DiscoveryQueryTestCase(unittest.TestCase):
    def test_builds_queries_from_seed_and_target_context(self) -> None:
        queries = build_discovery_queries(
            search_query="clinicas dentales",
            target_niche="clinicas dentales",
            target_location="Madrid",
            target_language="es",
        )

        self.assertEqual(queries[0], "clinicas dentales")
        self.assertIn("clinicas dentales Madrid", queries)
        self.assertTrue(any("sitio oficial" in query for query in queries))

    def test_synthesizes_query_when_search_query_is_missing(self) -> None:
        queries = build_discovery_queries(
            search_query=None,
            target_niche="veterinarias",
            target_location="Lima",
            target_language=None,
        )

        self.assertEqual(queries[0], "veterinarias Lima")


if __name__ == "__main__":
    unittest.main()
