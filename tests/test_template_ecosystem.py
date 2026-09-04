"""
Unit tests for Wikipedia Template & Module Ecosystem Engine (wiki_translator/template_ecosystem.py).

All tests use 100% mocked network calls (zero live requests to Wikipedia).
"""

import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from wiki_translator.template_ecosystem import (
    RecursiveDependencyScanner,
    CategoryTreeLinker,
    SandboxTestcaseEngine,
    TemplateEcosystemManager,
    default_ecosystem_manager,
    DependencyNode,
    DependencyKind,
    ValidationResult,
)
from wiki_translator.wiki_client import PageNotFoundError, WikipediaClient
from wiki_translator.wiki_link_mapper import WikiLinkMapper, CategoryResolution
from wiki_translator.wikidata_linker import WikidataLinker


class TestRecursiveDependencyScanner(unittest.TestCase):
    def setUp(self):
        self.mock_en_client = MagicMock(spec=WikipediaClient)
        self.mock_id_client = MagicMock(spec=WikipediaClient)
        self.mock_id_client.api_url = "https://id.wikipedia.org/w/api.php"
        self.mock_id_client.user_agent = "TestUserAgent"
        self.mock_en_client.api_url = "https://en.wikipedia.org/w/api.php"
        self.mock_en_client.user_agent = "TestUserAgent"

        self.scanner = RecursiveDependencyScanner(
            en_client=self.mock_en_client,
            id_client=self.mock_id_client,
        )

    def test_normalize_title(self):
        self.assertEqual(
            self.scanner.normalize_title("infobox film"),
            "Template:Infobox film",
        )
        self.assertEqual(
            self.scanner.normalize_title("Template:Infobox film"),
            "Template:Infobox film",
        )
        self.assertEqual(
            self.scanner.normalize_title("Templat:Infobox film"),
            "Template:Infobox film",
        )
        self.assertEqual(
            self.scanner.normalize_title("Module:Navbox/config"),
            "Module:Navbox/config",
        )
        self.assertEqual(
            self.scanner.normalize_title("Modul:Navbox/data"),
            "Module:Navbox/data",
        )
        self.assertEqual(
            self.scanner.normalize_title("Category:Action films"),
            "Category:Action films",
        )
        self.assertEqual(
            self.scanner.normalize_title("navbox", default_namespace="Module"),
            "Module:Navbox",
        )

    def test_extract_templates_and_filter_parser_functions(self):
        wikitext = (
            "{{Infobox film|title=Dune}}\n"
            "{{#if: {{{param|}}} | {{Yes}} | {{No}} }}\n"
            "{{#switch: {{{type|}}} | a = {{Formatdate|2026-01-01}} }}\n"
            "{{Navbox|name=Dune}}\n"
            "{{#invoke:Navbox|navbox}}\n"
        )
        templates = self.scanner.extract_templates_from_wikitext(wikitext)
        # Should include Infobox film, Yes, No, Navbox
        # Should NOT include #if, #switch, formatdate, #invoke
        self.assertIn("Template:Infobox film", templates)
        self.assertIn("Template:Yes", templates)
        self.assertIn("Template:No", templates)
        self.assertIn("Template:Navbox", templates)
        self.assertNotIn("Template:#if", templates)
        self.assertNotIn("Template:#switch", templates)
        self.assertNotIn("Template:Formatdate", templates)
        self.assertNotIn("Template:#invoke", templates)

    def test_extract_invocations_from_wikitext(self):
        wikitext = (
            "{{#invoke:Navbox|navbox|...}}\n"
            "{{#invoke:String|replace|source|pattern|replace}}\n"
            "{{#invoke:Module:Arguments|getArgs}}\n"
        )
        invocations = self.scanner.extract_invocations_from_wikitext(wikitext)
        self.assertIn("Module:Navbox", invocations)
        self.assertIn("Module:String", invocations)
        self.assertIn("Module:Arguments", invocations)

    def test_extract_lua_dependencies(self):
        lua_code = """
        local p = {}
        local navbox = require('Module:Navbox')
        local cfg = require("Module:Navbox/config")
        local data = mw.loadData('Module:Navbox/data')
        local m_args = require('Module:Arguments')
        return p
        """
        deps = self.scanner.extract_lua_dependencies(lua_code)
        self.assertIn("Module:Navbox", deps)
        self.assertIn("Module:Navbox/config", deps)
        self.assertIn("Module:Navbox/data", deps)
        self.assertIn("Module:Arguments", deps)

    @patch("urllib.request.urlopen")
    def test_check_existence_on_idwiki(self, mock_urlopen):
        # Mock API response for existing page
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "query": {
                "pages": [{"pageid": 12345, "ns": 10, "title": "Template:Navbox"}]
            }
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        exists = self.scanner.check_existence_on_idwiki("Template:Navbox")
        self.assertTrue(exists)
        # Should be cached now
        self.assertTrue(self.scanner._existence_cache["Template:Navbox"])

    def test_recursive_scan_and_topological_sort(self):
        # Create a mock tree:
        # Template:Main -> Template:SubA, Module:Engine
        # Module:Engine -> Module:Data, Module:Config
        # Module:Config -> Module:Base
        content_map = {
            "Template:Main": "{{SubA}}\n{{#invoke:Engine|run}}",
            "Template:SubA": "{{Base}}",
            "Template:Base": "Base template content",
            "Module:Engine": "local d = mw.loadData('Module:Data')\nlocal c = require('Module:Config')",
            "Module:Data": "return { x = 1 }",
            "Module:Config": "local b = require('Module:Base')",
            "Module:Base": "return {}",
        }

        def fake_fetch(title, **kwargs):
            norm = self.scanner.normalize_title(title)
            if norm in content_map:
                return content_map[norm]
            raise PageNotFoundError(f"Page not found: {title}")

        self.mock_en_client.fetch_wikitext.side_effect = fake_fetch
        # Mock idwiki existence: Module:Base exists, others don't
        self.scanner.check_existence_on_idwiki = MagicMock(
            side_effect=lambda title: title == "Module:Base"
        )

        nodes = self.scanner.scan_dependencies_recursive("Template:Main")
        self.assertIn("Template:Main", nodes)
        self.assertIn("Template:SubA", nodes)
        self.assertIn("Module:Engine", nodes)
        self.assertIn("Module:Data", nodes)
        self.assertIn("Module:Config", nodes)
        self.assertIn("Module:Base", nodes)

        # Module:Base exists on id.wiki
        self.assertTrue(nodes["Module:Base"].exists_on_id)
        # Module:Engine does not exist
        self.assertFalse(nodes["Module:Engine"].exists_on_id)

        # Topological sort verification
        topo = self.scanner.topological_sort(nodes)
        self.assertEqual(len(topo), len(nodes))

        # Check topological ordering invariants:
        # Module:Base must precede Module:Config
        self.assertLess(topo.index("Module:Base"), topo.index("Module:Config"))
        # Module:Config must precede Module:Engine
        self.assertLess(topo.index("Module:Config"), topo.index("Module:Engine"))
        # Module:Data must precede Module:Engine
        self.assertLess(topo.index("Module:Data"), topo.index("Module:Engine"))
        # Module:Engine and Template:SubA must precede Template:Main
        self.assertLess(topo.index("Module:Engine"), topo.index("Template:Main"))
        self.assertLess(topo.index("Template:SubA"), topo.index("Template:Main"))


class TestCategoryTreeLinker(unittest.TestCase):
    def setUp(self):
        self.mock_en_client = MagicMock(spec=WikipediaClient)
        self.mock_id_client = MagicMock(spec=WikipediaClient)
        self.mock_link_mapper = MagicMock(spec=WikiLinkMapper)
        self.mock_wikidata_linker = MagicMock(spec=WikidataLinker)

        self.linker = CategoryTreeLinker(
            en_client=self.mock_en_client,
            id_client=self.mock_id_client,
            link_mapper=self.mock_link_mapper,
            wikidata_linker=self.mock_wikidata_linker,
        )

    @patch("urllib.request.urlopen")
    def test_fetch_parent_categories_from_enwiki(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "query": {
                "pages": [
                    {
                        "categories": [
                            {"title": "Category:British action thriller films"},
                            {"title": "Category:2026 action thriller films"},
                        ]
                    }
                ]
            }
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        parents = self.linker.fetch_parent_categories_from_enwiki("Category:The Runner (2026 film)")
        self.assertIn("Category:British action thriller films", parents)
        self.assertIn("Category:2026 action thriller films", parents)

    def test_map_parent_category_via_wikidata(self):
        # 1. WikidataLinker resolves item id
        self.mock_wikidata_linker.get_item_id_from_enwiki.return_value = "Q12345"
        self.mock_wikidata_linker.api_url = "https://www.wikidata.org/w/api.php"
        self.mock_wikidata_linker.user_agent = "TestAgent"

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({
                "entities": {
                    "Q12345": {
                        "sitelinks": {
                            "idwiki": {
                                "title": "Kategori:Film laga Britania Raya"
                            }
                        }
                    }
                }
            }).encode("utf-8")
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            mapped = self.linker.map_parent_category_to_idwiki("Category:British action films")
            self.assertEqual(mapped, "Kategori:Film laga Britania Raya")

    def test_attach_parent_categories_prevents_orphans(self):
        self.linker.fetch_parent_categories_from_enwiki = MagicMock(
            return_value=["Category:Action films by country", "Category:British films"]
        )
        self.linker.map_parent_category_to_idwiki = MagicMock(
            side_effect=lambda cat: "Kategori:Film Britania Raya" if "British" in cat else "Kategori:Film menurut negara"
        )

        initial_wikitext = "Kategori ini berisi daftar film laga."
        enriched = self.linker.attach_parent_categories(
            "Category:British action films",
            initial_wikitext,
        )

        self.assertIn("[[Kategori:Film menurut negara]]", enriched)
        self.assertIn("[[Kategori:Film Britania Raya]]", enriched)
        # Verify no duplicate addition if category already present
        second_pass = self.linker.attach_parent_categories(
            "Category:British action films",
            enriched,
        )
        self.assertEqual(second_pass.count("[[Kategori:Film Britania Raya]]"), 1)


class TestSandboxTestcaseEngine(unittest.TestCase):
    def setUp(self):
        self.mock_id_client = MagicMock(spec=WikipediaClient)
        self.engine = SandboxTestcaseEngine(id_client=self.mock_id_client)

    def test_sandbox_and_testcase_title_generation(self):
        self.assertEqual(
            self.engine.get_sandbox_title("Template:Christopher Nolan"),
            "Template:Christopher Nolan/bak pasir",
        )
        self.assertEqual(
            self.engine.get_sandbox_title("Template:Christopher Nolan/bak pasir"),
            "Template:Christopher Nolan/bak pasir",
        )
        self.assertEqual(
            self.engine.get_testcases_title("Template:Christopher Nolan"),
            "Template:Christopher Nolan/kasus uji",
        )
        self.assertEqual(
            self.engine.get_testcases_title("Template:Christopher Nolan/kasus uji"),
            "Template:Christopher Nolan/kasus uji",
        )

    def test_generate_sandbox_and_testcase_wikitext(self):
        sandbox_text = self.engine.generate_sandbox_wikitext(
            "{{Navbox|name=Nolan}}",
            "Template:Christopher Nolan",
        )
        self.assertIn("{{Template sandbox notice|Christopher Nolan}}", sandbox_text)
        self.assertIn("{{Navbox|name=Nolan}}", sandbox_text)

        testcase_text = self.engine.generate_testcase_wikitext(
            "Template:Christopher Nolan",
            sample_calls=[
                {"title": "Kasus 1", "params": {"state": "autocollapse"}},
                {"title": "Kasus 2", "params": {"state": "expanded"}},
            ],
        )
        self.assertIn("{{Test cases notice|Christopher Nolan}}", testcase_text)
        self.assertIn("{{Test case|_format=columns|_collapsible=yes|_title=Kasus 1", testcase_text)
        self.assertIn("| state = autocollapse", testcase_text)
        self.assertIn("| state = expanded", testcase_text)

    def test_unclosed_tag_detection(self):
        bad_wikitext = "<div><span>Some content without closing tag</div>"
        res = self.engine.simulate_parse("Template:Test", bad_wikitext)
        self.assertFalse(res.is_valid)
        self.assertTrue(res.has_unclosed_tag)
        self.assertTrue(any("Unclosed tag <span>" in e for e in res.errors))

    @patch("urllib.request.urlopen")
    def test_lua_runtime_error_detection(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "parse": {
                "text": {
                    "*": "<div class=\"scribunto-error\">Galat skrip: Modul tidak ditemukan.</div>"
                }
            }
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = self.engine.simulate_parse("Template:Faulty", "{{#invoke:NonExistent|main}}")
        self.assertFalse(res.is_valid)
        self.assertTrue(res.has_lua_error)
        self.assertTrue(any("Galat skrip" in e or "Lua runtime error" in e for e in res.errors))

    def test_promotion_gate(self):
        # Failing validation result
        bad_val = ValidationResult(
            is_valid=False,
            errors=["Lua error occurred"],
            has_lua_error=True,
        )
        allowed, msg = self.engine.evaluate_promotion_gate(bad_val)
        self.assertFalse(allowed)
        self.assertIn("Promotion blocked", msg)

        # Successful validation result
        clean_val = ValidationResult(
            is_valid=True,
            errors=[],
            has_lua_error=False,
            has_unclosed_tag=False,
        )
        allowed, msg = self.engine.evaluate_promotion_gate(clean_val)
        self.assertTrue(allowed)
        self.assertIn("Promotion gate passed", msg)


class TestTemplateEcosystemManager(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.mock_en_client = MagicMock(spec=WikipediaClient)
        self.mock_id_client = MagicMock(spec=WikipediaClient)
        self.mock_scanner = MagicMock(spec=RecursiveDependencyScanner)
        self.mock_category_linker = MagicMock(spec=CategoryTreeLinker)
        self.mock_sandbox_engine = MagicMock(spec=SandboxTestcaseEngine)
        self.mock_wikidata_linker = MagicMock(spec=WikidataLinker)

        self.manager = TemplateEcosystemManager(
            scanner=self.mock_scanner,
            category_linker=self.mock_category_linker,
            sandbox_engine=self.mock_sandbox_engine,
            wikidata_linker=self.mock_wikidata_linker,
            en_client=self.mock_en_client,
            id_client=self.mock_id_client,
        )

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_discover_subpages(self):
        # Mock en_client to return content only for /config and /data
        def fake_fetch(title, **kwargs):
            if title.endswith("/config") or title.endswith("/data"):
                return "return {}"
            raise PageNotFoundError("Not found")

        self.mock_en_client.fetch_wikitext.side_effect = fake_fetch
        subs = self.manager.discover_subpages("Module:Navbox")
        self.assertIn("Module:Navbox/config", subs)
        self.assertIn("Module:Navbox/data", subs)
        self.assertNotIn("Module:Navbox/i18n", subs)

    def test_full_orchestration_workflow(self):
        # Setup mock dependencies
        root_node = DependencyNode(
            title="Template:Infobox film",
            kind=DependencyKind.TEMPLATE,
            exists_on_id=False,
            dependencies=["Module:Infobox", "Template:Formatdate"],
            missing_dependencies=["Module:Infobox"],
            content="{{#invoke:Infobox|main}}",
        )
        mod_node = DependencyNode(
            title="Module:Infobox",
            kind=DependencyKind.MODULE,
            exists_on_id=False,
            dependencies=[],
            missing_dependencies=[],
            content="return {}",
        )
        self.mock_scanner.scan_dependencies_recursive.return_value = {
            "Template:Infobox film": root_node,
            "Module:Infobox": mod_node,
        }
        self.mock_scanner.topological_sort.return_value = [
            "Module:Infobox",
            "Template:Infobox film",
        ]

        self.mock_sandbox_engine.get_sandbox_title.return_value = "Template:Infobox film/bak pasir"
        self.mock_sandbox_engine.get_testcases_title.return_value = "Template:Infobox film/kasus uji"
        self.mock_sandbox_engine.generate_sandbox_wikitext.return_value = "Sandbox wikitext content"
        self.mock_sandbox_engine.generate_testcase_wikitext.return_value = "Testcase wikitext content"

        # Mock clean validation passing promotion gate
        clean_val = ValidationResult(is_valid=True, errors=[])
        self.mock_sandbox_engine.simulate_parse.return_value = clean_val
        self.mock_sandbox_engine.evaluate_promotion_gate.return_value = (True, "Gate passed")

        # Mock Wikidata QID
        self.mock_wikidata_linker.get_item_id_from_enwiki.return_value = "Q11111"

        report = self.manager.sync_ecosystem(
            "Template:Infobox film",
            publish_sandbox=True,
            promote=True,
            output_dir=self.tmp_dir,
        )

        self.assertEqual(report["root_title"], "Template:Infobox film")
        self.assertEqual(report["topological_order"], ["Module:Infobox", "Template:Infobox film"])
        self.assertIn("Template:Infobox film", report["missing_dependencies"])
        self.assertTrue(report["promotion"]["can_promote"])
        self.assertTrue(report["promotion"]["promoted"])
        self.assertEqual(report["wikidata"]["item_id"], "Q11111")

        # Check saved files in output_dir
        self.assertTrue((self.tmp_dir / "Template_Infobox_film_sandbox.wikitext").exists())
        self.assertTrue((self.tmp_dir / "Template_Infobox_film_testcases.wikitext").exists())
        self.assertTrue((self.tmp_dir / "Template_Infobox_film_report.json").exists())

    def test_default_ecosystem_manager_instance(self):
        self.assertIsInstance(default_ecosystem_manager, TemplateEcosystemManager)


if __name__ == "__main__":
    unittest.main()
