"""
Unit and Integration Tests for Token Saver, Cache, Delta Skip, and Token Optimization.
"""

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from wiki_translator.token_saver import (
    PROMPT_VERSION,
    SectionFilter,
    TokenCompressor,
    TokenTracker,
    TranslationCache,
    estimate_tokens,
)


class TestTokenCompressor(unittest.TestCase):
    """Tests for placeholder extraction and lossless rehydration."""

    def test_math_compression_and_decompress(self):
        text = (
            "The equation is defined as <math>\\psi(x, t) = A e^{i(kx - \\omega t)}</math> "
            "where <math>k = \\frac{2\\pi}{\\lambda}</math> is the wave number."
        )
        compressed = TokenCompressor.compress(text)
        self.assertIn("⟦MATH_0⟧", compressed.compressed_text)
        self.assertIn("⟦MATH_1⟧", compressed.compressed_text)
        self.assertNotIn("\\psi(x, t)", compressed.compressed_text)
        self.assertGreater(compressed.chars_saved, 0)
        self.assertGreater(compressed.token_savings_percent, 0)

        # Decompress
        translated_mock = (
            "Persamaan tersebut didefinisikan sebagai ⟦MATH_0⟧ "
            "dengan ⟦MATH_1⟧ adalah bilangan gelombang."
        )
        restored = TokenCompressor.decompress(translated_mock, compressed.placeholders)
        self.assertIn("<math>\\psi(x, t) = A e^{i(kx - \\omega t)}</math>", restored)
        self.assertIn("<math>k = \\frac{2\\pi}{\\lambda}</math>", restored)

    def test_ref_compression_and_decompress(self):
        text = (
            "Quantum computers use qubits.<ref>{{cite journal |last1=Deutsch |first1=D. |year=1985 "
            "|title=Quantum theory, the Church-Turing principle and the universal quantum computer "
            "|journal=Proc. R. Soc. Lond. A |volume=400 |pages=97-117 |doi=10.1098/rspa.1985.0070}}</ref> "
            "They also use superposition.<ref name=\"feynman1982\" />"
        )
        compressed = TokenCompressor.compress(text)
        self.assertIn("⟦REF_0⟧", compressed.compressed_text)
        self.assertIn("⟦REF_1⟧", compressed.compressed_text)
        self.assertNotIn("Deutsch", compressed.compressed_text)
        self.assertGreater(compressed.token_savings_percent, 50.0)

        # Rehydrate
        translated_mock = "Komputer kuantum memanfaatkan kubit.⟦REF_0⟧ Mereka juga menggunakan superposisi.⟦REF_1⟧"
        restored = TokenCompressor.decompress(translated_mock, compressed.placeholders)
        self.assertIn("{{cite journal", restored)
        self.assertIn("<ref name=\"feynman1982\" />", restored)

    def test_standalone_cite_template_compression(self):
        text = (
            "* {{cite book |author=Nielsen, M. A. |author2=Chuang, I. L. |year=2010 "
            "|title=Quantum Computation and Quantum Information |publisher=Cambridge University Press |isbn=978-1-107-00217-3}}"
        )
        compressed = TokenCompressor.compress(text)
        self.assertIn("⟦CITE_0⟧", compressed.compressed_text)
        self.assertNotIn("Nielsen", compressed.compressed_text)

        translated_mock = "* ⟦CITE_0⟧"
        restored = TokenCompressor.decompress(translated_mock, compressed.placeholders)
        self.assertEqual(restored, text)

    def test_code_and_chem_compression(self):
        text = (
            "Consider chemical formula <chem>H2O</chem> and python code:\n"
            "<syntaxhighlight lang=\"python\">\n"
            "def quantum_state():\n"
            "    return [1, 0]\n"
            "</syntaxhighlight>"
        )
        compressed = TokenCompressor.compress(text)
        self.assertIn("⟦MATH_0⟧", compressed.compressed_text)
        self.assertIn("⟦CODE_0⟧", compressed.compressed_text)

        translated_mock = "Perhatikan rumus kimia ⟦MATH_0⟧ dan kode python:\n⟦CODE_0⟧"
        restored = TokenCompressor.decompress(translated_mock, compressed.placeholders)
        self.assertIn("<chem>H2O</chem>", restored)
        self.assertIn("def quantum_state():", restored)

    def test_decompress_robustness_to_llm_bracket_modifications(self):
        """Tests that minor bracket distortions by LLMs are smoothly recovered."""
        placeholders = {
            "⟦REF_0⟧": "<ref>https://example.com</ref>",
            "⟦MATH_0⟧": "<math>E=mc^2</math>",
        }
        # Distorted variations: [REF_0], [[MATH_0]]
        test_text = "Teks dengan sitasi [REF_0] dan rumus [[MATH_0]]."
        restored = TokenCompressor.decompress(test_text, placeholders)
        self.assertIn("<ref>https://example.com</ref>", restored)
        self.assertIn("<math>E=mc^2</math>", restored)


class TestTranslationCache(unittest.TestCase):
    """Tests for SQLite persistent semantic cache (Headroom caching)."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "test_cache.db"
        self.cache = TranslationCache(str(self.db_path))

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_cache_put_and_get(self):
        src = "== History ==\nQuantum computers were proposed in the 1980s."
        tr = "== Sejarah ==\nKomputer kuantum diusulkan pada dekade 1980-an."
        title = "History"
        topic = "computing_science"

        # Initially miss
        self.assertIsNone(self.cache.get(src, title, topic))
        self.assertEqual(self.cache.count(), 0)

        # Put
        self.cache.put(src, tr, title, topic)
        self.assertEqual(self.cache.count(), 1)

        # Hit
        cached_val = self.cache.get(src, title, topic)
        self.assertEqual(cached_val, tr)

        # Different topic -> miss
        self.assertIsNone(self.cache.get(src, title, "medical_biology"))

        # Clear
        self.cache.clear()
        self.assertEqual(self.cache.count(), 0)
        self.assertIsNone(self.cache.get(src, title, topic))


class TestSectionFilterDeltaSkip(unittest.TestCase):
    """Tests for smart delta skipping on boilerplate sections."""

    def test_references_section_skip(self):
        title = "References"
        content = "{{reflist}}\n{{Reflist|30em}}"
        can_skip, body = SectionFilter.can_skip_llm(title, content)
        self.assertTrue(can_skip)
        self.assertEqual(body, content)

    def test_external_links_section_skip(self):
        title = "External links"
        content = (
            "* [https://qiskit.org Qiskit official website]\n"
            "* [https://quantumai.google Google Quantum AI]\n"
            "{{Authority control}}"
        )
        can_skip, body = SectionFilter.can_skip_llm(title, content)
        self.assertTrue(can_skip)
        self.assertEqual(body, content)

    def test_prose_section_not_skipped(self):
        title = "History"
        content = "In 1980, Paul Benioff described the first quantum mechanical model."
        can_skip, body = SectionFilter.can_skip_llm(title, content)
        self.assertFalse(can_skip)
        self.assertIsNone(body)


class TestTokenTracker(unittest.TestCase):
    """Tests for token usage counting, savings calculations, and dashboard rendering."""

    def test_token_tracker_metrics(self):
        tracker = TokenTracker()

        # 1. Cache hit: 1000 raw chars (~263 tokens)
        src = "A" * 1000
        tr = "B" * 1000
        tracker.record_cache_hit(src, tr)
        self.assertEqual(tracker.cache_hits, 1)
        self.assertEqual(tracker.total_optimized_tokens, 0)
        self.assertGreater(tracker.total_raw_tokens, 0)
        self.assertEqual(tracker.savings_percent, 100.0)

        # 2. Delta skip
        tracker.record_delta_skip(src, tr)
        self.assertEqual(tracker.delta_skips, 1)
        self.assertEqual(tracker.total_optimized_tokens, 0)

        # 3. LLM call with compression
        raw_src = "Quantum computing <ref>" + "cite journal" * 50 + "</ref>"
        comp_src = "Quantum computing ⟦REF_0⟧"
        raw_out = "Komputer kuantum <ref>" + "cite journal" * 50 + "</ref>"
        comp_out = "Komputer kuantum ⟦REF_0⟧"

        tracker.record_llm_call(raw_src, comp_src, raw_out, comp_out)
        self.assertEqual(tracker.compressed_sections, 1)
        self.assertGreater(tracker.total_raw_tokens, tracker.total_optimized_tokens)
        self.assertGreater(tracker.savings_percent, 0.0)

        # 4. Summary table rendering
        table = tracker.get_summary_table()
        self.assertIn("OMP TOKEN SAVER & OPTIMIZATION DASHBOARD", table)
        self.assertIn("Total Raw Tokens", table)
        self.assertIn("Optimized Tokens Sent/Received via LLM", table)
        self.assertIn("Total Tokens Saved", table)


if __name__ == "__main__":
    unittest.main()
