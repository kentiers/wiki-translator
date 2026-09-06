import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from wiki_translator.dependency_deployer import DependencyDeployer
from wiki_translator.template_ecosystem import DependencyKind, DependencyNode


class TestDependencyDeployer(unittest.TestCase):
    def test_deploys_in_topological_order_without_publishing(self):
        scanner = MagicMock()
        scanner.normalize_title.side_effect = lambda title: title
        scanner.check_existence_on_idwiki.return_value = False
        scanner.scan_dependencies_recursive.return_value = {
            "Module:Base": DependencyNode("Module:Base", DependencyKind.MODULE, False, [], [], "return 1"),
            "Template:Root": DependencyNode("Template:Root", DependencyKind.TEMPLATE, False, ["Module:Base"], [], "{{#invoke:Base|main}}"),
        }
        scanner.topological_sort.return_value = ["Module:Base", "Template:Root"]
        syncer = MagicMock()
        syncer.sync_template.return_value = {
            "template_file": "root.wikitext", "doc_file": "root_doc.wikitext"
        }
        syncer.sync_template.return_value["wikitext"] = "{{#invoke:Base|main}}"
        validator = MagicMock()
        validator.simulate_parse.return_value = MagicMock(
            errors=[], warnings=[], has_missing_template=False
        )
        validator.evaluate_promotion_gate.return_value = (True, "ok")
        with tempfile.TemporaryDirectory() as temp:
            result = DependencyDeployer(scanner, syncer, validator).deploy("Template:Root", Path(temp))
            self.assertEqual(result.drafted, ["Module:Base", "Template:Root"])
            syncer.sync_template.assert_called_once()
            self.assertFalse(syncer.sync_template.call_args.kwargs["publish"])
            self.assertTrue((Path(temp) / "Template_Root" / "approval-manifest.json").exists())

    def test_blocks_dependents_when_dependency_is_unresolved(self):
        scanner = MagicMock()
        scanner.normalize_title.side_effect = lambda title: title
        scanner.check_existence_on_idwiki.return_value = False
        scanner.scan_dependencies_recursive.return_value = {
            "Template:Root": DependencyNode("Template:Root", DependencyKind.TEMPLATE, False, ["Template:Missing"], ["Template:Missing"], "{{Missing}}"),
        }
        scanner.topological_sort.return_value = ["Template:Root"]
        with tempfile.TemporaryDirectory() as temp:
            result = DependencyDeployer(scanner, MagicMock(), MagicMock()).deploy("Template:Root", Path(temp))
        self.assertEqual(result.drafted, [])
        self.assertIn("unresolved dependencies", result.blocked[0])

    def test_validation_failure_blocks_node_and_its_dependent(self):
        scanner = MagicMock()
        scanner.normalize_title.side_effect = lambda title: title
        scanner.check_existence_on_idwiki.return_value = False
        scanner.scan_dependencies_recursive.return_value = {
            "Module:Bad": DependencyNode("Module:Bad", DependencyKind.MODULE, False, [], [], "bad"),
            "Template:Root": DependencyNode("Template:Root", DependencyKind.TEMPLATE, False, ["Module:Bad"], ["Module:Bad"], ""),
        }
        scanner.topological_sort.return_value = ["Module:Bad", "Template:Root"]
        validator = MagicMock()
        validator.simulate_parse.return_value = MagicMock(
            errors=["Lua error"], warnings=[], has_missing_template=False
        )
        validator.evaluate_promotion_gate.return_value = (False, "Promotion blocked: Lua error")
        with tempfile.TemporaryDirectory() as temp:
            result = DependencyDeployer(scanner, MagicMock(), validator).deploy("Template:Root", Path(temp))
        self.assertEqual(result.drafted, [])
        self.assertEqual(len(result.blocked), 2)

    def test_existing_root_is_reused_without_scanning_enwiki_dependencies(self):
        scanner = MagicMock()
        scanner.normalize_title.return_value = "Template:Existing"
        scanner.check_existence_on_idwiki.return_value = True
        with tempfile.TemporaryDirectory() as temp:
            result = DependencyDeployer(scanner, MagicMock(), MagicMock()).deploy(
                "Existing", Path(temp)
            )
        self.assertEqual(result.reused, ["Template:Existing"])
        self.assertEqual(
            Path(result.report_path).parts[-2:],
            ("Template_Existing", "deployment-report.json"),
        )
        scanner.scan_dependencies_recursive.assert_not_called()

    def test_existing_dependency_is_a_graph_boundary(self):
        scanner = MagicMock()
        scanner.normalize_title.side_effect = lambda title: title
        scanner.check_existence_on_idwiki.return_value = False
        scanner.scan_dependencies_recursive.return_value = {
            "Template:Root": DependencyNode("Template:Root", DependencyKind.TEMPLATE, False, ["Template:Local"], [], "root"),
            "Template:Local": DependencyNode("Template:Local", DependencyKind.TEMPLATE, True, ["Template:EnOnly"], [], "local"),
            "Template:EnOnly": DependencyNode("Template:EnOnly", DependencyKind.TEMPLATE, False, [], [], "en"),
        }
        scanner.topological_sort.return_value = ["Template:EnOnly", "Template:Local", "Template:Root"]
        syncer = MagicMock()
        syncer.sync_template.return_value = {
            "template_file": "root.wikitext",
            "doc_file": "root_doc.wikitext",
            "wikitext": "root",
        }
        validator = MagicMock()
        validator.simulate_parse.return_value = MagicMock(errors=[], warnings=[], has_missing_template=False)
        validator.evaluate_promotion_gate.return_value = (True, "ok")
        with tempfile.TemporaryDirectory() as temp:
            result = DependencyDeployer(scanner, syncer, validator).deploy("Template:Root", Path(temp))
        self.assertEqual(result.order, ["Template:Local", "Template:Root"])
        self.assertNotIn("Template:EnOnly", result.drafted)


if __name__ == "__main__":
    unittest.main()
