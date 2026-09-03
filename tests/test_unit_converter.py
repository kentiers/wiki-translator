"""
Unit tests for UnitCurrencyLocalizer (wiki_translator/unit_converter.py).
"""

import unittest
from wiki_translator.unit_converter import (
    UnitCurrencyLocalizer,
    default_unit_converter,
)


class TestUnitCurrencyLocalizer(unittest.TestCase):
    def setUp(self):
        self.converter = UnitCurrencyLocalizer()

    # ----------------------------------------------------
    # 1. Currency Tests
    # ----------------------------------------------------
    def test_currency_million_billion_thousand(self):
        self.assertEqual(self.converter.localize_currency("$50 million"), "US$50 juta")
        self.assertEqual(self.converter.localize_currency("$50M"), "US$50 juta")
        self.assertEqual(self.converter.localize_currency("$50 billion"), "US$50 miliar")
        self.assertEqual(self.converter.localize_currency("$50B"), "US$50 miliar")
        self.assertEqual(self.converter.localize_currency("$50 thousand"), "US$50 ribu")
        self.assertEqual(self.converter.localize_currency("$50K"), "US$50 ribu")
        self.assertEqual(self.converter.localize_currency("US$ 50 million"), "US$50 juta")
        self.assertEqual(self.converter.localize_currency("US$50 million"), "US$50 juta")

    def test_currency_decimals_and_thousands(self):
        self.assertEqual(self.converter.localize_currency("$50,000"), "US$50.000")
        self.assertEqual(self.converter.localize_currency("$50.00"), "US$50,00")
        self.assertEqual(self.converter.localize_currency("$1.5 million"), "US$1,5 juta")
        self.assertEqual(self.converter.localize_currency("$2.5 billion"), "US$2,5 miliar")

    def test_other_major_currencies(self):
        self.assertEqual(self.converter.localize_currency("£10 million"), "£10 juta")
        self.assertEqual(self.converter.localize_currency("€5 million"), "€5 juta")
        self.assertEqual(self.converter.localize_currency("¥100 billion"), "¥100 miliar")
        self.assertEqual(
            self.converter.localize_currency("₹50 crore"),
            "₹50 crore (sekitar 500 juta)"
        )
        self.assertEqual(
            self.converter.localize_currency("₹5 crore"),
            "₹5 crore (sekitar 50 juta)"
        )
        self.assertEqual(
            self.converter.localize_currency("₹50 lakh"),
            "₹50 lakh (sekitar 5 juta)"
        )

    # ----------------------------------------------------
    # 2. Measurement Unit Tests
    # ----------------------------------------------------
    def test_measurement_units_spelled_out_and_abbrev(self):
        self.assertEqual(self.converter.localize_measurement_units("50 miles"), "50 mil")
        self.assertEqual(self.converter.localize_measurement_units("50 mi"), "50 mil")
        self.assertEqual(self.converter.localize_measurement_units("50 feet"), "50 kaki")
        self.assertEqual(self.converter.localize_measurement_units("50 ft"), "50 kaki")
        self.assertEqual(self.converter.localize_measurement_units("50 inches"), "50 inci")
        self.assertEqual(self.converter.localize_measurement_units("50 in"), "50 inci")
        self.assertEqual(self.converter.localize_measurement_units("50 pounds"), "50 pon")
        self.assertEqual(self.converter.localize_measurement_units("50 lbs"), "50 pon")
        self.assertEqual(self.converter.localize_measurement_units("50 square miles"), "50 mil persegi")
        self.assertEqual(self.converter.localize_measurement_units("sq mi"), "mil persegi")
        self.assertEqual(self.converter.localize_measurement_units("50 square feet"), "50 kaki persegi")
        self.assertEqual(self.converter.localize_measurement_units("sq ft"), "kaki persegi")
        self.assertEqual(self.converter.localize_measurement_units("50 light-years"), "50 tahun cahaya")

    def test_additional_units(self):
        self.assertEqual(self.converter.localize_measurement_units("50 mph"), "50 mil/jam")
        self.assertEqual(self.converter.localize_measurement_units("100 km/h"), "100 km/jam")
        self.assertEqual(self.converter.localize_measurement_units("10 acres"), "10 ekar")
        self.assertEqual(self.converter.localize_measurement_units("5 nautical miles"), "5 mil laut")

    def test_localize_text_snippet(self):
        self.assertEqual(
            self.converter.localize_text_snippet("$150 million (50 miles)"),
            "US$150 juta (50 mil)"
        )

    # ----------------------------------------------------
    # 3. Safeguards Tests
    # ----------------------------------------------------
    def test_safeguards_urls_and_refs(self):
        wikitext = (
            "Anggaran: $50 million, jarak 50 miles.\n"
            "URL: https://example.com/item?id=50in&val=50M\n"
            "<ref name=\"cite1\">https://example.com/ref?val=50M&dist=50mi</ref>\n"
            "[[File:Poster_50_miles_away.jpg|thumb|Poster (50 miles)]]\n"
            "<code>var dist = \"50 miles\";</code>\n"
            "<nowiki>$50 million</nowiki>"
        )
        res = self.converter.localize_currency_and_units(wikitext)
        self.assertIn("Anggaran: US$50 juta, jarak 50 mil.", res)
        self.assertIn("https://example.com/item?id=50in&val=50M", res)
        self.assertIn("<ref name=\"cite1\">https://example.com/ref?val=50M&dist=50mi</ref>", res)
        self.assertIn("[[File:Poster_50_miles_away.jpg|thumb|Poster (50 miles)]]", res)
        self.assertIn("<code>var dist = \"50 miles\";</code>", res)
        self.assertIn("<nowiki>$50 million</nowiki>", res)

    def test_default_instance(self):
        self.assertIsNotNone(default_unit_converter)
        self.assertEqual(default_unit_converter.localize_text_snippet("$50M"), "US$50 juta")


if __name__ == "__main__":
    unittest.main()
