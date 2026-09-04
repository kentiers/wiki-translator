"""
Unit tests for CLI template ecosystem flags:
--scan-template-deps
--sync-ecosystem
"""

import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from wiki_translator.cli import main, WikiTranslatorCLI
from wiki_translator.template_ecosystem import (
    DependencyNode,
    DependencyKind,
)


class TestCLITemplateEcosystem(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @patch("wiki_translator.cli.default_ecosystem_manager")
    def test_cli_scan_template_deps(self, mock_eco):
        mock_node_root = DependencyNode(
            title="Template:Infobox film",
            kind=DependencyKind.TEMPLATE,
            exists_on_id=True,
            dependencies=["Module:Infobox"],
        )
        mock_node_mod = DependencyNode(
            title="Module:Infobox",
            kind=DependencyKind.MODULE,
            exists_on_id=False,
            dependencies=[],
        )
        mock_eco.scanner.scan_dependencies_recursive.return_value = {
            "Template:Infobox film": mock_node_root,
            "Module:Infobox": mock_node_mod,
        }
        mock_eco.scanner.topological_sort.return_value = [
            "Module:Infobox",
            "Template:Infobox film",
        ]

        with patch(
            "sys.argv",
            [
                "wiki_translator",
                "--scan-template-deps",
                "Template:Infobox film",
            ],
        ):
            with patch("builtins.print") as mock_print:
                main()
                mock_eco.scanner.scan_dependencies_recursive.assert_called_once_with("Template:Infobox film")
                mock_eco.scanner.topological_sort.assert_called_once()

    @patch("wiki_translator.cli.default_ecosystem_manager")
    def test_cli_sync_ecosystem(self, mock_eco):
        mock_eco.sync_ecosystem.return_value = {
            "root_title": "Template:Infobox film",
            "dependency_tree": {"Template:Infobox film": {}},
            "missing_dependencies": ["Module:Infobox"],
            "sandbox": {"title": "Template:Infobox film/bak pasir"},
            "testcases": {"title": "Template:Infobox film/kasus uji"},
            "validation": {"is_valid": True},
            "promotion": {"message": "All checks passed", "promoted": False},
        }

        with patch(
            "sys.argv",
            [
                "wiki_translator",
                "--sync-ecosystem",
                "Template:Infobox film",
                "--output-dir",
                str(self.tmp_dir),
            ],
        ):
            with patch("builtins.print") as mock_print:
                main()
                mock_eco.sync_ecosystem.assert_called_once_with(
                    "Template:Infobox film",
                    publish_sandbox=True,
                    promote=False,
                    output_dir=self.tmp_dir / "ecosystem",
                )


if __name__ == "__main__":
    unittest.main()
