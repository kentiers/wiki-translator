from pathlib import Path
from wiki_translator.category_page_sync import CategoryPageSynchronizer


class Client:
    def __init__(self, text, revid=1): self.text, self.revid = text, revid
    def get(self, params):
        return ({"query": {"pages": [{"revisions": [{"revid": self.revid, "slots": {"main": {"content": self.text}}}]}]}}, None)


def test_sync_creates_local_diff_and_manifest(tmp_path: Path):
    result = CategoryPageSynchronizer(
        Client("Deskripsi English.\n"), Client("Deskripsi lama.\n"),
        translate_plain_text=lambda text: "Deskripsi Indonesia.",
    ).sync("Category:Example", "Kategori:Contoh", tmp_path)
    assert result.changed
    assert result.source_oldid == 1
    assert "Deskripsi Indonesia" in result.draft_wikitext
    assert Path(result.approval_manifest_path).exists()
    assert "Deskripsi lama" in CategoryPageSynchronizer.diff(result)


def test_sync_localizes_category_namespace_and_common_template(tmp_path: Path):
    result = CategoryPageSynchronizer(
        Client("{{Category more|Example}}\n[[Category:People]]\n"),
        Client(""),
    ).sync("Category:Example", "Kategori:Contoh", tmp_path)
    assert "{{Cat more|Example}}" in result.draft_wikitext
    assert "[[Kategori:People]]" in result.draft_wikitext
