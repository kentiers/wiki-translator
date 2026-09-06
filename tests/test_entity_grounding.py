"""
Unit tests for the Universal Multi-Domain Entity & Claim Grounding Auditor.
Covers all topics: Biography, History, Film, Computing, Medicine, Physics, and Auto-Repair.
"""

import unittest
from wiki_translator.entity_grounding import (
    EntityGroundingAuditor,
    EntityGroundingResult,
    default_entity_grounding_auditor,
)
from wiki_translator.factual_audit import FactualConsistencyAuditor


class TestEntityGroundingAuditor(unittest.TestCase):
    def setUp(self):
        self.auditor = EntityGroundingAuditor()

    # -------------------------------------------------------------------------
    # 1. Biography & History (Stasova / Gurevich / Shabanova Case)
    # -------------------------------------------------------------------------
    def test_biography_detects_dropped_and_phantom_entities(self):
        source = (
            'She served as a mentor to [[Liubov Gurevich]] and other younger feminists; '
            'the historian [[Rochelle Ruthchild]] writes that she "achieved almost saintlike status".'
        )
        draft_hallucinated = (
            'Di samping itu, Stasova menjadi sumber inspirasi bagi kalangan feminis muda. '
            'Pemimpin feminis [[Anna Shabanova]] mengenang pertemuannya dengan menulis bahwa '
            '"semua orang terpikat oleh kepribadiannya".'
        )

        res = self.auditor.audit(source, draft_hallucinated, topic="history_social")
        self.assertFalse(res.passed)
        self.assertIn("Liubov Gurevich", res.dropped_entities)
        self.assertIn("Rochelle Ruthchild", res.dropped_entities)
        self.assertIn("Anna Shabanova", res.phantom_entities)
        self.assertTrue(any("atribusi kutipan" in w for w in res.warnings))
        self.assertIsNotNone(res.revision_prompt)
        self.assertIn("Liubov Gurevich", res.revision_prompt)

    def test_biography_passes_when_grounded(self):
        source = (
            'She served as a mentor to [[Liubov Gurevich]] and other younger feminists; '
            'the historian [[Rochelle Ruthchild]] writes that she "achieved almost saintlike status".'
        )
        draft_faithful = (
            'Ia menjadi mentor bagi [[Liubov Gurevich]] serta kalangan feminis muda lainnya. '
            'Sejarawan [[Rochelle Ruthchild]] menulis bahwa ia "nyaris mencapai status serupa orang suci".'
        )

        res = self.auditor.audit(source, draft_faithful, topic="history_social")
        self.assertTrue(res.passed)
        self.assertEqual(len(res.dropped_entities), 0)
        self.assertEqual(len(res.phantom_entities), 0)
        self.assertEqual(len(res.warnings), 0)

    # -------------------------------------------------------------------------
    # 2. Film & Cinema
    # -------------------------------------------------------------------------
    def test_film_detects_director_actor_inversion(self):
        source = (
            "[[Interstellar (film)|Interstellar]] is a 2014 science fiction film directed by "
            "[[Christopher Nolan]], starring [[Matthew McConaughey]]."
        )
        draft_inverted = (
            "[[Interstellar (film)|Interstellar]] adalah film fiksi ilmiah tahun 2014 yang disutradarai oleh "
            "[[Matthew McConaughey]], dibintangi oleh [[Christopher Nolan]]."
        )

        res = self.auditor.audit(source, draft_inverted, topic="film")
        self.assertFalse(res.passed)
        self.assertTrue(any("peran sutradara" in w for w in res.attribution_warnings))

    def test_film_preserves_titles_and_actors(self):
        source = (
            "[[Interstellar (film)|Interstellar]] is a 2014 science fiction film directed by "
            "[[Christopher Nolan]], starring [[Matthew McConaughey]]."
        )
        draft_correct = (
            "[[Interstellar (film)|Interstellar]] adalah film fiksi ilmiah tahun 2014 yang disutradarai oleh "
            "[[Christopher Nolan]] dan dibintangi oleh [[Matthew McConaughey]]."
        )

        res = self.auditor.audit(source, draft_correct, topic="film")
        self.assertTrue(res.passed)
        self.assertEqual(len(res.attribution_warnings), 0)

    # -------------------------------------------------------------------------
    # 3. Computing & Technology
    # -------------------------------------------------------------------------
    def test_computing_detects_creator_drift(self):
        source = "Python was created by [[Guido van Rossum]] and first released in 1991."
        draft_swapped = "Python dibuat oleh [[Linus Torvalds]] dan pertama kali dirilis pada 1991."

        res = self.auditor.audit(source, draft_swapped, topic="computing_science")
        self.assertFalse(res.passed)
        self.assertIn("Guido van Rossum", res.dropped_entities)
        self.assertIn("Linus Torvalds", res.phantom_entities)
        self.assertTrue(any("pengembang/pencipta" in w for w in res.attribution_warnings))

    def test_computing_preserves_technical_entities(self):
        source = (
            "The model is based on the [[Transformer (deep learning architecture)|Transformer]] architecture "
            "developed by [[Google Brain]]."
        )
        draft_faithful = (
            "Model ini didasarkan pada arsitektur [[Transformer (arsitektur pembelajaran dalam)|Transformer]] "
            "yang dikembangkan oleh [[Google Brain]]."
        )

        res = self.auditor.audit(source, draft_faithful, topic="computing_science")
        self.assertTrue(res.passed)
        self.assertEqual(len(res.dropped_entities), 0)

    # -------------------------------------------------------------------------
    # 4. Medicine & Biology
    # -------------------------------------------------------------------------
    def test_medical_preserves_pathogen_and_taxa(self):
        source = (
            "[[Tuberculosis]] is caused by the bacterium ''[[Mycobacterium tuberculosis]]'', "
            "which attacks the lungs."
        )
        draft_faithful = (
            "[[Tuberkulosis]] disebabkan oleh bakteri ''[[Mycobacterium tuberculosis]]'', "
            "yang menyerang paru-paru."
        )

        res = self.auditor.audit(source, draft_faithful, topic="medical_biology")
        self.assertTrue(res.passed)
        self.assertEqual(len(res.dropped_entities), 0)

    def test_medical_flags_dropped_pathogen(self):
        source = "Infection by ''[[Helicobacter pylori]]'' can cause peptic ulcer disease."
        draft_dropped = "Infeksi bakteri umum dapat menyebabkan penyakit tukak lambung."

        res = self.auditor.audit(source, draft_dropped, topic="medical_biology")
        self.assertFalse(res.passed)
        self.assertTrue(any("Helicobacter pylori" in ent for ent in res.dropped_entities))

    # -------------------------------------------------------------------------
    # 5. Physics, Mathematics & Astronomy
    # -------------------------------------------------------------------------
    def test_physics_preserves_equations_and_theorems(self):
        source = (
            "The [[James Webb Space Telescope]] observed distant galaxies confirming predictions "
            "of [[Albert Einstein]]'s [[general relativity]]."
        )
        draft_faithful = (
            "[[Teleskop Luar Angkasa James Webb]] mengamati galaksi-galaksi jauh yang mengonfirmasi "
            "prediksi [[relativitas umum]] karya [[Albert Einstein]]."
        )

        res = self.auditor.audit(source, draft_faithful, topic="physics_astronomy")
        self.assertTrue(res.passed)
        self.assertEqual(len(res.dropped_entities), 0)

    # -------------------------------------------------------------------------
    # 6. Deterministic Auto-Repair
    # -------------------------------------------------------------------------
    def test_auto_repair_restores_missing_wikilink_brackets(self):
        source = "The publication included works by [[Charles Darwin]] and [[Hans Christian Andersen]]."
        draft_plain = "Penerbitan tersebut mencakup karya-karya karya Charles Darwin dan Hans Christian Andersen."

        repaired, count = self.auditor.auto_repair_entities(draft_plain, source)
        self.assertEqual(count, 2)
        self.assertIn("[[Charles Darwin]]", repaired)
        self.assertIn("[[Hans Christian Andersen]]", repaired)

    # -------------------------------------------------------------------------
    # 7. Integration with FactualConsistencyAuditor
    # -------------------------------------------------------------------------
    def test_integration_with_factual_consistency_auditor(self):
        auditor = FactualConsistencyAuditor()
        source = "Mentored by [[Liubov Gurevich]]. Founded in 1895.<ref>Src</ref>"
        draft_hallucinated = "Didukung oleh [[Anna Shabanova]]. Didirikan pada 1895.<ref>Src</ref>"

        res = auditor.audit(source, draft_hallucinated, topic="history_social")
        self.assertFalse(res.passed)
        self.assertIn("Liubov Gurevich", res.dropped_entities)
        self.assertIn("Anna Shabanova", res.phantom_entities)
        self.assertTrue(any("Liubov Gurevich" in w for w in res.warnings))
    # -------------------------------------------------------------------------
    # 8. Unanchored Eulogy / Hallucinated Conclusion Detection
    # -------------------------------------------------------------------------
    def test_detects_unanchored_eulogy_sentence(self):
        source = "Stasova was buried in Tikhvin Cemetery in St. Petersburg."
        draft_with_eulogy = (
            "Jenazahnya dimakamkan di Pemakaman Tikhvin, Sankt-Peterburg. "
            "Kepergiannya ditangisi secara luas oleh ribuan perempuan Rusia yang mengenang dedikasi tanpa pamrihnya "
            "selama lebih dari empat dasawarsa dalam memperjuangkan hak dan martabat kaum perempuan."
        )

        warnings = self.auditor.audit_unanchored_sentences(source, draft_with_eulogy)
        self.assertTrue(len(warnings) > 0)
        self.assertTrue(any("fabrikasi kesimpulan/eulogi" in w for w in warnings))

    def test_slop_linter_flags_puffery(self):
        from wiki_translator.slop_linter import default_slop_linter
        bad_text = "Kepergiannya ditangisi secara luas oleh masyarakat yang mengenang dedikasi tanpa pamrihnya."
        res = default_slop_linter.lint(bad_text)
        self.assertFalse(res.is_clean)
        rule_ids = [v.rule_id for v in res.violations]
        self.assertIn("puffery_dedikasi_tanpa_pamrih", rule_ids)
        self.assertIn("puffery_ditangisi_secara_luas", rule_ids)


if __name__ == "__main__":
    unittest.main()
