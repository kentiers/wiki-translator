"""
CLI Argument Parser definition for Wiki Translator Suite.

Centralizes all CLI flags, options, help descriptions, and defaults
for Wikipedia Grade A++ translation, category reconciliation,
template ecosystem management, and publishing workflows.
"""

import argparse
from typing import Optional, Sequence


def build_cli_parser() -> argparse.ArgumentParser:
    """Constructs and returns the comprehensive ArgumentParser for the CLI."""
    parser = argparse.ArgumentParser(
        description="Semi-Automatic Grade A++ Wikipedia Translator (EN -> ID)"
    )
    parser.add_argument(
        "title",
        nargs="?",
        default=None,
        help="English Wikipedia article title (e.g., 'Quantum computing')",
    )
    parser.add_argument(
        "--model",
        default="gemini-3.8-flash",
        help="Gemini model to use (gemini-3.8-flash, gemini-3.7-flash-tiered)",
    )
    parser.add_argument(
        "--thinking",
        "--thinking-level",
        dest="thinking",
        choices=["auto", "low", "medium", "high"],
        default="auto",
        help="Thinking budget tier for Gemini 3.8 Flash (choices: auto, low, medium, high; default: auto)",
    )
    parser.add_argument(
        "--topic",
        choices=[
            "film",
            "cinema",
            "tv_series",
            "television",
            "entertainment",
            "media",
            "computing_science",
            "physics_mathematics",
            "medical_biology",
            "history_social",
            "history",
            "biography",
            "monarchy",
            "politics",
            "aerospace_aviation",
            "aerospace",
            "aviation",
            "mechanical_engineering",
            "engineering",
            "mathematics_statistics",
            "math",
            "chemistry_materials",
            "chemistry",
            "earth_environment",
            "geology",
            "economics_finance",
            "economics",
            "military_defense",
            "military",
            "music_arts",
            "music",
            "law_jurisprudence",
            "law",
        ],
        default=None,
        help="Specific topic glossary to apply",
    )
    parser.add_argument(
        "--oldid",
        "--revid",
        dest="revid",
        type=int,
        default=None,
        help="Pin translation to a specific Wikipedia revision ID (oldid)",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Auto-approve all sections without interactive prompt",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory to save generated wikitext and markdown",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable persistent semantic cache",
    )
    parser.add_argument(
        "--no-compression",
        action="store_true",
        help="Disable markup / citation compression",
    )
    parser.add_argument(
        "--no-delta-skip",
        action="store_true",
        help="Disable smart delta skip for boilerplate sections",
    )
    parser.add_argument(
        "--auto-glossary",
        "--resolve-terms",
        dest="auto_glossary",
        action="store_true",
        default=True,
        help="Enable dynamic term and exonym resolution (default: True)",
    )
    parser.add_argument(
        "--no-glossary",
        dest="auto_glossary",
        action="store_false",
        help="Disable dynamic term and exonym resolution",
    )
    parser.add_argument(
        "--map-links",
        dest="map_links",
        action="store_true",
        default=True,
        help="Enable automated Wikipedia live link and category validation and mapping (default: True)",
    )
    parser.add_argument(
        "--no-map-links",
        dest="map_links",
        action="store_false",
        help="Disable automated Wikipedia live link and category validation and mapping",
    )
    parser.add_argument(
        "--polish",
        "--humanize",
        dest="polish",
        action="store_true",
        default=False,
        help="Enable 2-pass Polish / Humanize mode for refined Indonesian journalistic cadence",
    )
    parser.add_argument(
        "--no-typography",
        "--no-sanitize",
        dest="typography",
        action="store_false",
        default=True,
        help="Disable automatic Wikipedia ID typography and reference date sanitization",
    )
    parser.add_argument(
        "--no-slop-linter",
        dest="slop_linter",
        action="store_false",
        default=True,
        help="Disable Anti-AI-Slop and calque linter",
    )
    parser.add_argument(
        "--no-syntax-balancer",
        dest="syntax_balancer",
        action="store_false",
        default=True,
        help="Disable wikitext syntax balancer auto-repair",
    )
    parser.add_argument(
        "--no-template-mapper",
        dest="template_mapper",
        action="store_false",
        default=True,
        help="Disable cross-wiki template mapper and missing template safeguard",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Automatically open HTML preview in default browser when finished",
    )
    parser.add_argument(
        "--publish-sandbox",
        default=None,
        help="Indonesian Wikipedia username for sandbox publishing",
    )
    parser.add_argument(
        "--publish-main",
        default=None,
        help="Publish directly to the specified mainspace title",
    )
    parser.add_argument(
        "--promote-draft",
        default=None,
        help="Move the current or existing sandbox draft to the specified mainspace title",
    )
    parser.add_argument(
        "--force-overwrite",
        action="store_true",
        default=False,
        help="Allow overwriting an existing mainspace article if explicitly requested",
    )
    parser.add_argument(
        "--sandbox-slug",
        default=None,
        help="Custom slug between Bak_pasir and article title (default: <project-slug>/YYYY-MM)",
    )
    parser.add_argument(
        "--sandbox-project",
        "--project-slug",
        dest="sandbox_project",
        default="Draf",
        help="Project/folder slug before YYYY-MM in sandbox hierarchy (default: Draf)",
    )
    parser.add_argument(
        "-m",
        "--summary",
        dest="summary",
        default=None,
        help="Custom Wikipedia edit summary (ringkasan suntingan). If omitted, natural human summaries are used.",
    )
    parser.add_argument(
        "--create-stubs",
        dest="create_stubs",
        action="store_true",
        default=False,
        help="Optional stub generation for high-value red links ({{ill}}), saving compliant stubs to output/stubs/",
    )
    parser.add_argument(
        "--delink-ill",
        dest="delink_ill",
        default=None,
        metavar="TARGET_TITLE",
        help="Finds all articles linking to TARGET_TITLE via {{ill}} and converts them to direct [[TARGET_TITLE]] links",
    )
    parser.add_argument(
        "--audit-navboxes",
        dest="audit_navboxes",
        action="store_true",
        default=False,
        help="Checks bottom navboxes in the article, generating drafts in output/templates/ for any missing on id.wiki",
    )
    parser.add_argument(
        "--curate-categories",
        dest="curate_categories",
        action="store_true",
        default=False,
        help="Audits categories against id.wiki's WP:PEDKAT (finding related articles)",
    )
    parser.add_argument(
        "--reconcile-category",
        default=None,
        help="Plan membership updates from an enwiki category",
    )
    parser.add_argument(
        "--plan-category-creation",
        default=None,
        help="Inventory enwiki category content and idwiki dependencies without writing",
    )
    parser.add_argument(
        "--materialize-category",
        default=None,
        help="Generate a validated local idwiki category draft without publishing",
    )
    parser.add_argument(
        "--parent-override",
        action="append",
        default=[],
        metavar="EN=ID",
        help="Explicit parent category mapping; repeatable",
    )
    parser.add_argument(
        "--plan-category-tree",
        default=None,
        help="Plan parent category tree without writing",
    )
    parser.add_argument(
        "--audit-category-diff",
        default=None,
        help="Audit direct category membership differences",
    )
    parser.add_argument(
        "--sync-category-page",
        default=None,
        help="Create a reviewed local draft for an existing category page",
    )
    parser.add_argument(
        "--publish-category-page",
        default=None,
        help="Publish an approved category-page draft",
    )
    parser.add_argument(
        "--deploy-dependencies",
        default=None,
        help="Draft template/module dependencies locally",
    )
    parser.add_argument(
        "--check-publish-gate",
        metavar="TITLE",
        help="Verify an approved manifest, artifact hashes, and target revision without editing",
    )
    parser.add_argument(
        "--approval-manifest",
        default=None,
        help="Path to approval-manifest.json for --check-publish-gate",
    )
    parser.add_argument("--expected-revision", type=int, default=None)
    parser.add_argument("--allow-existing-target", action="store_true", default=False)
    parser.add_argument(
        "--id-category",
        default=None,
        help="Existing idwiki target category for reconciliation",
    )
    parser.add_argument(
        "--recursive-category",
        action="store_true",
        help="Reserved until each enwiki subcategory can map to its own idwiki category",
    )
    parser.add_argument(
        "--category-depth",
        type=int,
        default=2,
        help="Maximum nested category depth (default: 2)",
    )
    parser.add_argument(
        "--reconcile-limit",
        type=int,
        default=500,
        help="Maximum enwiki articles inspected (default: 500)",
    )
    parser.add_argument(
        "--apply-category-edits",
        action="store_true",
        help="Apply the reconciliation plan; default is dry-run",
    )
    parser.add_argument(
        "--generate-redirects",
        dest="enable_redirects",
        action="store_true",
        default=False,
        help="Generates Wikipedia redirect files (opt-in per WP:PENGALIHAN; default is disabled)",
    )
    parser.add_argument(
        "--batch",
        dest="batch_file",
        default=None,
        help="Path to a text file containing article titles (one per line) for sequential batch translation",
    )
    parser.add_argument(
        "--gen-category",
        dest="gen_category",
        default=None,
        help="Generates translation queue of missing id.wiki articles from an en.wiki category",
    )
    parser.add_argument(
        "--gen-backlinks",
        dest="gen_backlinks",
        default=None,
        help="Generates translation queue of missing id.wiki articles from backlinks/transclusions to an en.wiki page",
    )
    parser.add_argument(
        "--output-queue",
        dest="output_queue",
        default=None,
        help="Specifies output text file for generated translation queue (e.g. output/queues/queue.txt)",
    )
    parser.add_argument(
        "--dry-run-queue",
        dest="dry_run_queue",
        action="store_true",
        default=False,
        help="Prints generated page queue to console without writing to file",
    )
    parser.add_argument(
        "--queue-limit",
        dest="queue_limit",
        type=int,
        default=50,
        help="Maximum number of missing articles to generate in queue (default: 50)",
    )
    parser.add_argument(
        "--queue-recursive",
        dest="queue_recursive",
        action="store_true",
        default=False,
        help="Enables recursive subcategory traversal for --gen-category (default: False)",
    )
    parser.add_argument(
        "--check-media",
        dest="check_media",
        action="store_true",
        default=False,
        help="Audit article media/posters with default_media_manager",
    )
    parser.add_argument(
        "--upload-media",
        dest="upload_media",
        action="store_true",
        default=False,
        help="Enable automated non-free poster/media uploading to id.wikipedia.org via default_media_manager using bot credentials",
    )
    parser.add_argument(
        "--enrich-archives",
        dest="enrich_archives",
        action="store_true",
        default=False,
        help="Enable automated Wayback Machine archive-url injection via default_reference_checker",
    )
    parser.add_argument(
        "--no-metric-first",
        dest="metric_first",
        action="store_false",
        default=True,
        help="Disable metric-first normalization (enabled by default per WP:GAYA)",
    )
    parser.add_argument(
        "--proyek-wiki",
        dest="include_proyek_wiki",
        action="store_true",
        default=False,
        help="Include ProyekWiki community banners in talk page (default: False)",
    )
    parser.add_argument(
        "--sync-template",
        "--update-template",
        dest="sync_template",
        default=None,
        help="Sync and update a template and its documentation from en.wiki",
    )
    parser.add_argument(
        "--scan-template-deps",
        dest="scan_template_deps",
        default=None,
        help="Recursively scans and prints full dependency tree for a Wikipedia template/module",
    )
    parser.add_argument(
        "--sync-ecosystem",
        dest="sync_ecosystem",
        default=None,
        help="Orchestrates recursive sync with sandbox/testcases for a Wikipedia template/module",
    )
    parser.add_argument(
        "--publish-template",
        dest="publish_template",
        action="store_true",
        default=False,
        help="Publish synced template directly to id.wikipedia.org",
    )
    parser.add_argument(
        "--review-article",
        dest="review_article",
        default=None,
        help="Audit and review an existing Indonesian Wikipedia article against en.wiki and WP:KAP",
    )
    parser.add_argument(
        "--glossary-memory",
        default=".cache/glossary_memory.db",
        help="SQLite glossary memory path (default: .cache/glossary_memory.db)",
    )
    parser.add_argument(
        "--list-glossary-candidates",
        action="store_true",
        help="List pending glossary candidates without changing terminology",
    )
    parser.add_argument(
        "--approve-glossary",
        metavar="SOURCE=TARGET",
        help="Approve one glossary candidate, optionally scoped with --glossary-topic",
    )
    parser.add_argument(
        "--reject-glossary",
        metavar="SOURCE=TARGET",
        help="Reject one glossary candidate, optionally scoped with --glossary-topic",
    )
    parser.add_argument(
        "--glossary-topic",
        default=None,
        help="Limit glossary candidate listing or approval to a topic",
    )
    parser.add_argument(
        "--by-paragraph",
        dest="by_paragraph",
        action="store_true",
        default=True,
        help="Enable context-aware paragraph-by-paragraph translation for multi-paragraph sections (default: True)",
    )
    parser.add_argument(
        "--no-paragraph-split",
        "--no-by-paragraph",
        dest="by_paragraph",
        action="store_false",
        help="Disable paragraph-by-paragraph translation and translate entire section as single prompt",
    )
    parser.add_argument(
        "--learn-glossary-revision",
        nargs=2,
        metavar=("DRAFT", "REVISED"),
        help="Import terminology candidates from two UTF-8 wikitext files",
    )
    parser.add_argument(
        "--cache-status",
        action="store_true",
        help="Display SQLite cache database sizes and filesystem locations",
    )
    parser.add_argument(
        "--clear-cache",
        nargs="?",
        const="all",
        default=None,
        metavar="TARGET",
        help="Safely clear SQLite caches (choices: all, translation, glossary, wayback, templates, links; default: all)",
    )
    return parser
