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
    find_prospect_urls_by_queries as ddg_find_prospect_urls_by_queries,
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
from app.services.discovery_ranker import classify_discovery_candidate
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

    def test_builds_social_first_queries_for_creative_roles(self) -> None:
        queries = build_discovery_queries(
            search_query="marcas personales ecommerce y coaches de negocios España",
            user_profession="Editor de Video",
            target_niche="Marcas Personales y Coaches",
            target_location="España",
            target_language="es",
            target_budget_signals=[
                "Activos en Instagram o TikTok con mas de 10k seguidores",
                "Tienen linktree/tienda oficial",
            ],
        )

        self.assertTrue(any("site:instagram.com" in query for query in queries))
        self.assertTrue(any("site:tiktok.com" in query for query in queries))
        self.assertTrue(any("link in bio" in query or "linktree" in query for query in queries))
        self.assertFalse(any("-instagram" in query or "-tiktok" in query for query in queries))
        self.assertIn("Marcas Personales España", queries)
        self.assertFalse(any(query == "Personales España" for query in queries))
        self.assertFalse(any(query == "ecommerce España" for query in queries))
        self.assertFalse(any(query == "marcas personales ecommerce y coaches de negocios España" for query in queries))

    def test_infers_location_from_search_query_and_prioritizes_niche_queries(self) -> None:
        queries = build_discovery_queries(
            search_query="marcas personales ecommerce y coaches de negocios España",
            user_profession="Editor de Video",
            target_niche="Marcas Personales y Coaches",
            target_location=None,
            target_language="es",
            target_budget_signals=[
                "Venden cursos o infoproductos",
                "Activos en Instagram o TikTok con mas de 10k seguidores",
                "Tienen linktree/tienda oficial",
            ],
        )

        self.assertEqual(queries[0], "Marcas Personales y Coaches España")
        self.assertIn("Marcas Personales España", queries[:4])
        self.assertIn("Coaches España", queries[:5])
        self.assertNotEqual(queries[0], "marcas personales ecommerce y coaches de negocios España")

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
                accepted_count=3,
                target_accepted_results=3,
                processed_count=7,
                candidate_cap=12,
                discovered_candidates=12,
                exhaustive_candidate_scan=True,
            ),
            "discovery_exhausted",
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

    def test_discovery_classifier_excludes_zhihu_reference_noise(self) -> None:
        classified = classify_discovery_candidate(
            "https://www.zhihu.com/question/375662963",
            "什么是商业教练？ - 知乎",
            "知乎问答社区",
        )

        self.assertEqual(classified["exclusion_reason"], "excluded_reference_page")

    def test_discovery_classifier_excludes_what_is_article_pages(self) -> None:
        classified = classify_discovery_candidate(
            "https://creartecoaching.com/que-es-para-que-sirve-y-como-funciona-el-coaching/",
            "¿Qué es, para qué sirve y cómo funciona el Coaching?",
            "En los últimos años el crecimiento del coaching ha sido extraordinario.",
        )

        self.assertEqual(classified["exclusion_reason"], "excluded_as_article")

    def test_discovery_classifier_excludes_pdf_documents(self) -> None:
        classified = classify_discovery_candidate(
            "http://www.escuelaeuropeadelideres.com/fotos/1415358820_2M6d.pdf",
            "Escuela Europea de Lideres PDF",
            "Descarga el brochure institucional.",
        )

        self.assertEqual(classified["exclusion_reason"], "blocked_binary_document")

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
        self.assertTrue(any(reason in {"editorial_title", "editorial_path"} for reason in report_reasons))
        self.assertLess(press_score, 0.15)
        self.assertLess(report_score, 0.15)

    def test_business_likeness_blocks_reddit_and_whatsapp_noise(self) -> None:
        whatsapp_score, whatsapp_reasons, whatsapp_exclusion = score_business_likeness(
            "https://web.whatsapp.com/",
            "WhatsApp Web",
            "Usa WhatsApp Web desde tu navegador.",
        )
        reddit_score, reddit_reasons, reddit_exclusion = score_business_likeness(
            "https://www.reddit.com/r/EveryDayBingQuiz/",
            "EveryDayBingQuiz - Reddit",
            "Subreddit con respuestas del quiz diario.",
        )

        self.assertEqual(whatsapp_exclusion, "blocked_domain:whatsapp.com")
        self.assertEqual(reddit_exclusion, "blocked_domain:reddit.com")
        self.assertIn("blocked_domain:whatsapp.com", whatsapp_reasons)
        self.assertIn("blocked_domain:reddit.com", reddit_reasons)
        self.assertLess(whatsapp_score, 0.0)
        self.assertLess(reddit_score, 0.0)

    def test_business_likeness_excludes_product_detail_pages(self) -> None:
        product_score, product_reasons, product_exclusion = score_business_likeness(
            "https://lamasbolano.com/francisco-franco-1936-1975-/10015954-espana-1974-bellas-artes-sello-correo.html",
            "Bellas Artes 1974 Espana correo",
            "Serie completa, distribuidor oficial en Espana y carrito de compra disponible.",
        )

        self.assertEqual(product_exclusion, "excluded_as_product_page")
        self.assertIn("product_page", product_reasons)
        self.assertLess(product_score, 0.15)

    def test_business_likeness_accepts_canonical_social_profiles_and_rejects_posts(self) -> None:
        social_score, social_reasons, social_exclusion = score_business_likeness(
            "https://www.instagram.com/editorpro/",
            "EditorPro | Reels para coaches y ecommerce",
            "Video editor. DM or link in bio. Servicios para marcas personales.",
            allow_social_profiles=True,
        )
        post_score, post_reasons, post_exclusion = score_business_likeness(
            "https://www.instagram.com/p/ABC123/",
            "Instagram post",
            "Reel viral de un creador.",
            allow_social_profiles=True,
        )

        self.assertIsNone(social_exclusion)
        self.assertGreater(social_score, 0.45)
        self.assertIn("social_profile_candidate", social_reasons)
        self.assertEqual(post_exclusion, "excluded_social_post")
        self.assertEqual(post_score, 0.0)
        self.assertIn("social_post_or_share", post_reasons)

    def test_business_likeness_rejects_reference_and_finance_pages(self) -> None:
        reference_score, _, reference_exclusion = score_business_likeness(
            "https://es.wikipedia.org/wiki/Reserva_de_la_biosfera",
            "Reserva de la biosfera - Wikipedia, la enciclopedia libre",
            "Articulo de referencia enciclopedica.",
        )
        finance_score, _, finance_exclusion = score_business_likeness(
            "https://www.marketwatch.com/investing/fund/gdx",
            "GDX overview by MarketWatch",
            "ETF, investing news and market data.",
        )

        self.assertEqual(reference_exclusion, "excluded_reference_page")
        self.assertEqual(finance_exclusion, "excluded_reference_page")
        self.assertEqual(reference_score, 0.0)
        self.assertEqual(finance_score, 0.0)

    def test_business_likeness_rejects_encyclopedia_and_qa_platforms(self) -> None:
        encyclopedia_score, _, encyclopedia_exclusion = score_business_likeness(
            "https://www.ecured.cu/Número_4",
            "Número 4 - EcuRed",
            "Enciclopedia colaborativa en espanol.",
        )
        qa_score, _, qa_exclusion = score_business_likeness(
            "https://zhidao.baidu.com/",
            "百度知道 - 全球领先中文互动问答平台",
            "百度知道是全球领先的中文问答互动平台。",
        )

        self.assertEqual(encyclopedia_exclusion, "excluded_reference_page")
        self.assertEqual(qa_exclusion, "excluded_reference_page")
        self.assertEqual(encyclopedia_score, 0.0)
        self.assertEqual(qa_score, 0.0)

    def test_business_likeness_rejects_search_utility_and_quiz_noise(self) -> None:
        bing_score, bing_reasons, bing_exclusion = score_business_likeness(
            "https://www.bing.com/images/feed?cc=es&setlang=es",
            "Imágenes de Bing",
            "Busca y explora fotos y fondos de pantalla gratuitos de alta calidad.",
        )
        quiz_score, quiz_reasons, quiz_exclusion = score_business_likeness(
            "https://www.quizinside.com/bing-entertainment-quiz/",
            "Bing Entertainment Quiz",
            "Discover the Bing Entertainment Quiz and daily trivia rewards.",
        )

        self.assertEqual(bing_exclusion, "blocked_domain:bing.com")
        self.assertIn("blocked_domain:bing.com", bing_reasons)
        self.assertEqual(quiz_exclusion, "excluded_reference_page")
        self.assertIn("quiz_or_trivia_noise", quiz_reasons)
        self.assertLess(bing_score, 0.0)
        self.assertEqual(quiz_score, 0.0)


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

    async def test_ddg_provider_distributes_results_across_queries(self) -> None:
        async def fake_search(query: str, max_results: int = 15, region: str = "es-es", allow_social_profiles: bool = False):
            if query == "query-a":
                return (
                    [
                        SearchDiscoveryEntry(url="https://a1.com", query=query, title="A1", snippet="Coach", business_likeness_score=0.6),
                        SearchDiscoveryEntry(url="https://a2.com", query=query, title="A2", snippet="Coach", business_likeness_score=0.55),
                        SearchDiscoveryEntry(url="https://a3.com", query=query, title="A3", snippet="Coach", business_likeness_score=0.5),
                    ],
                    [],
                    None,
                    None,
                )
            return (
                [
                    SearchDiscoveryEntry(url="https://b1.com", query=query, title="B1", snippet="Coach", business_likeness_score=0.58),
                    SearchDiscoveryEntry(url="https://b2.com", query=query, title="B2", snippet="Coach", business_likeness_score=0.53),
                ],
                [],
                None,
                None,
            )

        async def passthrough_expand(entry: SearchDiscoveryEntry, allow_social_profiles: bool = False):
            return entry, None

        with patch("app.scraper.search_engines.ddg_search._search_single_query_async", new=fake_search), patch(
            "app.scraper.search_engines.ddg_search._expand_directory_seed_entry",
            new=passthrough_expand,
        ):
            result = await ddg_find_prospect_urls_by_queries(["query-a", "query-b"], max_results=4)

        self.assertEqual([entry.url for entry in result.entries], ["https://a1.com", "https://b1.com", "https://a2.com", "https://b2.com"])


class DiscoveryProviderOrchestrationTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_detects_ddg_antibot_challenge(self) -> None:
        html = '<form id="challenge-form" action="//duckduckgo.com/anomaly.js?cc=botnet"></form>'

        self.assertTrue(_detect_antibot_challenge(202, html))
        self.assertFalse(_detect_antibot_challenge(200, html))

    async def test_orchestrator_falls_back_to_next_provider(self) -> None:
        class EmptyProvider(SearchProvider):
            provider_name = "primary"
            source_type = "duckduckgo_search"

            async def search(
                self,
                queries: list[str],
                max_results: int = 10,
                allow_social_profiles: bool = False,
            ) -> SearchDiscoveryResult:
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

            async def search(
                self,
                queries: list[str],
                max_results: int = 10,
                allow_social_profiles: bool = False,
            ) -> SearchDiscoveryResult:
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

    async def test_orchestrator_skips_off_target_english_batch_and_keeps_contextual_match(self) -> None:
        class OffTargetProvider(SearchProvider):
            provider_name = "primary"
            source_type = "duckduckgo_search"

            async def search(
                self,
                queries: list[str],
                max_results: int = 10,
                allow_social_profiles: bool = False,
            ) -> SearchDiscoveryResult:
                return SearchDiscoveryResult(
                    entries=[
                        SearchDiscoveryEntry(
                            url="https://collarsandco.com/",
                            query=queries[0],
                            title="Collars & Co. - The Original Dress Collar Polo",
                            snippet="The most comfortable polo shirt with a real English spread collar.",
                            discovery_confidence="high",
                            business_likeness_score=0.58,
                        ),
                        SearchDiscoveryEntry(
                            url="https://www.nhl.com/wild/schedule",
                            query=queries[0],
                            title="Minnesota Wild Schedule",
                            snippet="The official calendar for the Minnesota Wild including ticket information.",
                            discovery_confidence="high",
                            business_likeness_score=0.51,
                        ),
                    ],
                    source_type=self.source_type,
                    discovery_method="search_query",
                    queries=queries,
                    provider_name=self.provider_name,
                    provider_status="ok",
                )

        class ContextualProvider(SearchProvider):
            provider_name = "secondary"
            source_type = "duckduckgo_search"

            async def search(
                self,
                queries: list[str],
                max_results: int = 10,
                allow_social_profiles: bool = False,
            ) -> SearchDiscoveryResult:
                return SearchDiscoveryResult(
                    entries=[
                        SearchDiscoveryEntry(
                            url="https://joannaprieto.com/",
                            query=queries[0],
                            title="Joanna Prieto - Coaching de Marca Personal",
                            snippet="Coaching y mentoring para marcas personales.",
                            discovery_confidence="medium",
                            business_likeness_score=0.41,
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
            return_value=[OffTargetProvider(), ContextualProvider()],
        ), patch(
            "app.services.discovery_orchestrator.get_settings",
            return_value=SimpleNamespace(DEMO_MODE=False),
        ):
            result = await discover_prospect_urls_by_queries(
                ["marcas personales coaches espana"],
                max_results=5,
                user_profession="Editor de Video",
                target_niche="Marcas Personales y Coaches",
                target_language="es",
                target_location="España",
                target_budget_signals=[
                    "Venden cursos o infoproductos",
                    "Activos en Instagram o TikTok con mas de 10k seguidores",
                ],
            )

        self.assertEqual(result.provider_name, "secondary")
        self.assertEqual(len(result.entries), 1)
        self.assertEqual(result.entries[0].url, "https://joannaprieto.com/")
        self.assertTrue(any(item["reason"] == "excluded_discovery_language_mismatch" for item in result.excluded_results))

    async def test_orchestrator_excludes_cjk_results_when_target_language_is_spanish(self) -> None:
        class MixedLanguageProvider(SearchProvider):
            provider_name = "primary"
            source_type = "duckduckgo_search"

            async def search(
                self,
                queries: list[str],
                max_results: int = 10,
                allow_social_profiles: bool = False,
            ) -> SearchDiscoveryResult:
                return SearchDiscoveryResult(
                    entries=[
                        SearchDiscoveryEntry(
                            url="https://zhidao.baidu.com/",
                            query=queries[0],
                            title="百度知道 - 全球领先中文互动问答平台",
                            snippet="百度知道通过AI技术实现智能检索和智能推荐。",
                            discovery_confidence="medium",
                            business_likeness_score=0.22,
                        ),
                        SearchDiscoveryEntry(
                            url="https://joannaprieto.com/",
                            query=queries[0],
                            title="Joanna Prieto - Coaching de Marca Personal",
                            snippet="Coaching y mentoring para marcas personales.",
                            discovery_confidence="medium",
                            business_likeness_score=0.41,
                        ),
                    ],
                    source_type=self.source_type,
                    discovery_method="search_query",
                    queries=queries,
                    provider_name=self.provider_name,
                    provider_status="ok",
                )

        with patch(
            "app.services.discovery_orchestrator._build_providers",
            return_value=[MixedLanguageProvider()],
        ), patch(
            "app.services.discovery_orchestrator.get_settings",
            return_value=SimpleNamespace(DEMO_MODE=False),
        ):
            result = await discover_prospect_urls_by_queries(
                ["marcas personales coaches espana"],
                max_results=5,
                user_profession="Editor de Video",
                target_niche="Marcas Personales y Coaches",
                target_language="es",
                target_location="España",
                target_budget_signals=["Venden cursos o infoproductos"],
            )

        self.assertEqual(len(result.entries), 1)
        self.assertEqual(result.entries[0].url, "https://joannaprieto.com/")
        self.assertTrue(any(item["reason"] == "excluded_discovery_language_mismatch" for item in result.excluded_results))

    async def test_orchestrator_excludes_generic_noise_without_target_alignment(self) -> None:
        class MixedNoiseProvider(SearchProvider):
            provider_name = "primary"
            source_type = "duckduckgo_search"

            async def search(
                self,
                queries: list[str],
                max_results: int = 10,
                allow_social_profiles: bool = False,
            ) -> SearchDiscoveryResult:
                return SearchDiscoveryResult(
                    entries=[
                        SearchDiscoveryEntry(
                            url="https://www.bing.com/images/feed?cc=es&setlang=es",
                            query=queries[0],
                            title="Imágenes de Bing",
                            snippet="Busca y explora fotos y fondos de pantalla gratuitos de alta calidad.",
                            discovery_confidence="medium",
                            business_likeness_score=0.18,
                        ),
                        SearchDiscoveryEntry(
                            url="https://coachjuan.es/",
                            query=queries[0],
                            title="Coach de negocios en España | Mentor de emprendedores",
                            snippet="Programa, mentoría, instagram e infoproductos para marcas personales.",
                            discovery_confidence="medium",
                            business_likeness_score=0.48,
                        ),
                    ],
                    source_type=self.source_type,
                    discovery_method="search_query",
                    queries=queries,
                    provider_name=self.provider_name,
                    provider_status="ok",
                )

        with patch(
            "app.services.discovery_orchestrator._build_providers",
            return_value=[MixedNoiseProvider()],
        ), patch(
            "app.services.discovery_orchestrator.get_settings",
            return_value=SimpleNamespace(DEMO_MODE=False),
        ):
            result = await discover_prospect_urls_by_queries(
                ["marcas personales coaches espana"],
                max_results=5,
                user_profession="Editor de Video",
                target_niche="Marcas Personales y Coaches",
                target_language="es",
                target_location="España",
                target_budget_signals=[
                    "Venden cursos o infoproductos",
                    "Activos en Instagram o TikTok con mas de 10k seguidores",
                ],
            )

        self.assertEqual(len(result.entries), 1)
        self.assertEqual(result.entries[0].url, "https://coachjuan.es/")

    async def test_orchestrator_overfetches_before_context_filtering(self) -> None:
        observed_limits: list[int] = []

        class TrackingProvider(SearchProvider):
            provider_name = "primary"
            source_type = "duckduckgo_search"

            async def search(
                self,
                queries: list[str],
                max_results: int = 10,
                allow_social_profiles: bool = False,
            ) -> SearchDiscoveryResult:
                observed_limits.append(max_results)
                return SearchDiscoveryResult(
                    entries=[
                        SearchDiscoveryEntry(
                            url="https://coachfinal.es/",
                            query=queries[0],
                            title="Coach final en España",
                            snippet="Programa y mentoría para marcas personales.",
                            discovery_confidence="high",
                            business_likeness_score=0.55,
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
            return_value=[TrackingProvider()],
        ), patch(
            "app.services.discovery_orchestrator.get_settings",
            return_value=SimpleNamespace(DEMO_MODE=False),
        ):
            result = await discover_prospect_urls_by_queries(
                ["marcas personales coaches espana"],
                max_results=5,
                user_profession="Editor de Video",
                target_niche="Marcas Personales y Coaches",
                target_language="es",
                target_location="España",
            )

        self.assertEqual(result.entries[0].url, "https://coachfinal.es/")
        self.assertTrue(observed_limits)
        self.assertGreater(observed_limits[0], 5)


if __name__ == "__main__":
    unittest.main()
