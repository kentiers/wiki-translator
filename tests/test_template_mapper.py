"""
Unit tests for WikiTemplateMapper (wiki_translator/template_mapper.py).
"""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from wiki_translator.template_mapper import (
    WikiTemplateMapper,
    default_template_mapper,
)


class TestWikiTemplateMapper(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_db = Path(self.temp_dir.name) / "test_templates_cache.db"
        self.mapper = WikiTemplateMapper(
            cache_db_path=str(self.cache_db),
            allow_network=True,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    # ----------------------------------------------------
    # 1. resolve_template_name Tests
    # ----------------------------------------------------
    def test_resolve_template_name_common(self):
        self.assertEqual(self.mapper.resolve_template_name("Main"), "Utama")
        self.assertEqual(self.mapper.resolve_template_name("main"), "Utama")
        self.assertEqual(self.mapper.resolve_template_name("See also"), "Lihat pula")
        self.assertEqual(self.mapper.resolve_template_name("see also"), "Lihat pula")
        self.assertEqual(self.mapper.resolve_template_name("Citation needed"), "Butuh rujukan")
        self.assertEqual(self.mapper.resolve_template_name("cn"), "Butuh rujukan")
        self.assertEqual(self.mapper.resolve_template_name("Reflist"), "reflist")
        self.assertEqual(self.mapper.resolve_template_name("reflist"), "reflist")
        self.assertEqual(self.mapper.resolve_template_name("daftar rujukan"), "reflist")
        self.assertEqual(self.mapper.resolve_template_name("Daftar rujukan"), "reflist")
        self.assertEqual(self.mapper.resolve_template_name("Birth date and age"), "Tanggal lahir dan umur")
        self.assertEqual(self.mapper.resolve_template_name("Death date and age"), "Tanggal kematian dan umur")
        self.assertEqual(self.mapper.resolve_template_name("Official website"), "Situs web resmi")
        self.assertEqual(self.mapper.resolve_template_name("IMDb title"), "IMDb title")
        self.assertEqual(self.mapper.resolve_template_name("IMDb name"), "IMDb name")
        self.assertEqual(self.mapper.resolve_template_name("RT prose"), "Rotten Tomatoes prose")
        self.assertEqual(self.mapper.resolve_template_name("rt"), "Rotten Tomatoes")
        self.assertEqual(self.mapper.resolve_template_name("Rotten Tomatoes prose"), "Rotten Tomatoes prose")

    def test_resolve_infoboxes(self):
        self.assertEqual(self.mapper.resolve_template_name("Infobox film"), "Infobox film")
        self.assertEqual(self.mapper.resolve_template_name("Infobox television"), "Infobox televisi")
        self.assertEqual(self.mapper.resolve_template_name("Infobox musical artist"), "Infobox penyanyi dan pemusik")

    # ----------------------------------------------------
    # 2. process_wikitext_templates Mapping Tests
    # ----------------------------------------------------
    def test_process_template_name_replacement(self):
        text = "== Lihat Pula ==\n{{Main|Sejarah Indonesia}}\n{{See also|Budaya Indonesia}}"
        result = self.mapper.process_wikitext_templates(text, check_existence=False)
        self.assertIn("{{Utama|Sejarah Indonesia}}", result)
        self.assertIn("{{Lihat pula|Budaya Indonesia}}", result)

    def test_process_dates_and_citations(self):
        text = "Lahir: {{birth date and age|1990|1|15}}\nFakta kontroversial.{{cn}}\n== Referensi ==\n{{reflist}}"
        result = self.mapper.process_wikitext_templates(text, check_existence=False)
        self.assertIn("{{Tanggal lahir dan umur|1990|1|15}}", result)
        self.assertIn("{{Butuh rujukan}}", result)
        self.assertIn("{{reflist}}", result)


    def test_magic_words_protection(self):
        text = "{{DEFAULTSORT:Runner (2026 film), The}}\n{{DISPLAYTITLE:The Runner}}\n{{formatnum:12345}}"
        offline_mapper = WikiTemplateMapper(
            cache_db_path=str(self.cache_db),
            allow_network=False,
        )
        result = offline_mapper.process_wikitext_templates(text, check_existence=True)
        self.assertNotIn("<!-- Templat belum tersedia di id.wiki:", result)
        self.assertIn("{{DEFAULTSORT:Runner (2026 film), The}}", result)
        self.assertIn("{{DISPLAYTITLE:The Runner}}", result)
        self.assertIn("{{formatnum:12345}}", result)

    def test_rt_prose_and_imdb_processing(self):
        text = "{{RT prose|9|3.9|22|ref=y}}\n{{IMDb title|tt34564059}}\n{{IMDb name|nm0000001}}"
        offline_mapper = WikiTemplateMapper(
            cache_db_path=str(self.cache_db),
            allow_network=False,
        )
        result = offline_mapper.process_wikitext_templates(text, check_existence=True)
        self.assertNotIn("<!-- Templat belum tersedia di id.wiki:", result)
        self.assertIn("{{Rotten Tomatoes prose|9|3.9|22|ref=y}}", result)
        self.assertIn("{{IMDb title|tt34564059}}", result)
        self.assertIn("{{IMDb name|nm0000001}}", result)

    @patch.object(WikiTemplateMapper, "check_id_wiki_templates_exist")
    def test_kevin_macdonald_template_wrapped_if_missing(self, mock_check_exists):
        mock_check_exists.return_value = {
            "Kevin Macdonald": False,
        }
        text = "{{Kevin Macdonald}}"
        result = self.mapper.process_wikitext_templates(text, check_existence=True)
        self.assertIn("<!-- Templat belum tersedia di id.wiki: {{Kevin Macdonald}} -->", result)

    @patch.object(WikiTemplateMapper, "check_id_wiki_templates_exist")
    def test_kevin_macdonald_template_kept_if_exists(self, mock_check_exists):
        mock_check_exists.return_value = {
            "Kevin Macdonald": True,
        }
        text = "{{Kevin Macdonald}}"
        result = self.mapper.process_wikitext_templates(text, check_existence=True)
        self.assertNotIn("<!-- Templat belum tersedia di id.wiki:", result)
        self.assertIn("{{Kevin Macdonald}}", result)
    # ----------------------------------------------------
    # 3. Whitelist & Safeguard Tests
    # ----------------------------------------------------
    def test_whitelist_unwrapped(self):
        text = "{{reflist}}\n{{cite web|url=https://example.com|title=Test}}\n{{ill|Nama ID|en|Name EN}}"
        # Even with check_existence=True and allow_network=False, whitelisted templates are not commented out
        offline_mapper = WikiTemplateMapper(
            cache_db_path=str(self.cache_db),
            allow_network=False,
        )
        result = offline_mapper.process_wikitext_templates(text, check_existence=True)
        self.assertNotIn("<!-- Templat belum tersedia di id.wiki:", result)
        self.assertIn("{{reflist}}", result)
        self.assertIn("{{cite web", result)
        self.assertIn("{{ill", result)

    @patch.object(WikiTemplateMapper, "check_id_wiki_templates_exist")
    def test_missing_template_safeguard_wrapping(self, mock_check_exists):
        # Suppose a navbox template does not exist on id.wikipedia.org
        mock_check_exists.return_value = {
            "Marvel Cinematic Universe Phase Four": False,
        }

        text = "Artikel tentang film.\n\n{{Marvel Cinematic Universe Phase Four}}"
        result = self.mapper.process_wikitext_templates(text, check_existence=True)
        self.assertIn(
            "<!-- Templat belum tersedia di id.wiki: {{Marvel Cinematic Universe Phase Four}} -->",
            result,
        )

    @patch.object(WikiTemplateMapper, "check_id_wiki_templates_exist")
    def test_existing_template_not_wrapped(self, mock_check_exists):
        mock_check_exists.return_value = {
            "Kotak info aktor": True,
        }

        text = "{{Kotak info aktor|name=John}}"
        result = self.mapper.process_wikitext_templates(text, check_existence=True)
        self.assertNotIn("<!-- Templat belum tersedia", result)
        self.assertIn("{{Kotak info aktor|name=John}}", result)
    def test_strip_metadata_templates(self):
        text = (
            "{{Short description|American film}}\n"
            "{{Featured article}}\n"
            "{{Artikel pilihan}}\n"
            "{{Good article}}\n"
            "{{Artikel bagus}}\n"
            "{{Use dmy dates|date=May 2020}}\n"
            "'''Title''' is a film."
        )
        result = self.mapper.process_wikitext_templates(text, check_existence=False)
        self.assertNotIn("Short description", result)
        self.assertNotIn("Featured article", result)
        self.assertNotIn("Artikel pilihan", result)
        self.assertNotIn("Good article", result)
        self.assertNotIn("Artikel bagus", result)
        self.assertNotIn("Use dmy dates", result)
        self.assertIn("'''Title''' is a film.", result)


    def test_caching_behavior(self):
        self.mapper.cache_template("TestTemplate", True, "test_source")
        self.assertTrue(self.mapper.get_cached_template("TestTemplate"))
        self.assertTrue(self.mapper.get_cached_template("testtemplate"))

        self.mapper.cache_template("MissingTemplate", False, "test_source")
        self.assertFalse(self.mapper.get_cached_template("MissingTemplate"))

    def test_default_instance(self):
        self.assertIsNotNone(default_template_mapper)
        res = default_template_mapper.resolve_template_name("main")
        self.assertEqual(res, "Utama")


if __name__ == "__main__":
    unittest.main()
