from unittest.mock import patch

from wiki_translator.glossary_resolver import GlossaryResolver
from wiki_translator.paragraph_translator import ParagraphTranslator
from wiki_translator.prompts import (
    SYSTEM_PROMPT_GRADE_A_PLUS_PLUS,
    SYSTEM_PROMPT_HUMANIZE_POLISH,
    build_translation_prompt,
)
from wiki_translator.editorial_qa import EditorialQAPipeline


def test_custom_glossary_overrides_case_insensitive_conflicts():
    prompt = build_translation_prompt(
        'Physics', 'Spin', topic='physics_mathematics',
        resolved_glossary={'SPIN': 'putaran'}, custom_glossary={'Spin': 'spin kuantum'},
    )
    assert prompt.count('-> "spin kuantum"') == 1
    assert '-> "putaran"' not in prompt
    assert '-> "spin"' not in prompt


def test_glossary_does_not_borrow_another_fields_sense(tmp_path):
    resolver = GlossaryResolver(str(tmp_path / 'glossary.db'))
    assert resolver.resolve_term('spin', topic='physics_mathematics', allow_network=False) == 'spin'
    assert resolver.resolve_term('spin', topic='film', allow_network=False) is None
    with patch('wiki_translator.glossary_resolver.extract_candidate_terms', return_value=['spin']):
        assert resolver.resolve_section_terms('spin', topic='film', allow_network=False) == {}


def test_chunk_context_contains_source_and_explicit_system_instruction():
    calls = []

    def translate(prompt, system):
        calls.append((prompt, system))
        return 'Draf keliru.'

    ParagraphTranslator(max_chunk_words=3).translate_section_by_paragraphs(
        'History', 'He may return.\n\nShe did not leave.', translate,
    )
    assert len(calls) == 2
    assert all(system == SYSTEM_PROMPT_GRADE_A_PLUS_PLUS for _, system in calls)
    assert 'He may return.' in calls[1][0]
    assert 'draf dapat keliru' in calls[1][0]
    assert 'bukan sumber fakta tambahan' in calls[1][0]


def test_polisher_shares_fidelity_rules():
    assert SYSTEM_PROMPT_HUMANIZE_POLISH.startswith(SYSTEM_PROMPT_GRADE_A_PLUS_PLUS)


def test_source_mismatch_blocks_qa_even_when_structure_is_good():
    text = ('Indonesia adalah negara kepulauan di Asia Tenggara. ' * 25
            + '\n== Referensi ==\n{{Reflist}}')
    report = EditorialQAPipeline().audit(text, source_wikitext=text + ' Pada 2020.')
    assert report.factual_consistency.missing_numbers == ['2020']
    assert not report.approved
    assert report.critical_errors
