"""
Comprehensive Unit and Integration Tests for Dynamic Terminology & Exonym Resolver.

Covers:
1. Candidate term extraction (wikilinks, capitalized entities, quotes, italics, hyphenated nouns)
2. Term resolution precedence (custom glossary -> topic glossary -> base exonyms -> SQLite cache -> Wikipedia API)
3. Wikipedia Langlinks API fetching and batching (mocked responses, error resilience)
4. Local SQLite cache persistence (caching hits, negative results, 0 network lookups when cached)
5. Dynamic injection into translation prompts under `GLOSARIUM SPESIFIK UNTUK BAGIAN INI:`
6. CLI integration (--auto-glossary / --no-glossary / --resolve-terms)
"""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from wiki_translator.cli import WikiTranslatorCLI, main
from wiki_translator.glossary_resolver import (
    BASE_EXONYMS_AND_TERMS,
    GlossaryResolver,
    clean_wikitext_for_extraction,
    extract_candidate_terms,
)
from wiki_translator.prompts import build_translation_prompt


class TestCandidateTermExtraction(unittest.TestCase):
    """Tests heuristic extraction of candidate terms from English wikitext."""

    def test_extract_wikilinks(self):
        wikitext = (
            "In [[quantum computing]], a [[qubit|quantum bit]] is the basic unit of information. "
            "See [[Category:Physics]] and [[File:Quantum.jpg|thumb|diagram]]."
        )
        terms = extract_candidate_terms(wikitext)
        self.assertIn("quantum computing", terms)
        self.assertIn("qubit", terms)
        self.assertIn("quantum bit", terms)
        # Ensure category and file links are excluded
        self.assertNotIn("Category:Physics", terms)
        self.assertNotIn("File:Quantum.jpg", terms)

    def test_extract_capitalized_multiword_and_exonyms(self):
        wikitext = (
            "Albert Einstein published his theory in the United States and Germany after visiting Japan."
        )
        terms = extract_candidate_terms(wikitext)
        self.assertIn("Albert Einstein", terms)
        self.assertIn("United States", terms)
        self.assertIn("Germany", terms)
        self.assertIn("Japan", terms)

    def test_extract_quotes_and_italics(self):
        wikitext = (
            "The phenomenon is known as ''quantum entanglement'' or \"wave-particle duality\"."
        )
        terms = extract_candidate_terms(wikitext)
        self.assertIn("quantum entanglement", terms)
        self.assertIn("wave-particle duality", terms)

    def test_clean_wikitext_removes_refs_comments_and_templates(self):
        raw = (
            "Text before <!-- comment with Fake Term --> and {{Infobox | title = Ignored }} "
            "<ref name='test'>Ref Content</ref><math>E = mc^2</math> Text after."
        )
        cleaned = clean_wikitext_for_extraction(raw)
        self.assertNotIn("Fake Term", cleaned)
        self.assertNotIn("Infobox", cleaned)
        self.assertNotIn("Ref Content", cleaned)
        self.assertNotIn("E = mc^2", cleaned)
        self.assertIn("Text before", cleaned)
        self.assertIn("Text after", cleaned)


class TestGlossaryResolver(unittest.TestCase):
    """Tests GlossaryResolver cache, resolution, and Wikipedia API interaction."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_db = Path(self.temp_dir.name) / "glossary_cache.db"
        self.resolver = GlossaryResolver(cache_db_path=str(self.cache_db))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_sqlite_schema_creation_and_caching(self):
        self.resolver.cache_term("Quantum computer", "Komputer kuantum", source="test")
        cached = self.resolver.get_cached_term("quantum computer")
        self.assertIsNotNone(cached)
        self.assertEqual(cached[0], "Komputer kuantum")
        self.assertEqual(cached[1], "test")

        # Test negative caching (term without Indonesian page)
        self.resolver.cache_term("ObscureTermXyz", None, source="test_neg")
        cached_neg = self.resolver.get_cached_term("ObscureTermXyz")
        self.assertIsNotNone(cached_neg)
        self.assertIsNone(cached_neg[0])

    def test_resolve_from_topic_glossary_and_base_exonyms(self):
        # From base exonyms
        res_us = self.resolver.resolve_term("United States", allow_network=False)
        self.assertEqual(res_us, "Amerika Serikat")

        res_nl = self.resolver.resolve_term("Netherlands", allow_network=False)
        self.assertEqual(res_nl, "Belanda")

        # From topic glossary
        res_qc = self.resolver.resolve_term(
            "quantum computing", topic="computing_science", allow_network=False
        )
        self.assertEqual(res_qc, "komputasi kuantum")
        custom = {"custom widget": "gawai kustom"}
        res_custom = self.resolver.resolve_term(
            "custom widget", custom_glossary=custom, allow_network=False
        )
        self.assertEqual(res_custom, "gawai kustom")

    @patch("urllib.request.urlopen")
    def test_wikipedia_langlinks_api_resolution(self, mock_urlopen):
        mock_response_data = {
            "query": {
                "pages": [
                    {
                        "title": "Quantum computing",
                        "langlinks": [
                            {"lang": "fr", "title": "Informatique quantique"},
                            {"lang": "id", "title": "Komputasi kuantum"},
                        ],
                    },
                    {
                        "title": "Superposition principle",
                        "langlinks": [
                            {"lang": "id", "title": "Prinsip superposisi"},
                        ],
                    },
                    {
                        "title": "NonExistentPage",
                        "langlinks": [],
                    },
                ]
            }
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_response_data).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        results = self.resolver.fetch_wikipedia_langlinks(
            ["Quantum computing", "Superposition principle", "NonExistentPage"]
        )

        self.assertEqual(results.get("Quantum computing"), "Komputasi kuantum")
        self.assertEqual(results.get("Superposition principle"), "Prinsip superposisi")
        self.assertIsNone(results.get("NonExistentPage"))

    @patch("urllib.request.urlopen")
    def test_zero_network_cost_on_cached_terms(self, mock_urlopen):
        # Pre-seed cache
        self.resolver.cache_term("Machine learning", "Pembelajaran mesin", source="test")

        resolved = self.resolver.resolve_term("Machine learning", allow_network=True)
        self.assertEqual(resolved, "Pembelajaran mesin")
        # Ensure network urlopen was never called
        mock_urlopen.assert_not_called()

    @patch.object(GlossaryResolver, "fetch_wikipedia_langlinks")
    def test_resolve_section_terms(self, mock_fetch):
        mock_fetch.return_value = {
            "Superconducting quantum computing": "Komputasi kuantum superkonduksi",
            "superconducting quantum computing": "Komputasi kuantum superkonduksi",
        }

        wikitext = (
            "== Technology ==\n"
            "In the United States and Germany, researchers study [[Superconducting quantum computing]] "
            "using advanced [[qubit]] designs."
        )

        resolved = self.resolver.resolve_section_terms(
            wikitext=wikitext,
            topic="computing_science",
            allow_network=True,
        )

        # Built-in topic/base terms
        self.assertIn("United States", resolved)
        self.assertEqual(resolved["United States"], "Amerika Serikat")
        self.assertIn("Germany", resolved)
        self.assertEqual(resolved["Germany"], "Jerman")
        self.assertIn("qubit", resolved)
        self.assertEqual(resolved["qubit"], "kubit")

        # Wikipedia API resolved term
        self.assertIn("Superconducting quantum computing", resolved)
        self.assertEqual(
            resolved["Superconducting quantum computing"],
            "Komputasi kuantum superkonduksi",
        )

    def test_resolve_film_and_tv_terms(self):
        wikitext = (
            "== Production and Reception ==\n"
            "The [[feature film]] began [[principal photography]] under the [[showrunner]] and "
            "director of photography. It was a major [[box office]] hit, receiving positive "
            "[[critical reception]] on Rotten Tomatoes and Metacritic with high [[approval rating]], "
            "culminating in an [[Academy Awards]] nomination for its [[original score]]."
        )

        resolved = self.resolver.resolve_section_terms(
            wikitext=wikitext,
            topic="film",
            allow_network=False,
        )

        self.assertIn("feature film", resolved)
        self.assertIn("principal photography", resolved)
        self.assertIn("showrunner", resolved)
        self.assertIn("box office", resolved)
        self.assertIn("critical reception", resolved)
        self.assertIn("original score", resolved)
        self.assertIn("academy awards", resolved)
        self.assertEqual(resolved["feature film"], "film cerita panjang / film panjang")
        self.assertEqual(resolved["principal photography"], "pengambilan gambar utama")
        self.assertEqual(resolved["academy awards"], "Academy Awards (Piala Oscar)")

    def test_tv_series_topic_glossary(self):
        wikitext = (
            "The [[pilot episode]] served as the [[season premiere]], followed by a recurring role "
            "and a cliffhanger [[season finale]] on the [[streaming service]] miniseries."
        )
        resolved = self.resolver.resolve_section_terms(
            wikitext=wikitext,
            topic="tv_series",
            allow_network=False,
        )
        self.assertIn("pilot episode", resolved)
        self.assertIn("season premiere", resolved)
        self.assertIn("season finale", resolved)
        self.assertIn("miniseries", resolved)
        self.assertIn("streaming service", resolved)
        self.assertEqual(resolved["pilot episode"], "episode perintis / episode pilot")
        self.assertEqual(resolved["miniseries"], "serial mini")

    def test_idiom_and_phrase_resolution(self):
        wikitext = (
            "The initiative stayed under the radar and was a game-changer. "
            "It was a race against time, and though bittersweet, there was a silver lining."
        )
        resolved = self.resolver.resolve_section_terms(
            wikitext=wikitext,
            allow_network=False,
        )
        self.assertIn("under the radar", resolved)
        self.assertIn("game-changer", resolved)
        self.assertIn("race against time", resolved)
        self.assertIn("bittersweet", resolved)
        self.assertIn("silver lining", resolved)
        self.assertEqual(resolved["under the radar"], "tanpa banyak diketahui / diam-diam")
        self.assertEqual(resolved["game-changer"], "pengubah keadaan / terobosan besar")
        self.assertEqual(resolved["race against time"], "berlomba dengan waktu")
        self.assertEqual(resolved["bittersweet"], "bercampur haru / manis dan pahit")
        self.assertEqual(resolved["silver lining"], "hikmah / sisi positif")

    def test_candidate_extraction_detects_idioms(self):
        wikitext = "They realized it was only the tip of the iceberg and decided to nip in the bud."
        terms = extract_candidate_terms(wikitext)
        self.assertIn("tip of the iceberg", terms)
        self.assertIn("nip in the bud", terms)

class TestPromptInjection(unittest.TestCase):
    """Tests dynamic injection of resolved terms into user prompts."""

    def test_prompt_contains_resolved_glossary_section(self):
        resolved = {
            "United States": "Amerika Serikat",
            "Quantum gate": "Gerbang kuantum",
        }
        prompt = build_translation_prompt(
            section_title="Architecture",
            wikitext_content="Sample wikitext",
            resolved_glossary=resolved,
        )

        self.assertIn("### GLOSARIUM SPESIFIK UNTUK BAGIAN INI:", prompt)
        self.assertIn('- "United States" -> "Amerika Serikat"', prompt)
        self.assertIn('- "Quantum gate" -> "Gerbang kuantum"', prompt)

    def test_prompt_without_resolved_glossary(self):
        prompt = build_translation_prompt(
            section_title="Architecture",
            wikitext_content="Sample wikitext",
        )
        self.assertNotIn("### GLOSARIUM SPESIFIK UNTUK BAGIAN INI:", prompt)


class TestCLIIntegration(unittest.TestCase):
    """Tests CLI arguments and configuration for auto glossary."""

    def test_cli_default_auto_glossary_enabled(self):
        cli = WikiTranslatorCLI()
        self.assertTrue(cli.enable_auto_glossary)
        self.assertIsNotNone(cli.glossary_resolver)

    def test_cli_disable_auto_glossary(self):
        cli = WikiTranslatorCLI(enable_auto_glossary=False)
        self.assertFalse(cli.enable_auto_glossary)

    def test_cli_argument_parser_flags(self):
        # Test parser behavior with --auto-glossary and --no-glossary
        with patch("sys.argv", ["wiki_translator", "Quantum computing", "--no-glossary"]):
            with patch("wiki_translator.cli.WikiTranslatorCLI") as mock_cli:
                main()
                mock_cli.assert_called_once()
                _, kwargs = mock_cli.call_args
                self.assertFalse(kwargs["enable_auto_glossary"])

        with patch("sys.argv", ["wiki_translator", "Quantum computing", "--resolve-terms"]):
            with patch("wiki_translator.cli.WikiTranslatorCLI") as mock_cli:
                main()
                mock_cli.assert_called_once()
                _, kwargs = mock_cli.call_args
                self.assertTrue(kwargs["enable_auto_glossary"])


if __name__ == "__main__":
    unittest.main()
