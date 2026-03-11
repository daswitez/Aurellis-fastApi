import unittest

from app.services.business_taxonomy import resolve_business_taxonomy


class BusinessTaxonomyTestCase(unittest.TestCase):
    def test_maps_dental_clinic_to_closed_taxonomy(self) -> None:
        result = resolve_business_taxonomy(
            clean_text="Clinica dental en Madrid con implantes, ortodoncia y reservas online.",
            metadata={
                "title": "Clinica Dental Madrid",
                "description": "Clinica dental con reservas online",
                "structured_data": [{"@type": "Dentist"}],
            },
            entity_type_detected="direct_business",
            inferred_niche="Dental Clinic",
        )

        self.assertEqual(result["taxonomy_top_level"], "health")
        self.assertEqual(result["taxonomy_business_type"], "dental_clinic")
        self.assertEqual(result["inferred_niche"], "Dental")

    def test_maps_directory_entity_to_marketplace_taxonomy(self) -> None:
        result = resolve_business_taxonomy(
            clean_text="Directorio de clinicas dentales en Madrid para comparar opciones.",
            metadata={
                "title": "Directorio de Clinicas Dentales en Madrid",
                "description": "Encuentra y compara clinicas dentales en Madrid",
            },
            entity_type_detected="directory",
            inferred_niche="Dental",
        )

        self.assertEqual(result["taxonomy_top_level"], "marketplace")
        self.assertEqual(result["taxonomy_business_type"], "directory_listing")
        self.assertEqual(result["inferred_niche"], "Directorio")

    def test_maps_editorial_entity_to_media_taxonomy(self) -> None:
        result = resolve_business_taxonomy(
            clean_text="Top 10 clinicas dentales en Madrid para comparar precios y opiniones.",
            metadata={
                "title": "Top 10 Clinicas Dentales en Madrid",
                "description": "Comparativa de clinicas dentales",
            },
            entity_type_detected="blog_post",
            inferred_niche="Dental",
        )

        self.assertEqual(result["taxonomy_top_level"], "media")
        self.assertEqual(result["taxonomy_business_type"], "editorial_content")
        self.assertEqual(result["inferred_niche"], "Editorial")


if __name__ == "__main__":
    unittest.main()
