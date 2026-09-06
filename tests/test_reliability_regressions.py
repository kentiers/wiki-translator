"""Regression tests for batch accuracy, publication gates, and cache efficiency."""

from pathlib import Path
from types import SimpleNamespace
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from wiki_translator.batch_runner import BatchRunner
from wiki_translator.cli import WikiTranslatorCLI, main
from wiki_translator.editorial_qa import QAAuditReport
from wiki_translator.stub_generator import StubGenerator
from wiki_translator.token_saver import TranslationCache
from wiki_translator.wiki_client import WikiSection
from wiki_translator.wiki_link_mapper import WikiLinkMapper


class TestReliableResultContracts(unittest.TestCase):
    def setUp(self):
        checker = patch("wiki_translator.cli.review_claims", return_value=[])
        checker.start()
        self.addCleanup(checker.stop)

    def _configured_cli_for_cache_flow(self, tmpdir):
        cli = WikiTranslatorCLI(
            output_dir=tmpdir,
            topic="general",
            enable_compression=False,
            enable_delta_skip=False,
            enable_auto_glossary=False,
            enable_map_links=False,
            enable_typography_sanitizer=False,
            enable_slop_linter=False,
            enable_syntax_balancer=False,
            enable_template_mapper=False,
            metric_first=False,
            by_paragraph=False,
        )
        cli.auth_manager = MagicMock()
        cli.auth_manager.get_active_credential.return_value = None
        cli.wiki_client = MagicMock()
        cli.wiki_client.last_revision_id = 1
        cli.wiki_client.fetch_sections.return_value = [
            WikiSection(index=0, title="Lead", level=1, header_raw="", content="Source text", word_count=2, char_count=11)
        ]
        cli.gemini_client = MagicMock()
        cli.gemini_client.thinking_level = "none"
        cli.gemini_client.translate_section.return_value = "Teks hasil terjemahan."
        cli.cache = MagicMock()
        cli.cache.get.return_value = None
        cli.tracker = MagicMock()
        cli.tracker.get_summary_table.return_value = "metrics"
        cli._handle_sandbox_publishing = MagicMock()
        return cli

    def test_approved_translation_is_persisted_with_gemini_38_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cli = self._configured_cli_for_cache_flow(tmpdir)
            approved = QAAuditReport(overall_score=100, grade="A++", approved=True)
            with patch("wiki_translator.cli.print_banner"), patch("wiki_translator.cli.default_shared_memory.get_memory_glossary", return_value={}), patch("wiki_translator.cli.default_qa_pipeline.audit", return_value=approved), patch("builtins.input", return_value="0"):
                result = cli.run_interactive("Article", auto_approve=True)
        self.assertTrue(result["success"])
        self.assertEqual(cli.model, "gemini-3.8-flash")
        cli.cache.put.assert_called_once()
        self.assertEqual(cli.cache.put.call_args.kwargs["model"], "gemini-3.8-flash")

    def test_skipped_translation_is_not_persisted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cli = self._configured_cli_for_cache_flow(tmpdir)
            approved = QAAuditReport(overall_score=100, grade="A++", approved=True)
            with patch("wiki_translator.cli.print_banner"), patch("wiki_translator.cli.default_shared_memory.get_memory_glossary", return_value={}), patch("wiki_translator.cli.default_qa_pipeline.audit", return_value=approved), patch("builtins.input", return_value="S"):
                cli.run_interactive("Article", auto_approve=False)
        cli.cache.put.assert_not_called()

    def test_resolved_glossary_is_used_for_cache_lookup_and_write(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cli = self._configured_cli_for_cache_flow(tmpdir)
            cli.enable_auto_glossary = True
            cli.glossary_resolver = MagicMock()
            cli.glossary_resolver.resolve_section_terms.return_value = {"quantum": "kuantum"}
            approved = QAAuditReport(overall_score=100, grade="A++", approved=True)
            with patch("wiki_translator.cli.print_banner"), patch("wiki_translator.cli.default_shared_memory.get_memory_glossary", return_value={}), patch("wiki_translator.cli.default_qa_pipeline.audit", return_value=approved):
                cli.run_interactive("Article", auto_approve=True)
        self.assertEqual(cli.cache.get.call_args.kwargs["glossary"], {"quantum": "kuantum"})
        self.assertEqual(cli.cache.put.call_args.kwargs["glossary"], {"quantum": "kuantum"})

    def test_fetch_failure_returns_structured_failure(self):
        cli = object.__new__(WikiTranslatorCLI)
        cli.auth_manager = MagicMock()
        cli.auth_manager.get_active_credential.return_value = None
        cli.wiki_client = MagicMock()
        cli.wiki_client.fetch_sections.side_effect = RuntimeError("API unavailable")

        with patch("wiki_translator.cli.print_banner"):
            result = cli.run_interactive("Missing article", auto_approve=True)

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "fetch_failed")
        self.assertIn("API unavailable", result["error"])
        self.assertEqual(result["output_files"], {})

    def test_empty_llm_output_fails_batch_without_prompting(self):
        cli = object.__new__(WikiTranslatorCLI)
        cli.auth_manager = MagicMock()
        cli.auth_manager.get_active_credential.return_value = None
        cli.wiki_client = MagicMock()
        cli.wiki_client.fetch_sections.return_value = [
            WikiSection(
                index=0,
                title="Lead",
                level=1,
                header_raw="",
                content="Source text",
                word_count=2,
                char_count=11,
            )
        ]
        cli.topic = "general"
        cli.custom_glossary = {}
        cli.enable_auto_glossary = False
        cli.enable_delta_skip = False
        cli.enable_cache = False
        cli.cache = None
        cli.enable_compression = False
        cli.by_paragraph = False
        cli.gemini_client = MagicMock()
        cli.gemini_client.thinking_level = "none"
        cli.gemini_client.translate_section.return_value = "   "

        with (
            patch("wiki_translator.cli.print_banner"),
            patch("builtins.input", side_effect=AssertionError("batch mode must not prompt")),
        ):
            result = cli.run_interactive("Article", auto_approve=True)

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "empty_translation")

    def test_integrity_error_blocks_publication(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            template_mapper = MagicMock()
            template_mapper.process_wikitext_templates.side_effect = RuntimeError("mapper failed")
            attribution = MagicMock()
            attribution.generate_talk_page.return_value = "Talk attribution"
            preview = MagicMock()
            cli = WikiTranslatorCLI(
                output_dir=tmpdir,
                topic="general",
                enable_cache=False,
                enable_compression=False,
                enable_delta_skip=False,
                enable_auto_glossary=False,
                enable_map_links=False,
                enable_polish=False,
                enable_typography_sanitizer=False,
                enable_slop_linter=False,
                enable_syntax_balancer=False,
                enable_template_mapper=True,
                template_mapper=template_mapper,
                attribution_generator=attribution,
                preview_generator=preview,
                metric_first=False,
                by_paragraph=False,
            )
            cli.auth_manager = MagicMock()
            cli.auth_manager.get_active_credential.return_value = None
            cli.wiki_client = MagicMock()
            cli.wiki_client.last_revision_id = 1
            cli.wiki_client.fetch_sections.return_value = [
                WikiSection(
                    index=0,
                    title="Lead",
                    level=1,
                    header_raw="",
                    content="Source text",
                    word_count=2,
                    char_count=11,
                )
            ]
            cli.gemini_client = MagicMock()
            cli.gemini_client.thinking_level = "none"
            cli.gemini_client.translate_section.return_value = "Teks hasil terjemahan."
            cli.tracker = MagicMock()
            cli.tracker.get_summary_table.return_value = "metrics"
            cli._handle_sandbox_publishing = MagicMock()
            approved = QAAuditReport(overall_score=100, grade="A++", approved=True)

            with (
                patch("wiki_translator.cli.print_banner"),
                patch("wiki_translator.cli.default_shared_memory.get_memory_glossary", return_value={}),
                patch("wiki_translator.cli.default_qa_pipeline.audit", return_value=approved),
            ):
                result = cli.run_interactive("Article", auto_approve=True)

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "pipeline_failed")
        self.assertFalse(result["publication_ready"])
        self.assertIn("template_mapping: mapper failed", result["pipeline_errors"])
        cli._handle_sandbox_publishing.assert_not_called()

    def test_cli_batch_forwards_real_translation_result(self):
        failed = {"success": False, "status": "qa_rejected", "error": "QA rejected"}
        cli_instance = MagicMock()
        cli_instance.run_interactive.return_value = failed
        observed = {}

        def run_batch(**kwargs):
            observed.update(kwargs["translate_fn"]("Article"))
            return SimpleNamespace(succeeded=0, total_articles=1, total_elapsed_seconds=0.01)

        with (
            patch("sys.argv", ["wiki-translator", "--batch", "queue.txt"]),
            patch("wiki_translator.cli.WikiTranslatorCLI", return_value=cli_instance),
            patch("wiki_translator.cli.default_batch_runner.run_batch_from_file", side_effect=run_batch),
        ):
            main()

        self.assertEqual(observed, failed)
        cli_instance.run_interactive.assert_called_once_with(
            article_title="Article", auto_approve=True, revid=None
        )

    def test_batch_runner_rejects_ambiguous_callback_results(self):
        runner = BatchRunner(pause_interval=0)
        missing = runner.run_batch(["A"], lambda _: {"output_files": "invalid"})
        nondict = runner.run_batch(["B"], lambda _: None)

        self.assertEqual(missing.failed, 1)
        self.assertEqual(missing.items[0].output_files, {})
        self.assertIn("explicit success", missing.items[0].error)
        self.assertEqual(nondict.failed, 1)
        self.assertIn("result dictionary", nondict.items[0].error)


class TestFailClosedQA(unittest.TestCase):
    def test_stub_qa_exception_is_not_approved(self):
        qa_pipeline = MagicMock()
        qa_pipeline.audit.side_effect = RuntimeError("QA crashed")
        generator = StubGenerator(qa_pipeline=qa_pipeline, translator_client=None)

        result = generator.generate_stub(
            "Test Person",
            id_title="Tokoh Uji",
            custom_lead="'''Test Person''' is a notable film director.",
            custom_full_wikitext="'''Test Person''' is a notable film director.",
        )

        self.assertFalse(result["is_qa_approved"])
        self.assertIsNone(result["qa_report"])
        self.assertEqual(result["qa_error"], "QA crashed")


class TestEfficientLookupsAndCache(unittest.TestCase):
    def test_existence_lookup_matches_space_and_underscore_titles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mapper = WikiLinkMapper(cache_db_path=str(Path(tmpdir) / "links.db"))
            mapper._api_get = MagicMock(
                return_value={
                    "query": {
                        "pages": [
                            {"title": "Alpha Beta", "pageid": 10},
                            {"title": "Gamma Delta", "pageid": 20},
                        ]
                    }
                }
            )

            result = mapper.check_id_wiki_pages_exist(
                ["Alpha_Beta", "Alpha Beta", "Gamma_Delta", "Missing"]
            )
        self.assertTrue(result["Alpha_Beta"])
        self.assertTrue(result["Alpha Beta"])
        self.assertFalse(result["Missing"])
        self.assertTrue(result["Gamma_Delta"])

    def test_batch_link_resolution_deduplicates_base_targets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mapper = WikiLinkMapper(cache_db_path=str(Path(tmpdir) / "links.db"))
            mapper.get_cached_page_link = MagicMock(return_value=None)
            mapper.check_id_wiki_pages_exist = MagicMock(return_value={"Same": False})
            mapper.fetch_en_to_id_langlinks = MagicMock(return_value={})
            mapper.fetch_wikidata_id_sitelink = MagicMock(return_value=None)
            mapper.cache_page_link = MagicMock()

            mapper.batch_resolve_wikilinks(["Same", "Same", "Same#History"])

        mapper.get_cached_page_link.assert_called_once_with("Same")
        mapper.check_id_wiki_pages_exist.assert_called_once_with(["Same"])
        mapper.fetch_en_to_id_langlinks.assert_called_once_with(["Same"])
        mapper.fetch_wikidata_id_sitelink.assert_called_once_with("Same")

    def test_translation_cache_uses_wal_and_normal_synchronous_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = TranslationCache(Path(tmpdir) / "translations.db")
            conn = cache._get_conn()
            try:
                journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
                synchronous = conn.execute("PRAGMA synchronous").fetchone()[0]
            finally:
                conn.close()

        self.assertEqual(journal_mode.lower(), "wal")
        self.assertEqual(synchronous, 1)


if __name__ == "__main__":
    unittest.main()
