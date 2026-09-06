"""Find existing Indonesian translation evidence before asking the LLM."""

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

from .http_client import MediaWikiApiClient


@dataclass(frozen=True)
class TranslationCandidate:
    title: str
    source: str
    confidence: float

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


class TranslationEvidenceResolver:
    def __init__(self, en_client: MediaWikiApiClient, id_client: MediaWikiApiClient):
        self.en_client = en_client
        self.id_client = id_client

    def resolve_category(self, en_title: str) -> List[TranslationCandidate]:
        candidates: List[TranslationCandidate] = []
        payload, _ = self.en_client.get({
            "action": "query", "titles": en_title, "prop": "langlinks",
            "lllang": "id", "lllimit": 10, "formatversion": "2",
        })
        pages = (payload or {}).get("query", {}).get("pages", [])
        for link in (pages[0].get("langlinks", []) if pages else []):
            title = link.get("title")
            if title:
                candidates.append(TranslationCandidate(title, "sitelink", 1.0))
        if candidates:
            return candidates

        phrase = en_title.split(":", 1)[-1].strip()
        payload, _ = self.id_client.get({
            "action": "query", "list": "search", "srsearch": phrase,
            "srnamespace": 14, "srlimit": 10, "formatversion": "2",
        })
        for item in (payload or {}).get("query", {}).get("search", []):
            title = item.get("title")
            if title:
                candidates.append(TranslationCandidate(title, "idwiki-search", 0.45))
        return candidates


__all__ = ["TranslationCandidate", "TranslationEvidenceResolver"]
