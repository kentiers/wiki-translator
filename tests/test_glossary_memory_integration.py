from wiki_translator.glossary_memory import GlossaryCandidate, GlossaryMemory, extract_revision_corrections
from wiki_translator.glossary_resolver import GlossaryResolver
import pytest


def test_approved_memory_reaches_section_mapping(tmp_path):
    memory = GlossaryMemory(str(tmp_path / "memory.db"))
    resolver = GlossaryResolver(str(tmp_path / "cache.db"), memory=memory)
    memory.propose(GlossaryCandidate("test device", "perangkat uji", "engineering", None, "human", .9))
    assert memory.approved_terms("engineering") == {}
    memory.approve("test device", "perangkat uji", "engineering")
    assert resolver.resolve_term("test device", topic="engineering", allow_network=False) == "perangkat uji"
    assert resolver.resolve_section_terms("A test device works.", topic="engineering", allow_network=False)["test device"] == "perangkat uji"
    assert memory.approved_terms("medicine") == {}
    assert resolver.resolve_term("test device", topic="engineering", custom_glossary={"test device": "alat uji"}, allow_network=False) == "alat uji"


def test_conflicts_and_revision_evidence_do_not_enter_translation_memory(tmp_path):
    memory = GlossaryMemory(str(tmp_path / "memory.db"))
    for target in ("alat", "perangkat"):
        memory.propose(GlossaryCandidate("device", target, None, None, "human", .9))
        memory.approve("device", target)
    memory.propose(GlossaryCandidate("efektifitas", "efektivitas", None, None, "human_revision", .8))
    memory.approve("efektifitas", "efektivitas")
    assert memory.approved_terms() == {}


def test_proposal_cannot_approve_or_reopen_rejection(tmp_path):
    memory = GlossaryMemory(str(tmp_path / "memory.db"))
    item = GlossaryCandidate("device", "alat", None, None, "llm", .9, status="approved")
    assert memory.propose(item).status == "candidate"
    memory.reject("device", "alat")
    assert memory.propose(item).status == "rejected"


def test_structural_edits_do_not_become_terms():
    for before, after in (
        ("[[Kategori:Lama]]", "[[Kategori:Baru]]"),
        ("{{A|x={{B|old}}}}", "{{A|x={{B|new}}}}"),
        ('<ref name="old">old citation</ref>', '<ref name="new">new citation</ref>'),
        ("<!-- old -->", "<!-- new -->"),
        ("[[Old|label]]", "[[New|label]]"),
    ):
        assert extract_revision_corrections(before, after) == []


@pytest.mark.parametrize("markup", [
    "{{Infobox|x={{nested|old}}}}",
    '<ref name="source">{{cite|title=old}}</ref>',
    '<REF name="source" />',
    "<!-- old -->",
    "[[Kategori:Old]]",
    "[[File:Old.jpg|thumb|old caption]]",
    "<math>old</math>",
    "{|\n| old\n|}",
])
def test_prose_survives_structural_changes(markup):
    before = f"{markup}\nMetode ini efektifitas tinggi."
    after = f"{markup.replace('old', 'new').replace('Old', 'New')}\nMetode ini efektivitas tinggi."
    pairs = extract_revision_corrections(before, after)
    assert [(p.source_term, p.target_term) for p in pairs] == [("efektifitas", "efektivitas")]
    assert all(p.status == "candidate" for p in pairs)


@pytest.mark.parametrize("before,after", [
    ("Ini [[Old|efektifitas]] tinggi.", "Ini [[New|efektivitas]] tinggi."),
    ("Ini '''efektifitas''' tinggi.", "Ini '''efektivitas''' tinggi."),
    ('Ini <span class="old">efektifitas</span> tinggi.', 'Ini <span class="new">efektivitas</span> tinggi.'),
    ("Ini [https://old.test efektifitas] tinggi.", "Ini [https://new.test efektivitas] tinggi."),
])
def test_visible_labels_and_formatting_are_read(before, after):
    pairs = extract_revision_corrections(before, after)
    assert [(p.source_term, p.target_term) for p in pairs] == [("efektifitas", "efektivitas")]


def test_malformed_template_does_not_leak_terms():
    assert extract_revision_corrections("{{Broken|old", "{{Broken|new") == []
