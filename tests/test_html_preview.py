"""
Unit tests for Visual HTML Browser Preview generator (wiki_translator/html_preview.py).
"""

from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from wiki_translator.html_preview import (
    HTMLPreviewGenerator,
    default_preview_generator,
)


class TestHTMLPreviewGenerator(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.generator = HTMLPreviewGenerator()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_offline_render_basic_headers_and_typography(self):
        wikitext = (
            "== Sejarah ==\n"
            "Ini adalah paragraf dengan '''teks tebal''' dan ''teks miring''.\n\n"
            "=== Subbagian ===\n"
            "'''''Tebal dan miring''''' juga didukung."
        )
        html = self.generator.render_html("Uji Coba", wikitext, try_api_parse=False)

        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("Uji Coba - Wikipedia Bahasa Indonesia", html)
        self.assertIn("Pratinjau Draf Terjemahan Wikipedia Bahasa Indonesia", html)
        self.assertIn("<h2>Sejarah</h2>", html)
        self.assertIn("<h3>Subbagian</h3>", html)
        self.assertIn("<strong>teks tebal</strong>", html)
        self.assertIn("<em>teks miring</em>", html)
        self.assertIn("<strong><em>Tebal dan miring</em></strong>", html)

    def test_offline_render_lists(self):
        wikitext = (
            "* Item Satu\n"
            "* Item Dua\n"
            "# Urutan Pertama\n"
            "# Urutan Kedua"
        )
        html = self.generator.render_html("Daftar", wikitext, try_api_parse=False)

        self.assertIn("<ul>", html)
        self.assertIn("<li>Item Satu</li>", html)
        self.assertIn("<li>Item Dua</li>", html)
        self.assertIn("</ul>", html)
        self.assertIn("<ol>", html)
        self.assertIn("<li>Urutan Pertama</li>", html)
        self.assertIn("<li>Urutan Kedua</li>", html)
        self.assertIn("</ol>", html)

    def test_offline_render_wikilinks_and_external_links(self):
        wikitext = (
            "Lihat artikel [[Fisika kuantum|ilmu kuantum]] dan [[Indonesia]].\n"
            "Sumber eksternal: [https://example.com Situs Resmi]."
        )
        html = self.generator.render_html("Tautan", wikitext, try_api_parse=False)

        self.assertIn('<a href="https://id.wikipedia.org/wiki/Fisika_kuantum" title="Fisika kuantum">ilmu kuantum</a>', html)
        self.assertIn('<a href="https://id.wikipedia.org/wiki/Indonesia" title="Indonesia">Indonesia</a>', html)
        self.assertIn('<a href="https://example.com" class="external" target="_blank" rel="noopener">Situs Resmi</a>', html)

    def test_offline_render_nested_wikilink_in_image_caption(self):
        # Image caption ending with nested wikilink (]]]] brackets)
        wikitext = "[[Berkas:Canal.png|jmpl|kanan|Pembangunan [[Kanal Besar Stavropol]]]]\nTeks paragraf berikutnya."
        html = self.generator.render_html("Uji Gambar", wikitext, try_api_parse=False)

        self.assertIn('<a href="https://id.wikipedia.org/wiki/Kanal Besar Stavropol">Kanal Besar Stavropol</a>', html)
        self.assertNotIn("</div>]</div>", html)
        self.assertNotIn("</div>]", html)
        self.assertNotIn("]\n<p>Teks", html)

    def test_offline_render_multi_language_ill_badges(self):
        # Template with both English and Russian targets prioritizes 'en' and renders strictly single badge
        wikitext = "Tokoh {{ill|Leonid Yefremov|en|Leonid Yefremov|ru|Ефремов, Леонид Николаевич}} hadir dalam rapat."
        html = self.generator.render_html("Uji Multi-ill", wikitext, try_api_parse=False)

        self.assertIn('<a href="https://en.wikipedia.org/wiki/Leonid_Yefremov" class="interlanguage-link-badge ext-iw" target="_blank" rel="noopener" title="Lihat artikel \'Leonid Yefremov\' di Wikipedia bahasa en">(en)</a>', html)
        self.assertNotIn('(ru)</a>', html)

        # Fallback to foreign language only when 'en' is absent
        wikitext_ru = "Tokoh {{ill|Leonid Yefremov|ru|Ефремов, Леонид Николаевич}} hadir dalam rapat."
        html_ru = self.generator.render_html("Uji Fallback ill", wikitext_ru, try_api_parse=False)
        self.assertIn('(ru)</a>', html_ru)
    def test_offline_render_hatnote_redlinks(self):
        # Hatnotes linking to uncreated articles must receive class="new"
        wikitext = "{{Utama|Masa jabatan Mikhail Gorbachev sebagai Sekretaris Jenderal}}"
        html = self.generator.render_html("Uji Hatnote", wikitext, try_api_parse=False)

        self.assertIn('class="hatnote navigation-not-searchable">Artikel utama:', html)
        self.assertIn('class="new"', html)
        self.assertIn('(halaman belum dibuat)', html)

    def test_offline_render_sidebar_template_does_not_leak_parameter_text(self):
        # Sidebar templates with section parameters must not leak parameter as body text
        wikitext = "== Kehidupan pasca-Soviet ==\n{{Social democracy sidebar|people}}\n=== Tahun-tahun awal ==="
        html = self.generator.render_html("Uji Sidebar", wikitext, try_api_parse=False)

        self.assertNotIn("<p>people</p>", html)
        self.assertNotIn("people", html)

    def test_offline_render_references_and_citations(self):
        wikitext = (
            "Pernyataan ilmiah penting.<ref>{{cite web|title=Kuantum Hari Ini|url=https://quantum.org}}</ref>\n"
            "Fakta sejarah lainnya.<ref>Buku Referensi Sejarah, hlm. 42.</ref>\n\n"
            "== Referensi ==\n"
            "{{reflist}}"
        )
        html = self.generator.render_html("Rujukan", wikitext, try_api_parse=False)

        self.assertIn('<sup class="reference" id="cite_ref-1"><a href="#cite_note-1">[1]</a></sup>', html)
        self.assertIn('<sup class="reference" id="cite_ref-2"><a href="#cite_note-2">[2]</a></sup>', html)
        self.assertIn('<ol class="references">', html)
        self.assertIn('id="cite_note-1"', html)
        self.assertIn('Kuantum Hari Ini', html)
        self.assertIn('Buku Referensi Sejarah', html)

    def test_offline_render_infobox(self):
        wikitext = (
            "{{Infobox film\n"
            "| nama = The Matrix\n"
            "| sutradara = The Wachowskis\n"
            "| tahun = 1999\n"
            "}}\n"
            "The Matrix adalah film fiksi ilmiah ternama."
        )
        html = self.generator.render_html("The Matrix", wikitext, try_api_parse=False)

        self.assertIn('<table class="infobox">', html)
        self.assertIn('<th colspan="2" class="infobox-title">The Matrix</th>', html)
        self.assertIn("<th>Sutradara</th><td>The Wachowskis</td>", html)
        self.assertIn("<th>Tahun</th><td>1999</td>", html)
        self.assertIn("The Matrix adalah film fiksi ilmiah ternama.", html)

    def test_api_parse_success(self):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__.return_value = mock_response
        mock_response.read.return_value = b'{"parse": {"title": "Uji", "text": {"*": "<p>Teks parse Wikipedia resmi</p>"}}}'
        with patch("urllib.request.urlopen", return_value=mock_response):
            html = self.generator.render_html("Uji", "== Teks ==", try_api_parse=True)
            self.assertIn("Teks parse Wikipedia resmi", html)
            self.assertIn("Online MediaWiki Parse", html)

    def test_api_parse_failure_falls_back_to_offline(self):
        with patch("urllib.request.urlopen", side_effect=Exception("Timeout")):
            html = self.generator.render_html("Fallback", "== Bab Fallback ==", try_api_parse=True)
            self.assertIn("<h2>Bab Fallback</h2>", html)
            self.assertIn("Offline Fallback Renderer", html)

    def test_save_and_open_preview(self):
        out_file = self.generator.save_and_open_preview(
            title="Quantum Computing (2026)",
            wikitext="== Bab 1 ==\nKonten pratinjau.",
            output_dir=str(self.tmp_dir),
            auto_open=False,
            try_api_parse=False,
        )
        self.assertTrue(out_file.exists())
        self.assertEqual(out_file.name, "quantum_computing_2026.preview.html")
        content = out_file.read_text(encoding="utf-8")
        self.assertIn("Quantum Computing (2026)", content)
        self.assertIn("<h2>Bab 1</h2>", content)

    def test_save_and_open_preview_with_browser_open(self):
        with patch("webbrowser.open") as mock_open:
            out_file = self.generator.save_and_open_preview(
                title="Buka Browser",
                wikitext="Tes browser.",
                output_dir=str(self.tmp_dir),
                auto_open=True,
                try_api_parse=False,
            )
            self.assertTrue(out_file.exists())
            mock_open.assert_called_once()
            args, _ = mock_open.call_args
            self.assertTrue(args[0].startswith("file:"))

    def test_default_instance_exists(self):
        self.assertIsInstance(default_preview_generator, HTMLPreviewGenerator)


if __name__ == "__main__":
    unittest.main()
