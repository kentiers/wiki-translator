"""
Unit tests for AWB-style Smart Page Generators (wiki_translator/page_generators.py).
100% mocked network calls testing CategoryPageGenerator, WhatLinksHerePageGenerator,
filtering existing vs missing articles, and PageQueueExporter.
"""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from wiki_translator.page_generators import (
    PageQueueItem,
    CategoryPageGenerator,
    WhatLinksHerePageGenerator,
    PageQueueExporter,
)


class TestPageGenerators(unittest.TestCase):
    def setUp(self):
        self.en_api_url = "https://en.wikipedia.org/w/api.php"
        self.id_api_url = "https://id.wikipedia.org/w/api.php"

    def test_page_queue_item_to_dict(self):
        item = PageQueueItem(
            en_title="Dune: Part Two",
            predicted_id_title="Dune: Part Two",
            status="missing_on_idwiki",
        )
        data = item.to_dict()
        self.assertEqual(data["en_title"], "Dune: Part Two")
        self.assertEqual(data["predicted_id_title"], "Dune: Part Two")
        self.assertEqual(data["status"], "missing_on_idwiki")

    def test_predict_id_title(self):
        gen = CategoryPageGenerator(en_category="Films")
        self.assertEqual(gen.predict_id_title("Dune (film)"), "Dune (film)")
        self.assertEqual(gen.predict_id_title("Christopher Nolan (director)"), "Christopher Nolan (sutradara)")
        self.assertEqual(gen.predict_id_title("Cillian Murphy (actor)"), "Cillian Murphy (pemeran)")
        self.assertEqual(gen.predict_id_title("Emma Thomas (producer)"), "Emma Thomas (producer)")
        self.assertEqual(gen.predict_id_title("Inception"), "Inception")

    @patch.object(CategoryPageGenerator, "_api_get")
    def test_category_page_generator_non_recursive(self, mock_api_get):
        # Mock API calls:
        # 1. categorymembers query on en.wikipedia.org
        # 2. langlinks query on en.wikipedia.org
        # 3. existence query on id.wikipedia.org
        def fake_api_get(endpoint, params):
            if "categorymembers" in params.get("list", ""):
                return {
                    "query": {
                        "categorymembers": [
                            {"ns": 0, "title": "Film A (film)"},
                            {"ns": 0, "title": "Film B (film)"},
                            {"ns": 0, "title": "Film C (film)"},
                            {"ns": 14, "title": "Category:Subfilms"},
                        ]
                    }
                }
            if params.get("prop") == "langlinks":
                # Let's say Film A already has an Indonesian langlink: Film A
                return {
                    "query": {
                        "pages": [
                            {
                                "title": "Film A (film)",
                                "langlinks": [{"lang": "id", "title": "Film A"}],
                            },
                            {
                                "title": "Film B (film)",
                                "langlinks": [],
                            },
                            {
                                "title": "Film C (film)",
                                "langlinks": [],
                            },
                        ]
                    }
                }
            if endpoint == "https://id.wikipedia.org/w/api.php":
                # Check existence of predicted ID titles:
                # Let's say Film B (film) already exists on id.wiki
                # but Film C (film) is missing!
                return {
                    "query": {
                        "pages": [
                            {"title": "Film B (film)", "pageid": 12345, "missing": False},
                            {"title": "Film C (film)", "pageid": 0, "missing": True},
                        ]
                    }
                }
            return {}

        mock_api_get.side_effect = fake_api_get

        gen = CategoryPageGenerator(
            en_category="2026 films",
            limit=10,
            recursive=False,
        )
        self.assertEqual(gen.en_category, "Category:2026 films")
        queue = gen.generate()

        # Film A is excluded because it has id langlink.
        # Film B is excluded because it exists on id.wiki.
        # Film C is retained as missing_on_idwiki.
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0].en_title, "Film C (film)")
        self.assertEqual(queue[0].predicted_id_title, "Film C (film)")
        self.assertEqual(queue[0].status, "missing_on_idwiki")

    @patch.object(CategoryPageGenerator, "_api_get")
    def test_category_page_generator_recursive(self, mock_api_get):
        def fake_api_get(endpoint, params):
            if "categorymembers" in params.get("list", ""):
                cmtitle = params.get("cmtitle", "")
                if cmtitle == "Category:MainCat":
                    return {
                        "query": {
                            "categorymembers": [
                                {"ns": 0, "title": "Article 1"},
                                {"ns": 14, "title": "Category:SubCat"},
                            ]
                        }
                    }
                elif cmtitle == "Category:SubCat":
                    return {
                        "query": {
                            "categorymembers": [
                                {"ns": 0, "title": "Article 2"},
                            ]
                        }
                    }
            if params.get("prop") == "langlinks":
                return {"query": {"pages": []}}
            if endpoint == "https://id.wikipedia.org/w/api.php":
                # Both Article 1 and Article 2 are missing
                return {
                    "query": {
                        "pages": [
                            {"title": "Article 1", "missing": True},
                            {"title": "Article 2", "missing": True},
                        ]
                    }
                }
            return {}

        mock_api_get.side_effect = fake_api_get

        gen = CategoryPageGenerator(
            en_category="MainCat",
            limit=5,
            recursive=True,
        )
        queue = gen.generate()
        self.assertEqual(len(queue), 2)
        titles = [it.en_title for it in queue]
        self.assertIn("Article 1", titles)
        self.assertIn("Article 2", titles)

    @patch.object(WhatLinksHerePageGenerator, "_api_get")
    def test_what_links_here_page_generator(self, mock_api_get):
        def fake_api_get(endpoint, params):
            if "linkshere|transcludedin" in params.get("prop", ""):
                return {
                    "query": {
                        "pages": [
                            {
                                "title": "OpenAI",
                                "linkshere": [
                                    {"ns": 0, "title": "Sam Altman"},
                                    {"ns": 1, "title": "Talk:Sam Altman"},  # filtered out
                                ],
                                "transcludedin": [
                                    {"ns": 0, "title": "ChatGPT"},
                                    {"ns": 10, "title": "Template:AI"},  # filtered out
                                ],
                            }
                        ]
                    }
                }
            if params.get("prop") == "langlinks":
                # Let's say Sam Altman has id langlink
                return {
                    "query": {
                        "pages": [
                            {"title": "Sam Altman", "langlinks": [{"lang": "id", "title": "Sam Altman"}]},
                            {"title": "ChatGPT", "langlinks": []},
                        ]
                    }
                }
            if endpoint == "https://id.wikipedia.org/w/api.php":
                # ChatGPT is missing on id.wiki
                return {
                    "query": {
                        "pages": [
                            {"title": "ChatGPT", "missing": True, "pageid": 0}
                        ]
                    }
                }
            return {}

        mock_api_get.side_effect = fake_api_get

        gen = WhatLinksHerePageGenerator(
            en_target_page="OpenAI",
            limit=10,
        )
        queue = gen.generate()
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0].en_title, "ChatGPT")
        self.assertEqual(queue[0].predicted_id_title, "ChatGPT")
        self.assertEqual(queue[0].status, "missing_on_idwiki")

    def test_page_queue_exporter(self):
        items = [
            PageQueueItem("Title One", "Title One"),
            PageQueueItem("Title Two (film)", "Title Two (film)"),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "output" / "queues" / "test_queue.txt"
            saved_path = PageQueueExporter.export_to_file(
                items=items,
                output_path=out_file,
                source_description="Test Category",
            )
            self.assertTrue(saved_path.is_file())
            content = saved_path.read_text(encoding="utf-8")
            self.assertIn("# Wikipedia Translation Queue", content)
            self.assertIn("# Source: Test Category", content)
            self.assertIn("Title One\n", content)
            self.assertIn("Title Two (film)\n", content)

            # Test compatibility with BatchRunner.parse_queue_file
            from wiki_translator.batch_runner import BatchRunner
            parsed_titles = BatchRunner.parse_queue_file(saved_path)
            self.assertEqual(parsed_titles, ["Title One", "Title Two (film)"])
    @patch("wiki_translator.cli.CategoryPageGenerator.generate")
    def test_cli_gen_category_dry_run(self, mock_generate):
        from wiki_translator.cli import main
        mock_generate.return_value = [
            PageQueueItem("Film A (film)", "Film A (film)"),
        ]
        with patch("sys.argv", ["cli.py", "--gen-category", "2026 films", "--dry-run-queue"]):
            with patch("builtins.print") as mock_print:
                main()
                mock_generate.assert_called_once()

    @patch("wiki_translator.cli.WhatLinksHerePageGenerator.generate")
    def test_cli_gen_backlinks_export(self, mock_generate):
        from wiki_translator.cli import main
        mock_generate.return_value = [
            PageQueueItem("ChatGPT", "ChatGPT"),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "output.txt"
            with patch("sys.argv", ["cli.py", "--gen-backlinks", "OpenAI", "--output-queue", str(out_file)]):
                main()
                mock_generate.assert_called_once()
                self.assertTrue(out_file.is_file())
                content = out_file.read_text(encoding="utf-8")
                self.assertIn("ChatGPT", content)


if __name__ == "__main__":
    unittest.main()
