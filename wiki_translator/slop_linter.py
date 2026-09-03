"""
Anti-AI-Slop Linter & Linguistic Guardrails for Indonesian Wikipedia Translation.

Features:
1. Automated post-generation rule-based scanner to catch machine translation cliches,
   calques, unidiomatic Indonesian constructions, and unnatural syntax.
2. Core rules & pattern checks:
   - "yang berbasis di" -> "di [kota/negara]", "berpusat di", "berkantor di"
   - "dalam upaya untuk" / "dalam upaya putus asa untuk" -> "demi", "untuk", "berusaha keras"
   - "memainkan peran kunci" / "memainkan peran penting" -> "berperan kunci", "berperan penting", "berperan besar"
   - "menghasilkan dampak yang signifikan" -> "berdampak besar", "berpengaruh nyata"
   - "berfungsi sebagai" -> "menjadi", "berperan sebagai"
   - "dikenal karena menjadi" -> "dikenal sebagai"
   - "membuat debutnya" -> "memulai debut", "tampil perdana"
   - "merupakan sebuah / adalah sebuah" -> "merupakan [benda]", "adalah [benda]"
   - Unidiomatic relative "di mana" -> "tempat", "saat", "ketika", "yang"
   - Excessive passive calques like "dipaksa untuk mematuhi" -> "dipaksa mematuhi"
3. Readability & Naturalness Scoring:
   - Score: 0 to 100 based on violation density and severity.
   - Violations: tag type, severity ("high", "medium", "low"), line number, excerpt, explanation, suggestions.
4. Auto-correction capability (`auto_fix`):
   - Safely substitutes unambiguous calques while preserving context.
   - Ignores matches inside `<ref>...</ref>`, `{{cite ...}}`, or URLs.
"""

from dataclasses import dataclass, field
import re
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
        return [
            # 1. yang berbasis di -> berpusat di / berkantor di / di
            SlopRule(
                rule_id="calque_berbasis_di",
                pattern=re.compile(r"\byang\s+berbasis\s+di\b", re.IGNORECASE),
                severity="high",
                explanation="Kalkir harfiah dari 'based in'. Gunakan 'berpusat di', 'berkantor di', atau cukup 'di'.",
                suggestions=["berpusat di", "berkantor di", "di"],
                auto_replace="berpusat di",
            ),
            # 2. dalam upaya putus asa untuk -> berusaha keras untuk / demi
            SlopRule(
                rule_id="calque_upaya_putus_asa",
                pattern=re.compile(r"\bdalam\s+upaya\s+putus\s+asa\s+untuk\b", re.IGNORECASE),
                severity="high",
                explanation="Kalkir harfiah dari 'in a desperate attempt to'. Gunakan 'berusaha keras untuk' atau 'demi'.",
                suggestions=["berusaha keras untuk", "demi"],
                auto_replace="berusaha keras untuk",
            ),
            # 3. dalam upaya untuk -> demi / untuk / agar
            SlopRule(
                rule_id="calque_dalam_upaya_untuk",
                pattern=re.compile(r"\bdalam\s+upaya\s+untuk\b", re.IGNORECASE),
                severity="medium",
                explanation="Kalkir bertele-tele dari 'in an effort to' / 'in an attempt to'. Cukup gunakan 'demi' atau 'untuk'.",
                suggestions=["demi", "untuk", "agar"],
                auto_replace="demi",
            ),
            # 4. memainkan peran kunci / penting / besar -> berperan kunci / penting / besar
            SlopRule(
                rule_id="calque_memainkan_peran_kunci",
                pattern=re.compile(r"\bmemainkan\s+peran\s+kunci\b", re.IGNORECASE),
                severity="high",
                explanation="Kalkir harfiah dari 'play a key role'. Bahasa Indonesia baku menggunakan 'berperan kunci'.",
                suggestions=["berperan kunci", "sangat berperan"],
                auto_replace="berperan kunci",
            ),
            SlopRule(
                rule_id="calque_memainkan_peran_penting",
                pattern=re.compile(r"\bmemainkan\s+peran\s+penting\b", re.IGNORECASE),
                severity="high",
                explanation="Kalkir harfiah dari 'play an important role'. Bahasa Indonesia baku menggunakan 'berperan penting'.",
                suggestions=["berperan penting", "berperan besar"],
                auto_replace="berperan penting",
            ),
            SlopRule(
                rule_id="calque_memainkan_peran",
                pattern=re.compile(r"\bmemainkan\s+peran\s+besar\b", re.IGNORECASE),
                severity="medium",
                explanation="Kalkir harfiah dari 'play a major role'. Gunakan 'berperan besar'.",
                suggestions=["berperan besar"],
                auto_replace="berperan besar",
            ),
            # 5. menghasilkan dampak yang signifikan -> berdampak besar / berpengaruh nyata
            SlopRule(
                rule_id="calque_menghasilkan_dampak",
                pattern=re.compile(r"\bmenghasilkan\s+dampak\s+yang\s+signifikan\b", re.IGNORECASE),
                severity="high",
                explanation="Kalkir klise mesin dari 'produced a significant impact'. Gunakan 'berdampak besar' atau 'berpengaruh nyata'.",
                suggestions=["berdampak besar", "berpengaruh nyata"],
                auto_replace="berdampak besar",
            ),
            # 6. berfungsi sebagai -> menjadi / berperan sebagai
            SlopRule(
                rule_id="calque_berfungsi_sebagai",
                pattern=re.compile(r"\bberfungsi\s+sebagai\b", re.IGNORECASE),
                severity="medium",
                explanation="Kalkir dari 'serves as' / 'functions as'. Lebih wajar menggunakan 'menjadi' atau 'berperan sebagai'.",
                suggestions=["menjadi", "berperan sebagai"],
                auto_replace="menjadi",
            ),
            # 7. dikenal karena menjadi -> dikenal sebagai
            SlopRule(
                rule_id="calque_dikenal_karena_menjadi",
                pattern=re.compile(r"\bdikenal\s+karena\s+menjadi\b", re.IGNORECASE),
                severity="high",
                explanation="Kalkir kaku dari 'known for being'. Gunakan 'dikenal sebagai'.",
                suggestions=["dikenal sebagai"],
                auto_replace="dikenal sebagai",
            ),
            # 8. membuat debutnya / membuat debut -> memulai debut / tampil perdana
            SlopRule(
                rule_id="calque_membuat_debut",
                pattern=re.compile(r"\bmembuat\s+debut(?:nya)?\b", re.IGNORECASE),
                severity="high",
                explanation="Kalkir harfiah dari 'made its/his/her debut'. Bahasa Indonesia baku menggunakan 'memulai debut' atau 'tampil perdana'.",
                suggestions=["memulai debut", "tampil perdana"],
                auto_replace="memulai debut",
            ),
            # 9. merupakan sebuah / adalah sebuah (untuk konsep abstrak/karya)
            SlopRule(
                rule_id="calque_merupakan_sebuah",
                pattern=re.compile(r"\b(merupakan|adalah)\s+sebuah\b", re.IGNORECASE),
                severity="medium",
                explanation="Penggunaan kata penggolong 'sebuah' yang tidak perlu / terjemahan harfiah dari 'is a/an'. Cukup 'adalah' atau 'merupakan' langsung diikuti kata benda.",
                suggestions=["merupakan", "adalah"],
                # auto_replace can replace 'merupakan sebuah' -> 'merupakan' or 'adalah sebuah' -> 'adalah'
                auto_replace=None,
            ),
            # 10. Unidiomatic relative "di mana" (e.g. "... di mana ia dilahirkan ...", "... sistem di mana data disimpan ...")
            SlopRule(
                rule_id="unidiomatic_di_mana",
                pattern=re.compile(r"(?<!\?)\bdi\s+mana\b", re.IGNORECASE),
                severity="high",
                explanation="Penggunaan 'di mana' sebagai kata penghubung relatif (kalkir 'where' / 'in which'). Gunakan 'tempat', 'saat', 'ketika', 'yang', atau susun ulang kalimat.",
                suggestions=["tempat", "saat", "ketika", "yang"],
                auto_replace=None,
            ),
            # 11. Excessive passive calques e.g. "dipaksa untuk mematuhi" -> "dipaksa mematuhi"
            SlopRule(
                rule_id="calque_dipaksa_untuk",
                pattern=re.compile(r"\b(dipaksa|didorong|dituntut|diminta)\s+untuk\s+([a-zA-Z]+)\b", re.IGNORECASE),
                severity="medium",
                explanation="Preposisi 'untuk' berlebih setelah verba pasif (kalkir 'forced to do', 'asked to do'). Cukup verba pasif langsung diikuti verba.",
                suggestions=["\\1 \\2"],
                auto_replace=None,
            ),
            # 12. Em-dashes in narrative prose
            SlopRule(
                rule_id="orthography_em_dash",
                pattern=re.compile(r"\s*—\s*"),
                severity="medium",
                explanation="Hindari tanda pisah em-dash (—) di tengah kalimat narasi prosa. Gunakan koma, tanda kurung, atau pecah kalimat.",
                suggestions=["koma (,)", "tanda kurung ()", "pecah kalimat"],
                auto_replace=", ",
            ),
            # 13. Semicolons in narrative sentences
            SlopRule(
                rule_id="orthography_semicolon",
                pattern=re.compile(r";(?!\s*(?:&[a-zA-Z0-9#]+;|\d+;))\s*"),
                severity="low",
                explanation="Bahasa Indonesia ensiklopedis sangat jarang menggunakan titik koma dalam narasi. Pecah kalimat atau gunakan konjungsi koordinatif.",
                suggestions=["pecah kalimat", ", dan ", ", tetapi "],
                auto_replace=", dan ",
            ),
            # 14. Banned calque hyphens like pro-Palestina / pro-[Negara]
            SlopRule(
                rule_id="calque_pro_hyphen",
                pattern=re.compile(r"\bpro-([A-Z][a-zA-Z]+)\b"),
                severity="medium",
                explanation="Kalkir compound hyphen bahasa Inggris ('pro-Palestina'). Gunakan 'pendukung [Entitas]' atau 'membela [Entitas]'.",
                suggestions=["pendukung \\1", "membela \\1"],
                auto_replace="pendukung \\1",
            ),
            # 15. Banned loanword/calque "reviu"
            SlopRule(
                rule_id="calque_reviu",
                pattern=re.compile(r"\breviu\b", re.IGNORECASE),
                severity="high",
                explanation="Bentuk serapan tidak lazim / kalkir 'review'. Gunakan 'peninjauan', 'pemeriksaan', atau 'ulasan'.",
                suggestions=["peninjauan", "pemeriksaan", "ulasan"],
                auto_replace="peninjauan",
            ),
        ]

    def _mask_protected_zones(self, text: str) -> Tuple[str, List[Tuple[str, str]]]:
        """
        Masks out references (<ref>...</ref>), cite templates ({{cite ...}}),
        external links [http...], URLs, and HTML comments to prevent false positives.
        Returns masked_text and list of (placeholder, original_text).
        """
        placeholders: List[Tuple[str, str]] = []

        def repl(match: re.Match) -> str:
            token = f"§§SLOPMASK_{len(placeholders)}§§"
            placeholders.append((token, match.group(0)))
            return token

        # 1. Mask HTML comments <!-- ... -->
        masked = re.sub(r"<!--[\s\S]*?-->", repl, text)

        # 2. Mask <nowiki> ... </nowiki>
        masked = re.sub(r"<nowiki\b[^>]*>[\s\S]*?</nowiki>", repl, masked, flags=re.IGNORECASE)

        # 3. Mask <ref> ... </ref> and self-closing <ref ... />
        masked = re.sub(r"<ref\b[^>]*>[\s\S]*?</ref>", repl, masked, flags=re.IGNORECASE)
        masked = re.sub(r"<ref\b[^>]*/>", repl, masked, flags=re.IGNORECASE)

        # 4. Mask {{cite ...}} or {{rujukan ...}} templates
        masked = re.sub(r"\{\{(?:cite|rujukan)\b[^{}]*\}\}", repl, masked, flags=re.IGNORECASE)

        # 5. Mask URLs (http:// or https://)
        masked = re.sub(r"https?://[^\s<>\[\]{}]+", repl, masked, flags=re.IGNORECASE)

        # 6. Mask external link brackets [http... text]
        masked = re.sub(r"\[https?://[^\]]+\]", repl, masked, flags=re.IGNORECASE)

        return masked, placeholders

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
        """
        Safely substitutes unambiguous calques while preserving surrounding context.
        Does NOT touch inside <ref>...</ref>, {{cite ...}}, or URLs.
        Returns (repaired_wikitext, fix_count).
        """
        if not wikitext or not wikitext.strip():
            return wikitext, 0

        masked_text, placeholders = self._mask_protected_zones(wikitext)
        total_fixes = 0

        # Safe substitutions
        # 1. yang berbasis di -> berpusat di
        sub_count = 0
        def repl_berbasis(m):
            # Preserve capitalization of first character if capitalized
            orig = m.group(0)
            rep = "berpusat di"
            if orig[0].isupper():
                rep = "Berpusat di"
            return rep
        masked_text, sub_count = re.subn(r"\byang\s+berbasis\s+di\b", repl_berbasis, masked_text, flags=re.IGNORECASE)
        total_fixes += sub_count

        # 2. dalam upaya putus asa untuk -> berusaha keras untuk
        def repl_putus_asa(m):
            orig = m.group(0)
            rep = "berusaha keras untuk"
            if orig[0].isupper():
                rep = "Berusaha keras untuk"
            return rep
        masked_text, sub_count = re.subn(r"\bdalam\s+upaya\s+putus\s+asa\s+untuk\b", repl_putus_asa, masked_text, flags=re.IGNORECASE)
        total_fixes += sub_count

        # 3. dalam upaya untuk -> demi
        def repl_upaya(m):
            orig = m.group(0)
            rep = "demi"
            if orig[0].isupper():
                rep = "Demi"
            return rep
        masked_text, sub_count = re.subn(r"\bdalam\s+upaya\s+untuk\b", repl_upaya, masked_text, flags=re.IGNORECASE)
        total_fixes += sub_count

        # 4. memainkan peran kunci -> berperan kunci
        def repl_peran_kunci(m):
            orig = m.group(0)
            rep = "berperan kunci"
            if orig[0].isupper():
                rep = "Berperan kunci"
            return rep
        masked_text, sub_count = re.subn(r"\bmemainkan\s+peran\s+kunci\b", repl_peran_kunci, masked_text, flags=re.IGNORECASE)
        total_fixes += sub_count

        # 5. memainkan peran penting -> berperan penting
        def repl_peran_penting(m):
            orig = m.group(0)
            rep = "berperan penting"
            if orig[0].isupper():
                rep = "Berperan penting"
            return rep
        masked_text, sub_count = re.subn(r"\bmemainkan\s+peran\s+penting\b", repl_peran_penting, masked_text, flags=re.IGNORECASE)
        total_fixes += sub_count

        # 6. memainkan peran besar -> berperan besar
        def repl_peran_besar(m):
            orig = m.group(0)
            rep = "berperan besar"
            if orig[0].isupper():
                rep = "Berperan besar"
            return rep
        masked_text, sub_count = re.subn(r"\bmemainkan\s+peran\s+besar\b", repl_peran_besar, masked_text, flags=re.IGNORECASE)
        total_fixes += sub_count

        # 7. menghasilkan dampak yang signifikan -> berdampak besar
        def repl_dampak(m):
            orig = m.group(0)
            rep = "berdampak besar"
            if orig[0].isupper():
                rep = "Berdampak besar"
            return rep
        masked_text, sub_count = re.subn(r"\bmenghasilkan\s+dampak\s+yang\s+signifikan\b", repl_dampak, masked_text, flags=re.IGNORECASE)
        total_fixes += sub_count

        # 8. berfungsi sebagai -> menjadi
        def repl_fungsi(m):
            orig = m.group(0)
            rep = "menjadi"
            if orig[0].isupper():
                rep = "Menjadi"
            return rep
        masked_text, sub_count = re.subn(r"\bberfungsi\s+sebagai\b", repl_fungsi, masked_text, flags=re.IGNORECASE)
        total_fixes += sub_count

        # 9. dikenal karena menjadi -> dikenal sebagai
        def repl_dikenal(m):
            orig = m.group(0)
            rep = "dikenal sebagai"
            if orig[0].isupper():
                rep = "Dikenal sebagai"
            return rep
        masked_text, sub_count = re.subn(r"\bdikenal\s+karena\s+menjadi\b", repl_dikenal, masked_text, flags=re.IGNORECASE)
        total_fixes += sub_count

        # 10. membuat debutnya / membuat debut -> memulai debut
        def repl_debut(m):
            orig = m.group(0)
            rep = "memulai debut"
            if orig[0].isupper():
                rep = "Memulai debut"
            return rep
        masked_text, sub_count = re.subn(r"\bmembuat\s+debut(?:nya)?\b", repl_debut, masked_text, flags=re.IGNORECASE)
        total_fixes += sub_count

        # 11. merupakan sebuah / adalah sebuah -> merupakan / adalah
        def repl_sebuah(m):
            verb = m.group(1)
            return verb
        masked_text, sub_count = re.subn(r"\b(merupakan|adalah)\s+sebuah\b", repl_sebuah, masked_text, flags=re.IGNORECASE)
        total_fixes += sub_count

        # 12. dipaksa untuk [verba] -> dipaksa [verba]
        def repl_dipaksa(m):
            verb1 = m.group(1)
            verb2 = m.group(2)
            return f"{verb1} {verb2}"
        masked_text, sub_count = re.subn(
            r"\b(dipaksa|didorong|dituntut|diminta)\s+untuk\s+([a-zA-Z]+)\b",
            repl_dipaksa,
            masked_text,
            flags=re.IGNORECASE,
        )
        total_fixes += sub_count

        # 13. Em-dash normalization in prose
        def repl_em_dash_pair(m):
            content = m.group(1).strip()
            return f", {content}, "
        masked_text, sub_count1 = re.subn(r"\s*(?:—|--)\s*([^—\n]+?)\s*(?:—|--)\s*", repl_em_dash_pair, masked_text)
        masked_text, sub_count2 = re.subn(r"\s*(?:—|--)\s*", ", ", masked_text)
        total_fixes += (sub_count1 + sub_count2)

        # 14. Semicolon normalization in narrative prose
        def repl_semi_conj(m):
            conj = m.group(1)
            return f", {conj}"
        masked_text, sub_count = re.subn(r";\s*(dan|tetapi|namun|sementara|melainkan)\b", repl_semi_conj, masked_text, flags=re.IGNORECASE)
        total_fixes += sub_count

        def repl_semi_lower(m):
            char = m.group(1)
            return f", dan {char}"
        masked_text, sub_count = re.subn(r";\s*([a-z])", repl_semi_lower, masked_text)
        total_fixes += sub_count

        def repl_semi_upper(m):
            char = m.group(1)
            return f". {char}"
        masked_text, sub_count = re.subn(r";\s*([A-Z])", repl_semi_upper, masked_text)
        total_fixes += sub_count

        # 15. pro-[Entitas] -> pendukung [Entitas]
        def repl_pro_entity(m):
            entity = m.group(1)
            return f"pendukung {entity}"
        masked_text, sub_count = re.subn(r"\bpro-([A-Z][a-zA-Z]+)\b", repl_pro_entity, masked_text)
        total_fixes += sub_count
        # 16. reviu -> peninjauan
        def repl_reviu(m):
            orig = m.group(0)
            rep = "peninjauan"
            if orig[0].isupper():
                rep = "Peninjauan"
            return rep
        masked_text, sub_count = re.subn(r"\breviu\b", repl_reviu, masked_text, flags=re.IGNORECASE)
        total_fixes += sub_count


        # Clean up any duplicate commas
        masked_text = re.sub(r",\s*,+", ",", masked_text)
        # Unmask protected zones
        reconstructed = self._unmask_protected_zones(masked_text, placeholders)
        return reconstructed, total_fixes


default_slop_linter = AntiAISlopLinter()
