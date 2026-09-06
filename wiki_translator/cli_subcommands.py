"""
Subcommand execution handlers for Wiki Translator Suite CLI.

Extracts distinct execution domains (glossary actions, category management,
template ecosystem, page queue generation, and batch translation) from
the main CLI orchestrator. Accesses domain singletons via the parent
cli facade module to maintain 100% compatibility with test mocks.
"""

import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional

from .cli_ui import slugify
from .glossary_memory import GlossaryMemory
from .category_page_sync import CategoryPageSyncResult, CategoryPageSynchronizer


def _get_cli_module():
    """Dynamically resolves the wiki_translator.cli module so patched symbols are respected."""
    import wiki_translator.cli as cli_module
    return cli_module

def handle_storage_commands(args: argparse.Namespace, parser: argparse.ArgumentParser) -> bool:
    """Handles cache status inspection and clearing."""
    from .storage_manager import default_storage_manager, KNOWN_DATABASES

    if args.cache_status:
        print("\n" + "=" * 76)
        print(" 💾 WIKI TRANSLATOR SUITE - CACHE & DATABASE STATUS")
        print("=" * 76)
        print(f" Cache Directory  : {default_storage_manager.cache_dir}")
        print(f" Output Directory : {default_storage_manager.output_dir}")
        print(f" Data Directory   : {default_storage_manager.data_dir}")
        print("-" * 76)
        print(f"{'Database Key':<24} {'Status':<10} {'Size (KB)':<12} {'Filename'}")
        print("-" * 76)
        inspected = default_storage_manager.inspect_databases()
        total_kb = 0.0
        for item in inspected:
            status = "[ADA]" if item["exists"] else "[KOSONG]"
            size_str = f"{item['size_kb']:,.2f}" if item["exists"] else "-"
            total_kb += item["size_kb"]
            print(f"{item['key']:<24} {status:<10} {size_str:<12} {item['filename']}")
        print("-" * 76)
        print(f" Total Cache Size : {total_kb:,.2f} KB ({round(total_kb / 1024.0, 2)} MB)")
        print("=" * 76 + "\n")
        return True

    if args.clear_cache:
        target = args.clear_cache.lower().strip()
        print(f"[*] Clearing cache target: '{target}'...")
        if target == "all":
            results = default_storage_manager.clear_all_caches()
            cleared_count = sum(1 for v in results.values() if v)
            print(f"[+] Cleared {cleared_count} temporary cache database(s).")
        else:
            alias_map = {
                "translation": "translation_cache",
                "glossary": "glossary_cache",
                "glossary_memory": "glossary_memory",
                "wayback": "wayback_cache",
                "workspace": "workspace_glossary",
                "templates": "wiki_templates_cache",
                "links": "wiki_links_cache",
            }
            resolved_key = alias_map.get(target, target)
            if resolved_key not in KNOWN_DATABASES:
                valid_keys = list(KNOWN_DATABASES.keys()) + list(alias_map.keys())
                parser.error(
                    f"Unknown cache target '{target}'. Valid targets: {', '.join(sorted(set(valid_keys)))}"
                )
            ok = default_storage_manager.clear_database(resolved_key)
            if ok:
                print(f"[+] Successfully cleared database '{resolved_key}'.")
            else:
                print(f"[*] Database '{resolved_key}' was already empty or not found.")
        return True

    return False


def handle_glossary_actions(args: argparse.Namespace, parser: argparse.ArgumentParser) -> bool:
    """Handles glossary memory listing, revision extraction, approval, and rejection."""
    glossary_actions = sum(
        bool(value)
        for value in (
            args.list_glossary_candidates,
            args.learn_glossary_revision,
            args.approve_glossary,
            args.reject_glossary,
        )
    )
    if not glossary_actions:
        return False

    if glossary_actions > 1:
        parser.error("Use only one glossary memory action at a time")

    if args.learn_glossary_revision:
        try:
            draft, revised = (
                Path(filename).read_text(encoding="utf-8-sig")
                for filename in args.learn_glossary_revision
            )
        except (OSError, UnicodeError) as exc:
            parser.error(f"Cannot read glossary revision files: {exc}")
        memory = GlossaryMemory(args.glossary_memory)
        rows = memory.propose_from_revision(draft, revised, topic=args.glossary_topic)
        print(json.dumps([item.__dict__ for item in rows], ensure_ascii=False, indent=2))
        return True

    memory = GlossaryMemory(args.glossary_memory)
    if args.list_glossary_candidates:
        rows = [item.__dict__ for item in memory.list(args.glossary_topic, status="candidate")]
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return True

    expression = args.approve_glossary or args.reject_glossary
    if "=" not in expression:
        parser.error("Glossary term must use SOURCE=TARGET")
    source_term, target_term = expression.split("=", 1)
    if not source_term.strip() or not target_term.strip():
        parser.error("Glossary SOURCE and TARGET cannot be empty")
    approved = bool(args.approve_glossary)
    changed = (
        memory.approve(source_term, target_term, args.glossary_topic)
        if approved
        else memory.reject(source_term, target_term, args.glossary_topic)
    )
    print(json.dumps({"changed": changed, "status": "approved" if approved else "rejected"}))
    return True


def handle_ecosystem_and_category_commands(
    args: argparse.Namespace, parser: argparse.ArgumentParser, cli: Any
) -> bool:
    """Dispatches category reconciliation/materialization and template ecosystem commands."""
    mod = _get_cli_module()

    if args.check_publish_gate:
        if not args.approval_manifest:
            parser.error("--approval-manifest required with --check-publish-gate")
        result = mod.PublishGate().check(
            args.check_publish_gate,
            Path(args.approval_manifest),
            expected_revision=args.expected_revision,
            allow_existing=args.allow_existing_target,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return True

    if args.deploy_dependencies:
        result = mod.default_dependency_deployer.deploy(
            args.deploy_dependencies,
            output_dir=Path(args.output_dir) / "dependencies",
            max_depth=max(0, args.category_depth),
        )
        print(f"[*] Dependency order : {len(result.order)}")
        print(f"[+] Reused : {len(result.reused)}")
        print(f"[+] Drafted : {len(result.drafted)}")
        print(f"[!] Blocked : {len(result.blocked)}")
        print(f"[*] Report : {result.report_path}")
        print("[*] Approval manifest : pending (review and approve before any future publish workflow)")
        for item in result.blocked:
            print(f" - {item}")
        print("[*] Sandbox/local output only. No pages were created or edited.")
        return True

    if args.plan_category_tree:
        if not args.id_category:
            parser.error("--id-category is required with --plan-category-tree")
        tree = mod.default_category_tree_planner.build_plan(
            args.plan_category_tree,
            args.id_category,
            max_depth=max(0, args.category_depth),
            max_nodes=args.reconcile_limit,
        )
        for node in tree.nodes:
            print(
                f"{'  ' * node.depth}- {node.en_category} -> {node.id_category or 'unresolved'} "
                f"({'exists' if node.target_exists else 'missing'})"
            )
            for blocker in node.blockers:
                print(f"{'  ' * (node.depth + 1)}[!] {blocker}")
        if tree.cycles:
            print(f"[!] Cycles : {', '.join(tree.cycles)}")
        if tree.truncated:
            print("[!] Tree truncated by safety limit")
        print("[*] Read-only plan. No pages were created or edited.")
        return True

    if args.audit_category_diff:
        if not args.id_category:
            parser.error("--id-category is required with --audit-category-diff")
        audit = mod.default_category_diff_auditor.audit(
            args.audit_category_diff, args.id_category, limit=max(1, args.reconcile_limit)
        )
        print(f"[*] Category : {audit.en_category} -> {audit.id_category}")
        print(f"[*] Expected mapped articles : {len(audit.expected_articles)}")
        print(f"[!] Missing articles : {len(audit.missing_articles)}")
        for item in audit.missing_articles:
            print(f" + {item.id_title} <- {item.en_title}")
        print(f"[!] Extra idwiki articles : {len(audit.extra_id_articles)}")
        for title in audit.extra_id_articles:
            print(f" - {title} (review only; not removed)")
        print(f"[*] enwiki subcategories : {len(audit.en_subcategories)}")
        print(f"[*] idwiki subcategories : {len(audit.id_subcategories)}")
        print("[*] Read-only audit. No pages were created, edited, or deleted.")
        return True

    if args.sync_category_page:
        if not args.id_category:
            parser.error("--id-category required with --sync-category-page")
        syncer = CategoryPageSynchronizer(
            en_client=mod.default_category_creation_planner.en_client,
            id_client=mod.default_category_creation_planner.id_client,
            translate_plain_text=lambda text: cli.gemini_client.translate_section(
                f"Terjemahkan ke bahasa Indonesia, keluarkan hanya hasilnya:\n\n{text}",
                system_instruction="Pertahankan markup dan fakta.",
                source_text=text,
                topic=args.topic,
                section_title=args.sync_category_page,
            ),
        )
        overrides = {}
        for item in args.parent_override:
            if "=" not in item:
                parser.error("--parent-override must use EN=ID")
            source, target = item.split("=", 1)
            if source.strip() and target.strip():
                overrides[source.strip()] = target.strip()
        result = syncer.sync(
            args.sync_category_page,
            args.id_category,
            Path(args.output_dir) / "categories",
            category_overrides=overrides,
        )
        print(f"[+] Draft : {result.output_path}")
        print(f"[*] Changed : {'yes' if result.changed else 'no'}")
        for warning in result.warnings:
            print(f"[!] Warning : {warning}")
        print("[*] Local output only. No pages were edited.")
        return True

    if args.publish_category_page:
        if not args.id_category:
            parser.error("--id-category required with --publish-category-page")
        username = os.environ.get("WIKI_USERNAME") or os.environ.get("MEDIAWIKI_USERNAME")
        bot_password = os.environ.get("WIKI_BOT_PASSWORD") or os.environ.get("MEDIAWIKI_BOT_PASSWORD")
        if not username or not bot_password:
            print("[!] Publish blocked: WIKI_USERNAME/WIKI_BOT_PASSWORD unavailable.")
            return True
        syncer = CategoryPageSynchronizer(
            en_client=mod.default_category_creation_planner.en_client,
            id_client=mod.default_category_creation_planner.id_client,
        )
        safe = re.sub(r'[\\/*?:"<>|]+', "_", args.id_category)
        draft_path = Path(args.output_dir) / "categories" / f"{safe}.wikitext"
        manifest_path = Path(args.output_dir) / "categories" / "approval-manifest.json"
        if not draft_path.exists() or not manifest_path.exists():
            print("[!] Publish blocked: category draft or approval manifest missing.")
            return True
        source, oldid = syncer._fetch(syncer.en_client, args.publish_category_page)
        existing, _ = syncer._fetch(syncer.id_client, args.id_category)
        result = CategoryPageSyncResult(
            args.publish_category_page,
            args.id_category,
            oldid,
            draft_path.read_text(encoding="utf-8"),
            existing,
            draft_path.read_text(encoding="utf-8") != existing,
            [],
            str(draft_path),
            str(manifest_path),
        )
        publish_result = syncer.publish(result, username, bot_password)
        print(json.dumps(publish_result, ensure_ascii=False, indent=2))
        return True

    if args.materialize_category:
        if not args.id_category:
            parser.error("--id-category is required with --materialize-category")
        plan = mod.default_category_creation_planner.build_plan(
            args.materialize_category, args.id_category
        )

        def translate_category_line(text: str) -> str:
            return cli.gemini_client.translate_section(
                (
                    "Terjemahkan teks kategori Wikipedia berikut ke bahasa Indonesia "
                    "yang alami. Pertahankan nama diri. Keluarkan hanya hasil terjemahan.\n\n"
                    f"Teks: {text}"
                ),
                system_instruction=(
                    "Anda penerjemah Wikipedia bahasa Indonesia. Jangan menambah fakta, "
                    "markup, penjelasan, atau tanda kutip."
                ),
                source_text=text,
                topic=args.topic,
                section_title=plan.en_category,
            )

        materializer = mod.CategoryMaterializer(
            id_client=mod.default_category_creation_planner.id_client,
            translate_plain_text=translate_category_line,
        )
        overrides = {}
        for item in args.parent_override:
            if "=" not in item:
                parser.error("--parent-override must use EN=ID")
            source, target = item.split("=", 1)
            if source.strip() and target.strip():
                overrides[source.strip()] = target.strip()
        result = materializer.materialize(
            plan,
            Path(args.output_dir) / "categories",
            parent_overrides=overrides,
        )
        print(f"[+] Draft : {result.output_path}")
        print(f"[*] Publication ready : {'yes' if result.publication_ready else 'no'}")
        for title in result.required_dependencies:
            print(f"[!] Required dependency : {title}")
        for title in result.required_parent_categories:
            print(f"[!] Required parent category : {title}")
        for blocker in result.blockers:
            print(f"[!] Blocker : {blocker}")
        for warning in result.warnings:
            print(f"[!] Warning : {warning}")
        print("[*] Local output only. No pages were created or edited.")
        return True

    if args.plan_category_creation:
        if not args.id_category:
            parser.error("--id-category is required with --plan-category-creation")
        plan = mod.default_category_creation_planner.build_plan(
            args.plan_category_creation, args.id_category
        )
        print(f"[*] Source category : {plan.en_category} (oldid {plan.source_oldid})")
        print(f"[*] Target category : {plan.id_category}")
        print(f"[*] Target exists : {'yes' if plan.target_exists else 'no'}")
        print(f"[*] Attribution : {plan.attribution}")
        print(f"[*] Dependencies : {len(plan.dependencies)}")
        for item in plan.dependencies:
            status = "reuse" if item.exists_on_id else "missing" if item.id_title else "unresolved"
            target = item.id_title or "no idwiki sitelink"
            print(f" {status:10} {item.en_title} -> {target}")
            if item.en_doc_title and item.doc_exists_on_en:
                doc_status = "reuse" if item.doc_exists_on_id else "missing"
                print(f" {doc_status:10} {item.en_doc_title} -> {item.id_doc_title or 'unresolved'}")
        print(f"[*] Parent categories : {len(plan.parent_categories)}")
        for item in plan.parent_categories:
            status = "reuse" if item.exists_on_id else "missing" if item.id_title else "unresolved"
            print(f" {status:10} {item.en_title} -> {item.id_title or 'no idwiki sitelink'}")
        print(f"[!] Blockers : {len(plan.blockers)}")
        for blocker in plan.blockers:
            print(f" - {blocker}")
        print("[*] Dry-run only. No pages were created or edited.")
        return True

    if args.reconcile_category:
        if not args.id_category:
            parser.error("--id-category is required with --reconcile-category")
        if args.recursive_category:
            parser.error(
                "--recursive-category is unsafe until subcategories can be mapped individually"
            )
        plan = mod.default_category_reconciler.build_plan(
            en_category=args.reconcile_category,
            id_category=args.id_category,
            limit=max(1, args.reconcile_limit),
            recursive=args.recursive_category,
            max_depth=max(0, args.category_depth),
        )
        print(f"[*] Source category : {plan.en_category}")
        print(f"[*] Target category : {plan.id_category}")
        print(f"[*] Target exists : {'yes' if plan.category_exists else 'no'}")
        print(f"[*] enwiki members : {plan.en_member_count}")
        print(f"[*] Resolved to idwiki : {plan.resolved_count}")
        print(f"[*] Existing members : {plan.existing_member_count}")
        print(f"[*] Proposed additions : {len(plan.candidates)}")
        for candidate in plan.candidates:
            print(f"  + {candidate.id_title} <- {candidate.en_title}")
        if not args.apply_category_edits:
            print("[*] Dry-run only. Use --apply-category-edits to apply this exact plan.")
            return True
        username = os.environ.get("WIKI_USERNAME") or os.environ.get("MEDIAWIKI_USERNAME")
        bot_password = os.environ.get("WIKI_BOT_PASSWORD") or os.environ.get("MEDIAWIKI_BOT_PASSWORD")
        if not username or not bot_password:
            parser.error("WIKI_USERNAME and WIKI_BOT_PASSWORD are required to apply category edits")
        result = mod.default_category_reconciler.apply_plan(plan, username, bot_password)
        print(f"[+] Applied : {len(result['applied'])}")
        print(f"[*] Skipped : {len(result['skipped'])}")
        print(f"[!] Failed : {len(result['failed'])}")
        return True

    if args.review_article:
        print(f"[*] Auditing and reviewing article '{args.review_article}' against en.wiki and WP:KAP...")
        report, review_text, polished = mod.default_article_reviewer.audit_and_report(args.review_article)
        clean_filename = re.sub(r'[\\/*?:"<>| ]', "_", args.review_article)
        review_path = Path("output/reviews") / f"{clean_filename}_review.md"
        polished_path = Path("output/reviews") / f"{clean_filename}_polished.wikitext"
        print("\n" + "=" * 60)
        print(f" WP:KAP AUDIT SCORECARD: {report.title}")
        print("=" * 60)
        print(f" Skor Keseluruhan   : {report.overall_score}/100")
        print(f" Status Kelayakan   : {report.verdict}")
        print(f" Kesalahan Fatal    : {len(report.fatal_errors)}")
        print(f" Kalkir / Slop MT   : {len(report.calque_issues)}")
        print(f" Tipografi / EYD    : {len(report.typo_issues)}")
        print(f" Rujukan / Kategori : {len(report.reference_issues)}")
        print("=" * 60)
        print(f"[+] Laporan ulasan komunitas disimpan ke: {review_path}")
        print(f"[+] Teks wikitext terpoles disimpan ke   : {polished_path}")
        print("=" * 60 + "\n")
        return True

    if args.sync_template:
        print(f"[*] Synchronizing template '{args.sync_template}' from en.wiki...")
        sync_res = mod.default_template_syncer.sync_template(
            args.sync_template,
            publish=args.publish_template,
            output_dir=Path(args.output_dir) / "templates" if args.output_dir else None,
        )
        print(f"[+] Template synced: {sync_res['id_title']} saved to {sync_res['template_file']}")
        print(f"[+] Documentation saved to {sync_res['doc_file']}")
        if args.publish_template:
            if sync_res.get("published"):
                print(f"[+] Published {sync_res['id_title']} and {sync_res['doc_title']} to id.wikipedia.org successfully.")
                wiki_info = sync_res.get("wikidata", {})
                if wiki_info:
                    if wiki_info.get("success"):
                        print(f"[+] Wikidata Terhubung   : {wiki_info.get('item_id')} -> {wiki_info.get('url')}")
                    else:
                        print(f"[!] Wikidata Linker Info : {wiki_info.get('error')}")
            else:
                err = sync_res.get("publish_results", {}).get("error", "Unknown error")
                print(f"[!] Warning: Failed to publish template: {err}")
        return True

    if args.scan_template_deps:
        print(f"[*] Scanning recursive dependency tree for '{args.scan_template_deps}'...")
        nodes = mod.default_ecosystem_manager.scanner.scan_dependencies_recursive(args.scan_template_deps)
        topo = mod.default_ecosystem_manager.scanner.topological_sort(nodes)
        print(f"[+] Total components discovered: {len(nodes)}")
        print("\n" + "=" * 60)
        print(" TOPOLOGICAL RESOLUTION ORDER (Prerequisites first):")
        print("=" * 60)
        for idx, title in enumerate(topo, 1):
            node = nodes.get(title)
            status = "[ADA]" if (node and node.exists_on_id) else "[BELUM ADA]"
            kind = node.kind.value if node else "item"
            deps_count = len(node.dependencies) if node else 0
            print(f"  {idx}. {status} ({kind}) {title} - {deps_count} sub-dependencies")
        print("=" * 60 + "\n")
        return True

    if args.sync_ecosystem:
        print(f"[*] Orchestrating template & module ecosystem sync for '{args.sync_ecosystem}'...")
        eco_res = mod.default_ecosystem_manager.sync_ecosystem(
            args.sync_ecosystem,
            publish_sandbox=True,
            promote=args.publish_template,
            output_dir=Path(args.output_dir) / "ecosystem" if args.output_dir else None,
        )
        print(f"[+] Root component        : {eco_res['root_title']}")
        print(f"[+] Discovered components : {len(eco_res['dependency_tree'])}")
        print(f"[+] Missing on id.wiki    : {len(eco_res['missing_dependencies'])}")
        print(f"[+] Sandbox Page          : {eco_res['sandbox']['title']}")
        print(f"[+] Testcases Page        : {eco_res['testcases']['title']}")
        val = eco_res.get("validation", {})
        print(f"[+] Pre-flight Validation : {'VALID' if val.get('is_valid') else 'INVALID'}")
        promo = eco_res.get("promotion", {})
        print(f"[+] Promotion Gate        : {promo.get('message')}")
        if args.publish_template and promo.get("promoted"):
            print("[+] Promoted successfully to mainspace!")
        return True

    return False


def handle_page_gen_commands(args: argparse.Namespace, parser: argparse.ArgumentParser) -> bool:
    """Handles smart page generation (backlinks / category queues)."""
    if not (args.gen_category or args.gen_backlinks):
        return False

    mod = _get_cli_module()
    limit = getattr(args, "queue_limit", 50)
    recursive = getattr(args, "queue_recursive", False)

    if args.gen_category:
        source_desc = f"en.wiki Category: {args.gen_category}"
        print(
            f"[*] AWB Smart Page Generator: Scanning en.wiki category '{args.gen_category}' "
            f"(limit={limit}, recursive={recursive})..."
        )
        generator = mod.CategoryPageGenerator(
            en_category=args.gen_category,
            limit=limit,
            recursive=recursive,
        )
        items = generator.generate()
    else:
        source_desc = f"en.wiki Backlinks: {args.gen_backlinks}"
        print(
            f"[*] AWB Smart Page Generator: Scanning inbound links/transclusions to '{args.gen_backlinks}' "
            f"(limit={limit})..."
        )
        generator = mod.WhatLinksHerePageGenerator(
            en_target_page=args.gen_backlinks,
            limit=limit,
        )
        items = generator.generate()

    print(f"[+] Found {len(items)} article(s) missing on id.wikipedia.org.")

    if args.dry_run_queue:
        print("\n--- Dry Run Queue (Console Output) ---")
        for idx, it in enumerate(items, 1):
            print(f"  [{idx}] {it.en_title} -> {it.predicted_id_title} ({it.status})")
        print("--------------------------------------\n")
        return True

    out_file = args.output_queue
    if not out_file:
        slug = slugify(args.gen_category or args.gen_backlinks or "queue")
        prefix = "category" if args.gen_category else "backlinks"
        out_file = f"output/queues/{prefix}_{slug}.txt"

    from .page_generators import PageQueueExporter
    saved_path = PageQueueExporter.export_to_file(
        items=items,
        output_path=out_file,
        source_description=source_desc,
    )
    print(f"[+] Translation queue exported successfully to: {saved_path}")
    print(f"[*] You can run translation with: uv run python -m wiki_translator.cli --batch {saved_path}")
    return True


def handle_batch_command(args: argparse.Namespace, cli: Any) -> bool:
    """Handles automated sequential batch translation."""
    if not args.batch_file:
        return False

    mod = _get_cli_module()
    print(f"[*] Batch Translation Mode: Reading queue from '{args.batch_file}'...")

    def run_single_article(title_to_translate: str) -> Dict[str, Any]:
        try:
            result = cli.run_interactive(
                article_title=title_to_translate,
                auto_approve=True,
                revid=args.revid,
            )
            if not isinstance(result, dict):
                return {
                    "success": False,
                    "status": "invalid_result",
                    "error": "run_interactive must return a result dictionary",
                }
            return result
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    report = mod.default_batch_runner.run_batch_from_file(
        queue_file_path=args.batch_file,
        translate_fn=run_single_article,
    )
    print(
        f"\n[+] Batch Run Completed: {report.succeeded}/{report.total_articles} "
        f"succeeded in {round(report.total_elapsed_seconds, 2)}s."
    )
    return True
