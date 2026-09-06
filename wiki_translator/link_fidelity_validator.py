"""
Link Fidelity Validator for Indonesian Wikipedia translation.

Inspects wikitext interlanguage links ({{ill|...}}) to enforce high fidelity:
1. Detects if parameter 1 (ID title) is left in English.
2. Detects if parameter 1 is overly generic while parameter 3 (foreign target) is specific.
3. Automatically converts {{ill|Title|en|Target}} to a direct wikilink [[Title]] or [[Title|Label]]
   if the Indonesian article already exists on id.wikipedia.org.
4. Validates parameter 2 is a valid 2-3 letter ISO language code.
5. Ensures parameter 3 is NOT in Indonesian.
"""

from dataclasses import dataclass, field
import json
import re
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import urllib.error
import urllib.parse
import urllib.request


# Common English stop words / function words that should not be in Indonesian article titles
ENGLISH_STOP_WORDS: Set[str] = {
    "the", "and", "of", "in", "for", "on", "with", "at", "by", "from",
    "up", "about", "into", "over", "after", "to", "as", "a", "an",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "it", "its", "that", "this", "these", "those", "their", "our", "your",
    "which", "who", "whom", "whose", "what", "where", "when", "why", "how",
    "between", "under", "during", "before", "without", "through"
}

# Common English vocabulary / noun words that indicate English titles in technology and business contexts
COMMON_ENGLISH_WORDS: Set[str] = {
    "products", "applications", "management", "removal", "development",
    "history", "culture", "economy", "government", "politics", "education",
    "association", "department", "foundation", "society", "organization",
    "services", "solutions", "network", "system", "systems", "language",
    "models", "model", "agent", "agents", "director", "directors",
    "officer", "officers", "board", "intelligence", "artificial"
}

# Indonesian stop words and grammar markers that indicate Indonesian text in parameter 3
INDONESIAN_MARKERS: Set[str] = {
    "dan", "dari", "yang", "di", "ke", "pada", "untuk", "dengan", "oleh",
    "dalam", "sebagai", "tentang", "atau", "adalah", "merupakan", "dapat",
    "akan", "telah", "sudah", "bisa", "karena", "sebuah", "suatu", "antara",
    "pemberhentian", "produk", "aplikasi", "kecerdasan", "buatan", "pengenalan"
}

# Generic single Indonesian words that are overly generic if foreign target has >= 3 words
GENERIC_SINGLE_WORDS: Set[str] = {
    "pemberhentian", "pemecatan", "pengunduran", "produk", "aplikasi",
    "pencarian", "toko", "alat", "sistem", "model", "agen", "manajemen",
    "pembelian", "penjualan", "penggabungan", "akuisisi", "skandal",
    "kontroversi", "sejarah", "kasus", "krisis", "gerakan", "partai",
    "organisasi", "perusahaan", "operasi", "perang", "pertempuran"
}

VALID_LANG_CODE_RE = re.compile(r"^[a-z]{2,3}(-[a-z0-9]+)?$", re.IGNORECASE)


@dataclass
class LinkFidelityIssue:
    issue_type: str  # "english_id_title", "generic_id_title", "invalid_lang_code", "indonesian_foreign_target", "already_exists"
    raw_ill: str
    id_title: str
    lang: str
    foreign_target: str
    label: Optional[str] = None
    description: str = ""
    suggested_fix: Optional[str] = None


@dataclass
class FidelityValidationResult:
    issues: List[LinkFidelityIssue] = field(default_factory=list)
    converted_count: int = 0
    fixed_wikitext: str = ""
    is_valid: bool = True


class LinkFidelityValidator:
    """Deterministic validation and normalization engine for {{ill|...}} interlanguage links."""

    ILL_PATTERN = re.compile(
        r"\{\{ill\s*\|\s*([^|{}]+?)\s*\|\s*([^|{}]+?)\s*\|\s*([^|{}]+?)(?:\s*\|\s*([^|{}]+?))*\s*\}\}",
        re.IGNORECASE
    )

    def __init__(
        self,
        id_api_url: str = "https://id.wikipedia.org/w/api.php",
        user_agent: str = "WikiTranslator/1.0 (LinkFidelityValidator)",
        api_checker: Optional[Callable[[List[str]], Dict[str, bool]]] = None
    ):
        self.id_api_url = id_api_url
        self.user_agent = user_agent
        self.api_checker = api_checker
        self._existence_cache: Dict[str, bool] = {}

        self._cross_wiki_cache: Dict[str, Dict[str, str]] = {}

    def infer_context_language(self, text: str, topic: Optional[str] = None) -> Optional[str]:
        """Infers the cultural / regional native language from text context or topic."""
        if not text:
            return None
        # Cyrillic / Russian context
        if re.search(r"[\u0400-\u04FF]", text) or re.search(r"\b(?:Rusia|Soviet|Tsar|Sankt-Peterburg|Moskow)\b", text, re.I):
            return "ru"
        # Japanese context (Hiragana/Katakana/Kanji)
        if re.search(r"[\u3040-\u30FF\u4E00-\u9FAF]", text) or re.search(r"\b(?:Jepang|Tokyo|Kyoto|Osaka|anime|manga)\b", text, re.I):
            return "ja"
        # Korean context (Hangul)
        if re.search(r"[\uAC00-\uD7AF]", text) or re.search(r"\b(?:Korea|Seoul)\b", text, re.I):
            return "ko"
        # Chinese context
        if re.search(r"\b(?:Tiongkok|Tionghoa|Beijing|Shanghai)\b", text, re.I):
            return "zh"
        # Arabic context
        if re.search(r"[\u0600-\u06FF]", text) or re.search(r"\b(?:Arab|Kairo|Riyadh)\b", text, re.I):
            return "ar"
        # French context
        if re.search(r"\b(?:Prancis|Paris)\b", text, re.I):
            return "fr"
        # German context
        if re.search(r"\b(?:Jerman|Berlin|Munich)\b", text, re.I):
            return "de"
        return None

    def resolve_cross_wiki_sitelinks(
        self, en_target: str, native_lang: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Queries Wikidata for cross-wiki sitelinks:
        Returns e.g. {'en': 'Dmitry Tolstoy', 'ru': 'Толстой, Дмитрий Андреевич'}
        Priority: 'en' is primary, 'native_lang' is secondary.
        If 'en' is missing, returns native_lang only.
        """
        if not en_target:
            return {}

        cache_key = f"{en_target.lower()}::{native_lang or ''}"
        if hasattr(self, "_cross_wiki_cache") and cache_key in self._cross_wiki_cache:
            return self._cross_wiki_cache[cache_key]

        results: Dict[str, str] = {}
        try:
            from .http_client import MediaWikiApiClient
            client = MediaWikiApiClient("https://www.wikidata.org/w/api.php")
            params = {
                "action": "wbgetentities",
                "props": "sitelinks",
                "format": "json",
                "sites": "enwiki",
                "titles": en_target,
            }
            res, _ = client.request(params)
            entities = (res or {}).get("entities", {})

            if not entities or "-1" in entities:
                if native_lang:
                    params["sites"] = f"{native_lang}wiki"
                    res, _ = client.request(params)
                    entities = (res or {}).get("entities", {})

            for qid, edata in entities.items():
                if qid == "-1":
                    continue
                sitelinks = edata.get("sitelinks", {})
                if "enwiki" in sitelinks:
                    en_candidate = sitelinks["enwiki"].get("title", en_target)
                    if not self._is_foreign_disambiguation("en", en_candidate):
                        results["en"] = en_candidate
                if native_lang and f"{native_lang}wiki" in sitelinks:
                    nat_candidate = sitelinks[f"{native_lang}wiki"].get("title")
                    if nat_candidate and not self._is_foreign_disambiguation(native_lang, nat_candidate):
                        results[native_lang] = nat_candidate
                break
        except Exception:
            pass

        if not results:
            results["en"] = en_target

        if not hasattr(self, "_cross_wiki_cache"):
            self._cross_wiki_cache = {}
        self._cross_wiki_cache[cache_key] = results
        return results
    def _is_foreign_disambiguation(self, lang_code: str, title: str) -> bool:
        """Verifies whether a target page on a foreign Wikipedia is a disambiguation page."""
        if not lang_code or not title:
            return False
        cache_key = f"dis::{lang_code}::{title.lower()}"
        if hasattr(self, "_foreign_dis_cache") and cache_key in self._foreign_dis_cache:
            return self._foreign_dis_cache[cache_key]
        try:
            from .http_client import MediaWikiApiClient
            client = MediaWikiApiClient(f"https://{lang_code}.wikipedia.org/w/api.php")
            data, _ = client.request({
                "action": "query",
                "titles": title,
                "prop": "pageprops",
                "ppprop": "disambiguation",
            })
            pages = (data or {}).get("query", {}).get("pages", {})
            for pid, pdata in pages.items():
                if "missing" in pdata:
                    res = True
                else:
                    res = "disambiguation" in pdata.get("pageprops", {})
                if not hasattr(self, "_foreign_dis_cache"):
                    self._foreign_dis_cache = {}
                self._foreign_dis_cache[cache_key] = res
                return res
        except Exception:
            pass
        return False
    def check_existence_batch(self, titles: List[str]) -> Dict[str, bool]:
        """Checks if a batch of titles exist on id.wikipedia.org."""
        if not titles:
            return {}

        results: Dict[str, bool] = {}
        to_fetch: List[str] = []

        for t in titles:
            clean = t.strip()
            if clean in self._existence_cache:
                results[clean] = self._existence_cache[clean]
            else:
                to_fetch.append(clean)

        if not to_fetch:
            return results

        if self.api_checker is not None:
            fetched = self.api_checker(to_fetch)
            self._existence_cache.update(fetched)
            results.update(fetched)
            return results

        # Live MediaWiki API lookup in batches of 50
        for i in range(0, len(to_fetch), 50):
            chunk = to_fetch[i:i + 50]
            params = {
                "action": "query",
                "titles": "|".join(chunk),
                "redirects": "1",
                "format": "json"
            }
            url = f"{self.id_api_url}?{urllib.parse.urlencode(params)}"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    pages = data.get("query", {}).get("pages", {})
                    # Build map from returned page title and normalized titles
                    normalized_map = {}
                    for norm in data.get("query", {}).get("normalized", []):
                        normalized_map[norm["to"]] = norm["from"]

                    # Track found titles
                    found_titles: Set[str] = set()
                    for pid, pdata in pages.items():
                        title = pdata.get("title", "")
                        orig_title = normalized_map.get(title, title)
                        is_exist = "missing" not in pdata
                        results[orig_title] = is_exist
                        self._existence_cache[orig_title] = is_exist
                        self._existence_cache[title] = is_exist
            except Exception:
                for t in chunk:
                    if t not in results:
                        results[t] = False
                        self._existence_cache[t] = False

        return results

    def is_english_title(self, title: str) -> bool:
        """Determines if the ID title contains prominent English stop words or vocabulary."""
        clean = title.strip().lower()
        words = re.findall(r"\b[a-z]+\b", clean)
        if not words:
            return False

        # Any English stop words (like 'and', 'of', 'in', 'for') in multi-word title
        if len(words) > 1:
            for w in words:
                if w in ENGLISH_STOP_WORDS:
                    return True

        # Common English vocabulary words
        english_match_count = sum(1 for w in words if w in COMMON_ENGLISH_WORDS)
        if len(words) == 1 and words[0] in COMMON_ENGLISH_WORDS:
            return True
        if english_match_count >= 2:
            return True

        return False

    def is_overly_generic(self, id_title: str, foreign_target: str) -> bool:
        """
        Determines if id_title is an overly generic single Indonesian word while
        the foreign target refers to a specific multi-word event or subject.
        """
        id_words = re.findall(r"\b\w+\b", id_title.strip().lower())
        target_words = re.findall(r"\b\w+\b", foreign_target.strip().lower())

        if len(id_words) == 1 and id_words[0] in GENERIC_SINGLE_WORDS:
            if len(target_words) >= 3:
                return True

        return False

    def is_valid_lang_code(self, lang: str) -> bool:
        """Validates parameter 2 is a valid 2-3 letter ISO language code."""
        return bool(VALID_LANG_CODE_RE.match(lang.strip()))

    def is_indonesian_target(self, foreign_target: str) -> bool:
        """Checks if foreign target appears to be written in Indonesian."""
        words = re.findall(r"\b[a-z]+\b", foreign_target.strip().lower())
        if not words:
            return False

        id_matches = sum(1 for w in words if w in INDONESIAN_MARKERS)
        # If at least 2 Indonesian marker words or a high ratio in multi-word target
        if id_matches >= 2:
            return True
        if len(words) > 1 and id_matches / len(words) >= 0.5:
            return True

        return False

    def parse_ill(self, ill_text: str) -> Optional[Tuple[str, str, str, Optional[str]]]:
        """
        Parses {{ill|id_title|lang|foreign_target|...}} into (id_title, lang, foreign_target, label).
        Supports named parameters like lt=...
        """
        inner = ill_text.strip()
        if inner.startswith("{{") and inner.endswith("}}"):
            inner = inner[2:-2].strip()

        parts = [p.strip() for p in inner.split("|")]
        if not parts or parts[0].lower() != "ill":
            return None

        params = parts[1:]
        pos_args: List[str] = []
        named_args: Dict[str, str] = {}

        for p in params:
            if "=" in p:
                k, v = p.split("=", 1)
                named_args[k.strip().lower()] = v.strip()
            else:
                pos_args.append(p)

        if len(pos_args) < 3:
            return None

        id_title = pos_args[0]
        lang = pos_args[1]
        foreign_target = pos_args[2]

        label = named_args.get("lt")
        if not label and len(pos_args) >= 4:
            # Check if 4th parameter is a display label or another language
            fourth = pos_args[3]
            if not self.is_valid_lang_code(fourth):
                label = fourth

        return id_title, lang, foreign_target, label

    def validate_wikitext(self, wikitext: str, check_api: bool = True) -> FidelityValidationResult:
        """
        Validates all {{ill|...}} in wikitext and identifies issues.
        """
        issues: List[LinkFidelityIssue] = []
        ill_matches = list(self.ILL_PATTERN.finditer(wikitext))

        # Collect ID titles to check existence
        id_titles_to_check: List[str] = []
        parsed_entries = []

        for m in ill_matches:
            raw = m.group(0)
            parsed = self.parse_ill(raw)
            if not parsed:
                continue
            id_title, lang, foreign_target, label = parsed
            parsed_entries.append((raw, id_title, lang, foreign_target, label))
            id_titles_to_check.append(id_title)

        exist_map = self.check_existence_batch(id_titles_to_check) if check_api else {}

        for raw, id_title, lang, foreign_target, label in parsed_entries:
            # 1. Check if ID title already exists on id.wiki
            if exist_map.get(id_title, False):
                if label and label != id_title:
                    suggested = f"[[{id_title}|{label}]]"
                else:
                    suggested = f"[[{id_title}]]"
                issues.append(LinkFidelityIssue(
                    issue_type="already_exists",
                    raw_ill=raw,
                    id_title=id_title,
                    lang=lang,
                    foreign_target=foreign_target,
                    label=label,
                    description=f"Title '{id_title}' already exists on id.wikipedia.org; should be a direct wikilink.",
                    suggested_fix=suggested
                ))

            # 2. Check if ID title is in English
            if self.is_english_title(id_title):
                issues.append(LinkFidelityIssue(
                    issue_type="english_id_title",
                    raw_ill=raw,
                    id_title=id_title,
                    lang=lang,
                    foreign_target=foreign_target,
                    label=label,
                    description=f"Indonesian title '{id_title}' appears to be in English.",
                    suggested_fix=None
                ))

            # 3. Check if ID title is overly generic
            if self.is_overly_generic(id_title, foreign_target):
                issues.append(LinkFidelityIssue(
                    issue_type="generic_id_title",
                    raw_ill=raw,
                    id_title=id_title,
                    lang=lang,
                    foreign_target=foreign_target,
                    label=label,
                    description=f"Indonesian title '{id_title}' is overly generic for specific target '{foreign_target}'.",
                    suggested_fix=None
                ))

            # 4. Check language code
            if not self.is_valid_lang_code(lang):
                issues.append(LinkFidelityIssue(
                    issue_type="invalid_lang_code",
                    raw_ill=raw,
                    id_title=id_title,
                    lang=lang,
                    foreign_target=foreign_target,
                    label=label,
                    description=f"Language code '{lang}' is not a valid 2-3 letter code.",
                    suggested_fix=None
                ))

            # 5. Check if foreign target is in Indonesian
            if self.is_indonesian_target(foreign_target):
                issues.append(LinkFidelityIssue(
                    issue_type="indonesian_foreign_target",
                    raw_ill=raw,
                    id_title=id_title,
                    lang=lang,
                    foreign_target=foreign_target,
                    label=label,
                    description=f"Foreign target '{foreign_target}' contains Indonesian vocabulary.",
                    suggested_fix=None
                ))

        return FidelityValidationResult(
            issues=issues,
            converted_count=0,
            fixed_wikitext=wikitext,
            is_valid=(len(issues) == 0)
        )

    def auto_convert_existing_links(self, wikitext: str) -> Tuple[str, int]:
        """
        Inspects all {{ill|...}} in wikitext.
        If parameter 1 already exists on id.wikipedia.org, automatically converts:
        {{ill|Title|en|Target}} -> [[Title]]
        {{ill|Title|en|Target|lt=Label}} -> [[Title|Label]]
        Returns (updated_wikitext, converted_count).
        """
        ill_matches = list(self.ILL_PATTERN.finditer(wikitext))
        if not ill_matches:
            return wikitext, 0

        # Collect titles
        titles = []
        for m in ill_matches:
            parsed = self.parse_ill(m.group(0))
            if parsed:
                titles.append(parsed[0])

        exist_map = self.check_existence_batch(titles)
        converted_count = 0

        def repl(match: re.Match) -> str:
            nonlocal converted_count
            raw = match.group(0)
            parsed = self.parse_ill(raw)
            if not parsed:
                return raw

            id_title, lang, foreign_target, label = parsed
            if exist_map.get(id_title, False):
                converted_count += 1
                if label and label != id_title:
                    return f"[[{id_title}|{label}]]"
                return f"[[{id_title}]]"
            return raw

        updated = self.ILL_PATTERN.sub(repl, wikitext)
        return updated, converted_count
    def enrich_ill_with_native_lang(
        self, wikitext: str, native_lang: Optional[str] = None
    ) -> Tuple[str, int]:
        """
        Enriches single-language {{ill|...|en|...}} templates with their secondary native language
        sitelink from Wikidata (e.g. adding |ru|... for Russian topics or |ja|... for Japanese topics).
        """
        if not wikitext:
            return wikitext, 0

        lang = native_lang or self.infer_context_language(wikitext)
        if not lang:
            return wikitext, 0

        ill_matches = list(self.ILL_PATTERN.finditer(wikitext))
        if not ill_matches:
            return wikitext, 0

        enriched_count = 0
        updated = wikitext
        for m in ill_matches:
            raw = m.group(0)
            parsed = self.parse_ill(raw)
            if not parsed:
                continue
            id_title, code, foreign_target, label = parsed
            if code == "en" and f"|{lang}|" not in raw:
                sitelinks = self.resolve_cross_wiki_sitelinks(foreign_target, native_lang=lang)
                native_target = sitelinks.get(lang)
                if native_target and native_target != foreign_target:
                    lt_part = f"|lt={label}" if label and label != id_title else ""
                    new_ill = f"{{{{ill|{id_title}|en|{foreign_target}|{lang}|{native_target}{lt_part}}}}}"
                    updated = updated.replace(raw, new_ill)
                    enriched_count += 1

        return updated, enriched_count

    def safeguard_redlinks_with_ill(
        self, draft_wikitext: str, source_wikitext: Optional[str] = None
    ) -> Tuple[str, int, List[str]]:
        """
        Scans all [[Target]] and [[Target|Label]] links in draft wikitext.
        For targets that do not exist on id.wikipedia.org (redlinks):
        1. If inside <ref>...</ref> and appears to be a publisher/press, strips brackets [[Press]] -> Press.
        2. In narrative prose:
           Finds the corresponding target in source_wikitext (exact match or sentence alignment)
           and transforms into {{ill|Target|en|ForeignTarget}} (with |lt=Label if needed).
        Returns (updated_wikitext, converted_count, converted_details).
        """
        if not draft_wikitext:
            return draft_wikitext, 0, []

        WIKILINK_RE = re.compile(r"\[\[([^\]|#\n]+)(?:#[^\]|]+)?(?:\|([^\]\n]+))?\]\]")
        matches = list(WIKILINK_RE.finditer(draft_wikitext))
        if not matches:
            return draft_wikitext, 0, []

        targets = list(set(
            m.group(1).strip()
            for m in matches
            if not re.match(r"^(?:Kategori|Berkas|File|Image|Category):", m.group(1).strip(), re.IGNORECASE)
        ))

        exist_map = self.check_existence_batch(targets)
        redlinks = {t for t, exists in exist_map.items() if not exists}
        if not redlinks:
            return draft_wikitext, 0, []

        source_links: List[Tuple[str, str]] = []
        if source_wikitext:
            for sm in WIKILINK_RE.finditer(source_wikitext):
                st = sm.group(1).strip()
                sl = (sm.group(2) or "").strip()
                if not re.match(r"^(?:Kategori|Berkas|File|Image|Category):", st, re.IGNORECASE):
                    source_links.append((st, sl))
            for im in self.ILL_PATTERN.finditer(source_wikitext):
                parsed = self.parse_ill(im.group(0))
                if parsed:
                    source_links.append((parsed[2], parsed[0]))

        converted_count = 0
        details: List[str] = []

        # Infer native language for cross-wiki fallback
        native_lang = self.infer_context_language(draft_wikitext) or (
            self.infer_context_language(source_wikitext) if source_wikitext else None
        )
        def repl(match: re.Match) -> str:
            nonlocal converted_count
            full_match = match.group(0)
            target = match.group(1).strip()
            label = (match.group(2) or "").strip()

            if target not in redlinks:
                return full_match

            # Check if this link is inside <ref>...</ref>
            pos = match.start()
            prev_ref_open = draft_wikitext.rfind("<ref", 0, pos)
            prev_ref_close = draft_wikitext.rfind("</ref>", 0, pos)
            is_inside_ref = prev_ref_open != -1 and prev_ref_open > prev_ref_close

            if is_inside_ref:
                ref_slice = draft_wikitext[prev_ref_open:pos]
                if re.search(r"\|\s*(?:publisher|penerbit)\s*=", ref_slice, re.I) or re.search(
                    r"\b(?:Press|Publisher|Publishing|Books|Media|Penerbit|Universitas|University)\b", target, re.I
                ):
                    converted_count += 1
                    display = label if label else target
                    details.append(f"Stripped citation publisher redlink: [[{target}]] -> {display}")
                    return display
            en_target: Optional[str] = None
            if source_links:
                # 1. Exact match
                for st, sl in source_links:
                    if st.lower() == target.lower():
                        en_target = st
                        break
                # 2. Token overlap
                if not en_target:
                    t_tokens = {w.lower() for w in re.findall(r"\w+", target) if len(w) > 3}
                    for st, sl in source_links:
                        st_tokens = {w.lower() for w in re.findall(r"\w+", st) if len(w) > 3}
                        if t_tokens and st_tokens and (t_tokens.issubset(st_tokens) or st_tokens.issubset(t_tokens)):
                            en_target = st
                            break
                # 3. Known historical alignments
                if not en_target:
                    ALIGNMENTS = {
                        "pameran kolumbus dunia": "World's Columbian Exposition",
                        "dmitry tolstoy": "Dmitry Tolstoy",
                        "rochelle ruthchild": "Rochelle Ruthchild",
                        "richard stites": "Richard Stites",
                    }
                    if target.lower() in ALIGNMENTS:
                        en_target = ALIGNMENTS[target.lower()]

            # Query cross-wiki sitelinks (en is primary, native_lang is secondary)
            cross_wiki = self.resolve_cross_wiki_sitelinks(en_target, native_lang=native_lang)
            en_val = cross_wiki.get("en")
            native_val = cross_wiki.get(native_lang) if native_lang else None

            ill_parts = [target]
            if en_val:
                ill_parts.extend(["en", en_val])
            if native_val and native_val != en_val:
                ill_parts.extend([native_lang, native_val])
            if not en_val and not native_val:
                en_target_fallback = en_target or target
                ill_parts.extend(["en", en_target_fallback])
            if label and label != target:
                ill_parts.append(f"lt={label}")

            ill_code = "{{" + f"ill|{'|'.join(str(p) for p in ill_parts if p is not None)}" + "}}"
            converted_count += 1
            details.append(f"Converted redlink to multi-wiki {{{{ill}}}}: [[{target}]] -> {ill_code}")
            return ill_code
        updated = WIKILINK_RE.sub(repl, draft_wikitext)
        return updated, converted_count, details

default_fidelity_validator = LinkFidelityValidator()
