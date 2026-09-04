"""
Unit tests for LinkFidelityValidator.
"""

import unittest
from wiki_translator.link_fidelity_validator import (
    LinkFidelityValidator,
    LinkFidelityIssue,
    FidelityValidationResult,
)


class TestLinkFidelityValidator(unittest.TestCase):
    def setUp(self):
        # Mock existence checker for deterministic tests
        self.mock_db = {
            "Agen cerdas": True,
            "ChatGPT": True,
            "OpenAI": True,
            "DALL-E": True,
            "Pemberhentian Sam Altman dari OpenAI": False,
            "Model dasar (kecerdasan buatan)": False,
            "Produk dan aplikasi OpenAI": False,
            "Products and applications of OpenAI": False,
            "Removal of Sam Altman from OpenAI": False,
            "pemberhentian": False,
        }
        self.validator = LinkFidelityValidator(
            api_checker=lambda titles: {t: self.mock_db.get(t, False) for t in titles}
        )

    def test_detects_english_id_title(self):
        """Detects if parameter 1 (ID title) is in English."""
        wikitext = "{{ill|Products and applications of OpenAI|en|Products and applications of OpenAI|lt=Produk}}"
        res = self.validator.validate_wikitext(wikitext)
        self.assertFalse(res.is_valid)
        issue_types = [i.issue_type for i in res.issues]
        self.assertIn("english_id_title", issue_types)

    def test_detects_overly_generic_id_title(self):
        """Detects if parameter 1 is a generic single word when foreign target is a specific multi-word subject."""
        wikitext = "{{ill|pemberhentian|en|Removal of Sam Altman from OpenAI}}"
        res = self.validator.validate_wikitext(wikitext)
        self.assertFalse(res.is_valid)
        issue_types = [i.issue_type for i in res.issues]
        self.assertIn("generic_id_title", issue_types)

    def test_validates_contextual_indonesian_title(self):
        """Validates contextual Indonesian title with short display label."""
        wikitext = "{{ill|Pemberhentian Sam Altman dari OpenAI|en|Removal of Sam Altman from OpenAI|lt=pemberhentian}}"
        res = self.validator.validate_wikitext(wikitext)
        self.assertTrue(res.is_valid)
        self.assertEqual(len(res.issues), 0)

    def test_detects_existing_page_and_auto_converts(self):
        """Automatically converts {{ill|Title|en|Target}} to [[Title]] if it already exists."""
        wikitext = "* {{ill|Agen cerdas|en|Intelligent agent}}\n* {{ill|ChatGPT|en|ChatGPT|lt=Chat Bot}}"
        converted, count = self.validator.auto_convert_existing_links(wikitext)
        self.assertEqual(count, 2)
        self.assertIn("[[Agen cerdas]]", converted)
        self.assertIn("[[ChatGPT|Chat Bot]]", converted)
        self.assertNotIn("{{ill|Agen cerdas", converted)
        self.assertNotIn("{{ill|ChatGPT", converted)

    def test_invalid_language_code(self):
        """Detects invalid language codes in parameter 2."""
        wikitext = "{{ill|Model dasar|invalid_code|Foundation model}}"
        res = self.validator.validate_wikitext(wikitext)
        self.assertFalse(res.is_valid)
        issue_types = [i.issue_type for i in res.issues]
        self.assertIn("invalid_lang_code", issue_types)

    def test_indonesian_in_foreign_target(self):
        """Detects if foreign target parameter is in Indonesian."""
        wikitext = "{{ill|Model dasar|en|Pemberhentian dari perusahaan}}"
        res = self.validator.validate_wikitext(wikitext)
        self.assertFalse(res.is_valid)
        issue_types = [i.issue_type for i in res.issues]
        self.assertIn("indonesian_foreign_target", issue_types)

    def test_parse_ill_with_various_attributes(self):
        """Verifies parsing of {{ill}} with positional and named arguments."""
        parsed = self.validator.parse_ill("{{ill|Produk dan aplikasi OpenAI|en|Products and applications of OpenAI|lt=Produk}}")
        self.assertIsNotNone(parsed)
        id_title, lang, foreign_target, label = parsed
        self.assertEqual(id_title, "Produk dan aplikasi OpenAI")
        self.assertEqual(lang, "en")
        self.assertEqual(foreign_target, "Products and applications of OpenAI")
        self.assertEqual(label, "Produk")


if __name__ == "__main__":
    unittest.main()
