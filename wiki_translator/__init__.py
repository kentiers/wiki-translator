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
    SandboxTestcaseEngine,
    TemplateEcosystemManager,
    default_ecosystem_manager,
)
