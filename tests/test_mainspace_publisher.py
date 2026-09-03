"""
Unit tests for Mainspace Publisher and Page Mover (wiki_translator/mainspace_publisher.py).
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from wiki_translator.mainspace_publisher import (
    MainspacePublisher,
    default_mainspace_publisher,
)


class TestMainspacePublisher(unittest.TestCase):
    def setUp(self):
        self.publisher = MainspacePublisher()

    def test_default_instance(self):
        self.assertIsInstance(default_mainspace_publisher, MainspacePublisher)

    def test_check_mainspace_collision_page_exists(self):
        mock_response = {
            "query": {
                "pages": {
                    "12345": {
                        "pageid": 12345,
                        "ns": 0,
                        "title": "The Runner (film 2026)",
                    }
                }
            }
        }
        with patch.object(self.publisher, "_make_request", return_value=(mock_response, None)):
            exists, url = self.publisher.check_mainspace_collision("The Runner (film 2026)")
            self.assertTrue(exists)
            self.assertEqual(url, "https://id.wikipedia.org/wiki/The_Runner_(film_2026)")

    def test_check_mainspace_collision_page_missing(self):
        mock_response = {
            "query": {
                "pages": {
                    "-1": {
                        "ns": 0,
                        "title": "Artikel Tidak Ada 2026",
                        "missing": "",
                    }
                }
            }
        }
        with patch.object(self.publisher, "_make_request", return_value=(mock_response, None)):
            exists, url = self.publisher.check_mainspace_collision("Artikel Tidak Ada 2026")
            self.assertFalse(exists)
            self.assertIsNone(url)

    def test_check_mainspace_collision_api_error(self):
        with patch.object(self.publisher, "_make_request", return_value=(None, "Connection timeout")):
            exists, url = self.publisher.check_mainspace_collision("Some Article")
            self.assertFalse(exists)
            self.assertIsNone(url)

    def test_move_draft_to_mainspace_dry_run(self):
        result = self.publisher.move_draft_to_mainspace(
            username="EditorUser",
            bot_password="secret_password",
            sandbox_source="Pengguna:EditorUser/Bak_pasir/Draf/2026-09/The_Runner",
            mainspace_target="The Runner (film 2026)",
            reason="Uji coba pemindahan",
            move_talk=True,
            dry_run=True,
        )
        self.assertTrue(result["success"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["from"], "Pengguna:EditorUser/Bak_pasir/Draf/2026-09/The_Runner")
        self.assertEqual(result["to"], "The Runner (film 2026)")
        self.assertTrue(result["talk_moved"])
        self.assertEqual(result["url"], "https://id.wikipedia.org/wiki/The_Runner_(film_2026)")
        self.assertIsNone(result["error"])

    def test_move_draft_to_mainspace_auth_failure(self):
        with patch.object(self.publisher, "_authenticate_bot_password", return_value=(False, "Incorrect password")):
            result = self.publisher.move_draft_to_mainspace(
                username="EditorUser",
                bot_password="wrong_password",
                sandbox_source="Pengguna:EditorUser/Bak_pasir/Draf/The_Runner",
                mainspace_target="The Runner (film 2026)",
                dry_run=False,
            )
            self.assertFalse(result["success"])
            self.assertIn("Authentication failed", result["error"])

    def test_move_draft_to_mainspace_csrf_failure(self):
        with patch.object(self.publisher, "_authenticate_bot_password", return_value=(True, None)):
            with patch.object(self.publisher, "_get_csrf_token", return_value=(None, "CSRF error")):
                result = self.publisher.move_draft_to_mainspace(
                    username="EditorUser",
                    bot_password="valid_password",
                    sandbox_source="Pengguna:EditorUser/Bak_pasir/Draf/The_Runner",
                    mainspace_target="The Runner (film 2026)",
                    dry_run=False,
                )
                self.assertFalse(result["success"])
                self.assertIn("CSRF", result["error"])

    def test_move_draft_to_mainspace_success(self):
        with patch.object(self.publisher, "_authenticate_bot_password", return_value=(True, None)):
            with patch.object(self.publisher, "_get_csrf_token", return_value=("csrf123+\\", None)):
                move_api_resp = {
                    "move": {
                        "from": "Pengguna:EditorUser/Bak_pasir/Draf/The_Runner",
                        "to": "The Runner (film 2026)",
                        "reason": "pemindahan draf ke ruang utama",
                        "talkmove": {"from": "Pembicaraan_Pengguna:EditorUser/...", "to": "Pembicaraan:..."},
                    }
                }
                with patch.object(self.publisher, "_make_request", return_value=(move_api_resp, None)) as mock_req:
                    result = self.publisher.move_draft_to_mainspace(
                        username="EditorUser",
                        bot_password="valid_password",
                        sandbox_source="Pengguna:EditorUser/Bak_pasir/Draf/The_Runner",
                        mainspace_target="The Runner (film 2026)",
                        reason=None,
                        move_talk=True,
                        dry_run=False,
                    )
                    self.assertTrue(result["success"])
                    self.assertEqual(result["from"], "Pengguna:EditorUser/Bak_pasir/Draf/The_Runner")
                    self.assertEqual(result["to"], "The Runner (film 2026)")
                    self.assertTrue(result["talk_moved"])
                    self.assertIsNone(result["error"])

                    # Check that _make_request received the right move params
                    mock_req.assert_called_once()
                    params = mock_req.call_args[0][0]
                    self.assertEqual(params["action"], "move")
                    self.assertEqual(params["from"], "Pengguna:EditorUser/Bak_pasir/Draf/The_Runner")
                    self.assertEqual(params["to"], "The Runner (film 2026)")
                    self.assertEqual(params["movetalk"], "1")
                    self.assertEqual(params["token"], "csrf123+\\")
                    self.assertEqual(params["reason"], "pemindahan draf ke ruang utama")

    def test_move_draft_to_mainspace_api_error_response(self):
        with patch.object(self.publisher, "_authenticate_bot_password", return_value=(True, None)):
            with patch.object(self.publisher, "_get_csrf_token", return_value=("csrf123+\\", None)):
                error_resp = {
                    "error": {
                        "code": "articleexists",
                        "info": "Halaman tujuan sudah ada.",
                    }
                }
                with patch.object(self.publisher, "_make_request", return_value=(error_resp, None)):
                    result = self.publisher.move_draft_to_mainspace(
                        username="EditorUser",
                        bot_password="valid_password",
                        sandbox_source="Pengguna:EditorUser/Bak_pasir/Draf/The_Runner",
                        mainspace_target="The Runner (film 2026)",
                        dry_run=False,
                    )
                    self.assertFalse(result["success"])
                    self.assertEqual(result["error"], "Halaman tujuan sudah ada.")

    def test_publish_directly_to_mainspace_collision_prevented(self):
        with patch.object(
            self.publisher,
            "check_mainspace_collision",
            return_value=(True, "https://id.wikipedia.org/wiki/The_Runner"),
        ):
            result = self.publisher.publish_directly_to_mainspace(
                username="EditorUser",
                bot_password="valid_password",
                mainspace_title="The Runner",
                wikitext="== Konten ==",
                force=False,
                dry_run=False,
            )
            self.assertFalse(result["success"])
            self.assertIn("already exists", result["error"])
            self.assertEqual(result["main_page"]["url"], "https://id.wikipedia.org/wiki/The_Runner")

    def test_publish_directly_to_mainspace_force_overwrite(self):
        with patch.object(
            self.publisher,
            "check_mainspace_collision",
            return_value=(True, "https://id.wikipedia.org/wiki/The_Runner"),
        ):
            with patch.object(self.publisher, "_authenticate_bot_password", return_value=(True, None)):
                with patch.object(self.publisher, "_get_csrf_token", return_value=("csrf123+\\", None)):
                    edit_resp = {"success": True, "edit": {"result": "Success", "pageid": 999, "newrevid": 1234}}
                    with patch.object(self.publisher, "_edit_page", return_value=edit_resp) as mock_edit:
                        result = self.publisher.publish_directly_to_mainspace(
                            username="EditorUser",
                            bot_password="valid_password",
                            mainspace_title="The Runner",
                            wikitext="== Konten Baru ==",
                            talk_wikitext="== Atribusi ==",
                            force=True,
                            dry_run=False,
                        )
                        self.assertTrue(result["success"])
                        self.assertEqual(result["main_page"]["status"], "published")
                        self.assertEqual(result["main_page"]["pageid"], 999)
                        self.assertEqual(result["talk_page"]["status"], "published")
                        self.assertEqual(mock_edit.call_count, 2)

    def test_publish_directly_to_mainspace_dry_run(self):
        with patch.object(
            self.publisher,
            "check_mainspace_collision",
            return_value=(False, None),
        ):
            result = self.publisher.publish_directly_to_mainspace(
                username="EditorUser",
                bot_password="valid_password",
                mainspace_title="Artikel Unik 2026",
                wikitext="== Konten ==",
                talk_wikitext="== Atribusi ==",
                dry_run=True,
            )
            self.assertTrue(result["success"])
            self.assertTrue(result["dry_run"])
            self.assertEqual(result["main_page"]["status"], "simulated")
            self.assertEqual(result["main_page"]["title"], "Artikel Unik 2026")
            self.assertEqual(
                result["main_page"]["url"],
                "https://id.wikipedia.org/wiki/Artikel_Unik_2026",
            )
            self.assertEqual(result["talk_page"]["status"], "simulated")
            self.assertEqual(result["talk_page"]["title"], "Pembicaraan:Artikel Unik 2026")

    def test_authenticate_bot_password_flow(self):
        # 1. Login token response
        token_payload = {"query": {"tokens": {"logintoken": "login_token_xyz"}}}
        # 2. Login response
        login_success_payload = {"login": {"result": "Success", "lgusername": "TestUser"}}

        with patch.object(self.publisher, "_make_request", side_effect=[(token_payload, None), (login_success_payload, None)]):
            ok, err = self.publisher._authenticate_bot_password("TestUser", "password123")
            self.assertTrue(ok)
            self.assertIsNone(err)

    def test_authenticate_bot_password_rejected(self):
        token_payload = {"query": {"tokens": {"logintoken": "login_token_xyz"}}}
        login_failed_payload = {"login": {"result": "Failed", "reason": "Wrong password"}}

        with patch.object(self.publisher, "_make_request", side_effect=[(token_payload, None), (login_failed_payload, None)]):
            ok, err = self.publisher._authenticate_bot_password("TestUser", "wrongpass")
            self.assertFalse(ok)
            self.assertIn("Wrong password", err)

    def test_get_csrf_token_success_and_failure(self):
        # Success
        success_payload = {"query": {"tokens": {"csrftoken": "test_csrf_token+\\"}}}
        with patch.object(self.publisher, "_make_request", return_value=(success_payload, None)):
            token, err = self.publisher._get_csrf_token()
            self.assertEqual(token, "test_csrf_token+\\")
            self.assertIsNone(err)

        # Missing token in payload
        missing_payload = {"query": {"tokens": {}}}
        with patch.object(self.publisher, "_make_request", return_value=(missing_payload, None)):
            token, err = self.publisher._get_csrf_token()
            self.assertIsNone(token)
            self.assertIn("CSRF token not present", err)

        # Network error
        with patch.object(self.publisher, "_make_request", return_value=(None, "Network failure")):
            token, err = self.publisher._get_csrf_token()
            self.assertIsNone(token)
            self.assertEqual(err, "Network failure")

    def test_publish_directly_auth_and_csrf_failure(self):
        with patch.object(self.publisher, "check_mainspace_collision", return_value=(False, None)):
            # Auth failure
            with patch.object(self.publisher, "_authenticate_bot_password", return_value=(False, "Invalid bot credentials")):
                res = self.publisher.publish_directly_to_mainspace(
                    username="UserX",
                    bot_password="wrong",
                    mainspace_title="Judul Baru",
                    wikitext="Teks",
                )
                self.assertFalse(res["success"])
                self.assertIn("Authentication failed", res["error"])

            # CSRF failure
            with patch.object(self.publisher, "_authenticate_bot_password", return_value=(True, None)):
                with patch.object(self.publisher, "_get_csrf_token", return_value=(None, "CSRF fetch failed")):
                    res = self.publisher.publish_directly_to_mainspace(
                        username="UserX",
                        bot_password="correct",
                        mainspace_title="Judul Baru",
                        wikitext="Teks",
                    )
                    self.assertFalse(res["success"])
                    self.assertIn("Failed to obtain CSRF token", res["error"])


class TestMainspaceCLIIntegration(unittest.TestCase):
    def setUp(self):
        from pathlib import Path
        import tempfile
        import shutil
        self.tmp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_cli_arguments_parsing(self):
        from wiki_translator.cli import main
        with patch(
            "sys.argv",
            [
                "wiki_translator",
                "The Runner",
                "--publish-main",
                "The Runner (film 2026)",
                "--promote-draft",
                "The Runner (film 2026)",
                "--force-overwrite",
            ],
        ):
            with patch("wiki_translator.cli.WikiTranslatorCLI") as mock_cli:
                main()
                mock_cli.assert_called_once()
                _, kwargs = mock_cli.call_args
                self.assertEqual(kwargs["publish_main"], "The Runner (film 2026)")
                self.assertEqual(kwargs["promote_draft"], "The Runner (film 2026)")
                self.assertTrue(kwargs["force_overwrite"])

    def test_cli_handle_publishing_choice_3_direct_mainspace(self):
        from wiki_translator.cli import WikiTranslatorCLI
        mock_mainspace_pub = MagicMock(spec=MainspacePublisher)
        mock_mainspace_pub.publish_directly_to_mainspace.return_value = {
            "success": True,
            "dry_run": True,
            "main_page": {
                "title": "Direct Article",
                "url": "https://id.wikipedia.org/wiki/Direct_Article",
            },
        }

        cli = WikiTranslatorCLI(
            output_dir=str(self.tmp_dir),
            publish_sandbox="TestEditor",
            publish_main="Direct Article",
            mainspace_publisher=mock_mainspace_pub,
        )

        wiki_f = self.tmp_dir / "art.wikitext"
        talk_f = self.tmp_dir / "art.talk.wikitext"
        wiki_f.write_text("== Konten Utama ==", encoding="utf-8")
        talk_f.write_text("== Atribusi Talk ==", encoding="utf-8")

        with patch.dict("os.environ", {}, clear=True), patch("getpass.getpass", return_value=""):
            cli._handle_sandbox_publishing("Direct Article", wiki_f, talk_f)

        mock_mainspace_pub.publish_directly_to_mainspace.assert_called_once_with(
            username="TestEditor",
            bot_password="dummy",
            mainspace_title="Direct Article",
            wikitext="== Konten Utama ==",
            talk_wikitext="== Atribusi Talk ==",
            summary=None,
            force=False,
            dry_run=True,
            en_title="Direct Article",
        )

    def test_cli_handle_publishing_choice_2_promote_draft(self):
        from wiki_translator.cli import WikiTranslatorCLI
        from wiki_translator.sandbox_publisher import SandboxPublisher

        mock_sandbox_pub = MagicMock(spec=SandboxPublisher)
        mock_sandbox_pub.publish_to_sandbox.return_value = {
            "success": True,
            "dry_run": True,
            "main_page": {
                "title": "Pengguna:TestEditor/Bak_pasir/Draf/2026-09/Article_X",
                "url": "https://id.wikipedia.org/wiki/Pengguna:TestEditor/Bak_pasir/Draf/2026-09/Article_X",
            },
        }
        mock_mainspace_pub = MagicMock(spec=MainspacePublisher)
        mock_mainspace_pub.check_mainspace_collision.return_value = (False, None)
        mock_mainspace_pub.move_draft_to_mainspace.return_value = {
            "success": True,
            "url": "https://id.wikipedia.org/wiki/Article_X",
            "from": "Pengguna:TestEditor/Bak_pasir/Draf/2026-09/Article_X",
            "to": "Article X",
            "talk_moved": True,
            "error": None,
        }

        cli = WikiTranslatorCLI(
            output_dir=str(self.tmp_dir),
            publish_sandbox="TestEditor",
            promote_draft="Article X",
            sandbox_publisher=mock_sandbox_pub,
            mainspace_publisher=mock_mainspace_pub,
        )

        wiki_f = self.tmp_dir / "art.wikitext"
        talk_f = self.tmp_dir / "art.talk.wikitext"
        wiki_f.write_text("== Konten Utama ==", encoding="utf-8")
        talk_f.write_text("== Atribusi Talk ==", encoding="utf-8")

        with patch.dict("os.environ", {}, clear=True), patch("getpass.getpass", return_value=""):
            cli._handle_sandbox_publishing("Article X", wiki_f, talk_f)

        mock_sandbox_pub.publish_to_sandbox.assert_called_once()
        mock_mainspace_pub.move_draft_to_mainspace.assert_called_once_with(
            username="TestEditor",
            bot_password="dummy",
            sandbox_source="Pengguna:TestEditor/Bak_pasir/Draf/2026-09/Article_X",
            mainspace_target="Article X",
            reason=None,
            move_talk=True,
            dry_run=True,
            en_title="Article X",
        )

    def test_cli_handle_publishing_choice_4_local_only(self):
        from wiki_translator.cli import WikiTranslatorCLI
        from wiki_translator.sandbox_publisher import SandboxPublisher

        mock_sandbox_pub = MagicMock(spec=SandboxPublisher)
        mock_mainspace_pub = MagicMock(spec=MainspacePublisher)

        cli = WikiTranslatorCLI(
            output_dir=str(self.tmp_dir),
            publish_sandbox="TestEditor",
            sandbox_publisher=mock_sandbox_pub,
            mainspace_publisher=mock_mainspace_pub,
        )

        wiki_f = self.tmp_dir / "art.wikitext"
        talk_f = self.tmp_dir / "art.talk.wikitext"
        wiki_f.write_text("== Konten Utama ==", encoding="utf-8")
        talk_f.write_text("== Atribusi Talk ==", encoding="utf-8")

        # Select option 4: Simpan Lokal Saja
        with patch("builtins.input", return_value="4"):
            cli._handle_sandbox_publishing("Article Local", wiki_f, talk_f, auto_approve=False)

        mock_sandbox_pub.publish_to_sandbox.assert_not_called()
        mock_mainspace_pub.publish_directly_to_mainspace.assert_not_called()
        mock_mainspace_pub.move_draft_to_mainspace.assert_not_called()

if __name__ == "__main__":
    unittest.main()
