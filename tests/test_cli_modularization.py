"""
Unit tests verifying CLI modularization (cli_args, cli_subcommands, cli_ui).
"""

import argparse
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from wiki_translator.cli_args import build_cli_parser
from wiki_translator.cli_ui import print_console_safe, print_banner, slugify, load_env_file
from wiki_translator.cli_subcommands import (
    handle_storage_commands,
    handle_glossary_actions,
    handle_page_gen_commands,
    handle_batch_command,
)


class TestCliModularization(unittest.TestCase):

    def test_build_cli_parser_defaults(self):
        parser = build_cli_parser()
        self.assertIsInstance(parser, argparse.ArgumentParser)
        args = parser.parse_args(["Quantum computing"])
        self.assertEqual(args.title, "Quantum computing")
        self.assertEqual(args.model, "gemini-3.8-flash")
        self.assertEqual(args.thinking, "auto")
        self.assertTrue(args.auto_glossary)
        self.assertTrue(args.map_links)
        self.assertTrue(args.metric_first)

    def test_build_cli_parser_flags(self):
        parser = build_cli_parser()
        args = parser.parse_args([
            "--model", "gemini-3.8-flash",
            "--thinking", "high",
            "--no-glossary",
            "--no-map-links",
            "--no-metric-first",
            "--preview",
        ])
        self.assertEqual(args.thinking, "high")
        self.assertFalse(args.auto_glossary)
        self.assertFalse(args.map_links)
        self.assertFalse(args.metric_first)
        self.assertTrue(args.preview)

    def test_slugify(self):
        self.assertEqual(slugify("Quantum Computing! (film)"), "quantum_computing_film")
        self.assertEqual(slugify("Hello World"), "hello_world")

    def test_load_env_file(self):
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".env", encoding="utf-8") as f:
            f.write("TEST_CUSTOM_MOD_VAR=loaded_value\n# Comment\n")
            temp_env = Path(f.name)
        try:
            import os
            load_env_file(temp_env)
            self.assertEqual(os.environ.get("TEST_CUSTOM_MOD_VAR"), "loaded_value")
        finally:
            if temp_env.exists():
                temp_env.unlink()

    def test_handle_glossary_actions_none(self):
        parser = build_cli_parser()
        args = parser.parse_args([])
        handled = handle_glossary_actions(args, parser)
        self.assertFalse(handled)

    def test_handle_page_gen_commands_none(self):
        parser = build_cli_parser()
        args = parser.parse_args([])
        handled = handle_page_gen_commands(args, parser)
        self.assertFalse(handled)

    def test_handle_batch_command_none(self):
        parser = build_cli_parser()
        args = parser.parse_args([])
        cli_mock = MagicMock()
        handled = handle_batch_command(args, cli_mock)
        self.assertFalse(handled)
    def test_handle_storage_commands_status(self):
        parser = build_cli_parser()
        args = parser.parse_args(["--cache-status"])
        with patch("builtins.print") as mock_print:
            handled = handle_storage_commands(args, parser)
            self.assertTrue(handled)
            mock_print.assert_called()

    def test_handle_storage_commands_clear(self):
        parser = build_cli_parser()
        args = parser.parse_args(["--clear-cache", "translation"])
        with patch("builtins.print") as mock_print:
            handled = handle_storage_commands(args, parser)
            self.assertTrue(handled)
            mock_print.assert_called()


if __name__ == "__main__":
    unittest.main()
