"""Read-first synchronization of existing category page wikitext."""

from dataclasses import dataclass, asdict
import difflib
import json
from pathlib import Path
import re
from typing import Callable, Dict, List, Optional

from .approval_journal import ApprovalManifest
from .category_reconciler import EN_API_URL, ID_API_URL, CategoryReconciler
from .http_client import MediaWikiApiClient
from .translation_evidence import TranslationEvidenceResolver


@dataclass
class CategoryPageSyncResult:
    en_title: str
    id_title: str
    source_oldid: Optional[int]
    draft_wikitext: str
    existing_wikitext: str
    changed: bool
    warnings: List[str]
    output_path: Optional[str] = None
    approval_manifest_path: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


class CategoryPageSynchronizer:
    """Build a local reviewed draft; never edits an existing category directly."""

    def __init__(
        self,
        en_client: Optional[MediaWikiApiClient] = None,
        id_client: Optional[MediaWikiApiClient] = None,
        translate_plain_text: Optional[Callable[[str], str]] = None,
        evidence_resolver: Optional[TranslationEvidenceResolver] = None,
    ) -> None:
        self.en_client = en_client or MediaWikiApiClient(api_url=EN_API_URL)
        self.id_client = id_client or MediaWikiApiClient(api_url=ID_API_URL)
        self.translate_plain_text = translate_plain_text
        self.evidence_resolver = evidence_resolver or TranslationEvidenceResolver(self.en_client, self.id_client)

    @staticmethod
    def _fetch(client: MediaWikiApiClient, title: str):
        payload, error = client.get({
            "action": "query", "titles": title, "prop": "revisions",
            "rvprop": "ids|content", "rvslots": "main", "rvlimit": 1,
            "formatversion": "2",
        })
        if error or not payload:
            raise RuntimeError(error or "empty MediaWiki response")
        page = (payload.get("query", {}).get("pages") or [{}])[0]
        if page.get("missing"):
            return "", None
        revision = (page.get("revisions") or [{}])[0]
        return revision.get("slots", {}).get("main", {}).get("content", ""), revision.get("revid")

    def _translate(self, source: str, warnings: List[str]) -> str:
        lines: List[str] = []
        for line in source.splitlines():
            stripped = line.strip()
            if not stripped or any(mark in stripped for mark in ("{{", "}}", "[[", "]]", "<", ">", "__")):
                lines.append(line)
                continue
            if not self.translate_plain_text:
                warnings.append(f"Untranslated category prose: {stripped}")
                lines.append(line)
                continue
            try:
                translated = self.translate_plain_text(stripped).strip()
            except Exception as exc:
                warnings.append(f"Category prose translation failed: {exc}")
                translated = ""
            lines.append(translated or line)
        result = "\n".join(lines).strip() + "\n"
        # Namespace names are syntax, not prose: localize them deterministically.
        result = re.sub(r"(\[\[\s*)Category:", r"\1Kategori:", result, flags=re.I)
        result = re.sub(r"(\{\{\s*)Category\s+more\b", r"\1Cat more", result, flags=re.I)
        return result

    def _map_category_titles(self, wikitext: str, warnings: List[str]) -> str:
        titles = list(dict.fromkeys(re.findall(r"\[\[Kategori:([^\]|]+)", wikitext, re.I)))
        for name in titles:
            en_title = "Category:" + name.strip()
            payload, error = self.en_client.get({
                "action": "query", "titles": en_title, "prop": "langlinks",
                "lllang": "id", "lllimit": 1, "formatversion": "2",
            })
            if error or not payload:
                continue
            pages = payload.get("query", {}).get("pages", [])
            links = pages[0].get("langlinks", []) if pages else []
            if links and links[0].get("title"):
                local = links[0]["title"].removeprefix("Kategori:")
                wikitext = re.sub(
                    rf"(\[\[\s*Kategori:)({re.escape(name)})(?=[\]|])",
                    rf"\g<1>{local}", wikitext, flags=re.I,
                )
            else:
                evidence = self.evidence_resolver.resolve_category(en_title)
                if len(evidence) == 1 and evidence[0].confidence >= 0.9:
                    local = evidence[0].title.removeprefix("Kategori:")
                    wikitext = re.sub(
                        rf"(\[\[\s*Kategori:)({re.escape(name)})(?=[\]|])",
                        rf"\g<1>{local}", wikitext, flags=re.I,
                    )
                elif evidence:
                    warnings.append(
                        "Translation candidates require review for parent category "
                        f"{en_title}: " + ", ".join(item.title for item in evidence[:5])
                    )
                else:
                    warnings.append(f"No idwiki translation evidence for parent category: {en_title}")
        return wikitext

    def sync(self, en_title: str, id_title: str, output_dir: Path, category_overrides: Optional[Dict[str, str]] = None) -> CategoryPageSyncResult:
        source, oldid = self._fetch(self.en_client, en_title)
        existing, _ = self._fetch(self.id_client, id_title)
        warnings: List[str] = []
        draft = self._map_category_titles(self._translate(source, warnings), warnings)
        for source_title, target_title in (category_overrides or {}).items():
            source_name = source_title.removeprefix("Category:").removeprefix("Kategori:")
            target_name = target_title.removeprefix("Kategori:").removeprefix("Category:")
            draft = re.sub(
                rf"(\[\[\s*Kategori:)({re.escape(source_name)})(?=[\]|])",
                rf"\g<1>{target_name}", draft, flags=re.I,
            )
            warnings[:] = [
                warning for warning in warnings if source_title not in warning
            ]
        output_dir.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r'[\\/*?:"<>|]+', "_", id_title)
        path = output_dir / f"{safe}.wikitext"
        path.write_text(draft, encoding="utf-8")
        manifest_path = output_dir / "approval-manifest.json"
        ApprovalManifest.create(f"category-page:{id_title}", [path]).write(manifest_path)
        result = CategoryPageSyncResult(en_title, id_title, oldid, draft, existing, draft != existing, warnings, str(path), str(manifest_path))
        (output_dir / f"{safe}.json").write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return result

    @staticmethod
    def diff(result: CategoryPageSyncResult) -> str:
        return "".join(difflib.unified_diff(
            result.existing_wikitext.splitlines(True),
            result.draft_wikitext.splitlines(True),
            fromfile=result.id_title + " (existing)",
            tofile=result.id_title + " (draft)",
        ))

    def publish(self, result: CategoryPageSyncResult, username: str, bot_password: str) -> Dict[str, object]:
        """Publish an approved draft with a current-revision conflict check."""
        manifest = ApprovalManifest(**json.loads(Path(result.approval_manifest_path).read_text(encoding="utf-8")))
        ok, errors = manifest.verify()
        if not ok:
            return {"success": False, "errors": errors}
        existing, revision = self._fetch(self.id_client, result.id_title)
        if existing != result.existing_wikitext:
            return {"success": False, "errors": ["target changed since draft was generated"]}
        token = CategoryReconciler(en_client=self.en_client, id_client=self.id_client)._authenticate(username, bot_password)
        payload, error = self.id_client.post({
            "action": "edit", "title": result.id_title, "text": result.draft_wikitext,
            "summary": "sinkronisasi halaman kategori dari enwiki", "token": token,
            "baserevid": revision, "bot": "1", "assert": "user", "formatversion": "2",
        })
        edit = (payload or {}).get("edit", {})
        return {"success": not error and edit.get("result") == "Success", "error": error or (payload or {}).get("error", {}).get("info"), "edit": edit}
