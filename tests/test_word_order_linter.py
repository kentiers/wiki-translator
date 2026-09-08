"""
Unit tests for WordOrderLinter (wiki_translator/word_order_linter.py).
Validates Indonesian syntactic word order and Hukum D-M constituent arrangements.
"""

import unittest
from wiki_translator.word_order_linter import (
    WordOrderLinter,
    default_word_order_linter,
)


class TestWordOrderLinter(unittest.TestCase):
    def setUp(self):
        self.linter = default_word_order_linter

    def test_default_instance(self):
        self.assertIsNotNone(self.linter)
        self.assertIsInstance(self.linter, WordOrderLinter)

    # ----------------------------------------------------
    # 1. Hukum D-M Inversion Tests (Noun-Adjunct Calques)
    # ----------------------------------------------------
    def test_detects_then_title_inversion(self):
        text = "Pada tahun 1950, kemudian presiden menandatangani pakta pertahanan."
        res = self.linter.audit_word_order(text)
        self.assertFalse(res.passed)
        self.assertTrue(any(iss.category == "hukum_dm_inversi" for iss in res.issues))
        self.assertTrue(any("presiden saat itu" in iss.suggested_fix for iss in res.issues))

    def test_detects_above_mentioned_inversion(self):
        text = "Dokumen di atas disebutkan merupakan rujukan resmi."
        res = self.linter.audit_word_order(text)
        self.assertFalse(res.passed)
        self.assertTrue(any("di atas disebutkan" in iss.matched_text for iss in res.issues))

    # ----------------------------------------------------
    # 2. Aspect - Modality - Negation Sequencing Tests
    # ----------------------------------------------------
    def test_detects_and_fixes_aspect_negation_inversion(self):
        # 'akan tidak' -> 'tidak akan'
        text = "Pemerintah daerah akan tidak memberikan izin tambang."
        res = self.linter.audit_word_order(text)
        self.assertFalse(res.passed)
        self.assertTrue(any(iss.category == "urutan_aspek_modalitas_negasi" for iss in res.issues))

        fixed, count, details = self.linter.auto_fix_word_order(text)
        self.assertEqual(count, 1)
        self.assertIn("tidak akan memberikan", fixed)

    def test_detects_and_fixes_modality_aspect_inversion(self):
        # 'bisa belum' -> 'belum bisa'
        text = "Pasukan bantuan bisa belum mencapai garis depan."
        fixed, count, details = self.linter.auto_fix_word_order(text)
        self.assertEqual(count, 1)
        self.assertIn("belum bisa mencapai", fixed)

    # ----------------------------------------------------
    # 3. Declarative Complement 'bahwa' vs 'yang'
    # ----------------------------------------------------
    def test_detects_and_fixes_reporting_verb_relative_yang(self):
        # 'menyatakan yang dia' -> 'menyatakan bahwa dia'
        text = "Kaisar menyatakan yang dia akan memimpin ekspedisi bantuan."
        res = self.linter.audit_word_order(text)
        self.assertFalse(res.passed)
        self.assertTrue(any(iss.category == "pewatas_relatif_dan_komplemen" for iss in res.issues))

        fixed, count, details = self.linter.auto_fix_word_order(text)
        self.assertEqual(count, 1)
        self.assertIn("menyatakan bahwa dia", fixed)

    # ----------------------------------------------------
    # 4. Plural-Quantifier Duplication (Anti-Pleonasme)
    # ----------------------------------------------------
    def test_detects_and_fixes_plural_quantifier_pleonasm(self):
        # 'para menteri-menteri' -> 'para menteri'
        text = "Rapat dihadiri oleh para menteri-menteri dan semua prajurit-prajurit."
        fixed, count, details = self.linter.auto_fix_word_order(text)
        self.assertEqual(count, 2)
        self.assertIn("para menteri", fixed)
        self.assertIn("semua prajurit", fixed)

    # ----------------------------------------------------
    # 5. Clean Valid Text Passes (100% Score)
    # ----------------------------------------------------
    def test_clean_text_passes_with_perfect_score(self):
        text = "Presiden saat itu menyatakan bahwa kebijakan baru akan segera diterapkan untuk seluruh menteri."
        res = self.linter.audit_word_order(text)
        self.assertTrue(res.passed)
        self.assertEqual(res.score, 100)
        self.assertEqual(len(res.issues), 0)


if __name__ == "__main__":
    unittest.main()
