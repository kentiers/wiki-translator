"""Build read-only plans for adapting enwiki categories to idwiki."""

from dataclasses import asdict, dataclass, field
import re
from typing import Any, Dict, Iterable, List, Optional

from .category_reconciler import EN_API_URL, ID_API_URL, CategoryReconciler
from .http_client import MediaWikiApiClient
from .template_ecosystem import RecursiveDependencyScanner


@dataclass(frozen=True)
class CategoryDependency:
    en_title: str
    kind: str
    id_title: Optional[str]
    exists_on_id: bool
    en_doc_title: Optional[str] = None
    id_doc_title: Optional[str] = None
    doc_exists_on_en: bool = False
    doc_exists_on_id: bool = False


@dataclass(frozen=True)
class ParentCategoryMapping:
    en_title: str
    id_title: Optional[str]
    exists_on_id: bool
    sort_key: str = ""


@dataclass
class CategoryCreationPlan:
    en_category: str
    id_category: str
    source_oldid: int
    source_timestamp: str
    source_wikitext: str
    target_exists: bool
    dependencies: List[CategoryDependency] = field(default_factory=list)
    parent_categories: List[ParentCategoryMapping] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)

    @property
    def attribution(self) -> str:
        return f"Diadaptasi dari [[en:{self.en_category}]], revisi {self.source_oldid}"

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["attribution"] = self.attribution
        return result


class CategoryCreationPlanner:
    """Inventory category content and dependencies without writing to a wiki."""

    def __init__(
        self,
        en_client: Optional[MediaWikiApiClient] = None,
        id_client: Optional[MediaWikiApiClient] = None,
    ) -> None:
        self.en_client = en_client or MediaWikiApiClient(api_url=EN_API_URL)
        self.id_client = id_client or MediaWikiApiClient(api_url=ID_API_URL)

    @staticmethod
    def _request(client: MediaWikiApiClient, params: Dict[str, Any]) -> Dict[str, Any]:
        payload, error = client.get(params)
        if error:
            raise RuntimeError(error)
        if payload and payload.get("error"):
            raise RuntimeError(payload["error"].get("info", "MediaWiki API error"))
        return payload or {}

    def _fetch_source(self, title: str) -> tuple[str, int, str]:
        data = self._request(
            self.en_client,
            {
                "action": "query",
                "titles": title,
                "prop": "revisions",
                "rvprop": "ids|timestamp|content",
                "rvslots": "main",
                "redirects": "1",
                "formatversion": "2",
            },
        )
        pages = data.get("query", {}).get("pages", [])
        page = pages[0] if pages else {}
        revisions = page.get("revisions", [])
        if "missing" in page or not revisions:
            raise ValueError(f"Source category does not exist: {title}")
        revision = revisions[0]
        content = revision.get("slots", {}).get("main", {}).get("content", "")
        return content, int(revision.get("revid", 0)), revision.get("timestamp", "")

    def _fetch_rendered_parents(self, title: str) -> List[str]:
        parents: List[str] = []
        continuation: Optional[str] = None
        while True:
            params: Dict[str, Any] = {
                "action": "query",
                "titles": title,
                "prop": "categories",
                "cllimit": "max",
                "clshow": "!hidden",
                "formatversion": "2",
            }
            if continuation:
                params["clcontinue"] = continuation
            data = self._request(self.en_client, params)
            pages = data.get("query", {}).get("pages", [])
            if pages:
                parents.extend(
                    item["title"]
                    for item in pages[0].get("categories", [])
                    if item.get("title") and item["title"] != "Category:Hidden categories"
                )
            continuation = data.get("continue", {}).get("clcontinue")
            if not continuation:
                return list(dict.fromkeys(parents))

    def _resolve_id_titles(self, titles: Iterable[str]) -> Dict[str, str]:
        requested = list(dict.fromkeys(title for title in titles if title))
        resolved: Dict[str, str] = {}
        for offset in range(0, len(requested), 50):
            batch = requested[offset : offset + 50]
            data = self._request(
                self.en_client,
                {
                    "action": "query",
                    "titles": "|".join(batch),
                    "prop": "langlinks",
                    "lllang": "id",
                    "lllimit": "max",
                    "redirects": "1",
                    "formatversion": "2",
                },
            )
            aliases = {title.casefold(): title for title in batch}
            for item in data.get("query", {}).get("normalized", []):
                original = aliases.get(item.get("from", "").casefold())
                if original:
                    aliases[item.get("to", "").casefold()] = original
            for item in data.get("query", {}).get("redirects", []):
                original = aliases.get(item.get("from", "").casefold())
                if original:
                    aliases[item.get("to", "").casefold()] = original
            for page in data.get("query", {}).get("pages", []):
                original = aliases.get(page.get("title", "").casefold())
                links = page.get("langlinks", [])
                if original and links and links[0].get("title"):
                    resolved[original] = links[0]["title"]
        return resolved

    def _existing_titles(self, client: MediaWikiApiClient, titles: Iterable[str]) -> set[str]:
        requested = list(dict.fromkeys(title for title in titles if title))
        existing: set[str] = set()
        for offset in range(0, len(requested), 50):
            data = self._request(
                client,
                {
                    "action": "query",
                    "titles": "|".join(requested[offset : offset + 50]),
                    "formatversion": "2",
                },
            )
            for page in data.get("query", {}).get("pages", []):
                if "missing" not in page and page.get("pageid") and page.get("title"):
                    existing.add(page["title"].casefold())
        return existing

    def build_plan(self, en_category: str, id_category: str) -> CategoryCreationPlan:
        en_category = CategoryReconciler._category_title(en_category, "en")
        id_category = CategoryReconciler._category_title(id_category, "id")
        wikitext, oldid, timestamp = self._fetch_source(en_category)

        scanner = RecursiveDependencyScanner()
        templates = [
            title
            for title in scanner.extract_templates_from_wikitext(wikitext)
            if title.startswith("Template:")
        ]
        modules = scanner.extract_invocations_from_wikitext(wikitext)
        dependency_titles = list(dict.fromkeys(templates + modules))
        parents = self._fetch_rendered_parents(en_category)
        explicit_sort_keys = {
            f"Category:{match.group(1).strip()}".casefold(): (match.group(2) or "").strip()
            for match in re.finditer(
                r"\[\[\s*Category\s*:\s*([^\]|]+)(?:\|([^\]]*))?\]\]",
                wikitext,
                flags=re.IGNORECASE,
            )
        }
        mappings = self._resolve_id_titles(dependency_titles + parents)

        mapped_titles = list(mappings.values())
        id_docs = [f"{mappings[title]}/doc" for title in templates if title in mappings]
        en_docs = [f"{title}/doc" for title in templates]
        existing_id = self._existing_titles(self.id_client, [id_category] + mapped_titles + id_docs)
        existing_en_docs = self._existing_titles(self.en_client, en_docs)

        dependencies: List[CategoryDependency] = []
        for title in dependency_titles:
            id_title = mappings.get(title)
            en_doc = f"{title}/doc" if title in templates else None
            id_doc = f"{id_title}/doc" if en_doc and id_title else None
            dependencies.append(
                CategoryDependency(
                    en_title=title,
                    kind="module" if title.startswith("Module:") else "template",
                    id_title=id_title,
                    exists_on_id=bool(id_title and id_title.casefold() in existing_id),
                    en_doc_title=en_doc,
                    id_doc_title=id_doc,
                    doc_exists_on_en=bool(en_doc and en_doc.casefold() in existing_en_docs),
                    doc_exists_on_id=bool(id_doc and id_doc.casefold() in existing_id),
                )
            )

        parent_mappings = [
            ParentCategoryMapping(
                en_title=title,
                id_title=mappings.get(title),
                exists_on_id=bool(mappings.get(title) and mappings[title].casefold() in existing_id),
                sort_key=explicit_sort_keys.get(title.casefold(), ""),
            )
            for title in parents
        ]
        blockers = [
            f"Unresolved dependency: {item.en_title}"
            for item in dependencies
            if not item.id_title
        ]
        blockers.extend(
            f"Unresolved parent category: {item.en_title}"
            for item in parent_mappings
            if not item.id_title
        )
        return CategoryCreationPlan(
            en_category=en_category,
            id_category=id_category,
            source_oldid=oldid,
            source_timestamp=timestamp,
            source_wikitext=wikitext,
            target_exists=id_category.casefold() in existing_id,
            dependencies=dependencies,
            parent_categories=parent_mappings,
            blockers=blockers,
        )


default_category_creation_planner = CategoryCreationPlanner()
