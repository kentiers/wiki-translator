"""
Unit tests for CategoryCurator (wiki_translator/category_curator.py).
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from wiki_translator.category_curator import (
    CategoryCurator,
    default_category_curator,
)


class TestCategoryCurator(unittest.TestCase):
    def setUp(self):
        self.curator = CategoryCurator(min_articles_threshold=3)

    def test_clean_category_name(self):
        self.assertEqual(
            self.curator._clean_category_name("Kategori:Film tahun 2020"),
            "Film tahun 2020",
        )
        self.assertEqual(
            self.curator._clean_category_name("Category:Scottish film directors"),
            "Scottish film directors",
        )
        self.assertEqual(
            self.curator._clean_category_name("  Kategori:Tokoh Indonesia  "),
            "Tokoh Indonesia",
        )

    def test_derive_search_query(self):
        q1 = self.curator._derive_search_query("Kategori:Film yang disutradarai oleh Kevin Macdonald")
        self.assertEqual(q1, '"Kevin Macdonald"')

        q2 = self.curator._derive_search_query("Kategori:Album karya Iwan Fals")
        self.assertEqual(q2, '"Iwan Fals"')

        q3 = self.curator._derive_search_query("Tokoh dari Bandung")
        self.assertEqual(q3, '"Bandung"')

    def test_infer_parent_categories(self):
        parents1 = self.curator.infer_parent_categories("Film yang disutradarai oleh Kevin Macdonald")
        self.assertIn("[[Kategori:Film menurut sutradara]]", parents1)
        self.assertIn("[[Kategori:Kevin Macdonald]]", parents1)

        parents2 = self.curator.infer_parent_categories("Film tahun 2024")
        self.assertIn("[[Kategori:Film menurut tahun]]", parents2)
        self.assertIn("[[Kategori:Karya tahun 2024]]", parents2)

        parents3 = self.curator.infer_parent_categories("Album karya Dewa 19")
        self.assertIn("[[Kategori:Album menurut artis]]", parents3)
        self.assertIn("[[Kategori:Dewa 19]]", parents3)

        parents4 = self.curator.infer_parent_categories("Kelahiran 1980")
        self.assertIn("[[Kategori:Kelahiran menurut tahun]]", parents4)

    @patch("urllib.request.urlopen")
    def test_search_related_articles(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "query": {
                "search": [
                    {"title": "The Last King of Scotland (film)"},
                    {"title": "State of Play (film)"},
                    {"title": "Life in a Day (film 2011)"},
                ]
            }
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        articles = self.curator.search_related_articles('"Kevin Macdonald"')
        self.assertEqual(len(articles), 3)
        self.assertIn("The Last King of Scotland (film)", articles)

    @patch.object(CategoryCurator, "search_related_articles")
    def test_curate_category_safe(self, mock_search):
        mock_search.return_value = [
            "Film A",
            "Film B",
            "Film C",
            "Film D",
        ]
        result = self.curator.curate_category("Kategori:Film yang disutradarai oleh Sutradara Hebat")
        self.assertTrue(result["is_safe_to_create"])
        self.assertEqual(result["article_count"], 4)
        self.assertEqual(len(result["found_articles"]), 4)
        self.assertIn("Aman untuk dibuat", result["reason"])
        self.assertIn("[[Kategori:Film menurut sutradara]]", result["parent_categories"])

    @patch.object(CategoryCurator, "search_related_articles")
    def test_curate_category_unsafe(self, mock_search):
        mock_search.return_value = ["Film A"]
        result = self.curator.curate_category("Film yang disutradarai oleh Sutradara Baru")
        self.assertFalse(result["is_safe_to_create"])
        self.assertEqual(result["article_count"], 1)
        self.assertIn("Belum aman untuk dibuat", result["reason"])

    def test_default_instance(self):
        self.assertIsInstance(default_category_curator, CategoryCurator)


if __name__ == "__main__":
    unittest.main()
