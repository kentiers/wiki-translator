"""
Conservative Infobox Parameter Normalizer & Mapper for Indonesian Wikipedia.

Features:
1. Canonical English Infobox Parameter Enforcement:
   - On id.wikipedia.org, most Lua-based infobox templates (such as Template:Infobox film,
     Template:Infobox person, etc.) are direct forks of en.wiki templates and ONLY accept
     canonical English parameter names (e.g., director, producer, starring, runtime, etc.).
   - If parameter names are translated to Indonesian, the infobox displays red Lua error
     warnings ("parameter tidak dikenal: sutradara, produser, pemeran...").
   - Automatically normalizes/maps any translated Indonesian keys back to standard English keys:
     * sutradara -> director
     * produser -> producer
     * penulis -> writer
     * skenario -> screenplay
     * cerita -> story
     * pemeran -> starring
     * musik -> music
     * sinematografi -> cinematography
     * penyuntingan -> editing
     * studio / perusahaan_produksi -> studio
     * tanggal_rilis -> release_date
     * durasi -> runtime
     * negara -> country
     * bahasa -> language
     * anggaran -> budget
     * pendapatan_kotor -> gross
     * nama -> name
     * nama_lahir -> birth_name
     * tanggal_lahir -> birth_date
     * tempat_lahir -> birth_place
     * tanggal_kematian -> death_date
     * tempat_kematian -> death_place
     * kebangsaan -> nationality
     * kewarganegaraan -> citizenship
     * pekerjaan -> occupation
     * pasangan -> spouse
     * anak -> children
     * orang_tua -> parents
     * almamater -> alma_mater

2. Unit and Currency Localization:
   - Automatically applies unit & currency localization to values of parameters
     known to contain currency or measurements (such as budget, gross, height, weight, etc.),
     or any parameter values while safeguarding wikitext links/refs/nested templates
     (e.g., `$50 million` -> `US$50 juta`).
"""

import re
from typing import Dict, List, Optional, Tuple

from .unit_converter import UnitCurrencyLocalizer, default_unit_converter


# Mapping from Indonesian translated infobox keys back to canonical English parameter names
INDONESIAN_TO_ENGLISH_INFOBOX_KEYS: Dict[str, str] = {
    # Film & Media
    "sutradara": "director",
    "produser": "producer",
    "produser_eksekutif": "executive_producer",
    "penulis": "writer",
    "skenario": "screenplay",
    "cerita": "story",
    "pemeran": "starring",
    "narator": "narrator",
    "musik": "music",
    "sinematografi": "cinematography",
    "penyuntingan": "editing",
    "perusahaan_produksi": "studio",
    "tanggal_rilis": "release_date",
    "durasi": "runtime",
    "negara": "country",
    "bahasa": "language",
    "anggaran": "budget",
    "pendapatan_kotor": "gross",
    # Person / Biography
    "nama": "name",
    "nama_lahir": "birth_name",
    "tanggal_lahir": "birth_date",
    "tempat_lahir": "birth_place",
    "tanggal_kematian": "death_date",
    "tempat_kematian": "death_place",
    "kebangsaan": "nationality",
    "kewarganegaraan": "citizenship",
    "pekerjaan": "occupation",
    "pasangan": "spouse",
    "anak": "children",
    "orang_tua": "parents",
    "ayah": "father",
    "ibu": "mother",
    "almamater": "alma_mater",
    "pendidikan": "education",
    "dikenal_karena": "known_for",
    "tempat_istirahat": "resting_place",
    "kekayaan_bersih": "net_worth",
    "tinggi": "height",
    "berat": "weight",
    # TV / Series
    "pencipta": "creator",
    "pengembang": "developer",
    "pencipta_lagu_tema": "theme_music_composer",
    "jumlah_musim": "num_seasons",
    "jumlah_episode": "num_episodes",
    "jaringan": "network",
    "tayang_perdana": "first_aired",
    "tayang_terakhir": "last_aired",
    # Books / Publications
    "judul": "title",
    "ilustrator": "illustrator",
    "perancang_sampul": "cover_artist",
    "seri": "series",
    "genre": "genre",
    "penerbit": "publisher",
    "tanggal_terbit": "pub_date",
    "halaman": "pages",
    "isbn": "isbn",
}

# Common infobox name aliases mapping to canonical category
INFOBOX_TYPE_ALIASES: Dict[str, str] = {
    "infobox film": "film",
    "infobox movie": "film",
    "film infobox": "film",
    "kotak info film": "film",
    "infobox person": "person",
    "infobox people": "person",
    "kotak info orang": "person",
    "infobox biography": "person",
    "kotak info tokoh": "person",
    "infobox television": "television",
    "infobox tv": "television",
    "kotak info televisi": "television",
    "infobox book": "book",
    "kotak info buku": "book",
}

# Parameters whose values specifically benefit from unit/currency localization
VALUE_LOCALIZATION_PARAMS = {
    "budget",
    "anggaran",
    "gross",
    "pendapatan_kotor",
    "box_office",
    "net_worth",
    "kekayaan_bersih",
    "runtime",
    "running_time",
    "durasi",
    "height",
    "tinggi",
    "weight",
    "berat",
}


class InfoboxMapper:
    """
    Enforces canonical English infobox parameter names for id.wikipedia.org
    and localizes values (units, currency, etc.).
    """

    def __init__(self, unit_converter: Optional[UnitCurrencyLocalizer] = None):
        self.unit_converter = unit_converter or default_unit_converter

    def get_infobox_type(self, template_name: str) -> Optional[str]:
        """Returns the canonical infobox type (e.g. 'film', 'person') if recognized."""
        cleaned = template_name.strip().lower()
        return INFOBOX_TYPE_ALIASES.get(cleaned)

    def _split_template_parameters(self, args_body: str) -> List[Tuple[str, str, str, str]]:
        """
        Splits the arguments part of a template into parameter tuples:
        (raw_prefix, param_name, raw_delimiter, param_value)
        Taking into account nested templates {{...}}, tables {|...|}, and links [[...]].
        """
        if not args_body:
            return []

        chunks: List[str] = []
        depth_template = 0
        depth_link = 0
        cur: List[str] = []

        i = 0
        n = len(args_body)
        while i < n:
            if args_body.startswith("{{", i):
                depth_template += 1
                cur.append("{{")
                i += 2
            elif args_body.startswith("}}", i):
                depth_template = max(0, depth_template - 1)
                cur.append("}}")
                i += 2
            elif args_body.startswith("[[", i):
                depth_link += 1
                cur.append("[[")
                i += 2
            elif args_body.startswith("]]", i):
                depth_link = max(0, depth_link - 1)
                cur.append("]]")
                i += 2
            elif args_body[i] == "|" and depth_template == 0 and depth_link == 0:
                chunks.append("".join(cur))
                cur = []
                i += 1
            else:
                cur.append(args_body[i])
                i += 1

        chunks.append("".join(cur))

        parsed_params: List[Tuple[str, str, str, str]] = []
        for chunk in chunks:
            if not chunk.strip():
                # Plain separator or whitespace
                parsed_params.append(("", "", "", chunk))
                continue

            # Look for '=' at top-level
            depth_t = 0
            depth_l = 0
            eq_pos = -1
            for idx, ch in enumerate(chunk):
                if chunk.startswith("{{", idx):
                    depth_t += 1
                elif chunk.startswith("}}", idx):
                    depth_t = max(0, depth_t - 1)
                elif chunk.startswith("[[", idx):
                    depth_l += 1
                elif chunk.startswith("]]", idx):
                    depth_l = max(0, depth_l - 1)
                elif ch == "=" and depth_t == 0 and depth_l == 0:
                    eq_pos = idx
                    break

            if eq_pos != -1:
                key_part = chunk[:eq_pos]
                val_part = chunk[eq_pos + 1:]
                m_key = re.match(r"^(\s*)(.*?)(\s*)$", key_part, re.DOTALL)
                pre_ws = m_key.group(1) if m_key else ""
                clean_key = m_key.group(2) if m_key else key_part.strip()
                post_ws = m_key.group(3) if m_key else ""
                parsed_params.append((pre_ws, clean_key, f"{post_ws}=", val_part))
            else:
                parsed_params.append(("", "", "", chunk))

        return parsed_params

    def normalize_infobox_template(
        self, full_template: str, template_name: str, enforce_english_keys: bool = True
    ) -> str:
        """
        Normalizes a single infobox template string:
        - If enforce_english_keys is True, maps translated Indonesian keys back to canonical English.
        - Applies currency and unit localization to values while preserving wikitext markup.
        """
        inner = full_template[2:-2]
        pipe_pos = inner.find("|")
        if pipe_pos == -1:
            return full_template

        header_part = inner[:pipe_pos]
        args_body = inner[pipe_pos + 1:]

        parsed_params = self._split_template_parameters(args_body)

        reconstructed_args: List[str] = []
        for pre_ws, key, delim, val in parsed_params:
            if not key:
                reconstructed_args.append(val)
                continue

            normalized_key = key.lower().replace(" ", "_")
            new_key = key

            # Map Indonesian key back to canonical English if present
            if enforce_english_keys and normalized_key in INDONESIAN_TO_ENGLISH_INFOBOX_KEYS:
                new_key = INDONESIAN_TO_ENGLISH_INFOBOX_KEYS[normalized_key]
            # Unit & currency localization on value
            new_val = val
            if (
                normalized_key in VALUE_LOCALIZATION_PARAMS
                or new_key.lower() in VALUE_LOCALIZATION_PARAMS
            ):
                new_val = self.unit_converter.localize_currency_and_units(val)
            else:
                if any(sym in val for sym in ["$", "£", "€", "¥", "₹"]) or re.search(
                    r"\b(?:miles?|feet|inches?|lbs?|sq\s*mi)\b", val, re.IGNORECASE
                ):
                    new_val = self.unit_converter.localize_currency_and_units(val)

            # Infobox specific value localization (occupation, years_active, caption, known_for, citizenship, etc.)
            new_val = self.localize_infobox_value(new_key, new_val)

            reconstructed_args.append(f"{pre_ws}{new_key}{delim}{new_val}")

        joined_args = "|".join(reconstructed_args)
        return f"{{{{{header_part}|{joined_args}}}}}"
    def localize_infobox_value(self, param_key: str, value: str) -> str:
        """
        Localizes common English terms in infobox values into natural Indonesian,
        safeguarding wikilinks, references, and nested templates.
        """
        if not value or not value.strip():
            return value

        norm_key = param_key.strip().lower().replace(" ", "_")

        # Mask wikilinks [[...]], templates {{...}}, refs <ref>...</ref> and <ref.../>
        tokens: List[str] = []

        def mask_token(m: re.Match) -> str:
            placeholder = f"§§IBX_TOKEN_{len(tokens)}§§"
            tokens.append(m.group(0))
            return placeholder

        masked = re.sub(r"<!--[\s\S]*?-->|<ref\b[^>]*>[\s\S]*?</ref>|<ref\b[^>]*/>|\[\[[^\]]+\]\]|\{\{[^\}]+\}\}", mask_token, value)

        if norm_key in ("occupation", "pekerjaan"):
            # Occupations translation
            occ_subs = [
                (r"\bFilm director\b", "Sutradara film"),
                (r"\bTelevision director\b", "Sutradara televisi"),
                (r"\bdirector\b", "sutradara"),
                (r"\bDirector\b", "Sutradara"),
                (r"\bproducer\b", "produser"),
                (r"\bProducer\b", "Produser"),
                (r"\bscreenwriter\b", "penulis skenario"),
                (r"\bScreenwriter\b", "Penulis skenario"),
                (r"\bwriter\b", "penulis"),
                (r"\bWriter\b", "Penulis"),
                (r"\bactor\b", "pemeran"),
                (r"\bActor\b", "Pemeran"),
                (r"\bactress\b", "pemeran"),
                (r"\bActress\b", "Pemeran"),
                (r"\bmusician\b", "musisi"),
                (r"\bMusician\b", "Musisi"),
                (r"\bsinger\b", "penyanyi"),
                (r"\bSinger\b", "Penyanyi"),
                (r"\bauthor\b", "penulis"),
                (r"\bAuthor\b", "Penulis"),
                (r"\bjournalist\b", "wartawan"),
                (r"\bJournalist\b", "Wartawan"),
            ]
            for pat, repl in occ_subs:
                masked = re.sub(pat, repl, masked)

        elif norm_key in ("years_active", "tahun_aktif"):
            # years_active: YYYY–present / YYYY-present -> YYYY–sekarang
            masked = re.sub(r"([–\-\s])present\b", r"\1sekarang", masked, flags=re.IGNORECASE)

        elif norm_key in ("caption", "keterangan"):
            # caption: Name in YYYY -> Name pada tahun YYYY
            masked = re.sub(r"\bin\s+(\d{4})\b", r"pada tahun \1", masked, flags=re.IGNORECASE)
            masked = re.sub(r"\bat\s+the\b", "di", masked, flags=re.IGNORECASE)
            masked = re.sub(r"\bat\b", "di", masked, flags=re.IGNORECASE)

        elif norm_key in ("known_for", "dikenal_karena", "dikenal_atas"):
            # known_for: X in Y -> X dalam Y
            masked = re.sub(r"\bin\b", "dalam", masked, flags=re.IGNORECASE)

        elif norm_key in ("citizenship", "kewarganegaraan"):
            # | citizenship = United Kingdom -> | citizenship = Britania Raya
            country_subs = [
                (r"\bUnited Kingdom\b", "Britania Raya"),
                (r"\bGreat Britain\b", "Britania Raya"),
                (r"\bUnited States\b", "Amerika Serikat"),
                (r"\bScotland\b", "Skotlandia"),
                (r"\bEngland\b", "Inggris"),
            ]
            for pat, repl in country_subs:
                masked = re.sub(pat, repl, masked, flags=re.IGNORECASE)

        elif norm_key in ("relatives", "kerabat", "family", "keluarga", "parents", "orang_tua", "children", "anak", "spouse", "pasangan"):
            # Kinship terms translation in infoboxes
            kinship_subs = [
                (r"\(\s*brother\s*\)", "(saudara)"),
                (r"\(\s*sister\s*\)", "(saudari)"),
                (r"\(\s*father\s*\)", "(ayah)"),
                (r"\(\s*mother\s*\)", "(ibu)"),
                (r"\(\s*grandfather\s*\)", "(kakek)"),
                (r"\(\s*grandmother\s*\)", "(nenek)"),
                (r"\(\s*son\s*\)", "(putra)"),
                (r"\(\s*daughter\s*\)", "(putri)"),
                (r"\(\s*husband\s*\)", "(suami)"),
                (r"\(\s*wife\s*\)", "(istri)"),
                (r"\(\s*cousin\s*\)", "(sepupu)"),
                (r"\(\s*uncle\s*\)", "(paman)"),
                (r"\(\s*aunt\s*\)", "(bibi)"),
            ]
            for pat, repl in kinship_subs:
                masked = re.sub(pat, repl, masked, flags=re.IGNORECASE)

        elif norm_key in ("birth_place", "tempat_lahir", "death_place", "tempat_kematian", "resting_place", "tempat_istirahat", "place_of_birth", "place_of_death"):
            # Country / place names translation
            place_subs = [
                (r"\bScotland\b", "Skotlandia"),
                (r"\bEngland\b", "Inggris"),
                (r"\bUnited States\b", "Amerika Serikat"),
                (r"\bUnited Kingdom\b", "Britania Raya"),
                (r"\bGreat Britain\b", "Britania Raya"),
            ]
            for pat, repl in place_subs:
                masked = re.sub(pat, repl, masked, flags=re.IGNORECASE)

        # General replacements for any param if matched
        masked = re.sub(r"([–\-\s])present\b", r"\1sekarang", masked, flags=re.IGNORECASE)
        # Kinship terms general check (e.g. if in other parameters)
        kinship_general = [
            (r"\(\s*brother\s*\)", "(saudara)"),
            (r"\(\s*sister\s*\)", "(saudari)"),
            (r"\(\s*father\s*\)", "(ayah)"),
            (r"\(\s*mother\s*\)", "(ibu)"),
            (r"\(\s*grandfather\s*\)", "(kakek)"),
            (r"\(\s*grandmother\s*\)", "(nenek)"),
            (r"\(\s*son\s*\)", "(putra)"),
            (r"\(\s*daughter\s*\)", "(putri)"),
            (r"\(\s*husband\s*\)", "(suami)"),
            (r"\(\s*wife\s*\)", "(istri)"),
            (r"\(\s*cousin\s*\)", "(sepupu)"),
            (r"\(\s*uncle\s*\)", "(paman)"),
            (r"\(\s*aunt\s*\)", "(bibi)"),
        ]
        for pat, repl in kinship_general:
            masked = re.sub(pat, repl, masked, flags=re.IGNORECASE)
        # Restore tokens
        # Also inspect inside tokens: if token is {{hlist|...}}, {{plainlist|...}}, {{nowrap|...}}, etc.
        for i, tok in enumerate(tokens):
            if tok.startswith("{{"):
                tok_lower = tok.lower()
                if any(k in tok_lower for k in ("hlist", "plainlist", "flatlist", "nowrap")):
                    tok = re.sub(r"\bUnited Kingdom\b", "Britania Raya", tok, flags=re.IGNORECASE)
                    tok = re.sub(r"\bUnited States\b", "Amerika Serikat", tok, flags=re.IGNORECASE)
                    tok = re.sub(r"\bScotland\b", "Skotlandia", tok, flags=re.IGNORECASE)
                    tok = re.sub(r"\bEngland\b", "Inggris", tok, flags=re.IGNORECASE)
                    # Also kinship if inside nowrap or list
                    for pat, repl in kinship_general:
                        tok = re.sub(pat, repl, tok, flags=re.IGNORECASE)
            masked = masked.replace(f"§§IBX_TOKEN_{i}§§", tok)

        return masked

    def normalize_infobox_keys(self, wikitext: str) -> str:
        """
        Scans wikitext for Infobox templates and restores translated Indonesian keys
        back to standard English parameter names, while localizing values (currency/units).
        """
        return self._process_infoboxes_in_wikitext(wikitext, enforce_english_keys=True)

    def map_infobox_parameters(self, wikitext: str) -> str:
        """
        Processes infoboxes: enforces canonical English keys and localizes units/currency.
        Alias for normalize_infobox_keys to maintain backwards compatibility.
        """
        return self.normalize_infobox_keys(wikitext)

    def _process_infoboxes_in_wikitext(self, wikitext: str, enforce_english_keys: bool = True) -> str:
        if not wikitext:
            return wikitext

        # Protect HTML comments
        protected_comments: List[str] = []

        def comment_sub(m: re.Match) -> str:
            placeholder = f"__INFOBOX_COMMENT_{len(protected_comments)}__"
            protected_comments.append(m.group(0))
            return placeholder

        sanitized = re.sub(r"<!--[\s\S]*?-->", comment_sub, wikitext)

        pos = 0
        length = len(sanitized)
        output_chunks: List[str] = []

        while pos < length:
            start = sanitized.find("{{", pos)
            if start == -1:
                output_chunks.append(sanitized[pos:])
                break

            output_chunks.append(sanitized[pos:start])

            depth = 1
            idx = start + 2
            while idx < length and depth > 0:
                if sanitized.startswith("{{", idx):
                    depth += 1
                    idx += 2
                elif sanitized.startswith("}}", idx):
                    depth -= 1
                    idx += 2
                else:
                    idx += 1

            if depth == 0:
                full_tmpl = sanitized[start:idx]
                inner = full_tmpl[2:-2].strip()
                pipe_pos = inner.find("|")
                if pipe_pos != -1:
                    tmpl_name = inner[:pipe_pos].strip()
                else:
                    tmpl_name = inner.strip()

                if (
                    "infobox" in tmpl_name.lower()
                    or "kotak info" in tmpl_name.lower()
                    or self.get_infobox_type(tmpl_name)
                ):
                    mapped_tmpl = self.normalize_infobox_template(
                        full_tmpl, tmpl_name, enforce_english_keys=enforce_english_keys
                    )
                    output_chunks.append(mapped_tmpl)
                else:
                    output_chunks.append(full_tmpl)

                pos = idx
            else:
                output_chunks.append(sanitized[start : start + 2])
                pos = start + 2

        result = "".join(output_chunks)

        for idx in range(len(protected_comments) - 1, -1, -1):
            result = result.replace(f"__INFOBOX_COMMENT_{idx}__", protected_comments[idx])

        return result


default_infobox_mapper = InfoboxMapper()
