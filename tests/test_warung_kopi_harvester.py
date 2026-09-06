"""
Unit tests for Warung Kopi (Bahasa) Community Consensus Harvester & Ingestion Engine.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from wiki_translator.warung_kopi_harvester import (
    WarungKopiHarvester,
    WarungKopiTerm,
    default_warung_kopi_harvester,
)
from wiki_translator.glossary_resolver import default_glossary_resolver
from wiki_translator.slop_linter import default_slop_linter


class TestWarungKopiHarvester(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "test_wk.sqlite"
        self.mock_client = MagicMock()
        self.harvester = WarungKopiHarvester(client=self.mock_client, db_path=self.db_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_seed_terms_present(self):
        lex = self.harvester.export_lexicon_dict()
        self.assertIn("film", lex)
        self.assertIn("computing_science", lex)
        self.assertEqual(lex["computing_science"]["monospaced font"], "fon berjarak tunggal")
        self.assertEqual(lex["geography"]["territorial extent"], "luas wilayah")
        self.assertEqual(lex["history_social"]["rump state"], "negara sisa")

    def test_parse_thread_for_terms(self):
        thread_title = "== Padanan kata territorial extent =="
        thread_body = (
            "Halo rekan-rekan, apa padanan yang tepat untuk istilah ''territorial extent''?\n"
            "Dalam konteks geografi negara, saya mengusulkan \"luas wilayah\" atau \"cakupan wilayah\".\n"
            "::Saya sepakat dengan \"luas wilayah\" karena sudah baku di BPS dan KBBI."
        )
        terms = self.harvester.parse_thread_for_terms(thread_title, thread_body, year=2020)
        self.assertTrue(len(terms) > 0)
        en_terms = [t.en_term for t in terms]
        id_terms = [t.id_term for t in terms]
        self.assertTrue(any("territorial extent" in t for t in en_terms))
        self.assertTrue(any("luas wilayah" in t for t in id_terms))

    def test_export_lexicon_json(self):
        json_path = Path(self.tmp_dir.name) / "output.json"
        exported = self.harvester.export_lexicon_json(json_path)
        self.assertTrue(exported.exists())
        self.assertTrue(exported.stat().st_size > 50)

    def test_glossary_resolver_integration(self):
        # Glossary resolver should dynamically resolve Warung Kopi consensus terms
        res_film = default_glossary_resolver.resolve_term("film score", topic="film")
        self.assertIn(res_film, ("tata musik", "musik film", "musik latar"))

        res_cs = default_glossary_resolver.resolve_term("monospaced font", topic="computing_science")
        self.assertEqual(res_cs, "fon berjarak tunggal")

        res_geo = default_glossary_resolver.resolve_term("suburb", topic="geography")
        self.assertEqual(res_geo, "pinggiran kota")

    def test_slop_linter_calque_skor_film(self):
        # Linter should flag 'skor film' based on Warung Kopi consensus
        bad_text = "Komposer ini memenangkan penghargaan untuk kategori skor film terbaik."
        lint_res = default_slop_linter.lint(bad_text)
        self.assertFalse(lint_res.is_clean)
        rule_ids = [v.rule_id for v in lint_res.violations]
        self.assertIn("calque_skor_film", rule_ids)


if __name__ == "__main__":
    unittest.main()
