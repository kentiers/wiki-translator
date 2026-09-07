"""
Lexical Register & Collocation Weighting Engine for Indonesian Wikipedia.

Elevates casual or generic machine-translated verbs and nouns to mature,
authoritative, and contextually precise encyclopedic diction (Leksikon Berbobot).

Examples:
- "kelompok diskusi (salon) yang diadakan" -> "kelompok diskusi (salon) yang diselenggarakan"
- "organisasi yang dibuat" -> "organisasi yang didirikan"
- "anggaran dasar yang disetujui pemerintah" -> "anggaran dasar yang disahkan pemerintah"
- "buku yang dikeluarkan" -> "buku yang diterbitkan"
- "sebelum kematiannya" -> "menjelang akhir hayatnya" / "sebelum wafat"
"""

import re
from typing import Dict, List, Optional, Tuple


class LexicalRegisterReranker:
    """
    Evaluates and elevates Indonesian vocabulary using contextual collocation weights.
    Distinguishes high-register formal encyclopedic phrasing from flat, generic machine output.
    """

    # High-register contextual substitutions
    # (Regex pattern, replacement, category, explanation)
    CONTEXTUAL_ELEVATION_RULES: List[Tuple[re.Pattern, str, str, str]] = [
        # 1. Event / Forum / Conference / Salon: diadakan -> diselenggarakan
        (
            re.compile(
                r"\b((?:kelompok\s+diskusi|salon|forum|konferensi|kongres|sidang|seminar|pameran|kuliah\s+umum|kelas)(?:\s*\([^)]*\))?)\s+yang\s+diadakan\b",
                re.IGNORECASE,
            ),
            r"\1 yang diselenggarakan",
            "event_elevation",
            "Gunakan 'diselenggarakan' alih-alih 'diadakan' untuk forum formal, salon, dan konferensi.",
        ),
        (
            re.compile(
                r"\bdiadakan\s+(oleh\s+(?:kelompok\s+diskusi|salon|forum|lembaga|panitia))\b",
                re.IGNORECASE,
            ),
            r"diselenggarakan \1",
            "event_elevation",
            "Gunakan 'diselenggarakan' untuk kegiatan yang diinisiasi oleh lembaga atau panitia formal.",
        ),

        # 2. Organization / Institution: dibuat / dibikin -> didirikan / dibentuk
        (
            re.compile(
                r"\b((?:organisasi|perhimpunan|lembaga|koperasi|sekolah|yayasan|komite|asosiasi))\s+(?:yang\s+)?(?:dibuat|dibikin)\b",
                re.IGNORECASE,
            ),
            r"\1 yang didirikan",
            "institution_elevation",
            "Gunakan 'didirikan' alih-alih 'dibuat' untuk organisasi atau lembaga institusional.",
        ),

        # 3. Charters / Treaties / Statutes: disetujui pemerintah / diterima -> disahkan
        (
            re.compile(
                r"\b((?:anggaran\s+dasar|piagam|traktat|perjanjian|statuta|undang-undang))\s+(?:yang\s+)?(?:disetujui\s+oleh|diterima\s+oleh)\s+(pemerintah|kementerian|menteri|tsar|raja|presiden)\b",
                re.IGNORECASE,
            ),
            r"\1 disahkan oleh \2",
            "legal_elevation",
            "Gunakan 'disahkan' untuk anggaran dasar atau dokumen hukum oleh otoritas resmi.",
        ),

        # 4. Publications: buku / jurnal / novel yang dikeluarkan -> diterbitkan
        (
            re.compile(
                r"\b((?:buku|jurnal|novel|karya\s+ilmiah|buku\s+pelajaran|majalah))\s+yang\s+dikeluarkan\b",
                re.IGNORECASE,
            ),
            r"\1 yang diterbitkan",
            "publication_elevation",
            "Gunakan 'diterbitkan' alih-alih 'dikeluarkan' untuk karya pustaka dan buku.",
        ),

        # 5. Death of historical figure: sebelum kematiannya -> menjelang akhir hayatnya
        (
            re.compile(
                r"\bsebelum\s+kematiannya\b",
                re.IGNORECASE,
            ),
            "menjelang akhir hayatnya",
            "death_elevation",
            "Gunakan 'menjelang akhir hayatnya' alih-alih 'sebelum kematiannya' untuk biografi formal.",
        ),
        (
            re.compile(
                r"\bsampai\s+kematiannya\b",
                re.IGNORECASE,
            ),
            "hingga akhir hayatnya",
            "death_elevation",
            "Gunakan 'hingga akhir hayatnya' alih-alih 'sampai kematiannya'.",
        ),

        # 6. Education / Qualifications: mendapatkan pendidikan -> menempuh pendidikan
        (
            re.compile(
                r"\bmendapatkan\s+pendidikan\s+(?:di|pada)\b",
                re.IGNORECASE,
            ),
            "menempuh pendidikan di",
            "education_elevation",
            "Gunakan 'menempuh pendidikan' alih-alih 'mendapatkan pendidikan'.",
        ),
        # 7. Directness: Periphrastic verb phrases -> Direct core verbs
        (
            re.compile(
                r"\bmengambil\s+keputusan\s+untuk\b",
                re.IGNORECASE,
            ),
            "memutuskan untuk",
            "directness_elevation",
            "Gunakan verba inti langsung 'memutuskan untuk' alih-alih 'mengambil keputusan untuk'.",
        ),
        (
            re.compile(
                r"\bmelakukan\s+penolakan\s+terhadap\b",
                re.IGNORECASE,
            ),
            "menolak",
            "directness_elevation",
            "Gunakan verba inti 'menolak' alih-alih frasa bertele-tele 'melakukan penolakan terhadap'.",
        ),
        (
            re.compile(
                r"\bmelakukan\s+kunjungan\s+ke\b",
                re.IGNORECASE,
            ),
            "mengunjungi",
            "directness_elevation",
            "Gunakan verba inti 'mengunjungi' alih-alih frasa 'melakukan kunjungan ke'.",
        ),
        # 8. Bureaucratic Latinate Loanwords -> Natural Core Indonesian Verbs
        (
            re.compile(r"\bmengimplementasikan\b", re.IGNORECASE),
            "menerapkan",
            "bureaucratic_loanword_elevation",
            "Gunakan 'menerapkan' alih-alih kata serapan birokratis 'mengimplementasikan'.",
        ),
        (
            re.compile(r"\bdiimplementasikan\b", re.IGNORECASE),
            "diterapkan",
            "bureaucratic_loanword_elevation",
            "Gunakan 'diterapkan' alih-alih kata serapan birokratis 'diimplementasikan'.",
        ),
        (
            re.compile(r"\bmenginisiasi\b", re.IGNORECASE),
            "memprakarsai",
            "bureaucratic_loanword_elevation",
            "Gunakan 'memprakarsai' alih-alih kata serapan 'menginisiasi'.",
        ),
        (
            re.compile(r"\bdiinisiasi\b", re.IGNORECASE),
            "diprakarsai",
            "bureaucratic_loanword_elevation",
            "Gunakan 'diprakarsai' alih-alih kata serapan 'diinisiasi'.",
        ),
        (
            re.compile(r"\bmerefleksikan\b", re.IGNORECASE),
            "mencerminkan",
            "bureaucratic_loanword_elevation",
            "Gunakan 'mencerminkan' alih-alih kata serapan 'merefleksikan'.",
        ),
        (
            re.compile(r"\bdirefleksikan\b", re.IGNORECASE),
            "dicerminkan",
            "bureaucratic_loanword_elevation",
            "Gunakan 'dicerminkan' alih-alih kata serapan 'direfleksikan'.",
        ),
        (
            re.compile(r"\bmeminimalisir\b", re.IGNORECASE),
            "meminimalkan",
            "spelling_elevation",
            "Gunakan bentuk baku 'meminimalkan' alih-alih bentuk tidak baku 'meminimalisir'.",
        ),
        # 9. Systematic Collocation Elevation (Property, Legislative, Administrative, Diplomatic, Speeches)
        (
            re.compile(r"\bmemprivatisasi\s+(apartemen\s+mereka|apartemen|rumah\s+dinas|rumah|hunian|tempat\s+tinggal)\b", re.IGNORECASE),
            r"mengalihkan kepemilikan \1 menjadi hak milik pribadi",
            "property_elevation",
            "Gunakan 'mengalihkan kepemilikan apartemen/rumah menjadi hak milik pribadi' alih-alih 'memprivatisasi apartemen/rumah'.",
        ),
        (
            re.compile(r"\b((?:kongres|parlemen|majelis|dpr))\s+meloloskan\s+(reformasi|undang-undang|ruu|amendemen|resolusi)\b", re.IGNORECASE),
            r"\1 mengesahkan \2",
            "legislative_elevation",
            "Gunakan 'mengesahkan' alih-alih 'meloloskan' untuk lembaga legislatif.",
        ),
        (
            re.compile(r"\bmeloloskan\s+(undang-undang|ruu|amendemen|resolusi|kebijakan)\b", re.IGNORECASE),
            r"mengesahkan \1",
            "legislative_elevation",
            "Gunakan 'mengesahkan' alih-alih 'meloloskan' untuk undang-undang atau resolusi.",
        ),
        (
            re.compile(r"\bditugaskan\s+ke\s+kantor\b", re.IGNORECASE),
            "ditempatkan di kantor",
            "administrative_elevation",
            "Gunakan 'ditempatkan di kantor' alih-alih 'ditugaskan ke kantor' untuk penempatan dinas.",
        ),
        (
            re.compile(r"\bmembuat\s+pernyataan\s+bahwa\b", re.IGNORECASE),
            "menyatakan bahwa",
            "directness_elevation",
            "Gunakan verba langsung 'menyatakan bahwa' alih-alih 'membuat pernyataan bahwa'.",
        ),
        (
            re.compile(r"\bmembuat\s+kesepakatan\b", re.IGNORECASE),
            "mencapai kesepakatan",
            "diplomatic_elevation",
            "Gunakan 'mencapai kesepakatan' alih-alih 'membuat kesepakatan'.",
        ),
        (
            re.compile(r"\bmembayar\s+kunjungan\s+(?:ke|kepada)\b", re.IGNORECASE),
            "melawat ke",
            "diplomatic_elevation",
            "Gunakan 'melawat ke' atau 'berkunjung ke' alih-alih terjemahan harfiah 'membayar kunjungan ke'.",
        ),
        (
            re.compile(r"\b(?:membuat|memberikan)\s+pidato\b", re.IGNORECASE),
            "menyampaikan pidato",
            "speech_elevation",
            "Gunakan 'menyampaikan pidato' atau 'berpidato' alih-alih 'membuat/memberikan pidato'.",
        ),
        (
            re.compile(r"\bmembuat\s+kemajuan\b", re.IGNORECASE),
            "mencapai kemajuan",
            "directness_elevation",
            "Gunakan 'mencapai kemajuan' alih-alih kalkir 'membuat kemajuan'.",
        ),
    ]

    def elevate_text(self, text: str) -> Tuple[str, int, List[str]]:
        """
        Applies contextual lexical elevation rules to wikitext.
        Returns (elevated_text, elevation_count, elevation_explanations).
        """
        if not text:
            return text, 0, []

        count = 0
        explanations = []
        result = text

        for pattern, replacement, cat, exp in self.CONTEXTUAL_ELEVATION_RULES:
            new_text, n = pattern.subn(replacement, result)
            if n > 0:
                count += n
                explanations.append(f"[{cat}] {exp} ({n}x)")
                result = new_text

        return result, count, explanations

    def calculate_register_score(self, text: str) -> Tuple[int, List[str]]:
        """
        Calculates an Encyclopedic Register Score (0-100) based on diction maturity.
        Penalizes casual / under-elevated collocations in formal prose.
        """
        if not text:
            return 100, []

        deductions = 0
        warnings = []

        for pattern, _, cat, exp in self.CONTEXTUAL_ELEVATION_RULES:
            matches = pattern.findall(text)
            if matches:
                deduct = min(15, len(matches) * 3)
                deductions += deduct
                warnings.append(f"Pilihan kata kurang berbobot: {exp} (ditemukan {len(matches)}x)")

        score = max(0, 100 - deductions)
        return score, warnings
    def suggest_synonyms(self, word: str) -> List[str]:
        """Queries Kateglo thesaurus dynamically for formal synonyms."""
        from .kateglo_client import default_kateglo_client
        return default_kateglo_client.get_synonyms(word)


default_lexical_reranker = LexicalRegisterReranker()
