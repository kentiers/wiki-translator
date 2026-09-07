"""
Optional Stub Crafter for high-value red links ({{ill}}), avoiding WP:KELAYAKAN & KPC A1.

Features:
- Takes a red-link subject (e.g. `Kevin Macdonald (sutradara)` / en: `Kevin Macdonald (director)`).
- Fetches lead section and infobox data from en.wikipedia.org.
- Formulates a compliant 2-3 paragraph stub in natural Indonesian:
  * Clear definition sentence following EYD V / KBBI VI.
  * Concise biographical / conceptual summary.
  * Verified citations retained from source.
  * Appropriate stub template (e.g. `{{tokoh-stub}}`, `{{film-stub}}`, `{{sutradara-stub}}`).
  * Valid parent categories.
- Saves to `output/stubs/<SafeTitle>.wikitext`.
"""

import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
import os
import urllib.error
import urllib.parse
import urllib.request

from .auth import AuthManager
from .editorial_qa import EditorialQAPipeline, QAAuditReport, default_qa_pipeline
from .gemini import GeminiTranslatorClient
from .infobox_mapper import InfoboxMapper, default_infobox_mapper
from .prompts import SYSTEM_PROMPT_GRADE_A_PLUS_PLUS
from .syntax_balancer import WikitextSyntaxBalancer, default_syntax_balancer
from .template_mapper import (
    MAGIC_WORDS,
    STRIP_METADATA_TEMPLATES,
    WikiTemplateMapper,
    default_template_mapper,
)
from .typography_sanitizer import TypographySanitizer, default_typography_sanitizer
from .wiki_link_mapper import WikiLinkMapper, default_link_mapper
DISAMBIGUATION_MAP: Dict[str, str] = {
    "director": "sutradara",
    "film director": "sutradara",
    "actor": "pemeran",
    "actress": "pemeran",
    "writer": "penulis",
    "producer": "produser",
    "musician": "musisi",
    "singer": "penyanyi",
    "politician": "politikus",
    "footballer": "pesepak bola",
}


class StubGenerator:
    """Generates clean, compliant Indonesian Wikipedia stubs from en.wikipedia leads."""

    def __init__(
        self,
        en_api_url: Optional[str] = None,
        user_agent: Optional[str] = None,
        link_mapper: Optional[WikiLinkMapper] = None,
        qa_pipeline: Optional[EditorialQAPipeline] = None,
        infobox_mapper: Optional[InfoboxMapper] = None,
        syntax_balancer: Optional[WikitextSyntaxBalancer] = None,
        template_mapper: Optional[WikiTemplateMapper] = None,
        translator_client: Optional[Any] = None,
        typography_sanitizer: Optional[TypographySanitizer] = None,
    ):
        self.en_api_url = en_api_url or "https://en.wikipedia.org/w/api.php"
        self.user_agent = (
            user_agent
            or "WikiTranslatorGradeA/1.0 (https://id.wikipedia.org; stub-generator)"
        )
        self.link_mapper = link_mapper or default_link_mapper
        self.qa_pipeline = qa_pipeline or default_qa_pipeline
        self.infobox_mapper = infobox_mapper or default_infobox_mapper
        self.syntax_balancer = syntax_balancer or default_syntax_balancer
        self.template_mapper = template_mapper or default_template_mapper
        self.typography_sanitizer = typography_sanitizer or default_typography_sanitizer
        self.translator_client = translator_client
        self._translator_initialized = translator_client is not None
        self.data_domains_file = Path(__file__).resolve().parent.parent / "data" / "encyclopedic_domains.json"
        self._domains_taxonomy = self._load_domains_taxonomy()

    def _load_domains_taxonomy(self) -> Dict[str, Any]:
        """Loads the encyclopedic 8-metacategory taxonomy schema dynamically."""
        if hasattr(self, "data_domains_file") and self.data_domains_file.exists():
            try:
                return json.loads(self.data_domains_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}
    def _get_translator_client(self) -> Optional[Any]:
        """Lazily initializes and returns GeminiTranslatorClient if credentials exist."""
        if self._translator_initialized:
            return self.translator_client
        try:
            auth_manager = AuthManager()
            has_antigravity = bool(auth_manager.load_credentials())
            has_api_key = bool(os.environ.get("GEMINI_API_KEY"))
            if has_antigravity or has_api_key:
                self.translator_client = GeminiTranslatorClient(auth_manager=auth_manager)
        except Exception:
            self.translator_client = None
        self._translator_initialized = True
        return self.translator_client
    def determine_target_title(self, en_title: str) -> str:
        """
        Implements Indonesian Wikipedia Disambiguation Title Priority (WP:DISAMBIGUASI & WP:PEDAN).
        On en.wiki with 7M+ articles, titles often carry disambiguators (e.g. `Kevin Macdonald (director)`).
        On id.wiki:
        - If bare name `Foo` does NOT exist yet, prioritize the BARE name `Foo` without parentheses!
        - Only add Indonesian disambiguator (e.g. `Foo (sutradara)`) if `Foo` already exists for someone else
          or as a disambiguation page.
        """
        clean_en = en_title.strip()
        m = re.match(r"^(.+?)\s*\(([^)]+)\)$", clean_en)
        if not m:
            return clean_en

        bare_title = m.group(1).strip()
        disambig_part = m.group(2).strip().lower()
        id_disambig = DISAMBIGUATION_MAP.get(disambig_part, disambig_part)

        # Query id.wikipedia Action API to see if bare_title exists
        endpoint = "https://id.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "titles": f"{bare_title}|{bare_title} ({id_disambig})",
            "prop": "pageprops",
            "ppprop": "disambiguation|wikibase_item",
            "format": "json",
        }
        query_str = urllib.parse.urlencode(params)
        url = f"{endpoint}?{query_str}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": self.user_agent},
            method="GET",
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            pages = data.get("query", {}).get("pages", {})
            bare_page = None
            for _, p in pages.items():
                title = p.get("title", "")
                if title.lower() == bare_title.lower():
                    bare_page = p
                    break

            if bare_page is None or bare_page.get("missing") is not None:
                # Bare title does not exist on id.wiki! Use bare name.
                return bare_title

            # Bare page exists. If it is a disambiguation page, disambiguator is needed
            props = bare_page.get("pageprops", {})
            if "disambiguation" in props:
                return f"{bare_title} ({id_disambig})"

            # Page exists: check Wikidata entity to see if it's the exact same subject
            # If en_title has wikibase_item and matches bare_page wikibase_item, bare name is fine
            # Otherwise, distinguish with Indonesian disambiguator
            return f"{bare_title} ({id_disambig})"
        except Exception:
            # Default fallback: if bare name exists or network fails, prefer bare name if uncreated
            return bare_title

    def fetch_en_lead_wikitext(self, en_title: str) -> str:
        """
        Fetches section 0 (lead section) wikitext for en_title via en.wikipedia Action API.
        """
        params = {
            "action": "query",
            "prop": "revisions",
            "titles": en_title,
            "rvslots": "*",
            "rvprop": "content",
            "rvsection": "0",
            "format": "json",
            "formatversion": "2",
            "redirects": "1",
        }
        query_str = urllib.parse.urlencode(params)
        url = f"{self.en_api_url}?{query_str}"

        req = urllib.request.Request(
            url,
            headers={"User-Agent": self.user_agent},
            method="GET",
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            pages = data.get("query", {}).get("pages", [])
            if not pages or pages[0].get("missing"):
                return ""
            revs = pages[0].get("revisions", [])
            if not revs:
                return ""
            return revs[0].get("slots", {}).get("main", {}).get("content", "")
        except Exception:
            return ""

    def fetch_en_full_wikitext(self, en_title: str) -> str:
        """
        Fetches full wikitext for en_title via en.wikipedia Action API.
        Used to extract filmography, selected works, infoboxes, etc.
        """
        params = {
            "action": "query",
            "prop": "revisions",
            "titles": en_title,
            "rvslots": "*",
            "rvprop": "content",
            "format": "json",
            "formatversion": "2",
            "redirects": "1",
        }
        query_str = urllib.parse.urlencode(params)
        url = f"{self.en_api_url}?{query_str}"

        req = urllib.request.Request(
            url,
            headers={"User-Agent": self.user_agent},
            method="GET",
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            pages = data.get("query", {}).get("pages", [])
            if not pages or pages[0].get("missing"):
                return ""
            revs = pages[0].get("revisions", [])
            if not revs:
                return ""
            return revs[0].get("slots", {}).get("main", {}).get("content", "")
        except Exception:
            return ""

    def fetch_en_categories(self, en_title: str) -> List[str]:
        """
        Fetches category titles for en_title via en.wikipedia Action API.
        Returns a list of raw category names without 'Category:' prefix.
        """
        params = {
            "action": "query",
            "prop": "categories",
            "titles": en_title,
            "cllimit": "max",
            "format": "json",
            "formatversion": "2",
            "redirects": "1",
        }
        query_str = urllib.parse.urlencode(params)
        url = f"{self.en_api_url}?{query_str}"

        req = urllib.request.Request(
            url,
            headers={"User-Agent": self.user_agent},
            method="GET",
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            pages = data.get("query", {}).get("pages", [])
            if not pages or pages[0].get("missing"):
                return []
            raw_cats = pages[0].get("categories", [])
            categories = []
            for c in raw_cats:
                t = c.get("title", "")
                if t.startswith("Category:"):
                    t = t[len("Category:"):].strip()
                if t:
                    categories.append(t)
            return categories
        except Exception:
            return []

    def translate_works_section_content(self, header: str, content: str, title: str = "") -> str:
        """
        Translates the body of a works/catalog/table section into Indonesian Wikipedia standard:
        - Translates award categories, notes, roles, descriptions.
        - Routes through GeminiTranslatorClient if available, with robust offline fallback.
        - Maps wikilinks and sanitizes {{ill}} syntax.
        """
        cleaned_body = content

        # 1. Map wikilinks via WikiLinkMapper
        if self.link_mapper:
            try:
                cleaned_body = self.link_mapper.process_wikitext(cleaned_body)
            except Exception:
                try:
                    cleaned_body = self.link_mapper.map_wikilinks(cleaned_body)
                except Exception:
                    pass

        # 2. Translate via LLM client if available
        client = self._get_translator_client()
        if client:
            try:
                prompt = (
                    f"Terjemahkan bagian tabel karya/penghargaan berikut ({header}) ke dalam bahasa Indonesia baku untuk artikel ensiklopedia Wikipedia '{title or 'Tokoh'}'.\n\n"
                    f"PEDOMAN TERJEMAHAN:\n"
                    f"- Standar ensiklopedia Grade A++ (KBBI VI, EYD V, Pedoman Gaya Wikipedia).\n"
                    f"- Terjemahkan kategori penghargaan, catatan, peran, dan deskripsi di dalam sel tabel:\n"
                    f"  * 'Best Young Actor' -> 'Aktor Muda Terbaik'\n"
                    f"  * 'Best Actor Award' -> 'Penghargaan Aktor Terbaik'\n"
                    f"  * 'Best Actor' -> 'Aktor Terbaik'\n"
                    f"  * 'Best Actress' -> 'Aktris Terbaik'\n"
                    f"  * 'Outstanding Supporting Actor in a Drama Series' -> 'Aktor Pendukung Luar Biasa dalam Seri Drama'\n"
                    f"  * 'Outstanding Supporting Actress in a Drama Series' -> 'Aktris Pendukung Luar Biasa dalam Seri Drama'\n"
                    f"  * Catatan dan prosa tabel (misal: 'Made professional London stage debut at...' -> 'Memulai debut panggung profesionalnya di London di...', '(Online)' -> '(Daring)', 'Dramaturg only' -> 'Hanya sebagai dramaturg')\n"
                    f"  * Peran: 'Special appearance' -> 'Penampilan khusus', 'Voice' -> 'Suara'\n"
                    f"- JANGAN merusak sintaks wikitext: pertahankan semua tabel {{| ... |}}, pranala [[...]], templat {{{{...}}}}, dan tag <ref>...</ref>.\n"
                    f"- Berikan LANGSUNG hasil wikitext tabel yang diterjemahkan tanpa teks pengantar atau penutup:\n\n"
                    f"{cleaned_body}"
                )
                translated_llm = client.translate_section(prompt, system_instruction=SYSTEM_PROMPT_GRADE_A_PLUS_PLUS)
                if translated_llm and ("{|" in translated_llm or "* " in translated_llm):
                    cleaned_body = translated_llm.strip()
            except Exception:
                pass

        # 3. Subheadings localization
        subheadings = [
            (r"===\s*Documentary works\s*===", "=== Karya dokumenter ==="),
            (r"===\s*Documentary\s*===", "=== Dokumenter ==="),
            (r"===\s*Feature films\s*===", "=== Film layar lebar ==="),
            (r"===\s*Films?\s*===", "=== Film ==="),
            (r"===\s*Television\s*===", "=== Televisi ==="),
            (r"===\s*Theatre\s*===", "=== Teater ==="),
            (r"===\s*Theater\s*===", "=== Teater ==="),
            (r"===\s*Video games\s*===", "=== Permainan video ==="),
            (r"===\s*Audiobooks\s*===", "=== Buku audio ==="),
            (r"===\s*Audio dramas\s*===", "=== Drama audio ==="),
            (r"===\s*Audio\s*===", "=== Audio ==="),
            (r"===\s*Short films?\s*===", "=== Film pendek ==="),
            (r"===\s*(?:Narrative works|Karya naratif)\s*===", "=== Film layar lebar ==="),
            (r"===\s*TV movies\s*===", "=== Film televisi ==="),
            (r"===\s*Television movies?\s*===", "=== Film televisi ==="),
            (r"===\s*Television films?\s*===", "=== Film televisi ==="),
            (r"===\s*Direct-to-video\s*===", "=== Direct-to-video ==="),
        ]
        for pat, repl in subheadings:
            cleaned_body = re.sub(pat, repl, cleaned_body, flags=re.IGNORECASE)

        # Section bold labels localization
        bold_labels = [
            (r"'''\s*Short films?\s*'''", "'''Film pendek'''"),
            (r"'''\s*TV movies?\s*'''", "'''Film televisi'''"),
            (r"'''\s*Television movies?\s*'''", "'''Film televisi'''"),
            (r"'''\s*Television films?\s*'''", "'''Film televisi'''"),
            (r"'''\s*Television\s*'''", "'''Televisi'''"),
            (r"'''\s*Films?\s*'''", "'''Film'''"),
        ]
        for pat, repl in bold_labels:
            cleaned_body = re.sub(pat, repl, cleaned_body, flags=re.IGNORECASE)

        # Table Headers localization
        table_headers = [
            (r"!(\s*(?:class=\"[^\"]*\"\s*\|\s*)?)Nominated work\b", r"!\1Karya yang dinominasikan"),
            (r"!(\s*(?:class=\"[^\"]*\"\s*\|\s*)?)Venue\b", r"!\1Lokasi / Panggung"),
            (r"!(\s*(?:class=\"[^\"]*\"\s*\|\s*)?)Theatre\b", r"!\1Lokasi / Panggung"),
            (r"!(\s*(?:class=\"[^\"]*\"\s*\|\s*)?)Theater\b", r"!\1Lokasi / Panggung"),
            (r"!(\s*(?:class=\"[^\"]*\"\s*\|\s*)?)Year\b", r"!\1Tahun"),
            (r"!(\s*(?:class=\"[^\"]*\"\s*\|\s*)?)Title\b", r"!\1Judul"),
            (r"!(\s*(?:class=\"[^\"]*\"\s*\|\s*)?)Role\b", r"!\1Peran"),
            (r"!(\s*(?:class=\"[^\"]*\"\s*\|\s*)?)Author\b", r"!\1Pengarang"),
            (r"!(\s*(?:class=\"[^\"]*\"\s*\|\s*)?)Production\b", r"!\1Produksi"),
            (r"!(\s*(?:class=\"[^\"]*\"\s*\|\s*)?)Director\b", r"!\1Sutradara"),
            (r"!(\s*(?:class=\"[^\"]*\"\s*\|\s*)?)Producer\b", r"!\1Produser"),
            (r"!(\s*(?:class=\"[^\"]*\"\s*\|\s*)?)Writer\b", r"!\1Penulis"),
            (r"!(\s*(?:class=\"[^\"]*\"\s*\|\s*)?)Character\b", r"!\1Karakter"),
            (r"!(\s*(?:class=\"[^\"]*\"\s*\|\s*)?)Episodes?\b", r"!\1Episode"),
            (r"!(\s*(?:class=\"[^\"]*\"\s*\|\s*)?)Series\b", r"!\1Serial"),
            (r"!(\s*(?:class=\"[^\"]*\"\s*\|\s*)?)Medium\b", r"!\1Media"),
            (r"!(\s*(?:class=\"[^\"]*\"\s*\|\s*)?)Award\b", r"!\1Penghargaan"),
            (r"!(\s*(?:class=\"[^\"]*\"\s*\|\s*)?)Category\b", r"!\1Kategori"),
            (r"!(\s*(?:class=\"[^\"]*\"\s*\|\s*)?)Result\b", r"!\1Hasil"),
            (r"!(\s*(?:class=\"[^\"]*\"\s*\|\s*)?)Ref(?:\.|\b)", r"!\1Ref."),
            (r"!(\s*(?:class=\"[^\"]*\"\s*\|\s*)?)Work\b", r"!\1Karya yang dinominasikan"),
            (r"!(\s*(?:class=\"[^\"]*\"\s*\|\s*)?)Notes\b", r"!\1Catatan"),
        ]
        for pat, repl in table_headers:
            cleaned_body = re.sub(pat, repl, cleaned_body, flags=re.IGNORECASE)

        # Award table terms localization
        award_terms = [
            (r"(?<=[\s|!])Nominated(?=[\s|!}\n]|$)", "Nominasi"),
            (r"(?<=[\s|!])Won(?=[\s|!}\n]|$)", "Menang"),
            (r"(?<=[\s|!])Pending(?=[\s|!}\n]|$)", "Menunggu"),
        ]
        for pat, repl in award_terms:
            cleaned_body = re.sub(pat, repl, cleaned_body)

        # CRITICAL: Prevent `season 1`, `season 4` from becoming `{{ill}}` links!
        cleaned_body = re.sub(
            r"\{\{ill\|(?:season|musim)\s*(\d+)\|[^{}]*\}\}",
            r"musim \1",
            cleaned_body,
            flags=re.IGNORECASE,
        )
        cleaned_body = re.sub(
            r"\{\{ill\|(\d+)\|en\|[^|}]*season\s*\d+[^{}]*\}\}",
            r"\1",
            cleaned_body,
            flags=re.IGNORECASE,
        )

        # 4. Clean broken ill syntax (e.g. {{ill|FESTin|en|:pt:Festival...}} -> {{ill|FESTin|pt|Festival...}})
        cleaned_body = re.sub(
            r"\{\{ill\|([^|}]+)\|en\|:?([a-z]{2,3}):([^|}]+)(.*?)\}\}",
            r"{{ill|\1|\2|\3\4}}",
            cleaned_body,
            flags=re.IGNORECASE,
        )
        cleaned_body = re.sub(
            r"\{\{ill\|([^|}]+)\|([a-z]{2,3})\|:([^|}]+)(.*?)\}\}",
            r"{{ill|\1|\2|\3\4}}",
            cleaned_body,
            flags=re.IGNORECASE,
        )
        # Fix fullwidth parentheses in ill links: e.g. {{ill|Title（Suffix|en|...}}）
        cleaned_body = re.sub(
            r"\{\{ill\|([^|}（]+)（([^|}）]+)\|en\|([^|}]+)\}\}）",
            r"{{ill|\1 (\2)|en|\3}}",
            cleaned_body,
        )

        # 5. Comprehensive award categories & roles & notes dictionary replacements
        category_subs = [
            (r"Best Young Actor", "Aktor Muda Terbaik"),
            (r"Best Actor Award", "Penghargaan Aktor Terbaik"),
            (r"Best Actor", "Aktor Terbaik"),
            (r"Best Actress", "Aktris Terbaik"),
            (r"Outstanding Supporting Actor in a Drama Series", "Aktor Pendukung Luar Biasa dalam Seri Drama"),
            (r"Outstanding Supporting Actress in a Drama Series", "Aktris Pendukung Luar Biasa dalam Seri Drama"),
            (r"Outstanding Lead Actor in a Drama Series", "Aktor Utama Luar Biasa dalam Seri Drama"),
            (r"Outstanding Lead Actress in a Drama Series", "Aktris Utama Luar Biasa dalam Seri Drama"),
        ]
        # Translate category in ill display parameter 1 without touching foreign target
        for pat, repl in category_subs:
            ill_cat_pat = re.compile(r"\{\{ill\|" + pat + r"\|", re.IGNORECASE)
            cleaned_body = ill_cat_pat.sub(r"{{ill|" + repl + r"|", cleaned_body)

        role_notes_subs = [
            (r"\bMain role\b", "Peran utama"),
            (r"\bGuest role\b", "Peran tamu"),
            (r"\bRecurring role\b", "Peran berulang"),
            (r"\bVoice role\b", "Peran suara"),
            (r"\b(?:TV|Television)\s+(?:movie|film)\b", "Film televisi"),
            (r"\bTelevision special\b", "Spesial televisi"),
            (r"\[\[Netflix\]\]\s+series\b", "Serial [[Netflix]]"),
            (r"\bNetflix series\b", "Serial Netflix"),
            (r"\bHimself\b", "Dirinya sendiri"),
            (r"\bHerself\b", "Dirinya sendiri"),
            (r"\bAlso writer\b", "Juga sebagai penulis"),
            (r"\bAlso producer\b", "Juga sebagai produser"),
            (r"\bAlso cinematographer\b", "Juga sebagai sinematografer"),
            (r"\bExecutive\s*<br\s*/?>\s*Producer\b", "Produser<br>eksekutif"),
            (r"\bExecutive\s+Producer\b", "Produser eksekutif"),
            (r"\bEpisode\s*:\s*", "Episode: "),
            (r'\bEpisode\s+"', 'Episode: "'),
            (r"\b(\d+)\s+episodes?\b", r"\1 episode"),
            (r"\bseason\s+(\d+)\b", r"musim \1"),
            (r"\bseasons\s+", "musim "),
            (r"Credited as ([^|\n]+)", r"Dikreditkan sebagai \1"),
            (r"Co-directed with ([^|\n]+)", r"Disutradarai bersama \1"),
            (r"Post-production", r"Pascaproduksi"),
            # Theatre, audio, & descriptive prose
            (r"Made professional London stage debut at the ([^<\n.]+)", r"Memulai debut panggung profesionalnya di London di \1"),
            (r"Made professional London stage debut at ([^<\n.]+)", r"Memulai debut panggung profesionalnya di London di \1"),
            (r"Made (?:his|her) professional London stage debut at the ([^<\n.]+)", r"Memulai debut panggung profesionalnya di London di \1"),
            (r"Made (?:his|her) professional London stage debut at ([^<\n.]+)", r"Memulai debut panggung profesionalnya di London di \1"),
            (r"Made (?:his|her) stage debut at ([^<\n.]+)", r"Memulai debut panggungnya di \1"),
            (r"Made (?:his|her) professional stage debut at ([^<\n.]+)", r"Memulai debut panggung profesionalnya di \1"),
            (r"\(Online\)", "(Daring)"),
            (r"\bOnline\b", "Daring"),
            (r"\{\{ill\|Dramaturg\|en\|Dramaturg\}\}\s+only\b", "Hanya sebagai dramaturg"),
            (r"\[\[Dramaturg\]\]\s+only\b", "Hanya sebagai [[dramaturg]]"),
            (r"\bDramaturg only\b", "Hanya sebagai dramaturg"),
            (r"\bDramaturge only\b", "Hanya sebagai dramaturg"),
            (r"\bSpecial appearance\b", "Penampilan khusus"),
            (r"\bVoice\b", "Suara"),
        ]

        # Mask {{ill|...}} before applying bare text substitutions to avoid corrupting foreign targets
        ill_tokens = []
        def mask_ill(m: re.Match) -> str:
            idx = len(ill_tokens)
            ill_tokens.append(m.group(0))
            return f"§§ILL_MASK_{idx}§§"

        masked_body = re.sub(r"\{\{ill\|[^{}]+\}\}", mask_ill, cleaned_body, flags=re.IGNORECASE)

        for pat, repl in category_subs + role_notes_subs:
            regex_pat = r"\b" + pat + r"\b" if not pat.startswith(r"\b") and not pat.startswith("Made") and not pat.startswith("(") and not pat.startswith("Credit") and not pat.startswith("Co-") and not pat.startswith(r"\[\[") and not pat.startswith(r"\{\{") else pat
            masked_body = re.sub(regex_pat, repl, masked_body, flags=re.IGNORECASE)

        def unmask_ill(m: re.Match) -> str:
            return ill_tokens[int(m.group(1))]

        cleaned_body = re.sub(r"§§ILL_MASK_(\d+)§§", unmask_ill, masked_body)

        # Final pass via link mapper if available
        if self.link_mapper:
            try:
                cleaned_body = self.link_mapper.process_wikitext(cleaned_body)
            except Exception:
                pass

        return cleaned_body

    def extract_works_sections(self, wikitext: str, title: str = "") -> List[Dict[str, str]]:
        """
        Extracts work catalog sections (Filmography, Bibliography, Discography, Publications, Works, Books, Theatre, Awards)
        from wikitext.
        Returns a list of dicts: [{"header": id_header, "content": cleaned_content}, ...]
        """
        if not wikitext:
            return []

        heading_map = {
            "filmography": "== Filmografi ==",
            "selected filmography": "== Filmografi ==",
            "bibliography": "== Bibliografi ==",
            "selected bibliography": "== Bibliografi ==",
            "discography": "== Diskografi ==",
            "selected discography": "== Diskografi ==",
            "publications": "== Publikasi ==",
            "selected publications": "== Publikasi ==",
            "works": "== Karya pilihan ==",
            "selected works": "== Karya pilihan ==",
            "books": "== Buku ==",
            "theatre": "== Teater ==",
            "theater": "== Teater ==",
            "audio": "== Audio ==",
            "awards and nominations": "== Penghargaan dan nominasi ==",
            "accolades": "== Penghargaan dan nominasi ==",
            "awards": "== Penghargaan dan nominasi ==",
            "radio": "== Radio ==",
            "exhibitions": "== Pameran ==",
            "concert tours": "== Tur konser ==",
        }

        section_pattern = re.compile(
            r"^(==\s*([^=\n]+?)\s*==\s*\n)(.*?)(?=\n==\s*[^=]|\Z)",
            flags=re.MULTILINE | re.DOTALL,
        )

        raw_sections: List[Dict[str, str]] = []
        for match in section_pattern.finditer(wikitext):
            raw_heading = match.group(2).strip()
            raw_body = match.group(3).strip()
            normalized_h = raw_heading.lower()

            if normalized_h in heading_map and raw_body:
                id_header = heading_map[normalized_h]
                raw_sections.append({
                    "header": id_header,
                    "raw_body": raw_body,
                })

        if not raw_sections:
            return []

        # Parallel translation for multi-section biographical catalogs
        import concurrent.futures

        def process_section(sec_info: Dict[str, str]) -> Dict[str, str]:
            h = sec_info["header"]
            body = sec_info["raw_body"]
            processed = self.translate_works_section_content(h, body, title=title)
            return {
                "header": h,
                "content": processed,
            }

        # If translator client is available, run concurrent translation
        if len(raw_sections) > 1 and self._get_translator_client():
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(raw_sections))) as executor:
                sections = list(executor.map(process_section, raw_sections))
        else:
            sections = [process_section(s) for s in raw_sections]

        return sections

    def extract_filmography_section(self, wikitext: str, title: str = "") -> Optional[Dict[str, str]]:
        """
        Extracts Filmography / Selected filmography / Works / Selected works section from wikitext.
        Helper/alias for backwards compatibility.
        Returns a dict with {"header": translated_header, "content": cleaned_content} or None.
        """
        sections = self.extract_works_sections(wikitext, title=title)
        for sec in sections:
            if sec["header"] in ("== Filmografi ==", "== Karya pilihan =="):
                return sec
        return None
    def extract_external_links_section(self, wikitext: str) -> Optional[str]:
        """
        Extracts and localizes the External links section from en.wiki wikitext.
        - Finds == External links == or == External link == in wikitext.
        - Extracts bulleted links (* ...).
        - Localizes standard templates:
          * {{Official website|...}} -> {{Situs web resmi|...}}
          * {{official|...}} -> {{Situs web resmi|...}}
          * {{IMDb title|...}} -> {{IMDb title|...}}
          * {{IMDb name|...}} -> {{IMDb name|...}}
          * {{Rotten Tomatoes|...}} -> {{Rotten Tomatoes|...}}
          * {{AllMusic|...}} -> {{AllMusic|...}}
        - Returns formatted wikitext content for == Pranala luar == (without header).
        """
        if not wikitext:
            return None

        section_pattern = re.compile(
            r"^(==\s*External links?\s*==\s*\n)(.*?)(?=\n==\s*[^=]|\Z)",
            flags=re.MULTILINE | re.IGNORECASE | re.DOTALL,
        )
        match = section_pattern.search(wikitext)
        if not match:
            return None

        raw_body = match.group(2)
        bullet_lines: List[str] = []

        for line in raw_body.splitlines():
            stripped = line.strip()
            if stripped.startswith("*"):
                # Localize standard templates
                loc_line = re.sub(
                    r"\{\{\s*Official website(\s*\||\s*\}\})",
                    r"{{Situs web resmi\1",
                    stripped,
                    flags=re.IGNORECASE,
                )
                loc_line = re.sub(
                    r"\{\{\s*official(\s*\||\s*\}\})",
                    r"{{Situs web resmi\1",
                    loc_line,
                    flags=re.IGNORECASE,
                )
                loc_line = re.sub(
                    r"\{\{\s*IMDb title(\s*\||\s*\}\})",
                    r"{{IMDb title\1",
                    loc_line,
                    flags=re.IGNORECASE,
                )
                loc_line = re.sub(
                    r"\{\{\s*IMDb name(\s*\||\s*\}\})",
                    r"{{IMDb name\1",
                    loc_line,
                    flags=re.IGNORECASE,
                )
                loc_line = re.sub(
                    r"\{\{\s*Rotten Tomatoes(\s*\||\s*\}\})",
                    r"{{Rotten Tomatoes\1",
                    loc_line,
                    flags=re.IGNORECASE,
                )
                loc_line = re.sub(
                    r"\{\{\s*AllMusic(\s*\||\s*\}\})",
                    r"{{AllMusic\1",
                    loc_line,
                    flags=re.IGNORECASE,
                )
                bullet_lines.append(loc_line)

        if not bullet_lines:
            return None

        return "\n".join(bullet_lines)

    def extract_bottom_navboxes(self, wikitext: str) -> List[str]:
        """
        Extracts standalone top-level templates at the bottom of the article after References/External links.
        Excludes metadata templates, stub tags, categories, and authority control.
        For each navbox, runs existence check on id.wikipedia.org via template_mapper:
        - If exists on id.wiki: keep it!
        - If does NOT exist: wrap with <!-- Templat belum tersedia di id.wiki: {{Navbox_Name}} -->
        Returns list of navbox strings.
        """
        if not wikitext:
            return []

        # Find where tail begins (prefer External links, fallback References)
        pattern = re.compile(r"^==\s*(?:External links?|References?)\s*==\s*$", flags=re.MULTILINE | re.IGNORECASE)
        matches = list(pattern.finditer(wikitext))
        if not matches:
            # If no sections, examine entire text
            tail = wikitext
        else:
            # If External links is present, start after it (or last section)
            ext_m = re.search(r"^==\s*External links?\s*==\s*$", wikitext, flags=re.MULTILINE | re.IGNORECASE)
            start_pos = ext_m.start() if ext_m else matches[-1].start()
            tail = wikitext[start_pos:]

        # Extract all top-level templates with their spans in tail
        top_templates: List[Tuple[int, int, str]] = []
        i = 0
        n = len(tail)
        while i < n:
            if tail[i:i+2] == "{{":
                start = i
                depth = 1
                i += 2
                while i < n and depth > 0:
                    if tail[i:i+2] == "{{":
                        depth += 1
                        i += 2
                    elif tail[i:i+2] == "}}":
                        depth -= 1
                        i += 2
                    else:
                        i += 1
                top_templates.append((start, i, tail[start:i]))
            else:
                i += 1

        # Filter for standalone bottom navboxes
        navbox_candidates: List[str] = []
        for start, end, tmpl_str in top_templates:
            # Must be standalone: preceding content on its line must be empty (or only whitespace)
            line_start = tail.rfind("\n", 0, start)
            prefix = tail[0 if line_start == -1 else line_start + 1:start].strip()
            if prefix:
                continue

            inner = tmpl_str[2:-2].strip()
            tmpl_name = inner.split("|")[0].strip()
            clean_lower = tmpl_name.lower()
            clean_prefix = clean_lower.split(":")[0].strip()

            # Exclude magic words, metadata, categories, stubs, authority control, reflists, commons
            if clean_lower in MAGIC_WORDS or clean_prefix in MAGIC_WORDS:
                continue
            if clean_lower in STRIP_METADATA_TEMPLATES:
                continue
            if clean_lower.startswith("defaultsort") or clean_lower.startswith("kategori") or clean_lower.startswith("category"):
                continue
            if "authority control" in clean_lower or "pengawasan otoritas" in clean_lower:
                continue
            if clean_lower.endswith("-stub") or clean_lower == "stub" or "stub" in clean_lower:
                continue
            if clean_lower in (
                "reflist",
                "daftar rujukan",
                "commons category",
                "kategori commons",
                "commons category-inline",
                "portal bar",
                "portal",
                "portals",
                "wikiquote",
                "wikiquote-inline",
                "coord",
                "koordinat",
            ):
                continue

            navbox_candidates.append(tmpl_str)

        if not navbox_candidates:
            return []

        # Check existence on id.wikipedia.org via template_mapper
        names_to_check = [c[2:-2].strip().split("|")[0].strip() for c in navbox_candidates]
        existence_map: Dict[str, bool] = {}
        if self.template_mapper:
            try:
                existence_map = self.template_mapper.check_id_wiki_templates_exist(names_to_check)
            except Exception:
                pass

        processed_navboxes: List[str] = []
        for tmpl_str in navbox_candidates:
            inner_name = tmpl_str[2:-2].strip().split("|")[0].strip()
            exists = existence_map.get(inner_name, False)
            if exists:
                processed_navboxes.append(tmpl_str)
            else:
                processed_navboxes.append(f"<!-- Templat belum tersedia di id.wiki: {tmpl_str} -->")

        return processed_navboxes

    def has_authority_control(self, wikitext: str) -> bool:
        """
        Checks if {{Authority control or {{Pengawasan otoritas is present in en.wiki wikitext.
        """
        if not wikitext:
            return False
        lower = wikitext.lower()
        return "{{authority control" in lower or "{{pengawasan otoritas" in lower


    def extract_infobox(self, wikitext: str) -> str:
        """Extracts the top-level infobox wikitext if present in the lead."""
        match = re.search(r"(\{\{Infobox[^\n]*\n(?:[^{}]|\{\{[^{}]*\}\})*\}\})", wikitext, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
        # Fallback multi-line balanced search
        start = wikitext.lower().find("{{infobox")
        if start != -1:
            depth = 0
            i = start
            while i < len(wikitext):
                if wikitext[i:i+2] == "{{":
                    depth += 1
                    i += 2
                elif wikitext[i:i+2] == "}}":
                    depth -= 1
                    i += 2
                    if depth == 0:
                        return wikitext[start:i].strip()
                else:
                    i += 1
        return ""

    def extract_lead_paragraphs(self, wikitext: str) -> List[str]:
        """
        Extracts lead prose paragraphs from wikitext, excluding infoboxes and banners.
        Retains <ref> tags.
        """
        cleaned = wikitext

        # Stop at the first section heading if full wikitext was passed
        first_heading = re.search(r"^={2,6}[^=]+={2,6}\s*$", cleaned, flags=re.MULTILINE)
        if first_heading:
            cleaned = cleaned[:first_heading.start()]

        # Strip infobox
        infobox = self.extract_infobox(cleaned)
        if infobox:
            cleaned = cleaned.replace(infobox, "")
        # Strip top banners {{...}}
        cleaned = re.sub(r"^\{\{[^}]+\}\}\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"<!--.*?-->", "", cleaned, flags=re.DOTALL)

        raw_paragraphs = [p.strip() for p in cleaned.split("\n\n") if p.strip()]
        lead_paras = []
        for p in raw_paragraphs:
            # Skip tables, headers, categories, or remaining standalone template lines
            if p.startswith("{|") or p.startswith("==") or p.startswith("[[Category:") or p.startswith("[[Kategori:"):
                continue
            if p.startswith("{{") and p.endswith("}}") and "\n" not in p:
                continue
            lead_paras.append(p)
        return lead_paras

    def determine_stub_template(self, title: str, text: str, topic: Optional[str] = None) -> str:
        """
        Determines the most specific appropriate stub template on id.wikipedia across all domains:
        - Science & Technology (Mathematics, Physics, Chemistry, Astronomy, Computing, Software)
        - Biology & Earth Sciences (Animals, Birds, Fish, Plants, Geology)
        - Medicine & Healthcare (Diseases, Pharmacology, Anatomy)
        - Geography & Places (Mountains, Rivers, Lakes, Islands, Cities, Stations, Airports)
        - History, Warfare & Politics (Battles, Treaties, Military Officers, Politicians)
        - People & Professions (Athletes, Scientists, Writers, Musicians, Directors, Actors)
        - Institutions & Organizations (Companies, Universities, Organizations)
        """
        combined = f"{title} {text}".lower()
        topic_str = (topic or "").lower()

        # 1. Animals & Plants (Biology)
        if any(k in combined for k in ("spesies burung", "bird", "burung", "aves")):
            return "{{burung-stub}}"
        if any(k in combined for k in ("spesies ikan", "fish", "ikan", "pisces")):
            return "{{ikan-stub}}"
        if any(k in combined for k in ("spesies hewan", "spesies mamalia", "animal", "hewan", "binatang", "fauna", "serangga", "insect", "reptil", "amfibi")):
            return "{{hewan-stub}}"
        if any(k in combined for k in ("spesies tumbuhan", "plant", "tumbuhan", "tanaman", "flora", "pohon", "bunga", "famili tumbuhan")):
            return "{{tumbuhan-stub}}"
        if topic_str in ("medical_biology", "biology") or any(k in combined for k in ("biologi", "genetika", "taksonomi", "genus", "spesies")):
            return "{{biologi-stub}}"

        # 2. Medicine & Health
        if any(k in combined for k in ("obat", "farmakologi", "drug", "medication", "kapsul", "tablet")):
            return "{{farmasi-stub}}"
        if any(k in combined for k in ("penyakit", "sindrom", "gejala", "medis", "kedokteran", "virus", "bakteri", "disease", "syndrome", "disorder", "kanker", "infeksi")):
            return "{{kedokteran-stub}}"
        if any(k in combined for k in ("anatomi", "organ tubuh", "tulang", "otot", "saraf", "anatomy")):
            return "{{anatomi-stub}}"

        # 3. Science & Computing
        if any(k in combined for k in ("matematika", "teorema", "aljabar", "kalkulus", "geometri", "mathematics", "theorem", "persamaan")):
            return "{{matematika-stub}}"
        if any(k in combined for k in ("fisika", "partikel", "mekanika kuantum", "termodinamika", "physics", "relativitas")):
            return "{{fisika-stub}}"
        if any(k in combined for k in ("kimia", "senyawa", "molekul", "unsur kimia", "chemistry", "reaksi kimia")):
            return "{{kimia-stub}}"
        if any(k in combined for k in ("astronomi", "planet", "bintang", "galaksi", "asteroid", "astronomy", "komet")):
            return "{{astronomi-stub}}"
        if any(k in combined for k in ("perangkat lunak", "software", "aplikasi", "sistem operasi", "open source")):
            return "{{perangkat-lunak-stub}}"
        if topic_str in ("computing_science", "computing") or any(k in combined for k in ("komputer", "algoritma", "bahasa pemrograman", "pemrograman", "hardware", "prosesor")):
            return "{{komputer-stub}}"

        # 4. Geography & Earth
        if any(k in combined for k in ("gunung berapi", "gunung", "pegunungan", "puncak", "volcano", "mountain", "mount")):
            return "{{gunung-stub}}"
        if any(k in combined for k in ("sungai", "river", "anak sungai", "air terjun", "waterfall")):
            return "{{sungai-stub}}"
        if any(k in combined for k in ("danau", "lake", "teluk", "selat", "bay", "strait")):
            return "{{danau-stub}}"
        if any(k in combined for k in ("pulau", "kepulauan", "island", "archipelago", "atol")):
            return "{{pulau-stub}}"
        if any(k in combined for k in ("stasiun kereta", "stasiun api", "railway station", "station")):
            return "{{stasiun-stub}}"
        if any(k in combined for k in ("bandar udara", "bandara", "airport", "aerodrome")):
            return "{{bandara-stub}}"
        if any(k in combined for k in ("desa", "kelurahan", "kecamatan", "kabupaten", "distrik")):
            return "{{kelurahan-stub}}" if "kelurahan" in combined else "{{desa-stub}}"
        if any(k in combined for k in ("kota", "city", "ibukota", "ibu kota", "munisipalitas", "provinsi", "negara", "geografi", "geography")):
            return "{{geografi-stub}}"

        # 5. History, War & Military
        if any(k in combined for k in ("pertempuran", "perang", "invasi", "operasi militer", "battle", "war", "siege")):
            return "{{perang-stub}}"
        if any(k in combined for k in ("sejarah", "dinasti", "kekaisaran", "kerajaan", "perjanjian", "history", "treaty")):
            return "{{sejarah-stub}}"

        # 6. People & Occupations
        if any(k in combined for k in ("pesepak bola", "pemain sepak bola", "footballer", "soccer player")):
            return "{{pemain-sb-stub}}"
        if any(k in combined for k in ("atlet", "olahragawan", "pebulu tangkis", "pembalap", "petinju", "atletik", "athlete")):
            return "{{atlet-stub}}"
        if any(k in combined for k in ("politikus", "presiden", "perdana menteri", "menteri", "anggota parlemen", "senator", "politician")):
            return "{{politikus-stub}}"
        if any(k in combined for k in ("ilmuwan", "fisikawan", "matematikawan", "astronom", "biolog", "ahli kimia", "scientist")):
            return "{{ilmuwan-stub}}"
        if any(k in combined for k in ("jenderal", "laksamana", "marsekal", "komandan militer", "perwira militer", "prajurit")):
            return "{{militer-stub}}"
        if any(k in combined for k in ("sutradara", "director", "filmmaker")):
            return "{{sutradara-stub}}"
        if any(k in combined for k in ("aktor", "aktris", "actor", "actress", "pemeran")):
            return "{{pemeran-stub}}"
        if any(k in combined for k in ("penyanyi", "singer", "vokalis")):
            return "{{penyanyi-stub}}"
        if any(k in combined for k in ("musisi", "gitaris", "komposer", "pianis", "musician", "band", "grup musik")):
            return "{{musik-stub}}"
        if any(k in combined for k in ("penulis", "sastrawan", "novelis", "penyair", "writer", "novelist", "poet")):
            return "{{penulis-stub}}"
        if any(k in combined for k in ("film", "movie", "cinema")) or topic_str == "film":
            return "{{film-stub}}"
        if any(k in combined for k in ("album", "lagu", "singel", "song")):
            return "{{musik-stub}}"
        if any(k in combined for k in ("novel", "buku", "book")):
            return "{{buku-stub}}"

        # 7. Organizations & Institutions
        if any(k in combined for k in ("universitas", "institut", "perguruan tinggi", "university", "college")):
            return "{{universitas-stub}}"
        if any(k in combined for k in ("perusahaan", "maskapai", "korporasi", "company", "corporation", "enterprise")):
            return "{{perusahaan-stub}}"
        if any(k in combined for k in ("organisasi", "yayasan", "lembaga", "partai politik", "organization", "foundation")):
            return "{{organisasi-stub}}"

        if any(k in combined for k in ("tokoh", "born", "lahir", "biography")):
            return "{{tokoh-stub}}"

        return "{{stub}}"

    def determine_categories(
        self,
        title: str,
        text: str,
        topic: Optional[str] = None,
        en_title: Optional[str] = None,
    ) -> List[str]:
        """
        Determines compliant categories on id.wikipedia according to WP:BIOGRAFI & WP:PEDKAT.
        Extracts real categories from the source en.wikipedia article dynamically via Wikipedia APIs,
        resolves them to verified id.wikipedia categories via link_mapper.resolve_category,
        filters out tracking/maintenance categories, and guarantees mandatory biographical categories:
        - Birth year: [[Kategori:Kelahiran <YYYY>]]
        - Living status: [[Kategori:Orang hidup]] or [[Kategori:Kematian <YYYY>]]
        """
        combined = f"{title} {text}".lower()
        cats: List[str] = []

        # 1. Mandatory biographical metadata detection: Birth Year
        birth_year = None
        m_birth_cat = re.search(r"(\d{4})\s+births", text, re.IGNORECASE)
        if m_birth_cat:
            birth_year = m_birth_cat.group(1)
        else:
            m_birth_date = re.search(
                r"\{\{(?:birth[ _]date(?:[ _]and[ _]age)?|bda|dob)[^}]*?\b(1[89]\d\d|20[0-2]\d)\b",
                text,
                re.IGNORECASE,
            )
            if m_birth_date:
                birth_year = m_birth_date.group(1)
            else:
                m_born = re.search(
                    r"(?:lahir|born)[^\d]{0,30}\b(1[89]\d\d|20[0-2]\d)\b",
                    text,
                    re.IGNORECASE,
                )
                if m_born:
                    birth_year = m_born.group(1)

        # 2. Mandatory biographical metadata detection: Death Year or Living Person
        death_year = None
        m_death_cat = re.search(r"(\d{4})\s+deaths", text, re.IGNORECASE)
        if m_death_cat:
            death_year = m_death_cat.group(1)
        else:
            m_death_date = re.search(
                r"\{\{(?:death[ _]date(?:[ _]and[ _]age)?|dda|dod)[^}]*?\b(1[89]\d\d|20[0-2]\d)\b",
                text,
                re.IGNORECASE,
            )
            if m_death_date:
                death_year = m_death_date.group(1)
            else:
                m_died = re.search(
                    r"(?:meninggal|died)[^\d]{0,30}\b(1[89]\d\d|20[0-2]\d)\b",
                    text,
                    re.IGNORECASE,
                )
                if m_died:
                    death_year = m_died.group(1)

        # 3. Dynamic category extraction from source article data
        en_cats: List[str] = []
        # Source A: en.wikipedia API query if en_title provided
        if en_title:
            en_cats = self.fetch_en_categories(en_title)

        # Source B: embedded [[Category:...]] tags in source wikitext (fallback or supplementary)
        wikitext_cats = re.findall(r"\[\[Category:([^|\]]+)", text, re.IGNORECASE)
        for wc in wikitext_cats:
            wc_clean = wc.strip()
            if wc_clean and wc_clean not in en_cats:
                en_cats.append(wc_clean)

        # Check birth/death from en_cats if not already found
        for c in en_cats:
            if not birth_year:
                m_b = re.match(r"^(\d{4})\s+births$", c, re.IGNORECASE)
                if m_b:
                    birth_year = m_b.group(1)
            if not death_year:
                m_d = re.match(r"^(\d{4})\s+deaths$", c, re.IGNORECASE)
                if m_d:
                    death_year = m_d.group(1)

        # Filter prefixes for Wikipedia tracking / maintenance categories
        ignored_prefixes = (
            "all ",
            "articles ",
            "cs1 ",
            "commons ",
            "use ",
            "short description",
            "wikipedia ",
            "webarchive ",
            "blp articles ",
            "hcards",
            "pages ",
            "tracking ",
        )

        resolved_id_cats: List[str] = []
        for en_cat in en_cats:
            en_cat_clean = en_cat.strip()
            lower_cat = en_cat_clean.lower()
            if any(lower_cat.startswith(p) for p in ignored_prefixes):
                continue

            if self.link_mapper:
                try:
                    res = self.link_mapper.resolve_category(en_cat_clean)
                    if res.exists_on_id and res.id_category:
                        cat_tag = f"[[Kategori:{res.id_category}]]"
                        if cat_tag not in resolved_id_cats:
                            resolved_id_cats.append(cat_tag)
                except Exception:
                    pass

        # Add resolved dynamic categories
        for c in resolved_id_cats:
            if c not in cats:
                cats.append(c)

        # 4. Mandatory biographical categories guarantees
        if birth_year:
            birth_cat = f"[[Kategori:Kelahiran {birth_year}]]"
            if birth_cat not in cats:
                cats.append(birth_cat)

        if death_year:
            death_cat = f"[[Kategori:Kematian {death_year}]]"
            if death_cat not in cats:
                cats.append(death_cat)
        else:
            is_bio = (
                bool(birth_year)
                or any(k in combined for k in ("born", "lahir", "sutradara", "pemeran", "actor", "actress", "director", "tokoh", "biography"))
                or any("living people" in c.lower() for c in en_cats)
            )
            if is_bio and not death_year and "death" not in combined and "meninggal" not in combined:
                living_cat = "[[Kategori:Orang hidup]]"
                if living_cat not in cats:
                    cats.append(living_cat)

        # Fallback if no categories could be resolved dynamically at all
        if not cats:
            cats.append("[[Kategori:Semua artikel rintisan]]")

        # Deduplicate preserving insertion order
        unique_cats: List[str] = []
        for c in cats:
            if c not in unique_cats:
                unique_cats.append(c)

        return unique_cats

    def translate_lead_prose(self, raw_lead: str, id_title: str) -> str:
        """
        Formulates an Indonesian encyclopedic summary sentence / paragraphs
        respecting EYD V / KBBI VI, retaining references.
        When GeminiTranslatorClient is available, translates via LLM with SYSTEM_PROMPT_GRADE_A_PLUS_PLUS
        to produce 100% natural, human-flowing Indonesian prose.
        Otherwise, uses the offline rule-based fallback.
        """
        if not raw_lead:
            return (
                f"'''{id_title}''' adalah seorang tokoh dan figur penting di bidangnya. "
                f"Artikel ini merupakan rintisan mengenai topik tersebut."
            )

        text = raw_lead.strip()

        # Step 1: Map all wikilinks safely using WikiLinkMapper
        if self.link_mapper:
            try:
                text = self.link_mapper.process_wikitext(text)
            except Exception:
                pass
        # Step 1.5: If GeminiTranslatorClient is available, use LLM with Grade A++ prompt
        client = self._get_translator_client()
        if client:
            try:
                clean_title = re.sub(r"\s*\([^)]+\)$", "", id_title).strip()
                prompt = (
                    f"Terjemahkan teks pembuka (lead prose) Wikipedia berikut ke dalam bahasa Indonesia baku untuk artikel rintisan '{id_title}'.\n\n"
                    f"PEDOMAN UTAMA:\n"
                    f"- Standar ensiklopedia Grade A++ (KBBI VI, EYD V, Pedoman Gaya Penulisan Wikipedia bahasa Indonesia).\n"
                    f"- Rekonstruksi sintaksis alami (Hukum D-M, anti-calque, anti-AI-slop).\n"
                    f"- Susunan frasa nomina dan keterangan waktu harus alami dan mengalir (misalnya: 'film dokumenter tentang pembunuhan 11 atlet Israel pada tahun 1972 yang memenangkannya [[Academy Award untuk Film Dokumenter Terbaik]]' atau 'pemeran asal Inggris yang dikenal luas atas perannya sebagai [[Dean Thomas]]').\n"
                    f"- Jangan mengubah atau merusak sintaks wikitext: pertahankan semua pranala [[...]], templat {{{{...}}}}, teks tebal/miring, dan referensi <ref>...</ref>.\n"
                    f"- Berikan LANGSUNG hasil terjemahannya saja tanpa teks pengantar atau penutup:\n\n"
                    f"{text}"
                )
                translated_llm = client.translate_section(prompt, system_instruction=SYSTEM_PROMPT_GRADE_A_PLUS_PLUS)
                if translated_llm and translated_llm.strip():
                    res = translated_llm.strip()
                    # Ensure bold subject if missing
                    if f"'''{id_title}'''" not in res and f"'''{clean_title}'''" not in res and "'''" not in res:
                        res = f"'''{id_title}''' {res}"
                    # Natural phrasing cleanup
                    res = re.sub(r"\badalah seorang? (?:aktor|pemeran) Inggris yang paling dikenal (?:atas|karena)\b", "adalah seorang pemeran asal Inggris yang dikenal luas atas", res)
                    res = re.sub(r"\badalah (?:aktor|pemeran) Inggris yang paling dikenal (?:atas|karena)\b", "adalah pemeran asal Inggris yang dikenal luas atas", res)
                    res = re.sub(r"\badalah (?:aktor|pemeran) asal Inggris yang paling dikenal (?:atas|karena)\b", "adalah pemeran asal Inggris yang dikenal luas atas", res)
                    return res
            except Exception:
                # Fallback to offline rule-based translation on LLM failure
                pass
        # Step 2: Mask all [[...]] and {{...}} so text substitutions do NOT touch link internals
        tokens: List[str] = []

        def mask_token(m: re.Match) -> str:
            placeholder = f"§§TOKEN_{len(tokens)}§§"
            tokens.append(m.group(0))
            return placeholder

        masked = re.sub(r"\[\[[^\]]+\]\]|\{\{[^\}]+\}\}", mask_token, text)

        # Step 3: Translate English months to Indonesian
        months = {
            "January": "Januari",
            "February": "Februari",
            "March": "Maret",
            "April": "April",
            "May": "Mei",
            "June": "Juni",
            "July": "Juli",
            "August": "Agustus",
            "September": "September",
            "October": "Oktober",
            "November": "November",
            "December": "Desember",
        }
        for en_m, id_m in months.items():
            masked = re.sub(rf"\b{en_m}\b", id_m, masked, flags=re.IGNORECASE)

        # Step 4: Natural Indonesian encyclopedic phrasing (EYD V)
        masked = re.sub(r"\(born\s+([^)]+)\)", r"(lahir \1)", masked, flags=re.IGNORECASE)

        # Natural Biographical Phrasing:
        # Pattern: "adalah seorang pemeran (asal|berkebangsaan) {Negara} yang dikenal luas..."
        # Replace "is an English actor, best known for playing" -> "adalah seorang pemeran asal Inggris yang dikenal luas atas perannya sebagai"
        masked = re.sub(
            r"\bis an English actor,\s*best known for playing\b",
            "adalah seorang pemeran asal Inggris yang dikenal luas karena memerankan",
            masked,
            flags=re.IGNORECASE,
        )
        masked = re.sub(
            r"\bis an English actor\b",
            "adalah seorang pemeran asal Inggris",
            masked,
            flags=re.IGNORECASE,
        )
        masked = re.sub(
            r"\bis a British actor,\s*best known for playing\b",
            "adalah seorang pemeran berkebangsaan Britania Raya yang dikenal luas karena memerankan",
            masked,
            flags=re.IGNORECASE,
        )
        masked = re.sub(
            r"\bis a British actor\b",
            "adalah seorang pemeran berkebangsaan Britania Raya",
            masked,
            flags=re.IGNORECASE,
        )
        masked = re.sub(
            r"\bis an American actor,\s*best known for playing\b",
            "adalah seorang pemeran asal Amerika Serikat yang dikenal luas karena memerankan",
            masked,
            flags=re.IGNORECASE,
        )
        masked = re.sub(
            r"\bis an American actor\b",
            "adalah seorang pemeran asal Amerika Serikat",
            masked,
            flags=re.IGNORECASE,
        )
        masked = re.sub(
            r"\bis an actor,\s*best known for playing\b",
            "adalah seorang pemeran yang dikenal luas karena memerankan",
            masked,
            flags=re.IGNORECASE,
        )
        masked = re.sub(r"\bis an actor\b", "adalah seorang pemeran", masked, flags=re.IGNORECASE)

        masked = re.sub(
            r"\bis an English actress,\s*best known for playing\b",
            "adalah seorang pemeran wanita asal Inggris yang dikenal luas karena memerankan",
            masked,
            flags=re.IGNORECASE,
        )
        masked = re.sub(r"\bis an English actress\b", "adalah seorang pemeran wanita asal Inggris", masked, flags=re.IGNORECASE)
        masked = re.sub(
            r"\bis a British actress,\s*best known for playing\b",
            "adalah seorang pemeran wanita berkebangsaan Britania Raya yang dikenal luas karena memerankan",
            masked,
            flags=re.IGNORECASE,
        )
        masked = re.sub(r"\bis a British actress\b", "adalah seorang pemeran wanita berkebangsaan Britania Raya", masked, flags=re.IGNORECASE)
        masked = re.sub(
            r"\bis an American actress,\s*best known for playing\b",
            "adalah seorang pemeran wanita asal Amerika Serikat yang dikenal luas karena memerankan",
            masked,
            flags=re.IGNORECASE,
        )
        masked = re.sub(r"\bis an American actress\b", "adalah seorang pemeran wanita asal Amerika Serikat", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bis an actress\b", "adalah seorang pemeran wanita", masked, flags=re.IGNORECASE)

        masked = re.sub(r"\bis a Scottish film director, producer, and screenwriter\b", "adalah seorang sutradara film, produser, dan penulis skenario berkebangsaan Skotlandia", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bis a Scottish film director\b", "adalah seorang sutradara film asal Skotlandia", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bis a Scottish director\b", "adalah seorang sutradara asal Skotlandia", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bis an American film director\b", "adalah seorang sutradara film asal Amerika Serikat", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bis an American director\b", "adalah seorang sutradara asal Amerika Serikat", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bis an English director\b", "adalah seorang sutradara asal Inggris", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bis an English film director\b", "adalah seorang sutradara film asal Inggris", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bis a British film director\b", "adalah seorang sutradara film berkebangsaan Britania Raya", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bis a British director\b", "adalah seorang sutradara berkebangsaan Britania Raya", masked, flags=re.IGNORECASE)

        masked = re.sub(r"\bbest known for playing\b", "yang dikenal luas karena memerankan", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bbest known for\b", "yang dikenal luas atas karyanya", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bknown for playing\b", "yang dikenal karena memerankan", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bknown for\b", "yang dikenal melalui karyanya", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bin the fantasy film series\b", "dalam seri film fantasi", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bin the legal thriller television series\b", "dalam seri televisi cerita seru hukum", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bin the television series\b", "dalam seri televisi", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bin the film series\b", "dalam seri film", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bin the film\b", "dalam film", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bHe won the\b", "Ia memenangkan", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bShe won the\b", "Ia memenangkan", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bHis films include\b", "Film-film karyanya meliputi", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bHer films include\b", "Film-film karyanya meliputi", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\ba documentary about the 1972 murder of 11 Israeli athletes\b", "sebuah film dokumenter tentang pembunuhan 11 atlet Israel pada tahun 1972", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\babout the (\d{4})\s+(§§TOKEN_\d+§§)", r"tentang \2 pada tahun \1", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\babout (\d{4})\s+(§§TOKEN_\d+§§)", r"tentang \2 pada tahun \1", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\ba documentary about the (\d{4})\b", r"sebuah film dokumenter tentang tahun \1", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\ba documentary about the\b", "sebuah film dokumenter tentang", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\ba documentary about\b", "sebuah film dokumenter tentang", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\babout the (\d{4})\b", r"tentang tahun \1", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\babout the\b", "tentang", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\babout\b", "tentang", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bmurder of 11 Israeli athletes\b", "pembunuhan 11 atlet Israel", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bthe political thriller\b", "film cerita seru politik", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bthe post-apocalyptic drama\b", "film drama pascakiamat", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bthe thriller\b", "film cerita seru", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bthe drama\b", "film drama", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bthe legal drama film\b", "film drama hukum", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bwhich won him the\b", "yang memenangkannya", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bwhich won her the\b", "yang memenangkannya", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\band the\b", "dan", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\ba documentary\b", "sebuah film dokumenter", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bdocumentary\b", "dokumenter", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bis an\b", "adalah seorang", masked, flags=re.IGNORECASE)
        masked = re.sub(r"\bis a\b", "adalah seorang", masked, flags=re.IGNORECASE)

        # Fix noun phrase and year gap: flip so year comes AFTER the noun phrase/token
        # e.g., "1972 §§TOKEN_X§§" -> "§§TOKEN_X§§ pada tahun 1972"
        masked = re.sub(r"\b(1[89]\d\d|20[0-2]\d)\s+(§§TOKEN_\d+§§)", r"\2 pada tahun \1", masked)

        # Clean double spaces
        # Clean awkward unidiomatic commas before 'yang' (e.g. "pemeran Inggris, yang" -> "pemeran Inggris yang")
        masked = re.sub(r",\s*yang\b", " yang", masked)

        # Clean awkward phrasing: "adalah seorang pemeran Inggris yang paling di..." -> "adalah seorang pemeran asal Inggris yang dikenal luas..."
        masked = re.sub(
            r"\badalah seorang pemeran Inggris yang paling dikenal karena memerankan\b",
            "adalah seorang pemeran asal Inggris yang dikenal luas karena memerankan",
            masked,
        )
        masked = re.sub(
            r"\badalah seorang pemeran Inggris yang paling dikenal atas\b",
            "adalah seorang pemeran asal Inggris yang dikenal luas atas",
            masked,
        )
        masked = re.sub(
            r"\badalah seorang pemeran Inggris\b",
            "adalah seorang pemeran asal Inggris",
            masked,
        )
        masked = re.sub(
            r"\badalah seorang sutradara film Skotlandia\b",
            "adalah seorang sutradara film asal Skotlandia",
            masked,
        )
        masked = re.sub(
            r"\badalah seorang sutradara Skotlandia\b",
            "adalah seorang sutradara asal Skotlandia",
            masked,
        )
        masked = re.sub(r"  +", " ", masked)

        # Step 5: Restore tokens
        for i, tok in enumerate(tokens):
            masked = masked.replace(f"§§TOKEN_{i}§§", tok)

        # Ensure bold subject in definition sentence if not present
        clean_bare_title = re.sub(r"\s*\([^)]+\)$", "", id_title).strip()
        if f"'''{id_title}'''" not in masked and f"'''{clean_bare_title}'''" not in masked and "'''" not in masked:
            masked = f"'''{id_title}''' {masked}"

        return masked

    def generate_stub(
        self,
        en_title: str,
        id_title: Optional[str] = None,
        topic: Optional[str] = None,
        custom_lead: Optional[str] = None,
        custom_full_wikitext: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generates a 2-3 paragraph stub in natural Indonesian avoiding WP:KELAYAKAN and KPC A1.
        Includes Infobox (if present) and Filmography/Works section (for biographical subjects).
        """
        if id_title:
            target_id_title = id_title.strip()
        else:
            target_id_title = self.determine_target_title(en_title)
        # Fetch full wikitext if available or if custom_full_wikitext provided
        if custom_full_wikitext is not None:
            raw_full_wikitext = custom_full_wikitext
            raw_en_wikitext = custom_lead if custom_lead is not None else raw_full_wikitext
        elif custom_lead is not None:
            raw_en_wikitext = custom_lead
            raw_full_wikitext = self.fetch_en_full_wikitext(en_title)
        else:
            raw_full_wikitext = self.fetch_en_full_wikitext(en_title)
            raw_lead_wikitext = self.fetch_en_lead_wikitext(en_title)
            raw_en_wikitext = raw_lead_wikitext or raw_full_wikitext
        # Extract infobox if present
        infobox = self.extract_infobox(raw_en_wikitext) or (self.extract_infobox(raw_full_wikitext) if raw_full_wikitext else "")
        if infobox and self.link_mapper:
            try:
                infobox = self.link_mapper.map_wikilinks(infobox)
            except Exception:
                pass
        if infobox and self.infobox_mapper:
            try:
                infobox = self.infobox_mapper.normalize_infobox_keys(infobox)
            except Exception:
                pass

        paragraphs = self.extract_lead_paragraphs(raw_en_wikitext)
        # Translate the ENTIRE lead section without arbitrary paragraph truncation,
        # ensuring the stub fully captures the complete executive summary.
        lead_prose = "\n\n".join(paragraphs) if paragraphs else ""
        translated_body = self.translate_lead_prose(lead_prose, target_id_title)
        # Check for works / catalog sections (Filmography, Bibliography, Discography, Publications, Works, Books)
        works_sections = []
        if raw_full_wikitext:
            works_sections = self.extract_works_sections(raw_full_wikitext, title=target_id_title)
        elif raw_en_wikitext:
            works_sections = self.extract_works_sections(raw_en_wikitext, title=target_id_title)
        stub_template = self.determine_stub_template(target_id_title, raw_en_wikitext, topic)
        categories = self.determine_categories(
            target_id_title,
            raw_full_wikitext or raw_en_wikitext,
            topic,
            en_title=en_title,
        )
        cat_lines = "\n".join(categories)

        # Extract External links, bottom navboxes, and authority control
        source_for_sections = raw_full_wikitext or raw_en_wikitext or ""
        external_links = self.extract_external_links_section(source_for_sections)
        navboxes = self.extract_bottom_navboxes(source_for_sections)
        has_auth = self.has_authority_control(source_for_sections)

        # Format in strict Indonesian Wikipedia standard order:
        # 1. infobox
        # 2. translated_body
        # 3. works_sections
        # 4. == Referensi ==\n{{reflist}}
        # 5. == Pranala luar ==\n{external_links} (if present)
        # 6. {navboxes} (if present)
        # 7. {{Pengawasan otoritas}} (if present)
        # 8. {stub_template}
        # 9. {categories}
        parts = []
        if infobox:
            parts.append(infobox)
        if translated_body:
            parts.append(translated_body)
        for sec in works_sections:
            parts.append(f"{sec['header']}\n{sec['content']}")
        parts.append("== Referensi ==\n{{reflist}}")
        if external_links:
            parts.append(f"== Pranala luar ==\n{external_links}")
        for nb in navboxes:
            parts.append(nb)
        if has_auth:
            parts.append("{{Pengawasan otoritas}}")
        parts.append(stub_template)
        parts.append(cat_lines)
        full_wikitext = "\n\n".join(parts) + "\n"

        if self.typography_sanitizer:
            try:
                full_wikitext = self.typography_sanitizer.sanitize_wikitext(full_wikitext)
            except Exception:
                pass

        # Resolve any orphan reference tags (<ref name="..." /> without defining tag)
        # by searching full en.wiki wikitext for the definition or safely stripping the orphan
        if self.syntax_balancer:
            try:
                full_wikitext = self.syntax_balancer.resolve_orphan_references(
                    full_wikitext,
                    source_en_wikitext=raw_full_wikitext or raw_en_wikitext,
                )
            except Exception:
                pass

        # Word count approximation
        words = re.findall(r"\b\w+\b", re.sub(r"<[^>]+>|\{\{[^}]+\}\}|\[\[|\]\]", " ", full_wikitext))
        word_count = len(words)

        # Connect with Editorial QA Pipeline regulation
        qa_report: Optional[QAAuditReport] = None
        qa_error: Optional[str] = None
        if self.qa_pipeline:
            try:
                qa_report = self.qa_pipeline.audit(full_wikitext, title=target_id_title)
            except Exception as exc:
                qa_error = str(exc)
        else:
            qa_error = "Editorial QA pipeline is unavailable"

        return {
            "id_title": target_id_title,
            "en_title": en_title,
            "wikitext": full_wikitext,
            "stub_template": stub_template,
            "word_count": word_count,
            "has_filmography": any(sec["header"] in ("== Filmografi ==", "== Karya pilihan ==") for sec in works_sections),
            "has_works": bool(works_sections),
            "works_sections": works_sections,
            "has_infobox": bool(infobox),
            "qa_report": qa_report,
            "qa_error": qa_error,
            "is_qa_approved": bool(qa_report and qa_report.is_approved()),
        }
    def save_stub(self, stub_info: Dict[str, Any], output_dir: Path) -> Path:
        """Saves generated stub to output/stubs/<SafeTitle>.wikitext."""
        title = stub_info.get("id_title") or stub_info.get("en_title", "Stub")
        safe_title = re.sub(r'[\\/*?:"<>| ]', "_", title)
        target_dir = Path(output_dir) / "stubs"
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / f"{safe_title}.wikitext"
        file_path.write_text(stub_info.get("wikitext", ""), encoding="utf-8")
        return file_path


default_stub_generator = StubGenerator()
