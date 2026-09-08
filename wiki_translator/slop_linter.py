"""Contextual Indonesian prose linting; only clear spelling errors are auto-fixed."""

from dataclasses import dataclass, field
import re
import mwparserfromhell
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class SlopViolation:
    rule_id: str
    severity: str  # "high", "medium", "low"
    line_number: int
    matched_text: str
    excerpt: str
    explanation: str
    suggestions: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "line_number": self.line_number,
            "matched_text": self.matched_text,
            "excerpt": self.excerpt,
            "explanation": self.explanation,
            "suggestions": self.suggestions,
        }


@dataclass
class SlopLintResult:
    score: int  # 0 to 100
    violations: List[SlopViolation] = field(default_factory=list)
    suggestions_summary: List[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return len(self.violations) == 0


@dataclass
class SlopRule:
    rule_id: str
    pattern: re.Pattern
    severity: str
    explanation: str
    suggestions: List[str]
    auto_replace: Optional[str] = None  # replacement string if safe for auto_fix


class AntiAISlopLinter:
    """
    Automated linguistic guardrail & Anti-AI-Slop linter for Indonesian translation.
    Identifies machine translation cliches, calques, unidiomatic relative clauses,
    and unnatural passive constructions.
    """

    def __init__(self):
        self.rules: List[SlopRule] = self._init_rules()

    def _init_rules(self) -> List[SlopRule]:
        rules = [
            SlopRule(
                rule_id=rule_id,
                pattern=re.compile(pattern, re.IGNORECASE),
                severity="low",
                explanation="Periksa konteks sumber sebelum menyunting; bentuk ini tidak otomatis salah.",
                suggestions=suggestions,
            )
            for rule_id, pattern, suggestions in [
                ("calque_berbasis_di", r"\byang\s+berbasis\s+di\b",
                 ["berbasis di; berkantor di hanya jika sumber menyatakan lokasi kantor"]),
                ("calque_upaya_putus_asa", r"\bdalam\s+upaya\s+putus\s+asa\s+untuk\b",
                 ["susun ulang kalimat dengan mempertahankan makna keputusasaan"]),
                ("calque_dalam_upaya", r"\bdalam\s+upaya\s+untuk\b",
                 ["dalam upaya untuk; pertahankan makna usaha"]),
                ("calque_memainkan_peran", r"\bmemainkan\s+peran\s+(?:kunci|penting|besar)\b",
                 ["berperan; pertahankan tingkat peran dan konteks pemeranan"]),
                ("calque_menghasilkan_dampak", r"\bmenghasilkan\s+dampak\s+yang\s+signifikan\b",
                 ["berdampak signifikan; signifikansi statistik bukan besarnya efek"]),
                ("calque_membuat_debut", r"\bmembuat\s+debut(?:nya)?\b",
                 ["tampil perdana; pertahankan subjek dan waktunya"]),
                ("calque_pemukiman_luar_dewan", r"\bpemukiman\s+luar\s+dewan\b",
                 ["penyelesaian sengketa di luar pengadilan (kalkir dari out-of-court settlement)"]),
                ("calque_pemilihan_jenderal", r"\bpemilihan\s+jenderal\b",
                 ["pemilihan umum (kalkir keliru dari general elections)"]),
                ("neologisme_merkenari", r"\bmerkenari\b",
                 ["tentara bayaran (neologisme palsu dari mercenaries)"]),
                ("neologisme_memproporsalkan", r"\bmemproporsalkan\b",
                 ["mengusulkan (neologisme palsu dari propose)"]),
                ("calque_pendidikan_privat", r"\b(?:pendidikan|bimbingan)\s+privat\b",
                 ["pendidikan di rumah / bimbingan pengajar pribadi"]),
                ("pleonasme_jamak", r"\b(berbagai|beberapa|sejumlah|para|banyak)\s+([a-zA-Z]+)-\2\b",
                 ["pleonasme kata jamak: setelah kata penanda jamak, kata dasar tidak perlu diulang"]),
                ("calque_salah_satu_manusia", r"\bsalah satu (?:pendidik|aktivis|penulis|menteri|presiden|arsitek|pemimpin|tokoh|ilmuwan|pahlawan|dokter|seniman|sejarawan|sutradara|pemeran|aktor|aktris)\b",
                 ["gunakan 'salah seorang' untuk manusia/tokoh alih-alih 'salah satu'"]),
                ("puffery_dedikasi_tanpa_pamrih", r"\b(?:dedikasi|pengabdian|perjuangan)\s+tanpa\s+pamrih(?:nya)?\b",
                 ["hindari sanjungan subjektif (WP:NPOV/WP:PUFFERY); sebutkan pencapaian konkret secara berjarak dan netral"]),
                ("puffery_ditangisi_secara_luas", r"\bditangisi\s+secara\s+luas\b",
                 ["gaya bahasa obituari/eulogi emosional (WP:NPOV); paparkan peristiwa kematian secara lugas dan faktual"]),
                ("puffery_tiada_tara", r"\b(?:kontribusi|jasa)\s+(?:yang\s+)?tiada\s+tara\b",
                 ["klaim superlatif subjektif (WP:PUFFERY); paparkan fakta kontribusinya secara objektif"]),
                ("puffery_jasa_tak_terhingga", r"\bjasa-jasanya\s+(?:yang\s+)?tak\s+terhingga\b",
                 ["sanjungan emosional (WP:PUFFERY); gunakan bahasa ensiklopedis netral"]),
                ("calque_skor_film", r"\b(?:skor\s+film|skor\s+dan\s+lagu)\b",
                 ["hindari 'skor' untuk musik (konsensus WP:Skor film & Warung Kopi); gunakan 'komposisi musik', 'musik film', 'musik latar', atau 'tata musik' (FFI)"]),
                ("calque_kedatangan_benda", r"\bkedatangan(?:nya)?\s+(?:di|ke)\s+([A-Z][a-z]+)\b",
                 ["periksa subjek: jika merujuk pada artefak/benda/prasasti (bukan manusia), gunakan 'diboyong ke' atau 'dipindahkan ke' (tinjauan WP:AP)"]),
                ("calque_di_tangan_kirinya", r"\bdi\s+tangan\s+(?:kiri|kanan)nya\s+ia\s+memegang\b",
                 ["susunan terbalik kalkir bahasa Inggris; gunakan urutan alami 'ia memegang ... di tangan kiri/kanan' (tinjauan WP:AP)"]),
                ("tbbbi_sehingga_opener", r"(?:^|[.!?]\s+)Sehingga,\s+",
                 ["'Sehingga' adalah konjungsi intrakalimat subordinatif (TBBBI Bab X); gunakan konjungsi antarkalimat seperti 'Akibatnya,'"]),
                ("tbbbi_sedangkan_opener", r"(?:^|[.!?]\s+)Sedangkan,\s+",
                 ["'Sedangkan' adalah konjungsi intrakalimat koordinatif (TBBBI Bab VIII); gunakan 'Sementara itu,' di awal kalimat"]),
                ("tbbbi_dan_opener", r"(?:^|[.!?]\s+)Dan,\s+",
                 ["'Dan' adalah konjungsi intrakalimat (TBBBI Bab VIII); gunakan 'Selain itu,' di awal kalimat"]),
                ("tbbbi_negation_calque", r"\btidak\s+(?:sebuah|suatu|seorang|seekor)\b",
                 ["Gunakan 'bukan' alih-alih 'tidak' di depan kata penggolong nomina (TBBBI Bab IX Tabel 9.5 Kata Ingkar)"]),
                ("tbbbi_negation_copula", r"\btidak\s+merupakan\b",
                 ["Gunakan 'bukan merupakan' alih-alih 'tidak merupakan' (TBBBI Tabel 9.5 Kata Ingkar)"]),
                ("calque_pensiun_ke", r"\b(?:pensiun|mengundurkan\s+diri)\s+ke\s+(?:rumah|kediaman|kampung|desa|daerah|negeri|tanah|wilayah)(?:nya)?\b",
                 ["Kata 'pensiun' bukan verba pergerakan (kalkir dari 'retired to'); gunakan 'pensiun dan kembali ke...', 'pensiun lalu menetap di...', atau 'menghabiskan masa pensiun di...'"]),
                ("arkaisme_bertarikh", r"\bbertarikh\s+(\d+[\s\w]*)\b",
                 ["Kata 'bertarikh' adalah bentuk arkais; gunakan 'berangka tahun ...' (khusus prasasti/koin), 'berasal dari tahun ...', atau 'bertanggal ...'"]),
                ("calque_adalah_hal_yang", r"\badalah\s+hal\s+yang\b",
                 ["Kalkir bahasa Inggris 'is one that / is something that'; pangkas 'adalah hal yang' dan gunakan predikat langsung (misal: 'bermakna sangat mendalam bagi saya')"]),
                ("calque_merupakan_inti_dari", r"\bmerupakan\s+inti\s+dari\b",
                 ["Pangkas kata pengisi mubazir: gunakan 'menjadi inti ...' tanpa kata 'dari'"]),
            ]
        ]
        for typo, spelling in {
            "pernikaahn": "pernikahan",
            "senbagai": "sebagai",
            "aristoktrat": "aristokrat",
            "tersbeut": "tersebut",
            "unicersitas": "universitas",
            "berpedapat": "berpendapat",
        }.items():
            rules.append(SlopRule(
                rule_id=f"typo_{typo}",
                pattern=re.compile(rf"\b{typo}\b", re.IGNORECASE),
                severity="high",
                explanation=f"Salah ketik: gunakan {spelling}.",
                suggestions=[spelling],
                auto_replace=spelling,
            ))

        # Dynamically add macro-micro tribal contradiction rules from data/historical_ethnonyms.json
        try:
            from .historical_ethnonyms import default_ethnonyms_manager
            macro_names = default_ethnonyms_manager.get_entity_names()
            if macro_names:
                macro_group = "|".join(re.escape(n) for n in macro_names)
                rules.append(SlopRule(
                    rule_id="ethnonym_macro_micro_contradiction",
                    pattern=re.compile(rf"\bsuku\s+({macro_group})\s+(?:relatif\s+\w+\s+|\w+\s+)?terpecah\s+(?:menjadi|ke\s+dalam)\s+banyak\s+suku\b", re.IGNORECASE),
                    severity="high",
                    explanation="Kontradiksi taksonomi etnis: entitas makro adalah 'bangsa' yang terpecah menjadi banyak 'suku' (bukan satu suku terpecah menjadi banyak suku).",
                    suggestions=["Gunakan 'Bangsa' untuk entitas makro"],
                ))
        except Exception:
            pass
        # Dynamically load community peer-review rules from FeaturedArticleHarvester
        try:
            from .featured_article_harvester import default_fa_harvester
            for cp in default_fa_harvester.SEED_CRITIQUE_POINTS:
                if cp.quote and cp.critique:
                    clean_id = re.sub(r"[^a-zA-Z0-9]", "_", cp.quote).strip("_")[:24]
                    rules.append(SlopRule(
                        rule_id=f"ap_critique_{clean_id}",
                        pattern=re.compile(rf"\b{re.escape(cp.quote)}\b", re.IGNORECASE),
                        severity="medium",
                        explanation=f"Konsensus Peninjau Artikel Pilihan (WP:AP '{cp.article_title}'): {cp.critique}",
                        suggestions=[cp.critique],
                    ))
        except Exception:
            pass

        return rules
    def _mask_protected_zones(self, text: str) -> Tuple[str, List[Tuple[str, str]]]:
        """Protect markup and quotations, retaining newlines for lint locations."""
        placeholders: List[Tuple[str, str]] = []
        prefix = "SLOPMASK"
        while prefix in text:
            prefix += "_"

        def protect(original: str) -> str:
            token = f"{prefix}{len(placeholders)}END" + "\n" * original.count("\n")
            placeholders.append((token, original))
            return token

        parts = []
        for node in mwparserfromhell.parse(text).nodes:
            if isinstance(node, mwparserfromhell.nodes.Template):
                t_name = str(node.name).strip().lower()
                if t_name in ("efn", "efn-lr", "explanatory footnote"):
                    parts.append(protect("{{Efn|"))
                    for param in node.params:
                        pval = str(param.value)
                        pval = re.sub(r"<ref\b[^>]*>[\s\S]*?<\/ref>", lambda m: protect(m.group(0)), pval)
                        pval = re.sub(r"<ref\b[^>]*/>", lambda m: protect(m.group(0)), pval)
                        parts.append(pval)
                    parts.append(protect("}}"))
                    continue
            if not isinstance(node, mwparserfromhell.nodes.Text):
                parts.append(protect(str(node)))
                continue
            prose = re.sub(
                r'https?://[^\s<>\[\]{}]+|"[^"\n]*"|“[^”\n]*”|‘[^’\n]*’',
                lambda match: protect(match.group(0)),
                str(node),
            )
            parts.append(prose)
        return "".join(parts), placeholders

    def _unmask_protected_zones(self, text: str, placeholders: List[Tuple[str, str]]) -> str:
        for token, original in reversed(placeholders):
            text = text.replace(token, original)
        return text

    def _get_line_number(self, text: str, pos: int) -> int:
        return text.count("\n", 0, pos) + 1

    def _get_excerpt(self, text: str, start: int, end: int, window: int = 35) -> str:
        s = max(0, start - window)
        e = min(len(text), end + window)
        prefix = "..." if s > 0 else ""
        suffix = "..." if e < len(text) else ""
        return f"{prefix}{text[s:e].strip()}{suffix}"

    def lint(self, text: str) -> SlopLintResult:
        """
        Scans wikitext/Indonesian text for machine translation slop and calques.
        Returns SlopLintResult with score, violations list, and suggestions summary.
        """
        if not text or not text.strip():
            return SlopLintResult(score=100, violations=[], suggestions_summary=[])

        masked_text, _ = self._mask_protected_zones(text)
        violations: List[SlopViolation] = []

        for rule in self.rules:
            for match in rule.pattern.finditer(masked_text):
                # Filter out valid question usage for "di mana" e.g. "Di mana letak..." or questions ending with "?"
                if rule.rule_id == "unidiomatic_di_mana":
                    # Check if line ends with a question mark
                    line_start = masked_text.rfind("\n", 0, match.start())
                    line_start = 0 if line_start == -1 else line_start + 1
                    line_end = masked_text.find("\n", match.end())
                    line_end = len(masked_text) if line_end == -1 else line_end
                    line = masked_text[line_start:line_end].strip()
                    if "?" in line:
                        continue  # Valid interrogative sentence!

                line_no = self._get_line_number(masked_text, match.start())
                matched_str = match.group(0)
                excerpt = self._get_excerpt(masked_text, match.start(), match.end())

                violations.append(
                    SlopViolation(
                        rule_id=rule.rule_id,
                        severity=rule.severity,
                        line_number=line_no,
                        matched_text=matched_str,
                        excerpt=excerpt,
                        explanation=rule.explanation,
                        suggestions=rule.suggestions,
                    )
                )

        # Sort violations by line number
        violations.sort(key=lambda v: (v.line_number, v.rule_id))

        # Calculate Naturalness & Compliance Score (0 to 100)
        # Word count penalty:
        word_count = max(1, len(text.split()))
        penalty = 0
        for v in violations:
            if v.severity == "high":
                penalty += 12
            elif v.severity == "medium":
                penalty += 6
            else:
                penalty += 3

        # Base score normalized with length
        raw_score = 100 - penalty
        final_score = max(0, min(100, raw_score))

        # Suggestions summary
        summary = []
        seen_rules = set()
        for v in violations:
            if v.rule_id not in seen_rules:
                seen_rules.add(v.rule_id)
                summary.append(f"[{v.matched_text}] -> {', '.join(v.suggestions)} ({v.explanation})")

        return SlopLintResult(
            score=final_score,
            violations=violations,
            suggestions_summary=summary,
        )

    def auto_fix(self, wikitext: str) -> Tuple[str, int]:
        """Fix spelling only; semantic and stylistic suggestions require source review."""
        masked, placeholders = self._mask_protected_zones(wikitext)
        total = 0
        for rule in self.rules:
            if rule.auto_replace is None:
                continue

            def replace(match):
                original = match.group(0)
                replacement = rule.auto_replace
                if original.isupper():
                    return replacement.upper()
                return replacement.capitalize() if original[0].isupper() else replacement

            masked, count = rule.pattern.subn(replace, masked)
            total += count
        return self._unmask_protected_zones(masked, placeholders), total


default_slop_linter = AntiAISlopLinter()
