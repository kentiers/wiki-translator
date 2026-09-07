"""
Unit tests for Dynamic HistoricalOfficesManager.
"""

import unittest
from wiki_translator.historical_offices import HistoricalOfficesManager, default_offices_manager


class TestHistoricalOffices(unittest.TestCase):
    def setUp(self):
        self.manager = default_offices_manager

    def test_schema_loaded(self):
        self.assertGreater(self.manager.total_offices, 10)

    def test_scan_text_grand_administrator(self):
        text = "Xin Wuxian was the Grand Administrator of Jiuquan commandery."
        matches = self.manager.scan_text(text)
        matched_keys = [m.key for m in matches]
        self.assertIn("taishou", matched_keys)
        self.assertEqual(matches[0].canonical_id_title, "Gubernur Komanderi")

    def test_get_office_glossary(self):
        text = "The Roman consul led the legions, while the grand vizier advised the sultan."
        glossary = self.manager.get_office_glossary(text)
        self.assertIn("consul", glossary)
        self.assertEqual(glossary["consul"], "Konsul")
        self.assertIn("grand vizier", glossary)
        self.assertEqual(glossary["grand vizier"], "Wazir Agung")

    def test_get_editorial_guidance_for_text(self):
        text = "The Emperor appointed the Strong Crossbow General and Commandant of Waters and Parks."
        guidance = self.manager.get_editorial_guidance_for_text(text)
        self.assertIn("Panduan Gelar & Jabatan Birokrasi Sejarah Kuno", guidance)
        self.assertIn("Jenderal Busur Silang", guidance)


if __name__ == "__main__":
    unittest.main()
