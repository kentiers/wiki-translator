"""
Category Curator adhering to id.wikipedia's WP:PEDKAT guidelines.

WP:PEDKAT discourages "kategori sebatang kara" (isolated categories),
requiring at least 3 existing related articles before creating a new category.

Features:
- Takes candidate category (e.g. Kategori:Film yang disutradarai oleh Kevin Macdonald).
- Queries id.wikipedia Action API (action=query&list=search&srsearch=...) to find existing articles.
- Evaluates is_safe_to_create: True if found articles >= 3, False if < 3.
- Suggests existing articles that should receive this category tag.
- Suggests standard parent categories on id.wikipedia (e.g. [[Kategori:Film menurut sutradara]]).
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple
import urllib.error
import urllib.parse
import urllib.request

from .film_categorizer import FilmCategoryNormalizer, default_film_categorizer


class CategoryCurator:
    """Smart Category Curator complying with id.wikipedia WP:PEDKAT and WikiProject Film consensus."""

    def __init__(
        self,
        lang: str = "id",
        min_articles_threshold: int = 3,
        profile: str = "legacy",
        user_agent: Optional[str] = None,
        api_url: Optional[str] = None,
        film_categorizer: Optional[FilmCategoryNormalizer] = None,
    ):
        self.lang = lang
        self.min_articles_threshold = min_articles_threshold
        self.profile = profile
        self.api_url = api_url or f"https://{lang}.wikipedia.org/w/api.php"
        self.film_categorizer = film_categorizer or default_film_categorizer
        self.user_agent = (
            user_agent
            or "WikiTranslatorGradeA/1.0 (https://id.wikipedia.org; category-curator)"
        )

    def _clean_category_name(self, category_name: str) -> str:
        """Strips namespace prefix 'Kategori:' or 'Category:' and whitespace."""
        clean = category_name.strip()
        clean = re.sub(r"^(Kategori|Category)\s*:\s*", "", clean, flags=re.IGNORECASE)
        return clean.strip()

    def _derive_search_query(self, category_name: str) -> str:
        """
        Derives an effective Wikipedia search query from category title.
        e.g. 'Film yang disutradarai oleh Kevin Macdonald' -> '"Kevin Macdonald"'
        """
        clean = self._clean_category_name(category_name)
        if self.profile == "generic":
            return ["[[Kategori:Kategori Wikipedia]]"]

        # Pattern: Film yang disutradarai oleh X
        m = re.search(r"disutradarai oleh\s+(.+)$", clean, flags=re.IGNORECASE)
        if m:
            director = m.group(1).strip()
            return f'"{director}"'

        # Pattern: Album karya X
        m = re.search(r"(?:karya|oleh)\s+(.+)$", clean, flags=re.IGNORECASE)
        if m:
            creator = m.group(1).strip()
            return f'"{creator}"'

        # Pattern: Tokoh dari X / Kelahiran X
        m = re.search(r"(?:dari|kelahiran|kematian)\s+(.+)$", clean, flags=re.IGNORECASE)
        if m:
            loc = m.group(1).strip()
            return f'"{loc}"'

        return f'"{clean}"'

    def search_related_articles(self, query: str, limit: int = 15) -> List[str]:
        """
        Queries id.wikipedia Action API to find main-namespace articles matching query.
        """
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srnamespace": "0",  # Main namespace (articles only)
            "srlimit": str(limit),
            "format": "json",
            "formatversion": "2",
        }
        query_str = urllib.parse.urlencode(params)
        url = f"{self.api_url}?{query_str}"

        req = urllib.request.Request(
            url,
            headers={"User-Agent": self.user_agent},
            method="GET",
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            search_results = data.get("query", {}).get("search", [])
            articles = [
                item["title"] for item in search_results if "title" in item and item["title"]
            ]
            return articles
        except Exception:
            return []

    def infer_parent_categories(self, category_name: str) -> List[str]:
        """
        Suggests standard parent categories on id.wikipedia based on naming conventions.
        """
        clean = self._clean_category_name(category_name)
        parents: List[str] = []

        # 1. Film yang disutradarai oleh <Sutradara>
        if re.search(r"^Film yang disutradarai oleh\b", clean, flags=re.IGNORECASE):
            parents.append("[[Kategori:Film menurut sutradara]]")
            director = re.sub(r"^Film yang disutradarai oleh\s+", "", clean, flags=re.IGNORECASE).strip()
            if director:
                parents.append(f"[[Kategori:{director}]]")

        # 2. Film yang diproduseri oleh <Produser>
        elif re.search(r"^Film yang diproduseri oleh\b", clean, flags=re.IGNORECASE):
            parents.append("[[Kategori:Film menurut produser]]")
            producer = re.sub(r"^Film yang diproduseri oleh\s+", "", clean, flags=re.IGNORECASE).strip()
            if producer:
                parents.append(f"[[Kategori:{producer}]]")

        # 3. Film tahun <Tahun>
        elif re.search(r"^Film tahun\s+\d+", clean, flags=re.IGNORECASE):
            parents.append("[[Kategori:Film menurut tahun]]")
            m = re.search(r"(\d+)", clean)
            if m:
                year = m.group(1)
                parents.append(f"[[Kategori:Karya tahun {year}]]")

        # 4. Film <Negara> tahun <Tahun> (Level 2 consensus combination)
        elif re.search(r"^Film\s+[A-Za-z\s\-]+?\s+tahun\s+\d{4}$", clean, flags=re.IGNORECASE):
            m_cy = re.match(r"^Film\s+([A-Za-z\s\-]+?)\s+tahun\s+(\d{4})$", clean, flags=re.IGNORECASE)
            if m_cy:
                country, year = m_cy.group(1).strip(), m_cy.group(2).strip()
                parents.append(f"[[Kategori:Film {country}]]")
                parents.append(f"[[Kategori:Film tahun {year}]]")
            else:
                parents.append("[[Kategori:Film menurut tahun]]")

        # 4.5 Film menurut negara / Film <Negara>
        elif re.search(r"^Film\s+(?:Amerika Serikat|Britania Raya|Inggris|Indonesia|Jepang|Korea Selatan|Prancis|Jerman|India|Australia|Kanada)", clean, flags=re.IGNORECASE):
            parents.append("[[Kategori:Film menurut negara]]")

        # 4.6 Film tentang <Topik> (Format topik consensus)
        elif re.search(r"^Film tentang\b", clean, flags=re.IGNORECASE):
            parents.append("[[Kategori:Film menurut topik]]")

        # 4.7 Film peran hidup / animasi / teknologi
        elif re.search(r"^Film\s+(?:peran hidup|animasi|animasi komputer|anime|3D|bisu|hitam putih)\b", clean, flags=re.IGNORECASE):
            parents.append("[[Kategori:Film menurut teknologi]]")

        # 4.8 Film genre level 1
        elif re.search(r"^Film\s+(?:laga|cerita seru|horor|komedi|drama|fiksi ilmiah|fantasi|petualangan|kriminal|misteri|perang|musikal|olahraga|pahlawan super|dokumenter|biografi|erotis|keluarga|anak-anak|remaja)\b", clean, flags=re.IGNORECASE):
            parents.append("[[Kategori:Film menurut genre]]")
        elif re.search(r"^Album (?:karya|oleh)\b", clean, flags=re.IGNORECASE):
            parents.append("[[Kategori:Album menurut artis]]")
            artist = re.sub(r"^Album (?:karya|oleh)\s+", "", clean, flags=re.IGNORECASE).strip()
            if artist:
                parents.append(f"[[Kategori:{artist}]]")

        # 6. Lagu yang ditulis oleh <Penulis>
        elif re.search(r"^Lagu yang ditulis oleh\b", clean, flags=re.IGNORECASE):
            parents.append("[[Kategori:Lagu menurut penulis lagu]]")
            writer = re.sub(r"^Lagu yang ditulis oleh\s+", "", clean, flags=re.IGNORECASE).strip()
            if writer:
                parents.append(f"[[Kategori:{writer}]]")

        # 7. Kelahiran <Tahun> / Kematian <Tahun>
        elif re.search(r"^(?:Kelahiran|Kematian)\s+\d+", clean, flags=re.IGNORECASE):
            parents.append("[[Kategori:Kelahiran menurut tahun]]" if "Kelahiran" in clean else "[[Kategori:Kematian menurut tahun]]")

        # 8. Tokoh dari <Lokasi>
        elif re.search(r"^Tokoh dari\b", clean, flags=re.IGNORECASE):
            parents.append("[[Kategori:Tokoh menurut lokasi]]")

        # Fallback default parent category
        if not parents:
            if "film" in clean.lower():
                parents.append("[[Kategori:Film]]")
            elif "album" in clean.lower() or "lagu" in clean.lower() or "musik" in clean.lower():
                parents.append("[[Kategori:Musik]]")
            elif "tokoh" in clean.lower() or "orang" in clean.lower():
                parents.append("[[Kategori:Tokoh]]")
            else:
                parents.append("[[Kategori:Kategori menurut topik]]")

        return parents

    def curate_category(
        self,
        category_name: str,
        search_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Evaluates category safety per WP:PEDKAT (minimum articles threshold).
        Returns dict with category details, safety status, found articles, and parent suggestions.
        """
        clean_name = self._clean_category_name(category_name)
        full_cat_name = f"Kategori:{clean_name}"

        query = search_query or self._derive_search_query(clean_name)
        found_articles = self.search_related_articles(query)
        article_count = len(found_articles)
        is_safe = article_count >= self.min_articles_threshold
        is_film = self.film_categorizer.is_film_category(clean_name)
        consensus_valid = True
        consensus_violation = None
        suggested_categories = []

        if is_film:
            consensus_valid, consensus_violation = self.film_categorizer.validate_film_category(clean_name)
            if not consensus_valid:
                is_safe = False
                suggested_categories = self.film_categorizer.decompose_enwiki_film_category(clean_name)
                reason = (
                    f"Tidak aman / melanggar konsensus Wikipedia:ProyekWiki Film/Kategorisasi: "
                    f"{consensus_violation} "
                    f"Rekomendasi pemecahan kategori: {', '.join(suggested_categories)}."
                )

        if is_safe and consensus_valid:
            reason = (
                f"Aman untuk dibuat (WP:PEDKAT): Ditemukan {article_count} artikel terkait "
                f"(ambang batas minimum: {self.min_articles_threshold})."
            )
        elif not is_safe and consensus_valid:
            reason = (
                f"Belum aman untuk dibuat (WP:PEDKAT / anti-kategori sebatang kara): "
                f"Hanya ditemukan {article_count} artikel terkait "
                f"(diperlukan minimal {self.min_articles_threshold} artikel)."
            )

        parents = self.infer_parent_categories(clean_name)

        return {
            "category_name": full_cat_name,
            "article_count": article_count,
            "is_safe_to_create": is_safe,
            "found_articles": found_articles,
            "parent_categories": parents,
            "reason": reason,
            "consensus_valid": consensus_valid,
            "consensus_violation": consensus_violation,
            "suggested_categories": suggested_categories,
        }


default_category_curator = CategoryCurator()
