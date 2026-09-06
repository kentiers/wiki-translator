import unittest
from unittest.mock import MagicMock

from wiki_translator.category_tree_audit import CategoryDiffAuditor, CategoryTreePlanner
from wiki_translator.category_reconciler import CategoryCandidate


class TestCategoryTreeAudit(unittest.TestCase):
    def test_tree_planner_keeps_each_parent_as_own_node(self):
        planner = MagicMock()
        planner.build_plan.side_effect = [
            MagicMock(target_exists=False, blockers=[], parent_categories=[MagicMock(en_title="Category:Parent", id_title="Kategori:Induk")]),
            MagicMock(target_exists=True, blockers=[], parent_categories=[]),
        ]
        result = CategoryTreePlanner(planner).build_plan("Root", "Target", max_depth=2)
        self.assertEqual([node.en_category for node in result.nodes], ["Category:Root", "Category:Parent"])

    def test_diff_audit_reports_missing_extra_and_subcategories(self):
        reconciler = MagicMock()
        reconciler._category_title.side_effect = lambda title, lang: f"Category:{title}" if lang == "en" else f"Kategori:{title}"
        reconciler._fetch_members.side_effect = [
            (["One", "Two"], ["Category:Nested"]),
            (["Satu", "Extra"], ["Kategori:Lain"]),
        ]
        reconciler._resolve_id_titles.return_value = ([CategoryCandidate("One", "Satu"), CategoryCandidate("Two", "Dua")], [])
        audit = CategoryDiffAuditor(reconciler).audit("Root", "Akar")
        self.assertEqual([item.id_title for item in audit.missing_articles], ["Dua"])
        self.assertEqual(audit.extra_id_articles, ["Extra"])
        self.assertEqual(audit.en_subcategories, ["Category:Nested"])
        self.assertEqual(audit.id_subcategories, ["Kategori:Lain"])


if __name__ == "__main__":
    unittest.main()
