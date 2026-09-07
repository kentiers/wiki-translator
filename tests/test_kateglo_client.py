"""
Unit tests for KategloClient (wiki_translator/kateglo_client.py).
"""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from wiki_translator.kateglo_client import KategloClient, default_kateglo_client


class TestKategloClient(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_db = Path(self.temp_dir.name) / "test_kateglo.sqlite"
        self.client = KategloClient(cache_db_path=str(self.cache_db), allow_network=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_init_db_creates_tables(self):
        import sqlite3
        conn = sqlite3.connect(self.cache_db)
        try:
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            self.assertIn("kateglo_entries", tables)
            self.assertIn("kateglo_thesaurus", tables)
            self.assertIn("kateglo_glossary", tables)
        finally:
            conn.close()
    def test_offline_mode_returns_cached_or_none(self):
        offline_client = KategloClient(cache_db_path=str(self.cache_db), allow_network=False)
        # Not in cache, network disabled
        self.assertIsNone(offline_client.get_entry_detail("bahtera"))
        self.assertEqual(offline_client.get_synonyms("bahtera"), [])

    @patch.object(KategloClient, "_api_get")
    def test_get_entry_detail_caches_response(self, mock_api):
        mock_api.return_value = {
            "indeks": "bahtera",
            "entri": [
                {
                    "entri": "bahtera",
                    "sumber_kode": "KBBI4",
                    "makna": [{"makna": "perahu; kapal"}],
                }
            ],
            "tesaurus": {"sinonim": ["perahu", "kapal"], "antonim": []},
            "glosarium": [
                {"asing": "ark", "indonesia": "bahtera"}
            ],
        }

        # First call hits mock API
        detail = self.client.get_entry_detail("bahtera")
        self.assertIsNotNone(detail)
        self.assertEqual(detail["indeks"], "bahtera")
        mock_api.assert_called_once()

        # Second call hits local SQLite cache (mock not called again)
        mock_api.reset_mock()
        cached_detail = self.client.get_entry_detail("bahtera")
        self.assertIsNotNone(cached_detail)
        self.assertEqual(cached_detail["indeks"], "bahtera")
        mock_api.assert_not_called()

        # Verify glossary was indexed into kateglo_glossary table
        matches = self.client.find_glossary_terms("ark")
        self.assertIn("bahtera", matches)

    @patch.object(KategloClient, "_api_get")
    def test_get_synonyms_from_thesaurus_endpoint(self, mock_api):
        # Entry detail returns no embedded thesaurus
        def mock_endpoints(endpoint, params=None):
            if "kamus/detail" in endpoint:
                return {"indeks": "uji", "entri": [{"entri": "uji"}]}
            if "tesaurus/cari" in endpoint:
                return {
                    "data": [
                        {"indeks": "uji", "sinonim": "tes; eksperimen; percobaan"}
                    ]
                }
            return None

        mock_api.side_effect = mock_endpoints

        synonyms = self.client.get_synonyms("uji")
        self.assertIn("tes", synonyms)
        self.assertIn("eksperimen", synonyms)
        self.assertIn("percobaan", synonyms)
    @patch.object(KategloClient, "_api_get")
    def test_search_by_definition_caches_results(self, mock_api):
        mock_api.return_value = {
            "query": "pemerintahan",
            "total": 1,
            "data": [
                {"entri": "absolutisme", "makna_cocok": [{"makna": "bentuk pemerintahan monarki"}]}
            ],
        }

        results = self.client.search_by_definition("pemerintahan")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["entri"], "absolutisme")
        mock_api.assert_called_once()

        # Second call hits cache
        mock_api.reset_mock()
        cached = self.client.search_by_definition("pemerintahan")
        self.assertEqual(len(cached), 1)
        mock_api.assert_not_called()

    @patch.object(KategloClient, "_api_get")
    def test_get_categories_and_bidang(self, mock_api):
        mock_api.return_value = {
            "bidang": [{"kode": "Fis", "nama": "Fisika"}],
            "kelas_kata": [{"kode": "n", "nama": "Nomina"}],
        }
        cats = self.client.get_categories()
        self.assertIn("bidang", cats)
        self.assertEqual(cats["bidang"][0]["nama"], "Fisika")

    @patch.object(KategloClient, "_api_get")
    def test_rhyme_and_call_endpoint(self, mock_api):
        mock_api.return_value = {"pemenggalan": "de.mok.ra.si", "rima_akhir": "si"}
        r = self.client.get_rhyme_and_syllabification("demokrasi")
        self.assertEqual(r["pemenggalan"], "de.mok.ra.si")

        # Dynamic pass-through dispatcher
        mock_api.return_value = {"custom_feature": True}
        res = self.client.call_endpoint("etimologi/cari/kata")
        self.assertTrue(res.get("custom_feature"))


if __name__ == "__main__":
    unittest.main()
