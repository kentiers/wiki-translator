"""
Dynamic Historical Ethnonyms Manager for Indonesian Wikipedia Translation Suite.

Loads and operationalizes the historical ethnonym taxonomy schema from
data/historical_ethnonyms.json (zero hardcoding):
1. Distinguishes macro-level ethnos/people ("bangsa") from micro-level tribes/clans ("suku/kabilah").
2. Automatically detects historical tribal entities in source text (e.g. Qiang, Xiongnu, Goths, Franks, Mongols, Sioux, etc.).
3. Generates targeted editorial guidance and disambiguation notes for AI prompts and linters.
"""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union


@dataclass
class HistoricalEntityMatch:
    key: str
    name: str
    macro_category: str
    subgroups: List[str] = field(default_factory=list)
    editorial_note: str = ""
    disambiguation: str = ""


class HistoricalEthnonymsManager:
    """Dynamic, schema-driven manager for world historical ethnonyms."""

    def __init__(self, data_file: Optional[Union[str, Path]] = None):
        self.data_file = (
            Path(data_file)
            if data_file is not None
            else Path(__file__).resolve().parent.parent / "data" / "historical_ethnonyms.json"
        )
        self.reload()

    def reload(self) -> None:
        """Loads and compiles ethnonym taxonomy dynamically from disk."""
        self._raw_data: Dict[str, Any] = {}
        self._entities: Dict[str, Dict[str, Any]] = {}
        self._triggers: List[Tuple[str, List[re.Pattern], Dict[str, Any]]] = []

        if not self.data_file.exists():
            return

        try:
            self._raw_data = json.loads(self.data_file.read_text(encoding="utf-8"))
        except Exception:
            self._raw_data = {}

        wilayah = self._raw_data.get("wilayah", {})
        for region_name, entity_dict in wilayah.items():
            if isinstance(entity_dict, dict):
                for ent_key, info in entity_dict.items():
                    if isinstance(info, dict):
                        self._entities[ent_key] = info
                        triggers = info.get("en_triggers", [])
                        compiled_patterns = [
                            re.compile(r"\b" + re.escape(t.strip()) + r"\b", re.IGNORECASE)
                            for t in triggers
                            if t.strip()
                        ]
                        if compiled_patterns:
                            self._triggers.append((ent_key, compiled_patterns, info))

    @property
    def total_entities(self) -> int:
        return len(self._entities)

    def get_entity_names(self) -> List[str]:
        """Returns all canonical entity names."""
        return [info.get("nama_entitas", k) for k, info in self._entities.items()]

    def scan_text(self, text: str) -> List[HistoricalEntityMatch]:
        """
        Scans source wikitext or draft text for any historical ethnonym triggers.
        Returns list of matched entities with their taxonomy and editorial notes.
        """
        if not text:
            return []

        matched: List[HistoricalEntityMatch] = []
        seen_keys: Set[str] = set()

        for ent_key, patterns, info in self._triggers:
            if ent_key in seen_keys:
                continue
            for pat in patterns:
                if pat.search(text):
                    seen_keys.add(ent_key)
                    matched.append(
                        HistoricalEntityMatch(
                            key=ent_key,
                            name=info.get("nama_entitas", ent_key),
                            macro_category=info.get("kategori_makro", ""),
                            subgroups=info.get("suku_bagian", info.get("bangsa_bagian", [])),
                            editorial_note=info.get("catatan_redaksi", ""),
                            disambiguation=info.get("catatan_disambiguasi", ""),
                        )
                    )
                    break

        return matched

    def get_editorial_guidance_for_text(self, text: str) -> str:
        """
        Generates targeted editorial guidance text to be injected into
        translation prompts when historical ethnic groups are present.
        """
        matches = self.scan_text(text)
        if not matches:
            return ""

        lines = ["[Panduan Taksonomi Antropologi Sejarah (Bangsa vs Suku)]"]
        for m in matches:
            lines.append(f"• Entitas {m.name}:")
            if m.macro_category:
                lines.append(f"  - Kategori Makro: Gunakan '{m.macro_category}' untuk entitas kolektif/etnis besar.")
            if m.subgroups:
                subs = ", ".join(m.subgroups[:4])
                lines.append(f"  - Kelompok Suku/Klan: Gunakan '{subs}' untuk klan/kabilah bawahannya.")
            if m.editorial_note:
                lines.append(f"  - Catatan Redaksi: {m.editorial_note}")
            if m.disambiguation:
                lines.append(f"  - Perhatian: {m.disambiguation}")

        return "\n".join(lines)

    def audit_and_fix_homonym_blunders(self, text: str) -> Tuple[str, int, List[str]]:
        """
        Dynamically audits and auto-corrects dangerous historical homonym and conflation blunders
        driven by 'aturan_disambiguasi_homonim' in data/historical_ethnonyms.json.
        e.g. bare 'suku Han' -> 'suku Qiang Han' in Qiang context; 'Kekaisaran Romawi' -> 'Kekaisaran Romawi Suci' in HRE context.
        """
        if not text:
            return "", 0, []

        rules = self._raw_data.get("aturan_disambiguasi_homonim", [])
        if not rules:
            return text, 0, []

        result = text
        total_fixes = 0
        all_details = []

        text_lower = text.lower()
        for r in rules:
            ctx = r.get("konteks_wajib", [])
            # If context is required, ensure at least one keyword is present in text
            if ctx and not any(k.lower() in text_lower for k in ctx):
                continue

            pola = r.get("pola_salah", "")
            repl = r.get("pengganti_baku", "")
            if not pola or not repl:
                continue

            try:
                pat = re.compile(pola, re.IGNORECASE)
                new_text, n = pat.subn(repl, result)
                if n > 0:
                    total_fixes += n
                    all_details.append(f"[{r.get('id_aturan', 'disambig')}] {r.get('alasan', '')} ({n}x)")
                    result = new_text
            except Exception:
                pass

        return result, total_fixes, all_details


default_ethnonyms_manager = HistoricalEthnonymsManager()
