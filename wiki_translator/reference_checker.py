"""
Reference Checker module for dead link detection and automated Wayback Machine
(archive.org) archive-url injection for Wikipedia citations lacking archive backups.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
from .storage_manager import default_storage_manager


class ReferenceChecker:
    """
    Scans wikitext for citation templates ({{cite web}}, {{cite news}}, {{cite journal}}, etc.)
    that have a `url=` parameter but lack an `archive-url=` backup.
    Queries the official Wayback Machine Availability API:
    https://archive.org/wayback/available?url={encoded_url} (timeout: 5s).
    If an archived snapshot exists, injects `|archive-url={url} |archive-date={date} |url-status=live`
    into the citation template safely.
    Caches lookups in SQLite `.cache/wayback_cache.db`.
    """

    # Citation templates supported for archive injection
    CITE_TEMPLATE_NAMES = {
        "cite web",
        "cite news",
        "cite journal",
        "cite book",
        "cite paper",
        "cite magazine",
        "cite report",
        "cite conference",
        "cite press release",
        "cite podcast",
        "cite av media",
        "cite video",
        "citation",
        "rujukan web",
        "rujukan berita",
        "rujukan jurnal",
    }

    WAYBACK_API_URL = "https://archive.org/wayback/available"

    def __init__(
        self,
        cache_db_path: Optional[Union[str, Path]] = None,
        user_agent: Optional[str] = None,
        timeout: float = 5.0,
    ) -> None:
        self.cache_db_path = (
            Path(cache_db_path)
            if cache_db_path is not None
            else default_storage_manager.wayback_cache_db
        )
        self.user_agent = (
            user_agent
            or "WikiTranslatorReferenceChecker/1.0 (https://id.wikipedia.org; translator-tool)"
        )
        self.timeout = timeout
        self._init_db()

    def _init_db(self) -> None:
        """Initializes the SQLite schema for wayback cache."""
        self.cache_db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.cache_db_path)
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS wayback_cache (
                        url TEXT PRIMARY KEY,
                        has_archive INTEGER NOT NULL,
                        archive_url TEXT,
                        archive_date TEXT,
                        checked_at REAL
                    )
                    """
                )
        finally:
            conn.close()

    def get_cached_archive(self, url: str) -> Optional[Tuple[bool, Optional[str], Optional[str]]]:
        """
        Retrieves cached archive lookup for a URL.
        Returns:
            (has_archive, archive_url, archive_date) or None if not cached.
        """
        clean_url = url.strip()
        conn = sqlite3.connect(self.cache_db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT has_archive, archive_url, archive_date FROM wayback_cache WHERE url = ?",
                (clean_url,),
            )
            row = cur.fetchone()
            if row:
                return bool(row[0]), row[1], row[2]
            return None
        finally:
            conn.close()

    def cache_archive(
        self,
        url: str,
        has_archive: bool,
        archive_url: Optional[str] = None,
        archive_date: Optional[str] = None,
    ) -> None:
        """Caches archive lookup result in SQLite."""
        clean_url = url.strip()
        now = time.time()
        conn = sqlite3.connect(self.cache_db_path)
        try:
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO wayback_cache (url, has_archive, archive_url, archive_date, checked_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (clean_url, 1 if has_archive else 0, archive_url, archive_date, now),
                )
        finally:
            conn.close()

    def query_wayback_api(
        self,
        url: str,
        allow_network: bool = True,
    ) -> Optional[Tuple[str, str]]:
        """
        Queries Wayback Machine Availability API for snapshot of url.
        Returns (archive_url, archive_date_YYYY_MM_DD) if available, else None.
        Checks local SQLite cache first.
        """
        clean_url = url.strip()
        if not clean_url:
            return None

        # 1. Check SQLite cache
        cached = self.get_cached_archive(clean_url)
        if cached is not None:
            has_archive, archive_url, archive_date = cached
            if has_archive and archive_url and archive_date:
                return archive_url, archive_date
            return None

        # 2. If network not allowed (offline / dry run), do not query
        if not allow_network:
            return None

        # 3. Query Wayback Machine API
        api_query_url = f"{self.WAYBACK_API_URL}?url={urllib.parse.quote(clean_url, safe=':/?#[]@!$&()*+,;=')}"
        req = urllib.request.Request(
            api_query_url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                if response.status != 200:
                    self.cache_archive(clean_url, False)
                    return None
                data = json.loads(response.read().decode("utf-8"))

            archived_snapshots = data.get("archived_snapshots", {})
            closest = archived_snapshots.get("closest")
            if not closest or not closest.get("available"):
                self.cache_archive(clean_url, False)
                return None

            archive_url = closest.get("url")
            raw_timestamp = str(closest.get("timestamp", ""))

            if not archive_url:
                self.cache_archive(clean_url, False)
                return None

            # Format timestamp YYYYMMDDhhmmss -> YYYY-MM-DD
            archive_date = ""
            if len(raw_timestamp) >= 8 and raw_timestamp[:8].isdigit():
                archive_date = f"{raw_timestamp[:4]}-{raw_timestamp[4:6]}-{raw_timestamp[6:8]}"
            else:
                archive_date = time.strftime("%Y-%m-%d")

            self.cache_archive(clean_url, True, archive_url, archive_date)
            return archive_url, archive_date

        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            # Network failure or timeout; do not cache failure permanently or do safe cache
            return None

    @classmethod
    def _find_matching_brace(cls, text: str, start_index: int) -> int:
        """
        Finds index of the closing '}}' matching the '{{' at start_index.
        Handles nested braces properly.
        Returns ending index (position right after the closing '}}'), or -1 if unclosed.
        """
        length = len(text)
        depth = 0
        i = start_index

        while i < length:
            if text[i : i + 2] == "{{":
                depth += 1
                i += 2
            elif text[i : i + 2] == "}}":
                depth -= 1
                i += 2
                if depth == 0:
                    return i
            else:
                i += 1
        return -1

    def enrich_citations_with_archives(
        self,
        wikitext: str,
        allow_network: bool = True,
    ) -> str:
        """
        Scans wikitext for citation templates lacking `archive-url`.
        Queries Wayback API (or cache) and injects:
        |archive-url={url} |archive-date={date} |url-status=live
        safely into each citation.
        """
        if not wikitext:
            return ""

        output_parts: List[str] = []
        last_idx = 0
        length = len(wikitext)

        i = 0
        while i < length:
            if wikitext[i : i + 2] == "{{":
                close_idx = self._find_matching_brace(wikitext, i)
                if close_idx == -1:
                    i += 2
                    continue

                tmpl_full = wikitext[i:close_idx]
                enriched_tmpl = self._process_single_citation(tmpl_full, allow_network=allow_network)

                output_parts.append(wikitext[last_idx:i])
                output_parts.append(enriched_tmpl)
                last_idx = close_idx
                i = close_idx
            else:
                i += 1

        output_parts.append(wikitext[last_idx:])
        return "".join(output_parts)

    def _process_single_citation(
        self,
        tmpl_text: str,
        allow_network: bool = True,
    ) -> str:
        """
        Inspects a single template string {{cite ... |url=...}}.
        If it's a target citation template, has `url=`, and lacks `archive-url=`,
        attempts to find snapshot and inject archive parameters.
        """
        # Strip outer {{ and }}
        if not (tmpl_text.startswith("{{") and tmpl_text.endswith("}}")):
            return tmpl_text

        inner = tmpl_text[2:-2]
        pipe_split = inner.split("|", 1)
        tmpl_name = pipe_split[0].strip().lower()

        if tmpl_name not in self.CITE_TEMPLATE_NAMES:
            return tmpl_text

        if len(pipe_split) < 2:
            return tmpl_text

        params_text = pipe_split[1]

        # Check if archive-url or archiveurl is already present
        if re.search(r"\|\s*archive-?url\s*=", "|" + params_text, flags=re.IGNORECASE):
            return tmpl_text

        # Find url= parameter
        url_match = re.search(r"\|\s*url\s*=\s*([^|}\n]+)", "|" + params_text, flags=re.IGNORECASE)
        if not url_match:
            return tmpl_text

        raw_url = url_match.group(1).strip()
        if not (raw_url.startswith("http://") or raw_url.startswith("https://")):
            return tmpl_text

        # Lookup archive
        result = self.query_wayback_api(raw_url, allow_network=allow_network)
        if not result:
            return tmpl_text

        archive_url, archive_date = result

        # Inject archive parameters before closing }}
        # Check formatting/spacing convention in the template
        # Usually: " |archive-url=... |archive-date=... |url-status=live"
        injection = f" |archive-url={archive_url} |archive-date={archive_date} |url-status=live"

        # If template ends with whitespace/newline before }}, preserve it
        trailing_space_match = re.search(r"(\s+)$", inner)
        if trailing_space_match:
            trailing_ws = trailing_space_match.group(1)
            new_inner = inner[: -len(trailing_ws)] + injection + trailing_ws
        else:
            new_inner = inner + injection

        return f"{{{{{new_inner}}}}}"


default_reference_checker = ReferenceChecker()
