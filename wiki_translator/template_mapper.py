"""
Cross-Wiki Template Resolver & Safeguard for Indonesian Wikipedia.

Features:
1. Cross-Wiki Template Mapping:
   - Maps standard English Wikipedia maintenance & cross-reference templates to id.wikipedia.org equivalents:
     * {{Main|...}} -> {{Utama|...}}
     * {{See also|...}} -> {{Lihat pula|...}}
     * {{Citation needed}} / {{cn}} -> {{Butuh rujukan}}
     * {{Reflist}} -> {{reflist}}
     * {{Birth date and age|...}} -> {{Tanggal lahir dan umur|...}}
     * {{Death date and age|...}} -> {{Tanggal kematian dan umur|...}}
     * {{Official website|...}} -> {{Situs web resmi|...}}
     * {{Infobox ...}} mapping where standard Indonesian templates exist.
2. Missing Template Safeguard:
   - Identifies bottom templates / navboxes.
   - Verifies if 'Templat:Nama' exists on id.wikipedia.org via Action API or SQLite cache (.cache/wiki_templates_cache.db).
   - If template does NOT exist on id.wikipedia.org and is not whitelisted, wraps with:
     <!-- Templat belum tersedia di id.wiki: {{Original Template}} -->
   - Whitelists universal templates that don't need wrapping (e.g. reflist, cite *, ill, coord, etc.).
"""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from typing import Dict, List, Optional, Set, Tuple, Union
from .storage_manager import default_storage_manager
import urllib.error
import urllib.parse
import urllib.request
from .infobox_mapper import InfoboxMapper, default_infobox_mapper


# Mapping of English demonyms and countries to standardized Indonesian names
DISAMBIGUATION_DEMONYM_MAP: Dict[str, str] = {
    "american": "Amerika Serikat",
    "amerika": "Amerika Serikat",
    "amerika serikat": "Amerika Serikat",
    "the american": "Amerika Serikat",
    "british": "Britania Raya",
    "britania": "Britania Raya",
    "britania raya": "Britania Raya",
    "the british": "Britania Raya",
    "spanish": "Spanyol",
    "spanyol": "Spanyol",
    "the spanish": "Spanyol",
    "french": "Prancis",
    "prancis": "Prancis",
    "the french": "Prancis",
    "japanese": "Jepang",
    "jepang": "Jepang",
    "the japanese": "Jepang",
    "south korean": "Korea Selatan",
    "korea selatan": "Korea Selatan",
    "korean": "Korea",
    "korea": "Korea",
    "german": "Jerman",
    "jerman": "Jerman",
    "the german": "Jerman",
    "italian": "Italia",
    "italia": "Italia",
    "the italian": "Italia",
    "canadian": "Kanada",
    "kanada": "Kanada",
    "australian": "Australia",
    "australia": "Australia",
    "indonesian": "Indonesia",
    "indonesia": "Indonesia",
    "chinese": "Tiongkok",
    "tiongkok": "Tiongkok",
    "cina": "Tiongkok",
    "indian": "India",
    "india": "India",
    "russian": "Rusia",
    "rusia": "Rusia",
    "dutch": "Belanda",
    "belanda": "Belanda",
    "swedish": "Swedia",
    "swedia": "Swedia",
    "norwegian": "Norwegia",
    "norwegia": "Norwegia",
    "danish": "Denmark",
    "denmark": "Denmark",
    "thai": "Thailand",
    "thailand": "Thailand",
}

DISAMBIGUATION_MEDIA_MAP: Dict[str, str] = {
    "television series": "serial televisi",
    "tv series": "serial televisi",
    "novel": "novel",
    "video game": "permainan video",
    "album": "album",
    "film": "film",
    "movie": "film",
    "miniseries": "miniseri",
    "tv miniseries": "miniseri",
    "short story": "cerita pendek",
    "play": "sandiwara",
    "soundtrack": "jalur suara",
    "song": "lagu",
}

DISAMBIGUATION_PERSON_MAP: Dict[str, str] = {
    "director": "sutradara",
    "actor": "pemeran",
    "actress": "pemeran",
    "politician": "politikus",
    "footballer": "pesepak bola",
    "musician": "musisi",
    "writer": "penulis",
    "singer": "penyanyi",
    "author": "penulis",
    "filmmaker": "pembuat film",
    "artist": "seniman",
    "composer": "komponis",
    "producer": "produser",
}


def normalize_disambiguation_parenthetical(inner: str) -> str:
    """
    Normalizes parenthetical disambiguation qualifiers to natural Indonesian Hukum D-M:
    - Inverted film: (film 2026 Amerika) -> (film Amerika Serikat 2026)
    - English film: (2026 American film) -> (film Amerika Serikat 2026)
    - Media: (2026 television series) -> (serial televisi 2026), (1984 novel) -> (novel 1984)
    - Person: (director) -> (sutradara), (actor) -> (pemeran)
    - Country normalization: (film Amerika 2026) -> (film Amerika Serikat 2026)
    """
    s = inner.strip()
    if not s or s.isdigit():
        return inner

    # 1. Inverted film format: (film YYYY Country) -> (film Country YYYY)
    m = re.match(r"^film\s+(\d{4})\s+([A-Za-z\s]+)$", s, re.IGNORECASE)
    if m:
        year, country = m.groups()
        c_norm = DISAMBIGUATION_DEMONYM_MAP.get(country.strip().lower(), country.strip())
        return f"film {c_norm} {year}"

    # 2. English film format: (YYYY Country film) -> (film Country YYYY)
    m = re.match(r"^(\d{4})\s+([A-Za-z\s]+?)\s+(?:film|movie)$", s, re.IGNORECASE)
    if m:
        year, country = m.groups()
        c_norm = DISAMBIGUATION_DEMONYM_MAP.get(country.strip().lower(), country.strip())
        return f"film {c_norm} {year}"

    # 3. Media with year: (YYYY Media) -> (Media YYYY)
    for en_media, id_media in DISAMBIGUATION_MEDIA_MAP.items():
        m = re.match(rf"^(\d{{4}})\s+{re.escape(en_media)}$", s, re.IGNORECASE)
        if m:
            return f"{id_media} {m.group(1)}"
        m = re.match(rf"^(\d{{4}})\s+{re.escape(id_media)}$", s, re.IGNORECASE)
        if m:
            return f"{id_media} {m.group(1)}"

    # 4. Country film YYYY: (Country film YYYY) -> (film Country YYYY)
    for demonym, norm_country in DISAMBIGUATION_DEMONYM_MAP.items():
        m = re.match(rf"^{re.escape(demonym)}\s+film\s+(\d{{4}})$", s, re.IGNORECASE)
        if m:
            return f"film {norm_country} {m.group(1)}"

    # 5. Person disambiguators: (director) -> (sutradara)
    if s.lower() in DISAMBIGUATION_PERSON_MAP:
        return DISAMBIGUATION_PERSON_MAP[s.lower()]

    # 6. Normalize 'Amerika' alone as country in film disambiguator:
    # (film Amerika 2026) -> (film Amerika Serikat 2026)
    m = re.match(r"^film\s+([A-Za-z\s]+)\s+(\d{4})$", s, re.IGNORECASE)
    if m:
        c, y = m.groups()
        c_norm = DISAMBIGUATION_DEMONYM_MAP.get(c.strip().lower(), c.strip())
        return f"film {c_norm} {y}"

    return s


def normalize_tentang_param(arg: str) -> str:
    """
    Normalizes individual parameter text in {{Tentang}} / {{About}} templates:
    - 'film 2026 Amerika' -> 'film Amerika Serikat tahun 2026'
    - 'film 2026 Spanyol' -> 'film Spanyol tahun 2026'
    - 'the 2026 American film' -> 'film Amerika Serikat tahun 2026'
    - 'the American film' -> 'film Amerika Serikat'
    - 'film Amerika' -> 'film Amerika Serikat'
    """
    s = arg.strip()
    if not s:
        return arg

    # 1. Inverted pattern: 'film 2026 Amerika' -> 'film Amerika Serikat tahun 2026'
    m = re.match(r"^film\s+(\d{4})\s+([A-Za-z\s]+)$", s, re.IGNORECASE)
    if m:
        year, country = m.groups()
        c_norm = DISAMBIGUATION_DEMONYM_MAP.get(country.strip().lower(), country.strip())
        return f"film {c_norm} tahun {year}"

    # 2. 'the 2026 American film' -> 'film Amerika Serikat tahun 2026'
    m = re.match(r"^(?:the\s+)?(\d{4})\s+([A-Za-z\s]+?)\s+film$", s, re.IGNORECASE)
    if m:
        year, country = m.groups()
        c_norm = DISAMBIGUATION_DEMONYM_MAP.get(country.strip().lower(), country.strip())
        return f"film {c_norm} tahun {year}"

    # 3. 'the American film' / 'the Spanish film'
    m = re.match(r"^(?:the\s+)?([A-Za-z\s]+?)\s+film$", s, re.IGNORECASE)
    if m:
        country = m.group(1).strip()
        c_norm = DISAMBIGUATION_DEMONYM_MAP.get(country.lower(), None)
        if c_norm:
            return f"film {c_norm}"

    # 4. 'film Amerika' -> 'film Amerika Serikat'
    m = re.match(r"^film\s+amerika$", s, re.IGNORECASE)
    if m:
        return "film Amerika Serikat"

    return s


def normalize_disambiguation_titles(wikitext: str) -> str:
    """
    Detects inverted patterns in parenthetical qualifiers and hatnote templates (Hukum D-M vs Modifier-Head):
    1. Normalizes {{Tentang}} / {{About}} parameters and target titles.
    2. Flips inverted parentheticals: (film YYYY Country) -> (film Country YYYY).
    3. Normalizes 'Amerika' -> 'Amerika Serikat'.
    4. Normalizes media disambiguations: (YYYY television series) -> (serial televisi YYYY), etc.
    5. Normalizes person disambiguations: (director) -> (sutradara), (actor) -> (pemeran), etc.
    """
    if not wikitext:
        return wikitext

    # Protect HTML comments
    comments: List[Tuple[str, str]] = []
    def comment_sub(m: re.Match) -> str:
        placeholder = f"§§COMMENT_{len(comments)}§§"
        comments.append((placeholder, m.group(0)))
        return placeholder
    text = re.sub(r"<!--[\s\S]*?-->", comment_sub, wikitext)
    # Protect {{ill|...}} templates to prevent altering en language link parameter targets
    ills: List[Tuple[str, str]] = []
    def ill_sub(m: re.Match) -> str:
        placeholder = f"§§ILL_{len(ills)}§§"
        ills.append((placeholder, m.group(0)))
        return placeholder
    text = re.sub(r"\{\{ill\|[\s\S]*?\}\}", ill_sub, text, flags=re.IGNORECASE)

    # Protect magic words like DEFAULTSORT and DISPLAYTITLE from arbitrary parenthetical replacement
    magics: List[Tuple[str, str]] = []
    def magic_sub(m: re.Match) -> str:
        placeholder = f"§§MAGIC_{len(magics)}§§"
        magics.append((placeholder, m.group(0)))
        return placeholder
    text = re.sub(r"\{\{\s*(?:DEFAULTSORT|DISPLAYTITLE)[^}]*\}\}", magic_sub, text, flags=re.IGNORECASE)

    # Protect external URLs
    urls: List[Tuple[str, str]] = []
    def url_sub(m: re.Match) -> str:
        placeholder = f"§§URL_{len(urls)}§§"
        urls.append((placeholder, m.group(0)))
        return placeholder
    text = re.sub(r"https?://[^\s\]\}]+", url_sub, text)

    # 1. Normalize {{Tentang|...}} and {{About|...}}
    def replace_tentang(m: re.Match) -> str:
        tmpl_name = m.group(1).strip()
        norm_tmpl = "Tentang" if tmpl_name.lower() in ("about", "tentang") else tmpl_name
        args_str = m.group(2)
        args = args_str.split("|")

        # Step A: Normalize parentheticals and descriptors in all args
        normalized_args = []
        for a in args:
            a_norm = re.sub(r"\(([^()\n]+)\)", lambda pm: f"({normalize_disambiguation_parenthetical(pm.group(1))})", a)
            a_norm = normalize_tentang_param(a_norm)
            normalized_args.append(a_norm)

        # Step B: Pair descriptor with target to inject year if target has year
        for idx in range(len(normalized_args)):
            curr = normalized_args[idx]
            if idx + 1 < len(normalized_args):
                next_arg = normalized_args[idx + 1]
                ym = re.search(r"\(film\s+.*?\s+(\d{4})\)", next_arg)
                if ym and "tahun" not in curr:
                    yr = ym.group(1)
                    m_film = re.match(r"^film\s+([A-Za-z\s]+)$", curr.strip(), re.IGNORECASE)
                    if m_film:
                        c_norm = DISAMBIGUATION_DEMONYM_MAP.get(m_film.group(1).strip().lower(), m_film.group(1).strip())
                        normalized_args[idx] = f"film {c_norm} tahun {yr}"

        return "{{" + norm_tmpl + "|" + "|".join(normalized_args) + "}}"

    text = re.sub(r"\{\{\s*(Tentang|About)\s*\|([\s\S]*?)\}\}", replace_tentang, text, flags=re.IGNORECASE)

    # 2. Normalize parentheticals everywhere in remaining wikitext
    text = re.sub(r"\(([^()\n]+)\)", lambda m: f"({normalize_disambiguation_parenthetical(m.group(1))})", text)

    # Restore protected elements
    for ph, orig in reversed(urls):
        text = text.replace(ph, orig)
    for ph, orig in reversed(magics):
        text = text.replace(ph, orig)
    for ph, orig in reversed(ills):
        text = text.replace(ph, orig)
    for ph, orig in reversed(comments):
        text = text.replace(ph, orig)

    return text

# Known template mapping dictionary (English lowercase/capitalized -> Indonesian standardized)
TEMPLATE_NAME_MAPPINGS: Dict[str, str] = {
    # Cross-reference & Navigation
    "main": "Utama",
    "main article": "Utama",
    "see also": "Lihat pula",
    "further": "Informasi lebih lanjut",
    "further information": "Informasi lebih lanjut",
    "about": "Tentang",
    "details": "Detail",
    # Citations & References
    "citation needed": "Butuh rujukan",
    "cn": "Butuh rujukan",
    "reflist": "reflist",
    "daftar rujukan": "reflist",
    "notelist": "Catatan kaki",
    # Dates & Biography
    "birth date and age": "Tanggal lahir dan umur",
    "birth date and age2": "Tanggal lahir dan umur",
    "death date and age": "Tanggal kematian dan umur",
    "birth date": "Tanggal lahir",
    "death date": "Tanggal kematian",
    "birth year and age": "Tahun lahir dan umur",
    "death year and age": "Tahun kematian dan umur",
    # External Links & IDs
    "official website": "Situs web resmi",
    "official": "Situs web resmi",
    "imdb title": "IMDb title",
    "imdb name": "IMDb name",
    "allmusic": "AllMusic",
    "rottentomatoes": "Rotten Tomatoes",
    "rotten tomatoes": "Rotten Tomatoes",
    "rt prose": "Rotten Tomatoes prose",
    "rt": "Rotten Tomatoes",
    "rotten tomatoes prose": "Rotten Tomatoes prose",
    # Common Maintenance
    "disambiguation": "Disambiguasi",
    "disambig": "Disambiguasi",
    "stub": "Rintisan",
    "expand section": "Kembangkan bagian",
    "unreferenced": "Tanpa referensi",
    # Infoboxes
    "infobox person": "Infobox person",
    "infobox people": "Infobox person",
    "infobox film": "Infobox film",
    "infobox movie": "Infobox film",
    "infobox television": "Infobox televisi",
    "infobox tv": "Infobox televisi",
    "infobox book": "Infobox buku",
    "infobox album": "Infobox album",
    "infobox musical artist": "Infobox penyanyi dan pemusik",
    "infobox company": "Infobox perusahaan",
    "infobox settlement": "Infobox settlement",
    "infobox video game": "Infobox video game",
}

# English Wikipedia-specific metadata / maintenance templates that have no equivalent on id.wiki
# or cause broken display (e.g. red "Templat:SHORTDESC:..." or clutter).
STRIP_METADATA_TEMPLATES: Set[str] = {
    "short description",
    "short desc",
    "use dmy dates",
    "use mdy dates",
    "engvarb",
    "use american english",
    "use british english",
    "good article",
    "featured article",
    "artikel pilihan",
    "artikel bagus",
}

# MediaWiki Magic Words (cannot be queried as templates, must be preserved pristine)
MAGIC_WORDS: Set[str] = {
    "defaultsort",
    "displaytitle",
    "formatnum",
    "plural",
    "lc",
    "uc",
    "lcfirst",
    "ucfirst",
    "padleft",
    "padright",
    "urlencode",
    "anchorencode",
    "ns",
    "nse",
    "int",
    "gender",
    "tag",
    "pagesincat",
    "pagesincategory",
    "numberofarticles",
    "numberoffiles",
    "numberofedits",
    "numberofviews",
    "numberofusers",
}

# Universal template prefixes or names that exist or are handled universally on id.wikipedia.org
# These should NEVER be commented out as missing
WHITELISTED_TEMPLATES: Set[str] = {
    # References & Citations
    "reflist",
    "daftar rujukan",
    "notelist",
    "catatan kaki",
    "cite web",
    "cite news",
    "cite book",
    "cite journal",
    "cite paper",
    "cite magazine",
    "cite episode",
    "cite av media",
    "cite video",
    "cite conference",
    "cite press release",
    "citation",
    "rujukan",
    # Localization & Interwiki
    "ill",
    "interlanguage link",
    "lang",
    "transl",
    "lit",
    "literal translation",
    "terj. har.",
    "coord",
    "koordinat",
    "convert",
    "konversi",
    # Common Formatting / Icons
    "val",
    "flag",
    "bendera",
    "flagicon",
    "flagcountry",
    "small",
    "smaller",
    "nowrap",
    "clear",
    "hlist",
    "plainlist",
    "flatlist",
    "formatnum",
    "nihongo",
    "zh",
    "anchor",
    # Core structural & meta
    "utama",
    "lihat pula",
    "informasi lebih lanjut",
    "imdb title",
    "imdb name",
    "rotten tomatoes prose",
    "rotten tomatoes",
    "tentang",
    "butuh rujukan",
    "tanggal lahir dan umur",
    "tanggal kematian dan umur",
    "situs web resmi",
    "commons category",
    "kategori commons",
}


@dataclass
class TemplateResolution:
    original_name: str
    resolved_name: str
    exists_on_id: bool
    source: str  # "mapping", "api", "cache", "whitelist"


class WikiTemplateMapper:
    """
    Cross-Wiki Template Resolver & Safeguard.
    Maps EN templates to ID equivalents, checks existence on id.wikipedia.org,
    and safeguards missing templates (e.g. navboxes) by wrapping them in comments.
    """

    def __init__(
        self,
        cache_db_path: Optional[Union[str, Path]] = None,
        user_agent: Optional[str] = None,
        allow_network: bool = True,
        infobox_mapper: Optional[InfoboxMapper] = None,
    ):
        self.cache_db_path = (
            Path(cache_db_path)
            if cache_db_path is not None
            else default_storage_manager.wiki_templates_cache_db
        )
        self.allow_network = allow_network
        self.user_agent = (
            user_agent
            or "WikiTranslatorTemplateMapper/1.0 (https://id.wikipedia.org; translator-tool)"
        )
        self.infobox_mapper = infobox_mapper or default_infobox_mapper
        self._init_db()

    def _init_db(self) -> None:
        """Initializes SQLite cache schema for templates."""
        self.cache_db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.cache_db_path)
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS template_cache (
                        template_name_lower TEXT PRIMARY KEY,
                        template_name_original TEXT NOT NULL,
                        exists_on_id INTEGER NOT NULL,
                        source TEXT NOT NULL,
                        created_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tmpl_lower ON template_cache(template_name_lower)"
                )
        finally:
            conn.close()

    def get_cached_template(self, template_name: str) -> Optional[bool]:
        """Retrieves cached existence status if available."""
        key = template_name.strip().lower()
        conn = sqlite3.connect(self.cache_db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT exists_on_id FROM template_cache WHERE template_name_lower = ?",
                (key,),
            )
            row = cur.fetchone()
            if row is not None:
                return bool(row[0])
            return None
        finally:
            conn.close()

    def cache_template(self, template_name: str, exists: bool, source: str) -> None:
        """Saves template existence status to SQLite cache."""
        key = template_name.strip().lower()
        conn = sqlite3.connect(self.cache_db_path)
        try:
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO template_cache
                    (template_name_lower, template_name_original, exists_on_id, source, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (key, template_name.strip(), 1 if exists else 0, source, time.time()),
                )
        finally:
            conn.close()

    def resolve_template_name(self, en_template_name: str) -> str:
        """
        Maps English template name to Indonesian Wikipedia equivalent.
        Preserves leading/trailing spaces if any.
        """
        raw_name = en_template_name.strip()
        lower_name = raw_name.lower()

        # Check direct mapping
        if lower_name in TEMPLATE_NAME_MAPPINGS:
            mapped = TEMPLATE_NAME_MAPPINGS[lower_name]
            # If original was lowercase, maybe return mapped; standard id wiki templates are usually capitalized
            return mapped

        # Handle Infobox mapping pattern
        if lower_name.startswith("infobox "):
            sub = lower_name[8:].strip()
            # If specific sub-mapping exists
            if lower_name in TEMPLATE_NAME_MAPPINGS:
                return TEMPLATE_NAME_MAPPINGS[lower_name]
            # Otherwise return capitalized format e.g. "Infobox sub"
            return f"Infobox {sub}"

        # Default: preserve original trimmed name with first letter capitalized
        if raw_name:
            return raw_name[0].upper() + raw_name[1:]
        return raw_name

    def is_magic_word(self, template_name: str) -> bool:
        """Checks if template_name or its prefix before colon is a MediaWiki magic word."""
        clean = template_name.strip().lower()
        prefix = clean.split(":", 1)[0].strip()
        return clean in MAGIC_WORDS or prefix in MAGIC_WORDS

    def is_whitelisted(self, template_name: str) -> bool:
        """Checks if template is in universal whitelist or is a magic word."""
        clean = template_name.strip().lower()
        if self.is_magic_word(clean):
            return True
        if clean in WHITELISTED_TEMPLATES:
            return True
        for prefix in ("cite ", "infobox ", "kotak info "):
            if clean.startswith(prefix):
                return True
        return False

    def check_id_wiki_templates_exist(self, template_names: List[str]) -> Dict[str, bool]:
        """
        Queries id.wikipedia.org Action API to check if 'Templat:Name' exists.
        Uses cached data where available.
        """
        results: Dict[str, bool] = {}
        to_fetch: List[str] = []

        for name in template_names:
            cached = self.get_cached_template(name)
            if cached is not None:
                results[name] = cached
            elif self.is_whitelisted(name):
                results[name] = True
                self.cache_template(name, True, "whitelist")
            else:
                to_fetch.append(name)

        if not to_fetch or not self.allow_network:
            for name in to_fetch:
                results[name] = False
            return results

        # Query Action API in batches of 50
        api_url = "https://id.wikipedia.org/w/api.php"
        batch_size = 50
        for i in range(0, len(to_fetch), batch_size):
            batch = to_fetch[i : i + batch_size]
            titles = ["Templat:" + (n if not n.lower().startswith("templat:") else n[8:]) for n in batch]
            params = {
                "action": "query",
                "titles": "|".join(titles),
                "format": "json",
            }
            url = f"{api_url}?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    pages = data.get("query", {}).get("pages", {})
                    # Build set of existing titles (normalized)
                    existing_titles = set()
                    normalized_map = {}
                    for norm in data.get("query", {}).get("normalized", []):
                        normalized_map[norm.get("from")] = norm.get("to")

                    for page_id, page_data in pages.items():
                        if int(page_id) > 0 and "missing" not in page_data:
                            existing_titles.add(page_data.get("title", "").lower())

                    for original_name, full_title in zip(batch, titles):
                        # resolve normalization if any
                        norm_title = normalized_map.get(full_title, full_title).lower()
                        exists = norm_title in existing_titles
                        results[original_name] = exists
                        self.cache_template(original_name, exists, "id_api")
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                for original_name in batch:
                    results[original_name] = False

        return results

    def _extract_top_level_templates(self, wikitext: str) -> List[Tuple[int, int, str, str, str]]:
        """
        Parses top-level {{ ... }} templates from wikitext.
        Returns list of (start_idx, end_idx, full_template, template_name, args_part).
        Handles nested templates properly.
        """
        templates = []
        pos = 0
        length = len(wikitext)

        while pos < length:
            start = wikitext.find("{{", pos)
            if start == -1:
                break

            # Find matching }} taking nesting into account
            depth = 1
            idx = start + 2
            while idx < length and depth > 0:
                if wikitext.startswith("{{", idx):
                    depth += 1
                    idx += 2
                elif wikitext.startswith("}}", idx):
                    depth -= 1
                    idx += 2
                else:
                    idx += 1

            if depth == 0:
                full_tmpl = wikitext[start:idx]
                inner = full_tmpl[2:-2].strip()
                # Split template name and args
                pipe_pos = inner.find("|")
                if pipe_pos != -1:
                    tmpl_name = inner[:pipe_pos].strip()
                    args_part = inner[pipe_pos:]
                else:
                    tmpl_name = inner.strip()
                    args_part = ""

                templates.append((start, idx, full_tmpl, tmpl_name, args_part))
                pos = idx
            else:
                pos = start + 2

        return templates

    def map_infobox_parameters(self, wikitext: str) -> str:
        """
        Maps Infobox parameters to Indonesian equivalents and localizes units/currency.
        """
        if not wikitext:
            return wikitext
        return self.infobox_mapper.map_infobox_parameters(wikitext)

    def process_wikitext_templates(self, wikitext: str, check_existence: bool = True) -> str:
        """
        Scans wikitext for templates:
        1. Maps Infobox parameters and values to Indonesian equivalents.
        2. Translates template names to Indonesian equivalents (e.g. Main -> Utama).
        3. Checks if bottom/navbox templates exist on id.wikipedia.org.
        4. If a navbox or untranslated template does not exist, wraps it gracefully:
           <!-- Templat belum tersedia di id.wiki: {{Original Template}} -->
        """
        if not wikitext:
            return wikitext

        # First, run conservative infobox parameter mapping & unit localization
        wikitext = self.map_infobox_parameters(wikitext)
        # Mask out HTML comments so we don't process templates inside existing comments
        masked_text = wikitext
        comments = []

        def comment_sub(m):
            placeholder = f"§§COMMENT_{len(comments)}§§"
            comments.append((placeholder, m.group(0)))
            return placeholder

        masked_text = re.sub(r"<!--[\s\S]*?-->", comment_sub, masked_text)

        # Extract top-level templates
        extracted = self._extract_top_level_templates(masked_text)
        if not extracted:
            # Restore comments and return
            for ph, orig in reversed(comments):
                masked_text = masked_text.replace(ph, orig)
            return masked_text

        # 1. Strip en.wiki-specific metadata templates (e.g. {{Short description}}, {{Use dmy dates}}, etc.)
        # Replace templates from right to left to keep string indices intact
        extracted.sort(key=lambda x: x[0], reverse=True)
        reconstructed = list(masked_text)

        non_stripped_extracted = []
        for start, end, full, name, args in extracted:
            clean_name = name.strip().lower()
            if clean_name in STRIP_METADATA_TEMPLATES:
                # Cleanly remove the template including any immediate trailing newline/whitespace
                trailing_idx = end
                length = len(reconstructed)
                while trailing_idx < length and reconstructed[trailing_idx] in (' ', '\t'):
                    trailing_idx += 1
                if trailing_idx < length and reconstructed[trailing_idx] == '\n':
                    trailing_idx += 1
                reconstructed[start:trailing_idx] = []
            else:
                non_stripped_extracted.append((start, end, full, name, args))

        # If any templates were stripped, update text and re-extract to have accurate indices
        if len(non_stripped_extracted) != len(extracted):
            masked_text = "".join(reconstructed)
            extracted = self._extract_top_level_templates(masked_text)
            extracted.sort(key=lambda x: x[0], reverse=True)
            reconstructed = list(masked_text)

        # 2. Check which templates need existence checking
        templates_to_check = []
        for start, end, full, name, args in extracted:
            if self.is_magic_word(name):
                continue
            resolved_name = self.resolve_template_name(name)
            if check_existence and not self.is_whitelisted(resolved_name):
                templates_to_check.append(resolved_name)
        existence_map = {}
        if check_existence and templates_to_check:
            existence_map = self.check_id_wiki_templates_exist(templates_to_check)

        for start, end, full, name, args in extracted:
            if self.is_magic_word(name):
                # MediaWiki magic word: keep pristine, never query or comment out
                continue

            resolved_name = self.resolve_template_name(name)
            is_mapped = (resolved_name.lower() != name.strip().lower())
            
            # Check existence if required
            exists = True
            if check_existence:
                if self.is_whitelisted(resolved_name):
                    exists = True
                else:
                    exists = existence_map.get(resolved_name, False)

            if not exists and not self.is_whitelisted(resolved_name):
                # Template does NOT exist on id.wiki!
                # Wrap it in comment safeguard
                # Use resolved template name if mapped, or original
                new_inner = f"{resolved_name}{args}"
                wrapped = f"<!-- Templat belum tersedia di id.wiki: {{{{{new_inner}}}}} -->"
                reconstructed[start:end] = list(wrapped)
            else:
                # Template exists or is whitelisted
                if is_mapped:
                    new_tmpl = f"{{{{{resolved_name}{args}}}}}"
                    reconstructed[start:end] = list(new_tmpl)
                else:
                    # Keep as is
                    pass

        result = "".join(reconstructed)
        # Restore comments
        for ph, orig in reversed(comments):
            result = result.replace(ph, orig)

        # Normalize disambiguation titles and hatnote parameters (Hukum D-M vs Modifier-Head)
        result = normalize_disambiguation_titles(result)

        return result


default_template_mapper = WikiTemplateMapper()
