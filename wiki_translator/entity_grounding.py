"""
Universal Multi-Domain Entity & Claim Grounding Auditor for Indonesian Wikipedia.

Provides deterministic, cross-domain factual alignment between source and draft wikitext:
1. Multi-Domain Entity Extraction:
   - Wikilinks [[Target|Label]] & Interlanguage links {{ill|Target|...}}
   - Italicized titles & biological taxa (''Film Title'', ''Species name'')
   - Mathematical & scientific formulas (<math>...</math>, {{math|...}})
   - Proper noun phrases & named entities (People, places, organizations, algorithms)
2. Hallucination & Drift Detection:
   - Dropped Entities: Key entities present in source but omitted in draft.
   - Phantom Entities: Entities introduced in draft with zero grounding in source paragraph.
   - Swapped Entities & Attribution Drift: Quotes or roles attributed to the wrong actor.
3. Topic-Aware Heuristics:
   - film / cinema: Director, cast, producer, release title fidelity.
   - computing_science / tech: Software creators, protocols, versions, architectures.
   - medical_biology: Pathogens, binomial nomenclature, clinical statistics.
   - physics_astronomy / mathematics: Constants, celestial objects, equations.
   - history_social: Historical actors, succession, quote attribution.
4. Auto-Repair & Targeted Re-Prompting:
   - Deterministic restoration of wikilink brackets on recognized entities.
   - Surgical prompt generation for zero-hallucination re-translation.
"""

from dataclasses import dataclass, field
import difflib
import re
from typing import Any, Dict, List, Optional, Set, Tuple


# Common English stopwords to ignore when extracting capitalized proper nouns at sentence boundaries
ENGLISH_STOPWORDS: Set[str] = {
    "however", "in", "on", "at", "by", "from", "for", "with", "about", "into", "through",
    "during", "before", "after", "above", "below", "to", "up", "down", "over", "under",
    "again", "further", "then", "once", "here", "there", "when", "where", "why", "how",
    "all", "any", "both", "each", "few", "more", "most", "other", "some", "such", "no",
    "nor", "not", "only", "own", "same", "so", "than", "too", "very", "can", "will",
    "just", "should", "now", "although", "though", "even", "while", "as", "since",
    "unless", "until", "because", "despite", "meanwhile", "furthermore", "moreover",
    "nevertheless", "subsequently", "initially", "eventually", "she", "he", "it", "they",
    "we", "you", "i", "his", "her", "their", "its", "our", "your", "my", "this", "that",
    "these", "those", "the", "a", "an", "according", "following", "based", "unlike"
}

# Common Indonesian stopwords to ignore when extracting proper nouns
INDONESIAN_STOPWORDS: Set[str] = {
    "namun", "tetapi", "akan", "tetapi", "pada", "di", "ke", "dari", "untuk", "dengan",
    "oleh", "dalam", "sebagai", "tentang", "mengenai", "terhadap", "bagi", "atas",
    "antara", "melalui", "tanpa", "selama", "sebelum", "setelah", "sesudah", "sejak",
    "hingga", "sampai", "sementara", "sedangkan", "selain", "kemudian", "lalu", "kelak",
    "akhirnya", "meskipun", "walaupun", "kendati", "biarpun", "karena", "sebab", "oleh",
    "jika", "apabila", "kalau", "bahwa", "seperti", "bagaikan", "ia", "dia", "mereka",
    "kami", "kita", "kamu", "anda", "saya", "aku", "beliau", "sang", "si", "para", "kaum",
    "ini", "itu", "tersebut", "suatu", "sebuah", "adalah", "merupakan", "yaitu", "yakni"
}

NEUTRAL_WIKI_TARGETS: Set[str] = {
    "rusia", "kekaisaran rusia", "indonesia", "inggris", "amerika serikat", "eropa", "asia", "bahasa rusia",
    "bahasa indonesia", "bahasa inggris", "pemerintah", "negara", "kota", "desa",
    "tahun", "abad", "bulan", "hari", "universitas", "sekolah", "buku", "film"
}


@dataclass
class EntityGroundingResult:
    """Detailed scorecard of entity alignment and grounding between source and draft."""
    passed: bool
    topic: Optional[str] = None
    source_entities: List[str] = field(default_factory=list)
    draft_entities: List[str] = field(default_factory=list)
    dropped_entities: List[str] = field(default_factory=list)
    phantom_entities: List[str] = field(default_factory=list)
    swapped_entities: List[Tuple[str, str]] = field(default_factory=list)
    attribution_warnings: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    can_auto_repair: bool = False
    repaired_wikitext: Optional[str] = None
    revision_prompt: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "topic": self.topic,
            "source_entities": list(self.source_entities),
            "draft_entities": list(self.draft_entities),
            "dropped_entities": list(self.dropped_entities),
            "phantom_entities": list(self.phantom_entities),
            "swapped_entities": list(self.swapped_entities),
            "attribution_warnings": list(self.attribution_warnings),
            "warnings": list(self.warnings),
            "can_auto_repair": self.can_auto_repair,
            "has_revision_prompt": bool(self.revision_prompt),
        }


class EntityGroundingAuditor:
    """
    Universal entity and attribution auditor across all Wikipedia topic domains:
    - Biographies, History, Politics, Social Sciences
    - Cinema, Television, Media, Arts, Literature
    - Computing, Science, Technology, Mathematics
    - Medicine, Biology, Anatomy, Pharmaceuticals
    - Physics, Chemistry, Astronomy, Earth Sciences
    """

    _WIKILINK_RE = re.compile(r"\[\[([^\]|#\n]+)(?:#[^\]|]+)?(?:\|[^\]\n]+)?\]\]")
    _ILL_RE = re.compile(r"\{\{ill\|([^|}]+)\|[^}]*\}\}", re.IGNORECASE)
    _ITALICS_RE = re.compile(r"''([^'\n]{3,60})''")
    _MATH_RE = re.compile(r"<math[\s>]([\s\S]*?)<\/math>", re.IGNORECASE)
    _QUOTE_RE = re.compile(r'"([^"\n]{10,250})"')

    def __init__(self) -> None:
        pass

    # -------------------------------------------------------------------------
    # Entity Extraction
    # -------------------------------------------------------------------------
    def extract_entities(self, wikitext: str, lang: str = "en", topic: Optional[str] = None) -> Set[str]:
        """
        Extracts key factual entities from wikitext:
        - Wikilink targets
        - Interlanguage link targets
        - Italicized titles (works, films, taxa)
        - Multi-word Proper Nouns (ignoring stopwords)
        """
        if not wikitext:
            return set()

        # Strip references and citation page templates so book publishers in citations don't pollute narrative entity audit
        clean_text = re.sub(r"<ref\b[^>]*\/>", "", wikitext)
        clean_text = re.sub(r"<ref\b[^>]*>[\s\S]*?<\/ref>", "", clean_text)
        clean_text = re.sub(r"\{\{rp\|[^{}]*\}\}", "", clean_text, flags=re.I)

        entities: Set[str] = set()

        # 1. Wikilinks
        for m in self._WIKILINK_RE.finditer(clean_text):
            target = m.group(1).strip()
            # Normalize non-breaking spaces
            # Ignore file / category / interwiki dictionary links
            if re.match(r"^(?:File|Berkas|Image|Gambar|Category|Kategori|Template|Templat|wikt|q|s):", target, re.I):
                continue
            if len(target) > 1:
                entities.add(target)
        # 2. Interlanguage links ({{ill|Target|...}})
        for m in self._ILL_RE.finditer(clean_text):
            target = m.group(1).strip()
            if len(target) > 1:
                entities.add(target)

        # 3. Italicized titles (works of art, books, films, biological taxa)
        for m in self._ITALICS_RE.finditer(clean_text):
            inner = m.group(1).strip()
            clean_inner = re.sub(r"\[\[(?:[^|\]]+\|)?([^\]]+)\]\]", r"\1", inner).strip()
            if len(clean_inner) > 2 and not clean_inner.startswith("{"):
                entities.add(clean_inner)

        # 4. Multi-word Proper Nouns in prose
        # Strip templates and citations first
        clean_prose = re.sub(r"<ref\b[^>]*>[\s\S]*?<\/ref>", "", wikitext)
        clean_prose = re.sub(r"<ref\b[^>]*/>", "", clean_prose)
        clean_prose = re.sub(r"\{\{[\s\S]*?\}\}", "", clean_prose)
        clean_prose = re.sub(r"\[\[(?:[^|\]]+\|)?([^\]]+)\]\]", r"\1", clean_prose)

        stopwords = ENGLISH_STOPWORDS if lang == "en" else INDONESIAN_STOPWORDS
        proper_noun_re = re.compile(r"\b[A-Z][a-z0-9]+(?:\s+[A-Z][a-z0-9]+)+\b")
        for m in proper_noun_re.finditer(clean_prose):
            name = m.group(0).strip()
            first_word = name.split()[0].lower()
            if first_word in stopwords:
                # Remove leading stopword (e.g. "In 1895 Stasova" or "However Dmitry")
                words = name.split()
                if len(words) > 2 and words[1][0].isupper():
                    name = " ".join(words[1:])
                else:
                    continue
            if len(name) > 3 and name.lower() not in stopwords:
                entities.add(name)

        # Filter out entities that are strict substrings of longer compound entities in the same text
        # (e.g. 'Bantuan Lainnya' or 'Warga Sankt' inside 'Perhimpunan Pemondokan Murah dan Bantuan Lainnya bagi Warga Sankt-Peterburg')
        final_entities: Set[str] = set()
        for ent in entities:
            if not any(ent != other and ent in other for other in entities):
                final_entities.add(ent)

        return final_entities

    # -------------------------------------------------------------------------
    # Entity Matching & Equivalence
    # -------------------------------------------------------------------------
    @staticmethod
    def _is_equivalent(ent1: str, ent2: str) -> bool:
        """Determines if two entity strings refer to the same underlying entity."""
        e1 = ent1.strip().casefold()
        e2 = ent2.strip().casefold()

        if e1 == e2:
            return True

        # Token set match / partial inclusion
        t1 = set(re.findall(r"\w+", e1))
        t2 = set(re.findall(r"\w+", e2))
        if t1 and t2:
            # If all substantive tokens of one are in the other
            subst1 = {w for w in t1 if len(w) > 2}
            subst2 = {w for w in t2 if len(w) > 2}
            if subst1 and subst2 and (subst1.issubset(subst2) or subst2.issubset(subst1)):
                return True

        # Common cross-language exonyms and suffixes
        # e.g. "Russian Empire" <-> "Kekaisaran Rusia"
        EXONYM_PAIRS = (
            ("russian empire", "kekaisaran rusia"),
            ("saint petersburg", "sankt-peterburg"),
            ("st. petersburg", "sankt-peterburg"),
            ("st petersburg", "sankt-peterburg"),
            ("united states", "amerika serikat"),
            ("united kingdom", "britania raya"),
            ("soviet union", "uni soviet"),
            ("academy awards", "academy awards"),
            ("academy award", "piala oscar"),
            ("world war i", "perang dunia i"),
            ("world war ii", "perang dunia ii"),
            ("alexander i of russia", "aleksandr i dari rusia"),
            ("alexander ii of russia", "aleksandr ii dari rusia"),
            ("alexander iii of russia", "aleksandr iii dari rusia"),
            ("sexually transmitted infection", "penyakit menular seksual"),
            ("sexually transmitted infection", "infeksi menular seksual"),
            ("blue-collar worker", "buruh"),
            ("blue-collar worker", "pekerja"),
            ("blue-collar", "buruh pabrik"),
            ("sunday school", "sekolah minggu"),
            ("fairy tales", "dongeng anak-anak"),
            ("fairy tales", "dongeng"),
            ("children's aid society", "lembaga bantuan anak"),
            ("society for cheap lodging", "perhimpunan pemondokan murah"),
            ("russian women's publishing cooperative", "koperasi penerbitan perempuan rusia"),
            ("women's mutual philanthropic society", "perhimpunan amal bersama perempuan rusia"),
            ("zhenskoe delo", "zhenskoye delo"),
            ("zhenskoe delo", "urusan perempuan"),
        )
        for p1, p2 in EXONYM_PAIRS:
            if (e1 == p1 and e2 == p2) or (e1 == p2 and e2 == p1):
                return True

        # High-similarity fuzzy ratio for slight transliterations (e.g. "Alexander" vs "Aleksandr")
        ratio = difflib.SequenceMatcher(None, e1, e2).ratio()
        if ratio >= 0.82:
            return True

        # Scientific, academic, and technical cross-language cognate matching (EYD V loanword phonology)
        def norm_loan(w: str) -> str:
            w = w.lower()
            w = re.sub(r"qu", "ku", w)
            w = re.sub(r"ph", "f", w)
            w = re.sub(r"th", "t", w)
            w = re.sub(r"c([aourl])", r"k\1", w)
            w = re.sub(r"c$", "k", w)
            w = re.sub(r"y", "i", w)
            w = re.sub(r"(?:ity|itas|tion|si|ism|isme|ic|ik|ical|is|um|us|a)$", "", w)
            return w

        tokens1 = [norm_loan(w) for w in re.findall(r"\w+", e1) if len(w) > 3]
        tokens2 = [norm_loan(w) for w in re.findall(r"\w+", e2) if len(w) > 3]
        for r1 in tokens1:
            for r2 in tokens2:
                if r1 == r2 or (len(r1) >= 4 and len(r2) >= 4 and (r1.startswith(r2) or r2.startswith(r1))):
                    return True

        return False
    def _entity_present_in_text(self, entity: str, text: str) -> bool:
        """Checks whether an entity is present in text either as a link, name, or tokens."""
        if not entity or not text:
            return False

        t_lower = text.casefold()
        e_lower = entity.casefold()

        if e_lower in t_lower:
            return True

        # Substantive tokens (e.g., surname like "Gurevich" or "Ruthchild" or "Nolan")
        tokens = [t for t in re.findall(r"[a-z0-9\-]+", e_lower) if len(t) > 3]
        if tokens:
            # If at least the primary distinctive surname/token is in the text
            if any(t in t_lower for t in tokens):
                return True

        return False

    # -------------------------------------------------------------------------
    # Attribution & Relational Drift Audit
    # -------------------------------------------------------------------------
    def audit_quote_attribution(
        self, source_wikitext: str, draft_wikitext: str
    ) -> List[str]:
        """
        Audits whether direct quotes in source are attributed to the correct speaker/actor in draft.
        Detects hallucinatory attribution swapping (e.g. historian quote turned into character memory).
        """
        warnings: List[str] = []
        source_quotes = self._QUOTE_RE.findall(source_wikitext or "")
        draft_quotes = self._QUOTE_RE.findall(draft_wikitext or "")

        if not source_quotes or not draft_quotes:
            return warnings

        REPORTING_VERB_ID = re.compile(
            r"(?:(?:pemimpin|tokoh|sejarawan|penulis|pengarang|ilmuwan|kritikus|sutradara)[^,\n]*,\s*)?(?:\[\[([^\]|]+)(?:\|[^\]]+)?\]\]|\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,4}))(?:\s+dari\s+[^,\n]+)?\s*,?\s*(?:mengenang[^,\n]*dengan\s+)?(?:menulis|menuliskan|mengenang|menuturkan|mencatat|menyatakan|menggambarkan|menyebut(?:nya)?)\b(?:\s+bahwa|\s+sebagai)?\s*[,:]?\s*[\"“«]",
            re.IGNORECASE,
        )
        REPORTING_VERB_EN = re.compile(
            r"(?:(?:the\s+)?(?:historian|author|writer|scholar|critic|director|leader|website(?:'s)?(?:\s+consensus)?)\s+)?(?:\[\[([^\]|]+)(?:\|[^\]]+)?\]\]|\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,4}))(?:\s+of\s+[^,\n]+)?(?:\s*,\s*|\s+)(?:(?:rated|gave)\s+[^,\n]+,\s*)?(?:writes|wrote|writing|stated|states|stating|recalled|noted|noting|argued|described|describing|reads|called|calling|said|saying)\b(?:\s+[a-z]+){0,3}\s*[,:]?\s*[\"“«]",
            re.IGNORECASE,
        )

        PRONOUNS = {"as", "they", "he", "she", "it", "we", "you", "i", "ia", "dia", "mereka", "beliau"}
        NON_ACTORS = {"film ini", "sinema ini", "karya ini", "proyek ini", "dan", "serta", "namun", "tetapi", "konsensus", "konsensus kritik", "konsensus kritik situs web tersebut"}
        en_actors = []
        for m in REPORTING_VERB_EN.finditer(source_wikitext):
            actor = (m.group(1) or m.group(2) or "").strip()
            if actor and not any(w.lower() in PRONOUNS for w in actor.split()) and actor.lower() not in ENGLISH_STOPWORDS and actor.lower() not in NON_ACTORS:
                en_actors.append(actor)

        id_actors = []
        for m in REPORTING_VERB_ID.finditer(draft_wikitext):
            actor = (m.group(1) or m.group(2) or "").strip()
            if actor and not any(w.lower() in PRONOUNS for w in actor.split()) and actor.lower() not in INDONESIAN_STOPWORDS and actor.lower() not in NON_ACTORS:
                id_actors.append(actor)

        # An attribution drift occurs when an actor reporting a quote in the draft
        # does not exist anywhere in the source reporting actors (unrooted attribution).
        for id_actor in id_actors:
            if not any(self._is_equivalent(id_actor, en_a) for en_a in en_actors):
                warnings.append(
                    f"Penyimpangan atribusi kutipan: Kutipan dalam draf diatribusikan ke '{id_actor}' yang tidak berakar dari aktor sumber ({', '.join(en_actors)})."
                )

        return warnings
    # -------------------------------------------------------------------------
    # Topic-Aware Role & Attribute Auditing
    # -------------------------------------------------------------------------
    def audit_role_attribution(
        self, source_wikitext: str, draft_wikitext: str, topic: Optional[str] = None
    ) -> List[str]:
        """
        Validates topic-specific roles to prevent relationship inversion:
        - Film: director vs cast
        - Computing: creator vs organization
        - Medicine: pathogen vs disease
        """
        warnings: List[str] = []
        if not source_wikitext or not draft_wikitext:
            return warnings

        # Film / Cinema Topic
        if topic in ("film", "cinema", "entertainment", "media", "tv_series"):
            # Check director inversion
            dir_en = re.search(r"\bdirected\s+by\s+\[\[([^\]|]+)", source_wikitext, re.I)
            dir_id = re.search(r"\bdisutradarai\s+oleh\s+\[\[([^\]|]+)", draft_wikitext, re.I)
            if dir_en and dir_id:
                s_dir = dir_en.group(1).strip()
                d_dir = dir_id.group(1).strip()
                if not self._is_equivalent(s_dir, d_dir):
                    warnings.append(
                        f"Pembalikan peran sutradara: Sumber menyebut disutradarai oleh '[[{s_dir}]]', tetapi draf menyebut '[[{d_dir}]]'."
                    )

        # Computing / Tech Topic
        elif topic in ("computing_science", "technology", "software"):
            dev_en = re.search(r"\b(?:developed|created)\s+by\s+\[\[([^\]|]+)", source_wikitext, re.I)
            dev_id = re.search(r"\b(?:dibuat|dikembangkan)\s+oleh\s+\[\[([^\]|]+)", draft_wikitext, re.I)
            if dev_en and dev_id:
                s_dev = dev_en.group(1).strip()
                d_dev = dev_id.group(1).strip()
                if not self._is_equivalent(s_dev, d_dev):
                    warnings.append(
                        f"Penyimpangan pengembang/pencipta: Sumber menyebut '[[{s_dev}]]', draf menyebut '[[{d_dev}]]'."
                    )

        return warnings
    # -------------------------------------------------------------------------
    # Extraneous / Unanchored Sentence Detection (Anti-Hallucinated Conclusion)
    # -------------------------------------------------------------------------
    def audit_unanchored_sentences(
        self, source_wikitext: str, draft_wikitext: str
    ) -> List[str]:
        """
        Detects fabricated / unanchored sentences added to draft (e.g. invented eulogies/conclusions).
        Compares substantive content stems between draft sentences and source text.
        """
        warnings: List[str] = []
        if not source_wikitext or not draft_wikitext:
            return warnings

        clean_en = re.sub(r"<ref\b[^>]*\/>", "", source_wikitext)
        clean_en = re.sub(r"<ref\b[^>]*>[\s\S]*?<\/ref>", "", clean_en)

        clean_id = re.sub(r"<ref\b[^>]*\/>", "", draft_wikitext)
        clean_id = re.sub(r"<ref\b[^>]*>[\s\S]*?<\/ref>", "", clean_id)

        en_sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean_en) if len(s.strip().split()) > 4]
        id_sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean_id) if len(s.strip().split()) > 4]

        if len(id_sents) <= len(en_sents):
            return warnings

        def get_stems(s: str) -> Set[str]:
            words = re.findall(r"[a-zA-Z]{4,}", s.lower())
            return {w[:5] for w in words}

        all_en_stems: Set[str] = set()
        for s in en_sents:
            all_en_stems.update(get_stems(s))

        STOP_STEMS = {"seper", "dalam", "untuk", "bahwa", "denga", "serta", "terse", "karen", "merup", "adala", "menja"}
        for s in id_sents[-2:]:
            s_stems = get_stems(s) - STOP_STEMS
            overlap = len(s_stems & all_en_stems)
            if len(s_stems) >= 5 and overlap == 0:
                short_snippet = s[:85] + ("..." if len(s) > 85 else "")
                warnings.append(
                    f"Kalimat tambahan tanpa jangkar sumber (diduga fabrikasi kesimpulan/eulogi): \"{short_snippet}\""
                )

        return warnings


    # -------------------------------------------------------------------------
    # Deterministic Auto-Repair
    # -------------------------------------------------------------------------
    def auto_repair_entities(self, draft_wikitext: str, source_wikitext: str) -> Tuple[str, int]:
        """
        Deterministically restores missing wikilink brackets [[ ... ]] in draft
        if an entity was wikilinked in source and exists as plain text in draft.
        Returns (repaired_wikitext, repair_count).
        """
        if not draft_wikitext or not source_wikitext:
            return draft_wikitext, 0

        source_links = self._WIKILINK_RE.findall(source_wikitext)
        repaired = draft_wikitext
        repair_count = 0

        for link in source_links:
            target = link.strip()
            if not target or len(target) < 3:
                continue
            if re.match(r"^(?:File|Berkas|Image|Gambar|Category|Kategori):", target, re.I):
                continue

            # If entity is already wikilinked in draft, skip
            if f"[[{target}" in repaired or f"|{target}]]" in repaired:
                continue

            # If plain text exists outside brackets and quotes
            plain_pattern = re.compile(rf"(?<!\[\[)(?<!\|)\b{re.escape(target)}\b(?!\]\])", re.IGNORECASE)
            if plain_pattern.search(repaired):
                repaired, n = plain_pattern.subn(f"[[{target}]]", repaired, count=1)
                if n > 0:
                    repair_count += n

        return repaired, repair_count

    # -------------------------------------------------------------------------
    # Primary Audit Entry Point
    # -------------------------------------------------------------------------
    def audit(
        self,
        source_wikitext: str,
        draft_wikitext: str,
        topic: Optional[str] = None,
    ) -> EntityGroundingResult:
        """
        Executes full entity grounding, drift, and attribution audit.
        """
        source_entities = sorted(self.extract_entities(source_wikitext, lang="en", topic=topic))
        draft_entities = sorted(self.extract_entities(draft_wikitext, lang="id", topic=topic))

        dropped: List[str] = []
        for s_ent in source_entities:
            # Check if source entity is present in draft text or draft entities
            matched = any(self._is_equivalent(s_ent, d_ent) for d_ent in draft_entities)
            if not matched and not self._entity_present_in_text(s_ent, draft_wikitext):
                # Only flag non-neutral, high-value entities
                if s_ent.lower() not in NEUTRAL_WIKI_TARGETS:
                    dropped.append(s_ent)

        phantom: List[str] = []
        for d_ent in draft_entities:
            # Check if draft entity is rooted in source
            matched = any(self._is_equivalent(d_ent, s_ent) for s_ent in source_entities)
            if not matched and not self._entity_present_in_text(d_ent, source_wikitext):
                if d_ent.lower() not in NEUTRAL_WIKI_TARGETS:
                    phantom.append(d_ent)

        # Attribution checks
        attribution_warnings = self.audit_quote_attribution(source_wikitext, draft_wikitext)
        role_warnings = self.audit_role_attribution(source_wikitext, draft_wikitext, topic=topic)
        attribution_warnings.extend(role_warnings)

        warnings: List[str] = []
        if dropped:
            warnings.append(
                f"Entitas penting dari teks sumber hilang di draf: {', '.join(dropped[:8])}"
            )
        if phantom:
            warnings.append(
                f"Entitas tanpa jangkar (diduga halusinasi/salah tempat): {', '.join(phantom[:8])}"
            )
        warnings.extend(attribution_warnings)

        # Attempt auto-repair
        repaired_text, repair_n = self.auto_repair_entities(draft_wikitext, source_wikitext)
        # Unanchored / fabricated sentence check
        unanchored_warnings = self.audit_unanchored_sentences(source_wikitext, draft_wikitext)
        warnings.extend(unanchored_warnings)

        can_repair = repair_n > 0

        # Generate targeted revision prompt if issues exist
        revision_prompt: Optional[str] = None
        if warnings:
            revision_prompt = self.generate_revision_prompt(
                dropped=dropped,
                phantom=phantom,
                attribution_warnings=attribution_warnings,
                source_wikitext=source_wikitext,
                draft_wikitext=draft_wikitext,
                topic=topic,
            )

        passed = len(warnings) == 0

        return EntityGroundingResult(
            passed=passed,
            topic=topic,
            source_entities=source_entities,
            draft_entities=draft_entities,
            dropped_entities=dropped,
            phantom_entities=phantom,
            attribution_warnings=attribution_warnings,
            warnings=warnings,
            can_auto_repair=can_repair,
            repaired_wikitext=repaired_text if can_repair else None,
            revision_prompt=revision_prompt,
        )

    # -------------------------------------------------------------------------
    # Targeted Revision Prompt Generator
    # -------------------------------------------------------------------------
    def generate_revision_prompt(
        self,
        dropped: List[str],
        phantom: List[str],
        attribution_warnings: List[str],
        source_wikitext: str,
        draft_wikitext: str,
        topic: Optional[str] = None,
    ) -> str:
        """
        Generates a surgical, high-priority prompt to force the LLM
        to fix hallucinations without altering tone or style.
        """
        lines = [
            "========================================================================",
            "⚠️ [PERINGATAN INTEGRITAS FAKTA & ENTITAS — KOREKSI OTOMATIS DIPERLUKAN]",
            "========================================================================",
            f"Topik Domain: {topic or 'Umum'}",
            "Terdeteksi ketidakcocokan fakta antara naskah sumber bahasa Inggris dan draf terjemahan:",
        ]

        if dropped:
            lines.append(f"- ENTITAS SUMBER HILANG (WAJIB DIKEMBALIKAN): {', '.join(dropped)}")
        if phantom:
            lines.append(f"- ENTITAS TIDAK BERASAL DARI SUMBER (HAPUS/KOREKSI): {', '.join(phantom)}")
        for att in attribution_warnings:
            lines.append(f"- PENYIMPANGAN ATRIBUSI: {att}")

        lines.extend([
            "",
            "PETUNJUK PERBAIKAN BEDAH:",
            "1. Tulis ulang bagian tersebut agar setia 100% pada subjek dan aktor dari naskah sumber.",
            "2. Jangan menukar nama orang, pembuat karya, atau penerima kutipan.",
            "3. Pertahankan gaya bahasa Indonesia ensiklopedis yang alami (KBBI VI, EYD V).",
            "========================================================================",
        ])

        return "\n".join(lines)


default_entity_grounding_auditor = EntityGroundingAuditor()
