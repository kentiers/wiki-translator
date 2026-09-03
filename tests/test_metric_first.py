"""
Unit tests for Metric-First Normalization (wiki_translator/unit_converter.py).
"""

import unittest
from wiki_translator.unit_converter import (
    normalize_metric_first,
    default_unit_converter,
)


class TestMetricFirstNormalization(unittest.TestCase):
    def test_miles_to_km(self):
        # 100 miles (160 km) -> 160 km (100 mil)
        self.assertEqual(
            normalize_metric_first("Jaraknya sekitar 100 miles (160 km)."),
            "Jaraknya sekitar 160 km (100 mil)."
        )
        self.assertEqual(
            normalize_metric_first("Jaraknya sekitar 100 mil (160 km)."),
            "Jaraknya sekitar 160 km (100 mil)."
        )
        self.assertEqual(
            normalize_metric_first("50 miles (80 km)"),
            "80 km (50 mil)"
        )

    def test_feet_and_inches(self):
        # 5 ft 10 in (178 cm) / 5 kaki 10 inci (178 cm) -> 178 cm (5 kaki 10 inci)
        self.assertEqual(
            normalize_metric_first("Tingginya 5 ft 10 in (178 cm)."),
            "Tingginya 178 cm (5 kaki 10 inci)."
        )
        self.assertEqual(
            normalize_metric_first("Tingginya 5 kaki 10 inci (178 cm)."),
            "Tingginya 178 cm (5 kaki 10 inci)."
        )

    def test_pounds_to_kg(self):
        # 150 pounds (68 kg) / 150 pon (68 kg) -> 68 kg (150 pon)
        self.assertEqual(
            normalize_metric_first("Beratnya 150 pounds (68 kg)."),
            "Beratnya 68 kg (150 pon)."
        )
        self.assertEqual(
            normalize_metric_first("Beratnya 150 pon (68 kg)."),
            "Beratnya 68 kg (150 pon)."
        )

    def test_thousands_formatting(self):
        # 1,000 feet (300 m) -> 300 m (1.000 kaki)
        self.assertEqual(
            normalize_metric_first("Ketinggian 1,000 feet (300 m)."),
            "Ketinggian 300 m (1.000 kaki)."
        )

    def test_safeguards(self):
        # URLs
        url_text = "Lihat https://example.com/item/100-miles-(160-km) untuk info."
        self.assertEqual(normalize_metric_first(url_text), url_text)

        # File names
        file_text = "[[Berkas:Map of 50 miles (80 km) radius.png|thumb|Peta]]"
        self.assertEqual(normalize_metric_first(file_text), file_text)

        # Code blocks
        code_text = "<code>100 miles (160 km)</code>"
        self.assertEqual(normalize_metric_first(code_text), code_text)

        # Refs
        ref_text = "Teks<ref>Sumber: 100 miles (160 km) data</ref>"
        self.assertEqual(normalize_metric_first(ref_text), ref_text)

    def test_method_on_class_instance(self):
        self.assertEqual(
            default_unit_converter.normalize_metric_first("50 miles (80 km)"),
            "80 km (50 mil)"
        )


if __name__ == "__main__":
    unittest.main()
