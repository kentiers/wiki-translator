"""
AWB-style Smart Page Generators for Wikipedia Translation Pipeline.

Provides automated generators to populate translation queues with missing articles:
1. CategoryPageGenerator: Generates queue from en.wikipedia categories (with optional recursion and limit).
2. WhatLinksHerePageGenerator: Generates queue from backlinks/transclusions pointing to an en.wiki target.
3. PageQueueExporter: Exports PageQueueItem lists to batch_runner-compatible text files.
"""

from dataclasses import dataclass
import json
import logging
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger(__name__)


@dataclass
class PageQueueItem:
    """Represents an article queued for translation."""
    en_title: str
    predicted_id_title: str
    status: str = "missing_on_idwiki"

    def to_dict(self) -> Dict[str, str]:
        return {
            "en_title": self.en_title,
            "predicted_id_title": self.predicted_id_title,
            "status": self.status,
        }


class BasePageGenerator:
    """Base class with shared MediaWiki API utilities for page generators."""

    def __init__(
        self,
        en_api_url: str = "https://en.wikipedia.org/w/api.php",
        id_api_url: str = "https://id.wikipedia.org/w/api.php",
        user_agent: Optional[str] = None,
        timeout: int = 15,
    ):
        self.en_api_url = en_api_url
        self.id_api_url = id_api_url
        self.user_agent = (
            user_agent
            or "WikiTranslatorPageGenerator/1.0 (https://id.wikipedia.org; translator-tool)"
        )
        self.timeout = timeout

    def _api_get(self, endpoint: str, params: Dict[str, str]) -> Dict[str, Any]:
        """Generic HTTP GET wrapper with JSON decoding."""
        query_str = urllib.parse.urlencode(params)
        url = f"{endpoint}?{query_str}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": self.user_agent},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.warning("API GET request failed for %s with params %s: %s", endpoint, params, e)
            return {}

    def predict_id_title(self, en_title: str) -> str:
        """
        Predicts the Indonesian title for an English article:
        - If title contains a disambiguation suffix like (film), maps to standard ID term or strips bare name.
        - Defaults to clean title.
        """
        clean = en_title.strip()
        m = re.match(r"^(.+?)\s*\(([^)]+)\)$", clean)
        if not m:
            return clean
        bare = m.group(1).strip()
        disambig = m.group(2).strip().lower()
        disambig_map = {
            "film": "film",
            "movie": "film",
            "director": "sutradara",
            "actor": "pemeran",
            "actress": "pemeran",
            "singer": "penyanyi",
            "musician": "musisi",
            "novel": "novel",
            "book": "buku",
            "tv series": "seri televisi",
            "television series": "seri televisi",
            "video game": "permainan video",
            "song": "lagu",
            "album": "album",
            "band": "grup musik",
            "company": "perusahaan",
            "organization": "organisasi",
            "season": "musim",
            "short film": "film pendek",
        }
        id_disambig = disambig_map.get(disambig, disambig)
        return f"{bare} ({id_disambig})"

    def filter_missing_on_idwiki(
        self,
        en_titles: List[str],
        batch_size: int = 50,
    ) -> List[PageQueueItem]:
        """
        Checks en_titles against id.wikipedia.org to determine which articles DO NOT exist yet.
        First checks en -> id interlanguage links (langlinks).
        If an article has an existing id.wiki langlink, it is considered already existing on id.wiki.
        Otherwise, predicts the Indonesian title and checks if that predicted title exists on id.wiki.
        Returns PageQueueItems only for missing articles.
        """
        if not en_titles:
            return []

        # Deduplicate while preserving order
        seen_titles: Set[str] = set()
        unique_en_titles: List[str] = []
        for t in en_titles:
            t_clean = t.strip()
            if t_clean and t_clean not in seen_titles:
                seen_titles.add(t_clean)
                unique_en_titles.append(t_clean)

        # 1. Batch query en.wikipedia.org for langlinks (lllang=id)
        # If an en.wiki article already has an id.wiki sitelink, it exists on id.wiki.
        has_id_langlink: Dict[str, Optional[str]] = {}
        for i in range(0, len(unique_en_titles), batch_size):
            batch = unique_en_titles[i : i + batch_size]
            params = {
                "action": "query",
                "titles": "|".join(batch),
                "prop": "langlinks",
                "lllang": "id",
                "lllimit": "max",
                "redirects": "1",
                "format": "json",
                "formatversion": "2",
            }
            data = self._api_get(self.en_api_url, params)
            pages = data.get("query", {}).get("pages", [])
            for p in pages:
                orig_title = p.get("title", "")
                ll = p.get("langlinks", [])
                id_target = ll[0].get("title") if ll else None
                if id_target:
                    has_id_langlink[orig_title] = id_target
                    # Also match normalized/case
                    for b in batch:
                        if b.lower() == orig_title.lower() or b.replace("_", " ").lower() == orig_title.lower():
                            has_id_langlink[b] = id_target

        candidates: List[Tuple[str, str]] = []
        for en_t in unique_en_titles:
            if en_t in has_id_langlink and has_id_langlink[en_t]:
                # Already exists on id.wiki via official langlink
                continue
            pred_id = self.predict_id_title(en_t)
            candidates.append((en_t, pred_id))

        if not candidates:
            return []

        # 2. Batch check predicted ID titles on id.wikipedia.org
        pred_titles = [pred for _, pred in candidates]
        existing_id_titles: Set[str] = set()

        for i in range(0, len(pred_titles), batch_size):
            batch = pred_titles[i : i + batch_size]
            params = {
                "action": "query",
                "titles": "|".join(batch),
                "format": "json",
                "formatversion": "2",
            }
            data = self._api_get(self.id_api_url, params)
            pages = data.get("query", {}).get("pages", [])
            for p in pages:
                p_title = p.get("title", "")
                is_missing = p.get("missing", False)
                # If pageid > 0 and missing not in p, article exists
                if not is_missing and p.get("pageid", 0) > 0:
                    existing_id_titles.add(p_title.lower())

        missing_items: List[PageQueueItem] = []
        for en_t, pred_id in candidates:
            if pred_id.lower() in existing_id_titles:
                continue
            missing_items.append(
                PageQueueItem(
                    en_title=en_t,
                    predicted_id_title=pred_id,
                    status="missing_on_idwiki",
                )
            )

        return missing_items


class CategoryPageGenerator(BasePageGenerator):
    """
    Generates queue of missing Indonesian Wikipedia articles from an English Wikipedia category.
    """

    def __init__(
        self,
        en_category: str,
        limit: int = 50,
        recursive: bool = False,
        en_api_url: str = "https://en.wikipedia.org/w/api.php",
        id_api_url: str = "https://id.wikipedia.org/w/api.php",
        user_agent: Optional[str] = None,
        timeout: int = 15,
    ):
        super().__init__(
            en_api_url=en_api_url,
            id_api_url=id_api_url,
            user_agent=user_agent,
            timeout=timeout,
        )
        self.en_category = self._normalize_category_title(en_category)
        self.limit = limit
        self.recursive = recursive

    @staticmethod
    def _normalize_category_title(cat: str) -> str:
        clean = cat.strip()
        if not clean.lower().startswith("category:"):
            clean = f"Category:{clean}"
        return clean

    def fetch_category_members(
        self,
        category_title: str,
        max_results: Optional[int] = None,
    ) -> Tuple[List[str], List[str]]:
        """
        Queries en.wikipedia.org for members of category_title.
        Returns:
            (article_titles_ns0, subcategory_titles_ns14)
        """
        articles: List[str] = []
        subcategories: List[str] = []
        cmcontinue: Optional[str] = None
        target_limit = max_results or self.limit

        while True:
            params = {
                "action": "query",
                "list": "categorymembers",
                "cmtitle": category_title,
                "cmlimit": "max",
                "cmtype": "page|subcat",
                "format": "json",
                "formatversion": "2",
            }
            if cmcontinue:
                params["cmcontinue"] = cmcontinue

            data = self._api_get(self.en_api_url, params)
            query = data.get("query", {})
            members = query.get("categorymembers", [])

            for m in members:
                ns = m.get("ns")
                title = m.get("title", "")
                if ns == 0:
                    articles.append(title)
                elif ns == 14:
                    subcategories.append(title)

                if len(articles) >= target_limit:
                    break

            if len(articles) >= target_limit:
                break

            cmcontinue = data.get("continue", {}).get("cmcontinue")
            if not cmcontinue:
                break

        return articles[:target_limit], subcategories

    def generate(self) -> List[PageQueueItem]:
        """
        Executes category retrieval (with optional recursion for subcategories)
        and filters for articles missing on id.wikipedia.org up to self.limit.
        """
        collected_articles: List[str] = []
        visited_categories: Set[str] = set()
        queue_categories: List[str] = [self.en_category]

        while queue_categories and len(collected_articles) < self.limit:
            current_cat = queue_categories.pop(0)
            if current_cat in visited_categories:
                continue
            visited_categories.add(current_cat)

            remaining_slots = self.limit - len(collected_articles)
            arts, subcats = self.fetch_category_members(
                current_cat,
                max_results=remaining_slots if not self.recursive else self.limit,
            )
            for a in arts:
                if a not in collected_articles:
                    collected_articles.append(a)
                if len(collected_articles) >= self.limit:
                    break

            if self.recursive and len(collected_articles) < self.limit:
                for sc in subcats:
                    if sc not in visited_categories and sc not in queue_categories:
                        queue_categories.append(sc)

        # Batch filter against id.wikipedia.org
        return self.filter_missing_on_idwiki(collected_articles[: self.limit])


class WhatLinksHerePageGenerator(BasePageGenerator):
    """
    Generates queue of missing Indonesian Wikipedia articles that link to or transclude
    a given English Wikipedia target page.
    """

    def __init__(
        self,
        en_target_page: str,
        limit: int = 50,
        en_api_url: str = "https://en.wikipedia.org/w/api.php",
        id_api_url: str = "https://id.wikipedia.org/w/api.php",
        user_agent: Optional[str] = None,
        timeout: int = 15,
    ):
        super().__init__(
            en_api_url=en_api_url,
            id_api_url=id_api_url,
            user_agent=user_agent,
            timeout=timeout,
        )
        self.en_target_page = en_target_page.strip()
        self.limit = limit

    def fetch_inbound_articles(self) -> List[str]:
        """
        Queries en.wikipedia.org action=query&prop=linkshere|transcludedin for target page.
        Filters for namespace 0 (articles).
        """
        inbound_titles: List[str] = []
        seen: Set[str] = set()

        lhcontinue: Optional[str] = None
        ticontinue: Optional[str] = None

        # 1. Fetch linkshere & transcludedin
        while len(inbound_titles) < self.limit:
            params = {
                "action": "query",
                "titles": self.en_target_page,
                "prop": "linkshere|transcludedin",
                "lhnamespace": "0",
                "lhlimit": "max",
                "tinamespace": "0",
                "tilimit": "max",
                "format": "json",
                "formatversion": "2",
            }
            if lhcontinue:
                params["lhcontinue"] = lhcontinue
            if ticontinue:
                params["ticontinue"] = ticontinue

            data = self._api_get(self.en_api_url, params)
            pages = data.get("query", {}).get("pages", [])
            if not pages:
                break

            for p in pages:
                # Direct links
                for lh in p.get("linkshere", []):
                    if lh.get("ns") == 0:
                        t = lh.get("title", "")
                        if t and t not in seen:
                            seen.add(t)
                            inbound_titles.append(t)
                            if len(inbound_titles) >= self.limit:
                                break

                if len(inbound_titles) >= self.limit:
                    break

                # Transclusions
                for ti in p.get("transcludedin", []):
                    if ti.get("ns") == 0:
                        t = ti.get("title", "")
                        if t and t not in seen:
                            seen.add(t)
                            inbound_titles.append(t)
                            if len(inbound_titles) >= self.limit:
                                break

            cont = data.get("continue", {})
            lhcontinue = cont.get("lhcontinue")
            ticontinue = cont.get("ticontinue")

            if not lhcontinue and not ticontinue:
                break

        return inbound_titles[: self.limit]

    def generate(self) -> List[PageQueueItem]:
        """
        Queries inbound links/transclusions and filters for those missing on id.wikipedia.org.
        """
        inbound = self.fetch_inbound_articles()
        return self.filter_missing_on_idwiki(inbound)


class PageQueueExporter:
    """
    Exports a list of PageQueueItems to a text file compatible with BatchRunner.
    Format:
    - Informative header comments starting with #
    - One article per line (English title to be translated)
    """

    @staticmethod
    def export_to_file(
        items: List[PageQueueItem],
        output_path: Union[str, Path],
        source_description: str = "",
    ) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        lines: List[str] = [
            "# Wikipedia Translation Queue",
            f"# Generated: {len(items)} missing article(s)",
        ]
        if source_description:
            lines.append(f"# Source: {source_description}")
        lines.append("# Format: One English Wikipedia title per line (compatible with --batch)")
        lines.append("")

        for item in items:
            lines.append(item.en_title)

        content = "\n".join(lines) + "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        return path
