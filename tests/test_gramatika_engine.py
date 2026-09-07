"""
Unit tests for GramatikaEngine (Kateglo / TBBBI rules).
"""

import unittest
from wiki_translator.gramatika_engine import GramatikaEngine, default_gramatika_engine


class TestGramatikaEngine(unittest.TestCase):
    def setUp(self):
        self.engine = default_gramatika_engine

    def test_knowledge_base_loaded(self):
        self.assertGreater(self.engine.total_terms, 200)
        self.assertGreater(self.engine.total_tables, 10)
        self.assertGreater(self.engine.total_diagrams, 10)

    def test_get_term_definition(self):
        defn = self.engine.get_term_definition("adverbia")
        self.assertIsNotNone(defn)
        self.assertIn("kata yang menjelaskan", defn.lower())

    def test_search_terms(self):
        matches = self.engine.search_terms("transitif")
        self.assertGreater(len(matches), 0)

    def test_normalize_sentence_openers(self):
        text = "Gorbachev mengundurkan diri. Sehingga, Uni Soviet bubar. Sedangkan, oposisi bersorak."
        fixed, count, details = self.engine.normalize_sentence_openers(text)
        self.assertEqual(count, 2)
        self.assertIn("Akibatnya, Uni Soviet bubar.", fixed)
        self.assertIn("Sementara itu, oposisi bersorak.", fixed)

    def test_normalize_negation_agreement(self):
        text = "Wilayah ini tidak sebuah negara dan tidak merupakan bagian resmi."
        fixed, count, details = self.engine.normalize_negation_agreement(text)
        self.assertEqual(count, 2)
        self.assertIn("bukan sebuah negara", fixed)
        self.assertIn("bukan merupakan bagian", fixed)

    def test_normalize_adversarial_conjunction_commas(self):
        text = "Ia menyetujui usulan itu tetapi rekan-rekannya menolak."
        fixed, count = self.engine.normalize_adversarial_conjunction_commas(text)
        self.assertEqual(count, 1)
        self.assertIn("usulan itu, tetapi", fixed)

    def test_apply_all_gramatika_fixes(self):
        text = "Dan, mereka tidak sebuah kelompok biasa tetapi sebuah ormas."
        fixed, count, details = self.engine.apply_all_gramatika_fixes(text)
        self.assertGreaterEqual(count, 2)
        self.assertTrue(fixed.startswith("Selain itu, "))
        self.assertIn("bukan sebuah kelompok", fixed)


if __name__ == "__main__":
    unittest.main()
