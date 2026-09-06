"""Plan and apply conservative enwiki-to-idwiki category membership updates."""

from dataclasses import asdict, dataclass, field
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .http_client import MediaWikiApiClient


EN_API_URL = "https://en.wikipedia.org/w/api.php"
ID_API_URL = "https://id.wikipedia.org/w/api.php"


@dataclass(frozen=True)
class CategoryCandidate:
    en_title: str
    id_title: str


@dataclass
class CategoryReconciliationPlan:
    en_category: str
    id_category: str
    category_exists: bool
    en_member_count: int
    resolved_count: int
    existing_member_count: int
    candidates: List[CategoryCandidate] = field(default_factory=list)
    unresolved_en_titles: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CategoryReconciler:
    """Reconcile category membership using official interlanguage links."""

    def __init__(
        self,
        en_client: Optional[MediaWikiApiClient] = None,
        id_client: Optional[MediaWikiApiClient] = None,
        pause_seconds: float = 1.0,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.en_client = en_client or MediaWikiApiClient(api_url=EN_API_URL)
        self.id_client = id_client or MediaWikiApiClient(api_url=ID_API_URL)
        self.pause_seconds = pause_seconds
        self.sleeper = sleeper

    @staticmethod
    def _category_title(title: str, language: str) -> str:
        clean = title.strip().replace("_", " ")
        for prefix in ("Category:", "Kategori:"):
            if clean.lower().startswith(prefix.lower()):
                clean = clean[len(prefix) :].strip()
                break
        return f"{'Category' if language == 'en' else 'Kategori'}:{clean}"

    @staticmethod
    def _request(client: MediaWikiApiClient, params: Dict[str, Any]) -> Dict[str, Any]:
        payload, error = client.get(params)
        if error or payload is None:
            raise RuntimeError(error or "MediaWiki API returned no response")
        if "error" in payload:
            raise RuntimeError(payload["error"].get("info", str(payload["error"])))
        return payload

    def _fetch_members(
        self, client: MediaWikiApiClient, category: str, include_subcategories: bool
    ) -> Tuple[List[str], List[str]]:
        articles: List[str] = []
        subcategories: List[str] = []
        continuation: Optional[str] = None
        while True:
            params: Dict[str, Any] = {
                "action": "query",
                "list": "categorymembers",
                "cmtitle": category,
                "cmtype": "page|subcat" if include_subcategories else "page",
                "cmlimit": "max",
                "formatversion": "2",
            }
            if continuation:
                params["cmcontinue"] = continuation
            data = self._request(client, params)
            for member in data.get("query", {}).get("categorymembers", []):
                if member.get("ns") == 0 and member.get("title"):
                    articles.append(member["title"])
                elif member.get("ns") == 14 and member.get("title"):
                    subcategories.append(member["title"])
            continuation = data.get("continue", {}).get("cmcontinue")
            if not continuation:
                return articles, subcategories

    def _fetch_en_tree(self, category: str, limit: int, recursive: bool, max_depth: int) -> List[str]:
        if recursive:
            raise ValueError(
                "Recursive category flattening is unsafe; reconcile each subcategory "
                "against its own idwiki category"
            )
        members, _ = self._fetch_members(self.en_client, category, include_subcategories=False)
        return list(dict.fromkeys(members))[:limit]

    def _resolve_id_titles(self, en_titles: List[str]) -> Tuple[List[CategoryCandidate], List[str]]:
        resolved: List[CategoryCandidate] = []
        unresolved: List[str] = []
        for offset in range(0, len(en_titles), 50):
            batch = en_titles[offset : offset + 50]
            data = self._request(
                self.en_client,
                {
                    "action": "query",
                    "titles": "|".join(batch),
                    "prop": "langlinks|pageprops",
                    "lllang": "id",
                    "lllimit": "max",
                    "redirects": "1",
                    "formatversion": "2",
                },
            )
            found: Set[str] = set()
            for page in data.get("query", {}).get("pages", []):
                en_title = page.get("title", "")
                if "disambiguation" in page.get("pageprops", {}):
                    found.add(en_title.casefold())
                    continue
                links = page.get("langlinks", [])
                id_title = links[0].get("title") if links else None
                if en_title and id_title:
                    resolved.append(CategoryCandidate(en_title=en_title, id_title=id_title))
                    found.add(en_title.casefold())
            unresolved.extend(title for title in batch if title.casefold() not in found)
        return resolved, unresolved

    def _category_exists(self, category: str) -> bool:
        data = self._request(
            self.id_client,
            {"action": "query", "titles": category, "formatversion": "2"},
        )
        pages = data.get("query", {}).get("pages", [])
        return bool(pages and "missing" not in pages[0] and pages[0].get("pageid"))

    def build_plan(
        self,
        en_category: str,
        id_category: str,
        limit: int = 500,
        recursive: bool = False,
        max_depth: int = 2,
    ) -> CategoryReconciliationPlan:
        en_category = self._category_title(en_category, "en")
        id_category = self._category_title(id_category, "id")
        en_members = self._fetch_en_tree(en_category, limit, recursive, max_depth)
        resolved, unresolved = self._resolve_id_titles(en_members)
        existing, _ = self._fetch_members(self.id_client, id_category, include_subcategories=False)
        existing_folded = {title.casefold() for title in existing}
        candidates = [item for item in resolved if item.id_title.casefold() not in existing_folded]
        return CategoryReconciliationPlan(
            en_category=en_category,
            id_category=id_category,
            category_exists=self._category_exists(id_category),
            en_member_count=len(en_members),
            resolved_count=len(resolved),
            existing_member_count=len(existing),
            candidates=candidates,
            unresolved_en_titles=unresolved,
        )

    def _authenticate(self, username: str, bot_password: str) -> str:
        token_data = self._request(
            self.id_client,
            {"action": "query", "meta": "tokens", "type": "login", "formatversion": "2"},
        )
        login_token = token_data.get("query", {}).get("tokens", {}).get("logintoken")
        if not login_token:
            raise RuntimeError("Login token missing")
        login_data, error = self.id_client.post(
            {
                "action": "login",
                "lgname": username,
                "lgpassword": bot_password,
                "lgtoken": login_token,
                "formatversion": "2",
            }
        )
        if error or not login_data or login_data.get("login", {}).get("result") != "Success":
            reason = error or (login_data or {}).get("login", {}).get("reason", "Login failed")
            raise RuntimeError(str(reason))
        csrf_data = self._request(
            self.id_client,
            {"action": "query", "meta": "tokens", "type": "csrf", "formatversion": "2"},
        )
        csrf_token = csrf_data.get("query", {}).get("tokens", {}).get("csrftoken")
        if not csrf_token:
            raise RuntimeError("CSRF token missing")
        return csrf_token

    def apply_plan(
        self,
        plan: CategoryReconciliationPlan,
        username: str,
        bot_password: str,
        summary: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not plan.category_exists:
            raise ValueError(f"Target category does not exist: {plan.id_category}")
        token = self._authenticate(username, bot_password)
        applied: List[str] = []
        skipped: List[str] = []
        failed: List[Dict[str, str]] = []
        edit_summary = summary or f"menambahkan [[{plan.id_category}]] berdasarkan padanan kategori enwiki"
        for candidate in plan.candidates:
            state = self._request(
                self.id_client,
                {
                    "action": "query",
                    "titles": candidate.id_title,
                    "prop": "categories|revisions",
                    "cltitle": plan.id_category,
                    "cllimit": "max",
                    "rvprop": "timestamp",
                    "curtimestamp": "1",
                    "formatversion": "2",
                },
            )
            pages = state.get("query", {}).get("pages", [])
            page = pages[0] if pages else {}
            if "missing" in page or not page.get("pageid"):
                failed.append({"title": candidate.id_title, "error": "Article no longer exists"})
                continue
            target_key = plan.id_category.casefold()
            has_target_category = any(
                str(category.get("title", "")).casefold() == target_key
                for category in page.get("categories", [])
            )
            if has_target_category:
                skipped.append(candidate.id_title)
                continue
            revisions = page.get("revisions", [])
            params: Dict[str, Any] = {
                "action": "edit",
                "title": candidate.id_title,
                "appendtext": f"\n[[{plan.id_category}]]",
                "summary": edit_summary,
                "token": token,
                "bot": "1",
                "assert": "user",
                "nocreate": "1",
                "maxlag": "5",
                "formatversion": "2",
            }
            if revisions and revisions[0].get("timestamp"):
                params["basetimestamp"] = revisions[0]["timestamp"]
            if state.get("curtimestamp"):
                params["starttimestamp"] = state["curtimestamp"]
            response, error = self.id_client.post(params)
            edit = (response or {}).get("edit", {})
            if not error and edit.get("result") == "Success":
                applied.append(candidate.id_title)
                if self.pause_seconds:
                    self.sleeper(self.pause_seconds)
            else:
                message = error or (response or {}).get("error", {}).get("info") or "Edit failed"
                failed.append({"title": candidate.id_title, "error": str(message)})
        return {"applied": applied, "skipped": skipped, "failed": failed}


default_category_reconciler = CategoryReconciler()
