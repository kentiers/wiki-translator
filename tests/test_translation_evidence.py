from wiki_translator.translation_evidence import TranslationEvidenceResolver


class Client:
    def __init__(self, payload): self.payload = payload
    def get(self, params): return self.payload, None


def test_sitelink_has_highest_confidence():
    resolver = TranslationEvidenceResolver(
        Client({"query": {"pages": [{"langlinks": [{"title": "Kategori:Karya X"}]}]}}),
        Client({}),
    )
    result = resolver.resolve_category("Category:Works by X")
    assert result[0].source == "sitelink"
    assert result[0].confidence == 1.0


def test_idwiki_search_is_review_candidate():
    resolver = TranslationEvidenceResolver(
        Client({"query": {"pages": [{}]}}),
        Client({"query": {"search": [{"title": "Kategori:Karya X"}]}}),
    )
    result = resolver.resolve_category("Category:Works by X")
    assert result[0].source == "idwiki-search"
    assert result[0].confidence < 1.0
