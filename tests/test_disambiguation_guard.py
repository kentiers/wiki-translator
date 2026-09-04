"""
Unit tests for Contextual Disambiguation Guard in WikiLinkMapper.
Tests:
1. Detection of disambiguation pages via mocked API responses (pageprops and category checks).
2. Disambiguation options extraction (prop=links).
3. Contextual resolution with various contexts (astronomy, chemistry, mythology, etc.).
4. process_wikitext replacing ambiguous links with disambiguated piped links (with and without prior anchors).
5. Cache persistence of disambiguation data (is_disambiguation, disambiguation_target, migration).
"""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from wiki_translator.wiki_link_mapper import LinkResolution, WikiLinkMapper


class TestContextualDisambiguationGuard(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_db = Path(self.temp_dir.name) / "test_disambig_cache.db"
        self.mapper = WikiLinkMapper(
            cache_db_path=str(self.cache_db),
            allow_network=True,
            use_ill_templates=True,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    # -------------------------------------------------------------------------
    # 1 & 2: API Disambiguation Detection & Options Extraction
    # -------------------------------------------------------------------------

    @patch.object(WikiLinkMapper, "_api_get")
    def test_check_id_disambiguation_via_pageprops(self, mock_api_get):
        """Disambiguation detected via pageprops.disambiguation."""
        def side_effect(endpoint, params):
            if params.get("prop") == "pageprops|categories":
                return {
                    "query": {
                        "pages": [
                            {
                                "pageid": 101,
                                "title": "Merkurius",
                                "pageprops": {"disambiguation": ""},
                                "categories": [],
                            },
                            {
                                "pageid": 102,
                                "title": "Jupiter",
                                "categories": [],
                            }
                        ]
                    }
                }
            elif params.get("prop") == "links":
                return {
                    "query": {
                        "pages": [
                            {
                                "pageid": 101,
                                "title": "Merkurius",
                                "links": [
                                    {"ns": 0, "title": "Merkurius (planet)"},
                                    {"ns": 0, "title": "Merkurius (unsur)"},
                                    {"ns": 0, "title": "Merkurius (mitologi)"},
                                ],
                            }
                        ]
                    }
                }
            return {}

        mock_api_get.side_effect = side_effect
        res = self.mapper.check_id_disambiguation(["Merkurius", "Jupiter"])

        self.assertIn("Merkurius", res)
        self.assertTrue(res["Merkurius"][0])
        self.assertEqual(
            res["Merkurius"][1],
            ["Merkurius (planet)", "Merkurius (unsur)", "Merkurius (mitologi)"],
        )

        self.assertIn("Jupiter", res)
        self.assertFalse(res["Jupiter"][0])
        self.assertEqual(res["Jupiter"][1], [])

    @patch.object(WikiLinkMapper, "_api_get")
    def test_check_id_disambiguation_via_category(self, mock_api_get):
        """Disambiguation detected via 'Kategori:Halaman disambiguasi' or 'Kategori:Semua halaman disambiguasi'."""
        def side_effect(endpoint, params):
            if params.get("prop") == "pageprops|categories":
                return {
                    "query": {
                        "pages": {
                            "201": {
                                "pageid": 201,
                                "title": "Bima",
                                "categories": [
                                    {"ns": 14, "title": "Kategori:Semua halaman disambiguasi"}
                                ],
                            }
                        }
                    }
                }
            elif params.get("prop") == "links":
                return {
                    "query": {
                        "pages": {
                            "201": {
                                "pageid": 201,
                                "title": "Bima",
                                "links": [
                                    {"ns": 0, "title": "Bima (tokoh pewayangan)"},
                                    {"ns": 0, "title": "Kota Bima"},
                                    {"ns": 0, "title": "Kabupaten Bima"},
                                ],
                            }
                        }
                    }
                }
            return {}

        mock_api_get.side_effect = side_effect
        res = self.mapper.check_id_disambiguation(["Bima"])
        self.assertTrue(res["Bima"][0])
        self.assertIn("Bima (tokoh pewayangan)", res["Bima"][1])
        self.assertIn("Kota Bima", res["Bima"][1])

    # -------------------------------------------------------------------------
    # 3: Contextual Selection Engine
    # -------------------------------------------------------------------------

    def test_resolve_disambiguation_context_astronomy(self):
        options = ["Merkurius (planet)", "Merkurius (unsur)", "Merkurius (mitologi)"]
        context = "Planet ini memiliki orbit terdekat dengan matahari dalam tata surya kita."
        resolved = self.mapper.resolve_disambiguation_context("Merkurius", options, context)
        self.assertEqual(resolved, "Merkurius (planet)")

    def test_resolve_disambiguation_context_chemistry(self):
        options = ["Merkurius (planet)", "Merkurius (unsur)", "Merkurius (mitologi)"]
        context = "Cairan raksa di dalam termometer merupakan zat kimia logam yang dapat menyebabkan keracunan."
        resolved = self.mapper.resolve_disambiguation_context("Merkurius", options, context)
        self.assertEqual(resolved, "Merkurius (unsur)")

    def test_resolve_disambiguation_context_mythology(self):
        options = ["Merkurius (planet)", "Merkurius (unsur)", "Merkurius (mitologi)"]
        context = "Kuil pemujaan dewa dalam mitologi Romawi kuno didirikan untuk menghormatinya."
        resolved = self.mapper.resolve_disambiguation_context("Merkurius", options, context)
        self.assertEqual(resolved, "Merkurius (mitologi)")

    def test_resolve_disambiguation_context_fallback_when_ambiguous(self):
        options = ["Merkurius (planet)", "Merkurius (unsur)", "Merkurius (mitologi)"]
        context = "Informasi umum tanpa konteks spesifik sama sekali."
        resolved = self.mapper.resolve_disambiguation_context("Merkurius", options, context)
        self.assertIsNone(resolved)

    def test_resolve_disambiguation_context_with_gemini_client_fallback(self):
        options = ["Bima (tokoh pewayangan)", "Kota Bima"]
        context = "Kisah perjalanan ksatria Pandawa yang perkasa."

        mock_gemini = MagicMock()
        mock_gemini.translate_section.return_value = "Bima (tokoh pewayangan)"
        mapper_with_gemini = WikiLinkMapper(
            cache_db_path=str(self.cache_db),
            allow_network=False,
            gemini_client=mock_gemini,
        )

        resolved = mapper_with_gemini.resolve_disambiguation_context("Bima", options, context)
        self.assertEqual(resolved, "Bima (tokoh pewayangan)")

    # -------------------------------------------------------------------------
    # 4: Integration into process_wikitext
    # -------------------------------------------------------------------------

    @patch.object(WikiLinkMapper, "check_id_wiki_pages_exist")
    @patch.object(WikiLinkMapper, "check_id_disambiguation")
    def test_process_wikitext_resolves_disambiguation_links(self, mock_disambig, mock_exist):
        mock_exist.return_value = {"Merkurius": True}
        mock_disambig.return_value = {
            "Merkurius": (
                True,
                ["Merkurius (planet)", "Merkurius (unsur)", "Merkurius (mitologi)"],
            )
        }

        # Case A: Plain wikilink [[Merkurius]] in astronomy context
        wikitext_astronomy = "Di tata surya, orbit terdekat matahari adalah [[Merkurius]]."
        result_astronomy = self.mapper.process_wikitext(wikitext_astronomy, resolve_disambiguation=True)
        self.assertEqual(
            result_astronomy,
            "Di tata surya, orbit terdekat matahari adalah [[Merkurius (planet)|Merkurius]].",
        )

        # Case B: Wikilink with existing anchor [[Merkurius|bintang fajar]] in astronomy context
        wikitext_anchor = "Teleskop mengamati [[Merkurius|bintang fajar]] di orbit matahari."
        result_anchor = self.mapper.process_wikitext(wikitext_anchor, resolve_disambiguation=True)
        self.assertEqual(
            result_anchor,
            "Teleskop mengamati [[Merkurius (planet)|bintang fajar]] di orbit matahari.",
        )

        # Case C: Chemistry context
        wikitext_chem = "Termometer kuno mengandung cairan logam [[Merkurius]]."
        result_chem = self.mapper.process_wikitext(wikitext_chem, resolve_disambiguation=True)
        self.assertEqual(
            result_chem,
            "Termometer kuno mengandung cairan logam [[Merkurius (unsur)|Merkurius]].",
        )

        # Case D: When resolve_disambiguation=False, standard mapping applies
        result_disabled = self.mapper.process_wikitext(wikitext_astronomy, resolve_disambiguation=False)
        self.assertEqual(
            result_disabled,
            "Di tata surya, orbit terdekat matahari adalah [[Merkurius]].",
        )

    # -------------------------------------------------------------------------
    # 5: Cache Persistence & Migration
    # -------------------------------------------------------------------------

    def test_cache_persistence_of_disambiguation_columns(self):
        self.mapper.cache_page_link(
            en_title="Mercury",
            id_title="Merkurius",
            exists_on_id=True,
            source="id_direct",
            is_disambiguation=True,
            disambiguation_target="Merkurius (planet)",
        )

        cached = self.mapper.get_cached_page_link("Mercury")
        self.assertIsNotNone(cached)
        self.assertEqual(cached.target_id, "Merkurius")
        self.assertTrue(cached.is_disambiguation)
        self.assertEqual(cached.disambiguation_target, "Merkurius (planet)")

    def test_update_cached_disambiguation(self):
        self.mapper.cache_page_link(
            en_title="Venus",
            id_title="Venus",
            exists_on_id=True,
            source="id_direct",
            is_disambiguation=False,
        )

        self.mapper.update_cached_disambiguation(
            en_title="Venus",
            is_disambiguation=True,
            disambiguation_target="Venus (mitologi)",
        )

        cached = self.mapper.get_cached_page_link("Venus")
        self.assertIsNotNone(cached)
        self.assertTrue(cached.is_disambiguation)
        self.assertEqual(cached.disambiguation_target, "Venus (mitologi)")


if __name__ == "__main__":
    unittest.main()
