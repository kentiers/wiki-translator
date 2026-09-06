"""
Film Categorization Normalizer & Decomposer for Indonesian Wikipedia (id.wikipedia.org).

Implements the official consensus established at Wikipedia:ProyekWiki Film/Kategorisasi
(Bennylin 2022, Gnolihz 2026, and Wikipedia ID film community consensus):

Core Consensus Rules:
1. 1-Level Genre Constraint (Anti-Intersectionality):
   - Multi-genre categories are strictly prohibited (e.g., no 'Film aksi fiksi ilmiah', no 'Film drama komedi').
   - Genre + Year combinations are prohibited (e.g., no 'Film laga tahun 2024').
   - Genre + Country combinations are prohibited (e.g., no 'Film laga Amerika Serikat').
   - Solution: Decompose into independent level-1 categories (e.g., [[Kategori:Film laga]], [[Kategori:Film fiksi ilmiah]]).
2. Level-2 Combination Allowed: Country + Year:
   - Format: [[Kategori:Film <negara> tahun <tahun>]] (e.g. [[Kategori:Film Indonesia tahun 2021]], [[Kategori:Film Amerika Serikat tahun 2024]]).
3. Standardized Genre Vocabulary:
   - Action -> Film laga (not film aksi / aksi laga).
   - Thriller -> Film cerita seru (not film thriller / tegang).
   - Sci-Fi -> Film fiksi ilmiah (not sains fiksi).
   - Romance -> Film romantis (not film roman / percintaan).
   - Live-action -> Film peran hidup (not aksi langsung / laga hidup).
   - Superhero -> Film pahlawan super.
4. Standardized Topic Categories:
   - Topic categories must follow: Film tentang <topik> (e.g. Film tentang Natal, Film tentang perampokan, Film tentang basket, Film tentang silat).
5. UK Entity Merging:
   - Films from England, Scotland, Wales, Northern Ireland must be unified under Britania Raya (e.g. Film Britania Raya tahun 2024).
"""

import re
from typing import Dict, Iterable, List, Optional, Set, Tuple


STANDARD_FILM_GENRES: Dict[str, str] = {
    # Action & Adventure
    "action": "Film laga",
    "aksi": "Film laga",
    "laga": "Film laga",
    "adventure": "Film petualangan",
    "petualangan": "Film petualangan",
    "chase": "Film kejar-kejaran",
    "kejar-kejaran": "Film kejar-kejaran",

    # Thriller & Crime & Mystery
    "thriller": "Film cerita seru",
    "suspense": "Film cerita seru",
    "cerita seru": "Film cerita seru",
    "crime": "Film kriminal",
    "kriminal": "Film kriminal",
    "kejahatan": "Film kriminal",
    "mystery": "Film misteri",
    "misteri": "Film misteri",
    "detective": "Film detektif",
    "detektif": "Film detektif",
    "spy": "Film mata-mata",
    "mata-mata": "Film mata-mata",
    "noir": "Film noir",
    "gangster": "Film geng",
    "geng": "Film geng",

    # Comedy
    "romantic comedy": "Film komedi romantis",
    "romcom": "Film komedi romantis",
    "komedi romantis": "Film komedi romantis",
    "dark comedy": "Film komedi gelap",
    "black comedy": "Film komedi gelap",
    "komedi gelap": "Film komedi gelap",
    "comedy": "Film komedi",
    "komedi": "Film komedi",
    "parody": "Film parodi",
    "parodi": "Film parodi",
    "satire": "Film satir",
    "satir": "Film satir",

    # Drama & Romance
    "drama": "Film drama",
    "romance": "Film romantis",
    "romantic": "Film romantis",
    "romantis": "Film romantis",
    "melodrama": "Film melodrama",
    "erotic": "Film erotis",
    "erotis": "Film erotis",

    # Sci-Fi & Fantasy & Horror
    "science fiction": "Film fiksi ilmiah",
    "sci-fi": "Film fiksi ilmiah",
    "fiksi ilmiah": "Film fiksi ilmiah",
    "fantasy": "Film fantasi",
    "fantasi": "Film fantasi",
    "superhero": "Film pahlawan super",
    "pahlawan super": "Film pahlawan super",
    "monster": "Film monster",
    "tokusatsu": "Film tokusatsu",
    "super sentai": "Film Super Sentai",
    "horror": "Film horor",
    "horor": "Film horor",
    "slasher": "Film jagal",
    "jagal": "Film jagal",
    "body horror": "Film horor tubuh",
    "horor tubuh": "Film horor tubuh",

    # War, History, Western & Politics
    "war": "Film perang",
    "perang": "Film perang",
    "history": "Film sejarah",
    "historical": "Film sejarah",
    "sejarah": "Film sejarah",
    "epic": "Film epik",
    "epik": "Film epik",
    "western": "Film koboi",
    "koboi": "Film koboi",
    "political": "Film politik",
    "politik": "Film politik",
    "propaganda": "Film propaganda",

    # Martial Arts
    "martial arts": "Film seni bela diri",
    "seni bela diri": "Film seni bela diri",

    # Documentaries & Non-fiction
    "documentary": "Film dokumenter",
    "dokumenter": "Film dokumenter",
    "biographical": "Film biografi",
    "biopic": "Film biografi",
    "biografi": "Film biografi",

    # Miscellaneous
    "musical": "Film musikal",
    "musikal": "Film musikal",
    "sports": "Film olahraga",
    "sport": "Film olahraga",
    "olahraga": "Film olahraga",
    "disaster": "Film bencana",
    "bencana": "Film bencana",
    "independent": "Film independen",
    "indie": "Film independen",
    "independen": "Film independen",
    "short": "Film pendek",
    "pendek": "Film pendek",
    "legal": "Film hukum",
    "hukum": "Film hukum",

    # Audience / Demographics
    "children's": "Film anak-anak",
    "children": "Film anak-anak",
    "anak-anak": "Film anak-anak",
    "teen": "Film remaja",
    "remaja": "Film remaja",
    "family": "Film keluarga",
    "keluarga": "Film keluarga",
}


FILM_MEDIUM_MAPPINGS: Dict[str, str] = {
    "live-action": "Film peran hidup",
    "live action": "Film peran hidup",
    "peran hidup": "Film peran hidup",
    "computer-animated": "Film animasi komputer",
    "computer animation": "Film animasi komputer",
    "animasi komputer": "Film animasi komputer",
    "anime": "Film anime",
    "animated": "Film animasi",
    "animation": "Film animasi",
    "animasi": "Film animasi",
    "silent": "Film bisu",
    "bisu": "Film bisu",
    "black-and-white": "Film hitam putih",
    "black and white": "Film hitam putih",
    "hitam putih": "Film hitam putih",
    "3d": "Film 3D",
}


FILM_TOPIC_MAPPINGS: Dict[str, str] = {
    "christmas": "Film tentang Natal",
    "natal": "Film tentang Natal",
    "heist": "Film tentang perampokan",
    "robbery": "Film tentang perampokan",
    "perampokan": "Film tentang perampokan",
    "basketball": "Film tentang basket",
    "basket": "Film tentang basket",
    "baseball": "Film tentang bisbol",
    "bisbol": "Film tentang bisbol",
    "football": "Film tentang sepak bola",
    "soccer": "Film tentang sepak bola",
    "sepak bola": "Film tentang sepak bola",
    "silat": "Film tentang silat",
    "kung fu": "Film tentang silat",
    "ghost": "Film tentang hantu",
    "ghosts": "Film tentang hantu",
    "hantu": "Film tentang hantu",
    "vampire": "Film tentang vampir",
    "vampires": "Film tentang vampir",
    "vampir": "Film tentang vampir",
    "zombie": "Film tentang zombi",
    "zombies": "Film tentang zombi",
    "zombi": "Film tentang zombi",
    "religion": "Film tentang agama",
    "agama": "Film tentang agama",
}


FILM_COUNTRY_NORMALIZATION: Dict[str, str] = {
    # UK and British constituent nations -> Britania Raya
    "british": "Britania Raya",
    "english": "Britania Raya",
    "scottish": "Britania Raya",
    "welsh": "Britania Raya",
    "northern irish": "Britania Raya",
    "united kingdom": "Britania Raya",
    "uk": "Britania Raya",
    "britania raya": "Britania Raya",

    # North America
    "american": "Amerika Serikat",
    "united states": "Amerika Serikat",
    "us": "Amerika Serikat",
    "usa": "Amerika Serikat",
    "amerika serikat": "Amerika Serikat",
    "canadian": "Kanada",
    "canada": "Kanada",
    "kanada": "Kanada",
    "mexican": "Meksiko",
    "mexico": "Meksiko",
    "meksiko": "Meksiko",

    # Asia
    "indonesian": "Indonesia",
    "indonesia": "Indonesia",
    "japanese": "Jepang",
    "japan": "Jepang",
    "jepang": "Jepang",
    "south korean": "Korea Selatan",
    "korean": "Korea Selatan",
    "south korea": "Korea Selatan",
    "korea selatan": "Korea Selatan",
    "chinese": "Tiongkok",
    "china": "Tiongkok",
    "tiongkok": "Tiongkok",
    "hong kong": "Hong Kong",
    "taiwanese": "Taiwan",
    "taiwan": "Taiwan",
    "macanese": "Makau",
    "macau": "Makau",
    "makau": "Makau",
    "indian": "India",
    "india": "India",
    "thai": "Thailand",
    "thailand": "Thailand",

    # Europe
    "french": "Prancis",
    "france": "Prancis",
    "prancis": "Prancis",
    "german": "Jerman",
    "germany": "Jerman",
    "jerman": "Jerman",
    "italian": "Italia",
    "italy": "Italia",
    "italia": "Italia",
    "spanish": "Spanyol",
    "spain": "Spanyol",
    "spanyol": "Spanyol",
    "russian": "Rusia",
    "russia": "Rusia",
    "rusia": "Rusia",
    "dutch": "Belanda",
    "netherlands": "Belanda",
    "belanda": "Belanda",
    "swedish": "Swedia",
    "sweden": "Swedia",
    "swedia": "Swedia",
    "norwegian": "Norwegia",
    "norway": "Norwegia",
    "norwegia": "Norwegia",
    "danish": "Denmark",
    "denmark": "Denmark",
    "polish": "Polandia",
    "poland": "Polandia",
    "polandia": "Polandia",

    # Oceania & South America
    "australian": "Australia",
    "australia": "Australia",
    "new zealand": "Selandia Baru",
    "selandia baru": "Selandia Baru",
    "brazilian": "Brasil",
    "brazil": "Brasil",
    "brasil": "Brasil",
    "argentine": "Argentina",
    "argentina": "Argentina",
}


class FilmCategoryNormalizer:
    """
    Normalizes, validates, and decomposes film categories in accordance with
    the official Wikipedia:ProyekWiki Film/Kategorisasi consensus.
    """

    def is_film_category(self, cat_name: str) -> bool:
        """Determines if a category name relates to films."""
        clean = self._clean_cat(cat_name).lower()
        if clean.startswith("film ") or clean.startswith("film\t") or " film" in clean or "film-" in clean:
            return True
        if clean.endswith(" films") or clean.endswith(" film"):
            return True
        if "films by " in clean or "films set in " in clean or "films directed by " in clean:
            return True
        if "film menurut " in clean or "film yang disutradarai " in clean:
            return True
        return False

    def validate_film_category(self, cat_name: str) -> Tuple[bool, Optional[str]]:
        """
        Validates an Indonesian film category against the Bennylin / WP:FILMKAT consensus:
        - Allowed:
          * Level-1 genre: [[Kategori:Film laga]], [[Kategori:Film cerita seru]], etc.
          * Level-1 year: [[Kategori:Film tahun 2024]]
          * Level-1 country: [[Kategori:Film Indonesia]], [[Kategori:Film Britania Raya]]
          * Level-2 Country + Year: [[Kategori:Film Indonesia tahun 2021]]
          * Level-1 language: [[Kategori:Film berbahasa Indonesia]]
          * Level-1 language + year: [[Kategori:Film berbahasa Inggris tahun 2024]]
          * Topic: [[Kategori:Film tentang Natal]]
          * Director / crew: [[Kategori:Film yang disutradarai oleh X]]
        - Disallowed:
          * Multi-genre (e.g. Film cerita seru laga, Film aksi fiksi ilmiah)
          * Genre + Year (e.g. Film laga tahun 2024)
          * Genre + Country (e.g. Film laga Amerika Serikat)
          * Subdivided UK nations (e.g. Film Inggris tahun 2024 -> must be Britania Raya)
        """
        clean = self._clean_cat(cat_name)
        if not clean.lower().startswith("film"):
            return True, None

        # 1. Check for illegal UK subdivisions in film categories
        uk_sub_match = re.search(r"\bFilm\s+(Inggris|Skotlandia|Wales|Irlandia Utara)\b", clean, re.IGNORECASE)
        if uk_sub_match:
            sub = uk_sub_match.group(1)
            return (
                False,
                f"Melanggar konsensus ProyekWiki Film: jangan kategorikan '{sub}', gunakan 'Britania Raya'.",
            )

        # 2. Check for multi-genre violation (e.g. "Film cerita seru laga", "Film drama komedi")
        lower_clean = clean.lower()
        if re.search(r"\bfilm\s+(?:cerita seru laga|aksi laga|aksi fiksi ilmiah|drama komedi|drama romantis|komedi horor|horor komedi|aksi thriller)\b", lower_clean):
            return (
                False,
                "Melanggar konsensus ProyekWiki Film: multi-genre dilarang (batasi kategori genre pada 1 level).",
            )

        # 3. Check for Genre + Year violation (e.g. "Film laga tahun 2024", "Film horor tahun 2024")
        # Allowed country+year: Film <Negara> tahun <Tahun>
        # Check if between "Film" and "tahun <YYYY>" is a genre rather than a country
        gy_match = re.match(r"^Film\s+([A-Za-z\s\-]+?)\s+tahun\s+\d{4}$", clean, re.IGNORECASE)
        if gy_match:
            middle_term = gy_match.group(1).strip().lower()
            # If middle term matches a genre (like 'laga', 'horor', 'cerita seru', 'drama', 'komedi')
            for g_key in STANDARD_FILM_GENRES:
                if middle_term == g_key or middle_term == STANDARD_FILM_GENRES[g_key].lower().replace("film ", ""):
                    return (
                        False,
                        f"Melanggar konsensus ProyekWiki Film: kategori genre + tahun ('{clean}') dilarang. Pecah menjadi level 1.",
                    )

        # 4. Check for Genre + Country violation (e.g. "Film laga Amerika Serikat", "Film horor Indonesia")
        gc_match = re.match(r"^Film\s+([A-Za-z\s\-]+?)\s+(Amerika Serikat|Indonesia|Britania Raya|Jepang|Korea Selatan|Prancis|Jerman|India|Australia|Kanada)$", clean, re.IGNORECASE)
        if gc_match:
            possible_genre = gc_match.group(1).strip().lower()
            for g_key in STANDARD_FILM_GENRES:
                if possible_genre == g_key or possible_genre == STANDARD_FILM_GENRES[g_key].lower().replace("film ", ""):
                    return (
                        False,
                        f"Melanggar konsensus ProyekWiki Film: kategori genre + negara ('{clean}') dilarang. Pecah menjadi level 1.",
                    )

        return True, None

    def decompose_enwiki_film_category(self, en_cat: str) -> List[str]:
        """
        Decomposes a complex English Wikipedia film category into valid Indonesian Wikipedia categories.

        Examples:
        - "2024 American action thriller films" ->
          ["Kategori:Film Amerika Serikat tahun 2024", "Kategori:Film laga", "Kategori:Film cerita seru"]
        - "British action thriller films" ->
          ["Kategori:Film Britania Raya", "Kategori:Film laga", "Kategori:Film cerita seru"]
        - "2026 films" ->
          ["Kategori:Film tahun 2026"]
        - "American Christmas comedy films" ->
          ["Kategori:Film Amerika Serikat", "Kategori:Film komedi", "Kategori:Film tentang Natal"]
        - "Heist films" ->
          ["Kategori:Film tentang perampokan"]
        - "Films directed by Kevin Macdonald" ->
          ["Kategori:Film yang disutradarai oleh Kevin Macdonald"]
        """
        clean = self._clean_cat(en_cat)
        lower = clean.lower()

        # 1. Non-complex patterns
        # Director
        m_dir = re.match(r"^films\s+directed\s+by\s+(.+)$", clean, re.IGNORECASE)
        if m_dir:
            director = m_dir.group(1).strip()
            return [f"Kategori:Film yang disutradarai oleh {director}"]

        # Producer
        m_prod = re.match(r"^films\s+produced\s+by\s+(.+)$", clean, re.IGNORECASE)
        if m_prod:
            producer = m_prod.group(1).strip()
            return [f"Kategori:Film yang diproduseri oleh {producer}"]

        # Upcoming English-language films
        if re.search(r"\bupcoming\s+english-language\s+films\b", lower):
            return ["Kategori:Film mendatang berbahasa Inggris"]

        # 2. Extract Year
        year = None
        m_year = re.search(r"\b(18\d{2}|19\d{2}|20\d{2})\b", clean)
        if m_year:
            year = m_year.group(1)

        # 3. Extract Country / Nationality
        country = None
        # Sort keys by length descending to match multi-word countries first
        for nat_key in sorted(FILM_COUNTRY_NORMALIZATION.keys(), key=lambda x: -len(x)):
            if re.search(rf"\b{re.escape(nat_key)}\b", lower):
                country = FILM_COUNTRY_NORMALIZATION[nat_key]
                break

        # 4. Extract Language (e.g. English-language films)
        is_english_lang = bool(re.search(r"\benglish-language\b", lower))

        # 5. Extract Medium (live-action, animated, anime, 3D, silent, etc.)
        detected_mediums: Set[str] = set()
        for med_key in sorted(FILM_MEDIUM_MAPPINGS.keys(), key=lambda x: -len(x)):
            if re.search(rf"\b{re.escape(med_key)}\b", lower):
                detected_mediums.add(FILM_MEDIUM_MAPPINGS[med_key])

        # 6. Extract Topics (Christmas, heist, sports, etc.)
        detected_topics: Set[str] = set()
        for top_key in sorted(FILM_TOPIC_MAPPINGS.keys(), key=lambda x: -len(x)):
            if re.search(rf"\b{re.escape(top_key)}\b", lower):
                detected_topics.add(FILM_TOPIC_MAPPINGS[top_key])

        # 7. Extract Genres (action, thriller, comedy, sci-fi, horror, etc.)
        detected_genres: Set[str] = set()
        genre_search_text = re.sub(r"\blive[-\s]action\b", "", lower)
        # Sort by length descending to match "romantic comedy" before "comedy"
        for g_key in sorted(STANDARD_FILM_GENRES.keys(), key=lambda x: -len(x)):
            if re.search(rf"\b{re.escape(g_key)}\b", genre_search_text):
                genre_cat = STANDARD_FILM_GENRES[g_key]
                # Special check: don't double count comedy if romantic comedy matched
                if g_key == "comedy" and "Film komedi romantis" in detected_genres:
                    continue
                if g_key == "romance" and "Film komedi romantis" in detected_genres:
                    continue
                detected_genres.add(genre_cat)

        results: List[str] = []

        # Assemble Level-2 Country + Year (Allowed by consensus)
        if country and year:
            results.append(f"Kategori:Film {country} tahun {year}")
        elif country and not detected_genres and not detected_mediums and not detected_topics:
            results.append(f"Kategori:Film {country}")
        elif year and not detected_genres and not detected_mediums and not detected_topics and not country:
            results.append(f"Kategori:Film tahun {year}")
        elif country and (detected_genres or detected_mediums or detected_topics):
            # Decompose country to standalone
            results.append(f"Kategori:Film {country}")
            if year:
                results.append(f"Kategori:Film tahun {year}")

        # Add language category if present
        if is_english_lang:
            if year and not country:
                results.append(f"Kategori:Film berbahasa Inggris tahun {year}")
            else:
                results.append("Kategori:Film berbahasa Inggris")

        # Add decomposed level-1 genres
        for g in sorted(detected_genres):
            results.append(f"Kategori:{g}")

        # Add decomposed level-1 mediums
        for m in sorted(detected_mediums):
            results.append(f"Kategori:{m}")

        # Add decomposed topics
        for t in sorted(detected_topics):
            results.append(f"Kategori:{t}")

        # Deduplicate preserving order
        dedup: List[str] = []
        for r in results:
            if r not in dedup:
                dedup.append(r)

        return dedup

    def normalize_film_categories(self, categories: Iterable[str]) -> List[str]:
        """
        Normalizes a list of category names (either English or candidate Indonesian),
        decomposing complex multi-marker categories and enforcing consensus rules.
        """
        out: List[str] = []
        for cat in categories:
            clean = self._clean_cat(cat)
            if not clean:
                continue

            # If English category, decompose using enwiki rules
            if self.is_enwiki_category(clean):
                decomposed = self.decompose_enwiki_film_category(clean)
                for d in decomposed:
                    if d not in out:
                        out.append(d)
            else:
                # Validate Indonesian category against consensus
                is_valid, reason = self.validate_film_category(clean)
                prefix_clean = clean if clean.startswith("Kategori:") else f"Kategori:{clean}"
                if is_valid:
                    if prefix_clean not in out:
                        out.append(prefix_clean)
                else:
                    # Attempt automated flattening if it is an illegal multi-genre or genre+country/year
                    decomposed = self.decompose_enwiki_film_category(clean)
                    if decomposed:
                        for d in decomposed:
                            if d not in out:
                                out.append(d)
                    else:
                        if prefix_clean not in out:
                            out.append(prefix_clean)
        return out

    def is_enwiki_category(self, cat_name: str) -> bool:
        """Heuristic to detect if a category string is in English."""
        clean = self._clean_cat(cat_name).lower()
        if clean.endswith(" films") or clean.endswith(" film"):
            return True
        if any(w in clean for w in ("british", "american", "action", "thriller", "comedy", "horror", "sci-fi", "directed by", "upcoming")):
            return True
        return False

    def _clean_cat(self, cat_name: str) -> str:
        s = cat_name.strip()
        s = re.sub(r"^\[\[\s*", "", s)
        s = re.sub(r"\s*\]\]$", "", s)
        s = re.sub(r"^(?:Category|Kategori)\s*:\s*", "", s, flags=re.IGNORECASE)
        # remove pipe and sort key
        if "|" in s:
            s = s.split("|", 1)[0].strip()
        return s.strip()


default_film_categorizer = FilmCategoryNormalizer()
