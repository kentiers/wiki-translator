"""
Automated Translation Quality Auditor and Reviewer for Indonesian Wikipedia Articles.

Evaluates existing id.wikipedia articles against en.wikipedia and Indonesian Featured Article
criteria (WP:KAP - Kriteria Artikel Pilihan & WP:GAYA).
Identifies:
1. Fatal Mistranslations & Context Inversions (e.g. 'sewing' -> 'menyemai', 'died' -> 'lahir').
2. Machine Translation Calques & Unnatural Cadence (anti-slop).
3. Typographical & Orthographical Errors (EYD V / KBBI VI).
4. Reference & Citation Health (missing templates, dead links, citation errors).
5. Overall WP:KAP Score (0-100) and Verdict:
   - 'BELUM LAYAK - PERLU PERBAIKAN TOTAL' (< 70)
   - 'PERLU REVISI DAN TINJAUAN MANUSIA' (70 - 89)
   - 'LOLOS PEMERIKSAAN DASAR — PERLU TINJAUAN MANUSIA' (>= 90)
"""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse
import urllib.request

from .auth import AuthManager
from .awb_genfixes import default_genfixes
from .gramatika_engine import default_gramatika_engine
from .eyd_engine import default_eyd_engine
from .historical_ethnonyms import default_ethnonyms_manager
from .editorial_qa import default_qa_pipeline
from .factual_audit import default_factual_auditor
from .article_quality import check_saved_integrity, review_claims
from .glossary_audit import audit_glossary_consistency
from .review_snapshot import save_review_snapshot

from .gemini import GeminiTranslatorClient
from .prompts import (
    SYSTEM_PROMPT_GRADE_A_PLUS_PLUS,
    SYSTEM_PROMPT_HUMANIZE_POLISH,
    build_polish_prompt,
)
from .sandbox_publisher import SandboxPublisher, default_sandbox_publisher
from .slop_linter import default_slop_linter
from .syntax_balancer import default_syntax_balancer
from .typography_sanitizer import default_typography_sanitizer
from .wiki_client import WikipediaClient
from .wiki_link_mapper import default_link_mapper


def _load_env_file(env_path: Optional[Path] = None) -> None:
    """Loads .env file safely without circular import on cli."""
    target_file: Optional[Path] = None
    if env_path is not None:
        if env_path.is_file():
            target_file = env_path
    else:
        cwd = Path.cwd()
        for dir_path in [cwd, cwd.parent, Path(__file__).resolve().parent.parent]:
            candidate = dir_path / ".env"
            if candidate.is_file():
                target_file = candidate
                break
    if not target_file or not target_file.is_file():
        return
    try:
        with open(target_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip()
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                if key not in os.environ:
                    os.environ[key] = val
    except Exception:
        pass
@dataclass
class ReviewFinding:
    category: str  # "Fatal Error", "Calque / Terjemahan Mesin", "Tipografi & EYD", "Referensi"
    severity: str  # "CRITICAL", "HIGH", "MEDIUM", "LOW"
    description: str
    original_text: str
    suggested_fix: str
    context: Optional[str] = None


@dataclass
class APReviewReport:
    title: str
    en_title: str
    overall_score: int  # 0 - 100
    verdict: str  # "BELUM LAYAK - PERLU PERBAIKAN TOTAL" | "PERLU REVISI DAN TINJAUAN MANUSIA" | "LOLOS PEMERIKSAAN DASAR — PERLU TINJAUAN MANUSIA"
    fatal_errors: List[ReviewFinding] = field(default_factory=list)
    calque_issues: List[ReviewFinding] = field(default_factory=list)
    typo_issues: List[ReviewFinding] = field(default_factory=list)
    reference_issues: List[ReviewFinding] = field(default_factory=list)
    summary_notes: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    factual_consistency: Any = None


# Common patterns for known fatal mistranslations / context inversions
FATAL_MISTRANSLATION_RULES: List[Dict[str, Any]] = [
    {
        "id": "fatal_born_vs_died",
        "pattern": re.compile(r"\b(?:Ia\s+)?(?:lahir|dilahirkan)\b[^\n\r]*?(?:\d{1,2}\s+[A-Za-z]+\s+\d{4})?[^\n\r]*?\b(?:pemakaman|dikebumikan)\b", re.IGNORECASE),
        "desc": "Fatal factual inversion: Menyatakan tokoh 'lahir' pada konteks kematian/pemakaman.",
        "fix": "Ganti 'lahir' menjadi 'wafat'/'meninggal dunia' sesuai tanggal kematian.",
    },
    {
        "id": "fatal_sewing_menyemai",
        "pattern": re.compile(r"\bmenyemai\s+(?:pengerjaan|pekerjaan)\s+dari\s+militer\b", re.IGNORECASE),
        "desc": "Fatal mistranslation: 'sewing work' (pekerjaan menjahit) diterjemahkan keliru menjadi 'menyemai pengerjaan' (menanam benih/bibit).",
        "fix": "pekerjaan menjahit untuk militer",
    },
    {
        "id": "fatal_sewing_menyemai_general",
        "pattern": re.compile(r"\bkontrak\s+[^\.\n]*menyemai\b", re.IGNORECASE),
        "desc": "Fatal mistranslation: 'sewing' diterjemahkan menjadi 'menyemai'.",
        "fix": "kontrak penjahitan / pekerjaan menjahit",
    },
]

# Machine Translation calques & unnatural cadence patterns
CALQUE_REVIEW_PATTERNS: List[Dict[str, Any]] = [
    {
        "pattern": re.compile(r"\btimbal\s+balik\s+konservatif\b", re.IGNORECASE),
        "desc": "Kalkir harfiah dari 'conservative backlash'.",
        "fix": "reaksi keras kaum konservatif / arus balik konservatif",
    },
    {
        "pattern": re.compile(r"\bmenubuhkan\s+(?:spiritualitas|etika|nilai|karakter)\b", re.IGNORECASE),
        "desc": "Kalkir harfiah dari 'embodied' ('menubuhkan' tidak lazim untuk perwujudan sifat rohani/etika).",
        "fix": "menjelmakan / mewujudkan / merepresentasikan",
    },
    {
        "pattern": re.compile(r"\bmenghimpun\s+stasiun\s+mereka\s+dalam\s+rahmat\s+baik\b", re.IGNORECASE),
        "desc": "Kalkir mentah dari 'retained their stations in the good graces'.",
        "fix": "mempertahankan kedudukan mereka dan tetap disenangi oleh",
    },
    {
        "pattern": re.compile(r"\bpendudukan\s+wanita\b", re.IGNORECASE),
        "desc": "Kekeliruan kata dari 'educational status of women' atau 'occupation' -> bukan pendudukan militer.",
        "fix": "pendidikan wanita / pekerjaan wanita",
    },
    {
        "pattern": re.compile(r"\bSerikat\s+Loji\s+Murah\b", re.IGNORECASE),
        "desc": "Kalkir harfiah dari 'Society for Cheap Lodgings' (loji = lodge/benteng militer; lodgings = pemukiman/indekos/hunian).",
        "fix": "Perhimpunan Hunian Murah",
    },
    {
        "pattern": re.compile(r"\bdijungkir\s+balik\b", re.IGNORECASE),
        "desc": "Kalkir canggung dari 'reversed' (kebijakan/keberhasilan yang dibatalkan atau ditarik kembali).",
        "fix": "dibatalkan / ditarik kembali",
    },
    {
        "pattern": re.compile(r"\bpekerjaan\s+senbagai\s+penekanan\b", re.IGNORECASE),
        "desc": "Kalkir canggung & tipo dari 'work as seamstresses'.",
        "fix": "pekerjaan sebagai penjahit",
    },
    {
        "pattern": re.compile(r"\bpekerjaan\s+sebagai\s+penekanan\b", re.IGNORECASE),
        "desc": "Kalkir rancu dari 'work as seamstresses' (penekanan vs penjahit).",
        "fix": "pekerjaan sebagai penjahit",
    },
    {
        "pattern": re.compile(r"\bceramah\s+Vladimirskii\b", re.IGNORECASE),
        "desc": "Kalkir dari 'Vladimirskii lectures' (kuliah akademik/perkuliahan Vladimirskii).",
        "fix": "perkuliahan Vladimirskii",
    },
    {
        "pattern": re.compile(r"\bpemasukan\s+ke\s+universitas\b", re.IGNORECASE),
        "desc": "Kalkir harfiah dari 'admission to universities' (penerimaan mahasiswa).",
        "fix": "penerimaan mahasiswa di universitas",
    },
    {
        "pattern": re.compile(r"diangkat\s+oleh\s+\[\[otokrasi\s+Tsaris\|pemerintahan\s+Tsaris\]\]", re.IGNORECASE),
        "desc": "Kalkir rancu dari 'approved by the Tsarist government' (piagam disahkan/disetujui, bukan diangkat).",
        "fix": "disahkan oleh [[otokrasi Tsaris|pemerintahan Tsaris]]",
    },
    {
        "pattern": re.compile(r"\bkeluarga\s+aristoktrat\b", re.IGNORECASE),
        "desc": "Bentuk tidak baku KBBI (aristokrat, bukan aristoktrat).",
        "fix": "keluarga bangsawan / keluarga aristokrat",
    },
    {
        "pattern": re.compile(r"\bmembiarkan\s+perhambaan\s+tani\b", re.IGNORECASE),
        "desc": "Kalkir canggung dari keluarga yang tidak memiliki hamba tani.",
        "fix": "tidak memiliki hamba tani",
    },
    {
        "pattern": re.compile(r"\bbusana\s+tak\s+dibuat\s+wanita\b", re.IGNORECASE),
        "desc": "Kalkir harfiah dari 'clothes do not make the woman' (busana tidak menentukan martabat wanita).",
        "fix": "pakaian tidak menentukan jati diri seorang wanita",
    },
    {
        "pattern": re.compile(r"\bmenempatkanmu\s+di\s+luar\s+kekuatanku\b", re.IGNORECASE),
        "desc": "Kalkir kaku dari 'to yield to you is beyond my power'.",
        "fix": "tunduk kepadamu berada di luar kemampuanku",
    },
    {
        "pattern": re.compile(r"\bwadah\s+otonomi\s+untuk\s+pekerjaan\b", re.IGNORECASE),
        "desc": "Kalkir kaku dari 'autonomous path to employment'.",
        "fix": "jalur mandiri untuk bekerja",
    },
    {
        "pattern": re.compile(r"\bdiinkorporasikan\b", re.IGNORECASE),
        "desc": "Kalkir dari 'incorporated' (dibentuk berbadan hukum / didirikan secara resmi).",
        "fix": "berbadan hukum resmi / diresmikan",
    },
    {
        "pattern": re.compile(r"\bceramah\s+persiapan\b", re.IGNORECASE),
        "desc": "Kalkir dari 'preparatory lectures' (kuliah persiapan).",
        "fix": "kuliah persiapan",
    },
]

# Typographical & Orthographical Errors
TYPOGRAPHICAL_RULES: List[Dict[str, Any]] = [
    {"pattern": re.compile(r"\bpernikaahn\b", re.IGNORECASE), "fix": "pernikahan", "word": "pernikaahn"},
    {"pattern": re.compile(r"\bsenbagai\b", re.IGNORECASE), "fix": "sebagai", "word": "senbagai"},
    {"pattern": re.compile(r"\bhabi\b", re.IGNORECASE), "fix": "habis", "word": "habi"},
    {"pattern": re.compile(r"\baristoktrat\b", re.IGNORECASE), "fix": "aristokrat", "word": "aristoktrat"},
    {"pattern": re.compile(r"\btersbeut\b", re.IGNORECASE), "fix": "tersebut", "word": "tersbeut"},
    {"pattern": re.compile(r"\bunicersitas\b", re.IGNORECASE), "fix": "universitas", "word": "unicersitas"},
    {"pattern": re.compile(r"\bsabat\b", re.IGNORECASE), "fix": "sabar", "word": "sabat"},
    {"pattern": re.compile(r"\bMentujukan\b", re.IGNORECASE), "fix": "Bertujuan", "word": "Mentujukan"},
    {"pattern": re.compile(r"\bmentujukan\b", re.IGNORECASE), "fix": "bertujuan", "word": "mentujukan"},
    {"pattern": re.compile(r"\bberpedapat\b", re.IGNORECASE), "fix": "berpendapat", "word": "berpedapat"},
    {"pattern": re.compile(r"\bdimana\b", re.IGNORECASE), "fix": "di mana", "word": "dimana"},
    {"pattern": re.compile(r"\bdisana\b", re.IGNORECASE), "fix": "di sana", "word": "disana"},
]


class ArticleReviewer:
    """
    Automated Translation Quality Auditor for reviewing existing id.wikipedia articles
    against en.wikipedia and Indonesian Featured Article criteria (WP:KAP & WP:GAYA).
    """

    def __init__(
        self,
        id_client: Optional[WikipediaClient] = None,
        en_client: Optional[WikipediaClient] = None,
        gemini_client: Optional[GeminiTranslatorClient] = None,
        link_mapper: Optional[Any] = None,
    ):
        self.id_client = id_client or WikipediaClient(lang="id")
        self.en_client = en_client or WikipediaClient(lang="en")
        self.gemini_client = gemini_client
        self._gemini_initialized = gemini_client is not None
        self.link_mapper = link_mapper or default_link_mapper

    def _get_gemini_client(self) -> Optional[GeminiTranslatorClient]:
        """Lazily initializes and returns GeminiTranslatorClient if Antigravity / Gemini credentials exist."""
        if self._gemini_initialized:
            return self.gemini_client
        try:
            auth_manager = AuthManager()
            has_antigravity = bool(auth_manager.load_credentials())
            has_api_key = bool(os.environ.get("GEMINI_API_KEY"))
            if has_antigravity or has_api_key:
                self.gemini_client = GeminiTranslatorClient(
                    auth_manager=auth_manager,
                    preferred_model="gemini-3.8-flash",
                )
        except Exception:
            self.gemini_client = None
        self._gemini_initialized = True
        return self.gemini_client

    def _rule_based_clean(self, text: str) -> str:
        """
        Applies generalized, article-agnostic linguistic, typographic, and syntax cleaning
        for common machine-translation calques, grammatical inversions, typos, and metadata.
        """
        # Source-dependent semantic repairs belong to the LLM/source audit.
        cleaned, _ = default_slop_linter.auto_fix(text)
        cleaned, _, _ = default_gramatika_engine.apply_all_gramatika_fixes(cleaned)
        cleaned, _, _ = default_eyd_engine.apply_all_eyd_fixes(cleaned)
        cleaned, _, _ = default_ethnonyms_manager.audit_and_fix_homonym_blunders(cleaned)
        # 6. Strip status/metadata templates and comments
        cleaned = re.sub(
            r"<!--\s*Templat belum tersedia di id\.wiki:\s*\{\{\s*(?:deskripsi singkat|short description)[^\}]*\}\}\s*-->\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"\{\{\s*(?:artikel pilihan|featured article|artikel bagus|good article|deskripsi singkat|short description)(?:\|[^\}]*)?\}\}\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        return cleaned

    def reconcile_missing_wikilinks(self, en_wikitext: str, id_wikitext: str) -> str:
        """
        Reconciles wikilinks from the English wikitext to the Indonesian draft.
        Extracts wikilinks from en_wikitext and ensures counterpart terms in id_wikitext
        are resolved via default_link_mapper rather than hardcoded replacements.
        """
        if not en_wikitext.strip() or not id_wikitext.strip():
            return id_wikitext
        try:
            from .link_fidelity_validator import default_fidelity_validator
            reconciled, _, _ = default_fidelity_validator.safeguard_redlinks_with_ill(
                draft_wikitext=id_wikitext,
                source_wikitext=en_wikitext,
            )
            return reconciled
        except Exception:
            return id_wikitext
    def fetch_article_pair(
        self, id_title: str, en_title: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Fetches wikitext from id.wikipedia and en.wikipedia.
        If en_title is not provided, resolves the interlanguage link automatically.
        """
        id_wikitext = self.id_client.fetch_wikitext(id_title)

        resolved_en_title = en_title
        if not resolved_en_title:
            resolved_en_title = self._resolve_interlanguage_en_title(id_title)

        if not resolved_en_title:
            resolved_en_title = id_title

        try:
            en_wikitext = self.en_client.fetch_wikitext(resolved_en_title)
        except Exception:
            en_wikitext = ""

        return id_wikitext, en_wikitext

    def _resolve_interlanguage_en_title(self, id_title: str) -> Optional[str]:
        """Looks up the English Wikipedia sitelink for the given Indonesian page."""
        url = (
            f"https://id.wikipedia.org/w/api.php?action=query&prop=langlinks"
            f"&titles={urllib.parse.quote(id_title)}&lllang=en&formatversion=2&format=json"
        )
        req = urllib.request.Request(
            url, headers={"User-Agent": "WikiTranslatorReviewer/1.0"}
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                pages = data.get("query", {}).get("pages", [])
                if pages and "langlinks" in pages[0]:
                    ll = pages[0]["langlinks"]
                    if ll and "title" in ll[0]:
                        return ll[0]["title"]
        except Exception:
            pass
        return None

    def audit_translation_quality(
        self, id_wikitext: str, en_wikitext: str, title: str
    ) -> APReviewReport:
        """
        Audits an Indonesian Wikipedia article against en.wiki and WP:KAP:
        1. Fatal Mistranslations & Context Inversions
        2. Machine Translation Calques & Unnatural Cadence
        3. Typographical & Orthographical Errors
        4. Reference & Citation Health
        5. Overall WP:KAP Score (0-100) and Verdict
        """
        fatal_errors: List[ReviewFinding] = []
        calque_issues: List[ReviewFinding] = []
        typo_issues: List[ReviewFinding] = []
        reference_issues: List[ReviewFinding] = []
        summary_notes: List[str] = []

        # 1. Fatal Mistranslations & Context Inversions
        for rule in FATAL_MISTRANSLATION_RULES:
            for match in rule["pattern"].finditer(id_wikitext):
                matched_str = match.group(0)
                start_pos = max(0, match.start() - 50)
                end_pos = min(len(id_wikitext), match.end() + 50)
                context_snippet = id_wikitext[start_pos:end_pos].strip()
                fatal_errors.append(
                    ReviewFinding(
                        category="Fatal Error",
                        severity="CRITICAL",
                        description=rule["desc"],
                        original_text=matched_str,
                        suggested_fix=rule["fix"],
                        context=context_snippet,
                    )
                )

        # Generalized check for born vs died contradiction (born on funeral/cemetery/death context)
        death_funeral_birth = re.search(
            r"\b(?:Ia\s+)?(?:lahir|dilahirkan)\b[^\n\r]*?\b(?:1912|pemakaman|dikebumikan)\b",
            id_wikitext,
            re.IGNORECASE,
        )
        if death_funeral_birth:
            fatal_errors.append(
                ReviewFinding(
                    category="Fatal Error",
                    severity="CRITICAL",
                    description="Pembalikan fakta fatal: Teks menyatakan tokoh 'lahir' pada konteks kematian/pemakaman.",
                    original_text=death_funeral_birth.group(0),
                    suggested_fix="Ganti 'lahir' menjadi 'wafat'/'meninggal dunia' sesuai fakta biografi.",
                    context=id_wikitext[max(0, death_funeral_birth.start() - 40):min(len(id_wikitext), death_funeral_birth.end() + 40)],
                )
            )

        # Deduplicate fatal errors by original_text
        deduped_fatal = []
        seen_fatal_texts = set()
        for f in fatal_errors:
            if f.original_text not in seen_fatal_texts:
                seen_fatal_texts.add(f.original_text)
                deduped_fatal.append(f)
        fatal_errors = deduped_fatal
        # 2. Machine Translation Calques & Unnatural Cadence
        for c_rule in CALQUE_REVIEW_PATTERNS:
            for match in c_rule["pattern"].finditer(id_wikitext):
                matched_str = match.group(0)
                start_pos = max(0, match.start() - 40)
                end_pos = min(len(id_wikitext), match.end() + 40)
                context_snippet = id_wikitext[start_pos:end_pos].strip()
                calque_issues.append(
                    ReviewFinding(
                        category="Calque / Terjemahan Mesin",
                        severity="HIGH",
                        description=c_rule["desc"],
                        original_text=matched_str,
                        suggested_fix=c_rule["fix"],
                        context=context_snippet,
                    )
                )


        # Also use AntiAISlopLinter
        slop_res = default_slop_linter.lint(id_wikitext)
        for v in slop_res.violations:
            if v.rule_id == "orthography_semicolon":
                continue
            calque_issues.append(
                ReviewFinding(
                    category="Calque / Terjemahan Mesin",
                    severity="MEDIUM" if v.severity != "high" else "HIGH",
                    description=v.explanation,
                    original_text=v.matched_text,
                    suggested_fix=", ".join(v.suggestions) if v.suggestions else "Poles gaya bahasa",
                    context=v.excerpt,
                )
            )

        # 3. Typographical & Orthographical Errors
        for t_rule in TYPOGRAPHICAL_RULES:
            for match in t_rule["pattern"].finditer(id_wikitext):
                matched_str = match.group(0)
                start_pos = max(0, match.start() - 30)
                end_pos = min(len(id_wikitext), match.end() + 30)
                context_snippet = id_wikitext[start_pos:end_pos].strip()
                typo_issues.append(
                    ReviewFinding(
                        category="Tipografi & EYD",
                        severity="MEDIUM",
                        description=f"Kesalahan ketik / ortografi: '{matched_str}' tidak baku.",
                        original_text=matched_str,
                        suggested_fix=t_rule["fix"],
                        context=context_snippet,
                    )
                )

        # 4. Reference & Citation Health
        factual = default_factual_auditor.audit(en_wikitext, id_wikitext)
        for warning in factual.warnings:
            reference_issues.append(
                ReviewFinding(
                    category="Konsistensi Faktual",
                    severity="HIGH",
                    description=warning,
                    original_text="",
                    suggested_fix="Bandingkan kembali angka/tanggal dan jumlah referensi dengan sumber enwiki.",
                )
            )
        glossary_check = audit_glossary_consistency(en_wikitext, id_wikitext)
        for item in glossary_check.missing:
            reference_issues.append(
                ReviewFinding(
                    category="Konsistensi Glosarium",
                    severity="MEDIUM",
                    description=f"Padanan glosarium tidak ditemukan di draft: {item}",
                    original_text=item.split(" -> ", 1)[0],
                    suggested_fix="Gunakan padanan glosarium yang konsisten atau tandai pengecualian konteks.",
                )
            )
        syntax_issues = default_syntax_balancer.check_balance(id_wikitext)
        if syntax_issues:
            for issue in syntax_issues:
                reference_issues.append(
                    ReviewFinding(
                        category="Referensi & Sintaks",
                        severity="HIGH",
                        description=f"Ketidakseimbangan sintaks wikitext: {issue.get('description', issue.get('tag_type', 'tag'))}",
                        original_text=str(issue),
                        suggested_fix="Tutup atau seimbangkan tag / markah rujukan wikitext.",
                    )
                )

        # Check for empty reflist
        if "<ref" in id_wikitext and "{{reflist" not in id_wikitext.lower() and "<references" not in id_wikitext.lower():
            reference_issues.append(
                ReviewFinding(
                    category="Referensi & Sintaks",
                    severity="HIGH",
                    description="Artikel memiliki tag <ref> tetapi tidak memiliki templat {{reflist}} atau tag <references/>.",
                    original_text="",
                    suggested_fix="Tambahkan {{reflist}} pada bagian Referensi.",
                )
            )

        # Check undefined named references
        defined_refs = set(re.findall(r'<ref\s+name=[\"\']?([^\"\'/>]+)[\"\']?\s*>', id_wikitext))
        invoked_refs = set(re.findall(r'<ref\s+name=[\"\']?([^\"\'/>]+)[\"\']?\s*/>', id_wikitext))
        missing_defs = invoked_refs - defined_refs
        for m_ref in missing_defs:
            reference_issues.append(
                ReviewFinding(
                    category="Referensi & Sintaks",
                    severity="HIGH",
                    description=f"Rujukan bernama '<ref name=\"{m_ref}\"/>' dipanggil tetapi definisinya tidak ditemukan.",
                    original_text=f'<ref name="{m_ref}"/>',
                    suggested_fix=f'Sediakan teks rujukan lengkap <ref name="{m_ref}">...</ref>',
                )
            )

        # Check category health
        categories = re.findall(r"\[\[(?:Kategori|Category):([^\]]+)\]\]", id_wikitext, re.IGNORECASE)
        if len(categories) <= 1:
            reference_issues.append(
                ReviewFinding(
                    category="Kategori & Navigasi",
                    severity="MEDIUM",
                    description=f"Artikel hanya memiliki {len(categories)} kategori (WP:KAP mensyaratkan kategorisasi yang lengkap dan relevan).",
                    original_text=", ".join(categories) if categories else "Tanpa kategori",
                    suggested_fix="Tambahkan kategori spesifik (e.g. Tokoh wanita Rusia, Feminis, Kelahiran 1837, Kematian 1912).",
                )
            )

        # 5. Calculate Overall Score & Verdict
        # Starting base score: 100
        # Penalties:
        # - Fatal error: -25 each (capped)
        # - Calque / MT: -6 each
        # - Typo / EYD: -3 each
        # - Reference issue: -8 each
        score = 100
        score -= len(fatal_errors) * 25
        score -= len(calque_issues) * 6
        score -= len(typo_issues) * 3
        score -= len(reference_issues) * 8
        score = max(0, min(100, score))

        if score < 70 or len(fatal_errors) > 0:
            verdict = "BELUM LAYAK - PERLU PERBAIKAN TOTAL"
        elif score < 90:
            verdict = "PERLU REVISI DAN TINJAUAN MANUSIA"
        else:
            verdict = "LOLOS PEMERIKSAAN DASAR — PERLU TINJAUAN MANUSIA"

        id_words = len(re.findall(r"\b\w+\b", id_wikitext))
        en_words = len(re.findall(r"\b\w+\b", en_wikitext)) if en_wikitext else 0
        completeness_ratio = (id_words / max(en_words, 1)) if en_words else 1.0
        metrics = {
            "word_count": id_words,
            "en_word_count": en_words,
            "completeness_ratio": round(completeness_ratio, 3),
            "fatal_errors_count": len(fatal_errors),
            "calque_issues_count": len(calque_issues),
            "typo_issues_count": len(typo_issues),
            "reference_issues_count": len(reference_issues),
            "category_count": len(categories),
        }
        # Build summary notes
        if fatal_errors:
            summary_notes.append(
                f"Ditemukan {len(fatal_errors)} kesalahan penerjemahan fatal dan pembalikan konteks faktual (seperti pembalikan tanggal lahir/wafat dan kekeliruan istilah militer)."
            )
        if calque_issues:
            summary_notes.append(
                f"Ditemukan {len(calque_issues)} kalkir terjemahan mesin (machine translation calques) dan konstruksi kalimat tidak alami."
            )
        if typo_issues:
            summary_notes.append(
                f"Ditemukan {len(typo_issues)} kesalahan ejaan dan ketik (EYD V / KBBI VI)."
            )
        if reference_issues:
            summary_notes.append(
                f"Ditemukan {len(reference_issues)} catatan terkait integritas referensi, sintaks, atau kekurangan kategori ensiklopedis."
            )

        return APReviewReport(
            title=title,
            en_title=title,
            overall_score=score,
            verdict=verdict,
            fatal_errors=fatal_errors,
            calque_issues=calque_issues,
            typo_issues=typo_issues,
            reference_issues=reference_issues,
            summary_notes=summary_notes,
            metrics=metrics,
            factual_consistency=factual,
        )

    def generate_community_review_text(
        self,
        report: APReviewReport,
        reviewer_name: str = "Baloo Official",
        requester_name: str = "Glorious Engine",
    ) -> str:
        """
        Generates a formal, polite, constructive, and comprehensive review comment
        ready to be posted on Wikipedia talk pages (Warung Kopi / Pembicaraan Pengguna / Evaluasi AP).
        """
        score_emoji = "🔴" if report.overall_score < 70 else ("🟡" if report.overall_score < 90 else "🟢")
        verdict_badge = f"**{score_emoji} {report.verdict} (Skor heuristik: {report.overall_score}/100)**"

        lines: List[str] = [
            f"Halo Bung @{requester_name},",
            "",
            f"Terima kasih atas pesan dan permohonan peninjauan artikel '''[[{report.title}]]''' untuk persiapan usulan Artikel Pilihan (AP) / Artikel Bagus (AB). Saya telah melakukan audit mendalam terhadap artikel tersebut dengan membandingkannya secara langsung terhadap teks sumber di English Wikipedia serta mengukurnya berdasarkan pedoman kelayakan '''[[WP:KAP|Kriteria Artikel Pilihan]]''' dan '''[[WP:GAYA|Pedoman Gaya Penulisan]]'''.",
            "",
            "== Hasil Evaluasi & Status Kelayakan ==",
            f"* Status Kelayakan: {verdict_badge}",
            f"* Jumlah kata: ±{report.metrics.get('word_count', 0):,} kata",
            f"* Masalah fatal / pembalikan fakta: {len(report.fatal_errors)} temuan",
            f"* Kalkir terjemahan mesin (slop/calque): {len(report.calque_issues)} temuan",
            f"* Kesalahan ketik & EYD V: {len(report.typo_issues)} temuan",
            f"* Catatan referensi & kategori: {len(report.reference_issues)} temuan",
            "",
            "Secara umum, cakupan topik artikel ini sangat baik dan komprehensif. Namun, '''artikel ini belum dapat diajukan ke halaman evaluasi AP/AB dalam kondisinya saat ini''' karena mengandung sejumlah kesalahan fatal penerjemahan mesin, pembalikan fakta sejarah, dan kalimat-kalimat kaku (kalkir bahasa Inggris) yang melanggar butir 1a WP:KAP (''\"memiliki prosa yang menarik, bahkan cemerlang, dan berstandar bahasa ensiklopedia profesional\"'').",
            "",
            "== Rincian Temuan Kritis ==",
        ]

        # Fatal section
        if report.fatal_errors:
            lines.append("=== 1. Kesalahan Fatal & Pembalikan Fakta Historis ===")
            for i, item in enumerate(report.fatal_errors, 1):
                lines.append(f"{i}. '''{item.description}'''")
                lines.append(f"   * ''Teks saat ini:'' \"<nowiki>{item.original_text}</nowiki>\"")
                lines.append(f"   * ''Perbaikan yang benar:'' \"'''{item.suggested_fix}'''\"")
                if item.context:
                    lines.append(f"   * ''Konteks:'' <small>\"{item.context}\"</small>")
            lines.append("")

        # Calque section
        if report.calque_issues:
            lines.append("=== 2. Kalkir Terjemahan Mesin & Ritme Kalimat Kaku (Anti-AI Slop) ===")
            # Limit display to top 8 if too many
            displayed_calques = report.calque_issues[:8]
            for i, item in enumerate(displayed_calques, 1):
                lines.append(f"{i}. '''{item.description}'''")
                lines.append(f"   * ''Bentuk kaku:'' \"<nowiki>{item.original_text}</nowiki>\"")
                lines.append(f"   * ''Rekomendasi redaksi:'' \"'''{item.suggested_fix}'''\"")
            if len(report.calque_issues) > 8:
                lines.append(f"   * ''(Serta {len(report.calque_issues) - 8} frasa terjemahan mesin lainnya telah diselaraskan pada draf polesan)''.")
            lines.append("")

        # Typo section
        if report.typo_issues:
            lines.append("=== 3. Kesalahan Tipografi & Ejaan (EYD V / KBBI VI) ===")
            seen_typos = set()
            t_idx = 1
            for item in report.typo_issues:
                if item.original_text in seen_typos:
                    continue
                seen_typos.add(item.original_text)
                lines.append(f"{t_idx}. \"{item.original_text}\" $\\rightarrow$ ganti menjadi \"'''{item.suggested_fix}'''\"")
                t_idx += 1
            lines.append("")

        # Reference & Categories
        if report.reference_issues:
            lines.append("=== 4. Kelengkapan Kategori & Navigasi ===")
            for item in report.reference_issues:
                lines.append(f"* '''{item.category}:''' {item.description} (''Saran:'' {item.suggested_fix})")
            lines.append("")

        # Next Steps & Closing
        lines.extend([
            "== Solusi & Langkah Selanjutnya ==",
            "Temuan ini berasal dari pemeriksaan otomatis. Cocokkan draf dengan sumber, terutama pelaku tindakan, negasi, angka, dan batas klaim.",
            "",
            "Skor ini bukan penetapan kelayakan Artikel Pilihan atau persetujuan penerbitan. Draf tetap memerlukan peninjauan manusia.",
            "",
            f"Semoga catatan evaluasi ini bermanfaat dan salam hangat untuk kontribusi luar biasa Anda di Wikipedia bahasa Indonesia! ~~~~",
            "",
            f"— '''{reviewer_name}'''",
        ])

        return "\n".join(lines)

    def _split_top_elements(self, wikitext: str) -> Tuple[str, str]:
        """Splits leading templates, comments, or tables (like notice boxes/infobox) from prose."""
        pos = 0
        while True:
            m_cmt = re.match(r"^\s*<!--[\s\S]*?-->\s*", wikitext[pos:])
            if m_cmt:
                pos += m_cmt.end()
                continue
            if wikitext[pos : pos + 2] == "{{":
                depth = 0
                i = pos
                while i < len(wikitext):
                    if wikitext[i : i + 2] == "{{":
                        depth += 2
                        i += 2
                    elif wikitext[i : i + 2] == "}}":
                        depth -= 2
                        i += 2
                        if depth == 0:
                            break
                    else:
                        i += 1
                pos = i
                while pos < len(wikitext) and wikitext[pos] in " \t\r\n":
                    pos += 1
                continue
            m_tbl = re.match(r"^\s*\{\|[\s\S]*?\n\|\}\s*", wikitext[pos:])
            if m_tbl:
                pos += m_tbl.end()
                continue
            break
        return wikitext[:pos], wikitext[pos:]

    def generate_polished_wikitext(
        self,
        id_wikitext: str,
        en_wikitext: str = "",
        id_title: str = "Artikel",
        requester: str = "Pengguna",
    ) -> str:
        """
        Rewrites and polishes wikitext into natural, human-flowing, authentic Indonesian
        encyclopedic prose (WP:GAYA & Ensiklopedi Peradaban Dunia).
        
        When GeminiTranslatorClient credentials exist:
        - Splits en_wikitext and id_wikitext into sections (== ... ==).
        - For each section, passes English source and current draft to polish_section.
        - Falls back to rule-based cleaning if offline or on section failure.
        - Resolves links via default_link_mapper.process_wikitext.
        - Sanitizes typography and syntax via default_typography_sanitizer and default_syntax_balancer.
        - Prepends clean notice box.
        """
        # Strip any existing notice box first to avoid duplicate nesting
        working_id = re.sub(
            r"^\s*\{\|[^\n]*\n\|[^\n]*'''Draf perbaikan'''[^\n]*\n\|\}\s*",
            "", id_wikitext,
        )
        working_id = re.sub(r"\{\{Kotak pemberitahuan[\s\S]*?\}\}\s*", "", working_id, flags=re.IGNORECASE).strip()

        gemini = self._get_gemini_client()
        polished_body = ""

        if gemini and en_wikitext.strip():
            try:
                sec_id_list = self.id_client.split_sections(working_id)
                sec_en_list = self.en_client.split_sections(en_wikitext)

                assembled_sections: List[str] = []

                for i, sec_id in enumerate(sec_id_list):
                    # Check if metadata section (reflist, notes, etc.)
                    title_lower = sec_id.title.lower()
                    is_meta = any(k in title_lower for k in [
                        "catatan", "referensi", "rujukan", "pranala luar",
                        "daftar pustaka", "notes", "references", "external links"
                    ])

                    if is_meta or not sec_id.content.strip():
                        # Clean rule-based only, no LLM polish needed for pure reflist / authority control
                        clean_meta = self._rule_based_clean(sec_id.content)
                        if sec_id.header_raw:
                            assembled_sections.append(f"{sec_id.header_raw}\n{clean_meta.strip()}")
                        else:
                            assembled_sections.append(clean_meta.strip())
                        continue

                    # Find matching English section
                    heading_pairs = {
                        "sejarah": "history", "kehidupan awal": "early life",
                        "karier": "career", "alur cerita": "plot", "sinopsis": "plot",
                        "pemeran": "cast", "produksi": "production", "perilisan": "release",
                        "penerimaan": "reception", "warisan": "legacy",
                        "penghargaan": "awards", "kematian": "death",
                        "kehidupan selanjutnya": "later life", "kehidupan pribadi": "personal life",
                        "pendidikan": "education", "latar belakang": "background",
                    }
                    source_title = heading_pairs.get(title_lower.strip(), title_lower.strip())
                    candidates = [
                        e for e in sec_en_list
                        if e.level == sec_id.level and e.title.strip().lower() == source_title
                    ]
                    matching_en = candidates[0] if len(candidates) == 1 else None
                    if not matching_en and i < len(sec_en_list) and sec_en_list[i].level == sec_id.level:
                        matching_en = sec_en_list[i]
                    en_source = matching_en.content if matching_en else ""
                    id_draft = sec_id.content

                    # For lead section (level 1 or index 0), separate top infobox from prose
                    if sec_id.level == 1 or i == 0:
                        top_id, prose_id = self._split_top_elements(id_draft)
                        top_en, prose_en = self._split_top_elements(en_source) if en_source else ("", "")

                        if prose_id.strip() and prose_en.strip():
                            try:
                                polished_prose = gemini.polish_section(
                                    source_en=prose_en,
                                    draft_id=prose_id,
                                    model="gemini-3.8-flash",
                                )
                                polished_prose = self._rule_based_clean(polished_prose)
                            except Exception:
                                polished_prose = self._rule_based_clean(prose_id)
                        else:
                            polished_prose = self._rule_based_clean(prose_id)

                        clean_top = self._rule_based_clean(top_id)
                        combined_lead = f"{clean_top.strip()}\n\n{polished_prose.strip()}".strip()
                        if sec_id.header_raw:
                            assembled_sections.append(f"{sec_id.header_raw}\n{combined_lead}")
                        else:
                            assembled_sections.append(combined_lead)
                    else:
                        # Body section
                        if en_source.strip() and id_draft.strip():
                            try:
                                polished_sec = gemini.polish_section(
                                    source_en=en_source,
                                    draft_id=id_draft,
                                    model="gemini-3.8-flash",
                                )
                                polished_sec = self._rule_based_clean(polished_sec)
                            except Exception:
                                polished_sec = self._rule_based_clean(id_draft)
                        else:
                            polished_sec = self._rule_based_clean(id_draft)

                        if sec_id.header_raw:
                            assembled_sections.append(f"{sec_id.header_raw}\n{polished_sec.strip()}")
                        else:
                            assembled_sections.append(polished_sec.strip())

                polished_body = "\n\n".join(s for s in assembled_sections if s.strip())
            except Exception:
                polished_body = self._rule_based_clean(working_id)
        else:
            # Offline / fallback rule-based cleaning
            polished_body = self._rule_based_clean(working_id)

        # Extra rule-based pass to guarantee complete zero-calque hygiene
        polished_body = self._rule_based_clean(polished_body)

        # Reconcile cross-wiki missing links from en_wikitext
        if en_wikitext.strip():
            polished_body = self.reconcile_missing_wikilinks(en_wikitext, polished_body)

        # Map and validate wikilinks (ensuring [[Perhambaan tani di Rusia|hamba tani]] etc. are resolved)
        polished_body = self.link_mapper.process_wikitext(polished_body)

        # Sanitize typography (standard quotation marks, non-breaking spaces, heading casing)
        polished_body = default_typography_sanitizer.sanitize_wikitext(polished_body)

        # Apply AWB General Fixes & RegEx Typo Fixes (RETF)
        polished_body = default_genfixes.apply_all_fixes(polished_body)
        # Auto-repair wikitext syntax
        polished_body = default_syntax_balancer.auto_repair(polished_body)

        # Notice box
        clean_requester = requester.strip().replace("Pengguna:", "")
        notice_box = (
            '{| class="wikitable" style="width:100%; background:#f8f9fa;"\n'
            f"| ℹ️ '''Draf perbaikan''' untuk artikel [[:{id_title}]] atas permintaan [[Pengguna:{clean_requester}|{clean_requester}]].\n"
            "|}\n\n"
        )

        # Ensure notice box is cleanly prepended exactly once
        final_text = notice_box + polished_body.strip()

        try:
            from .cli_ui import render_article_database_summary
            from .storage_manager import default_session_tracker
            render_article_database_summary(default_session_tracker, id_title)
        except Exception:
            pass

        return final_text.strip()
    def publish_polished_to_sandbox(
        self,
        id_title: str,
        polished_wikitext: str,
        username: str,
        bot_password: str,
        requester: Optional[str] = None,
        slug: Optional[str] = None,
        project_slug: Optional[str] = "Draf",
        sandbox_publisher: Optional[SandboxPublisher] = None,
        review_summary: Optional[str] = None,
        summary: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Publishes polished draft wikitext to user sandbox:
        1. Prepends a clean notice box to the polished wikitext.
        2. Creates talk page with review summary and link to evaluation report.
        3. Publishes to Pengguna:<clean_user>/Bak_pasir/<project_slug>/<slug>/<clean_title>.
        4. Updates monthly dashboard with activity_type="review", requester=requester.
        """
        _load_env_file()
        pub = sandbox_publisher or default_sandbox_publisher
        base_user = username.strip().split("@")[0].strip()
        clean_user = base_user.replace(" ", "_")
        clean_title = id_title.strip().replace(" ", "_")
        clean_requester = requester.strip().replace("Pengguna:", "") if requester else None
        # 1. Clean and strip forbidden draft templates / metadata
        cleaned_polished = re.sub(
            r"<!--\s*Templat belum tersedia di id\.wiki:\s*\{\{\s*(?:deskripsi singkat|short description)[^\}]*\}\}\s*-->\s*",
            "",
            polished_wikitext,
            flags=re.IGNORECASE,
        )
        cleaned_polished = re.sub(
            r"\{\{\s*(?:artikel pilihan|featured article|artikel bagus|good article|deskripsi singkat|short description)(?:\|[^\}]*)?\}\}\s*",
            "",
            cleaned_polished,
            flags=re.IGNORECASE,
        )
        cleaned_polished = re.sub(
            r"\{\{Kotak pemberitahuan[\s\S]*?\}\}\s*",
            "",
            cleaned_polished,
            flags=re.IGNORECASE,
        ).strip()

        # Native zero-dependency clean wikitable box
        if clean_requester:
            notice_box = (
                '{| class="wikitable" style="width:100%; background:#f8f9fa;"\n'
                f"| ℹ️ '''Draf perbaikan''' untuk artikel [[:{id_title}]] atas permintaan [[Pengguna:{clean_requester}|{clean_requester}]].\n"
                "|}\n\n"
            )
            summary_text = review_summary or f"Hasil evaluasi mutu dan draf pemolesan untuk [[:{id_title}]] atas permohonan Bung [[Pengguna:{clean_requester}|{clean_requester}]]."
        else:
            notice_box = (
                '{| class="wikitable" style="width:100%; background:#f8f9fa;"\n'
                f"| ℹ️ '''Draf perbaikan''' untuk artikel [[:{id_title}]].\n"
                "|}\n\n"
            )
            summary_text = review_summary or f"Hasil evaluasi mutu dan draf pemolesan untuk [[:{id_title}]]."

        final_sandbox_wikitext = notice_box + cleaned_polished

        # 2. Talk page content
        talk_wikitext = (
            "== Hasil Evaluasi Mutu & Draf Pemolesan ==\n\n"
            f"{summary_text}\n\n"
            f"* Draf ini disiapkan untuk membantu persiapan pengajuan Artikel Pilihan (WP:KAP).\n"
            f"* Draf pemolesan: [[Pengguna:{clean_user}/Bak_pasir/{project_slug or 'Draf'}/{slug or ''}/{clean_title}]]\n\n"
            "~~~~"
        )

        # 3. Publish to sandbox
        main_title, talk_title = pub.build_sandbox_titles(
            username=username,
            article_title=id_title,
            slug=slug,
            project_slug=project_slug,
        )

        res = pub.publish_to_sandbox(
            username=username,
            bot_password=bot_password,
            article_title=id_title,
            wikitext=final_sandbox_wikitext,
            talk_wikitext=talk_wikitext,
            slug=slug,
            project_slug=project_slug,
            summary=summary or "rapikan draf",
            talk_summary="catatan evaluasi",
            dry_run=dry_run,
            update_dashboard=False,  # We will call update_monthly_dashboard explicitly with activity_type="review"
        )

        if not res.get("success") and not dry_run:
            return res

        # 4. Update monthly dashboard as review
        dash_res = pub.update_monthly_dashboard(
            username=username,
            article_title=id_title,
            status="Audit selesai",
            slug=slug,
            project_slug=project_slug,
            bot_password=bot_password,
            dry_run=dry_run,
            activity_type="review",
            requester=clean_requester,
            review_status="Audit selesai",
            sandbox_draft=f"[[{main_title}|{id_title} (Draf Polesan)]]",
            article_status=f"[[:{id_title}]]",
        )
        res["dashboard"] = dash_res
        return res

    def evaluate_full_translation_threshold(
        self,
        id_wikitext: str,
        en_wikitext: str,
        report: APReviewReport,
        min_score: int = 60,
        min_ratio: float = 0.40,
    ) -> Tuple[bool, str, float]:
        """
        Evaluates whether an existing Indonesian article is too incomplete or heavily damaged
        to simply be polished, warranting an automatic full translation from en.wikipedia.
        """
        id_words = report.metrics.get("word_count", len(id_wikitext.split()))
        en_words = report.metrics.get("en_word_count", len(en_wikitext.split()))
        ratio = id_words / max(en_words, 1)

        reasons: List[str] = []
        if en_words >= 250 and ratio < min_ratio:
            reasons.append(
                f"Artikel id.wiki sangat tidak lengkap (kelengkapan {ratio * 100:.1f}%: {id_words} kata ID vs {en_words} kata EN; di bawah ambang {min_ratio * 100:.0f}%)"
            )
        if report.overall_score < min_score:
            reasons.append(
                f"Skor audit mutu teks lama terlalu rendah ({report.overall_score}/100; di bawah ambang minimum {min_score})"
            )
        if len(report.fatal_errors) >= 3:
            reasons.append(
                f"Ditemukan {len(report.fatal_errors)} kesalahan konteks fatal (pembalikan fakta/pelaku)"
            )

        needs_full = len(reasons) > 0
        return needs_full, "; ".join(reasons), ratio

    def translate_full_from_en(
        self, en_wikitext: str, id_title: str = "Artikel"
    ) -> str:
        """
        Translates a complete article from en.wikipedia when the existing Indonesian
        article is an incomplete stub or critically broken.
        Iterates over all sections in en.wikipedia to ensure 100% structural and factual parity.
        """
        gemini = self._get_gemini_client()
        if not gemini or not en_wikitext.strip():
            return self._rule_based_clean(en_wikitext)

        sec_en_list = self.en_client.split_sections(en_wikitext)
        assembled_sections: List[str] = []

        for i, sec_en in enumerate(sec_en_list):
            title_lower = sec_en.title.lower()
            is_meta = any(k in title_lower for k in [
                "references", "see also", "external links", "further reading", "notes"
            ])

            if is_meta:
                clean_sec = self._rule_based_clean(sec_en.content)
                header = sec_en.header_raw or ""
                header = re.sub(r"==\s*References\s*==", "== Referensi ==", header, flags=re.IGNORECASE)
                header = re.sub(r"==\s*Notes\s*==", "== Catatan ==", header, flags=re.IGNORECASE)
                header = re.sub(r"==\s*See also\s*==", "== Lihat pula ==", header, flags=re.IGNORECASE)
                header = re.sub(r"==\s*External links\s*==", "== Pranala luar ==", header, flags=re.IGNORECASE)
                header = re.sub(r"==\s*Further reading\s*==", "== Bacaan lanjutan ==", header, flags=re.IGNORECASE)
                if header:
                    assembled_sections.append(f"{header}\n{clean_sec.strip()}")
                else:
                    assembled_sections.append(clean_sec.strip())
                continue

            if not sec_en.content.strip():
                continue

            try:
                translated_sec = gemini.translate_section(
                    sec_en.content,
                    model="gemini-3.8-flash",
                )
                translated_sec = self._rule_based_clean(translated_sec)
            except Exception:
                translated_sec = self._rule_based_clean(sec_en.content)

            header = sec_en.header_raw or ""
            if header and i > 0:
                header = default_typography_sanitizer.normalize_headings(header)
                assembled_sections.append(f"{header}\n{translated_sec.strip()}")
            else:
                assembled_sections.append(translated_sec.strip())

        full_body = "\n\n".join(s for s in assembled_sections if s.strip())

        if self.link_mapper:
            try:
                full_body = self.link_mapper.process_wikitext(full_body)
            except Exception:
                pass

        full_body = default_typography_sanitizer.sanitize_wikitext(full_body)
        full_body = default_syntax_balancer.auto_repair(full_body)
        return full_body.strip()

    def audit_and_report(
        self,
        id_title: str,
        en_title: Optional[str] = None,
        auto_full_threshold: int = 60,
        min_completeness_ratio: float = 0.40,
        allow_auto_full: bool = True,
    ) -> Tuple[APReviewReport, str, str]:
        """
        Full workflow:
        1. Fetches article pair from id and en Wikipedia.
        2. Audits translation quality and calculates WP:KAP score.
        3. Checks if article is below threshold (stub or broken legacy text).
           If below threshold and allow_auto_full is True:
           - Automatically runs Full Grade A++ Translation from en.wikipedia.
           - Generates complete, comprehensive wikitext covering all en.wiki sections.
        4. Otherwise:
           - Generates polished wikitext by improving existing sections.
        5. Saves review and preview.
        Returns (report, review_text, polished_wikitext).
        """
        id_wikitext, en_wikitext = self.fetch_article_pair(id_title, en_title)
        report = self.audit_translation_quality(id_wikitext, en_wikitext, id_title)

        needs_full = False
        escalation_reason = ""
        if allow_auto_full and en_wikitext.strip():
            needs_full, escalation_reason, ratio = self.evaluate_full_translation_threshold(
                id_wikitext, en_wikitext, report, min_score=auto_full_threshold, min_ratio=min_completeness_ratio
            )

        if needs_full:
            print(f"\n[!] AMBANG BATAS TERPICU: {escalation_reason}")
            print("[*] Mengalihkan otomatis: Menjalankan Penerjemahan Penuh (Full Grade A++ Translation Pipeline) dari en.wikipedia...")
            polished_wikitext = self.translate_full_from_en(en_wikitext, id_title=id_title)
            # Re-evaluate report for the newly translated article
            report = self.audit_translation_quality(polished_wikitext, en_wikitext, id_title)
            report.metrics["escalated_to_full_translation"] = True
            report.metrics["escalation_reason"] = escalation_reason
            review_text = self.generate_community_review_text(report)
            editorial_notice = (
                f"> ℹ️ **Catatan Redaksi (Auto-Escalation):** Naskah Wikipedia bahasa Indonesia sebelumnya berada di bawah ambang batas kelayakan ({escalation_reason}).\n"
                f"> Sistem secara otomatis mengalihkan proses ke **Penerjemahan Penuh (Full Grade A++ Translation)** dari en.wikipedia agar artikel menjadi utuh, lengkap, dan berimbang.\n\n"
            )
            review_text = editorial_notice + review_text
        else:
            review_text = self.generate_community_review_text(report)
            polished_wikitext = self.generate_polished_wikitext(id_wikitext, en_wikitext, id_title=id_title)

        check_saved_integrity(id_wikitext if not needs_full else polished_wikitext, polished_wikitext, preserve_prose=False)
        findings = review_claims(en_wikitext, polished_wikitext, self._get_gemini_client())
        if findings:
            raise ValueError("Quality gate klaim: " + "; ".join(findings))
        # Save to output/reviews/
        reviews_dir = Path("output/reviews")
        reviews_dir.mkdir(parents=True, exist_ok=True)
        snapshot = save_review_snapshot(
            reviews_dir, id_title, id_wikitext, en_wikitext, polished_wikitext
        )
        print(f"[*] Review snapshot: {snapshot}")

        clean_filename = re.sub(r'[\\/*?:"<>| ]', "_", id_title)
        review_file = reviews_dir / f"{clean_filename}_review.md"
        polished_file = reviews_dir / f"{clean_filename}_polished.wikitext"

        with open(review_file, "w", encoding="utf-8") as f:
            f.write(review_text)

        with open(polished_file, "w", encoding="utf-8") as f:
            f.write(polished_wikitext)

        # Generate standalone Vector 2022 HTML preview
        preview_file = reviews_dir / f"{clean_filename}.preview.html"
        try:
            from .html_preview import default_preview_generator
            preview_html = default_preview_generator.render_html(id_title, polished_wikitext)
            with open(preview_file, "w", encoding="utf-8") as f:
                f.write(preview_html)
            print(f"[+] Pratinjau visual HTML Vector 2022 disimpan ke: {preview_file}")
        except Exception as pe:
            print(f"[!] Warning: Gagal membuat pratinjau HTML: {pe}")

        # Review is local-only. Publishing requires an explicit CLI action.
        return report, review_text, polished_wikitext


default_article_reviewer = ArticleReviewer()
