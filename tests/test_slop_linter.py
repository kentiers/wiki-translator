"""
Unit tests for AntiAISlopLinter (wiki_translator/slop_linter.py).
"""

import unittest
from wiki_translator.slop_linter import (
    AntiAISlopLinter,
    SlopLintResult,
    default_slop_linter,
)


class TestAntiAISlopLinter(unittest.TestCase):
    def setUp(self):
        self.linter = AntiAISlopLinter()

    # ----------------------------------------------------
    # 1. Banned Pattern Detection Tests
    # ----------------------------------------------------
    def test_detect_berbasis_di(self):
        text = "Perusahaan teknologi yang berbasis di Jakarta ini berkembang pesat."
        res = self.linter.lint(text)
        self.assertFalse(res.is_clean)
        self.assertTrue(any(v.rule_id == "calque_berbasis_di" for v in res.violations))

    def test_detect_dalam_upaya_untuk(self):
        text = "Pemerintah bertindak dalam upaya untuk menstabilkan harga pangan."
        res = self.linter.lint(text)
        self.assertTrue(any(v.rule_id == "calque_dalam_upaya_untuk" for v in res.violations))

    def test_detect_dalam_upaya_putus_asa_untuk(self):
        text = "Dia melompat dalam upaya putus asa untuk menyelamatkan diri."
        res = self.linter.lint(text)
        self.assertTrue(any(v.rule_id == "calque_upaya_putus_asa" for v in res.violations))

    def test_detect_memainkan_peran(self):
        text1 = "Tokoh ini memainkan peran kunci dalam negosiasi."
        text2 = "Vitamin ini memainkan peran penting bagi kesehatan."
        self.assertTrue(any(v.rule_id == "calque_memainkan_peran_kunci" for v in self.linter.lint(text1).violations))
        self.assertTrue(any(v.rule_id == "calque_memainkan_peran_penting" for v in self.linter.lint(text2).violations))

    def test_detect_menghasilkan_dampak(self):
        text = "Kebijakan baru tersebut menghasilkan dampak yang signifikan terhadap ekonomi."
        res = self.linter.lint(text)
        self.assertTrue(any(v.rule_id == "calque_menghasilkan_dampak" for v in res.violations))

    def test_detect_berfungsi_sebagai(self):
        text = "Gedung ini berfungsi sebagai kantor pusat."
        res = self.linter.lint(text)
        self.assertTrue(any(v.rule_id == "calque_berfungsi_sebagai" for v in res.violations))

    def test_detect_dikenal_karena_menjadi(self):
        text = "Ia dikenal karena menjadi penjelajah pertama yang mencapai kutub."
        res = self.linter.lint(text)
        self.assertTrue(any(v.rule_id == "calque_dikenal_karena_menjadi" for v in res.violations))

    def test_detect_membuat_debut(self):
        text = "Band ini membuat debutnya pada tahun 2010."
        res = self.linter.lint(text)
        self.assertTrue(any(v.rule_id == "calque_membuat_debut" for v in res.violations))

    def test_detect_merupakan_sebuah(self):
        text = "Inception merupakan sebuah film fiksi ilmiah yang disutradarai Christopher Nolan."
        res = self.linter.lint(text)
        self.assertTrue(any(v.rule_id == "calque_merupakan_sebuah" for v in res.violations))

    def test_detect_unidiomatic_di_mana(self):
        text = "Kota tersebut adalah tempat di mana ia dilahirkan."
        res = self.linter.lint(text)
        self.assertTrue(any(v.rule_id == "unidiomatic_di_mana" for v in res.violations))

    def test_allow_interrogative_di_mana(self):
        # A question ending with ? should NOT trigger unidiomatic_di_mana
        text = "Di mana letak ibukota negara tersebut?"
        res = self.linter.lint(text)
        self.assertFalse(any(v.rule_id == "unidiomatic_di_mana" for v in res.violations))

    def test_detect_passive_calque(self):
        text = "Para prajurit dipaksa untuk mematuhi perintah komandan."
        res = self.linter.lint(text)
        self.assertTrue(any(v.rule_id == "calque_dipaksa_untuk" for v in res.violations))

    def test_detect_reviu(self):
        text = "Kami sedang melakukan reviu terhadap artikel ini."
        res = self.linter.lint(text)
        self.assertTrue(any(v.rule_id == "calque_reviu" for v in res.violations))
        violation = next(v for v in res.violations if v.rule_id == "calque_reviu")
        self.assertIn("peninjauan", violation.suggestions)
        self.assertIn("pemeriksaan", violation.suggestions)
        self.assertIn("ulasan", violation.suggestions)

    def test_auto_fix_reviu(self):
        text = "Tim melakukan reviu mingguan."
        repaired, count = self.linter.auto_fix(text)
        self.assertIn("peninjauan", repaired)
        self.assertNotIn("reviu", repaired)

    def test_detect_em_dash(self):
        text = "Sutradara film tersebut — seorang pakar sinema — mulai syuting."
        res = self.linter.lint(text)
        self.assertTrue(any(v.rule_id == "orthography_em_dash" for v in res.violations))

    def test_detect_semicolon(self):
        text = "Syuting dimulai pada bulan Mei; penayangan dijadwalkan tahun depan."
        res = self.linter.lint(text)
        self.assertTrue(any(v.rule_id == "orthography_semicolon" for v in res.violations))

    def test_detect_pro_hyphen_calque(self):
        text = "Delapan demonstran pro-Palestina diamankan oleh petugas kepolisian."
        res = self.linter.lint(text)
        self.assertTrue(any(v.rule_id == "calque_pro_hyphen" for v in res.violations))
    # 2. Protected Zones (Refs, Cite, URLs) Tests
    # ----------------------------------------------------
    def test_protected_zones_ignored(self):
        # Even if banned phrases are inside citation titles or URLs or quotes, linter should ignore them
        text = (
            "Artikel ini mengutip buku.<ref>{{cite web |url=https://example.com/yang-berbasis-di-jakarta "
            "|title=Perusahaan yang berbasis di London}}</ref>\n"
            "Referensi kedua.<ref name=\"test\">Buku tentang di mana mereka berada.</ref>\n"
            "Tautan: [https://example.com/dalam-upaya-untuk Sumber luar]"
        )
        res = self.linter.lint(text)
        self.assertTrue(res.is_clean)
        self.assertEqual(len(res.violations), 0)

    # ----------------------------------------------------
    # 3. Readability & Naturalness Scoring Tests
    # ----------------------------------------------------
    def test_scoring_clean_text(self):
        text = "Indonesia adalah negara kepulauan yang terletak di Asia Tenggara."
        res = self.linter.lint(text)
        self.assertEqual(res.score, 100)
        self.assertTrue(res.is_clean)

    def test_scoring_with_violations(self):
        text = (
            "Perusahaan yang berbasis di Tokyo ini memainkan peran kunci dalam industri. "
            "Kebijakan ini menghasilkan dampak yang signifikan."
        )
        res = self.linter.lint(text)
        self.assertLess(res.score, 100)
        self.assertGreaterEqual(res.score, 0)
        self.assertGreater(len(res.violations), 1)

    # ----------------------------------------------------
    # 4. auto_fix Tests
    # ----------------------------------------------------
    def test_auto_fix_calques(self):
        text = (
            "Organisasi yang berbasis di Jenewa ini memainkan peran kunci dalam perdamaian. "
            "Mereka bertindak dalam upaya untuk mencapai stabilitas. "
            "Film ini membuat debutnya tahun lalu."
        )
        repaired, count = self.linter.auto_fix(text)
        self.assertGreater(count, 0)
        self.assertNotIn("yang berbasis di", repaired)
        self.assertIn("berpusat di", repaired)
        self.assertNotIn("memainkan peran kunci", repaired)
        self.assertIn("berperan kunci", repaired)
        self.assertNotIn("dalam upaya untuk", repaired)
        self.assertIn("demi", repaired)
        self.assertNotIn("membuat debutnya", repaired)
        self.assertIn("memulai debut", repaired)

    def test_auto_fix_preserves_refs_and_urls(self):
        text = (
            "Perusahaan yang berbasis di Bali membuat debutnya.<ref>Lihat "
            "https://example.com/yang-berbasis-di</ref>"
        )
        repaired, count = self.linter.auto_fix(text)
        self.assertIn("berpusat di", repaired)
        self.assertIn("memulai debut", repaired)
        # Inside <ref> URL should remain untouched
        self.assertIn("https://example.com/yang-berbasis-di", repaired)

    def test_auto_fix_merupakan_sebuah(self):
        text = "Titanic merupakan sebuah film drama romantis yang legendaris."
        repaired, count = self.linter.auto_fix(text)
        self.assertIn("merupakan film drama", repaired)
        self.assertNotIn("merupakan sebuah film", repaired)

    def test_auto_fix_passive_calque(self):
        text = "Mereka dipaksa untuk mundur dari medan tempur."
        repaired, count = self.linter.auto_fix(text)
        self.assertIn("dipaksa mundur", repaired)
        self.assertNotIn("dipaksa untuk mundur", repaired)

    def test_auto_fix_punctuation_and_pro_hyphen(self):
        text = "Aktor tersebut — peraih penghargaan — hadir di lokasi; syuting berjalan lancar bersama aktivis pro-Palestina."
        repaired, count = self.linter.auto_fix(text)
        self.assertNotIn("—", repaired)
        self.assertNotIn(";", repaired)
        self.assertNotIn("pro-Palestina", repaired)
        self.assertIn("pendukung Palestina", repaired)
        self.assertGreater(count, 0)
    def test_default_instance(self):
        self.assertIsNotNone(default_slop_linter)
        res = default_slop_linter.lint("Teks bersih.")
        self.assertEqual(res.score, 100)


if __name__ == "__main__":
    unittest.main()
