"""Local approval manifests and append-only transaction journals."""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class ApprovalManifest:
    workflow: str
    approved: bool
    artifacts: Dict[str, str]
    created_at: str
    approved_at: Optional[str] = None

    @classmethod
    def create(cls, workflow: str, paths: Iterable[Path]) -> "ApprovalManifest":
        return cls(
            workflow=workflow,
            approved=False,
            artifacts={str(path): _sha256(path) for path in paths if path.exists()},
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def approve(self) -> None:
        self.approved = True
        self.approved_at = datetime.now(timezone.utc).isoformat()

    def verify(self, require_approval: bool = True) -> tuple[bool, list[str]]:
        errors: list[str] = []
        if require_approval and not self.approved:
            errors.append("manifest is not approved")
        for raw_path, expected in self.artifacts.items():
            path = Path(raw_path)
            if not path.exists():
                errors.append(f"missing artifact: {raw_path}")
            elif _sha256(path) != expected:
                errors.append(f"artifact hash changed: {raw_path}")
        return not errors, errors

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path


class TransactionJournal:
    """Append-only JSONL journal with idempotent status lookup."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, node: str, status: str, **details: Any) -> None:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "node": node,
            "status": status,
            **details,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def latest(self) -> Dict[str, Dict[str, Any]]:
        if not self.path.exists():
            return {}
        result: Dict[str, Dict[str, Any]] = {}
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            result[event["node"]] = event
        return result
