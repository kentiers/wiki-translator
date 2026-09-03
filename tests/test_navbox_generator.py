"""
Unit tests for wiki_translator/navbox_generator.py.
"""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock

from wiki_translator.navbox_generator import (
    NavboxGenerator,
    default_navbox_generator,
    STANDARD_GROUP_TRANSLATIONS,
)
from wiki_translator.wiki_client import PageNotFoundError, WikipediaClient
from wiki_translator.wiki_link_mapper import LinkResolution, WikiLinkMapper


class TestNavboxGenerator(unittest.TestCase):

    def setUp(self):
        self.mock_en_client = MagicMock(spec=WikipediaClient)
        self.mock_id_client = MagicMock(spec=WikipediaClient)
        self.mock_link_mapper = MagicMock(spec=WikiLinkMapper)

        # Configure link mapper mock to return mapped wikilinks and categories
        self.mock_link_mapper.map_wikilinks.side_effect = lambda text: text
        self.mock_link_mapper.map_categories.side_effect = lambda cat: cat.replace("Category:", "Kategori:")

        self.generator = NavboxGenerator(
            en_client=self.mock_en_client,
            id_client=self.mock_id_client,
            link_mapper=self.mock_link_mapper,
        )

    def test_translate_group_label(self):
        self.assertEqual(self.generator.translate_group_label("Directed by"), "Disutradarai oleh")
        self.assertEqual(self.generator.translate_group_label("Films"), "Film")
        self.assertEqual(self.generator.translate_group_label("Television"), "Televisi")
        self.assertEqual(self.generator.translate_group_label("Cast"), "Pemeran")
        self.assertEqual(self.generator.translate_group_label("Awards"), "Penghargaan")
        # With bold formatting
        self.assertEqual(self.generator.translate_group_label("'''Films'''"), "'''Film'''")

    def test_convert_navbox_wikitext(self):
        en_wikitext = """{{Navbox
| name = Christopher Nolan
| title = Films directed by Christopher Nolan
| state = {{{state|autocollapse}}}
| group1 = Directed by
| list1 = [[Memento (film)|Memento]] * [[Inception]] * [[Interstellar (film)|Interstellar]]
| group2 = Produced by
| list2 = [[Man of Steel (film)|Man of Steel]]
<noinclude>
[[Category:English film director navigational boxes]]
</noinclude>
}}"""
        converted = self.generator.convert_navbox(en_wikitext, "Christopher Nolan")

        # Must contain Kotak navigasi
        self.assertIn("{{Kotak navigasi", converted)
        # Parameters mapped
        self.assertIn("| nama = Christopher Nolan", converted)
        self.assertIn("| judul =", converted)
        self.assertIn("| status = {{{state|autocollapse}}}", converted)
        self.assertIn("| kelompok1 = Disutradarai oleh", converted)
        self.assertIn("| daftar1 =", converted)
        self.assertIn("| kelompok2 = Diproduseri oleh", converted)
        self.assertIn("| daftar2 =", converted)
        # Check documentation and category
        self.assertIn("<noinclude>", converted)
        self.assertIn("{{Dokumentasi}}", converted)
        self.assertIn("[[Kategori:", converted)

    def test_check_template_exists_on_id(self):
        # When exists
        self.mock_id_client.fetch_wikitext.return_value = "{{Kotak navigasi|...}}"
        self.assertTrue(self.generator.check_template_exists_on_id("Christopher Nolan"))

        # When missing
        self.mock_id_client.fetch_wikitext.side_effect = PageNotFoundError("Missing")
        self.assertFalse(self.generator.check_template_exists_on_id("Missing Template"))

    def test_generate_navbox_success(self):
        sample_wikitext = "{{Navbox| name = Test | title = Test Title | group1 = Films | list1 = [[Film A]]}}"
        self.mock_en_client.fetch_wikitext.return_value = sample_wikitext
        self.mock_id_client.fetch_wikitext.side_effect = PageNotFoundError("Missing")

        res = self.generator.generate_navbox("Template:Test", check_existence=True)
        self.assertIsNotNone(res)
        self.assertEqual(res["template_name"], "Test")
        self.assertEqual(res["id_title"], "Templat:Test")
        self.assertFalse(res["already_exists"])
        self.assertIn("{{Kotak navigasi", res["wikitext"])

    def test_save_navbox(self):
        navbox_info = {
            "template_name": "Christopher Nolan",
            "id_title": "Templat:Christopher Nolan",
            "wikitext": "{{Kotak navigasi\n| nama = Christopher Nolan\n}}",
            "already_exists": False,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            saved = self.generator.save_navbox(navbox_info, out_dir)
            self.assertTrue(saved.exists())
            self.assertEqual(saved.name, "Christopher Nolan.wikitext")
            self.assertIn("Kotak navigasi", saved.read_text(encoding="utf-8"))

    def test_navbox_film_list_and_redirect_handling(self):
        """
        Assert that navbox generator and wikitext correctly include recent films
        and properly map/handle redirect targets (e.g. Kevin Macdonald).
        """
        kevin_navbox_en = """{{Navbox
| name = Kevin Macdonald
| title = Films directed by [[Kevin Macdonald (director)|Kevin Macdonald]]
| state = {{{state|autocollapse}}}
| list1 = 
* ''[[Black Sea (film)|Black Sea]]'' (2014)
* ''[[The Mauritanian]]'' (2021)
* ''[[The Runner (film 2026)|The Runner]]'' (2026)
}}"""
        # Configure mock link mapper to resolve director redirect
        def mock_map(text: str) -> str:
            return text.replace(
                "[[Kevin Macdonald (director)|Kevin Macdonald]]",
                "[[Kevin Macdonald (sutradara)|Kevin Macdonald]]"
            )

        self.mock_link_mapper.map_wikilinks.side_effect = mock_map
        converted = self.generator.convert_navbox(kevin_navbox_en, "Kevin Macdonald")

        # Check converted template header and title link
        self.assertIn("{{Kotak navigasi", converted)
        self.assertIn("| nama = Kevin Macdonald", converted)
        self.assertIn("[[Kevin Macdonald (sutradara)|Kevin Macdonald]]", converted)

        # Check films in list
        self.assertIn("''[[The Mauritanian]]'' (2021)", converted)
        self.assertIn("''[[The Runner (film 2026)|The Runner]]'' (2026)", converted)
        self.assertIn("''[[Black Sea (film)|Black Sea]]'' (2014)", converted)
    def test_default_instance(self):
        self.assertIsNotNone(default_navbox_generator)


if __name__ == "__main__":
    unittest.main()
