"""Regression tests for source-preserving Indonesian editing."""
import pytest

from wiki_translator.slop_linter import AntiAISlopLinter


@pytest.mark.parametrize("text", [
    "Ia lahir pada 1912 dan menghadiri pemakaman ayahnya.",
    "Organisasi yang berbasis di Jenewa ini memainkan peran kunci.",
    "Mereka bertindak dalam upaya untuk mencapai stabilitas.",
    "Ia bertindak dalam upaya putus asa untuk menyelamatkan anaknya.",
    "Efek kecil itu menghasilkan dampak yang signifikan secara statistik.",
    "Gedung ini berfungsi sebagai kantor pusat.",
    "Ia dikenal karena menjadi satu-satunya saksi.",
    "Film ini membuat debutnya tahun lalu.",
    "Titanic merupakan sebuah film.",
    "Mereka dipaksa untuk mundur.",
    "Aktor itu — peraih penghargaan — hadir; syuting dihentikan.",
    "Demonstran pro-Palestina meminta reviu kebijakan.",
    "Ia tidak tahu di mana berkas itu disimpan.",
    "; Istilah\n: Definisi &nbsp; berikut",
])
def test_auto_fix_preserves_context_dependent_meaning(text):
    assert AntiAISlopLinter().auto_fix(text) == (text, 0)


def test_clear_typo_is_fixed_with_capitalization_and_idempotence():
    linter = AntiAISlopLinter()
    fixed, count = linter.auto_fix("Tersbeut adalah ARISTOKTRAT senbagai saksi.")
    assert fixed == "Tersebut adalah ARISTOKRAT sebagai saksi."
    assert count == 3
    assert linter.auto_fix(fixed) == (fixed, 0)


@pytest.mark.parametrize("protected", [
    '<ref name="a">{{cite web|title=tersbeut|date=1912}}</ref>',
    '{{box|caption=tersbeut|nested={{x|senbagai}}}}',
    '[[Tersbeut|senbagai]]',
    '[[File:tersbeut.jpg|thumb|senbagai]]',
    '[https://example.org tersbeut]',
    'https://example.org/tersbeut',
    '<math>tersbeut</math>',
    '<nowiki>tersbeut</nowiki>',
    '<code>senbagai</code>',
    '<!-- tersbeut -->',
    '"tersbeut"',
    '“tersbeut”',
    "''tersbeut''",
])
def test_markup_and_quotes_are_not_rewritten(protected):
    linter = AntiAISlopLinter()
    assert linter.auto_fix(protected + " tersbeut") == (protected + " tersebut", 1)
    assert linter.lint(protected).is_clean


def test_lint_line_numbers_survive_multiline_protected_content():
    text = "<ref>\ntersbeut\n</ref>\ntersbeut"
    report = AntiAISlopLinter().lint(text)
    assert len(report.violations) == 1
    assert report.violations[0].line_number == 4


def test_valid_language_is_not_penalized():
    text = "Ia tidak tahu di mana wanita itu bekerja; alat pro-Indonesia berfungsi sebagai sensor."
    assert AntiAISlopLinter().lint(text).score == 100


def test_style_findings_are_contextual_suggestions():
    report = AntiAISlopLinter().lint("Ia bertindak dalam upaya putus asa untuk membantu.")
    assert report.violations
    assert all(v.severity == "low" for v in report.violations)
    assert "konteks" in report.violations[0].explanation


def test_efn_footnote_prose_is_audited_by_linter():
    linter = AntiAISlopLinter()
    text = "{{Efn|Organisasi ini merupakan sebuah lembaga yang berbasis di Moskow.<ref>Sumber</ref>}}"
    report = linter.lint(text)
    assert not report.is_clean
    rule_ids = [v.rule_id for v in report.violations]
    assert "calque_berbasis_di" in rule_ids
