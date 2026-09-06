import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from wiki_translator.article_quality import check_saved_integrity, review_claims
from wiki_translator.article_reviewer import ArticleReviewer
from wiki_translator.cli import WikiTranslatorCLI
from wiki_translator.typography_sanitizer import TypographySanitizer
from wiki_translator.awb_genfixes import RegExTypoFixEngine
from wiki_translator.wiki_client import WikiSection


def response(source, draft, status='supported'):
    return {'complete': True, 'claims': [{'source_quote': source, 'draft_quote': draft, 'status': status, 'reason': 'Temuan uji.'}], 'additions': []}


@pytest.mark.parametrize('source,draft,status', [
    ('She opposed the proposal.', 'Ia mendukung usulan tersebut.', 'contradicted'),
    ('She mentored Anna.', 'Anna membimbingnya.', 'contradicted'),
    ('She founded a cooperative.', '', 'missing'),
    ('It may cause illness.', 'Hal itu pasti menyebabkan penyakit.', 'contradicted'),
    ('More than 200 women attended.', 'Sebanyak 200 perempuan hadir.', 'contradicted'),
])
def test_claim_findings_block_with_evidence(source, draft, status):
    client = MagicMock()
    client.translate_section.return_value = json.dumps(response(source, draft, status))
    assert review_claims(source, draft, client)
    assert 'untrusted data' in client.translate_section.call_args.kwargs['system_instruction']


def test_equivalent_paraphrase_is_accepted():
    source, draft = 'She opposed the proposal.', 'Ia menentang usulan itu.'
    client = MagicMock()
    client.translate_section.return_value = json.dumps(response(source, draft))
    assert review_claims(source, draft, client) == []


@pytest.mark.parametrize('raw', ['', '{}', '{"complete":true,"claims":[],"additions":[]}', json.dumps(response('invented source', 'invented draft')), json.dumps(dict(response('She wrote.', 'Ia menulis.'), complete=False))])
def test_incomplete_or_fabricated_review_fails_closed(raw):
    client = MagicMock()
    client.translate_section.return_value = raw
    assert review_claims('She opposed the proposal.', 'Ia mendukung usulan itu.', client)


def test_unavailable_reviewer_blocks_acceptance():
    assert review_claims('She wrote.', 'Ia menulis.', None)


def test_automatic_cleanup_preserves_valid_words_quotes_and_markup():
    text = ('Unta mempelajari tata bahasa secara sistematik; ia pro-Palestina — menurut sumber. '
            '"aktifitas; analisa" [[Analisa|analisa]] {{cite book|title=Analisa|url=https://example.org/aktifitas}} '
            '<ref name="x">Analisa merupakan judul.</ref>')
    assert RegExTypoFixEngine().fix_typos(text) == text
    assert TypographySanitizer().sanitize_wikitext(text) == text
    assert RegExTypoFixEngine().fix_typos('Aktifitas meningkat.') == 'Aktivitas meningkat.'


def test_sentence_loss_without_numbers_is_blocked_after_cleanup():
    before = 'Pembuka.\n== Karier ==\nIa mendirikan koperasi. Ia memperjuangkan pendidikan perempuan.'
    after = 'Pembuka.\n== Karier ==\nIa mendirikan koperasi.'
    with pytest.raises(ValueError, match='isi kalimat hilang'):
        check_saved_integrity(before, after)


def test_cli_checks_final_text_before_writing(tmp_path):
    cli = WikiTranslatorCLI(output_dir=str(tmp_path), enable_map_links=False, enable_template_mapper=False, enable_cache=False)
    cli._require_claim_review = True
    source, draft = 'She opposed the proposal.', 'Ia mendukung usulan tersebut.'
    section = WikiSection(0, 'Lead', 0, '', source, 4, len(source), draft)
    target = tmp_path / 'article.wikitext'
    target.write_text('Draf lama.', encoding='utf-8')
    with patch('wiki_translator.cli.review_claims', return_value=['Pembalikan makna']) as review:
        with pytest.raises(ValueError, match='Quality gate klaim'):
            cli._save_output('article', 'Article', [section])
        assert review.call_args.args[1].strip() == draft
    assert target.read_text(encoding='utf-8') == 'Draf lama.'


def test_reviewer_blocks_before_any_snapshot_or_write():
    reviewer = ArticleReviewer()
    reviewer.gemini_client = None
    reviewer._gemini_initialized = True
    with patch.object(reviewer, 'fetch_article_pair', return_value=('Ia menulis buku.', 'She wrote a book.')), patch.object(reviewer, 'generate_polished_wikitext', return_value='Ia menulis buku.'), patch('wiki_translator.article_reviewer.review_claims', return_value=['Klaim hilang']), patch('wiki_translator.article_reviewer.save_review_snapshot') as snapshot:
        with pytest.raises(ValueError, match='Quality gate klaim'):
            reviewer.audit_and_report('Uji lokal')
        snapshot.assert_not_called()
