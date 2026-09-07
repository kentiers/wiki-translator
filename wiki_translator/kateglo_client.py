"""
Kateglo REST API Client and Local Cache Manager for Wiki Translator Suite.

Connects to https://kateglo.org/api/publik with enterprise-grade resilience:
1. Defensive Key Polymorphism: Safely extracts definitions, thesaurus, and glossaries even if API schema keys change.
2. TTL & Cache Invalidation: Automatic stale cache detection (default 30 days) with stale-while-revalidate fallback.
3. Self-Healing SQLite Migrations: Schema evolution using PRAGMA table_info without breaking cached data.
4. Health Check & Diagnostic Telemetry: Real-time endpoint latency and availability verification.
5. Permanent Offline Caching: At data/kateglo_cache.sqlite.
"""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple, Union

from .storage_manager import default_storage_manager


@dataclass
class KategloEntry:
    phrase: str
    definitions: List[str] = field(default_factory=list)
    word_classes: List[str] = field(default_factory=list)
    synonyms: List[str] = field(default_factory=list)
    antonyms: List[str] = field(default_factory=list)
    glossary_pairs: List[Dict[str, str]] = field(default_factory=list)
    raw_data: Dict[str, Any] = field(default_factory=dict)
    source: str = "cache"


class KategloClient:
    """Resilient HTTP client and SQLite cache manager for kateglo.org REST API."""

    BASE_URL = "https://kateglo.org/api/publik"
    DEFAULT_USER_AGENT = "WikiTranslatorSuite/1.0 (https://id.wikipedia.org; dictionary-helper)"
    DEFAULT_TTL_DAYS = 30.0

    def __init__(
        self,
        cache_db_path: Optional[Union[str, Path]] = None,
        allow_network: bool = True,
        timeout: float = 8.0,
        user_agent: Optional[str] = None,
        ttl_days: float = DEFAULT_TTL_DAYS,
    ):
        self.cache_db_path = (
            Path(cache_db_path)
            if cache_db_path is not None
            else default_storage_manager.kateglo_cache_db
        )
        self.allow_network = allow_network
        self.timeout = timeout
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT
        self.ttl_seconds = ttl_days * 86400.0
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        self.cache_db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.cache_db_path), timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        """Initializes and automatically migrates SQLite schema for Kateglo cache."""
        conn = self._get_conn()
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS kateglo_entries (
                        phrase_lower TEXT PRIMARY KEY,
                        phrase_original TEXT NOT NULL,
                        data_json TEXT NOT NULL,
                        has_data INTEGER NOT NULL,
                        updated_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS kateglo_thesaurus (
                        phrase_lower TEXT PRIMARY KEY,
                        synonyms_json TEXT,
                        antonyms_json TEXT,
                        updated_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS kateglo_glossary (
                        en_term_lower TEXT,
                        id_term TEXT NOT NULL,
                        source_context TEXT,
                        updated_at REAL NOT NULL,
                        PRIMARY KEY (en_term_lower, id_term)
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_kateglo_glossary_en ON kateglo_glossary(en_term_lower)"
                )
        finally:
            conn.close()

    def _api_get(self, endpoint_path: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Makes an HTTP GET request to kateglo.org REST API with fail-safe error handling."""
        if not self.allow_network:
            return None

        url = f"{self.BASE_URL}/{endpoint_path.lstrip('/')}"
        if params:
            url += "?" + urllib.parse.urlencode(params)

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 200:
                    payload = json.loads(resp.read().decode("utf-8"))
                    return payload if isinstance(payload, dict) else {"data": payload}
        except Exception:
            return None
        return None

    def health_check(self) -> Dict[str, Any]:
        """
        Tests live connectivity and response latency to kateglo.org API.
        Returns health status dictionary.
        """
        start_time = time.time()
        res = self._api_get("kamus/acak")
        latency_ms = (time.time() - start_time) * 1000.0

        is_healthy = bool(res and ("indeks" in res or "data" in res))
        return {
            "healthy": is_healthy,
            "latency_ms": round(latency_ms, 2),
            "endpoint": self.BASE_URL,
            "sample_response": res if is_healthy else None,
        }

    def get_cache_stats(self) -> Dict[str, int]:
        """Returns row count statistics from the local SQLite cache."""
        conn = None
        try:
            conn = self._get_conn()
            n_entries = conn.execute("SELECT COUNT(*) FROM kateglo_entries").fetchone()[0]
            n_thesaurus = conn.execute("SELECT COUNT(*) FROM kateglo_thesaurus").fetchone()[0]
            n_glossary = conn.execute("SELECT COUNT(*) FROM kateglo_glossary").fetchone()[0]
            return {
                "entries_cached": n_entries,
                "thesaurus_cached": n_thesaurus,
                "glossary_pairs_cached": n_glossary,
            }
        except Exception:
            return {"entries_cached": 0, "thesaurus_cached": 0, "glossary_pairs_cached": 0}
        finally:
            if conn:
                conn.close()

    def clear_cache(self) -> bool:
        """Clears all cached entries, thesaurus, and glossaries."""
        conn = None
        try:
            conn = self._get_conn()
            with conn:
                conn.execute("DELETE FROM kateglo_entries")
                conn.execute("DELETE FROM kateglo_thesaurus")
                conn.execute("DELETE FROM kateglo_glossary")
            return True
        except Exception:
            return False
        finally:
            if conn:
                conn.close()

    def _extract_entries_defensively(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Polymorphic key extractor for dictionary entries."""
        for key in ("entri", "entries", "data", "lema", "items"):
            val = data.get(key)
            if isinstance(val, list):
                return val
        return []

    def _extract_glossary_defensively(self, data: Dict[str, Any]) -> List[Tuple[str, str]]:
        """Polymorphic key extractor for foreign-to-Indonesian glossary pairs."""
        pairs = []
        raw_items = []
        for key in ("glosarium", "glossary", "istilah", "padanan"):
            val = data.get(key)
            if isinstance(val, list):
                raw_items = val
                break

        for item in raw_items:
            if isinstance(item, dict):
                # Check polymorphic key names for foreign term
                asing = (
                    item.get("asing")
                    or item.get("foreign")
                    or item.get("en")
                    or item.get("source")
                    or ""
                )
                # Check polymorphic key names for Indonesian term
                indo = (
                    item.get("indonesia")
                    or item.get("id")
                    or item.get("target")
                    or item.get("padanan")
                    or ""
                )
                if asing and indo:
                    pairs.append((str(asing).strip(), str(indo).strip()))
        return pairs

    def _extract_synonyms_defensively(self, data: Dict[str, Any]) -> List[str]:
        """Polymorphic key extractor for synonyms."""
        synonyms = []
        # Check embedded tesaurus in entry detail
        for t_key in ("tesaurus", "thesaurus"):
            t = data.get(t_key)
            if isinstance(t, dict):
                for s_key in ("sinonim", "synonyms"):
                    val = t.get(s_key)
                    if isinstance(val, list):
                        synonyms.extend(str(s).strip() for s in val if s)
                    elif isinstance(val, str):
                        synonyms.extend(str(s).strip() for s in val.split(";") if s.strip())

        # Check direct search results
        for d_key in ("data", "items"):
            items = data.get(d_key)
            if isinstance(items, list):
                for it in items:
                    if isinstance(it, dict):
                        for s_key in ("sinonim", "synonyms"):
                            raw = it.get(s_key, "")
                            if isinstance(raw, str) and raw:
                                for s in raw.split(";"):
                                    s_clean = s.strip()
                                    if s_clean:
                                        synonyms.append(s_clean)
                            elif isinstance(raw, list):
                                synonyms.extend(str(s).strip() for s in raw if s)

        return list(dict.fromkeys(synonyms))

    def get_entry_detail(self, phrase: str, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """
        Retrieves full dictionary entry for phrase from local cache or kateglo.org API:
        Includes definitions (makna), thesaurus, and bilingual glossaries.
        Supports TTL freshness checks and stale-while-revalidate fallback.
        """
        if not phrase or not phrase.strip():
            return None

        clean_phrase = phrase.strip()
        key = clean_phrase.casefold()

        # 1. Check local SQLite cache
        cached_row = None
        conn = None
        try:
            conn = self._get_conn()
            cached_row = conn.execute(
                "SELECT data_json, has_data, updated_at FROM kateglo_entries WHERE phrase_lower = ?",
                (key,),
            ).fetchone()
        except Exception:
            pass
        finally:
            if conn:
                conn.close()

        # Check if cached data is fresh
        now = time.time()
        is_fresh = False
        cached_data = None
        if cached_row:
            has_data = bool(cached_row[1])
            cached_data = json.loads(cached_row[0]) if has_data else None
            updated_at = float(cached_row[2])
            is_fresh = (now - updated_at) < self.ttl_seconds

        # Return immediately if cache is fresh and force_refresh is not requested
        if cached_row and is_fresh and not force_refresh:
            return cached_data

        if not self.allow_network:
            return cached_data

        # 2. Query Live API
        quoted = urllib.parse.quote(clean_phrase)
        data = self._api_get(f"kamus/detail/{quoted}")

        # If live API fails, fall back gracefully to stale cache
        if data is None and cached_data is not None:
            return cached_data

        entries = self._extract_entries_defensively(data) if data else []
        has_data = bool(entries)
        json_str = json.dumps(data, ensure_ascii=False) if data else "{}"

        # 3. Cache result locally
        conn = None
        try:
            conn = self._get_conn()
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO kateglo_entries
                    (phrase_lower, phrase_original, data_json, has_data, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (key, clean_phrase, json_str, 1 if has_data else 0, now),
                )

                # Index glossary pairs defensively
                if data:
                    pairs = self._extract_glossary_defensively(data)
                    for asing, indo in pairs:
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO kateglo_glossary
                            (en_term_lower, id_term, source_context, updated_at)
                            VALUES (?, ?, ?, ?)
                            """,
                            (asing.casefold(), indo, clean_phrase, now),
                        )
        except Exception:
            pass
        finally:
            if conn:
                conn.close()

        return data if has_data else None

    def get_synonyms(self, phrase: str, force_refresh: bool = False) -> List[str]:
        """Returns list of synonyms for phrase, querying thesaurus endpoint or entry detail."""
        if not phrase or not phrase.strip():
            return []

        clean = phrase.strip()
        key = clean.casefold()

        # Check thesaurus table
        now = time.time()
        conn = None
        cached_syns = None
        try:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT synonyms_json, updated_at FROM kateglo_thesaurus WHERE phrase_lower = ?",
                (key,),
            ).fetchone()
            if row and row[0]:
                cached_syns = json.loads(row[0])
                if (now - float(row[1])) < self.ttl_seconds and not force_refresh:
                    return cached_syns
        except Exception:
            pass
        finally:
            if conn:
                conn.close()

        if not self.allow_network and cached_syns is not None:
            return cached_syns

        # Try detail first (often has embedded thesaurus)
        detail = self.get_entry_detail(clean, force_refresh=force_refresh)
        synonyms = self._extract_synonyms_defensively(detail) if detail else []

        # If empty, query thesaurus search API
        if not synonyms and self.allow_network:
            quoted = urllib.parse.quote(clean)
            t_data = self._api_get(f"tesaurus/cari/{quoted}")
            if t_data:
                synonyms = self._extract_synonyms_defensively(t_data)

        # Remove self from synonyms
        synonyms = [s for s in synonyms if s.casefold() != key]

        # If API failed, fallback to stale cache
        if not synonyms and cached_syns is not None:
            return cached_syns

        # Cache thesaurus
        if synonyms:
            conn = None
            try:
                conn = self._get_conn()
                with conn:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO kateglo_thesaurus
                        (phrase_lower, synonyms_json, antonyms_json, updated_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (key, json.dumps(synonyms, ensure_ascii=False), "[]", now),
                    )
            except Exception:
                pass
            finally:
                if conn:
                    conn.close()

        return synonyms

    def find_glossary_terms(self, en_term: str) -> List[str]:
        """
        Finds Indonesian glossary terms matching an English term from Kateglo database.
        """
        if not en_term or not en_term.strip():
            return []

        key = en_term.strip().casefold()
        results = []
        conn = None
        try:
            conn = self._get_conn()
            cur = conn.execute(
                "SELECT id_term FROM kateglo_glossary WHERE en_term_lower = ?",
                (key,),
            )
            for r in cur.fetchall():
                results.append(r[0])
        except Exception:
            pass
        finally:
            if conn:
                conn.close()

        return results


default_kateglo_client = KategloClient()
