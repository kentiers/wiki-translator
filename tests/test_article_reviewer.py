"""
Unit tests for Translation Quality Auditor & Article Reviewer (wiki_translator/article_reviewer.py).
"""

from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from wiki_translator.article_reviewer import (
    APReviewReport,
    ArticleReviewer,
    ReviewFinding,
    default_article_reviewer,
)


class TestArticleReviewer(unittest.TestCase):
    def setUp(self):
        self.reviewer = ArticleReviewer()
        self.sample_bad_id_wikitext = (
            "{{Infobox person\n"
            "| name = Tokoh Contoh\n"
            "}}\n"
            "'''Tokoh Contoh''' adalah aktivis.\n\n"
            "Perhimpunan tersebut kemudian mengakuisisi gedungnya sendiri dan kontrak besar untuk menyemai pengerjaan dari militer. "
            "Ini menyediakan perumahan dan pekerjaan senbagai penekanan untuk kliennya. "
            "Setelah pernikaahn mereka, ia giat berkunjung ke lahan Filosofov. "
            "Biaya pendidikan menjadi habi. Murid-murid tersbeut berasal dari keluarga aristoktrat.\n\n"
            "Berseberangan dengan gerakan sezaman, triwira tersebut menghimpun stasiun mereka dalam rahmat baik dari kelas atas. "
            "Filosofova menubuhkan spiritualitas dan etika. Usai timbal balik konservatif, ia terisolasi.\n\n"
            "Ia lahir di Saint Petersburg pada 17 Maret 1912, dan pemakamannya dihadiri ribuan pelayat.\n\n"
            "==Referensi==\n"
            "{{Reflist}}\n\n"
            "[[Kategori:Tokoh Rusia]]"
        )
        self.sample_en_wikitext = (
            "'''Example Figure''' was an activist.\n"
            "The society soon acquired its own building and a large contract for sewing work from the military. "
            "Filosofova embodied spirituality and ethics. She died in 1912."
        )

    def test_default_instance(self):
        self.assertIsNotNone(default_article_reviewer)
        self.assertIsInstance(default_article_reviewer, ArticleReviewer)

    def test_audit_detects_fatal_mistranslations(self):
        report = self.reviewer.audit_translation_quality(
            self.sample_bad_id_wikitext, self.sample_en_wikitext, "Tokoh Contoh"
        )
        self.assertGreater(len(report.fatal_errors), 0)

        # Check fatal error descriptions
        fatal_descs = [f.description for f in report.fatal_errors]
        fatal_texts = [f.original_text for f in report.fatal_errors]

        # 1. sewing -> menyemai
        self.assertTrue(any("menyemai" in t for t in fatal_texts))
        # 2. born vs died
        self.assertTrue(any("1912" in t or "pemakaman" in t for t in fatal_texts))

        # Overall score should be heavily penalized (< 70) and verdict set to BELUM LAYAK
        self.assertEqual(report.verdict, "BELUM LAYAK - PERLU PERBAIKAN TOTAL")
        self.assertLess(report.overall_score, 70)

    def test_audit_detects_calques_and_slop(self):
        report = self.reviewer.audit_translation_quality(
            self.sample_bad_id_wikitext, self.sample_en_wikitext, "Tokoh Contoh"
        )
        calque_texts = [c.original_text for c in report.calque_issues]

        self.assertTrue(any("timbal balik" in t for t in calque_texts))
        self.assertTrue(any("menubuhkan" in t for t in calque_texts))
        self.assertTrue(any("rahmat baik" in t for t in calque_texts))

    def test_audit_detects_typos(self):
        report = self.reviewer.audit_translation_quality(
            self.sample_bad_id_wikitext, self.sample_en_wikitext, "Tokoh Contoh"
        )
        typo_words = [t.original_text for t in report.typo_issues]

        self.assertIn("pernikaahn", typo_words)
        self.assertIn("senbagai", typo_words)
        self.assertIn("habi", typo_words)
        self.assertIn("aristoktrat", typo_words)
        self.assertIn("tersbeut", typo_words)

    def test_generate_community_review_text(self):
        report = self.reviewer.audit_translation_quality(
            self.sample_bad_id_wikitext, self.sample_en_wikitext, "Tokoh Contoh"
        )
        review_text = self.reviewer.generate_community_review_text(
            report, reviewer_name="Baloo Official", requester_name="Glorious Engine"
        )

        self.assertIn("Glorious Engine", review_text)
        self.assertIn("Baloo Official", review_text)
        self.assertIn("WP:KAP", review_text)
        self.assertIn("BELUM LAYAK", review_text)
        self.assertIn("menyemai", review_text)
        self.assertIn("17 Maret 1912", review_text)

    def test_generate_polished_wikitext_fixes_errors(self):
        bad_text_with_templates = (
            "{{Kotak pemberitahuan|teks=Contoh}}\n"
            "<!-- Templat belum tersedia di id.wiki: {{Deskripsi singkat|Tokoh Rusia}} -->\n"
            "{{Artikel pilihan}}\n"
            "{{Featured article}}\n"
            + self.sample_bad_id_wikitext
        )
        # In unit test, test offline / rule-based cleaning deterministically
        with patch.object(self.reviewer, "_get_gemini_client", return_value=None):
            polished = self.reviewer.generate_polished_wikitext(
                bad_text_with_templates, self.sample_en_wikitext
            )
        # Templates that must be stripped cleanly
        self.assertNotIn("Artikel pilihan", polished)
        self.assertNotIn("Featured article", polished)
        self.assertNotIn("Deskripsi singkat", polished)

        # Fatal errors and exonyms must be fixed
        self.assertNotIn("menyemai pengerjaan", polished)
        self.assertNotIn("Ia lahir di Saint Petersburg", polished)
        self.assertIn("Ia wafat di Sankt-Peterburg pada 17 Maret 1912, dan pemakamannya", polished)
        self.assertIn("Sankt-Peterburg", polished)
        self.assertNotIn("Saint Petersburg", polished)
        self.assertNotIn("timbal balik konservatif", polished)
        self.assertNotIn("menubuhkan spiritualitas", polished)
        self.assertNotIn("menghimpun stasiun mereka dalam rahmat baik", polished)

        # Typos must be fixed
        self.assertNotIn("pernikaahn", polished)
        self.assertNotIn("senbagai", polished)
        self.assertNotIn("habi.", polished)
        self.assertNotIn("aristoktrat", polished)
        self.assertNotIn("tersbeut", polished)

        # Correct replacements should be present
        self.assertIn("pernikahan", polished)
        self.assertIn("sebagai", polished)
        self.assertIn("aristokrat", polished)
        self.assertIn("tersebut", polished)

    def test_generate_polished_wikitext_fixes_accessible_prose_and_blue_links(self):
        sample_text = (
            "Awalnya menaruh perhatian pada penderitaan para [[Perhambaan di Rusia|hamba tani]]. "
            "Sekembalinya ke Rusia, ia melanjutkan kegiatannya. "
            "Murid-murid tersbeut berasal dari keluarga aristoktrat. "
            "Biaya pendidikan menjadi habi. "
            "Ia mendirikan sekolah campuran di Saint Petersburg."
        )
        polished = self.reviewer.generate_polished_wikitext(sample_text)

        # Geographic exonym standardization
        self.assertNotIn("Saint Petersburg", polished)
        self.assertIn("Sankt-Peterburg", polished)

        # Typo fixes
        self.assertNotIn("tersbeut", polished)
        self.assertIn("tersebut", polished)
        self.assertNotIn("aristoktrat", polished)
        self.assertIn("aristokrat", polished)
        self.assertNotIn(" habi.", polished)
        self.assertIn("habis", polished)

        # Phrasing polish
        self.assertNotIn("Sekembalinya ke Rusia,", polished)
        self.assertIn("Setelah kembali ke Rusia,", polished)
    def test_clean_article_scores_high(self):
        clean_wikitext = (
            "{{Infobox person\n"
            "| name = Tokoh Bersih\n"
            "}}\n"
            "'''Tokoh Bersih''' (5 April 1837 – 17 Maret 1912) adalah seorang aktivis dan reformis sosial Rusia.\n\n"
            "Ia mendirikan perhimpunan amal dan memperjuangkan pendidikan tinggi bagi perempuan di Rusia. "
            "Pemerintah menyetujui program pendidikan tersebut setelah kampanye yang panjang dan terorganisasi.\n\n"
            "Ia wafat di Saint Petersburg pada 17 Maret 1912 dan pemakamannya dihadiri oleh ribuan pelayat.\n\n"
            "== Referensi ==\n"
            "{{Reflist}}\n\n"
            "[[Kategori:Tokoh Rusia]]\n"
            "[[Kategori:Kelahiran 1837]]\n"
            "[[Kategori:Kematian 1912]]"
        )
        report = self.reviewer.audit_translation_quality(clean_wikitext, "", "Tokoh Bersih")
        self.assertEqual(len(report.fatal_errors), 0)
        self.assertEqual(len(report.calque_issues), 0)
        self.assertEqual(len(report.typo_issues), 0)
        self.assertGreaterEqual(report.overall_score, 90)
        self.assertEqual(report.verdict, "SIAP UNTUK AP")

    @patch.object(ArticleReviewer, "publish_polished_to_sandbox")
    @patch.object(ArticleReviewer, "fetch_article_pair")
    def test_audit_and_report_file_creation(self, mock_fetch, mock_publish):
        mock_fetch.return_value = (self.sample_bad_id_wikitext, self.sample_en_wikitext)

        report, review_text, polished = self.reviewer.audit_and_report("Test_Article")
        review_path = Path("output/reviews/Test_Article_review.md")
        polished_path = Path("output/reviews/Test_Article_polished.wikitext")

        self.assertTrue(review_path.exists())
        self.assertTrue(polished_path.exists())

        with open(review_path, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("Glorious Engine", content)

        # Cleanup test files
        if review_path.exists():
            review_path.unlink()
        if polished_path.exists():
            polished_path.unlink()

    @patch.object(ArticleReviewer, "publish_polished_to_sandbox")
    @patch.object(ArticleReviewer, "fetch_article_pair")
    def test_audit_and_report_auto_publishes_when_env_credentials_exist(self, mock_fetch, mock_publish):
        mock_fetch.return_value = (self.sample_bad_id_wikitext, self.sample_en_wikitext)
        with patch.dict("os.environ", {"WIKI_USERNAME": "TestUser", "WIKI_BOT_PASSWORD": "bot_password_123"}):
            self.reviewer.audit_and_report("Test_Auto_Publish")
            mock_publish.assert_called_once()
            call_kwargs = mock_publish.call_args[1]
            self.assertEqual(call_kwargs["id_title"], "Test_Auto_Publish")
            self.assertEqual(call_kwargs["username"], "TestUser")
            self.assertEqual(call_kwargs["bot_password"], "bot_password_123")
            self.assertEqual(call_kwargs["requester"], "Glorious Engine")

        # Clean up output files
        rev_p = Path("output/reviews/Test_Auto_Publish_review.md")
        pol_p = Path("output/reviews/Test_Auto_Publish_polished.wikitext")
        if rev_p.exists():
            rev_p.unlink()
        if pol_p.exists():
            pol_p.unlink()

    def test_publish_polished_to_sandbox_dry_run(self):
        mock_sandbox_pub = MagicMock()
        mock_sandbox_pub.build_sandbox_titles.return_value = (
            "Pengguna:Baloo_Official/Bak_pasir/Draf/2026-09/Anna_Filosofova",
            "Pembicaraan_Pengguna:Baloo_Official/Bak_pasir/Draf/2026-09/Anna_Filosofova",
        )
        mock_sandbox_pub.publish_to_sandbox.return_value = {"success": True, "dry_run": True}
        mock_sandbox_pub.update_monthly_dashboard.return_value = {"success": True, "dry_run": True}

        res = self.reviewer.publish_polished_to_sandbox(
            id_title="Anna Filosofova",
            polished_wikitext="== Biografi ==\nTeks polesan...",
            username="Baloo Official",
            bot_password="dummy_password",
            requester="Glorious Engine",
            slug="2026-09",
            project_slug="Draf",
            sandbox_publisher=mock_sandbox_pub,
            dry_run=True,
        )

        self.assertTrue(res["success"])
        mock_sandbox_pub.publish_to_sandbox.assert_called_once()
        call_kwargs = mock_sandbox_pub.publish_to_sandbox.call_args[1]
        self.assertNotIn("Kotak pemberitahuan", call_kwargs["wikitext"])
        self.assertIn('class="wikitable"', call_kwargs["wikitext"])
        self.assertIn("ℹ️ '''Draf perbaikan''' untuk artikel [[:Anna Filosofova]] atas permintaan [[Pengguna:Glorious Engine|Glorious Engine]].", call_kwargs["wikitext"])
        self.assertIn("Teks polesan...", call_kwargs["wikitext"])
        mock_sandbox_pub.update_monthly_dashboard.assert_called_once()
        dash_kwargs = mock_sandbox_pub.update_monthly_dashboard.call_args[1]
        self.assertEqual(dash_kwargs["activity_type"], "review")
        self.assertEqual(dash_kwargs["requester"], "Glorious Engine")
        self.assertEqual(dash_kwargs["article_title"], "Anna Filosofova")

if __name__ == "__main__":
    unittest.main()
