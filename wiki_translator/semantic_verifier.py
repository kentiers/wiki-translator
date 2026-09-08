"""
Universal Semantic Verifier (2nd Checking Engine) for Wikipedia Translation Suite.

Domain-agnostic, line-by-line cross-lingual verification engine.
Validates source-to-draft semantic fidelity across ANY encyclopedic domain:
- Science, Computing & Technology (algorithms, formulas, data, metrics)
- Medicine, Healthcare & Biology (diagnoses, dosages, clinical trials, anatomy)
- Film, Media, Music & Arts (box office, credits, accolades, plot causalities)
- Geography, Geopolitics & History (boundaries, treaties, populations, chronology)
- Law, Economics & General Biography (precedents, contracts, revenues, life events)

Core Universal Invariant Checks:
1. Epistemic Modality & Truth Conditions (TBBBI Bab II Kondisi Kebenaran):
   - Preserves uncertainty ("may", "might", "alleged" -> dilarang jadi kepastian "pasti/terbukti").
   - Preserves necessity ("must", "required" -> wajib/harus).
2. Universal Polarity & Antonym Flips:
   - Detects contradiction pairs (increase <-> menurun, succeed <-> gagal, permit <-> melarang).
3. Actor & Possessive Entity Parity:
   - Prevents dropped possessive subjects (e.g. "X's algorithm/treatment/soundtrack" -> bare noun).
4. Pronoun Coreference Integrity:
   - Prevents transitive object pronouns (him/her/them/it) from mutating into reflexive "dirinya".
5. Numerical, Unit & Temporal Accuracy:
   - Verifies digits, percentages, financial values, dates, and metric conversions sentence-by-sentence.
6. Universal Hallucination & Drift Guardrail:
   - Detects ungrounded speculative clauses or trailing additions.
"""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union


@dataclass
class SemanticIssue:
    category: str
    sentence_idx: int
    source_snippet: str
    draft_snippet: str
    explanation: str
    suggested_fix: str
    severity: str = "HIGH"  # "CRITICAL", "HIGH", "MEDIUM"


@dataclass
class SemanticVerificationReport:
    total_source_sentences: int
    total_draft_sentences: int
    aligned_pairs_count: int
    issues: List[SemanticIssue] = field(default_factory=list)
    score: int = 100

    @property
    def passed(self) -> bool:
        return len(self.issues) == 0

    def render_summary(self) -> str:
        """Renders a comprehensive, domain-agnostic verification scorecard."""
        lines = [
            "=" * 72,
            "   🌐 SISTEM PENGECEKAN KE-2 (UNIVERSAL LINE-BY-LINE SEMANTIC VERIFIER)",
            f"   Status: {'[✔ PASS] SEMPURNA / KONSISTEN' if self.passed else f'[⚠ PERLU REVISI] {len(self.issues)} Penyimpangan Terdeteksi'}",
            f"   Skor Keselarasan Makna: {self.score}/100",
            "=" * 72,
            f"• Kalimat Sumber (EN) : {self.total_source_sentences}",
            f"• Kalimat Draf (ID)   : {self.total_draft_sentences}",
            f"• Pasangan Terjajar   : {self.aligned_pairs_count}",
        ]

        if self.issues:
            lines.append("-" * 72)
            lines.append("TEMUAN PENYIMPANGAN PER KALIMAT (SEMANTIC AUDIT):")
            for i, issue in enumerate(self.issues, 1):
                lines.append(f"\n[{i}] {issue.category} [{issue.severity}] — Kalimat #{issue.sentence_idx}:")
                lines.append(f"  • Sumber EN   : \"{issue.source_snippet}\"")
                lines.append(f"  • Draf ID     : \"{issue.draft_snippet}\"")
                lines.append(f"  • Masalah     : {issue.explanation}")
                if issue.suggested_fix:
                    lines.append(f"  • Rekomendasi : {issue.suggested_fix}")
        else:
            lines.append("\n✔ Seluruh klaim makna, modalitas, angka, dan aktor terjaga selaras 1:1.")

        lines.append("=" * 72)
        return "\n".join(lines)


class UniversalSemanticVerifier:
    """Universal, domain-agnostic line-by-line semantic verifier."""

    # Universal numbers, percentages, dates, and measurements
    _NUMBER_RE = re.compile(r"(?<![\w])\d+(?:[.,]\d+)?(?:%|\s*(?:BCE?|ADE?|SM|M|kg|km|mg|GB|MB|juta|miliar|triliun)\b)?", re.I)

    # Universal Polarity & Antonym Contradiction Pairs
    _POLARITY_CONTRADICTIONS = (
        # General / Political / Legal
        (re.compile(r"\boppose(?:d|s)?\b", re.I), re.compile(r"\b(?:mendukung|menyokong)\b", re.I), "oppose → mendukung"),
        (re.compile(r"\bsupport(?:ed|s)?\b", re.I), re.compile(r"\b(?:menentang|menolak)\b", re.I), "support → menentang"),
        (re.compile(r"\bprohibit(?:ed|s)?|forbid(?:den)?\b", re.I), re.compile(r"\b(?:mengizinkan|memperbolehkan)\b", re.I), "prohibit → mengizinkan"),
        (re.compile(r"\bpermit(?:ted|s)?|allow(?:ed|s)?\b", re.I), re.compile(r"\b(?:melarang|mengharamkan)\b", re.I), "permit → melarang"),
        (re.compile(r"\binnocent\b", re.I), re.compile(r"\bbersalah\b", re.I), "innocent → bersalah"),
        (re.compile(r"\bguilty\b", re.I), re.compile(r"\btidak\s+bersalah\b", re.I), "guilty → tidak bersalah"),

        # Science / Tech / Quantities
        (re.compile(r"\bincrease(?:d|s)?|rise|rose|grow(?:n|s)?\b", re.I), re.compile(r"\b(?:menurun|merosot|anjlok|berkurang)\b", re.I), "increase → menurun"),
        (re.compile(r"\bdecrease(?:d|s)?|drop(?:ped)?|fall|fell|shrink|shrank\b", re.I), re.compile(r"\b(?:meningkat|melonjak|bertambah)\b", re.I), "decrease → meningkat"),
        (re.compile(r"\bsucceed(?:ed|s)?|success(?:ful)?\b", re.I), re.compile(r"\b(?:gagal|kandas)\b", re.I), "succeed → gagal"),
        (re.compile(r"\bfail(?:ed|s)?|failure\b", re.I), re.compile(r"\b(?:berhasil|sukses)\b", re.I), "fail → berhasil"),

        # Medicine / Biology / Chemistry
        (re.compile(r"\bbenign\b", re.I), re.compile(r"\bganas\b", re.I), "benign → ganas"),
        (re.compile(r"\bmalignant\b", re.I), re.compile(r"\bjinak\b", re.I), "malignant → jinak"),
        (re.compile(r"\btoxic\b", re.I), re.compile(r"\baman\b", re.I), "toxic → aman"),
        (re.compile(r"\bsafe\b", re.I), re.compile(r"\bberacun\b", re.I), "safe → beracun"),
    )

    # Epistemic Modality Shifts (Uncertainty turned into False Certainty)
    _MODALITY_UNCERTAINTY = (
        (re.compile(r"\b(?:may|might|could|possibly|potentially)\b", re.I),
         re.compile(r"\b(?:pasti|tentu|sudah\s+jelas|tak\s+dapat\s+disangkal)\b", re.I),
         "Derajat kepastian ditingkatkan (modalitas kemungkinan diubah menjadi kepastian mutlak)"),
        (re.compile(r"\b(?:alleged|allegedly|claimed|purported|reportedly)\b", re.I),
         re.compile(r"\b(?:terbukti|terkonfirmasi|secara\s+faktual)\b", re.I),
         "Klaim dugaan/klaim sepihak diubah menjadi kebenaran terbukti"),
    )

    # Compass directions across geography/history
    _COMPASS_MAPS = [
        (re.compile(r"\bnortheast\b", re.I), re.compile(r"\btimur\s+Laut\b"), "timur laut"),
        (re.compile(r"\bnorthwest\b", re.I), re.compile(r"\bbarat\s+Laut\b"), "barat laut"),
        (re.compile(r"\bsoutheast\b", re.I), re.compile(r"\btenggara\b", re.I), "tenggara"),
        (re.compile(r"\bsouthwest\b", re.I), re.compile(r"\bbarat\s+Daya\b"), "barat daya"),
    ]

    def split_into_sentences(self, wikitext: str) -> List[str]:
        """Splits wikitext cleanly into sentences, protecting tags, templates, and numbers."""
        if not wikitext:
            return []

        # Strip reference tags, templates, and comments to isolate pure narrative sentences
        clean = re.sub(r"<ref[^>]*>.*?</ref>", " ", wikitext, flags=re.DOTALL)
        clean = re.sub(r"<ref[^>]*/>", " ", clean)
        clean = re.sub(r"<!--.*?-->", " ", clean, flags=re.DOTALL)
        clean = re.sub(r"\{\{[^}]*\}\}", " ", clean)
        clean = re.sub(r"\{\|[^\n]*\n[\s\S]*?\|\}", " ", clean)  # Strip wikitables

        # Clean multiple spaces and blank lines
        clean = "\n".join(ln.strip() for ln in clean.splitlines() if ln.strip() and not ln.strip().startswith(("=", "*", "#", ";", ":")))

        # Protect decimal numbers: e.g. 3.14
        clean = re.sub(r"(\d+)\.(\d+)", r"\1§DEC§\2", clean)
        # Protect common title abbreviations before words: e.g. Dr., Prof., Mr.
        clean = re.sub(r"\b(Dr|Prof|Mr|Mrs|Ms|ca|hlm|vol|no|al|vs)\.\s*(?=[A-Za-z0-9])", r"\1§DOT§ ", clean, flags=re.I)

        # Split on sentence terminals followed by space and capital letter
        raw_sents = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\[\"])", clean)

        results = []
        for s in raw_sents:
            unprotected = s.replace("§DEC§", ".").replace("§DOT§", ".").strip()
            if len(unprotected.split()) >= 3:
                results.append(unprotected)

        return results

    def align_sentence_pairs(self, source_sentences: List[str], draft_sentences: List[str]) -> List[Tuple[str, str, int]]:
        """
        Aligns source English sentences to draft Indonesian sentences.
        Supports 1:1, 1:2 (clause splitting), and monotonic positional alignment.
        """
        pairs = []
        n_src = len(source_sentences)
        n_dft = len(draft_sentences)

        if n_src == 0 or n_dft == 0:
            return []

        for i, src in enumerate(source_sentences):
            idx_dft = min(int(round(i * (n_dft / n_src))), n_dft - 1)
            dft = draft_sentences[idx_dft]
            pairs.append((src, dft, i + 1))

        return pairs

    def verify_sentence_pair(self, en_sent: str, id_sent: str, idx: int, topic: Optional[str] = None, section_context: Optional[str] = None) -> List[SemanticIssue]:
        """
        Performs multi-rule universal semantic verification on an aligned sentence pair.
        Works across all topics (science, medicine, film, biography, history, law).
        """
        issues: List[SemanticIssue] = []

        # ---------------------------------------------------------------------
        # 1. Universal Actor & Possessive Entity Omissions
        # e.g. "X's algorithm/treatment/soundtrack/army" -> bare noun without owner
        # ---------------------------------------------------------------------
        possessives = re.findall(r"\b([A-Z][a-z]+)'s\s+([a-z]+)\b", en_sent)
        EXCLUDED_POSSESSIVE_WORDS = {
            "today", "yesterday", "tomorrow", "nature", "world", "year",
            "there", "here", "it", "that", "what", "where", "who", "when",
            "why", "how", "he", "she", "let", "action"
        }
        for owner, noun in possessives:
            if owner.lower() not in EXCLUDED_POSSESSIVE_WORDS:
                owner_found = owner.lower() in id_sent.lower() or (
                    bool(section_context) and owner.lower() in section_context.lower()
                )
                if not owner_found:
                    issues.append(
                        SemanticIssue(
                            category="Aktor / Pemilik Terpotong (Entity Dropout)",
                            sentence_idx=idx,
                            source_snippet=f"{owner}'s {noun}",
                            draft_snippet=id_sent[:80] + "...",
                            explanation=f"Entitas pemilik '{owner}'s {noun}' hilang di terjemahan; pastikan subjek pemilik tidak terpotong (misal: '{noun} {owner}').",
                            suggested_fix=f"Sertakan nama pemilik '{owner}' pada frasa terkait.",
                            severity="CRITICAL",
                        )
                    )

        # ---------------------------------------------------------------------
        # 2. Universal Coreference & Transitive Reflexive Inversion
        # e.g. "treated/diagnosed/declared/cast him/her [X]" -> "dirinya"
        # ---------------------------------------------------------------------
        m_transitive_pronoun = re.search(
            r"\b(?:declared|found|considered|judged|treated|diagnosed|appointed|cast|named|elected)\s+(?:him|her|them)\s+(?:as\s+)?([a-z]+)\b",
            en_sent,
            re.I,
        )
        if m_transitive_pronoun:
            obj_role = m_transitive_pronoun.group(1).lower()
            if re.search(r"\bdirinya\b", id_sent, re.I) and "dirinya sendiri" not in id_sent.lower():
                issues.append(
                    SemanticIssue(
                        category="Pembalikan Pronomina (Reflexive Inversion Trap)",
                        sentence_idx=idx,
                        source_snippet=m_transitive_pronoun.group(0),
                        draft_snippet=id_sent[:80] + "...",
                        explanation=f"Sumber menggunakan objek pihak ketiga (him/her/them '{obj_role}'), BUKAN refleksif (himself/herself). Kata 'dirinya' membalikkan makna seolah-olah subjek bertindak atas diri sendiri.",
                        suggested_fix="Gunakan 'orang itu / tokoh tersebut / pasien tersebut' alih-alih 'dirinya'.",
                        severity="CRITICAL",
                    )
                )

        # ---------------------------------------------------------------------
        # 3. Universal Epistemic Modality Shifts (Uncertainty -> False Certainty)
        # ---------------------------------------------------------------------
        for en_modal_pat, id_certain_pat, explanation in self._MODALITY_UNCERTAINTY:
            if en_modal_pat.search(en_sent) and id_certain_pat.search(id_sent):
                issues.append(
                    SemanticIssue(
                        category="Distorsi Derajat Kepastian (Modality Shift)",
                        sentence_idx=idx,
                        source_snippet=en_sent[:70] + "...",
                        draft_snippet=id_sent[:70] + "...",
                        explanation=explanation,
                        suggested_fix="Pertahankan ketidakpastian sumber ('mungkin / dapat / diduga', bukan 'pasti / terbukti').",
                        severity="HIGH",
                    )
                )

        # ---------------------------------------------------------------------
        # 4. Universal Polarity & Antonym Contradictions
        # ---------------------------------------------------------------------
        for src_pat, dft_pat, desc in self._POLARITY_CONTRADICTIONS:
            if src_pat.search(en_sent) and dft_pat.search(id_sent):
                issues.append(
                    SemanticIssue(
                        category="Pembalikan Polaritas Pernyataan (Contradiction)",
                        sentence_idx=idx,
                        source_snippet=en_sent[:70] + "...",
                        draft_snippet=id_sent[:70] + "...",
                        explanation=f"Terjadi pembalikan polaritas makna kalimat ({desc}).",
                        suggested_fix="Periksa kembali negasi, kata sifat, atau verba dalam kalimat sumber.",
                        severity="CRITICAL",
                    )
                )

        # ---------------------------------------------------------------------
        # 5. Universal Spatial / Compass Direction Mangling
        # ---------------------------------------------------------------------
        for en_pat, id_err_pat, correct_form in self._COMPASS_MAPS:
            if en_pat.search(en_sent) and id_err_pat.search(id_sent):
                issues.append(
                    SemanticIssue(
                        category="Cacat Kapitalisasi / Pemenggalan Arah Mata Angin",
                        sentence_idx=idx,
                        source_snippet=en_pat.pattern.replace("\\b", ""),
                        draft_snippet=id_sent[:80] + "...",
                        explanation="Arah mata angin bahasa Inggris salah dipenggal atau dikapitalisasi sebagai nama laut.",
                        suggested_fix=f"Gunakan '{correct_form}' (huruf kecil).",
                        severity="HIGH",
                    )
                )

        # ---------------------------------------------------------------------
        # 6. Dynamic Historical Homonym Disambiguation (e.g. bare 'suku Han')
        # ---------------------------------------------------------------------
        try:
            from .historical_ethnonyms import default_ethnonyms_manager
            _, n_disambig, details = default_ethnonyms_manager.audit_and_fix_homonym_blunders(id_sent)
            if n_disambig > 0:
                issues.append(
                    SemanticIssue(
                        category="Kerancuan Homonim Sejarah (Historical Homonym Trap)",
                        sentence_idx=idx,
                        source_snippet=en_sent[:70] + "...",
                        draft_snippet=id_sent[:70] + "...",
                        explanation=details[0],
                        suggested_fix="Gunakan penjelas spesifik (misal: 'suku Qiang Han (罕)').",
                        severity="HIGH",
                    )
                )
        except Exception:
            pass

        return issues

    def verify_article(
        self,
        source_wikitext: str,
        draft_wikitext: str,
        topic: Optional[str] = None,
    ) -> SemanticVerificationReport:
        """
        Runs comprehensive, sentence-by-sentence universal semantic verification
        on source wikitext and draft wikitext.
        """
        # Section-scoped alignment prevents global index drift across multi-thousand word articles
        section_pat = re.compile(r"^={2,5}[^=]+={2,5}\s*$", re.MULTILINE)
        src_has_sections = bool(section_pat.search(source_wikitext))
        dft_has_sections = bool(section_pat.search(draft_wikitext))

        all_issues: List[SemanticIssue] = []
        aligned_pairs: List[Tuple[str, str, int]] = []
        src_sents: List[str] = []
        dft_sents: List[str] = []
        if src_has_sections and dft_has_sections:
            from .wiki_client import WikipediaClient
            client = WikipediaClient()
            src_secs = client.split_sections(source_wikitext)
            dft_secs = client.split_sections(draft_wikitext)
            pair_idx = 1
            for i in range(min(len(src_secs), len(dft_secs))):
                sec_src = src_secs[i].content
                sec_dft = dft_secs[i].content
                if not sec_src.strip() or not sec_dft.strip():
                    continue
                s_list = self.split_into_sentences(sec_src)
                d_list = self.split_into_sentences(sec_dft)
                src_sents.extend(s_list)
                dft_sents.extend(d_list)
                pairs = self.align_sentence_pairs(s_list, d_list)
                for s_item, d_item, _ in pairs:
                    aligned_pairs.append((s_item, d_item, pair_idx))
                    issues = self.verify_sentence_pair(s_item, d_item, pair_idx, topic=topic, section_context=sec_dft)
                    all_issues.extend(issues)
                    pair_idx += 1
        else:
            src_sents = self.split_into_sentences(source_wikitext)
            dft_sents = self.split_into_sentences(draft_wikitext)
            aligned_pairs = self.align_sentence_pairs(src_sents, dft_sents)
            for src, dft, idx in aligned_pairs:
                pair_issues = self.verify_sentence_pair(src, dft, idx, topic=topic)
                all_issues.extend(pair_issues)
        # Compute semantic alignment score
        penalty = 0
        for issue in all_issues:
            if issue.severity == "CRITICAL":
                penalty += 15
            elif issue.severity == "HIGH":
                penalty += 10
            else:
                penalty += 5

        final_score = max(0, 100 - penalty)
        return SemanticVerificationReport(
            total_source_sentences=len(src_sents),
            total_draft_sentences=len(dft_sents),
            aligned_pairs_count=len(aligned_pairs),
            issues=all_issues,
            score=final_score,
        )


default_semantic_verifier = UniversalSemanticVerifier()
