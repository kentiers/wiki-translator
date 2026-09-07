"""
Unit tests for Dynamic EYDEngine (official EYD V rules).
"""

import unittest
from wiki_translator.eyd_engine import EYDEngine, default_eyd_engine


class TestEYDEngine(unittest.TestCase):
    def setUp(self):
        self.engine = default_eyd_engine

    def test_rules_loaded(self):
        self.assertGreater(self.engine.total_rules, 250)
        self.assertGreater(len(self.engine.bound_morphemes), 20)
        self.assertEqual(len(self.engine.compound_pun_conjunctions), 12)

    def test_search_rules(self):
        matches = self.engine.search_rules("elipsis")
        self.assertGreater(len(matches), 0)

    def test_normalize_bound_morphemes_merged(self):
        text = "Pada era pasca perang, kerja sama antar kelompok meningkat untuk tujuan non formal."
        fixed, count, details = self.engine.normalize_bound_morphemes(text)
        self.assertEqual(count, 3)
        self.assertIn("pascaperang", fixed)
        self.assertIn("antarkelompok", fixed)
        self.assertIn("nonformal", fixed)

    def test_normalize_bound_morphemes_capital_hyphen(self):
        text = "Sikap pro Palestina dan gerakan non Indonesia serta anti PKI dibahas."
        fixed, count, details = self.engine.normalize_bound_morphemes(text)
        self.assertEqual(count, 3)
        self.assertIn("pro-Palestina", fixed)
        self.assertIn("non-Indonesia", fixed)
        self.assertIn("anti-PKI", fixed)

    def test_normalize_pun_particles(self):
        text = "Meskipun demikian, siapapun dan apapun yang terjadi, mereka tidak akan menyerah."
        fixed, count, details = self.engine.normalize_pun_particles(text)
        self.assertEqual(count, 2)
        # 'Meskipun' remains intact!
        self.assertTrue(fixed.startswith("Meskipun"))
        self.assertIn("siapa pun", fixed)
        self.assertIn("apa pun", fixed)

    def test_normalize_en_dash_ranges(self):
        text = "Perang berlangsung pada tahun 1941 - 1945 dan tercatat pada hlm. 12 - 15."
        fixed, count, details = self.engine.normalize_en_dash_ranges(text)
        self.assertEqual(count, 2)
        self.assertIn("1941–1945", fixed)
        self.assertIn("hlm. 12–15", fixed)

    def test_apply_all_eyd_fixes(self):
        text = "Pada era pasca perang, apapun tantangannya pada 1945-1949, bangsa ini bersatu."
        fixed, count, details = self.engine.apply_all_eyd_fixes(text)
        self.assertGreaterEqual(count, 3)
        self.assertIn("pascaperang", fixed)
        self.assertIn("apa pun", fixed)
        self.assertIn("1945–1949", fixed)
    def test_bound_morphemes_avoids_conjunctions_and_musim_semi(self):
        # 'musim semi dan musim panas' must NOT become 'semidan'
        text = "Pasukan hidup dari hasil bumi setempat selama musim semi dan musim panas."
        fixed, count, details = self.engine.normalize_bound_morphemes(text)
        self.assertEqual(count, 0)
        self.assertEqual(fixed, text)
    def test_contextual_bound_morphemes_guardrails(self):
        """Validates all contextual homonyms and EYD V official exceptions."""
        cases = [
            ("Sistem tata kelola pemerintahan dan tata ruang daerah.", "Sistem tata kelola pemerintahan dan tata ruang daerah."),
            ("Pengakuan secara de facto dan de jure telah diberikan.", "Pengakuan secara de facto dan de jure telah diberikan."),
            ("Percaya kepada Tuhan Yang Maha Esa.", "Percaya kepada Tuhan Yang Maha Esa."),
            ("Perdebatan antara kubu pro dan kubu kontra berlangsung sengit.", "Perdebatan antara kubu pro dan kubu kontra berlangsung sengit."),
            ("Tersedia jasa antar barang dan kurir antar surat kilat.", "Tersedia jasa antar barang dan kurir antar surat kilat."),
            ("Analisis pada tingkat makro dan tingkat mikro.", "Analisis pada tingkat makro dan tingkat mikro."),
            ("Lolos ke babak semi final dan membangun pos semi permanen.", "Lolos ke babak semifinal dan membangun pos semipermanen."),
            ("Kerja sama antar negara di kawasan Asia.", "Kerja sama antarnegara di kawasan Asia."),
        ]
        for src, expected in cases:
            fixed, _, _ = self.engine.normalize_bound_morphemes(src)
            self.assertEqual(fixed, expected, f"Failed on input: {src}")


if __name__ == "__main__":
    unittest.main()
