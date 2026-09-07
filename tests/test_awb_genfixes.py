"""
Unit tests for AWB-style General Fixes and RegEx Typo Fix Engine (awb_genfixes.py).
"""

import unittest
from wiki_translator.awb_genfixes import (
    GeneralFixesEngine,
    RegExTypoFixEngine,
    AWBGenFixes,
    default_genfixes,
)


class TestGeneralFixesEngine(unittest.TestCase):
    def setUp(self):
        self.engine = GeneralFixesEngine()

    def test_appendix_section_reordering_standard(self):
        """Tests standard Wikipedia Bahasa Indonesia appendix section reordering per WP:PEDOMAN."""
        input_wikitext = """Bagian pendahuluan artikel.

== Pranala luar ==
* [https://example.com Link Luar]

== Referensi ==
{{reflist}}

== Catatan ==
{{notelist}}

== Bacaan lanjutan ==
* Penulis A (2020). Judul Buku.

[[Kategori:Artikel Uji]]
"""
        reordered = self.engine.reorder_appendices(input_wikitext)
        
        # Verify order: Catatan -> Referensi -> Bacaan lanjutan -> Pranala luar
        catatan_pos = reordered.find("== Catatan ==")
        referensi_pos = reordered.find("== Referensi ==")
        bacaan_pos = reordered.find("== Bacaan lanjutan ==")
        pranala_pos = reordered.find("== Pranala luar ==")
        kategori_pos = reordered.find("[[Kategori:Artikel Uji]]")

        self.assertTrue(catatan_pos != -1, "Catatan section must exist")
        self.assertTrue(referensi_pos != -1, "Referensi section must exist")
        self.assertTrue(bacaan_pos != -1, "Bacaan lanjutan section must exist")
        self.assertTrue(pranala_pos != -1, "Pranala luar section must exist")

        self.assertLess(catatan_pos, referensi_pos)
        self.assertLess(referensi_pos, bacaan_pos)
        self.assertLess(bacaan_pos, pranala_pos)
        self.assertLess(pranala_pos, kategori_pos)

    def test_appendix_reordering_with_rujukan(self):
        """Tests appendix reordering with alternative heading 'Rujukan'."""
        wikitext = """Konten artikel.

== Pranala luar ==
* [http://example.com/ Link]

== Rujukan ==
{{reflist}}

== Catatan ==
{{notelist}}
"""
        reordered = self.engine.reorder_appendices(wikitext)
        catatan_pos = reordered.find("== Catatan ==")
        rujukan_pos = reordered.find("== Rujukan ==")
        pranala_pos = reordered.find("== Pranala luar ==")

        self.assertLess(catatan_pos, rujukan_pos)
        self.assertLess(rujukan_pos, pranala_pos)

    def test_reference_deduplication(self):
        """Tests deduplication of identical named <ref name="X"> tags."""
        wikitext = (
            'Pernyataan pertama disetujui.<ref name="smith2020">Smith, J. (2020). \'\'Title\'\'. Publisher.</ref> '
            'Pernyataan kedua juga sama.<ref name="smith2020">Smith, J. (2020). \'\'Title\'\'. Publisher.</ref> '
            'Pernyataan ketiga.<ref name="smith2020">Smith, J. (2020). \'\'Title\'\'. Publisher.</ref>'
        )
        expected = (
            'Pernyataan pertama disetujui.<ref name="smith2020">Smith, J. (2020). \'\'Title\'\'. Publisher.</ref> '
            'Pernyataan kedua juga sama.<ref name="smith2020" /> '
            'Pernyataan ketiga.<ref name="smith2020" />'
        )
        deduped = self.engine.deduplicate_references(wikitext)
        self.assertEqual(deduped, expected)

    def test_reference_deduplication_different_names(self):
        """Different ref names must retain their unique bodies."""
        wikitext = (
            '<ref name="ref1">Content 1</ref>'
            '<ref name="ref2">Content 2</ref>'
            '<ref name="ref1">Content 1</ref>'
        )
        deduped = self.engine.deduplicate_references(wikitext)
        self.assertIn('<ref name="ref1">Content 1</ref>', deduped)
        self.assertIn('<ref name="ref2">Content 2</ref>', deduped)
        self.assertIn('<ref name="ref1" />', deduped)

    def test_citation_punctuation_spacing_and_placement(self):
        """Tests space before ref and moving trailing punctuation before ref."""
        # Space before dot/comma before ref
        self.assertEqual(
            self.engine.fix_citation_punctuation("pernyataan .<ref>sumber</ref>"),
            "pernyataan.<ref>sumber</ref>",
        )
        self.assertEqual(
            self.engine.fix_citation_punctuation("pernyataan ,<ref>sumber</ref>"),
            "pernyataan,<ref>sumber</ref>",
        )
        # Space between word and ref
        self.assertEqual(
            self.engine.fix_citation_punctuation("pernyataan <ref>sumber</ref>"),
            "pernyataan<ref>sumber</ref>",
        )
        # Punctuation trailing after ref moves before ref
        self.assertEqual(
            self.engine.fix_citation_punctuation("pernyataan<ref>sumber</ref>."),
            "pernyataan.<ref>sumber</ref>",
        )
        self.assertEqual(
            self.engine.fix_citation_punctuation('pernyataan<ref name="x" />,'),
            'pernyataan,<ref name="x" />',
        )
        # Chained refs
        self.assertEqual(
            self.engine.fix_citation_punctuation('klaim<ref>ref1</ref><ref name="ref2" />.'),
            'klaim.<ref>ref1</ref><ref name="ref2" />',
        )

    def test_page_range_en_dash_normalizer(self):
        """Tests conversion of pp./pages to hlm. with en-dash."""
        # pp. 12-15 -> hlm. 12–15
        self.assertEqual(
            self.engine.normalize_page_ranges("lihat pp. 12-15 untuk rincian"),
            "lihat hlm. 12–15 untuk rincian",
        )
        # pages 100-105 -> hlm. 100–105
        self.assertEqual(
            self.engine.normalize_page_ranges("baca pages 100-105."),
            "baca hlm. 100–105.",
        )
        # single page: p. 42 -> hlm. 42
        self.assertEqual(
            self.engine.normalize_page_ranges("pada p. 42 disebutkan"),
            "pada hlm. 42 disebutkan",
        )
        # Inside citation template |pages=50-60
        self.assertEqual(
            self.engine.normalize_page_ranges("{{cite book |title=Judul |pages=50-60 }}"),
            "{{cite book |title=Judul |pages=50–60 }}",
        )

    def test_duplicate_empty_parameter_cleaner(self):
        """Tests cleaning redundant empty citation parameters when archive is empty."""
        cite_empty = (
            "{{cite web |url=https://example.com |title=Judul "
            "|access-date= |archive-url= |url-status= |df= }}"
        )
        cleaned = self.engine.clean_empty_parameters(cite_empty)
        self.assertNotIn("archive-url=", cleaned)
        self.assertNotIn("url-status=", cleaned)
        self.assertNotIn("access-date=", cleaned)
        self.assertNotIn("df=", cleaned)

        # When archive-url IS present, it should keep archive parameters
        cite_filled_archive = (
            "{{cite web |url=https://example.com |title=Judul "
            "|archive-url=https://web.archive.org/web/123 |archive-date=2024-01-01 |url-status=live }}"
        )
        kept = self.engine.clean_empty_parameters(cite_filled_archive)
        self.assertIn("archive-url=https://web.archive.org/web/123", kept)
        self.assertIn("url-status=live", kept)

    def test_purge_pleonastic_conjunctions(self):
        s1 = "Meskipun usulan tersebut ditolak, namun ia tidak menyerah."
        self.assertEqual(self.engine.purge_pleonastic_conjunctions(s1), "Meskipun usulan tersebut ditolak, ia tidak menyerah.")
        s2 = "Karena ayahnya arsitek, maka ia menyukai seni."
        self.assertEqual(self.engine.purge_pleonastic_conjunctions(s2), "Karena ayahnya arsitek, ia menyukai seni.")
        s3 = "Walaupun ia sakit parah, tetapi ia tetap bekerja giat."
        self.assertEqual(self.engine.purge_pleonastic_conjunctions(s3), "Walaupun ia sakit parah, ia tetap bekerja giat.")

    def test_glue_and_clean_references(self):
        r1 = "Kota Sankt-Peterburg . <ref name=\":1\" /> <ref name=\":1\" />"
        self.assertEqual(self.engine.glue_and_clean_references(r1), "Kota Sankt-Peterburg .<ref name=\":1\" />")
        r2 = "akhir abad ke-19 <ref name=\":5\" />"
        self.assertEqual(self.engine.glue_and_clean_references(r2), "akhir abad ke-19<ref name=\":5\" />")

    def test_capitalize_geographic_proper_nouns(self):
        g1 = "Ia berlayar mengarungi laut Jawa menuju selat Sunda dekat gunung Krakatau dan danau Toba."
        self.assertEqual(self.engine.capitalize_geographic_proper_nouns(g1), "Ia berlayar mengarungi Laut Jawa menuju Selat Sunda dekat Gunung Krakatau dan Danau Toba.")

    def test_clean_deprecated_citation_parameters(self):
        c1 = "{{cite web |url=https://example.com |title=Judul |dead-url=no |language=en}}"
        res1 = self.engine.clean_deprecated_citation_parameters(c1)
        self.assertIn("|url-status=live", res1)
        self.assertNotIn("language=en", res1)

    def test_clean_overlinked_wikilinks(self):
        t1 = (
            "== Kehidupan awal ==\n"
            "Stasova lahir di [[Sankt-Peterburg]] pada 1822. Di [[Sankt-Peterburg]] ia belajar seni.\n\n"
            "Ia kemudian pindah ke [[Moskwa]]. Di [[Sankt-Peterburg]] saudaranya bekerja."
        )
        res = self.engine.clean_overlinked_wikilinks(t1, window_paragraphs=2)
        # Second Sankt-Peterburg in same paragraph should be plain text
        self.assertIn("Stasova lahir di [[Sankt-Peterburg]] pada 1822. Di Sankt-Peterburg ia belajar seni.", res)
        # Third Sankt-Peterburg in next paragraph should be plain text
        self.assertIn("Di Sankt-Peterburg saudaranya bekerja.", res)

    def test_deduplicate_parallel_modifiers(self):
        p1 = "segera menjalin persahabatan erat serta persekutuan erat hingga dijuluki"
        self.assertEqual(self.engine.deduplicate_parallel_modifiers(p1), "segera menjalin persahabatan serta persekutuan erat hingga dijuluki")
    def test_clean_editorial_quote_brackets(self):
        sample = 'Stites menggambarkannya sebagai "tiga tokoh [feminis] terpenting" di era itu.'
        self.assertEqual(
            self.engine.clean_editorial_quote_brackets(sample),
            'Stites menggambarkannya sebagai "tiga tokoh feminis terpenting" di era itu.',
        )


class TestRegExTypoFixEngine(unittest.TestCase):
    def setUp(self):
        self.retf = RegExTypoFixEngine()

    def test_dictionary_size(self):
        """Verifies RETF dictionary contains 80+ common Indonesian typos."""
        self.assertGreaterEqual(self.retf.dictionary_size, 80)

    def test_valid_words_are_not_rewritten_as_typos(self):
        self.assertEqual(self.retf.fix_typos("Unta mempelajari tata bahasa secara sistematik."), "Unta mempelajari tata bahasa secara sistematik.")

    def test_common_indonesian_typos(self):
        """Tests replacement of core common typos according to KBBI VI."""
        typo_test_cases = [
            ("aktifitas", "aktivitas"),
            ("analisa", "analisis"),
            ("merubah", "mengubah"),
            ("praktek", "praktik"),
            ("resiko", "risiko"),
            ("jaman", "zaman"),
            ("ijin", "izin"),
            ("obyek", "objek"),
            ("subyek", "subjek"),
            ("faham", "paham"),
            ("fikiran", "pikiran"),
            ("kwantitas", "kuantitas"),
            ("kwalitas", "kualitas"),
            ("sistim", "sistem"),
            ("tehnik", "teknik"),
            ("diagnosa", "diagnosis"),
            ("hipotesa", "hipotesis"),
            ("metoda", "metode"),
            ("standarisasi", "standardisasi"),
            ("pertanggung jawaban", "pertanggungjawaban"),
        ]
        for wrong, correct in typo_test_cases:
            result = self.retf.fix_typos(f"Ini adalah {wrong} penting.")
            self.assertEqual(result, f"Ini adalah {correct} penting.", f"Failed on {wrong} -> {correct}")

    def test_case_preservation(self):
        """Tests that capitalized or all-caps typos preserve capitalization."""
        self.assertEqual(self.retf.fix_typos("Aktifitas dan Analisa"), "Aktivitas dan Analisis")
        self.assertEqual(self.retf.fix_typos("AKTIFITAS"), "AKTIVITAS")
        self.assertEqual(self.retf.fix_typos("Praktek"), "Praktik")

    def test_url_protection(self):
        """Verifies URLs are never modified even if containing typo keywords."""
        url = "https://example.org/analisa-resiko-sistim/aktifitas.html"
        text = f"Kunjungi {url} untuk laporan."
        result = self.retf.fix_typos(text)
        self.assertIn(url, result)

    def test_media_file_protection(self):
        """Verifies [[Berkas:...]] and [[File:...]] names are preserved."""
        image_wikilink = "[[Berkas:Peta analisa daerah aktifitas.jpg|jmpl|Peta analisa]]"
        result = self.retf.fix_typos(image_wikilink)
        self.assertTrue(result.startswith("[[Berkas:Peta analisa daerah aktifitas.jpg|"))

    def test_math_and_code_tag_protection(self):
        """Verifies <math> and <code> blocks are safe from RETF."""
        math_block = "<math>\\text{analisa}(x) + \\text{aktifitas}</math>"
        code_block = "<code>const resiko = sistim.eval();</code>"
        text = f"{math_block} dan {code_block}"
        result = self.retf.fix_typos(text)
        self.assertEqual(result, text)

    def test_template_parameter_keys_protection(self):
        """Verifies parameter keys (e.g. |aktifitas=) are not renamed."""
        tpl = "{{infobox |aktifitas=tinggi |analisa=lengkap |resiko=rendah}}"
        result = self.retf.fix_typos(tpl)
        self.assertIn("|aktifitas=", result)
        self.assertIn("|analisa=", result)
        self.assertIn("|resiko=", result)


class TestAWBGenFixesIntegration(unittest.TestCase):
    def test_apply_all_fixes(self):
        """Tests end-to-end apply_all_fixes integration combining GenFixes and RETF."""
        raw_wikitext = """Praktek analisa sistim ini memiliki resiko yang tinggi .<ref name="sumber1">Konten sumber satu</ref>
Berikutnya dijelaskan pada pp. 20-25.<ref name="sumber1">Konten sumber satu</ref>

== Pranala luar ==
* [http://example.com/analisa/index.html Link resmi]

== Referensi ==
{{reflist}}

== Catatan ==
{{notelist}}

[[Kategori:Teknologi]]
"""
        fixed = default_genfixes.apply_all_fixes(raw_wikitext)

        # RETF: Praktek -> Praktik, analisa -> analisis, sistim -> sistem, resiko -> risiko
        self.assertIn("Praktik analisis sistem ini memiliki risiko yang tinggi.<ref name=\"sumber1\">", fixed)
        # Ref deduplication: second occurrence is collapsed
        self.assertIn('<ref name="sumber1" />', fixed)
        # Page range en-dash: pp. 20-25 -> hlm. 20–25
        self.assertIn("hlm. 20–25", fixed)
        # URL untouched
        self.assertIn("http://example.com/analisa/index.html", fixed)
        # Appendix reordering: Catatan before Referensi before Pranala luar
        catatan_pos = fixed.find("== Catatan ==")
        referensi_pos = fixed.find("== Referensi ==")
        pranala_pos = fixed.find("== Pranala luar ==")
        self.assertLess(catatan_pos, referensi_pos)
        self.assertLess(referensi_pos, pranala_pos)
    def test_separate_fused_words_and_number_boundaries(self):
        """Tests generalized word boundary separation and legitimate word protection."""
        text = "Pada tahun1945 di kota medan, pasukan meraih peringkat ke10 setelah berjuang selama musim semidan musim panas."
        fixed = default_genfixes.apply_all_fixes(text)
        self.assertIn("tahun 1945", fixed)
        self.assertIn("kota medan", fixed)
        self.assertIn("ke-10", fixed)
        self.assertIn("musim semi dan musim panas", fixed)


if __name__ == "__main__":
    unittest.main()
