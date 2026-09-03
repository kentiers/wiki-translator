"""
Unit tests for disambiguation title normalizer (Hukum D-M vs Modifier-Head).
Verifies WP:PEDAN compliance for Indonesian Wikipedia disambiguation formats.
"""

import unittest
from wiki_translator.template_mapper import (
    normalize_disambiguation_titles,
    normalize_disambiguation_parenthetical,
    normalize_tentang_param,
    WikiTemplateMapper,
)


class TestDisambiguationNormalizer(unittest.TestCase):
    def setUp(self):
        self.mapper = WikiTemplateMapper(allow_network=False)

    def test_normalize_film_inverted_year_country(self):
        """Test flipping (film YYYY Country) -> (film Country YYYY) with demonym normalization."""
        # American -> Amerika Serikat
        self.assertEqual(
            normalize_disambiguation_parenthetical("film 2026 Amerika"),
            "film Amerika Serikat 2026",
        )
        self.assertEqual(
            normalize_disambiguation_parenthetical("film 2026 American"),
            "film Amerika Serikat 2026",
        )
        # Spanish -> Spanyol
        self.assertEqual(
            normalize_disambiguation_parenthetical("film 2026 Spanyol"),
            "film Spanyol 2026",
        )
        self.assertEqual(
            normalize_disambiguation_parenthetical("film 2026 Spanish"),
            "film Spanyol 2026",
        )
        # British -> Britania Raya
        self.assertEqual(
            normalize_disambiguation_parenthetical("film 2026 Britania"),
            "film Britania Raya 2026",
        )
        self.assertEqual(
            normalize_disambiguation_parenthetical("film 2026 British"),
            "film Britania Raya 2026",
        )
        # French -> Prancis
        self.assertEqual(
            normalize_disambiguation_parenthetical("film 2026 Prancis"),
            "film Prancis 2026",
        )
        self.assertEqual(
            normalize_disambiguation_parenthetical("film 2026 French"),
            "film Prancis 2026",
        )
        # Japanese -> Jepang
        self.assertEqual(
            normalize_disambiguation_parenthetical("film 2026 Jepang"),
            "film Jepang 2026",
        )
        # South Korean -> Korea Selatan
        self.assertEqual(
            normalize_disambiguation_parenthetical("film 2026 Korea Selatan"),
            "film Korea Selatan 2026",
        )

    def test_normalize_film_english_pattern(self):
        """Test (YYYY Country film) -> (film Country YYYY)."""
        self.assertEqual(
            normalize_disambiguation_parenthetical("2026 American film"),
            "film Amerika Serikat 2026",
        )
        self.assertEqual(
            normalize_disambiguation_parenthetical("2026 Spanish film"),
            "film Spanyol 2026",
        )
        self.assertEqual(
            normalize_disambiguation_parenthetical("2026 British film"),
            "film Britania Raya 2026",
        )
        self.assertEqual(
            normalize_disambiguation_parenthetical("2026 French film"),
            "film Prancis 2026",
        )
        self.assertEqual(
            normalize_disambiguation_parenthetical("2026 Japanese film"),
            "film Jepang 2026",
        )
        self.assertEqual(
            normalize_disambiguation_parenthetical("2026 South Korean film"),
            "film Korea Selatan 2026",
        )

    def test_normalize_film_country_normalization(self):
        """Ensure 'Amerika' in (film Amerika 2026) becomes 'Amerika Serikat'."""
        self.assertEqual(
            normalize_disambiguation_parenthetical("film Amerika 2026"),
            "film Amerika Serikat 2026",
        )

    def test_normalize_media_disambiguators(self):
        """Test media disambiguations: (YYYY television series) -> (serial televisi YYYY), etc."""
        self.assertEqual(
            normalize_disambiguation_parenthetical("2026 television series"),
            "serial televisi 2026",
        )
        self.assertEqual(
            normalize_disambiguation_parenthetical("2026 tv series"),
            "serial televisi 2026",
        )
        self.assertEqual(
            normalize_disambiguation_parenthetical("1984 novel"),
            "novel 1984",
        )
        self.assertEqual(
            normalize_disambiguation_parenthetical("2020 video game"),
            "permainan video 2020",
        )
        self.assertEqual(
            normalize_disambiguation_parenthetical("2015 album"),
            "album 2015",
        )

    def test_normalize_person_disambiguators(self):
        """Test person disambiguations: (director) -> (sutradara), etc."""
        self.assertEqual(normalize_disambiguation_parenthetical("director"), "sutradara")
        self.assertEqual(normalize_disambiguation_parenthetical("actor"), "pemeran")
        self.assertEqual(normalize_disambiguation_parenthetical("actress"), "pemeran")
        self.assertEqual(normalize_disambiguation_parenthetical("politician"), "politikus")
        self.assertEqual(normalize_disambiguation_parenthetical("footballer"), "pesepak bola")
        self.assertEqual(normalize_disambiguation_parenthetical("musician"), "musisi")
        self.assertEqual(normalize_disambiguation_parenthetical("writer"), "penulis")
        self.assertEqual(normalize_disambiguation_parenthetical("singer"), "penyanyi")

    def test_normalize_tentang_template(self):
        """Test {{Tentang}} and {{About}} parameter normalization."""
        wikitext = (
            "{{Tentang||film Amerika|Runner (film 2026 Amerika)|film Spanyol|Runner (film 2026 Spanyol)}}"
        )
        expected = (
            "{{Tentang||film Amerika Serikat tahun 2026|Runner (film Amerika Serikat 2026)|film Spanyol tahun 2026|Runner (film Spanyol 2026)}}"
        )
        self.assertEqual(normalize_disambiguation_titles(wikitext), expected)

        # English About template
        wikitext_en = (
            "{{About||the American film|Runner (2026 American film)|the Spanish film|Runner (2026 Spanish film)}}"
        )
        self.assertEqual(normalize_disambiguation_titles(wikitext_en), expected)

        # Existing partially translated form
        wikitext_partial = (
            "{{Tentang||film Amerika|Runner (film Amerika 2026)|film Spanyol|Runner (film Spanyol 2026)}}"
        )
        self.assertEqual(normalize_disambiguation_titles(wikitext_partial), expected)

    def test_normalize_disambiguation_in_full_wikitext(self):
        """Test that links, hatnotes, and parentheticals are normalized in full wikitext."""
        wikitext = (
            "{{Tentang||film Amerika|Runner (film 2026 Amerika)|film Spanyol|Runner (film 2026 Spanyol)}}\n"
            "{{Infobox film\n"
            "| name = The Runner\n"
            "| director = {{ill|Kevin Macdonald|en|Kevin Macdonald (director)}}\n"
            "}}\n"
            "Artikel ini membahas film karya [[John Doe (director)]].\n"
            "Buku terkait: [[War and Peace (1869 novel)]].\n"
            "Film lain: [[Runner (2026 American film)]]."
        )
        result = self.mapper.process_wikitext_templates(wikitext, check_existence=False)
        self.assertIn(
            "{{Tentang||film Amerika Serikat tahun 2026|Runner (film Amerika Serikat 2026)|film Spanyol tahun 2026|Runner (film Spanyol 2026)}}",
            result,
        )
        self.assertIn("{{ill|Kevin Macdonald|en|Kevin Macdonald (director)}}", result)
        self.assertIn("[[John Doe (sutradara)]]", result)
        self.assertIn("[[War and Peace (novel 1869)]]", result)
        self.assertIn("[[Runner (film Amerika Serikat 2026)]]", result)

    def test_preserve_digits_and_comments(self):
        """Ensure numbers like (8) and HTML comments are preserved."""
        wikitext = "Total delapan (8) orang. <!-- film 2026 Amerika -->"
        result = normalize_disambiguation_titles(wikitext)
        self.assertEqual(result, "Total delapan (8) orang. <!-- film 2026 Amerika -->")


if __name__ == "__main__":
    unittest.main()
