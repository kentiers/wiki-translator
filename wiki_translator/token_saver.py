"""
Token Saver & Compression Module for Wiki Translator (OMP-inspired).

Key Mechanisms:
1. Persistent Semantic / Content Cache (Headroom Caching):
   - Cache translated wikitext sections by SHA-256 hash of (normalized source text + topic + prompt version).
   - SQLite store at `.cache/translation_cache.db`.
2. Citation / Heavy Markup Reducer & Restorer (Token Compression):
   - Replaces heavy `<ref>...</ref>`, `<ref name="..." />`, `<math>...</math>`, and complex `{{cite ...}}`
     with lightweight placeholders (⟦REF_0⟧, ⟦MATH_0⟧, ⟦TMPL_0⟧).
   - Rehydrates placeholders back to original wikitext after LLM translation.
3. Smart Delta Skip & Whitelist Filtering:
   - Identifies sections requiring 0 LLM translation (e.g. References, External links, See also)
     and directly converts headings / translates deterministic link titles without LLM calls.
4. Token Usage Tracker & Savings Dashboard:
   - Heuristic token estimation (chars / 4 standard approximation).
   - Tracks raw prompt/response tokens, optimized tokens sent/received, cache hits, and savings percentage.
"""

from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import time
from typing import Any, Dict, List, Optional, Set, Tuple


PROMPT_VERSION = "v1.0"


def estimate_tokens(text: str) -> int:
    """Heuristic token estimation: ~4 chars per token for Latin/Wikitext mixes, min 1 token for non-empty."""
    if not text:
        return 0
    # Average across English/Indonesian/markup is ~3.5-4 chars per token.
    # We use max(1, round(len(text) / 3.8))
    return max(1, round(len(text) / 3.8))


@dataclass
class CompressedWikitext:
    compressed_text: str
    placeholders: Dict[str, str] = field(default_factory=dict)
    original_char_count: int = 0
    compressed_char_count: int = 0

    @property
    def chars_saved(self) -> int:
        return max(0, self.original_char_count - self.compressed_char_count)

    @property
    def token_savings_percent(self) -> float:
        if self.original_char_count == 0:
            return 0.0
        return (self.chars_saved / self.original_char_count) * 100.0


class TokenCompressor:
    """
    Compresses wikitext markup (citations, math formulas, heavy templates) into compact placeholders
    and restores them accurately after LLM generation.
    """

    # Patterns to compress
    MATH_PATTERN = re.compile(r"<math[\s\S]*?</math>", re.IGNORECASE)
    CHEM_PATTERN = re.compile(r"<chem[\s\S]*?</chem>", re.IGNORECASE)
    SYNTAX_PATTERN = re.compile(r"<(syntaxhighlight|source)[\s\S]*?</\1>", re.IGNORECASE)
    REF_PAIR_PATTERN = re.compile(r"<ref(?:\s+[^>/]*)?>[\s\S]*?</ref>", re.IGNORECASE)
    REF_SELF_CLOSE_PATTERN = re.compile(r"<ref\s+[^>]*?/>", re.IGNORECASE)

    @classmethod
    def compress(cls, wikitext: str) -> CompressedWikitext:
        """
        Replaces heavy references, math formulas, and code blocks with placeholders.
        Preserves simple templates while extracting heavy cite templates outside or inside refs.
        """
        placeholders: Dict[str, str] = {}
        counter = {"ref": 0, "math": 0, "code": 0, "cite": 0}
        orig_len = len(wikitext)
        result = wikitext

        # 1. Compress math and chem blocks
        def replace_math(match: re.Match) -> str:
            tag = f"⟦MATH_{counter['math']}⟧"
            counter["math"] += 1
            placeholders[tag] = match.group(0)
            return tag

        result = cls.MATH_PATTERN.sub(replace_math, result)
        result = cls.CHEM_PATTERN.sub(replace_math, result)

        # 2. Compress syntaxhighlight / source blocks
        def replace_syntax(match: re.Match) -> str:
            tag = f"⟦CODE_{counter['code']}⟧"
            counter["code"] += 1
            placeholders[tag] = match.group(0)
            return tag

        result = cls.SYNTAX_PATTERN.sub(replace_syntax, result)

        # 3. Compress <ref>...</ref> pairs and self-closing <ref ... />
        def replace_ref(match: re.Match) -> str:
            tag = f"⟦REF_{counter['ref']}⟧"
            counter["ref"] += 1
            placeholders[tag] = match.group(0)
            return tag

        result = cls.REF_PAIR_PATTERN.sub(replace_ref, result)
        result = cls.REF_SELF_CLOSE_PATTERN.sub(replace_ref, result)

        # 4. Compress standalone {{cite ...}} or {{citation ...}} templates that are not inside refs
        # (Track balanced braces)
        result = cls._compress_standalone_cites(result, counter, placeholders)

        return CompressedWikitext(
            compressed_text=result,
            placeholders=placeholders,
            original_char_count=orig_len,
            compressed_char_count=len(result),
        )

    @classmethod
    def _compress_standalone_cites(
        cls, text: str, counter: Dict[str, int], placeholders: Dict[str, str]
    ) -> str:
        """Finds and replaces standalone cite templates like {{cite journal|...}} outside refs."""
        out = []
        i = 0
        n = len(text)
        while i < n:
            if text[i : i + 2] == "{{" and re.match(
                r"^\{\{\s*(cite\s|citation\b)", text[i:], re.IGNORECASE
            ):
                start = i
                depth = 1
                i += 2
                while i < n - 1 and depth > 0:
                    if text[i : i + 2] == "{{":
                        depth += 1
                        i += 2
                    elif text[i : i + 2] == "}}":
                        depth -= 1
                        i += 2
                    else:
                        i += 1
                if depth == 0:
                    full_tmpl = text[start:i]
                    tag = f"⟦CITE_{counter['cite']}⟧"
                    counter["cite"] += 1
                    placeholders[tag] = full_tmpl
                    out.append(tag)
                    continue
                else:
                    # Unbalanced, append as is
                    out.append(text[start:i])
                    continue
            else:
                out.append(text[i])
                i += 1

        return "".join(out)

    @classmethod
    def decompress(cls, text: str, placeholders: Dict[str, str]) -> str:
        """
        Rehydrates placeholders (⟦REF_0⟧, ⟦MATH_0⟧, etc.) with their original content.
        Also tolerates minor LLM distortions (like [REF_0], [[REF_0]], ⟦REF_0 ]).
        """
        if not placeholders:
            return text

        restored = text
        for tag, orig in placeholders.items():
            if tag in restored:
                restored = restored.replace(tag, orig)
            else:
                # Handle possible LLM modifications (brackets/spaces)
                # e.g., ⟦REF_0⟧ -> [REF_0] or ⟦ REF_0 ⟧ or [[REF_0]]
                clean_name = tag.strip("⟦⟧")
                variants = [
                    f"⟦ {clean_name} ⟧",
                    f"[{clean_name}]",
                    f"[[{clean_name}]]",
                    f"({clean_name})",
                    f"⟦{clean_name} ]",
                    f"[ {clean_name} ]",
                ]
                replaced = False
                for v in variants:
                    if v in restored:
                        restored = restored.replace(v, orig)
                        replaced = True
                        break
                # Regex fallback if still missing
                if not replaced:
                    pattern = re.compile(
                        r"[⟦\[\(]\s*" + re.escape(clean_name) + r"\s*[⟧\]\)]"
                    )
                    restored = pattern.sub(lambda _: orig, restored)

        return restored


class TranslationCache:
    """
    Persistent SQLite translation cache (Headroom semantic cache).
    Stores translated section results keyed by SHA-256 hash.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            cache_dir = Path(".cache")
            cache_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = cache_dir / "translation_cache.db"
        else:
            self.db_path = Path(db_path)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=10.0)

    def _init_db(self) -> None:
        conn = self._get_conn()
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS section_translations (
                        hash_key TEXT PRIMARY KEY,
                        source_title TEXT,
                        topic TEXT,
                        prompt_version TEXT,
                        source_text TEXT,
                        translated_text TEXT,
                        raw_tokens INTEGER,
                        created_at REAL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_cache_created ON section_translations(created_at)"
                )
        finally:
            conn.close()
    @staticmethod
    def compute_hash(
        source_text: str,
        section_title: str = "",
        topic: Optional[str] = None,
        prompt_version: str = PROMPT_VERSION,
    ) -> str:
        """Computes deterministic SHA-256 hash of normalized source text and metadata."""
        norm_text = "\n".join(line.rstrip() for line in source_text.strip().splitlines())
        norm_title = section_title.strip().lower()
        norm_topic = (topic or "general").strip().lower()

        data = f"{prompt_version}:{norm_topic}:{norm_title}:{norm_text}"
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def get(
        self,
        source_text: str,
        section_title: str = "",
        topic: Optional[str] = None,
        prompt_version: str = PROMPT_VERSION,
    ) -> Optional[str]:
        """Returns cached translated text or None if cache miss."""
        hash_key = self.compute_hash(source_text, section_title, topic, prompt_version)
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT translated_text FROM section_translations WHERE hash_key = ?",
                (hash_key,),
            )
            row = cur.fetchone()
            if row:
                return row[0]
            return None
        finally:
            conn.close()

    def put(
        self,
        source_text: str,
        translated_text: str,
        section_title: str = "",
        topic: Optional[str] = None,
        prompt_version: str = PROMPT_VERSION,
        raw_tokens: int = 0,
    ) -> None:
        """Saves a translated section into cache."""
        hash_key = self.compute_hash(source_text, section_title, topic, prompt_version)
        conn = self._get_conn()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO section_translations
                    (hash_key, source_title, topic, prompt_version, source_text, translated_text, raw_tokens, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        hash_key,
                        section_title,
                        topic or "general",
                        prompt_version,
                        source_text,
                        translated_text,
                        raw_tokens,
                        time.time(),
                    ),
                )
        finally:
            conn.close()

    def clear(self) -> None:
        """Clears all cached translations."""
        conn = self._get_conn()
        try:
            with conn:
                conn.execute("DELETE FROM section_translations")
        finally:
            conn.close()

    def count(self) -> int:
        """Returns total entries in cache."""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM section_translations")
            return cur.fetchone()[0]
        finally:
            conn.close()

class SectionFilter:
    """
    Detects boilerplate/non-prose sections that require 0 LLM translation tokens (Smart Delta Skip).
    Converts standard Wikipedia section headings directly to standard Indonesian equivalents.
    """

    # Section title mapping: English -> Indonesian standard headings
    STANDARD_HEADINGS: Dict[str, str] = {
        "references": "Referensi",
        "reference": "Referensi",
        "external links": "Pranala luar",
        "external link": "Pranala luar",
        "see also": "Lihat pula",
        "further reading": "Bacaan lanjutan",
        "notes": "Catatan",
        "notes and references": "Catatan dan referensi",
        "bibliography": "Bibliografi",
        "sources": "Sumber",
        "citations": "Kutipan",
    }

    # Known standard templates in boilerplate sections
    STANDARD_TEMPLATES: Dict[str, str] = {
        "reflist": "reflist",
        "refbegin": "refbegin",
        "refend": "refend",
        "commonscat": "commonscat",
        "commons category": "commons category",
        "wikiquote": "wikiquote",
        "authority control": "authority control",
    }

    @classmethod
    def can_skip_llm(cls, title: str, content: str) -> Tuple[bool, Optional[str]]:
        """
        Determines if a section can be converted directly without calling LLM.
        Returns (is_skippable, translated_content_or_None).
        """
        clean_title = re.sub(r"[^a-zA-Z0-9\s]", "", title).strip().lower()
        if clean_title not in cls.STANDARD_HEADINGS:
            return False, None

        id_heading_title = cls.STANDARD_HEADINGS[clean_title]

        # Check content complexity:
        # If content contains only template calls ({{reflist}}, {{Reflist|...}}), empty lines,
        # categories, or simple bullet list of external links / templates, we can directly format it.
        lines = [line.strip() for line in content.strip().splitlines() if line.strip()]

        # If completely empty content
        if not lines:
            return True, ""

        # Check if content consists only of boilerplate items
        # e.g., {{reflist}}, {{Reflist|30em}}, {{Authority control}}, [[Category:...]], * [http... Title]
        is_boilerplate = True
        for line in lines:
            if re.match(r"^\{\{\s*(reflist|refbegin|refend|authority control|commonscat|commons category|wikiquote|notelist)[^}]*\}\}$", line, re.IGNORECASE):
                continue
            if re.match(r"^<references\s*/?>", line, re.IGNORECASE):
                continue
            if re.match(r"^\*?\s*\[https?://[^\s\]]+\s+[^\]]+\]", line):
                # Simple external link item
                continue
            if re.match(r"^\*?\s*\[\[[^\]]+\]\]", line):
                # Simple internal link item e.g. * [[Related Topic]]
                continue
            # If there is substantive prose sentences (more than 5 plain words without wiki syntax)
            plain_words = [w for w in line.split() if not w.startswith("[[") and not w.startswith("{{") and not w.startswith("http")]
            if len(plain_words) > 6:
                is_boilerplate = False
                break

        if is_boilerplate:
            # We can retain the content directly or do simple substitutions
            return True, content.strip()

        return False, None


@dataclass
class TokenTracker:
    """
    Tracks token usage, compression ratio, and savings across all translation runs.
    """

    raw_input_tokens: int = 0
    raw_output_tokens: int = 0
    optimized_input_tokens: int = 0
    optimized_output_tokens: int = 0
    cache_hits: int = 0
    delta_skips: int = 0
    compressed_sections: int = 0

    def record_cache_hit(self, source_text: str, cached_translation: str) -> None:
        raw_in = estimate_tokens(source_text)
        raw_out = estimate_tokens(cached_translation)
        self.raw_input_tokens += raw_in
        self.raw_output_tokens += raw_out
        # 0 tokens sent to LLM for cache hit!
        self.cache_hits += 1

    def record_delta_skip(self, source_text: str, skipped_translation: str) -> None:
        raw_in = estimate_tokens(source_text)
        raw_out = estimate_tokens(skipped_translation)
        self.raw_input_tokens += raw_in
        self.raw_output_tokens += raw_out
        # 0 tokens sent to LLM for delta skip!
        self.delta_skips += 1

    def record_llm_call(
        self,
        raw_source_text: str,
        compressed_prompt_text: str,
        raw_output_text: str,
        compressed_output_text: str,
    ) -> None:
        raw_in = estimate_tokens(raw_source_text)
        raw_out = estimate_tokens(raw_output_text)
        opt_in = estimate_tokens(compressed_prompt_text)
        opt_out = estimate_tokens(compressed_output_text)

        self.raw_input_tokens += raw_in
        self.raw_output_tokens += raw_out
        self.optimized_input_tokens += opt_in
        self.optimized_output_tokens += opt_out
        self.compressed_sections += 1

    @property
    def total_raw_tokens(self) -> int:
        return self.raw_input_tokens + self.raw_output_tokens

    @property
    def total_optimized_tokens(self) -> int:
        return self.optimized_input_tokens + self.optimized_output_tokens

    @property
    def total_tokens_saved(self) -> int:
        return max(0, self.total_raw_tokens - self.total_optimized_tokens)

    @property
    def savings_percent(self) -> float:
        if self.total_raw_tokens == 0:
            return 0.0
        return (self.total_tokens_saved / self.total_raw_tokens) * 100.0

    def get_summary_table(self) -> str:
        """Renders an ASCII summary table showing token metrics."""
        lines = [
            "┌─────────────────────────────────────────────────────────────┐",
            "│          OMP TOKEN SAVER & OPTIMIZATION DASHBOARD           │",
            "├─────────────────────────────────────────────┬───────────────┤",
            f"│ Total Raw Tokens (Unoptimized Baseline)     │ {self.total_raw_tokens:>13,} │",
            f"│ Optimized Tokens Sent/Received via LLM      │ {self.total_optimized_tokens:>13,} │",
            f"│ Total Tokens Saved                          │ {self.total_tokens_saved:>13,} │",
            f"│ Overall Token Savings Rate                  │ {self.savings_percent:>12.1f}% │",
            "├─────────────────────────────────────────────┼───────────────┤",
            f"│ Headroom Cache Hits (0 Tokens)              │ {self.cache_hits:>13} │",
            f"│ Smart Delta Skips (0 Tokens)                │ {self.delta_skips:>13} │",
            f"│ Compressed Section Calls                    │ {self.compressed_sections:>13} │",
            "└─────────────────────────────────────────────┴───────────────┘",
        ]
        return "\n".join(lines)


# Global singleton instance for easy import and CLI tracking
default_cache = TranslationCache()
default_tracker = TokenTracker()
