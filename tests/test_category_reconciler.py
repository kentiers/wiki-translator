import unittest
from unittest.mock import MagicMock, patch

from wiki_translator.category_reconciler import (
    CategoryCandidate,
    CategoryReconciler,
    CategoryReconciliationPlan,
)
from wiki_translator.cli import main


class TestCategoryReconciler(unittest.TestCase):
    def test_build_plan_uses_direct_members_and_official_sitelinks(self):
        en_client = MagicMock()
        id_client = MagicMock()

        def en_get(params):
            if params.get("list") == "categorymembers":
                if params["cmtitle"] == "Category:Films by Test Director":
                    return ({"query": {"categorymembers": [
                        {"ns": 0, "title": "Film One"},
                        {"ns": 14, "title": "Category:Test Director sequels"},
                    ]}}, None)
                return ({"query": {"categorymembers": [{"ns": 0, "title": "Film Two"}]}}, None)
            pages = [
                {"title": "Film One", "langlinks": [{"title": "Film Satu"}]},
                {"title": "Film Two", "langlinks": [{"title": "Film Dua"}]},
            ]
            requested = set(params["titles"].split("|"))
            return ({"query": {"pages": [page for page in pages if page["title"] in requested]}}, None)

        def id_get(params):
            if params.get("list") == "categorymembers":
                return ({"query": {"categorymembers": [{"ns": 0, "title": "Film Satu"}]}}, None)
            return ({"query": {"pages": [{"pageid": 99, "title": "Kategori:Film menurut sutradara uji"}]}}, None)

        en_client.get.side_effect = en_get
        id_client.get.side_effect = id_get
        reconciler = CategoryReconciler(en_client=en_client, id_client=id_client)
        plan = reconciler.build_plan(
            "Films by Test Director",
            "Film menurut sutradara uji",
        )

        self.assertTrue(plan.category_exists)
        self.assertEqual(plan.en_member_count, 1)
        self.assertEqual(plan.resolved_count, 1)
        self.assertEqual(plan.existing_member_count, 1)
        self.assertEqual(plan.candidates, [])

    def test_recursive_flattening_is_rejected(self):
        reconciler = CategoryReconciler(en_client=MagicMock(), id_client=MagicMock())

        with self.assertRaisesRegex(ValueError, "flattening is unsafe"):
            reconciler.build_plan("Films by Test Director", "Film menurut sutradara uji", recursive=True)

    def test_apply_rechecks_membership_and_edits_idempotently(self):
        id_client = MagicMock()
        plan = CategoryReconciliationPlan(
            en_category="Category:Example",
            id_category="Kategori:Contoh",
            category_exists=True,
            en_member_count=2,
            resolved_count=2,
            existing_member_count=0,
            candidates=[
                CategoryCandidate("One", "Satu"),
                CategoryCandidate("Two", "Dua"),
            ],
        )

        def get(params):
            if params.get("type") == "login":
                return ({"query": {"tokens": {"logintoken": "LOGIN"}}}, None)
            if params.get("type") == "csrf":
                return ({"query": {"tokens": {"csrftoken": "CSRF"}}}, None)
            if params.get("titles") == "Satu":
                return ({"curtimestamp": "2026-09-05T00:00:01Z", "query": {"pages": [{
                    "pageid": 1,
                "categories": [
                    {"title": "Kategori:Lain"},
                    {"title": "Kategori:Contoh"},
                ],
                    "revisions": [{"timestamp": "2026-09-04T00:00:00Z"}],
                }]}}, None)
            return ({"curtimestamp": "2026-09-05T00:00:02Z", "query": {"pages": [{
                "pageid": 2,
                "revisions": [{"timestamp": "2026-09-04T00:00:00Z"}],
            }]}}, None)

        def post(params):
            if params.get("action") == "login":
                return ({"login": {"result": "Success"}}, None)
            return ({"edit": {"result": "Success"}}, None)

        id_client.get.side_effect = get
        id_client.post.side_effect = post
        reconciler = CategoryReconciler(
            en_client=MagicMock(), id_client=id_client, pause_seconds=0
        )
        result = reconciler.apply_plan(plan, "User@Bot", "password")

        self.assertEqual(result["skipped"], ["Satu"])
        self.assertEqual(result["applied"], ["Dua"])
        edit_params = id_client.post.call_args_list[-1].args[0]
        self.assertEqual(edit_params["appendtext"], "\n[[Kategori:Contoh]]")
        self.assertEqual(edit_params["basetimestamp"], "2026-09-04T00:00:00Z")
        self.assertEqual(edit_params["starttimestamp"], "2026-09-05T00:00:02Z")
        self.assertEqual(edit_params["nocreate"], "1")
        self.assertEqual(edit_params["assert"], "user")

    def test_apply_does_not_skip_article_with_unrelated_categories(self):
        client = MagicMock()
        plan = CategoryReconciliationPlan(
            en_category="Category:Example", id_category="Kategori:Contoh",
            category_exists=True, en_member_count=1, resolved_count=1,
            existing_member_count=0, candidates=[CategoryCandidate("One", "Satu")],
        )
        def get(params):
            if params.get("type") == "login":
                return ({"query": {"tokens": {"logintoken": "L"}}}, None)
            if params.get("type") == "csrf":
                return ({"query": {"tokens": {"csrftoken": "C"}}}, None)
            return ({"query": {"pages": [{"pageid": 1, "categories": [{"title": "Kategori:Lain"}]}], "curtimestamp": "now"}}, None)
        client.get.side_effect = get
        client.post.side_effect = lambda params: ({"login": {"result": "Success"}}, None) if params.get("action") == "login" else ({"edit": {"result": "Success"}}, None)
        result = CategoryReconciler(en_client=MagicMock(), id_client=client, pause_seconds=0).apply_plan(plan, "u", "p")
        self.assertEqual(result["applied"], ["Satu"])

    def test_apply_refuses_missing_category(self):
        plan = CategoryReconciliationPlan(
            en_category="Category:Example",
            id_category="Kategori:Contoh",
            category_exists=False,
            en_member_count=1,
            resolved_count=1,
            existing_member_count=0,
        )
        with self.assertRaisesRegex(ValueError, "does not exist"):
            CategoryReconciler().apply_plan(plan, "User@Bot", "password")

    def test_cli_is_dry_run_by_default(self):
        plan = CategoryReconciliationPlan(
            en_category="Category:Example",
            id_category="Kategori:Contoh",
            category_exists=True,
            en_member_count=1,
            resolved_count=1,
            existing_member_count=0,
            candidates=[CategoryCandidate("One", "Satu")],
        )
        with patch(
            "sys.argv",
            ["wiki-translator", "--reconcile-category", "Example", "--id-category", "Contoh"],
        ), patch("wiki_translator.cli.WikiTranslatorCLI"), patch(
            "wiki_translator.cli.default_category_reconciler.build_plan", return_value=plan
        ), patch("wiki_translator.cli.default_category_reconciler.apply_plan") as apply_plan:
            main()
        apply_plan.assert_not_called()


if __name__ == "__main__":
    unittest.main()
