from wiki_translator.glossary_resolver import GlossaryResolver


def test_outlive_preserves_direction_of_comparison(tmp_path):
    resolver = GlossaryResolver(str(tmp_path / "glossary.db"))
    for term in ("outlive", "outliving"):
        assert resolver.resolve_term(term, allow_network=False) == "hidup lebih lama daripada"
