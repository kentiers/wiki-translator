"""
Multi-Layer Editorial QA Pipeline for Indonesian Wikipedia Translation.

Simulates a 4-Layer Editorial & QA Room before publication:
- Layer 1: Drafter Audit (Word count, section count, lead presence).
- Layer 2: Linguistic & Anti-Slop Audit (KBBI VI, EYD V compliance, calque check from slop_linter, naturalness score).
- Layer 3: Wiki Technician Audit:
  * No broken {{SHORTDESC:...}} or raw {{Short description}}.
  * Infobox parameters are clean English keys (no unknown parameter warnings).
  * Wikilink brackets [[ ... ]], templates {{ ... }}, <ref> balance (from syntax_balancer).
  * Valid categories check (no empty red categories without comments, no invalid markup).
- Layer 4: Chief Editor Review & Scorecard:
  * Generates visual terminal summary / scorecard (Overall Score 0-100, Grade A++, A, B, etc.).
  * Status: PASSED / APPROVED FOR PUBLICATION or NEEDS REVISION.
  * Inspection checklist.
"""

from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from .infobox_mapper import (
    INDONESIAN_TO_ENGLISH_INFOBOX_KEYS,
    InfoboxMapper,
    default_infobox_mapper,
)
from .slop_linter import AntiAISlopLinter, SlopLintResult, default_slop_linter
from .syntax_balancer import WikitextSyntaxBalancer, default_syntax_balancer
from .template_mapper import STRIP_METADATA_TEMPLATES
from .factual_audit import FactualConsistencyResult, default_factual_auditor
from .lexical_register import LexicalRegisterReranker, default_lexical_reranker

@dataclass
class DrafterAuditResult:
    word_count: int
    section_count: int
    has_lead: bool
    has_references_section: bool
    score: int  # 0 - 100
    warnings: List[str] = field(default_factory=list)


@dataclass
class LinguisticAuditResult:
    naturalness_score: int  # 0 - 100
    slop_score: int  # 0 - 100
    calque_count: int
    eyd_compliance_score: int  # 0 - 100
    score: int  # 0 - 100
    warnings: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)


@dataclass
class WikiTechnicianAuditResult:
    has_broken_shortdesc: bool
    has_stripped_metadata_templates: bool
    has_uncommented_red_categories: bool
    score: int  # 0 - 100
    unknown_infobox_keys: List[str] = field(default_factory=list)
    syntax_balance_issues: List[Dict[str, Any]] = field(default_factory=list)
    uncommented_categories: List[str] = field(default_factory=list)
    mangled_wikilinks: List[str] = field(default_factory=list)
    raw_english_redlinks: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


MANGLED_WIKILINK_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (
        re.compile(r"\[\[[^\]]*\b(?:Best|Feature|Award|Awards)\s+dokumenter\b", re.IGNORECASE),
        "Pranala rusak percampuran bahasa (seperti 'Best dokumenter')",
    ),
    (
        re.compile(r"\[\[[^\]]*\bdokumenter\s+(?:Feature|Best|Award|Awards)\b", re.IGNORECASE),
        "Pranala rusak percampuran bahasa (seperti 'dokumenter Feature')",
    ),
]

RAW_ENGLISH_REDLINK_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (
        re.compile(r"\[\[\s*List\s+of\s+[^\]|]+(?:\||\]\])", re.IGNORECASE),
        "Pranala merah mentah bahasa Inggris (List of ...)",
    ),
    (
        re.compile(
            r"\[\[\s*([^\]|]+?\s*\((?:director|film\s+series|character|actor|actress|writer|series|season\s+\d+|Harry Potter)\))\s*(?:\||\]\])",
            re.IGNORECASE,
        ),
        "Pranala merah penentu arti bahasa Inggris mentah",
    ),
]

@dataclass
class QAAuditReport:
    overall_score: int
    grade: str  # "A++", "A+", "A", "B", "C", "F"
    approved: bool
    title: Optional[str] = None
    layer1_drafter: Optional[DrafterAuditResult] = None
    layer2_linguistic: Optional[LinguisticAuditResult] = None
    layer3_technician: Optional[WikiTechnicianAuditResult] = None
    critical_errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    factual_consistency: Optional[FactualConsistencyResult] = None

    def is_approved(self) -> bool:
        """Returns True if the article meets all editorial publication criteria."""
        return self.approved

    def render_terminal_scorecard(self) -> str:
        """Renders a visually striking terminal scorecard for publication review."""
        title_str = self.title or "Artikel Tanpa Judul"
        status_banner = (
            "PASSED / APPROVED FOR PUBLICATION (AUTOMATED CHECKS)"
            if self.approved else "NEEDS REVISION / UNAPPROVED"
        )
        status_color_box = "[✔ PASS]" if self.approved else "[✖ REVISE]"

        width = 72
        sep = "=" * width
        subsep = "-" * width

        lines = [
            sep,
            f"   🏛️  EDITORIAL & QA SCORECARD — {title_str}",
            f"   Status: {status_color_box} {status_banner}",
            f"   Overall Score: {self.overall_score}/100  |  Grade: {self.grade}",
            sep,
            "1. DRAFTER AUDIT (Structure & Density):",
        ]

        if self.layer1_drafter:
            l1 = self.layer1_drafter
            lead_str = "Hadir (Baik)" if l1.has_lead else "Hilang (Perlu lead)"
            ref_str = "Hadir" if l1.has_references_section else "Tidak terdeteksi"
            lines.append(f"   * Word Count       : {l1.word_count} kata")
            lines.append(f"   * Section Count    : {l1.section_count} bagian")
            lines.append(f"   * Lead Section     : {lead_str}")
            lines.append(f"   * References Sec   : {ref_str}")
            lines.append(f"   * Layer 1 Score    : {l1.score}/100")
            for w in l1.warnings:
                lines.append(f"     [!] {w}")
        else:
            lines.append("   * Not evaluated.")

        lines.append(subsep)
        lines.append("2. LINGUISTIC & ANTI-SLOP AUDIT (KBBI VI & EYD V):")
        if self.layer2_linguistic:
            l2 = self.layer2_linguistic
            lines.append(f"   * Naturalness Score: {l2.naturalness_score}/100")
            lines.append(f"   * Anti-Slop Score  : {l2.slop_score}/100")
            lines.append(f"   * Calque Issues    : {l2.calque_count} terdeteksi")
            lines.append(f"   * EYD V Compliance : {l2.eyd_compliance_score}/100")
            lines.append(f"   * Layer 2 Score    : {l2.score}/100")
            for w in l2.warnings[:3]:
                lines.append(f"     [!] {w}")
            if len(l2.warnings) > 3:
                lines.append(f"     ... ({len(l2.warnings) - 3} peringatan lainnya)")
        else:
            lines.append("   * Not evaluated.")

        lines.append(subsep)
        lines.append("3. WIKI TECHNICIAN AUDIT (Syntax & Templates):")
        if self.layer3_technician:
            l3 = self.layer3_technician
            shortdesc_str = "BERSIH (Tidak ada)" if not l3.has_broken_shortdesc else "DITEMUKAN (Rusak!)"
            metadata_str = "BERSIH (Dihapus)" if not l3.has_stripped_metadata_templates else "TERDETEKSI (Perlu dibersihkan)"
            infobox_str = (
                "BERSIH (Kunci Inggris kanonik)"
                if not l3.unknown_infobox_keys
                else f"PERINGATAN ({len(l3.unknown_infobox_keys)} kunci non-kanonik)"
            )
            syntax_str = (
                "SEIMBANG (0 masalah)"
                if not l3.syntax_balance_issues
                else f"MASALAH ({len(l3.syntax_balance_issues)} ketidakseimbangan)"
            )
            cat_str = (
                "AMAN (Terkonfirmasi/terkomentari)"
                if not l3.has_uncommented_red_categories
                else f"MERAH ({len(l3.uncommented_categories)} kategori polos tanpa komentar)"
            )

            lines.append(f"   * Broken SHORTDESC : {shortdesc_str}")
            lines.append(f"   * En-Wiki Metadata : {metadata_str}")
            lines.append(f"   * Infobox Schema   : {infobox_str}")
            lines.append(f"   * Syntax Balancing : {syntax_str}")
            lines.append(f"   * Categories Guard : {cat_str}")
            lines.append(f"   * Layer 3 Score    : {l3.score}/100")

            for err in l3.errors:
                lines.append(f"     [✖ ERROR] {err}")
            for w in l3.warnings:
                lines.append(f"     [!] {w}")
        else:
            lines.append("   * Not evaluated.")

        lines.append(subsep)
        lines.append("4. CHIEF EDITOR VERDICT & RECOMMENDATIONS:")
        if self.critical_errors:
            lines.append("   * Critical Blockers:")
            for e in self.critical_errors:
                lines.append(f"     - [BLOCKER] {e}")
        if self.recommendations:
            lines.append("   * Actionable Recommendations:")
            for r in self.recommendations:
                lines.append(f"     - {r}")
        if not self.critical_errors and not self.recommendations:
            lines.append("   * Pemeriksaan otomatis lulus; ketepatan makna masih memerlukan tinjauan sumber.")

        lines.append(sep)
        return "\n".join(lines)


class EditorialQAPipeline:
    """
    Multi-Layer Editorial QA Pipeline for Indonesian Wikipedia translations.
    """

    def __init__(
        self,
        slop_linter: Optional[AntiAISlopLinter] = None,
        syntax_balancer: Optional[WikitextSyntaxBalancer] = None,
        infobox_mapper: Optional[InfoboxMapper] = None,
        factual_auditor=None,
        lexical_reranker: Optional[LexicalRegisterReranker] = None,
    ):
        self.slop_linter = slop_linter or default_slop_linter
        self.syntax_balancer = syntax_balancer or default_syntax_balancer
        self.infobox_mapper = infobox_mapper or default_infobox_mapper
        self.factual_auditor = factual_auditor or default_factual_auditor
        self.lexical_reranker = lexical_reranker or default_lexical_reranker
    # -------------------------------------------------------------------------
    # Layer 1: Drafter Audit
    # -------------------------------------------------------------------------
    def audit_drafter(self, wikitext: str) -> DrafterAuditResult:
        """Audits word count, section count, and presence of lead & references."""
        clean_text = re.sub(r"<!--[\s\S]*?-->", "", wikitext)
        clean_text = re.sub(r"<ref[^>]*>[\s\S]*?<\/ref>", "", clean_text)
        clean_text = re.sub(r"<ref[^>]*\/>", "", clean_text)
        clean_text = re.sub(r"\{\{[\s\S]*?\}\}", "", clean_text)
        clean_text = re.sub(r"\[\[(?:File|Berkas|Image|Gambar):[^\]]+\]\]", "", clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"\[\[(?:Category|Kategori):[^\]]+\]\]", "", clean_text, flags=re.IGNORECASE)

        words = re.findall(r"\b\w+\b", clean_text)
        word_count = len(words)

        # Count headings (== Heading ==)
        headings = re.findall(r"^={2,5}[^=]+={2,5}\s*$", wikitext, flags=re.MULTILINE)
        section_count = len(headings)

        # Check lead section: text before the first section heading
        first_heading = re.search(r"^={2,5}[^=]+={2,5}\s*$", wikitext, flags=re.MULTILINE)
        lead_text = wikitext[: first_heading.start()] if first_heading else wikitext
        # Remove templates and comments from lead text to verify actual prose
        lead_prose = re.sub(r"<!--[\s\S]*?-->", "", lead_text)
        lead_prose = re.sub(r"\{\{[\s\S]*?\}\}", "", lead_prose)
        lead_words = re.findall(r"\b\w+\b", lead_prose)
        has_lead = len(lead_words) >= 15

        # Check references section presence
        has_ref = bool(
            re.search(
                r"==\s*(?:Rujukan|Referensi|Daftar rujukan|Catatan kaki|Pranala luar)\s*==",
                wikitext,
                flags=re.IGNORECASE,
            )
            or re.search(r"\{\{\s*(?:reflist|daftar rujukan)\s*\}\}", wikitext, flags=re.IGNORECASE)
        )

        warnings: List[str] = []
        score = 100

        if word_count < 50:
            score -= 30
            warnings.append(f"Artikel sangat pendek ({word_count} kata), berpotensi menjadi sub-rintisan.")
        elif word_count < 150:
            score -= 10
            warnings.append(f"Artikel relatif ringkas ({word_count} kata).")

        if not has_lead:
            score -= 25
            warnings.append("Bagian pengantar (lead section) tidak terdeteksi atau terlalu singkat.")

        if not has_ref:
            score -= 15
            warnings.append("Bagian rujukan/referensi tidak ditemukan secara eksplisit.")

        if section_count == 0 and word_count > 300:
            score -= 10
            warnings.append("Artikel panjang tanpa pembagian sub-bagian (sections).")

        score = max(0, min(100, score))
        return DrafterAuditResult(
            word_count=word_count,
            section_count=section_count,
            has_lead=has_lead,
            has_references_section=has_ref,
            score=score,
            warnings=warnings,
        )

    # -------------------------------------------------------------------------
    # Layer 2: Linguistic & Anti-Slop Audit
    # -------------------------------------------------------------------------
    def audit_linguistics(self, wikitext: str) -> LinguisticAuditResult:
        """Audits Indonesian language quality, calques, and EYD compliance."""
        lint_res: SlopLintResult = self.slop_linter.lint(wikitext)
        slop_score = lint_res.score
        calque_count = len(lint_res.violations)

        warnings = []
        for v in lint_res.violations:
            warnings.append(f"L{v.line_number}: {v.explanation} (ditemukan '{v.matched_text}')")

        # EYD V & Typographical compliance check
        eyd_deductions = 0
        eyd_warnings = []

        # Check for unformatted hyphens instead of en-dash in number ranges (e.g. 1990-1995)
        # Avoid checking URLs or template parameters
        prose_only = re.sub(r"<!--[\s\S]*?-->", "", wikitext)
        prose_only = re.sub(r"https?://\S+", "", prose_only)
        prose_only = re.sub(r"\|\s*[^=]+=([^|\}]+)", "", prose_only)

        if re.search(r"\b\d{4}-\d{4}\b", prose_only):
            eyd_deductions += 5
            eyd_warnings.append("Terdapat rentang tahun dengan tanda hubung biasa (-) alih-alih tanda pisah (–).")

        # Check for non-standard space before punctuation (e.g. "kata , kata")
        if re.search(r"\w\s+[,.:;?!]", prose_only):
            eyd_deductions += 5
            eyd_warnings.append("Terdapat spasi berlebih sebelum tanda baca.")

        # Mask protected zones (code, templates, refs, entities) for pure prose punctuation audit
        masked_prose, _ = self.slop_linter._mask_protected_zones(wikitext)

        # Check narrative semicolons (ignoring masked tokens)
        untokened_for_semis = re.sub(r"SLOPMASK\d+END", "", masked_prose)
        semis = re.findall(r"[a-zA-Z0-9\]\)]\s*;\s*[a-zA-Z\[]", untokened_for_semis)
        if semis:
            d = min(20, len(semis) * 5)
            eyd_deductions += d
            eyd_warnings.append(
                f"Terdapat {len(semis)} tanda titik koma (;) pada kalimat naratif. Hindari titik koma; pecah menjadi dua kalimat dengan tanda titik (.) atau gunakan konjungsi alami."
            )

        # Check comma clutter (sentences with >= 4 commas)
        prose_clean = re.sub(r"<!--[\s\S]*?-->", "", wikitext)
        prose_clean = re.sub(r"<ref\b[^>]*>[\s\S]*?</ref>", "", prose_clean)
        prose_clean = re.sub(r"<ref\b[^>]*/>", "", prose_clean)
        prose_clean = re.sub(r"\{\{[^{}]*\}\}", "", prose_clean)
        prose_clean = re.sub(r"\[\[(?:[^|\]]+\|)?([^\]]+)\]\]", r"\1", prose_clean)
        prose_clean = re.sub(r"^={1,6}[^=]+={1,6}\s*$", "", prose_clean, flags=re.M)

        cluttered_sents = []
        for p in prose_clean.split("\n\n"):
            p_strip = p.strip()
            if not p_strip or p_strip.startswith(("{|", "|", "!", "*", "#")):
                continue
            for s in re.split(r"[.!?]\s+", p_strip):
                s_clean = s.strip()
                if not s_clean or s_clean.startswith(("{|", "|", "!", "*", "#")):
                    continue
                c_cnt = s_clean.count(",")
                if c_cnt >= 4:
                    cluttered_sents.append((c_cnt, s_clean[:50]))

        if cluttered_sents:
            d = min(25, len(cluttered_sents) * 5)
            eyd_deductions += d
            eyd_warnings.append(
                f"Terdapat {len(cluttered_sents)} kalimat dengan kepadatan koma berlebih (>= 4 koma) yang menimbulkan efek cegukan (comma fatigue). Contoh: '{cluttered_sents[0][1]}...'."
            )

        # Check comma before coordinating conjunctions on parallel predicates
        comma_dan = re.findall(r"\b(\w+),\s+(dan|serta)\s+(\w+)\b", masked_prose, flags=re.IGNORECASE)
        flagged_dan = [
            f"{w1}, {conj} {w2}"
            for w1, conj, w2 in comma_dan
            if re.match(r"^(?:me\w+|di\w+|ber\w+|ter\w+)", w1) and re.match(r"^(?:me\w+|di\w+|ber\w+|ter\w+)", w2)
        ]
        if flagged_dan:
            d = min(15, len(flagged_dan) * 3)
            eyd_deductions += d
            eyd_warnings.append(
                f"Terdapat {len(flagged_dan)} tanda koma sebelum kata sambung koordinatif predikat setara ('{flagged_dan[0]}'). Dalam EYD V koma dihindari jika subjeknya sama."
            )

        # Check appositive comma sandwiching proper nouns (e.g. "rekan aktivis mereka, [[Anna Filosofova]], segera")
        appositive_commas = re.findall(
            r"\b((?:[Aa]yah|[Ii]bu|[Ss]audara|[Ss]audari|[Aa]dik|[Kk]akak|[Aa]nak|[Pp]utra|[Pp]utri|[Ss]uami|[Ii]stri|[Ss]ahabat|[Tt]eman|[Rr]ekan|[Kk]olega|[Pp]enulis|[Aa]rsitek|[Rr]ektor|[Mm]enteri|[Pp]residen|[Rr]aja|[Kk]aisar)(?:\s+\w+){0,3}),\s+(?:\[\[(?:[^|\]]+\|)?([^\]]+)\]\]|([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)),\s+(\w+)\b",
            wikitext,
        )
        if appositive_commas:
            d = min(15, len(appositive_commas) * 3)
            eyd_deductions += d
            desc = appositive_commas[0][0]
            name = appositive_commas[0][1] or appositive_commas[0][2]
            nxt = appositive_commas[0][3]
            eyd_warnings.append(
                f"Terdapat {len(appositive_commas)} frasa aposisi koma ganda yang menjepit nama diri ('{desc}, {name}, {nxt}'). Sesuai EYD V sebutan atributif langsung tidak perlu diapit koma."
            )

        eyd_compliance_score = max(0, 100 - eyd_deductions)
        warnings.extend(eyd_warnings)

        # Lexical register & diction maturity check
        reg_score, reg_warnings = self.lexical_reranker.calculate_register_score(wikitext)
        warnings.extend(reg_warnings)

        # Composite naturalness calculation incorporating register weight
        naturalness_score = int(0.5 * slop_score + 0.3 * eyd_compliance_score + 0.2 * reg_score)
        layer_score = int(0.5 * slop_score + 0.5 * naturalness_score)
        return LinguisticAuditResult(
            naturalness_score=naturalness_score,
            slop_score=slop_score,
            calque_count=calque_count,
            eyd_compliance_score=eyd_compliance_score,
            score=layer_score,
            warnings=warnings,
            suggestions=lint_res.suggestions_summary,
        )

    # -------------------------------------------------------------------------
    # Layer 3: Wiki Technician Audit
    # -------------------------------------------------------------------------
    def audit_wiki_technician(self, wikitext: str) -> WikiTechnicianAuditResult:
        """Checks for broken templates, infobox keys, syntax balance, and category formatting."""
        errors: List[str] = []
        warnings: List[str] = []
        mangled_wikilinks: List[str] = []
        raw_english_redlinks: List[str] = []
        score = 100

        # 1. Broken SHORTDESC or raw Short description
        has_broken_shortdesc = False
        if re.search(r"SHORTDESC\s*:", wikitext, flags=re.IGNORECASE) or re.search(
            r"\{\{\s*short description", wikitext, flags=re.IGNORECASE
        ):
            has_broken_shortdesc = True
            errors.append("Ditemukan template {{Short description}} atau SHORTDESC yang merusak tampilan id.wiki.")
            score -= 30
        # 2. Stripped metadata templates present
        has_stripped_metadata_templates = False
        for tmpl in STRIP_METADATA_TEMPLATES:
            escaped_tmpl = re.escape(tmpl)
            pattern = r"\{\{\s*" + escaped_tmpl + r"\b"
            if re.search(pattern, wikitext, flags=re.IGNORECASE):
                has_stripped_metadata_templates = True
                warnings.append(f"Template metadata en.wiki '{{{{{tmpl}}}}}' belum dibersihkan.")
                score -= 10
        # 2b. Mangled Wikilinks and Raw English Red Links Audit
        for pat, desc in MANGLED_WIKILINK_PATTERNS:
            for match in pat.finditer(wikitext):
                link_str = match.group(0)
                mangled_wikilinks.append(link_str)
                errors.append(f"{desc}: '{link_str}'")
                score -= 20

        for pat, desc in RAW_ENGLISH_REDLINK_PATTERNS:
            for match in pat.finditer(wikitext):
                link_str = match.group(0)
                raw_english_redlinks.append(link_str)
                errors.append(f"{desc}: '{link_str}'")
                score -= 15


        # 3. Infobox parameters check
        # Check if infobox contains translated Indonesian keys that cause Lua unknown parameter errors
        unknown_infobox_keys: List[str] = []
        # Find infobox blocks
        for match in re.finditer(r"\{\{\s*(?:Infobox|Kotak info)\s+([a-zA-Z0-9_\s]+)", wikitext, flags=re.IGNORECASE):
            # Extract infobox content
            start_pos = match.start()
            depth = 0
            end_pos = start_pos
            for i in range(start_pos, len(wikitext)):
                if wikitext.startswith("{{", i):
                    depth += 1
                elif wikitext.startswith("}}", i):
                    depth -= 1
                    if depth == 0:
                        end_pos = i + 2
                        break

            infobox_body = wikitext[start_pos:end_pos]
            for key in INDONESIAN_TO_ENGLISH_INFOBOX_KEYS:
                # Look for | key =
                key_pattern = rf"\|\s*{re.escape(key)}\s*="
                if re.search(key_pattern, infobox_body, flags=re.IGNORECASE):
                    unknown_infobox_keys.append(key)

        if unknown_infobox_keys:
            score -= min(25, len(unknown_infobox_keys) * 5)
            warnings.append(
                f"Infobox menggunakan kunci bahasa Indonesia non-kanonik: {', '.join(set(unknown_infobox_keys))}."
            )

        # 4. Syntax Balance Issues
        syntax_issues = self.syntax_balancer.check_balance(wikitext)
        syntax_balance_issues = [
            i for i in syntax_issues if i.get("severity") == "error"
        ]
        if syntax_balance_issues:
            score -= min(30, len(syntax_balance_issues) * 10)
            errors.append(f"Terdapat {len(syntax_balance_issues)} masalah sintaks tidak seimbang (bracket/ref/tabel).")

        # 5. Categories check
        # Search for categories that are neither commented out nor standard
        masked_for_cats = re.sub(r"<!--[\s\S]*?-->", "", wikitext)
        uncommented_cats = re.findall(
            r"\[\[\s*(?:Category|Kategori)\s*:\s*([^\]|]+)(?:\|[^\]]*)?\]\]",
            masked_for_cats,
            flags=re.IGNORECASE,
        )

        has_uncommented_red_categories = False
        uncommented_categories: List[str] = []
        for cat in uncommented_cats:
            cat_clean = cat.strip()
            # If category uses English "Category:" instead of "Kategori:", flag warning
            if re.search(rf"\[\[\s*Category\s*:\s*{re.escape(cat_clean)}", masked_for_cats, flags=re.IGNORECASE):
                warnings.append(f"Kategori masih menggunakan awalan bahasa Inggris 'Category:{cat_clean}'.")
                score -= 5
            uncommented_categories.append(cat_clean)

        # 6. Quote Box & Pull Quote Integrity Check
        quote_boxes = list(re.finditer(r"\{\{\s*(?:Quote[ _]box|Kotak[ _]kutipan)\b", wikitext, re.IGNORECASE))
        for qb in quote_boxes:
            qb_snippet = wikitext[qb.start() : qb.start() + 800]
            has_quote = bool(
                re.search(r"\|\s*(?:quote|kutipan)\s*=\s*\S+", qb_snippet, re.IGNORECASE)
                or re.search(r"\{\{\s*(?:Quote[ _]box|Kotak[ _]kutipan)\s*\|\s*[^|=]+[|=]", qb_snippet, re.IGNORECASE)
            )
            if not has_quote:
                warnings.append("Ditemukan template {{Quote box}} tanpa parameter kutipan yang jelas.")
                score -= 5
            has_source = bool(re.search(r"\|\s*(?:source|sumber)\s*=\s*\S+", qb_snippet, re.IGNORECASE))
            if not has_source:
                warnings.append("Template {{Quote box}} tidak menyertakan parameter sumber (|source=).")
                score -= 3

        score = max(0, min(100, score))
        return WikiTechnicianAuditResult(
            has_broken_shortdesc=has_broken_shortdesc,
            has_stripped_metadata_templates=has_stripped_metadata_templates,
            has_uncommented_red_categories=has_uncommented_red_categories,
            score=score,
            unknown_infobox_keys=list(set(unknown_infobox_keys)),
            syntax_balance_issues=syntax_balance_issues,
            uncommented_categories=uncommented_categories,
            mangled_wikilinks=mangled_wikilinks,
            raw_english_redlinks=raw_english_redlinks,
            errors=errors,
            warnings=warnings,
        )

    # -------------------------------------------------------------------------
    # Main Pipeline: audit()
    # -------------------------------------------------------------------------
    def audit(
        self,
        wikitext: str,
        talk_wikitext: Optional[str] = None,
        title: Optional[str] = None,
        source_wikitext: Optional[str] = None,
        topic: Optional[str] = None,
    ) -> QAAuditReport:
        """
        Runs the 4-Layer Editorial QA Audit on final wikitext and produces a comprehensive report.
        """
        layer1 = self.audit_drafter(wikitext)
        layer2 = self.audit_linguistics(wikitext)
        layer3 = self.audit_wiki_technician(wikitext)

        # Critical errors: technician errors or extreme linguistic/structural failure
        critical_errors: List[str] = []
        critical_errors.extend(layer3.errors)
        factual = (
            self.factual_auditor.audit(source_wikitext, wikitext, topic=topic)
            if source_wikitext is not None
            else None
        )
        if factual and not factual.passed:
            critical_errors.extend(factual.warnings)

        if layer1.word_count < 30:
            critical_errors.append("Panjang artikel tidak memadai untuk draf ensiklopedis (< 30 kata).")

        if layer3.has_broken_shortdesc:
            critical_errors.append("Templat Short description rusak terdeteksi di wikitext.")

        # Weighted overall score:
        # Layer 1 (Drafter): 25%
        # Layer 2 (Linguistic): 45%
        # Layer 3 (Technician): 30%
        overall_score = int(0.25 * layer1.score + 0.45 * layer2.score + 0.30 * layer3.score)

        if critical_errors:
            overall_score = min(overall_score, 65)

        # Determine Grade
        if overall_score >= 95:
            grade = "A++"
        elif overall_score >= 90:
            grade = "A+"
        elif overall_score >= 80:
            grade = "A"
        elif overall_score >= 70:
            grade = "B"
        elif overall_score >= 60:
            grade = "C"
        else:
            grade = "F"

        # Approval logic: Score >= 80 and no critical errors
        approved = (overall_score >= 80) and (len(critical_errors) == 0)

        # Collect consolidated recommendations
        recommendations: List[str] = []
        if not layer1.has_lead:
            recommendations.append("Tambahkan paragraf pembuka (lead paragraph) sebelum bagian pertama.")
        if layer2.calque_count > 0:
            recommendations.append(f"Tinjau {layer2.calque_count} temuan bahasa terhadap sumber sebelum menyunting.")
        if layer3.unknown_infobox_keys:
            recommendations.append("Kembalikan parameter kotak info ke nama bahasa Inggris kanonik.")
        if layer3.syntax_balance_issues:
            recommendations.append("Perbaiki ketidakseimbangan markup kurung atau tag referensi.")

        all_warnings = layer1.warnings + layer2.warnings + layer3.warnings
        if factual:
            all_warnings.extend(factual.warnings)

        return QAAuditReport(
            overall_score=overall_score,
            grade=grade,
            approved=approved,
            title=title,
            layer1_drafter=layer1,
            layer2_linguistic=layer2,
            layer3_technician=layer3,
            critical_errors=critical_errors,
            warnings=all_warnings,
            recommendations=recommendations,
            factual_consistency=factual,
        )


default_qa_pipeline = EditorialQAPipeline()
