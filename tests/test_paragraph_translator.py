"""
Unit tests for Context-Aware Paragraph-by-Paragraph Translation Engine.
"""

import unittest
from unittest.mock import MagicMock, call

from wiki_translator.paragraph_translator import (
    ParagraphTranslator,
    default_paragraph_translator,
    split_into_paragraph_chunks,
)


class TestParagraphTranslator(unittest.TestCase):
    def setUp(self):
        self.translator = ParagraphTranslator(max_chunk_words=50)

    def test_split_empty_text(self):
        chunks = split_into_paragraph_chunks("")
        self.assertEqual(chunks, [])

    def test_split_single_paragraph(self):
        text = "This is a single paragraph about Wikipedia articles."
        chunks = split_into_paragraph_chunks(text)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["type"], "prose")
        self.assertEqual(chunks[0]["content"], text)
        self.assertEqual(chunks[0]["index"], 0)

    def test_atomic_table_preservation(self):
        text = """First introductory paragraph.

{| class="wikitable"
|+ Table Title
|-
! Header 1 !! Header 2
|-
| Cell 1 || Cell 2
|}

Second concluding paragraph."""
        chunks = split_into_paragraph_chunks(text)
        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0]["type"], "prose")
        self.assertEqual(chunks[0]["content"], "First introductory paragraph.")

        self.assertEqual(chunks[1]["type"], "table")
        self.assertTrue(chunks[1]["content"].startswith("{|"))
        self.assertTrue(chunks[1]["content"].endswith("|}"))
        self.assertIn("Cell 1", chunks[1]["content"])

        self.assertEqual(chunks[2]["type"], "prose")
        self.assertEqual(chunks[2]["content"], "Second concluding paragraph.")

    def test_atomic_infobox_and_template_preservation(self):
        text = """{{Infobox film
| name = Oppenheimer
| director = Christopher Nolan
| starring = Cillian Murphy
}}

Oppenheimer is a 2023 epic biographical thriller film.

{{Navbox
| name = Christopher Nolan
| title = Films directed by Christopher Nolan
}}"""
        chunks = split_into_paragraph_chunks(text)
        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0]["type"], "infobox")
        self.assertTrue(chunks[0]["content"].startswith("{{Infobox"))
        self.assertTrue(chunks[0]["content"].endswith("}}"))

        self.assertEqual(chunks[1]["type"], "prose")
        self.assertEqual(
            chunks[1]["content"],
            "Oppenheimer is a 2023 epic biographical thriller film.",
        )

        self.assertEqual(chunks[2]["type"], "template")
        self.assertTrue(chunks[2]["content"].startswith("{{Navbox"))

    def test_inline_template_not_split_from_prose(self):
        text = """This is a paragraph with {{cite web|url=https://example.com|title=Example}} inline citation.

Second paragraph here."""
        # Split with 0 max_chunk_words or max_chunk_words=10 to preserve paragraphs separately
        chunks = split_into_paragraph_chunks(text, max_chunk_words=10)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0]["type"], "prose")
        self.assertIn("{{cite web", chunks[0]["content"])
        self.assertEqual(chunks[1]["type"], "prose")

    def test_multi_paragraph_chunk_grouping_by_max_words(self):
        p1 = "Word " * 20  # 20 words
        p2 = "Word " * 10  # 10 words (total 30 <= 35)
        p3 = "Word " * 15  # 15 words (total 45 > 35 -> chunk 2)
        wikitext = f"{p1.strip()}\n\n{p2.strip()}\n\n{p3.strip()}"

        chunks = split_into_paragraph_chunks(wikitext, max_chunk_words=35)
        self.assertEqual(len(chunks), 2)
        # First chunk has p1 + p2 = 30 words
        self.assertEqual(chunks[0]["type"], "prose")
        self.assertIn(p1.strip(), chunks[0]["content"])
        self.assertIn(p2.strip(), chunks[0]["content"])
        # Second chunk has p3
        self.assertEqual(chunks[1]["type"], "prose")
        self.assertEqual(chunks[1]["content"], p3.strip())

    def test_translate_section_single_paragraph_direct(self):
        mock_translator = MagicMock(return_value="Ini adalah satu paragraf.")
        result = self.translator.translate_section_by_paragraphs(
            section_title="Introduction",
            wikitext="This is one paragraph.",
            translator_func=mock_translator,
            topic="film",
        )

        self.assertEqual(result, "Ini adalah satu paragraf.")
        self.assertEqual(mock_translator.call_count, 1)
        prompt_arg = mock_translator.call_args[0][0]
        self.assertIn("This is one paragraph.", prompt_arg)
        self.assertNotIn("Bagian Paragraf 1 dari 1", prompt_arg)

    def test_translate_section_multi_paragraph_context_injection(self):
        p1 = "The production of the film began in 2021 in London. " * 3  # ~30 words
        p2 = "Principal photography wrapped after six months of intense shooting. " * 3  # ~27 words
        p3 = "Post-production and editing took another year to finalize the visual effects. " * 3  # ~33 words
        wikitext = f"== Production ==\n{p1}\n\n{p2}\n\n{p3}"

        translations = [
            "== Produksi ==\nProduksi film ini dimulai pada tahun 2021 di London.",
            "Pengambilan gambar utama rampung setelah enam bulan syuting intensif.",
            "Pascaproduksi dan penyuntingan memakan waktu satu tahun lagi.",
        ]
        call_idx = 0

        def mock_translate_fn(prompt: str, sys_inst=None) -> str:
            nonlocal call_idx
            res = translations[call_idx]
            call_idx += 1
            return res

        stream_calls = []
        result = self.translator.translate_section_by_paragraphs(
            section_title="Production",
            wikitext=wikitext,
            translator_func=mock_translate_fn,
            topic="film",
            stream_callback=stream_calls.append,
        )

        # Ensure all 3 chunks were translated and reassembled
        self.assertEqual(call_idx, 3)
        self.assertIn("== Produksi ==", result)
        self.assertIn("Pengambilan gambar utama rampung", result)
        self.assertIn("Pascaproduksi dan penyuntingan", result)

        # Verify reassembly spacing
        expected_assembled = "\n\n".join(translations)
        self.assertEqual(result, expected_assembled)

    def test_translate_section_preceding_context_content(self):
        prompts_received = []

        def mock_translate_fn(prompt: str, sys_inst=None) -> str:
            prompts_received.append(prompt)
            return f"Terjemahan {len(prompts_received)}"

        wikitext = "Paragraph 1.\n\nParagraph 2.\n\nParagraph 3."
        # Use small max_chunk_words to force 3 separate chunks
        translator = ParagraphTranslator(max_chunk_words=2)
        translator.translate_section_by_paragraphs(
            section_title="History",
            wikitext=wikitext,
            translator_func=mock_translate_fn,
        )

        self.assertEqual(len(prompts_received), 3)

        # First chunk prompt should not contain preceding context summary
        self.assertNotIn("Konteks terjemahan paragraf sebelumnya", prompts_received[0])

        # Second chunk prompt should contain chunk 1 translation in context
        self.assertIn("Konteks terjemahan paragraf sebelumnya", prompts_received[1])
        self.assertIn("Terjemahan 1", prompts_received[1])

        # Third chunk prompt should contain recent translated context
        self.assertIn("Konteks terjemahan paragraf sebelumnya", prompts_received[2])
        self.assertIn("Terjemahan 2", prompts_received[2])

    def test_gemini_client_translate_section_by_paragraphs_method(self):
        from wiki_translator.gemini import GeminiTranslatorClient

        client = GeminiTranslatorClient.__new__(GeminiTranslatorClient)
        client.preferred_model = "gemini-3.8-flash"
        client.thinking_level = "low"

        calls = []

        def fake_translate_section(user_prompt, **kwargs):
            calls.append(user_prompt)
            return f"Translated: {len(calls)}"

        client.translate_section = fake_translate_section

        # Long enough paragraphs to exceed default_paragraph_translator.max_chunk_words (250) or use custom words
        p1 = "First paragraph here with lots of detailed descriptive text. " * 30  # ~300 words
        p2 = "Second paragraph here with lots of detailed descriptive text. " * 30  # ~300 words
        wikitext = f"{p1}\n\n{p2}"
        res = client.translate_section_by_paragraphs(
            section_title="Overview",
            wikitext=wikitext,
            topic="film",
        )

        self.assertEqual(len(calls), 2)
        self.assertEqual(res, "Translated: 1\n\nTranslated: 2")


if __name__ == "__main__":
    unittest.main()
