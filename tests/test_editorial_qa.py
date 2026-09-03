"""
Unit tests for Multi-Layer Editorial QA Pipeline (wiki_translator/editorial_qa.py).
"""

import unittest

from wiki_translator.editorial_qa import (
    EditorialQAPipeline,
    QAAuditReport,
    default_qa_pipeline,
)
from wiki_translator.template_mapper import (
    STRIP_METADATA_TEMPLATES,
    WikiTemplateMapper,
    default_template_mapper,
)


class TestEditorialQAPipeline(unittest.TestCase):
    def setUp(self):
        self.pipeline = EditorialQAPipeline()

    def test_pipeline_default_instance(self):
        self.assertIsNotNone(default_qa_pipeline)
        self.assertIsInstance(default_qa_pipeline, EditorialQAPipeline)

    def test_strip_metadata_templates_in_template_mapper(self):
        """Test that en.wiki metadata templates are cleanly stripped."""
        mapper = WikiTemplateMapper(allow_network=False)
        wikitext = (
            "{{Short description|2026 science fiction film}}\n"
            "{{Use dmy dates|date=July 2024}}\n"
            "{{Use American English|date=July 2024}}\n"
            "{{Good article}}\n"
            "{{Infobox film\n"
            "| name = The Runner\n"
            "}}\n"
            "'''The Runner''' adalah film fiksi ilmiah Amerika Serikat tahun 2026."
        )
        cleaned = mapper.process_wikitext_templates(wikitext, check_existence=False)
        self.assertNotIn("Short description", cleaned)
        self.assertNotIn("SHORTDESC", cleaned)
        self.assertNotIn("Use dmy dates", cleaned)
        self.assertNotIn("Use American English", cleaned)
        self.assertNotIn("Good article", cleaned)
        self.assertIn("The Runner", cleaned)
        self.assertIn("{{Infobox film", cleaned)

    def test_strip_metadata_templates_set_contains_required(self):
        required = {
            "short description",
            "use dmy dates",
            "use mdy dates",
            "engvarb",
            "use american english",
            "use british english",
            "good article",
            "featured article",
        }
        for item in required:
            self.assertIn(item, STRIP_METADATA_TEMPLATES)

    def test_layer1_drafter_audit_clean_article(self):
        wikitext = (
            "'''The Matrix''' adalah film fiksi ilmiah yang dirilis pada tahun 1999 oleh Wachowski bersaudara. "
            "Film ini menggambarkan masa depan distopia di mana umat manusia terjebak dalam realitas simulasi.\n\n"
            "== Produksi ==\n"
            "Produksi film berlangsung di Australia dengan anggaran yang signifikan. Para pemeran menjalani pelatihan "
            "seni bela diri intensif selama berbulan-bulan sebelum proses syuting dimulai.\n\n"
            "== Penerimaan ==\n"
            "Film ini menerima pujian luas dari para kritikus dan memenangkan empat Penghargaan Academy.\n\n"
            "== Referensi ==\n"
            "{{Daftar rujukan}}"
        )
        res = self.pipeline.audit_drafter(wikitext)
        self.assertTrue(res.has_lead)
        self.assertTrue(res.has_references_section)
        self.assertGreaterEqual(res.section_count, 3)
        self.assertGreater(res.word_count, 50)
        self.assertGreaterEqual(res.score, 80)

    def test_layer1_drafter_audit_missing_lead_and_short(self):
        wikitext = "== Bab 1 ==\nTeks sangat pendek."
        res = self.pipeline.audit_drafter(wikitext)
        self.assertFalse(res.has_lead)
        self.assertLess(res.score, 70)

    def test_layer2_linguistic_audit_detects_calques(self):
        wikitext = (
            "Perusahaan yang berbasis di Jakarta ini memainkan peran kunci dalam upaya untuk menstabilkan ekonomi."
        )
        res = self.pipeline.audit_linguistics(wikitext)
        self.assertGreater(res.calque_count, 0)
        self.assertLess(res.score, 85)

    def test_layer3_wiki_technician_audit_detects_shortdesc_and_broken_syntax(self):
        wikitext = (
            "{{Short description|Test movie}}\n"
            "{{Infobox film\n"
            "| sutradara = John Doe\n"
            "}}\n"
            "Teks dengan kurung rusak [[Artikel tanpa penutup"
        )
        res = self.pipeline.audit_wiki_technician(wikitext)
        self.assertTrue(res.has_broken_shortdesc)
        self.assertIn("sutradara", res.unknown_infobox_keys)
        self.assertGreater(len(res.syntax_balance_issues), 0)
        self.assertLess(res.score, 60)

    def test_layer3_wiki_technician_clean(self):
        wikitext = (
            "{{Infobox film\n"
            "| director = Christopher Nolan\n"
            "| producer = Emma Thomas\n"
            "}}\n"
            "'''Oppenheimer''' adalah film biografi.\n\n"
            "[[Kategori:Film Amerika Serikat]]"
        )
        res = self.pipeline.audit_wiki_technician(wikitext)
        self.assertFalse(res.has_broken_shortdesc)
        self.assertEqual(len(res.unknown_infobox_keys), 0)
        self.assertEqual(len(res.syntax_balance_issues), 0)
        self.assertGreaterEqual(res.score, 90)

    def test_audit_pipeline_approval_flow(self):
        good_wikitext = (
            "{{Infobox film\n"
            "| name = Inception\n"
            "| director = Christopher Nolan\n"
            "}}\n"
            "'''Inception''' adalah film fiksi ilmiah tahun 2010 yang ditulis dan disutradarai oleh Christopher Nolan. "
            "Film ini dibintangi oleh Leonardo DiCaprio sebagai pencuri profesional yang mencuri informasi rahasia.\n\n"
            "== Alur cerita ==\n"
            "Dom Cobb dan Arthur melakukan infiltrasi bawah sadar militer untuk melakukan spionase perusahaan.\n\n"
            "== Produksi ==\n"
            "Pengambilan gambar utama dilakukan di enam negara berbeda selama beberapa bulan.\n\n"
            "== Referensi ==\n"
            "{{Daftar rujukan}}\n\n"
            "[[Kategori:Film tahun 2010]]"
        )
        report: QAAuditReport = self.pipeline.audit(good_wikitext, title="Inception")
        self.assertTrue(report.is_approved())
        self.assertGreaterEqual(report.overall_score, 80)
        self.assertIn(report.grade, ["A++", "A+", "A"])

        # Scorecard rendering
        scorecard = report.render_terminal_scorecard()
        self.assertIn("EDITORIAL & QA SCORECARD", scorecard)
        self.assertIn("PASSED / APPROVED FOR PUBLICATION", scorecard)
        self.assertIn("Inception", scorecard)

    def test_audit_pipeline_rejection_flow(self):
        bad_wikitext = (
            "{{Short description|Bad film}}\n"
            "Teks pendek."
        )
        report: QAAuditReport = self.pipeline.audit(bad_wikitext, title="Bad Film")
        self.assertFalse(report.is_approved())
        self.assertLess(report.overall_score, 80)
        scorecard = report.render_terminal_scorecard()
        self.assertIn("NEEDS REVISION", scorecard)
        self.assertIn("Broken SHORTDESC", scorecard)

    def test_audit_detects_mangled_wikilinks_and_raw_english_redlinks(self):
        mangled_wikitext = (
            "'''Kevin Macdonald''' adalah sutradara yang memenangkan [[Academy Award for Best dokumenter Feature]]. "
            "Ia juga bekerja sama dengan pemeran [[List of How to Get Away with Murder characters|Wes Gibbins]] "
            "serta memerankan karakter [[Dean Thomas (Harry Potter)|Dean Thomas]] dalam seri fantasi internasional. "
            "Karya-karya ini telah diakui oleh berbagai lembaga perfilman dunia dan meraih apresiasi tinggi.\n\n"
            "== Referensi ==\n{{reflist}}\n[[Kategori:Sutradara]]"
        )
        res = self.pipeline.audit_wiki_technician(mangled_wikitext)
        self.assertGreater(len(res.mangled_wikilinks), 0)
        self.assertGreater(len(res.raw_english_redlinks), 0)
        self.assertIn("[[Academy Award for Best dokumenter", res.mangled_wikilinks[0])

        report = self.pipeline.audit(mangled_wikitext)
        self.assertFalse(report.is_approved())
        self.assertTrue(any("dokumenter" in err for err in report.critical_errors))


if __name__ == "__main__":
    unittest.main()
