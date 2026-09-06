"""
Integration unit tests for HTML Preview and Sandbox Publisher within CLI.
"""

import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from wiki_translator.cli import WikiTranslatorCLI, load_env_file, main
from wiki_translator.html_preview import HTMLPreviewGenerator
from wiki_translator.sandbox_publisher import SandboxPublisher
from wiki_translator.wiki_client import WikiSection


class TestCLIPublisherAndPreviewIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_cli_save_output_generates_preview_file(self):
        cli = WikiTranslatorCLI(
            output_dir=str(self.tmp_dir),
            enable_map_links=False,
            enable_cache=False,
            enable_compression=False,
            enable_delta_skip=False,
            enable_auto_glossary=False,
        )

        section = WikiSection(
            index=1,
            title="Pengenalan",
            level=2,
            header_raw="== Pengenalan ==",
            content="Komputasi kuantum adalah bidang komputasi canggih.",
            word_count=7,
            char_count=50,
            translated_content="== Pengenalan ==\nKomputasi kuantum adalah bidang komputasi canggih.",
        )

        res = cli._save_output("komputasi_kuantum", "Komputasi kuantum", [section])
        preview_file = self.tmp_dir / "komputasi_kuantum.preview.html"

        self.assertTrue(preview_file.exists())
        self.assertEqual(res.preview, preview_file)
        content = preview_file.read_text(encoding="utf-8")
        self.assertIn("Komputasi kuantum", content)
        self.assertIn("Pratinjau Draf Terjemahan Wikipedia Bahasa Indonesia", content)

    def test_cli_argparser_preview_and_sandbox_flags(self):
        with patch(
            "sys.argv",
            [
                "wiki_translator",
                "Quantum computing",
                "--preview",
                "--publish-sandbox",
                "TestEditor",
                "--sandbox-slug",
                "2026-09/Special",
                "--sandbox-project",
                "CustomProject",
            ],
        ):
            with patch("wiki_translator.cli.WikiTranslatorCLI") as mock_cli:
                main()
                mock_cli.assert_called_once()
                _, kwargs = mock_cli.call_args
                self.assertTrue(kwargs["auto_preview"])
                self.assertEqual(kwargs["publish_sandbox"], "TestEditor")
                self.assertEqual(kwargs["sandbox_slug"], "2026-09/Special")
                self.assertEqual(kwargs["project_slug"], "CustomProject")

    def test_cli_argparser_project_slug_alias(self):
        with patch(
            "sys.argv",
            [
                "wiki_translator",
                "Quantum computing",
                "--project-slug",
                "AltProject",
            ],
        ):
            with patch("wiki_translator.cli.WikiTranslatorCLI") as mock_cli:
                main()
                mock_cli.assert_called_once()
                _, kwargs = mock_cli.call_args
                self.assertEqual(kwargs["project_slug"], "AltProject")
    def test_cli_handle_sandbox_publishing_dry_run(self):
        mock_publisher = MagicMock(spec=SandboxPublisher)
        mock_publisher.publish_to_sandbox.return_value = {
            "success": True,
            "dry_run": True,
            "main_page": {
                "title": "Pengguna:TestUser/Bak_pasir/2026-09/Uji",
                "url": "https://id.wikipedia.org/wiki/Pengguna:TestUser/Bak_pasir/2026-09/Uji",
            },
        }

        cli = WikiTranslatorCLI(
            output_dir=str(self.tmp_dir),
            publish_sandbox="TestUser",
            sandbox_slug="2026-09",
            project_slug="Draf",
            sandbox_publisher=mock_publisher,
        )
        wiki_f = self.tmp_dir / "uji.wikitext"
        talk_f = self.tmp_dir / "uji.talk.wikitext"
        wiki_f.write_text("== Konten ==", encoding="utf-8")
        talk_f.write_text("== Talk ==", encoding="utf-8")

        with patch.dict("os.environ", {}, clear=True), patch("getpass.getpass", return_value=""), patch("builtins.input", return_value="1"):
            cli._handle_sandbox_publishing("Uji", wiki_f, talk_f)
        mock_publisher.publish_to_sandbox.assert_called_once_with(
            username="TestUser",
            bot_password="dummy",
            article_title="Uji",
            wikitext="== Konten ==",
            talk_wikitext="== Talk ==",
            slug="2026-09",
            project_slug="Draf",
            dry_run=True,
        )

    def test_cli_handle_sandbox_publishing_interactive_custom_project_slug(self):
        mock_publisher = MagicMock(spec=SandboxPublisher)
        mock_publisher.publish_to_sandbox.return_value = {
            "success": True,
            "dry_run": True,
            "main_page": {
                "title": "Pengguna:PromptUser/Bak_pasir/InteractiveProject/2026-09/Uji",
                "url": "https://id.wikipedia.org/wiki/Pengguna:PromptUser/Bak_pasir/InteractiveProject/2026-09/Uji",
            },
        }

        cli = WikiTranslatorCLI(
            output_dir=str(self.tmp_dir),
            publish_sandbox=None,
            sandbox_slug="2026-09",
            project_slug="Draf",
            sandbox_publisher=mock_publisher,
        )
        wiki_f = self.tmp_dir / "uji.wikitext"
        talk_f = self.tmp_dir / "uji.talk.wikitext"
        wiki_f.write_text("== Konten ==", encoding="utf-8")
        talk_f.write_text("== Talk ==", encoding="utf-8")

        # inputs: 1) ask_publish ("y"), 2) username ("PromptUser"), 3) proj_in ("InteractiveProject")
        with patch.dict("os.environ", {}, clear=True), \
             patch("builtins.input", side_effect=["y", "PromptUser", "InteractiveProject"]), \
             patch("getpass.getpass", return_value=""):
            cli._handle_sandbox_publishing("Uji", wiki_f, talk_f)

        self.assertEqual(cli.project_slug, "InteractiveProject")
        mock_publisher.publish_to_sandbox.assert_called_once_with(
            username="PromptUser",
            bot_password="dummy",
            article_title="Uji",
            wikitext="== Konten ==",
            talk_wikitext="== Talk ==",
            slug="2026-09",
            project_slug="InteractiveProject",
            dry_run=True,
        )

    def test_cli_handle_sandbox_publishing_interactive_default_project_slug(self):
        mock_publisher = MagicMock(spec=SandboxPublisher)
        mock_publisher.publish_to_sandbox.return_value = {
            "success": True,
            "dry_run": True,
            "main_page": {
                "title": "Pengguna:PromptUser/Bak_pasir/Draf/2026-09/Uji",
                "url": "https://id.wikipedia.org/wiki/Pengguna:PromptUser/Bak_pasir/Draf/2026-09/Uji",
            },
        }

        cli = WikiTranslatorCLI(
            output_dir=str(self.tmp_dir),
            publish_sandbox=None,
            sandbox_slug="2026-09",
            project_slug="Draf",
            sandbox_publisher=mock_publisher,
        )
        wiki_f = self.tmp_dir / "uji.wikitext"
        talk_f = self.tmp_dir / "uji.talk.wikitext"
        wiki_f.write_text("== Konten ==", encoding="utf-8")
        talk_f.write_text("== Talk ==", encoding="utf-8")

        # inputs: 1) ask_publish ("y"), 2) username ("PromptUser"), 3) proj_in ("") -> keep default
        with patch.dict("os.environ", {}, clear=True), \
             patch("builtins.input", side_effect=["y", "PromptUser", ""]), \
             patch("getpass.getpass", return_value=""):
            cli._handle_sandbox_publishing("Uji", wiki_f, talk_f)

        self.assertEqual(cli.project_slug, "Draf")
        mock_publisher.publish_to_sandbox.assert_called_once_with(
            username="PromptUser",
            bot_password="dummy",
            article_title="Uji",
            wikitext="== Konten ==",
            talk_wikitext="== Talk ==",
            slug="2026-09",
            project_slug="Draf",
            dry_run=True,
        )

    def test_load_env_file_parses_simple_and_quoted_values(self):
        env_file = self.tmp_dir / ".env"
        env_file.write_text(
            "# Comment line\n"
            "\n"
            "WIKI_USERNAME=TestFromEnv\n"
            'WIKI_BOT_PASSWORD="bot_password_12345"\n'
            "GEMINI_API_KEY='secret_key_67890'\n"
            "EXISTING_KEY=new_val\n",
            encoding="utf-8",
        )

        with patch.dict("os.environ", {"EXISTING_KEY": "original_val"}, clear=True):
            load_env_file(env_path=env_file)
            self.assertEqual(os.environ.get("WIKI_USERNAME"), "TestFromEnv")
            self.assertEqual(os.environ.get("WIKI_BOT_PASSWORD"), "bot_password_12345")
            self.assertEqual(os.environ.get("GEMINI_API_KEY"), "secret_key_67890")
            self.assertEqual(os.environ.get("EXISTING_KEY"), "original_val")

    def test_load_env_file_searches_parent_directories(self):
        parent_dir = self.tmp_dir / "project"
        sub_dir = parent_dir / "subdir" / "deep"
        sub_dir.mkdir(parents=True)
        env_file = parent_dir / ".env"
        env_file.write_text("WIKI_USERNAME=ParentDirUser\n", encoding="utf-8")

        with patch("pathlib.Path.cwd", return_value=sub_dir):
            with patch.dict("os.environ", {}, clear=True):
                load_env_file()
                self.assertEqual(os.environ.get("WIKI_USERNAME"), "ParentDirUser")

    def test_cli_handle_sandbox_publishing_uses_env_vars(self):
        mock_publisher = MagicMock(spec=SandboxPublisher)
        mock_publisher.publish_to_sandbox.return_value = {
            "success": True,
            "dry_run": False,
            "main_page": {
                "title": "Pengguna:EnvUser/Bak_pasir/Draf/2026-09/Uji",
                "url": "https://id.wikipedia.org/wiki/Pengguna:EnvUser/Bak_pasir/Draf/2026-09/Uji",
            },
        }

        cli = WikiTranslatorCLI(
            output_dir=str(self.tmp_dir),
            publish_sandbox=None,
            sandbox_slug="2026-09",
            project_slug="Draf",
            sandbox_publisher=mock_publisher,
        )
        wiki_f = self.tmp_dir / "uji.wikitext"
        talk_f = self.tmp_dir / "uji.talk.wikitext"
        wiki_f.write_text("== Konten ==", encoding="utf-8")
        talk_f.write_text("== Talk ==", encoding="utf-8")

        with patch.dict(
            "os.environ",
            {
                "WIKI_USERNAME": "EnvUser",
                "WIKI_BOT_PASSWORD": "SecretBotPassword123",
            },
            clear=True,
        ), patch("builtins.input", return_value="1"):
            cli._handle_sandbox_publishing("Uji", wiki_f, talk_f)

        mock_publisher.publish_to_sandbox.assert_called_once_with(
            username="EnvUser",
            bot_password="SecretBotPassword123",
            article_title="Uji",
            wikitext="== Konten ==",
            talk_wikitext="== Talk ==",
            slug="2026-09",
            project_slug="Draf",
            dry_run=False,
        )


if __name__ == "__main__":
    unittest.main()
