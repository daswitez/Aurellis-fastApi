import unittest

from app.services.db_upsert import _extract_canonical_prospect_data, _sanitize_value_for_db


class DbUpsertSanitizationTestCase(unittest.TestCase):
    def test_sanitize_value_for_db_removes_null_bytes_recursively(self) -> None:
        payload = {
            "company_name": "Acme\x00 Studio",
            "raw_location_text": "Madrid\x00 Centro",
            "parsed_location": {
                "formatted": "Calle\x00 Mayor",
                "nested\x00key": ["va\x00lue", {"inner": "te\x00xt"}],
            },
            "contact_channels_json": [
                {"type": "phone", "value": "+34\x00000"},
            ],
        }

        sanitized = _sanitize_value_for_db(payload)

        self.assertEqual(sanitized["company_name"], "Acme Studio")
        self.assertEqual(sanitized["raw_location_text"], "Madrid Centro")
        self.assertEqual(sanitized["parsed_location"]["formatted"], "Calle Mayor")
        self.assertIn("nestedkey", sanitized["parsed_location"])
        self.assertEqual(sanitized["parsed_location"]["nestedkey"][0], "value")
        self.assertEqual(sanitized["parsed_location"]["nestedkey"][1]["inner"], "text")
        self.assertEqual(sanitized["contact_channels_json"][0]["value"], "+34000")

    def test_extract_canonical_prospect_data_sanitizes_json_fields(self) -> None:
        prospect_data = {
            "canonical_identity": "example.com",
            "domain": "example.com",
            "company_name": "Example\x00 Co",
            "raw_location_text": "Valencia\x00",
            "parsed_location": {"formatted": "Valencia\x00, España"},
            "contact_channels_json": [{"type": "phone", "value": "123\x004"}],
            "unknown_field": "ignored\x00",
        }

        extracted = _extract_canonical_prospect_data(prospect_data)

        self.assertEqual(extracted["company_name"], "Example Co")
        self.assertEqual(extracted["raw_location_text"], "Valencia")
        self.assertEqual(extracted["parsed_location"]["formatted"], "Valencia, España")
        self.assertEqual(extracted["contact_channels_json"][0]["value"], "1234")
        self.assertNotIn("unknown_field", extracted)
