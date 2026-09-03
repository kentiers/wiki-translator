"""
Unit tests for wiki_translator/redirect_generator.py.
"""

from pathlib import Path
import tempfile
import unittest

from wiki_translator.redirect_generator import (
    RedirectGenerator,
    default_redirect_generator,
)


class TestRedirectGenerator(unittest.TestCase):

    def setUp(self):
        self.generator = RedirectGenerator()

    def test_english_source_title_redirect(self):
        en_title = "The Runner (2026 film)"
        id_title = "The Runner (film 2026)"
        redirects = self.generator.generate_redirects(en_title, id_title)
        
        titles = [r["title"] for r in redirects]
        self.assertIn("The Runner (2026 film)", titles)
        
        # Check wikitext format for the en_title
        en_redir = next(r for r in redirects if r["title"] == "The Runner (2026 film)")
        self.assertIn("#ALIH [[The Runner (film 2026)]]", en_redir["wikitext"])
        self.assertIn("{{Pengalihan dari nama bahasa Inggris}}", en_redir["wikitext"])

    def test_year_format_swap_film(self):
        en_title = "The Runner (2026 film)"
        id_title = "The Runner (film 2026)"
        redirects = self.generator.generate_redirects(en_title, id_title)

        titles = [r["title"] for r in redirects]
        # Should generate "The Runner (film)"
        self.assertIn("The Runner (film)", titles)
        # Should generate "The Runner"
        self.assertIn("The Runner", titles)

        # Check template for without disambiguator
        no_disambig = next(r for r in redirects if r["title"] == "The Runner")
        self.assertIn("{{Pengalihan tanpa pembeda}}", no_disambig["wikitext"])

    def test_tv_series_disambiguation(self):
        en_title = "Midnight Sun (2025 television series)"
        id_title = "Midnight Sun (serial televisi 2025)"
        redirects = self.generator.generate_redirects(en_title, id_title)

        titles = [r["title"] for r in redirects]
        self.assertIn("Midnight Sun (2025 television series)", titles)
        self.assertIn("Midnight Sun (serial televisi)", titles)
        self.assertIn("Midnight Sun", titles)

    def test_punctuation_quotes_and_dashes(self):
        en_title = 'The “Fast” & The Furious – Tokyo Drift'
        id_title = 'The "Fast" & The Furious – Tokyo Drift'
        redirects = self.generator.generate_redirects(en_title, id_title)

        titles = [r["title"] for r in redirects]
        # Should generate hyphen variant for en-dash
        hyphen_variants = [t for t in titles if "-" in t and "–" not in t]
        self.assertTrue(len(hyphen_variants) > 0)

        # Should generate "dan" variant for ampersand
        amp_variants = [t for t in titles if " dan " in t]
        self.assertTrue(len(amp_variants) > 0)

    def test_case_variations(self):
        en_title = "Inception"
        id_title = "Inception"
        # Test with capitalized/lowercase variants
        redirects = self.generator.generate_redirects("INCEPTION", "Inception")
        titles = [r["title"] for r in redirects]
        self.assertIn("INCEPTION", titles)

    def test_save_redirects(self):
        redirects = [
            {
                "title": "The Runner (2026 film)",
                "wikitext": "#ALIH [[The Runner (film 2026)]]\n\n{{Pengalihan dari nama bahasa Inggris}}",
                "reason": "Pengalihan dari judul asli",
            },
            {
                "title": "The Runner (film)",
                "wikitext": "#ALIH [[The Runner (film 2026)]]\n\n{{Pengalihan dengan pembeda}}",
                "reason": "Pengalihan tanpa tahun pembeda",
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir)
            saved = self.generator.save_redirects(redirects, out_path)
            self.assertEqual(len(saved), 2)
            for p in saved:
                self.assertTrue(p.exists())
                content = p.read_text(encoding="utf-8")
                self.assertTrue(content.startswith("#ALIH [["))

    def test_default_instance(self):
        self.assertIsNotNone(default_redirect_generator)
        redirects = default_redirect_generator.generate_redirects("Avatar (2009 film)", "Avatar (film 2009)")
        self.assertTrue(len(redirects) > 0)


if __name__ == "__main__":
    unittest.main()
