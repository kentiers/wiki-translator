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
import mwparserfromhell
from .slop_linter import default_slop_linter
from .gramatika_engine import default_gramatika_engine
from .eyd_engine import default_eyd_engine
from .historical_ethnonyms import default_ethnonyms_manager
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
    "cendikiawan": "cendekiawan",
    # D
    "debet": "debit",
    "dekrit": "dekret",
    "definitif": "definitif",
    "deterjen": "detergen",
    "diagnosa": "diagnosis",
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
    "katagori": "kategori",
    "khotbah": "khotbah",
    "komplit": "komplet",
    "kongkrit": "konkret",
    "konsekwen": "konsekuen",
    "kreatip": "kreatif",
    "kreatifitas": "kreativitas",
    "kwalitas": "kualitas",
    "kwitansi": "kuitansi",
    "kwantitas": "kuantitas",
    "kolektip": "kolektif",
    "korma": "kurma",
    # L
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
    "mateng": "matang",
    "mempesona": "memesona",
    "mempengaruhi": "memengaruhi",
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
    "nasehat": "nasihat",
    "negosiasi": "negosiasi",
    "negeri": "negeri",
    "nomor": "nomor",
    "nomer": "nomor",
    # O
    "obyek": "objek",
    "obyektif": "objektif",
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
    "pengrajin": "perajin",
    "pengrusakan": "perusakan",
    "penasehat": "penasihat",
    "perancis": "prancis",
    "peranti": "peranti",
    "piranti": "peranti",
    "plesir": "pelesir",
    "pondasi": "fondasi",
    "prakata": "prakata",
    "propinsi": "provinsi",
    "psikotest": "psikotes",
    # R
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
    "sekedar": "sekadar",
    "sekretaris": "sekretaris",
    "selebriti": "selebritas",
    "sepion": "spion",
    "silahkan": "silakan",
    "sistim": "sistem",
    "semidan": "semi dan",
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
    "turis": "turis",
    # U
    "ubah": "ubah",
    # "unta" is the standard Indonesian word for camel.
    "ustadz": "ustaz",
    "ustadzah": "ustazah",
    "ujud": "wujud",
    # V
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

        sanitized, protected_blocks = default_slop_linter._mask_protected_zones(text)

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

        return default_slop_linter._unmask_protected_zones(sanitized, protected_blocks)



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
        canonical_titles = set(appendix_canonical_map)
        for match in matches[first_app_idx:]:
            if match.group(2).strip().lower() not in canonical_titles:
                return text
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

        code = mwparserfromhell.parse(text)
        seen_refs = set()
        for tag in code.filter_tags():
            if str(tag.tag).lower() != "ref" or tag.self_closing or not tag.has("name"):
                continue
            name = str(tag.get("name").value).strip()
            group = str(tag.get("group").value).strip() if tag.has("group") else ""
            content = str(tag.contents).strip()
            # Names are case-sensitive and scoped by group. Conflicting bodies
            # must remain visible for review, never be silently discarded.
            key = (name, group, content)
            if content and key in seen_refs:
                tag.contents = ""
                tag.self_closing = True
                tag.padding = " "
            seen_refs.add(key)
        return str(code)

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
    def clean_duplicate_punctuation(self, text: str) -> str:
        """
        Cleans duplicate or misplaced punctuation in wikitext:
        1. Duplicate commas: `, ,` or `,,` -> `,`
        2. Stray space before punctuation: `word ,` -> `word,`, `word .` -> `word.`
        3. Comma followed by period: `,.` or `, .` -> `.`
        4. Duplicate periods: `..` (not ellipsis `...`) -> `.`
        """
        if not text:
            return ""

        # Protect math, code, nowiki, and ref blocks
        placeholders = []
        def mask(m: re.Match) -> str:
            placeholders.append(m.group(0))
            return f"__PUNCT_MASK_{len(placeholders) - 1}__"

        masked = re.sub(
            r"<(?:math|code|nowiki|syntaxhighlight)\b[^>]*>[\s\S]*?</(?:math|code|nowiki|syntaxhighlight)>|<ref\b[^>]*>[\s\S]*?</ref>|\[\[\s*(?:File|Berkas|Image|Gambar)\s*:[^|\n\]]+",
            mask,
            text,
            flags=re.IGNORECASE,
        )

        # 1. Clean spaces before punctuation: "kata ," -> "kata,", "kata ." -> "kata."
        masked = re.sub(r"([a-zA-Z0-9\]\)\'\"])\s+([,.:;!?])", r"\1\2", masked)

        # 2. Duplicate commas: ",," or ", ," -> ","
        masked = re.sub(r",\s*,+", ",", masked)

        # 3. Comma followed by period: ",." or ", ." -> "."
        masked = re.sub(r",\s*\.", ".", masked)

        # 4. Period followed by comma: ".," or ". ," -> "." (excluding initials like M.S., or A.B.,)
        masked = re.sub(r"(?<!\b[A-Z])\.\s*,", ".", masked)
        # 5. Double periods: ".." but not "..." or "...."
        masked = re.sub(r"(?<!\.)\.\.(?!\.)", ".", masked)

        # Restore placeholders
        for i, original in enumerate(placeholders):
            masked = masked.replace(f"__PUNCT_MASK_{i}__", original)

        return masked


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

    def normalize_bound_morphemes(self, text: str) -> str:
        """
        Normalizes separated bound morphemes according to EYD V.
        Bound prefixes (pasca-, antar-, non-, sub-, pra-, tuna-, multi-)
        must be written attached without space when followed by lowercase words:
        - pasca perang -> pascaperang
        - pasca pembunuhan -> pascapembunuhan
        - antar menteri -> antarmenteri
        - non bebas -> nonbebas
        - sub bagian -> subbagian
        Preserves hyphens before capitals or numbers (pasca-1945, non-Rusia).
        """
        if not text:
            return ""
        bound_re = re.compile(r"\b(pasca|antar|non|sub|pra|tuna|multi)\s+([a-z]{3,})\b", re.IGNORECASE)
        def repl(m: re.Match) -> str:
            prefix = m.group(1)
            word = m.group(2)
            if prefix.isupper():
                return f"{prefix}{word.upper()}"
            elif prefix[0].isupper():
                return f"{prefix.capitalize()}{word.lower()}"
            return f"{prefix.lower()}{word.lower()}"
        return bound_re.sub(repl, text)

    def apply_general_fixes(self, text: str) -> str:
        """Applies all standard AWB general fixes."""
        if not text:
            return ""

        sanitized = text
        sanitized = self.reorder_appendices(sanitized)
        sanitized = self.deduplicate_references(sanitized)
        sanitized = self.fix_citation_punctuation(sanitized)
        sanitized = self.clean_duplicate_punctuation(sanitized)
        sanitized = self.normalize_page_ranges(sanitized)
        sanitized = self.clean_empty_parameters(sanitized)
        sanitized = self.clean_deprecated_citation_parameters(sanitized)
        sanitized = self.glue_and_clean_references(sanitized)
        sanitized = self.purge_pleonastic_conjunctions(sanitized)
        sanitized = self.capitalize_geographic_proper_nouns(sanitized)
        sanitized = self.normalize_bound_morphemes(sanitized)
        sanitized = self.deduplicate_parallel_modifiers(sanitized)
        sanitized = self.clean_editorial_quote_brackets(sanitized)
        sanitized = self.clean_narrative_colons(sanitized)
        sanitized = self.clean_saling_pleonasm(sanitized)
        sanitized = self.clean_common_pleonasms(sanitized)
        sanitized = self.clean_age_phrasing(sanitized)
        sanitized = self.clean_family_name_footnotes(sanitized)
        sanitized = self.clean_image_directions(sanitized)
        sanitized = self.separate_fused_words(sanitized)
        from .lexical_register import default_lexical_reranker
        return sanitized

    def clean_editorial_quote_brackets(self, text: str) -> str:
        """
        Removes single editorial brackets inside quotation marks:
        e.g. '"tiga tokoh [feminis] terpenting"' -> '"tiga tokoh feminis terpenting"'
        Eliminates reader confusion with broken wikilinks [[...]].
        """
        if not text:
            return ""
        def repl(m: re.Match) -> str:
            inner = m.group(1)
            # Never corrupt double-bracket wikilinks [[...]] or piped links [[...|...]]
            cleaned_inner = re.sub(r"(?<!\[)\[([a-zA-Z\s]+)\](?!\])", r"\1", inner)
            return f'"{cleaned_inner}"'

        return re.sub(r'"([^"\n]+)"', repl, text)

    def separate_fused_words(self, text: str) -> str:
        """
        Separates common fused words where a space was accidentally dropped before conjunctions/prepositions.
        e.g. 'musim semidan musim panas' -> 'musim semi dan musim panas'
        """
        if not text:
            return ""
        # 1. Seasons + dan (musim semidan -> musim semi dan)
        text = re.sub(r"\b(musim\s+(?:semi|panas|gugur|dingin|hujan|kemarau))dan\b", r"\1 dan", text, flags=re.IGNORECASE)
        # 2. Pronouns + dan (inidan -> ini dan)
        text = re.sub(r"\b(ini|itu|saya|mereka|beliau)dan\b", r"\1 dan", text, flags=re.IGNORECASE)
        return text
    def clean_narrative_colons(self, text: str) -> str:
        """
        Splits narrative sentences where colons inappropriately continue subordinate clauses.
        E.g. 'mencatat bahwa A saling melengkapi: gagasan...' -> 'mencatat bahwa A saling melengkapi. Gagasan...'
        """
        if not text:
            return ""
        colon_pat = re.compile(r"(\b(?:bahwa|karena|sehingga)\b[^:!?\n]{15,}?):\s*([a-z])")
        def repl(m: re.Match) -> str:
            clause = m.group(1)
            nxt = m.group(2)
            return f"{clause}. {nxt.upper()}"
        return colon_pat.sub(repl, text)

    def clean_saling_pleonasm(self, text: str) -> str:
        """
        Removes pleonastic 'satu sama lain' when preceded by 'saling':
        E.g. 'saling melengkapi satu sama lain' -> 'saling melengkapi'
        """
        if not text:
            return ""
        return re.sub(r"\bsaling\s+(\w+)\s+satu\s+sama\s+lain\b", r"saling \1", text, flags=re.IGNORECASE)
    def clean_common_pleonasms(self, text: str) -> str:
        """
        Cleans recurring Indonesian pleonasms and synonym stacks:
        - 'kelak di kemudian hari' -> 'di kemudian hari'
        - 'hunian tempat tinggal' -> 'tempat tinggal'
        - 'memasuki usia 20-an tahun' -> 'memasuki usia 20-an'
        - '}} }}' -> '}}}}'
        """
        if not text:
            return ""
        text = re.sub(r"\bkelak\s+di\s+kemudian\s+hari\b", "di kemudian hari", text, flags=re.IGNORECASE)
        text = re.sub(r"\bhunian\s+tempat\s+tinggal\b", "tempat tinggal", text, flags=re.IGNORECASE)
        text = re.sub(r"\b(memasuki\s+usia\s+[a-zA-Z0-9\-–]+an)\s+tahun\b", r"\1", text, flags=re.IGNORECASE)
        text = re.sub(r"\}\}\s+\}\}", "}}}}", text)
        return text
    def clean_age_phrasing(self, text: str) -> str:
        """
        Cleans preposition collisions and calques in biographical age phrasing:
        - 'pada dalam usia' -> 'pada usia'
        - 'pada [Tanggal/Tahun] dalam usia X tahun' -> 'pada [Tanggal/Tahun] saat berusia X tahun'
        - 'dalam usia X tahun' -> 'saat berusia X tahun'
        """
        if not text:
            return ""
        text = re.sub(r"\bpada\s+dalam\s+usia\b", "pada usia", text, flags=re.IGNORECASE)
        text = re.sub(
            r"\b(pada\s+[^\n.,;]+?)\s+dalam\s+usia\s+(\d+)\s+tahun\b",
            r"\1 saat berusia \2 tahun",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\bdalam\s+usia\s+(\d+)\s+tahun\b",
            r"saat berusia \1 tahun",
            text,
            flags=re.IGNORECASE,
        )
        return text
    def clean_family_name_footnotes(self, text: str) -> str:
        """
        Cleans and delinks family name footnote templates:
        {{Family name footnote|Vasilievna|[[Stasov]]a|lang=Eastern Slavic}}
        -> {{Family name footnote|Vasilievna|Stasova|lang=Slavia Timur}}
        Eliminates broken trailing letters (e.g. Stasov [en; ru]a) and ensures proper Indonesian labeling.
        """
        if not text:
            return ""
        if "Family name footnote" not in text and "family name footnote" not in text and "Eastern Slavic name" not in text:
            return text
        try:
            parsed = mwparserfromhell.parse(text)
            for tpl in parsed.filter_templates():
                tname = tpl.name.strip().lower()
                if tname in ("family name footnote", "eastern slavic name", "slavic name"):
                    if len(tpl.params) >= 2:
                        param2 = str(tpl.params[1].value).strip()
                        # If wrapped with multi-language ill including ru disambiguation, clean to en-only with proper label
                        if "{{ill" in param2.lower():
                            param2 = re.sub(
                                r"\{\{ill\|([^|}]+)\|en\|([^|}]+)(?:\|[a-z]{2,3}\|[^|}]+)*\}\}([a-zA-Z]*)",
                                r"{{ill|\1\3|en|\2}}",
                                param2,
                            )
                        elif "[[" in param2:
                            param2 = re.sub(r"\[\[([^\]|]+)\]\]([a-zA-Z]*)", r"{{ill|\1\2|en|\1}}", param2)
                        tpl.params[1].value = param2
                    if tpl.has("lang"):
                        lval = str(tpl.get("lang").value).strip().lower()
                        if lval in ("eastern slavic", "slavic", "eastern slavic naming customs"):
                            tpl.get("lang").value = "Slavia Timur"
            return str(parsed)
        except Exception:
            return text
    def clean_image_directions(self, text: str) -> str:
        """
        Standardizes directional markers inside image captions and multi-image templates:
        - (left) -> (kiri)
        - (right) -> (kanan)
        - (center) / (centre) -> (tengah)
        - (top) -> (atas)
        - (bottom) -> (bawah)
        - (from left to right) -> (dari kiri ke kanan)
        - (clockwise from top left) -> (searah jarum jam dari kiri atas)
        """
        if not text:
            return ""
        subs = [
            (r"\((?:left|on the left)\)", "(kiri)"),
            (r"\((?:right|on the right)\)", "(kanan)"),
            (r"\((?:center|centre|in the middle)\)", "(tengah)"),
            (r"\((?:top|above)\)", "(atas)"),
            (r"\((?:bottom|below)\)", "(bawah)"),
            (r"\(clockwise\s+from\s+(?:top\s+left|above)\)", "(searah jarum jam dari kiri atas)"),
            (r"\(from\s+left\s+to\s+right\)", "(dari kiri ke kanan)"),
        ]
        for pat, repl in subs:
            text = re.sub(pat, repl, text, flags=re.IGNORECASE)
        return text





    def deduplicate_parallel_modifiers(self, text: str) -> str:
        """
        Deduplicates redundant repeated modifiers across coordinated nouns.
        E.g. 'persahabatan erat serta persekutuan erat' -> 'persahabatan serta persekutuan erat'
        """
        if not text:
            return ""
        dup_mod_re = re.compile(r"\b(\w+)\s+([a-zA-Z]{3,})\s+(dan|serta)\s+(\w+)\s+\2\b", re.IGNORECASE)
        def repl(m: re.Match) -> str:
            n1, mod, conj, n2 = m.group(1), m.group(2), m.group(3), m.group(4)
            return f"{n1} {conj} {n2} {mod}"
        return dup_mod_re.sub(repl, text)
    def purge_pleonastic_conjunctions(self, text: str) -> str:
        """
        Removes pleonastic duplicate conjunctions prohibited in EYD V:
        - Walaupun/Meskipun/Kendati..., tetapi/namun... -> Walaupun/Meskipun..., ...
        - Karena/Sebab..., maka... -> Karena/Sebab..., ...
        """
        if not text:
            return ""
        text = re.sub(r"\b(Walaupun|Meskipun|Kendati|Biarpun|Sungguhpun)\s+([^,\n]+),\s*(?:tetapi|namun)\s+", r"\1 \2, ", text)
        text = re.sub(r"\b(walaupun|meskipun|kendati|biarpun|sungguhpun)\s+([^,\n]+),\s*(?:tetapi|namun)\s+", r"\1 \2, ", text)
        text = re.sub(r"\b(Karena|Sebab)\s+([^,\n]+),\s*maka\s+", r"\1 \2, ", text)
        text = re.sub(r"\b(karena|sebab)\s+([^,\n]+),\s*maka\s+", r"\1 \2, ", text)
        return text

    def glue_and_clean_references(self, text: str) -> str:
        """
        Standardizes Wikipedia reference tag spacing and placement:
        - Glues <ref> tags tightly to preceding punctuation without whitespace.
        - Removes whitespace between adjacent <ref> tags (<ref.../> <ref.../> -> <ref.../><ref.../>).
        - Deduplicates identical adjacent self-closing <ref> tags.
        """
        if not text:
            return ""
        # Remove whitespace between punctuation/word and <ref>
        text = re.sub(r"([.,;?!a-zA-Z0-9])\s+<ref\b", r"\1<ref", text)
        # Remove whitespace between adjacent <ref> tags
        text = re.sub(r"(</ref>|/>)\s+<ref\b", r"\1<ref", text)
        # Deduplicate identical adjacent self-closing refs: e.g. <ref name=":1" /><ref name=":1" />
        text = re.sub(r'(<ref\s+name=[\"\'][^\"\'\s/>]+[\"\']\s*/>)\s*\1', r"\1", text)
        return text

    def capitalize_geographic_proper_nouns(self, text: str) -> str:
        """
        Capitalizes geographic feature terms directly preceding a proper noun name per EYD V:
        - sungai Nil -> Sungai Nil
        - pulau Jawa -> Pulau Jawa
        - selat Sunda -> Selat Sunda
        - gunung Krakatau -> Gunung Krakatau
        - danau Toba -> Danau Toba
        - laut Jawa -> Laut Jawa
        """
        if not text:
            return ""
        geo_pattern = re.compile(
            r"\b(sungai|pulau|selat|gunung|teluk|danau|laut|bukit|lembah|samudra|tanjung)\s+([A-Z][a-z]+)\b"
        )
        return geo_pattern.sub(lambda m: f"{m.group(1).capitalize()} {m.group(2)}", text)

    def clean_deprecated_citation_parameters(self, text: str) -> str:
        """
        Cleans or modernizes deprecated citation parameters in wikitext:
        - |dead-url=no / |deadurl=no -> |url-status=live
        - |dead-url=yes / |deadurl=yes -> |url-status=dead
        - Removes redundant |language=en / |language=English (default in idwiki)
        """
        if not text:
            return ""
        text = re.sub(r"\|\s*dead-?url\s*=\s*(?:no|tidak)\b", "|url-status=live", text, flags=re.IGNORECASE)
        text = re.sub(r"\|\s*dead-?url\s*=\s*(?:yes|ya)\b", "|url-status=dead", text, flags=re.IGNORECASE)
        text = re.sub(r"\|\s*language\s*=\s*(?:en|english|bahasa inggris)\s*(?=[|}])", "", text, flags=re.IGNORECASE)
        return text

    def clean_overlinked_wikilinks(self, text: str, window_paragraphs: int = 2) -> str:
        """
        Removes duplicate wikilinks to the same page target within a sliding window of paragraphs
        according to WP:PRANALA (Overlinking guideline).
        Preserves first link per section, categories, infoboxes, and tables.
        """
        if not text:
            return ""
        paragraphs = re.split(r"(\n\s*\n)", text)
        cleaned_parts = []
        recent_links: Dict[str, int] = {}
        link_pattern = re.compile(r"\[\[\s*([^|\]\n:]+)(?:\|([^\]\n]+))?\s*\]\]")

        p_counter = 0
        for part in paragraphs:
            if not part.strip():
                cleaned_parts.append(part)
                continue

            p_counter += 1
            lines = part.split("\n")
            clean_lines = []
            for line in lines:
                # Skip headings, tables, templates, categories
                if line.strip().startswith(("==", "{|", "|", "!", "[[Kategori:", "[[Category:", "{{")):
                    if line.strip().startswith("=="):
                        recent_links.clear()
                    clean_lines.append(line)
                    continue

                def repl(m: re.Match) -> str:
                    target = m.group(1).strip()
                    alias = m.group(2).strip() if m.group(2) else target
                    norm_target = target.lower()

                    if norm_target in recent_links and (p_counter - recent_links[norm_target]) < window_paragraphs:
                        return alias

                    recent_links[norm_target] = p_counter
                    return m.group(0)

                clean_lines.append(link_pattern.sub(repl, line))
            cleaned_parts.append("\n".join(clean_lines))

        return "".join(cleaned_parts)

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
        3. Gramatika Engine (TBBBI / Kateglo: sentence opener conjunctions, negation agreement, adversarial commas)
        4. EYD V Engine (bound morphemes, particle pun, en-dash ranges)
        5. Historical Disambiguation Guardrail (homonym / false conflation protection)
        """
        if not wikitext:
            return ""
        # Step 1: General Fixes
        fixed = self.general_fixes.apply_general_fixes(wikitext)

        # Step 2: RETF
        fixed = self.retf.fix_typos(fixed)

        # Step 3: Gramatika Engine (TBBBI rules)
        fixed, _, _ = default_gramatika_engine.apply_all_gramatika_fixes(fixed)

        # Step 4: EYD V Engine (Official orthography)
        fixed, _, _ = default_eyd_engine.apply_all_eyd_fixes(fixed)

        # Step 5: Historical Disambiguation Guardrail (Zero-Blunder)
        fixed, _, _ = default_ethnonyms_manager.audit_and_fix_homonym_blunders(fixed)

        return fixed

# Default singleton instance
default_genfixes = AWBGenFixes()
