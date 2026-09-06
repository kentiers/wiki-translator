"""Keep review inputs and generated output together with explicit provenance."""

from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from .glossary_memory import extract_revision_corrections


def save_review_snapshot(directory: Path, title: str, original: str, english: str,
                         polished: str) -> Path:
    run = directory / "snapshots" / uuid4().hex
    run.mkdir(parents=True, exist_ok=False)
    artifacts = {}
    for name, content in (("original-id.wikitext", original),
                          ("source-en.wikitext", english),
                          ("polished-id.wikitext", polished)):
        data = content.encode("utf-8")
        (run / name).write_bytes(data)
        artifacts[name] = sha256(data).hexdigest()
    candidates = []
    for item in extract_revision_corrections(original, polished):
        record = asdict(item)
        record.update(source="ai_revision", confidence=0.0, status="candidate")
        candidates.append(record)
    candidate_data = json.dumps(candidates, ensure_ascii=False, indent=2).encode("utf-8")
    (run / "candidates.json").write_bytes(candidate_data)
    artifacts["candidates.json"] = sha256(candidate_data).hexdigest()
    manifest = {
        "version": 1,
        "title": title,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "origin": "ai_revision",
        "language_pair": "id-id",
        "human_reviewed": False,
        "candidate_count": len(candidates),
        "sha256": artifacts,
    }
    path = run / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
