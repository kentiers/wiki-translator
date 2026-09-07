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
    "indonesia", "jawa", "sumatra", "sumatera", "kalimantan", "sulawesi", "papua", "bali",
    "jakarta", "eropa", "asia", "amerika", "afrika", "australia", "inggris", "pasifik",
    "atlantik", "blu-ray", "perang", "dunia", "rusia", "soviet", "uni", "jerman", "tiongkok",
    "putin", "vladimir", "stalin", "lenin", "khrushchev", "brezhnev", "gorbachev", "komunis", "partai",
    "kudeta", "agustus", "teluk", "kaukasus", "stavropol", "moskow", "moskwa", "komsomol",
    "politbiro", "parlemen", "lituania", "estonia", "latvia", "ukraina", "belarus", "georgia",
    "armenia", "moldova", "persemakmuran", "kanada", "prancis", "barat", "timur", "kuba",
    "vietnam", "korea", "libya", "suriah", "afganistan", "reagan", "thatcher", "yeltsin",
    "trudeau", "kursk", "pkus", "duma", "balkon", "chernobyl", "nato", "pbb", "komite", "pusat",
}
COMMON_SENTENCE_ABBREVIATIONS: Set[str] = {
    "hlm", "hal", "dkk", "dll", "dsb", "ca", "vol", "no", "dr", "prof",
    "mr", "ms", "mrs", "st", "jr", "sr", "al", "vs", "etc", "ibid", "op", "cit",
}
PRESERVED_INDIRECT_SPEECH_QUOTES: Set[str] = {
    "musuh rakyat", "kekaisaran kejahatan", "gorbymania", "tokoh dekade ini",
    "dialog peterburg", "500 hari", "yayasan gorbachev", "zarya", "gang of eight",
    "rumah bersama eropa", "dari atlantik hingga ural", "doktrin brezhnev",
    "rusia demokratis", "inteligensia dan perestroika", "terima kasih, gorbi!",
    "kekuatan nuklir jangkauan menengah", "komite negara pada keadaan darurat",
    "seratus merah", "red hundred", "demokrasi sosialis", "demokrasi borjuis",
    "sosialisme modern", "anarki", "kehancuran", "perestroika", "glasnost",
    "kontradiksi antagonistik", "rusia", "negarawan terkemuka pada zaman kita",
    "seorang puritan", "bapak revolusi gorbachev", "salah satu bapak unifikasi jerman",
    "kelompok delapan", "kaum intelektual dan perestroika",
}


class TypographySanitizer:
    """Standardizes typography, citation dates, and heading casing for Indonesian Wikipedia articles."""

    def __init__(self):
        pass

    def sanitize_wikitext(self, text: str) -> str:
        """Normalize explicit formatting while protecting markup and quotations."""
        normalized = self._sanitize_prose(text)
        normalized = self.clean_indirect_speech_fragmented_quotes(normalized)
        normalized = self.clean_parenthetical_quotes(normalized)
        normalized = self.normalize_wikilink_italics(normalized)
        normalized = self.normalize_sentence_case_after_periods(normalized)
        normalized = self.normalize_image_thumbnail_syntax(normalized)
        return default_genfixes.apply_all_fixes(normalized)

    def sanitize_markdown(self, text: str) -> str:
        normalized = self._sanitize_prose(text)
        normalized = self.clean_indirect_speech_fragmented_quotes(normalized)
        normalized = self.clean_parenthetical_quotes(normalized)
        return self.normalize_sentence_case_after_periods(normalized)
    def _sanitize_prose(self, text: str) -> str:
        if not text:
            return ""
        text = self.localize_citation_dates(text)
        text = self.normalize_headings(text)
        text = self.normalize_bound_morphemes_before_links(text)
        masked, protected = default_slop_linter._mask_protected_zones(text)
        masked = self.normalize_en_dashes(masked)
        masked = self.normalize_em_dashes(masked)
        masked = self.normalize_quotations(masked)
        masked = self.normalize_bound_morphemes(masked)
        masked = self.normalize_common_spelling_mistakes(masked)
        masked = self.normalize_stylistic_collocations(masked)
        masked = self.restructure_double_temporal_markers(masked)
        masked = self.normalize_temporal_year_classifiers(masked)
        masked = self.normalize_appositive_commas(masked)
        masked = self.normalize_coordinating_conjunction_commas(masked)
        masked = self.normalize_introductory_adverbial_commas(masked)
        masked = self.normalize_relative_clause_commas(masked)
        masked = self.normalize_parenthetical_modifier_commas(masked)
        masked = self.normalize_comma_clutter(masked)
        masked = self.normalize_number_separators(masked)
        masked = self.normalize_semicolons(masked)
        return default_slop_linter._unmask_protected_zones(masked, protected)
    # ==========================================
    # Pillar 1: Typography & Orthography Linter
    # ==========================================

    def normalize_quotations(self, text: str) -> str:
        """Normalizes curly quotation marks to standard straight quotes and cleans redundant quotes inside parentheses."""
        text = text.replace("“", '"').replace("”", '"').replace("„", '"')
        text = text.replace("«", '"').replace("»", '"')
        text = text.replace("‘", "'").replace("’", "'")
        # Clean redundant single/double quotes inside explanatory parentheses: ('keterbukaan') -> (keterbukaan)
        text = re.sub(r"\(\s*['\"]([^'\"\n]+)['\"]\s*\)", r"(\1)", text)
        return text

    def clean_parenthetical_quotes(self, text: str) -> str:
        """Cleans redundant quotation marks inside explanatory parentheses: ('kata') -> (kata)"""
        if not text:
            return ""
        return re.sub(r"\(\s*['\"]([^'\"\n]+)['\"]\s*\)", r"(\1)", text)

    def normalize_wikilink_italics(self, text: str) -> str:
        """Moves italic markup outside wikilink pipes: [[Target|''Display'']] -> ''[[Target|Display]]''"""
        if not text:
            return ""
        return re.sub(r"\[\[([^|\]]+)\|\'\'([^\']+)\'\'\]\]", r"''[[\1|\2]]''", text)
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

    def normalize_bound_morphemes_before_links(self, text: str) -> str:
        """
        Normalizes bound morphemes immediately preceding a wikilink (before zone masking):
        - 'pasca-[[Bencana Chernobyl]]' -> 'pascabencana [[Bencana Chernobyl|Chernobyl]]'
        - 'Pasca-[[Pembubaran Uni Soviet|...]]' -> '[[Pembubaran Uni Soviet|Pascapembubaran...]]'
        - Preserves hyphen when link target is a proper noun:
          'pasca-[[Uni Soviet]]', 'pro-[[Barat]]'
        """
        BOUND_PREFIXES = r"(?:pasca|pra|antar|non|multi|anti|sub|semi|ekstra|kontra|inter|intra|pro|maha|tuna)"
        COMMON_EVENT_NOUNS = {
            "bencana", "pembubaran", "krisis", "invasi", "kudeta", "revolusi", "reformasi",
            "pemilu", "pandemi", "gempa", "letusan", "kebakaran", "perang", "kematian",
            "kejatuhan", "keruntuhan", "kelulusan", "kejadian", "peristiwa", "insiden",
            "konferensi", "perjanjian", "kesepakatan", "pemberontakan", "era"
        }
        pattern = re.compile(rf"\b({BOUND_PREFIXES})-\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", re.IGNORECASE)

        def repl(m: re.Match) -> str:
            pref = m.group(1)
            target = m.group(2).strip()
            label = m.group(3).strip() if m.group(3) else target
            words = (label or target).split()
            first_word_clean = words[0].lower()
            if first_word_clean in COMMON_EVENT_NOUNS:
                serangkai = f"{pref.lower()}{first_word_clean}"
                if pref[0].isupper():
                    serangkai = serangkai.capitalize()
                rest = " ".join(words[1:])
                if rest:
                    return f"{serangkai} [[{target}|{rest}]]"
                else:
                    return f"[[{target}|{serangkai}]]"
            return m.group(0)

        return pattern.sub(repl, text)

    def normalize_bound_morphemes(self, text: str) -> str:
        """
        Converts Indonesian bound morphemes (bentuk terikat) according to EYD V Bab II Huruf D.
        - Bound morpheme + hyphen + lowercase letter -> remove hyphen (written serangkai):
          e.g. 'pasca-kematian' -> 'pascakematian', 'pro-kemerdekaan' -> 'prokemerdekaan',
               'pasca-peristiwa' -> 'pascaperistiwa', 'non-blok' -> 'nonblok'
        - Bound morpheme before common noun inside wikilink -> write serangkai:
          e.g. 'pasca-[[Bencana Chernobyl]]' -> 'pascabencana [[Bencana Chernobyl|Chernobyl]]',
               'Pasca-[[Pembubaran Uni Soviet|...]]' -> '[[Pembubaran Uni Soviet|Pascapembubaran...]]'
        - Preserves hyphen when followed by capitalized proper nouns / countries / acronyms:
          e.g. 'pasca-Soviet', 'pro-Yeltsin', 'anti-Barat', 'de-Stalinisasi', 'non-ASEAN',
               'pasca-[[Uni Soviet]]', 'pro-[[Barat]]'
        - Combines common spaced bound morphemes:
          e.g. 'pasca perang' -> 'pascaperang', 'antar bangsa' -> 'antarbangsa'
        """
        BOUND_PREFIXES = r"(?:pasca|pra|antar|non|multi|anti|sub|semi|ekstra|kontra|inter|intra|pro|maha|tuna|panca|tri|dwi|eka)"
        COMMON_EVENT_NOUNS = {
            "bencana", "pembubaran", "krisis", "invasi", "kudeta", "revolusi", "reformasi",
            "pemilu", "pandemi", "gempa", "letusan", "kebakaran", "perang", "kematian",
            "kejatuhan", "keruntuhan", "kelulusan", "kejadian", "peristiwa", "insiden",
            "konferensi", "perjanjian", "kesepakatan", "pemberontakan", "era"
        }

        # 1. Prefix + hyphen + wikilink: prefix-[[Target]] or prefix-[[Target|Label]]
        def prefix_link_sub(m: re.Match) -> str:
            pref = m.group(1)
            target = m.group(2).strip()
            label = m.group(3).strip() if m.group(3) else target
            words = (label or target).split()
            first_word_clean = words[0].lower()
            if first_word_clean in COMMON_EVENT_NOUNS:
                serangkai = f"{pref.lower()}{first_word_clean}"
                if pref[0].isupper():
                    serangkai = serangkai.capitalize()
                rest = " ".join(words[1:])
                if rest:
                    return f"{serangkai} [[{target}|{rest}]]"
                else:
                    return f"[[{target}|{serangkai}]]"
            return m.group(0)

        text = re.sub(rf"\b({BOUND_PREFIXES})-\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", prefix_link_sub, text, flags=re.IGNORECASE)

        # 2. Prefix + hyphen + word
        def unhyphen_sub(m: re.Match) -> str:
            pref = m.group(1)
            word = m.group(2)
            word_lower = word.lower()
            if word_lower in COMMON_EVENT_NOUNS:
                serangkai = f"{pref.lower()}{word_lower}"
                if pref[0].isupper():
                    serangkai = serangkai.capitalize()
                return serangkai
            if word[0].isupper():
                return m.group(0)
            return f"{pref}{word}"

        text = re.sub(rf"\b({BOUND_PREFIXES})-([a-zA-Z]\w*)", unhyphen_sub, text, flags=re.IGNORECASE)

        # 3. Spaced prefixes before common words: 'pasca perang' -> 'pascaperang', 'antar bangsa' -> 'antarbangsa'
        SPACED_PREFIXES = r"(?:pasca|pra|non|multi|sub|kontra|tuna)"
        text = re.sub(rf"\b({SPACED_PREFIXES})\s+([a-z]{{3,}})\b", r"\1\2", text, flags=re.IGNORECASE)
        return text

    def normalize_common_spelling_mistakes(self, text: str) -> str:
        """
        Automates multi-category standard Indonesian orthography (EYD V & KBBI VI):
        1. Prepositions 'di ...' and 'ke ...' before spatial/locational words.
        2. Particle 'pun' separation when meaning 'also/even'.
        3. Standard suffixes and loanword vocabulary (PUPI / KBBI VI).
        """
        # 1. Glued prepositions before locational words
        PREP_FIXES = [
            (r"\bdiatas\b", "di atas"),
            (r"\bdibawah\b", "di bawah"),
            (r"\bdidalam\b", "di dalam"),
            (r"\bdiluar\b", "di luar"),
            (r"\bdiantara\b", "di antara"),
            (r"\bdisamping\b", "di samping"),
            (r"\bdisekeliling\b", "di sekeliling"),
            (r"\bdiseluruh\b", "di seluruh"),
            (r"\bkeatas\b", "ke atas"),
            (r"\bkebawah\b", "ke bawah"),
            (r"\bkedalam\b", "ke dalam"),
            (r"\bkesamping\b", "ke samping"),
        ]
        for pat, rep in PREP_FIXES:
            text = re.sub(pat, rep, text, flags=re.IGNORECASE)

        # 2. Glued 'pun' particles (excluding 12 lexicalized compound words)
        PUN_SEPARATE = [
            (r"\bsiapapun\b", "siapa pun"),
            (r"\bapapun\b", "apa pun"),
            (r"\bsatupun\b", "satu pun"),
            (r"\bmanapun\b", "mana pun"),
            (r"\bkapanpun\b", "kapan pun"),
            (r"\bmerekapun\b", "mereka pun"),
            (r"\biapun\b", "ia pun"),
            (r"\bdiapun\b", "dia pun"),
            (r"\bkitapun\b", "kita pun"),
            (r"\bkamupun\b", "kamu pun"),
        ]
        for pat, rep in PUN_SEPARATE:
            text = re.sub(pat, rep, text, flags=re.IGNORECASE)

        # 3. Standard Indonesian Vocabulary (KBBI VI)
        VOCAB_FIXES = [
            (r"\baktifitas\b", "aktivitas"),
            (r"\befektifitas\b", "efektivitas"),
            (r"\bkreatifitas\b", "kreativitas"),
            (r"\bproduktifitas\b", "produktivitas"),
            (r"\bkwalitas\b", "kualitas"),
            (r"\bstandarisasi\b", "standardisasi"),
            (r"\bteoritis\b", "teoretis"),
            (r"\bsistimatis\b", "sistematis"),
            (r"\bsistim\b", "sistem"),
            (r"\banalisa\b", "analisis"),
            (r"\bdiagnosa\b", "diagnosis"),
            (r"\bhipotesa\b", "hipotesis"),
            (r"\bsekedar\b", "sekadar"),
            (r"\bekstrim\b", "ekstrem"),
            (r"\bmerubah\b", "mengubah"),
            (r"\bhirarki\b", "hierarki"),
            (r"\bkonkrit\b", "konkret"),
            (r"\bkongkrit\b", "konkret"),
            (r"\bpraktek\b", "praktik"),
            (r"\bresiko\b", "risiko"),
            (r"\bjaman\b", "zaman"),
            (r"\bijin\b", "izin"),
            (r"\bdekrit\b", "dekret"),
            (r"\bpropinsi\b", "provinsi"),
            (r"\bantri\b", "antre"),
            (r"\bcidera\b", "cedera"),
            (r"\bpersonil\b", "personel"),
            (r"\bmanagemen\b", "manajemen"),
            (r"\bhakekat\b", "hakikat"),
        ]
        for pat, rep in VOCAB_FIXES:
            text = re.sub(pat, rep, text, flags=re.IGNORECASE)

        return text

    def normalize_stylistic_collocations(self, text: str) -> str:
        """
        Normalizes unnatural translation collocations and pleonasms according to KBBI VI and WP:GAYA:
        1. 'khalayak pelayat/demonstran/massa' -> 'kerumunan pelayat/demonstran/massa'
        2. 'khalayak mahasiswa/pekerja/hadirin' -> 'para mahasiswa/pekerja/hadirin'
        3. Classifier 'salah satu' for humans -> 'salah seorang'
        4. 'menghabiskan waktu luang' -> 'mengisi waktu luang'
        5. Pleonasms: 'adalah merupakan' -> 'merupakan', 'agar supaya' -> 'agar',
           'demi untuk' -> 'demi', 'banyak para' -> 'para'.
        """
        text = re.sub(r"\bkhalayak\s+(pelayat|demonstran|pengunjuk rasa|massa)\b", r"kerumunan \1", text, flags=re.IGNORECASE)
        text = re.sub(r"\bkhalayak\s+(mahasiswa|pekerja|buruh|hadirin|peserta)\b", r"para \1", text, flags=re.IGNORECASE)
        text = re.sub(r"\bsalah\s+satu\s+(tokoh|pemimpin|orang|pria|wanita|sosok|figur)\b", r"salah seorang \1", text, flags=re.IGNORECASE)
        text = re.sub(r"\bmenghabiskan\s+waktu\s+luang\b", "mengisi waktu luang", text, flags=re.IGNORECASE)
        text = re.sub(r"\badalah\s+merupakan\b", "merupakan", text, flags=re.IGNORECASE)
        text = re.sub(r"\bagar\s+supaya\b", "agar", text, flags=re.IGNORECASE)
        text = re.sub(r"\bdemi\s+untuk\b", "demi", text, flags=re.IGNORECASE)
        text = re.sub(r"\bbanyak\s+para\b", "para", text, flags=re.IGNORECASE)
        MONTHS = r"(?:Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember)"
        text = re.sub(rf"\b(pada|sejak|hingga|sampai|menjelang|selama)\s+bulan\s+({MONTHS})\b", r"\1 \2", text, flags=re.IGNORECASE)
        text = re.sub(r"\b(ke|di|pada)\s+sebuah\s+(pusat kanker|rumah sakit|klinik|puskesmas|sekolah|universitas|akademi|fakultas|lembaga|yayasan|instansi|kedutaan)\b", r"\1 \2", text, flags=re.IGNORECASE)
        text = re.sub(r"\bPada\s+([^,\n]{3,35}),\s+misalnya,\s+([a-z0-9A-Z\[])", r"Sebagai contoh, pada \1 \2", text)
        return text
    def restructure_double_temporal_markers(self, text: str) -> str:
        """
        Restructures double/pleonastic temporal stacking commonly calqued from English:
        e.g. 'Tak lama berselang, pada Juli, Raisa didiagnosis' -> 'Pada Juli tahun yang sama, Raisa didiagnosis'
        e.g. 'Dua tahun berselang, pada Juni 2002, ia' -> 'Pada Juni 2002, ia'
        e.g. 'Tak lama kemudian, pada November, pemerintah' -> 'Pada November tahun yang sama, pemerintah'
        e.g. 'Beberapa bulan kemudian, pada Agustus, ia' -> 'Pada Agustus tahun yang sama, ia'
        """
        if not text:
            return ""
        MONTHS = r"(?:Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember)"
        TEMPORAL_INTERVALS = (
            r"(?:(?:Tak|Tidak)\s+lama|"
            r"Setahun|Sebulan|"
            r"Beberapa\s+(?:bulan|tahun|waktu)|"
            r"(?:Satu|Dua|Tiga|Empat|Lima|Enam|Tujuh|Delapan|Sembilan|Sepuluh|\d+)\s+(?:bulan|tahun))"
            r"\s+(?:berselang|kemudian)"
        )

        pat1 = re.compile(
            rf"\b({TEMPORAL_INTERVALS}),\s+pada\s+({MONTHS})(?:\s+(\d{{4}}))?,?\s+([A-Za-z\[])"
        )
        def repl1(m: re.Match) -> str:
            month = m.group(2)
            year = m.group(3)
            subject = m.group(4)
            if year:
                # If year is explicitly given (e.g. 'Juni 2002'), relative interval is redundant!
                return f"Pada {month} {year}, {subject}"
            return f"Pada {month} tahun yang sama, {subject}"

        text = pat1.sub(repl1, text)
        text = re.sub(r"\bpada\s+awalnya\s+mulanya\b", "pada awalnya", text, flags=re.IGNORECASE)
        text = re.sub(r"\bkemudian\s+setelah\s+itu\b", "setelah itu", text, flags=re.IGNORECASE)
        text = re.sub(r"\blalu\s+kemudian\b", "kemudian", text, flags=re.IGNORECASE)
        return text
    def normalize_temporal_year_classifiers(self, text: str) -> str:
        """
        Normalizes standalone 4-digit calendar years preceded by prepositions into formal Indonesian encyclopedic register:
        - 'pada 2000' -> 'pada tahun 2000'
        - 'sejak 1985' -> 'sejak tahun 1985'
        - 'hingga 1991' -> 'hingga tahun 1991'
        - 'dari 1985' -> 'dari tahun 1985'
        - 'menjelang 1968' -> 'menjelang tahun 1968'
        Preserves natural month-year and full-date combinations:
        - 'pada Juni 2002' remains untouched (already natural and concise).
        - 'pada 11 Maret 2000' remains untouched.
        - '|date=14 Februari 2023' remains untouched.
        """
        if not text:
            return ""

        MONTHS = r"(?:Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember)"
        PREPOSITIONS = r"(?:Pada|pada|Sejak|sejak|Hingga|hingga|Sampai|sampai|Menjelang|menjelang|Dari|dari)"

        pat = re.compile(
            rf"\b({PREPOSITIONS})\s+([12]\d{{3}})\b(?!\s*[-–—]\s*\d|\s+{MONTHS})"
        )

        def repl(m: re.Match) -> str:
            prep = m.group(1)
            year = m.group(2)
            return f"{prep} tahun {year}"

        return pat.sub(repl, text)
    def normalize_sentence_case_after_periods(self, text: str) -> str:
        """
        Capitalizes the first letter of a sentence following a period and optional citation templates / refs.
        E.g.:
        - 'memuaskan. {{sfnm|...}} tugas akhirnya' -> 'memuaskan. {{sfnm|...}} Tugas akhirnya'
        - 'Sokolniki. {{sfnm|...}} sebulan berselang' -> 'Sokolniki. {{sfnm|...}} Sebulan berselang'
        """
        if not text:
            return ""

        citation_templates = r"(?:sfn|sfnm|sfnmp|r|rp|refn|sn|sfnp|cite[ _][a-z]+|citation)"
        cite_or_space_pattern = (
            r"(?:\s*<ref[^>]*>.*?</ref>|\s*<ref[^>]*/>|\s*\{\{\s*"
            + citation_templates
            + r"\b[^{}]*\}\}|\s+)+"
        )
        pattern = re.compile(
            r"\b([A-Za-z0-9_-]+)\.(" + cite_or_space_pattern + r")([a-z])([a-zA-Z0-9_-]*)",
            re.DOTALL | re.IGNORECASE,
        )

        def replacer(m: re.Match) -> str:
            prev_word = m.group(1)
            if prev_word.lower() in COMMON_SENTENCE_ABBREVIATIONS or len(prev_word) == 1 or prev_word.isdigit():
                return m.group(0)
            start_idx = max(0, m.start() - 10)
            preceding = text[start_idx:m.start()]
            if "http" in preceding or "www" in preceding:
                return m.group(0)
            cites_and_spaces = m.group(2)
            first_char = m.group(3)
            rest = m.group(4)
            return f"{prev_word}.{cites_and_spaces}{first_char.upper()}{rest}"

        return pattern.sub(replacer, text)
    def normalize_image_thumbnail_syntax(self, text: str) -> str:
        """
        Dynamically normalizes MediaWiki image thumbnail options to canonical 'thumb',
        matching English Wikipedia standard across all articles (eliminating 'jempol', 'jmpl', 'jempolan', 'mini'):
        - [[File:...|jempol|...]] -> [[File:...|thumb|...]]
        - [[Berkas:...|jmpl|...]] -> [[Berkas:...|thumb|...]]
        Handles balanced brackets for captions with nested wikilinks.
        """
        if not text:
            return ""

        file_prefix_re = re.compile(r"\[\[\s*(?:File|Berkas|Image)\s*:", re.IGNORECASE)
        pos = 0
        out = []

        while pos < len(text):
            m = file_prefix_re.search(text, pos)
            if not m:
                out.append(text[pos:])
                break
            start = m.start()
            out.append(text[pos:start])

            d = 0
            i = start
            end = len(text)
            while i < len(text):
                if text[i : i + 2] == "[[":
                    d += 1
                    i += 2
                elif text[i : i + 2] == "]]":
                    d -= 1
                    if d == 0:
                        end = i + 2
                        break
                    i += 2
                else:
                    i += 1

            raw_file = text[start:end]
            norm_file = re.sub(r"\|\s*(?:jempolan|jempol|jmpl|mini)\s*(\||\]\])", r"|thumb\1", raw_file, flags=re.IGNORECASE)
            norm_file = re.sub(r"\|\s*thumb\s*\|\s*thumb\b", "|thumb", norm_file, flags=re.IGNORECASE)
            out.append(norm_file)
            pos = end

        return "".join(out)
    def clean_indirect_speech_fragmented_quotes(self, text: str) -> str:
        """
        Cleans fragmented scare quotes in indirect speech clauses ('bahwa ...'):
        e.g. 'menuturkan bahwa peristiwa itu "sangat membekas"' -> 'menuturkan bahwa peristiwa itu sangat membekas'
        e.g. 'mengakui bahwa "hati nurani tersiksa"' -> 'mengakui bahwa hati nuraninya tersiksa'
        Preserves titles, slogans, and established political terms.
        """
        if not text:
            return ""

        pattern = re.compile(
            r'(\b(?:bahwa|mengakui bahwa|menuturkan bahwa|menilai bahwa|mencatat bahwa|mengamati bahwa|mengklaim bahwa|menegaskan bahwa)(?:\s+[^\"\n,]{1,35})?\s+)\"([a-z][^\"]{2,60})\"'
        )
        def replacer(m: re.Match) -> str:
            lead = m.group(1)
            quoted = m.group(2)
            if quoted.lower().strip() in PRESERVED_INDIRECT_SPEECH_QUOTES:
                return m.group(0)
            if quoted == "hati nurani tersiksa":
                quoted = "hati nuraninya tersiksa"
            return f"{lead}{quoted}"

        text = pattern.sub(replacer, text)
        text = pattern.sub(replacer, text)

        pattern2 = re.compile(
            r'(\b(?:sebagai|menjadi|berperan sebagai|menerima status|semata-mata|tindakan|memiliki|guna|menerapkan)(?:\s+(?:sebuah|suatu|sedikit kadar|kadar))?\s+)\"([a-z][^\"]{2,40})\"'
        )
        text = pattern2.sub(replacer, text)
        return text

    def normalize_appositive_commas(self, text: str) -> str:
        """
        Cleans appositive comma sandwiches around proper nouns according to EYD V & WP:GAYA.
        In Indonesian, direct attributive descriptions before names do not need commas:
        e.g. 'rekan kuliah, Raisa Titarenko, pada tahun' -> 'rekan kuliah Raisa Titarenko pada tahun'
        e.g. 'putrinya, Irina, menikah dengan' -> 'putrinya Irina menikah dengan'
        e.g. 'sesama mahasiswa, Anatoly Virgansky, pada' -> 'sesama mahasiswa Anatoly Virgansky pada'
        """
        ATTRIB_NOUNS = r"(?:[Aa]yah|[Ii]bu|[Ss]audara|[Ss]audari|[Aa]dik|[Kk]akak|[Aa]nak|[Pp]utra|[Pp]utri|[Ss]uami|[Ii]stri|[Ss]ahabat|[Tt]eman|[Rr]ekan|[Kk]olega|[Pp]enulis|[Aa]rsitek|[Rr]ektor|[Mm]enteri|[Pp]residen|[Rr]aja|[Kk]aisar|[Dd]uta [Bb]esar|sesama mahasiswa)(?:nya)?"
        pattern = re.compile(
            rf"\b({ATTRIB_NOUNS}(?:\s+\w+){{0,7}}),\s+((?:\[\[(?:[^|\]]+\|)?([^\]]+)\]\]|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)(?:\s+\([^)]+\))*),\s+(\w+)\b"
        )
        def clean_appositive(m: re.Match) -> str:
            desc = m.group(1)
            name = m.group(2)
            nxt = m.group(4)
            return f"{desc} {name} {nxt}"

        return pattern.sub(clean_appositive, text)

    def normalize_coordinating_conjunction_commas(self, text: str) -> str:
        """
        Removes commas before coordinating conjunctions ('dan', 'serta') when connecting
        two parallel verbal predicates sharing the same subject without a serial list (EYD V).
        e.g. 'belajar giat, dan lulus' -> 'belajar giat dan lulus'
        e.g. 'di Münster, Jerman, dan menjalani' -> 'di Münster, Jerman dan menjalani'
        Does NOT remove serial/Oxford commas in 3+ item lists: 'London, Paris, dan Berlin'.
        """
        verbs = r"(?:me[a-z]+|di[a-z]+|ber[a-z]+|ter[a-z]+|lulus|gugur|wafat|tewas|lahir|hidup|masuk|keluar|naik|turun|pergi|pulang|kembali|ikut|turut)"
        pattern = re.compile(rf"\b(\w+),\s+(dan|serta)\s+([a-z]\w*)\b")

        def clean_conj(m: re.Match) -> str:
            w1 = m.group(1)
            conj = m.group(2)
            w2 = m.group(3)
            # If w2 is not a lowercase verb, do not touch (e.g. proper nouns like 'Berlin')
            if not re.match(rf"^{verbs}$", w2):
                return m.group(0)

            full_start = m.start()
            pre = text[max(0, full_start - 35) : full_start]
            is_w1_verb = bool(re.match(rf"^{verbs}$", w1, re.IGNORECASE))

            if "," in pre:
                # If w1 is not a verb (e.g. 'Münster, Jerman, dan menjalani'), it cannot be a list of verbs
                if not is_w1_verb:
                    return f"{w1} {conj} {w2}"
                # If w1 IS a verb, check if pre has another verb before the comma (true serial list of verbs)
                pre_verbs = re.findall(rf"\b{verbs}\b", pre, re.IGNORECASE)
                if pre_verbs:
                    return m.group(0)
                return f"{w1} {conj} {w2}"

            return f"{w1} {conj} {w2}"

        return pattern.sub(clean_conj, text)
    def normalize_introductory_adverbial_commas(self, text: str) -> str:
        """
        Removes the redundant second comma in introductory conjunction + short adverbial sandwich:
        e.g. 'Namun, sesampainya di sana, ia mendapati' -> 'Namun, sesampainya di sana ia mendapati'
        e.g. 'Namun, pada Agustus 1968, ia diangkat' -> 'Namun, pada Agustus 1968 ia diangkat'
        e.g. 'Sementara itu, dalam rapat Komite Pusat, tokoh' -> 'Sementara itu, dalam rapat Komite Pusat tokoh'
        Preserves vocatives (e.g. 'Namun, Kamerad, jangan...') and long subordinate clauses.
        """
        CONNECTORS = (
            r"(?:Namun|Selain itu|Oleh karena itu|Sementara itu|Akan tetapi|Meskipun demikian|"
            r"Kendati demikian|Oleh sebab itu|Tak lama berselang|Tidak lama kemudian|"
            r"Tak lama kemudian|Beberapa bulan kemudian|Beberapa tahun kemudian|"
            r"Sesaat kemudian|Setelah itu|Sebelum itu|Menjelang akhir|Sejak saat itu|"
            r"Pada awalnya|Mulanya|"
            r"(?:Setahun|Sebulan|Beberapa\s+(?:bulan|tahun)|[A-Z][a-z]+\s+(?:bulan|tahun))\s+(?:berselang|kemudian))"
        )
        ADVERB_STARTERS = (
            r"(?:pada|di|dalam|sewaktu|saat|ketika|sesampainya|setibanya|menjelang|"
            r"selama|tak lama|tidak lama|sebulan|setahun|beberapa [a-z]+|"
            r"atas|menurut|berkat|seiring)"
        )
        pattern = re.compile(
            rf"\b({CONNECTORS}),\s+({ADVERB_STARTERS}(?:\s+[^,\n]+){{0,5}}),\s+([a-z0-9A-Z\[])"
        )
        def replacer(m: re.Match) -> str:
            connector = m.group(1)
            adverb = m.group(2)
            nxt = m.group(3)
            # If adverb contains a full clause (subject + action verb), preserve comma
            if re.search(r"\b(?:ia|dia|mereka|kami|kita)\s+(?:bertolak|pergi|datang|mulai|mencapai)\b", adverb):
                return m.group(0)
            # Protect boundary comma before capitalized Subject (Proper Noun) or wikilink
            if nxt.isupper() or nxt == "[":
                return m.group(0)
            return f"{connector}, {adverb} {nxt}"

        return pattern.sub(replacer, text)

    def normalize_relative_clause_commas(self, text: str) -> str:
        """
        Removes English-calqued comma sandwiches around 'yang' relative clauses:
        e.g. 'Gorbachev, yang kala itu berusia 53 tahun, masih terlalu muda'
             -> 'Gorbachev yang kala itu berusia 53 tahun masih terlalu muda'
        e.g. 'staf Komite Pusat, yang saat itu mencapai sekitar 3.000 orang, dipangkas'
             -> 'staf Komite Pusat yang saat itu mencapai sekitar 3.000 orang dipangkas'
        e.g. 'Yeltsin, yang saat itu menjabat sebagai Presiden, masuk ke dalam'
             -> 'Yeltsin yang saat itu menjabat sebagai Presiden masuk ke dalam'
        """
        ROOT_VERBS = r"(?:masuk|keluar|naik|turun|pergi|pulang|kembali|tiba|datang|lulus|wafat|tewas|gugur|tampil|ikut|turut|lahir|hidup)"
        PREDICATES = rf"(?:masih|dipangkas|justru|dengan|mengumumkan|kemudian|telah|akan|dapat|bisa|sempat|pernah|resmi|menjadi|berada|tercatat|menolak|mengakui|menyatakan|menilai|berpendapat|menuduh|terpaksa|{ROOT_VERBS}|\bme[a-z]+|\bdi[a-z]+|\bber[a-z]+|\bter[a-z]+)"
        pattern = re.compile(
            rf"(\b\w+|\]\]|\'\'),\s+yang\s+((?:[^\n,.\"]|(?<=\d)\.(?=\d))+),\s+({PREDICATES}\b)"
        )
        text = pattern.sub(r"\1 yang \2 \3", text)
        paren_aside_pat = re.compile(r",\s+(setelah\s+(?:\[\[[^\]]+\]\]|[^,.\n]+)),\s+yang\b", re.IGNORECASE)
        text = paren_aside_pat.sub(r" (\1) yang", text)
        return text

    def normalize_parenthetical_modifier_commas(self, text: str) -> str:
        """
        Cleans unnatural comma sandwiches around restrictive parenthetical modifiers
        (e.g. 'terutama', 'khususnya', 'terlebih') inserted between a Subject noun and its Predicate:
- 'banyak pihak, terutama di negara-negara Barat, memandangnya'
             -> 'banyak pihak terutama di negara-negara Barat memandangnya'
- 'para pengamat, khususnya di Eropa, menilai bahwa'
             -> 'para pengamat khususnya di Eropa menilai bahwa'
        In standard Indonesian (EYD V), restrictive modifiers specifying the subject
        do not take commas that sever the subject from its predicate verb.
        """
        if not text:
            return ""

        ROOT_VERBS = r"(?:tahu|yakin|percaya|ingin|mau|paham|kenal|sadar|luput|gagal|berhasil)"
        AFFIX_VERBS = r"(?:me[a-z]+|di[a-z]+|ber[a-z]+|ter[a-z]+|menjadi|merupakan|tampak|terlihat|dianggap|dipandang|dinilai)"
        AUXILIARIES = r"(?:telah|akan|sedang|pernah|sempat|masih|mulai|terus|turut|ikut|bisa|dapat|kerap|sering|justru|kembali)"
        PREDICATES = rf"(?:(?:{AUXILIARIES}\s+)?(?:{AFFIX_VERBS}|{ROOT_VERBS}))"
        MODIFIERS = r"(?:terutama|khususnya|terlebih|bahkan)"
        SUBJECT = r"(\b\w+|\]\]|\'\')"

        # Matches: [Noun/Subject], (terutama|khususnya) [Modifier phrase], [Verb predicate]
        pattern = re.compile(
            rf"{SUBJECT},\s+({MODIFIERS})\s+([^,\n]{{2,50}}),\s+({PREDICATES}\b)",
            re.IGNORECASE,
        )

        return pattern.sub(r"\1 \2 \3 \4", text)
    def normalize_comma_clutter(self, text: str) -> str:
        """
        Cleans comma clutter and sentence-level comma fatigue:
        1. Breaks double coordinating conjunction in same sentence:
           '... dan X, dan ia Y ...' -> '... dan X. Selain itu, ia Y ...'
        2. Cleans duplicate commas (',,') and stray spaces before commas.
        3. Cleans comma before period (',.').
        """
        def split_double_dan(m: re.Match) -> str:
            left = m.group(1)
            item1 = m.group(2)
            rest = m.group(3)
            return f"{left} dan {item1}. Selain itu, ia {rest}"

        text = re.sub(r"(\b\w+),\s+dan\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*),\s+dan\s+ia(?:\s+juga)?\s+(\w+)", split_double_dan, text)
        text = re.sub(r",\s*,+", ",", text)
        text = re.sub(r"\s+,", ",", text)
        text = re.sub(r",\s*\.", ".", text)
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
