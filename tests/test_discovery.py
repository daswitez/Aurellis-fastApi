import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.scraper.search_engines.ddg_search import (
    SearchDiscoveryEntry,
    _detect_antibot_challenge,
    _expand_directory_seed_entry,
    _extract_official_site_from_seed_html,
    _extract_search_results,
)
from app.services.discovery import (
    build_discovery_query_batches,
    build_discovery_queries,
    determine_capture_stop_reason,
    resolve_candidate_batch_size,
    resolve_capture_targets,
    resolve_discovery_batch_budget,
)
from app.services.discovery_orchestrator import discover_prospect_urls_by_queries
from app.services.discovery_ranker import score_business_likeness
from app.services.discovery_types import SearchDiscoveryResult
from app.services.search_providers.base import SearchProvider


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "serp"


def _read_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


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
        self.assertTrue(any("contacto" in query for query in queries))
        self.assertTrue(any("-blog" in query for query in queries[2:]))

    def test_synthesizes_query_when_search_query_is_missing(self) -> None:
        queries = build_discovery_queries(
            search_query=None,
            target_niche="veterinarias",
            target_location="Lima",
            target_language=None,
        )

        self.assertEqual(queries[0], "veterinarias Lima")
        self.assertTrue(any("sitio oficial" in query for query in queries))

    def test_builds_niche_driven_query_family_for_broad_user_search(self) -> None:
        queries = build_discovery_queries(
            search_query="Tiendas de productos o servicios que puedan necesitar disenadores",
            target_niche="Tiendas",
            target_location="Argentina",
            target_language="es",
        )

        self.assertIn("Tiendas Argentina", queries)
        self.assertTrue(any(query.startswith("Tiendas Argentina sitio oficial") for query in queries))
        self.assertTrue(any(query.startswith("Tiendas Argentina contacto") for query in queries))

    def test_splits_mixed_niches_into_more_prospectable_queries(self) -> None:
        queries = build_discovery_queries(
            search_query="empresas ecommerce y academias online España",
            target_niche="Ecommerce y academias online",
            target_location="España",
            target_language="es",
            user_target_offer_focus="Crear creativos para negocios que vendan productos digitales o hagan ecommerce",
        )

        self.assertIn("ecommerce España", queries)
        self.assertIn("academia online España", queries)
        self.assertTrue(any(query.startswith("ecommerce España sitio oficial") for query in queries))
        self.assertTrue(any(query.startswith("academia online España contacto") for query in queries))
        self.assertTrue(any("-prensa" in query for query in queries))
        self.assertTrue(any("-informe" in query for query in queries))
        self.assertTrue(any("-asesoria" in query or "-consultoria" in query for query in queries))

    def test_resolves_capture_targets_from_legacy_max_results(self) -> None:
        targets = resolve_capture_targets(
            max_results_legacy=5,
            target_accepted_results=None,
            max_candidates_to_process=None,
            seed_urls_count=0,
        )

        self.assertEqual(targets["target_accepted_results"], 5)
        self.assertEqual(targets["max_candidates_to_process"], 20)

    def test_resolves_capture_targets_with_explicit_override(self) -> None:
        targets = resolve_capture_targets(
            max_results_legacy=5,
            target_accepted_results=3,
            max_candidates_to_process=12,
            seed_urls_count=0,
        )

        self.assertEqual(targets["target_accepted_results"], 3)
        self.assertEqual(targets["max_candidates_to_process"], 12)

    def test_resolves_minimum_candidate_ratio_for_single_target(self) -> None:
        targets = resolve_capture_targets(
            max_results_legacy=1,
            target_accepted_results=None,
            max_candidates_to_process=None,
            seed_urls_count=0,
        )

        self.assertEqual(targets["target_accepted_results"], 1)
        self.assertEqual(targets["max_candidates_to_process"], 5)

    def test_resolves_candidate_and_discovery_batch_sizes(self) -> None:
        self.assertEqual(
            resolve_candidate_batch_size(target_accepted_results=1, candidate_cap=5),
            3,
        )
        self.assertEqual(
            resolve_candidate_batch_size(target_accepted_results=5, candidate_cap=20),
            5,
        )
        self.assertEqual(
            resolve_discovery_batch_budget(
                target_accepted_results=5,
                candidate_cap=20,
                remaining_budget=20,
            ),
            10,
        )

    def test_builds_incremental_discovery_query_batches(self) -> None:
        query_batches = build_discovery_query_batches(
            search_query="clinicas dentales",
            target_niche="clinicas dentales",
            target_location="Madrid",
            target_language="es",
        )

        self.assertGreaterEqual(len(query_batches), 2)
        self.assertLessEqual(len(query_batches[0]), 2)
        flattened = [query for batch in query_batches for query in batch]
        self.assertTrue(any("empresa" in query or "negocio" in query for query in flattened))
        self.assertTrue(any("ubicaciones" in query or "sedes" in query for query in flattened))

    def test_resolves_stop_reason(self) -> None:
        self.assertEqual(
            determine_capture_stop_reason(
                accepted_count=3,
                target_accepted_results=3,
                processed_count=7,
                candidate_cap=12,
                discovered_candidates=12,
            ),
            "target_reached",
        )
        self.assertEqual(
            determine_capture_stop_reason(
                accepted_count=1,
                target_accepted_results=3,
                processed_count=12,
                candidate_cap=12,
                discovered_candidates=12,
            ),
            "candidate_cap_reached",
        )
        self.assertEqual(
            determine_capture_stop_reason(
                accepted_count=1,
                target_accepted_results=3,
                processed_count=7,
                candidate_cap=12,
                discovered_candidates=7,
            ),
            "discovery_exhausted",
        )

    def test_discovery_excludes_editorial_results_and_ranks_business_sites_first(self) -> None:
        html = _read_fixture("serp_editorial_vs_official.html")

        entries, excluded = _extract_search_results(html, "tiendas argentina")

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].url, "https://tienda-ejemplo.com/contacto")
        self.assertEqual(entries[0].discovery_confidence, "high")
        self.assertGreater(entries[0].business_likeness_score or 0.0, 0.3)
        self.assertIn("official_site_hint", entries[0].discovery_reasons)
        self.assertTrue(any(item["reason"] == "excluded_as_article" for item in excluded))

    def test_discovery_offline_fixture_covers_articles_directories_geo_and_cta(self) -> None:
        html = _read_fixture("serp_mixed_local_businesses.html")

        entries, excluded = _extract_search_results(html, "clinicas dentales madrid")

        urls = [entry.url for entry in entries]
        self.assertIn("https://clinicamadrid.es/contacto", urls)
        self.assertIn("https://clinicabarcelona.es/contacto", urls)
        self.assertIn("https://www.doctoralia.es/clinica-madrid", urls)
        self.assertTrue(any(item["reason"] == "excluded_as_article" for item in excluded))
        self.assertTrue(
            any("directory_seed_candidate" in (entry.discovery_reasons or []) for entry in entries)
        )

        ranked_local = next(entry for entry in entries if entry.url == "https://clinicamadrid.es/contacto")
        ranked_foreign = next(entry for entry in entries if entry.url == "https://clinicabarcelona.es/contacto")
        self.assertEqual(ranked_local.discovery_confidence, "high")
        self.assertGreater((ranked_local.business_likeness_score or 0.0), (ranked_foreign.business_likeness_score or 0.0))

    def test_extracts_official_site_from_directory_seed_html(self) -> None:
        html = _read_fixture("directory_seed_official_site.html")

        official_url, reasons = _extract_official_site_from_seed_html("https://www.doctoralia.com/clinica-ejemplo", html)

        self.assertEqual(official_url, "https://clinicaejemplo.com")
        self.assertIn("directory_seed_resolved", reasons)

    def test_business_likeness_excludes_press_and_report_pages(self) -> None:
        press_score, press_reasons, press_exclusion = score_business_likeness(
            "https://www.cnmc.es/prensa/ecommerce-20230404",
            "El comercio electronico supera en Espana los 18.900 millones",
            "Nota de prensa e informe sectorial del comercio electronico en Espana.",
        )
        report_score, report_reasons, report_exclusion = score_business_likeness(
            "https://www.kantar.com/es/campaigns/informe-de-la-moda-online-en-espana-2024",
            "Informe de la moda online en Espana 2024",
            "Estudio e informe sobre ecommerce y moda online en Espana.",
        )

        self.assertEqual(press_exclusion, "excluded_as_article")
        self.assertEqual(report_exclusion, "excluded_as_article")
        self.assertIn("editorial_path", press_reasons)
        self.assertIn("editorial_title", report_reasons)
        self.assertLess(press_score, 0.15)
        self.assertLess(report_score, 0.15)

    def test_business_likeness_excludes_product_detail_pages(self) -> None:
        product_score, product_reasons, product_exclusion = score_business_likeness(
            "https://lamasbolano.com/francisco-franco-1936-1975-/10015954-espana-1974-bellas-artes-sello-correo.html",
            "Bellas Artes 1974 Espana correo",
            "Serie completa, distribuidor oficial en Espana y carrito de compra disponible.",
        )

        self.assertEqual(product_exclusion, "excluded_as_product_page")
        self.assertIn("product_page", product_reasons)
        self.assertLess(product_score, 0.15)


class DirectorySeedExpansionTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_directory_seed_resolves_to_official_site(self) -> None:
        entry = SearchDiscoveryEntry(
            url="https://www.doctoralia.com/clinica-ejemplo",
            query="clinica ejemplo argentina",
            title="Clinica Ejemplo | Doctoralia",
            snippet="Reserva turno y visita el sitio web de la clinica.",
            discovery_confidence="medium",
            business_likeness_score=0.22,
            discovery_reasons=["directory_seed_candidate"],
        )

        html = _read_fixture("directory_seed_official_site.html")

        with patch("app.scraper.search_engines.ddg_search.fetch_html", new=AsyncMock(return_value=html)):
            expanded_entry, excluded = await _expand_directory_seed_entry(entry)

        self.assertIsNotNone(expanded_entry)
        assert expanded_entry is not None
        self.assertEqual(expanded_entry.url, "https://clinicaejemplo.com")
        self.assertEqual(expanded_entry.seed_source_url, "https://www.doctoralia.com/clinica-ejemplo")
        self.assertEqual(expanded_entry.seed_source_type, "directory_seed")
        self.assertIn("official_site_from_directory_seed", expanded_entry.discovery_reasons)
        self.assertIsNotNone(excluded)
        assert excluded is not None
        self.assertTrue(str(excluded["reason"]).startswith("excluded_as_directory_seed"))


class DiscoveryProviderOrchestrationTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_detects_ddg_antibot_challenge(self) -> None:
        html = '<form id="challenge-form" action="//duckduckgo.com/anomaly.js?cc=botnet"></form>'

        self.assertTrue(_detect_antibot_challenge(202, html))
        self.assertFalse(_detect_antibot_challenge(200, html))

    async def test_orchestrator_falls_back_to_next_provider(self) -> None:
        class EmptyProvider(SearchProvider):
            provider_name = "primary"
            source_type = "duckduckgo_search"

            async def search(self, queries: list[str], max_results: int = 10) -> SearchDiscoveryResult:
                return SearchDiscoveryResult(
                    entries=[],
                    source_type=self.source_type,
                    discovery_method="search_query",
                    warning_message="Primary provider blocked.",
                    queries=queries,
                    provider_name=self.provider_name,
                    provider_status="blocked",
                    failure_reason="anti_bot_challenge",
                )

        class SuccessProvider(SearchProvider):
            provider_name = "secondary"
            source_type = "brave_search"

            async def search(self, queries: list[str], max_results: int = 10) -> SearchDiscoveryResult:
                return SearchDiscoveryResult(
                    entries=[
                        SearchDiscoveryEntry(
                            url="https://academiaejemplo.com",
                            query=queries[0],
                            title="Academia Ejemplo",
                            snippet="Cursos online y contacto",
                            discovery_confidence="high",
                            business_likeness_score=0.61,
                        )
                    ],
                    source_type=self.source_type,
                    discovery_method="search_query",
                    queries=queries,
                    provider_name=self.provider_name,
                    provider_status="ok",
                )

        with patch(
            "app.services.discovery_orchestrator._build_providers",
            return_value=[EmptyProvider(), SuccessProvider()],
        ), patch(
            "app.services.discovery_orchestrator.get_settings",
            return_value=SimpleNamespace(DEMO_MODE=False),
        ):
            result = await discover_prospect_urls_by_queries(["academias online espana"], max_results=5)

        self.assertEqual(len(result.entries), 1)
        self.assertEqual(result.provider_name, "secondary")
        self.assertEqual(result.source_type, "brave_search")
        self.assertIn("Primary provider blocked.", result.warning_message or "")


if __name__ == "__main__":
    unittest.main()
