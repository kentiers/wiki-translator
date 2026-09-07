"""
Dynamic Terminology & Exonym Resolver for English -> Indonesian Wikipedia Translation.

Features:
1. Extract candidate technical terms, compound nouns, capitalized entities, and quoted/italicized phrases from wikitext.
2. Resolve authoritative Indonesian equivalents using:
   a. Curated topic glossary from prompts.py (and common base dictionary)
   b. Persistent SQLite cache (.cache/glossary_cache.db)
   c. Wikipedia Interlanguage Link API (en.wikipedia.org -> id.wikipedia.org langlinks)
3. Dynamic injection of resolved glossary pairs into translation prompts.
"""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union
import urllib.error
import urllib.parse
import urllib.request

from .prompts import TOPIC_GLOSSARIES
from .glossary_memory import GlossaryMemory
from .storage_manager import default_storage_manager

# Default common glossary terms / exonyms
BASE_EXONYMS_AND_TERMS: Dict[str, str] = {
    # Diplomatic Standard Exonyms (Kemlu & Badan Bahasa)
    "united states": "Amerika Serikat",
    "united kingdom": "Britania Raya",
    "netherlands": "Belanda",
    "germany": "Jerman",
    "japan": "Jepang",
    "france": "Prancis",
    "spain": "Spanyol",
    "italy": "Italia",
    "egypt": "Mesir",
    "greece": "Yunani",
    "singapore": "Singapura",
    "china": "Tiongkok",
    "russia": "Rusia",
    "saint petersburg": "Sankt-Peterburg",
    "st. petersburg": "Sankt-Peterburg",
    "switzerland": "Swiss",
    "austria": "Austria",
    "belgium": "Belgia",
    "sweden": "Swedia",
    "norway": "Norwegia",
    "denmark": "Denmark",
    "finland": "Finlandia",
    "poland": "Polandia",
    "portugal": "Portugal",
    "morocco": "Maroko",
    "turkey": "Turki",
    "saudi arabia": "Arab Saudi",
    "new zealand": "Selandia Baru",
    "united arab emirates": "Uni Emirat Arab",
    "papua new guinea": "Papua Nugini",
    "south korea": "Korea Selatan",
    "north korea": "Korea Utara",
    "south africa": "Afrika Selatan",
    "mexico": "Meksiko",
    "brazil": "Brasil",
    "argentina": "Argentina",
    "canada": "Kanada",
    "australia": "Australia",
    "philippines": "Filipina",
    "thailand": "Thailand",
    "vietnam": "Vietnam",
    "malaysia": "Malaysia",
    # Core Science, Computing & Mathematics Standard Terms
    "algorithm": "algoritma",
    "parameter": "parameter",
    "matrix": "matriks",
    "interface": "antarmuka",
    "streamlining": "perampingan",
    "database": "basis data",
    "framework": "kerangka kerja",
    # Film, TV & Entertainment Domain Standard Terms (KBBI VI & EYD V)
    "academy awards": "Academy Awards (Piala Oscar)",
    "approval rating": "peringkat persetujuan",
    "box office": "pencapaian box office / bioskop komersial",
    "box-office bomb": "film gagal secara komersial",
    "box-office flop": "film gagal secara komersial",
    "cameo": "kameo",
    "cgi": "citra hasil komputer (CGI)",
    "character": "karakter / tokoh",
    "cinematographer": "penata sinematografi / pengarah fotografi",
    "cliffhanger": "cerita menggantung / ujung gantung",
    "critical reception": "penerimaan kritis / tanggapan kritikus",
    "debut": "debut",
    "development": "pengembangan",
    "direct-to-streaming": "rilis langsung ke layanan pengaliran",
    "director of photography": "penata sinematografi / pengarah fotografi",
    "distributor": "distributor",
    "executive producer": "produser eksekutif",
    "feature film": "film cerita panjang / film panjang",
    "foley": "foley",
    "franchise": "waralaba",
    "genre": "genre",
    "gross revenue": "pendapatan kotor",
    "guest appearance": "penampilan tamu",
    "guest star": "bintang tamu",
    "lead actor": "pemeran utama pria",
    "lead actress": "pemeran utama wanita",
    "metacritic": "Metacritic",
    "miniseries": "serial mini",
    "nomination": "nominasi",
    "original score": "musik orisinal",
    "pilot episode": "episode perintis / episode pilot",
    "plot summary": "ringkasan alur cerita",
    "post-credits scene": "adegan pascakredit",
    "post-production": "pascaproduksi",
    "pre-production": "praproduksi",
    "premiere": "pemutaran perdana",
    "prequel": "prekuel",
    "principal photography": "pengambilan gambar utama",
    "production company": "rumah produksi",
    "recurring role": "peran berulang",
    "rotten tomatoes": "Rotten Tomatoes",
    "runtime": "durasi film",
    "screenplay": "skenario",
    "screenwriter": "penulis skenario",
    "script": "naskah / skenario",
    "season finale": "akhir musim / episode pemungkas musim",
    "season premiere": "pemutaran perdana musim",
    "sequel": "sekuel",
    "short film": "film pendek",
    "showrunner": "penggagas utama serial / pengelola acara (showrunner)",
    "sound effect": "efek suara",
    "soundtrack": "jalur suara",
    "spin-off": "sempalan",
    "straight-to-video": "rilis langsung ke video",
    "streaming service": "layanan pengaliran media / layanan streaming",
    "stunt double": "pemeran pengganti",
    "supporting actor": "pemeran pendukung",
    "supporting actress": "pemeran pendukung",
    "television series": "serial televisi",
    "theatrical release": "perilisan bioskop",
    "visual effects": "efek visual (VFX)",
    "voice actor": "pengisi suara / pemeran suara",
    "voice actress": "pengisi suara wanita / pemeran suara wanita",
    "voice cast": "pengisi suara / pemeran suara",
}

# Curated Idioms, Figurative Phrases, and Colloquialisms
IDIOM_AND_PHRASE_MAPPINGS: Dict[str, str] = {
    "under the radar": "tanpa banyak diketahui / diam-diam",
    "rule of thumb": "panduan umum / patokan praktis",
    "silver lining": "hikmah / sisi positif",
    "at the eleventh hour": "pada saat-saat terakhir",
    "high-flying": "sukses / ternama",
    "race against time": "berlomba dengan waktu",
    "race against the clock": "berlomba dengan waktu",
    "in the good graces": "tetap disenangi / menjaga hubungan baik",
    "clothes do not make the woman": "pakaian tidak menentukan harkat seseorang",
    "clothes do not make the man": "pakaian tidak menentukan harkat seseorang",
    "shed light on": "menjelaskan / mengungkap",
    "take for granted": "menganggap remeh / menerima begitu saja",
    "play into the hands of": "menguntungkan pihak",
    "nip in the bud": "mencegah sejak awal",
    "tip of the iceberg": "sebagian kecil dari masalah yang lebih besar",
    "bittersweet": "bercampur haru / manis dan pahit",
    "touch-and-go": "kritis / belum pasti",
    "game-changer": "pengubah keadaan / terobosan besar",
    "cutting-edge": "mutakhir",
    "red tape": "hambatan birokrasi",
    "behind the scenes": "di balik layar",
    "household name": "nama yang dikenal luas",
    "in full swing": "sedang berada di puncaknya / berjalan lancar",
    "outlive": "hidup lebih lama daripada",
    "outliving": "hidup lebih lama daripada",
    "sewing work": "pekerjaan menjahit",
    "conservative backlash": "reaksi keras kaum konservatif",
    # Additional common English idioms and figurative expressions
    "state-of-the-art": "mutakhir / tercanggih",
    "break new ground": "membuat terobosan baru",
    "double-edged sword": "senjata bermata dua / pisau bermata dua",
    "last ditch": "upaya terakhir",
    "last-ditch": "upaya terakhir",
    "turn of the century": "pergantian abad",
    "across the board": "secara menyeluruh",
    "in the wake of": "setelah / menyusul terjadinya",
    "by and large": "secara garis besar",
    "back to the drawing board": "memulai kembali dari awal",
    "water under the bridge": "peristiwa yang sudah berlalu",
    "burn bridges": "memutus hubungan",
    "spill the beans": "membocorkan rahasia",
    "bite the bullet": "menghadapi situasi sulit dengan tabah",
    "through thick and thin": "dalam suka dan duka",
    "leave no stone unturned": "mencari ke segala penjuru / berusaha sekuat tenaga",
    "blessing in disguise": "berkah terselubung / hikmah tersembunyi",
    "steep learning curve": "proses belajar yang menuntut usaha keras",
    "stepping stone": "batu loncatan",
    "cornerstone": "fondasi utama / pilar penting",
    "bread and butter": "sumber penghidupan utama",
    "face the music": "menghadapi kenyataan / menanggung akibat",
}

# Common English stop words / punctuation words that should not be extracted as standalone candidate terms
COMMON_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "when", "at", "from",
    "by", "for", "with", "about", "against", "between", "into", "through", "during",
    "before", "after", "above", "below", "to", "of", "in", "on", "over", "under",
    "again", "further", "then", "once", "here", "there", "all", "any", "both", "each",
    "few", "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own",
    "same", "so", "than", "too", "very", "s", "t", "can", "will", "just", "don", "should",
    "now", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "having",
    "do", "does", "did", "doing", "would", "could", "might", "must", "shall",
    "this", "that", "these", "those", "it", "its", "they", "them", "their", "theirs",
    "he", "him", "his", "she", "her", "hers", "we", "us", "our", "ours", "you", "your",
    "yours", "i", "me", "my", "mine", "who", "whom", "whose", "which", "what",
    "also", "however", "therefore", "furthermore", "moreover", "although", "because",
    "since", "many", "much", "several", "various", "often", "usually", "sometimes",
    "well", "first", "second", "third", "early", "late", "new", "old", "good", "great",
    "see", "also", "main", "article", "section", "thumb", "right", "left", "center",
    "file", "image", "category", "ref", "http", "https", "www", "com", "org", "align",
}


def clean_wikitext_for_extraction(wikitext: str) -> str:
    """Strips comments, ref tags, templates, file markup, and math to avoid noisy candidates."""
    text = wikitext
    # Remove HTML comments
    text = re.sub(r"<!--[\s\S]*?-->", " ", text)
    # Remove <math>...</math>, <chem>...</chem>, <syntaxhighlight>...</syntaxhighlight>
    text = re.sub(r"<(math|chem|syntaxhighlight)[\s\S]*?</\1>", " ", text, flags=re.IGNORECASE)
    # Remove <ref...>...</ref> and self-closing refs
    text = re.sub(r"<ref[\s\S]*?</ref>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<ref[^>]*/>", " ", text, flags=re.IGNORECASE)
    # Remove template blocks {{...}}
    text = re.sub(r"\{\{[\s\S]*?\}\}", " ", text)
    # Remove file links [[File:...]] or [[Image:...]]
    text = re.sub(r"\[\[(File|Image|Berkas|Gambar):[^\]]+\]\]", " ", text, flags=re.IGNORECASE)
    # Clean section headers == Header ==
    text = re.sub(r"^=+\s*(.*?)\s*=+$", r"\1", text, flags=re.MULTILINE)
    # In cast lists / credits, strip 'as Character Name' so fictional character names
    # are never extracted and queried as exonyms (e.g. 'as Maia Marten', 'as Noah Marten')
    text = re.sub(r"\bas\s+[A-Z][a-z0-9]+(?:\s+[A-Z][a-z0-9]+)*\b", " ", text)
    return text


def extract_candidate_terms(wikitext: str, max_terms: int = 50) -> List[str]:
    """
    Extracts key candidate terms / entities from English wikitext using heuristic extraction:
    1. Wikilink targets [[Target|Alias]] or [[Target]]
    2. Capitalized phrases & proper nouns (e.g. 'United States', 'Albert Einstein')
    3. Terms in quotes ("term" or 'term') and italics (''term'')
    4. Compound technical nouns / hyphenated terms (e.g. 'fault-tolerant', 'wave function')
    """
    candidates: Set[str] = set()

    # 1. Wikilinks [[Target|Alias]] or [[Target]]
    for m in re.finditer(r"\[\[([^\|\]]+)(?:\|([^\]]+))?\]\]", wikitext):
        target = m.group(1).strip()
        # Skip namespace links like Category:, File:, Help:
        if any(target.lower().startswith(prefix) for prefix in ("category:", "file:", "image:", "help:", "wikipedia:", "template:")):
            continue
        # Strip section anchors like Target#Section
        target_clean = target.split("#")[0].strip()
        if target_clean and len(target_clean) > 2:
            candidates.add(target_clean)
        # Also inspect display alias if available
        alias = m.group(2)
        if alias:
            alias_clean = alias.strip()
            if alias_clean and len(alias_clean) > 2 and not alias_clean.isnumeric():
                candidates.add(alias_clean)

    cleaned = clean_wikitext_for_extraction(wikitext)

    # 2. Terms in quotes or italics: ''term'', "term", 'term'
    for m in re.finditer(r"''+([^'\n]{3,60})''+", cleaned):
        term = m.group(1).strip()
        if term and not term.startswith("⟦") and not term.endswith("⟧"):
            candidates.add(term)

    for m in re.finditer(r'["“]([A-Za-z0-9\s\-–]{3,60})["”]', cleaned):
        term = m.group(1).strip()
        if term:
            candidates.add(term)

    # 3. Capitalized phrases (e.g. "Quantum Hall Effect", "United States", "North America")
    # Matches capitalized word sequences
    for m in re.finditer(r"\b([A-Z][a-z0-9]+(?:\s+[A-Z][a-z0-9]+)+)\b", cleaned):
        phrase = m.group(1).strip()
        if len(phrase) > 3:
            candidates.add(phrase)

    # Also match capitalized phrases with connecting prepositions e.g. "Theory of Relativity", "University of Cambridge"
    for m in re.finditer(r"\b([A-Z][a-z0-9]+(?:\s+(?:of|the|de|du|von|van)\s+[A-Z][a-z0-9]+)+)\b", cleaned):
        phrase = m.group(1).strip()
        if len(phrase) > 3:
            candidates.add(phrase)

    # 4. Capitalized standalone words (potential exonyms/proper nouns)
    for m in re.finditer(r"\b([A-Z][a-z]{2,25})\b", cleaned):
        word = m.group(1).strip()
        if word.lower() not in COMMON_STOPWORDS:
            candidates.add(word)

    # 5. Compound technical noun phrases / hyphenated terms (e.g. "quantum computing", "fault-tolerant")
    for m in re.finditer(r"\b([a-z]{3,18}-[a-z]{3,18})\b", cleaned, flags=re.IGNORECASE):
        candidates.add(m.group(1).strip())

    # 6. Check for multi-word idioms and figurative phrases
    cleaned_lower = cleaned.lower()
    for idiom in IDIOM_AND_PHRASE_MAPPINGS:
        # Use word-boundary regex if possible, handling hyphens cleanly
        pattern = r"\b" + re.escape(idiom) + r"\b"
        if re.search(pattern, cleaned_lower, flags=re.IGNORECASE):
            candidates.add(idiom)
    # Filter and rank candidates
    cleaned_candidates: List[str] = []
    for cand in candidates:
        cand_str = re.sub(r"\s+", " ", cand).strip(" ,.;:!?\"'()[]{}/*")
        if not cand_str or len(cand_str) < 2:
            continue
        if cand_str.lower() in COMMON_STOPWORDS:
            continue
        # Avoid placeholders like ⟦REF_0⟧
        if "⟦" in cand_str or "⟧" in cand_str:
            continue
        # Avoid pure numbers
        if cand_str.replace(".", "").replace(",", "").isdigit():
            continue
        cleaned_candidates.append(cand_str)

    # Sort: multi-word phrases first, then longer words, deterministic
    cleaned_candidates.sort(key=lambda s: (len(s.split()), len(s)), reverse=True)
    return cleaned_candidates[:max_terms]


class GlossaryResolver:
    """
    Automated, lightweight Dynamic Terminology & Exonym Resolver.
    Caches resolved pairs in SQLite and queries Wikipedia Langlinks API.
    """

    def __init__(
        self,
        cache_db_path: Optional[Union[str, Path]] = None,
        user_agent: Optional[str] = None,
        memory: Optional[GlossaryMemory] = None,
        kateglo_client: Optional[Any] = None,
    ):
        self.cache_db_path = (
            Path(cache_db_path)
            if cache_db_path is not None
            else default_storage_manager.glossary_cache_db
        )
        self.memory = memory
        self.kateglo_client = kateglo_client
        self.user_agent = user_agent or "WikiTranslatorGlossaryResolver/1.0 (https://id.wikipedia.org; translator-tool)"
        self._init_db()

    def _init_db(self) -> None:
        """Initializes SQLite database schema for term resolution cache."""
        self.cache_db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.cache_db_path)
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS glossary_cache (
                        en_term_lower TEXT PRIMARY KEY,
                        en_term_display TEXT NOT NULL,
                        id_term TEXT,
                        source TEXT NOT NULL,
                        created_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_glossary_en_lower ON glossary_cache(en_term_lower)"
                )
        finally:
            conn.close()

    def get_cached_term(self, en_term: str) -> Optional[Tuple[Optional[str], str]]:
        """
        Retrieves cached resolution for a term.
        Returns (id_term, source) if found, else None.
        Note: id_term can be None (negative cache for terms not found on id.wikipedia).
        """
        en_lower = en_term.strip().lower()
        conn = sqlite3.connect(self.cache_db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id_term, source FROM glossary_cache WHERE en_term_lower = ?",
                (en_lower,),
            )
            row = cur.fetchone()
            if row:
                return (row[0], row[1])
            return None
        finally:
            conn.close()

    def cache_term(self, en_term: str, id_term: Optional[str], source: str) -> None:
        """Saves a resolved term (or negative result) to local SQLite cache."""
        en_lower = en_term.strip().lower()
        conn = sqlite3.connect(self.cache_db_path)
        try:
            import time
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO glossary_cache (en_term_lower, en_term_display, id_term, source, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (en_lower, en_term.strip(), id_term.strip() if id_term else None, source, time.time()),
                )
        finally:
            conn.close()

    def fetch_wikipedia_langlinks(self, en_titles: List[str]) -> Dict[str, Optional[str]]:
        """
        Batched query to en.wikipedia.org Action API to retrieve Indonesian (id) interlanguage links.
        Returns a dict mapping original title/lowercase -> Indonesian title (or None if none).
        """
        if not en_titles:
            return {}

        results: Dict[str, Optional[str]] = {t: None for t in en_titles}
        
        # Wikipedia API allows up to 50 titles per request
        batch_size = 40
        for i in range(0, len(en_titles), batch_size):
            batch = en_titles[i : i + batch_size]
            titles_param = "|".join(batch)
            params = {
                "action": "query",
                "titles": titles_param,
                "prop": "langlinks",
                "lllang": "id",
                "lllimit": "max",
                "redirects": "1",
                "formatversion": "2",
                "format": "json",
            }

            url = f"https://en.wikipedia.org/w/api.php?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": self.user_agent},
                method="GET",
            )

            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except Exception:
                # Network failure or timeout: gracefully continue
                continue

            query = data.get("query", {})
            # Normalized/redirected mappings if any
            normalized_map: Dict[str, str] = {}
            for item in query.get("normalized", []):
                normalized_map[item.get("to", "")] = item.get("from", "")
            for item in query.get("redirects", []):
                normalized_map[item.get("to", "")] = item.get("from", "")

            for page in query.get("pages", []):
                title = page.get("title", "")
                langlinks = page.get("langlinks", [])
                id_title = None
                if langlinks:
                    # langlinks is a list of objects: [{"lang": "id", "title": "Komputasi kuantum"}]
                    for ll in langlinks:
                        if ll.get("lang") == "id":
                            id_title = ll.get("title")
                            break

                # Match back to original requested batch title
                orig_key = title
                if orig_key not in results:
                    # check if normalized
                    for b in batch:
                        if b.lower() == title.lower() or normalized_map.get(title, "").lower() == b.lower():
                            orig_key = b
                            break

                results[orig_key] = id_title
                # Also store lowercase variant
                results[title.lower()] = id_title

        return results

    def resolve_term(
        self,
        term: str,
        topic: Optional[str] = None,
        custom_glossary: Optional[Dict[str, str]] = None,
        allow_network: bool = True,
    ) -> Optional[str]:
        """
        Resolves a single term:
        1. Custom glossary / topic glossary / BASE_EXONYMS_AND_TERMS
        2. SQLite cache
        3. Wikipedia Interlanguage Link API
        """
        term_clean = term.strip()
        term_lower = term_clean.lower()
        approved = self.memory.approved_terms(topic) if self.memory else {}
        custom_glossary = {**approved, **(custom_glossary or {})}

        # 1a. Custom glossary check
        if custom_glossary:
            for k, v in custom_glossary.items():
                if k.lower() == term_lower:
                    return v

        # 1b. Warung Kopi community consensus lexicon (highest community authority)
        try:
            from .warung_kopi_harvester import default_warung_kopi_harvester
            wk_lex = default_warung_kopi_harvester.export_lexicon_dict()
            if topic and topic in wk_lex and term_lower in wk_lex[topic]:
                return wk_lex[topic][term_lower]
            if "general" in wk_lex and term_lower in wk_lex["general"]:
                return wk_lex["general"][term_lower]
        except Exception:
            pass

        # 1c. Topic glossary check
        if topic and topic in TOPIC_GLOSSARIES:
            for k, v in TOPIC_GLOSSARIES[topic].items():
                if k.lower() == term_lower:
                    return v
        # 1c. Base exonyms & standard terms
        if term_lower in BASE_EXONYMS_AND_TERMS:
            return BASE_EXONYMS_AND_TERMS[term_lower]

        # 1d. Idioms and figurative phrases
        if term_lower in IDIOM_AND_PHRASE_MAPPINGS:
            return IDIOM_AND_PHRASE_MAPPINGS[term_lower]

        # 2. SQLite cache
        cached = self.get_cached_term(term_clean)
        if cached is not None:
            id_val, _ = cached
            return id_val

        # 3. Wikipedia API Langlinks
        if allow_network:
            try:
                langlinks_map = self.fetch_wikipedia_langlinks([term_clean])
                id_title = langlinks_map.get(term_clean) or langlinks_map.get(term_lower)
                self.cache_term(term_clean, id_title, source="wikipedia_langlinks")
                return id_title
            except Exception:
                pass

        return None

    def resolve_section_terms(
        self,
        wikitext: str,
        topic: Optional[str] = None,
        custom_glossary: Optional[Dict[str, str]] = None,
        max_candidates: int = 30,
        max_resolved: int = 20,
        allow_network: bool = True,
    ) -> Dict[str, str]:
        """
        Extracts candidates from section wikitext and resolves Indonesian equivalents.
        Returns a dictionary of {en_term: id_term}.
        """
        resolved: Dict[str, str] = {}
        approved = self.memory.approved_terms(topic) if self.memory else {}
        custom_glossary = {**approved, **(custom_glossary or {})}
        
        # 1. Start with any matching entries from custom glossary & active topic glossary
        active_dict: Dict[str, str] = {}
        if topic and topic in TOPIC_GLOSSARIES:
            active_dict.update(TOPIC_GLOSSARIES[topic])
        if custom_glossary:
            active_dict.update(custom_glossary)
        # Inject Warung Kopi consensus terms matching active topic
        try:
            from .warung_kopi_harvester import default_warung_kopi_harvester
            wk_lex = default_warung_kopi_harvester.export_lexicon_dict()
            if topic and topic in wk_lex:
                active_dict.update(wk_lex[topic])
            if "general" in wk_lex:
                active_dict.update(wk_lex["general"])
        except Exception:
            pass


        wikitext_lower = wikitext.lower()
        for k, v in active_dict.items():
            if re.search(r"(?<!\w)" + re.escape(k.lower()) + r"(?!\w)", wikitext_lower):
                resolved[k] = v

        # 1. First inject any matching idioms/figurative phrases directly from wikitext
        wikitext_clean_lower = clean_wikitext_for_extraction(wikitext).lower()
        for idiom_key, idiom_val in IDIOM_AND_PHRASE_MAPPINGS.items():
            pattern = r"\b" + re.escape(idiom_key) + r"\b"
            if re.search(pattern, wikitext_clean_lower, flags=re.IGNORECASE):
                resolved.setdefault(idiom_key, idiom_val)

        # 2. Candidate terms resolution
        candidates = extract_candidate_terms(wikitext, max_terms=max_candidates)
        to_fetch_network: List[str] = []
        for cand in candidates:
            cand_lower = cand.lower()
            if cand_lower in (k.lower() for k in resolved.keys()):
                continue

            # Active topic terms were added above; do not borrow unrelated senses.

            if cand_lower in BASE_EXONYMS_AND_TERMS:
                resolved[cand] = BASE_EXONYMS_AND_TERMS[cand_lower]
                continue

            if cand_lower in IDIOM_AND_PHRASE_MAPPINGS:
                resolved[cand] = IDIOM_AND_PHRASE_MAPPINGS[cand_lower]
                continue

            # Check cache
            cached = self.get_cached_term(cand)
            if cached is not None:
                id_val, _ = cached
                if id_val:
                    resolved[cand] = id_val
            else:
                to_fetch_network.append(cand)

        # 3. Batch fetch uncached candidates via Wikipedia Langlinks API
        if allow_network and to_fetch_network:
            try:
                fetched_map = self.fetch_wikipedia_langlinks(to_fetch_network)
                for cand in to_fetch_network:
                    id_val = fetched_map.get(cand) or fetched_map.get(cand.lower())
                    self.cache_term(cand, id_val, source="wikipedia_langlinks")
                    if id_val:
                        resolved[cand] = id_val
            except Exception:
                pass

        # 4. Check Kateglo bilingual glossary for candidates still unresolved
        k_client = self.kateglo_client
        if k_client is None:
            try:
                from .kateglo_client import default_kateglo_client
                k_client = default_kateglo_client
            except Exception:
                k_client = None

        if k_client:
            for cand in candidates:
                if cand not in resolved:
                    try:
                        k_terms = k_client.find_glossary_terms(cand)
                        if k_terms:
                            resolved[cand] = k_terms[0]
                    except Exception:
                        pass
        # Return top N resolved terms
        if len(resolved) > max_resolved:
            # Sort with multi-word terms first
            sorted_items = sorted(resolved.items(), key=lambda item: (len(item[0].split()), len(item[0])), reverse=True)
            return dict(sorted_items[:max_resolved])

        return resolved


# Global singleton resolver instance
default_glossary_resolver = GlossaryResolver(memory=GlossaryMemory())
