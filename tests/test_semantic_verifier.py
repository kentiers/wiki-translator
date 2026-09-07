"""
Unit tests for Universal SemanticVerifier (2nd Checking System across all domains).
"""

import unittest
from wiki_translator.semantic_verifier import UniversalSemanticVerifier, default_semantic_verifier


class TestUniversalSemanticVerifier(unittest.TestCase):
    def setUp(self):
        self.verifier = default_semantic_verifier

    def test_sentence_splitting(self):
        text = "Einstein proposed the theory in 1905. It revolutionized physics. He won the Nobel Prize later."
        sents = self.verifier.split_into_sentences(text)
        self.assertEqual(len(sents), 3)

    # -------------------------------------------------------------------------
    # Domain 1: Science & Computing
    # -------------------------------------------------------------------------
    def test_computing_dropped_possessive_entity(self):
        en = "Researchers demonstrated that Shor's algorithm could factor large integers efficiently."
        id_bad = "Para peneliti membuktikan bahwa algoritma dapat memfaktorkan bilangan bulat besar secara efisien."
        issues = self.verifier.verify_sentence_pair(en, id_bad, 1, topic="computing_science")
        self.assertGreater(len(issues), 0)
        self.assertEqual(issues[0].category, "Aktor / Pemilik Terpotong (Entity Dropout)")
        self.assertIn("Shor's algorithm", issues[0].source_snippet)

    def test_science_polarity_contradiction(self):
        en = "The experimental results showed that temperature increased over time."
        id_bad = "Hasil eksperimen menunjukkan bahwa suhu menurun seiring berjalannya waktu."
        issues = self.verifier.verify_sentence_pair(en, id_bad, 1, topic="physics_mathematics")
        self.assertGreater(len(issues), 0)
        self.assertEqual(issues[0].category, "Pembalikan Polaritas Pernyataan (Contradiction)")

    # -------------------------------------------------------------------------
    # Domain 2: Medicine & Biology
    # -------------------------------------------------------------------------
    def test_medicine_benign_malignant_contradiction(self):
        en = "Histological examination confirmed the tumor was benign."
        id_bad = "Pemeriksaan histologis mengonfirmasi bahwa tumor tersebut ganas."
        issues = self.verifier.verify_sentence_pair(en, id_bad, 1, topic="medical_biology")
        self.assertGreater(len(issues), 0)
        self.assertEqual(issues[0].category, "Pembalikan Polaritas Pernyataan (Contradiction)")

    def test_medicine_transitive_pronoun_trap(self):
        en = "The physician treated him for acute respiratory failure."
        id_bad = "Dokter merawat dirinya atas gagal napas akut."
        issues = self.verifier.verify_sentence_pair(en, id_bad, 1, topic="medical_biology")
        self.assertGreater(len(issues), 0)
        self.assertEqual(issues[0].category, "Pembalikan Pronomina (Reflexive Inversion Trap)")

    # -------------------------------------------------------------------------
    # Domain 3: Film & Entertainment
    # -------------------------------------------------------------------------
    def test_film_dropped_director_possessive(self):
        en = "Critics praised Nolan's direction and the visual effects."
        id_bad = "Kritikus memuji penyutradaraan dan efek visualnya."
        issues = self.verifier.verify_sentence_pair(en, id_bad, 1, topic="film")
        self.assertGreater(len(issues), 0)
        self.assertEqual(issues[0].category, "Aktor / Pemilik Terpotong (Entity Dropout)")

    def test_entertainment_modality_shift(self):
        en = "Analysts suggested the album may debut at number one."
        id_bad = "Para analis menyatakan bahwa album tersebut pasti debut di posisi nomor satu."
        issues = self.verifier.verify_sentence_pair(en, id_bad, 1, topic="media")
        self.assertGreater(len(issues), 0)
        self.assertEqual(issues[0].category, "Distorsi Derajat Kepastian (Modality Shift)")

    # -------------------------------------------------------------------------
    # Domain 4: General Biography & History
    # -------------------------------------------------------------------------
    def test_history_compass_mangling(self):
        en = "The cavalry proceeded to the northeast of the lake."
        id_bad = "Pasukan kavaleri maju ke sebelah timur Laut Danau."
        issues = self.verifier.verify_sentence_pair(en, id_bad, 1, topic="history_social")
        self.assertGreater(len(issues), 0)
        self.assertEqual(issues[0].category, "Cacat Kapitalisasi / Pemenggalan Arah Mata Angin")

    def test_general_clean_article_passes_all_checks(self):
        en = "Ada Lovelace wrote the first algorithm for Babbage's analytical engine in 1843."
        id_good = "Ada Lovelace menulis algoritma pertama untuk mesin analitis Babbage pada tahun 1843."
        report = self.verifier.verify_article(en, id_good, topic="computing_science")
        self.assertTrue(report.passed)
        self.assertEqual(report.score, 100)


if __name__ == "__main__":
    unittest.main()
