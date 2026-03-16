import unittest

from app.scraper.http_client import _should_reject_response_content


class HttpClientContentGuardTestCase(unittest.TestCase):
    def test_rejects_pdf_by_url_suffix_even_without_content_type(self) -> None:
        self.assertTrue(
            _should_reject_response_content(
                "http://example.com/files/brochure.pdf",
                None,
            )
        )

    def test_rejects_binary_content_type(self) -> None:
        self.assertTrue(
            _should_reject_response_content(
                "http://example.com/download",
                "application/pdf; charset=binary",
            )
        )

    def test_allows_html_content_type(self) -> None:
        self.assertFalse(
            _should_reject_response_content(
                "http://example.com/",
                "text/html; charset=utf-8",
            )
        )
