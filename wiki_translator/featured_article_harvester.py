"""
Wikipedia:Artikel pilihan/Usulan (Featured Article Candidates) Peer-Review Harvester.

Harvests, extracts, and codifies real editorial peer-review critiques from
Wikipedia:Artikel pilihan/Usulan/Disetujui/ (2012 - 2026).

Captures:
1. Reviewer critique points: sentence quotes and reviewer recommendations.
2. Translationese & calque warnings: phrases flagged as "terkesan menerjemahkan".
3. Style & encyclopedic improvements approved by WBI reviewers.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, List, Optional, Set, Tuple

from .http_client import MediaWikiApiClient, default_idwiki_client


@dataclass
class APCritiquePoint:
    """A specific linguistic or translation critique point from an AP review."""
    article_title: str
    quote: str
    critique: str
    reviewer: str = ""
    year: Optional[int] = None
    category: str = "translation_style"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FeaturedArticleHarvester:
    """
    Crawls and extracts peer-review critiques from approved Featured Article
    discussions (Wikipedia:Artikel pilihan/Usulan/Disetujui/) from 2012 to 2026.
    """

    ARCHIVE_PREFIX = "Artikel_pilihan/Usulan/Disetujui/"
    BASE_PAGE = "Wikipedia:Artikel pilihan/Usulan"

    # Core high-frequency editorial critiques identified in flagship AP reviews (seed rules)
    SEED_CRITIQUE_POINTS: List[APCritiquePoint] = [
        APCritiquePoint(
            article_title="Batu Rosetta",
            quote="kedatangannya di London",
            critique="Gunakan 'diboyong ke' atau 'dipindahkan ke'; 'kedatangan' mengesankan manusia, bukan artefak/benda mati.",
            reviewer="Mimihitam",
            year=2020,
            category="calque_object_personification",
        ),
        APCritiquePoint(
            article_title="Batu Rosetta",
            quote="bagian atas yang bundar",
            critique="Gunakan 'melengkung' untuk kubah/prasasti/stela; 'bundar' mengesankan lingkaran bola penuh.",
            reviewer="Mimihitam",
            year=2020,
            category="lexical_precision",
        ),
        APCritiquePoint(
            article_title="Batu Rosetta",
            quote="berdasarkan pada pilar yang sebanding yang bertahan",
            critique="Susunan kalimat ganjil kalkir bahasa Inggris; gunakan 'berdasarkan pilar sejenis yang masih utuh'.",
            reviewer="Mimihitam",
            year=2020,
            category="translation_flow",
        ),
        APCritiquePoint(
            article_title="Batu Rosetta",
            quote="Ia telah naik takhta pada usia lima tahun semenjak kematian",
            critique="Hindari inflasi 'telah' dan 'semenjak'; susun ulang kalimat agar tidak terkesan menerjemahkan harfiah.",
            reviewer="Mimihitam",
            year=2020,
            category="translationese_avoidance",
        ),
        APCritiquePoint(
            article_title="Pulau kestabilan nuklir",
            quote="memainkan peran kunci dalam reaksi",
            critique="Gunakan 'berperan penting' atau 'berperan utama' (hindari frasa terjemahan harfiah 'memainkan peran').",
            reviewer="Hanamanteo",
            year=2020,
            category="calque_idiom",
        ),
        APCritiquePoint(
            article_title="Sapfo",
            quote="merupakan salah satu dari penyair",
            critique="Gunakan 'salah seorang penyair' untuk manusia; hindari konstruksi kaku 'merupakan salah satu dari'.",
            reviewer="Glorious Engine",
            year=2020,
            category="human_distinction",
        ),
        APCritiquePoint(
            article_title="Invasi Asia Kecil oleh Abbasiyah",
            quote="di mana pasukan Romawi Timur",
            critique="Hindari 'di mana' sebagai kata hubung penjelas klausa selain keterangan tempat fisik.",
            reviewer="HaEr48",
            year=2020,
            category="relative_clause_calque",
        ),
    ]

    def __init__(
        self,
        client: Optional[MediaWikiApiClient] = None,
        db_path: Optional[Path] = None,
    ) -> None:
        self.client = client or default_idwiki_client
        self.db_path = db_path or Path("data/featured_article_reviews.sqlite")
        self._init_db()

    def _init_db(self) -> None:
        """Initializes SQLite database schema for storing AP peer review critiques."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ap_critique_points (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_title TEXT NOT NULL,
                    quote TEXT NOT NULL,
                    critique TEXT NOT NULL,
                    reviewer TEXT,
                    year INTEGER,
                    category TEXT,
                    created_at TEXT,
                    UNIQUE(article_title, quote)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ap_article ON ap_critique_points(article_title);")
            conn.commit()
        finally:
            conn.close()

        self.seed_core_critiques()

    def seed_core_critiques(self) -> int:
        """Seeds core flagship AP editorial review findings."""
        inserted = 0
        conn = sqlite3.connect(str(self.db_path))
        try:
            for c in self.SEED_CRITIQUE_POINTS:
                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO ap_critique_points
                        (article_title, quote, critique, reviewer, year, category, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (c.article_title, c.quote, c.critique, c.reviewer, c.year, c.category, c.created_at))
                    inserted += 1
                except Exception:
                    pass
            conn.commit()
        finally:
            conn.close()
        return inserted

    # -------------------------------------------------------------------------
    # Crawling & Extraction
    # -------------------------------------------------------------------------
    def get_approved_monthly_pages(self, start_year: int = 2012, end_year: int = 2026) -> List[Tuple[int, str]]:
        """
        Fetches list of all monthly approved subpages (e.g. Wikipedia:Artikel pilihan/Usulan/Disetujui/Januari 2020).
        Filters within [start_year, end_year].
        """
        all_pages: List[str] = []
        apcontinue = None

        while True:
            params = {
                "action": "query",
                "list": "allpages",
                "apprefix": self.ARCHIVE_PREFIX,
                "apnamespace": 4,
                "aplimit": 500,
            }
            if apcontinue:
                params["apcontinue"] = apcontinue
            data, err = self.client.request(params)
            if err or not data:
                break
            for p in (data or {}).get("query", {}).get("allpages", []):
                all_pages.append(p.get("title"))
            if "continue" in data:
                apcontinue = data["continue"].get("apcontinue")
            else:
                break

        results: List[Tuple[int, str]] = []
        for p in all_pages:
            m = re.search(r"(\d{4})", p)
            if m:
                year = int(m.group(1))
                if start_year <= year <= end_year:
                    results.append((year, p))

        return sorted(results, key=lambda x: x[0])

    def parse_review_wikitext(self, article_title: str, wikitext: str, year: Optional[int] = None) -> List[APCritiquePoint]:
        """
        Extracts reviewer feedback items (* "..." ==> ...) from an AP candidate proposal wikitext.
        """
        points: List[APCritiquePoint] = []
        if not wikitext:
            return points

        # Identify reviewers from section headings: ==== Komentar dari Nama ====
        sections = re.split(r"(?m)^===\s*Komentar dari ([^=\n]+?)\s*===+$", wikitext, flags=re.IGNORECASE)
        current_reviewer = "Reviewer"

        # Pattern: * "quote" ==> critique
        critique_pat = re.compile(
            r'^\s*[*:]+\s*["\'“]([^"\'”\n]{5,150})["\'”]\s*(?:==>|->|:|–)?\s*(.*?)$',
            re.MULTILINE,
        )

        for m in critique_pat.finditer(wikitext):
            quote = m.group(1).strip()
            critique = m.group(2).strip()
            # Clean comments
            critique = re.sub(r"<!--[\s\S]*?-->", "", critique).strip()
            # Filter trivial checks
            if len(critique) > 8 and not critique.startswith("{{done}}") and not critique.startswith("{{sudah}}"):
                category = "translation_style"
                c_lower = critique.lower()
                if "terjemah" in c_lower or "kalkir" in c_lower:
                    category = "translationese_avoidance"
                elif "kbbi" in c_lower or "eyd" in c_lower or "baku" in c_lower:
                    category = "orthography_standard"
                elif "koma" in c_lower or "tanda baca" in c_lower:
                    category = "punctuation"

                points.append(
                    APCritiquePoint(
                        article_title=article_title,
                        quote=quote,
                        critique=critique[:250],
                        reviewer=current_reviewer,
                        year=year,
                        category=category,
                    )
                )

        return points

    def harvest_month_page(self, month_title: str, year: int) -> List[APCritiquePoint]:
        """
        Fetches a monthly approved page and all its transcluded proposal threads.
        """
        data, err = self.client.request({
            "action": "parse",
            "page": month_title,
            "prop": "wikitext|templates",
            "format": "json",
        })
        if err or not data:
            return []

        parse_data = data.get("parse", {})
        templates = [t.get("*", "") for t in parse_data.get("templates", [])]
        # Find candidate proposal subpages: Wikipedia:Artikel pilihan/Usulan/Judul
        proposal_titles = [
            t for t in templates if t.startswith("Wikipedia:Artikel pilihan/Usulan/") and not t.endswith("/Disetujui") and not "Arsip" in t
        ]

        if not proposal_titles:
            # Fallback: check transclusions in raw wikitext
            wikitext = parse_data.get("wikitext", {}).get("*", "")
            matches = re.findall(r"\{\{(Wikipedia:Artikel pilihan/Usulan/[^}]+)\}\}", wikitext)
            proposal_titles = list(set(matches))

        all_points: List[APCritiquePoint] = []
        for prop_title in proposal_titles[:8]:  # Limit per month to avoid timeouts
            article_name = prop_title.replace("Wikipedia:Artikel pilihan/Usulan/", "").strip()
            p_data, p_err = self.client.request({
                "action": "parse",
                "page": prop_title,
                "prop": "wikitext",
                "format": "json",
            })
            if p_data and not p_err:
                p_wiki = p_data.get("parse", {}).get("wikitext", {}).get("*", "")
                points = self.parse_review_wikitext(article_name, p_wiki, year=year)
                all_points.extend(points)
        self.save_critiques(all_points)
        return all_points

    def harvest_all_approved_reviews(
        self, start_year: int = 2012, end_year: int = 2026, batch_size: int = 35
    ) -> Dict[str, Any]:
        """
        Main harvesting pipeline:
        1. Enumerates all 162 monthly approved pages from start_year to end_year.
        2. Discovers all transcluded candidate proposal subpages.
        3. Fetches candidate wikitext in batches to maximize API throughput.
        4. Extracts all reviewer critique points (* "..." ==> ...) and saves to SQLite & JSON.
        """
        monthly_pages = self.get_approved_monthly_pages(start_year=start_year, end_year=end_year)
        all_proposal_subpages: List[str] = []
        for i in range(0, len(monthly_pages), 40):
            batch = [p for _, p in monthly_pages[i : i + 40]]
            data, _ = self.client.request({
                "action": "query",
                "titles": "|".join(batch),
                "prop": "templates",
                "tllimit": 500,
                "format": "json",
            })
            for pid, pdata in (data or {}).get("query", {}).get("pages", {}).items():
                for tpl in pdata.get("templates", []):
                    t_name = tpl.get("title", "")
                    if t_name.startswith("Wikipedia:Artikel pilihan/Usulan/") and not t_name.endswith("/Disetujui") and "Arsip" not in t_name:
                        all_proposal_subpages.append(t_name)

        all_proposal_subpages = sorted(list(set(all_proposal_subpages)))

        all_critiques: List[APCritiquePoint] = []
        for i in range(0, len(all_proposal_subpages), batch_size):
            batch = all_proposal_subpages[i : i + batch_size]
            data, err = self.client.request({
                "action": "query",
                "titles": "|".join(batch),
                "prop": "revisions",
                "rvslots": "main",
                "rvprop": "content",
                "format": "json",
            })
            if err or not data:
                continue

            pages = (data or {}).get("query", {}).get("pages", {})
            for pid, pdata in pages.items():
                title = pdata.get("title", "")
                art_name = title.replace("Wikipedia:Artikel pilihan/Usulan/", "").strip()
                revs = pdata.get("revisions", [])
                if not revs:
                    continue
                wikitext = revs[0].get("slots", {}).get("main", {}).get("*", "")
                if not wikitext:
                    continue
                years_found = re.findall(r"\b(201[2-9]|202[0-6])\b", wikitext)
                year_val = int(years_found[-1]) if years_found else None

                points = self.parse_review_wikitext(art_name, wikitext, year=year_val)
                all_critiques.extend(points)

        saved = self.save_critiques(all_critiques)
        json_path = self.export_rules_json()

        return {
            "start_year": start_year,
            "end_year": end_year,
            "total_monthly_pages": len(monthly_pages),
            "total_articles_audited": len(all_proposal_subpages),
            "total_critiques_extracted": len(all_critiques),
            "saved_to_db": saved,
            "json_path": str(json_path),
            "sqlite_path": str(self.db_path),
        }
    def save_critiques(self, points: List[APCritiquePoint]) -> int:
        """Saves critique points to SQLite."""
        if not points:
            return 0
        saved = 0
        conn = sqlite3.connect(str(self.db_path))
        try:
            for p in points:
                try:
                    conn.execute("""
                        INSERT OR REPLACE INTO ap_critique_points
                        (article_title, quote, critique, reviewer, year, category, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (p.article_title, p.quote, p.critique, p.reviewer, p.year, p.category, p.created_at))
                    saved += 1
                except Exception:
                    pass
            conn.commit()
        finally:
            conn.close()
        return saved

    def export_rules_json(self, output_path: Optional[Path] = None) -> Path:
        """Exports all peer review critique points to a structured JSON file."""
        target = output_path or Path("data/featured_article_rules.json")
        target.parent.mkdir(parents=True, exist_ok=True)

        rules: List[Dict[str, Any]] = []
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT article_title, quote, critique, reviewer, year, category FROM ap_critique_points ORDER BY year DESC")
            for row in cursor:
                rules.append(dict(row))
        finally:
            conn.close()

        target.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")
        return target


default_fa_harvester = FeaturedArticleHarvester()
