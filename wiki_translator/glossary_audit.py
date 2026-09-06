"""Check that glossary-resolved terms remain consistent in a translated draft."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .glossary_resolver import (
    BASE_EXONYMS_AND_TERMS,
    IDIOM_AND_PHRASE_MAPPINGS,
    TOPIC_GLOSSARIES,
    GlossaryResolver,
    default_glossary_resolver,
    extract_candidate_terms,
)


@dataclass(frozen=True)
class GlossaryTermEvidence:
    term: str
    translation: str
    source: str
    confidence: float


@dataclass
class GlossaryConsistencyResult:
    mappings: Dict[str, str] = field(default_factory=dict)
    missing: List[str] = field(default_factory=list)
    evidence: List[GlossaryTermEvidence] = field(default_factory=list)


def resolve_terms_with_evidence(
    source_wikitext: str,
    *,
    topic: Optional[str] = None,
    custom_glossary: Optional[Dict[str, str]] = None,
    resolver: Optional[GlossaryResolver] = None,
) -> List[GlossaryTermEvidence]:
    """Resolve only the selected topic plus universal terms, with provenance."""
    glossary = resolver or default_glossary_resolver
    active = TOPIC_GLOSSARIES.get(topic, {}) if topic else {}
    if custom_glossary:
        active = {**active, **custom_glossary}
    active_by_key = {key.casefold(): value for key, value in active.items()}
    candidates = extract_candidate_terms(source_wikitext)
    result: List[GlossaryTermEvidence] = []
    for term in candidates:
        key = term.casefold()
        if key in active_by_key:
            translation = active_by_key[key]
            result.append(GlossaryTermEvidence(term, translation, "topic", 1.0))
        elif key in BASE_EXONYMS_AND_TERMS:
            result.append(GlossaryTermEvidence(term, BASE_EXONYMS_AND_TERMS[key], "base", 0.95))
        elif key in IDIOM_AND_PHRASE_MAPPINGS:
            result.append(GlossaryTermEvidence(term, IDIOM_AND_PHRASE_MAPPINGS[key], "idiom", 0.9))
    return result


def audit_glossary_consistency(
    source_wikitext: str,
    draft_wikitext: str,
    *,
    topic: Optional[str] = None,
    custom_glossary: Optional[Dict[str, str]] = None,
    resolver: Optional[GlossaryResolver] = None,
) -> GlossaryConsistencyResult:
    glossary = resolver or default_glossary_resolver
    evidence = resolve_terms_with_evidence(
        source_wikitext,
        topic=topic,
        custom_glossary=custom_glossary,
        resolver=glossary,
    )
    mappings = {item.term: item.translation for item in evidence}
    missing = [
        f"{source} -> {target}"
        for source, target in mappings.items()
        if target and target.casefold() not in draft_wikitext.casefold()
    ]
    return GlossaryConsistencyResult(mappings, missing, evidence)
