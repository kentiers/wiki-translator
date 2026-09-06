from types import SimpleNamespace
import pytest

from wiki_translator.cli import WikiTranslatorCLI
from wiki_translator.factual_audit import FactualConsistencyAuditor
from wiki_translator.syntax_balancer import WikitextSyntaxBalancer


def gate(*texts):
    cli = WikiTranslatorCLI.__new__(WikiTranslatorCLI)
    cli.syntax_balancer = WikitextSyntaxBalancer()
    return cli._quality_gate([
        SimpleNamespace(title=str(i), full_source=source, translated_content=draft)
        for i, (source, draft) in enumerate(texts)
    ])


def test_references_defined_in_other_sections_are_valid():
    first = 'Kalimat pertama di sini.<ref name="x" />'
    second = 'Kalimat kedua di sini.<ref name="x">Buku sejarah.</ref>'
    assert gate((first, first), (second, second)) == (True, [])


def test_actual_orphan_and_broken_markup_are_blocked():
    for text in ['Kalimat di sini.<ref name="x" />', 'Kalimat di [[sini.']:
        assert not gate((text, text))[0]


def test_indonesian_word_initials_do_not_become_era_suffixes():
    auditor = FactualConsistencyAuditor()
    result = auditor.audit('In 1894 her illness worsened.', 'Pada 1894 memburuk kondisinya.')
    assert result.passed
    assert auditor._NUMBER.findall('1894 M; 1894 SM; 200 juta') == ['1894 M', '1894 SM', '200 juta']


def test_actual_number_loss_and_empty_output_remain_blocked():
    assert not gate(('More than 200 women attended.', 'Lebih dari 700 perempuan hadir.'))[0]
    assert not gate(('A whole source paragraph.', ''))[0]


def test_basic_polarity_inversion_is_blocked():
    ok, failures = gate(('She opposed the proposal.', 'Ia mendukung usulan tersebut.'))
    assert not ok
    assert any('pembalikan makna' in failure for failure in failures)


def test_reference_deduplication_preserves_intervening_prose():
    from wiki_translator.awb_genfixes import GeneralFixesEngine
    text = ('Awal.<ref name="x">Buku X</ref> Pakai lagi.<ref name="x" />'
            '\n== Pendidikan ==\nLebih dari 200 perempuan hadir.'
            '<ref name="y">Buku Y</ref>')
    assert GeneralFixesEngine().deduplicate_references(text) == text


def test_reference_identity_and_conflicting_bodies_are_preserved():
    from wiki_translator.awb_genfixes import GeneralFixesEngine
    text = ('<ref name="x">A</ref><ref name="X">A</ref>'
            '<ref name="x" group="note">A</ref><ref name="x">B</ref>')
    assert GeneralFixesEngine().deduplicate_references(text) == text


def test_save_gate_blocks_postprocessing_loss():
    before = 'Pembuka.<ref name="x">Buku</ref>\n== Karier ==\nIsi lengkap.'
    WikiTranslatorCLI._check_saved_integrity(before, before)
    for after in ['', 'Pembuka.', before.replace('<ref name="x">Buku</ref>', '')]:
        with pytest.raises(ValueError, match='Quality gate penyimpanan'):
            WikiTranslatorCLI._check_saved_integrity(before, after)


def test_rejected_save_keeps_existing_output(tmp_path):
    from wiki_translator.wiki_client import WikiSection
    cli = WikiTranslatorCLI(
        output_dir=str(tmp_path), enable_cache=False,
        enable_map_links=False, enable_template_mapper=False,
        typography_sanitizer=SimpleNamespace(sanitize_wikitext=lambda _: 'Isi terpotong.'),
    )
    target = tmp_path / 'article.wikitext'
    target.write_text('Draf sebelumnya.', encoding='utf-8')
    text = 'Pembuka.<ref>Buku</ref>\n== Karier ==\nIsi lengkap.'
    section = WikiSection(0, 'Lead', 0, '', text, 8, len(text), text)
    with pytest.raises(ValueError, match='Quality gate penyimpanan'):
        cli._save_output('article', 'Artikel', [section])
    assert target.read_text(encoding='utf-8') == 'Draf sebelumnya.'
    assert not (tmp_path / 'article.md').exists()
