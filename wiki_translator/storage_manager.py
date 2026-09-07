"""
Centralized storage and cache configuration manager for Wiki Translator Suite.

Unifies SQLite databases, output directories, and cache locations into a single,
configurable registry. Supports environment overrides (WIKI_CACHE_DIR, WIKI_OUTPUT_DIR)
and cache maintenance (inspection, size calculation, selective clearing).
"""

from dataclasses import dataclass
import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Set, Tuple, Union


DEFAULT_CACHE_DIR = ".cache"
DEFAULT_OUTPUT_DIR = "output"
DEFAULT_DATA_DIR = "data"

ENV_CACHE_DIR = "WIKI_CACHE_DIR"
ENV_OUTPUT_DIR = "WIKI_OUTPUT_DIR"
ENV_DATA_DIR = "WIKI_DATA_DIR"


@dataclass(frozen=True)
class CacheDatabaseInfo:
    key: str
    filename: str
    description: str
    is_data_dir: bool = False


KNOWN_DATABASES: Dict[str, CacheDatabaseInfo] = {
    "translation_cache": CacheDatabaseInfo(
        key="translation_cache",
        filename="translation_cache.db",
        description="Semantic cache for section-level wikitext translations",
    ),
    "glossary_memory": CacheDatabaseInfo(
        key="glossary_memory",
        filename="glossary_memory.db",
        description="Human-reviewed memory for dynamic glossary candidates",
    ),
    "glossary_cache": CacheDatabaseInfo(
        key="glossary_cache",
        filename="glossary_cache.db",
        description="Resolved terminology cache from enwiki-idwiki langlinks",
    ),
    "wayback_cache": CacheDatabaseInfo(
        key="wayback_cache",
        filename="wayback_cache.db",
        description="Wayback Machine Availability API URL archive cache",
    ),
    "workspace_glossary": CacheDatabaseInfo(
        key="workspace_glossary",
        filename="workspace_glossary.db",
        description="Shared cross-article workspace approved terminology memory",
    ),
    "wiki_templates_cache": CacheDatabaseInfo(
        key="wiki_templates_cache",
        filename="wiki_templates_cache.db",
        description="Cache for id.wikipedia template and navbox existence checks",
    ),
    "wiki_links_cache": CacheDatabaseInfo(
        key="wiki_links_cache",
        filename="wiki_links_cache.db",
        description="Cache for internal wikilink validity and redirect targets",
    ),
    "wiki_link_data": CacheDatabaseInfo(
        key="wiki_link_data",
        filename="wiki_link_cache.sqlite",
        description="Offline pre-computed wiki link database in data/ directory",
        is_data_dir=True,
    ),
    "kateglo_cache": CacheDatabaseInfo(
        key="kateglo_cache",
        filename="kateglo_cache.sqlite",
        description="Offline cache for Kateglo dictionary, thesaurus, and glossary API",
        is_data_dir=True,
    ),
}


class StorageManager:
    """Manages filesystem paths, SQLite databases, and cache lifecycle."""

    def __init__(
        self,
        base_dir: Optional[Union[str, Path]] = None,
        cache_dir: Optional[Union[str, Path]] = None,
        output_dir: Optional[Union[str, Path]] = None,
        data_dir: Optional[Union[str, Path]] = None,
    ) -> None:
        self.base_dir = Path(base_dir).resolve() if base_dir else Path.cwd()
        self._cache_dir_override = Path(cache_dir) if cache_dir else None
        self._output_dir_override = Path(output_dir) if output_dir else None
        self._data_dir_override = Path(data_dir) if data_dir else None

    @property
    def cache_dir(self) -> Path:
        if self._cache_dir_override:
            p = self._cache_dir_override
        elif ENV_CACHE_DIR in os.environ:
            p = Path(os.environ[ENV_CACHE_DIR])
        else:
            p = self.base_dir / DEFAULT_CACHE_DIR
        return p if p.is_absolute() else (self.base_dir / p)

    @property
    def output_dir(self) -> Path:
        if self._output_dir_override:
            p = self._output_dir_override
        elif ENV_OUTPUT_DIR in os.environ:
            p = Path(os.environ[ENV_OUTPUT_DIR])
        else:
            p = self.base_dir / DEFAULT_OUTPUT_DIR
        return p if p.is_absolute() else (self.base_dir / p)

    @property
    def data_dir(self) -> Path:
        if self._data_dir_override:
            p = self._data_dir_override
        elif ENV_DATA_DIR in os.environ:
            p = Path(os.environ[ENV_DATA_DIR])
        else:
            p = self.base_dir / DEFAULT_DATA_DIR
        return p if p.is_absolute() else (self.base_dir / p)

    def ensure_directories(self) -> None:
        """Ensures that standard cache, output, and data directories exist."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def get_db_path(self, key: str, ensure_parent: bool = True) -> Path:
        """Resolves the full filesystem path for a registered SQLite database."""
        info = KNOWN_DATABASES.get(key)
        if info:
            parent = self.data_dir if info.is_data_dir else self.cache_dir
            path = parent / info.filename
        else:
            filename = key if key.endswith((".db", ".sqlite")) else f"{key}.db"
            path = self.cache_dir / filename

        if ensure_parent:
            path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def translation_cache_db(self) -> Path:
        return self.get_db_path("translation_cache")

    @property
    def glossary_memory_db(self) -> Path:
        return self.get_db_path("glossary_memory")

    @property
    def kateglo_cache_db(self) -> Path:
        return self.get_db_path("kateglo_cache")
    @property
    def glossary_cache_db(self) -> Path:
        return self.get_db_path("glossary_cache")

    @property
    def wayback_cache_db(self) -> Path:
        return self.get_db_path("wayback_cache")

    @property
    def workspace_glossary_db(self) -> Path:
        return self.get_db_path("workspace_glossary")

    @property
    def wiki_templates_cache_db(self) -> Path:
        return self.get_db_path("wiki_templates_cache")

    @property
    def wiki_links_cache_db(self) -> Path:
        return self.get_db_path("wiki_links_cache")

    @property
    def wiki_link_data_db(self) -> Path:
        return self.get_db_path("wiki_link_data")

    def inspect_databases(self) -> List[Dict[str, Any]]:
        """Inspects all known databases and returns size and existence status."""
        results = []
        for key, info in KNOWN_DATABASES.items():
            path = self.get_db_path(key, ensure_parent=False)
            exists = path.exists()
            size_bytes = path.stat().st_size if exists else 0
            results.append({
                "key": key,
                "filename": info.filename,
                "description": info.description,
                "path": str(path),
                "exists": exists,
                "size_bytes": size_bytes,
                "size_kb": round(size_bytes / 1024.0, 2),
            })
        return results

    def clear_database(self, key: str) -> bool:
        """Safely removes an existing SQLite database file and its WAL/SHM siblings."""
        path = self.get_db_path(key, ensure_parent=False)
        removed = False
        for target in (path, path.with_suffix(path.suffix + "-wal"), path.with_suffix(path.suffix + "-shm")):
            if target.exists():
                try:
                    target.unlink()
                    removed = True
                except OSError:
                    pass
        return removed

    def clear_all_caches(self, include_data: bool = False) -> Dict[str, bool]:
        """Clears all temporary SQLite caches."""
        results = {}
        for key, info in KNOWN_DATABASES.items():
            if info.is_data_dir and not include_data:
                continue
            results[key] = self.clear_database(key)
        return results
    def optimize_all_databases(self) -> Dict[str, Dict[str, Any]]:
        """
        Runs PRAGMA optimize, checks integrity, and ensures WAL mode across all known databases.
        Returns detailed optimization and health report.
        """
        report: Dict[str, Dict[str, Any]] = {}
        for key in KNOWN_DATABASES:
            path = self.get_db_path(key, ensure_parent=False)
            if not path.exists():
                continue
            conn = None
            try:
                conn = sqlite3.connect(str(path), timeout=10.0)
                cur = conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA synchronous=NORMAL")
                integrity = cur.execute("PRAGMA integrity_check").fetchone()[0]
                cur.execute("PRAGMA optimize")
                report[key] = {
                    "path": str(path),
                    "integrity": integrity,
                    "journal_mode": "wal",
                    "status": "healthy" if integrity == "ok" else "error",
                }
            except Exception as e:
                report[key] = {"path": str(path), "status": "error", "error": str(e)}
            finally:
                if conn:
                    conn.close()
        return report


@dataclass
class ArticleIngestionRecord:
    category: str
    database_key: str
    entry: str
    details: str
    timestamp: float = 0.0


class ArticleSessionTracker:
    """
    Tracks all database insertions, lemma discoveries, glossary resolutions,
    and cross-wiki link mappings performed specifically for the currently active article.
    Provides clear visibility into what exact knowledge was ingested.
    """

    def __init__(self, article_title: str = ""):
        self.article_title = article_title
        self.records: List[ArticleIngestionRecord] = []
        self._seen: Set[Tuple[str, str]] = set()

    def start_article(self, article_title: str) -> None:
        """Starts tracking a new article session."""
        self.article_title = article_title
        self.records.clear()
        self._seen.clear()

    def record_kateglo_lemma(self, lemma: str, definition: str = "", category: str = "Lema KBBI / Kateglo") -> None:
        """Records a new dictionary lemma / KBBI entry cached for this article."""
        clean = lemma.strip()
        if not clean:
            return
        key = ("kateglo", clean.lower())
        if key not in self._seen:
            self._seen.add(key)
            import time
            short_def = definition.strip().replace("\n", " ")
            if len(short_def) > 70:
                short_def = short_def[:67] + "..."
            self.records.append(ArticleIngestionRecord(
                category="📖 Lema & Definisi (KBBI / Kateglo)",
                database_key="kateglo_cache",
                entry=clean,
                details=short_def or "Entri lema & tesaurus tersimpan",
                timestamp=time.time(),
            ))

    def record_glossary_term(self, en_term: str, id_term: str, source: str = "Glosarium Istilah") -> None:
        """Records a bilingual glossary term pair resolved and cached for this article."""
        en_clean = en_term.strip()
        id_clean = id_term.strip() if id_term else ""
        if not en_clean:
            return
        key = ("glossary", en_clean.lower())
        if key not in self._seen:
            self._seen.add(key)
            import time
            self.records.append(ArticleIngestionRecord(
                category="🧠 Glosarium Istilah Baku (EN ➔ ID)",
                database_key="glossary_memory",
                entry=f"{en_clean} ➔ {id_clean}" if id_clean else en_clean,
                details=f"Sumber: {source}",
                timestamp=time.time(),
            ))

    def record_wiki_link(self, en_title: str, id_title: str, status: str = "Tervalidasi") -> None:
        """Records a cross-wiki interlanguage page or category mapping cached for this article."""
        en_clean = en_title.strip()
        id_clean = id_title.strip() if id_title else ""
        if not en_clean:
            return
        key = ("wikilink", en_clean.lower())
        if key not in self._seen:
            self._seen.add(key)
            import time
            self.records.append(ArticleIngestionRecord(
                category="🔗 Pranala & Entitas Wiki (Lintas-Bahasa)",
                database_key="wiki_links_cache",
                entry=f"en:{en_clean} ➔ id:{id_clean}" if id_clean else f"en:{en_clean}",
                details=status,
                timestamp=time.time(),
            ))

    def record_template(self, template_name: str, status: str = "Terverifikasi") -> None:
        """Records a template verified or mapped for this article."""
        t_clean = template_name.strip()
        if not t_clean:
            return
        key = ("template", t_clean.lower())
        if key not in self._seen:
            self._seen.add(key)
            import time
            self.records.append(ArticleIngestionRecord(
                category="🧩 Templat & Modul Wiki",
                database_key="wiki_templates_cache",
                entry=t_clean,
                details=status,
                timestamp=time.time(),
            ))

    def get_records(self) -> List[ArticleIngestionRecord]:
        """Returns all recorded ingestion items for the current session."""
        return list(self.records)

    def get_grouped_summary(self) -> Dict[str, List[ArticleIngestionRecord]]:
        """Groups recorded items by category."""
        grouped: Dict[str, List[ArticleIngestionRecord]] = {}
        for r in self.records:
            grouped.setdefault(r.category, []).append(r)
        return grouped

    def clear(self) -> None:
        """Clears all records."""
        self.records.clear()
        self._seen.clear()


default_session_tracker = ArticleSessionTracker()
default_storage_manager = StorageManager()
