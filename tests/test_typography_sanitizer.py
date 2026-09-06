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
        result = self.sanitizer.normalize_quotations(text)
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
        res1 = self.sanitizer.normalize_em_dashes(text1)
        self.assertNotIn("—", res1)
        self.assertIn("Sutradara film tersebut, seorang sineas berpengalaman, memulai proses syuting di London.", res1)

        # Connecting em-dash
        text2 = "Film ini menuai pujian — ulasannya sangat positif."
        res2 = self.sanitizer.normalize_em_dashes(text2)
        self.assertNotIn("—", res2)
        self.assertIn("Film ini menuai pujian, ulasannya sangat positif.", res2)

        # Protected blocks (math, code, ref) untouched
        text3 = "Teks narasi — ada ref.<ref>Catatan — sumber rujukan</ref>"
        res3 = self.sanitizer.sanitize_wikitext(text3)
        self.assertIn("<ref>Catatan — sumber rujukan</ref>", res3)

    def test_semicolon_normalization(self):
        # Semicolon followed by conjunction
        text1 = "Produksi film dimulai pada musim semi; namun jadwal syuting tertunda."
        res1 = self.sanitizer.normalize_semicolons(text1)
        self.assertNotIn(";", res1)
        self.assertIn("Produksi film dimulai pada musim semi, namun jadwal syuting tertunda.", res1)

        # Semicolon followed by lowercase letter
        text2 = "Aktris tersebut tiba di lokasi; para kru bersiap."
        res2 = self.sanitizer.normalize_semicolons(text2)
        self.assertNotIn(";", res2)
        self.assertIn("Aktris tersebut tiba di lokasi, dan para kru bersiap.", res2)

        # Semicolon followed by uppercase letter
        text3 = "Syuting selesai pada bulan Mei; Penayangan perdana dijadwalkan tahun depan."
        res3 = self.sanitizer.normalize_semicolons(text3)
        self.assertNotIn(";", res3)
        self.assertIn("Syuting selesai pada bulan Mei. Penayangan perdana dijadwalkan tahun depan.", res3)

    def test_bound_morpheme_normalization(self):
        # EYD V: Bound morphemes followed by lowercase letter must be joined without hyphen
        text1 = "Pasca-kematian Stalin, reformasi pro-kemerdekaan dibendung faksi pasca-peristiwa itu."
        res1 = self.sanitizer.normalize_bound_morphemes(text1)
        self.assertIn("Pascakematian", res1)
        self.assertIn("prokemerdekaan", res1)
        self.assertIn("pascaperistiwa", res1)

        # EYD V: Bound morphemes followed by capitalized proper nouns must retain hyphen
        text2 = "Kelompok pro-Soviet dan faksi anti-Barat menentang kebijakan pasca-Stalin."
        res2 = self.sanitizer.normalize_bound_morphemes(text2)
        self.assertIn("pro-Soviet", res2)
        self.assertIn("anti-Barat", res2)
        self.assertIn("pasca-Stalin", res2)

        # Spaced bound morphemes
        text3 = "Perjanjian non blok diadakan pada era pasca perang."
        res3 = self.sanitizer.normalize_bound_morphemes(text3)
        self.assertIn("nonblok", res3)
        self.assertIn("pascaperang", res3)
    def test_bound_morphemes_before_links(self):
        # Bound morphemes before wikilinks with common nouns must be joined serangkai
        text1 = "terutama pasca-[[Bencana Chernobyl]] tahun 1986."
        res1 = self.sanitizer.normalize_bound_morphemes_before_links(text1)
        self.assertIn("pascabencana [[Bencana Chernobyl|Chernobyl]]", res1)

        text2 = "Pasca-[[Pembubaran Uni Soviet|pembubaran Uni Soviet]] pada tahun 1991."
        res2 = self.sanitizer.normalize_bound_morphemes_before_links(text2)
        self.assertIn("Pascapembubaran [[Pembubaran Uni Soviet|Uni Soviet]]", res2)

        # Proper noun inside wikilink preserves hyphen per EYD V
        text3 = "era pasca-[[Uni Soviet]] dan faksi pro-[[Barat]]."
        res3 = self.sanitizer.normalize_bound_morphemes_before_links(text3)
        self.assertIn("pasca-[[Uni Soviet]]", res3)
        self.assertIn("pro-[[Barat]]", res3)

    def test_common_spelling_mistakes(self):
        # Glued prepositions, particle pun, and standard vocabulary
        text = "Gorbachev tidak menemukan satupun bukti bahwa siapapun didalam partai merubah aktifitas mereka diatas meja praktek."
        res = self.sanitizer.normalize_common_spelling_mistakes(text)
        self.assertIn("satu pun", res)
        self.assertIn("siapa pun", res)
        self.assertIn("di dalam", res)
        self.assertIn("mengubah", res)
        self.assertIn("aktivitas", res)
        self.assertIn("di atas", res)
        self.assertIn("praktik", res)
    def test_stylistic_collocations(self):
        # Khalayak collocations
        text1 = "Gorbachev berbaur dengan khalayak pelayat di Lapangan Merah."
        res1 = self.sanitizer.normalize_stylistic_collocations(text1)
        self.assertIn("kerumunan pelayat", res1)
        self.assertNotIn("khalayak pelayat", res1)

        # Classifier for humans
        text2 = "Ia diakui sebagai salah satu tokoh paling berpengaruh."
        res2 = self.sanitizer.normalize_stylistic_collocations(text2)
        self.assertIn("salah seorang tokoh", res2)

        # Pleonasms
        text3 = "Langkah ini adalah merupakan keputusan penting agar supaya tujuan tercapai demi untuk rakyat."
        res3 = self.sanitizer.normalize_stylistic_collocations(text3)
        self.assertIn("merupakan keputusan", res3)
        self.assertNotIn("adalah merupakan", res3)
        self.assertIn("agar tujuan", res3)
        self.assertNotIn("agar supaya", res3)
        self.assertIn("demi rakyat", res3)
        self.assertNotIn("demi untuk", res3)

        # Month pleonasm and introductory example phrase
        text4 = "Pada bulan Oktober 1980, misalnya, ia mendukung imbauan Moskow."
        res4 = self.sanitizer.normalize_stylistic_collocations(text4)
        self.assertIn("Sebagai contoh, pada Oktober 1980 ia mendukung", res4)
        self.assertNotIn("Pada bulan Oktober", res4)
        self.assertNotIn("1980, misalnya,", res4)

    def test_appositive_comma_normalization(self):
        # Appositive comma sandwich around names should be unsandwiched
        text1 = "Saat menempuh studi, ia menikahi sesama mahasiswa, Raisa Titarenko, pada tahun 1953."
        res1 = self.sanitizer.normalize_appositive_commas(text1)
        self.assertIn("sesama mahasiswa Raisa Titarenko pada", res1)
        self.assertNotIn("sesama mahasiswa, Raisa Titarenko,", res1)

        text2 = "Putrinya, Irina, menikah dengan rekan sesama mahasiswa, Anatoly Virgansky, pada April 1978."
        res2 = self.sanitizer.normalize_appositive_commas(text2)
        self.assertIn("Putrinya Irina menikah", res2)
        self.assertIn("sesama mahasiswa Anatoly Virgansky pada", res2)

    def test_coordinating_conjunction_comma_normalization(self):
        # Two parallel verbal predicates sharing same subject: no comma before dan/serta
        text1 = "Gorbachev belajar giat, dan lulus dengan predikat memuaskan."
        res1 = self.sanitizer.normalize_coordinating_conjunction_commas(text1)
        self.assertIn("belajar giat dan lulus", res1)
        self.assertNotIn("giat, dan lulus", res1)

        # Serial lists (3+ items) must retain Oxford comma
        text2 = "Ia mengunjungi London, Paris, dan Berlin."
        res2 = self.sanitizer.normalize_coordinating_conjunction_commas(text2)
        self.assertIn("London, Paris, dan Berlin", res2)

    def test_comma_clutter_normalization(self):
        # Double 'dan' in same sentence
        text1 = "Penulis favoritnya meliputi Arthur Miller, Dostoyevsky, dan Chinghiz Aitmatov, dan ia juga gemar membaca kisah detektif."
        res1 = self.sanitizer.normalize_comma_clutter(text1)
        self.assertIn("Chinghiz Aitmatov. Selain itu, ia gemar", res1)
        self.assertNotIn("Chinghiz Aitmatov, dan ia", res1)

        # Duplicate consecutive commas and commas before period
        text2 = "Kalimat dengan koma ganda,, dan koma sebelum titik,."
        res2 = self.sanitizer.normalize_comma_clutter(text2)
        self.assertIn("koma ganda, dan", res2)
        self.assertIn("sebelum titik.", res2)
        self.assertNotIn(",,", res2)
        self.assertNotIn(",.", res2)

    def test_introductory_adverbial_comma_normalization(self):
        # Eliminates second comma in introductory conjunction + short adverbial sandwich
        text1 = "Namun, sesampainya di sana, ia mendapati bahwa tidak ada posisi kerja yang tersedia baginya."
        res1 = self.sanitizer.normalize_introductory_adverbial_commas(text1)
        self.assertIn("Namun, sesampainya di sana ia mendapati", res1)
        self.assertNotIn("Namun, sesampainya di sana,", res1)

        text2 = "Namun, pada Agustus 1968, ia diangkat menjadi Sekretaris Kedua Kraikom."
        res2 = self.sanitizer.normalize_introductory_adverbial_commas(text2)
        self.assertIn("Namun, pada Agustus 1968 ia diangkat", res2)

        text3 = "Sementara itu, dalam rapat Komite Pusat, tokoh garis keras menuduh Gorbachev."
        res3 = self.sanitizer.normalize_introductory_adverbial_commas(text3)
        self.assertIn("Sementara itu, dalam rapat Komite Pusat tokoh garis keras", res3)

        # Preserves vocatives with direct address
        text4 = "Namun, Kamerad, janganlah berpikir tentang pelampung."
        res4 = self.sanitizer.normalize_introductory_adverbial_commas(text4)
        self.assertIn("Namun, Kamerad, janganlah", res4)

    def test_relative_clause_comma_normalization(self):
        # Relative clause 'yang' comma sandwich
        text1 = "Kendati demikian, banyak anggota Komite Pusat menganggap Gorbachev, yang kala itu berusia 53 tahun, masih terlalu muda dan minim pengalaman."
        res1 = self.sanitizer.normalize_relative_clause_commas(text1)
        self.assertIn("Gorbachev yang kala itu berusia 53 tahun masih terlalu muda", res1)
        self.assertNotIn("Gorbachev, yang", res1)
        self.assertNotIn("tahun, masih", res1)

        # Staff count with thousand separator
        text2 = "Jumlah staf Komite Pusat, yang saat itu mencapai sekitar 3.000 orang, dipangkas hingga separuhnya."
        res2 = self.sanitizer.normalize_relative_clause_commas(text2)
        self.assertIn("Pusat yang saat itu mencapai sekitar 3.000 orang dipangkas", res2)
        self.assertNotIn("Pusat, yang", res2)
        self.assertNotIn("orang, dipangkas", res2)

        # Proper noun inside wikilink
        text3 = "Yeltsin, yang saat itu menjabat sebagai Presiden [[RSFSR]], masuk ke dalam gedung."
        res3 = self.sanitizer.normalize_relative_clause_commas(text3)
        self.assertIn("Yeltsin yang saat itu menjabat sebagai Presiden [[RSFSR]] masuk", res3)

    def test_sentence_case_after_periods(self):
        # Sentence capitalization across citation templates
        text1 = "Gorbachev lulus dengan predikat memuaskan. {{sfnm|1a1=Medvedev|1y=1986|1p=42|2a1=McCauley|2y=1998|2p=20}} tugas akhirnya mengkaji keunggulan."
        res1 = self.sanitizer.normalize_sentence_case_after_periods(text1)
        self.assertIn("Tugas akhirnya mengkaji", res1)
        self.assertNotIn("tugas akhirnya", res1)

        # Sentence capitalization across ref tags
        text2 = "Peristiwa ini resmi berakhir.<ref>Sumber</ref> sebulan kemudian mereka pindah."
        res2 = self.sanitizer.normalize_sentence_case_after_periods(text2)
        self.assertIn("Sebulan kemudian", res2)
        self.assertNotIn("sebulan kemudian", res2)

        # Preserves abbreviations (hlm., dkk.)
        text3 = "Buku ini dicetak pada hlm. 45-50 dan dkk. mereka menyetujui."
        res3 = self.sanitizer.normalize_sentence_case_after_periods(text3)
        self.assertIn("hlm. 45", res3)
        self.assertIn("dkk. mereka", res3)

    def test_clean_indirect_speech_fragmented_quotes(self):
        # Unquotes fragmented quotes in indirect speech and fixes clitic
        text1 = 'Gorbachev menuturkan bahwa peristiwa itu "sangat membekas" dalam dirinya, seraya mengakui bahwa "hati nurani tersiksa" karena telah mengawasi persekusi.'
        res1 = self.sanitizer.clean_indirect_speech_fragmented_quotes(text1)
        self.assertIn("peristiwa itu sangat membekas dalam", res1)
        self.assertIn("hati nuraninya tersiksa karena", res1)
        self.assertNotIn('"sangat membekas"', res1)
        self.assertNotIn('"hati nurani tersiksa"', res1)

        # Preserves preserved political terms and direct speech
        text2 = 'Gorbachev mengkaji keunggulan "demokrasi sosialis" ala Soviet.'
        res2 = self.sanitizer.clean_indirect_speech_fragmented_quotes(text2)
        self.assertIn('"demokrasi sosialis"', res2)

        text3 = 'Gorbachev menyatakan, "Kami memang berjuang merebut kekuasaan."'
        res3 = self.sanitizer.clean_indirect_speech_fragmented_quotes(text3)
        self.assertIn('"Kami memang berjuang', res3)

        # Preposition + quoted common noun phrases
        text4 = 'mengukuhkan Partai Komunis sebagai "partai penguasa" di Uni Soviet.'
        res4 = self.sanitizer.clean_indirect_speech_fragmented_quotes(text4)
        self.assertIn("sebagai partai penguasa di", res4)
        self.assertNotIn('"partai penguasa"', res4)
    def test_quotation_punctuation_order(self):
        # EYD V: punctuation outside quotes
        text1 = 'Ia membintangi film "The Runner," yang diproduksi oleh Amazon.'
        res1 = self.sanitizer.fix_quotation_punctuation_order(text1)
        self.assertIn('"The Runner",', res1)

        text2 = 'Judul proyek ini adalah "The Runner."'
        res2 = self.sanitizer.fix_quotation_punctuation_order(text2)
        self.assertIn('"The Runner".', res2)

        # Wikitext italics
        text3 = "Proyek ini berjudul ''The Runner.'' Sutradara mengumumkan rilis."
        res3 = self.sanitizer.fix_quotation_punctuation_order(text3)
        self.assertIn("''The Runner''.", res3)

    def test_compound_hyphens_and_bound_forms(self):
        # pro-Palestina -> pendukung Palestina
        text1 = "Delapan pengunjuk rasa pro-Palestina ditangkap di London."
        res1 = self.sanitizer.normalize_compound_hyphens(text1)
        self.assertNotIn("pro-Palestina", res1)
        self.assertIn("pengunjuk rasa pendukung Palestina", res1)

        # Bound forms joined without hyphen before lowercase
        text2 = "Universitas ini membuka program pasca-sarjana dan non-blok antarkota multi-nasional."
        res2 = self.sanitizer.normalize_compound_hyphens(text2)
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
