import json
from pathlib import Path

from wiki_translator.approval_journal import ApprovalManifest, TransactionJournal
from wiki_translator.publish_gate import PublishGate, PublishTransaction


class FakeClient:
    def __init__(self, page=None, error=None):
        self.page = page or {"title": "Kategori:Baru", "missing": True}
        self.error = error

    def get(self, params):
        if self.error:
            return None, self.error
        return {"query": {"pages": [self.page]}}, None


def approved_manifest(tmp_path: Path) -> Path:
    artifact = tmp_path / "draft.wikitext"
    artifact.write_text("draft", encoding="utf-8")
    manifest = ApprovalManifest.create("test", [artifact])
    manifest.approve()
    return manifest.write(tmp_path / "approval-manifest.json")


def test_gate_allows_approved_unchanged_missing_target(tmp_path):
    result = PublishGate(FakeClient()).check(
        "Kategori:Baru", approved_manifest(tmp_path)
    )
    assert result.allowed
    assert not result.target_exists


def test_gate_rejects_unapproved_or_changed_artifact(tmp_path):
    artifact = tmp_path / "draft.wikitext"
    artifact.write_text("draft", encoding="utf-8")
    path = ApprovalManifest.create("test", [artifact]).write(tmp_path / "manifest.json")
    artifact.write_text("changed", encoding="utf-8")
    result = PublishGate(FakeClient()).check("Kategori:Baru", path)
    assert not result.allowed
    assert any("manifest" in reason and "approved" in reason for reason in result.reasons)
    assert any("artifact hash changed" in reason for reason in result.reasons)


def test_gate_rejects_collision_revision_change_and_blockers(tmp_path):
    client = FakeClient({"title": "Kategori:Ada", "revisions": [{"revid": 12}]})
    result = PublishGate(client).check(
        "Kategori:Ada",
        approved_manifest(tmp_path),
        expected_revision=11,
        blockers=["dependency missing"],
    )
    assert not result.allowed
    assert result.current_revision == 12
    assert "target already exists: Kategori:Ada" in result.reasons
    assert "revision changed: expected 11, current 12" in result.reasons


def test_transaction_orders_resumes_and_stops_on_failure(tmp_path):
    journal = TransactionJournal(tmp_path / "journal.jsonl")
    journal.record("Templat:A", "published")
    called = []

    def publish(title):
        called.append(title)
        return title != "Kategori:C"

    result = PublishTransaction(journal).run(
        ["Templat:A", "Modul:B", "Kategori:C", "Artikel:D"], publish
    )
    assert called == ["Modul:B", "Kategori:C"]
    assert result.statuses["Templat:A"] == "published"
    assert result.statuses["Modul:B"] == "published"
    assert result.statuses["Kategori:C"] == "failed"
    assert "Artikel:D" not in result.statuses
    assert not result.success


def test_transaction_stage_order(tmp_path):
    journal = TransactionJournal(tmp_path / "stages.jsonl")
    called = []
    result = PublishTransaction(journal).run_stages(
        ["Template:A"], ["Kategori:B"], ["Artikel:C"],
        lambda title: called.append(title) or True,
    )
    assert result.success
    assert called == ["Template:A", "Kategori:B", "Artikel:C"]
