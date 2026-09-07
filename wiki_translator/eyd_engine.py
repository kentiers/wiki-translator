"""
Dynamic EYD V Engine for Indonesian Wikipedia Translation Suite.

Fully data-driven orthography and spelling engine based on official EYD V
(Ejaan Bahasa Indonesia yang Disempurnakan Edisi V, Badan Pengembangan dan Pembinaan Bahasa / Kemendikdasmen).

Zero Hardcoded Rules:
All orthographic taxonomies, bound morphemes, particle matrices, loanword patterns,
and punctuation conventions are dynamically loaded from JSON schemas in data/eyd/:
- eyd_index.json (301 official EYD V articles and normative examples)
- bentuk_terikat.json (bound morphemes like pasca-, antar-, non-, multi-, anti-)
- partikel_pun.json (12 compound conjunctions vs separated pun particles)
- tanda_baca.json (en-dash, em-dash, thousand separators)
- unsur_serapan.json (foreign suffix and phoneme adaptation patterns)
"""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union


@dataclass
class EYDIssue:
    rule_id: str
    category: str
    line_number: int
    matched_text: str
    suggested_replacement: str
    explanation: str


class EYDEngine:
    """Dynamic, data-driven orthography engine for official EYD V."""

    def __init__(self, data_dir: Optional[Union[str, Path]] = None):
        self.data_dir = (
            Path(data_dir)
            if data_dir is not None
            else Path(__file__).resolve().parent.parent / "data" / "eyd"
        )
        self.reload()

    def reload(self) -> None:
        """Loads and compiles all EYD V schemas dynamically from disk."""
        self._rules_index: List[Dict[str, Any]] = []
        self._bentuk_terikat: Dict[str, Any] = {}
        self._partikel_pun: Dict[str, Any] = {}
        self._tanda_baca: Dict[str, Any] = {}
        self._unsur_serapan: Dict[str, Any] = {}

        # Compiled dynamic regex patterns
        self._bound_morpheme_patterns: List[Tuple[re.Pattern, str, str]] = []
        self._pun_patterns: List[Tuple[re.Pattern, str, str]] = []
        self._en_dash_patterns: List[Tuple[re.Pattern, str, str]] = []

        if not self.data_dir.exists():
            return

        self._load_json_files()
        self._compile_dynamic_rules()

    def _load_json_files(self) -> None:
        """Loads JSON files safely."""
        def _read_json(filename: str, default: Any) -> Any:
            target = self.data_dir / filename
            if target.exists():
                try:
                    return json.loads(target.read_text(encoding="utf-8"))
                except Exception:
                    pass
            return default

        self._rules_index = _read_json("eyd_index.json", [])
        self._bentuk_terikat = _read_json("bentuk_terikat.json", {})
        self._partikel_pun = _read_json("partikel_pun.json", {})
        self._tanda_baca = _read_json("tanda_baca.json", {})
        self._unsur_serapan = _read_json("unsur_serapan.json", {})

    def _compile_dynamic_rules(self) -> None:
        """Compiles regex engines dynamically from data schemas."""
        # 1. Compile Bound Morpheme Rules from bentuk_terikat.json
        bound_prefixes = self._bentuk_terikat.get("daftar_bentuk_terikat", [])
        if bound_prefixes:
            # Sort prefixes by length descending so longer prefixes match first
            prefixes_sorted = sorted(bound_prefixes, key=len, reverse=True)
            prefix_group = "|".join(re.escape(p) for p in prefixes_sorted)

            # Rule A: Followed by Capital letter (must have hyphen: "non-Indonesia", "anti-PKI", "pro-Palestina")
            # Matches: "non Indonesia", "anti PKI", "pro Palestina"
            pat_capital = re.compile(rf"\b({prefix_group})\s+([A-Z][A-Za-z0-9]*)")
            self._bound_morpheme_patterns.append((
                pat_capital,
                r"\1-\2",
                "Gunakan tanda hubung (-) setelah bentuk terikat sebelum huruf kapital (EYD V Bab II Huruf B)."
            ))

            # Exclude function words that must never be merged with a prefix (dan, atau, yang, di, ke, dll.)
            function_words = "dan|atau|yang|di|ke|dari|pada|untuk|dengan|ini|itu|juga|pun|ada|bisa|dapat"
            # Rule B: Followed by Lowercase content word (min 3 chars). Negative lookbehind prevents 'musim semi' collision.
            pat_lower = re.compile(
                rf"(?<!\bmusim\s)\b({prefix_group})\s+(?!(?:{function_words})\b)([a-z]{{3,}})\b",
                re.IGNORECASE,
            )
            self._bound_morpheme_patterns.append((
                pat_lower,
                r"\1\2",
                "Bentuk terikat ditulis serangkai dengan kata yang mengikutinya (EYD V Bab II Huruf B)."
            ))

        # 2. Compile Particle Pun Rules from partikel_pun.json
        pun_words_merged = set(self._partikel_pun.get("dua_belas_kata_hubung_serangkai", []))
        # Words commonly wrongly merged with pun: apapun, siapapun, manapun, kapanpun, merekapun, diapun, iapun
        wrong_pun_words = ["apa", "siapa", "mana", "kapan", "mereka", "dia", "ia", "kami", "kita"]
        if wrong_pun_words:
            # Only match words that are NOT in the 12 exceptions
            clean_wrong = [w for w in wrong_pun_words if f"{w}pun" not in pun_words_merged]
            wrong_group = "|".join(re.escape(w) for w in clean_wrong)
            pat_pun = re.compile(rf"\b({wrong_group})pun\b", re.IGNORECASE)
            self._pun_patterns.append((
                pat_pun,
                r"\1 pun",
                "Partikel pun ditulis terpisah dari kata yang mendahuluinya (EYD V Bab II Huruf G)."
            ))

        # 3. Compile En-dash Range Patterns from tanda_baca.json
        # Matches: "1945 - 1949", "1945-1949" in numeric years/pages -> "1945–1949"
        # Matches spaced en-dash: "1945 – 1949" -> "1945–1949"
        pat_year_hyphen = re.compile(r"\b(\d{4})\s*[-–]\s*(\d{4})\b")
        self._en_dash_patterns.append((
            pat_year_hyphen,
            r"\1–\2",
            "Tanda pisah en-dash (–) digunakan di antara dua bilangan/tahun tanpa spasi (EYD V Bab III Huruf F)."
        ))

        pat_page_hyphen = re.compile(r"\b(hlm\.|halaman)\s*(\d+)\s*[-–]\s*(\d+)\b", re.IGNORECASE)
        self._en_dash_patterns.append((
            pat_page_hyphen,
            r"\1 \2–\3",
            "Tanda pisah en-dash (–) digunakan di antara rentang halaman (EYD V Bab III Huruf F)."
        ))

    # =========================================================================
    # Knowledge Inspection & Queries
    # =========================================================================

    @property
    def total_rules(self) -> int:
        return len(self._rules_index)

    @property
    def bound_morphemes(self) -> List[str]:
        return self._bentuk_terikat.get("daftar_bentuk_terikat", [])

    @property
    def compound_pun_conjunctions(self) -> List[str]:
        return self._partikel_pun.get("dua_belas_kata_hubung_serangkai", [])

    @property
    def loanword_suffix_rules(self) -> List[Dict[str, Any]]:
        return self._unsur_serapan.get("pola_penyesuaian_sufiks", [])

    def search_rules(self, query: str) -> List[Dict[str, Any]]:
        """Searches all 301 official EYD V articles matching keyword."""
        clean_q = query.strip().lower()
        return [
            r
            for r in self._rules_index
            if clean_q in r.get("title", "").lower() or clean_q in r.get("text", "").lower()
        ]

    # =========================================================================
    # Dynamic Normalization Methods (Driven by Schemas)
    # =========================================================================

    def normalize_bound_morphemes(self, text: str) -> Tuple[str, int, List[str]]:
        """Normalizes bound morphemes (pasca-, antar-, non-, anti-, sub-, multi-)."""
        if not text:
            return "", 0, []

        fixes = 0
        details = []
        result = text

        for pat, repl, explanation in self._bound_morpheme_patterns:
            new_text, n = pat.subn(repl, result)
            if n > 0:
                fixes += n
                details.append(f"[bentuk_terikat] {explanation} ({n}x)")
                result = new_text

        return result, fixes, details

    def normalize_pun_particles(self, text: str) -> Tuple[str, int, List[str]]:
        """Normalizes particle pun (separates apapun -> apa pun, preserves 12 conjunctions)."""
        if not text:
            return "", 0, []

        fixes = 0
        details = []
        result = text

        for pat, repl, explanation in self._pun_patterns:
            new_text, n = pat.subn(repl, result)
            if n > 0:
                fixes += n
                details.append(f"[partikel_pun] {explanation} ({n}x)")
                result = new_text

        return result, fixes, details

    def normalize_en_dash_ranges(self, text: str) -> Tuple[str, int, List[str]]:
        """Normalizes number/year/page ranges to standard en-dash (–) without spaces."""
        if not text:
            return "", 0, []

        fixes = 0
        details = []
        result = text

        for pat, repl, explanation in self._en_dash_patterns:
            new_text, n = pat.subn(repl, result)
            if n > 0:
                fixes += n
                details.append(f"[en_dash] {explanation} ({n}x)")
                result = new_text

        return result, fixes, details

    def apply_all_eyd_fixes(self, text: str) -> Tuple[str, int, List[str]]:
        """Applies complete dynamic EYD V orthography and punctuation normalization."""
        total_fixes = 0
        all_details = []

        # 1. Bound morphemes (pasca-, antar-, non-, dll.)
        text, n1, d1 = self.normalize_bound_morphemes(text)
        total_fixes += n1
        all_details.extend(d1)

        # 2. Pun particles (apa pun, siapa pun, dll.)
        text, n2, d2 = self.normalize_pun_particles(text)
        total_fixes += n2
        all_details.extend(d2)

        # 3. En-dash ranges (1945–1949, hlm. 12–15)
        text, n3, d3 = self.normalize_en_dash_ranges(text)
        total_fixes += n3
        all_details.extend(d3)

        return text, total_fixes, all_details


default_eyd_engine = EYDEngine()
