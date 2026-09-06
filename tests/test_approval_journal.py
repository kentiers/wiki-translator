import tempfile
import unittest
from pathlib import Path

from wiki_translator.approval_journal import ApprovalManifest, TransactionJournal


class TestApprovalJournal(unittest.TestCase):
    def test_manifest_detects_mutation_until_approved(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "draft.wikitext"
            path.write_text("draft", encoding="utf-8")
            manifest = ApprovalManifest.create("category", [path])
            ok, errors = manifest.verify()
            self.assertFalse(ok)
            self.assertIn("not approved", errors[0])
            manifest.approve()
            self.assertTrue(manifest.verify()[0])
            path.write_text("changed", encoding="utf-8")
            ok, errors = manifest.verify()
            self.assertFalse(ok)
            self.assertIn("hash changed", errors[0])

    def test_journal_returns_latest_event_per_node(self):
        with tempfile.TemporaryDirectory() as temp:
            journal = TransactionJournal(Path(temp) / "journal.jsonl")
            journal.record("Template:A", "planned")
            journal.record("Template:A", "drafted", path="a.wikitext")
            journal.record("Template:B", "blocked", reason="missing")
            latest = journal.latest()
            self.assertEqual(latest["Template:A"]["status"], "drafted")
            self.assertEqual(latest["Template:B"]["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
