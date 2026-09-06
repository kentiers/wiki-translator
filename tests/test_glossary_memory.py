import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from wiki_translator.cli import main
from wiki_translator.glossary_memory import (
    GlossaryCandidate,
    GlossaryMemory,
    extract_revision_corrections,
)


class TestGlossaryMemory(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.memory = GlossaryMemory(str(Path(self.temp_dir.name) / "memory.db"))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_candidates_require_approval_and_track_usage(self):
        candidate = self.memory.propose(
            GlossaryCandidate("  filmmaker ", "pembuat film", "Film", "lead", "human", 1.2)
        )
        self.assertEqual(candidate.status, "candidate")
        self.assertEqual(self.memory.list("film")[0].target_term, "pembuat film")
        self.assertTrue(self.memory.approve("FILMMAKER", "pembuat film", "film"))
        self.assertTrue(self.memory.record_usage("filmmaker", "pembuat film", "film"))
        approved = self.memory.list("film", status="approved")[0]
        self.assertEqual(approved.confidence, 1.0)
        self.assertEqual(approved.usage_count, 1)

    def test_propose_does_not_demote_approved_term(self):
        self.memory.propose(GlossaryCandidate("director", "sutradara", "Film", None, "human", 0.9))
        self.memory.approve("director", "sutradara", "film")
        updated = self.memory.propose(
            GlossaryCandidate("director", "pengarah", "film", None, "llm", 0.99)
        )
        self.assertEqual(updated.status, "candidate")
        self.assertEqual(updated.target_term, "pengarah")
        self.assertEqual(self.memory.list("film", status="approved")[0].target_term, "sutradara")

    def test_extract_revision_corrections_ignores_markup_only_changes(self):
        draft = "Ia adalah a filmmaker terkenal.\n[[Kategori:Film]]"
        revised = "Ia adalah pembuat film terkenal.\n[[Kategori:Film]]"
        candidates = extract_revision_corrections(draft, revised)
        self.assertEqual([(item.source_term, item.target_term) for item in candidates], [("a filmmaker", "pembuat film")])

    def test_revision_candidates_are_topic_scoped_and_pending(self):
        stored = self.memory.propose_from_revision(
            "The director won awards.",
            "Sutradara tersebut memenangkan penghargaan.",
            topic="Biografi",
        )
        self.assertTrue(stored)
        self.assertTrue(all(item.status == "candidate" for item in stored))
        self.assertEqual(self.memory.list("biografi")[0].topic, "biografi")

    def test_cli_lists_and_approves_candidates(self):
        self.memory.propose(GlossaryCandidate("filmmaker", "pembuat film", "Film", None, "human", 0.9))
        output = StringIO()
        with patch("sys.argv", ["wiki-translator", "--list-glossary-candidates", "--glossary-memory", str(self.memory.db_path)]), redirect_stdout(output):
            main()
        self.assertIn("pembuat film", output.getvalue())
        with patch("sys.argv", ["wiki-translator", "--approve-glossary", "filmmaker=pembuat film", "--glossary-topic", "film", "--glossary-memory", str(self.memory.db_path)]), redirect_stdout(StringIO()):
            main()
        self.assertEqual(len(self.memory.list("film", status="approved")), 1)


if __name__ == "__main__":
    unittest.main()
