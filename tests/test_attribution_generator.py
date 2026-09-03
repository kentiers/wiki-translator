"""
Unit tests for TalkPageAttributionGenerator (wiki_translator/attribution_generator.py)
and WikipediaClient revision tracking.
"""

from datetime import datetime, timezone
import unittest
from unittest.mock import MagicMock, patch

from wiki_translator.attribution_generator import (
    TalkPageAttributionGenerator,
    default_attribution_generator,
)
from wiki_translator.wiki_client import WikipediaClient


class TestTalkPageAttributionGenerator(unittest.TestCase):
    def setUp(self):
        self.generator = TalkPageAttributionGenerator()

    # ----------------------------------------------------
    # 1. Template Generation Tests
    # ----------------------------------------------------
    def test_generate_attribution_template_basic(self):
        tmpl = self.generator.generate_attribution_template("Inception")
        self.assertEqual(tmpl, "{{Translated page|en|Inception}}")

    def test_generate_attribution_template_with_oldid(self):
        tmpl = self.generator.generate_attribution_template("Inception (film)", oldid=123456789)
        self.assertEqual(tmpl, "{{Translated page|en|Inception (film)|version=123456789}}")

    def test_generate_attribution_template_with_underscores(self):
        tmpl = self.generator.generate_attribution_template("Albert_Einstein", oldid=987654)
        self.assertEqual(tmpl, "{{Translated page|en|Albert Einstein|version=987654}}")

    def test_generate_attribution_template_with_insertversion(self):
        tmpl = self.generator.generate_attribution_template("Albert_Einstein", oldid=987654, insertversion=112233)
        self.assertEqual(tmpl, "{{Translated page|en|Albert Einstein|version=987654|insertversion=112233}}")
    # ----------------------------------------------------
    # 2. ProyekWiki Banners Tests
    # ----------------------------------------------------
    def test_proyek_wiki_banners_default(self):
        banners = self.generator.get_proyek_wiki_banners()
        self.assertIn("{{ProyekWiki Terjemahan}}", banners)

    def test_proyek_wiki_banners_by_topic(self):
        film_banners = self.generator.get_proyek_wiki_banners(topic="film")
        self.assertIn("{{ProyekWiki Film}}", film_banners)
        self.assertIn("{{ProyekWiki Terjemahan}}", film_banners)

        science_banners = self.generator.get_proyek_wiki_banners(topic="computing_science")
        self.assertIn("{{ProyekWiki Komputasi}}", science_banners)
        self.assertIn("{{ProyekWiki Sains}}", science_banners)

    # ----------------------------------------------------
    # 3. Full Talk Page Content Tests
    # ----------------------------------------------------
    def test_generate_full_talk_page_default_no_proyek_wiki(self):
        fixed_time = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
        talk = self.generator.generate_talk_page(
            en_title="Interstellar (film)",
            id_title="Interstellar (film)",
            oldid=123456789,
            topic="film",
            notes="Diterjemahkan dengan bantuan AI model Gemini 2.5 Flash.",
            timestamp=fixed_time,
        )

        self.assertIn("{{Translated page|en|Interstellar (film)|version=123456789}}", talk)
        self.assertNotIn("{{ProyekWiki Film}}", talk)
        self.assertNotIn("{{ProyekWiki Terjemahan}}", talk)
        self.assertIn("== Terjemahan Artikel ==", talk)
        self.assertIn("[https://en.wikipedia.org/w/index.php?oldid=123456789 123456789]", talk)
        self.assertIn("03 September 2026 12:00 UTC", talk)
        self.assertIn("Creative Commons Attribution-ShareAlike 4.0 International", talk)
        self.assertIn("Diterjemahkan dengan bantuan AI", talk)
        self.assertNotIn("WikiTranslator", talk)

    def test_generate_full_talk_page_with_proyek_wiki(self):
        fixed_time = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
        talk = self.generator.generate_talk_page(
            en_title="Interstellar (film)",
            id_title="Interstellar (film)",
            oldid=123456789,
            topic="film",
            timestamp=fixed_time,
            include_proyek_wiki=True,
        )

        self.assertIn("{{Translated page|en|Interstellar (film)|version=123456789}}", talk)
        self.assertIn("{{ProyekWiki Film}}", talk)
        self.assertIn("{{ProyekWiki Terjemahan}}", talk)

    def test_default_instance(self):
        self.assertIsNotNone(default_attribution_generator)
        res = default_attribution_generator.generate_attribution_template("Test")
        self.assertIn("{{Translated page|en|Test}}", res)

class TestWikipediaClientRevisionTracking(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_fetch_wikitext_records_revid_and_pageid(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b"""{
            "query": {
                "pages": [
                    {
                        "pageid": 42000,
                        "title": "Quantum computing",
                        "revisions": [
                            {
                                "revid": 99887766,
                                "slots": {
                                    "main": {
                                        "content": "Quantum computing wikitext content."
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
        }"""
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = WikipediaClient(lang="en")
        content = client.fetch_wikitext("Quantum computing")

        self.assertEqual(content, "Quantum computing wikitext content.")
        self.assertEqual(client.last_page_id, 42000)
        self.assertEqual(client.last_revision_id, 99887766)


if __name__ == "__main__":
    unittest.main()
