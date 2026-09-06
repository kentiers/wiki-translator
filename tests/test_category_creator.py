import unittest
from unittest.mock import MagicMock, patch

from wiki_translator.category_creator import (
    CategoryCreationPlan,
    CategoryCreationPlanner,
)
from wiki_translator.cli import main


class TestCategoryCreationPlanner(unittest.TestCase):
    def test_build_plan_inventories_mapped_dependencies_docs_and_parents(self):
        en_client = MagicMock()
        id_client = MagicMock()

        def en_get(params):
            if params.get("prop") == "revisions":
                return ({"query": {"pages": [{"pageid": 1, "revisions": [{
                    "revid": 123,
                    "timestamp": "2026-09-05T00:00:00Z",
                    "slots": {"main": {"content": (
                        "{{Foo}}\n{{#invoke:Bar|main}}\n{{DEFAULTSORT:Test}}\n"
                        "[[Category:Films by director|Test]]"
                    )}},
                }]}]}}, None)
            if params.get("prop") == "categories":
                return ({"query": {"pages": [{"categories": [
                    {"title": "Category:Films by director"}
                ]}]}}, None)
            if params.get("prop") == "langlinks":
                return ({"query": {"pages": [
                    {"title": "Template:Foo", "langlinks": [{"title": "Templat:Foo id"}]},
                    {"title": "Module:Bar", "langlinks": [{"title": "Modul:Bar id"}]},
                    {"title": "Category:Films by director", "langlinks": [{"title": "Kategori:Film menurut sutradara"}]},
                ]}}, None)
            return ({"query": {"pages": [
                {"title": "Template:Foo/doc", "pageid": 9}
            ]}}, None)

        def id_get(params):
            titles = params["titles"].split("|")
            pages = []
            existing = {"Templat:Foo id", "Templat:Foo id/doc", "Kategori:Film menurut sutradara"}
            for index, title in enumerate(titles, start=1):
                pages.append({"title": title, "pageid": index} if title in existing else {"title": title, "missing": True})
            return ({"query": {"pages": pages}}, None)

        en_client.get.side_effect = en_get
        id_client.get.side_effect = id_get
        plan = CategoryCreationPlanner(en_client=en_client, id_client=id_client).build_plan(
            "Test films", "Film uji"
        )

        self.assertEqual(plan.source_oldid, 123)
        self.assertFalse(plan.target_exists)
        self.assertEqual([item.kind for item in plan.dependencies], ["template", "module"])
        category_request = next(
            call.args[0] for call in en_client.get.call_args_list
            if call.args[0].get("prop") == "categories"
        )
        self.assertEqual(category_request["clshow"], "!hidden")
        self.assertTrue(plan.dependencies[0].exists_on_id)
        self.assertTrue(plan.dependencies[0].doc_exists_on_en)
        self.assertTrue(plan.dependencies[0].doc_exists_on_id)
        self.assertFalse(plan.dependencies[1].exists_on_id)
        self.assertEqual(plan.parent_categories[0].id_title, "Kategori:Film menurut sutradara")
        self.assertEqual(plan.parent_categories[0].sort_key, "Test")
        self.assertEqual(plan.blockers, [])
        self.assertIn("revisi 123", plan.attribution)

    def test_unresolved_dependency_and_parent_are_blockers(self):
        planner = CategoryCreationPlanner(en_client=MagicMock(), id_client=MagicMock())
        planner._fetch_source = MagicMock(return_value=("{{Unknown}}", 5, "now"))
        planner._fetch_rendered_parents = MagicMock(return_value=["Category:Unknown parent"])
        planner._resolve_id_titles = MagicMock(return_value={})
        planner._existing_titles = MagicMock(return_value=set())

        plan = planner.build_plan("Test", "Uji")

        self.assertEqual(len(plan.blockers), 2)

    def test_cli_category_creation_plan_is_read_only(self):
        plan = CategoryCreationPlan(
            en_category="Category:Test",
            id_category="Kategori:Uji",
            source_oldid=5,
            source_timestamp="now",
            source_wikitext="",
            target_exists=False,
        )
        with patch(
            "sys.argv",
            ["wiki-translator", "--plan-category-creation", "Test", "--id-category", "Uji"],
        ), patch("wiki_translator.cli.WikiTranslatorCLI"), patch(
            "wiki_translator.cli.default_category_creation_planner.build_plan",
            return_value=plan,
        ) as build_plan:
            main()

        build_plan.assert_called_once_with("Test", "Uji")


if __name__ == "__main__":
    unittest.main()
