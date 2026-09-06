"""
Unit tests for LexicalRegisterReranker (wiki_translator/lexical_register.py).
"""

import unittest
from wiki_translator.lexical_register import LexicalRegisterReranker, default_lexical_reranker


class TestLexicalRegisterReranker(unittest.TestCase):
    def setUp(self):
        self.reranker = LexicalRegisterReranker()

    def test_bureaucratic_loanwords_elevation(self):
        # Active and passive loanword forms
        text1 = "Pemerintah mengimplementasikan kebijakan baru dan program ini diimplementasikan di seluruh wilayah."
        elevated1, count1, _ = self.reranker.elevate_text(text1)
        self.assertEqual(count1, 2)
        self.assertIn("menerapkan kebijakan", elevated1)
        self.assertIn("diterapkan di seluruh", elevated1)
        self.assertNotIn("mengimplementasikan", elevated1)

        # Inisiasi -> prakarsai
        text2 = "Gorbachev menginisiasi pembaruan politik yang diinisiasi oleh kaum muda."
        elevated2, count2, _ = self.reranker.elevate_text(text2)
        self.assertEqual(count2, 2)
        self.assertIn("memprakarsai pembaruan", elevated2)
        self.assertIn("diprakarsai oleh kaum muda", elevated2)

        # Refleksi -> cermin
        text3 = "Sikap ini merefleksikan pandangan umum dan direfleksikan dalam karyanya."
        elevated3, count3, _ = self.reranker.elevate_text(text3)
        self.assertEqual(count3, 2)
        self.assertIn("mencerminkan pandangan", elevated3)
        self.assertIn("dicerminkan dalam karyanya", elevated3)

        # Meminimalisir -> meminimalkan
        text4 = "Upaya untuk meminimalisir dampak ekonomi."
        elevated4, count4, _ = self.reranker.elevate_text(text4)
        self.assertEqual(count4, 1)
        self.assertIn("meminimalkan dampak", elevated4)

    def test_direct_core_verbs(self):
        text = "Ia mengambil keputusan untuk mundur dan melakukan penolakan terhadap tawaran itu."
        elevated, count, _ = self.reranker.elevate_text(text)
        self.assertEqual(count, 2)
        self.assertIn("memutuskan untuk mundur", elevated)
        self.assertIn("menolak tawaran itu", elevated)

    def test_biography_death_phrasing(self):
        text = "Beberapa bulan sebelum kematiannya, ia menulis memoar dan sampai kematiannya ia tetap teguh."
        elevated, count, _ = self.reranker.elevate_text(text)
        self.assertIn("menjelang akhir hayatnya", elevated)
        self.assertIn("hingga akhir hayatnya", elevated)

if __name__ == "__main__":
    unittest.main()
