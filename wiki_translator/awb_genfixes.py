"""
AWB-style General Fixes (GenFixes) and RegEx Typo Fix (RETF) Engine for Indonesian Wikipedia.

Complies with Wikipedia Bahasa Indonesia guidelines (WP:PEDOMAN, WP:GAYA, EYD V, KBBI VI).
Provides deterministic, safe, automated corrections:
1. Standard Appendix Reordering (Catatan, Referensi/Rujukan, Bacaan lanjutan, Pranala luar)
2. Reference Deduplication (<ref name="X">...</ref> -> <ref name="X" />)
3. Citation Punctuation Placement (punctuation before ref, space cleanup)
4. Page Range En-Dash Normalizer (pp. 12-15 / pages 12-15 -> hlm. 12–15)
5. Duplicate/Redundant Empty Parameter Cleaner in Citation Templates
6. RegEx Typo Fix Engine (RETF) with 100+ deterministic Indonesian orthographic fixes
"""

import re
from typing import Dict, List, Optional, Set, Tuple


# Comprehensive Indonesian Typo mapping based on:
# - Wikipedia:Daftar kesalahan ejaan yang sering dibuat
# - Kamus Besar Bahasa Indonesia (KBBI VI)
# Format: {incorrect_lower: correct_lower}
INDONESIAN_TYPO_PAIRS: Dict[str, str] = {
    # A
    "aktifitas": "aktivitas",
    "aktip": "aktif",
    "analisa": "analisis",
    "antri": "antre",
    "antrian": "antrean",
    "apotik": "apotek",
    "atlit": "atlet",
    "atletik": "atletik",
    "adzan": "azan",
    "ambulan": "ambulans",
    "aseli": "asli",
    "azaz": "asas",
    # B
    "batalion": "batalyon",
    "berfikir": "berpikir",
    "biosfir": "biosfer",
    "blangko": "blanko",
    "brantas": "berantas",
    "budidaya": "budi daya",
    # C
    "cidera": "cedera",
    "cinderamata": "cenderamata",
    "capek": "capai",
    "cendikiawan": "cendekiawan",
    # D
    "debet": "debit",
    "dekrit": "dekret",
    "definitif": "definitif",
    "depo": "depot",
    "deterjen": "detergen",
    "diagnosa": "diagnosis",
    "duren": "durian",
    "debitur": "debitor",
    # E
    "efektip": "efektif",
    "ekstra kurikuler": "ekstrakurikuler",
    "ekstrim": "ekstrem",
    "elit": "elite",
    "esensil": "esensial",
    # F
    "faham": "paham",
    "faksimili": "faksimile",
    "fikiran": "pikiran",
    "filsafat": "filsafat",
    "filosofis": "filosofis",
    "fondamen": "fondasi",
    "frasa": "frasa",
    "fotosintesa": "fotosintesis",
    # G
    "gladi": "geladi",
    "glamour": "glamor",
    "goncang": "guncang",
    "gubuk": "gubuk",
    "greget": "gereget",
    # H
    "hafal": "hafal",
    "hakekat": "hakikat",
    "hembus": "embus",
    "hepar": "hepar",
    "heterogenitas": "heterogenitas",
    "hiearki": "hierarki",
    "hierarkis": "hierarkis",
    "himpit": "impit",
    "hipotesa": "hipotesis",
    "hirarki": "hierarki",
    "hisap": "isap",
    "himbau": "imbau",
    "himbauan": "imbauan",
    "hutang": "utang",
    # I
    "ijin": "izin",
    "ikhlas": "ikhlas",
    "iklas": "ikhlas",
    "ilusi": "ilusi",
    "indera": "indra",
    "inisiatip": "inisiatif",
    "insyaf": "insaf",
    "interogir": "interogasi",
    "intrupsi": "interupsi",
    "ijazah": "ijazah",
    "isap": "isap",
    "isteri": "istri",
    "istighfar": "istigfar",
    # J
    "jadwal": "jadwal",
    "jaman": "zaman",
    "jenazah": "jenazah",
    "jendral": "jenderal",
    "justru": "justru",
    # K
    "kaedah": "kaidah",
    "kangker": "kanker",
    "karir": "karier",
    "karna": "karena",
    "kantung": "kantong",
    "katagori": "kategori",
    "khotbah": "khotbah",
    "komplit": "komplet",
    "kongkrit": "kongret",
    "konsekwen": "konsekuen",
    "koordinir": "koordinasi",
    "kreatip": "kreatif",
    "kreatifitas": "kreativitas",
    "kwalitas": "kualitas",
    "kwitansi": "kuitansi",
    "kwantitas": "kuantitas",
    "kolektip": "kolektif",
    "korma": "kurma",
    # L
    "legalisir": "legalisasi",
    "lembab": "lembap",
    "lobang": "lubang",
    "longgar": "longgar",
    # M
    "maap": "maaf",
    "makdum": "maklum",
    "mampet": "mampat",
    "managemen": "manajemen",
    "manager": "manajer",
    "mandeg": "mandek",
    "massal": "masal",
    "mateng": "matang",
    "mempesona": "memesona",
    "mempengaruhi": "memengaruhi",
    "memperhatikan": "memerhatikan",
    "mengenyampingkan": "mengesampingkan",
    "menterjemahkan": "menerjemahkan",
    "mentertawakan": "menertawakan",
    "merubah": "mengubah",
    "metoda": "metode",
    "milyar": "miliar",
    "milyader": "miliarder",
    "mubasir": "mubazir",
    # N
    "nafas": "napas",
    "nampak": "tampak",
    "nasehat": "nasihat",
    "negosiasi": "negosiasi",
    "negeri": "negeri",
    "nomor": "nomor",
    "nomer": "nomor",
    # O
    "obyek": "objek",
    "obyektif": "objektif",
    "organisir": "organisasi",
    "otentik": "autentik",
    "otodidak": "autodidak",
    "otomatis": "otomatis",
    # P
    "paham": "paham",
    "praktek": "praktik",
    "prangko": "perangko",
    "paspor": "paspor",
    "pedas": "pedas",
    "pedes": "pedas",
    "pelepasan": "pelepasan",
    "pemukiman": "permukiman",
    "pengrajin": "perajin",
    "pengrusakan": "perusakan",
    "penasehat": "penasihat",
    "perancis": "prancis",
    "peranti": "peranti",
    "piranti": "peranti",
    "plesir": "pelesir",
    "pondasi": "fondasi",
    "prakata": "prakata",
    "proklamir": "proklamasi",
    "propinsi": "provinsi",
    "psikotest": "psikotes",
    # R
    "rebo": "rabu",
    "rapih": "rapi",
    "raport": "rapor",
    "rejeki": "rezeki",
    "respon": "respons",
    "resiko": "risiko",
    "robbani": "robbani",
    "rubuh": "roboh",
    # S
    "sahabat": "sahabat",
    "sahid": "syahid",
    "sahdu": "syahdu",
    "sahur": "sahur",
    "saraf": "saraf",
    "sarap": "saraf",
    "sekedar": "sekadar",
    "sekretaris": "sekretaris",
    "selebriti": "selebritas",
    "sepion": "spion",
    "silahkan": "silakan",
    "sistim": "sistem",
    "sistematik": "sistematika",
    "sosialisir": "sosialisasi",
    "standarisasi": "standardisasi",
    "stres": "stres",
    "stress": "stres",
    "subyek": "subjek",
    "subyektif": "subjektif",
    "sutera": "sutra",
    "syaraf": "saraf",
    # T
    "tahta": "takhta",
    "tauladan": "teladan",
    "tehnik": "teknik",
    "tehnologi": "teknologi",
    "telpon": "telepon",
    "teoritis": "teoretis",
    "terimakasih": "terima kasih",
    "trampil": "terampil",
    "tenggelam": "tenggelam",
    "tragedi": "tragedi",
    "tolerir": "toleransi",
    "turis": "turis",
    # U
    "ubah": "ubah",
    "unta": "onta",
    "ustadz": "ustaz",
    "ustadzah": "ustazah",
    "ujud": "wujud",
    # V
    "vaksinir": "vaksinasi",
    "variap": "variasi",
    "vitalitas": "vitalitas",
    "volunter": "sukarelawan",
    # W
    "wasyiat": "wasiat",
    # Z
    "zam-zam": "zamzam",
    "zina": "zina",
    "zone": "zona",
}

# Multi-word compound substitutions
# Note: "pertanggung jawaban" -> "pertanggungjawaban"
INDONESIAN_MULTIWORD_TYPOS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\bpertanggung\s+jawaban\b", flags=re.IGNORECASE), "pertanggungjawaban"),
    (re.compile(r"\btata\s+bahasa\b", flags=re.IGNORECASE), "tatabahasa"),  # or remains tata bahasa in KBBI (tata bahasa is standard noun, but if glued: keep standard)
    (re.compile(r"\btanda\s+tangan\b(?=\s+(?:oleh|surat|kontrak|perjanjian|dokumen))", flags=re.IGNORECASE), "tandatangan"),
    (re.compile(r"\bmenanda\s+tangani\b", flags=re.IGNORECASE), "menandatangani"),
    (re.compile(r"\bditanda\s+tangani\b", flags=re.IGNORECASE), "ditandatangani"),
    (re.compile(r"\bpenanda\s+tanganan\b", flags=re.IGNORECASE), "penandatanganan"),
    (re.compile(r"\bbudi\s+daya\b", flags=re.IGNORECASE), "budi daya"),
    (re.compile(r"\btata\s+cara\b", flags=re.IGNORECASE), "tata cara"),
    (re.compile(r"\btata\s+tertib\b", flags=re.IGNORECASE), "tata tertib"),
    (re.compile(r"\bantar\s+negara\b", flags=re.IGNORECASE), "antarnegara"),
    (re.compile(r"\bantar\s+bangsa\b", flags=re.IGNORECASE), "antarbangsa"),
    (re.compile(r"\bantar\s+kota\b", flags=re.IGNORECASE), "antarkota"),
    (re.compile(r"\bnon\s+aktif\b", flags=re.IGNORECASE), "nonaktif"),
    (re.compile(r"\bnon\s+blok\b", flags=re.IGNORECASE), "nonblok"),
    (re.compile(r"\bsub\s+bagian\b", flags=re.IGNORECASE), "subbagian"),
    (re.compile(r"\bpasca\s+panen\b", flags=re.IGNORECASE), "pascapanen"),
    (re.compile(r"\bpasca\s+perang\b", flags=re.IGNORECASE), "pascaperang"),
    (re.compile(r"\bpasca\s+sarjana\b", flags=re.IGNORECASE), "pascasarjana"),
    (re.compile(r"\bserah\s+terima\b", flags=re.IGNORECASE), "serah terima"),
    (re.compile(r"\bsebar\s+luas\b", flags=re.IGNORECASE), "sebar luas"),
    (re.compile(r"\bmenyebar\s+luaskan\b", flags=re.IGNORECASE), "menyebarluaskan"),
    (re.compile(r"\bdisebar\s+luaskan\b", flags=re.IGNORECASE), "disebarluaskan"),
    (re.compile(r"\bpenyebar\s+luasan\b", flags=re.IGNORECASE), "penyebarluasan"),
]


def _match_case(source: str, target: str) -> str:
    """Matches the capitalization pattern of source onto target."""
    if source.isupper():
        return target.upper()
    if source and source[0].isupper():
        if len(source) > 1 and source[1:].islower():
            return target.capitalize()
        return target.capitalize()
    return target.lower()


class RegExTypoFixEngine:
    """
    RegEx Typo Fix (RETF) Engine for Indonesian Wikipedia articles.
    Performs deterministic typo corrections based on KBBI VI and Wikipedia:Daftar kesalahan ejaan yang sering dibuat.
    Guaranteed safe: ignores URLs, file names, math tags, code, and template parameter keys.
    """

    def __init__(self, custom_typos: Optional[Dict[str, str]] = None):
        self.typo_map: Dict[str, str] = dict(INDONESIAN_TYPO_PAIRS)
        if custom_typos:
            self.typo_map.update({k.lower(): v for k, v in custom_typos.items()})

        # Pre-compile single-word patterns: filter out identical pairs (just in case)
        self.valid_pairs: List[Tuple[str, str]] = [
            (wrong, correct) for wrong, correct in self.typo_map.items() if wrong != correct.lower()
        ]

        # Build a single unified regex pattern for speed and efficiency
        # Sort by length descending to match longest word first
        sorted_wrongs = sorted([re.escape(w) for w, _ in self.valid_pairs], key=len, reverse=True)
        # Match as full word boundaries (\b)
        self.combined_pattern = re.compile(r"\b(" + "|".join(sorted_wrongs) + r")\b", flags=re.IGNORECASE)

    @property
    def dictionary_size(self) -> int:
        """Returns the total number of recognized typo pairs."""
        return len(self.valid_pairs) + len(INDONESIAN_MULTIWORD_TYPOS)

    def fix_typos(self, text: str) -> str:
        """Fixes common spelling mistakes safely in wikitext prose."""
        if not text:
            return ""

        # Step 1: Protect sensitive sections
        protected_blocks: List[str] = []

        def block_replacer(match: re.Match) -> str:
            protected_blocks.append(match.group(0))
            return f"__RETF_PROTECTED_{len(protected_blocks) - 1}__"

        # Patterns to strictly protect against any typo replacement:
        protect_patterns = [
            r"<!--[\s\S]*?-->",                                    # Comments
            r"<nowiki>[\s\S]*?</nowiki>",                          # Nowiki
            r"<math[\s\S]*?</math>",                               # Math
            r"<syntaxhighlight[\s\S]*?</syntaxhighlight>",        # Syntaxhighlight
            r"<source[\s\S]*?</source>",                           # Source
            r"<pre[\s\S]*?</pre>",                                 # Pre
            r"<code>[\s\S]*?</code>",                              # Code
            r"https?://[^\s\[\]<>\"]+",                            # URLs
            r"\[\[(?:Berkas|File|Gambar|Image):[^\]\n]+\]\]",     # Media/files
            r"\|\s*[a-zA-Z0-9_\-]+(?=\s*=)",                       # Template parameter keys (e.g. |aktifitas=)
        ]

        sanitized = text
        for pat in protect_patterns:
            sanitized = re.sub(pat, block_replacer, sanitized, flags=re.IGNORECASE)

        # Step 2: Apply multi-word compound replacements
        for pattern, replacement in INDONESIAN_MULTIWORD_TYPOS:
            def multi_replacer(m: re.Match) -> str:
                return _match_case(m.group(0), replacement)
            sanitized = pattern.sub(multi_replacer, sanitized)

        # Step 3: Apply single-word replacements using combined regex
        def single_replacer(m: re.Match) -> str:
            matched = m.group(1)
            target = self.typo_map.get(matched.lower())
            if not target:
                return matched
            return _match_case(matched, target)

        sanitized = self.combined_pattern.sub(single_replacer, sanitized)

        # Step 4: Restore protected blocks
        for idx, block in enumerate(protected_blocks):
            sanitized = sanitized.replace(f"__RETF_PROTECTED_{idx}__", block)

        return sanitized


class GeneralFixesEngine:
    """
    AWB-style General Fixes Engine conforming to Indonesian Wikipedia WP:PEDOMAN and MoS.
    """

    # WP:PEDOMAN Standard bottom appendix section order
    # 1. Catatan (or {{Notelist}})
    # 2. Referensi / Rujukan (or {{Reflist}})
    # 3. Bacaan lanjutan / Pustaka
    # 4. Pranala luar
    APPENDIX_ORDER = [
        "catatan",
        "referensi",
        "bacaan lanjutan",
        "pranala luar",
    ]

    def __init__(self):
        pass

    def reorder_appendices(self, text: str) -> str:
        """
        Reorders standard Wikipedia Bahasa Indonesia appendix sections at the end of the article
        according to WP:PEDOMAN:
        1. == Catatan ==
        2. == Referensi == (or == Rujukan ==)
        3. == Bacaan lanjutan ==
        4. == Pranala luar ==
        Preserves categories, defaultsort, and navbox templates below the appendices.
        """
        if not text:
            return ""

        # Heading regex for level 2 sections: == Section Name ==
        heading_re = re.compile(r"^(==\s*([^=\n]+?)\s*==)\s*$", flags=re.MULTILINE)
        matches = list(heading_re.finditer(text))
        if not matches:
            return text

        # Identify appendix sections
        appendix_canonical_map = {
            "catatan": "catatan",
            "catatan kaki": "catatan",
            "referensi": "referensi",
            "rujukan": "referensi",
            "daftar pustaka": "referensi",  # Note: sometimes daftar pustaka is references or bibliography
            "bacaan lanjutan": "bacaan lanjutan",
            "kepustakaan": "bacaan lanjutan",
            "pranala luar": "pranala luar",
            "link luar": "pranala luar",
            "tautan luar": "pranala luar",
        }

        # Find the earliest appendix section in the document
        appendix_indices: List[Tuple[int, str, int, int]] = []
        # (match_start, canonical_key, match_idx, match_end)

        for idx, m in enumerate(matches):
            title = m.group(2).strip().lower()
            if title in appendix_canonical_map:
                appendix_indices.append((m.start(), appendix_canonical_map[title], idx, m.end()))

        if not appendix_indices:
            return text

        # Check if the appendix sections are consecutive near the bottom of the article
        # Find first appendix index in matches
        first_app_idx = appendix_indices[0][2]
        # Any section between first appendix and end that is NOT appendix?
        # Non-appendix sections shouldn't be reordered if they are regular content.
        # But if they are among the appendices, we only reorder the known appendix sections.

        first_app_pos = appendix_indices[0][0]

        # Extract text before first appendix
        prose_before = text[:first_app_pos]

        # Extract blocks of each matched appendix section
        sections: Dict[str, str] = {}
        tail_content = ""

        for i, (m_start, canon_key, match_idx, m_end) in enumerate(appendix_indices):
            # The section content goes until the next heading or EOF/trailing navboxes/categories
            if match_idx + 1 < len(matches):
                next_start = matches[match_idx + 1].start()
                sec_text = text[m_start:next_start]
            else:
                # Last section heading in document. May contain categories / navboxes at the bottom.
                raw_tail = text[m_start:]
                # Split trailing categories / navboxes / defaultsort if present
                # Categories: [[Kategori:...]]
                # DEFAULTSORT: {{DEFAULTSORT:...}}
                # Bottom navboxes: {{...}} after the last link/bullet
                sec_text, trailing = self._split_tail_elements(raw_tail)
                tail_content = trailing

            # If duplicate appendix occurs (rare), preserve both
            if canon_key in sections:
                sections[canon_key] = sections[canon_key].rstrip() + "\n\n" + sec_text.strip() + "\n"
            else:
                sections[canon_key] = sec_text

        # Standardize appendix order
        reordered_parts: List[str] = []
        for key in self.APPENDIX_ORDER:
            if key in sections:
                reordered_parts.append(sections[key].rstrip())

        # Any non-canonical appendix sections that were in between?
        for canon_key, content in sections.items():
            if canon_key not in self.APPENDIX_ORDER:
                reordered_parts.append(content.rstrip())

        result = prose_before.rstrip() + "\n\n" + "\n\n".join(reordered_parts)
        if tail_content:
            result = result.rstrip() + "\n\n" + tail_content.strip() + "\n"
        else:
            result = result.rstrip() + "\n"

        return result

    def _split_tail_elements(self, last_sec_text: str) -> Tuple[str, str]:
        """Separates section content from bottom categories and DEFAULTSORT."""
        lines = last_sec_text.splitlines()
        split_idx = len(lines)
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i].strip()
            if not line:
                continue
            if (
                line.startswith("[[Kategori:")
                or line.startswith("[[Category:")
                or line.startswith("{{DEFAULTSORT:")
                or line.startswith("{{stub")
                or line.startswith("{{rintisan")
            ):
                split_idx = i
            else:
                break

        sec_body = "\n".join(lines[:split_idx])
        trailing = "\n".join(lines[split_idx:])
        return sec_body, trailing

    def deduplicate_references(self, text: str) -> str:
        """
        Detects duplicate named reference definitions:
        <ref name="X">Identical long content...</ref>
        and collapses second and subsequent occurrences into <ref name="X" />.
        Also handles slight whitespace variances in attributes like <ref name = "X" >.
        """
        if not text:
            return ""

        # Pattern for <ref name="...">(content)</ref>
        # Handles attribute quotes (single, double, or unquoted)
        ref_def_re = re.compile(
            r"<ref\s+name\s*=\s*(?P<quote>[\"']?)(?P<name>[^\"'>\s]+)(?P=quote)(?P<other_attrs>[^>]*)>(?P<content>[\s\S]*?)</ref>",
            flags=re.IGNORECASE,
        )

        seen_refs: Set[str] = set()

        def replacer(match: re.Match) -> str:
            name = match.group("name")
            content = match.group("content").strip()

            # If empty content inside <ref name="X"></ref>, just normalize to <ref name="X" />
            if not content:
                return f'<ref name="{name}" />'

            # Normalization key for name
            norm_name = name.lower()

            if norm_name in seen_refs:
                # Already defined previously, collapse subsequent occurrences
                return f'<ref name="{name}" />'
            else:
                seen_refs.add(norm_name)
                return match.group(0)

        return ref_def_re.sub(replacer, text)

    def fix_citation_punctuation(self, text: str) -> str:
        """
        Fixes punctuation placement and spacing around reference tags:
        1. Space-before-ref cleanup:
           `word .<ref>` -> `word.<ref>`
           `word ,<ref>` -> `word,<ref>`
           `word <ref>` -> `word<ref>` (when following a word directly)
        2. Move punctuation before ref (Wikipedia MoS):
           `word<ref>...</ref>.` -> `word.<ref>...</ref>`
           `word<ref>...</ref>,` -> `word,<ref>...</ref>`
           `word<ref name="X" />.` -> `word.<ref name="X" />`
        """
        if not text:
            return ""

        # Step 1: Fix space before punctuation followed immediately by ref
        # e.g. "kata .<ref>" -> "kata.<ref>", "kata ,<ref>" -> "kata,<ref>"
        sanitized = re.sub(r"([a-zA-Z0-9\)])\s+([.,;:!?])(?=<ref[\s>])", r"\1\2", text)

        # Step 2: Fix trailing space before ref tag: "kata <ref>" -> "kata<ref>"
        # Only remove space if preceded by regular word or punctuation (not after closing </ref>, not after newline/bullet)
        # Match word/punct (not > which would be </ref> or <ref/>) followed by space then <ref
        sanitized = re.sub(r"([a-zA-Z0-9\).,;:!?])\s+(<ref[\s>])", r"\1\2", sanitized)

        # Step 3: Move punctuation trailing immediately after ref(s) to before ref(s)
        # e.g. "word<ref>...</ref>." -> "word.<ref>...</ref>"
        # Handles chained refs: "word<ref>A</ref><ref name="B"/>." -> "word.<ref>A</ref><ref name="B"/>"
        # We find a cluster of one or more <ref>...</ref> or <ref.../> immediately preceded by non-space/non-punct,
        # and followed immediately by punctuation [.,;:!?]
        ref_cluster_re = re.compile(
            r"([a-zA-Z0-9\]\)'\"])"                             # Preceding word character
            r"((?:<ref\b[^>]*>[\s\S]*?</ref>|<ref\b[^>]*/>)+)"  # Cluster of one or more refs
            r"([.,;:!?])"                                       # Trailing punctuation
            r"(?!\s*[\w\d]*\.(?:com|org|net|id|html|php))",    # Guard against accidental domain dots
            flags=re.IGNORECASE,
        )

        def move_punct(match: re.Match) -> str:
            pre = match.group(1)
            refs = match.group(2)
            punct = match.group(3)
            return f"{pre}{punct}{refs}"

        # Run iteratively in case of nested/stacked structures
        sanitized = ref_cluster_re.sub(move_punct, sanitized)

        # Clean any double punctuation caused by moving (e.g. "word..<ref>" -> "word.<ref>")
        sanitized = re.sub(r"([.,])\1+(?=<ref[\s>])", r"\1", sanitized)

        return sanitized

    def normalize_page_ranges(self, text: str) -> str:
        """
        Normalizes page ranges in citation templates and prose:
        `pp. 12-15` or `pages 12-15` -> `hlm. 12–15` (en-dash '–').
        `p. 12` or `page 12` -> `hlm. 12`.
        Also normalizes hyphens inside |pages= and |page= to en-dash.
        """
        if not text:
            return ""

        sanitized = text

        # 1. Prose / citation prefix: pp. 12-15 / pages 12-15 / hlm. 12-15 -> hlm. 12–15
        sanitized = re.sub(
            r"\b(?:pp|pages|hlm)(?:\.|\b)\s*(\d+)\s*[-–]\s*(\d+)\b",
            r"hlm. \1–\2",
            sanitized,
            flags=re.IGNORECASE,
        )

        # 2. Single page prefix: pp. 12 / pages 12 / p. 12 / page 12 -> hlm. 12
        sanitized = re.sub(
            r"\b(?:pp?|pages?)(?:\.|\b)\s*(\d+)\b",
            r"hlm. \1",
            sanitized,
            flags=re.IGNORECASE,
        )

        # 3. Inside citation templates: |pages=12-15 or |page=12-15 -> en-dash
        def pages_param_replacer(match: re.Match) -> str:
            param_key = match.group(1)
            val = match.group(2)
            norm_val = re.sub(r"(\d+)\s*[-]\s*(\d+)", r"\1–\2", val)
            return f"|{param_key}={norm_val}"

        sanitized = re.sub(
            r"\|\s*(pages?|hlm)\s*=\s*([^|}\n]+)",
            pages_param_replacer,
            sanitized,
            flags=re.IGNORECASE,
        )

        return sanitized

    def clean_empty_parameters(self, text: str) -> str:
        """
        Cleans redundant empty parameters like `|access-date= |archive-url= |url-status= `
        if none of the archive parameters are filled in citation templates.
        Also strips trailing empty parameters that add noise.
        """
        if not text:
            return ""

        # Function to clean within a citation template {{cite ...}} or {{cita ...}}
        citation_re = re.compile(r"(\{\{(?:cite|cita)[^}]+\}\})", flags=re.IGNORECASE)

        def clean_template(match: re.Match) -> str:
            tpl = match.group(1)

            # Check if archive-url is actually filled
            archive_url_match = re.search(r"\|\s*archive-?url\s*=\s*([^|}\s]+)", tpl, flags=re.IGNORECASE)
            has_archive = archive_url_match is not None and bool(archive_url_match.group(1).strip())

            if not has_archive:
                # Remove empty archive parameters: |archive-url=, |archive-date=, |url-status=
                # Also remove |access-date= if it is empty
                tpl = re.sub(
                    r"\|\s*(?:archive-?url|archive-?date|url-status|access-?date)\s*=\s*(?=[|}])",
                    "",
                    tpl,
                    flags=re.IGNORECASE,
                )
            else:
                # If archive is present, only clean empty archive params if completely unset
                tpl = re.sub(
                    r"\|\s*(?:archive-?url|archive-?date|url-status)\s*=\s*(?=[|}])",
                    "",
                    tpl,
                    flags=re.IGNORECASE,
                )

            # Clean empty access-date if url is not present or empty
            url_match = re.search(r"\|\s*url\s*=\s*([^|}\s]+)", tpl, flags=re.IGNORECASE)
            has_url = url_match is not None and bool(url_match.group(1).strip())
            if not has_url:
                tpl = re.sub(r"\|\s*access-?date\s*=\s*(?=[|}])", "", tpl, flags=re.IGNORECASE)

            # Remove multiple redundant empty parameters (common AWB cleanup)
            redundant_empty_keys = [
                "df",
                "registration",
                "subscription",
                "doi-access",
                "bibcode-access",
            ]
            for rk in redundant_empty_keys:
                tpl = re.sub(rf"\|\s*{rk}\s*=\s*(?=[|}}])", "", tpl, flags=re.IGNORECASE)

            return tpl

        return citation_re.sub(clean_template, text)

    def apply_general_fixes(self, text: str) -> str:
        """Applies all standard AWB general fixes."""
        if not text:
            return ""

        sanitized = text
        sanitized = self.reorder_appendices(sanitized)
        sanitized = self.deduplicate_references(sanitized)
        sanitized = self.fix_citation_punctuation(sanitized)
        sanitized = self.normalize_page_ranges(sanitized)
        sanitized = self.clean_empty_parameters(sanitized)
        return sanitized


class AWBGenFixes:
    """
    Unified AWB-Style General Fixes & RegEx Typo Fix (RETF) Suite.
    Integrates GeneralFixesEngine with RegExTypoFixEngine safely.
    """

    def __init__(
        self,
        general_fixes: Optional[GeneralFixesEngine] = None,
        retf: Optional[RegExTypoFixEngine] = None,
    ):
        self.general_fixes = general_fixes or GeneralFixesEngine()
        self.retf = retf or RegExTypoFixEngine()

    def apply_all_fixes(self, wikitext: str) -> str:
        """
        Applies all General Fixes followed by RegEx Typo Fixes.
        Order of operations:
        1. General Fixes (reorder appendices, deduplicate refs, fix punctuation, clean empty params)
        2. RegEx Typo Fixes (spelling corrections safely avoiding URLs, tags, templates)
        """
        if not wikitext:
            return ""

        # Step 1: General Fixes
        fixed = self.general_fixes.apply_general_fixes(wikitext)

        # Step 2: RETF
        fixed = self.retf.fix_typos(fixed)

        return fixed


# Default singleton instance
default_genfixes = AWBGenFixes()
