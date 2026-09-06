"""
Unit tests for expanded encyclopedic domain glossaries and structural exemplars.
"""

import unittest

from wiki_translator.prompts import (
    TOPIC_GLOSSARIES,
    STRUCTURAL_EXEMPLARS,
    build_translation_prompt,
    build_polish_prompt,
)
from wiki_translator.gemini import SmartComplexityAnalyzer


class TestDomainGlossariesAndExemplars(unittest.TestCase):

    def test_canonical_topics_present(self):
        canonical_domains = [
            "computing_science",
            "physics_mathematics",
            "medical_biology",
            "history_social",
            "film",
            "tv_series",
            "entertainment",
            "aerospace_aviation",
            "mechanical_engineering",
            "mathematics_statistics",
            "chemistry_materials",
            "earth_environment",
            "economics_finance",
            "military_defense",
            "music_arts",
            "law_jurisprudence",
            "religion",
        ]
        for domain in canonical_domains:
            self.assertIn(domain, TOPIC_GLOSSARIES, f"Domain '{domain}' missing from TOPIC_GLOSSARIES")
            self.assertGreater(len(TOPIC_GLOSSARIES[domain]), 10, f"Domain '{domain}' has too few terms")

    def test_topic_aliases(self):
        aliases = {
            "aerospace": "aerospace_aviation",
            "aviation": "aerospace_aviation",
            "jet": "aerospace_aviation",
            "engineering": "mechanical_engineering",
            "mechanics": "mechanical_engineering",
            "math": "mathematics_statistics",
            "mathematics": "mathematics_statistics",
            "chemistry": "chemistry_materials",
            "geology": "earth_environment",
            "economics": "economics_finance",
            "military": "military_defense",
            "music": "music_arts",
            "law": "law_jurisprudence",
            "agama": "religion",
            "theology": "religion",
            "pure_mathematics": "mathematics_statistics",
        }
        for alias, target in aliases.items():
            self.assertIn(alias, TOPIC_GLOSSARIES)
            self.assertEqual(TOPIC_GLOSSARIES[alias], TOPIC_GLOSSARIES[target])

    def test_aerospace_glossary_terms(self):
        glossary = TOPIC_GLOSSARIES["aerospace_aviation"]
        self.assertEqual(glossary["afterburner"], "pembakar lanjut")
        self.assertEqual(glossary["supercruise"], "jelajah supersonik (supercruise)")
        self.assertEqual(glossary["angle of attack"], "sudut serang")
        self.assertEqual(glossary["thrust vectoring"], "pembelokan daya dorong")
        self.assertEqual(glossary["turbofan"], "turbofan")
    def test_religion_glossary_terms(self):
        glossary = TOPIC_GLOSSARIES["religion"]
        self.assertIn("keabasan", glossary["abbey"])
        self.assertEqual(glossary["archdiocese"], "keuskupan agung")
        self.assertEqual(glossary["monk"], "biarawan")
        self.assertIn("suster", glossary["nun"])
        self.assertEqual(glossary["bhikkhu"], "bikkhu")
        self.assertIn("Tri Sarana", glossary["three refuges"])
        self.assertIn("Tri Ratna", glossary["triple gem"])
        self.assertIn("dai", glossary["missionary"])
        self.assertEqual(glossary["rabbi"], "rabi")

    def test_pure_mathematics_terms(self):
        glossary = TOPIC_GLOSSARIES["mathematics_statistics"]
        self.assertEqual(glossary["set"], "himpunan")
        self.assertEqual(glossary["proper subset"], "himpunan bagian sejati")
        self.assertEqual(glossary["empty set"], "himpunan kosong")
        self.assertEqual(glossary["intersection"], "irisan")
        self.assertEqual(glossary["union"], "gabungan")
        self.assertIn("daerah asal", glossary["domain"])
        self.assertIn("daerah kawan", glossary["codomain"])
        self.assertIn("injektif", glossary["injective"])
        self.assertIn("surjektif", glossary["surjective"])
        self.assertIn("bijektif", glossary["bijective"])
        self.assertEqual(glossary["real number"], "bilangan real")
        self.assertIn("medan", glossary["field"])
        self.assertEqual(glossary["ring"], "gelanggang")

    def test_mechanical_engineering_glossary_terms(self):
        glossary = TOPIC_GLOSSARIES["mechanical_engineering"]
        self.assertEqual(glossary["gearbox"], "kotak roda gigi")
        self.assertEqual(glossary["internal combustion engine"], "mesin pembakaran dalam")
        self.assertEqual(glossary["heat dissipation"], "pelepasan panas / disipasi panas")
        self.assertEqual(glossary["camshaft"], "poros nok / poros bumbungan")

    def test_mathematics_statistics_glossary_terms(self):
        glossary = TOPIC_GLOSSARIES["mathematics_statistics"]
        self.assertEqual(glossary["eigenvalue"], "nilai eigen")
        self.assertEqual(glossary["null hypothesis"], "hipotesis nol")
        self.assertEqual(glossary["compact space"], "ruang kompak")
    def test_history_and_biography_terms_and_exemplars(self):
        glossary = TOPIC_GLOSSARIES["history_social"]
        self.assertEqual(glossary["heir apparent"], "putra mahkota / pewaris takhta utama")
        self.assertEqual(glossary["regent"], "wali penguasa / pemangku takhta")
        self.assertEqual(glossary["styled"], "bergelar")
        self.assertEqual(glossary["survived by"], "meninggalkan (keluarga yang masih hidup)")
        self.assertEqual(glossary["ascend the throne"], "naik takhta")
        self.assertEqual(glossary["abdicate"], "turun takhta / melepaskan takhta")
        self.assertEqual(glossary["serf"], "hamba tani")
        self.assertIn("perhambaan tani", glossary["serfdom"])
        self.assertIn("Dekabris", glossary["decembrist"])
        self.assertEqual(glossary["charlemagne"], "Karel yang Agung")
        self.assertEqual(glossary["peter the great"], "Petrus yang Agung")
        self.assertEqual(glossary["batavia"], "Batavia")
        self.assertEqual(glossary["dutch east indies"], "Hindia Belanda")
        self.assertEqual(glossary["russian empire"], "Kekaisaran Rusia")
        # Verify aliases
        self.assertEqual(TOPIC_GLOSSARIES["biography"], glossary)
        self.assertEqual(TOPIC_GLOSSARIES["history"], glossary)
        self.assertEqual(TOPIC_GLOSSARIES["monarchy"], glossary)

        # Verify structural exemplar injection
        prompt = build_translation_prompt(
            section_title="Early life and rise to power",
            wikitext_content="Born in Corsica, Napoleon rose rapidly through the ranks.",
            topic="biography",
        )
        self.assertIn("Napoleon lahir di Korsika", prompt)
        self.assertIn("putra mahkota", prompt)


    def test_structural_exemplars_injection(self):
        prompt = build_translation_prompt(
            section_title="Propulsion System",
            wikitext_content="The turbofan engine produces 35,000 lbf of thrust.",
            topic="aerospace_aviation",
        )
        self.assertIn("Pola Rekonstruksi Struktur Bahasa Indonesia Alami", prompt)
        self.assertIn("pembelok daya dorong", prompt)
        self.assertIn("afterburner", prompt)

    def test_structural_exemplars_polish_prompt(self):
        prompt = build_polish_prompt(
            source_en="Heat dissipation from the gearbox is achieved through forced air.",
            draft_id="Disipasi panas dari gearbox dicapai melalui udara paksa.",
            topic="mechanical_engineering",
        )
        self.assertIn("mechanical_engineering", prompt)
        self.assertIn("Instruksi Redaktur", prompt)

    def test_smart_complexity_routing_for_new_topics(self):
        analyzer = SmartComplexityAnalyzer()

        # Aerospace should be categorized as high complexity
        tier = analyzer.recommend_tier(
            "The Pratt & Whitney F119 afterburning turbofan has a high bypass ratio.",
            topic="aerospace_aviation",
        )
        self.assertEqual(tier, "high")

        # Mechanical engineering should also be high complexity
        tier = analyzer.recommend_tier(
            "The planetary gear mechanism dissipates thermal loads efficiently.",
            topic="mechanical_engineering",
        )
        self.assertEqual(tier, "high")

        # Economics should be medium complexity
        tier = analyzer.recommend_tier(
            "The central bank adjusted monetary policy to target inflation.",
            topic="economics_finance",
        )
        self.assertEqual(tier, "medium")


if __name__ == "__main__":
    unittest.main()
