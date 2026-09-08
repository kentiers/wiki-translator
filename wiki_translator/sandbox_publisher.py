"""
Structured User Sandbox Publisher for Indonesian Wikipedia (id.wikipedia.org).

Publishes translated drafts and talk page attributions to user sandbox subpages
organized cleanly by project folder and date slug:
- Main Page: Pengguna:<Username>/Bak_pasir/<project_slug>/<YYYY-MM>/<Article_Title>
- Talk Page: Pembicaraan_Pengguna:<Username>/Bak_pasir/<project_slug>/<YYYY-MM>/<Article_Title>
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from .http_client import MediaWikiApiClient

DEFAULT_PROJECT_SLUG = "Draf"
DEFAULT_DASHBOARD_SUMMARY = "pemutakhiran indeks"
MONTH_NAMES_ID = {
    1: "Januari",
    2: "Februari",
    3: "Maret",
    4: "April",
    5: "Mei",
    6: "Juni",
    7: "Juli",
    8: "Agustus",
    9: "September",
    10: "Oktober",
    11: "November",
    12: "Desember",
}

FORBIDDEN_SUMMARY_TERMS: List[str] = [
    r"gemini(?:-[\d\.]+(?:-flash)?)?",
    r"model",
    r"flash",
    r"grade\s+a\+{1,2}",
    r"\bai\b",
    r"\bllm\b",
    r"\bbot\b",
]

FORBIDDEN_COMPILED_PATTERNS = [
    re.compile(pat, re.IGNORECASE) for pat in FORBIDDEN_SUMMARY_TERMS
]

HUMAN_SUMMARY_REPLACEMENTS: List[Tuple[re.Pattern, str]] = [
    # 1. Full expansion / adaptation from enwiki
    (
        re.compile(r"\b(?:adaptasi\s+penuh|terjemahan\s+penuh|naskah\s+lengkap|perluas|ekspansi)\b", re.IGNORECASE),
        "perluas artikel dari enwiki",
    ),
    # 2. Specific draft polish
    (
        re.compile(
            r"pemolesan\s+menyeluruh\s+tata\s+bahasa\s+dan\s+kelancaran\s+kalimat\s+ensiklopedia(?:\s*\([^)]*\))?",
            re.IGNORECASE,
        ),
        "rapikan draf",
    ),
    # 3. Translation & reference polishing
    (
        re.compile(r"\b(?:pemutakhiran\s+terjemahan|pemolesan\s+menyeluruh|perbaikan\s+tata\s+bahasa|perbaikan\s+menyeluruh)\b", re.IGNORECASE),
        "rapikan terjemahan & rujukan",
    ),
    # 4. Wikilinks & categories
    (
        re.compile(r"\b(?:standardisasi\s+pranala|resolusi\s+pranala|pengamanan\s+pranala|pemutakhiran\s+kategori|kategori\s+idwiki)\b", re.IGNORECASE),
        "rapikan format pranala & kategori",
    ),
    # 5. Draft creation
    (
        re.compile(r"\b(?:buat\s+draf\s+awal|pembuatan\s+rintisan|artikel\s+rintisan)\b", re.IGNORECASE),
        "buat artikel rintisan dari enwiki",
    ),
    # 6. Citation & reference fixes
    (
        re.compile(r"\b(?:perbaikan\s+kesalahan\s+pengutipan|perbaikan\s+rujukan)\b", re.IGNORECASE),
        "perbaikan rujukan",
    ),
    # 7. Evaluation notes
    (
        re.compile(r"\b(?:catatan\s+evaluasi\s+draf(?:\s+pemolesan)?|hasil\s+evaluasi)\b", re.IGNORECASE),
        "catatan evaluasi",
    ),
    # 8. Standardize terms
    (
        re.compile(r"\bstandardisasi\s+penggunaan\s+istilah\b", re.IGNORECASE),
        "penyesuaian istilah",
    ),
    # 9. Standardize link targets
    (
        re.compile(r"\bstandardisasi\s+target\s+pranala\b", re.IGNORECASE),
        "perbaikan pranala",
    ),
]

POMPOUS_WORDS: List[re.Pattern] = [
    re.compile(r"\bmenyeluruh\b", re.IGNORECASE),
    re.compile(r"\bstandardisasi\b", re.IGNORECASE),
    re.compile(r"\bensiklopedis?\b", re.IGNORECASE),
    re.compile(r"\bresolusi\b", re.IGNORECASE),
    re.compile(r"\banalisis\s+mendalam\b", re.IGNORECASE),
]


def sanitize_edit_summary(summary: Optional[str], default_fallback: str = "rapikan draf") -> str:
    """
    Cleans and humanizes Wikipedia edit summaries:
    1. Replaces verbose/robotic bot phrasing with concise, natural human editor summaries.
    2. Strips AI/model leak words: gemini, model, flash, grade a++, ai, llm, bot.
    3. Normalizes whitespace and punctuation.
    4. Truncates cleanly on word boundaries (never cutting mid-word or leaving unclosed parentheses).
    5. Falls back to natural human summary if empty or stripped.
    """
    if not summary:
        return default_fallback

    s = summary.strip()

    # Priority 0: Check redirect pattern
    m_redir = re.search(r"\b(?:mengalihkan\s+ke|alih\s+ke)\s*(\[\[[^\]]+\]\])", s, re.IGNORECASE)
    if m_redir:
        return f"mengalihkan ke {m_redir.group(1)}"

    # Priority 1: Check canonical human action replacements (full replacement, avoid robotic hybrids)
    for pattern, replacement in HUMAN_SUMMARY_REPLACEMENTS:
        if pattern.search(s):
            return replacement

    # Priority 2: Strip AI leak patterns
    for compiled in FORBIDDEN_COMPILED_PATTERNS:
        s = compiled.sub("", s)

    # Priority 3: Strip pompous/verbose words
    for compiled in POMPOUS_WORDS:
        s = compiled.sub("", s)

    # Priority 4: Clean whitespace and dangling colons/hyphens
    s = re.sub(r"\s*[:\-–—]\s*(?=[:\-–—]|\Z)", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^[\s\-–—:,()]+|[\s\-–—:,()]+$", "", s).strip()

    # Priority 5: Word-boundary truncation at ~100 chars (never mid-word)
    max_len = 100
    if len(s) > max_len:
        cut_idx = s.rfind(" ", 0, max_len)
        if cut_idx > 20:
            s = s[:cut_idx].strip()
        else:
            s = s[:max_len].strip()
        s = re.sub(r"^[\s\-–—:,()]+|[\s\-–—:,()]+$", "", s).strip()
    # Priority 6: Balance unclosed parentheses
    if s.count("(") > s.count(")"):
        s += ")"
    elif s.count("(") < s.count(")"):
        s = s.replace(")", "")

    if not s:
        return default_fallback

    return s

class SandboxPublisher:
    """Publishes drafts and attribution to structured user sandboxes on id.wikipedia.org."""

    API_URL = "https://id.wikipedia.org/w/api.php"
    BASE_WEB_URL = "https://id.wikipedia.org/wiki"
    DEFAULT_SUMMARY = "buat draf awal"
    DEFAULT_UPDATE_SUMMARY = "pemutakhiran draf"
    DEFAULT_TALK_SUMMARY = "atribusi terjemahan"
    USER_AGENT = "WikiTranslatorUserScript/1.0 (https://id.wikipedia.org/wiki/Pengguna:Baloo_Official; User sandbox draft helper)"
    def __init__(
        self,
        api_url: str = API_URL,
        user_agent: str = USER_AGENT,
        http_client: Optional[MediaWikiApiClient] = None,
    ):
        self.api_url = api_url
        self.user_agent = user_agent
        self.http_client = http_client or MediaWikiApiClient(
            api_url=self.api_url, user_agent=self.user_agent
        )

    @property
    def _cookie_jar(self) -> Dict[str, str]:
        return self.http_client._cookie_jar

    @_cookie_jar.setter
    def _cookie_jar(self, value: Dict[str, str]) -> None:
        self.http_client._cookie_jar = value

    def build_sandbox_titles(
        self,
        username: str,
        article_title: str,
        slug: Optional[str] = None,
        project_slug: Optional[str] = DEFAULT_PROJECT_SLUG,
    ) -> Tuple[str, str]:
        """
        Constructs the target sandbox article title and talk page title.
        Format:
          Main: Pengguna:<Username>/Bak_pasir/<project_slug>/<YYYY-MM>/<Article_Title>
          Talk: Pembicaraan_Pengguna:<Username>/Bak_pasir/<project_slug>/<YYYY-MM>/<Article_Title>
        If slug is provided, uses it directly.
        Otherwise, constructs hierarchical slug: <project_slug>/<YYYY-MM> (or just <YYYY-MM> if project_slug is empty/None).
        """
        base_user = username.strip().split("@")[0].strip()
        clean_user = base_user.replace(" ", "_")
        clean_title = article_title.strip().replace(" ", "_")

        if slug:
            clean_slug = slug.strip().strip("/")
            if "/" in clean_slug:
                final_slug = clean_slug
            else:
                if project_slug and project_slug.strip():
                    final_slug = f"{project_slug.strip().strip('/')}/{clean_slug}"
                else:
                    final_slug = clean_slug
        else:
            now = datetime.now()
            date_str = now.strftime("%Y-%m")
            if project_slug and project_slug.strip():
                final_slug = f"{project_slug.strip().strip('/')}/{date_str}"
            else:
                final_slug = date_str

        main_page = f"Pengguna:{clean_user}/Bak_pasir/{final_slug}/{clean_title}"
        talk_page = f"Pembicaraan_Pengguna:{clean_user}/Bak_pasir/{final_slug}/{clean_title}"
        return main_page, talk_page

    def build_monthly_index_title(
        self,
        username: str,
        slug: Optional[str] = None,
        project_slug: Optional[str] = DEFAULT_PROJECT_SLUG,
    ) -> str:
        """
        Constructs the target monthly index / dashboard page title.
        Format:
          Pengguna:<Username>/Bak_pasir/<project_slug>/<YYYY-MM>
          (e.g. Pengguna:Baloo_Official/Bak_pasir/Draf/2026-09)
        If slug is provided:
          - If slug already contains '/', uses it directly.
          - If slug is just YYYY-MM and project_slug is provided, joins them.
        """
        base_user = username.strip().split("@")[0].strip()
        clean_user = base_user.replace(" ", "_")

        if slug:
            clean_slug = slug.strip().strip("/")
            if "/" in clean_slug:
                final_slug = clean_slug
            else:
                if project_slug and project_slug.strip():
                    final_slug = f"{project_slug.strip().strip('/')}/{clean_slug}"
                else:
                    final_slug = clean_slug
        else:
            now = datetime.now()
            date_str = now.strftime("%Y-%m")
            if project_slug and project_slug.strip():
                final_slug = f"{project_slug.strip().strip('/')}/{date_str}"
            else:
                final_slug = date_str

        return f"Pengguna:{clean_user}/Bak_pasir/{final_slug}"

    def get_page_content(self, title: str) -> Optional[str]:
        """Fetches the latest wikitext content of a page, or None if it does not exist."""
        params = {
            "action": "query",
            "prop": "revisions",
            "rvprop": "content",
            "rvslots": "main",
            "titles": title.strip(),
        }
        payload, err = self._make_request(params, method="GET")
        if err or not payload:
            return None

        pages = payload.get("query", {}).get("pages", {})
        for page_id_str, page_info in pages.items():
            if int(page_id_str) < 0 or "missing" in page_info:
                return None
            revisions = page_info.get("revisions", [])
            if not revisions:
                return None
            rev = revisions[0]
            # slots format (MW 1.32+)
            if "slots" in rev and "main" in rev["slots"]:
                return rev["slots"]["main"].get("*", "")
            return rev.get("*", "")
        return None

    def parse_dashboard_rows(
        self, wikitext: str
    ) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
        """
        Parses existing dashboard table rows from wikitext for both:
        1. Translation drafts (Draf Terjemahan Baru)
        2. Review & polish drafts (Draf Peninjauan & Pemolesan Artikel)

        Returns (translation_rows, review_rows).
        If old single-table dashboard format is detected, returns (rows, []).
        """
        trans_rows: List[Dict[str, str]] = []
        review_rows: List[Dict[str, str]] = []

        if "{|" not in wikitext or "|}" not in wikitext:
            return trans_rows, review_rows

        # Find sections or multiple tables
        # Match section headers for translation and review/perbaikan
        m_trans = re.search(r"===\s*(?:1\.\s*)?(?:Draf\s+)?Terjemahan Baru\s*===(.*?)(?=(?:===\s*(?:2\.\s*)?(?:Draf\s+)?(?:Peninjauan|Perbaikan|Reviu)|===\s*Ringkasan|\Z))", wikitext, re.DOTALL | re.IGNORECASE)
        m_rev = re.search(r"===\s*(?:2\.\s*)?(?:Draf\s+)?(?:Peninjauan|Perbaikan|Reviu)[^\n]*===(.*?)(?=(?:===\s*Ringkasan|\Z))", wikitext, re.DOTALL | re.IGNORECASE)

        if m_trans or m_rev:
            trans_section = m_trans.group(1) if m_trans else ""
            review_section = m_rev.group(1) if m_rev else ""
            if trans_section:
                trans_rows = self._parse_single_table(trans_section, table_type="translation")
            if review_section:
                review_rows = self._parse_single_table(review_section, table_type="review")
            return trans_rows, review_rows
        tables = re.findall(r"\{\|.*?\n(.*?)\|\}", wikitext, re.DOTALL)
        if len(tables) >= 2:
            trans_rows = self._parse_single_table(tables[0], table_type="translation")
            review_rows = self._parse_single_table(tables[1], table_type="review")
        elif len(tables) == 1:
            trans_rows = self._parse_single_table(tables[0], table_type="translation")
        return trans_rows, review_rows

    def _parse_single_table(self, table_wikitext: str, table_type: str = "translation") -> List[Dict[str, str]]:
        """Helper to parse rows from one wikitext table body."""
        rows: List[Dict[str, str]] = []
        table_match = re.search(r"\{\|.*?\n(.*?)\|\}", table_wikitext, re.DOTALL)
        table_body = table_match.group(1) if table_match else table_wikitext

        raw_rows = re.split(r"\n\|-\s*", table_body)
        for raw_row in raw_rows:
            lines = [l.strip() for l in raw_row.strip().splitlines() if l.strip()]
            if not lines or any(l.startswith("!") for l in lines):
                continue  # Skip table header row

            cells: List[str] = []
            for line in lines:
                if line.startswith("|"):
                    cell_parts = line[1:].split(" || ")
                    for p in cell_parts:
                        cells.append(p.strip())

            if table_type == "review":
                # Review table columns:
                # 7-col: No | Judul Artikel | Dari / Pemohon / Mitra | Status Reviu | Tanggal | Draf Polesan | Status Artikel
                # 6-col (clean/private): No | Judul Artikel | Status Reviu | Tanggal | Draf Polesan | Status Artikel
                has_req_col = bool(re.search(r"!\s*(?:Dari|Pemohon|Mitra)\b", table_wikitext, re.IGNORECASE))
                if has_req_col or len(cells) >= 7:
                    if len(cells) >= 5:
                        no = cells[0]
                        raw_title = cells[1]
                        link_m = re.search(r"\[\[(?:[^|\]]+\|)?([^\]]+)\]\]", raw_title)
                        article_title = link_m.group(1).strip() if link_m else raw_title.strip()
                        if article_title.startswith(":"):
                            article_title = article_title[1:].strip()

                        requester = cells[2] if len(cells) > 2 else "-"
                        req_m = re.search(r"\[\[(?:Pengguna:)?([^|\]]+)(?:\|[^\]]+)?\]\]", requester)
                        clean_requester = req_m.group(1).strip() if req_m else requester.strip()

                        review_status = cells[3] if len(cells) > 3 else "-"
                        date = cells[4] if len(cells) > 4 else "-"
                        sandbox_draft = cells[5] if len(cells) > 5 else "-"
                        article_status = cells[6] if len(cells) > 6 else "-"
                        rows.append({
                            "no": no,
                            "title": article_title,
                            "requester": clean_requester,
                            "review_status": review_status,
                            "date": date,
                            "sandbox_draft": sandbox_draft,
                            "article_status": article_status,
                        })
                else:
                    if len(cells) >= 5:
                        no = cells[0]
                        raw_title = cells[1]
                        link_m = re.search(r"\[\[(?:[^|\]]+\|)?([^\]]+)\]\]", raw_title)
                        article_title = link_m.group(1).strip() if link_m else raw_title.strip()
                        if article_title.startswith(":"):
                            article_title = article_title[1:].strip()

                        review_status = cells[2]
                        date = cells[3] if len(cells) > 3 else "-"
                        sandbox_draft = cells[4] if len(cells) > 4 else "-"
                        article_status = cells[5] if len(cells) > 5 else "-"
                        rows.append({
                            "no": no,
                            "title": article_title,
                            "requester": None,
                            "review_status": review_status,
                            "date": date,
                            "sandbox_draft": sandbox_draft,
                            "article_status": article_status,
                        })
            else:
                # Translation table columns:
                # No | Judul Draf | Topik | Status | Tanggal | Artikel Resmi
                if len(cells) >= 5:
                    no = cells[0]
                    raw_title = cells[1]
                    link_m = re.search(r"\[\[(?:[^|\]]+\|)?([^\]]+)\]\]", raw_title)
                    article_title = link_m.group(1).strip() if link_m else raw_title.strip()
                    if article_title.startswith(":"):
                        article_title = article_title[1:].strip()

                    topic = cells[2]
                    status = cells[3]
                    date = cells[4]
                    mainspace_link = cells[5] if len(cells) >= 6 else "-"
                    rows.append({
                        "no": no,
                        "title": article_title,
                        "topic": topic,
                        "status": status,
                        "date": date,
                        "mainspace_link": mainspace_link,
                    })
        return rows

    def format_dashboard_wikitext(
        self,
        index_title: str,
        rows: List[Dict[str, str]],
        year: int,
        month: int,
        review_rows: Optional[List[Dict[str, str]]] = None,
        include_requester: bool = False,
    ) -> str:
        """
        Renders monthly dashboard wikitext with modern Vector-compliant sortable tables:
        1. Draf Terjemahan Baru
        2. Draf Peninjauan & Pemolesan Artikel (clean 6-col without Dari by default for user privacy)
        3. Ringkasan Statistik Bulanan
        """
        month_name = MONTH_NAMES_ID.get(month, f"{month:02d}")
        new_trans_count = len(rows)
        review_rows = review_rows or []
        reviews_count = len(review_rows)

        # Count promoted articles across both lists
        promoted_count = 0
        for r in rows:
            main_link = r.get("mainspace_link", "-")
            status_text = r.get("status", "")
            if main_link != "-" or "tayang" in status_text.lower():
                promoted_count += 1
        for r in review_rows:
            art_status = r.get("article_status", "")
            if "tayang" in art_status.lower():
                promoted_count += 1

        # Table 1: Draf Terjemahan Baru
        trans_table_rows = []
        for idx, r in enumerate(rows, start=1):
            title_val = r["title"]
            if "[[" not in title_val:
                clean_subpage = title_val.replace(" ", "_")
                link_val = f"[[{index_title}/{clean_subpage}|{title_val}]]"
            else:
                link_val = title_val

            main_link_val = r.get("mainspace_link", "-")
            if not main_link_val:
                main_link_val = "-"

            row_str = (
                f"|-\n"
                f"| {idx} || {link_val} || {r.get('topic', 'Umum')} || "
                f"{r.get('status', 'Draf aktif')} || {r.get('date', '-')} || {main_link_val}"
            )
            trans_table_rows.append(row_str)

        trans_body = "\n".join(trans_table_rows)
        if trans_body:
            trans_body = "\n" + trans_body + "\n"
        else:
            trans_body = "\n"

        # Table 2: Draf Peninjauan & Pemolesan Artikel
        review_table_rows = []
        for idx, r in enumerate(review_rows, start=1):
            raw_title = r["title"]
            if not raw_title.startswith("[["):
                title_link = f"[[:{raw_title}]]"
            else:
                title_link = raw_title

            sandbox_val = r.get("sandbox_draft", "-")
            if sandbox_val != "-" and "[[" not in sandbox_val:
                clean_sub = raw_title.replace(" ", "_")
                sandbox_val = f"[[{index_title}/{clean_sub}|{raw_title}]]"

            art_status_val = r.get("article_status", "Tersedia di Ruang Utama")
            if not art_status_val.startswith("[[") and art_status_val not in ("-", "None", ""):
                clean_art = raw_title.replace(" ", "_")
                art_status_val = f"[[:{clean_art}]]"

            if include_requester:
                requester_val = r.get("requester") or "-"
                if "[[" in requester_val:
                    clean_req = re.sub(r"\[\[(?:Pengguna:)?([^|\]]+)(?:\|[^\]]+)?\]\]", r"\1", requester_val).strip()
                else:
                    clean_req = requester_val.replace("Pengguna:", "").strip()
                row_str = (
                    f"|-\n"
                    f"| {idx} || {title_link} || {clean_req} || "
                    f"{r.get('review_status', 'Audit selesai')} || {r.get('date', '-')} || "
                    f"{sandbox_val} || {art_status_val}"
                )
            else:
                row_str = (
                    f"|-\n"
                    f"| {idx} || {title_link} || "
                    f"{r.get('review_status', 'Audit selesai')} || {r.get('date', '-')} || "
                    f"{sandbox_val} || {art_status_val}"
                )
            review_table_rows.append(row_str)

        rev_body = "\n".join(review_table_rows)
        if rev_body:
            rev_body = "\n" + rev_body + "\n"
        else:
            rev_body = "\n"

        req_header_line = "! Dari\n" if include_requester else ""
        wikitext = (
            f"== Draf {month_name} {year} ==\n\n"
            f"=== Terjemahan Baru ===\n"
            f'{{| class="wikitable sortable" style="width:100%"\n'
            f"|-\n"
            f"! No\n"
            f"! Judul\n"
            f"! Topik\n"
            f"! Status\n"
            f"! Tanggal\n"
            f"! Artikel{trans_body}"
            f"|}}\n\n"
            f"=== Perbaikan Artikel ===\n"
            f'{{| class="wikitable sortable" style="width:100%"\n'
            f"|-\n"
            f"! No\n"
            f"! Judul\n"
            f"{req_header_line}"
            f"! Status\n"
            f"! Tanggal\n"
            f"! Draf\n"
            f"! Artikel{rev_body}"
            f"|}}\n\n"
            f"=== Ringkasan ===\n"
            f"* '''Terjemahan baru:''' {new_trans_count}\n"
            f"* '''Perbaikan artikel:''' {reviews_count}\n"
            f"* '''Sudah tayang:''' {promoted_count}\n"
            f"* '''Semua subhalaman:''' [[Istimewa:IndeksAwalan/{index_title}/|Lihat]]"
        )
        return wikitext

    def update_monthly_dashboard(
        self,
        username: str,
        article_title: str,
        topic: Optional[str] = None,
        status: str = "Draf aktif",
        mainspace_link: Optional[str] = None,
        date_str: Optional[str] = None,
        slug: Optional[str] = None,
        project_slug: Optional[str] = DEFAULT_PROJECT_SLUG,
        bot_password: Optional[str] = None,
        dry_run: bool = False,
        activity_type: str = "translation",
        requester: Optional[str] = None,
        review_status: Optional[str] = None,
        sandbox_draft: Optional[str] = None,
        article_status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Updates or appends a row in the monthly index / dashboard page.
        Supports activity_type: 'translation' (Table 1) or 'review' (Table 2).
        Target: Pengguna:{clean_user}/Bak_pasir/{project_slug}/{YYYY-MM}
        """
        index_title = self.build_monthly_index_title(
            username=username,
            slug=slug,
            project_slug=project_slug,
        )
        index_url = f"{self.BASE_WEB_URL}/{urllib.parse.quote(index_title, safe='/:()')}"

        # Determine Year and Month from slug or today
        now = datetime.now()
        year, month = now.year, now.month
        m = re.search(r"(\d{4})-(\d{2})", index_title)
        if m:
            year, month = int(m.group(1)), int(m.group(2))

        # Date display for the row
        if not date_str:
            month_name = MONTH_NAMES_ID.get(now.month, f"{now.month:02d}")
            resolved_date = f"{now.day:02d} {month_name} {now.year}"
        else:
            resolved_date = date_str

        resolved_topic = topic or "Umum"
        resolved_mainspace = mainspace_link or "-"
        if resolved_mainspace != "-" and not resolved_mainspace.startswith("[["):
            resolved_mainspace = f"[[{resolved_mainspace}]]"

        if not dry_run and bot_password and not self._cookie_jar:
            self._authenticate_bot_password(username, bot_password)

        existing_content = None
        if not dry_run:
            existing_content = self.get_page_content(index_title)

        parsed_res = self.parse_dashboard_rows(existing_content or "")
        if isinstance(parsed_res, tuple):
            trans_rows, review_rows = parsed_res
        else:
            trans_rows, review_rows = parsed_res, []

        norm_target = article_title.strip().replace("_", " ").lower()
        if activity_type == "review":
            found = False
            resolved_requester = requester
            resolved_rev_status = review_status or status or "Audit selesai"
            clean_subpage = article_title.strip().replace(" ", "_")
            resolved_sandbox = sandbox_draft or f"[[{index_title}/{clean_subpage}|{article_title.strip()} (Draf Polesan)]]"
            resolved_art_status = article_status or (f"[[:{article_title.strip()}]]" if not article_title.startswith("[[") else article_title.strip())
            for r in review_rows:
                norm_row_title = r["title"].strip().replace("_", " ").lower()
                if norm_row_title == norm_target:
                    found = True
                    r["review_status"] = resolved_rev_status
                    if requester:
                        r["requester"] = requester
                    if sandbox_draft:
                        r["sandbox_draft"] = sandbox_draft
                    if article_status:
                        r["article_status"] = article_status
                    if date_str:
                        r["date"] = resolved_date
                    break
            if not found:
                review_rows.append({
                    "no": str(len(review_rows) + 1),
                    "title": article_title.strip(),
                    "requester": resolved_requester,
                    "review_status": resolved_rev_status,
                    "date": resolved_date,
                    "sandbox_draft": resolved_sandbox,
                    "article_status": resolved_art_status,
                })
        else:
            found = False
            for r in trans_rows:
                norm_row_title = r["title"].strip().replace("_", " ").lower()
                if norm_row_title == norm_target:
                    found = True
                    r["status"] = status
                    if topic:
                        r["topic"] = topic
                    if mainspace_link is not None:
                        r["mainspace_link"] = resolved_mainspace
                    if date_str:
                        r["date"] = resolved_date
                    break
            if not found:
                trans_rows.append({
                    "no": str(len(trans_rows) + 1),
                    "title": article_title.strip(),
                    "topic": resolved_topic,
                    "status": status,
                    "date": resolved_date,
                    "mainspace_link": resolved_mainspace,
                })

        should_include_req = bool(requester)
        updated_wikitext = self.format_dashboard_wikitext(
            index_title=index_title,
            rows=trans_rows,
            year=year,
            month=month,
            review_rows=review_rows,
            include_requester=should_include_req,
        )

        total_items = len(trans_rows) + len(review_rows)
        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "index_title": index_title,
                "url": index_url,
                "wikitext": updated_wikitext,
                "total_drafts": total_items,
                "translation_drafts": len(trans_rows),
                "review_drafts": len(review_rows),
            }

        if not bot_password:
            return {
                "success": False,
                "error": "bot_password required to publish dashboard live",
                "index_title": index_title,
                "url": index_url,
            }

        # Authenticate if session empty
        if not self._cookie_jar:
            login_ok, login_err = self._authenticate_bot_password(username, bot_password)
            if not login_ok:
                return {
                    "success": False,
                    "error": f"Authentication failed: {login_err}",
                    "index_title": index_title,
                    "url": index_url,
                }

        csrf_token, token_err = self._get_csrf_token()
        if not csrf_token:
            return {
                "success": False,
                "error": f"Failed to get CSRF token: {token_err}",
                "index_title": index_title,
                "url": index_url,
            }

        edit_res = self._edit_page(
            title=index_title,
            text=updated_wikitext,
            summary=DEFAULT_DASHBOARD_SUMMARY,
            csrf_token=csrf_token,
        )
        if not edit_res.get("success"):
            return {
                "success": False,
                "error": edit_res.get("error", "Failed to update dashboard"),
                "index_title": index_title,
                "url": index_url,
            }

        return {
            "success": True,
            "dry_run": False,
            "index_title": index_title,
            "url": index_url,
            "pageid": edit_res.get("edit", {}).get("pageid"),
            "newrevid": edit_res.get("edit", {}).get("newrevid"),
            "total_drafts": total_items,
            "translation_drafts": len(trans_rows),
            "review_drafts": len(review_rows),
        }

    def publish_to_sandbox(
        self,
        username: str,
        bot_password: str,
        article_title: str,
        wikitext: str,
        talk_wikitext: Optional[str] = None,
        slug: Optional[str] = None,
        project_slug: Optional[str] = DEFAULT_PROJECT_SLUG,
        summary: Optional[str] = None,
        talk_summary: Optional[str] = None,
        is_new_page: Optional[bool] = None,
        topic: Optional[str] = None,
        dry_run: bool = False,
        update_dashboard: bool = True,
    ) -> Dict[str, Any]:
        """
        Publishes wikitext and optional talk_wikitext to the user's sandbox hierarchy.
        Supports dry_run=True for safe local testing without making network calls.
        Generates natural human-like edit summaries (Anti-Bot / Anti-Slop History).
        """
        main_title, talk_title = self.build_sandbox_titles(
            username=username,
            article_title=article_title,
            slug=slug,
            project_slug=project_slug,
        )
        main_url = f"{self.BASE_WEB_URL}/{urllib.parse.quote(main_title)}"
        talk_url = f"{self.BASE_WEB_URL}/{urllib.parse.quote(talk_title)}"

        dashboard_info: Optional[Dict[str, Any]] = None
        if summary:
            edit_summary = sanitize_edit_summary(summary, default_fallback=self.DEFAULT_UPDATE_SUMMARY if is_new_page is False else self.DEFAULT_SUMMARY)
        else:
            # Natural human edit summaries
            if is_new_page is False:
                edit_summary = self.DEFAULT_UPDATE_SUMMARY
            else:
                edit_summary = self.DEFAULT_SUMMARY

        resolved_talk_summary = sanitize_edit_summary(talk_summary or self.DEFAULT_TALK_SUMMARY, default_fallback=self.DEFAULT_TALK_SUMMARY)
        if dry_run:
            result: Dict[str, Any] = {
                "success": True,
                "dry_run": True,
                "main_page": {
                    "title": main_title,
                    "url": main_url,
                    "status": "simulated",
                    "bytes": len(wikitext),
                    "summary": edit_summary,
                },
            }
            if talk_wikitext:
                result["talk_page"] = {
                    "title": talk_title,
                    "url": talk_url,
                    "status": "simulated",
                    "bytes": len(talk_wikitext),
                    "summary": resolved_talk_summary,
                }
            if update_dashboard:
                dash_res = self.update_monthly_dashboard(
                    username=username,
                    article_title=article_title,
                    topic=topic,
                    status="Draf aktif",
                    slug=slug,
                    project_slug=project_slug,
                    dry_run=True,
                )
                result["dashboard"] = dash_res
            return result
        # Reset session cookies for fresh login
        self._cookie_jar = {}

        # Step 1 & 2: Login via MediaWiki Bot Password
        login_success, login_err = self._authenticate_bot_password(username, bot_password)
        if not login_success:
            return {
                "success": False,
                "error": f"Authentication failed: {login_err}",
                "main_page": {"title": main_title, "url": main_url},
            }

        # Step 3: Fetch CSRF edit token
        csrf_token, token_err = self._get_csrf_token()
        if not csrf_token:
            return {
                "success": False,
                "error": f"Failed to obtain CSRF token: {token_err}",
                "main_page": {"title": main_title, "url": main_url},
            }

        # Step 4: Publish Main Sandbox Page
        main_resp = self._edit_page(
            title=main_title,
            text=wikitext,
            summary=edit_summary,
            csrf_token=csrf_token,
        )

        if not main_resp.get("success"):
            return {
                "success": False,
                "error": main_resp.get("error", "Unknown edit error on main page"),
                "main_page": {
                    "title": main_title,
                    "url": main_url,
                    "response": main_resp,
                },
            }

        result = {
            "success": True,
            "dry_run": False,
            "main_page": {
                "title": main_title,
                "url": main_url,
                "status": "published",
                "pageid": main_resp.get("edit", {}).get("pageid"),
                "newrevid": main_resp.get("edit", {}).get("newrevid"),
                "bytes": len(wikitext),
            },
        }

        # Step 5: Publish Talk Page Attribution (if provided)
        if talk_wikitext:
            talk_resp = self._edit_page(
                title=talk_title,
                text=talk_wikitext,
                summary=resolved_talk_summary,
                csrf_token=csrf_token,
            )
            result["talk_page"] = {
                "title": talk_title,
                "url": talk_url,
                "status": "published" if talk_resp.get("success") else "failed",
                "pageid": talk_resp.get("edit", {}).get("pageid"),
                "newrevid": talk_resp.get("edit", {}).get("newrevid"),
                "error": talk_resp.get("error"),
                "bytes": len(talk_wikitext),
            }


        # Step 6: Update Monthly Dashboard (Log Book)
        if update_dashboard:
            try:
                dash_res = self.update_monthly_dashboard(
                    username=username,
                    article_title=article_title,
                    topic=topic,
                    status="Draf aktif",
                    slug=slug,
                    project_slug=project_slug,
                    bot_password=bot_password,
                    dry_run=False,
                )
                result["dashboard"] = dash_res
            except Exception as e:
                result["dashboard"] = {"success": False, "error": str(e)}
        return result

    def _make_request(
        self, params: Dict[str, Any], method: str = "GET"
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Executes an HTTP request to MediaWiki API with session cookie management."""
        self.http_client.api_url = self.api_url
        self.http_client.user_agent = self.user_agent
        return self.http_client.request(params, method=method)
    def _authenticate_bot_password(
        self, username: str, bot_password: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Authenticates using MediaWiki Bot Password flow:
        1. Query login token: action=query&meta=tokens&type=login
        2. Post login: action=login&lgname=...&lgpassword=...&lgtoken=...
        """
        # 1. Fetch login token
        token_payload, err = self._make_request(
            {"action": "query", "meta": "tokens", "type": "login"}, method="GET"
        )
        if err or not token_payload:
            return False, f"Failed to get login token: {err}"

        login_token = (
            token_payload.get("query", {}).get("tokens", {}).get("logintoken")
        )
        if not login_token:
            return False, "Login token not found in API response"

        # 2. Perform login
        login_params = {
            "action": "login",
            "lgname": username,
            "lgpassword": bot_password,
            "lgtoken": login_token,
        }
        resp, login_err = self._make_request(login_params, method="POST")
        if login_err or not resp:
            return False, f"Login HTTP request failed: {login_err}"

        login_res = resp.get("login", {})
        status = login_res.get("result")
        if status == "Success":
            return True, None
        else:
            reason = login_res.get("reason", status)
            return False, f"Login rejected: {reason}"

    def _get_csrf_token(self) -> Tuple[Optional[str], Optional[str]]:
        """Fetches CSRF token for edit actions: action=query&meta=tokens&type=csrf."""
        payload, err = self._make_request(
            {"action": "query", "meta": "tokens", "type": "csrf"}, method="GET"
        )
        if err or not payload:
            return None, err

        token = payload.get("query", {}).get("tokens", {}).get("csrftoken")
        if not token:
            return None, "CSRF token not present in query tokens"
        return token, None

    def _edit_page(
        self, title: str, text: str, summary: str, csrf_token: str
    ) -> Dict[str, Any]:
        """Edits/creates a page using action=edit."""
        params = {
            "action": "edit",
            "title": title,
            "text": text,
            "summary": summary,
            "token": csrf_token,
        }
        payload, err = self._make_request(params, method="POST")
        if err or not payload:
            return {"success": False, "error": f"Network/HTTP error: {err}"}

        if "error" in payload:
            err_info = payload["error"].get("info", str(payload["error"]))
            return {"success": False, "error": err_info}

        edit_result = payload.get("edit", {})
        if edit_result.get("result") == "Success":
            return {"success": True, "edit": edit_result}
        else:
            return {
                "success": False,
                "error": f"Edit failed with status: {edit_result.get('result')}",
                "edit": edit_result,
            }


default_sandbox_publisher = SandboxPublisher()
