"""
Unit tests for Monthly Dashboard & Log Book manager (wiki_translator/sandbox_publisher.py and mainspace_publisher.py).
"""

from datetime import datetime
import unittest
from unittest.mock import MagicMock, patch

from wiki_translator.sandbox_publisher import (
    SandboxPublisher,
    DEFAULT_PROJECT_SLUG,
    DEFAULT_DASHBOARD_SUMMARY,
)
from wiki_translator.mainspace_publisher import MainspacePublisher


class TestMonthlyDashboard(unittest.TestCase):
    def setUp(self):
        self.publisher = SandboxPublisher()

    def test_build_monthly_index_title_default(self):
        title = self.publisher.build_monthly_index_title(
            username="Baloo Official@asisten_draf",
        )
        current_ym = datetime.now().strftime("%Y-%m")
        self.assertEqual(
            title,
            f"Pengguna:Baloo_Official/Bak_pasir/Draf/{current_ym}",
        )

    def test_build_monthly_index_title_custom_slug(self):
        title = self.publisher.build_monthly_index_title(
            username="Baloo Official",
            slug="2026-09",
            project_slug="Draf",
        )
        self.assertEqual(
            title,
            "Pengguna:Baloo_Official/Bak_pasir/Draf/2026-09",
        )

    def test_build_monthly_index_title_full_slug(self):
        title = self.publisher.build_monthly_index_title(
            username="Baloo Official",
            slug="ProyekKhusus/2026-09",
        )
        self.assertEqual(
            title,
            "Pengguna:Baloo_Official/Bak_pasir/ProyekKhusus/2026-09",
        )

    def test_build_monthly_index_title_no_project_slug(self):
        title = self.publisher.build_monthly_index_title(
            username="Baloo Official",
            slug="2026-09",
            project_slug=None,
        )
        self.assertEqual(
            title,
            "Pengguna:Baloo_Official/Bak_pasir/2026-09",
        )

    def test_parse_dashboard_rows_empty_or_no_table(self):
        trans_rows, review_rows = self.publisher.parse_dashboard_rows("Halaman kosong")
        self.assertEqual(trans_rows, [])
        self.assertEqual(review_rows, [])

    def test_parse_and_format_dashboard_rows(self):
        sample_wikitext = """== Buku Log & Portofolio Penerjemahan (September 2026) ==
Halaman ini mencatat seluruh portofolio aktivitas terjemahan baru dan peninjauan/pemolesan artikel pada bulan ini.

=== 1. Draf Terjemahan Baru ===
{| class="wikitable sortable" style="width:100%"
|-
! No
! Judul Draf
! Topik
! Status
! Tanggal
! Artikel Resmi
|-
| 1 || [[Pengguna:Baloo_Official/Bak_pasir/Draf/2026-09/The_Runner_(2026_film)|The Runner (2026 film)]] || Film || Tayang resmi || 03 September 2026 || [[The Runner (film 2026)]]
|-
| 2 || [[Pengguna:Baloo_Official/Bak_pasir/Draf/2026-09/Kevin_Macdonald|Kevin Macdonald]] || Biografi / Sutradara || Draf aktif || 03 September 2026 || -
|}

=== 2. Draf Peninjauan & Pemolesan Artikel (Reviu Komunitas) ===
{| class="wikitable sortable" style="width:100%"
|-
! No
! Judul Artikel
! Pemohon / Mitra
! Status Reviu
! Tanggal
! Draf Polesan di Bak Pasir
! Status Artikel
|-
| 1 || [[:Anna Filosofova]] || [[Pengguna:Glorious Engine|Glorious Engine]] || Audit selesai || 03 September 2026 || [[Pengguna:Baloo_Official/Bak_pasir/Draf/2026-09/Anna_Filosofova|Anna Filosofova (Draf Polesan)]] || [[:Anna Filosofova]]
|}

=== Ringkasan Statistik Bulanan ===
* '''Total Draf Terjemahan Baru:''' 2
* '''Total Artikel Ditinjau / Dipoles:''' 1
* '''Telah Tayang di Ruang Nama Utama:''' 1
* '''Daftar Semua Subhalaman:''' [[Istimewa:IndeksAwalan/Pengguna:Baloo_Official/Bak_pasir/Draf/2026-09/|Lihat semua subhalaman]]"""

        trans_rows, review_rows = self.publisher.parse_dashboard_rows(sample_wikitext)
        self.assertEqual(len(trans_rows), 2)
        self.assertEqual(trans_rows[0]["title"], "The Runner (2026 film)")
        self.assertEqual(trans_rows[0]["status"], "Tayang resmi")
        self.assertEqual(trans_rows[0]["mainspace_link"], "[[The Runner (film 2026)]]")
        self.assertEqual(trans_rows[1]["title"], "Kevin Macdonald")
        self.assertEqual(trans_rows[1]["status"], "Draf aktif")
        self.assertEqual(trans_rows[1]["mainspace_link"], "-")

        self.assertEqual(len(review_rows), 1)
        self.assertEqual(review_rows[0]["title"], "Anna Filosofova")
        self.assertEqual(review_rows[0]["requester"], "Glorious Engine")
        self.assertEqual(review_rows[0]["review_status"], "Audit selesai")

        formatted = self.publisher.format_dashboard_wikitext(
            index_title="Pengguna:Baloo_Official/Bak_pasir/Draf/2026-09",
            rows=trans_rows,
            year=2026,
            month=9,
            review_rows=review_rows,
        )
        self.assertIn("== Draf September 2026 ==", formatted)
        self.assertIn("=== Terjemahan Baru ===", formatted)
        self.assertIn("=== Perbaikan Artikel ===", formatted)
        self.assertIn("* '''Terjemahan baru:''' 2", formatted)
        self.assertIn("* '''Perbaikan artikel:''' 1", formatted)
        self.assertIn("* '''Sudah tayang:''' 1", formatted)
        self.assertIn("[[Istimewa:IndeksAwalan/Pengguna:Baloo_Official/Bak_pasir/Draf/2026-09/|Lihat]]", formatted)

    def test_update_monthly_dashboard_dry_run_append_and_update(self):
        # 1. First item (translation)
        res1 = self.publisher.update_monthly_dashboard(
            username="Baloo Official",
            article_title="The Runner (2026 film)",
            topic="Film",
            status="Draf aktif",
            slug="2026-09",
            dry_run=True,
        )
        self.assertTrue(res1["success"])
        self.assertEqual(res1["total_drafts"], 1)
        self.assertEqual(res1["translation_drafts"], 1)
        self.assertEqual(res1["review_drafts"], 0)
        self.assertIn("The Runner (2026 film)", res1["wikitext"])
        self.assertIn("Draf aktif", res1["wikitext"])
        self.assertIn("* '''Terjemahan baru:''' 1", res1["wikitext"])
        self.assertIn("* '''Perbaikan artikel:''' 0", res1["wikitext"])
        self.assertIn("* '''Sudah tayang:''' 0", res1["wikitext"])

        # 2. Second item (review)
        res2 = self.publisher.update_monthly_dashboard(
            username="Baloo Official",
            article_title="Anna Filosofova",
            activity_type="review",
            requester="Glorious Engine",
            status="Audit selesai",
            slug="2026-09",
            dry_run=True,
        )
        self.assertTrue(res2["success"])
        self.assertEqual(res2["review_drafts"], 1)
        self.assertIn("Anna Filosofova", res2["wikitext"])
        self.assertIn("Glorious Engine", res2["wikitext"])
        self.assertIn("* '''Perbaikan artikel:''' 1", res2["wikitext"])

    def test_update_monthly_dashboard_live_flow_with_mocks(self):
        mock_get_content = MagicMock(return_value="""== Buku Log & Portofolio Penerjemahan (September 2026) ==
=== 1. Draf Terjemahan Baru ===
{| class="wikitable sortable" style="width:100%"
|-
! No
! Judul Draf
! Topik
! Status
! Tanggal
! Artikel Resmi
|-
| 1 || [[Pengguna:Baloo_Official/Bak_pasir/Draf/2026-09/The_Runner|The Runner]] || Film || Draf aktif || 01 September 2026 || -
|}
""")
        with patch.object(self.publisher, "get_page_content", mock_get_content):
            with patch.object(self.publisher, "_authenticate_bot_password", return_value=(True, None)):
                with patch.object(self.publisher, "_get_csrf_token", return_value=("csrf_test", None)):
                    with patch.object(self.publisher, "_edit_page", return_value={"success": True, "edit": {"pageid": 100, "newrevid": 200}}) as mock_edit:
                        # Update status of existing row "The Runner"
                        res = self.publisher.update_monthly_dashboard(
                            username="Baloo Official",
                            article_title="The Runner",
                            status="Tayang resmi",
                            mainspace_link="The Runner (film 2026)",
                            bot_password="secret_password",
                            slug="2026-09",
                            dry_run=False,
                        )
                        self.assertTrue(res["success"])
                        self.assertEqual(res["total_drafts"], 1)
                        self.assertEqual(res["pageid"], 100)

                        mock_edit.assert_called_once()
                        _, kwargs = mock_edit.call_args
                        self.assertIn("The Runner", kwargs["text"])
                        self.assertIn("Tayang resmi", kwargs["text"])
                        self.assertIn("[[The Runner (film 2026)]]", kwargs["text"])
                        self.assertIn("* '''Sudah tayang:''' 1", kwargs["text"])
                        self.assertEqual(kwargs["summary"], DEFAULT_DASHBOARD_SUMMARY)
    def test_mainspace_publisher_updates_dashboard_on_move(self):
        mainspace_pub = MainspacePublisher(sandbox_publisher=self.publisher)
        with patch.object(mainspace_pub, "_authenticate_bot_password", return_value=(True, None)):
            with patch.object(mainspace_pub, "_get_csrf_token", return_value=("csrf_test", None)):
                with patch.object(mainspace_pub, "_make_request", return_value=({"move": {"from": "Pengguna:Baloo_Official/Bak_pasir/Draf/2026-09/Kevin_Macdonald", "to": "Kevin Macdonald"}}, None)):
                    with patch.object(self.publisher, "update_monthly_dashboard", return_value={"success": True, "total_drafts": 1}) as mock_dash:
                        res = mainspace_pub.move_draft_to_mainspace(
                            username="Baloo Official",
                            bot_password="bot_pwd",
                            sandbox_source="Pengguna:Baloo_Official/Bak_pasir/Draf/2026-09/Kevin_Macdonald",
                            mainspace_target="Kevin Macdonald",
                            topic="Biografi / Sutradara",
                            dry_run=False,
                        )
                        self.assertTrue(res["success"])
                        mock_dash.assert_called_once()
                        call_kwargs = mock_dash.call_args[1]
                        self.assertEqual(call_kwargs["article_title"], "Kevin Macdonald")
                        self.assertEqual(call_kwargs["status"], "Tayang resmi")
                        self.assertEqual(call_kwargs["mainspace_link"], "[[Kevin Macdonald]]")
                        self.assertEqual(call_kwargs["topic"], "Biografi / Sutradara")


if __name__ == "__main__":
    unittest.main()
