"""
Unit tests for TemplateDocAuditor (wiki_translator/template_doc_auditor.py).
"""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from wiki_translator.template_doc_auditor import (
    TemplateDocAuditor,
    default_template_doc_auditor,
)


class TestTemplateDocAuditor(unittest.TestCase):
    def setUp(self):
        self.auditor = TemplateDocAuditor()

    def test_clean_template_name(self):
        self.assertEqual(self.auditor._clean_template_name("Templat:Film"), "Film")
        self.assertEqual(self.auditor._clean_template_name("Template:Film"), "Film")
        self.assertEqual(self.auditor._clean_template_name("Film/doc"), "Film")
        self.assertEqual(self.auditor._clean_template_name("  Templat:Navbox/doc  "), "Navbox")

    @patch("urllib.request.urlopen")
    def test_check_doc_exists_true(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "query": {
                "pages": [{"pageid": 12345, "title": "Templat:Film/doc"}]
            }
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        exists = self.auditor.check_doc_exists("Film")
        self.assertTrue(exists)

    @patch("urllib.request.urlopen")
    def test_check_doc_exists_false_missing(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "query": {
                "pages": [{"missing": True, "title": "Templat:UnknownTemplate/doc"}]
            }
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        exists = self.auditor.check_doc_exists("UnknownTemplate")
        self.assertFalse(exists)

    def test_generate_templatedata(self):
        td_wikitext = self.auditor.generate_templatedata(
            template_name="Infobox film",
            parameters=["title", "director", "year"],
            description="Templat kotak info untuk artikel film.",
        )
        self.assertIn("<templatedata>", td_wikitext)
        self.assertIn("</templatedata>", td_wikitext)
        self.assertIn('"title"', td_wikitext)
        self.assertIn('"director"', td_wikitext)
        self.assertIn('"year"', td_wikitext)
        self.assertIn("Templat kotak info untuk artikel film.", td_wikitext)

    def test_generate_doc_wikitext(self):
        wikitext = self.auditor.generate_doc_wikitext(
            template_name="Kevin Macdonald",
            parameters=["name", "awards"],
            description="Navigasi film-film Kevin Macdonald.",
            topic="film",
        )
        self.assertIn("{{Dokumentasi templat}}", wikitext)
        self.assertIn("== Penggunaan ==", wikitext)
        self.assertIn("<pre>", wikitext)
        self.assertIn("{{Kevin Macdonald", wikitext)
        self.assertIn("| name = ", wikitext)
        self.assertIn("| awards = ", wikitext)
        self.assertIn("=== Parameter ===", wikitext)
        self.assertIn("<code>name</code>", wikitext)
        self.assertIn("== TemplateData ==", wikitext)
        self.assertIn("<templatedata>", wikitext)
        self.assertIn("<includeonly>", wikitext)
        self.assertIn("[[Kategori:Templat navigasi film]]", wikitext)
        self.assertIn("</includeonly>", wikitext)

    def test_generate_navbox_doc_wikitext(self):
        wikitext = self.auditor.generate_navbox_doc_wikitext(
            template_name="Kevin Macdonald",
            topic="sutradara",
            see_also=["Kevin Macdonald", "The Runner (film 2026)"],
        )
        self.assertIn("{{Dokumentasi navbox}}", wikitext)
        self.assertIn("== Penggunaan ==", wikitext)
        self.assertIn("<pre>\n{{Kevin Macdonald}}\n</pre>", wikitext)
        self.assertIn("=== Pengaturan visibilitas awal ===", wikitext)
        self.assertIn("{{collapsible option}}", wikitext)
        self.assertIn("== Data templat ==", wikitext)
        self.assertIn("<templatedata>", wikitext)
        self.assertIn('"autocollapse"', wikitext)
        self.assertIn('"collapsed"', wikitext)
        self.assertIn('"expanded"', wikitext)
        self.assertIn("== Lihat pula ==", wikitext)
        self.assertIn("* [[Kevin Macdonald]]", wikitext)
        self.assertIn("* [[The Runner (film 2026)]]", wikitext)
        self.assertIn("<includeonly>", wikitext)
        self.assertIn("[[Kategori:Templat navigasi sutradara film Skotlandia|Macdonald, Kevin]]", wikitext)
        self.assertIn("[[Kategori:Templat navigasi sutradara Britania Raya|Macdonald, Kevin]]", wikitext)
        self.assertIn("</includeonly>", wikitext)

    @patch.object(TemplateDocAuditor, "check_doc_exists", return_value=False)
    def test_audit_and_generate(self, mock_exists):
        result = self.auditor.audit_and_generate(
            template_name="Templat:Sutradara",
            parameters=["nama", "film_terkenal"],
            description="Kotak navigasi sutradara.",
            topic="film",
        )
        self.assertEqual(result["template_name"], "Sutradara")
        self.assertEqual(result["full_title"], "Templat:Sutradara")
        self.assertEqual(result["doc_title"], "Templat:Sutradara/doc")
        self.assertFalse(result["doc_exists"])
        self.assertIn("Sutradara", result["wikitext"])
        self.assertIn("[[Kategori:Templat navigasi film]]", result["wikitext"])

    def test_save_doc(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = Path(temp_dir)
            doc_info = {
                "template_name": "Test Template",
                "wikitext": "{{Dokumentasi templat}}\nIsi doc",
            }
            saved_file = self.auditor.save_doc(doc_info, out_path)
            self.assertTrue(saved_file.exists())
            self.assertEqual(saved_file.name, "Test_Template_doc.wikitext")
            self.assertEqual(saved_file.read_text(encoding="utf-8"), "{{Dokumentasi templat}}\nIsi doc")

    def test_default_instance(self):
        self.assertIsInstance(default_template_doc_auditor, TemplateDocAuditor)


if __name__ == "__main__":
    unittest.main()
