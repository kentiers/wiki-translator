"""
Unit tests for Template Synchronization & Documentation Engine (wiki_translator/template_syncer.py).
"""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from wiki_translator.template_syncer import (
    TemplateSyncer,
    default_template_syncer,
    EXTENDED_GROUP_TRANSLATIONS,
)
from wiki_translator.wiki_client import PageNotFoundError, WikipediaClient
from wiki_translator.wiki_link_mapper import WikiLinkMapper
from wiki_translator.template_doc_auditor import TemplateDocAuditor


class TestTemplateSyncer(unittest.TestCase):
    def setUp(self):
        self.mock_en_client = MagicMock(spec=WikipediaClient)
        self.mock_id_client = MagicMock(spec=WikipediaClient)
        self.mock_link_mapper = MagicMock(spec=WikiLinkMapper)
        self.mock_doc_auditor = MagicMock(spec=TemplateDocAuditor)

        # By default mock_en_client.fetch_wikitext returns a default navbox, but raises PageNotFoundError for /doc
        self.mock_en_doc_content = None
        def default_fetch(title, **kwargs):
            if title.endswith("/doc"):
                if self.mock_en_doc_content is not None:
                    return self.mock_en_doc_content
                raise PageNotFoundError(f"Page not found: {title}")
            return self.default_en_content
        self.default_en_content = "{{Navbox| name = Default }}"
        self.mock_en_client.fetch_wikitext.side_effect = default_fetch
        # Basic link mapper mock behavior
        self.mock_link_mapper.map_wikilinks.side_effect = lambda text: text
        self.mock_link_mapper.map_categories.side_effect = lambda text: text
        self.mock_doc_auditor.generate_navbox_doc_wikitext.side_effect = (
            lambda template_name, topic=None, see_also=None, categories=None: (
                f"{{{{Dokumentasi navbox}}}}\n== Penggunaan ==\n<pre>\n{{{{{template_name}}}}}\n</pre>\n"
                f"=== Pengaturan visibilitas awal ===\n{{{{collapsible option}}}}\n"
                f"== Data templat ==\n<templatedata>\n{{}}\n</templatedata>\n"
                f"== Lihat pula ==\n* [[{template_name}]]\n"
                f"<includeonly>\n[[Kategori:Templat navigasi]]\n</includeonly>"
            )
        )
        # Basic doc auditor mock behavior
        self.mock_doc_auditor.generate_doc_wikitext.side_effect = (
            lambda template_name, parameters=None, description=None, topic=None: (
                f"{{{{Dokumentasi templat}}}}\n== Penggunaan ==\n<pre>\n{{{{{template_name}\n"
                f"| {parameters[0] if parameters else 'param'} = \n}}\n</pre>\n"
                f"=== Parameter ===\n== TemplateData ==\n<templatedata>\n{{}}\n</templatedata>\n"
                f"<includeonly>\n[[Kategori:Templat navigasi]]\n</includeonly>"
            )
        )

        self.syncer = TemplateSyncer(
            en_client=self.mock_en_client,
            id_client=self.mock_id_client,
            link_mapper=self.mock_link_mapper,
            doc_auditor=self.mock_doc_auditor,
        )

    def test_clean_template_name(self):
        self.assertEqual(self.syncer._clean_template_name("Template:Christopher Nolan"), "Christopher Nolan")
        self.assertEqual(self.syncer._clean_template_name("Templat:Christopher Nolan/doc"), "Christopher Nolan")
        self.assertEqual(self.syncer._clean_template_name("  Denis Villeneuve  "), "Denis Villeneuve")

    def test_translate_group_labels(self):
        self.assertEqual(self.syncer.translate_group_label("Feature films"), "Film layar lebar")
        self.assertEqual(self.syncer.translate_group_label("Documentaries"), "Film dokumenter")
        self.assertEqual(self.syncer.translate_group_label("Other"), "Karya lainnya")
        self.assertEqual(self.syncer.translate_group_label("Directed by"), "Disutradarai oleh")
        self.assertEqual(self.syncer.translate_group_label("Produced by"), "Diproduseri oleh")
        self.assertEqual(self.syncer.translate_group_label("Written by"), "Ditulis oleh")
        # Bold formatting preservation
        self.assertEqual(self.syncer.translate_group_label("'''Feature films'''"), "'''Film layar lebar'''")
        # Wikilink wrapped
        self.assertEqual(self.syncer.translate_group_label("[[Film director|Directed by]]"), "Disutradarai oleh")

    def test_fetch_en_template_wikitext(self):
        self.default_en_content = "{{Navbox| name = Nolan}}"
        content = self.syncer.fetch_en_template_wikitext("Template:Christopher Nolan")
        self.mock_en_client.fetch_wikitext.assert_called_with(
            "Template:Christopher Nolan", check_disambiguation=False
        )
        self.assertEqual(content, "{{Navbox| name = Nolan}}")

    def test_translate_navbox_template_wikitext(self):
        en_wikitext = """{{Navbox
| name = Christopher Nolan
| title = Films directed by Christopher Nolan
| state = {{{state|autocollapse}}}
| group1 = Feature films
| list1 = [[Memento (film)|Memento]] * [[Inception]] * [[Interstellar (film)|Interstellar]]
| group2 = Documentaries
| list2 = [[Doodlebug (film)|Doodlebug]]
| group3 = Other
| list3 = [[The Prestige]]
<noinclude>
[[Category:English film director navigational boxes]]
</noinclude>
}}"""
        translated = self.syncer.translate_template_wikitext(en_wikitext, "Christopher Nolan")
        self.assertIn("{{Kotak navigasi", translated)
        self.assertIn("| nama = Christopher Nolan", translated)
        self.assertIn("| kelompok1 = Film layar lebar", translated)
        self.assertIn("| kelompok2 = Film dokumenter", translated)
        self.assertIn("| kelompok3 = Karya lainnya", translated)
        self.assertIn("| daftar1 =", translated)
        self.assertIn("{{Dokumentasi navbox}}", translated)
        self.assertIn("<noinclude>", translated)
    def test_translate_general_template_wikitext(self):
        en_wikitext = """{{Infobox film
| name = Oppenheimer
| director = Christopher Nolan
| group1 = Directed by
}}
<noinclude>
[[Category:Templates]]
</noinclude>"""
        translated = self.syncer.translate_template_wikitext(en_wikitext, "Infobox film")
        self.assertIn("{{Infobox film", translated)
        self.assertIn("| group1 = Disutradarai oleh", translated)
        self.assertIn("<noinclude>\n{{Dokumentasi}}\n</noinclude>", translated)
        self.assertNotIn("Category:Templates", translated)

    def test_generate_doc_wikitext(self):
        doc = self.syncer.generate_doc_wikitext(
            template_name="Christopher Nolan",
            parameters=["nama", "judul", "kelompok1", "daftar1"],
            topic="film",
        )
        self.assertIn("{{Dokumentasi templat}}", doc)
        self.assertIn("== Penggunaan ==", doc)
        self.assertIn("=== Parameter ===", doc)
        self.assertIn("<includeonly>", doc)
        self.assertIn("[[Kategori:Templat navigasi]]", doc)

    def test_save_templates_locally(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            t_file, d_file = self.syncer.save_templates_locally(
                template_name="Templat:Denis Villeneuve",
                template_wikitext="{{Kotak navigasi\n| nama = Denis Villeneuve\n}}",
                doc_wikitext="{{Dokumentasi templat}}\n== Penggunaan ==\n",
                output_dir=out_dir,
            )
            self.assertTrue(t_file.exists())
            self.assertTrue(d_file.exists())
            self.assertEqual(t_file.name, "Denis_Villeneuve.wikitext")
            self.assertEqual(d_file.name, "Denis_Villeneuve_doc.wikitext")
            self.assertIn("Kotak navigasi", t_file.read_text(encoding="utf-8"))
            self.assertIn("Dokumentasi templat", d_file.read_text(encoding="utf-8"))

    def test_sync_template_without_publish(self):
        en_wikitext = """{{Navbox
| name = Guy Ritchie
| title = Works of Guy Ritchie
| group1 = Feature films
| list1 = [[Lock, Stock and Two Smoking Barrels]] * [[Snatch (film)|Snatch]]
| group2 = Other
| list2 = [[The Hire]]
}}"""
        self.default_en_content = en_wikitext

        with tempfile.TemporaryDirectory() as tmpdir:
            res = self.syncer.sync_template(
                template_name="Template:Guy Ritchie",
                output_dir=Path(tmpdir),
                publish=False,
            )
            self.assertEqual(res["template_name"], "Guy Ritchie")
            self.assertEqual(res["id_title"], "Templat:Guy Ritchie")
            self.assertEqual(res["doc_title"], "Templat:Guy Ritchie/doc")
            self.assertFalse(res["published"])
            self.assertTrue(Path(res["template_file"]).exists())
            self.assertTrue(Path(res["doc_file"]).exists())
            self.assertIn("Film layar lebar", res["wikitext"])
            self.assertIn("Karya lainnya", res["wikitext"])
            self.assertTrue(
                "{{Dokumentasi navbox}}" in res["doc_wikitext"]
                or "{{Dokumentasi templat}}" in res["doc_wikitext"]
            )

    def test_sync_template_with_publish_missing_credentials(self):
        self.mock_en_client.fetch_wikitext.return_value = "{{Navbox| name = Test }}"
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {}, clear=True):
                res = self.syncer.sync_template(
                    template_name="Test",
                    output_dir=Path(tmpdir),
                    publish=True,
                )
                self.assertFalse(res["published"])
                self.assertIn("error", res["publish_results"])
                self.assertIn("Credentials missing", res["publish_results"]["error"])

    @patch.object(TemplateSyncer, "_authenticate_bot_password")
    @patch.object(TemplateSyncer, "_get_csrf_token")
    @patch.object(TemplateSyncer, "_edit_page")
    def test_sync_template_with_publish_success(
        self, mock_edit_page, mock_get_csrf_token, mock_auth
    ):
        self.mock_en_client.fetch_wikitext.return_value = "{{Navbox| name = Test | group1 = Feature films | list1 = [[A]] }}"
        mock_auth.return_value = (True, None)
        mock_get_csrf_token.return_value = ("fake_csrf_token", None)
        mock_edit_page.return_value = {"success": True, "edit": {"result": "Success"}}

        with tempfile.TemporaryDirectory() as tmpdir:
            res = self.syncer.sync_template(
                template_name="Test",
                publish=True,
                username="BotUser@Bot",
                bot_password="secretpassword",
                output_dir=Path(tmpdir),
            )
            self.assertTrue(res["published"])
            self.assertTrue(res["publish_results"]["success"])
            self.assertEqual(mock_edit_page.call_count, 2)
            # Check summary passed
            for call_args in mock_edit_page.call_args_list:
                args, kwargs = call_args
                self.assertEqual(kwargs.get("summary") or args[2], "pemutakhiran templat & dokumentasi")
                self.assertEqual(kwargs.get("csrf_token") or args[3], "fake_csrf_token")

    def test_default_instance(self):
        self.assertIsInstance(default_template_syncer, TemplateSyncer)


class TestCLIIntegration(unittest.TestCase):
    @patch("wiki_translator.cli.default_template_syncer.sync_template")
    def test_cli_sync_template_flag(self, mock_sync):
        from wiki_translator.cli import main
        import sys

        mock_sync.return_value = {
            "id_title": "Templat:Test",
            "doc_title": "Templat:Test/doc",
            "template_file": "output/templates/Test.wikitext",
            "doc_file": "output/templates/Test_doc.wikitext",
            "published": False,
        }

        test_args = ["cli.py", "--sync-template", "Christopher Nolan"]
        with patch.object(sys, "argv", test_args):
            main()
            mock_sync.assert_called_once()
            args, kwargs = mock_sync.call_args
            self.assertEqual(args[0], "Christopher Nolan")
            self.assertFalse(kwargs.get("publish"))

    @patch("wiki_translator.cli.default_template_syncer.sync_template")
    def test_cli_sync_template_publish_flag(self, mock_sync):
        from wiki_translator.cli import main
        import sys

        mock_sync.return_value = {
            "id_title": "Templat:Test",
            "doc_title": "Templat:Test/doc",
            "template_file": "output/templates/Test.wikitext",
            "doc_file": "output/templates/Test_doc.wikitext",
            "published": True,
        }

        test_args = ["cli.py", "--update-template", "Christopher Nolan", "--publish-template"]
        with patch.object(sys, "argv", test_args):
            main()
            mock_sync.assert_called_once()
            args, kwargs = mock_sync.call_args
            self.assertEqual(args[0], "Christopher Nolan")
            self.assertTrue(kwargs.get("publish"))


if __name__ == "__main__":
    unittest.main()
