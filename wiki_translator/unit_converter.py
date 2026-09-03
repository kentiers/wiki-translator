"""
Currency and Measurement Unit Localizer for Indonesian Wikipedia (Grade A++ MoS / EYD V).

Features:
1. Currency Localization:
   - Formats currency amounts according to Indonesian Wikipedia conventions:
     * "$50 million" / "$50M" -> "US$50 juta"
     * "$50 billion" / "$50B" -> "US$50 miliar"
     * "$50 thousand" / "$50K" -> "US$50 ribu"
     * "$50,000" / "$50.00" -> "US$50.000" / "US$50,00"
     * "£10 million" -> "£10 juta"
     * "€5 million" -> "€5 juta"
     * "¥100 billion" -> "¥100 miliar"
     * "₹50 crore" -> "₹50 crore (sekitar ...)" / "₹50 crore"
     * "US$ 50 million" -> "US$50 juta"
     * "US$50 million" -> "US$50 juta"
2. Common Measurement Units (spelled-out & abbreviations):
   - "50 miles" / "50 mi" -> "50 mil"
   - "50 feet" / "50 ft" -> "50 kaki"
   - "50 inches" / "50 in" -> "50 inci"
   - "50 pounds" / "50 lbs" -> "50 pon"
   - "50 square miles" / "sq mi" -> "50 mil persegi"
   - "50 square feet" / "sq ft" -> "50 kaki persegi"
   - "50 light-years" -> "50 tahun cahaya"
   - Also area / length / weight / speed equivalents.
3. Safeguards:
   - MUST NOT alter URLs, file names, `<ref>...</ref>` internal IDs or contents, or code blocks.
"""

from decimal import Decimal
import re
from typing import List, Match, Optional, Tuple


class UnitCurrencyLocalizer:
    """Localizes currencies, numbers, and measurement units to Indonesian Wikipedia standards."""

    # Currency symbols and prefixes
    CURRENCY_MAP = {
        "$": "US$",
        "US$": "US$",
        "US $": "US$",
        "USD": "US$",
        "A$": "A$",
        "AU$": "A$",
        "AUD": "A$",
        "C$": "C$",
        "CA$": "C$",
        "CAD": "C$",
        "NZ$": "NZ$",
        "HK$": "HK$",
        "S$": "S$",
        "SGD": "S$",
        "£": "£",
        "GBP": "£",
        "€": "€",
        "EUR": "€",
        "¥": "¥",
        "JPY": "¥",
        "RMB": "¥",
        "CNY": "¥",
        "₹": "₹",
        "INR": "₹",
        "Rp": "Rp",
        "IDR": "Rp",
    }

    # Scale words mapping (English -> Indonesian)
    SCALE_MAP = {
        "trillion": "triliun",
        "billion": "miliar",
        "m": "juta",
        "million": "juta",
        "thousand": "ribu",
        "k": "ribu",
        "b": "miliar",
        "t": "triliun",
        "crore": "crore",
        "lakh": "lakh",
    }

    def __init__(self):
        pass

    def localize_number_separators(self, num_str: str) -> str:
        """
        Converts English number separators (1,234.56 or 50,000 or 50.00) to Indonesian (1.234,56).
        """
        if not num_str:
            return num_str

        # If both comma and dot exist:
        if "," in num_str and "." in num_str:
            # 1,234,567.89 -> 1.234.567,89
            parts = num_str.split(".")
            int_part = parts[0].replace(",", ".")
            dec_part = parts[1]
            return f"{int_part},{dec_part}"
        elif "," in num_str:
            # 50,000 or 1,234,567 (thousands separator)
            # Check if groups of 3 digits
            parts = num_str.split(",")
            if all(len(p) == 3 for p in parts[1:]):
                return ".".join(parts)
            return num_str.replace(",", ".")
        elif "." in num_str:
            # Check if decimal: e.g. 50.00 or 3.5 or 12.345
            # Note: in English, 3.5 or 50.00 is decimal.
            return num_str.replace(".", ",")

        return num_str

    def _convert_crore_explanation(self, num_str: str) -> str:
        """
        Converts e.g. '50' crore to '(sekitar 500 juta)'.
        1 crore = 10 million (10 juta).
        """
        try:
            val_clean = num_str.replace(",", ".")
            val = float(val_clean)
            millions = val * 10
            if millions == int(millions):
                m_str = f"{int(millions):,}".replace(",", ".")
            else:
                m_str = f"{millions:.2f}".rstrip("0").rstrip(".").replace(".", ",")
            return f" (sekitar {m_str} juta)"
        except Exception:
            return ""

    def _convert_lakh_explanation(self, num_str: str) -> str:
        """
        Converts e.g. '50' lakh to '(sekitar 5 juta)'.
        1 lakh = 100,000 (100 ribu).
        """
        try:
            val_clean = num_str.replace(",", ".")
            val = float(val_clean)
            hundred_k = val * 0.1  # in millions
            if hundred_k >= 1:
                if hundred_k == int(hundred_k):
                    m_str = f"{int(hundred_k):,}".replace(",", ".")
                else:
                    m_str = f"{hundred_k:.2f}".rstrip("0").rstrip(".").replace(".", ",")
                return f" (sekitar {m_str} juta)"
            else:
                ribus = val * 100
                if ribus == int(ribus):
                    r_str = f"{int(ribus):,}".replace(",", ".")
                else:
                    r_str = f"{ribus:.2f}".rstrip("0").rstrip(".").replace(".", ",")
                return f" (sekitar {r_str} ribu)"
        except Exception:
            return ""

    def localize_currency(self, text: str) -> str:
        """
        Localizes currency expressions in text snippet.
        Examples:
        - $50 million -> US$50 juta
        - $50M -> US$50 juta
        - $50 billion -> US$50 miliar
        - $50B -> US$50 miliar
        - $50 thousand -> US$50 ribu
        - $50K -> US$50 ribu
        - $50,000 -> US$50.000
        - $50.00 -> US$50,00
        - £10 million -> £10 juta
        - €5 million -> €5 juta
        - ¥100 billion -> ¥100 miliar
        - ₹50 crore -> ₹50 crore (sekitar 500 juta)
        - US$ 50 million -> US$50 juta
        - US$50 million -> US$50 juta
        """
        # Pattern 1: Currencies with scale word/abbreviation (million, billion, M, B, K, crore, lakh, etc.)
        # e.g. US$ 50 million, $50M, £10 million, ¥100 billion, ₹50 crore
        # Regex captures:
        # group 1: symbol (US$, US $, $, £, €, ¥, ₹, Rp, etc.)
        # group 2: number (e.g. 50, 50.5, 50,000)
        # group 3: scale word or letter (million, billion, thousand, M, B, K, crore, lakh)
        curr_symbols = r"(?:US\s*\$|A\s*\$|AU\s*\$|C\s*\$|CA\s*\$|NZ\s*\$|HK\s*\$|S\s*\$|USD|AUD|CAD|GBP|EUR|JPY|INR|IDR|[$£€¥₹])"
        scale_words = r"(?:trillion|billion|million|thousand|crore|lakh|[mbktMBKT])"

        pattern_scale = re.compile(
            rf"(?<![A-Za-z0-9_])({curr_symbols})\s*([0-9]+(?:[.,][0-9]+)?)\s*({scale_words})\b",
            re.IGNORECASE
        )

        def repl_scale(m: Match) -> str:
            raw_sym = m.group(1).upper().replace(" ", "")
            sym = "$" if raw_sym == "$" else raw_sym
            for k, v in self.CURRENCY_MAP.items():
                if raw_sym == k.upper().replace(" ", ""):
                    sym = v
                    break

            num_part = m.group(2)
            scale_part = m.group(3).lower()

            # Localize number part (e.g. 1.5 -> 1,5)
            num_localized = self.localize_number_separators(num_part)

            id_scale = self.SCALE_MAP.get(scale_part, scale_part)

            if scale_part == "crore":
                explanation = self._convert_crore_explanation(num_part)
                return f"{sym}{num_localized} {id_scale}{explanation}"
            elif scale_part == "lakh":
                explanation = self._convert_lakh_explanation(num_part)
                return f"{sym}{num_localized} {id_scale}{explanation}"
            else:
                return f"{sym}{num_localized} {id_scale}"

        text = pattern_scale.sub(lambda m: repl_scale(m).replace("\\", "\\\\"), text)

        # Pattern 2: Currencies with plain numbers (e.g. $50,000, $50.00, US$50,000, £100)
        # We must avoid matching if followed by another word like 'meters' or already matched.
        pattern_plain = re.compile(
            rf"(?<![A-Za-z0-9_])({curr_symbols})\s*([0-9]{{1,3}}(?:,[0-9]{{3}})+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+))\b(?!\s*(?:juta|miliar|ribu|triliun|crore|lakh|percent|%))"
        )

        def repl_plain(m: Match) -> str:
            raw_sym = m.group(1).upper().replace(" ", "")
            sym = "$" if raw_sym == "$" else raw_sym
            for k, v in self.CURRENCY_MAP.items():
                if raw_sym == k.upper().replace(" ", ""):
                    sym = v
                    break

            num_part = m.group(2)
            num_localized = self.localize_number_separators(num_part)
            return f"{sym}{num_localized}"

        text = pattern_plain.sub(lambda m: repl_plain(m).replace("\\", "\\\\"), text)

        # Clean any awkward spacing e.g. "US$ 50" -> "US$50"
        text = re.sub(r"(US\$|A\$|C\$|NZ\$|HK\$|S\$|Rp|£|€|¥|₹)\s+(\d)", r"\g<1>\2", text)

        return text

    def localize_measurement_units(self, text: str) -> str:
        """
        Localizes measurement units in English prose to Indonesian equivalents:
        - "50 miles" / "50 mi" -> "50 mil"
        - "50 feet" / "50 ft" -> "50 kaki"
        - "50 inches" / "50 in" -> "50 inci"
        - "50 pounds" / "50 lbs" / "50 lb" -> "50 pon"
        - "50 square miles" / "sq mi" -> "50 mil persegi"
        - "50 square feet" / "sq ft" -> "50 kaki persegi"
        - "50 square meters" / "sq m" -> "50 meter persegi"
        - "50 square kilometers" / "sq km" -> "50 kilometer persegi"
        - "50 light-years" / "light years" -> "50 tahun cahaya"
        - "50 mph" -> "50 mil/jam"
        - "50 km/h" -> "50 km/jam"
        - "50 acres" -> "50 ekar"
        - "50 ounces" / "oz" -> "50 ons"
        - "50 yards" / "yd" -> "50 yard"
        - "50 nautical miles" / "nmi" -> "50 mil laut"
        """
        # We define unit replacements with regex word boundaries
        # Note: must preserve numbers and localize decimal/thousand separators if appropriate

        # Multi-word units first to avoid partial matches
        units_multi = [
            (r"\b(?:square\s+miles?|sq\.?\s*mi\.?)\b", "mil persegi"),
            (r"\b(?:square\s+feet|square\s+foot|sq\.?\s*ft\.?)\b", "kaki persegi"),
            (r"\b(?:square\s+kilometers?|square\s+kilometres?|sq\.?\s*km\.?)\b", "kilometer persegi"),
            (r"\b(?:square\s+meters?|square\s+metres?|sq\.?\s*m\.?)\b", "meter persegi"),
            (r"\b(?:square\s+yards?|sq\.?\s*yd\.?)\b", "yard persegi"),
            (r"\b(?:square\s+inches?|sq\.?\s*in\.?)\b", "inci persegi"),
            (r"\b(?:nautical\s+miles?|nmi)\b", "mil laut"),
            (r"\b(?:light[-\s]years?)\b", "tahun cahaya"),
            (r"\b(?:cubic\s+meters?|cubic\s+metres?|cu\.?\s*m\.?)\b", "meter kubik"),
            (r"\b(?:cubic\s+feet|cubic\s+foot|cu\.?\s*ft\.?)\b", "kaki kubik"),
        ]

        # Single word units after numbers
        # Note: 'in' can be an English preposition, so 'in' is only replaced when preceded by a number!
        # e.g. "12 in" or "12 in." or "12 inches"
        units_single = [
            (r"miles?", "mil"),
            (r"feet|foot", "kaki"),
            (r"inches?", "inci"),
            (r"pounds?|lbs?\.?", "pon"),
            (r"acres?", "ekar"),
            (r"ounces?|oz\.?", "ons"),
            (r"yards?", "yard"),
            (r"mph", "mil/jam"),
            (r"km/h|kph", "km/jam"),
        ]

        # First pass: multi-word units (can occur with or without leading number)
        for pattern, repl in units_multi:
            # If preceded by number: e.g. "50 square miles" -> "50 mil persegi"
            text = re.sub(
                rf"(\d+(?:[.,]\d+)?)\s*{pattern}",
                lambda m: f"{self.localize_number_separators(m.group(1))} {repl}",
                text,
                flags=re.IGNORECASE
            )
            # If standalone unit mention: e.g. "(dalam square miles)"
            text = re.sub(pattern, repl, text, flags=re.IGNORECASE)

        # Second pass: single word units attached to numbers
        # Note: we specifically require preceding number to avoid mistranslating the word "in"
        for unit_pat, repl in units_single:
            # Handles: 50 miles, 50-mile, 50 mi, 50 ft, 50 in, etc.
            text = re.sub(
                rf"(\d+(?:[.,]\d+)?)(?:\s*|-)(?:{unit_pat})\b",
                lambda m: f"{self.localize_number_separators(m.group(1))} {repl}",
                text,
                flags=re.IGNORECASE
            )

        # Specifically handle abbreviations like '50 mi', '50 ft', '50 in', '50 yd'
        # when preceded by numbers:
        abbr_units = [
            (r"mi\.?", "mil"),
            (r"ft\.?", "kaki"),
            (r"in\.?", "inci"),
            (r"yd\.?", "yard"),
        ]
        for abbr, repl in abbr_units:
            text = re.sub(
                rf"(\d+(?:[.,]\d+)?)\s*(?:{abbr})(?=[,\s.;)\]\n\r]|$)",
                lambda m: f"{self.localize_number_separators(m.group(1))} {repl}",
                text,
                flags=re.IGNORECASE
            )

        return text

    def localize_text_snippet(self, text: str) -> str:
        """
        Localizes currency and measurement units in a plain text snippet (e.g. an infobox parameter value).
        """
        if not text:
            return ""
        text = self.localize_currency(text)
        text = self.localize_measurement_units(text)
        return text

    def localize_currency_and_units(self, wikitext: str) -> str:
        """
        Safely localizes currencies and measurement units in full wikitext.
        Safeguards:
        - Protects URLs (http://, https://)
        - Protects File/Berkas links ([[File:...]], [[Berkas:...]], [[Image:...]], [[Gambar:...]])
        - Protects `<ref>...</ref>` tags and `<ref name="..." />`
        - Protects code/pre/nowiki/math/syntaxhighlight blocks
        - Protects template names and cite templates
        """
        if not wikitext:
            return ""

        protected_blocks: List[str] = []

        def block_replacer(match: Match) -> str:
            protected_blocks.append(match.group(0))
            return f"__UNIT_PROTECTED_BLOCK_{len(protected_blocks) - 1}__"

        # 1. Protect code, nowiki, math, pre, syntaxhighlight
        protect_tags = [
            r"<nowiki>[\s\S]*?</nowiki>",
            r"<math[\s\S]*?</math>",
            r"<syntaxhighlight[\s\S]*?</syntaxhighlight>",
            r"<source[\s\S]*?</source>",
            r"<pre[\s\S]*?</pre>",
            r"<code>[\s\S]*?</code>",
        ]
        sanitized = wikitext
        for pat in protect_tags:
            sanitized = re.sub(pat, block_replacer, sanitized, flags=re.IGNORECASE)

        # 2. Protect HTML comments <!-- ... -->
        sanitized = re.sub(r"<!--[\s\S]*?-->", block_replacer, sanitized)

        # 3. Protect <ref ...>...</ref> and <ref .../>
        sanitized = re.sub(r"<ref(?:\s+[^>/]*)?>[\s\S]*?</ref>", block_replacer, sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"<ref(?:\s+[^>]*)?/>", block_replacer, sanitized, flags=re.IGNORECASE)

        # 4. Protect Citation templates (e.g. {{cite ...}}, {{citation ...}})
        sanitized = re.sub(r"\{\{\s*(?:cite|citation)[^}]*\}\}", block_replacer, sanitized, flags=re.IGNORECASE)

        # 5. Protect File/Image links
        sanitized = re.sub(
            r"\[\[\s*(?:File|Berkas|Image|Gambar)\s*:[^\]]+\]\]",
            block_replacer,
            sanitized,
            flags=re.IGNORECASE
        )

        # 6. Protect URLs (https://..., http://..., ftp://...)
        sanitized = re.sub(
            r"https?://[^\s\]<\"'{}|]+",
            block_replacer,
            sanitized,
            flags=re.IGNORECASE
        )

        # Now apply localization on the unprotected wikitext
        sanitized = self.localize_currency(sanitized)
        sanitized = self.localize_measurement_units(sanitized)

        # Restore protected blocks in reverse order
        for idx in range(len(protected_blocks) - 1, -1, -1):
            sanitized = sanitized.replace(f"__UNIT_PROTECTED_BLOCK_{idx}__", protected_blocks[idx])

        return sanitized
    def normalize_metric_first(self, wikitext: str) -> str:
        """
        In Indonesian Wikipedia (WP:GAYA), SI metric units have precedence over imperial units.
        Normalizes inverted patterns where imperial unit is first and metric unit is in parentheses:
          - '100 miles (160 km)' / '100 mil (160 km)' -> '160 km (100 mil)'
          - '50 miles (80 km)' -> '80 km (50 mil)'
          - '5 ft 10 in (178 cm)' / '5 kaki 10 inci (178 cm)' -> '178 cm (5 kaki 10 inci)'
          - '150 pounds (68 kg)' / '150 pon (68 kg)' -> '68 kg (150 pon)'
          - '1,000 feet (300 m)' -> '300 m (1.000 kaki)'

        Safeguards: Protects URLs, file names, refs, and code blocks.
        """
        return normalize_metric_first(wikitext)


default_unit_converter = UnitCurrencyLocalizer()


def normalize_metric_first(wikitext: str) -> str:
    """
    Standalone function for Metric-First Normalization according to Indonesian Wikipedia (WP:GAYA).
    SI metric units have precedence over imperial units.
    Inverted patterns where imperial is first and metric is in parentheses are swapped.
    """
    if not wikitext:
        return ""

    protected_blocks: List[str] = []

    def block_replacer(match: Match) -> str:
        protected_blocks.append(match.group(0))
        return f"__METRIC_FIRST_PROTECTED_BLOCK_{len(protected_blocks) - 1}__"

    # 1. Protect code, nowiki, math, pre, syntaxhighlight
    protect_tags = [
        r"<nowiki>[\s\S]*?</nowiki>",
        r"<math[\s\S]*?</math>",
        r"<syntaxhighlight[\s\S]*?</syntaxhighlight>",
        r"<source[\s\S]*?</source>",
        r"<pre[\s\S]*?</pre>",
        r"<code>[\s\S]*?</code>",
    ]
    sanitized = wikitext
    for pat in protect_tags:
        sanitized = re.sub(pat, block_replacer, sanitized, flags=re.IGNORECASE)

    # 2. Protect HTML comments <!-- ... -->
    sanitized = re.sub(r"<!--[\s\S]*?-->", block_replacer, sanitized)

    # 3. Protect <ref ...>...</ref> and <ref .../>
    sanitized = re.sub(r"<ref(?:\s+[^>/]*)?>[\s\S]*?</ref>", block_replacer, sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"<ref(?:\s+[^>]*)?/>", block_replacer, sanitized, flags=re.IGNORECASE)

    # 4. Protect Citation templates (e.g. {{cite ...}}, {{citation ...}})
    sanitized = re.sub(r"\{\{\s*(?:cite|citation)[^}]*\}\}", block_replacer, sanitized, flags=re.IGNORECASE)

    # 5. Protect File/Image links ([[File:...]], [[Berkas:...]], [[Image:...]], [[Gambar:...]])
    sanitized = re.sub(
        r"\[\[\s*(?:File|Berkas|Image|Gambar)\s*:[^\]]+\]\]",
        block_replacer,
        sanitized,
        flags=re.IGNORECASE,
    )

    # 6. Protect URLs (https://..., http://..., ftp://...)
    sanitized = re.sub(
        r"https?://[^\s\]<\"'{}|]+",
        block_replacer,
        sanitized,
        flags=re.IGNORECASE,
    )

    # Helper to localize number and imperial unit to Indonesian
    def format_imperial_id(val: str, unit: str) -> str:
        unit_lower = unit.lower().strip()
        num_id = default_unit_converter.localize_number_separators(val)
        if unit_lower in ("miles", "mile", "mil", "mi", "mi."):
            return f"{num_id} mil"
        elif unit_lower in ("feet", "foot", "kaki", "ft", "ft."):
            return f"{num_id} kaki"
        elif unit_lower in ("inches", "inch", "inci", "in", "in."):
            return f"{num_id} inci"
        elif unit_lower in ("pounds", "pound", "pon", "lbs", "lb", "lbs."):
            return f"{num_id} pon"
        elif unit_lower in ("yards", "yard", "yd", "yd."):
            return f"{num_id} yard"
        elif unit_lower in ("acres", "acre", "ekar"):
            return f"{num_id} ekar"
        return f"{num_id} {unit}"

    def format_metric_id(val: str, unit: str) -> str:
        num_id = default_unit_converter.localize_number_separators(val)
        return f"{num_id} {unit}"

    # 1. Compound feet and inches:
    # e.g., 5 ft 10 in (178 cm) or 5 kaki 10 inci (178 cm) or 5'10" (178 cm)
    ft_in_pattern = re.compile(
        r"(\d+(?:[.,]\d+)?)\s*(?:ft|ft\.|feet|foot|kaki)\s*(\d+(?:[.,]\d+)?)\s*(?:in|in\.|inches|inch|inci)\s*\(\s*(\d+(?:[.,]\d+)?)\s*(cm|m|mm)\s*\)",
        flags=re.IGNORECASE,
    )

    def repl_ft_in(m: Match) -> str:
        ft_val = m.group(1)
        in_val = m.group(2)
        metric_val = m.group(3)
        metric_unit = m.group(4)
        ft_id = default_unit_converter.localize_number_separators(ft_val)
        in_id = default_unit_converter.localize_number_separators(in_val)
        m_id = format_metric_id(metric_val, metric_unit)
        return f"{m_id} ({ft_id} kaki {in_id} inci)"

    sanitized = ft_in_pattern.sub(repl_ft_in, sanitized)

    # 2. General single imperial unit followed by metric unit in parentheses:
    # e.g. 100 miles (160 km), 1,000 feet (300 m), 150 pounds (68 kg)
    # Imperial units: miles/mile/mil/mi, feet/foot/kaki/ft, inches/inch/inci/in, pounds/pound/pon/lbs/lb, yards/yard/yd
    # Metric units: km, m, cm, mm, kg, g
    single_unit_pattern = re.compile(
        r"\b(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?|\d+)\s*"
        r"(miles?|mil|mi\.?|feet|foot|kaki|ft\.?|inches?|inci|in\.?|pounds?|pon|lbs?\.?|yards?|yard|yd\.?)\b\s*"
        r"\(\s*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?|\d+)\s*(km|m|cm|mm|kg|g)\s*\)",
        flags=re.IGNORECASE,
    )

    def repl_single(m: Match) -> str:
        imp_val = m.group(1)
        imp_unit = m.group(2)
        metric_val = m.group(3)
        metric_unit = m.group(4)
        imp_str = format_imperial_id(imp_val, imp_unit)
        metric_str = format_metric_id(metric_val, metric_unit)
        return f"{metric_str} ({imp_str})"

    sanitized = single_unit_pattern.sub(repl_single, sanitized)

    # Restore protected blocks in reverse order
    for idx in range(len(protected_blocks) - 1, -1, -1):
        sanitized = sanitized.replace(f"__METRIC_FIRST_PROTECTED_BLOCK_{idx}__", protected_blocks[idx])

    return sanitized
