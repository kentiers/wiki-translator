"""
Unit tests for StorageManager centralized storage & cache paths manager.
"""

import os
from pathlib import Path
import tempfile
import unittest

from wiki_translator.storage_manager import (
    StorageManager,
    default_storage_manager,
    KNOWN_DATABASES,
)


class TestStorageManager(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.mgr = StorageManager(base_dir=self.base_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_paths_resolution(self):
        self.assertEqual(self.mgr.cache_dir, self.base_dir / ".cache")
        self.assertEqual(self.mgr.output_dir, self.base_dir / "output")
        self.assertEqual(self.mgr.data_dir, self.base_dir / "data")

    def test_ensure_directories(self):
        self.mgr.ensure_directories()
        self.assertTrue(self.mgr.cache_dir.is_dir())
        self.assertTrue(self.mgr.output_dir.is_dir())
        self.assertTrue(self.mgr.data_dir.is_dir())

    def test_get_known_db_path(self):
        db_path = self.mgr.get_db_path("translation_cache")
        self.assertEqual(db_path, self.base_dir / ".cache" / "translation_cache.db")
        self.assertTrue(db_path.parent.is_dir())

    def test_get_data_dir_db_path(self):
        db_path = self.mgr.get_db_path("wiki_link_data")
        self.assertEqual(db_path, self.base_dir / "data" / "wiki_link_cache.sqlite")
        self.assertTrue(db_path.parent.is_dir())

    def test_get_arbitrary_db_path(self):
        db_path = self.mgr.get_db_path("custom_store")
        self.assertEqual(db_path, self.base_dir / ".cache" / "custom_store.db")

    def test_property_shortcuts(self):
        self.assertEqual(self.mgr.translation_cache_db.name, "translation_cache.db")
        self.assertEqual(self.mgr.glossary_memory_db.name, "glossary_memory.db")
        self.assertEqual(self.mgr.glossary_cache_db.name, "glossary_cache.db")
        self.assertEqual(self.mgr.wayback_cache_db.name, "wayback_cache.db")
        self.assertEqual(self.mgr.workspace_glossary_db.name, "workspace_glossary.db")
        self.assertEqual(self.mgr.wiki_templates_cache_db.name, "wiki_templates_cache.db")
        self.assertEqual(self.mgr.wiki_links_cache_db.name, "wiki_links_cache.db")
        self.assertEqual(self.mgr.wiki_link_data_db.name, "wiki_link_cache.sqlite")
        self.assertEqual(self.mgr.kateglo_cache_db.name, "kateglo_cache.sqlite")
        self.assertEqual(self.mgr.kateglo_cache_db.parent, self.mgr.data_dir)

    def test_inspect_and_clear_databases(self):
        db_path = self.mgr.get_db_path("translation_cache")
        db_path.write_bytes(b"dummy sqlite data")

        inspected = self.mgr.inspect_databases()
        info = next((item for item in inspected if item["key"] == "translation_cache"), None)
        self.assertIsNotNone(info)
        self.assertTrue(info["exists"])
        self.assertGreater(info["size_bytes"], 0)

        # Clear specific database
        cleared = self.mgr.clear_database("translation_cache")
        self.assertTrue(cleared)
        self.assertFalse(db_path.exists())

    def test_env_var_overrides(self):
        custom_cache = self.base_dir / "my_custom_cache"
        os.environ["WIKI_CACHE_DIR"] = str(custom_cache)
        try:
            env_mgr = StorageManager(base_dir=self.base_dir)
            self.assertEqual(env_mgr.cache_dir, custom_cache)
        finally:
            del os.environ["WIKI_CACHE_DIR"]

    def test_default_storage_manager_singleton(self):
        self.assertIsInstance(default_storage_manager, StorageManager)
        self.assertTrue(str(default_storage_manager.cache_dir).endswith(".cache"))
    def test_optimize_all_databases(self):
        import sqlite3
        db_path = self.mgr.get_db_path("translation_cache")
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("CREATE TABLE test_table (id INT)")
            conn.commit()
        finally:
            conn.close()

        report = self.mgr.optimize_all_databases()
        self.assertIn("translation_cache", report)
        self.assertEqual(report["translation_cache"]["integrity"], "ok")
        self.assertEqual(report["translation_cache"]["status"], "healthy")


if __name__ == "__main__":
    unittest.main()
