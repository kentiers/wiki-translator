"""
Permanent regression test suite for core editorial invariants established for
Indonesian Wikipedia Grade A++ translation quality.
"""

import unittest
from wiki_translator.awb_genfixes import default_genfixes
from wiki_translator.typography_sanitizer import default_typography_sanitizer
from wiki_translator.link_fidelity_validator import LinkFidelityValidator
from wiki_translator.editorial_qa import default_qa_pipeline


class TestEditorialInvariants(unittest.TestCase):
    """Guards against regressions in word splitting, punctuation, and source grounding."""

    def test_invariant_1_word_splitting_protection(self):
        """Standard Indonesian words must NEVER be split into pieces."""
        words_to_protect = [
            "menyadari", "menghindari", "mendasari", "mengedari", "kendari",
            "waspada", "daripada", "perantara", "dangkal", "danau", "dampak",
            "mendalam", "perdalam", "memperdalam", "sedalam", "kedalaman",
            "sepadan", "kesepadanan", "memantau", "merantau"
        ]
        for w in words_to_protect:
            sample = f"Tokoh tersebut {w} bahwa hal itu penting."
            fixed = default_genfixes.apply_all_fixes(sample)
            self.assertIn(w, fixed, f"Word '{w}' was mutilated into '{fixed}'!")

    def test_invariant_2_em_dash_eliminated_in_narrative(self):
        """Narrative prose must avoid em-dashes (—)."""
        sample = "Maui—yang terilhami oleh mana—bermakna sangat mendalam."
        sanitized = default_typography_sanitizer.normalize_em_dashes(sample)
        self.assertNotIn("—", sanitized, "Em-dash was not eliminated!")

    def test_invariant_3_appositive_comma_sandwiches_cleaned(self):
        """Attributive descriptors must not sandwich names with commas."""
        sample = "bersama mantan istrinya, [[Dany Garcia]], dan saudara laki-laki Dany, Hiram Garcia, untuk"
        sanitized = default_typography_sanitizer.sanitize_wikitext(sample)
        self.assertNotIn("istrinya, [[Dany Garcia]],", sanitized)
        self.assertIn("istrinya [[Dany Garcia]]", sanitized)
        self.assertIn("saudara laki-laki Dany Hiram Garcia", sanitized)

    def test_invariant_4_stacked_opening_adverbial_commas_merged(self):
        """Stacked introductory adverbials must merge into one opening block."""
        sample = "Dahulu kala, di Pulau Motunui di Polinesia, penduduk setempat memuja Te Fiti."
        sanitized = default_typography_sanitizer.sanitize_wikitext(sample)
        self.assertIn("Dahulu kala di Pulau Motunui di Polinesia,", sanitized)

    def test_invariant_5_semantic_link_disambiguation_protection(self):
        """Character redlinks must map to characters, not films or franchises."""
        validator = LinkFidelityValidator(api_checker=lambda titles: {t: False for t in titles})
        source = "[[Moana (2016 film)|2016 film]] [[Moana (character)|Moana]] [[Moana (franchise)|franchise]]"
        draft = "[[Moana (film 2016)|film 2016]] [[Moana (karakter)|Moana]] [[Moana (waralaba)|waralaba]]"
        updated, _, _ = validator.safeguard_redlinks_with_ill(draft, source)
        self.assertIn("en|Moana (character)", updated)
        self.assertIn("en|Moana (franchise)", updated)
        self.assertIn("en|Moana (2016 film)", updated)

    def test_invariant_6_source_of_truth_blocks_unanchored_templates(self):
        """Editorial QA must reject unanchored navbox templates not in source."""
        source = "==References==\n{{reflist}}\n==External links==\n{{Moana}}\n"
        draft_hallucinated = "Teks\n==Referensi==\n{{reflist}}\n==Pranala luar==\n{{Moana}}\n{{Thomas Kail}}\n"
        qa = default_qa_pipeline.audit(draft_hallucinated, title="Test", source_wikitext=source)
        self.assertFalse(qa.is_approved())
        self.assertTrue(any("Thomas Kail" in err for err in qa.critical_errors))
    def test_invariant_7_malay_loanwords_normalized(self):
        """Malaysian terminology (e.g. penstriman) must be normalized to standard Indonesian (pengaliran)."""
        sample = "film ini dirilis di layanan penstriman terkemuka"
        fixed = default_genfixes.apply_all_fixes(sample)
        self.assertIn("layanan pengaliran", fixed)
        self.assertNotIn("penstriman", fixed)


if __name__ == "__main__":
    unittest.main()
