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


default_fidelity_validator = LinkFidelityValidator()
