"""
Shared project memory module for cross-article terminology consistency.
Ensures 100% terminology consistency across multi-article translations in the same workspace or series.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Dict, Optional


class WorkspaceSharedMemory:
    """
    Manages cross-article shared memory and glossary storage using SQLite.
    Stores approved or recorded English-to-Indonesian terms to ensure
    consistent translations across articles in the same topic or workspace.
    """

    def __init__(self, db_path: str = ".cache/workspace_glossary.db") -> None:
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        """Initializes the SQLite schema for workspace terminology storage."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS workspace_terms (
                        en_term TEXT PRIMARY KEY,
                        id_term TEXT NOT NULL,
                        topic TEXT,
                        approved_count INTEGER DEFAULT 1,
                        last_used REAL
                    )
                    """
                )
        finally:
            conn.close()

    def remember_term(
        self,
        en_term: str,
        id_term: str,
        topic: Optional[str] = None,
    ) -> None:
        """
        Stores or updates an approved term translation.
        Increments approved_count if the term already exists and matches or updates it.
        """
        en_term_clean = en_term.strip()
        id_term_clean = id_term.strip()
        if not en_term_clean or not id_term_clean:
            return

        now = time.time()
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT approved_count FROM workspace_terms WHERE en_term = ?",
                    (en_term_clean,),
                )
                row = cur.fetchone()
                if row is not None:
                    new_count = row[0] + 1
                    cur.execute(
                        """
                        UPDATE workspace_terms
                        SET id_term = ?,
                            topic = COALESCE(?, topic),
                            approved_count = ?,
                            last_used = ?
                        WHERE en_term = ?
                        """,
                        (id_term_clean, topic, new_count, now, en_term_clean),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO workspace_terms (en_term, id_term, topic, approved_count, last_used)
                        VALUES (?, ?, ?, 1, ?)
                        """,
                        (en_term_clean, id_term_clean, topic, now),
                    )
        finally:
            conn.close()

    def get_memory_glossary(self, topic: Optional[str] = None) -> Dict[str, str]:
        """
        Retrieves a mapping of en_term -> id_term from memory.
        If topic is provided, retrieves terms matching that topic or terms with no topic (global).
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            if topic:
                cur.execute(
                    """
                    SELECT en_term, id_term FROM workspace_terms
                    WHERE topic = ? OR topic IS NULL
                    ORDER BY approved_count DESC, last_used DESC
                    """,
                    (topic,),
                )
            else:
                cur.execute(
                    """
                    SELECT en_term, id_term FROM workspace_terms
                    ORDER BY approved_count DESC, last_used DESC
                    """
                )
            rows = cur.fetchall()
            return {row[0]: row[1] for row in rows}
        finally:
            conn.close()

    def record_article_terms(
        self,
        glossary: Dict[str, str],
        topic: Optional[str] = None,
    ) -> None:
        """
        Batch records terminology discovered or finalized in an article.
        """
        for en_term, id_term in glossary.items():
            self.remember_term(en_term, id_term, topic=topic)

    def clear_memory(self, topic: Optional[str] = None) -> None:
        """
        Clears stored terms.
        If topic is specified, deletes only terms for that topic.
        If topic is None, deletes all terms.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                if topic:
                    conn.execute(
                        "DELETE FROM workspace_terms WHERE topic = ?",
                        (topic,),
                    )
                else:
                    conn.execute("DELETE FROM workspace_terms")
        finally:
            conn.close()


default_shared_memory = WorkspaceSharedMemory()
