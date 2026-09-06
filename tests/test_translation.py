"""
Comprehensive Unit and Edge-Case Tests for Wikipedia Translator.

Covers:
1. Nested section splitting (==, ===, ====, =====, ======)
2. Preservation of wikitext structures:
   - Multiline tables ({| ... |}) containing pseudo-headers
   - Infoboxes / multiline templates ({{ ... }})
   - <math>...</math> blocks
   - <ref>...</ref> blocks and <ref name="..." />
   - HTML comments (<!-- ... -->)
3. Wikipedia API Error & Edge Case handling:
   - Disambiguation page detection
   - Missing page handling
   - Rate limit (HTTP 429) simulation
   - Redirect parameter verification
4. Token refresh robustness & SQLite persistence
5. SSE streaming parser edge cases (multiline buffers, comments, [DONE], thoughts)
6. Prompt formatting & Glossary composition
"""

import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from wiki_translator.auth import AntigravityCredential, AuthManager
from wiki_translator.gemini import GeminiTranslatorClient
from wiki_translator.prompts import (
    SYSTEM_PROMPT_GRADE_A_PLUS_PLUS,
    TOPIC_GLOSSARIES,
    build_translation_prompt,
)
from wiki_translator.wiki_client import (
    DisambiguationPageError,
    PageNotFoundError,
    RateLimitExceededError,
    WikipediaAPIError,
    WikipediaClient,
    WikiSection,
)


class TestSectionSplittingAndMarkupPreservation(unittest.TestCase):
    """Tests for section splitting hierarchy and preservation of complex wikitext structures."""

    def setUp(self):
        self.client = WikipediaClient()

    def test_nested_sections_hierarchy(self):
        wikitext = (
            "Lead paragraph text.\n\n"
            "== Level 2 Section ==\n"
            "Content under level 2.\n\n"
            "=== Level 3 Subsection ===\n"
            "Content under level 3.\n\n"
            "==== Level 4 Sub-subsection ====\n"
            "Content under level 4.\n\n"
            "===== Level 5 =====\n"
            "Content under level 5.\n\n"
            "====== Level 6 ======\n"
            "Content under level 6.\n"
        )
        sections = self.client.split_sections(wikitext)
        self.assertEqual(len(sections), 6)

        self.assertEqual(sections[0].level, 1)
        self.assertEqual(sections[0].title, "Lead / Pengantar Utama")

        self.assertEqual(sections[1].level, 2)
        self.assertEqual(sections[1].title, "Level 2 Section")

        self.assertEqual(sections[2].level, 3)
        self.assertEqual(sections[2].title, "Level 3 Subsection")

        self.assertEqual(sections[3].level, 4)
        self.assertEqual(sections[3].title, "Level 4 Sub-subsection")

        self.assertEqual(sections[4].level, 5)
        self.assertEqual(sections[4].title, "Level 5")

        self.assertEqual(sections[5].level, 6)
        self.assertEqual(sections[5].title, "Level 6")

    def test_table_preservation_with_internal_equal_signs(self):
        """Tables with {| ... == Pseudo Header == ... |} must NOT be split into sections."""
        wikitext = (
            "Lead introduction.\n\n"
            "== Data Section ==\n"
            "Here is a table:\n"
            "{|\n"
            "! Header 1 !! Header 2\n"
            "|-\n"
            "| == Not A Section == || Some value\n"
            "| Value 2 || Value 3\n"
            "|}\n\n"
            "=== Real Subsection ===\n"
            "Subsection body."
        )
        sections = self.client.split_sections(wikitext)
        self.assertEqual(len(sections), 3)
        self.assertEqual(sections[1].title, "Data Section")
        self.assertIn("== Not A Section ==", sections[1].content)
        self.assertIn("{|", sections[1].content)
        self.assertIn("|}", sections[1].content)
        self.assertEqual(sections[2].title, "Real Subsection")

    def test_multiline_template_and_infobox_preservation(self):
        """Infoboxes and nested templates with inner headers must remain intact."""
        wikitext = (
            "{{Infobox computer\n"
            "| name = Quantum Alpha\n"
            "| caption = {{nested template | key = == fake == }}\n"
            "| developer = Lab\n"
            "}}\n"
            "Quantum Alpha is an experimental platform.\n\n"
            "== Architecture ==\n"
            "Architecture details."
        )
        sections = self.client.split_sections(wikitext)
        self.assertEqual(len(sections), 2)
        self.assertEqual(sections[0].level, 1)
        self.assertIn("{{Infobox computer", sections[0].content)
        self.assertIn("Quantum Alpha is an experimental platform.", sections[0].content)
        self.assertEqual(sections[1].title, "Architecture")

    def test_math_and_ref_block_preservation(self):
        """<math> and <ref> blocks with == inside must not be parsed as headings."""
        wikitext = (
            "Lead equation explanation.\n\n"
            "== Formulas ==\n"
            "Math block:\n"
            "<math>\n"
            "E == m c^2\n"
            "</math>\n"
            "Reference with note:<ref name=\"test\">\n"
            "Note: == important == comment\n"
            "</ref>\n\n"
            "== Conclusion ==\n"
            "Final words."
        )
        sections = self.client.split_sections(wikitext)
        self.assertEqual(len(sections), 3)
        self.assertEqual(sections[1].title, "Formulas")
        self.assertIn("<math>\nE == m c^2\n</math>", sections[1].content)
        self.assertIn("<ref name=\"test\">", sections[1].content)
        self.assertEqual(sections[2].title, "Conclusion")

    def test_html_comments_preservation(self):
        """<!-- == Hidden Section == --> must not be split."""
        wikitext = (
            "Lead text.\n"
            "<!-- == Hidden Section == -->\n"
            "More lead text.\n\n"
            "== Visible Section ==\n"
            "Content."
        )
        sections = self.client.split_sections(wikitext)
        self.assertEqual(len(sections), 2)
        self.assertIn("<!-- == Hidden Section == -->", sections[0].content)
        self.assertEqual(sections[1].title, "Visible Section")


class TestWikipediaAPIClient(unittest.TestCase):
    """Tests for Wikipedia API handling (redirects, missing, disambiguation, rate limits)."""

    def setUp(self):
        self.client = WikipediaClient(lang="en")

    @patch("urllib.request.urlopen")
    def test_fetch_wikitext_success_with_redirect(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "query": {
                "redirects": [{"from": "QC", "to": "Quantum computing"}],
                "pages": [{
                    "pageid": 1234,
                    "title": "Quantum computing",
                    "revisions": [{
                        "slots": {
                            "main": {
                                "content": "== Overview ==\nQuantum computing wikitext."
                            }
                        }
                    }]
                }]
            }
        }).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        content = self.client.fetch_wikitext("QC")
        self.assertIn("Quantum computing wikitext.", content)
    @patch("urllib.request.urlopen")
    def test_fetch_wikitext_with_revid(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "query": {
                "pages": [{
                    "pageid": 1234,
                    "title": "Quantum computing",
                    "revisions": [{
                        "revid": 999999,
                        "slots": {
                            "main": {
                                "content": "Pinned revision wikitext."
                            }
                        }
                    }]
                }]
            }
        }).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        content = self.client.fetch_wikitext("Quantum computing", revid=999999)
        self.assertEqual(content, "Pinned revision wikitext.")
        self.assertEqual(self.client.last_revision_id, 999999)

        # Verify fetch_sections also passes revid
        sections = self.client.fetch_sections("Quantum computing", revid=999999)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].content, "Pinned revision wikitext.")

    @patch("urllib.request.urlopen")
    def test_fetch_wikitext_page_not_found(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "query": {
                "pages": [{
                    "missing": True,
                    "title": "NonExistentPage12345"
                }]
            }
        }).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        with self.assertRaises(PageNotFoundError):
            self.client.fetch_wikitext("NonExistentPage12345")

    @patch("urllib.request.urlopen")
    def test_fetch_wikitext_disambiguation_page(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "query": {
                "pages": [{
                    "pageid": 5678,
                    "title": "Mercury",
                    "pageprops": {
                        "disambiguation": ""
                    },
                    "categories": [
                        {"title": "Category:All disambiguation pages"}
                    ],
                    "revisions": [{
                        "slots": {
                            "main": {
                                "content": "'''Mercury''' may refer to:\n* [[Mercury (planet)]]\n* [[Mercury (element)]]"
                            }
                        }
                    }]
                }]
            }
        }).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        with self.assertRaises(DisambiguationPageError):
            self.client.fetch_wikitext("Mercury")

    @patch("urllib.request.urlopen")
    def test_fetch_wikitext_rate_limit(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://en.wikipedia.org/w/api.php",
            code=429,
            msg="Too Many Requests",
            hdrs={},
            fp=None,
        )

        with self.assertRaises(RateLimitExceededError):
            self.client.fetch_wikitext("Quantum computing")


class TestAuthManagerAndTokenRefresh(unittest.TestCase):
    """Tests for token loading, expiration checks, and SQLite refresh persistence."""

    def test_credential_expiry_logic(self):
        now = time.time()
        # Expired
        cred_expired = AntigravityCredential(
            id=1, email="test@google.com", project_id="proj-1",
            access_token="tok1", refresh_token="ref1", expires_at=now - 10
        )
        self.assertTrue(cred_expired.is_expired())

        # Expiring soon (within 120s buffer)
        cred_soon = AntigravityCredential(
            id=2, email="test@google.com", project_id="proj-1",
            access_token="tok2", refresh_token="ref2", expires_at=now + 60
        )
        self.assertTrue(cred_soon.is_expired(buffer_seconds=120.0))

        # Valid fresh token
        cred_valid = AntigravityCredential(
            id=3, email="test@google.com", project_id="proj-1",
            access_token="tok3", refresh_token="ref3", expires_at=now + 3600
        )
        self.assertFalse(cred_valid.is_expired())

    def test_sqlite_token_refresh_and_persistence(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "agent.db"
            conn = sqlite3.connect(db_path)
            conn.execute(
                "CREATE TABLE auth_credentials (id INTEGER PRIMARY KEY, provider TEXT, data TEXT, updated_at INTEGER)"
            )
            initial_data = {
                "access": "old_access_token",
                "refresh": "valid_refresh_token",
                "expires": int((time.time() - 100) * 1000),
                "projectId": "test-project",
                "email": "agent@google.com",
            }
            conn.execute(
                "INSERT INTO auth_credentials (id, provider, data, updated_at) VALUES (1, 'google-antigravity', ?, ?)",
                (json.dumps(initial_data), int(time.time())),
            )
            conn.commit()
            conn.close()

            auth_manager = AuthManager(db_path=db_path)
            creds = auth_manager.load_credentials()
            self.assertEqual(len(creds), 1)
            cred = creds[0]
            self.assertEqual(cred.access_token, "old_access_token")
            self.assertTrue(cred.is_expired())

            # Mock OAuth endpoint refresh
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_resp = MagicMock()
                mock_resp.read.return_value = json.dumps({
                    "access_token": "new_refreshed_access_token",
                    "expires_in": 3600
                }).encode("utf-8")
                mock_resp.__enter__.return_value = mock_resp
                mock_urlopen.return_value = mock_resp

                new_token = auth_manager.refresh_access_token(cred)
                self.assertEqual(new_token, "new_refreshed_access_token")
                self.assertEqual(cred.access_token, "new_refreshed_access_token")
                self.assertFalse(cred.is_expired())

            # Verify persisted to SQLite
            reloaded_creds = auth_manager.load_credentials()
            self.assertEqual(reloaded_creds[0].access_token, "new_refreshed_access_token")


class TestSSEParsingAndGeminiClient(unittest.TestCase):
    """Tests for SSE stream parsing edge cases."""

    def setUp(self):
        self.client = GeminiTranslatorClient()

    def test_parse_sse_multiline_data_and_envelopes(self):
        sse_stream = [
            b"data: {\"response\": {\"candidates\": [{\"content\": {\"parts\": [{\"text\": \"== Sejarah ==\\n\"}]}}]}}\n",
            b"\n",
            b": keepalive comment\n",
            b"data: {\"candidates\": [{\"content\": {\"parts\": [{\"thought\": true, \"text\": \"thinking trace\"}, {\"text\": \"Komputer kuantum pertama.\"}]}}]}\n",
            b"\n",
            b"data: [DONE]\n",
        ]
        result = self.client._parse_sse_response(sse_stream)
        self.assertEqual(result, "== Sejarah ==\nKomputer kuantum pertama.")

    def test_parse_sse_strips_markdown_fences(self):
        sse_stream = [
            b"data: {\"candidates\": [{\"content\": {\"parts\": [{\"text\": \"```wikitext\\n== Penerapan ==\\n* Kriptografi\\n```\"}]}}]}\n",
            b"\n",
        ]
        sse_stream.append(b"data: [DONE]\n")
        result = self.client._parse_sse_response(sse_stream)
        self.assertEqual(result, "== Penerapan ==\n* Kriptografi")

    def test_thinking_tiers_and_model_mapping(self):
        from wiki_translator.gemini import ANTIGRAVITY_MODEL_MAP
        self.assertEqual(ANTIGRAVITY_MODEL_MAP["gemini-3.8-flash"], "gemini-3.8-flash-low")
        self.assertEqual(ANTIGRAVITY_MODEL_MAP["gemini-3.8-flash-low"], "gemini-3.8-flash-low")
        self.assertEqual(ANTIGRAVITY_MODEL_MAP["gemini-3.8-flash:low"], "gemini-3.8-flash-low")
        self.assertEqual(ANTIGRAVITY_MODEL_MAP["gemini-3.8-flash-medium"], "gemini-3.8-flash-medium")
        self.assertEqual(ANTIGRAVITY_MODEL_MAP["gemini-3.8-flash:medium"], "gemini-3.8-flash-medium")
        self.assertEqual(ANTIGRAVITY_MODEL_MAP["gemini-3.8-flash-high"], "gemini-3.8-flash-high")
        self.assertEqual(ANTIGRAVITY_MODEL_MAP["gemini-3.8-flash:high"], "gemini-3.8-flash-high")
        self.assertEqual(ANTIGRAVITY_MODEL_MAP["gemini-3.7-flash"], "gemini-3.7-flash-low")

        # Test GeminiTranslatorClient thinking_level
        client_default = GeminiTranslatorClient()
        self.assertEqual(client_default.preferred_model, "gemini-3.8-flash-low")
        self.assertEqual(client_default.thinking_level, "auto")

        client_low = GeminiTranslatorClient(thinking_level="low")
        self.assertEqual(client_low.preferred_model, "gemini-3.8-flash-low")
        self.assertEqual(client_low.thinking_level, "low")
        client_med = GeminiTranslatorClient(thinking_level="medium")
        self.assertEqual(client_med.preferred_model, "gemini-3.8-flash-medium")
        self.assertEqual(client_med.thinking_level, "medium")

        client_high = GeminiTranslatorClient(thinking_level="high")
        self.assertEqual(client_high.preferred_model, "gemini-3.8-flash-high")
        self.assertEqual(client_high.thinking_level, "high")

        client_custom = GeminiTranslatorClient(preferred_model="custom-model", thinking_level="high")
        self.assertEqual(client_custom.preferred_model, "custom-model")

    def test_cli_thinking_argument_mapping(self):
        from wiki_translator.cli import WikiTranslatorCLI
        import unittest.mock as mock
        with mock.patch("wiki_translator.cli.sys.argv", ["wiki-translator", "--thinking", "high"]):
            import argparse
            # Verify parser behavior
            from wiki_translator.cli import main
            # test parsing logic
            with mock.patch("wiki_translator.cli.WikiTranslatorCLI") as mock_cli:
                with mock.patch("wiki_translator.cli.load_env_file"):
                    try:
                        main()
                    except SystemExit:
                        pass
                    mock_cli.assert_called()
                    call_kwargs = mock_cli.call_args[1]
                    self.assertEqual(call_kwargs.get("model"), "gemini-3.8-flash-high")
                    self.assertEqual(call_kwargs.get("thinking"), "high")

        with mock.patch("wiki_translator.cli.sys.argv", ["wiki-translator", "--thinking-level", "medium"]):
            with mock.patch("wiki_translator.cli.WikiTranslatorCLI") as mock_cli:
                with mock.patch("wiki_translator.cli.load_env_file"):
                    try:
                        main()
                    except SystemExit:
                        pass
                    mock_cli.assert_called()
                    call_kwargs = mock_cli.call_args[1]
                    self.assertEqual(call_kwargs.get("model"), "gemini-3.8-flash-medium")
                    self.assertEqual(call_kwargs.get("thinking"), "medium")

class TestPromptsAndGlossaryFormatting(unittest.TestCase):
    """Tests for prompt builder, glossaries, and formatting."""

    def test_build_prompt_all_topics(self):
        for topic_key in TOPIC_GLOSSARIES:
            prompt = build_translation_prompt(
                section_title="Test Title",
                wikitext_content="Sample wikitext content",
                topic=topic_key,
            )
            self.assertIn("Glosarium Istilah Khusus", prompt)
            self.assertIn("```wikitext", prompt)
            self.assertIn("Sample wikitext content", prompt)

    def test_system_prompt_has_safeguards(self):
        self.assertIn("Infobox", SYSTEM_PROMPT_GRADE_A_PLUS_PLUS)
        self.assertIn("EYD", SYSTEM_PROMPT_GRADE_A_PLUS_PLUS)
        self.assertIn("<math>", SYSTEM_PROMPT_GRADE_A_PLUS_PLUS)
        self.assertIn("<ref>", SYSTEM_PROMPT_GRADE_A_PLUS_PLUS)
        self.assertIn("wikitable", SYSTEM_PROMPT_GRADE_A_PLUS_PLUS)


if __name__ == "__main__":
    unittest.main()
