import unittest

from app.scraper.parser import parse_html_basic
from app.services.entity_classifier import classify_entity_type
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
            "website_url": "https://clinicamadrid.es",
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
            entity_data=classify_entity_type(
                target_url="https://clinicamadrid.es",
                clean_text=clean_text,
                metadata=metadata,
                discovery_metadata={"query": "clinicas dentales madrid", "title": "Clinica Madrid"},
            ),
        )

        self.assertEqual(quality["location_match_status"], "match")
        self.assertEqual(quality["location"], "Madrid, España")
        self.assertEqual(quality["raw_location_text"], "Calle Mayor 1, Madrid, ES")
        self.assertEqual(quality["parsed_location"]["city"], "Madrid")
        self.assertEqual(quality["parsed_location"]["country"], "España")
        self.assertEqual(quality["quality_status"], "accepted")
        self.assertEqual(quality["acceptance_decision"], "accepted_target")
        self.assertEqual(quality["contact_consistency_status"], "consistent")
        self.assertEqual(quality["primary_email_confidence"], "high")
        self.assertEqual(quality["primary_phone_confidence"], "high")
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

    def test_parser_rejects_phone_like_dates_and_sequences(self) -> None:
        html = """
        <html>
          <body>
            <p>Fecha de actualizacion: 2026-03-11</p>
            <p>Telefono falso: 12345678</p>
            <p>Secuencia: 999999999</p>
            <a href="tel:+34 911 111 111">Llamanos</a>
          </body>
        </html>
        """

        _, metadata = parse_html_basic(html, "https://clinicamadrid.es")

        self.assertEqual(metadata["phones"], ["+34911111111"])
        self.assertEqual(metadata["invalid_phone_candidates_count"], 3)
        self.assertEqual(metadata["phone_validation_rejections"]["date_like"], 1)
        self.assertEqual(metadata["phone_validation_rejections"]["sequence_noise"], 2)

    def test_quality_flags_external_email_domains_as_inconsistent(self) -> None:
        clean_text = "Clinica dental con formulario de contacto y CTA para reservar."
        metadata = {
            "website_url": "https://clinicamadrid.es",
            "title": "Clinica Dental Madrid",
            "description": "Clinica dental en Madrid",
            "html_lang": "es",
            "meta_locale": "es_es",
            "emails": ["ventas@partner-leads.com"],
            "phones": [],
            "social_links": [],
            "internal_links": ["https://clinicamadrid.es/contacto"],
            "map_links": [],
            "addresses": [],
            "form_detected": True,
            "whatsapp_url": None,
            "booking_url": None,
            "pricing_page_url": None,
            "service_page_url": "https://clinicamadrid.es/servicios",
            "structured_data": [{"@type": "Dentist"}],
            "structured_data_evidence": ["json_ld_detected"],
            "contact_channels": [{"type": "email", "value": "ventas@partner-leads.com", "source": "mailto_link"}],
            "cta_candidates": ["contact_form"],
            "primary_cta": "contact_form",
        }
        heuristic_data = {
            "score": 0.72,
            "confidence_level": "medium",
            "inferred_niche": "Dental",
            "inferred_tech_stack": ["WordPress"],
            "generic_attributes": {"pain_points_detected": []},
            "hiring_signals": False,
        }

        quality = evaluate_prospect_quality(
            clean_text=clean_text,
            metadata=metadata,
            context={"target_language": "es"},
            heuristic_data=heuristic_data,
            discovery_metadata={"query": "clinicas dentales madrid", "title": "Clinica Madrid"},
            entity_data=classify_entity_type(
                target_url="https://clinicamadrid.es",
                clean_text=clean_text,
                metadata=metadata,
                discovery_metadata={"query": "clinicas dentales madrid", "title": "Clinica Madrid"},
            ),
        )

        self.assertEqual(quality["contact_consistency_status"], "inconsistent")
        self.assertIsNone(quality["email"])
        self.assertEqual(quality["primary_email_confidence"], "low")
        self.assertEqual(quality["quality_status"], "needs_review")
        self.assertEqual(quality["rejection_reason"], "contact_inconsistent")

    def test_quality_demotes_direct_business_when_target_niche_fit_is_low(self) -> None:
        clean_text = "Portal educativo con recursos, contacto y publicaciones para docentes."
        metadata = {
            "website_url": "https://orientacionandujar.es",
            "title": "Orientacion Andujar",
            "description": "Recursos educativos y orientacion",
            "html_lang": "es",
            "meta_locale": "es_es",
            "emails": ["contacto@orientacionandujar.es"],
            "phones": ["+34911111111"],
            "social_links": [],
            "internal_links": ["https://orientacionandujar.es/contacto", "https://orientacionandujar.es/nosotros"],
            "map_links": [],
            "addresses": ["Madrid, ES"],
            "form_detected": True,
            "whatsapp_url": None,
            "booking_url": None,
            "pricing_page_url": None,
            "service_page_url": None,
            "structured_data": [{"@type": "Organization"}],
            "structured_data_evidence": ["json_ld_detected"],
            "contact_channels": [{"type": "email", "value": "contacto@orientacionandujar.es", "source": "mailto_link"}],
            "cta_candidates": ["contact_form"],
            "primary_cta": "contact_form",
        }
        heuristic_data = {
            "score": 0.68,
            "confidence_level": "medium",
            "inferred_niche": "Servicios profesionales",
            "inferred_tech_stack": ["WordPress"],
            "generic_attributes": {
                "pain_points_detected": [],
                "heuristic_score_breakdown": {"context_fit": 0.1},
            },
            "heuristic_trace": {"component_scores": {"context_fit": 0.1}},
            "hiring_signals": False,
        }

        quality = evaluate_prospect_quality(
            clean_text=clean_text,
            metadata=metadata,
            context={
                "target_language": "es",
                "target_location": "España",
                "target_niche": "Ecommerce y academias online",
            },
            heuristic_data=heuristic_data,
            discovery_metadata={"query": "empresas ecommerce y academias online España", "title": "Orientacion Andujar"},
            entity_data={
                "entity_type_detected": "direct_business",
                "entity_type_confidence": "high",
                "entity_type_evidence": {},
                "is_target_entity": True,
            },
        )

        self.assertEqual(quality["quality_status"], "accepted")
        self.assertEqual(quality["acceptance_decision"], "accepted_related")
        self.assertEqual(quality["context_fit_score"], 0.1)

    def test_quality_demotes_consultant_when_target_requires_seller_or_academy_model(self) -> None:
        clean_text = "Asesoria y consultoria para ecommerce con presupuesto y servicios para empresas."
        metadata = {
            "website_url": "https://asesoriaecommerce.es",
            "title": "Asesoria y Consultoria para eCommerce y tiendas online",
            "description": "Servicios de asesoria ecommerce para autonomos y empresas.",
            "html_lang": "es",
            "meta_locale": "es_es",
            "emails": ["info@asesoriaecommerce.es"],
            "phones": ["+34911111111"],
            "social_links": [],
            "internal_links": ["https://asesoriaecommerce.es/contacto", "https://asesoriaecommerce.es/servicios"],
            "map_links": [],
            "addresses": ["España"],
            "form_detected": True,
            "whatsapp_url": None,
            "booking_url": None,
            "pricing_page_url": None,
            "service_page_url": "https://asesoriaecommerce.es/servicios",
            "structured_data": [],
            "structured_data_evidence": [],
            "contact_channels": [{"type": "email", "value": "info@asesoriaecommerce.es", "source": "mailto_link"}],
            "cta_candidates": ["quote"],
            "primary_cta": "quote",
        }
        heuristic_data = {
            "score": 0.72,
            "confidence_level": "high",
            "inferred_niche": "Consultoria",
            "inferred_tech_stack": ["WordPress"],
            "generic_attributes": {
                "pain_points_detected": [],
                "heuristic_score_breakdown": {"context_fit": 0.6},
            },
            "heuristic_trace": {"component_scores": {"context_fit": 0.6}},
            "hiring_signals": False,
        }

        quality = evaluate_prospect_quality(
            clean_text=clean_text,
            metadata=metadata,
            context={
                "target_language": "es",
                "target_location": "España",
                "target_niche": "Ecommerce y academias online",
                "user_target_offer_focus": "Negocios que vendan productos digitales o hagan ecommerce",
            },
            heuristic_data=heuristic_data,
            discovery_metadata={"query": "empresas ecommerce y academias online España", "title": "Asesoria Ecommerce"},
            entity_data={
                "entity_type_detected": "consultant",
                "entity_type_confidence": "high",
                "entity_type_evidence": {},
                "is_target_entity": True,
            },
        )

        self.assertEqual(quality["quality_status"], "accepted")
        self.assertEqual(quality["observed_business_model"], "service_provider")
        self.assertEqual(quality["business_model_fit_status"], "mismatch")
        self.assertEqual(quality["acceptance_decision"], "accepted_related")

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
            entity_data=classify_entity_type(
                target_url="https://example.com/blog/ideas-negocio",
                clean_text=clean_text,
                metadata=metadata,
                discovery_metadata={
                    "query": "disenadores argentina",
                    "title": "Ideas de negocio para disenadores",
                    "snippet": "Gumroad ofrece un enfoque mas directo para vender productos digitales.",
                },
            ),
        )

        self.assertEqual(quality["location_match_status"], "unknown")
        self.assertEqual(quality["quality_status"], "needs_review")
        self.assertEqual(quality["acceptance_decision"], "rejected_article")
        self.assertIsNone(quality["location"])
        self.assertIsNone(quality["validated_location"])

    def test_quality_uses_tld_phone_and_area_served_as_geo_signals(self) -> None:
        clean_text = "Clinica con reservas online y contacto por telefono."
        metadata = {
            "title": "Clinica Ejemplo",
            "description": "Clinica dental con area de servicio en Argentina",
            "html_lang": "es",
            "meta_locale": "es_ar",
            "emails": ["hola@clinicaejemplo.com.ar"],
            "phones": ["+541144445555"],
            "social_links": [],
            "internal_links": [],
            "map_links": [],
            "addresses": [],
            "form_detected": True,
            "whatsapp_url": None,
            "booking_url": None,
            "pricing_page_url": None,
            "service_page_url": None,
            "structured_data": [
                {"@type": "Dentist", "areaServed": {"name": "Argentina"}},
            ],
            "structured_data_evidence": ["json_ld_detected"],
            "contact_channels": [{"type": "phone", "value": "+541144445555"}],
            "cta_candidates": ["contact_form"],
            "primary_cta": "contact_form",
            "website_url": "https://clinicaejemplo.com.ar",
        }
        heuristic_data = {
            "score": 0.63,
            "confidence_level": "medium",
            "inferred_niche": "Dental",
            "inferred_tech_stack": ["WordPress"],
            "generic_attributes": {"pain_points_detected": []},
            "hiring_signals": False,
        }

        quality = evaluate_prospect_quality(
            clean_text=clean_text,
            metadata=metadata,
            context={"target_location": "Argentina", "target_language": "es"},
            heuristic_data=heuristic_data,
            discovery_metadata={"query": "clinicas argentina", "title": "Clinica Ejemplo"},
            entity_data=classify_entity_type(
                target_url="https://clinicaejemplo.com.ar",
                clean_text=clean_text,
                metadata=metadata,
                discovery_metadata={"query": "clinicas argentina", "title": "Clinica Ejemplo"},
            ),
        )

        self.assertEqual(quality["location_match_status"], "match")
        self.assertIn(quality["location_confidence"], {"high", "medium"})
        self.assertTrue(
            any(item["source"] in {"area_served", "phone_prefix", "tld"} for item in quality["geo_evidence"])
        )

    def test_quality_uses_postal_address_country_code_as_geo_signal(self) -> None:
        clean_text = "Clinica con reservas online y formulario de contacto."
        metadata = {
            "title": "Clinica Ejemplo",
            "description": "Clinica dental",
            "html_lang": "es",
            "meta_locale": "es_es",
            "emails": ["hola@clinicaejemplo.es"],
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
            "structured_data": [
                {"@type": "Dentist", "address": {"addressCountry": "ES"}},
            ],
            "structured_data_evidence": ["json_ld_detected"],
            "contact_channels": [{"type": "email", "value": "hola@clinicaejemplo.es"}],
            "cta_candidates": ["contact_form"],
            "primary_cta": "contact_form",
            "website_url": "https://clinicaejemplo.com",
        }
        heuristic_data = {
            "score": 0.63,
            "confidence_level": "medium",
            "inferred_niche": "Dental",
            "inferred_tech_stack": ["WordPress"],
            "generic_attributes": {"pain_points_detected": []},
            "hiring_signals": False,
        }

        quality = evaluate_prospect_quality(
            clean_text=clean_text,
            metadata=metadata,
            context={"target_location": "España", "target_language": "es"},
            heuristic_data=heuristic_data,
            discovery_metadata={"query": "clinicas espana", "title": "Clinica Ejemplo"},
            entity_data=classify_entity_type(
                target_url="https://clinicaejemplo.com",
                clean_text=clean_text,
                metadata=metadata,
                discovery_metadata={"query": "clinicas espana", "title": "Clinica Ejemplo"},
            ),
        )

        self.assertEqual(quality["location_match_status"], "match")
        self.assertTrue(
            any(item["source"] == "postal_address_country" for item in quality["geo_evidence"])
        )

    def test_quality_uses_tld_and_phone_prefix_for_bolivia_without_title_match(self) -> None:
        clean_text = "Clinica con reservas online y contacto por telefono."
        metadata = {
            "title": "Clinica Ejemplo",
            "description": "Clinica dental",
            "html_lang": "es",
            "meta_locale": "es_bo",
            "emails": ["hola@clinicaejemplo.com.bo"],
            "phones": ["+59171234567"],
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
            "contact_channels": [{"type": "phone", "value": "+59171234567"}],
            "cta_candidates": ["contact_form"],
            "primary_cta": "contact_form",
            "website_url": "https://clinicaejemplo.com.bo",
        }
        heuristic_data = {
            "score": 0.63,
            "confidence_level": "medium",
            "inferred_niche": "Dental",
            "inferred_tech_stack": ["WordPress"],
            "generic_attributes": {"pain_points_detected": []},
            "hiring_signals": False,
        }

        quality = evaluate_prospect_quality(
            clean_text=clean_text,
            metadata=metadata,
            context={"target_location": "Bolivia", "target_language": "es"},
            heuristic_data=heuristic_data,
            discovery_metadata={"query": "clinicas bolivia", "title": "Clinica Ejemplo"},
            entity_data=classify_entity_type(
                target_url="https://clinicaejemplo.com.bo",
                clean_text=clean_text,
                metadata=metadata,
                discovery_metadata={"query": "clinicas bolivia", "title": "Clinica Ejemplo"},
            ),
        )

        self.assertEqual(quality["location_match_status"], "match")
        self.assertTrue(
            any(item["source"] in {"phone_prefix", "tld"} for item in quality["geo_evidence"])
        )
        self.assertEqual(quality["location"], "Bolivia")
        self.assertEqual(quality["validated_location"], "Bolivia")
        self.assertEqual(quality["parsed_location"]["country"], "Bolivia")

    def test_quality_keeps_visible_location_normalized_without_target_geo(self) -> None:
        clean_text = "Clinica dental con reservas online y formulario de contacto."
        metadata = {
            "website_url": "https://clinicamadrid.es",
            "title": "Clinica Dental Madrid",
            "description": "Clinica dental en Madrid",
            "html_lang": "es",
            "meta_locale": "es_es",
            "emails": ["hola@clinicamadrid.es"],
            "phones": ["+34911111111"],
            "social_links": [],
            "internal_links": ["https://clinicamadrid.es/contacto"],
            "map_links": ["https://google.com/maps?q=Madrid"],
            "addresses": ["Calle Mayor 1, 28013 Madrid, ES"],
            "form_detected": True,
            "whatsapp_url": None,
            "booking_url": "https://clinicamadrid.es/reservas",
            "pricing_page_url": None,
            "service_page_url": None,
            "structured_data": [
                {
                    "@type": "Dentist",
                    "address": {
                        "streetAddress": "Calle Mayor 1",
                        "postalCode": "28013",
                        "addressLocality": "Madrid",
                        "addressCountry": "ES",
                    },
                }
            ],
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
            "generic_attributes": {"pain_points_detected": []},
            "hiring_signals": False,
        }

        quality = evaluate_prospect_quality(
            clean_text=clean_text,
            metadata=metadata,
            context={"target_language": "es"},
            heuristic_data=heuristic_data,
            discovery_metadata={"query": "clinicas madrid", "title": "Clinica Madrid"},
            entity_data=classify_entity_type(
                target_url="https://clinicamadrid.es",
                clean_text=clean_text,
                metadata=metadata,
                discovery_metadata={"query": "clinicas madrid", "title": "Clinica Madrid"},
            ),
        )

        self.assertEqual(quality["location"], "28013 Madrid, España")
        self.assertEqual(quality["raw_location_text"], "Calle Mayor 1, 28013 Madrid, ES")
        self.assertEqual(quality["parsed_location"]["postal_code"], "28013")
        self.assertEqual(quality["parsed_location"]["city"], "Madrid")
        self.assertEqual(quality["parsed_location"]["country"], "España")
        self.assertIsNone(quality["validated_location"])
        self.assertEqual(quality["location_match_status"], "unknown")


if __name__ == "__main__":
    unittest.main()
