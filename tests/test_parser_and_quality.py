import unittest

from app.scraper.parser import parse_html_basic
from app.services.prospect_quality import build_ai_evidence_pack, evaluate_prospect_quality


class ParserAndQualityTestCase(unittest.TestCase):
    def test_parser_extracts_structured_fields_and_ctas(self) -> None:
        html = """
        <html lang="es">
          <head>
            <title>Clinica Dental Madrid Centro</title>
            <meta name="description" content="Clinica dental en Madrid con reservas online" />
            <meta property="og:locale" content="es_ES" />
            <script type="application/ld+json">
              {
                "@context": "https://schema.org",
                "@type": "Dentist",
                "address": {
                  "streetAddress": "Calle Mayor 1",
                  "addressLocality": "Madrid",
                  "addressCountry": "ES"
                },
                "telephone": "+34 911 111 111",
                "email": "hola@clinicamadrid.es"
              }
            </script>
          </head>
          <body>
            <a href="/contacto">Contacto</a>
            <a href="/reservas">Reserva tu cita</a>
            <a href="/precios">Precios</a>
            <a href="https://wa.me/34111111111">WhatsApp</a>
            <a href="https://google.com/maps?q=Clinica+Madrid">Mapa</a>
            <form action="/send"></form>
          </body>
        </html>
        """

        clean_text, metadata = parse_html_basic(html, "https://clinicamadrid.es")

        self.assertEqual(metadata["description"], "Clinica dental en Madrid con reservas online")
        self.assertEqual(metadata["html_lang"], "es")
        self.assertEqual(metadata["meta_locale"], "es_es")
        self.assertEqual(metadata["booking_url"], "https://clinicamadrid.es/reservas")
        self.assertEqual(metadata["pricing_page_url"], "https://clinicamadrid.es/precios")
        self.assertEqual(metadata["whatsapp_url"], "https://wa.me/34111111111")
        self.assertTrue(metadata["form_detected"])
        self.assertIn("structured_address_detected", metadata["structured_data_evidence"])
        self.assertIn("+34911111111", metadata["phones"])
        self.assertIn("hola@clinicamadrid.es", metadata["emails"])
        self.assertTrue(any("Madrid" in address for address in metadata["addresses"]))

    def test_quality_marks_geo_match_and_builds_compact_pack(self) -> None:
        clean_text = (
            "Clinica dental en Madrid con servicios de implantes, ortodoncia y reservas online. "
            "Agenda tu cita hoy mismo."
        )
        metadata = {
            "title": "Clinica Dental Madrid",
            "description": "Clinica dental en Madrid",
            "html_lang": "es",
            "meta_locale": "es_es",
            "emails": ["hola@clinicamadrid.es"],
            "phones": ["+34911111111"],
            "social_links": [],
            "internal_links": ["https://clinicamadrid.es/contacto"],
            "map_links": ["https://google.com/maps?q=Madrid"],
            "addresses": ["Calle Mayor 1, Madrid, ES"],
            "form_detected": True,
            "whatsapp_url": "https://wa.me/34111111111",
            "booking_url": "https://clinicamadrid.es/reservas",
            "pricing_page_url": "https://clinicamadrid.es/precios",
            "service_page_url": "https://clinicamadrid.es/servicios",
            "structured_data": [{"@type": "Dentist"}],
            "structured_data_evidence": ["json_ld_detected", "structured_address_detected"],
            "contact_channels": [{"type": "email", "value": "hola@clinicamadrid.es"}],
            "cta_candidates": ["booking"],
            "primary_cta": "booking",
        }
        heuristic_data = {
            "score": 0.72,
            "confidence_level": "medium",
            "inferred_niche": "Dental",
            "inferred_tech_stack": ["WordPress"],
            "generic_attributes": {"pain_points_detected": ["Sin CTA clara"]},
            "hiring_signals": False,
        }

        quality = evaluate_prospect_quality(
            clean_text=clean_text,
            metadata=metadata,
            context={"target_location": "Madrid", "target_language": "es"},
            heuristic_data=heuristic_data,
            discovery_metadata={"query": "clinicas dentales madrid", "title": "Clinica Madrid"},
        )

        self.assertEqual(quality["location_match_status"], "match")
        self.assertEqual(quality["quality_status"], "accepted")
        self.assertEqual(quality["detected_language"], "es")
        self.assertEqual(quality["primary_cta"], "booking")
        self.assertGreaterEqual(quality["contact_quality_score"], 0.6)

        evidence_pack = build_ai_evidence_pack(
            domain="clinicamadrid.es",
            clean_text=clean_text,
            metadata=metadata,
            heuristic_data=heuristic_data,
            quality_data=quality,
            discovery_metadata=quality["discovery_evidence"],
        )
        self.assertIn("Madrid", evidence_pack["validated_location"])
        self.assertEqual(evidence_pack["primary_cta"], "booking")
        self.assertIn("implantes", evidence_pack["service_keywords"])

    def test_parser_does_not_treat_gumroad_as_address(self) -> None:
        html = """
        <html lang="es">
          <head>
            <title>Ideas de negocio para disenadores</title>
            <meta name="description" content="Articulo sobre negocio digital para disenadores" />
          </head>
          <body>
            <p>Gumroad ofrece un enfoque mas directo para vender productos digitales.</p>
            <p>Tambien puedes usar Etsy o tu propia web.</p>
          </body>
        </html>
        """

        _, metadata = parse_html_basic(html, "https://example.com")

        self.assertEqual(metadata["addresses"], [])

    def test_quality_uses_unknown_when_geo_evidence_is_weak(self) -> None:
        clean_text = "Articulo sobre productos digitales y oportunidades de negocio."
        metadata = {
            "title": "Ideas de negocio para disenadores",
            "description": "Articulo sobre negocio digital para disenadores",
            "html_lang": "es",
            "meta_locale": "es_es",
            "emails": ["hola@example.com"],
            "phones": [],
            "social_links": [],
            "internal_links": [],
            "map_links": [],
            "addresses": [],
            "form_detected": True,
            "whatsapp_url": None,
            "booking_url": None,
            "pricing_page_url": None,
            "service_page_url": None,
            "structured_data": [],
            "structured_data_evidence": [],
            "contact_channels": [{"type": "email", "value": "hola@example.com"}],
            "cta_candidates": ["contact_form"],
            "primary_cta": "contact_form",
        }
        heuristic_data = {
            "score": 0.61,
            "confidence_level": "medium",
            "inferred_niche": "Diseno",
            "inferred_tech_stack": ["WordPress"],
            "generic_attributes": {"pain_points_detected": []},
            "hiring_signals": False,
        }

        quality = evaluate_prospect_quality(
            clean_text=clean_text,
            metadata=metadata,
            context={"target_location": "Argentina", "target_language": "es"},
            heuristic_data=heuristic_data,
            discovery_metadata={
                "query": "disenadores argentina",
                "title": "Ideas de negocio para disenadores",
                "snippet": "Gumroad ofrece un enfoque mas directo para vender productos digitales.",
            },
        )

        self.assertEqual(quality["location_match_status"], "unknown")
        self.assertEqual(quality["quality_status"], "needs_review")
        self.assertIsNone(quality["validated_location"])


if __name__ == "__main__":
    unittest.main()
