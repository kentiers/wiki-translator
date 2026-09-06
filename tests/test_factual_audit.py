from wiki_translator.factual_audit import FactualConsistencyAuditor


def test_flags_missing_source_numbers_and_references():
    result = FactualConsistencyAuditor().audit(
        "Didirikan pada 2020. Nilai 50%.<ref>Source</ref>",
        "Didirikan pada 2019. Nilai 50%.",
    )
    assert "2020" in result.missing_numbers
    assert result.source_references == 1
    assert result.draft_references == 0
    assert not result.passed


def test_consistency_passes_when_numbers_and_refs_preserved():
    result = FactualConsistencyAuditor().audit(
        "Pada 2020, nilai 50%.<ref>Source</ref>",
        "Pada 2020, nilai 50%.<ref>Sumber</ref>",
    )
    assert result.passed
