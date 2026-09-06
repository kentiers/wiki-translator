"""
Typography and Reference Date Sanitizer for Indonesian Wikipedia (Grade A++ MoS / EYD V).

Implements the 3 Pillars of Wikipedia ID Typography & Reference Date Standardization:
1. Pillar 1: Typography & Orthography Linter:
   - En-dash conversion: converts hyphens '-' in year/page/number ranges to en-dash '–' (e.g. 1939-1945 -> 1939–1945, hlm. 45-50 -> 45–50).
   - Quotation mark normalization: changes curly quotes to standard straight quotes.
   - Decimal & thousand separator consistency in Indonesian prose without breaking math/code/urls.
2. Pillar 2: Citation Date Localizer (cite web, cite journal, cite book, cite news, etc.):
   - Translates English month names inside |date=, |access-date=, |archive-date= to Indonesian month names.
   - Converts English order (e.g. November 11, 2024 / Nov 11, 2024) to Indonesian D M Y order (11 November 2024).
3. Pillar 3: Heading Sentence-Case Normalizer (EYD V & Wikipedia ID MoS):
   - Normalizes section headings to sentence case (e.g. == Produksi Dan Perilisan == -> == Produksi dan perilisan ==).
   - Lowercases standard Indonesian prepositions and conjunctions in headings.
"""

import re
from typing import Dict, List, Optional, Tuple, Set
from .awb_genfixes import default_genfixes
from .slop_linter import default_slop_linter


ENGLISH_TO_INDONESIAN_MONTHS: Dict[str, str] = {
    "january": "Januari",
    "february": "Februari",
    "march": "Maret",
    "april": "April",
    "may": "Mei",
    "june": "Juni",
    "july": "Juli",
    "august": "Agustus",
    "september": "September",
    "october": "Oktober",
    "november": "November",
    "december": "Desember",
    # Short variants
    "jan": "Januari",
    "feb": "Februari",
    "mar": "Maret",
    "apr": "April",
    "jun": "Juni",
    "jul": "Juli",
    "aug": "Agustus",
    "sep": "September",
    "sept": "September",
    "oct": "Oktober",
    "nov": "November",
    "dec": "Desember",
}

# Indonesian lowercase words in headings (prepositions, conjunctions, particles)
LOWERCASE_HEADING_WORDS: Set[str] = {
    "dan",
    "di",
    "ke",
    "dari",
    "pada",
    "untuk",
    "tentang",
    "yang",
    "atau",
    "sebagai",
    "dengan",
    "terhadap",
    "dalam",
    "oleh",
    "atas",
    "bagi",
    "sampai",
    "hingga",
    "secara",
    "serta",
    "maupun",
    "antara",
}

# Known proper names / historic events / geographic / entities in Indonesian headings that must preserve Capitalization
KNOWN_PROPER_NOUNS: Set[str] = {
    "indonesia",
    "jawa",
    "sumatra",
    "sumatera",
    "kalimantan",
    "sulawesi",
    "papua",
    "bali",
    "jakarta",
    "eropa",
    "asia",
    "amerika",
    "afrika",
    "australia",
    "inggris",
    "pasifik",
    "atlantik",
    "blu-ray",
    "perang",
    "dunia",
}


class TypographySanitizer:
    """Standardizes typography, citation dates, and heading casing for Indonesian Wikipedia articles."""

    def __init__(self):
        pass

    def sanitize_wikitext(self, text: str) -> str:
        """Normalize explicit formatting while protecting markup and quotations."""
        normalized = self._sanitize_prose(text)
        return default_genfixes.apply_all_fixes(normalized)

    def sanitize_markdown(self, text: str) -> str:
        return self._sanitize_prose(text)

    def _sanitize_prose(self, text: str) -> str:
        if not text:
            return ""
        text = self.localize_citation_dates(text)
        text = self.normalize_headings(text)
        masked, protected = default_slop_linter._mask_protected_zones(text)
        masked = self.normalize_en_dashes(masked)
        masked = self.normalize_em_dashes(masked)
        masked = self.normalize_number_separators(masked)
        masked = self.normalize_semicolons(masked)
        return default_slop_linter._unmask_protected_zones(masked, protected)
    # ==========================================
    # Pillar 1: Typography & Orthography Linter
    # ==========================================

    def normalize_quotations(self, text: str) -> str:
        """Normalizes curly quotation marks to standard straight quotes."""
        text = text.replace("“", '"').replace("”", '"').replace("„", '"')
        text = text.replace("«", '"').replace("»", '"')
        text = text.replace("‘", "'").replace("’", "'")
        return text

    def fix_quotation_punctuation_order(self, text: str) -> str:
        """
        Fixes quotation mark punctuation order according to Indonesian EYD V.
        In Indonesian (unlike American English), punctuation belongs outside quotes
        when the quoted text is not a direct full sentence:
        - ',"' -> '",'
        - '."' -> '".'
        - ",''" -> "'',"
        - ".''" -> "''.'"
        """
        # Straight double quotes: ," -> ", and ." -> ".
        text = re.sub(r',"', '",', text)
        text = re.sub(r'\."', '".', text)
        # Wikitext italics quotes: ,'' -> '', and .'' -> ''.
        text = re.sub(r",''", "'',", text)
        text = re.sub(r"\.''", "''.", text)
        return text

    def normalize_em_dashes(self, text: str) -> str:
        """
        Converts em-dashes '—' (U+2014) or '--' in narrative prose to commas, periods, or en-dashes.
        - Parenthetical clause: 'kata — penjelasan — kata' -> 'kata, penjelasan, kata'
        - Clause-connecting em-dash: 'klausa — klausa' -> 'klausa, klausa' or 'klausa. Klausa'
        - Bullet item description: '* [[Link]] — Keterangan' -> '* [[Link]] – Keterangan'
        - Preserves quote attributions: '| source = — Tokoh' or '— Penulis'
        """
        # 1. Protect quote attributions (e.g. | source = — ...)
        attributions = {}
        def hide_attr(m: re.Match) -> str:
            key = f"⟦ATTR_{len(attributions)}⟧"
            attributions[key] = m.group(0)
            return key

        text = re.sub(r"(?:\|\s*source\s*=\s*—\s*[^|\n}]+|\|\s*—\s*[^|\n}]+)", hide_attr, text, flags=re.IGNORECASE)

        # 2. Bullet list separator: * [[X]] — Y -> * [[X]] – Y (en-dash with space)
        text = re.sub(r"^(\s*\*+\s*\[\[[^\]]+\]\]\s*)—\s*", r"\1– ", text, flags=re.MULTILINE)

        # 3. Parenthetical em-dash pair: " — ... — " or "—...—"
        def parenthetical_replacer(m: re.Match) -> str:
            content = m.group(1).strip()
            return f", {content}, "

        text = re.sub(r"\s*(?:—|--)\s*([^—\n]+?)\s*(?:—|--)\s*", parenthetical_replacer, text)

        # 4. Standalone em-dash connecting clauses: "kata — kata" -> "kata, kata"
        text = re.sub(r"\s*(?:—|--)\s*", ", ", text)
        # Clean up any accidental double commas
        text = re.sub(r",\s*,+", ",", text)

        # Restore attributions
        for key, val in attributions.items():
            text = text.replace(key, val)

        return text

    def normalize_semicolons(self, text: str) -> str:
        """
        Converts semicolons (';') in narrative prose.
        Indonesian encyclopedic prose avoids semicolons; uses ', dan ' or splits sentences.
        Must not touch semicolons inside HTML entities (&nbsp;, &#123;).
        """
        # Semicolons followed by lowercase letter or conjunction
        text = re.sub(r";\s*(dan|tetapi|namun|sementara|melainkan)\b", r", \1", text, flags=re.IGNORECASE)
        # Semicolons followed by space and lowercase letter -> ", dan "
        text = re.sub(r";\s*([a-z])", r", dan \1", text)
        # Semicolons followed by space and uppercase letter -> ". "
        text = re.sub(r";\s*([A-Z])", r". \1", text)
        # Any remaining semicolons with space -> ", "
        text = re.sub(r";\s+", ", ", text)
        # Standalone semicolon at end of line/sentence
        text = re.sub(r";$", ".", text, flags=re.MULTILINE)
        return text

    def normalize_compound_hyphens(self, text: str) -> str:
        """
        Normalizes unnatural English compound hyphens to natural Indonesian expressions.
        E.g.:
        - 'pro-Palestina' -> 'pendukung Palestina' (or 'protes pro-Palestina' -> 'protes membela Palestina')
        - 'pengunjuk rasa pro-Palestina' -> 'pengunjuk rasa pendukung Palestina'
        - 'aktivis pro-Palestina' -> 'aktivis pendukung Palestina'
        - 'kelompok pro-Palestina' -> 'kelompok pendukung Palestina'
        - 'pro-[Negara/Entitas]' -> 'pendukung [Negara/Entitas]' when acting as adjective
        - Prefixes (pasca, antar, multi, sub, pra, non) before lowercase words joined without hyphen:
          pasca-sarjana -> pascasarjana, non-blok -> nonblok, multi-nasional -> multinasional
        """
        # 1. Protests/activists/demonstrators/supporters pro-[Entitas]
        text = re.sub(
            r"\b(pengunjuk\s+rasa|pendemo|demonstran|aktivis|kelompok|gerakan|organisasi)\s+pro-([A-Z][a-zA-Z]+)\b",
            r"\1 pendukung \2",
            text,
            flags=re.IGNORECASE,
        )

        # 2. General "pro-Palestina" -> "pendukung Palestina"
        def pro_entity_replacer(m: re.Match) -> str:
            entity = m.group(1)
            return f"pendukung {entity}"

        text = re.sub(r"\bpro-Palestina\b", "pendukung Palestina", text, flags=re.IGNORECASE)
        text = re.sub(r"\bpro-([A-Z][a-z]+)\b", pro_entity_replacer, text)

        # 3. Bound forms (bentuk terikat serapan: pasca, antar, multi, sub, pra, non, infra, ekstra)
        # before lowercase letters WAJIB digabung tanpa tanda hubung
        def bound_form_replacer(m: re.Match) -> str:
            prefix = m.group(1).lower()
            base = m.group(2)
            return f"{prefix}{base}"

        bound_prefixes = r"(pasca|antar|multi|sub|pra|non|infra|ekstra|ultra|semi|makro|mikro)"
        text = re.sub(
            rf"\b{bound_prefixes}-([a-z]+)\b",
            bound_form_replacer,
            text,
            flags=re.IGNORECASE,
        )
        return text
    def normalize_en_dashes(self, text: str) -> str:
        """Converts hyphens '-' to en-dash '–' (U+2013) in year, page, and numerical ranges."""
        # 1. Page ranges: hlm. 45-50, hal. 12-18, hlm. 123-145, pp. 20-30, p. 5-9
        def page_range_replacer(m: re.Match) -> str:
            prefix = m.group(1)
            p1 = m.group(2)
            p2 = m.group(3)
            return f"{prefix}{p1}–{p2}"

        text = re.sub(
            r"\b(hlm\.\s*|hal\.\s*|pp\.\s*|p\.\s*)(\d+)\s*-\s*(\d+)\b",
            page_range_replacer,
            text,
            flags=re.IGNORECASE,
        )

        # 2. Inside citation parameters like |page=45-50 or |pages=45-50
        def cite_page_replacer(m: re.Match) -> str:
            param = m.group(1)
            p1 = m.group(2)
            p2 = m.group(3)
            return f"{param}{p1}–{p2}"

        text = re.sub(
            r"(\|\s*(?:page|pages|halaman|hlm)\s*=\s*)(\d+)\s*-\s*(\d+)",
            cite_page_replacer,
            text,
            flags=re.IGNORECASE,
        )

        # 3. Year ranges: e.g. 1939-1945, 2001-2005, 1850-1890, 1990-an -> keep -an as hyphen (1990-an)
        def year_range_replacer(m: re.Match) -> str:
            y1 = m.group(1)
            y2 = m.group(2)
            return f"{y1}–{y2}"

        text = re.sub(
            r"(?<![-\d/])(\b\d{3,4})\s*-\s*(\d{3,4}\b)(?!\s*-\s*\d{1,2})(?!-an\b)",
            year_range_replacer,
            text,
        )

        # 4. Short year ranges: e.g. 2023-24, 1998-99, 1914-18
        def short_year_replacer(m: re.Match) -> str:
            y1 = m.group(1)
            y2 = m.group(2)
            if len(y1) == 4 and len(y2) == 2:
                return f"{y1}–{y2}"
            return m.group(0)

        text = re.sub(
            r"(?<![-\d/])(\b\d{4})\s*-\s*(\d{2}\b)(?!\s*-\s*\d{1,2})(?!-an\b)",
            short_year_replacer,
            text,
        )

        # 5. General number ranges with words like "antara X-Y" or "sebesar X-Y"
        def context_range_replacer(m: re.Match) -> str:
            prefix = m.group(1)
            n1 = m.group(2)
            n2 = m.group(3)
            return f"{prefix}{n1}–{n2}"

        text = re.sub(
            r"\b(antara|sekitar|berkisar|sebanyak|sebesar|sejumlah)\s+(\d+)\s*-\s*(\d+)\b",
            context_range_replacer,
            text,
            flags=re.IGNORECASE,
        )

        return text

    def normalize_number_separators(self, text: str) -> str:
        """
        Normalizes decimal & thousand separators in Indonesian prose.
        In Indonesian (EYD):
        - Decimal separator: comma (,) (e.g. 3,14; 2,5 juta; US$ 4,5 miliar; 15,8%)
        - Thousand separator: period (.) (e.g. 1.000, 25.000, 1.500.000)
        Must NOT corrupt math formulas, URLs, ISO dates (2024-05-12), image dimensions (800x600), or template parameters.
        """
        # 1. Decimal with % or percentage / words
        def decimal_percent_replacer(m: re.Match) -> str:
            int_part = m.group(1)
            dec_part = m.group(2)
            suffix = m.group(3)
            return f"{int_part},{dec_part}{suffix}"

        text = re.sub(
            r"\b(\d+)\.(\d+)(%)",
            decimal_percent_replacer,
            text,
        )

        # 2. Decimal with units: "3.5 juta", "12.8 miliar", "0.5 triliun", "15.4 persen"
        def decimal_unit_replacer(m: re.Match) -> str:
            int_part = m.group(1)
            dec_part = m.group(2)
            unit = m.group(3)
            return f"{int_part},{dec_part}{unit}"

        text = re.sub(
            r"\b(\d+)\.(\d+)(\s+(?:juta|miliar|triliun|biliun|persen))\b",
            decimal_unit_replacer,
            text,
            flags=re.IGNORECASE,
        )

        # 3. Currency with decimal: e.g. "US$ 4.5" -> "US$ 4,5", "$ 10.5" -> "$ 10,5", "Rp 12.5" -> "Rp 12,5"
        def currency_decimal_replacer(m: re.Match) -> str:
            curr = m.group(1)
            int_part = m.group(2)
            dec_part = m.group(3)
            return f"{curr}{int_part},{dec_part}"

        text = re.sub(
            r"\b(US\$|Rp|\$|€|£)\s*(\d+)\.(\d+)(?=\s+(?:juta|miliar|triliun|ribu|dolar|rupiah|\b))",
            currency_decimal_replacer,
            text,
            flags=re.IGNORECASE,
        )

        return text

    # ==========================================
    # Pillar 2: Citation Date Localizer
    # ==========================================

    def localize_citation_dates(self, text: str) -> str:
        """
        Localizes citation date formats inside citation templates (|date=, |access-date=, |archive-date=).
        E.g.:
        - November 11, 2024 -> 11 November 2024
        - Nov 11, 2024 -> 11 November 2024
        - 11 November 2024 -> 11 November 2024
        - November 2024 -> November 2024
        """
        # Regex for citation parameters
        date_param_pattern = r"(\|\s*(?:date|access-date|accessdate|archive-date|archivedate|publication-date|air-date|airdate)\s*=\s*)([^|}\n]+)"

        def date_field_replacer(m: re.Match) -> str:
            param_prefix = m.group(1)
            raw_val = m.group(2)
            clean_val = raw_val.strip()

            converted_val = self._convert_date_string(clean_val)
            trailing = ""
            if raw_val.endswith(" "):
                trailing = " "
            return f"{param_prefix}{converted_val}{trailing}"

        return re.sub(date_param_pattern, date_field_replacer, text, flags=re.IGNORECASE)

    def _convert_date_string(self, date_str: str) -> str:
        """Converts an English date string into Indonesian format."""
        if not date_str:
            return ""

        # Leave ISO dates (YYYY-MM-DD) untouched
        if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            return date_str

        # Pattern 1: Month DD, YYYY (e.g. November 11, 2024 or Nov 11, 2024 or November 11 2024)
        m1 = re.match(
            r"^([a-zA-Z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})$",
            date_str,
            flags=re.IGNORECASE,
        )
        if m1:
            month_name = m1.group(1).lower()
            day = str(int(m1.group(2)))
            year = m1.group(3)
            id_month = ENGLISH_TO_INDONESIAN_MONTHS.get(month_name, m1.group(1).capitalize())
            return f"{day} {id_month} {year}"

        # Pattern 2: DD Month YYYY (e.g. 11 November 2024, 11th November 2024, 11 Nov 2024, 11 March 2024)
        m2 = re.match(
            r"^(\d{1,2})(?:st|nd|rd|th)?\s+([a-zA-Z]+),?\s+(\d{4})$",
            date_str,
            flags=re.IGNORECASE,
        )
        if m2:
            day = str(int(m2.group(1)))
            month_name = m2.group(2).lower()
            year = m2.group(3)
            id_month = ENGLISH_TO_INDONESIAN_MONTHS.get(month_name, m2.group(2).capitalize())
            return f"{day} {id_month} {year}"

        # Pattern 3: Month YYYY (e.g. November 2024, March 2024)
        m3 = re.match(
            r"^([a-zA-Z]+)\s+(\d{4})$",
            date_str,
            flags=re.IGNORECASE,
        )
        if m3:
            month_name = m3.group(1).lower()
            year = m3.group(2)
            id_month = ENGLISH_TO_INDONESIAN_MONTHS.get(month_name, m3.group(1).capitalize())
            return f"{id_month} {year}"

        # Pattern 4: Month DD (e.g. November 11)
        m4 = re.match(
            r"^([a-zA-Z]+)\s+(\d{1,2})(?:st|nd|rd|th)?$",
            date_str,
            flags=re.IGNORECASE,
        )
        if m4:
            month_name = m4.group(1).lower()
            day = str(int(m4.group(2)))
            id_month = ENGLISH_TO_INDONESIAN_MONTHS.get(month_name, m4.group(1).capitalize())
            return f"{day} {id_month}"

        # Pattern 5: DD Month (e.g. 11 November, 11 March)
        m5 = re.match(
            r"^(\d{1,2})(?:st|nd|rd|th)?\s+([a-zA-Z]+)$",
            date_str,
            flags=re.IGNORECASE,
        )
        if m5:
            day = str(int(m5.group(1)))
            month_name = m5.group(2).lower()
            id_month = ENGLISH_TO_INDONESIAN_MONTHS.get(month_name, m5.group(2).capitalize())
            return f"{day} {id_month}"

        # Fallback word-by-word replacement for English months
        result = date_str
        for en_m, id_m in ENGLISH_TO_INDONESIAN_MONTHS.items():
            result = re.sub(rf"\b{en_m}\b", id_m, result, flags=re.IGNORECASE)

        return result

    # ==========================================
    # Pillar 3: Heading Sentence-Case Normalizer
    # ==========================================

    def normalize_headings(self, text: str) -> str:
        """
        Normalizes section headings to Sentence case according to Wikipedia ID MoS and EYD V.
        E.g.
        == Produksi Dan Perilisan == -> == Produksi dan perilisan ==
        === Pemeran Dan Karakter === -> === Pemeran dan karakter ===
        == Tanggapan Kritis == -> == Tanggapan kritis ==
        ## Produksi Dan Perilisan -> ## Produksi dan perilisan
        """
        lines = text.split("\n")
        normalized_lines = []

        for line in lines:
            # Check Wikitext heading: == Title == or === Title === etc.
            wiki_heading_match = re.match(r"^(={1,6})\s*(.*?)\s*(={1,6})$", line)
            if wiki_heading_match:
                prefix = wiki_heading_match.group(1)
                title = wiki_heading_match.group(2)
                suffix = wiki_heading_match.group(3)
                norm_title = self._to_sentence_case_heading(title)
                normalized_lines.append(f"{prefix} {norm_title} {suffix}")
                continue

            # Check Markdown heading: # Title or ## Title etc.
            md_heading_match = re.match(r"^(#{1,6})\s+(.*?)$", line)
            if md_heading_match:
                prefix = md_heading_match.group(1)
                title = md_heading_match.group(2)
                norm_title = self._to_sentence_case_heading(title)
                normalized_lines.append(f"{prefix} {norm_title}")
                continue

            normalized_lines.append(line)

        return "\n".join(normalized_lines)

    def _to_sentence_case_heading(self, heading: str) -> str:
        """
        Converts a heading title to Indonesian sentence case.
        - First letter of the heading is capitalized.
        - Prepositions, conjunctions, and general words are lowercased unless they are acronyms, proper nouns, or Roman numerals.
        """
        if not heading:
            return ""

        # Hyphenated compound token splitter or space splitter
        tokens = re.split(r"(\s+|[/\–—])", heading)
        words: List[str] = []
        is_first_word = True

        for token in tokens:
            if not token or re.match(r"^(\s+|[/\–—])$", token):
                words.append(token)
                continue

            # Check if word is enclosed in wikilink [[...]]
            if token.startswith("[[") and token.endswith("]]"):
                words.append(token)
                is_first_word = False
                continue

            # Handle hyphenated tokens e.g. Blu-Ray or Blu-ray or undang-undang
            if "-" in token:
                lower_token = token.lower()
                if lower_token == "blu-ray":
                    words.append("Blu-ray")
                    is_first_word = False
                    continue
                subparts = token.split("-")
                sub_norm = []
                for idx, sub in enumerate(subparts):
                    lower_sub = sub.lower()
                    if lower_sub in KNOWN_PROPER_NOUNS:
                        sub_norm.append(sub.capitalize())
                    elif sub.isupper() and len(sub) > 1:
                        sub_norm.append(sub)
                    elif is_first_word and idx == 0:
                        sub_norm.append(sub.capitalize())
                    else:
                        sub_norm.append(lower_sub)
                words.append("-".join(sub_norm))
                is_first_word = False
                continue

            # Check for acronyms (e.g. NASA, AS, TV, CGI, MCU, EYD, DVD)
            if token.isupper() and len(token) > 1:
                words.append(token)
                is_first_word = False
                continue

            # Check for Roman numerals (I, II, III, IV, V, VI, VII, VIII, IX, X, etc.)
            if re.match(r"^(?:[IVXLCDM]+)$", token, flags=re.IGNORECASE) and token.isupper():
                words.append(token)
                is_first_word = False
                continue

            lower_word = token.lower()

            # Check known proper nouns
            if lower_word in KNOWN_PROPER_NOUNS:
                words.append(token.capitalize())
                is_first_word = False
                continue

            if is_first_word:
                # Capitalize first word
                words.append(token.capitalize())
                is_first_word = False
            else:
                # Lowercase standard words & prepositions/conjunctions
                words.append(lower_word)

        return "".join(words)


default_typography_sanitizer = TypographySanitizer()
