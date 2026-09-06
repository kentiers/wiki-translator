"""
Unit tests for MediaManager (wiki_translator/media_manager.py).
"""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from wiki_translator.media_manager import (
    MediaManager,
    MediaAuditItem,
    default_media_manager,
)


class TestMediaManager(unittest.TestCase):
    def setUp(self):
        self.manager = MediaManager()

    def test_clean_filename(self):
        self.assertEqual(
            self.manager.clean_filename("File:Example Poster.jpg"),
            "Example_Poster.jpg",
        )
        self.assertEqual(
            self.manager.clean_filename("Berkas:Example_Poster.jpg"),
            "Example_Poster.jpg",
        )
        self.assertEqual(
            self.manager.clean_filename("[[File:Test.png|thumb|right|Caption]]"),
            "Test.png",
        )
        self.assertEqual(
            self.manager.clean_filename("Image:Album_cover.jpeg"),
            "Album_cover.jpeg",
        )

    def test_extract_media_references(self):
        wikitext = (
            "{{Infobox film\n"
            "| name = Oppenheimer\n"
            "| image = Oppenheimer (film) poster.jpg\n"
            "| alt = Poster\n"
            "}}\n"
            "Beberapa teks di sini.\n"
            "[[File:Oppenheimer filming.jpg|thumb|Proses syuting]]\n"
            "[[Berkas:Director_photo.png|right]]\n"
        )
        refs = self.manager.extract_media_references(wikitext)
        self.assertEqual(len(refs), 3)
        names = [r[0] for r in refs]
        self.assertIn("Oppenheimer_(film)_poster.jpg", names)
        self.assertIn("Oppenheimer_filming.jpg", names)
        self.assertIn("Director_photo.png", names)

    def test_reconcile_media_fidelity(self):
        en_wiki = (
            "{{Infobox film | image = Poster.jpg }}\n"
            "[[File:Scene1.png|thumb|Scene]]\n"
            "[[File:Scene2.png|thumb|Scene 2]]\n"
        )
        id_wiki = (
            "{{Infobox film | image = Poster.jpg }}\n"
            "[[File:Scene1.png|thumb|Adegan]]\n"
        )
        with patch.object(self.manager, "check_commons_existence", return_value=True), \
             patch.object(self.manager, "check_id_wiki_existence", return_value=True), \
             patch.object(self.manager, "check_en_wiki_existence", return_value=(False, None)):
            res = self.manager.reconcile_media_fidelity(en_wiki, id_wiki)
            self.assertEqual(res["source_count"], 3)
            self.assertEqual(res["target_count"], 2)
            self.assertEqual(res["missing_count"], 1)
            self.assertEqual(res["missing_items"][0]["filename"], "Scene2.png")
            self.assertTrue(res["missing_items"][0]["is_commons"])

    def test_check_id_wiki_existence_shared_commons(self):
        mock_response = {
            "query": {
                "pages": {
                    "-1": {
                        "missing": "",
                        "imagerepository": "shared",
                        "imageinfo": [{"url": "https://upload.wikimedia.org/commons/test.jpg"}]
                    }
                }
            }
        }
        with patch.object(self.manager, "_query_api", return_value=(mock_response, None)):
            self.assertTrue(self.manager.check_id_wiki_existence("test.jpg"))

    def test_generate_fair_use_rationale(self):
        rationale = self.manager.generate_fair_use_rationale(
            title="Inception",
            id_title="Inception (film)",
            filename="Inception_poster.jpg",
            media_type="film",
        )
        self.assertIn("{{Dari|en|Inception_poster.jpg}}", rationale)
        self.assertIn("== Ringkasan ==", rationale)
        self.assertIn("== Lisensi ==", rationale)
        self.assertIn("{{Non-free use rationale", rationale)
        self.assertIn("Description = Poster resmi untuk film/karya Inception", rationale)
        self.assertIn("Source = [[:en:File:Inception_poster.jpg]]", rationale)
        self.assertIn("Article = Inception (film)", rationale)
        self.assertIn("{{Poster film}}", rationale)

        # Test album rationale
        album_rationale = self.manager.generate_fair_use_rationale(
            title="Thriller",
            id_title="Thriller (album)",
            filename="Michael_Jackson_Thriller.jpg",
            media_type="album",
        )
        self.assertIn("{{Dari|en|Michael_Jackson_Thriller.jpg}}", album_rationale)
        self.assertIn("{{Sampul album}}", album_rationale)
        self.assertIn("Sampul album/lagu resmi untuk karya Thriller", album_rationale)

        # Test logo rationale
        logo_rationale = self.manager.generate_fair_use_rationale(
            title="OpenAI",
            id_title="OpenAI",
            filename="OpenAI_Logo.svg",
            media_type="logo",
        )
        self.assertIn("{{Dari|en|OpenAI_Logo.svg}}", logo_rationale)
        self.assertIn("{{Logo nonbebas}}", logo_rationale)
    @patch.object(MediaManager, "_query_api")
    def test_check_commons_existence(self, mock_query):
        # Mock commons exists
        mock_query.return_value = (
            {"query": {"pages": {"12345": {"pageid": 12345, "title": "File:Test.jpg"}}}},
            None,
        )
        self.assertTrue(self.manager.check_commons_existence("Test.jpg"))

        # Mock commons missing
        mock_query.return_value = (
            {"query": {"pages": {"-1": {"ns": 6, "title": "File:Missing.jpg", "missing": ""}}}},
            None,
        )
        self.assertFalse(self.manager.check_commons_existence("Missing.jpg"))

    @patch.object(MediaManager, "_query_api")
    def test_check_id_wiki_existence(self, mock_query):
        mock_query.return_value = (
            {"query": {"pages": {"54321": {"pageid": 54321, "title": "File:Existing.jpg"}}}},
            None,
        )
        self.assertTrue(self.manager.check_id_wiki_existence("Existing.jpg"))

    @patch.object(MediaManager, "_query_api")
    def test_audit_article_media_commons_vs_local(self, mock_query):
        wikitext = (
            "{{Infobox film\n"
            "| image = Nonfree_Poster.jpg\n"
            "}}\n"
            "[[File:Free_Photo.jpg|thumb|Pemandangan]]\n"
        )

        def side_effect(api_url, params, method="GET", **kwargs):
            title = params.get("titles", "")
            if "Free_Photo.jpg" in title:
                if api_url == self.manager.commons_api:
                    return ({"query": {"pages": {"101": {"title": "File:Free_Photo.jpg"}}}}, None)
            elif "Nonfree_Poster.jpg" in title:
                if api_url == self.manager.commons_api:
                    return ({"query": {"pages": {"-1": {"missing": ""}}}}, None)
                elif api_url == self.manager.id_wiki_api:
                    return ({"query": {"pages": {"-1": {"missing": ""}}}}, None)
                elif api_url == self.manager.en_wiki_api:
                    return (
                        {
                            "query": {
                                "pages": {
                                    "202": {
                                        "title": "File:Nonfree_Poster.jpg",
                                        "imageinfo": [{"url": "https://upload.wikimedia.org/poster.jpg"}],
                                    }
                                }
                            }
                        },
                        None,
                    )
            return ({"query": {"pages": {"-1": {"missing": ""}}}}, None)

        mock_query.side_effect = side_effect

        items = self.manager.audit_article_media(
            wikitext=wikitext,
            en_title="Test Movie",
            id_title="Test Movie (film)",
            default_media_type="film",
        )

        self.assertEqual(len(items), 2)
        poster_item = next(i for i in items if i.cleaned_filename == "Nonfree_Poster.jpg")
        self.assertEqual(poster_item.status, "local_non_free")
        self.assertIsNotNone(poster_item.rationale)
        self.assertIn("{{Poster film}}", poster_item.rationale)

        photo_item = next(i for i in items if i.cleaned_filename == "Free_Photo.jpg")
        self.assertEqual(photo_item.status, "commons_shared")
        self.assertTrue(photo_item.is_commons)

    @patch("urllib.request.urlopen")
    @patch.object(MediaManager, "check_en_wiki_existence")
    def test_download_en_media(self, mock_check, mock_urlopen):
        mock_check.return_value = (True, "https://upload.wikimedia.org/test.jpg")
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"FAKE_IMAGE_BYTES"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with tempfile.TemporaryDirectory() as tmpdir:
            out = self.manager.download_en_media("test.jpg", Path(tmpdir))
            self.assertIsNotNone(out)
            self.assertTrue(out.is_file())
            self.assertEqual(out.read_bytes(), b"FAKE_IMAGE_BYTES")

    @patch.object(MediaManager, "_get_csrf_token")
    @patch.object(MediaManager, "_authenticate_bot_password")
    @patch.object(MediaManager, "_query_api")
    def test_upload_to_id_wiki(self, mock_query, mock_auth, mock_token):
        mock_auth.return_value = (True, None)
        mock_token.return_value = ("test-csrf-token", None)
        mock_query.return_value = ({"upload": {"result": "Success", "filename": "Poster.jpg"}}, None)

        with tempfile.TemporaryDirectory() as tmpdir:
            fpath = Path(tmpdir) / "Poster.jpg"
            fpath.write_bytes(b"DATA")

            res = self.manager.upload_to_id_wiki(
                filename="Poster.jpg",
                file_path=fpath,
                wikitext_description="{{Alasan}}",
                username="BotUser@test",
                bot_password="botpassword123",
            )
            self.assertTrue(res.get("success"))
            self.assertEqual(res.get("upload", {}).get("result"), "Success")


if __name__ == "__main__":
    unittest.main()
