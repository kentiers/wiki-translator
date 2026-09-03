"""
Unit and integration tests for Wikipedia Live Link & Category Validator and Mapper (wiki_link_mapper.py).
"""

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from wiki_translator.wiki_link_mapper import (
    CategoryResolution,
    LinkResolution,
    WikiLinkMapper,
    default_link_mapper,
    sanitize_ill_foreign_targets,
)
from wiki_translator.cli import WikiTranslatorCLI, main
from wiki_translator.wiki_client import WikiSection


class TestWikiLinkMapperCategories(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_db = Path(self.temp_dir.name) / "test_links_cache.db"
        self.mapper = WikiLinkMapper(cache_db_path=str(self.cache_db), allow_network=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_rule_based_category_translation(self):
        self.assertEqual(self.mapper.translate_category_rule_based("2024 films"), "Film tahun 2024")
        self.assertEqual(self.mapper.translate_category_rule_based("American television series"), "Amerika Serikat Serial televisi")
        self.assertEqual(self.mapper.translate_category_rule_based("1998 births"), "Kelahiran 1998")
        self.assertEqual(self.mapper.translate_category_rule_based("2026 action thriller films"), "Film cerita seru laga tahun 2026")
        self.assertEqual(self.mapper.translate_category_rule_based("action thriller films"), "Film cerita seru laga")
        self.assertEqual(self.mapper.translate_category_rule_based("English-language films"), "Film berbahasa Inggris")
        self.assertEqual(self.mapper.translate_category_rule_based("British films"), "Film Britania Raya")
        self.assertEqual(self.mapper.translate_category_rule_based("American films"), "Film Amerika Serikat")
        self.assertEqual(self.mapper.translate_category_rule_based("films directed by Kevin Macdonald"), "Film yang disutradarai oleh Kevin Macdonald")
        self.assertEqual(self.mapper.translate_category_rule_based("British action thriller films"), "Film cerita seru laga Britania Raya")
        self.assertEqual(self.mapper.translate_category_rule_based("American action thriller films"), "Film cerita seru laga Amerika Serikat")
        self.assertEqual(self.mapper.translate_category_rule_based("2026 British films"), "Film Britania Raya tahun 2026")
        self.assertEqual(self.mapper.translate_category_rule_based("2026 English-language films"), "Film berbahasa Inggris tahun 2026")
        self.assertEqual(self.mapper.translate_category_rule_based("upcoming English-language films"), "Film mendatang berbahasa Inggris")

    @patch.object(WikiLinkMapper, "check_id_wiki_pages_exist")
    @patch.object(WikiLinkMapper, "fetch_en_to_id_langlinks")
    @patch.object(WikiLinkMapper, "fetch_wikidata_id_sitelink")
    def test_uncreated_category_comments_original_english(self, mock_wd, mock_langlinks, mock_exists):
        mock_langlinks.return_value = {}
        mock_exists.return_value = {}
        mock_wd.return_value = None

        wikitext = "[[Category:2026 action thriller films]]\n[[Category:British action thriller films]]"
        mapped = self.mapper.map_categories(wikitext)
        self.assertIn("<!-- Kategori belum ada di id.wiki: [[Category:2026 action thriller films]] -->", mapped)
        self.assertIn("<!-- Kategori belum ada di id.wiki: [[Category:British action thriller films]] -->", mapped)
        self.assertNotIn("Film", mapped)

    @patch.object(WikiLinkMapper, "check_id_wiki_pages_exist")
    @patch.object(WikiLinkMapper, "fetch_en_to_id_langlinks")
    def test_category_with_en_langlink_existing_on_id(self, mock_langlinks, mock_exists):
        mock_langlinks.return_value = {"Category:Quantum computing": "Kategori:Komputasi kuantum"}
        mock_exists.return_value = {"Kategori:Komputasi kuantum": True}

        wikitext = "[[Category:Quantum computing]]"
        mapped = self.mapper.map_categories(wikitext)
        self.assertEqual(mapped, "[[Kategori:Komputasi kuantum]]")

    @patch.object(WikiLinkMapper, "check_id_wiki_pages_exist")
    @patch.object(WikiLinkMapper, "fetch_en_to_id_langlinks")
    @patch.object(WikiLinkMapper, "fetch_wikidata_id_sitelink")
    def test_category_uncreated_on_id_commented(self, mock_wd, mock_langlinks, mock_exists):
        mock_langlinks.return_value = {}
        mock_exists.return_value = {"Kategori:Film fiksi ilmiah 2024": False}
        mock_wd.return_value = None

        wikitext = "[[Category:2024 science fiction films]]"
        mapped = self.mapper.map_categories(wikitext)
        self.assertTrue(mapped.startswith("<!-- Kategori belum ada di id.wiki: [[Category:"))
        self.assertIn("-->", mapped)

    @patch.object(WikiLinkMapper, "check_id_wiki_pages_exist")
    @patch.object(WikiLinkMapper, "fetch_en_to_id_langlinks")
    def test_category_with_sortkey(self, mock_langlinks, mock_exists):
        mock_langlinks.return_value = {"Category:Physics": "Kategori:Fisika"}
        mock_exists.return_value = {"Kategori:Fisika": True}

        wikitext = "[[Category:Physics|*]]"
        mapped = self.mapper.map_categories(wikitext)
        self.assertEqual(mapped, "[[Kategori:Fisika|*]]")


class TestWikiLinkMapperLinks(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_db = Path(self.temp_dir.name) / "test_links_cache.db"
        self.mapper = WikiLinkMapper(
            cache_db_path=str(self.cache_db),
            use_ill_templates=True,
            allow_network=True,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch.object(WikiLinkMapper, "check_id_wiki_pages_exist")
    def test_direct_id_link_exists(self, mock_exists):
        mock_exists.return_value = {"Indonesia": True}
        wikitext = "Saya tinggal di [[Indonesia]]."
        mapped = self.mapper.map_wikilinks(wikitext)
        self.assertEqual(mapped, "Saya tinggal di [[Indonesia]].")

    @patch.object(WikiLinkMapper, "fetch_en_to_id_langlinks")
    @patch.object(WikiLinkMapper, "check_id_wiki_pages_exist")
    def test_en_to_id_langlink_mapping(self, mock_exists, mock_langlinks):
        mock_exists.return_value = {"Quantum computing": False, "Komputasi kuantum": True}
        mock_langlinks.return_value = {"Quantum computing": "Komputasi kuantum"}

        wikitext = "Studi tentang [[Quantum computing]]."
        mapped = self.mapper.map_wikilinks(wikitext)
        self.assertEqual(mapped, "Studi tentang [[Komputasi kuantum]].")
    @patch.object(WikiLinkMapper, "fetch_en_to_id_langlinks")
    @patch.object(WikiLinkMapper, "check_id_wiki_pages_exist")
    def test_en_to_id_with_display_alias(self, mock_exists, mock_langlinks):
        mock_exists.return_value = {"United States": False, "Amerika Serikat": True}
        mock_langlinks.return_value = {"United States": "Amerika Serikat"}

        wikitext = "Presiden [[United States|AS]] tiba."
        mapped = self.mapper.map_wikilinks(wikitext)
        self.assertEqual(mapped, "Presiden [[Amerika Serikat|AS]] tiba.")

    @patch.object(WikiLinkMapper, "fetch_en_to_id_langlinks")
    @patch.object(WikiLinkMapper, "check_id_wiki_pages_exist")
    def test_en_to_id_with_descriptive_alias_adapted(self, mock_exists, mock_langlinks):
        mock_exists.return_value = {"Munich massacre": False, "Pembantaian München": True}
        mock_langlinks.return_value = {"Munich massacre": "Pembantaian München"}

        wikitext = "Peristiwa [[Munich massacre|murder of 11 Israeli athletes]] terjadi."
        mapped = self.mapper.map_wikilinks(wikitext)
        self.assertEqual(mapped, "Peristiwa [[Pembantaian München|pembunuhan 11 atlet Israel]] terjadi.")

    @patch.object(WikiLinkMapper, "fetch_en_to_id_langlinks")
    @patch.object(WikiLinkMapper, "check_id_wiki_pages_exist")
    def test_link_without_alias_returns_clean_id_title(self, mock_exists, mock_langlinks):
        mock_exists.return_value = {"Academy Award for Best Documentary Feature": False, "Academy Award untuk Film Dokumenter Terbaik": True}
        mock_langlinks.return_value = {"Academy Award for Best Documentary Feature": "Academy Award untuk Film Dokumenter Terbaik"}

        wikitext = "Memenangkan [[Academy Award for Best Documentary Feature]] pada tahun 2000."
        mapped = self.mapper.map_wikilinks(wikitext)
        self.assertEqual(mapped, "Memenangkan [[Academy Award untuk Film Dokumenter Terbaik]] pada tahun 2000.")
    @patch.object(WikiLinkMapper, "fetch_en_to_id_langlinks")
    @patch.object(WikiLinkMapper, "check_id_wiki_pages_exist")
    def test_redlink_ill_template_safeguard(self, mock_exists, mock_langlinks):
        mock_exists.return_value = {"Uncreated Future Subject": False}
        mock_langlinks.return_value = {"Uncreated Future Subject": None}

        wikitext = "Lihat [[Uncreated Future Subject]]."
        mapped = self.mapper.map_wikilinks(wikitext)
        self.assertEqual(mapped, "Lihat {{ill|Uncreated Future Subject|en|Uncreated Future Subject}}.")

    @patch.object(WikiLinkMapper, "fetch_en_to_id_langlinks")
    @patch.object(WikiLinkMapper, "check_id_wiki_pages_exist")
    def test_redlink_with_alias_ill_template(self, mock_exists, mock_langlinks):
        mock_exists.return_value = {"Obscure Actor": False}
        mock_langlinks.return_value = {"Obscure Actor": None}

        wikitext = "Dibintangi oleh [[Obscure Actor|Aktor Terkenal]]."
        mapped = self.mapper.map_wikilinks(wikitext)
        self.assertEqual(mapped, "Dibintangi oleh {{ill|Aktor Terkenal|en|Obscure Actor}}.")

    def test_known_page_mapping_israelis_and_action_thriller(self):
        wikitext = "Aktris tersebut adalah [[Israelis|orang Israel]] dalam sebuah [[action thriller film]]."
        mapped = self.mapper.map_wikilinks(wikitext)
        self.assertEqual(mapped, "Aktris tersebut adalah [[Orang Israel|orang Israel]] dalam sebuah [[Film laga|cerita seru laga]].")

        # Direct action thriller without alias
        wikitext2 = "Ini adalah [[action thriller]]."
        mapped2 = self.mapper.map_wikilinks(wikitext2)
        self.assertEqual(mapped2, "Ini adalah [[Film laga|cerita seru laga]].")

    def test_sanitize_ill_cerita_seru_laga_never_targets_indonesian(self):
        bad_ill = "Film {{ill|cerita seru laga|en|film cerita seru laga}} Britania Raya"
        sanitized = sanitize_ill_foreign_targets(bad_ill)
        self.assertEqual(sanitized, "Film [[Film laga|cerita seru laga]] Britania Raya")

        bad_ill2 = "Film {{ill|cerita seru laga|en|action thriller film}} Britania Raya"
        sanitized2 = sanitize_ill_foreign_targets(bad_ill2)
        self.assertEqual(sanitized2, "Film [[Film laga|cerita seru laga]] Britania Raya")

    def test_excludes_file_and_image_namespaces(self):
        wikitext = "[[File:Example.jpg|thumb|Deskripsi]] dan [[Berkas:Foto.png|gambar]]."
        mapped = self.mapper.map_wikilinks(wikitext)
        self.assertEqual(mapped, wikitext)

    def test_sanitize_ill_foreign_targets_rules(self):
        test_cases = [
            (
                "{{ill|Kevin Macdonald|en|Kevin Macdonald (sutradara)}}",
                "{{ill|Kevin Macdonald|en|Kevin Macdonald (director)}}",
            ),
            (
                "{{ill|John Doe|en|John Doe (pemeran)}}",
                "{{ill|John Doe|en|John Doe (actor)}}",
            ),
            (
                "{{ill|Jane Doe|en|Jane Doe (aktor)}}",
                "{{ill|Jane Doe|en|Jane Doe (actor)}}",
            ),
            (
                "{{ill|Runner|en|Runner (film 2026)}}",
                "{{ill|Runner|en|Runner (2026 film)}}",
            ),
            (
                "{{ill|The Runner|en|The Runner (film Britania Raya 2026)}}",
                "{{ill|The Runner|en|The Runner (2026 Britania Raya film)}}",
            ),
            (
                "{{ill|Arthur Conan Doyle|en|Arthur Conan Doyle (penulis)}}",
                "{{ill|Arthur Conan Doyle|en|Arthur Conan Doyle (writer)}}",
            ),
            (
                "{{ill|Hans Zimmer|en|Hans Zimmer (musisi)}}",
                "{{ill|Hans Zimmer|en|Hans Zimmer (musician)}}",
            ),
            (
                "{{ill|John Smith|en|John Smith (pemusik)}}",
                "{{ill|John Smith|en|John Smith (musician)}}",
            ),
            (
                "{{ill|Winston Churchill|en|Winston Churchill (politikus)}}",
                "{{ill|Winston Churchill|en|Winston Churchill (politician)}}",
            ),
            (
                "{{ill|Ronaldo|en|Ronaldo (pesepak bola)}}",
                "{{ill|Ronaldo|en|Ronaldo (footballer)}}",
            ),
            (
                "{{ill|Loki|en|Loki (serial televisi 2021)}}",
                "{{ill|Loki|en|Loki (2021 television series)}}",
            ),
            (
                "{{ill|Doctor Who|en|Doctor Who (serial televisi)}}",
                "{{ill|Doctor Who|en|Doctor Who (television series)}}",
            ),
            (
                "{{ill|Something|en|Something (director)|lt=Custom Text}}",
                "{{ill|Something|en|Something (director)|lt=Custom Text}}",
            ),
        ]
        for src, expected in test_cases:
            with self.subTest(src=src):
                self.assertEqual(sanitize_ill_foreign_targets(src), expected)

    def test_process_wikitext_applies_sanitize_ill(self):
        wikitext = "Sutradara: {{ill|Kevin Macdonald|en|Kevin Macdonald (sutradara)}}."
        processed = self.mapper.process_wikitext(wikitext)
        self.assertIn("{{ill|Kevin Macdonald|en|Kevin Macdonald (director)}}", processed)
        self.assertNotIn("Kevin Macdonald (sutradara)", processed)


class TestWikiLinkMapperCaching(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_db = Path(self.temp_dir.name) / "test_links_cache.db"
        self.mapper = WikiLinkMapper(cache_db_path=str(self.cache_db), allow_network=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_sqlite_cache_roundtrip(self):
        self.mapper.cache_page_link("Special Topic", "Topik Khusus", True, "test")
        cached = self.mapper.get_cached_page_link("special topic")
        self.assertIsNotNone(cached)
        self.assertEqual(cached.target_id, "Topik Khusus")
        self.assertTrue(cached.exists_on_id)

        self.mapper.cache_category("Special Films", "Film Khusus", True, "test")
        cached_cat = self.mapper.get_cached_category("Special Films")
        self.assertIsNotNone(cached_cat)
        self.assertEqual(cached_cat.id_category, "Film Khusus")
        self.assertTrue(cached_cat.exists_on_id)


class TestCLIIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.out_dir = Path(self.temp_dir.name) / "output"
        self.cache_db = Path(self.temp_dir.name) / "test_cache.db"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_cli_save_output_with_link_mapping(self):
        mapper = WikiLinkMapper(cache_db_path=str(self.cache_db), allow_network=False)
        cli = WikiTranslatorCLI(
            output_dir=str(self.out_dir),
            enable_map_links=True,
            link_mapper=mapper,
            enable_cache=False,
        )
        sections = [
            WikiSection(
                index=0,
                title="Lead",
                level=1,
                header_raw="",
                content="Artikel tentang [[Quantum computing]].\n[[Category:Quantum computing]]",
                word_count=10,
                char_count=60,
                translated_content="Artikel tentang [[Quantum computing]].\n[[Category:Quantum computing]]",
            )
        ]
        wikitext_file, md_file, talk_file = cli._save_output("quantum_test", "Quantum Test", sections)
        self.assertTrue(wikitext_file.exists())
        self.assertTrue(talk_file.exists())
        content = wikitext_file.read_text(encoding="utf-8")
        self.assertIn("ill|Quantum computing|en|Quantum computing", content)


if __name__ == "__main__":
    unittest.main()
