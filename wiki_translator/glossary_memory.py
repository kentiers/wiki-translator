"""Human-reviewed memory for dynamic glossary candidates."""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from difflib import SequenceMatcher
import re
import mwparserfromhell
import sqlite3
import time
from pathlib import Path
from typing import List, Optional, Union

from .storage_manager import default_storage_manager

@dataclass(frozen=True)
class GlossaryCandidate:
    source_term: str
    target_term: str
    topic: Optional[str]
    context: Optional[str]
    source: str
    confidence: float
    status: str = "candidate"
    usage_count: int = 0


def extract_revision_corrections(draft_wikitext: str, revised_wikitext: str) -> List[GlossaryCandidate]:
    """Extract small human edits as glossary candidates; never auto-approve them."""
    draft_tokens = _revision_tokens(draft_wikitext)
    revised_tokens = _revision_tokens(revised_wikitext)
    candidates: List[GlossaryCandidate] = []
    matcher = SequenceMatcher(None, draft_tokens, revised_tokens, autojunk=False)
    for tag, start_a, end_a, start_b, end_b in matcher.get_opcodes():
        if tag != "replace" or not (start_a < end_a and start_b < end_b):
            continue
        source_term = " ".join(draft_tokens[start_a:end_a]).strip()
        target_term = " ".join(revised_tokens[start_b:end_b]).strip()
        if not 1 <= len(source_term.split()) <= 6 or not 1 <= len(target_term.split()) <= 6:
            continue
        if source_term.casefold() == target_term.casefold():
            continue
        if not re.search(r"[A-Za-zÀ-ÿ]", source_term) or not re.search(r"[A-Za-zÀ-ÿ]", target_term):
            continue
        context_start = max(0, start_b - 6)
        context_end = min(len(revised_tokens), end_b + 6)
        confidence = 0.8 if len(source_term.split()) <= 3 else 0.7
        candidates.append(
            GlossaryCandidate(
                source_term=source_term,
                target_term=target_term,
                topic=None,
                context=" ".join(revised_tokens[context_start:context_end]),
                source="human_revision",
                confidence=confidence,
            )
        )
    return candidates


def _revision_tokens(text: str) -> List[str]:
    prose = _revision_prose(mwparserfromhell.parse(text))
    return re.findall(r"\w+(?:['-]\w+)*", prose, flags=re.UNICODE)


def _revision_prose(code) -> str:
    """Read visible prose without expanding templates or citation contents."""
    nodes = mwparserfromhell.nodes
    parts = []
    for node in code.nodes:
        if isinstance(node, nodes.Text):
            value = str(node)
            # Unparsed delimiters may be malformed markup, not prose.
            parts.append(" " if any(c in value for c in "{}[]<>") else value)
        elif isinstance(node, nodes.HTMLEntity):
            parts.append(node.normalize())
        elif isinstance(node, nodes.Wikilink):
            title = str(node.title).strip()
            if ":" not in title:
                parts.append(_revision_prose(node.text if node.text is not None else node.title))
            else:
                parts.append(" ")
        elif isinstance(node, nodes.ExternalLink):
            parts.append(_revision_prose(node.title) if node.title is not None else " ")
        elif isinstance(node, nodes.Tag) and str(node.tag).strip().casefold() in {
            "b", "i", "em", "strong", "span", "div", "p", "small", "big", "u", "s",
        }:
            parts.append(_revision_prose(node.contents))
        else:
            parts.append(" ")
    return "".join(parts)


class GlossaryMemory:
    """Persist candidates and approved terminology without auto-promoting them."""

    def __init__(self, db_path: Optional[Union[str, Path]] = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else default_storage_manager.glossary_memory_db
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS glossary_memory (
                    source_key TEXT NOT NULL,
                    target_term TEXT NOT NULL,
                    topic_key TEXT NOT NULL DEFAULT '',
                    context TEXT,
                    source TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'candidate',
                    usage_count INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (source_key, target_term, topic_key)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_glossary_memory_status "
                "ON glossary_memory(status, topic_key, source_key)"
            )

    @staticmethod
    def _key(value: str) -> str:
        return " ".join(value.strip().casefold().split())

    def propose(self, candidate: GlossaryCandidate) -> GlossaryCandidate:
        """Insert or update a candidate; never changes an approved row's status."""
        now = time.time()
        topic_key = self._key(candidate.topic or "")
        source_key = self._key(candidate.source_term)
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT status, usage_count FROM glossary_memory "
                "WHERE source_key = ? AND target_term = ? AND topic_key = ?",
                (source_key, candidate.target_term.strip(), topic_key),
            ).fetchone()
            status = existing["status"] if existing else "candidate"
            usage_count = existing["usage_count"] if existing else candidate.usage_count
            conn.execute(
                """
                INSERT INTO glossary_memory
                    (source_key, target_term, topic_key, context, source,
                     confidence, status, usage_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_key, target_term, topic_key) DO UPDATE SET
                    updated_at = excluded.updated_at
                """,
                (
                    source_key,
                    candidate.target_term.strip(),
                    topic_key,
                    candidate.context,
                    candidate.source,
                    max(0.0, min(1.0, candidate.confidence)),
                    status,
                    usage_count,
                    now,
                    now,
                ),
            )
        return self.get(source_key, candidate.target_term, candidate.topic)  # type: ignore[return-value]

    def propose_from_revision(
        self,
        draft_wikitext: str,
        revised_wikitext: str,
        *,
        topic: Optional[str] = None,
    ) -> List[GlossaryCandidate]:
        """Learn from a reviewed revision while keeping every result pending."""
        stored: List[GlossaryCandidate] = []
        for candidate in extract_revision_corrections(draft_wikitext, revised_wikitext):
            candidate = GlossaryCandidate(
                source_term=candidate.source_term,
                target_term=candidate.target_term,
                topic=topic,
                context=candidate.context,
                source=candidate.source,
                confidence=candidate.confidence,
            )
            stored.append(self.propose(candidate))
        return stored

    def approve(self, source_term: str, target_term: str, topic: Optional[str] = None) -> bool:
        return self._set_status(source_term, target_term, topic, "approved")

    def approved_terms(self, topic: Optional[str] = None) -> dict:
        """Return unambiguous EN-ID terms; revision corrections are ID-ID evidence."""
        result = {}
        scopes = [""] + ([self._key(topic)] if topic else [])
        for scope in scopes:
            grouped = {}
            for item in self.list(scope, status="approved"):
                if item.source == "human_revision":
                    continue
                grouped.setdefault(item.source_term, set()).add(item.target_term)
            for key, targets in grouped.items():
                result.pop(key, None)
                if len(targets) == 1:
                    result[key] = next(iter(targets))
        return result

    def reject(self, source_term: str, target_term: str, topic: Optional[str] = None) -> bool:
        return self._set_status(source_term, target_term, topic, "rejected")

    def _set_status(self, source_term: str, target_term: str, topic: Optional[str], status: str) -> bool:
        with self._connect() as conn:
            result = conn.execute(
                "UPDATE glossary_memory SET status = ?, updated_at = ? "
                "WHERE source_key = ? AND target_term = ? AND topic_key = ?",
                (status, time.time(), self._key(source_term), target_term.strip(), self._key(topic or "")),
            )
            return result.rowcount == 1

    def record_usage(self, source_term: str, target_term: str, topic: Optional[str] = None) -> bool:
        with self._connect() as conn:
            result = conn.execute(
                "UPDATE glossary_memory SET usage_count = usage_count + 1, updated_at = ? "
                "WHERE source_key = ? AND target_term = ? AND topic_key = ?",
                (time.time(), self._key(source_term), target_term.strip(), self._key(topic or "")),
            )
            return result.rowcount == 1

    def get(self, source_term: str, target_term: str, topic: Optional[str] = None) -> Optional[GlossaryCandidate]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM glossary_memory WHERE source_key = ? AND target_term = ? AND topic_key = ?",
                (self._key(source_term), target_term.strip(), self._key(topic or "")),
            ).fetchone()
        return self._from_row(row) if row else None

    def list(self, topic: Optional[str] = None, status: str = "candidate") -> List[GlossaryCandidate]:
        query = "SELECT * FROM glossary_memory WHERE status = ?"
        params: List[object] = [status]
        if topic is not None:
            query += " AND topic_key = ?"
            params.append(self._key(topic))
        query += " ORDER BY confidence DESC, updated_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row: sqlite3.Row) -> GlossaryCandidate:
        return GlossaryCandidate(
            source_term=row["source_key"],
            target_term=row["target_term"],
            topic=row["topic_key"] or None,
            context=row["context"],
            source=row["source"],
            confidence=row["confidence"],
            status=row["status"],
            usage_count=row["usage_count"],
        )
