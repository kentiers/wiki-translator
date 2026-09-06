import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from wiki_translator.category_creator import (
    CategoryCreationPlan,
    CategoryDependency,
    ParentCategoryMapping,
)
from wiki_translator.category_materializer import (
    CategoryMaterializationResult,
    CategoryMaterializer,
)
from wiki_translator.cli import main


class TestCategoryMaterializer(unittest.TestCase):
    def test_materializes_localized_structure_and_reports_missing_parent(self):
        id_client = MagicMock()
        id_client.post.return_value = ({"parse": {"text": "ok"}}, None)
        plan = CategoryCreationPlan(
            en_category="Category:Films directed by Test",
            id_category="Kategori:Film yang disutradarai oleh Test",
            source_oldid=10,
            source_timestamp="now",
            source_wikitext=(
                "A category about films.\n{{Commons category}}\n"
                "{{#invoke:Foo|main}}\n{{DEFAULTSORT:Test}}\n"
                "[[Category:Films by American directors]]"
            ),
            target_exists=False,
            dependencies=[
                CategoryDependency("Template:Commons category", "template", "Templat:Commonscat", True),
                CategoryDependency("Module:Foo", "module", "Modul:Foo id", True),
            ],
            parent_categories=[
                ParentCategoryMapping(
                    "Category:Films by American directors",
                    "Kategori:Film menurut sutradara Amerika Serikat",
                    True,
                ),
                ParentCategoryMapping("Category:Works by Test", None, False, "directed"),
            ],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            result = CategoryMaterializer(
                id_client=id_client,
                translate_plain_text=lambda text: {
                    "A category about films.": "Kategori tentang film.",
                    "directed": "disutradarai",
                }[text],
            ).materialize(plan, Path(temp_dir))

            self.assertIn("Kategori tentang film.", result.wikitext)
            self.assertIn("{{Commonscat}}", result.wikitext)
            self.assertIn("{{#invoke:Foo id|main}}", result.wikitext)
            self.assertIn("{{DEFAULTSORT:Test}}", result.wikitext)
            self.assertIn("[[Kategori:Film menurut sutradara Amerika Serikat]]", result.wikitext)
            self.assertNotIn("[[Category:", result.wikitext)
            self.assertEqual(result.required_parent_categories, ["Kategori:Karya Test"])
            self.assertIn("[[Kategori:Karya Test|disutradarai]]", result.wikitext)
            self.assertFalse(result.publication_ready)
            self.assertTrue(Path(result.output_path).exists())
            self.assertTrue(Path(result.output_path).with_suffix(".json").exists())
            self.assertTrue(Path(result.approval_manifest_path).exists())
            self.assertTrue(Path(result.journal_path).exists())

    def test_does_not_emit_mixed_language_parent_fallback(self):
        id_client = MagicMock()
        id_client.post.return_value = ({"parse": {"text": "ok"}}, None)
        plan = CategoryCreationPlan(
            en_category="Category:Test",
            id_category="Kategori:Uji",
            source_oldid=1,
            source_timestamp="now",
            source_wikitext="konten",
            target_exists=False,
            parent_categories=[ParentCategoryMapping("Category:Works by American filmmakers", None, False)],
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = CategoryMaterializer(
                id_client=id_client, translate_plain_text=lambda text: text
            ).materialize(plan, Path(tmp))
        self.assertNotIn("Kategori:Karya American filmmakers", result.wikitext)
        self.assertTrue(any("Untranslated parent category" in item for item in result.blockers))

    def test_unresolved_dependency_blocks_publication(self):
        id_client = MagicMock()
        id_client.post.return_value = ({"parse": {"text": "ok"}}, None)
        plan = CategoryCreationPlan(
            en_category="Category:Test",
            id_category="Kategori:Uji",
            source_oldid=1,
            source_timestamp="now",
            source_wikitext="{{Unknown}}",
            target_exists=False,
            dependencies=[CategoryDependency("Template:Unknown", "template", None, False)],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            result = CategoryMaterializer(id_client=id_client).materialize(plan, Path(temp_dir))

        self.assertEqual(result.blockers, ["Unresolved dependency: Template:Unknown"])
        self.assertFalse(result.publication_ready)

    def test_cli_materializes_locally_without_publisher(self):
        plan = CategoryCreationPlan(
            en_category="Category:Test",
            id_category="Kategori:Uji",
            source_oldid=1,
            source_timestamp="now",
            source_wikitext="",
            target_exists=False,
        )
        result = CategoryMaterializationResult(
            title="Kategori:Uji",
            wikitext="",
            output_path="output/categories/uji.wikitext",
            publication_ready=True,
        )
        with patch(
            "sys.argv",
            ["wiki-translator", "--materialize-category", "Test", "--id-category", "Uji"],
        ), patch("wiki_translator.cli.WikiTranslatorCLI"), patch(
            "wiki_translator.cli.default_category_creation_planner.build_plan",
            return_value=plan,
        ), patch("wiki_translator.cli.CategoryMaterializer") as materializer:
            materializer.return_value.materialize.return_value = result
            main()

        materializer.return_value.materialize.assert_called_once()


if __name__ == "__main__":
    unittest.main()
