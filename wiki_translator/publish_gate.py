"""Safety gate and small transaction runner for wiki publications.

The gate is deliberately side-effect free: it only validates local artifacts,
the approval manifest, and the current target revision. Callers decide how to
publish after ``allowed`` is true.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from .approval_journal import ApprovalManifest, TransactionJournal
from .http_client import MediaWikiApiClient, DEFAULT_API_URL


@dataclass
class GateResult:
    allowed: bool
    title: str
    reasons: List[str] = field(default_factory=list)
    current_revision: Optional[int] = None
    target_exists: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "title": self.title,
            "reasons": list(self.reasons),
            "current_revision": self.current_revision,
            "target_exists": self.target_exists,
        }


class PublishGate:
    """Validate an approved artifact before any MediaWiki edit is attempted."""

    def __init__(self, client: Optional[MediaWikiApiClient] = None):
        self.client = client or MediaWikiApiClient(api_url=DEFAULT_API_URL)

    def current_revision(self, title: str) -> tuple[bool, Optional[int], Optional[str]]:
        payload, error = self.client.get(
            {
                "action": "query",
                "titles": title,
                "prop": "revisions",
                "rvprop": "ids",
                "rvlimit": 1,
                "formatversion": "2",
            }
        )
        if error or not payload:
            return False, None, error or "empty MediaWiki response"
        pages = payload.get("query", {}).get("pages", [])
        if not pages or pages[0].get("missing"):
            return False, None, None
        revisions = pages[0].get("revisions", [])
        return True, (revisions[0].get("revid") if revisions else None), None

    def check(
        self,
        title: str,
        manifest_path: Path,
        *,
        blockers: Iterable[str] = (),
        validation_errors: Iterable[str] = (),
        expected_revision: Optional[int] = None,
        allow_existing: bool = False,
        require_approval: bool = True,
    ) -> GateResult:
        reasons: List[str] = []
        try:
            import json

            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = ApprovalManifest(**data)
        except Exception as exc:
            return GateResult(False, title, [f"invalid approval manifest: {exc}"])
        ok, errors = manifest.verify(require_approval=require_approval)
        if not ok:
            reasons.extend(errors)
        reasons.extend(str(x) for x in blockers if str(x))
        reasons.extend(str(x) for x in validation_errors if str(x))

        exists, revision, api_error = self.current_revision(title)
        if api_error:
            reasons.append(f"revision check failed: {api_error}")
        if exists and not allow_existing:
            reasons.append(f"target already exists: {title}")
        if expected_revision is not None and revision != expected_revision:
            reasons.append(
                f"revision changed: expected {expected_revision}, current {revision}"
            )
        return GateResult(not reasons, title, reasons, revision, exists)


@dataclass
class TransactionResult:
    statuses: Dict[str, str]
    errors: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.errors


class PublishTransaction:
    """Run already-planned nodes in dependency order with resumable journal."""

    def __init__(self, journal: TransactionJournal):
        self.journal = journal

    def run(
        self,
        nodes: Iterable[str],
        publish: Callable[[str], bool],
        *,
        reused: Iterable[str] = (),
        resume: bool = True,
    ) -> TransactionResult:
        statuses: Dict[str, str] = {
            title: event.get("status", "")
            for title, event in self.journal.latest().items()
        } if resume else {}
        errors: List[str] = []
        reused_titles = set(reused)
        for title in nodes:
            if title in statuses and statuses[title] in {"published", "reused"}:
                continue
            if title in reused_titles:
                statuses[title] = "reused"
                self.journal.record(title, "reused")
                continue
            self.journal.record(title, "planned")
            try:
                success = bool(publish(title))
            except Exception as exc:
                success = False
                errors.append(f"{title}: {exc}")
            if not success:
                statuses[title] = "failed"
                self.journal.record(title, "failed", reason=errors[-1] if errors else "publish failed")
                errors.append(f"{title}: publish failed")
                break
            statuses[title] = "published"
            self.journal.record(title, "published")
        return TransactionResult(statuses, errors)

    def run_stages(
        self,
        dependencies: Iterable[str],
        categories: Iterable[str],
        memberships: Iterable[str],
        publish: Callable[[str], bool],
        *,
        reused: Iterable[str] = (),
        resume: bool = True,
    ) -> TransactionResult:
        """Publish dependency, category, then membership nodes in fixed order."""
        return self.run(
            [*dependencies, *categories, *memberships],
            publish,
            reused=reused,
            resume=resume,
        )


__all__ = ["GateResult", "PublishGate", "PublishTransaction", "TransactionResult"]
