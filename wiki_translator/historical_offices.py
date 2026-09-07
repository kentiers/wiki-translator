"""
Dynamic Historical Offices and Titles Manager for Indonesian Wikipedia Translation Suite.

Loads and operationalizes bureaucratic, imperial, and military rank taxonomies from
data/historical_offices.json (zero hardcoding):
1. Maps ancient administrative titles (e.g. Han Dynasty, Roman Republic/Empire, Ottoman Empire).
2. Prevents literal translationese (e.g. converting 'Grand Administrator' into 'Gubernur Komanderi',
   not modern desk clerk 'Administrator').
3. Dispatches canonical Indonesian titles and historical context notes directly into translation pipelines.
"""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union


@dataclass
class OfficeMatch:
    key: str
    original_title: str
    canonical_id_title: str
    explanation: str
    matched_trigger: str


class HistoricalOfficesManager:
    """Dynamic, schema-driven manager for historical bureaucratic and military titles."""

    def __init__(self, data_file: Optional[Union[str, Path]] = None):
        self.data_file = (
            Path(data_file)
            if data_file is not None
            else Path(__file__).resolve().parent.parent / "data" / "historical_offices.json"
        )
        self.reload()

    def reload(self) -> None:
        """Loads and compiles office taxonomy dynamically from disk."""
        self._raw_data: Dict[str, Any] = {}
        self._offices: Dict[str, Dict[str, Any]] = {}
        self._triggers: List[Tuple[str, str, List[re.Pattern], Dict[str, Any]]] = []

        if not self.data_file.exists():
            return

        try:
            self._raw_data = json.loads(self.data_file.read_text(encoding="utf-8"))
        except Exception:
            self._raw_data = {}

        peradaban = self._raw_data.get("peradaban", {})
        for civ_name, civ_dict in peradaban.items():
            if isinstance(civ_dict, dict):
                for off_key, info in civ_dict.items():
                    if isinstance(info, dict):
                        self._offices[off_key] = info
                        triggers = info.get("en_triggers", [])
                        compiled_patterns = [
                            re.compile(r"\b" + re.escape(t.strip()) + r"\b", re.IGNORECASE)
                            for t in triggers
                            if t.strip()
                        ]
                        if compiled_patterns:
                            self._triggers.append((off_key, info.get("id_baku", ""), compiled_patterns, info))

    @property
    def total_offices(self) -> int:
        return len(self._offices)

    def scan_text(self, text: str) -> List[OfficeMatch]:
        """
        Scans source text for historical office triggers.
        Returns list of matched offices with canonical Indonesian equivalents.
        """
        if not text:
            return []

        matched: List[OfficeMatch] = []
        seen_keys: Set[str] = set()

        for off_key, id_title, patterns, info in self._triggers:
            if off_key in seen_keys:
                continue
            for pat in patterns:
                m = pat.search(text)
                if m:
                    seen_keys.add(off_key)
                    matched.append(
                        OfficeMatch(
                            key=off_key,
                            original_title=info.get("istilah_asli", off_key),
                            canonical_id_title=id_title,
                            explanation=info.get("penjelasan", ""),
                            matched_trigger=m.group(0),
                        )
                    )
                    break

        return matched

    def get_office_glossary(self, text: str) -> Dict[str, str]:
        """
        Returns a dictionary mapping English triggers found in text to canonical Indonesian titles.
        e.g. {'grand administrator': 'Gubernur Komanderi', 'strong crossbow general': 'Jenderal Busur Silang'}
        """
        mapping: Dict[str, str] = {}
        matches = self.scan_text(text)
        for m in matches:
            mapping[m.matched_trigger.lower()] = m.canonical_id_title
        return mapping

    def get_editorial_guidance_for_text(self, text: str) -> str:
        """
        Generates targeted editorial guidance text to be injected into
        translation prompts when historical offices or titles are present.
        """
        matches = self.scan_text(text)
        if not matches:
            return ""

        lines = ["[Panduan Gelar & Jabatan Birokrasi Sejarah Kuno]"]
        for m in matches:
            orig = f" ({m.original_title})" if m.original_title else ""
            lines.append(f"• '{m.matched_trigger}'{orig} -> WAJIB: '{m.canonical_id_title}'")
            if m.explanation:
                lines.append(f"  ({m.explanation})")

        return "\n".join(lines)
    def audit_translated_titles(self, id_wikitext: str) -> List[str]:
        """
        Audits Indonesian wikitext for common calques or mistranslated ancient bureaucratic titles.
        Returns a list of warning descriptions.
        """
        warnings: List[str] = []
        flawed_patterns = [
            (re.compile(r"\bnegara\s+dependen\b", re.IGNORECASE), "Anakronisme gelar/wilayah: 'negara dependen' -> gunakan 'wilayah dependensi (shuguo)' (bukan negara berdaulat merdeka)."),
            (re.compile(r"\b(?:komanderi\s+administrator|administrator\s+komanderi)\b", re.IGNORECASE), "Kalkir modern kantor: 'administrator komanderi' -> gunakan 'Gubernur Komanderi' (Tàishǒu)."),
            (re.compile(r"\bmenteri\s+pelayan\b", re.IGNORECASE), "Kalkir harfiah: 'menteri pelayan' -> gunakan 'Bendahara Rumah Tangga Istana' (Shǎo Fǔ)."),
        ]
        for pat, desc in flawed_patterns:
            for match in pat.finditer(id_wikitext):
                warnings.append(f"{desc} (ditemukan '{match.group(0)}')")
        return warnings


default_offices_manager = HistoricalOfficesManager()
