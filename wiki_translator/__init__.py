"""
Wiki Translator - Grade A++ English to Indonesian Wikipedia Translation Suite.
"""
from .wiki_link_mapper import (
    WikiLinkMapper,
    default_link_mapper,
    LinkResolution,
    CategoryResolution,
    LinkFidelityValidator,
    default_fidelity_validator,
    LinkFidelityIssue,
    FidelityValidationResult,
)
from .link_fidelity_validator import (
    LinkFidelityValidator as StandaloneLinkFidelityValidator,
)
from .syntax_balancer import (
    WikitextSyntaxBalancer,
    default_syntax_balancer,
)
from .template_mapper import (
    WikiTemplateMapper,
    default_template_mapper,
    normalize_disambiguation_titles,
    normalize_disambiguation_parenthetical,
    normalize_tentang_param,
)
from .slop_linter import (
    AntiAISlopLinter,
    default_slop_linter,
    SlopLintResult,
    SlopViolation,
)
from .attribution_generator import (
    TalkPageAttributionGenerator,
    default_attribution_generator,
)
from .html_preview import (
    HTMLPreviewGenerator,
    default_preview_generator,
)
from .http_client import (
    MediaWikiApiClient,
    default_idwiki_client,
    default_wikidata_client,
)
from .sandbox_publisher import (
    SandboxPublisher,
    default_sandbox_publisher,
)
from .unit_converter import (
    UnitCurrencyLocalizer,
    default_unit_converter,
    normalize_metric_first,
)
from .infobox_mapper import (
    InfoboxMapper,
    default_infobox_mapper,
)
from .editorial_qa import (
    EditorialQAPipeline,
    default_qa_pipeline,
    QAAuditReport,
    DrafterAuditResult,
    LinguisticAuditResult,
    WikiTechnicianAuditResult,
)
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
from .category_reconciler import (
    CategoryCandidate,
    CategoryReconciler,
    CategoryReconciliationPlan,
    default_category_reconciler,
)
from .category_creator import (
    CategoryCreationPlan,
    CategoryCreationPlanner,
    CategoryDependency,
    ParentCategoryMapping,
    default_category_creation_planner,
)
from .category_materializer import (
    CategoryMaterializationResult,
    CategoryMaterializer,
    default_category_materializer,
)
from .category_tree_audit import (
    CategoryDiffAudit,
    CategoryDiffAuditor,
    CategoryTreeNode,
    CategoryTreePlan,
    CategoryTreePlanner,
    default_category_diff_auditor,
    default_category_tree_planner,
)
from .dependency_deployer import (
    DependencyDeploymentResult,
    DependencyDeployer,
    default_dependency_deployer,
)
from .approval_journal import ApprovalManifest, TransactionJournal
from .publish_gate import (
    GateResult,
    PublishGate,
    PublishTransaction,
    TransactionResult,
)
from .factual_audit import (
    FactualConsistencyAuditor,
    FactualConsistencyResult,
    default_factual_auditor,
)
from .entity_grounding import (
    EntityGroundingAuditor,
    EntityGroundingResult,
    default_entity_grounding_auditor,
)
from .warung_kopi_harvester import (
    WarungKopiHarvester,
    WarungKopiTerm,
    default_warung_kopi_harvester,
)
from .featured_article_harvester import (
    FeaturedArticleHarvester,
    APCritiquePoint,
    default_fa_harvester,
)
from .category_page_sync import CategoryPageSyncResult, CategoryPageSynchronizer
from .translation_evidence import TranslationCandidate, TranslationEvidenceResolver
from .glossary_audit import (
    GlossaryConsistencyResult,
    GlossaryTermEvidence,
    audit_glossary_consistency,
    resolve_terms_with_evidence,
)
from .glossary_memory import (
    GlossaryCandidate,
    GlossaryMemory,
    extract_revision_corrections,
)
from .stub_generator import (
    StubGenerator,
    default_stub_generator,
)
from .media_manager import (
    MediaManager,
    default_media_manager,
    MediaAuditItem,
)
from .batch_runner import (
    BatchRunner,
    default_batch_runner,
    BatchReport,
    ArticleBatchItemResult,
)
from .shared_memory import (
    WorkspaceSharedMemory,
    default_shared_memory,
)
from .reference_checker import (
    ReferenceChecker,
    default_reference_checker,
)
from .mainspace_publisher import (
    MainspacePublisher,
    default_mainspace_publisher,
)
from .gemini import (
    SmartComplexityAnalyzer,
    default_complexity_analyzer,
    GeminiTranslatorClient,
)
from .wikidata_linker import (
    WikidataLinker,
    default_wikidata_linker,
)
from .template_syncer import (
    TemplateSyncer,
    default_template_syncer,
)
from .article_reviewer import (
    ArticleReviewer,
    default_article_reviewer,
    APReviewReport,
    ReviewFinding,
)
from .paragraph_translator import (
    ParagraphTranslator,
    default_paragraph_translator,
    split_into_paragraph_chunks,
)
from .template_ecosystem import (
    RecursiveDependencyScanner,
    CategoryTreeLinker,
    EnWikiPreflightInspector,
    PreflightReport,
    SandboxTestcaseEngine,
    TemplateEcosystemManager,
    default_ecosystem_manager,
)
from .page_generators import (
    PageQueueItem,
    CategoryPageGenerator,
    WhatLinksHerePageGenerator,
    PageQueueExporter,
)
from .awb_genfixes import (
    GeneralFixesEngine,
    RegExTypoFixEngine,
    AWBGenFixes,
    default_genfixes,
)
from .storage_manager import (
    StorageManager,
    default_storage_manager,
)
from .film_categorizer import (
    FilmCategoryNormalizer,
    default_film_categorizer,
)
from .ill_delinker import (
    IllDelinker,
    default_ill_delinker,
)
from .lexical_register import (
    LexicalRegisterReranker,
    default_lexical_reranker,
)
from .kateglo_client import (
    KategloClient,
    default_kateglo_client,
    KategloEntry,
)
from .gramatika_engine import (
    GramatikaEngine,
    default_gramatika_engine,
)
from .eyd_engine import (
    EYDEngine,
    default_eyd_engine,
)
from .historical_ethnonyms import (
    HistoricalEthnonymsManager,
    default_ethnonyms_manager,
)
from .historical_offices import (
    HistoricalOfficesManager,
    default_offices_manager,
)
from .semantic_verifier import (
    UniversalSemanticVerifier,
    default_semantic_verifier,
)
