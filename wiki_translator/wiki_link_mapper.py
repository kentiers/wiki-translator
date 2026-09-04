"""
Wikipedia Live Link & Category Validator and Mapper (en.wikipedia -> id.wikipedia).

Features:
1. Category Translation & Existence Checker:
   - Translates categories `[[Category:English Name]]` -> `[[Kategori:Nama Indonesia]]`.
   - Verifies whether `Kategori:Nama Indonesia` exists on id.wikipedia.org.
   - If not found directly, resolves via en.wikipedia.org / Wikidata langlinks.
   - Formats existing category as `[[Kategori:Nama Yang Ada]]`.
   - If not yet created on id.wikipedia.org, marks with a clean comment tag `<!-- Kategori belum ada di id.wiki: [[Kategori:Nama Indonesia]] -->` or creates/flags appropriately.
2. Wikilink Resolver & Red-Link Safeguard:
   - Scans internal wikilinks `[[Target]]` or `[[Target|Anchor]]`.
   - Resolves `Target` to official Indonesian article title via en -> id langlinks or direct id.wikipedia.org check.
   - If `Target` exists on id.wikipedia.org, maps to `[[Target ID|Anchor]]` (or `[[Target ID]]` if same).
   - If `Target` does NOT exist on id.wikipedia.org (red link):
     * Formats with `{{ill|Nama Indonesia|en|Target English}}` or `[[Nama Indonesia]]` based on configuration.
3. Persistent SQLite Cache:
   - Caches existence and mapping results at `.cache/wiki_links_cache.db`.
"""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
import urllib.error
import urllib.parse
import urllib.request


@dataclass
class LinkResolution:
    original_target: str
    target_id: Optional[str] = None
    exists_on_id: bool = False
    source: str = "unknown"  # "id_direct", "en_langlink", "wikidata", "cache", "fallback"
    is_disambiguation: bool = False
    disambiguation_target: Optional[str] = None

@dataclass
class CategoryResolution:
    original_category: str
    id_category: Optional[str] = None
    exists_on_id: bool = False
    source: str = "unknown"


# Standard known category root prefixes / keyword translations (English -> Indonesian)
STANDARD_CATEGORY_PREFIXES: Dict[str, str] = {
    "category:": "Kategori:",
    "categories:": "Kategori:",
    "kategori:": "Kategori:",
}

COMMON_CATEGORY_REPLACEMENTS: List[Tuple[re.Pattern, str]] = [
    # Complex / specific film patterns
(re.compile(r"\b(\d{4})\s+action\s+thriller\s+films\b", re.IGNORECASE), r"Film cerita seru laga tahun \1"),
(re.compile(r"\bBritish\s+action\s+thriller\s+films\b", re.IGNORECASE), "Film cerita seru laga Britania Raya"),
(re.compile(r"\bAmerican\s+action\s+thriller\s+films\b", re.IGNORECASE), "Film cerita seru laga Amerika Serikat"),
(re.compile(r"\baction\s+thriller\s+films\b", re.IGNORECASE), "Film cerita seru laga"),
    (re.compile(r"\b(\d{4})\s+British\s+films\b", re.IGNORECASE), r"Film Britania Raya tahun \1"),
    (re.compile(r"\b(\d{4})\s+American\s+films\b", re.IGNORECASE), r"Film Amerika Serikat tahun \1"),
    (re.compile(r"\bupcoming\s+English-language\s+films\b", re.IGNORECASE), "Film mendatang berbahasa Inggris"),
    (re.compile(r"\b(\d{4})\s+English-language\s+films\b", re.IGNORECASE), r"Film berbahasa Inggris tahun \1"),
    (re.compile(r"\bEnglish-language\s+films\b", re.IGNORECASE), "Film berbahasa Inggris"),
    (re.compile(r"\bBritish\s+films\b", re.IGNORECASE), "Film Britania Raya"),
    (re.compile(r"\bAmerican\s+films\b", re.IGNORECASE), "Film Amerika Serikat"),
    (re.compile(r"\bfilms\s+directed\s+by\s+([^\]]+)", re.IGNORECASE), r"Film yang disutradarai oleh \1"),
    # General year patterns
    (re.compile(r"\b(\d{4})\s+films\b", re.IGNORECASE), r"Film tahun \1"),
    (re.compile(r"\b(\d{4})\s+television\s+series\b", re.IGNORECASE), r"Serial televisi tahun \1"),
    (re.compile(r"\b(\d{4})\s+video\s+games\b", re.IGNORECASE), r"Permainan video tahun \1"),
    (re.compile(r"\b(\d{4})\s+births\b", re.IGNORECASE), r"Kelahiran \1"),
    (re.compile(r"\b(\d{4})\s+deaths\b", re.IGNORECASE), r"Kematian \1"),
    (re.compile(r"\bestablished\s+in\s+(\d{4})\b", re.IGNORECASE), r"Pendirian \1"),
    (re.compile(r"\bdisestablished\s+in\s+(\d{4})\b", re.IGNORECASE), r"Pembubaran \1"),
    (re.compile(r"\bby\s+country\b", re.IGNORECASE), "menurut negara"),
    (re.compile(r"\bby\s+year\b", re.IGNORECASE), "menurut tahun"),
    # Demonyms / nationalities
    (re.compile(r"\bAmerican\b", re.IGNORECASE), "Amerika Serikat"),
    (re.compile(r"\bBritish\b", re.IGNORECASE), "Britania Raya"),
    (re.compile(r"\bIndonesian\b", re.IGNORECASE), "Indonesia"),
    (re.compile(r"\bJapanese\b", re.IGNORECASE), "Jepang"),
    (re.compile(r"\bFrench\b", re.IGNORECASE), "Prancis"),
    (re.compile(r"\bGerman\b", re.IGNORECASE), "Jerman"),
    # General entities / nouns
    (re.compile(r"\btelevision\s+series\b", re.IGNORECASE), "Serial televisi"),
    (re.compile(r"\btv\s+series\b", re.IGNORECASE), "Serial televisi"),
    (re.compile(r"\bvideo\s+games\b", re.IGNORECASE), "Permainan video"),
    (re.compile(r"\bfilms\b", re.IGNORECASE), "Film"),
    (re.compile(r"\bfilm\b", re.IGNORECASE), "Film"),
    (re.compile(r"\bactors\b", re.IGNORECASE), "Pemeran"),
    (re.compile(r"\bactresses\b", re.IGNORECASE), "Pemeran wanita"),
    (re.compile(r"\bdirectors\b", re.IGNORECASE), "Sutradara"),
    (re.compile(r"\bproducers\b", re.IGNORECASE), "Produser"),
    (re.compile(r"\bscreenwriters\b", re.IGNORECASE), "Penulis skenario"),
    (re.compile(r"\balbums\b", re.IGNORECASE), "Album"),
    (re.compile(r"\bsongs\b", re.IGNORECASE), "Lagu"),
    (re.compile(r"\bsingers\b", re.IGNORECASE), "Penyanyi"),
    (re.compile(r"\bmusicians\b", re.IGNORECASE), "Musisi"),
    (re.compile(r"\bnovels\b", re.IGNORECASE), "Novel"),
    (re.compile(r"\bbooks\b", re.IGNORECASE), "Buku"),
    (re.compile(r"\bcountries\b", re.IGNORECASE), "Negara"),
    (re.compile(r"\bcities\b", re.IGNORECASE), "Kota"),
    (re.compile(r"\bcompanies\b", re.IGNORECASE), "Perusahaan"),
    (re.compile(r"\buniversity\b", re.IGNORECASE), "Universitas"),
    (re.compile(r"\buniversities\b", re.IGNORECASE), "Universitas"),
]

ILL_EN_DISAMBIGUATION_RULES: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\(film\s+([A-Za-z\s]+?)\s+(\d{4})\)", re.IGNORECASE), r"(\2 \1 film)"),
    (re.compile(r"\(film\s+(\d{4})\)", re.IGNORECASE), r"(\1 film)"),
    (re.compile(r"\(serial\s+televisi\s+(\d{4})\)", re.IGNORECASE), r"(\1 television series)"),
    (re.compile(r"\(serial\s+televisi\)", re.IGNORECASE), r"(television series)"),
    (re.compile(r"\(sutradara\)", re.IGNORECASE), r"(director)"),
    (re.compile(r"\((?:pemeran|aktor)\)", re.IGNORECASE), r"(actor)"),
    (re.compile(r"\(penulis\)", re.IGNORECASE), r"(writer)"),
    (re.compile(r"\((?:musisi|pemusik)\)", re.IGNORECASE), r"(musician)"),
    (re.compile(r"\(politikus\)", re.IGNORECASE), r"(politician)"),
    (re.compile(r"\(pesepak\s+bola\)", re.IGNORECASE), r"(footballer)"),
]

# Static / canonical link mappings (English wikilink target -> Indonesian wikilink target)
KNOWN_PAGE_MAPPINGS: Dict[str, str] = {
    "israelis": "Orang Israel",
    "israeli": "Orang Israel",
    "action thriller": "Film laga",
    "action thriller film": "Film laga",
    "film cerita seru laga": "Film laga",
    "cerita seru laga": "Film laga",
    "saint petersburg": "Sankt-Peterburg",
    "st. petersburg": "Sankt-Peterburg",
    "people from saint petersburg": "Kategori:Tokoh dari Sankt-Peterburg",
    "people from st. petersburg": "Kategori:Tokoh dari Sankt-Peterburg",
    "saint petersburg state university": "Universitas Negeri Sankt-Peterburg",
    "st. petersburg state university": "Universitas Negeri Sankt-Peterburg",
}


def sanitize_ill_foreign_targets(wikitext: str) -> str:
    """
    Scans all {{ill|Target_ID|...}} templates and:
    1. Reverses Indonesian disambiguators in parameter 3 (en target) back to canonical English.
    2. Cleans broken nested language prefixes like {{ill|Target|en|:pt:Foreign}} -> {{ill|Target|pt|Foreign}}.
    3. Cleans leading colon in language targets like {{ill|Target|pt|:Foreign}} -> {{ill|Target|pt|Foreign}}.
    """
    # 1. Clean broken nested/prefix language ill like {{ill|Target_ID|en|:([a-z]{2,3}):Foreign}}
    nested_lang_pat = re.compile(r"\{\{ill\|([^|}]+)\|en\|:?([a-z]{2,3}):([^|}]+)(.*?)\}\}", re.IGNORECASE)
    wikitext = nested_lang_pat.sub(r"{{ill|\1|\2|\3\4}}", wikitext)

    # 2. Clean leading colon in lang target: {{ill|Title|lang|:Target...}} -> {{ill|Title|lang|Target...}}
    colon_target_pat = re.compile(r"\{\{ill\|([^|}]+)\|([a-z]{2,3})\|:([^|}]+)(.*?)\}\}", re.IGNORECASE)
    wikitext = colon_target_pat.sub(r"{{ill|\1|\2|\3\4}}", wikitext)

    # 3. Standard en disambiguation sanitation
    ill_pattern = re.compile(r"\{\{ill\|([^|}]+)\|en\|([^|}]+)(.*?)\}\}", re.IGNORECASE)

    def repl(m: re.Match) -> str:
        target_id = m.group(1).strip()
        en_target = m.group(2).strip()
        rest = m.group(3)

        # Safeguard: If target_id or en_target is Indonesian 'film cerita seru laga' or 'cerita seru laga'
        if en_target.lower() in ("film cerita seru laga", "cerita seru laga"):
            return "[[Film laga|cerita seru laga]]"
        if target_id.lower() in ("film cerita seru laga", "cerita seru laga") and en_target.lower() in ("action thriller", "action thriller film"):
            return "[[Film laga|cerita seru laga]]"

        # Specific broken / erroneous en targets that mistakenly received Indonesian strings
        if en_target.lower() in ("pendidikan koedukasi", "koedukasi"):
            en_target = "Mixed-sex education"
        elif en_target.lower() in ("tanah dan kebebasan", "tanah dan kebebasan (rusia)"):
            en_target = "Land and Liberty (Russia)"
        elif en_target.lower() == target_id.lower() and re.search(r"\b(?:perhimpunan|kongres|sekolah|gerakan|partai|kementerian)\b", en_target, re.IGNORECASE):
            # If target_id and foreign en target are identical Indonesian phrases that don't exist on en.wiki
            return f"[[{target_id}]]"

        for pat, replacement in ILL_EN_DISAMBIGUATION_RULES:
            en_target = pat.sub(replacement, en_target)

        return f"{{{{ill|{target_id}|en|{en_target}{rest}}}}}"

    return ill_pattern.sub(repl, wikitext)


class WikiLinkMapper:
    """
    Automated Wikipedia Live Link & Category Validator and Mapper.
    
    Handles:
    - Verifying id.wikipedia.org article / category existence.
    - Resolving EN wikilinks to ID titles via langlinks / Wikidata.
    - Transforming missing articles into {{ill|Nama ID|en|Target EN}} (or plain link).
    - Translating and verifying categories, with comment fallback for non-existent ones.
    - SQLite caching for speed and zero redundant network overhead.
    """

    def __init__(
        self,
        cache_db_path: str = ".cache/wiki_links_cache.db",
        use_ill_templates: bool = True,
        comment_uncreated_categories: bool = True,
        user_agent: Optional[str] = None,
        allow_network: bool = True,
        gemini_client: Optional[Any] = None,
    ):
        self.cache_db_path = Path(cache_db_path)
        self.use_ill_templates = use_ill_templates
        self.comment_uncreated_categories = comment_uncreated_categories
        self.allow_network = allow_network
        self.gemini_client = gemini_client
        self.user_agent = (
            user_agent
            or "WikiTranslatorLinkMapper/1.0 (https://id.wikipedia.org; translator-tool)"
        )
        self._init_db()

    def _init_db(self) -> None:
        """Initializes SQLite schema for link and category resolution cache."""
        self.cache_db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.cache_db_path)
        try:
            with conn:
                # Cache table for pages (articles & general titles)
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS page_link_cache (
                        en_title_lower TEXT PRIMARY KEY,
                        en_title_original TEXT NOT NULL,
                        id_title TEXT,
                        exists_on_id INTEGER NOT NULL,
                        source TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        is_disambiguation INTEGER DEFAULT 0,
                        disambiguation_target TEXT
                    )
                    """
                )
                # Schema migration / ALTER TABLE check for existing cache databases
                cur = conn.cursor()
                cur.execute("PRAGMA table_info(page_link_cache)")
                existing_cols = {row[1] for row in cur.fetchall()}
                if "is_disambiguation" not in existing_cols:
                    conn.execute("ALTER TABLE page_link_cache ADD COLUMN is_disambiguation INTEGER DEFAULT 0")
                if "disambiguation_target" not in existing_cols:
                    conn.execute("ALTER TABLE page_link_cache ADD COLUMN disambiguation_target TEXT")

                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_page_link_en ON page_link_cache(en_title_lower)"
                )
                # Cache table for categories
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS category_cache (
                        en_cat_lower TEXT PRIMARY KEY,
                        en_cat_original TEXT NOT NULL,
                        id_cat TEXT,
                        exists_on_id INTEGER NOT NULL,
                        source TEXT NOT NULL,
                        created_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_cat_en ON category_cache(en_cat_lower)"
                )
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # SQLite Cache Operations
    # -------------------------------------------------------------------------

    def get_cached_page_link(self, en_title: str) -> Optional[LinkResolution]:
        """Retrieves cached link resolution if available."""
        key = en_title.strip().lower()
        conn = sqlite3.connect(self.cache_db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT en_title_original, id_title, exists_on_id, source, is_disambiguation, disambiguation_target FROM page_link_cache WHERE en_title_lower = ?",
                (key,),
            )
            row = cur.fetchone()
            if row:
                return LinkResolution(
                    original_target=row[0],
                    target_id=row[1],
                    exists_on_id=bool(row[2]),
                    source=f"cache_{row[3]}",
                    is_disambiguation=bool(row[4]) if row[4] is not None else False,
                    disambiguation_target=row[5],
                )
            return None
        finally:
            conn.close()

    def cache_page_link(
        self,
        en_title: str,
        id_title: Optional[str],
        exists_on_id: bool,
        source: str,
        is_disambiguation: bool = False,
        disambiguation_target: Optional[str] = None,
    ) -> None:
        """Saves page link resolution to SQLite cache."""
        key = en_title.strip().lower()
        conn = sqlite3.connect(self.cache_db_path)
        try:
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO page_link_cache (
                        en_title_lower, en_title_original, id_title, exists_on_id, source, created_at, is_disambiguation, disambiguation_target
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        key,
                        en_title.strip(),
                        id_title.strip() if id_title else None,
                        1 if exists_on_id else 0,
                        source,
                        time.time(),
                        1 if is_disambiguation else 0,
                        disambiguation_target.strip() if disambiguation_target else None,
                    ),
                )
        finally:
            conn.close()

    def update_cached_disambiguation(
        self,
        en_title: str,
        is_disambiguation: bool,
        disambiguation_target: Optional[str] = None,
    ) -> None:
        """Updates disambiguation flag and resolved target for a cached title."""
        key = en_title.strip().lower()
        conn = sqlite3.connect(self.cache_db_path)
        try:
            with conn:
                conn.execute(
                    """
                    UPDATE page_link_cache
                    SET is_disambiguation = ?, disambiguation_target = ?
                    WHERE en_title_lower = ?
                    """,
                    (
                        1 if is_disambiguation else 0,
                        disambiguation_target.strip() if disambiguation_target else None,
                        key,
                    ),
                )
        finally:
            conn.close()

    def get_cached_category(self, en_category: str) -> Optional[CategoryResolution]:
        """Retrieves cached category resolution if available."""
        key = self._normalize_cat_name(en_category).lower()
        conn = sqlite3.connect(self.cache_db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT en_cat_original, id_cat, exists_on_id, source FROM category_cache WHERE en_cat_lower = ?",
                (key,),
            )
            row = cur.fetchone()
            if row:
                return CategoryResolution(
                    original_category=row[0],
                    id_category=row[1],
                    exists_on_id=bool(row[2]),
                    source=f"cache_{row[3]}",
                )
            return None
        finally:
            conn.close()

    def cache_category(self, en_category: str, id_category: Optional[str], exists_on_id: bool, source: str) -> None:
        """Saves category resolution to SQLite cache."""
        key = self._normalize_cat_name(en_category).lower()
        conn = sqlite3.connect(self.cache_db_path)
        try:
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO category_cache (en_cat_lower, en_cat_original, id_cat, exists_on_id, source, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (key, en_category.strip(), id_category.strip() if id_category else None, 1 if exists_on_id else 0, source, time.time()),
                )
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # API Helpers (Wikipedia & Wikidata)
    # -------------------------------------------------------------------------

    def _api_get(self, endpoint: str, params: Dict[str, str]) -> Dict:
        """Generic HTTP GET wrapper for MediaWiki / Wikidata APIs."""
        query_str = urllib.parse.urlencode(params)
        url = f"{endpoint}?{query_str}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": self.user_agent},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return {}

    def check_id_wiki_pages_exist(self, titles: List[str]) -> Dict[str, bool]:
        """
        Batched existence check on id.wikipedia.org.
        Returns dict of {title: exists_bool}.
        """
        if not titles:
            return {}

        results: Dict[str, bool] = {t: False for t in titles}
        endpoint = "https://id.wikipedia.org/w/api.php"
        batch_size = 40

        for i in range(0, len(titles), batch_size):
            batch = titles[i : i + batch_size]
            params = {
                "action": "query",
                "titles": "|".join(batch),
                "formatversion": "2",
                "format": "json",
            }
            data = self._api_get(endpoint, params)
            pages = data.get("query", {}).get("pages", [])
            for p in pages:
                title = p.get("title", "")
                is_missing = p.get("missing", False)
                # If page is not missing and has pageid > 0, it exists
                exists = not is_missing and p.get("pageid", 0) > 0
                
                # Match title back to batch
                for b in batch:
                    if b.lower() == title.lower() or b.replace("_", " ").lower() == title.lower():
                        results[b] = exists

        return results
    def check_id_disambiguation(self, titles: List[str]) -> Dict[str, Tuple[bool, List[str]]]:
        """
        Batched disambiguation detection for Indonesian titles.
        Queries https://id.wikipedia.org/w/api.php with:
        action=query&titles=...&prop=pageprops|categories&ppprop=disambiguation&cllimit=max&format=json
        Checks if pageprops.disambiguation is present or if page is in
        'Kategori:Halaman disambiguasi' / 'Kategori:Semua halaman disambiguasi'.
        For any disambiguation page, fetches candidate target links via prop=links&plnamespace=0&pllimit=100.
        Returns Dict[str, Tuple[bool, List[str]]].
        """
        if not titles:
            return {}

        results: Dict[str, Tuple[bool, List[str]]] = {t: (False, []) for t in titles}
        endpoint = "https://id.wikipedia.org/w/api.php"
        batch_size = 40

        disambig_titles: List[str] = []

        disambig_cat_names = {
            "kategori:halaman disambiguasi",
            "kategori:semua halaman disambiguasi",
            "halaman disambiguasi",
            "semua halaman disambiguasi",
        }

        for i in range(0, len(titles), batch_size):
            batch = titles[i : i + batch_size]
            params = {
                "action": "query",
                "titles": "|".join(batch),
                "prop": "pageprops|categories",
                "ppprop": "disambiguation",
                "cllimit": "max",
                "format": "json",
            }
            data = self._api_get(endpoint, params)
            query = data.get("query", {})
            pages_obj = query.get("pages", {})

            # Handles pages as either dict (pageid -> obj) or list (if formatversion=2)
            pages_list = list(pages_obj.values()) if isinstance(pages_obj, dict) else pages_obj

            for page in pages_list:
                page_title = page.get("title", "")
                is_disambig = False

                # Check pageprops
                pageprops = page.get("pageprops")
                if isinstance(pageprops, dict) and "disambiguation" in pageprops:
                    is_disambig = True

                # Check categories
                if not is_disambig:
                    categories = page.get("categories", [])
                    for cat in categories:
                        cat_title = cat.get("title", "").strip().lower()
                        if cat_title in disambig_cat_names or any(cat_title.endswith(dc) for dc in ("halaman disambiguasi", "semua halaman disambiguasi")):
                            is_disambig = True
                            break

                # Match page_title back to original batch title(s)
                matched_originals = [
                    b for b in batch
                    if b.lower() == page_title.lower() or b.replace("_", " ").lower() == page_title.lower()
                ]
                if not matched_originals:
                    matched_originals = [page_title]

                for orig in matched_originals:
                    if is_disambig:
                        results[orig] = (True, [])
                        if page_title not in disambig_titles:
                            disambig_titles.append(page_title)
                    else:
                        results[orig] = (False, [])

        # For any disambiguation page, fetch candidate target links
        if disambig_titles:
            for i in range(0, len(disambig_titles), batch_size):
                batch_disambig = disambig_titles[i : i + batch_size]
                params = {
                    "action": "query",
                    "titles": "|".join(batch_disambig),
                    "prop": "links",
                    "plnamespace": "0",
                    "pllimit": "100",
                    "format": "json",
                }
                data = self._api_get(endpoint, params)
                query = data.get("query", {})
                pages_obj = query.get("pages", {})
                pages_list = list(pages_obj.values()) if isinstance(pages_obj, dict) else pages_obj

                for page in pages_list:
                    page_title = page.get("title", "")
                    raw_links = page.get("links", [])
                    candidate_links = [l.get("title", "").strip() for l in raw_links if l.get("title")]

                    # Map back to results
                    for orig, (is_dis, _) in list(results.items()):
                        if is_dis and (orig.lower() == page_title.lower() or orig.replace("_", " ").lower() == page_title.lower()):
                            results[orig] = (True, candidate_links)

        return results
    def resolve_disambiguation_context(
        self,
        title: str,
        options: List[str],
        context_sentence: str,
    ) -> Optional[str]:
        """
        Uses semantic keyword similarity between context_sentence and the option titles/qualifiers.
        If self.gemini_client is provided or available, supports LLM-assisted disambiguation resolution
        when heuristics are tied or ambiguous.
        Fallback: If no candidate clearly matches, returns original target (or None).
        """
        if not options:
            return None

        # Pre-process context words and n-grams
        ctx_clean = context_sentence.lower()
        ctx_words = set(re.findall(r"\w+", ctx_clean))

        # Known semantic domain associations for common Indonesian / disambiguation domains
        domain_associations: Dict[str, Set[str]] = {
            "planet": {"orbit", "matahari", "planet", "tata surya", "astronomi", "antariksa", "gravitasi", "bintang", "bumi", "satelit", "teleskop"},
            "astronomi": {"orbit", "matahari", "planet", "tata surya", "astronomi", "antariksa", "gravitasi", "bintang"},
            "unsur": {"raksa", "termometer", "kimia", "logam", "keracunan", "tabel periodik", "merkuri", "senyawa", "larutan", "atom", "massa"},
            "kimia": {"raksa", "termometer", "kimia", "logam", "keracunan", "senyawa", "reaksi", "larutan"},
            "mitologi": {"dewa", "mitologi", "romawi", "yunani", "pemujaan", "kuil", "agama", "legenda", "dewa-dewi", "pantheon"},
            "film": {"film", "sutradara", "pemeran", "aktor", "bioskop", "sinema", "box office", "alur", "karakter", "tayang"},
            "tokoh": {"lahir", "meninggal", "politikus", "presiden", "menteri", "tokoh", "penulis", "aktivis", "biografi"},
            "kota": {"kota", "provinsi", "wilayah", "penduduk", "ibukota", "kabupaten", "daerah"},
            "negara": {"negara", "republik", "kerajaan", "bangsa", "pemerintah", "presiden"},
            "album": {"album", "lagu", "rekaman", "musik", "penyanyi", "band", "musisi"},
            "lagu": {"lagu", "singel", "penyanyi", "musik", "lirik", "irama", "vokal"},
            "buku": {"buku", "novel", "penulis", "karya", "penerbit", "halaman", "fiksi"},
            "perusahaan": {"perusahaan", "korporasi", "bisnis", "saham", "industri", "pendiri", "kantor"},
        }

        scores: Dict[str, float] = {}
        for opt in options:
            score = 0.0
            opt_lower = opt.lower()

            # Extract qualifier if present e.g. "Merkurius (planet)" -> "planet"
            qualifier_match = re.search(r"\(([^)]+)\)", opt)
            qualifier = qualifier_match.group(1).strip().lower() if qualifier_match else ""

            # 1. Exact qualifier word match in context
            if qualifier:
                qual_tokens = set(re.findall(r"\w+", qualifier))
                for qt in qual_tokens:
                    if qt in ctx_words:
                        score += 3.0
                    if qt in ctx_clean:
                        score += 1.5

                # Check domain associations for the qualifier
                for domain_key, keywords in domain_associations.items():
                    if domain_key in qual_tokens or domain_key in qualifier:
                        matches = keywords.intersection(ctx_words)
                        score += len(matches) * 2.0
                        for kw in keywords:
                            if " " in kw and kw in ctx_clean:
                                score += 3.0

            # 2. Non-qualifier words unique to the option
            opt_tokens = set(re.findall(r"\w+", opt_lower))
            base_tokens = set(re.findall(r"\w+", title.lower()))
            diff_tokens = opt_tokens - base_tokens
            for dt in diff_tokens:
                if dt in ctx_words:
                    score += 2.0
                for domain_key, keywords in domain_associations.items():
                    if dt == domain_key:
                        matches = keywords.intersection(ctx_words)
                        score += len(matches) * 1.5

            scores[opt] = score

        # Determine best scoring option
        sorted_opts = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        best_opt, best_score = sorted_opts[0]
        second_score = sorted_opts[1][1] if len(sorted_opts) > 1 else 0.0

        # Clear winner heuristic: score >= 2.0 and score strictly exceeds second_score
        if best_score >= 2.0 and best_score > second_score:
            return best_opt

        # If heuristic is tied, ambiguous, or no candidate clearly matched (best_score == 0 or best_score == second_score)
        # try LLM-assisted disambiguation if gemini_client is available
        if self.gemini_client and options:
            try:
                resolved_by_llm = self._resolve_disambiguation_llm(title, options, context_sentence)
                if resolved_by_llm in options:
                    return resolved_by_llm
            except Exception:
                pass

        # Fallback: if best_score > 0 and no clear tie
        if best_score > 0 and best_score > second_score:
            return best_opt

        # If no candidate clearly matches, return original title or None
        return None

    def _resolve_disambiguation_llm(
        self,
        title: str,
        options: List[str],
        context_sentence: str,
    ) -> Optional[str]:
        """Queries gemini_client to resolve disambiguation given sentence context."""
        prompt = (
            f"Diberikan kata/istilah '{title}' yang merupakan halaman disambiguasi di Wikipedia bahasa Indonesia.\n"
            f"Konteks kalimat:\n\"{context_sentence}\"\n\n"
            f"Pilihan halaman spesifik yang tersedia:\n"
            + "\n".join(f"- {opt}" for opt in options)
            + "\n\nTentukan mana SATU halaman yang paling tepat sesuai konteks kalimat di atas.\n"
            "Jawab HANYA dengan judul halaman persis dari daftar pilihan di atas tanpa teks tambahan."
        )

        client = self.gemini_client
        response_text = ""
        if hasattr(client, "translate_section"):
            response_text = client.translate_section(user_prompt=prompt)
        elif hasattr(client, "generate_content"):
            res = client.generate_content(prompt)
            response_text = getattr(res, "text", str(res))
        elif callable(client):
            response_text = client(prompt)

        cleaned_resp = response_text.strip().strip('"').strip("'")
        for opt in options:
            if opt.lower() == cleaned_resp.lower():
                return opt
        # Partial match if exact failed
        for opt in options:
            if opt.lower() in cleaned_resp.lower():
                return opt
        return None

    def fetch_en_to_id_langlinks(self, en_titles: List[str]) -> Dict[str, Optional[str]]:
        """
        Batched query to en.wikipedia.org for Indonesian interlanguage links.
        Returns dict of {en_title: id_title_or_none}.
        """
        if not en_titles:
            return {}

        results: Dict[str, Optional[str]] = {t: None for t in en_titles}
        endpoint = "https://en.wikipedia.org/w/api.php"
        batch_size = 40

        for i in range(0, len(en_titles), batch_size):
            batch = en_titles[i : i + batch_size]
            params = {
                "action": "query",
                "titles": "|".join(batch),
                "prop": "langlinks",
                "lllang": "id",
                "lllimit": "max",
                "redirects": "1",
                "formatversion": "2",
                "format": "json",
            }
            data = self._api_get(endpoint, params)
            query = data.get("query", {})
            redirects = query.get("redirects", [])
            redirect_map: Dict[str, str] = {}
            for r in redirects:
                fr = r.get("from", "").strip()
                to = r.get("to", "").strip()
                if fr and to:
                    redirect_map[fr.lower()] = to

            pages = query.get("pages", [])
            page_id_map: Dict[str, Optional[str]] = {}
            for p in pages:
                title = p.get("title", "")
                langlinks = p.get("langlinks", [])
                id_title = None
                if langlinks:
                    for ll in langlinks:
                        if ll.get("lang") == "id":
                            id_title = ll.get("title")
                            break
                page_id_map[title.lower()] = id_title

            for b in batch:
                b_clean = b.replace("_", " ").strip().lower()
                target_title = redirect_map.get(b_clean, b.strip())
                id_title = page_id_map.get(target_title.lower())
                if id_title is None and b_clean in page_id_map:
                    id_title = page_id_map.get(b_clean)
                results[b] = id_title

        return results

    def fetch_wikidata_id_sitelink(self, en_title: str) -> Optional[str]:
        """
        Queries Wikidata API for enwiki sitelink and checks if it has an idwiki sitelink.
        Fallback when langlinks API doesn't return or for tricky redirects.
        """
        endpoint = "https://www.wikidata.org/w/api.php"
        params = {
            "action": "wbgetentities",
            "sites": "enwiki",
            "titles": en_title,
            "props": "sitelinks",
            "format": "json",
        }
        data = self._api_get(endpoint, params)
        entities = data.get("entities", {})
        for _, ent in entities.items():
            sitelinks = ent.get("sitelinks", {})
            if "idwiki" in sitelinks:
                return sitelinks["idwiki"].get("title")
        return None

    # -------------------------------------------------------------------------
    # Resolution Logic: Categories & Links
    # -------------------------------------------------------------------------

    def _normalize_cat_name(self, cat: str) -> str:
        """Strips namespace prefix like 'Category:' or 'Kategori:'."""
        c = cat.strip()
        for prefix in ("Category:", "category:", "Kategori:", "kategori:"):
            if c.startswith(prefix):
                return c[len(prefix):].strip()
        return c

    def translate_category_rule_based(self, en_cat_name: str) -> str:
        """Applies rule-based regex and pattern translation for common category formats."""
        res = en_cat_name
        for pattern, replacement in COMMON_CATEGORY_REPLACEMENTS:
            res = pattern.sub(replacement, res)
        return res.strip()

    def resolve_category(self, raw_category: str) -> CategoryResolution:
        """
        Resolves an English or Indonesian category markup/title to an official id.wikipedia.org category.
        1. Checks local cache.
        2. Queries en.wikipedia.org langlinks for `Category:<English Name>`.
        3. If no langlink, translates heuristically (e.g. `2024 films` -> `Film tahun 2024`) and checks if `Kategori:<Name>` exists on id.wikipedia.org.
        4. Checks Wikidata sitelink if needed.
        """
        cat_name = self._normalize_cat_name(raw_category)
        if not cat_name:
            return CategoryResolution(original_category=raw_category, id_category=None, exists_on_id=False)

        # 1. Check cache
        cached = self.get_cached_category(cat_name)
        if cached:
            return cached

        if not self.allow_network:
            # Offline / mock-friendly heuristic
            rule_id = self.translate_category_rule_based(cat_name)
            res = CategoryResolution(
                original_category=cat_name,
                id_category=rule_id,
                exists_on_id=False,
                source="offline_heuristic",
            )
            self.cache_category(cat_name, rule_id, False, "offline_heuristic")
            return res

        # 2. Try langlink from en.wikipedia.org for "Category:<cat_name>"
        en_cat_title = f"Category:{cat_name}"
        langlinks = self.fetch_en_to_id_langlinks([en_cat_title])
        id_cat_title = langlinks.get(en_cat_title)

        if id_cat_title:
            id_name = self._normalize_cat_name(id_cat_title)
            # Verify existence on id.wikipedia
            exists_map = self.check_id_wiki_pages_exist([f"Kategori:{id_name}"])
            exists = exists_map.get(f"Kategori:{id_name}", True)
            res = CategoryResolution(
                original_category=cat_name,
                id_category=id_name,
                exists_on_id=exists,
                source="en_langlink",
            )
            self.cache_category(cat_name, id_name, exists, "en_langlink")
            return res

        # 3. Rule-based translation + direct existence check on id.wikipedia
        rule_translated = self.translate_category_rule_based(cat_name)
        id_full_cat = f"Kategori:{rule_translated}"
        exists_map = self.check_id_wiki_pages_exist([id_full_cat])
        if exists_map.get(id_full_cat, False):
            res = CategoryResolution(
                original_category=cat_name,
                id_category=rule_translated,
                exists_on_id=True,
                source="id_direct_rule",
            )
            self.cache_category(cat_name, rule_translated, True, "id_direct_rule")
            return res

        # 4. Check Wikidata
        wd_title = self.fetch_wikidata_id_sitelink(en_cat_title)
        if wd_title:
            wd_name = self._normalize_cat_name(wd_title)
            exists_map = self.check_id_wiki_pages_exist([f"Kategori:{wd_name}"])
            exists = exists_map.get(f"Kategori:{wd_name}", True)
            res = CategoryResolution(
                original_category=cat_name,
                id_category=wd_name,
                exists_on_id=exists,
                source="wikidata",
            )
            self.cache_category(cat_name, wd_name, exists, "wikidata")
            return res

        # 5. Fallback: Category does not exist yet on id.wikipedia
        res = CategoryResolution(
            original_category=cat_name,
            id_category=rule_translated,
            exists_on_id=False,
            source="fallback_uncreated",
        )
        self.cache_category(cat_name, rule_translated, False, "fallback_uncreated")
        return res

    def resolve_wikilink(self, target: str, display_alias: Optional[str] = None) -> LinkResolution:
        """
        Resolves a single wikilink target to its Indonesian equivalent.
        0. Checks known page mappings.
        1. Checks cache.
        2. Direct check on id.wikipedia.org.
        3. Langlinks query from en.wikipedia.org.
        4. Wikidata query.
        """
        target_clean = target.strip()
        if not target_clean:
            return LinkResolution(original_target=target, exists_on_id=False)

        # Handle section links like Target#Section
        section_part = ""
        if "#" in target_clean:
            base_target, section_part = target_clean.split("#", 1)
            section_part = "#" + section_part
        else:
            base_target = target_clean

        if not base_target:
            return LinkResolution(original_target=target, exists_on_id=False)
        # 0. Check static / known page mappings
        lower_clean = base_target.lower()
        if lower_clean in KNOWN_PAGE_MAPPINGS:
            mapped_target = KNOWN_PAGE_MAPPINGS[lower_clean]
            return LinkResolution(
                original_target=base_target,
                target_id=mapped_target,
                exists_on_id=True,
                source="known_mapping",
            )


        cached = self.get_cached_page_link(base_target)
        if cached:
            return cached

        if not self.allow_network:
            # Offline / fallback mode
            res = LinkResolution(
                original_target=base_target,
                target_id=base_target,
                exists_on_id=False,
                source="offline",
            )
            self.cache_page_link(base_target, base_target, False, "offline")
            return res

        # 2. Check if target directly exists on id.wikipedia.org
        direct_exists = self.check_id_wiki_pages_exist([base_target])
        if direct_exists.get(base_target, False):
            res = LinkResolution(
                original_target=base_target,
                target_id=base_target,
                exists_on_id=True,
                source="id_direct",
            )
            self.cache_page_link(base_target, base_target, True, "id_direct")
            return res

        # 3. Langlink query from en.wikipedia.org
        langlinks = self.fetch_en_to_id_langlinks([base_target])
        id_title = langlinks.get(base_target)
        if id_title:
            res = LinkResolution(
                original_target=base_target,
                target_id=id_title,
                exists_on_id=True,
                source="en_langlink",
            )
            self.cache_page_link(base_target, id_title, True, "en_langlink")
            return res

        # 4. Wikidata sitelink check
        wd_title = self.fetch_wikidata_id_sitelink(base_target)
        if wd_title:
            res = LinkResolution(
                original_target=base_target,
                target_id=wd_title,
                exists_on_id=True,
                source="wikidata",
            )
            self.cache_page_link(base_target, wd_title, True, "wikidata")
            return res

        # 5. Not found on id.wikipedia (Red link)
        res = LinkResolution(
            original_target=base_target,
            target_id=None,
            exists_on_id=False,
            source="not_found",
        )
        self.cache_page_link(base_target, None, False, "not_found")
        return res

    def batch_resolve_wikilinks(self, targets: List[str]) -> Dict[str, LinkResolution]:
        """
        Batched resolution for multiple targets to minimize API round trips.
        """
        resolutions: Dict[str, LinkResolution] = {}
        uncached: List[str] = []

        # 0. Check known page mappings first
        remaining_targets: List[str] = []
        for t in targets:
            base = t.split("#")[0].strip()
            if not base:
                continue
            lower_base = base.lower()
            if lower_base in KNOWN_PAGE_MAPPINGS:
                resolutions[base] = LinkResolution(
                    original_target=base,
                    target_id=KNOWN_PAGE_MAPPINGS[lower_base],
                    exists_on_id=True,
                    source="known_mapping",
                )
            else:
                remaining_targets.append(base)

        # 1. Check cache next
        for base in remaining_targets:
            cached = self.get_cached_page_link(base)
            if cached:
                resolutions[base] = cached
            else:
                uncached.append(base)

        if not uncached or not self.allow_network:
            for u in uncached:
                resolutions[u] = LinkResolution(original_target=u, target_id=u, exists_on_id=False, source="offline")
            return resolutions

        # 2. Check direct existence on id.wikipedia in batch
        id_exist_map = self.check_id_wiki_pages_exist(uncached)
        remaining: List[str] = []
        for u in uncached:
            if id_exist_map.get(u, False):
                res = LinkResolution(original_target=u, target_id=u, exists_on_id=True, source="id_direct")
                self.cache_page_link(u, u, True, "id_direct")
                resolutions[u] = res
            else:
                remaining.append(u)

        if not remaining:
            return resolutions

        # 3. Query en -> id langlinks in batch
        langlinks_map = self.fetch_en_to_id_langlinks(remaining)
        for r in remaining:
            id_title = langlinks_map.get(r)
            if id_title:
                res = LinkResolution(original_target=r, target_id=id_title, exists_on_id=True, source="en_langlink")
                self.cache_page_link(r, id_title, True, "en_langlink")
                resolutions[r] = res
            else:
                # 4. Fallback: try Wikidata sitelink
                wd_title = self.fetch_wikidata_id_sitelink(r)
                if wd_title:
                    res = LinkResolution(original_target=r, target_id=wd_title, exists_on_id=True, source="wikidata")
                    self.cache_page_link(r, wd_title, True, "wikidata")
                    resolutions[r] = res
                else:
                    # 5. Red link
                    res = LinkResolution(original_target=r, target_id=None, exists_on_id=False, source="not_found")
                    self.cache_page_link(r, None, False, "not_found")
                    resolutions[r] = res

        return resolutions

    # -------------------------------------------------------------------------
    # Wikitext Transformation & Mapping
    # -------------------------------------------------------------------------

    def map_categories(self, wikitext: str) -> str:
        """
        Finds all `[[Category:...]]` or `[[Kategori:...]]` tags, translates and verifies them.
        Formats existing categories as `[[Kategori:Nama]]`.
        Formats uncreated categories with a comment tag or flags as requested.
        """
        # Match [[Category:Name]] or [[Kategori:Name|Sortkey]]
        cat_pattern = re.compile(
            r"\[\[\s*(Category|Kategori)\s*:\s*([^\|\]]+)(?:\|([^\]]+))?\s*\]\]",
            re.IGNORECASE,
        )

        def replace_cat(match: re.Match) -> str:
            raw_ns = match.group(1)
            raw_name = match.group(2).strip()
            sortkey = match.group(3)
            sortkey_str = f"|{sortkey.strip()}" if sortkey else ""

            res = self.resolve_category(raw_name)
            final_name = res.id_category or raw_name

            if res.exists_on_id:
                return f"[[Kategori:{final_name}{sortkey_str}]]"
            else:
                # Category does not exist on id.wikipedia yet
                if self.comment_uncreated_categories:
                    # If the category resolution did not find an official id page,
                    # comment it out cleanly using [[Category:...]] (or [[Kategori:...]] if original was already Indonesian)
                    # to avoid awkward hybrid half-translated text.
                    if raw_ns.lower() == "category":
                        return f"<!-- Kategori belum ada di id.wiki: [[Category:{raw_name}{sortkey_str}]] -->"
                    else:
                        return f"<!-- Kategori belum ada di id.wiki: [[Kategori:{raw_name}{sortkey_str}]] -->"
                else:
                    return f"[[Kategori:{final_name}{sortkey_str}]]"
        return cat_pattern.sub(replace_cat, wikitext)

    def adapt_link_alias(self, alias: Optional[str], en_target: str, id_target: str) -> str:
        """
        Adapts or translates descriptive English link aliases when mapping to an Indonesian article.
        If the alias was explicitly provided in the source wikitext:
        - Checks for common descriptive English phrases (e.g. 'murder of 11 Israeli athletes' -> 'pembunuhan 11 atlet Israel').
        - If alias is an English version of the target and identical to en_target, returns id_target.
        """
        if not alias:
            if en_target.lower() in ("action thriller", "action thriller film"):
                return "cerita seru laga"
            return id_target

        # If alias literally equals en_target (e.g. [[Munich massacre|Munich massacre]]), return id_target
        if alias.strip().lower() == en_target.strip().lower():
            if en_target.lower() in ("action thriller", "action thriller film"):
                return "cerita seru laga"
            return id_target
        adapted = alias
        # Common descriptive phrase patterns in wikilink aliases
        phrase_replacements = [
            (r"\bmurder of 11 Israeli athletes\b", "pembunuhan 11 atlet Israel"),
            (r"\bmurder of\b", "pembunuhan"),
            (r"\bkillings? of\b", "pembunuhan"),
            (r"\bdeath of\b", "kematian"),
            (r"\bassassination of\b", "pembunuhan"),
            (r"\bexecution of\b", "eksekusi"),
            (r"\bmassacre of\b", "pembantaian"),
            (r"\bIsraeli athletes\b", "atlet Israel"),
            (r"\bathletes\b", "atlet"),
            (r"\bhostages\b", "sandera"),
            (r"\bterrorist attacks?\b", "serangan teroris"),
            (r"\bSummer Olympic Games\b", "Olimpiade Musim Panas"),
            (r"\bOlympic Games\b", "Olimpiade"),
            (r"\bOlympics\b", "Olimpiade"),
            (r"\bWorld Cup\b", "Piala Dunia"),
        ]
        for pat, repl in phrase_replacements:
            adapted = re.sub(pat, repl, adapted, flags=re.IGNORECASE)

        return adapted

    def map_wikilinks(self, wikitext: str, resolve_disambiguation: bool = True) -> str:
        """
        Finds internal wikilinks `[[Target]]` or `[[Target|Anchor]]` (excluding Categories and Files/Images).
        Maps to official ID article title or formats red-links with {{ill|...}} when appropriate.
        When resolve_disambiguation=True, checks if resolved ID target is a disambiguation page and
        disambiguates using sentence context.
        """
        # Exclude File, Image, Berkas, Gambar, Category, Kategori
        excluded_namespaces = (
            "category:", "kategori:", "file:", "image:", "berkas:", "gambar:",
            "template:", "templat:", "help:", "bantuan:", "wikipedia:",
        )

        link_pattern = re.compile(r"\[\[\s*([^\|\]]+?)\s*(?:\|\s*([^\]]+?)\s*)?\]\]")

        # Collect targets for batch resolution
        targets_to_resolve: List[str] = []

        for m in link_pattern.finditer(wikitext):
            target = m.group(1).strip()
            
            # Check if namespace is excluded
            target_lower = target.lower()
            if any(target_lower.startswith(prefix) for prefix in excluded_namespaces):
                continue

            targets_to_resolve.append(target)
            # Also check stripped parenthetical if present (e.g. 'Dean Thomas (Harry Potter)' -> 'Dean Thomas')
            if "(" in target and target.endswith(")"):
                bare = re.sub(r"\s*\([^)]+\)$", "", target).strip()
                if bare:
                    targets_to_resolve.append(bare)

        # Batch resolve all targets
        resolutions = self.batch_resolve_wikilinks(targets_to_resolve)

        # Batch disambiguation check for resolved id targets if enabled
        disambig_map: Dict[str, Tuple[bool, List[str]]] = {}
        if resolve_disambiguation and self.allow_network:
            id_targets_to_check: List[str] = []
            for res in resolutions.values():
                if res.exists_on_id and res.target_id:
                    # If already checked in cache (is_disambiguation is known)
                    if not res.is_disambiguation and res.source.startswith("cache_"):
                        continue
                    id_targets_to_check.append(res.target_id)

            if id_targets_to_check:
                disambig_map = self.check_id_disambiguation(list(set(id_targets_to_check)))
                for t_id, (is_dis, opts) in disambig_map.items():
                    if is_dis:
                        for res in resolutions.values():
                            if res.target_id and res.target_id.lower() == t_id.lower():
                                res.is_disambiguation = True

        def extract_context(start_idx: int, end_idx: int) -> str:
            """Extracts surrounding sentence or line for contextual resolution."""
            # Find line boundaries first
            line_start = wikitext.rfind("\n", 0, start_idx)
            line_start = 0 if line_start == -1 else line_start + 1
            line_end = wikitext.find("\n", end_idx)
            line_end = len(wikitext) if line_end == -1 else line_end
            line = wikitext[line_start:line_end].strip()

            # Extract surrounding sentence if punctuation exists
            prev_punct = max(wikitext.rfind(". ", 0, start_idx), wikitext.rfind("! ", 0, start_idx), wikitext.rfind("? ", 0, start_idx))
            sent_start = 0 if prev_punct == -1 else prev_punct + 2
            sent_start = max(sent_start, line_start)

            next_punct = -1
            for p in (". ", "! ", "? "):
                idx = wikitext.find(p, end_idx)
                if idx != -1 and (next_punct == -1 or idx < next_punct):
                    next_punct = idx
            sent_end = len(wikitext) if next_punct == -1 else next_punct + 1
            sent_end = min(sent_end, line_end)

            context = wikitext[sent_start:sent_end].strip()
            return context or line or wikitext[max(0, start_idx - 100):min(len(wikitext), end_idx + 100)]

        def replace_link(match: re.Match) -> str:
            target = match.group(1).strip()
            alias = match.group(2).strip() if match.group(2) else None
            target_lower = target.lower()

            if any(target_lower.startswith(prefix) for prefix in excluded_namespaces):
                return match.group(0)

            # Split section anchor if present
            section_anchor = ""
            base_target = target
            if "#" in target:
                base_target, section = target.split("#", 1)
                section_anchor = "#" + section.strip()

            # Check for direct interlanguage / interwiki links like [[:pt:Festival...|FESTin]] or [[pt:Festival...]]
            interwiki_match = re.match(r"^:?([a-z]{2,3}):(.+)$", base_target)
            if interwiki_match and interwiki_match.group(1).lower() != "en":
                iw_lang = interwiki_match.group(1).lower()
                iw_target = interwiki_match.group(2).strip()
                id_display = self.adapt_link_alias(alias, iw_target, iw_target) if alias else iw_target
                if self.use_ill_templates:
                    return f"{{{{ill|{id_display}|{iw_lang}|{iw_target}}}}}"
                else:
                    return f"[[{id_display}]]"

            res = resolutions.get(base_target) or self.resolve_wikilink(base_target, alias)
            # 1. If base_target has an official Indonesian article (via direct exist, langlinks, wikidata)
            if res.exists_on_id and res.target_id:
                # Check if target_id is a generic list page (e.g. Dean Thomas (Harry Potter) -> Daftar karakter Harry Potter)
                # while a specific standalone article exists on id.wiki (e.g. Dean Thomas exists)
                is_generic_list = res.target_id.lower().startswith("daftar ")
                bare_target = None
                if "(" in base_target and base_target.endswith(")"):
                    bare_target = re.sub(r"\s*\([^)]+\)$", "", base_target).strip()

                if is_generic_list and bare_target and bare_target in resolutions and resolutions[bare_target].exists_on_id:
                    bare_res = resolutions[bare_target]
                    id_title = (bare_res.target_id or bare_target) + section_anchor
                    if alias is None:
                        return f"[[{id_title}]]"
                    display = self.adapt_link_alias(alias, base_target, id_title)
                    if display.lower() == id_title.lower():
                        return f"[[{id_title}]]"
                    else:
                        return f"[[{id_title}|{display}]]"

                final_id_target = res.target_id

                # Contextual Disambiguation Guard:
                # If resolved ID target is a disambiguation page and resolution is requested
                if resolve_disambiguation:
                    # Check if marked in res or disambig_map
                    is_dis = res.is_disambiguation
                    options: List[str] = []
                    if final_id_target in disambig_map:
                        is_dis_api, opts_api = disambig_map[final_id_target]
                        is_dis = is_dis or is_dis_api
                        options = opts_api
                    elif is_dis and self.allow_network:
                        dis_res = self.check_id_disambiguation([final_id_target])
                        if final_id_target in dis_res:
                            is_dis, options = dis_res[final_id_target]

                    if is_dis and options:
                        context_sent = extract_context(match.start(), match.end())
                        resolved_target = self.resolve_disambiguation_context(
                            title=final_id_target,
                            options=options,
                            context_sentence=context_sent,
                        )
                        if resolved_target:
                            # Update cache and res
                            res.disambiguation_target = resolved_target
                            self.update_cached_disambiguation(
                                en_title=base_target,
                                is_disambiguation=True,
                                disambiguation_target=resolved_target,
                            )
                            # Target resolved to specific option:
                            # e.g. [[Merkurius]] -> [[Merkurius (planet)|Merkurius]]
                            # [[Merkurius|bintang fajar]] -> [[Merkurius (planet)|bintang fajar]]
                            display_text = alias if alias else final_id_target
                            return f"[[{resolved_target}{section_anchor}|{display_text}]]"

                id_title = final_id_target + section_anchor
                if alias is None:
                    if base_target.lower() in ("action thriller", "action thriller film"):
                        return f"[[{id_title}|cerita seru laga]]"
                    return f"[[{id_title}]]"
                display = self.adapt_link_alias(alias, base_target, id_title)
                if display == id_title:
                    return f"[[{id_title}]]"
                else:
                    return f"[[{id_title}|{display}]]"

            # 2. Check if bare target (without parenthetical) exists directly on id.wiki
            # E.g. 'Dean Thomas (Harry Potter)' -> id.wiki has 'Dean Thomas'
            bare_target = None
            if "(" in base_target and base_target.endswith(")"):
                bare_target = re.sub(r"\s*\([^)]+\)$", "", base_target).strip()
            if bare_target and bare_target in resolutions and resolutions[bare_target].exists_on_id:
                bare_res = resolutions[bare_target]
                id_title = (bare_res.target_id or bare_target) + section_anchor
                if alias is None:
                    return f"[[{id_title}]]"
                display = self.adapt_link_alias(alias, base_target, id_title)
                if display.lower() == id_title.lower():
                    return f"[[{id_title}]]"
                else:
                    return f"[[{id_title}|{display}]]"
            # Red link (does not exist on id.wikipedia)
            # Special handling for character lists / lists of characters:
            # E.g. [[List of How to Get Away with Murder characters|Wes Gibbins]]
            # -> {{ill|Daftar karakter How to Get Away with Murder|en|List of How to Get Away with Murder characters|lt=Wes Gibbins}}
            list_char_match = re.match(r"^List of (.*) characters$", base_target, re.IGNORECASE)
            if list_char_match and alias:
                series_name = list_char_match.group(1).strip()
                id_list_title = f"Daftar karakter {series_name}"
                return f"{{{{ill|{id_list_title}|en|{base_target}|lt={alias}}}}}"

            if self.use_ill_templates:
                # Prevent creating {{ill}} targeting Indonesian words as en target (e.g. film cerita seru laga)
                if base_target.lower() in ("film cerita seru laga", "cerita seru laga", "action thriller", "action thriller film"):
                    return "[[Film laga|cerita seru laga]]"
                id_display = self.adapt_link_alias(alias, base_target, base_target) if alias else base_target
                # {{ill|Nama Indonesia|en|Target English}}
                return f"{{{{ill|{id_display}|en|{base_target}}}}}"
            else:
                if base_target.lower() in ("film cerita seru laga", "cerita seru laga", "action thriller", "action thriller film"):
                    return "[[Film laga|cerita seru laga]]"
                display = self.adapt_link_alias(alias, base_target, base_target) if alias else base_target
                return f"[[{display}]]"

        return link_pattern.sub(replace_link, wikitext)

    def process_wikitext(
        self,
        wikitext: str,
        use_ill_templates: bool = True,
        resolve_disambiguation: bool = True,
    ) -> str:
        """
        Full pipeline:
        1. Maps and validates categories.
        2. Resolves wikilinks & red-link safeguards (with contextual disambiguation when resolve_disambiguation=True).
        3. Sanitizes {{ill}} foreign targets against corrupted Indonesian disambiguators.
        """
        # Temporarily adapt use_ill_templates if different
        orig_ill = self.use_ill_templates
        self.use_ill_templates = use_ill_templates
        try:
            # Step 1: Map categories
            text = self.map_categories(wikitext)
            # Step 2: Map wikilinks
            text = self.map_wikilinks(text, resolve_disambiguation=resolve_disambiguation)
            # Step 3: Sanitize {{ill}} foreign targets
            text = sanitize_ill_foreign_targets(text)
            return text
        finally:
            self.use_ill_templates = orig_ill

# Global default instance
default_link_mapper = WikiLinkMapper()
