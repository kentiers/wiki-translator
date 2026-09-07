"""Deterministic source-vs-draft consistency checks for editorial review."""

from dataclasses import dataclass, field
import re
from typing import List, Optional

from .entity_grounding import EntityGroundingAuditor, default_entity_grounding_auditor


@dataclass
class FactualConsistencyResult:
    source_numbers: List[str] = field(default_factory=list)
    draft_numbers: List[str] = field(default_factory=list)
    missing_numbers: List[str] = field(default_factory=list)
    source_references: int = 0
    draft_references: int = 0
    dropped_entities: List[str] = field(default_factory=list)
    phantom_entities: List[str] = field(default_factory=list)
    attribution_warnings: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.missing_numbers and not self.warnings

class FactualConsistencyAuditor:
    """Flags source drift, entity mutations, and attribution mismatches across all topics."""

    _NUMBER = re.compile(r"(?<![\w])\d+(?:[.,]\d+)?(?:%|\s*(?:BC|AD|SM|M|juta|miliar)\b)?", re.I)
    _POLARITY_PAIRS = (
        (re.compile(r"\boppose(?:d|s)?\b", re.I), re.compile(r"\b(?:mendukung|mendukungnya|menyokong)\b", re.I), "opposed → mendukung"),
        (re.compile(r"\bsupport(?:ed|s)?\b", re.I), re.compile(r"\b(?:menentang|menolak)\b", re.I), "supported → menentang/menolak"),
    )
    _ID_NUMBER_WORDS = {
        "satu": "1", "dua": "2", "tiga": "3", "empat": "4", "lima": "5",
        "enam": "6", "tujuh": "7", "delapan": "8", "sembilan": "9", "sepuluh": "10"
    }
    def __init__(self, entity_auditor: Optional[EntityGroundingAuditor] = None) -> None:
        self.entity_auditor = entity_auditor or default_entity_grounding_auditor


    @staticmethod
    def _claim_text(wikitext: str) -> str:
        """Strip maintenance templates and reference metadata to isolate narrative claims."""
        text = wikitext or ""
        # Strip self-closing refs first
        text = re.sub(r"<ref\b[^>]*\/>", "", text)
        # Strip full reference blocks
        text = re.sub(r"<ref\b[^>]*>[\s\S]*?<\/ref>", "", text)
        # Strip reference page templates ({{rp|...}})
        text = re.sub(r"\{\{rp\|[^{}]*\}\}", "", text, flags=re.I)
        # Strip maintenance and date metadata templates
        text = re.sub(
            r"\{\{\s*(?:short description|featured article|good article|use dmy dates|use mdy dates|use oxford spelling)\b[\s\S]*?\}\}",
            "",
            text,
            flags=re.I,
        )
        return text
    def audit(
        self, source_wikitext: str, draft_wikitext: str, topic: Optional[str] = None
    ) -> FactualConsistencyResult:
        source_clean = self._claim_text(source_wikitext)
        draft_clean = self._claim_text(draft_wikitext)

        # Map Indonesian number words to digits according to EYD V prose standards
        for word, digit in self._ID_NUMBER_WORDS.items():
            draft_clean = re.sub(rf"\b{word}\b", digit, draft_clean, flags=re.I)

        source_numbers = self._NUMBER.findall(source_clean)
        draft_numbers = self._NUMBER.findall(draft_clean)
        remaining = list(draft_numbers)
        missing: List[str] = []
        def _core_num(s: str) -> str:
            m = re.search(r"\d+(?:[.,]\d+)?", s)
            return m.group(0).replace(",", ".") if m else s

        def _matches_number(val: str, candidates: List[str]) -> bool:
            val_core = _core_num(val)
            for i, cand in enumerate(candidates):
                if _core_num(cand) == val_core:
                    candidates.pop(i)
                    return True
            return False

        for value in source_numbers:
            if not _matches_number(value, remaining):
                missing.append(value)
        source_refs = len(re.findall(r"<ref\b", source_wikitext or "", re.I))
        draft_refs = len(re.findall(r"<ref\b", draft_wikitext or "", re.I))
        warnings: List[str] = []
        if missing:
            warnings.append("Angka/tanggal sumber tidak ditemukan di draf: " + ", ".join(missing[:12]))
        if source_refs and draft_refs < source_refs:
            warnings.append(f"Jumlah referensi berkurang: sumber {source_refs}, draf {draft_refs}")
        # A conservative warning for simple affirmative clauses only. Article-
        # wide keyword matching confuses different actors and different claims.
        source_text, draft_text = source_wikitext or "", draft_wikitext or ""
        simple = all(len(t.split()) < 15 and len(re.findall(r'[.!?]', t)) <= 1 for t in (source_text, draft_text))
        qualified = re.search(r'\b(not|never|no|but|and|nor|tidak|bukan|belum|tanpa|dan|tetapi|namun)\b', source_text + ' ' + draft_text, re.I)
        if simple and not qualified:
            for source_pattern, opposite_pattern, label in self._POLARITY_PAIRS:
                if source_pattern.search(source_text) and opposite_pattern.search(draft_text):
                    warnings.append(f"Kemungkinan pembalikan makna: {label}")
        # Entity & claim grounding check across all topics
        entity_res = self.entity_auditor.audit(source_wikitext, draft_wikitext, topic=topic)
        dropped_entities = entity_res.dropped_entities
        phantom_entities = entity_res.phantom_entities
        attribution_warnings = entity_res.attribution_warnings
        warnings.extend(entity_res.warnings)

        return FactualConsistencyResult(
            source_numbers=source_numbers,
            draft_numbers=draft_numbers,
            missing_numbers=missing,
            source_references=source_refs,
            draft_references=draft_refs,
            dropped_entities=dropped_entities,
            phantom_entities=phantom_entities,
            attribution_warnings=attribution_warnings,
            warnings=warnings,
        )


default_factual_auditor = FactualConsistencyAuditor()
