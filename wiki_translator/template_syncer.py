"""
Template Synchronization & Documentation Engine for wiki_translator.

Fetches templates from en.wikipedia.org, translates their groups and structure to
id.wikipedia.org standards, maps internal wikilinks, generates professional Indonesian
/doc documentation, and supports live updating.
"""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
import urllib.error
import urllib.parse
import urllib.request

from .wiki_client import PageNotFoundError, WikipediaClient
from .wiki_link_mapper import WikiLinkMapper, default_link_mapper
from .template_doc_auditor import TemplateDocAuditor, default_template_doc_auditor
from .navbox_generator import STANDARD_GROUP_TRANSLATIONS, PARAM_TRANSLATION_MAP

# Additional group translations specific to broad templates / navboxes / infoboxes
EXTENDED_GROUP_TRANSLATIONS: Dict[str, str] = {
    **STANDARD_GROUP_TRANSLATIONS,
    "feature films": "Film layar lebar",
    "documentaries": "Film dokumenter",
    "documentary films": "Film dokumenter",
    "other": "Karya lainnya",
    "others": "Lainnya",
    "directed by": "Disutradarai oleh",
    "produced by": "Diproduseri oleh",
    "written by": "Ditulis oleh",
    "music by": "Musik oleh",
    "cinematography by": "Sinematografi oleh",
    "edited by": "Disunting oleh",
    "screenplay by": "Skenario oleh",
    "story by": "Cerita oleh",
    "executive producer": "Produser eksekutif",
    "executive producers": "Produser eksekutif",
    "creator": "Pencipta",
    "creators": "Pencipta",
    "cast and characters": "Pemeran dan karakter",
    "main characters": "Karakter utama",
    "recurring characters": "Karakter berulang",
    "guest characters": "Karakter tamu",
    "seasons": "Musim",
    "season 1": "Musim 1",
    "season 2": "Musim 2",
    "season 3": "Musim 3",
    "season 4": "Musim 4",
    "season 5": "Musim 5",
    "adaptations": "Adaptasi",
    "soundtracks": "Jalur suara",
    "discography": "Diskografi",
    "bibliography": "Bibliografi",
    "filmography": "Filmografi",
    "awards and nominations": "Penghargaan dan nominasi",
    "related articles": "Artikel terkait",
    "related": "Terkait",
    "see also": "Lihat pula",
    "external links": "Pranala luar",
    "references": "Referensi",
}


class TemplateSyncer:
    """
    Synchronizes templates and documentation from en.wikipedia.org to id.wikipedia.org.
    """

    ID_WIKI_API = "https://id.wikipedia.org/w/api.php"
    EN_WIKI_API = "https://en.wikipedia.org/w/api.php"
    DEFAULT_USER_AGENT = "WikiTranslatorGradeA/1.0 (https://id.wikipedia.org; template-syncer)"

    def __init__(
        self,
        en_client: Optional[WikipediaClient] = None,
        id_client: Optional[WikipediaClient] = None,
        link_mapper: Optional[WikiLinkMapper] = None,
        doc_auditor: Optional[TemplateDocAuditor] = None,
        id_api_url: str = ID_WIKI_API,
        en_api_url: str = EN_WIKI_API,
        user_agent: str = DEFAULT_USER_AGENT,
        output_dir: Optional[Path] = None,
    ):
        self.en_client = en_client or WikipediaClient(lang="en")
        self.id_client = id_client or WikipediaClient(lang="id")
        self.link_mapper = link_mapper or default_link_mapper
        self.doc_auditor = doc_auditor or default_template_doc_auditor
        self.id_api_url = id_api_url
        self.en_api_url = en_api_url
        self.user_agent = user_agent
        self.output_dir = Path(output_dir) if output_dir else Path("output/templates")
        self._cookie_jar: Dict[str, str] = {}

    def _clean_template_name(self, template_name: str) -> str:
        """Strips namespace prefixes and extra whitespace."""
        clean = template_name.strip()
        clean = re.sub(r"^(Template|Templat)\s*:\s*", "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"/doc$", "", clean, flags=re.IGNORECASE)
        return clean.strip()

    def fetch_en_template_wikitext(self, template_name: str) -> str:
        """Fetches `Template:<Name>` from en.wikipedia.org."""
        clean_name = self._clean_template_name(template_name)
        en_title = f"Template:{clean_name}"
        return self.en_client.fetch_wikitext(en_title, check_disambiguation=False)
    def fetch_en_doc_wikitext(self, template_name: str) -> Optional[str]:
        """Fetches `Template:<Name>/doc` from en.wikipedia.org if it exists, else None."""
        clean_name = self._clean_template_name(template_name)
        en_doc_title = f"Template:{clean_name}/doc"
        try:
            return self.en_client.fetch_wikitext(en_doc_title, check_disambiguation=False)
        except PageNotFoundError:
            return None
        except Exception:
            return None


    def translate_group_label(self, label: str) -> str:
        """Translates group labels using standard and extended dictionaries."""
        clean_label = label.strip()
        lower_label = clean_label.lower()

        if lower_label in EXTENDED_GROUP_TRANSLATIONS:
            return EXTENDED_GROUP_TRANSLATIONS[lower_label]

        # Handle bold/italic or wikilinks: e.g. "[[Documentaries]]" or "'''Feature films'''"
        plain = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", clean_label)
        plain = re.sub(r"['*#]", "", plain).strip().lower()

        if plain in EXTENDED_GROUP_TRANSLATIONS:
            trans = EXTENDED_GROUP_TRANSLATIONS[plain]
            if clean_label.startswith("'''") and clean_label.endswith("'''"):
                return f"'''{trans}'''"
            if clean_label.startswith("''") and clean_label.endswith("''"):
                return f"''{trans}''"
            return trans

        return clean_label

    def _split_template_parameters(self, template_body: str) -> List[Tuple[str, str]]:
        """
        Parses top-level parameters of a template body into (param_name, param_value) tuples.
        Respects nested {{...}} and [[...]].
        """
        params: List[Tuple[str, str]] = []
        pos = 0
        n = len(template_body)
        current_part: List[str] = []
        depth_curly = 0
        depth_square = 0

        while pos < n:
            ch = template_body[pos]
            next_ch = template_body[pos + 1] if pos + 1 < n else ""

            if ch == "{" and next_ch == "{":
                depth_curly += 2
                current_part.append("{{")
                pos += 2
                continue
            elif ch == "}" and next_ch == "}":
                depth_curly = max(0, depth_curly - 2)
                current_part.append("}}")
                pos += 2
                continue
            elif ch == "[" and next_ch == "[":
                depth_square += 2
                current_part.append("[[")
                pos += 2
                continue
            elif ch == "]" and next_ch == "]":
                depth_square = max(0, depth_square - 2)
                current_part.append("]]")
                pos += 2
                continue
            elif ch == "|" and depth_curly == 0 and depth_square == 0:
                param_text = "".join(current_part).strip()
                if param_text:
                    if "=" in param_text:
                        p_name, p_val = param_text.split("=", 1)
                        params.append((p_name.strip(), p_val.strip()))
                    else:
                        params.append(("", param_text))
                current_part = []
                pos += 1
                continue

            current_part.append(ch)
            pos += 1

        param_text = "".join(current_part).strip()
        if param_text:
            if "=" in param_text:
                p_name, p_val = param_text.split("=", 1)
                params.append((p_name.strip(), p_val.strip()))
            else:
                params.append(("", param_text))

        return params

    def translate_template_wikitext(self, en_wikitext: str, id_template_name: str) -> str:
        """
        Translates groups and structure of an en.wiki template wikitext to id.wiki standards:
        - Detects template type (Navbox / Kotak navigasi, or general template)
        - Translates parameter keys and group names
        - Maps wikilinks across lists, titles, above/below
        - Wraps tail in `<noinclude>\\n{{Dokumentasi navbox}}\\n{category_lines}\\n</noinclude>`
          for navbox templates, or standard `{{Dokumentasi}}` for general templates.
        """
        clean_target = self._clean_template_name(id_template_name)

        # Check if it contains a Navbox / Kotak navigasi structure
        navbox_start = re.search(
            r"\{\{\s*(?:Template:)?(?:Navbox|Kotak navigasi)\s*\|",
            en_wikitext,
            flags=re.IGNORECASE,
        )

        if navbox_start:
            start_idx = navbox_start.start()
            depth = 0
            end_idx = start_idx
            for i in range(start_idx, len(en_wikitext) - 1):
                if en_wikitext[i : i + 2] == "{{":
                    depth += 1
                elif en_wikitext[i : i + 2] == "}}":
                    depth -= 1
                    if depth == 0:
                        end_idx = i + 2
                        break
            navbox_full = en_wikitext[start_idx:end_idx]
            inner = navbox_full[2:-2].strip()
            inner = re.sub(
                r"^(?:Template:)?(?:Navbox|Kotak navigasi)\s*\|\s*",
                "",
                inner,
                flags=re.IGNORECASE,
            )
            raw_params = self._split_template_parameters(inner)

            converted_params: List[Tuple[str, str]] = []
            for name, val in raw_params:
                if not name:
                    continue
                lower_name = name.lower()
                new_key = PARAM_TRANSLATION_MAP.get(lower_name, lower_name)

                group_match = re.match(r"^group(\d+)$", lower_name)
                list_match = re.match(r"^list(\d+)$", lower_name)

                if group_match:
                    new_key = f"kelompok{group_match.group(1)}"
                    val = self.translate_group_label(val)
                elif list_match:
                    new_key = f"daftar{list_match.group(1)}"
                    val = self.link_mapper.map_wikilinks(val)
                elif lower_name == "name" or new_key == "nama":
                    val = clean_target
                elif lower_name == "title" or new_key == "judul":
                    val = self.link_mapper.map_wikilinks(val)
                elif lower_name in ("above", "below") or new_key in ("atas", "bawah"):
                    val = self.link_mapper.map_wikilinks(val)
                else:
                    # Generic param value with wikilinks
                    val = self.link_mapper.map_wikilinks(val)

                converted_params.append((new_key, val))

            lines = ["{{Kotak navigasi"]
            for k, v in converted_params:
                if "\n" in v:
                    lines.append(f"| {k} = \n{v}")
                else:
                    lines.append(f"| {k} = {v}")
            lines.append("}}")
            body_wikitext = "\n".join(lines)
            is_navbox = True
        else:
            is_navbox = False
            # General template structure
            # Strip existing noinclude blocks from original tail
            cleaned_text = re.sub(
                r"<noinclude>.*?</noinclude>", "", en_wikitext, flags=re.DOTALL | re.IGNORECASE
            ).strip()

            # Translate groups in parameters if present: e.g. | group1 = ... or | Feature films =
            def group_replacer(match: re.Match) -> str:
                param_name = match.group(1)
                group_val = match.group(2)
                trans_val = self.translate_group_label(group_val)
                return f"| {param_name} = {trans_val}"

            cleaned_text = re.sub(
                r"\|\s*(group\d+|kelompok\d+)\s*=\s*([^|\}\n]+)",
                group_replacer,
                cleaned_text,
                flags=re.IGNORECASE,
            )

            # Map all internal links via WikiLinkMapper
            body_wikitext = self.link_mapper.map_wikilinks(cleaned_text)

        # Extract and map any category lines from en_wikitext
        cat_lines: List[str] = []
        existing_cats = re.findall(
            r"\[\[\s*(?:Category|Kategori)\s*:\s*([^\]|]+)(?:\|([^\]]*))?\]\]",
            en_wikitext,
            flags=re.IGNORECASE,
        )
        for cat_name, sortkey in existing_cats:
            cat_clean = cat_name.strip()
            # Ignore documentation / template tracking categories if not needed
            mapped = self.link_mapper.map_categories(f"[[Category:{cat_clean}]]")
            if mapped and "Kategori:" in mapped:
                m = re.match(r"\[\[\s*Kategori:\s*([^\]|]+)", mapped, flags=re.IGNORECASE)
                if m:
                    id_cat_name = m.group(1).strip()
                    if sortkey and sortkey.strip():
                        cat_lines.append(f"[[Kategori:{id_cat_name}|{sortkey.strip()}]]")
                    else:
                        cat_lines.append(f"[[Kategori:{id_cat_name}]]")
            elif cat_clean.startswith("Templat navigasi"):
                if sortkey and sortkey.strip():
                    cat_lines.append(f"[[Kategori:{cat_clean}|{sortkey.strip()}]]")
                else:
                    cat_lines.append(f"[[Kategori:{cat_clean}]]")

        # Check if the template or body uses Navbox / Kotak navigasi
        if not is_navbox:
            is_navbox = bool(
                re.search(r"\{\{\s*(?:Template:)?(?:Navbox|Kotak navigasi)\b", body_wikitext, re.IGNORECASE)
                or re.search(r"\{\{\s*(?:Template:)?(?:Navbox|Kotak navigasi)\b", en_wikitext, re.IGNORECASE)
            )

        # Append documentation tail
        if is_navbox:
            doc_tag = "{{Dokumentasi navbox}}"
            if cat_lines:
                cat_block = "\n" + "\n".join(cat_lines)
            else:
                cat_block = ""
            final_wikitext = f"{body_wikitext}\n<noinclude>\n{doc_tag}{cat_block}\n</noinclude>"
        else:
            doc_tag = "{{Dokumentasi}}"
            if cat_lines:
                cat_block = "\n" + "\n".join(cat_lines)
            else:
                cat_block = ""
            final_wikitext = f"{body_wikitext}\n<noinclude>\n{doc_tag}{cat_block}\n</noinclude>"
        return final_wikitext.strip()

    def generate_doc_wikitext(
        self,
        template_name: str,
        parameters: Optional[List[str]] = None,
        description: Optional[str] = None,
        topic: Optional[str] = None,
        is_navbox: bool = False,
        see_also: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
    ) -> str:
        """
        Generates /doc wikitext.
        If is_navbox is True, delegates to rich `generate_navbox_doc_wikitext` with
        {{Dokumentasi navbox}}, TemplateData, and collapsible option.
        Otherwise, delegates to standard `generate_doc_wikitext`.
        """
        clean_name = self._clean_template_name(template_name)
        if is_navbox:
            return self.doc_auditor.generate_navbox_doc_wikitext(
                template_name=clean_name,
                topic=topic,
                see_also=see_also,
                categories=categories,
            )
        return self.doc_auditor.generate_doc_wikitext(
            template_name=clean_name,
            parameters=parameters,
            description=description or f"Dokumentasi untuk [[Templat:{clean_name}]].",
            topic=topic,
        )

    def _make_request(
        self, params: Dict[str, Any], method: str = "GET"
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Makes an HTTP request to id.wikipedia.org API maintaining cookie jar session."""
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }
        if self._cookie_jar:
            cookie_str = "; ".join(f"{k}={v}" for k, v in self._cookie_jar.items())
            headers["Cookie"] = cookie_str

        try:
            if method.upper() == "GET":
                query_string = urllib.parse.urlencode(
                    {**params, "format": "json", "formatversion": "2"}
                )
                url = f"{self.id_api_url}?{query_string}"
                req = urllib.request.Request(url, headers=headers, method="GET")
            else:
                post_data = urllib.parse.urlencode(
                    {**params, "format": "json", "formatversion": "2"}
                ).encode("utf-8")
                headers["Content-Type"] = "application/x-www-form-urlencoded"
                req = urllib.request.Request(
                    self.id_api_url, data=post_data, headers=headers, method="POST"
                )

            with urllib.request.urlopen(req, timeout=30) as resp:
                # Update cookies
                set_cookie = resp.headers.get_all("Set-Cookie") or resp.headers.get(
                    "Set-Cookie"
                )
                if set_cookie:
                    cookies_to_process = (
                        set_cookie if isinstance(set_cookie, list) else [set_cookie]
                    )
                    for c_header in cookies_to_process:
                        for cookie in c_header.split(","):
                            parts = cookie.split(";")[0].split("=", 1)
                            if len(parts) == 2:
                                self._cookie_jar[parts[0].strip()] = parts[1].strip()

                raw_body = resp.read().decode("utf-8")
                data = json.loads(raw_body)
                return data, None

        except urllib.error.HTTPError as e:
            return None, f"HTTP {e.code}: {e.reason}"
        except Exception as e:
            return None, str(e)

    def _authenticate_bot_password(
        self, username: str, bot_password: str
    ) -> Tuple[bool, Optional[str]]:
        """Authenticates using MediaWiki Bot Password flow."""
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
        """Edits/creates a page on id.wikipedia.org using action=edit."""
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

    def save_templates_locally(
        self,
        template_name: str,
        template_wikitext: str,
        doc_wikitext: str,
        output_dir: Optional[Path] = None,
    ) -> Tuple[Path, Path]:
        """
        Saves local wikitext to `output/templates/<Name>.wikitext` and
        `output/templates/<Name>_doc.wikitext`.
        """
        clean_name = self._clean_template_name(template_name)
        safe_name = re.sub(r'[\\/*?:"<>| ]', "_", clean_name)
        target_dir = Path(output_dir or self.output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        template_file = target_dir / f"{safe_name}.wikitext"
        doc_file = target_dir / f"{safe_name}_doc.wikitext"

        template_file.write_text(template_wikitext, encoding="utf-8")
        doc_file.write_text(doc_wikitext, encoding="utf-8")

        return template_file, doc_file

    def sync_template(
        self,
        template_name: str,
        id_template_name: Optional[str] = None,
        publish: bool = False,
        username: Optional[str] = None,
        bot_password: Optional[str] = None,
        output_dir: Optional[Path] = None,
        topic: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Main synchronization pipeline:
        1. Fetches en.wiki template wikitext.
        2. Translates groups and structure.
        3. Generates professional Indonesian /doc wikitext.
        4. Saves both files locally to output/templates/.
        5. If publish=True and credentials available, publishes Templat:<Name>
           and Templat:<Name>/doc via MediaWiki API.
        """
        clean_en_name = self._clean_template_name(template_name)
        clean_id_name = (
            self._clean_template_name(id_template_name)
            if id_template_name
            else clean_en_name
        )

        # 1. Fetch raw en template wikitext
        en_wikitext = self.fetch_en_template_wikitext(clean_en_name)

        # 2. Translate groups, structure, wikilinks, add <noinclude>{{Dokumentasi}}</noinclude>
        translated_wikitext = self.translate_template_wikitext(
            en_wikitext=en_wikitext, id_template_name=clean_id_name
        )

        # Extract parameters for doc generation
        params_found: List[str] = []
        raw_params = self._split_template_parameters(translated_wikitext)
        for p_name, _ in raw_params:
            if p_name and p_name not in params_found:
                params_found.append(p_name)

        # 3. Handle /doc documentation wikitext
        # Check if Template:<Name>/doc exists on en.wiki
        en_doc_raw = self.fetch_en_doc_wikitext(clean_en_name)
        is_navbox = bool(
            re.search(r"\{\{\s*(?:Template:)?(?:Navbox|Kotak navigasi)\b", en_wikitext, re.IGNORECASE)
            or "navbox" in clean_en_name.lower()
        )

        if isinstance(en_doc_raw, str) and en_doc_raw.strip():
            # Custom /doc exists on en.wiki: translate its wikilinks and categories
            translated_doc = self.link_mapper.map_wikilinks(en_doc_raw)
            translated_doc = self.link_mapper.map_categories(translated_doc)
            # Translate English heading names
            translated_doc = re.sub(r"==\s*Usage\s*==", "== Penggunaan ==", translated_doc, flags=re.IGNORECASE)
            translated_doc = re.sub(r"==\s*See also\s*==", "== Lihat pula ==", translated_doc, flags=re.IGNORECASE)
            translated_doc = re.sub(r"==\s*Parameters\s*==", "== Parameter ==", translated_doc, flags=re.IGNORECASE)
            translated_doc = re.sub(r"==\s*TemplateData\s*==", "== Data templat ==", translated_doc, flags=re.IGNORECASE)
            doc_wikitext = translated_doc.strip()
        else:
            # No custom /doc or en.wiki uses {{navbox documentation}}:
            # use rich Indonesian documentation suite!
            if is_navbox:
                doc_wikitext = self.doc_auditor.generate_navbox_doc_wikitext(
                    template_name=clean_id_name,
                    topic=topic,
                )
            else:
                doc_wikitext = self.generate_doc_wikitext(
                    template_name=clean_id_name,
                    parameters=params_found,
                    topic=topic,
                    is_navbox=False,
                )

        # 4. Save to local output/templates/<Name>.wikitext and <Name>_doc.wikitext
        target_dir = output_dir or self.output_dir
        template_file, doc_file = self.save_templates_locally(
            template_name=clean_id_name,
            template_wikitext=translated_wikitext,
            doc_wikitext=doc_wikitext,
            output_dir=target_dir,
        )

        result: Dict[str, Any] = {
            "template_name": clean_id_name,
            "id_title": f"Templat:{clean_id_name}",
            "doc_title": f"Templat:{clean_id_name}/doc",
            "template_file": str(template_file),
            "doc_file": str(doc_file),
            "wikitext": translated_wikitext,
            "doc_wikitext": doc_wikitext,
            "published": False,
            "publish_results": {},
        }

        # 5. Handle publication if requested
        if publish:
            wiki_user = (
                username
                or os.environ.get("WIKI_USERNAME")
                or os.environ.get("MEDIAWIKI_USERNAME")
                or os.environ.get("WIKI_SANDBOX_USER")
            )
            bot_pass = (
                bot_password
                or os.environ.get("WIKI_BOT_PASSWORD")
                or os.environ.get("MEDIAWIKI_BOT_PASSWORD")
            )

            if not wiki_user or not bot_pass:
                result["publish_results"] = {
                    "success": False,
                    "error": "Credentials missing (WIKI_USERNAME or WIKI_BOT_PASSWORD not found)",
                }
                return result

            # Authenticate
            login_ok, login_err = self._authenticate_bot_password(wiki_user, bot_pass)
            if not login_ok:
                result["publish_results"] = {
                    "success": False,
                    "error": f"Authentication failed: {login_err}",
                }
                return result

            # Fetch CSRF token
            csrf_token, token_err = self._get_csrf_token()
            if not csrf_token:
                result["publish_results"] = {
                    "success": False,
                    "error": f"Failed to obtain CSRF token: {token_err}",
                }
                return result

            summary = "pemutakhiran templat & dokumentasi"
            # Edit main template
            template_res = self._edit_page(
                title=f"Templat:{clean_id_name}",
                text=translated_wikitext,
                summary=summary,
                csrf_token=csrf_token,
            )
            # Edit doc subpage
            doc_res = self._edit_page(
                title=f"Templat:{clean_id_name}/doc",
                text=doc_wikitext,
                summary=summary,
                csrf_token=csrf_token,
            )

            is_published = bool(
                template_res.get("success") and doc_res.get("success")
            )
            result["published"] = is_published
            result["publish_results"] = {
                "success": is_published,
                "template_edit": template_res,
                "doc_edit": doc_res,
            }

        return result


default_template_syncer = TemplateSyncer()
