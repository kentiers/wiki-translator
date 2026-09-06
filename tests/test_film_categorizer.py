"""
Unit tests for FilmCategoryNormalizer and WikiProject Film categorization consensus
(wiki_translator/film_categorizer.py and integration with CategoryCurator).
"""

import unittest
from wiki_translator.category_curator import CategoryCurator
from wiki_translator.film_categorizer import (
    FilmCategoryNormalizer,
    default_film_categorizer,
    STANDARD_FILM_GENRES,
    FILM_MEDIUM_MAPPINGS,
    FILM_TOPIC_MAPPINGS,
    FILM_COUNTRY_NORMALIZATION,
)


class TestFilmCategorizerConsensus(unittest.TestCase):
    def setUp(self):
        self.normalizer = FilmCategoryNormalizer()
        self.curator = CategoryCurator(film_categorizer=self.normalizer)

    def test_default_instance(self):
        self.assertIsInstance(default_film_categorizer, FilmCategoryNormalizer)

    # -------------------------------------------------------------------------
    # Rule 1: Anti-Intersectionality & 1-Level Genre Constraint
    # -------------------------------------------------------------------------
    def test_multi_genre_forbidden(self):
        illegal_genres = [
            "Film cerita seru laga",
            "Film aksi laga",
            "Film aksi fiksi ilmiah",
            "Film drama komedi",
            "Film drama romantis",
            "Film komedi horor",
            "Film aksi thriller",
        ]
        for cat in illegal_genres:
            is_valid, reason = self.normalizer.validate_film_category(cat)
            self.assertFalse(is_valid, f"Should reject multi-genre: {cat}")
            self.assertIn("multi-genre dilarang", reason)

    def test_genre_plus_year_forbidden(self):
        illegal_genre_years = [
            "Film laga tahun 2024",
            "Film horor tahun 2024",
            "Film drama tahun 2021",
            "Film komedi tahun 2023",
            "Film cerita seru tahun 2025",
        ]
        for cat in illegal_genre_years:
            is_valid, reason = self.normalizer.validate_film_category(cat)
            self.assertFalse(is_valid, f"Should reject genre+year: {cat}")
            self.assertIn("genre + tahun", reason)

    def test_genre_plus_country_forbidden(self):
        illegal_genre_countries = [
            "Film laga Amerika Serikat",
            "Film horor Indonesia",
            "Film drama Prancis",
            "Film komedi Jepang",
            "Film cerita seru Britania Raya",
        ]
        for cat in illegal_genre_countries:
            is_valid, reason = self.normalizer.validate_film_category(cat)
            self.assertFalse(is_valid, f"Should reject genre+country: {cat}")
            self.assertIn("genre + negara", reason)

    # -------------------------------------------------------------------------
    # Rule 2: Allowed Level 2 Combination (Country + Year)
    # -------------------------------------------------------------------------
    def test_country_plus_year_allowed(self):
        valid_country_years = [
            "Film Indonesia tahun 2021",
            "Film Amerika Serikat tahun 2024",
            "Film Britania Raya tahun 2026",
            "Film Jepang tahun 2023",
            "Film Prancis tahun 2020",
        ]
        for cat in valid_country_years:
            is_valid, reason = self.normalizer.validate_film_category(cat)
            self.assertTrue(is_valid, f"Should allow country+year: {cat}")
            self.assertIsNone(reason)

    # -------------------------------------------------------------------------
    # Rule 3: UK Entity Merging (Britania Raya)
    # -------------------------------------------------------------------------
    def test_uk_subdivisions_forbidden_in_film_categories(self):
        illegal_uk = [
            "Film Inggris tahun 2024",
            "Film Skotlandia tahun 2020",
            "Film Wales",
            "Film Irlandia Utara",
        ]
        for cat in illegal_uk:
            is_valid, reason = self.normalizer.validate_film_category(cat)
            self.assertFalse(is_valid, f"Should reject UK constituent nation: {cat}")
            self.assertIn("Britania Raya", reason)

    def test_uk_decomposes_to_britania_raya(self):
        decomposed_british = self.normalizer.decompose_enwiki_film_category("2026 British films")
        self.assertEqual(decomposed_british, ["Kategori:Film Britania Raya tahun 2026"])

        decomposed_english = self.normalizer.decompose_enwiki_film_category("English comedy films")
        self.assertIn("Kategori:Film Britania Raya", decomposed_english)
        self.assertIn("Kategori:Film komedi", decomposed_english)

    # -------------------------------------------------------------------------
    # Rule 4: Standardized Vocabulary (Action -> Film laga, etc.)
    # -------------------------------------------------------------------------
    def test_standard_genre_vocabulary(self):
        self.assertEqual(STANDARD_FILM_GENRES["action"], "Film laga")
        self.assertEqual(STANDARD_FILM_GENRES["thriller"], "Film cerita seru")
        self.assertEqual(STANDARD_FILM_GENRES["sci-fi"], "Film fiksi ilmiah")
        self.assertEqual(STANDARD_FILM_GENRES["science fiction"], "Film fiksi ilmiah")
        self.assertEqual(STANDARD_FILM_GENRES["romance"], "Film romantis")
        self.assertEqual(STANDARD_FILM_GENRES["romantic comedy"], "Film komedi romantis")
        self.assertEqual(STANDARD_FILM_GENRES["superhero"], "Film pahlawan super")

    def test_standard_medium_vocabulary(self):
        self.assertEqual(FILM_MEDIUM_MAPPINGS["live-action"], "Film peran hidup")
        self.assertEqual(FILM_MEDIUM_MAPPINGS["animated"], "Film animasi")
        self.assertEqual(FILM_MEDIUM_MAPPINGS["computer-animated"], "Film animasi komputer")
        self.assertEqual(FILM_MEDIUM_MAPPINGS["anime"], "Film anime")

    def test_standard_topic_vocabulary(self):
        self.assertEqual(FILM_TOPIC_MAPPINGS["christmas"], "Film tentang Natal")
        self.assertEqual(FILM_TOPIC_MAPPINGS["heist"], "Film tentang perampokan")
        self.assertEqual(FILM_TOPIC_MAPPINGS["silat"], "Film tentang silat")
        self.assertEqual(FILM_TOPIC_MAPPINGS["basketball"], "Film tentang basket")

    # -------------------------------------------------------------------------
    # Rule 5: Decomposer & Flattener Engine
    # -------------------------------------------------------------------------
    def test_decompose_complex_action_thriller(self):
        res = self.normalizer.decompose_enwiki_film_category("2024 American action thriller films")
        self.assertEqual(
            res,
            [
                "Kategori:Film Amerika Serikat tahun 2024",
                "Kategori:Film cerita seru",
                "Kategori:Film laga",
            ],
        )

    def test_decompose_live_action_superhero(self):
        res = self.normalizer.decompose_enwiki_film_category("Live-action superhero films")
        self.assertIn("Kategori:Film pahlawan super", res)
        self.assertIn("Kategori:Film peran hidup", res)
        # Verify action was not falsely triggered by live-action
        self.assertNotIn("Kategori:Film laga", res)

    def test_decompose_heist_films(self):
        res = self.normalizer.decompose_enwiki_film_category("Heist films")
        self.assertEqual(res, ["Kategori:Film tentang perampokan"])

    def test_decompose_american_christmas_comedy(self):
        res = self.normalizer.decompose_enwiki_film_category("American Christmas comedy films")
        self.assertIn("Kategori:Film Amerika Serikat", res)
        self.assertIn("Kategori:Film komedi", res)
        self.assertIn("Kategori:Film tentang Natal", res)

    def test_decompose_director_films(self):
        res = self.normalizer.decompose_enwiki_film_category("Films directed by Christopher Nolan")
        self.assertEqual(res, ["Kategori:Film yang disutradarai oleh Christopher Nolan"])

    def test_normalize_film_categories_batch(self):
        batch = [
            "Category:2024 American action thriller films",
            "Category:British action thriller films",
            "Heist films",
        ]
        norm = self.normalizer.normalize_film_categories(batch)
        self.assertIn("Kategori:Film Amerika Serikat tahun 2024", norm)
        self.assertIn("Kategori:Film Britania Raya", norm)
        self.assertIn("Kategori:Film laga", norm)
        self.assertIn("Kategori:Film cerita seru", norm)
        self.assertIn("Kategori:Film tentang perampokan", norm)

    # -------------------------------------------------------------------------
    # Rule 6: CategoryCurator Integration & Parent Inferences
    # -------------------------------------------------------------------------
    def test_curator_infer_parents_film_country_year(self):
        parents = self.curator.infer_parent_categories("Film Amerika Serikat tahun 2024")
        self.assertIn("[[Kategori:Film Amerika Serikat]]", parents)
        self.assertIn("[[Kategori:Film tahun 2024]]", parents)

    def test_curator_infer_parents_film_genre(self):
        parents = self.curator.infer_parent_categories("Film laga")
        self.assertIn("[[Kategori:Film menurut genre]]", parents)

    def test_curator_infer_parents_film_topic(self):
        parents = self.curator.infer_parent_categories("Film tentang Natal")
        self.assertIn("[[Kategori:Film menurut topik]]", parents)

    def test_curator_infer_parents_film_medium(self):
        parents = self.curator.infer_parent_categories("Film peran hidup")
        self.assertIn("[[Kategori:Film menurut teknologi]]", parents)

    def test_curator_curate_violating_film_category(self):
        res = self.curator.curate_category("Film laga Amerika Serikat")
        self.assertFalse(res["is_safe_to_create"])
        self.assertFalse(res["consensus_valid"])
        self.assertIn("melanggar konsensus", res["reason"])
        self.assertIn("Kategori:Film Amerika Serikat", res["suggested_categories"])
        self.assertIn("Kategori:Film laga", res["suggested_categories"])


if __name__ == "__main__":
    unittest.main()
