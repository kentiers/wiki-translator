"""
Unit tests for Structured User Sandbox Publisher (wiki_translator/sandbox_publisher.py).
"""

from datetime import datetime
import json
import unittest
from unittest.mock import MagicMock, patch

from wiki_translator.sandbox_publisher import (
    SandboxPublisher,
    default_sandbox_publisher,
)

from wiki_translator.sandbox_publisher import sanitize_edit_summary


class TestSandboxPublisher(unittest.TestCase):
    def setUp(self):
        self.publisher = SandboxPublisher()

    def test_build_sandbox_titles_default_slug(self):
        main_page, talk_page = self.publisher.build_sandbox_titles(
            username="Budi Santoso",
            article_title="Quantum computing",
            slug=None,
        )
        current_ym = datetime.now().strftime("%Y-%m")
        expected_main = f"Pengguna:Budi_Santoso/Bak_pasir/Draf/{current_ym}/Quantum_computing"
        expected_talk = f"Pembicaraan_Pengguna:Budi_Santoso/Bak_pasir/Draf/{current_ym}/Quantum_computing"

        self.assertEqual(main_page, expected_main)
        self.assertEqual(talk_page, expected_talk)

    def test_build_sandbox_titles_custom_project_slug(self):
        main_page, talk_page = self.publisher.build_sandbox_titles(
            username="Budi",
            article_title="The Runner",
            slug=None,
            project_slug="ProyekKhusus",
        )
        current_ym = datetime.now().strftime("%Y-%m")
        self.assertEqual(
            main_page,
            f"Pengguna:Budi/Bak_pasir/ProyekKhusus/{current_ym}/The_Runner",
        )
        self.assertEqual(
            talk_page,
            f"Pembicaraan_Pengguna:Budi/Bak_pasir/ProyekKhusus/{current_ym}/The_Runner",
        )

    def test_build_sandbox_titles_empty_project_slug(self):
        main_page, talk_page = self.publisher.build_sandbox_titles(
            username="Budi",
            article_title="The Runner",
            slug=None,
            project_slug=None,
        )
        current_ym = datetime.now().strftime("%Y-%m")
        self.assertEqual(
            main_page,
            f"Pengguna:Budi/Bak_pasir/{current_ym}/The_Runner",
        )
        self.assertEqual(
            talk_page,
            f"Pembicaraan_Pengguna:Budi/Bak_pasir/{current_ym}/The_Runner",
        )
    def test_build_sandbox_titles_custom_slug(self):
        main_page, talk_page = self.publisher.build_sandbox_titles(
            username="Editor123",
            article_title="The Matrix (Film)",
            slug="2026-03/Proyek_Film",
        )
        self.assertEqual(
            main_page,
            "Pengguna:Editor123/Bak_pasir/2026-03/Proyek_Film/The_Matrix_(Film)",
        )
        self.assertEqual(
            talk_page,
            "Pembicaraan_Pengguna:Editor123/Bak_pasir/2026-03/Proyek_Film/The_Matrix_(Film)",
        )
    def test_build_sandbox_titles_bot_username_with_at(self):
        main_page, talk_page = self.publisher.build_sandbox_titles(
            username="Baloo Official@asisten_draf",
            article_title="Film Baru",
            slug="Proyek/2026-03",
        )
        self.assertEqual(
            main_page,
            "Pengguna:Baloo_Official/Bak_pasir/Proyek/2026-03/Film_Baru",
        )
        self.assertEqual(
            talk_page,
            "Pembicaraan_Pengguna:Baloo_Official/Bak_pasir/Proyek/2026-03/Film_Baru",
        )


    def test_publish_to_sandbox_dry_run(self):
        res = self.publisher.publish_to_sandbox(
            username="TestUser",
            bot_password="dummy_password",
            article_title="Algoritma Shor",
            wikitext="== Algoritma ==\nPenjelasan...",
            talk_wikitext="{{Atribusi|en|Shor's algorithm}}",
            slug=None,
            project_slug=None,
            dry_run=True,
        )
        current_ym = datetime.now().strftime("%Y-%m")
        self.assertTrue(res["success"])
        self.assertTrue(res["dry_run"])
        self.assertEqual(
            res["main_page"]["title"],
            f"Pengguna:TestUser/Bak_pasir/{current_ym}/Algoritma_Shor",
        )
        self.assertEqual(res["main_page"]["status"], "simulated")
        self.assertIn("url", res["main_page"])
        self.assertEqual(
            res["talk_page"]["title"],
            f"Pembicaraan_Pengguna:TestUser/Bak_pasir/{current_ym}/Algoritma_Shor",
        )
        self.assertEqual(res["talk_page"]["status"], "simulated")
    def test_publish_to_sandbox_natural_summaries(self):
        # New page default summary
        res1 = self.publisher.publish_to_sandbox(
            username="TestUser",
            bot_password="dummy",
            article_title="Uji1",
            wikitext="Konten",
            talk_wikitext="Talk",
            is_new_page=True,
            dry_run=True,
        )
        self.assertEqual(res1["main_page"]["summary"], "buat draf awal")
        self.assertEqual(res1["talk_page"]["summary"], "atribusi terjemahan")

        # Update page default summary
        res2 = self.publisher.publish_to_sandbox(
            username="TestUser",
            bot_password="dummy",
            article_title="Uji2",
            wikitext="Konten",
            is_new_page=False,
            dry_run=True,
        )
        self.assertEqual(res2["main_page"]["summary"], "pemutakhiran draf")

        # Custom summary
        res3 = self.publisher.publish_to_sandbox(
            username="TestUser",
            bot_password="dummy",
            article_title="Uji3",
            wikitext="Konten",
            talk_wikitext="Talk",
            summary="merapikan teks dan rujukan",
            talk_summary="pencatatan sumber lisensi CC-BY-SA",
            dry_run=True,
        )
        self.assertEqual(res3["main_page"]["summary"], "merapikan teks dan rujukan")
        self.assertEqual(res3["talk_page"]["summary"], "pencatatan sumber lisensi CC-BY-SA")

    def test_sanitize_edit_summary_strips_forbidden_terms(self):
        leaked = "memperbarui draf rintisan Kevin Macdonald dengan model gemini-3.8-flash dan struktur standar Grade A++ sekarang"
        sanitized = sanitize_edit_summary(leaked)
        self.assertNotIn("gemini", sanitized.lower())
        self.assertNotIn("model", sanitized.lower())
        self.assertNotIn("flash", sanitized.lower())
        self.assertNotIn("grade a++", sanitized.lower())
        self.assertEqual(sanitized, "memperbarui draf rintisan Kevin Macdonald dengan dan struktur standar sekarang")

    def test_sanitize_edit_summary_fallback_when_empty_or_all_stripped(self):
        only_leaked = "gemini model flash grade a++ ai bot llm"
        sanitized = sanitize_edit_summary(only_leaked, default_fallback="pemutakhiran draf")
        self.assertEqual(sanitized, "pemutakhiran draf")

        empty_str = ""
        sanitized_empty = sanitize_edit_summary(empty_str, default_fallback="buat draf awal")
        self.assertEqual(sanitized_empty, "buat draf awal")

        none_str = None
        sanitized_none = sanitize_edit_summary(none_str, default_fallback="atribusi terjemahan")
        self.assertEqual(sanitized_none, "atribusi terjemahan")

    def test_publish_to_sandbox_sanitizes_leaked_summary(self):
        res = self.publisher.publish_to_sandbox(
            username="TestUser",
            bot_password="dummy",
            article_title="Kevin Macdonald",
            wikitext="Test",
            summary="memperbarui draf rintisan Kevin Macdonald dengan model gemini-3.8-flash dan Grade A++",
            dry_run=True,
        )
        self.assertNotIn("gemini", res["main_page"]["summary"].lower())
        self.assertNotIn("flash", res["main_page"]["summary"].lower())
        self.assertNotIn("grade a++", res["main_page"]["summary"].lower())

    def test_sanitize_edit_summary_humanizes_verbose_bot_summaries(self):
        self.assertEqual(
            sanitize_edit_summary("pemolesan menyeluruh: perbaikan tata bahasa ensiklopedis, istilah historis, standardisasi EYD V, dan resolusi pranala"),
            "rapikan terjemahan & rujukan",
        )
        self.assertEqual(
            sanitize_edit_summary("pemolesan menyeluruh tata bahasa dan kelancaran kalimat ensiklopedia (Test Article)"),
            "rapikan draf",
        )
        self.assertEqual(
            sanitize_edit_summary("catatan evaluasi draf pemolesan Test Article"),
            "catatan evaluasi",
        )
        self.assertEqual(
            sanitize_edit_summary("perbaikan kesalahan pengutipan: melengkapi definisi rujukan ref ':4'"),
            "perbaikan rujukan",
        )
        self.assertEqual(
            sanitize_edit_summary("standardisasi penggunaan istilah perempuan berstandar WP:GAYA"),
            "penyesuaian istilah",
        )
        self.assertEqual(
            sanitize_edit_summary("standardisasi target pranala Kekaisaran Rusia"),
            "perbaikan pranala",
        )

    def test_sanitize_edit_summary_length_capping_and_pompous_removal(self):
        long_text = "analisis mendalam dan pemolesan menyeluruh serta standardisasi ensiklopedis resolusi pranala yang sangat panjang sekali " * 3
        sanitized = sanitize_edit_summary(long_text)
        self.assertLessEqual(len(sanitized), 80)
        self.assertNotIn("analisis mendalam", sanitized.lower())
        self.assertNotIn("menyeluruh", sanitized.lower())
        self.assertNotIn("standardisasi", sanitized.lower())
        self.assertNotIn("ensiklopedis", sanitized.lower())
        self.assertNotIn("resolusi", sanitized.lower())


    def test_publish_to_sandbox_login_failure(self):
        # Mock tokens API then login returning failure
        with patch.object(self.publisher, "_make_request") as mock_req:
            mock_req.side_effect = [
                # 1. token
                ({"query": {"tokens": {"logintoken": "tok123"}}}, None),
                # 2. login
                ({"login": {"result": "Failed", "reason": "Incorrect username or password"}}, None),
            ]
            res = self.publisher.publish_to_sandbox(
                username="BadUser",
                bot_password="wrong_password",
                article_title="Artikel Uji",
                wikitext="Konten",
                dry_run=False,
            )
            self.assertFalse(res["success"])
            self.assertIn("Authentication failed", res["error"])

    def test_publish_to_sandbox_successful_flow(self):
        with patch.object(self.publisher, "_make_request") as mock_req:
            mock_req.side_effect = [
                # 1. Login token
                ({"query": {"tokens": {"logintoken": "logintoken123"}}}, None),
                # 2. Login response
                ({"login": {"result": "Success", "lgusername": "ValidUser"}}, None),
                # 3. CSRF token
                ({"query": {"tokens": {"csrftoken": "csrftoken456"}}}, None),
                # 4. Edit main page
                ({"edit": {"result": "Success", "pageid": 1001, "newrevid": 5001}}, None),
                # 5. Edit talk page
                ({"edit": {"result": "Success", "pageid": 1002, "newrevid": 5002}}, None),
            ]
            res = self.publisher.publish_to_sandbox(
                username="ValidUser",
                bot_password="bot@password",
                article_title="Kecerdasan Buatan",
                wikitext="== Definisi ==\nAI adalah...",
                talk_wikitext="{{Atribusi|en|Artificial intelligence}}",
                slug="2026-09",
                dry_run=False,
            )
            self.assertTrue(res["success"])
            self.assertFalse(res["dry_run"])
            self.assertEqual(res["main_page"]["status"], "published")
            self.assertEqual(res["main_page"]["pageid"], 1001)
            self.assertEqual(res["main_page"]["newrevid"], 5001)
            self.assertEqual(res["talk_page"]["status"], "published")
            self.assertEqual(res["talk_page"]["pageid"], 1002)

    def test_default_instance_exists(self):
        self.assertIsInstance(default_sandbox_publisher, SandboxPublisher)


if __name__ == "__main__":
    unittest.main()
