from pathlib import Path
import unittest

from app.scraper.parser import parse_html_basic
from app.services.entity_classifier import classify_entity_type
from app.services.prospect_quality import evaluate_prospect_quality


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "commercial"


def _read_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def _default_heuristic_data() -> dict:
    return {
        "score": 0.72,
        "confidence_level": "medium",
        "inferred_niche": "Dental",
        "inferred_tech_stack": ["WordPress"],
        "generic_attributes": {"pain_points_detected": []},
        "hiring_signals": False,
    }


def _run_fixture(
    fixture_name: str,
    *,
    target_url: str,
    context: dict | None = None,
    discovery_metadata: dict | None = None,
) -> tuple[dict, dict]:
    html = _read_fixture(fixture_name)
    clean_text, metadata = parse_html_basic(html, target_url)
    metadata["website_url"] = target_url
    entity_data = classify_entity_type(
        target_url=target_url,
        clean_text=clean_text,
        metadata=metadata,
        discovery_metadata=discovery_metadata or {"title": metadata.get("title")},
    )
    quality = evaluate_prospect_quality(
        clean_text=clean_text,
        metadata=metadata,
        context=context or {"target_language": "es", "target_location": "Madrid"},
        heuristic_data=_default_heuristic_data(),
        discovery_metadata=discovery_metadata or {"title": metadata.get("title")},
        entity_data=entity_data,
    )
    return metadata, quality


class CommercialFixturesTestCase(unittest.TestCase):
    def test_real_business_fixture_is_accepted_target(self) -> None:
        metadata, quality = _run_fixture(
            "direct_business_clinic.html",
            target_url="https://sonrisamadrid.es",
            discovery_metadata={"query": "clinicas dentales madrid", "title": "Clinica Dental Sonrisa Madrid"},
        )

        self.assertEqual(quality["entity_type_detected"], "direct_business")
        self.assertTrue(quality["is_target_entity"])
        self.assertEqual(quality["acceptance_decision"], "accepted_target")
        self.assertEqual(quality["contact_consistency_status"], "consistent")
        self.assertIn("+34911111111", metadata["phones"])

    def test_directory_fixture_is_rejected_as_directory(self) -> None:
        _, quality = _run_fixture(
            "directory_listing.html",
            target_url="https://example.com/directorio/clinicas-dentales-madrid",
            discovery_metadata={"title": "Directorio de Clinicas Dentales en Madrid"},
        )

        self.assertEqual(quality["entity_type_detected"], "directory")
        self.assertFalse(quality["is_target_entity"])
        self.assertEqual(quality["acceptance_decision"], "rejected_directory")

    def test_aggregator_fixture_is_not_accepted_as_target(self) -> None:
        _, quality = _run_fixture(
            "aggregator_compare.html",
            target_url="https://compare.example.com/ranking/mejores-clinicas-dentales-madrid",
            discovery_metadata={"title": "Mejores Clinicas Dentales en Madrid"},
        )

        self.assertEqual(quality["entity_type_detected"], "aggregator")
        self.assertFalse(quality["is_target_entity"])
        self.assertEqual(quality["acceptance_decision"], "rejected_directory")

    def test_media_fixture_is_rejected_as_media(self) -> None:
        _, quality = _run_fixture(
            "media_home.html",
            target_url="https://revistadentalnews.com",
            context={"target_language": "es"},
            discovery_metadata={"title": "Revista Dental Hoy"},
        )

        self.assertEqual(quality["entity_type_detected"], "media")
        self.assertFalse(quality["is_target_entity"])
        self.assertEqual(quality["acceptance_decision"], "rejected_media")

    def test_association_fixture_is_rejected_as_non_target(self) -> None:
        _, quality = _run_fixture(
            "association_listing.html",
            target_url="https://asociaciondentalmadrid.org",
            context={"target_language": "es"},
            discovery_metadata={"title": "Asociacion de Clinicas Dentales de Madrid"},
        )

        self.assertEqual(quality["entity_type_detected"], "association")
        self.assertFalse(quality["is_target_entity"])
        self.assertEqual(quality["acceptance_decision"], "rejected_media")

    def test_inconsistent_contact_fixture_is_flagged(self) -> None:
        _, quality = _run_fixture(
            "inconsistent_contact.html",
            target_url="https://sonrisamadrid.es",
            discovery_metadata={"query": "clinicas dentales madrid", "title": "Clinica Dental Sonrisa Madrid"},
        )

        self.assertEqual(quality["entity_type_detected"], "direct_business")
        self.assertEqual(quality["contact_consistency_status"], "inconsistent")
        self.assertEqual(quality["quality_status"], "needs_review")
        self.assertEqual(quality["rejection_reason"], "contact_inconsistent")
        self.assertIsNone(quality["email"])

    def test_contaminated_location_fixture_keeps_only_normalized_visible_location(self) -> None:
        _, quality = _run_fixture(
            "contaminated_location.html",
            target_url="https://sonrisamadrid.es",
            context={"target_language": "es"},
            discovery_metadata={"query": "clinicas madrid", "title": "Clinica Dental Sonrisa Madrid"},
        )

        self.assertEqual(quality["raw_location_text"], "Calle Mayor 1, Madrid, 28013, ES")
        self.assertEqual(quality["location"], "28013 Madrid, España")
        self.assertEqual(quality["parsed_location"]["postal_code"], "28013")
        self.assertEqual(quality["parsed_location"]["city"], "Madrid")
        self.assertIsNone(quality["validated_location"])

    def test_false_phone_fixture_tracks_filtered_noise(self) -> None:
        metadata, quality = _run_fixture(
            "false_phone_date.html",
            target_url="https://sonrisamadrid.es",
            context={"target_language": "es"},
            discovery_metadata={"title": "Clinica Dental Sonrisa Madrid"},
        )

        self.assertEqual(metadata["phones"], ["+34911111111"])
        self.assertEqual(metadata["invalid_phone_candidates_count"], 3)
        self.assertEqual(metadata["phone_validation_rejections"]["date_like"], 1)
        self.assertEqual(metadata["phone_validation_rejections"]["sequence_noise"], 2)
        self.assertEqual(quality["phone"], "+34911111111")


if __name__ == "__main__":
    unittest.main()
