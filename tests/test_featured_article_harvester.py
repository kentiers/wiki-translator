"""
Unit tests for Featured Article (Artikel Pilihan) Peer-Review Harvester.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from wiki_translator.featured_article_harvester import (
    FeaturedArticleHarvester,
    APCritiquePoint,
    default_fa_harvester,
)
from wiki_translator.slop_linter import default_slop_linter


class TestFeaturedArticleHarvester(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "test_ap.sqlite"
        self.mock_client = MagicMock()
        self.harvester = FeaturedArticleHarvester(client=self.mock_client, db_path=self.db_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_seed_ap_critiques_present(self):
        json_path = Path(self.tmp_dir.name) / "ap_rules.json"
        exported = self.harvester.export_rules_json(json_path)
        self.assertTrue(exported.exists())
        self.assertTrue(exported.stat().st_size > 100)

    def test_parse_review_wikitext(self):
        sample_review = (
            "==== Komentar dari Mimihitam ====\n"
            "* \"kedatangannya di London\" ==> mungkin lebih pas \"diboyong ke\", karena kedatangan mengesankan orang.\n"
            "* \"bagian atas yang bundar\" ==> lebih pas melengkung daripada bundar.\n"
        )
        points = self.harvester.parse_review_wikitext("Batu Rosetta", sample_review, year=2020)
        self.assertEqual(len(points), 2)
        quotes = [p.quote for p in points]
        self.assertIn("kedatangannya di London", quotes)
        self.assertIn("bagian atas yang bundar", quotes)

    def test_slop_linter_flags_ap_calques(self):
        # Linter should flag 'kedatangannya di London' for objects
        text = "Setelah kedatangannya di London, prasasti tersebut dipamerkan di museum."
        report = default_slop_linter.lint(text)
        self.assertFalse(report.is_clean)
        rule_ids = [v.rule_id for v in report.violations]
        self.assertIn("calque_kedatangan_benda", rule_ids)


if __name__ == "__main__":
    unittest.main()
