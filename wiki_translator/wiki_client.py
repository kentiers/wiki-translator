"""
Wikipedia REST and Action API client for fetching and parsing wikitext.

Supports fetching full wikitext from en.wikipedia.org and splitting into logical
sections (== Section ==, === Subsection ===) for independent high-precision translation.
"""

from dataclasses import dataclass
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import List, Optional, Tuple


class WikipediaAPIError(Exception):
    """Base exception for Wikipedia API errors."""
    pass


class PageNotFoundError(WikipediaAPIError):
    """Raised when the requested Wikipedia page does not exist."""
    pass


class DisambiguationPageError(WikipediaAPIError):
    """Raised when the requested title is a disambiguation page."""

    def __init__(self, title: str, options: Optional[List[str]] = None):
        self.title = title
        self.options = options or []
        msg = f"'{title}' is a disambiguation page."
        if self.options:
            msg += f" Potential options: {', '.join(self.options[:5])}"
        super().__init__(msg)


class RateLimitExceededError(WikipediaAPIError):
    """Raised when Wikipedia API rate limit (HTTP 429) is encountered."""
    pass


@dataclass
class WikiSection:
    index: int
    title: str
    level: int  # 1 for main article title, 2 for == Section ==, 3 for === Subsection ===, etc.
    header_raw: str  # Raw header markup e.g. "== History =="
    content: str  # Wikitext content under this header
    word_count: int
    char_count: int
    translated_content: Optional[str] = None
    is_cached: bool = False
    is_skipped: bool = False
    @property
    def full_source(self) -> str:
        if self.header_raw:
            return f"{self.header_raw}\n{self.content}".strip()
        return self.content.strip()

    @property
    def full_translated(self) -> str:
        res = self.translated_content or self.content
        if self.header_raw and self.index > 0:
            # If header is not in translated_content, return with header
            return res.strip()
        return res.strip()


class WikipediaClient:
    """Client for en.wikipedia.org / id.wikipedia.org Action API."""

    def __init__(self, lang: str = "en", user_agent: Optional[str] = None):
        self.lang = lang
        self.api_url = f"https://{lang}.wikipedia.org/w/api.php"
        self.user_agent = (
            user_agent
            or "WikiTranslatorGradeA/1.0 (https://id.wikipedia.org; translator-tool)"
        )
        self.last_page_id: Optional[int] = None
        self.last_revision_id: Optional[int] = None

    def fetch_wikitext(
        self,
        page_title: str,
        follow_redirects: bool = True,
        check_disambiguation: bool = True,
        revid: Optional[int] = None,
    ) -> str:
        """
        Fetches the raw wikitext content for a given page title (or specific revision ID).
        Handles redirects, missing pages, disambiguation detection, and rate limits.
        """
        if revid is not None:
            params = {
                "action": "query",
                "prop": "revisions|categories|pageprops",
                "revids": str(revid),
                "rvslots": "*",
                "rvprop": "ids|content",
                "formatversion": "2",
                "format": "json",
            }
        else:
            params = {
                "action": "query",
                "prop": "revisions|categories|pageprops",
                "titles": page_title,
                "rvslots": "*",
                "rvprop": "ids|content",
                "formatversion": "2",
                "format": "json",
                "cllimit": "max",
            }
            if follow_redirects:
                params["redirects"] = "1"
        query_str = urllib.parse.urlencode(params)
        url = f"{self.api_url}?{query_str}"

        req = urllib.request.Request(
            url,
            headers={"User-Agent": self.user_agent},
            method="GET",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as he:
            if he.code == 429:
                raise RateLimitExceededError(
                    f"Wikipedia API rate limit exceeded (HTTP 429) while fetching '{page_title}'."
                ) from he
            raise WikipediaAPIError(f"HTTP error {he.code} fetching Wikipedia page '{page_title}': {he.reason}") from he
        except Exception as e:
            raise WikipediaAPIError(f"Network error fetching Wikipedia page '{page_title}': {e}") from e

        query = data.get("query", {})
        pages = query.get("pages", [])
        if not pages:
            raise PageNotFoundError(f"No pages found for title: {page_title}")

        page = pages[0]
        if page.get("missing"):
            raise PageNotFoundError(f"Wikipedia page not found: {page_title}")

        self.last_page_id = page.get("pageid")

        # Disambiguation check
        if check_disambiguation:
            pageprops = page.get("pageprops", {})
            is_disambig = "disambiguation" in pageprops
            if not is_disambig:
                for cat in page.get("categories", []):
                    cat_title = cat.get("title", "").lower()
                    if "disambiguation" in cat_title or "halaman disambiguasi" in cat_title:
                        is_disambig = True
                        break

            if is_disambig:
                raise DisambiguationPageError(title=page_title)

        revisions = page.get("revisions", [])
        if not revisions:
            raise PageNotFoundError(f"No revision content found for: {page_title}")

        rev = revisions[0]
        self.last_revision_id = revid if revid is not None else rev.get("revid")
        slots = rev.get("slots", {})
        main_slot = slots.get("main", {})
        content = main_slot.get("content", "")
        return content

    @staticmethod
    def _find_protected_spans(wikitext: str) -> List[Tuple[int, int]]:
        """
        Finds byte/character spans in wikitext that should NOT be split across sections:
        - Tags: <nowiki>, <math>, <ref>, <syntaxhighlight>, <code>, <pre>, <!-- comments -->
        - Tables: {| ... |}
        - Multi-line templates: {{ ... }}
        """
        spans: List[Tuple[int, int]] = []

        # HTML / XML style tags and comments
        tag_patterns = [
            re.compile(r"<!--[\s\S]*?-->", re.IGNORECASE),
            re.compile(r"<math[\s\S]*?</math>", re.IGNORECASE),
            re.compile(r"<nowiki[\s\S]*?</nowiki>", re.IGNORECASE),
            re.compile(r"<syntaxhighlight[\s\S]*?</syntaxhighlight>", re.IGNORECASE),
            re.compile(r"<source[\s\S]*?</source>", re.IGNORECASE),
            re.compile(r"<pre[\s\S]*?</pre>", re.IGNORECASE),
            re.compile(r"<code[\s\S]*?</code>", re.IGNORECASE),
            re.compile(r"<ref[^>/]*>[\s\S]*?</ref>", re.IGNORECASE),
        ]

        for pat in tag_patterns:
            for match in pat.finditer(wikitext):
                spans.append((match.start(), match.end()))

        # Wikitext tables: {| ... |}
        table_starts: List[int] = []
        for m in re.finditer(r"^\{\|", wikitext, re.MULTILINE):
            table_starts.append(m.start())

        for start in table_starts:
            end_m = re.search(r"^\|\}\s*$", wikitext[start:], re.MULTILINE)
            if end_m:
                spans.append((start, start + end_m.end()))

        # Multi-line template blocks: {{ ... }} (track balanced nested braces)
        i = 0
        n = len(wikitext)
        while i < n - 1:
            if wikitext[i:i+2] == "{{":
                tpl_start = i
                depth = 1
                i += 2
                while i < n - 1 and depth > 0:
                    if wikitext[i:i+2] == "{{":
                        depth += 1
                        i += 2
                    elif wikitext[i:i+2] == "}}":
                        depth -= 1
                        i += 2
                    else:
                        i += 1
                if depth == 0:
                    spans.append((tpl_start, i))
            else:
                i += 1

        return spans

    def split_sections(self, wikitext: str, page_title: str = "Lead") -> List[WikiSection]:
        """
        Splits wikitext by section headings (== Section ==, === Sub ===, etc.).
        Ensures headings inside protected blocks (math, ref, tables, comments, templates) are preserved.
        Returns list of WikiSection objects.
        """
        protected_spans = self._find_protected_spans(wikitext)

        def is_in_protected_span(pos: int) -> bool:
            for start, end in protected_spans:
                if start <= pos < end:
                    return True
            return False

        # Regex matching == Heading == at beginning of line
        section_pattern = re.compile(r"^(={2,6})\s*(.+?)\s*\1\s*$", re.MULTILINE)

        raw_matches = list(section_pattern.finditer(wikitext))
        matches = [m for m in raw_matches if not is_in_protected_span(m.start())]
        sections: List[WikiSection] = []

        if not matches:
            word_count = len(wikitext.split())
            return [
                WikiSection(
                    index=0,
                    title="Lead / Pengantar Utama",
                    level=1,
                    header_raw="",
                    content=wikitext.strip(),
                    word_count=word_count,
                    char_count=len(wikitext),
                )
            ]
        # 1. Lead section (from start of text to first heading match)
        first_match = matches[0]
        lead_content = wikitext[: first_match.start()].strip()
        if lead_content:
            sections.append(
                WikiSection(
                    index=0,
                    title="Lead / Pengantar Utama",
                    level=1,
                    header_raw="",
                    content=lead_content,
                    word_count=len(lead_content.split()),
                    char_count=len(lead_content),
                )
            )

        # 2. Subsequent sections
        for idx, match in enumerate(matches):
            header_markup = match.group(0)
            equals_sign = match.group(1)
            title = match.group(2).strip()
            level = len(equals_sign)

            start_pos = match.end()
            if idx + 1 < len(matches):
                end_pos = matches[idx + 1].start()
            else:
                end_pos = len(wikitext)

            section_body = wikitext[start_pos:end_pos].strip()
            total_content = f"{header_markup}\n{section_body}".strip() if section_body else header_markup

            sections.append(
                WikiSection(
                    index=len(sections),
                    title=title,
                    level=level,
                    header_raw=header_markup,
                    content=section_body,
                    word_count=len(section_body.split()),
                    char_count=len(section_body),
                )
            )

        return sections
    def fetch_sections(
        self,
        page_title: str,
        follow_redirects: bool = True,
        check_disambiguation: bool = True,
        revid: Optional[int] = None,
    ) -> List[WikiSection]:
        """
        Fetches wikitext for a given title/revid and splits it into logical WikiSections.
        """
        wikitext = self.fetch_wikitext(
            page_title=page_title,
            follow_redirects=follow_redirects,
            check_disambiguation=check_disambiguation,
            revid=revid,
        )
        return self.split_sections(wikitext, page_title=page_title)
