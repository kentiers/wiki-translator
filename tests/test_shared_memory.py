import sqlite3
import tempfile
import unittest
from pathlib import Path

from wiki_translator.shared_memory import WorkspaceSharedMemory, default_shared_memory


class TestWorkspaceSharedMemory(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_workspace_glossary.db"
        self.memory = WorkspaceSharedMemory(db_path=str(self.db_path))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_remember_term_and_get_glossary(self):
        self.memory.remember_term("Cast", "Pemeran", topic="film")
        self.memory.remember_term("Box office", "Pencapaian bioskop", topic="film")
        self.memory.remember_term("Director", "Sutradara")

        # Global glossary (topic=None) includes all
        all_glossary = self.memory.get_memory_glossary()
        self.assertEqual(all_glossary.get("Cast"), "Pemeran")
        self.assertEqual(all_glossary.get("Box office"), "Pencapaian bioskop")
        self.assertEqual(all_glossary.get("Director"), "Sutradara")

        # Film-specific glossary includes film terms and global (None) terms
        film_glossary = self.memory.get_memory_glossary(topic="film")
        self.assertIn("Cast", film_glossary)
        self.assertIn("Director", film_glossary)

        # Different topic does not include film-specific terms
        bio_glossary = self.memory.get_memory_glossary(topic="biography")
        self.assertNotIn("Cast", bio_glossary)
        self.assertIn("Director", bio_glossary)

    def test_remember_term_increments_count(self):
        self.memory.remember_term("Soundtrack", "Trek suara", topic="film")
        self.memory.remember_term("Soundtrack", "Trek suara", topic="film")

        glossary = self.memory.get_memory_glossary()
        self.assertEqual(glossary["Soundtrack"], "Trek suara")

        # Verify count in database
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT approved_count FROM workspace_terms WHERE en_term = 'Soundtrack'"
            )
            count = cur.fetchone()[0]
            self.assertEqual(count, 2)
        finally:
            conn.close()

    def test_record_article_terms(self):
        article_terms = {
            "Producer": "Produser",
            "Screenplay": "Skenario",
            "Cinematography": "Sinematografi",
        }
        self.memory.record_article_terms(article_terms, topic="cinema")

        glossary = self.memory.get_memory_glossary(topic="cinema")
        for en, id_t in article_terms.items():
            self.assertEqual(glossary.get(en), id_t)

    def test_clear_memory(self):
        self.memory.remember_term("Term A", "Istilah A", topic="tech")
        self.memory.remember_term("Term B", "Istilah B", topic="science")

        # Clear topic-specific
        self.memory.clear_memory(topic="tech")
        self.assertNotIn("Term A", self.memory.get_memory_glossary())
        self.assertIn("Term B", self.memory.get_memory_glossary())

        # Clear all
        self.memory.clear_memory()
        self.assertEqual(len(self.memory.get_memory_glossary()), 0)

    def test_default_shared_memory_instance(self):
        self.assertIsInstance(default_shared_memory, WorkspaceSharedMemory)


if __name__ == "__main__":
    unittest.main()
