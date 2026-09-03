"""
Unit tests for InfoboxMapper and infobox parameter mapping in wiki_translator.
"""

import unittest
from wiki_translator.infobox_mapper import (
    InfoboxMapper,
    default_infobox_mapper,
)
from wiki_translator.template_mapper import (
    WikiTemplateMapper,
)


class TestInfoboxMapper(unittest.TestCase):
    def setUp(self):
        self.mapper = InfoboxMapper()

    # ----------------------------------------------------
    # 1. Infobox Film: Enforce Canonical English Keys & Unit Localization
    # ----------------------------------------------------
    def test_normalize_translated_indonesian_keys_to_english(self):
        """Tests that translated Indonesian keys are restored back to canonical English keys."""
        wikitext = (
            "{{Infobox film\n"
            "| name = Inception\n"
            "| sutradara = Christopher Nolan\n"
            "| produser = Emma Thomas\n"
            "| penulis = Christopher Nolan\n"
            "| skenario = Christopher Nolan\n"
            "| cerita = Christopher Nolan\n"
            "| pemeran = Leonardo DiCaprio\n"
            "| musik = Hans Zimmer\n"
            "| sinematografi = Wally Pfister\n"
            "| penyuntingan = Lee Smith\n"
            "| studio = Syncopy\n"
            "| perusahaan_produksi = Legendary Pictures\n"
            "| distributor = Warner Bros. Pictures\n"
            "| tanggal_rilis = July 16, 2010\n"
            "| durasi = 148 minutes\n"
            "| negara = United States\n"
            "| bahasa = English\n"
            "| anggaran = $160 million\n"
            "| pendapatan_kotor = $836.8 million\n"
            "| unmapped_param = Unchanged Value\n"
            "}}"
        )
        mapped = self.mapper.normalize_infobox_keys(wikitext)
        self.assertIn("| director = Christopher Nolan", mapped)
        self.assertIn("| producer = Emma Thomas", mapped)
        self.assertIn("| writer = Christopher Nolan", mapped)
        self.assertIn("| screenplay = Christopher Nolan", mapped)
        self.assertIn("| story = Christopher Nolan", mapped)
        self.assertIn("| starring = Leonardo DiCaprio", mapped)
        self.assertIn("| music = Hans Zimmer", mapped)
        self.assertIn("| cinematography = Wally Pfister", mapped)
        self.assertIn("| editing = Lee Smith", mapped)
        self.assertIn("| studio = Syncopy", mapped)
        self.assertIn("| distributor = Warner Bros. Pictures", mapped)
        self.assertIn("| release_date = July 16, 2010", mapped)
        self.assertIn("| runtime = 148 minutes", mapped)
        self.assertIn("| country = United States", mapped)
        self.assertIn("| language = English", mapped)
        # Currency and unit localization in values
        self.assertIn("| budget = US$160 juta", mapped)
        self.assertIn("| gross = US$836,8 juta", mapped)
        # Unmapped parameter is preserved
        self.assertIn("| unmapped_param = Unchanged Value", mapped)

    def test_infobox_film_already_english_keys(self):
        """Tests that infoboxes that already use English keys are untouched except value localization."""
        wikitext = (
            "{{Infobox film\n"
            "| director = James Cameron\n"
            "| producer = Jon Landau\n"
            "| writer = James Cameron\n"
            "| studio = Lightstorm Entertainment\n"
            "| distributed_by = 20th Century Fox\n"
            "| release_date = December 18, 2009\n"
            "| budget = $237 million\n"
            "| gross = $2.923 billion\n"
            "}}"
        )
        mapped = self.mapper.normalize_infobox_keys(wikitext)
        self.assertIn("| director = James Cameron", mapped)
        self.assertIn("| producer = Jon Landau", mapped)
        self.assertIn("| writer = James Cameron", mapped)
        self.assertIn("| studio = Lightstorm Entertainment", mapped)
        self.assertIn("| distributed_by = 20th Century Fox", mapped)
        self.assertIn("| release_date = December 18, 2009", mapped)
        self.assertIn("| budget = US$237 juta", mapped)
        self.assertIn("| gross = US$2,923 miliar", mapped)

    # ----------------------------------------------------
    # 2. Infobox Person / Biography Mappings
    # ----------------------------------------------------
    def test_infobox_person_parameter_normalization(self):
        wikitext = (
            "{{Infobox person\n"
            "| nama = Albert Einstein\n"
            "| nama_lahir = Albert Einstein\n"
            "| tanggal_lahir = 14 March 1879\n"
            "| tempat_lahir = Ulm, Kingdom of Württemberg\n"
            "| tanggal_kematian = 18 April 1955\n"
            "| tempat_kematian = Princeton, New Jersey\n"
            "| kebangsaan = German, American\n"
            "| kewarganegaraan = Switzerland, United States\n"
            "| pekerjaan = Theoretical physicist\n"
            "| pasangan = Mileva Marić\n"
            "| anak = Hans Albert Einstein\n"
            "| orang_tua = Hermann Einstein\n"
            "| almamater = University of Zurich\n"
            "| custom_unknown = Preserved\n"
            "}}"
        )
        mapped = self.mapper.normalize_infobox_keys(wikitext)
        self.assertIn("| name = Albert Einstein", mapped)
        self.assertIn("| birth_name = Albert Einstein", mapped)
        self.assertIn("| birth_date = 14 March 1879", mapped)
        self.assertIn("| birth_place = Ulm, Kingdom of Württemberg", mapped)
        self.assertIn("| death_date = 18 April 1955", mapped)
        self.assertIn("| death_place = Princeton, New Jersey", mapped)
        self.assertIn("| nationality = German, American", mapped)
        self.assertIn("| citizenship = Switzerland, Amerika Serikat", mapped)
        self.assertIn("| occupation = Theoretical physicist", mapped)
        self.assertIn("| spouse = Mileva Marić", mapped)
        self.assertIn("| children = Hans Albert Einstein", mapped)
        self.assertIn("| parents = Hermann Einstein", mapped)
        self.assertIn("| alma_mater = University of Zurich", mapped)
        self.assertIn("| custom_unknown = Preserved", mapped)

    def test_infobox_kinship_and_place_localization(self):
        wikitext = (
            "{{Infobox person\n"
            "| name = Kevin Macdonald\n"
            "| birth_place = {{Nowrap|[[Glasgow]], Scotland}}\n"
            "| relatives = [[Andrew Macdonald (produser)|Andrew Macdonald]] (brother)<br>{{ill|Emeric Pressburger|en|Emeric Pressburger}} (grandfather)\n"
            "}}"
        )
        mapped = self.mapper.normalize_infobox_keys(wikitext)
        self.assertIn("| birth_place = {{Nowrap|[[Glasgow]], Skotlandia}}", mapped)
        self.assertIn("(saudara)", mapped)
        self.assertIn("(kakek)", mapped)
        self.assertNotIn("(brother)", mapped)
        self.assertNotIn("(grandfather)", mapped)
        self.assertNotIn("Scotland}}", mapped)

    # ----------------------------------------------------
    # 3. Integration with WikiTemplateMapper
    # ----------------------------------------------------
    def test_integration_with_wiki_template_mapper(self):
        template_mapper = WikiTemplateMapper(allow_network=False)
        wikitext = (
            "{{Main|Daftar film}}\n"
            "{{Infobox film\n"
            "| name = Interstellar\n"
            "| sutradara = Christopher Nolan\n"
            "| anggaran = $165 million\n"
            "| pendapatan_kotor = $701.8 million\n"
            "}}\n"
            "Film ini sukses besar."
        )
        result = template_mapper.process_wikitext_templates(wikitext, check_existence=False)
        self.assertIn("{{Utama|Daftar film}}", result)
        self.assertIn("| director = Christopher Nolan", result)
        self.assertIn("| budget = US$165 juta", result)
        self.assertIn("| gross = US$701,8 juta", result)

    def test_nested_templates_inside_infobox(self):
        wikitext = (
            "{{Infobox film\n"
            "| name = The Dark Knight\n"
            "| sutradara = Christopher Nolan\n"
            "| pemeran = {{plainlist|\n"
            "* Christian Bale\n"
            "* Heath Ledger\n"
            "}}\n"
            "| anggaran = $185 million\n"
            "}}"
        )
        mapped = self.mapper.normalize_infobox_keys(wikitext)
        self.assertIn("| director = Christopher Nolan", mapped)
        self.assertIn("| starring = {{plainlist|", mapped)
        self.assertIn("| budget = US$185 juta", mapped)


if __name__ == "__main__":
    unittest.main()
