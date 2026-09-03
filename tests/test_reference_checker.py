import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from wiki_translator.reference_checker import (
    ReferenceChecker,
    default_reference_checker,
)


class TestReferenceChecker(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_db = Path(self.temp_dir.name) / "test_wayback_cache.db"
        self.checker = ReferenceChecker(
            cache_db_path=str(self.cache_db),
            timeout=2.0,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_reference_checker_instance(self):
        self.assertIsInstance(default_reference_checker, ReferenceChecker)

    def test_cache_roundtrip(self):
        url = "https://example.com/article"
        self.checker.cache_archive(
            url,
            has_archive=True,
            archive_url="https://web.archive.org/web/20230101/https://example.com/article",
            archive_date="2023-01-01",
        )
        cached = self.checker.get_cached_archive(url)
        self.assertIsNotNone(cached)
        has_arc, arc_url, arc_date = cached
        self.assertTrue(has_arc)
        self.assertEqual(arc_url, "https://web.archive.org/web/20230101/https://example.com/article")
        self.assertEqual(arc_date, "2023-01-01")

    def test_offline_mode_returns_none_when_uncached(self):
        url = "https://example.com/uncached"
        result = self.checker.query_wayback_api(url, allow_network=False)
        self.assertIsNone(result)

    def test_offline_mode_returns_cached_result(self):
        url = "https://example.com/preloaded"
        self.checker.cache_archive(
            url,
            has_archive=True,
            archive_url="https://web.archive.org/web/20220512/https://example.com/preloaded",
            archive_date="2022-05-12",
        )
        result = self.checker.query_wayback_api(url, allow_network=False)
        self.assertIsNotNone(result)
        arc_url, arc_date = result
        self.assertEqual(arc_url, "https://web.archive.org/web/20220512/https://example.com/preloaded")
        self.assertEqual(arc_date, "2022-05-12")

    @patch("urllib.request.urlopen")
    def test_query_wayback_api_success(self, mock_urlopen):
        api_response = {
            "archived_snapshots": {
                "closest": {
                    "available": True,
                    "url": "http://web.archive.org/web/20201115000000/http://example.org/",
                    "timestamp": "20201115000000",
                    "status": "200",
                }
            }
        }
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(api_response).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        mock_urlopen.return_value = mock_resp

        result = self.checker.query_wayback_api("http://example.org/", allow_network=True)
        self.assertIsNotNone(result)
        arc_url, arc_date = result
        self.assertEqual(arc_url, "http://web.archive.org/web/20201115000000/http://example.org/")
        self.assertEqual(arc_date, "2020-11-15")

        # Verify it was saved to cache
        cached = self.checker.get_cached_archive("http://example.org/")
        self.assertIsNotNone(cached)
        self.assertTrue(cached[0])

    @patch("urllib.request.urlopen")
    def test_query_wayback_api_not_available(self, mock_urlopen):
        api_response = {"archived_snapshots": {}}
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(api_response).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        mock_urlopen.return_value = mock_resp

        result = self.checker.query_wayback_api("http://not-archived.org/", allow_network=True)
        self.assertIsNone(result)

        cached = self.checker.get_cached_archive("http://not-archived.org/")
        self.assertIsNotNone(cached)
        self.assertFalse(cached[0])

    def test_enrich_citations_with_archives_injection(self):
        self.checker.cache_archive(
            "https://deadline.com/test-news",
            has_archive=True,
            archive_url="https://web.archive.org/web/20210315/https://deadline.com/test-news",
            archive_date="2021-03-15",
        )

        wikitext = (
            "Film ini diumumkan pada bulan Maret.<ref>"
            "{{cite news |title=New Movie Announced |url=https://deadline.com/test-news |access-date=2021-03-20}}"
            "</ref> Sukses besar."
        )

        enriched = self.checker.enrich_citations_with_archives(wikitext, allow_network=False)

        expected_part = (
            "{{cite news |title=New Movie Announced |url=https://deadline.com/test-news "
            "|access-date=2021-03-20 |archive-url=https://web.archive.org/web/20210315/https://deadline.com/test-news "
            "|archive-date=2021-03-15 |url-status=live}}"
        )
        self.assertIn(expected_part, enriched)

    def test_enrich_citations_skips_if_already_archived(self):
        wikitext = (
            "{{cite web |title=Already Archived |url=https://example.com "
            "|archive-url=https://web.archive.org/web/123/https://example.com |archive-date=2020-01-01}}"
        )
        enriched = self.checker.enrich_citations_with_archives(wikitext, allow_network=True)
        self.assertEqual(enriched, wikitext)

    def test_enrich_citations_skips_non_cite_templates(self):
        wikitext = "{{Infobox film |title=My Movie |url=https://example.com}}"
        enriched = self.checker.enrich_citations_with_archives(wikitext, allow_network=True)
        self.assertEqual(enriched, wikitext)


if __name__ == "__main__":
    unittest.main()
