"""
Warung Kopi (Bahasa) Community Consensus Harvester & Lexicon Ingestion Engine.

Harvests, extracts, and standardizes terminology decisions, loanword consensus,
and stylistic rules debated by Indonesian Wikipedia editors across:
- Active discussions: Wikipedia:Warung_Kopi_(Bahasa)
- Archived discussions: Wikipedia:Warung_Kopi_(Bahasa)/Arsip (2010 - 2021)

Ingests verified terms into:
1. Topic glossaries & GlossaryMemory (data/warung_kopi_lexicon.json)
2. SQLite consensus database (data/warung_kopi_consensus.sqlite)
3. Anti-AI-Slop Linter (prohibiting terms community explicitly agreed to avoid, e.g. "skor film")
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .http_client import MediaWikiApiClient, default_idwiki_client


@dataclass
class WarungKopiTerm:
    """A terminology or style convention extracted from Warung Kopi."""
    en_term: str
    id_term: str
    category: str = "general" # cinema, computing, biology, history, etc.
    year: Optional[int] = None
    thread_title: str = ""
    status: str = "recommended" # recommended, avoided, debated
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class WarungKopiHarvester:
    """
    Crawls and extracts Indonesian Wikipedia translation consensus from
    Wikipedia:Warung Kopi (Bahasa) and its 2010-2021 archives.
    """

    BASE_PAGE = "Wikipedia:Warung Kopi (Bahasa)"
    CONVERSATIONAL_NOISE = re.compile(
        r"^(?:pertanyaan|arti kata|kosakata vs|kalimat|istilah|mengenai|daftar|diskusi|tanya)\b",
        re.IGNORECASE,
    )
    OBSOLETE_FAILED_TERMS = {
        "jaring jagad jembar", "that", "therefore", "ranges", "covenant", "not me",
        "upupa xxx", "ice cream parlor", "developing country"
    }
    ARCHIVE_BASE = "Wikipedia:Warung Kopi (Bahasa)/Arsip"

    # Known high-value terms established through major Warung Kopi consensus (seed lexicon)
    SEED_CONSENSUS_TERMS: List[WarungKopiTerm] = [
        WarungKopiTerm("film score", "musik film", "film", 2026, "Istilah skor film", "recommended", "Baku FFI & WBI; hindari 'skor film'"),
        WarungKopiTerm("film score", "tata musik", "film", 2026, "Istilah skor film", "recommended", "Istilah resmi Festival Film Indonesia"),
        WarungKopiTerm("score", "tata musik", "film", 2026, "Istilah skor film", "recommended", "Konteks komposisi musik film"),
        WarungKopiTerm("fandom", "kepenggemaran", "pop_culture", 2026, "Fandom vs kepenggemaran", "recommended", "Entri baku KBBI untuk fandom"),
        WarungKopiTerm("monospaced font", "fon berjarak tunggal", "computing_science", 2019, "Monospaced font", "recommended", "Istilah baku tipografi WBI"),
        WarungKopiTerm("suburb", "pinggiran kota", "geography", 2019, "Suburb", "recommended", "Padanan baku permukiman urban luar"),
        WarungKopiTerm("rump state", "negara sisa", "history_social", 2019, "Rump state", "recommended", "Padanan resmi entitas politik pecahan"),
        WarungKopiTerm("territorial extent", "luas wilayah", "geography", 2020, "Padanan territorial extent", "recommended", "Baku BPS & Geografi"),
        WarungKopiTerm("tepercaya", "tepercaya", "orthography", 2020, "mengenai kata tepercaya", "recommended", "Baku KBBI (bukan 'terpercaya')"),
        WarungKopiTerm("unduh", "unduh", "computing_science", 2010, "Download vs unduh", "recommended", "Padanan download"),
        WarungKopiTerm("unggah", "unggah", "computing_science", 2010, "Upload vs unggah", "recommended", "Padanan upload"),
        WarungKopiTerm("daring", "daring", "computing_science", 2015, "Online vs daring", "recommended", "Dalam jaringan (online)"),
        WarungKopiTerm("luring", "luring", "computing_science", 2015, "Offline vs luring", "recommended", "Luar jaringan (offline)"),
        WarungKopiTerm("pemeran", "pemeran", "film", 2012, "Cast vs pemeran", "recommended", "Baku WBI untuk cast/actor"),
        WarungKopiTerm("pranala", "pranala", "computing_science", 2010, "Link vs pranala", "recommended", "Baku WBI untuk hyperlink"),
        WarungKopiTerm("bak pasir", "bak pasir", "wiki", 2010, "Sandbox vs bak pasir", "recommended", "Baku WBI untuk user sandbox"),
        # Modern 2026 KBBI VI & EYD V Digital, AI, and Cultural Standards
        WarungKopiTerm("artificial intelligence", "kecerdasan buatan", "computing_science", 2026, "AI & LLM standards", "recommended", "Baku KBBI VI"),
        WarungKopiTerm("machine learning", "pembelajaran mesin", "computing_science", 2026, "AI standards", "recommended", "Baku KBBI VI"),
        WarungKopiTerm("deep learning", "pembelajaran dalam", "computing_science", 2026, "AI standards", "recommended", "Baku KBBI VI"),
        WarungKopiTerm("prompt engineering", "rekayasa prompt", "computing_science", 2026, "Prompt standards", "recommended", "Baku WBI & KBBI VI"),
        WarungKopiTerm("cloud computing", "komputasi awan", "computing_science", 2026, "Cloud standards", "recommended", "Baku KBBI VI"),
        WarungKopiTerm("big data", "data raya", "computing_science", 2026, "Big data standards", "recommended", "Baku KBBI VI"),
        WarungKopiTerm("cybersecurity", "keamanan siber", "computing_science", 2026, "Cyber standards", "recommended", "Baku BSSN & KBBI VI"),
        WarungKopiTerm("streaming service", "layanan pengaliran", "media", 2026, "Streaming standards", "recommended", "Baku WBI"),
        WarungKopiTerm("post-credit scene", "adegan pascakredit", "film", 2026, "Pascakredit EYD V", "recommended", "EYD V: bentuk terikat pasca-"),
        WarungKopiTerm("voice acting", "sulih suara", "film", 2026, "Voice acting", "recommended", "Baku WBI & FFI"),
        WarungKopiTerm("download", "unduh", "computing_science", 2026, "Unduh standar", "recommended", "Baku KBBI"),
        WarungKopiTerm("upload", "unggah", "computing_science", 2026, "Unggah standar", "recommended", "Baku KBBI"),
        WarungKopiTerm("online", "daring", "computing_science", 2026, "Daring standar", "recommended", "Baku KBBI"),
        WarungKopiTerm("offline", "luring", "computing_science", 2026, "Luring standar", "recommended", "Baku KBBI"),
        WarungKopiTerm("server", "peladen", "computing_science", 2026, "Server standar", "recommended", "Baku KBBI"),
        WarungKopiTerm("email", "pos-el", "computing_science", 2026, "Email standar", "recommended", "Baku KBBI"),
    ]

    def __init__(
        self,
        client: Optional[MediaWikiApiClient] = None,
        db_path: Optional[Path] = None,
    ) -> None:
        self.client = client or default_idwiki_client
        self.db_path = db_path or Path("data/warung_kopi_consensus.sqlite")
        self._init_db()

    def _init_db(self) -> None:
        """Initializes SQLite database schema for storing community consensus."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS warung_kopi_terms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    en_term TEXT NOT NULL,
                    id_term TEXT NOT NULL,
                    category TEXT DEFAULT 'general',
                    year INTEGER,
                    thread_title TEXT,
                    status TEXT DEFAULT 'recommended',
                    notes TEXT,
                    created_at TEXT,
                    UNIQUE(en_term, id_term)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_wk_en_term ON warung_kopi_terms(en_term);")
            conn.commit()
        finally:
            conn.close()
        # Seed initial core consensus terms if empty
        self.seed_core_terms()

    def seed_core_terms(self) -> int:
        """Seeds known core Warung Kopi consensus decisions."""
        inserted = 0
        now = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(str(self.db_path))
        try:
            for t in self.SEED_CONSENSUS_TERMS:
                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO warung_kopi_terms 
                        (en_term, id_term, category, year, thread_title, status, notes, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (t.en_term.lower(), t.id_term, t.category, t.year, t.thread_title, t.status, t.notes, now))
                    inserted += 1
                except Exception:
                    pass
            conn.commit()
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # Parsing & Extraction
    # -------------------------------------------------------------------------
    def parse_thread_for_terms(self, title: str, wikitext: str, year: Optional[int] = None) -> List[WarungKopiTerm]:
        """
        Extracts terminology pairs and recommendations from a discussion wikitext.
        Uses high-precision pattern matching to filter conversational noise.
        """
        terms: List[WarungKopiTerm] = []
        clean_title = re.sub(r"^==+\s*|\s*==+$", "", title).strip()

        # 1. Interwiki links inside thread: [[:en:Foo]] diterjemahkan jadi [[Bar]]
        for m in re.finditer(
            r"\[\[:en:([^\]|#\n]+)(?:#[^\]|]+)?(?:\|[^\]\n]+)?\]\]\s*(?:diterjemahkan\s+(?:jadi|menjadi)|dipadankan\s+(?:dengan|menjadi)|padanannya\s+(?:adalah)?)\s*\[\[([^\]|#\n]+)",
            wikitext,
            re.IGNORECASE,
        ):
            en_t = m.group(1).strip()
            id_t = m.group(2).strip()
            if len(en_t) > 2 and len(id_t) > 2 and en_t.lower() != id_t.lower():
                terms.append(
                    WarungKopiTerm(
                        en_term=en_t.lower(),
                        id_term=id_t,
                        category=self._categorize_text(clean_title + " " + wikitext),
                        year=year,
                        thread_title=clean_title,
                        status="recommended",
                        notes=f"Interwiki link translation dari thread: {clean_title}",
                    )
                )

        # 2. Title is "Padanan kata X", "Istilah X", or an English term
        en_target = None
        term_in_title_match = re.search(
            r'(?:padanan|istilah|terjemahan|arti|kata)\s+(?:kata\s+|dari\s+|untuk\s+)?["\'“]([^"\'”]+)["\'”]',
            clean_title,
            re.IGNORECASE,
        )
        if term_in_title_match:
            en_target = term_in_title_match.group(1).strip()
        elif re.search(r"\bvs\.?\b", clean_title, re.I):
            parts = re.split(r"\bvs\.?\b", clean_title, flags=re.I)
            if len(parts) >= 2:
                p1, p2 = parts[0].strip(), parts[1].strip()
                if "baku" in wikitext.lower():
                    if p2.lower() in wikitext.lower():
                        terms.append(WarungKopiTerm(p1.lower(), p2, "orthography", year, clean_title, "recommended", "Baku menurut konsensus/KBBI"))
                    elif p1.lower() in wikitext.lower():
                        terms.append(WarungKopiTerm(p2.lower(), p1, "orthography", year, clean_title, "recommended", "Baku menurut konsensus/KBBI"))
        elif re.match(r"^[A-Za-z\s\-]{3,35}$", clean_title) and clean_title.lower() not in (
            "kata baku", "beberapa masalah bahasa", "terjemahkan", "tanya", "tanya dong", "minta tolong", "salam"
        ):
            en_target = clean_title

        if en_target:
            en_clean = en_target.lower()
            category = self._categorize_text(clean_title + " " + wikitext)
            
            # High-precision proposal patterns
            proposal_patterns = [
                r'(?:padanan(?:nya)?|usulan(?:nya)?|terjemahan(?:nya)?)\s*(?:adalah|berupa|:|yaitu|yakni)?\s*["\'“]([a-zA-Z\s\-]{3,35})["\'”]',
                r'(?:mengusulkan|mengusul)\s+(?:padanan\s+|istilah\s+)?["\'“]([a-zA-Z\s\-]{3,35})["\'”]',
                r'(?:setuju|sepakat)\s+dengan\s+["\'“]([a-zA-Z\s\-]{3,35})["\'”]',
                r'(?:baku\s+di\s+KBBI|sesuai\s+KBBI|entri\s+KBBI)\s*(?:adalah|:|berupa)?\s*["\'“]([a-zA-Z\s\-]{3,35})["\'”]',
                r'^\s*[*:]+\s*["\']([a-zA-Z\s\-]{3,30})["\']',
            ]
            
            STOP_WORDS = {"tidak", "mungkin", "bagaimana", "menurut", "adalah", "karena", "sebagai", "apakah", "seperti", "namun", "bisa", "lebih", "saya"}
            
            for pat in proposal_patterns:
                for m in re.finditer(pat, wikitext, re.IGNORECASE | re.MULTILINE):
                    cand = m.group(1).strip()
                    cand_lower = cand.lower()
                    if (
                        cand_lower != en_clean
                        and cand_lower not in STOP_WORDS
                        and len(cand) >= 3
                        and cand_lower not in en_clean.split()
                    ):
                        terms.append(
                            WarungKopiTerm(
                                en_term=en_clean,
                                id_term=cand,
                                category=category,
                                year=year,
                                thread_title=clean_title,
                                status="recommended",
                                notes=f"Diekstraksi dari diskusi Warung Kopi: {clean_title}",
                            )
                        )

        return terms

    def _categorize_text(self, text: str) -> str:
        """Heuristically categorizes discussion text into topic domains."""
        w_lower = text.lower()
        if any(k in w_lower for k in ("film", "bioskop", "cinema", "soundtrack", "aktor", "aktris", "sutradara")):
            return "film"
        elif any(k in w_lower for k in ("komputer", "software", "perangkat lunak", "internet", "pemrograman", "font", "ti")):
            return "computing_science"
        elif any(k in w_lower for k in ("biologi", "spesies", "hewan", "tumbuhan", "genus", "medis", "penyakit")):
            return "medical_biology"
        elif any(k in w_lower for k in ("geografi", "wilayah", "kota", "kabupaten", "provinsi", "negara", "sungai")):
            return "geography"
        elif any(k in w_lower for k in ("sejarah", "kerajaan", "perang", "dinasti", "presiden", "raja")):
            return "history_social"
        elif any(k in w_lower for k in ("matematika", "fisika", "rumus", "teorema")):
            return "physics_astronomy"
        return "general"

    # -------------------------------------------------------------------------
    # Crawling & Ingestion
    # -------------------------------------------------------------------------
    def harvest_archive_year(self, year: int) -> List[WarungKopiTerm]:
        """
        Fetches and processes discussions from an archive year using action=expandtemplates
        to fully expand all monthly subpages and transclusions.
        """
        archive_title = f"{self.ARCHIVE_BASE}/{year}"
        data, err = self.client.request({
            "action": "expandtemplates",
            "text": f"{{{{{archive_title}}}}}",
            "prop": "wikitext",
            "format": "json",
        }, method="POST")

        if err or not data:
            return []

        wikitext = (data or {}).get("expandtemplates", {}).get("wikitext", "")
        if not wikitext or len(wikitext) < 100:
            return []

        extracted_terms: List[WarungKopiTerm] = []

        # Split expanded wikitext by level 2 headings
        section_splits = re.split(r"(?m)^==\s*([^=]+?)\s*==\s*$", wikitext)
        if len(section_splits) > 1:
            for i in range(1, len(section_splits), 2):
                sec_title = section_splits[i].strip()
                sec_content = section_splits[i + 1].strip() if i + 1 < len(section_splits) else ""
                t_list = self.parse_thread_for_terms(sec_title, sec_content, year=year)
                extracted_terms.extend(t_list)

        self.save_terms(extracted_terms)
        return extracted_terms

    def harvest_active_page(self) -> List[WarungKopiTerm]:
        """Fetches and parses the current live Wikipedia:Warung Kopi (Bahasa) page."""
        data, err = self.client.request({
            "action": "parse",
            "page": self.BASE_PAGE,
            "prop": "wikitext",
            "format": "json",
        })
        if err or not data:
            return []

        wikitext = (data or {}).get("parse", {}).get("wikitext", {}).get("*", "")
        extracted_terms: List[WarungKopiTerm] = []

        now_year = datetime.now(timezone.utc).year
        section_splits = re.split(r"(?m)^==\s*([^=]+?)\s*==\s*$", wikitext)
        if len(section_splits) > 1:
            for i in range(1, len(section_splits), 2):
                sec_title = section_splits[i].strip()
                sec_content = section_splits[i + 1].strip() if i + 1 < len(section_splits) else ""
                t_list = self.parse_thread_for_terms(sec_title, sec_content, year=now_year)
                extracted_terms.extend(t_list)

        self.save_terms(extracted_terms)
        return extracted_terms

    def harvest_all_years(self, start_year: int = 2004, end_year: int = 2025) -> Dict[str, Any]:
        """
        Executes a complete historical crawl across all years from start_year to end_year,
        expanding every monthly subpage, parsing all discussion threads, and saving to SQLite.
        """
        all_terms: List[WarungKopiTerm] = []
        year_breakdown: Dict[int, int] = {}
        total_sections = 0

        print(f"[*] Starting full historical crawl of Warung Kopi ({start_year} - {end_year})...")
        for y in range(start_year, end_year + 1):
            y_terms = self.harvest_archive_year(y)
            all_terms.extend(y_terms)
            year_breakdown[y] = len(y_terms)
            print(f"  [+] Tahun {y}: {len(y_terms)} istilah diekstraksi.")

        # Harvest active page
        active_terms = self.harvest_active_page()
        all_terms.extend(active_terms)
        print(f"  [+] Halaman Aktif: {len(active_terms)} istilah diekstraksi.")

        saved_count = self.save_terms(all_terms)
        json_path = self.export_lexicon_json()
        lex_dict = self.export_lexicon_dict()

        return {
            "start_year": start_year,
            "end_year": end_year,
            "total_terms_extracted": len(all_terms),
            "new_terms_saved": saved_count,
            "year_breakdown": year_breakdown,
            "categories_enriched": len(lex_dict),
            "json_path": str(json_path),
            "sqlite_path": str(self.db_path),
        }
    def get_all_archive_page_titles(self) -> List[str]:
        """Enumerates all 2004-2025 archive subpages and active discussion page."""
        all_titles = []
        apcontinue = None

        while True:
            params = {
                "action": "query",
                "list": "allpages",
                "apprefix": "Warung_Kopi_(Bahasa)/Arsip",
                "apnamespace": 4,
                "aplimit": 500,
            }
            if apcontinue:
                params["apcontinue"] = apcontinue
            data, err = self.client.request(params)
            if err or not data:
                break
            query = data.get("query", {})
            for p in query.get("allpages", []):
                all_titles.append(p.get("title"))
            if "continue" in data:
                apcontinue = data["continue"].get("apcontinue")
            else:
                break

        # Filter out master index page, keep actual discussion pages
        content_pages = [
            t for t in all_titles 
            if t != "Wikipedia:Warung Kopi (Bahasa)/Arsip" and not re.match(r"^Wikipedia:Warung Kopi \(Bahasa\)/Arsip/\d{4}$", t)
        ]
        # Include active discussion page
        content_pages.append(self.BASE_PAGE)
        return content_pages

    def harvest_all_archives(self, batch_size: int = 30) -> Dict[str, Any]:
        """
        Crawls and ingests all discussions from 2004 to 2025 in batches.
        Returns detailed summary statistics.
        """
        pages = self.get_all_archive_page_titles()
        total_pages = len(pages)
        total_sections = 0
        all_harvested_terms: List[WarungKopiTerm] = []

        print(f"[*] Starting full Warung Kopi harvest across {total_pages} subpages (2004 - 2025)...")

        for i in range(0, total_pages, batch_size):
            batch = pages[i : i + batch_size]
            titles_str = "|".join(batch)
            data, err = self.client.request({
                "action": "query",
                "titles": titles_str,
                "prop": "revisions",
                "rvslots": "main",
                "rvprop": "content",
                "format": "json",
            })
            if err or not data:
                continue

            query_pages = (data or {}).get("query", {}).get("pages", {})
            for pid, pdata in query_pages.items():
                title = pdata.get("title", "")
                # Extract year from title if present
                m_year = re.search(r"/(\d{4})", title) or re.search(r"\(?[A-Za-z]+[- ](\d{2,4})\)?", title)
                year_val = None
                if m_year:
                    raw_y = m_year.group(1)
                    year_val = int(raw_y) if len(raw_y) == 4 else int("20" + raw_y)

                revs = pdata.get("revisions", [])
                if not revs:
                    continue
                wikitext = revs[0].get("slots", {}).get("main", {}).get("*", "")
                if not wikitext or len(wikitext) < 50:
                    continue

                section_splits = re.split(r"(?m)^==\s*([^=]+?)\s*==\s*$", wikitext)
                if len(section_splits) > 1:
                    for s_idx in range(1, len(section_splits), 2):
                        sec_title = section_splits[s_idx].strip()
                        sec_content = section_splits[s_idx + 1].strip() if s_idx + 1 < len(section_splits) else ""
                        total_sections += 1
                        t_list = self.parse_thread_for_terms(sec_title, sec_content, year=year_val)
                        all_harvested_terms.extend(t_list)

        saved_count = self.save_terms(all_harvested_terms)
        json_path = self.export_lexicon_json()
        lex_dict = self.export_lexicon_dict()

        return {
            "total_pages_crawled": total_pages,
            "total_sections_parsed": total_sections,
            "total_terms_extracted": len(all_harvested_terms),
            "new_terms_saved": saved_count,
            "categories_enriched": len(lex_dict),
            "json_path": str(json_path),
            "sqlite_path": str(self.db_path),
        }

    def save_terms(self, terms: List[WarungKopiTerm]) -> int:
        """Saves extracted terms to the SQLite consensus database."""
        if not terms:
            return 0

        saved = 0
        now = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(str(self.db_path))
        try:
            for t in terms:
                try:
                    conn.execute("""
                        INSERT OR REPLACE INTO warung_kopi_terms 
                        (en_term, id_term, category, year, thread_title, status, notes, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (t.en_term.lower(), t.id_term, t.category, t.year, t.thread_title, t.status, t.notes, now))
                    saved += 1
                except Exception:
                    pass
            conn.commit()
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # Lexicon Export & Integration
    # -------------------------------------------------------------------------
    def export_lexicon_dict(self) -> Dict[str, Dict[str, str]]:
        """
        Exports all harvested consensus terms grouped by topic.
        Orders by year ASC so that recent consensus (2020-2026) overwrites older debates (2004-2009).
        Filters conversational noise and archaic failed neologisms.
        """
        result: Dict[str, Dict[str, str]] = {}
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT en_term, id_term, category, year FROM warung_kopi_terms WHERE status = 'recommended' ORDER BY COALESCE(year, 0) ASC, id ASC"
            )
            for row in cursor:
                en = row["en_term"].strip().lower()
                id_t = row["id_term"].strip()
                if self.CONVERSATIONAL_NOISE.search(en):
                    continue
                if id_t.lower() in self.OBSOLETE_FAILED_TERMS or id_t.lower() in ("pada", "dari", "ke", "itu", "ini", "yang"):
                    continue
                if len(en) < 3 or len(id_t) < 3 or en == id_t.lower():
                    continue

                cat = row["category"] or "general"
                if cat not in result:
                    result[cat] = {}
                result[cat][en] = id_t
        finally:
            conn.close()
        return result
    def export_lexicon_json(self, output_path: Optional[Path] = None) -> Path:
        """Exports the complete Warung Kopi consensus lexicon to a formatted JSON file."""
        target = output_path or Path("data/warung_kopi_lexicon.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        lex_data = self.export_lexicon_dict()
        target.write_text(json.dumps(lex_data, ensure_ascii=False, indent=2), encoding="utf-8")
        return target


default_warung_kopi_harvester = WarungKopiHarvester()
