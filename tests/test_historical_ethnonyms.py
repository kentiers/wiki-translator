"""
Unit tests for Dynamic HistoricalEthnonymsManager.
"""

import unittest
from wiki_translator.historical_ethnonyms import HistoricalEthnonymsManager, default_ethnonyms_manager


class TestHistoricalEthnonyms(unittest.TestCase):
    def setUp(self):
        self.manager = default_ethnonyms_manager

    def test_schema_loaded(self):
        self.assertGreater(self.manager.total_entities, 10)
        self.assertIn("Qiang", self.manager.get_entity_names())

    def test_scan_text_qiang_and_xiongnu(self):
        text = "The Western Qiang and Xianlian chieftains sought alliance with Xiongnu chanyu."
        matches = self.manager.scan_text(text)
        matched_names = [m.name for m in matches]
        self.assertIn("Qiang", matched_names)
        self.assertIn("Xiongnu", matched_names)

    def test_scan_text_germanic_and_goths(self):
        text = "The Roman Empire fought against Visigoths and other Germanic tribes."
        matches = self.manager.scan_text(text)
        matched_names = [m.name for m in matches]
        self.assertIn("Germanik", matched_names)
    def test_get_editorial_guidance_for_text(self):
        text = "General Zhao Chongguo led campaigns against the Western Qiang."
        guidance = self.manager.get_editorial_guidance_for_text(text)
        self.assertIn("Qiang", guidance)
        self.assertIn("bangsa Qiang", guidance)
    def test_audit_and_fix_homonym_blunders_qiang_han(self):
        text = "Dalam kampanye militer melawan Qiang, pasukan bergerak menyerang suku Han di sekitar danau."
        fixed, count, details = self.manager.audit_and_fix_homonym_blunders(text)
        self.assertEqual(count, 1)
        self.assertIn("suku Qiang Han", fixed)
        self.assertNotIn("menyerang suku Han di", fixed)

    def test_audit_and_fix_homonym_blunders_does_not_corrupt_dinasti_han(self):
        text = "Kaisar Wu dari Dinasti Han memerintahkan kampanye militer melawan Qiang."
        fixed, count, details = self.manager.audit_and_fix_homonym_blunders(text)
        self.assertEqual(count, 0)
        self.assertEqual(fixed, text)

    def test_audit_and_fix_homonym_blunders_does_not_double_convert(self):
        text = "Pasukan berhadapan dengan suku Qiang Han dan suku Kai."
        fixed, count, details = self.manager.audit_and_fix_homonym_blunders(text)
        self.assertEqual(count, 0)
        self.assertEqual(fixed, text)

    def test_audit_and_fix_homonym_blunders_hre(self):
        text = "Kekaisaran Romawi dipimpin oleh kaisar dari wangsa Habsburg hingga tahun 1806."
        fixed, count, details = self.manager.audit_and_fix_homonym_blunders(text)
        self.assertEqual(count, 1)
        self.assertIn("Kekaisaran Romawi Suci", fixed)


if __name__ == "__main__":
    unittest.main()
