"""
Unit tests for BatchRunner (wiki_translator/batch_runner.py).
"""

from pathlib import Path
import tempfile
import unittest

from wiki_translator.batch_runner import (
    BatchRunner,
    BatchReport,
    ArticleBatchItemResult,
    default_batch_runner,
)


class TestBatchRunner(unittest.TestCase):
    def setUp(self):
        self.runner = BatchRunner(pause_interval=0.0)

    def test_parse_queue_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_file = Path(tmpdir) / "queue.txt"
            queue_file.write_text(
                "# List of articles to translate\n"
                "\n"
                "Oppenheimer (film)\n"
                "Barbie (film)\n"
                "# Ignored commented line\n"
                "Inception\n"
                "   \n"
                "Interstellar (film)\n",
                encoding="utf-8",
            )

            titles = BatchRunner.parse_queue_file(queue_file)
            self.assertEqual(
                titles,
                ["Oppenheimer (film)", "Barbie (film)", "Inception", "Interstellar (film)"],
            )

    def test_parse_queue_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            BatchRunner.parse_queue_file("non_existent_queue_file.txt")

    def test_run_batch_success_and_failure(self):
        titles = ["Article One", "Article Two", "Article Error"]

        def mock_translate(title: str):
            if "Error" in title:
                return {"success": False, "error": "API 500 error", "tokens_saved": 0}
            return {
                "success": True,
                "tokens_saved": 150,
                "output_files": {"wikitext": f"output/{title}.wiki"},
            }

        progress_calls = []

        def on_prog(idx, total, title, item_res):
            progress_calls.append((idx, total, title, item_res.success))

        report = self.runner.run_batch(
            queue=titles,
            translate_fn=mock_translate,
            pause_interval=0.0,
            on_progress=on_prog,
        )

        self.assertEqual(report.total_articles, 3)
        self.assertEqual(report.succeeded, 2)
        self.assertEqual(report.failed, 1)
        self.assertEqual(report.total_tokens_saved, 300)
        self.assertEqual(len(report.items), 3)
        self.assertEqual(len(progress_calls), 3)
        self.assertEqual(progress_calls[0], (1, 3, "Article One", True))
        self.assertEqual(progress_calls[2], (3, 3, "Article Error", False))

        report_dict = report.to_dict()
        self.assertIn("total_articles", report_dict)
        self.assertIn("succeeded", report_dict)
        self.assertIn("items", report_dict)
        self.assertEqual(report_dict["succeeded"], 2)

    def test_run_batch_with_exception_in_fn(self):
        def failing_translate(title: str):
            raise RuntimeError("Unexpected crash")

        report = self.runner.run_batch(
            queue=["Crash Title"],
            translate_fn=failing_translate,
            pause_interval=0.0,
        )
        self.assertEqual(report.total_articles, 1)
        self.assertEqual(report.succeeded, 0)
        self.assertEqual(report.failed, 1)
        self.assertIn("Unexpected crash", report.items[0].error or "")

    def test_default_instance(self):
        self.assertIsInstance(default_batch_runner, BatchRunner)


if __name__ == "__main__":
    unittest.main()
