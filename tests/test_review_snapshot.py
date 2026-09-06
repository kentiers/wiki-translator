from hashlib import sha256
import json

from wiki_translator.review_snapshot import save_review_snapshot


def test_review_snapshot_keeps_pair_and_ai_provenance(tmp_path):
    manifest_path = save_review_snapshot(
        tmp_path, "Judul", "Ini efektifitas tinggi.", "High effectiveness.",
        "Ini efektivitas tinggi.",
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["human_reviewed"] is False
    assert manifest["language_pair"] == "id-id"
    assert manifest["candidate_count"] == 1
    for filename, digest in manifest["sha256"].items():
        assert sha256((manifest_path.parent / filename).read_bytes()).hexdigest() == digest
    candidates = json.loads((manifest_path.parent / "candidates.json").read_text(encoding="utf-8"))
    assert candidates[0]["source"] == "ai_revision"
    assert candidates[0]["status"] == "candidate"
    second = save_review_snapshot(tmp_path, "Judul", "a", "b", "c")
    assert second.parent != manifest_path.parent
    assert (manifest_path.parent / "original-id.wikitext").read_text() == "Ini efektifitas tinggi."
