"""
Kateglo REST API Client and Local Cache Manager for Wiki Translator Suite.

Connects to https://kateglo.org/api/publik to provide:
1. KBBI dictionary definitions and part-of-speech metadata.
2. Thesaurus (synonyms & antonyms) to enrich lexical variety.
3. Cross-language bilingual glossary pairs (English <-> Indonesian).
4. Permanent offline SQLite caching at data/kateglo_cache.sqlite.
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
    """HTTP client and SQLite cache manager for kateglo.org REST API."""

    BASE_URL = "https://kateglo.org/api/publik"
    DEFAULT_USER_AGENT = "WikiTranslatorSuite/1.0 (https://id.wikipedia.org; dictionary-helper)"

    def __init__(
        self,
        cache_db_path: Optional[Union[str, Path]] = None,
        allow_network: bool = True,
        timeout: float = 8.0,
        user_agent: Optional[str] = None,
    ):
        self.cache_db_path = (
            Path(cache_db_path)
            if cache_db_path is not None
            else default_storage_manager.kateglo_cache_db
        )
        self.allow_network = allow_network
        self.timeout = timeout
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        self.cache_db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.cache_db_path), timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        """Initializes SQLite schema for Kateglo dictionary and thesaurus cache."""
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
        finally:
            conn.close()

    def _api_get(self, endpoint_path: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Makes an HTTP GET request to kateglo.org REST API."""
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

    def get_entry_detail(self, phrase: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves full dictionary entry for phrase from local cache or kateglo.org API:
        Includes definitions (makna), thesaurus, and bilingual glossaries.
        """
        if not phrase or not phrase.strip():
            return None

        clean_phrase = phrase.strip()
        key = clean_phrase.casefold()

        # 1. Check local SQLite cache
        conn = None
        try:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT data_json, has_data FROM kateglo_entries WHERE phrase_lower = ?",
                (key,),
            ).fetchone()
            if row:
                has_data = bool(row[1])
                return json.loads(row[0]) if has_data else None
        except Exception:
            pass
        finally:
            if conn:
                conn.close()

        if not self.allow_network:
            return None

        # 2. Query Live API
        quoted = urllib.parse.quote(clean_phrase)
        data = self._api_get(f"kamus/detail/{quoted}")

        has_data = bool(data and data.get("entri"))
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
                    (key, clean_phrase, json_str, 1 if has_data else 0, time.time()),
                )

                # Index glossary pairs into searchable table
                if data and "glosarium" in data:
                    for g in data["glosarium"]:
                        asing = g.get("asing", "").strip()
                        indo = g.get("indonesia", "").strip()
                        if asing and indo:
                            conn.execute(
                                """
                                INSERT OR IGNORE INTO kateglo_glossary
                                (en_term_lower, id_term, source_context, updated_at)
                                VALUES (?, ?, ?, ?)
                                """,
                                (asing.casefold(), indo, clean_phrase, time.time()),
                            )
        except Exception:
            pass
        finally:
            if conn:
                conn.close()

        return data if has_data else None

    def get_synonyms(self, phrase: str) -> List[str]:
        """Returns list of synonyms for phrase, querying thesaurus endpoint or entry detail."""
        if not phrase or not phrase.strip():
            return []

        clean = phrase.strip()
        key = clean.casefold()

        # Check thesaurus table
        conn = None
        try:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT synonyms_json FROM kateglo_thesaurus WHERE phrase_lower = ?",
                (key,),
            ).fetchone()
            if row and row[0]:
                return json.loads(row[0])
        except Exception:
            pass
        finally:
            if conn:
                conn.close()

        # Try detail first (often has embedded thesaurus)
        detail = self.get_entry_detail(clean)
        synonyms = []
        if detail and "tesaurus" in detail:
            t = detail["tesaurus"]
            if isinstance(t, dict):
                synonyms = t.get("sinonim", []) or []

        # If empty, query thesaurus search API
        if not synonyms and self.allow_network:
            quoted = urllib.parse.quote(clean)
            t_data = self._api_get(f"tesaurus/cari/{quoted}")
            if t_data and "data" in t_data:
                for item in t_data["data"]:
                    raw_syn = item.get("sinonim", "")
                    if raw_syn:
                        for s in raw_syn.split(";"):
                            s_clean = s.strip()
                            if s_clean and s_clean.casefold() != key:
                                synonyms.append(s_clean)

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
                        (key, json.dumps(synonyms, ensure_ascii=False), "[]", time.time()),
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
