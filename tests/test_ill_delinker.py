"""
Unit tests for IllDelinker (wiki_translator/ill_delinker.py).
"""

import unittest
from unittest.mock import MagicMock, patch

from wiki_translator.ill_delinker import (
    IllDelinker,
    default_ill_delinker,
)


class TestIllDelinker(unittest.TestCase):
    def setUp(self):
        self.delinker = IllDelinker()

    def test_default_instance(self):
        self.assertIsInstance(default_ill_delinker, IllDelinker)

    def test_delink_article_wikitext_targeted(self):
        wikitext = (
            "Tokoh ini lahir di {{ill|Kegubernuran Irkutsk|en|Irkutsk Governorate}}.\n"
            "Ia juga mengunjungi {{ill|Sankt-Peterburg|en|Saint Petersburg}} dan "
            "{{ill|Kegubernuran Irkutsk|en|Irkutsk Governorate|lt=wilayah Irkutsk}}."
        )
        # Delink only Kegubernuran Irkutsk
        cleaned, count = self.delinker.delink_article_wikitext(
            wikitext, target_title="Kegubernuran Irkutsk"
        )
        self.assertEqual(count, 2)
        self.assertIn("[[Kegubernuran Irkutsk]]", cleaned)
        self.assertIn("[[Kegubernuran Irkutsk|wilayah Irkutsk]]", cleaned)
        # Sankt-Peterburg should remain untouched since it wasn't the target
        self.assertIn("{{ill|Sankt-Peterburg|en|Saint Petersburg}}", cleaned)

    def test_delink_article_wikitext_no_target_uses_fidelity_validator(self):
        mock_val = MagicMock()
        mock_val.auto_convert_existing_links.return_value = ("Converted text", 3)
        delinker = IllDelinker(fidelity_validator=mock_val)

        res, count = delinker.delink_article_wikitext("Sample text", target_title=None)
        self.assertEqual(res, "Converted text")
        self.assertEqual(count, 3)
        mock_val.auto_convert_existing_links.assert_called_once_with("Sample text")

    def test_find_referring_articles(self):
        mock_http = MagicMock()
        mock_http.request.return_value = (
            {
                "query": {
                    "backlinks": [
                        {"title": "Artikel A"},
                        {"title": "Artikel B"},
                    ]
                }
            },
            None,
        )
        delinker = IllDelinker(http_client=mock_http)
        articles = delinker.find_referring_articles("Target Title")
        self.assertEqual(articles, ["Artikel A", "Artikel B"])
        mock_http.request.assert_called_once()
        params = mock_http.request.call_args[0][0]
        self.assertEqual(params["bltitle"], "Target Title")
        self.assertEqual(params["blnamespace"], "0")

    def test_delink_across_wikipedia_dry_run(self):
        delinker = IllDelinker()
        delinker.find_referring_articles = MagicMock(return_value=["Artikel X", "Artikel Y"])
        delinker.fetch_page_wikitext = MagicMock(
            side_effect=lambda title: (
                "Ini merujuk {{ill|Target|en|Target EN}}."
                if title == "Artikel X"
                else "Tidak ada templat di sini."
            )
        )

        res = delinker.delink_target_across_wikipedia(
            target_title="Target",
            username="TestUser",
            bot_password="pass",
            dry_run=True,
        )
        self.assertTrue(res["dry_run"])
        self.assertEqual(res["referring_articles_count"], 2)
        self.assertEqual(res["modified_articles_count"], 1)
        self.assertEqual(res["results"][0]["title"], "Artikel X")
        self.assertEqual(res["results"][0]["converted_links"], 1)
        self.assertEqual(res["results"][0]["status"], "simulated")


if __name__ == "__main__":
    unittest.main()
