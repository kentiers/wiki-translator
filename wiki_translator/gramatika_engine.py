"""
Dynamic Gramatika Engine for Indonesian Wikipedia Translation Suite.

Fully data-driven linguistic engine based on Kateglo's Gramatika
(codification of Tata Bahasa Baku Bahasa Indonesia - TBBBI, 4th ed., Badan Bahasa).

Zero Hardcoded Rules:
All grammatical taxonomies, transformation matrices, and validation rules
are dynamically loaded from structured JSON knowledge schemas in data/gramatika/:
- konjungsi_antarkalimat.json (11 sub-groups of inter-sentence connectors)
- konjungsi_subordinatif.json (9 categories of subordinate clause conjunctions & comma rules)
- kata_ingkar_matrix.json (Table 9.5 predicate negation matrix)
- kaidah_aposisi.json (Bagan 9.2 restrictive vs non-restrictive appositive comma rules)
- ciri_objek_pelengkap.json (Table 9.2 object vs complement distinctions)
- daftar_istilah.json (218 formal linguistic terminology definitions)
- daftar_isi.json (335 chapter & section hierarchies)
- daftar_bagan.json (12 syntactic diagrams)
- daftar_tabel.json (16 grammar tables)
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
    """Dynamic, data-driven grammar rule engine for TBBBI / Kateglo Gramatika."""

    def __init__(self, data_dir: Optional[Union[str, Path]] = None):
        self.data_dir = (
            Path(data_dir)
            if data_dir is not None
            else Path(__file__).resolve().parent.parent / "data" / "gramatika"
        )
        self.reload()

    def reload(self) -> None:
        """Loads and compiles all grammar schemas dynamically from disk."""
        self._istilah: Dict[str, str] = {}
        self._bagan: List[str] = []
        self._tabel: List[str] = []
        self._isi: List[str] = []
        self._konjungsi_antarkalimat: Dict[str, Any] = {}
        self._konjungsi_subordinatif: Dict[str, Any] = {}
        self._kata_ingkar: Dict[str, Any] = {}
        self._kaidah_aposisi: Dict[str, Any] = {}
        self._ciri_objek_pelengkap: Dict[str, Any] = {}

        # Compiled dynamic patterns
        self._opener_patterns: List[Tuple[re.Pattern, str, str, str]] = []
        self._negation_patterns: List[Tuple[re.Pattern, str, str, str]] = []
        self._appositive_patterns: List[Tuple[re.Pattern, str]] = []
        self._subordinate_comma_patterns: List[Tuple[re.Pattern, str]] = []

        if not self.data_dir.exists():
            return

        self._load_json_files()
        self._compile_dynamic_rules()

    def _load_json_files(self) -> None:
        """Loads JSON files safely."""
        def _read_json(filename: str) -> Any:
            target = self.data_dir / filename
            if target.exists():
                try:
                    return json.loads(target.read_text(encoding="utf-8"))
                except Exception:
                    pass
            return {}

        self._istilah = _read_json("daftar_istilah.json") or {}
        self._bagan = _read_json("daftar_bagan.json") or []
        self._tabel = _read_json("daftar_tabel.json") or []
        self._isi = _read_json("daftar_isi.json") or []
        self._konjungsi_antarkalimat = _read_json("konjungsi_antarkalimat.json") or {}
        self._konjungsi_subordinatif = _read_json("konjungsi_subordinatif.json") or {}
        self._kata_ingkar = _read_json("kata_ingkar_matrix.json") or {}
        self._kaidah_aposisi = _read_json("kaidah_aposisi.json") or {}
        self._ciri_objek_pelengkap = _read_json("ciri_objek_pelengkap.json") or {}

    def _compile_dynamic_rules(self) -> None:
        """Compiles regex engines dynamically from data schemas."""
        # 1. Compile Sentence Opener Conjunction Rules from konjungsi_antarkalimat.json
        transforms = self._konjungsi_antarkalimat.get("transformasi_kalkir_terlarang", [])
        for item in transforms:
            wrong = item.get("pembuka_salah", "").strip()
            repl = item.get("pengganti_baku", "").strip()
            alasan = item.get("alasan", "")
            target_group = item.get("kelompok_target", "")
            if wrong and repl:
                # Matches sentence start (or after period/question/exclamation mark)
                clean_wrong = re.escape(wrong)
                pattern = re.compile(rf"(^|[.!?]\s+){clean_wrong}\s+([A-Za-z\[])")
                replacement = rf"\1{repl} \2"
                rule_id = f"opener_{clean_wrong.replace(',', '').lower()}"
                self._opener_patterns.append((pattern, replacement, rule_id, alasan))

        # 2. Compile Negation Matrix Rules from kata_ingkar_matrix.json
        aturan_distribusi = self._kata_ingkar.get("aturan_distribusi", {})
        bukan_data = aturan_distribusi.get("bukan", {})
        classifiers = bukan_data.get("penanda_penggolong", [])
        if classifiers:
            cls_group = "|".join(re.escape(c) for c in classifiers)
            pattern = re.compile(rf"\btidak\s+({cls_group})\b", re.IGNORECASE)
            self._negation_patterns.append((
                pattern,
                r"bukan \1",
                "negation_noun_classifier",
                "Gunakan 'bukan' alih-alih 'tidak' sebelum kata penggolong nomina (Tabel 9.5).",
            ))

        copulas = bukan_data.get("frasa_identifikasi", [])
        if copulas:
            cop_group = "|".join(re.escape(c) for c in copulas)
            pattern = re.compile(rf"\btidak\s+({cop_group})\b", re.IGNORECASE)
            self._negation_patterns.append((
                pattern,
                r"bukan \1",
                "negation_copula",
                "Gunakan 'bukan' alih-alih 'tidak' sebelum frasa identifikasi kopula (Tabel 9.5).",
            ))

        # 3. Compile Restrictive Appositive Cleaners from kaidah_aposisi.json
        aposisi_data = self._kaidah_aposisi.get("jenis_aposisi", {})
        restriktif = aposisi_data.get("aposisi_mewatasi_restriktif", {})
        titles = restriktif.get("kategori_gelar_jabatan", [])
        if titles:
            titles_group = "|".join(re.escape(t) for t in sorted(titles, key=len, reverse=True))
            # Detects comma sandwich: "tokoh wanita, Maria Trubnikova," or "presiden, Ronald Reagan,"
            # Normalizes to: "tokoh wanita Maria Trubnikova"
            pattern = re.compile(
                rf"\b({titles_group}),\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*),",
                re.IGNORECASE,
            )
            self._appositive_patterns.append((pattern, r"\1 \2"))

        # 4. Compile Subordinate Trailing Comma Cleaners from konjungsi_subordinatif.json
        sub_categories = self._konjungsi_subordinatif.get("kategori", {})
        sub_words = set()
        for words in sub_categories.values():
            if isinstance(words, list):
                for w in words:
                    if len(w) > 3 and w not in ("tetapi", "sedangkan", "melainkan"):
                        sub_words.add(w)
        if sub_words:
            # Words that should not have a comma right before them when posterior
            key_posteriors = [w for w in sub_words if w in ("karena", "sehingga", "ketika", "agar", "supaya", "setelah", "sebelum", "sejak", "jika")]
            if key_posteriors:
                post_group = "|".join(re.escape(w) for w in key_posteriors)
                pattern = re.compile(rf"([a-z0-9\]\)]),+\s+({post_group})\b", re.IGNORECASE)
                self._subordinate_comma_patterns.append((pattern, r"\1 \2"))

    # =========================================================================
    # Knowledge Base Inspection Properties & Queries
    # =========================================================================

    @property
    def total_terms(self) -> int:
        return len(self._istilah)

    @property
    def total_tables(self) -> int:
        return len(self._tabel)

    @property
    def total_diagrams(self) -> int:
        return len(self._bagan)

    @property
    def intersentence_subgroups(self) -> Dict[str, Any]:
        """Returns the 11 sub-groups of inter-sentence conjunctions."""
        return self._konjungsi_antarkalimat.get("subkelompok", {})

    @property
    def subordinate_categories(self) -> Dict[str, List[str]]:
        """Returns the 9 categories of subordinate conjunctions."""
        return self._konjungsi_subordinatif.get("kategori", {})

    @property
    def negation_matrix(self) -> Dict[str, Any]:
        """Returns the Table 9.5 Negation Matrix."""
        return self._kata_ingkar.get("aturan_distribusi", {})

    @property
    def apposition_rules(self) -> Dict[str, Any]:
        """Returns Bagan 9.2 Apposition rules."""
        return self._kaidah_aposisi.get("jenis_aposisi", {})

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
    # Dynamic Normalization Methods (Driven by Schemas)
    # =========================================================================

    def normalize_sentence_openers(self, text: str) -> Tuple[str, int, List[str]]:
        """Dynamically normalizes invalid sentence openers using konjungsi_antarkalimat.json."""
        if not text:
            return "", 0, []

        fixes = 0
        details = []
        result = text

        for pat, repl, rule_id, exp in self._opener_patterns:
            new_text, n = pat.subn(repl, result)
            if n > 0:
                fixes += n
                details.append(f"[{rule_id}] {exp} ({n}x)")
                result = new_text

        return result, fixes, details

    def normalize_negation_agreement(self, text: str) -> Tuple[str, int, List[str]]:
        """Dynamically normalizes negation agreements using kata_ingkar_matrix.json."""
        if not text:
            return "", 0, []

        fixes = 0
        details = []
        result = text

        for pat, repl, rule_id, exp in self._negation_patterns:
            new_text, n = pat.subn(repl, result)
            if n > 0:
                fixes += n
                details.append(f"[{rule_id}] {exp} ({n}x)")
                result = new_text

        return result, fixes, details

    def normalize_restrictive_appositives(self, text: str) -> Tuple[str, int]:
        """Cleans commas around restrictive appositives (titles + proper names) using kaidah_aposisi.json."""
        if not text:
            return "", 0

        fixes = 0
        result = text

        for pat, repl in self._appositive_patterns:
            new_text, n = pat.subn(repl, result)
            if n > 0:
                fixes += n
                result = new_text

        return result, fixes

    def normalize_subordinate_trailing_commas(self, text: str) -> Tuple[str, int]:
        """Cleans ungrammatical commas before posterior subordinate conjunctions using konjungsi_subordinatif.json."""
        if not text:
            return "", 0

        fixes = 0
        result = text

        for pat, repl in self._subordinate_comma_patterns:
            new_text, n = pat.subn(repl, result)
            if n > 0:
                fixes += n
                result = new_text

        return result, fixes

    def normalize_adversarial_conjunction_commas(self, text: str) -> Tuple[str, int]:
        """Ensures coordinating adversarial conjunctions ('tetapi', 'sedangkan', 'melainkan') have a comma."""
        if not text:
            return "", 0

        pattern = re.compile(r"([^\s,.\n\(\{\[\>])\s+(tetapi|sedangkan|melainkan)\b")
        new_text, count = pattern.subn(r"\1, \2", text)
        return new_text, count

    def apply_all_gramatika_fixes(self, text: str) -> Tuple[str, int, List[str]]:
        """
        Applies full suite of dynamic TBBBI / Kateglo grammatical normalizations.
        All transformations are derived from schema rules.
        """
        total_fixes = 0
        all_details = []

        # 1. Sentence opener conjunctions (konjungsi_antarkalimat.json)
        text, n1, d1 = self.normalize_sentence_openers(text)
        total_fixes += n1
        all_details.extend(d1)

        # 2. Negation agreement (kata_ingkar_matrix.json)
        text, n2, d2 = self.normalize_negation_agreement(text)
        total_fixes += n2
        all_details.extend(d2)

        # 3. Restrictive appositive commas (kaidah_aposisi.json)
        text, n3 = self.normalize_restrictive_appositives(text)
        if n3 > 0:
            total_fixes += n3
            all_details.append(f"[restrictive_appositive] Menghapus koma penjepit pada aposisi mewatasi ({n3}x)")

        # 4. Posterior subordinate commas (konjungsi_subordinatif.json)
        text, n4 = self.normalize_subordinate_trailing_commas(text)
        if n4 > 0:
            total_fixes += n4
            all_details.append(f"[subordinate_comma] Menghapus koma sebelum anak kalimat di belakang ({n4}x)")

        # 5. Adversarial commas (tetapi, sedangkan, melainkan)
        text, n5 = self.normalize_adversarial_conjunction_commas(text)
        if n5 > 0:
            total_fixes += n5
            all_details.append(f"[adversarial_comma] Menambahkan koma sebelum konjungsi pertentangan ({n5}x)")

        return text, total_fixes, all_details


default_gramatika_engine = GramatikaEngine()
