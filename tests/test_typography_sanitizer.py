"""
Unit tests for Wikipedia ID Typography & Reference Date Standardization (typography_sanitizer.py).
"""
from pathlib import Path
import tempfile
import unittest
from wiki_translator.typography_sanitizer import (
    TypographySanitizer,
    default_typography_sanitizer,
)
from wiki_translator.cli import WikiTranslatorCLI
from wiki_translator.wiki_client import WikiSection


class TestTypographySanitizerPillars(unittest.TestCase):
    def setUp(self):
        self.sanitizer = TypographySanitizer()

    # ----------------------------------------------------
    # Pillar 1: Typography & Orthography Linter Tests
    # ----------------------------------------------------
    def test_en_dash_conversion_years_and_pages(self):
        # Year ranges
        text = "Perang Dunia II terjadi pada rentang tahun 1939-1945 di Eropa."
        result = self.sanitizer.sanitize_wikitext(text)
        self.assertIn("1939–1945", result)

        # Short year ranges
        text_short = "Musim kompetisi 2023-24 berlangsung sengit."
        result_short = self.sanitizer.sanitize_wikitext(text_short)
        self.assertIn("2023–24", result_short)

        # Decade with -an must remain hyphen
        text_decade = "Musik pada era 1990-an sangat populer."
        result_decade = self.sanitizer.sanitize_wikitext(text_decade)
        self.assertIn("1990-an", result_decade)

        # Page ranges in prose
        text_page = "Lihat referensi pada hlm. 45-50 dan hal. 12-18."
        result_page = self.sanitizer.sanitize_wikitext(text_page)
        self.assertIn("hlm. 45–50", result_page)
        self.assertIn("hal. 12–18", result_page)

        # Page ranges in citation templates
        cite_page = "{{cite book |title=Buku Sejarah |pages=105-120 |year=2000}}"
        result_cite = self.sanitizer.sanitize_wikitext(cite_page)
        self.assertIn("|pages=105–120", result_cite)

    def test_quotation_mark_normalization(self):
        text = 'Dia berkata “Ini adalah kutipan luar biasa” dan ‘kutipan tunggal’.'
        result = self.sanitizer.sanitize_wikitext(text)
        self.assertIn('"Ini adalah kutipan luar biasa"', result)
        self.assertIn("'kutipan tunggal'", result)

    def test_decimal_and_thousand_separators(self):
        # Indonesian decimals with units
        text = "Film ini meraup pendapatan sebesar US$ 4.5 juta dan ditonton oleh 2.5 juta orang dengan keuntungan 15.8%."
        result = self.sanitizer.sanitize_wikitext(text)
        self.assertIn("US$ 4,5 juta", result)
        self.assertIn("2,5 juta", result)
        self.assertIn("15,8%", result)

        # Math and code tags must NOT be corrupted
        math_text = "<math>3.14159 + x</math> dan <code>const rate = 0.75;</code>"
        result_math = self.sanitizer.sanitize_wikitext(math_text)
        self.assertIn("<math>3.14159 + x</math>", result_math)
        self.assertIn("<code>const rate = 0.75;</code>", result_math)

    def test_em_dash_normalization(self):
        # Parenthetical em-dash
        text1 = "Sutradara film tersebut — seorang sineas berpengalaman — memulai proses syuting di London."
        res1 = self.sanitizer.sanitize_wikitext(text1)
        self.assertNotIn("—", res1)
        self.assertIn("Sutradara film tersebut, seorang sineas berpengalaman, memulai proses syuting di London.", res1)

        # Connecting em-dash
        text2 = "Film ini menuai pujian — ulasannya sangat positif."
        res2 = self.sanitizer.sanitize_wikitext(text2)
        self.assertNotIn("—", res2)
        self.assertIn("Film ini menuai pujian, ulasannya sangat positif.", res2)

        # Protected blocks (math, code, ref) untouched
        text3 = "Teks narasi — ada ref.<ref>Catatan — sumber rujukan</ref>"
        res3 = self.sanitizer.sanitize_wikitext(text3)
        self.assertIn("<ref>Catatan — sumber rujukan</ref>", res3)

    def test_semicolon_normalization(self):
        # Semicolon followed by conjunction
        text1 = "Produksi film dimulai pada musim semi; namun jadwal syuting tertunda."
        res1 = self.sanitizer.sanitize_wikitext(text1)
        self.assertNotIn(";", res1)
        self.assertIn("Produksi film dimulai pada musim semi, namun jadwal syuting tertunda.", res1)

        # Semicolon followed by lowercase letter
        text2 = "Aktris tersebut tiba di lokasi; para kru bersiap."
        res2 = self.sanitizer.sanitize_wikitext(text2)
        self.assertNotIn(";", res2)
        self.assertIn("Aktris tersebut tiba di lokasi, dan para kru bersiap.", res2)

        # Semicolon followed by uppercase letter
        text3 = "Syuting selesai pada bulan Mei; Penayangan perdana dijadwalkan tahun depan."
        res3 = self.sanitizer.sanitize_wikitext(text3)
        self.assertNotIn(";", res3)
        self.assertIn("Syuting selesai pada bulan Mei. Penayangan perdana dijadwalkan tahun depan.", res3)

    def test_quotation_punctuation_order(self):
        # EYD V: punctuation outside quotes
        text1 = 'Ia membintangi film "The Runner," yang diproduksi oleh Amazon.'
        res1 = self.sanitizer.sanitize_wikitext(text1)
        self.assertIn('"The Runner",', res1)

        text2 = 'Judul proyek ini adalah "The Runner."'
        res2 = self.sanitizer.sanitize_wikitext(text2)
        self.assertIn('"The Runner".', res2)

        # Wikitext italics
        text3 = "Proyek ini berjudul ''The Runner.'' Sutradara mengumumkan rilis."
        res3 = self.sanitizer.sanitize_wikitext(text3)
        self.assertIn("''The Runner''.", res3)

    def test_compound_hyphens_and_bound_forms(self):
        # pro-Palestina -> pendukung Palestina
        text1 = "Delapan pengunjuk rasa pro-Palestina ditangkap di London."
        res1 = self.sanitizer.sanitize_wikitext(text1)
        self.assertNotIn("pro-Palestina", res1)
        self.assertIn("pengunjuk rasa pendukung Palestina", res1)

        # Bound forms joined without hyphen before lowercase
        text2 = "Universitas ini membuka program pasca-sarjana dan non-blok antarkota multi-nasional."
        res2 = self.sanitizer.sanitize_wikitext(text2)
        self.assertIn("pascasarjana", res2)
        self.assertIn("nonblok", res2)
        self.assertIn("multinasional", res2)
    # Pillar 2: Citation Date Localizer Tests
    # ----------------------------------------------------
    def test_citation_date_localization_english_months(self):
        cite_en = (
            "{{cite web |url=https://example.com |title=News "
            "|date=November 11, 2024 |access-date=March 5, 2025 |archive-date=January 1, 2025}}"
        )
        result = self.sanitizer.sanitize_wikitext(cite_en)
        self.assertIn("|date=11 November 2024", result)
        self.assertIn("|access-date=5 Maret 2025", result)
        self.assertIn("|archive-date=1 Januari 2025", result)

    def test_citation_date_formats(self):
        # DD Month YYYY English -> DD Bulan YYYY
        cite1 = "{{cite news |title=Test |date=14 February 2023 |accessdate=23 August 2024}}"
        res1 = self.sanitizer.sanitize_wikitext(cite1)
        self.assertIn("|date=14 Februari 2023", res1)
        self.assertIn("|accessdate=23 Agustus 2024", res1)

        # Month YYYY
        cite2 = "{{cite journal |title=Paper |date=October 2021}}"
        res2 = self.sanitizer.sanitize_wikitext(cite2)
        self.assertIn("|date=Oktober 2021", res2)

        # ISO format untouched
        cite_iso = "{{cite web |date=2024-11-11 |access-date=2025-01-05}}"
        res_iso = self.sanitizer.sanitize_wikitext(cite_iso)
        self.assertIn("|date=2024-11-11", res_iso)
        self.assertIn("|access-date=2025-01-05", res_iso)

    # ----------------------------------------------------
    # Pillar 3: Heading Sentence-Case Normalizer Tests
    # ----------------------------------------------------
    def test_heading_sentence_case_wikitext(self):
        wikitext = """== Produksi Dan Perilisan ==
Konten produksi.
=== Pemeran Dan Karakter ===
Daftar pemeran.
== Tanggapan Kritis ==
Ulasan film.
== Penghargaan Dan Nominasi ==
Penghargaan."""
        result = self.sanitizer.sanitize_wikitext(wikitext)
        self.assertIn("== Produksi dan perilisan ==", result)
        self.assertIn("=== Pemeran dan karakter ===", result)
        self.assertIn("== Tanggapan kritis ==", result)
        self.assertIn("== Penghargaan dan nominasi ==", result)

    def test_heading_sentence_case_markdown(self):
        md = """# The Runner (Film 2026)
## Produksi Dan Perilisan
## Tanggapan Kritis
### Media Rumah Dan Distribusi"""
        result = self.sanitizer.sanitize_markdown(md)
        self.assertIn("# The runner (film 2026)", result)
        self.assertIn("## Produksi dan perilisan", result)
        self.assertIn("## Tanggapan kritis", result)
        self.assertIn("### Media rumah dan distribusi", result)

    def test_heading_preserves_acronyms_and_numerals(self):
        headings = """== Sejarah NASA Di Indonesia ==
=== Perang Dunia II Di Pasifik ===
== Rilis DVD Dan Blu-Ray =="""
        result = self.sanitizer.sanitize_wikitext(headings)
        self.assertIn("== Sejarah NASA di Indonesia ==", result)
        self.assertIn("=== Perang Dunia II di Pasifik ===", result)
        self.assertIn("== Rilis DVD dan Blu-ray ==", result)



class TestCLITypographyIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.out_dir = Path(self.temp_dir.name) / "output"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_cli_save_output_with_typography_sanitization(self):
        cli = WikiTranslatorCLI(
            output_dir=str(self.out_dir),
            enable_map_links=False,
            enable_typography_sanitizer=True,
            enable_cache=False,
        )
        sections = [
            WikiSection(
                index=0,
                title="Lead",
                level=1,
                header_raw="",
                content="== Produksi Dan Perilisan ==\nFilm ini berdurasi tahun 1939-1945 dan meraup US$ 4.5 juta. {{cite web |title=Test |date=November 11, 2024}}",
                word_count=20,
                char_count=120,
                translated_content="== Produksi Dan Perilisan ==\nFilm ini berdurasi tahun 1939-1945 dan meraup US$ 4.5 juta. {{cite web |title=Test |date=November 11, 2024}}",
            )
        ]
        wikitext_file, md_file, talk_file = cli._save_output("runner_test", "The Runner (Film 2026)", sections)
        self.assertTrue(wikitext_file.exists())
        self.assertTrue(md_file.exists())
        self.assertTrue(talk_file.exists())
        content = wikitext_file.read_text(encoding="utf-8")
        self.assertIn("== Produksi dan perilisan ==", content)
        self.assertIn("1939–1945", content)
        self.assertIn("4,5 juta", content)
        self.assertIn("|date=11 November 2024", content)

if __name__ == "__main__":
    unittest.main()
