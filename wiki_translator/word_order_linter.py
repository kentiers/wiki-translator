"""
Indonesian Syntactic Word-Order & Constituent Arrangement Engine (SusunanKataEngine).

Enforces authoritative Indonesian syntactic and word-order principles (TBBBI & Hukum D-M):
1. Hukum D-M (Diterangkan - Menerangkan):
   Ensures head nouns precede modifiers, detecting English noun-adjunct calques
   (e.g. 'the then president' -> 'kemudian presiden' [INVALID] -> 'presiden saat itu' [BAKU]).
2. Aspect - Modality - Negation Ordering:
   Enforces TBBBI canonical verb modifier sequences:
   'akan tidak' -> 'tidak akan'; 'bisa belum' -> 'belum bisa'.
3. Declarative Complement Ordering ('bahwa' vs 'yang'):
   Replaces unidiomatic relative 'yang' with complementizer 'bahwa' after reporting verbs
   (e.g. 'menyatakan yang' -> 'menyatakan bahwa').
4. Plural-Quantifier Word Order (Anti-Pleonasme):
   Prevents redundant duplication after quantifiers ('para menteri-menteri' -> 'para menteri').
5. Passive Prepositional Inversions:
   Prevents unidiomatic agent fronting before passive verbs.
"""

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union


@dataclass
class WordOrderIssue:
    category: str
    line_number: int
    matched_text: str
    suggested_fix: str
    explanation: str
    severity: str = "MEDIUM"


@dataclass
class WordOrderAuditResult:
    passed: bool
    score: int  # 0 - 100
    issues: List[WordOrderIssue] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)


class WordOrderLinter:
    """Dynamic, data-driven Indonesian word order and constituent linter."""

    def __init__(self, data_file: Optional[Union[str, Path]] = None):
        self.data_file = (
            Path(data_file)
            if data_file is not None
            else Path(__file__).resolve().parent.parent / "data" / "susunan_kata.json"
        )
        self.reload()

    def reload(self) -> None:
        """Loads and compiles word order patterns from data/susunan_kata.json."""
        self._raw_data: Dict[str, Any] = {}
        self._rules: List[Tuple[str, re.Pattern, str, str, str]] = []

        if not self.data_file.exists():
            return

        try:
            self._raw_data = json.loads(self.data_file.read_text(encoding="utf-8"))
        except Exception:
            self._raw_data = {}

        aturan_dict = self._raw_data.get("aturan_susunan_kata", {})
        for cat_key, cat_info in aturan_dict.items():
            if not isinstance(cat_info, dict):
                continue

            patterns_list = (
                cat_info.get("pola_inversi_rusak", [])
                or cat_info.get("pola_urutan_rancu", [])
                or cat_info.get("pola_salah_letak", [])
                or cat_info.get("pola_pleonastis", [])
                or cat_info.get("pola_inversi", [])
            )

            for item in patterns_list:
                pola = item.get("pola")
                anjuran = item.get("anjuran", "")
                penjelasan = item.get("penjelasan", "")
                if pola:
                    try:
                        compiled = re.compile(pola, re.IGNORECASE)
                        self._rules.append((cat_key, compiled, anjuran, penjelasan, "HIGH" if "negasi" in cat_key else "MEDIUM"))
                    except Exception:
                        pass

    def audit_word_order(self, text: str) -> WordOrderAuditResult:
        """Audits wikitext or prose for unnatural word order and syntactic inversions."""
        if not text:
            return WordOrderAuditResult(passed=True, score=100)

        issues: List[WordOrderIssue] = []
        lines = text.splitlines()

        for line_idx, line in enumerate(lines, 1):
            stripped = line.strip()
            # Skip pure template lines, categories, or tables
            if not stripped or stripped.startswith(("{|", "|", "!", "[[Kategori:", "[[Category:", "<!--")):
                continue

            # Strip protected tags like <ref>...</ref> or templates for prose checking
            clean_line = re.sub(r"<ref\b[^>]*>[\s\S]*?</ref>", "", line)
            clean_line = re.sub(r"<ref\b[^>]*/>", "", clean_line)
            clean_line = re.sub(r"\{\{[^{}]*\}\}", "", clean_line)

            for cat_key, pat, anjuran, penjelasan, severity in self._rules:
                for match in pat.finditer(clean_line):
                    matched_str = match.group(0)
                    issues.append(
                        WordOrderIssue(
                            category=cat_key,
                            line_number=line_idx,
                            matched_text=matched_str,
                            suggested_fix=anjuran,
                            explanation=penjelasan,
                            severity=severity,
                        )
                    )

        deductions = len(issues) * 5
        score = max(0, 100 - deductions)
        suggestions = [f"L{iss.line_number}: {iss.explanation} (pada '{iss.matched_text}') -> Saran: {iss.suggested_fix}" for iss in issues]

        return WordOrderAuditResult(
            passed=len(issues) == 0,
            score=score,
            issues=issues,
            suggestions=suggestions,
        )

    def auto_fix_word_order(self, text: str) -> Tuple[str, int, List[str]]:
        """Safely fixes unambiguous word-order inversions (e.g. 'akan tidak' -> 'tidak akan')."""
        if not text:
            return "", 0, []

        fixes = 0
        details = []
        result = text

        # 1. Aspek - Negasi order: 'akan tidak' -> 'tidak akan'
        for wrong, correct in [
            (r"\bakan\s+tidak\b", "tidak akan"),
            (r"\bbisa\s+belum\b", "belum bisa"),
            (r"\bdapat\s+telah\b", "telah dapat"),
            (r"\bmenyatakan\s+yang\s+(dia|ia|mereka|pemerintah|pihak)\b", r"menyatakan bahwa \1"),
            (r"\bmengumumkan\s+yang\s+(dia|ia|mereka|pemerintah|pihak)\b", r"mengumumkan bahwa \1"),
        ]:
            pat = re.compile(wrong, re.IGNORECASE)
            new_text, n = pat.subn(correct, result)
            if n > 0:
                fixes += n
                details.append(f"[susunan_kata] Memperbaiki susunan pewatas: '{wrong}' -> '{correct}' ({n}x)")
                result = new_text

        # 2. Plural quantifier duplication: 'para menteri-menteri' -> 'para menteri'
        for quant in ("para", "berbagai", "semua"):
            p_dup = re.compile(rf"\b({quant})\s+([a-zA-Z]+)-\2\b", re.IGNORECASE)
            def repl_quant(m: re.Match) -> str:
                return f"{m.group(1)} {m.group(2)}"
            new_text, n = p_dup.subn(repl_quant, result)
            if n > 0:
                fixes += n
                details.append(f"[susunan_kata] Menghilangkan pleonasme reduplikasi setelah '{quant}' ({n}x)")
                result = new_text

        # 3. Stacked introductory adverbials comma clutter:
        # e.g. 'Dahulu kala, di...' -> 'Dahulu kala di...'
        p_intro = re.compile(
            r"(^|[.!?\n]\s*)\b(Dahulu\s+kala|Pada\s+tahun\s+\d{4}|Pada\s+[A-Za-z]+\s+\d{4}|Setelah\s+itu|Sebelumnya|Kini|Awalnya|Mulanya|Sekitar\s+tahun\s+\d{4}|Di\s+kemudian\s+hari),\s+((?:di|ke|dari|pada|dalam|selama)\s+[^,]{3,50}),",
            re.IGNORECASE,
        )
        def repl_intro(m: re.Match) -> str:
            return f"{m.group(1)}{m.group(2)} {m.group(3)},"
        new_text, n = p_intro.subn(repl_intro, result)
        if n > 0:
            fixes += n
            details.append(f"[susunan_kata] Menghilangkan koma cegukan pada keterangan pembuka bertumpuk ({n}x)")
            result = new_text

        return result, fixes, details


# Global default instance
default_word_order_linter = WordOrderLinter()
