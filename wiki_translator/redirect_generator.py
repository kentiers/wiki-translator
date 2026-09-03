"""
Indonesian Wikipedia Redirect Generator.

Generates official Indonesian Wikipedia redirect wikitext (`#ALIH [[...]]`) for
translated articles to maximize discoverability and ease of navigation.

Features:
- English source title redirect (e.g. `The Runner (2026 film)` -> `#ALIH [[The Runner (film 2026)]]`).
- Year format swap: `(YYYY film)` / `(YYYY television series)` -> `(film YYYY)` / `(serial televisi YYYY)`.
- Base title without disambiguator / year when unambiguous: `The Runner (film)`.
- Disambiguator translation: `(film)` -> `(film)`, `(miniseries)` -> `(miniseri)`, `(novel)` -> `(novel)`, etc.
- Punctuation & typography variations:
  * Standard vs curly quotes (" vs “ ”, ' vs ‘ ’)
  * Hyphen vs en-dash vs em-dash (- vs – vs —)
  * Colon spacing and ampersand vs "dan" / "and"
- Case variations:
  * All lowercase (e.g. standard capitalization redirect)
  * First letter capitalized
- Standard MediaWiki redirect template categories:
  * `{{Pengalihan dari nama bahasa Inggris}}`
  * `{{Pengalihan dari kapitalisasi lain}}`
  * `{{Pengalihan dari tanda baca lain}}`
  * `{{Pengalihan dengan pembeda}}`
  * `{{Pengalihan tanpa pembeda}}`
"""

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Dict, List, Optional, Set, Tuple


# Standard disambiguation mapping from English to Indonesian
DISAMBIGUATION_MAP = {
    "film": "film",
    "movie": "film",
    "television series": "serial televisi",
    "tv series": "serial televisi",
    "miniseries": "miniseri",
    "tv miniseries": "miniseri",
    "novel": "novel",
    "soundtrack": "jalur suara",
    "album": "album",
    "song": "lagu",
    "play": "sandiwara",
    "short story": "cerita pendek",
    "video game": "permainan video",
}


@dataclass
class RedirectItem:
    title: str
    wikitext: str
    reason: str


class RedirectGenerator:
    """Generates official Indonesian Wikipedia redirect wikitext."""

    def __init__(self):
        pass

    def _format_wikitext(self, target: str, template: Optional[str] = None) -> str:
        """Constructs standard #ALIH wikitext with optional redirect template."""
        clean_target = target.strip()
        lines = [f"#ALIH [[{clean_target}]]"]
        if template:
            clean_tmpl = template.strip()
            if not clean_tmpl.startswith("{{"):
                clean_tmpl = f"{{{{{clean_tmpl}}}}}"
            lines.append("")
            lines.append(clean_tmpl)
        return "\n".join(lines).strip()

    def generate_redirects(self, en_title: str, id_title: str) -> List[Dict[str, str]]:
        """
        Generates redirect candidates from English and Indonesian titles.

        Returns list of dicts:
        {"title": redirect_title, "wikitext": redirect_wikitext, "reason": reason_description}
        """
        en_title = en_title.strip()
        id_title = id_title.strip()
        if not id_title:
            return []

        seen_titles: Set[str] = {id_title}
        redirects: List[Dict[str, str]] = []

        def add_redirect(title: str, template: Optional[str], reason: str):
            clean = title.strip()
            if not clean or clean in seen_titles:
                return
            seen_titles.add(clean)
            wikitext = self._format_wikitext(id_title, template)
            redirects.append({
                "title": clean,
                "wikitext": wikitext,
                "reason": reason,
            })

        # 1. English Source Title Redirect
        if en_title and en_title != id_title:
            add_redirect(
                en_title,
                "Pengalihan dari nama bahasa Inggris",
                "Pengalihan dari judul asli bahasa Inggris",
            )

        # Parse disambiguation patterns from both titles
        # Pattern: "Base Title (Disambig)"
        # e.g. "The Runner (2026 film)", "The Runner (film 2026)", "Spider-Man (film)"
        en_match = re.match(r"^(.*?)\s*\(([^)]+)\)$", en_title)
        id_match = re.match(r"^(.*?)\s*\(([^)]+)\)$", id_title)

        base_en = en_match.group(1).strip() if en_match else en_title
        disambig_en = en_match.group(2).strip() if en_match else ""

        base_id = id_match.group(1).strip() if id_match else id_title
        disambig_id = id_match.group(2).strip() if id_match else ""

        # 2. Year format swaps: "(YYYY film)" <-> "(film YYYY)", "(YYYY television series)" <-> "(serial televisi YYYY)"
        # Check en disambig: e.g. "2026 film" -> "film 2026", "2026 television series" -> "serial televisi 2026"
        year_type_match = re.match(r"^(\d{4})\s+(.+)$", disambig_en)
        if year_type_match:
            year, dtype = year_type_match.groups()
            id_dtype = DISAMBIGUATION_MAP.get(dtype.lower(), dtype)
            # Candidate 1: en base with Indonesian order: "Base (film YYYY)"
            candidate_en_swapped = f"{base_en} ({id_dtype} {year})"
            add_redirect(
                candidate_en_swapped,
                "Pengalihan dengan pembeda",
                "Pengalihan variasi pembeda tahun bahasa Indonesia untuk judul sumber",
            )
            # Candidate 2: id base with English order: "Base ID (YYYY film)"
            candidate_id_en_order = f"{base_id} ({year} {dtype})"
            add_redirect(
                candidate_id_en_order,
                "Pengalihan dengan pembeda",
                "Pengalihan variasi urutan tahun Inggris untuk judul Indonesia",
            )
            # Candidate 3: en base with original "(YYYY film)" if different from en_title
            candidate_en_orig = f"{base_en} ({year} {dtype})"
            add_redirect(
                candidate_en_orig,
                "Pengalihan dari nama bahasa Inggris",
                "Pengalihan judul bahasa Inggris dengan format tahun",
            )

        # Check id disambig: e.g. "film 2026" -> swap to "2026 film"
        type_year_match = re.match(r"^(.+)\s+(\d{4})$", disambig_id)
        if type_year_match:
            id_dtype, year = type_year_match.groups()
            # If id disambig is "film 2026", candidate "(2026 film)"
            en_dtype = "film"
            for k, v in DISAMBIGUATION_MAP.items():
                if v == id_dtype.lower():
                    en_dtype = k
                    break
            candidate_swapped = f"{base_id} ({year} {en_dtype})"
            add_redirect(
                candidate_swapped,
                "Pengalihan dengan pembeda",
                "Pengalihan format pembeda tahun alternatif",
            )

        # 3. Base Title without Year or Disambiguator
        # e.g. "The Runner (film 2026)" -> "The Runner (film)", "The Runner"
        if disambig_id:
            # Check if disambig contains year: e.g. "film 2026"
            if type_year_match:
                id_dtype, _ = type_year_match.groups()
                candidate_type_only = f"{base_id} ({id_dtype})"
                add_redirect(
                    candidate_type_only,
                    "Pengalihan dengan pembeda",
                    "Pengalihan tanpa tahun pembeda",
                )
            # Direct base title without any disambiguator
            add_redirect(
                base_id,
                "Pengalihan tanpa pembeda",
                "Pengalihan tanpa pembeda untuk judul Indonesia",
            )

        if disambig_en and base_en != base_id:
            if year_type_match:
                _, dtype = year_type_match.groups()
                id_dtype = DISAMBIGUATION_MAP.get(dtype.lower(), dtype)
                add_redirect(
                    f"{base_en} ({id_dtype})",
                    "Pengalihan dari nama bahasa Inggris",
                    "Pengalihan judul bahasa Inggris tanpa tahun",
                )
            add_redirect(
                base_en,
                "Pengalihan tanpa pembeda",
                "Pengalihan tanpa pembeda untuk judul bahasa Inggris",
            )

        # 4. Clean Punctuation Variations
        # For all registered redirects + base titles, generate punctuation variants
        current_candidates = [id_title, en_title] + [r["title"] for r in redirects]
        for cand in current_candidates:
            if not cand:
                continue

            # A. Quotes: curly “ ” -> " or ' ‘ ’
            has_curly_double = "“" in cand or "”" in cand
            has_curly_single = "‘" in cand or "’" in cand
            if has_curly_double:
                flat_quotes = cand.replace("“", '"').replace("”", '"')
                add_redirect(
                    flat_quotes,
                    "Pengalihan dari tanda baca lain",
                    "Pengalihan dari tanda kutip lurus",
                )
            if has_curly_single:
                flat_single = cand.replace("‘", "'").replace("’", "'")
                add_redirect(
                    flat_single,
                    "Pengalihan dari tanda baca lain",
                    "Pengalihan dari tanda petik lurus",
                )
            if '"' in cand:
                curly_quotes = cand.replace('"', "“")  # or standard pair
                # Replace pairs with curly
                parts = cand.split('"')
                if len(parts) >= 3:
                    rebuilt = []
                    for i, p in enumerate(parts):
                        rebuilt.append(p)
                        if i < len(parts) - 1:
                            rebuilt.append("“" if i % 2 == 0 else "”")
                    curly_str = "".join(rebuilt)
                    add_redirect(
                        curly_str,
                        "Pengalihan dari tanda baca lain",
                        "Pengalihan dari tanda kutip lengkung",
                    )
            if "'" in cand:
                # Common apostrophe variant e.g. "O'Connor" -> "O’Connor"
                curly_apostrophe = cand.replace("'", "’")
                add_redirect(
                    curly_apostrophe,
                    "Pengalihan dari tanda baca lain",
                    "Pengalihan dari tanda petik tunggal lengkung (apostrof)",
                )

            # B. Dashes: en-dash (–), em-dash (—), hyphen (-)
            if "–" in cand:
                hyphen_variant = cand.replace("–", "-")
                add_redirect(
                    hyphen_variant,
                    "Pengalihan dari tanda baca lain",
                    "Pengalihan dari tanda hubung biasa (pengganti en-dash)",
                )
            elif "—" in cand:
                hyphen_variant = cand.replace("—", "-")
                add_redirect(
                    hyphen_variant,
                    "Pengalihan dari tanda baca lain",
                    "Pengalihan dari tanda hubung biasa (pengganti em-dash)",
                )
            elif " - " in cand:
                endash_variant = cand.replace(" - ", " – ")
                add_redirect(
                    endash_variant,
                    "Pengalihan dari tanda baca lain",
                    "Pengalihan dari tanda pisah en-dash",
                )

            # C. Ampersand (& vs and / dan)
            if " & " in cand:
                dan_variant = cand.replace(" & ", " dan ")
                and_variant = cand.replace(" & ", " and ")
                add_redirect(
                    dan_variant,
                    "Pengalihan dari tanda baca lain",
                    "Pengalihan dari simbol ampersand ke 'dan'",
                )
                add_redirect(
                    and_variant,
                    "Pengalihan dari tanda baca lain",
                    "Pengalihan dari simbol ampersand ke 'and'",
                )

            # D. Colons with/without trailing space or subtitle separator
            if ": " in cand:
                nospace_colon = cand.replace(": ", ":")
                dash_colon = cand.replace(": ", " - ")
                add_redirect(
                    dash_colon,
                    "Pengalihan dari tanda baca lain",
                    "Pengalihan dari tanda pisah sebagai pengganti titik dua",
                )

        # 5. Case Variations
        # Add lowercase / capitalized variations of id_title and en_title
        for cand in [id_title, en_title]:
            if not cand:
                continue
            # Capitalize only first letter (sentence case)
            first_upper = cand[0].upper() + cand[1:].lower() if len(cand) > 1 else cand.upper()
            if first_upper != cand and first_upper != id_title:
                add_redirect(
                    first_upper,
                    "Pengalihan dari kapitalisasi lain",
                    "Pengalihan dari kapitalisasi kalimat",
                )
            # All lowercase (except title case first character if wiki standard)
            all_lower = cand.lower()
            if all_lower != cand.lower():
                pass
            # Also check if title is ALL CAPS
            if cand.isupper() and len(cand) > 3:
                title_case = cand.title()
                add_redirect(
                    title_case,
                    "Pengalihan dari kapitalisasi lain",
                    "Pengalihan dari format huruf judul ke huruf besar",
                )

        return redirects

    def save_redirects(self, redirects: List[Dict[str, str]], output_dir: Path) -> List[Path]:
        """
        Saves redirect files to output_dir/redirects/<SafeName>.wikitext.

        Returns list of saved Paths.
        """
        out_dir = Path(output_dir)
        target_dir = out_dir / "redirects"
        target_dir.mkdir(parents=True, exist_ok=True)

        saved_files: List[Path] = []
        for red in redirects:
            title = red.get("title", "")
            wikitext = red.get("wikitext", "")
            if not title or not wikitext:
                continue

            # Safe filename: sanitize colons, slashes, quotes, and question marks
            safe_name = re.sub(r'[\\/*?:"<>|]', "_", title).strip()
            if not safe_name:
                safe_name = "redirect"
            
            file_path = target_dir / f"{safe_name}.wikitext"
            file_path.write_text(wikitext, encoding="utf-8")
            saved_files.append(file_path)

        return saved_files


default_redirect_generator = RedirectGenerator()
