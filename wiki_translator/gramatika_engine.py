"""
Gramatika Engine for Indonesian Wikipedia Translation Suite.

Operationalizes the foundational grammar rules from Kateglo's Gramatika
(codification of Tata Bahasa Baku Bahasa Indonesia - TBBBI, 4th ed., Badan Bahasa):
1. Chapter X & Table 8.1: Conjunction classification and sentence opener boundaries.
   - Forbidden intra-sentence conjunctions at sentence start (e.g. 'Sehingga,', 'Sedangkan,', 'Dan,').
   - Automatic transformation to valid inter-sentence discourse connectors (e.g. 'Akibatnya,', 'Sementara itu,', 'Selain itu,').
2. Chapter IX & Table 9.5: Negation agreements (Kata Ingkar).
   - 'bukan' for nouns/prepositional phrases vs 'tidak' for verbs/adjectives.
3. Chapter VIII & Table 9.2: Adversarial coordinating conjunction comma enforcement ('tetapi', 'sedangkan', 'melainkan').
4. Linguistic Terminology Knowledge Base (218 terms, 16 tables, 12 charts, 335 chapters).
"""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union


@dataclass
class GramatikaIssue:
    rule_id: str
    category: str
    line_number: int
    matched_text: str
    suggested_replacement: str
    explanation: str


class GramatikaEngine:
    """Rule engine and query interface for Kateglo Gramatika (TBBBI)."""

    def __init__(self, data_dir: Optional[Union[str, Path]] = None):
        self.data_dir = (
            Path(data_dir)
            if data_dir is not None
            else Path(__file__).resolve().parent.parent / "data" / "gramatika"
        )
        self._istilah: Dict[str, str] = {}
        self._bagan: List[str] = []
        self._tabel: List[str] = []
        self._isi: List[str] = []
        self._load_knowledge_base()

    def _load_knowledge_base(self) -> None:
        """Loads serialized Gramatika knowledge files from disk."""
        if not self.data_dir.exists():
            return

        istilah_file = self.data_dir / "daftar_istilah.json"
        if istilah_file.exists():
            try:
                self._istilah = json.loads(istilah_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        bagan_file = self.data_dir / "daftar_bagan.json"
        if bagan_file.exists():
            try:
                self._bagan = json.loads(bagan_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        tabel_file = self.data_dir / "daftar_tabel.json"
        if tabel_file.exists():
            try:
                self._tabel = json.loads(tabel_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        isi_file = self.data_dir / "daftar_isi.json"
        if isi_file.exists():
            try:
                self._isi = json.loads(isi_file.read_text(encoding="utf-8"))
            except Exception:
                pass

    @property
    def total_terms(self) -> int:
        return len(self._istilah)

    @property
    def total_tables(self) -> int:
        return len(self._tabel)

    @property
    def total_diagrams(self) -> int:
        return len(self._bagan)

    def get_term_definition(self, term: str) -> Optional[str]:
        """Retrieves official grammatical definition for a linguistic term."""
        return self._istilah.get(term.strip().lower())

    def search_terms(self, query: str) -> Dict[str, str]:
        """Searches linguistic terms and definitions matching query."""
        clean_q = query.strip().lower()
        return {
            k: v
            for k, v in self._istilah.items()
            if clean_q in k.lower() or clean_q in v.lower()
        }

    # =========================================================================
    # Rule Enforcers (Derived from TBBBI / Kateglo Gramatika)
    # =========================================================================

    def normalize_sentence_openers(self, text: str) -> Tuple[str, int, List[str]]:
        """
        Chapter X / Table 8.1: Replaces forbidden intra-sentence conjunctions
        erroneously placed as standalone sentence openers:
        - 'Sehingga, X' -> 'Akibatnya, X'
        - 'Sedangkan, X' -> 'Sementara itu, X'
        - 'Dan, X' -> 'Selain itu, X'
        - 'Atau, X' -> 'Di sisi lain, X'
        """
        if not text:
            return "", 0, []

        fixes = 0
        details = []

        conjunction_opener_rules = [
            (
                re.compile(r"(^|[.!?]\s+)Sehingga,\s+([A-Za-z\[])"),
                r"\1Akibatnya, \2",
                "sehingga_opener",
                "'Sehingga' adalah konjungsi intrakalimat; gunakan 'Akibatnya,' di awal kalimat.",
            ),
            (
                re.compile(r"(^|[.!?]\s+)Sedangkan,\s+([A-Za-z\[])"),
                r"\1Sementara itu, \2",
                "sedangkan_opener",
                "'Sedangkan' adalah konjungsi intrakalimat; gunakan 'Sementara itu,' di awal kalimat.",
            ),
            (
                re.compile(r"(^|[.!?]\s+)Dan,\s+([A-Za-z\[])"),
                r"\1Selain itu, \2",
                "dan_opener",
                "'Dan' adalah konjungsi koordinatif; gunakan 'Selain itu,' di awal kalimat.",
            ),
            (
                re.compile(r"(^|[.!?]\s+)Atau,\s+([A-Za-z\[])"),
                r"\1Di sisi lain, \2",
                "atau_opener",
                "'Atau' adalah konjungsi koordinatif; gunakan 'Di sisi lain,' di awal kalimat.",
            ),
        ]

        result = text
        for pat, repl, rule_id, exp in conjunction_opener_rules:
            new_text, n = pat.subn(repl, result)
            if n > 0:
                fixes += n
                details.append(f"[{rule_id}] {exp} ({n}x)")
                result = new_text

        return result, fixes, details

    def normalize_negation_agreement(self, text: str) -> Tuple[str, int, List[str]]:
        """
        Chapter IX / Table 9.5 (Kata Ingkar):
        - 'bukan' negates nouns and prepositional phrases (e.g. 'bukan sebuah negara').
        - 'tidak' negates verbs and adjectives (e.g. 'tidak setuju').
        Corrects calqued errors like 'tidak sebuah...', 'tidak seorang...', 'tidak merupakan'.
        """
        if not text:
            return "", 0, []

        fixes = 0
        details = []

        negation_rules = [
            (
                re.compile(r"\btidak\s+(sebuah|suatu|seorang|seekor|sebutir|sebelah|sepotong)\b", re.IGNORECASE),
                r"bukan \1",
                "negation_noun_classifier",
                "Gunakan 'bukan' alih-alih 'tidak' sebelum kata penggolong nomina.",
            ),
            (
                re.compile(r"\btidak\s+merupakan\b", re.IGNORECASE),
                "bukan merupakan",
                "negation_copula",
                "Gunakan 'bukan merupakan' alih-alih 'tidak merupakan' (Tabel 9.5).",
            ),
        ]

        result = text
        for pat, repl, rule_id, exp in negation_rules:
            new_text, n = pat.subn(repl, result)
            if n > 0:
                fixes += n
                details.append(f"[{rule_id}] {exp} ({n}x)")
                result = new_text

        return result, fixes, details

    def normalize_adversarial_conjunction_commas(self, text: str) -> Tuple[str, int]:
        """
        Chapter VIII: Ensures coordinating adversarial conjunctions
        ('tetapi', 'sedangkan', 'melainkan') are preceded by a comma within a sentence.
        """
        if not text:
            return "", 0

        pattern = re.compile(r"([^\s,.\n\(\{\[\>])\s+(tetapi|sedangkan|melainkan)\b")
        new_text, count = pattern.subn(r"\1, \2", text)
        return new_text, count

    def apply_all_gramatika_fixes(self, text: str) -> Tuple[str, int, List[str]]:
        """
        Applies full suite of TBBBI / Kateglo grammatical normalizations.
        Returns (repaired_text, total_fixes_count, list_of_explanations).
        """
        total_fixes = 0
        all_details = []

        # 1. Sentence opener conjunctions
        text, n1, d1 = self.normalize_sentence_openers(text)
        total_fixes += n1
        all_details.extend(d1)

        # 2. Negation agreement (bukan vs tidak)
        text, n2, d2 = self.normalize_negation_agreement(text)
        total_fixes += n2
        all_details.extend(d2)

        # 3. Adversarial commas
        text, n3 = self.normalize_adversarial_conjunction_commas(text)
        if n3 > 0:
            total_fixes += n3
            all_details.append(f"[adversarial_comma] Menambahkan koma sebelum konjungsi pertentangan ({n3}x)")

        return text, total_fixes, all_details


default_gramatika_engine = GramatikaEngine()
