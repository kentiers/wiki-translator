"""
CLI Integration tests for AntiAISlopLinter, WikitextSyntaxBalancer, and TemplateMapper.
"""

from pathlib import Path
import tempfile
import unittest

from wiki_translator.cli import WikiTranslatorCLI
from wiki_translator.wiki_client import WikiSection


class TestCLISlopAndSyntaxIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.out_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_cli_save_output_with_slop_and_syntax_fixes(self):
        cli = WikiTranslatorCLI(
            output_dir=str(self.out_dir),
            enable_map_links=False,
            enable_cache=False,
            enable_slop_linter=True,
            enable_syntax_balancer=True,
            enable_template_mapper=True,
        )

        # Section containing:
        # 1. Calque slop: "memainkan peran penting", "yang berbasis di"
        # 2. Template to map: {{Main|Sejarah}}
        s1 = WikiSection(
            index=1,
            title="Pengantar",
            level=2,
            header_raw="== Pengantar ==",
            content="Organisasi yang berbasis di Jenewa ini memainkan peran penting. Lihat artikel [[Indonesia untuk info.\n{{Main|Sejarah}}",
            word_count=20,
            char_count=120,
            translated_content="== Pengantar ==\nOrganisasi yang berbasis di Jenewa ini memainkan peran penting. Lihat artikel [[Indonesia untuk info.\n{{Main|Sejarah}}",
        )

        wiki_path, md_path, talk_path = cli._save_output("test_slug", "Test Title", [s1])
        self.assertTrue(talk_path.exists())
        with open(wiki_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Contextual style suggestions must not silently rewrite the saved text.
        self.assertIn("memainkan peran penting", content)
        self.assertIn("yang berbasis di", content)

        # Check template mapped
        self.assertIn("{{Utama|Sejarah}}", content)

        # Check wikilink balanced
        self.assertIn("[[Indonesia]]", content)


if __name__ == "__main__":
    unittest.main()
