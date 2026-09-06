"""
Interactive CLI for Semi-Automatic Grade A++ Wikipedia Translation.

Provides:
- Page title lookup & fetching
- Section breakdown & statistics
- Live streaming translation per section
- Review mode (Approve, Retry, Edit prompt/notes, Skip)
- Saving final wikitext and markdown outputs to output/ directory
"""

import argparse
import json
import os
from pathlib import Path
import re
import sys
from collections import namedtuple
from typing import Any, Dict, List, Optional, Tuple, NamedTuple

from .auth import AuthManager
from .gemini import GeminiTranslatorClient
from .glossary_resolver import GlossaryResolver, default_glossary_resolver
from .glossary_memory import GlossaryMemory
from .prompts import (
    SYSTEM_PROMPT_GRADE_A_PLUS_PLUS,
    TOPIC_GLOSSARIES,
    build_translation_prompt,
)
from .token_saver import (
    SectionFilter,
    TokenCompressor,
    TokenTracker,
    TranslationCache,
    default_cache,
    default_tracker,
)
from .attribution_generator import (
    TalkPageAttributionGenerator,
    default_attribution_generator,
)
from .slop_linter import AntiAISlopLinter, default_slop_linter
from .factual_audit import default_factual_auditor
from .article_quality import check_saved_integrity, review_claims
from .syntax_balancer import WikitextSyntaxBalancer, default_syntax_balancer
from .infobox_mapper import InfoboxMapper, default_infobox_mapper
from .template_mapper import WikiTemplateMapper, default_template_mapper
from .typography_sanitizer import TypographySanitizer, default_typography_sanitizer
from .wiki_client import WikipediaClient, WikiSection
from .html_preview import (
    HTMLPreviewGenerator,
    default_preview_generator,
)
from .sandbox_publisher import (
    SandboxPublisher,
    default_sandbox_publisher,
)
from .mainspace_publisher import (
    MainspacePublisher,
    default_mainspace_publisher,
)
from .wikidata_linker import (
    WikidataLinker,
    default_wikidata_linker,
)
from .editorial_qa import (
    EditorialQAPipeline,
    default_qa_pipeline,
    QAAuditReport,
)
from .wiki_link_mapper import WikiLinkMapper, default_link_mapper
from .redirect_generator import (
    RedirectGenerator,
    default_redirect_generator,
)
from .navbox_generator import (
    NavboxGenerator,
    default_navbox_generator,
)
from .template_doc_auditor import (
    TemplateDocAuditor,
    default_template_doc_auditor,
)
from .category_curator import (
    CategoryCurator,
    default_category_curator,
)
from .category_reconciler import default_category_reconciler
from .category_creator import default_category_creation_planner
from .category_materializer import CategoryMaterializer
from .category_tree_audit import default_category_diff_auditor, default_category_tree_planner
from .dependency_deployer import default_dependency_deployer
from .publish_gate import PublishGate
from .approval_journal import ApprovalManifest
from .category_page_sync import CategoryPageSyncResult, CategoryPageSynchronizer
from .article_reviewer import (
    ArticleReviewer,
    default_article_reviewer,
    APReviewReport,
)
from .stub_generator import (
    StubGenerator,
    default_stub_generator,
)
from .unit_converter import default_unit_converter
from .reference_checker import default_reference_checker
from .media_manager import default_media_manager
from .shared_memory import default_shared_memory
from .batch_runner import default_batch_runner
from .template_syncer import (
    TemplateSyncer,
    default_template_syncer,
)
from .paragraph_translator import (
    ParagraphTranslator,
    default_paragraph_translator,
)
from .template_ecosystem import (
    RecursiveDependencyScanner,
    CategoryTreeLinker,
    SandboxTestcaseEngine,
    TemplateEcosystemManager,
    default_ecosystem_manager,
)
from .page_generators import (
    CategoryPageGenerator,
    WhatLinksHerePageGenerator,
    PageQueueExporter,
    PageQueueItem,
)
from .cli_args import build_cli_parser
from .cli_ui import (
    print_console_safe,
    print_banner,
    render_sections_table,
    render_section_header,
    render_review_menu,
    render_diff_view,
    UI,
    ui,
    slugify,
    load_env_file,
)
from .cli_subcommands import (
    handle_storage_commands,
    handle_glossary_actions,
    handle_ecosystem_and_category_commands,
    handle_page_gen_commands,
    handle_batch_command,
)

class WikiTranslatorCLI:
    def _quality_gate(self, sections: List[WikiSection]) -> Tuple[bool, List[str]]:
        """Reject incomplete or structurally unsafe output before final writes."""
        failures: List[str] = []
        for section in sections:
            source = section.full_source or ""
            draft = section.translated_content or ""
            if not draft.strip():
                failures.append(f"{section.title}: keluaran kosong")
                continue
            if source and len(draft.split()) < max(3, int(len(source.split()) * 0.15)):
                failures.append(f"{section.title}: keluaran terpotong (terlalu pendek)")
            topic_val = getattr(self, "topic", None)
            factual = default_factual_auditor.audit(source, draft, topic=topic_val)
            for warning in factual.warnings:
                if "pembalikan makna" in warning or "Entitas penting" in warning or "Penyimpangan atribusi" in warning:
                    failures.append(f"{section.title}: {warning}")
            if factual.missing_numbers:
                failures.append(f"{section.title}: angka/tanggal sumber hilang: {', '.join(factual.missing_numbers[:12])}")
            if factual.source_references and factual.draft_references < factual.source_references:
                failures.append(f"{section.title}: rujukan sumber berkurang")
        # Named references may be defined in a different section of the article.
        combined = "\n\n".join(section.translated_content or "" for section in sections)
        for issue in self.syntax_balancer.check_balance(combined):
            if issue.get("severity") == "error":
                failures.append(f"Artikel: {issue.get('description', 'markup tidak seimbang')}")
        return not failures, failures
    def __init__(
        self,
        model: str = "gemini-3.8-flash",
        thinking: str = "auto",
        output_dir: str = "output",
        topic: Optional[str] = None,
        enable_cache: bool = True,
        enable_compression: bool = True,
        enable_delta_skip: bool = True,
        enable_auto_glossary: bool = True,
        glossary_resolver: Optional[GlossaryResolver] = None,
        enable_map_links: bool = True,
        link_mapper: Optional[WikiLinkMapper] = None,
        enable_polish: bool = False,
        enable_typography_sanitizer: bool = True,
        typography_sanitizer: Optional[TypographySanitizer] = None,
        enable_slop_linter: bool = True,
        slop_linter: Optional[AntiAISlopLinter] = None,
        enable_syntax_balancer: bool = True,
        syntax_balancer: Optional[WikitextSyntaxBalancer] = None,
        enable_template_mapper: bool = True,
        template_mapper: Optional[WikiTemplateMapper] = None,
        attribution_generator: Optional[TalkPageAttributionGenerator] = None,
        preview_generator: Optional[HTMLPreviewGenerator] = None,
        sandbox_publisher: Optional[SandboxPublisher] = None,
        mainspace_publisher: Optional[MainspacePublisher] = None,
        wikidata_linker: Optional[WikidataLinker] = None,
        auto_preview: bool = False,
        publish_sandbox: Optional[str] = None,
        publish_main: Optional[str] = None,
        promote_draft: Optional[str] = None,
        force_overwrite: bool = False,
        sandbox_slug: Optional[str] = None,
        project_slug: Optional[str] = "Draf",
        enable_redirects: bool = False,
        redirect_generator: Optional[RedirectGenerator] = None,
        create_stubs: bool = False,
        stub_generator: Optional[StubGenerator] = None,
        audit_navboxes: bool = False,
        navbox_generator: Optional[NavboxGenerator] = None,
        template_doc_auditor: Optional[TemplateDocAuditor] = None,
        curate_categories: bool = False,
        category_curator: Optional[CategoryCurator] = None,
        summary: Optional[str] = None,
        metric_first: bool = True,
        enrich_archives: bool = False,
        check_media: bool = False,
        upload_media: bool = False,
        include_proyek_wiki: bool = False,
        by_paragraph: bool = True,
        paragraph_translator: Optional[ParagraphTranslator] = None,
        qa_pipeline: Optional[EditorialQAPipeline] = None,
    ):
        self.auth_manager = AuthManager()
        self.cache = default_cache if enable_cache else None
        self.tracker = default_tracker
        self.gemini_client = GeminiTranslatorClient(
            auth_manager=self.auth_manager,
            preferred_model=model,
            cache=self.cache,
            tracker=self.tracker,
            thinking_level=thinking,
        )
        self.wiki_client = WikipediaClient(lang="en")
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.topic = topic
        self.model = model
        self.thinking = thinking
        self.enable_cache = enable_cache
        self.enable_compression = enable_compression
        self.enable_delta_skip = enable_delta_skip
        self.custom_glossary: Dict[str, str] = {}
        self.enable_auto_glossary = enable_auto_glossary
        self.glossary_resolver = glossary_resolver or default_glossary_resolver
        self.enable_map_links = enable_map_links
        self.link_mapper = link_mapper or default_link_mapper
        self.enable_polish = enable_polish
        self.enable_typography_sanitizer = enable_typography_sanitizer
        self.typography_sanitizer = typography_sanitizer or default_typography_sanitizer
        self.enable_slop_linter = enable_slop_linter
        self.slop_linter = slop_linter or default_slop_linter
        self.enable_syntax_balancer = enable_syntax_balancer
        self.syntax_balancer = syntax_balancer or default_syntax_balancer
        self.enable_template_mapper = enable_template_mapper
        self.template_mapper = template_mapper or default_template_mapper
        self.attribution_generator = attribution_generator or default_attribution_generator
        self.preview_generator = preview_generator or default_preview_generator
        self.sandbox_publisher = sandbox_publisher or default_sandbox_publisher
        self.mainspace_publisher = mainspace_publisher or default_mainspace_publisher
        self.wikidata_linker = wikidata_linker or default_wikidata_linker
        self.publish_main = publish_main
        self.promote_draft = promote_draft
        self.force_overwrite = force_overwrite
        self.auto_preview = auto_preview
        self.publish_sandbox = publish_sandbox
        self.sandbox_slug = sandbox_slug
        self.project_slug = project_slug
        self.enable_redirects = enable_redirects
        self.redirect_generator = redirect_generator or default_redirect_generator
        self.create_stubs = create_stubs
        self.stub_generator = stub_generator or default_stub_generator
        self.audit_navboxes = audit_navboxes
        self.navbox_generator = navbox_generator or default_navbox_generator
        self.template_doc_auditor = template_doc_auditor or default_template_doc_auditor
        self.curate_categories = curate_categories
        self.category_curator = category_curator or default_category_curator
        self.summary = summary
        self.metric_first = metric_first
        self.enrich_archives = enrich_archives
        self.check_media = check_media
        self.upload_media = upload_media
        self.include_proyek_wiki = include_proyek_wiki
        self.by_paragraph = by_paragraph
        self.paragraph_translator = paragraph_translator or default_paragraph_translator
        self.qa_pipeline = qa_pipeline or default_qa_pipeline
        # Results from the last save are exposed to callers (especially batch mode)
        # without changing the backwards-compatible SavedOutputs return type.
        self.last_pipeline_errors: List[str] = []
        self.last_pipeline_warnings: List[str] = []

    @staticmethod
    def _run_result(
        *,
        success: bool,
        status: str,
        error: Optional[str] = None,
        output_files: Optional[Dict[str, str]] = None,
        qa_report: Optional[QAAuditReport] = None,
        publication_ready: bool = False,
        pipeline_errors: Optional[List[str]] = None,
        pipeline_warnings: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Build the stable result contract used by interactive and batch callers."""
        result: Dict[str, Any] = {
            "success": bool(success),
            "status": status,
            "output_files": output_files or {},
            "qa_approved": bool(qa_report and qa_report.is_approved()),
            "qa_score": getattr(qa_report, "overall_score", None),
            "publication_ready": bool(publication_ready),
            "pipeline_errors": list(pipeline_errors or []),
            "pipeline_warnings": list(pipeline_warnings or []),
        }
        if error:
            result["error"] = str(error)
        return result

    @staticmethod
    def _saved_output_dict(saved_paths: Any) -> Dict[str, str]:
        """Convert SavedOutputs paths to JSON-friendly values for callers."""
        output_files: Dict[str, str] = {}
        for name in ("wikitext", "markdown", "talk", "preview"):
            value = getattr(saved_paths, name, None)
            if value is not None:
                output_files[name] = str(value)
        return output_files
    def run_interactive(
        self,
        article_title: Optional[str] = None,
        auto_approve: bool = False,
        revid: Optional[int] = None,
    ) -> Dict[str, Any]:
        self._require_claim_review = True
        print_banner()

        # Check credentials
        active_cred = self.auth_manager.get_active_credential()
        if active_cred:
            print(f"[*] Antigravity Auth: Connected ({active_cred.email} | Project: {active_cred.project_id})")
        else:
            api_key = os.environ.get("GEMINI_API_KEY")
            if api_key:
                print(f"[*] Antigravity Auth: Fallback to GEMINI_API_KEY (AI Studio)")
            else:
                print("[!] Warning: No Antigravity auth found and GEMINI_API_KEY not set.")

        if not article_title:
            try:
                article_title = input("\n[?] Enter English Wikipedia article title: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nOperation cancelled.")
                return self._run_result(success=False, status="cancelled", error="Operation cancelled")

        if not article_title:
            print("[!] Article title cannot be empty.")
            return self._run_result(success=False, status="invalid_title", error="Article title cannot be empty")

        if revid is not None:
            print(f"\n[*] Fetching wikitext from en.wikipedia.org for '{article_title}' (revid: {revid})...")
        else:
            print(f"\n[*] Fetching wikitext from en.wikipedia.org for '{article_title}'...")
        try:
            sections = self.wiki_client.fetch_sections(article_title, revid=revid)
        except Exception as e:
            print(f"[!] Error fetching article: {e}")
            return self._run_result(success=False, status="fetch_failed", error=str(e))

        total_chars = sum(s.char_count for s in sections)
        print(f"[+] Successfully fetched {total_chars:,} characters across {len(sections)} sections.")
        render_sections_table(sections)

        # Select topic if not set
        if not self.topic:
            print("\n[?] Select Topic Glossary (Optional):")
            print("  [0] None / General Knowledge")
            print("  [1] Film & Cinema (Film & Sinematografi)")
            print("  [2] TV Series & Television (Serial TV & Televisi)")
            print("  [3] Entertainment & Streaming Media (Hiburan & Media)")
            print("  [4] Computing & Computer Science")
            print("  [5] Physics & Mathematics")
            print("  [6] Medicine & Biology")
            print("  [7] History & Social Sciences")
            print("  [8] Aerospace & Jet Aviation (Dirgantara & Mesin Jet)")
            print("  [9] Mechanical Engineering & Thermodynamics (Teknik Mesin)")
            print("  [10] Pure Mathematics & Statistics (Matematika & Statistika)")
            print("  [11] Chemistry & Materials Science (Kimia & Material)")
            print("  [12] Earth Sciences & Environment (Ilmu Kebumian & Lingkungan)")
            print("  [13] Economics & Finance (Ekonomi & Keuangan)")
            print("  [14] Military & Defense Technology (Militer & Pertahanan)")
            print("  [15] Music & Fine Arts (Musik & Seni Rupa)")
            print("  [16] Law & Jurisprudence (Hukum & Yurisprudensi)")
            print("  [17] Religion & Theology (Agama & Teologi)")
            try:
                choice = input("Select choice [0-17] (default: 0): ").strip()
                if choice == "1":
                    self.topic = "film"
                elif choice == "2":
                    self.topic = "tv_series"
                elif choice == "3":
                    self.topic = "entertainment"
                elif choice == "4":
                    self.topic = "computing_science"
                elif choice == "5":
                    self.topic = "physics_mathematics"
                elif choice == "6":
                    self.topic = "medical_biology"
                elif choice == "7":
                    self.topic = "history_social"
                elif choice == "8":
                    self.topic = "aerospace_aviation"
                elif choice == "9":
                    self.topic = "mechanical_engineering"
                elif choice == "10":
                    self.topic = "mathematics_statistics"
                elif choice == "11":
                    self.topic = "chemistry_materials"
                elif choice == "12":
                    self.topic = "earth_environment"
                elif choice == "13":
                    self.topic = "economics_finance"
                elif choice == "14":
                    self.topic = "military_defense"
                elif choice == "15":
                    self.topic = "music_arts"
                elif choice == "16":
                    self.topic = "law_jurisprudence"
                elif choice == "17":
                    self.topic = "religion"
            except (KeyboardInterrupt, EOFError):
                pass

        if self.topic:
            print(f"[*] Active topic glossary: {self.topic}")
        # Inject terms from default_shared_memory into custom_glossary
        try:
            memory_terms = default_shared_memory.get_memory_glossary(self.topic)
            if memory_terms:
                print(f"[*] [SharedMemory] Injected {len(memory_terms)} remembered term(s) from workspace memory.")
                # Custom glossary takes precedence if explicitly supplied, else memory terms
                for en_k, id_v in memory_terms.items():
                    if en_k not in self.custom_glossary:
                        self.custom_glossary[en_k] = id_v
        except Exception as me:
            print(f"[!] [SharedMemory] Warning: Failed to load workspace memory: {me}")


        # Semi-automatic section by section translation
        translated_sections: List[WikiSection] = []
        slug = slugify(article_title)
        for s in sections:
            # Skip empty sections
            if not s.content.strip() and not s.header_raw.strip():
                continue

            render_section_header(s.index, len(sections) - 1, s.title, s.word_count, s.char_count)

            # 1. Smart Delta Skip check (References, External links, etc.)
            if self.enable_delta_skip:
                can_skip, skipped_body = SectionFilter.can_skip_llm(s.title, s.content)
                if can_skip:
                    # Map standard header title to Indonesian
                    clean_t = re.sub(r"[^a-zA-Z0-9\s]", "", s.title).strip().lower()
                    id_header_title = SectionFilter.STANDARD_HEADINGS.get(clean_t, s.title)
                    eqs = "=" * s.level
                    full_skipped = f"{eqs} {id_header_title} {eqs}\n{skipped_body}".strip()
                    s.translated_content = full_skipped
                    s.is_skipped = True
                    self.tracker.record_delta_skip(s.full_source, full_skipped)
                    print(f"[*] [TokenSaver] Smart Delta Skip applied: Section '{s.title}' -> '{id_header_title}' (0 LLM tokens spent!)")
                    translated_sections.append(s)
                    continue

            # Resolve the glossary before cache lookup so the key matches the prompt.
            resolved_glossary = None
            if self.enable_auto_glossary and self.glossary_resolver:
                try:
                    resolved_glossary = self.glossary_resolver.resolve_section_terms(
                        wikitext=s.full_source,
                        topic=self.topic,
                        custom_glossary=self.custom_glossary,
                    )
                except Exception as e:
                    print(f"[!] [GlossaryResolver] Warning: term resolution failed ({e})")
            cache_glossary = dict(resolved_glossary or {})
            cache_glossary.update(self.custom_glossary or {})

            # 2. Semantic Cache lookup
            if self.enable_cache and self.cache:
                cached_res = self.cache.get(
                    source_text=s.full_source,
                    section_title=s.title,
                    topic=self.topic,
                    model=self.model,
                    thinking_level=self.thinking,
                    glossary=cache_glossary,
                    polish=self.enable_polish,
                )
                if cached_res:
                    s.translated_content = cached_res
                    s.is_cached = True
                    self.tracker.record_cache_hit(s.full_source, cached_res)
                    print(f"[+] [TokenSaver] Headroom Cache Hit: Section '{s.title}' loaded from persistent cache (0 LLM tokens spent!)")
                    if auto_approve:
                        translated_sections.append(s)
                        continue
                    else:
                        print("-" * 72)
                        print(cached_res[:300] + ("..." if len(cached_res) > 300 else ""))
                        print("-" * 72)
                        print("\n[?] Cached Translation Review:")
                        print("  [A] Use Cached (Default)")
                        print("  [R] Force Re-translate with LLM")
                        action = input("Select action [A/r] (default: A): ").strip().upper()
                        if action != "R":
                            translated_sections.append(s)
                            continue

            # 3. LLM Translation with Token Compression
            context_notes = None
            translated_text = ""

            while True:
                source_text_to_translate = s.full_source
                placeholders = {}

                if self.enable_compression:
                    compressed_obj = TokenCompressor.compress(source_text_to_translate)
                    source_text_to_translate = compressed_obj.compressed_text
                    placeholders = compressed_obj.placeholders
                    if compressed_obj.chars_saved > 0:
                        print(
                            f"[*] [TokenSaver] Compressed markup: {compressed_obj.original_char_count} -> {compressed_obj.compressed_char_count} chars "
                            f"({compressed_obj.token_savings_percent:.1f}% reduction)"
                        )

                if resolved_glossary:
                    print(f"[*] [GlossaryResolver] Injected {len(resolved_glossary)} dynamic terms/exonyms for section '{s.title}'")

                prompt = build_translation_prompt(
                    section_title=s.title,
                    wikitext_content=source_text_to_translate,
                    context_notes=context_notes,
                    topic=self.topic,
                    custom_glossary=self.custom_glossary,
                    resolved_glossary=resolved_glossary,
                )

                # If thinking is auto, log SmartModel resolution
                model_to_use = None
                if getattr(self.gemini_client, "thinking_level", None) == "auto":
                    analyzer = getattr(self.gemini_client, "complexity_analyzer", None)
                    if analyzer:
                        resolved_model, resolved_tier = analyzer.resolve_model(
                            requested_model=self.gemini_client.preferred_model,
                            requested_thinking="auto",
                            source_text=source_text_to_translate,
                            topic=self.topic,
                            section_title=s.title,
                        )
                        model_to_use = resolved_model
                        sec_name = s.title or "Lead"
                        print(f"[*] [SmartModel] Section '{sec_name}': Complexity '{resolved_tier.upper()}' -> Model '{model_to_use}'")

                print("\n[Translating...] Live stream:")
                print("-" * 72)
                def on_chunk(chunk: str) -> None:
                    try:
                        sys.stdout.write(chunk)
                    except UnicodeEncodeError:
                        sys.stdout.buffer.write(chunk.encode("utf-8", errors="replace"))
                    sys.stdout.flush()

                try:
                    # Check if by-paragraph mode should be used:
                    # Enabled if self.by_paragraph is True, and section has >= 2 prose paragraphs
                    chunks_preview = (
                        self.paragraph_translator.split_into_paragraph_chunks(source_text_to_translate)
                        if self.by_paragraph
                        else []
                    )
                    use_paragraph_mode = (
                        self.by_paragraph
                        and len(chunks_preview) >= 2
                        and any(c["type"] == "prose" for c in chunks_preview)
                    )

                    if use_paragraph_mode:
                        print(f"[*] [ParagraphEngine] Translating section '{s.title}' across {len(chunks_preview)} context-aware paragraph chunks...")

                        def chunk_translator_fn(chunk_prompt: str, sys_inst: Optional[str] = None) -> str:
                            return self.gemini_client.translate_section(
                                user_prompt=chunk_prompt,
                                system_instruction=sys_inst,
                                model=model_to_use,
                                source_text=chunk_prompt,
                                topic=self.topic,
                                section_title=s.title,
                            )

                        raw_llm_output = self.paragraph_translator.translate_section_by_paragraphs(
                            section_title=s.title,
                            wikitext=source_text_to_translate,
                            translator_func=chunk_translator_fn,
                            topic=self.topic,
                            context_notes=context_notes,
                            custom_glossary=self.custom_glossary,
                            resolved_glossary=resolved_glossary,
                            stream_callback=on_chunk,
                        )
                    else:
                        raw_llm_output = self.gemini_client.translate_section(
                            user_prompt=prompt,
                            stream_callback=on_chunk,
                            model=model_to_use,
                            source_text=source_text_to_translate,
                            topic=self.topic,
                            section_title=s.title,
                        )
                    print("\n" + "-" * 72)
                except Exception as e:
                    print(f"\n[!] Translation error on section '{s.title}': {e}")
                    if auto_approve:
                        return self._run_result(
                            success=False,
                            status="translation_failed",
                            error=f"Section '{s.title}': {e}",
                        )
                    retry = input("\n[?] Retry translation? [Y/n/s (skip)]: ").strip().lower()
                    if retry == "s":
                        translated_text = s.full_source  # keep original
                        break
                    elif retry == "n":
                        return self._run_result(
                            success=False,
                            status="translation_cancelled",
                            error=f"Section '{s.title}' translation cancelled",
                        )
                    else:
                        continue

                if not isinstance(raw_llm_output, str) or not raw_llm_output.strip():
                    message = f"LLM returned an empty translation for section '{s.title}'"
                    print(f"[!] {message}")
                    if auto_approve:
                        return self._run_result(success=False, status="empty_translation", error=message)
                    retry = input("\n[?] Retry translation? [Y/n/s (skip)]: ").strip().lower()
                    if retry == "s":
                        translated_text = s.full_source
                        break
                    if retry == "n":
                        return self._run_result(success=False, status="translation_cancelled", error=message)
                    continue

                # Rehydrate placeholders if compressed
                if self.enable_compression and placeholders:
                    translated_text = TokenCompressor.decompress(raw_llm_output, placeholders)
                else:
                    translated_text = raw_llm_output

                # Optional 2nd Pass Polish / Humanize (Anti-AI Slop refinement)
                if self.enable_polish:
                    print("\n[*] [PolishMode] Running 2nd Pass Humanize / Redaktur Polish...")
                    polish_stream_output = []
                    def on_polish_chunk(chunk: str) -> None:
                        sys.stdout.write(chunk)
                        sys.stdout.flush()
                    try:
                        polished_text = self.gemini_client.polish_section(
                            source_en=s.full_source,
                            draft_id=translated_text,
                            topic=self.topic,
                            glossary=cache_glossary,
                            context_notes=context_notes,
                            stream_callback=on_polish_chunk,
                        )
                        print("\n" + "-" * 72)
                        if polished_text and len(polished_text.strip()) > 10:
                            translated_text = polished_text
                    except Exception as pe:
                        print(f"[!] [PolishMode] Warning: 2nd pass polish skipped due to error: {pe}")

                # Record metrics in tracker
                self.tracker.record_llm_call(
                    raw_source_text=s.full_source,
                    compressed_prompt_text=prompt,
                    raw_output_text=translated_text,
                    compressed_output_text=raw_llm_output,
                )

                s.translated_content = translated_text

                if auto_approve:
                    if self.enable_cache and self.cache:
                        self.cache.put(
                            source_text=s.full_source,
                            translated_text=translated_text,
                            section_title=s.title,
                            topic=self.topic,
                            model=self.model,
                            thinking_level=self.thinking,
                            glossary=cache_glossary,
                            context=context_notes,
                            polish=self.enable_polish,
                        )
                    print("[+] Auto-approved section.")
                    break
                # Slop Linter inspection before review
                lint_result = None
                if self.enable_slop_linter and self.slop_linter:
                    lint_result = self.slop_linter.lint(translated_text)
                    if not lint_result.is_clean:
                        print(f"\n⚠️  [Slop Linter] Naturalness Score: {lint_result.score}/100 | {len(lint_result.violations)} calque/machine issues detected:")
                        for v in lint_result.violations[:4]:
                            sugg_str = ", ".join(v.suggestions[:3])
                            print(f"    - L{v.line_number} [{v.matched_text}]: {v.explanation} (Saran: {sugg_str})")
                        if len(lint_result.violations) > 4:
                            print(f"    ... dan {len(lint_result.violations) - 4} temuan lainnya.")

                # Semi-automatic review prompt
                render_review_menu(s.title)
                try:
                    action = input("Select action [A/v/d/f/p/r/e/s/q] (default: A): ").strip().upper()
                except (KeyboardInterrupt, EOFError):
                    action = "Q"

                if action in ("", "A"):
                    if self.enable_cache and self.cache:
                        self.cache.put(
                            source_text=s.full_source,
                            translated_text=translated_text,
                            section_title=s.title,
                            topic=self.topic,
                            model=self.model,
                            thinking_level=self.thinking,
                            glossary=cache_glossary,
                            context=context_notes,
                            polish=self.enable_polish,
                        )
                    print("[+] Approved.")
                    break
                elif action == "V":
                    print("\n[*] Generating HTML preview for section draft...")
                    try:
                        self.preview_generator.save_and_open_preview(
                            title=f"{article_title} - {s.title}",
                            wikitext=translated_text,
                            output_dir=str(self.output_dir),
                            auto_open=True,
                        )
                        print("[+] Opened section preview in default browser.")
                    except Exception as ve:
                        print(f"[!] Error generating HTML preview: {ve}")
                    continue
                elif action == "D":
                    self._show_diff_comparison(s.full_source, translated_text)
                    continue
                elif action == "F":
                    print("\n[*] Running Auto-Fix on Slop and Syntax...")
                    fixed_text = translated_text
                    fix_count = 0
                    if self.enable_slop_linter and self.slop_linter:
                        fixed_text, fix_count = self.slop_linter.auto_fix(fixed_text)
                        print(f"[+] Applied {fix_count} slop/calque auto-corrections.")
                    if self.enable_syntax_balancer and self.syntax_balancer:
                        fixed_text = self.syntax_balancer.auto_repair(fixed_text)
                        print("[+] Syntax balanced and repaired.")
                    translated_text = fixed_text
                    s.translated_content = translated_text
                    print("-" * 72)
                    print(translated_text)
                    print("-" * 72)
                    continue
                elif action == "P":
                    print("\n[*] [PolishMode] Applying Humanize Polish on current draft...")
                    def on_polish_chunk(chunk: str) -> None:
                        sys.stdout.write(chunk)
                        sys.stdout.flush()
                    try:
                        polished_text = self.gemini_client.polish_section(
                            source_en=s.full_source,
                            draft_id=translated_text,
                            stream_callback=on_polish_chunk,
                        )
                        print("\n" + "-" * 72)
                        if polished_text and len(polished_text.strip()) > 10:
                            translated_text = polished_text
                            s.translated_content = translated_text
                    except Exception as pe:
                        print(f"[!] Polish error: {pe}")
                    continue
                elif action == "R":
                    print("[*] Retrying section...")
                    continue
                elif action == "E":
                    note = input("Enter custom note or glossary directive: ").strip()
                    context_notes = note
                    continue
                elif action == "S":
                    print("[*] Skipped. Keeping original wikitext for this section.")
                    s.translated_content = s.full_source
                    break
                elif action == "Q":
                    print("\n[*] Saving current progress before exit...")
                    saved = self._save_output(slug, article_title, translated_sections, oldid=revid)
                    output_files = self._saved_output_dict(saved)
                    return self._run_result(
                        success=False,
                        status="partial_saved",
                        error="Translation stopped by user",
                        output_files=output_files,
                        pipeline_errors=self.last_pipeline_errors,
                        pipeline_warnings=self.last_pipeline_warnings,
                    )
            translated_sections.append(s)

        # Final save
        print("\n" + "=" * 72)
        print("[*] All sections completed! Saving outputs...")
        quality_ok, quality_failures = self._quality_gate(sections)
        if not quality_ok:
            print("[!] Quality gate blocked final save:")
            for failure in quality_failures[:20]:
                print(f"    - {failure}")
            return self._run_result(
                success=False,
                status="quality_gate_failed",
                error="; ".join(quality_failures),
                pipeline_errors=quality_failures,
                pipeline_warnings=self.last_pipeline_warnings,
            )
        try:
            saved_paths = self._save_output(slug, article_title, sections, oldid=revid)
        except ValueError as exc:
            return self._run_result(success=False, status="quality_gate_failed", error=str(exc))
        wikitext_path, md_path, talk_path, preview_path = (
            saved_paths.wikitext,
            saved_paths.markdown,
            saved_paths.talk,
            saved_paths.preview,
        )
        print(f"[+] Wikitext saved to      : {wikitext_path}")
        print(f"[+] Markdown saved to      : {md_path}")
        print(f"[+] Talk page saved to     : {talk_path}")
        print(f"[+] HTML Preview saved to  : {preview_path}")
        print("=" * 72)
        # Display Token Saver Dashboard
        print("\n" + self.tracker.get_summary_table())
        print("=" * 72)

        # Handle HTML preview opening if requested
        if self.auto_preview:
            print("[*] Opening full HTML preview in default browser...")
            try:
                import webbrowser
                webbrowser.open(preview_path.resolve().as_uri())
            except Exception as e:
                print(f"[!] Warning: Could not open browser preview: {e}")

        # Run Multi-Layer Editorial QA Pipeline audit before publication.
        try:
            qa_report = self.qa_pipeline.audit(
                wikitext=wikitext_path.read_text(encoding="utf-8"),
                talk_wikitext=talk_path.read_text(encoding="utf-8") if talk_path.exists() else None,
                title=article_title,
                source_wikitext="\n\n".join(section.full_source for section in sections),
            )
        except Exception as e:
            message = f"Editorial QA failed: {e}"
            print(f"[!] {message}")
            self.last_pipeline_errors.append(message)
            return self._run_result(
                success=False,
                status="qa_failed",
                error=message,
                output_files=self._saved_output_dict(saved_paths),
                pipeline_errors=self.last_pipeline_errors,
                pipeline_warnings=self.last_pipeline_warnings,
            )
        print_console_safe("\n" + qa_report.render_terminal_scorecard())
        # Interactive Red-Link selection if in interactive mode
        if not auto_approve and self.stub_generator and not self.create_stubs:
            self._process_red_links_and_stubs(wikitext_path.read_text(encoding="utf-8"), is_interactive=True)

        if qa_report.is_approved() and not self.last_pipeline_errors:
            self._handle_sandbox_publishing(article_title, wikitext_path, talk_path, auto_approve=auto_approve)
        else:
            if self.last_pipeline_errors:
                print("[!] Publication blocked because one or more integrity stages failed:")
                for message in self.last_pipeline_errors:
                    print(f"    - {message}")
            else:
                print("[!] Editorial QA Scorecard did not pass minimum publication thresholds (Score < 80 or Critical Errors present).")
            print("[!] Sandbox publishing skipped until revisions are made.")
        qa_approved = qa_report.is_approved()
        publication_ready = qa_approved and not self.last_pipeline_errors
        return self._run_result(
            success=publication_ready,
            status="completed" if publication_ready else ("pipeline_failed" if self.last_pipeline_errors else "qa_rejected"),
            output_files=self._saved_output_dict(saved_paths),
            qa_report=qa_report,
            publication_ready=publication_ready,
            pipeline_errors=self.last_pipeline_errors,
            pipeline_warnings=self.last_pipeline_warnings,
        )
    def _show_diff_comparison(self, source_en: str, draft_id: str) -> None:
        """Displays a structured side-by-side or dual-pane comparison between source EN and draft ID."""
        render_diff_view(source_en, draft_id)

    _check_saved_integrity = staticmethod(check_saved_integrity)

    def _save_output(
        self, slug: str, title: str, sections: List[WikiSection], oldid: Optional[int] = None
    ) -> Any:
        """Saves accumulated translated sections to wikitext, markdown, talk page, and HTML preview files."""
        self.last_pipeline_errors = []
        self.last_pipeline_warnings = []

        def record_pipeline_issue(stage: str, exc: Exception, *, blocking: bool = True) -> None:
            message = f"{stage}: {exc}"
            if blocking:
                self.last_pipeline_errors.append(message)
            else:
                self.last_pipeline_warnings.append(message)

        wikitext_file = self.output_dir / f"{slug}.wikitext"
        md_file = self.output_dir / f"{slug}.md"
        talk_file = self.output_dir / f"{slug}.talk.wikitext"
        preview_file = self.output_dir / f"{slug}.preview.html"
        # Combine wikitext
        full_wikitext_parts = []
        for s in sections:
            content = s.translated_content or s.full_source
            if content:
                full_wikitext_parts.append(content)

        final_wikitext = "\n\n".join(full_wikitext_parts) + "\n"
        original_draft = final_wikitext

        # Apply cross-wiki template mapping & safeguard if enabled
        if self.enable_template_mapper and self.template_mapper:
            print("[*] Running cross-wiki template mapper and missing template safeguard...")
            try:
                final_wikitext = self.template_mapper.process_wikitext_templates(final_wikitext)
                print("[+] Templates mapped and safeguards applied.")
            except Exception as e:
                print(f"[!] Warning: Template mapping encountered an issue: {e}")
                record_pipeline_issue("template_mapping", e)

        # Apply automated link & category mapping if enabled
        if self.enable_map_links and self.link_mapper:
            print("[*] Running automated Wikipedia Live Link & Category Validator/Mapper...")
            try:
                full_source_text = "\n\n".join(s.full_source for s in sections if s.full_source)
                final_wikitext = self.link_mapper.process_wikitext(final_wikitext, source_wikitext=full_source_text)
                print("[+] Wikilinks and categories successfully validated and mapped.")
            except Exception as e:
                print(f"[!] Warning: Link mapping encountered an issue: {e}")
                record_pipeline_issue("link_mapping", e)
        # Apply Typography & Reference Date Standardization if enabled
        if self.enable_typography_sanitizer and self.typography_sanitizer:
            print("[*] Running Wikipedia ID Typography & Reference Date Sanitizer (MoS / EYD V)...")
            try:
                final_wikitext = self.typography_sanitizer.sanitize_wikitext(final_wikitext)
                print("[+] Typography, reference dates, and heading sentence-casing standardized.")
            except Exception as e:
                print(f"[!] Warning: Typography sanitization encountered an issue: {e}")
                record_pipeline_issue("typography_sanitization", e)
        # Apply anti-ai slop auto-fix if enabled
        if self.enable_slop_linter and self.slop_linter:
            print("[*] Running Anti-AI-Slop Linter auto-fix...")
            try:
                final_wikitext, fix_c = self.slop_linter.auto_fix(final_wikitext)
                print(f"[+] Anti-AI-Slop Linter completed: {fix_c} calque issues corrected.")
            except Exception as e:
                print(f"[!] Warning: Anti-AI-Slop auto-fix encountered an issue: {e}")
                record_pipeline_issue("slop_linter", e)

        # Apply wikitext syntax balancer auto-repair if enabled
        if self.enable_syntax_balancer and self.syntax_balancer:
            print("[*] Running Wikitext Syntax Balancer auto-repair...")
            try:
                final_wikitext = self.syntax_balancer.auto_repair(final_wikitext)
                print("[+] Wikitext syntax balanced and repaired.")
            except Exception as e:
                print(f"[!] Warning: Syntax balancing encountered an issue: {e}")
                record_pipeline_issue("syntax_balancer", e)
        # Normalize infobox parameter keys back to canonical English to avoid Lua unknown parameter errors
        try:
            final_wikitext = default_infobox_mapper.normalize_infobox_keys(final_wikitext)
        except Exception as e:
            print(f"[!] Warning: Infobox key normalization encountered an issue: {e}")
            record_pipeline_issue("infobox_normalization", e)
        # Apply Metric-First Normalization (WP:GAYA - enabled by default)
        if getattr(self, "metric_first", True):
            try:
                final_wikitext = default_unit_converter.normalize_metric_first(final_wikitext)
            except Exception as e:
                print(f"[!] Warning: Metric-first normalization encountered an issue: {e}")
                record_pipeline_issue("metric_normalization", e)

        # Apply automated Wayback Machine archive-url injection (--enrich-archives)
        if getattr(self, "enrich_archives", False):
            print("[*] Running Reference Checker (Wayback Machine archive-url enrichment)...")
            try:
                final_wikitext = default_reference_checker.enrich_citations_with_archives(final_wikitext)
                print("[+] Citations successfully enriched with archive backups.")
            except Exception as e:
                print(f"[!] Warning: Reference archive enrichment encountered an issue: {e}")
                record_pipeline_issue("archive_enrichment", e, blocking=False)

        # Audit or upload article media (--check-media or --upload-media)
        if getattr(self, "check_media", False) or getattr(self, "upload_media", False):
            print("[*] Auditing article media (images/posters/infobox)...")
            try:
                media_items = default_media_manager.audit_article_media(title, final_wikitext)
                print(f"[+] Media audit found {len(media_items)} referenced file(s).")
                for item in media_items:
                    print(f"    - File: {item.cleaned_filename} | Status: {item.status}")

                # If --upload-media is enabled, upload non-free files
                if getattr(self, "upload_media", False):
                    wiki_user = os.environ.get("WIKI_USERNAME") or os.environ.get("MEDIAWIKI_USERNAME") or getattr(self, "publish_sandbox", None)
                    bot_pass = os.environ.get("WIKI_BOT_PASSWORD") or os.environ.get("MEDIAWIKI_BOT_PASSWORD")
                    if wiki_user and bot_pass:
                        for item in media_items:
                            if item.status == "local_non_free":
                                print(f"[*] Downloading en.wiki non-free file: {item.cleaned_filename}...")
                                dl_path = default_media_manager.download_en_media(item.cleaned_filename, self.output_dir / "media")
                                if dl_path:
                                    print(f"[*] Uploading {item.cleaned_filename} to id.wikipedia.org...")
                                    up_res = default_media_manager.upload_to_id_wiki(
                                        filename=item.cleaned_filename,
                                        file_path=dl_path,
                                        wikitext_description=item.rationale or "{{Non-free use rationale}}",
                                        username=wiki_user,
                                        bot_password=bot_pass,
                                    )
                                    if up_res.get("success"):
                                        print(f"[+] Successfully uploaded: {item.cleaned_filename}")
                                    else:
                                        print(f"[!] Upload failed for {item.cleaned_filename}: {up_res.get('error')}")
                    else:
                        print("[!] Warning: --upload-media requested but WIKI_USERNAME or WIKI_BOT_PASSWORD not found in environment.")
            except Exception as me:
                print(f"[!] Warning: Media manager encountered an issue: {me}")
                record_pipeline_issue("media_manager", me, blocking=False)

        # Record translated terms into workspace shared memory
        try:
            if hasattr(self, "custom_glossary") and self.custom_glossary:
                for en_term, id_term in self.custom_glossary.items():
                    default_shared_memory.remember_term(en_term, id_term, topic=self.topic)
        except Exception as me:
            print(f"[!] Warning: Could not record terms to shared memory: {me}")
            record_pipeline_issue("shared_memory", me, blocking=False)


        # Validate the actual bytes about to be saved, after every transformation.
        self._check_saved_integrity(original_draft, final_wikitext)
        if getattr(self, "_require_claim_review", False):
            print("[*] Checking source claims against the final article...")
            findings = review_claims("\n\n".join(s.full_source for s in sections), final_wikitext, self.gemini_client)
            if findings:
                raise ValueError("Quality gate klaim: " + "; ".join(findings))
        with open(wikitext_file, "w", encoding="utf-8") as f:
            f.write(final_wikitext)

        # Markdown representation with headers
        md_parts = [f"# {title} (Terjemahan Bahasa Indonesia)\n"]
        for s in sections:
            content = s.translated_content or s.full_source
            if content:
                md_parts.append(content)
        final_md = "\n\n".join(md_parts) + "\n"
        if self.enable_typography_sanitizer and self.typography_sanitizer:
            try:
                final_md = self.typography_sanitizer.sanitize_markdown(final_md)
            except Exception as e:
                print(f"[!] Warning: Markdown typography sanitization encountered an issue: {e}")
                record_pipeline_issue("markdown_typography", e, blocking=False)
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(final_md)

        # Talk page (Halaman Pembicaraan) attribution for CC-BY-SA compliance
        effective_oldid = oldid or getattr(self.wiki_client, "last_revision_id", None)
        talk_wikitext = self.attribution_generator.generate_talk_page(
            en_title=title,
            id_title=title,
            oldid=effective_oldid,
            topic=self.topic,
            include_proyek_wiki=self.include_proyek_wiki,
        )
        with open(talk_file, "w", encoding="utf-8") as f:
            f.write(talk_wikitext)

        # HTML Preview generation mimicking Vector 2022 skin
        try:
            self.preview_generator.save_and_open_preview(
                title=title,
                wikitext=final_wikitext,
                output_dir=str(self.output_dir),
                auto_open=False,
            )
        except Exception as e:
            print(f"[!] Warning: HTML preview generation encountered an issue: {e}")
            record_pipeline_issue("html_preview", e, blocking=False)
        # 1. Wikipedia Redirect Generation (opt-in via --generate-redirects)
        if self.enable_redirects and self.redirect_generator:
            print("[*] Generating Wikipedia ID redirects for maximum discoverability...")
            try:
                redirects = self.redirect_generator.generate_redirects(title, title)
                saved_redirects = self.redirect_generator.save_redirects(redirects, self.output_dir)
                print(f"[+] Saved {len(saved_redirects)} redirect(s) to {self.output_dir / 'redirects'}")
            except Exception as e:
                print(f"[!] Warning: Redirect generation encountered an issue: {e}")
                record_pipeline_issue("redirect_generation", e, blocking=False)

        # 2. High-value Red-Link Stub Generation
        if self.stub_generator:
            self._process_red_links_and_stubs(final_wikitext, is_interactive=False)
        # 3. Navbox & Documentation Audit (--audit-navboxes)
        if self.audit_navboxes and self.navbox_generator:
            print("[*] Auditing bottom navboxes and checking for missing templates on id.wiki...")
            try:
                # Find potential navboxes: {{TemplateName}} or commented <!-- Templat belum tersedia di id.wiki: {{TemplateName}} -->
                navboxes_to_audit = set()
                # Scan commented out missing templates
                comment_matches = re.findall(r"<!--\s*Templat belum tersedia di id\.wiki:\s*\{\{\s*([^\|\}]+)(?:\|[^\}]*)?\}\}\s*-->", final_wikitext, flags=re.IGNORECASE)
                for cm in comment_matches:
                    navboxes_to_audit.add(cm.strip())

                # Also scan bottom templates (after references/reflist)
                ref_split = re.split(r"==\s*Referensi\s*==|\{\{Daftar rujukan|\{\{Reflist", final_wikitext, flags=re.IGNORECASE)
                if len(ref_split) > 1:
                    bottom_text = ref_split[-1]
                    tmpl_matches = re.findall(r"\{\{\s*([^\|\}]+)(?:\|[^\}]*)?\}\}", bottom_text)
                    for tm in tmpl_matches:
                        clean_tm = tm.strip()
                        lower_tm = clean_tm.lower()
                        if not any(k in lower_tm for k in ("daftar rujukan", "reflist", "kategori", "category", "stub", "portal", "coord", "authority control", "defaultsort")):
                            navboxes_to_audit.add(clean_tm)

                generated_navboxes = 0
                for nb in navboxes_to_audit:
                    try:
                        nav_info = self.navbox_generator.generate_navbox(nb, check_existence=True)
                        if nav_info and not nav_info.get("already_exists"):
                            self.navbox_generator.save_navbox(nav_info, self.output_dir)
                            # Generate documentation subpage
                            if self.template_doc_auditor:
                                doc_info = self.template_doc_auditor.audit_and_generate(
                                    template_name=nav_info.get("template_name", nb),
                                    topic=self.topic,
                                )
                                self.template_doc_auditor.save_doc(doc_info, self.output_dir)
                            generated_navboxes += 1
                    except Exception as ne:
                        print(f"[!] Warning: Could not process navbox '{nb}': {ne}")
                        record_pipeline_issue(f"navbox:{nb}", ne, blocking=False)
                print(f"[+] Audited navboxes: Generated {generated_navboxes} missing navbox draft(s) in {self.output_dir / 'templates'}")
            except Exception as e:
                print(f"[!] Warning: Navbox audit encountered an issue: {e}")
                record_pipeline_issue("navbox_audit", e, blocking=False)

        # 4. Category Curation Audit (--curate-categories)
        if self.curate_categories and self.category_curator:
            print("[*] Auditing categories against id.wikipedia WP:PEDKAT guidelines...")
            try:
                cat_matches = re.findall(r"\[\[(?:Kategori|Category):([^\|\]]+)(?:\|[^\]]*)?\]\]", final_wikitext, flags=re.IGNORECASE)
                audited_cats = []
                for cat in cat_matches:
                    cat_clean = cat.strip()
                    cur_res = self.category_curator.curate_category(cat_clean)
                    audited_cats.append(cur_res)
                print(f"[+] Category Curation Report (WP:PEDKAT) for {len(audited_cats)} category/categories:")
                for c in audited_cats:
                    status = "AMAN" if c["is_safe_to_create"] else "PERINGATAN (Sebatang kara)"
                    print(f"    - [{status}] {c['category_name']}: {c['article_count']} artikel terkait.")
            except Exception as e:
                print(f"[!] Warning: Category curation encountered an issue: {e}")
                record_pipeline_issue("category_curation", e, blocking=False)

        class SavedOutputs(tuple):
            """Tuple supporting backwards-compatible (wikitext, md, talk) and 4-tuple (..., preview)."""
            def __new__(cls, wikitext_p, md_p, talk_p, preview_p):
                return super().__new__(cls, (wikitext_p, md_p, talk_p, preview_p))

            @property
            def wikitext(self) -> Path:
                return self[0]

            @property
            def markdown(self) -> Path:
                return self[1]

            @property
            def talk(self) -> Path:
                return self[2]

            @property
            def preview(self) -> Path:
                return self[3]

            def __iter__(self):
                return iter((self[0], self[1], self[2]))

            def as_four(self):
                return (self[0], self[1], self[2], self[3])

        manifest = ApprovalManifest.create(
            f"article:{title}", [wikitext_file, md_file, talk_file]
        )
        manifest.write(self.output_dir / "approval-manifest.json")
        return SavedOutputs(wikitext_file, md_file, talk_file, preview_file)
    def scan_red_links(self, wikitext: str) -> List[Dict[str, str]]:
        """
        Scans wikitext for red links formatted with {{ill|target_id|...|en|target_en...}}.
        Returns a list of dicts: [{"id_title": ..., "en_title": ...}, ...]
        """
        red_links = []
        seen_ids = set()
        for m in re.finditer(r"\{\{ill\|([^}]+)\}\}", wikitext, flags=re.IGNORECASE):
            body = m.group(1)
            parts = [p.strip() for p in body.split("|")]
            if not parts:
                continue
            id_target = parts[0]
            # Find en target
            en_target = None
            for idx, part in enumerate(parts[1:], 1):
                if part.lower() == "en" and idx + 1 < len(parts):
                    en_target = parts[idx + 1]
                    break
                elif part.lower().startswith("en="):
                    en_target = part[3:]
                    break
            if not en_target and len(parts) >= 2 and parts[1].lower() != "id":
                en_target = parts[1]

            if id_target and en_target and id_target not in seen_ids:
                seen_ids.add(id_target)
                red_links.append({"id_title": id_target, "en_title": en_target})
        return red_links

    def _process_red_links_and_stubs(self, wikitext: str, is_interactive: bool = False) -> int:
        """
        Scans red links and generates stubs based on --create-stubs flag or interactive prompt.
        """
        red_links = self.scan_red_links(wikitext)
        if not red_links:
            return 0

        selected_links = []
        if self.create_stubs:
            selected_links = red_links
        elif is_interactive:
            print(f"\n[?] Ditemukan {len(red_links)} pranala merah (red links) dalam artikel:")
            for idx, rl in enumerate(red_links, 1):
                print(f"  [{idx}] {rl['id_title']} (en: {rl['en_title']})")
            try:
                choice = input("Pilih nomor rintisan yang ingin dibuat [misal: 1,3 / all / none] (default: none): ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                choice = "none"

            if choice in ("all", "semua"):
                selected_links = red_links
            elif choice and choice not in ("none", "tidak", "0"):
                raw_indices = re.split(r"[,; ]+", choice)
                for raw_i in raw_indices:
                    if raw_i.isdigit():
                        num = int(raw_i)
                        if 1 <= num <= len(red_links):
                            selected_links.append(red_links[num - 1])

        if not selected_links:
            return 0
        print(f"[*] Scanning for high-value red links ({{{{ill}}}}) to generate compliant stubs ({len(selected_links)} selected)...")
        stubs_created = 0
        for item in selected_links:
            id_target = item["id_title"]
            en_target = item["en_title"]
            try:
                stub_info = self.stub_generator.generate_stub(
                    en_title=en_target,
                    id_title=id_target,
                    topic=self.topic,
                )
                self.stub_generator.save_stub(stub_info, self.output_dir)
                stubs_created += 1
            except Exception as se:
                print(f"[!] Warning: Could not generate stub for '{id_target}': {se}")
        print(f"[+] Generated and saved {stubs_created} stub(s) to {self.output_dir / 'stubs'}")
        return stubs_created

    def _handle_sandbox_publishing(
        self, title: str, wikitext_file: Path, talk_file: Path, auto_approve: bool = False
    ) -> None:
        username = self.publish_sandbox
        if not username:
            username = os.environ.get("WIKI_SANDBOX_USER") or os.environ.get("WIKI_USERNAME")

        target_choice = "1"
        if self.publish_main:
            target_choice = "3"
        elif self.promote_draft:
            target_choice = "2"
        elif not auto_approve:
            if not username:
                try:
                    ask_publish = input("\n[?] Would you like to publish this draft to your id.wikipedia sandbox? [y/N]: ").strip().lower()
                    if ask_publish != "y":
                        print("[*] Penerbitan dilewati. Hasil tersimpan secara lokal.")
                        return
                    username = input("[?] Enter your Wikipedia username: ").strip()
                    proj_in = input(f"[?] Masukkan nama subkategori/folder (default: {self.project_slug}): ").strip()
                    if proj_in:
                        self.project_slug = proj_in
                except (KeyboardInterrupt, EOFError):
                    return
            else:
                print("\n[?] Target Penerbitan:")
                print("  [1] Bak Pasir (Draf Aman untuk Kurasi) [Default]")
                print("  [2] Pindahkan Draf ke Ruang Nama Utama (Tayang Resmi)")
                print("  [3] Terbitkan Langsung ke Ruang Nama Utama")
                print("  [4] Simpan Lokal Saja")
                try:
                    choice_in = input("Pilih target penerbitan [1/2/3/4] (default: 1): ").strip()
                    if choice_in in ("1", "2", "3", "4"):
                        target_choice = choice_in
                    elif not choice_in:
                        target_choice = "1"
                except (KeyboardInterrupt, EOFError):
                    target_choice = "1"
        if target_choice == "4":
            print("[*] Penerbitan dilewati. Hasil tersimpan secara lokal.")
            return

        if not username:
            print("[!] Nama pengguna Wikipedia diperlukan untuk penerbitan.")
            return

        bot_password = os.environ.get("WIKI_BOT_PASSWORD")
        if not bot_password:
            try:
                import getpass
                bot_password = getpass.getpass("[?] Masukkan Wikipedia Bot Password (kosongkan untuk simulasi dry-run): ").strip()
            except (KeyboardInterrupt, EOFError):
                return
        dry_run = not bool(bot_password)
        chosen_summary = self.summary

        if not dry_run:
            manifest_path = self.output_dir / "approval-manifest.json"
            if not manifest_path.exists() and (self.publish_main or self.promote_draft):
                print("[!] Publish blocked: approval-manifest.json is missing.")
                return
            if manifest_path.exists():
                gate_result = PublishGate().check(
                    title,
                    manifest_path,
                    allow_existing=bool(
                        self.force_overwrite
                        or (not self.publish_main and not self.promote_draft)
                    ),
                )
                if not gate_result.allowed:
                    print(f"[!] Publish blocked by gate: {'; '.join(gate_result.reasons)}")
                    return

        try:
            wikitext_content = wikitext_file.read_text(encoding="utf-8")
            talk_content = talk_file.read_text(encoding="utf-8") if talk_file.exists() else None
        except Exception as e:
            print(f"[!] Gagal membaca file sumber untuk penerbitan: {e}")
            return

        # Choice 3: Terbitkan Langsung ke Ruang Nama Utama
        if target_choice == "3":
            target_title = self.publish_main or title
            if dry_run:
                print(f"[*] Menjalankan penerbitan langsung ke Ruang Nama Utama '{target_title}' dalam mode DRY-RUN...")
            else:
                print(f"[*] Menerbitkan langsung ke Ruang Nama Utama '{target_title}' sebagai '{username}'...")

            pub_result = self.mainspace_publisher.publish_directly_to_mainspace(
                username=username,
                bot_password=bot_password or "dummy",
                mainspace_title=target_title,
                wikitext=wikitext_content,
                talk_wikitext=talk_content,
                summary=chosen_summary,
                force=self.force_overwrite,
                dry_run=dry_run,
                en_title=title,
            )
            if pub_result.get("success"):
                main_info = pub_result.get("main_page", {})
                print(f"[+] Artikel Utama Tayang : {main_info.get('url')}")
                talk_info = pub_result.get("talk_page", {})
                if talk_info:
                    print(f"[+] Halaman Pembicaraan : {talk_info.get('url')}")
                wiki_info = pub_result.get("wikidata", {})
                if wiki_info:
                    if wiki_info.get("success"):
                        print(f"[+] Wikidata Terhubung   : {wiki_info.get('item_id')} -> {wiki_info.get('url')}")
                    else:
                        print(f"[!] Wikidata Linker Info : {wiki_info.get('error')}")
            else:
                print(f"[!] Penerbitan ke ruang nama utama gagal: {pub_result.get('error')}")
            return

        # Choice 1 or 2: Publish to sandbox first (if 2, then move to mainspace)
        if dry_run:
            print("[*] Running in DRY-RUN mode (simulation without network edits)...")
        else:
            print(f"[*] Publishing draft to user sandbox for '{username}'...")

        publish_kwargs = {
            "username": username,
            "bot_password": bot_password or "dummy",
            "article_title": title,
            "wikitext": wikitext_content,
            "talk_wikitext": talk_content,
            "slug": self.sandbox_slug,
            "project_slug": self.project_slug,
            "dry_run": dry_run,
        }
        if chosen_summary is not None:
            publish_kwargs["summary"] = chosen_summary

        pub_result = self.sandbox_publisher.publish_to_sandbox(**publish_kwargs)
        if not pub_result.get("success"):
            print(f"[!] Sandbox publishing failed: {pub_result.get('error')}")
            return

        main_info = pub_result.get("main_page", {})
        sandbox_title = main_info.get("title", "")
        print(f"[+] Sandbox Draft URL : {main_info.get('url')}")
        talk_info = pub_result.get("talk_page", {})
        if talk_info:
            print(f"[+] Sandbox Talk URL  : {talk_info.get('url')}")

        # Choice 2: Pindahkan Draf ke Ruang Nama Utama
        if target_choice == "2":
            target_title = self.promote_draft if isinstance(self.promote_draft, str) and self.promote_draft else title
            # Collision check
            exists, existing_url = self.mainspace_publisher.check_mainspace_collision(target_title)
            if exists and not self.force_overwrite:
                print(f"[!] Peringatan: Artikel '{target_title}' sudah ada di Wikipedia ({existing_url}). Pemindahan dibatalkan demi keamanan.")
                return

            if dry_run:
                print(f"[*] Memindahkan draf '{sandbox_title}' ke '{target_title}' dalam mode DRY-RUN...")
            else:
                print(f"[*] Memindahkan draf '{sandbox_title}' ke '{target_title}'...")

            move_res = self.mainspace_publisher.move_draft_to_mainspace(
                username=username,
                bot_password=bot_password or "dummy",
                sandbox_source=sandbox_title,
                mainspace_target=target_title,
                reason=chosen_summary,
                move_talk=bool(talk_content),
                dry_run=dry_run,
                en_title=title,
            )
            if move_res.get("success"):
                print(f"[+] Berhasil memindahkan ke Ruang Nama Utama: {move_res.get('url')}")
                wiki_info = move_res.get("wikidata", {})
                if wiki_info:
                    if wiki_info.get("success"):
                        print(f"[+] Wikidata Terhubung   : {wiki_info.get('item_id')} -> {wiki_info.get('url')}")
                    else:
                        print(f"[!] Wikidata Linker Info : {wiki_info.get('error')}")
            else:
                print(f"[!] Pemindahan draf gagal: {move_res.get('error')}")
def main() -> None:
    load_env_file()
    # Keep Unicode status tables and streamed translations printable on Windows.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = build_cli_parser()
    args = parser.parse_args()
    if handle_storage_commands(args, parser):
        return

    if handle_glossary_actions(args, parser):
        return
    cli = WikiTranslatorCLI(
        glossary_resolver=GlossaryResolver(memory=GlossaryMemory(args.glossary_memory)),
        model=(
            f"gemini-3.8-flash-{args.thinking}"
            if args.model == "gemini-3.8-flash" and args.thinking != "auto"
            else args.model
        ),
        thinking=args.thinking,
        output_dir=args.output_dir,
        topic=args.topic,
        enable_cache=not args.no_cache,
        enable_compression=not args.no_compression,
        enable_delta_skip=not args.no_delta_skip,
        enable_auto_glossary=args.auto_glossary,
        enable_map_links=args.map_links,
        enable_polish=args.polish,
        enable_typography_sanitizer=args.typography,
        enable_slop_linter=args.slop_linter,
        enable_syntax_balancer=args.syntax_balancer,
        enable_template_mapper=args.template_mapper,
        auto_preview=args.preview,
        publish_sandbox=args.publish_sandbox,
        publish_main=args.publish_main,
        promote_draft=args.promote_draft,
        force_overwrite=args.force_overwrite,
        sandbox_slug=args.sandbox_slug,
        project_slug=args.sandbox_project,
        enable_redirects=args.enable_redirects,
        create_stubs=args.create_stubs,
        audit_navboxes=args.audit_navboxes,
        curate_categories=args.curate_categories,
        summary=args.summary,
        metric_first=args.metric_first,
        enrich_archives=args.enrich_archives,
        check_media=args.check_media,
        upload_media=args.upload_media,
        include_proyek_wiki=args.include_proyek_wiki,
        by_paragraph=args.by_paragraph,
    )

    if handle_ecosystem_and_category_commands(args, parser, cli):
        return

    if handle_page_gen_commands(args, parser):
        return

    if handle_batch_command(args, cli):
        return
    if getattr(args, "delink_ill", None):
        from .ill_delinker import default_ill_delinker
        target = args.delink_ill.strip()
        print(f"[*] Scanning Wikipedia backlinks for '{{{{ill}}}}' referencing '{target}'...")
        user = os.environ.get("WIKI_USERNAME")
        pwd = os.environ.get("WIKI_BOT_PASSWORD")
        dry_run = not (user and pwd)
        if dry_run:
            print("[*] Running in DRY-RUN mode (credentials not found in environment)...")
        delink_res = default_ill_delinker.delink_target_across_wikipedia(
            target_title=target,
            username=user or "User",
            bot_password=pwd or "pass",
            dry_run=dry_run,
        )
        print(f"[+] Referring articles found: {delink_res['referring_articles_count']}")
        print(f"[+] Articles requiring delink: {delink_res['modified_articles_count']}")
        for r in delink_res.get("results", []):
            stat = "simulated" if r.get("status") == "simulated" else ("success" if r.get("success") else "failed")
            print(f"    - {r['title']}: {r['converted_links']} link(s) converted [{stat}]")
        return


    cli.run_interactive(
        article_title=args.title,
        auto_approve=args.auto_approve,
        revid=args.revid,
    )
if __name__ == "__main__":
    main()
