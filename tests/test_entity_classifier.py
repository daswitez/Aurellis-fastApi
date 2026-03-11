import unittest

from app.services.entity_classifier import classify_entity_type
from app.services.prospect_quality import evaluate_prospect_quality


class EntityClassifierTestCase(unittest.TestCase):
    def test_classifies_direct_business_as_target(self) -> None:
        clean_text = "Clinica dental en Madrid con implantes, ortodoncia y reserva de citas online."
        metadata = {
            "website_url": "https://clinicamadrid.es",
            "title": "Clinica Dental Madrid",
            "description": "Clinica dental con reservas online",
            "emails": ["hola@clinicamadrid.es"],
            "phones": ["+34911111111"],
            "addresses": ["Calle Mayor 1, Madrid, ES"],
            "map_links": ["https://maps.example/madrid"],
            "internal_links": [
                "https://clinicamadrid.es/contacto",
                "https://clinicamadrid.es/servicios",
                "https://clinicamadrid.es/nosotros",
                "https://clinicamadrid.es/reservas",
            ],
            "structured_data": [{"@type": "Dentist"}],
            "form_detected": True,
            "booking_url": "https://clinicamadrid.es/reservas",
            "pricing_page_url": None,
        }

        result = classify_entity_type(
            target_url="https://clinicamadrid.es",
            clean_text=clean_text,
            metadata=metadata,
            discovery_metadata={"title": "Clinica Dental Madrid", "snippet": "Sitio oficial"},
        )

        self.assertEqual(result["entity_type_detected"], "direct_business")
        self.assertTrue(result["is_target_entity"])
        self.assertIn(result["entity_type_confidence"], {"medium", "high"})

    def test_classifies_directory_as_non_target(self) -> None:
        clean_text = "Directorio de clinicas dentales en Madrid para comparar opciones."
        metadata = {
            "website_url": "https://example.com/directorio/clinicas-dentales-madrid",
            "title": "Directorio de Clinicas Dentales en Madrid",
            "description": "Encuentra y compara clinicas dentales en Madrid",
            "emails": [],
            "phones": [],
            "addresses": [],
            "map_links": [],
            "internal_links": [
                "https://example.com/directorio",
                "https://example.com/compare",
            ],
            "structured_data": [{"@type": "ItemList"}],
            "form_detected": False,
            "booking_url": None,
            "pricing_page_url": None,
        }

        result = classify_entity_type(
            target_url="https://example.com/directorio/clinicas-dentales-madrid",
            clean_text=clean_text,
            metadata=metadata,
            discovery_metadata={"title": "Directorio dental", "snippet": "Encuentra y compara"},
        )

        self.assertEqual(result["entity_type_detected"], "directory")
        self.assertFalse(result["is_target_entity"])
        self.assertIn("directory", result["entity_type_evidence"]["score_by_entity_type"])

    def test_quality_moves_non_target_entity_out_of_accepted(self) -> None:
        clean_text = "Top 10 clinicas dentales en Madrid para comparar precios y opiniones."
        metadata = {
            "website_url": "https://example.com/blog/top-10-clinicas-dentales",
            "title": "Top 10 Clinicas Dentales en Madrid",
            "description": "Comparativa de clinicas dentales",
            "html_lang": "es",
            "meta_locale": "es_es",
            "emails": ["editor@example.com"],
            "phones": [],
            "social_links": [],
            "internal_links": ["https://example.com/blog", "https://example.com/contacto"],
            "map_links": [],
            "addresses": [],
            "form_detected": True,
            "whatsapp_url": None,
            "booking_url": None,
            "pricing_page_url": None,
            "service_page_url": None,
            "structured_data": [{"@type": "BlogPosting"}],
            "structured_data_evidence": ["json_ld_detected"],
            "contact_channels": [{"type": "email", "value": "editor@example.com"}],
            "cta_candidates": ["contact_form"],
            "primary_cta": "contact_form",
        }
        heuristic_data = {
            "score": 0.62,
            "confidence_level": "medium",
            "inferred_niche": "Dental",
            "inferred_tech_stack": ["WordPress"],
            "generic_attributes": {"pain_points_detected": []},
            "hiring_signals": False,
        }
        entity_data = classify_entity_type(
            target_url="https://example.com/blog/top-10-clinicas-dentales",
            clean_text=clean_text,
            metadata=metadata,
            discovery_metadata={"query": "clinicas dentales madrid", "title": "Top 10 Clinicas Dentales"},
        )

        quality = evaluate_prospect_quality(
            clean_text=clean_text,
            metadata=metadata,
            context={"target_language": "es"},
            heuristic_data=heuristic_data,
            discovery_metadata={"query": "clinicas dentales madrid", "title": "Top 10 Clinicas Dentales"},
            entity_data=entity_data,
        )

        self.assertFalse(quality["is_target_entity"])
        self.assertEqual(quality["quality_status"], "accepted")
        self.assertEqual(quality["acceptance_decision"], "rejected_article")


if __name__ == "__main__":
    unittest.main()
