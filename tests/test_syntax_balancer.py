"""
Unit tests for WikitextSyntaxBalancer (wiki_translator/syntax_balancer.py).
"""

import unittest
from wiki_translator.syntax_balancer import (
    WikitextSyntaxBalancer,
    default_syntax_balancer,
)


class TestWikitextSyntaxBalancer(unittest.TestCase):
    def setUp(self):
        self.balancer = WikitextSyntaxBalancer()

    # ----------------------------------------------------
    # 1. Wikilinks [[ ... ]] Tests
    # ----------------------------------------------------
    def test_wikilinks_balanced(self):
        text = "Ini adalah [[Indonesia]] dan [[Jakarta|ibu kota]]."
        issues = self.balancer.check_balance(text)
        self.assertEqual(len(issues), 0)
        repaired = self.balancer.auto_repair(text)
        self.assertEqual(repaired, text)

    def test_wikilinks_unclosed_repair(self):
        text = "Lihat artikel [[Indonesia untuk info lebih lanjut."
        issues = self.balancer.check_balance(text)
        self.assertTrue(any(i["tag_type"] == "wikilink" for i in issues))
        repaired = self.balancer.auto_repair(text)
        self.assertIn("[[Indonesia]]", repaired)

    def test_wikilinks_extra_closing_repair(self):
        text = "Teks ini memiliki closing berlebih]]."
        issues = self.balancer.check_balance(text)
        self.assertTrue(any(i["tag_type"] == "wikilink" for i in issues))
        repaired = self.balancer.auto_repair(text)
        self.assertNotIn("]]", repaired)

    # ----------------------------------------------------
    # 2. Templates {{ ... }} Tests
    # ----------------------------------------------------
    def test_templates_balanced(self):
        text = "{{Utama|Sejarah Indonesia}}\n{{Infobox film|title=Film}}"
        issues = self.balancer.check_balance(text)
        self.assertEqual(len(issues), 0)
        repaired = self.balancer.auto_repair(text)
        self.assertEqual(repaired, text)

    def test_templates_unclosed_repair(self):
        text = "{{Utama|Sejarah Indonesia\nArtikel lanjutan..."
        issues = self.balancer.check_balance(text)
        self.assertTrue(any(i["tag_type"] == "template" for i in issues))
        repaired = self.balancer.auto_repair(text)
        self.assertTrue(repaired.endswith("}}") or "}}" in repaired)
        repaired_issues = self.balancer.check_balance(repaired)
        self.assertFalse(any(i["tag_type"] == "template" for i in repaired_issues))

    def test_templates_nested(self):
        text = "{{cite web|url=https://example.com|title={{lang|en|Hello}}}}"
        issues = self.balancer.check_balance(text)
        self.assertEqual(len(issues), 0)

    # ----------------------------------------------------
    # 3. Citation / Footnote <ref> Tags Tests
    # ----------------------------------------------------
    def test_ref_tags_balanced_and_self_closing(self):
        text = 'Pernyataan satu.<ref name="ref1">Sumber 1</ref> Pernyataan dua.<ref name="ref1" />'
        issues = self.balancer.check_balance(text)
        self.assertEqual(len(issues), 0)
        self.assertEqual(self.balancer.auto_repair(text), text)

    def test_ref_tags_unclosed_repair(self):
        text = 'Kota ini didirikan pada tahun 1900.<ref name="sejarah">Buku Sejarah\n== Pemerintahan =='
        issues = self.balancer.check_balance(text)
        self.assertTrue(any(i["tag_type"] == "ref" for i in issues))
        repaired = self.balancer.auto_repair(text)
        self.assertIn("</ref>", repaired)
        repaired_issues = self.balancer.check_balance(repaired)
        self.assertFalse(any(i["tag_type"] == "ref" for i in repaired_issues))

    def test_ref_tags_unmatched_closing(self):
        text = "Teks tanpa pembuka.</ref>"
        issues = self.balancer.check_balance(text)
        self.assertTrue(any(i["tag_type"] == "ref" for i in issues))

    def test_ref_tags_orphan_self_closing_detected(self):
        text = 'Alfred Lewis Enoch<ref name="TV Guide" /> lahir di London.'
        issues = self.balancer.check_balance(text)
        self.assertTrue(any(i["tag_type"] == "ref" and "TV Guide" in i["description"] for i in issues))

    def test_ref_tags_orphan_self_closing_safely_removed(self):
        text = 'Alfred Lewis Enoch<ref name="TV Guide" /> lahir di London.'
        repaired = self.balancer.auto_repair(text)
        self.assertNotIn('<ref name="TV Guide"', repaired)
        self.assertIn("Alfred Lewis Enoch lahir di London.", repaired)

    def test_ref_tags_orphan_self_closing_resolved_from_source(self):
        text = 'Alfred Lewis Enoch<ref name="TV Guide" /> lahir di London.'
        source_en = 'Enoch was born in London.<ref name="TV Guide">{{cite web|title=TVG}}</ref>'
        resolved = self.balancer.resolve_orphan_references(text, source_en_wikitext=source_en)
        self.assertIn('<ref name="TV Guide">{{cite web|title=TVG}}</ref>', resolved)
    # ----------------------------------------------------
    # 4. Wikitables {| ... |} Tests
    # ----------------------------------------------------
    def test_wikitable_balanced(self):
        text = "{| class=\"wikitable\"\n! Kolom 1 !! Kolom 2\n|-\n| A || B\n|}"
        issues = self.balancer.check_balance(text)
        self.assertEqual(len(issues), 0)
        self.assertEqual(self.balancer.auto_repair(text), text)

    def test_wikitable_unclosed_repair(self):
        text = "{| class=\"wikitable\"\n! Header 1\n|-\n| Data 1"
        issues = self.balancer.check_balance(text)
        self.assertTrue(any(i["tag_type"] == "wikitable" for i in issues))
        repaired = self.balancer.auto_repair(text)
        self.assertTrue(repaired.strip().endswith("|}") or "|}" in repaired)
        repaired_issues = self.balancer.check_balance(repaired)
        self.assertFalse(any(i["tag_type"] == "wikitable" for i in repaired_issues))

    # ----------------------------------------------------
    # 5. Formatting Tags: ''', '', <code>, <blockquote>, <nowiki>
    # ----------------------------------------------------
    def test_formatting_quotes_balanced(self):
        text = "Ini '''tebal''' dan ini ''miring'' serta '''''tebal miring'''''."
        issues = self.balancer.check_balance(text)
        self.assertEqual(len(issues), 0)

    def test_formatting_quotes_unbalanced_repair(self):
        text = "Ini '''tebal tanpa penutup\nBaris berikutnya ''miring tanpa penutup"
        issues = self.balancer.check_balance(text)
        self.assertTrue(any(i["tag_type"] in ("bold", "italic") for i in issues))
        repaired = self.balancer.auto_repair(text)
        repaired_issues = self.balancer.check_balance(repaired)
        self.assertFalse(any(i["tag_type"] in ("bold", "italic") for i in repaired_issues))

    def test_html_tags_unclosed_repair(self):
        text = "Gunakan kode <code>const x = 10; dan kutipan <blockquote>Kutipan hebat"
        issues = self.balancer.check_balance(text)
        self.assertTrue(any(i["tag_type"] in ("code", "blockquote") for i in issues))
        repaired = self.balancer.auto_repair(text)
        self.assertIn("</code>", repaired)
        self.assertIn("</blockquote>", repaired)

    def test_nowiki_masking(self):
        text = "Contoh: <nowiki>[[Bukan Tautan]] dan {{Bukan Templat}}</nowiki>"
        issues = self.balancer.check_balance(text)
        self.assertEqual(len(issues), 0)

    def test_default_instance(self):
        self.assertIsNotNone(default_syntax_balancer)
        res = default_syntax_balancer.check_balance("[[Link]]")
        self.assertEqual(res, [])


if __name__ == "__main__":
    unittest.main()
