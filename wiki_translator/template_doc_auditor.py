"""
Template Documentation Auditor and Generator for id.wikipedia.org.

Audits and generates documentation subpages (`Templat:<Name>/doc`) for templates on id.wikipedia.
Features:
- Checks if Templat:<Name>/doc exists on id.wikipedia.org via Action API.
- Generates standard /doc wikitext:
  * Summary description of the template.
  * Clean blank syntax box for copying (`== Penggunaan ==\\n<pre>{{Nama templat\\n| parameter1 = \\n| parameter2 = \\n}}</pre>`).
  * Parameter explanations (`=== Parameter ===`).
  * TemplateData block (`<templatedata>...</templatedata>`).
  * Categorization wrapped inside `<includeonly>[[Kategori:Templat ...]]</includeonly>`.
- Saves to output/templates/<SafeName>_doc.wikitext.
"""

import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.parse
import urllib.request


class TemplateDocAuditor:
    """Audits and generates documentation subpages (Templat:<Name>/doc) for id.wikipedia."""

    def __init__(
        self,
        lang: str = "id",
        user_agent: Optional[str] = None,
        api_url: Optional[str] = None,
    ):
        self.lang = lang
        self.api_url = api_url or f"https://{lang}.wikipedia.org/w/api.php"
        self.user_agent = (
            user_agent
            or "WikiTranslatorGradeA/1.0 (https://id.wikipedia.org; template-doc-auditor)"
        )

    def _clean_template_name(self, template_name: str) -> str:
        """Strips namespace prefix 'Templat:' or 'Template:' and whitespace."""
        clean = template_name.strip()
        clean = re.sub(r"^(Templat|Template)\s*:\s*", "", clean, flags=re.IGNORECASE)
        # Remove trailing /doc if passed inadvertently
        clean = re.sub(r"/doc$", "", clean, flags=re.IGNORECASE)
        return clean.strip()

    def check_doc_exists(self, template_name: str) -> bool:
        """Checks if Templat:<Name>/doc exists on id.wikipedia.org via Action API."""
        clean_name = self._clean_template_name(template_name)
        full_doc_title = f"Templat:{clean_name}/doc"

        params = {
            "action": "query",
            "titles": full_doc_title,
            "format": "json",
            "formatversion": "2",
        }
        query_str = urllib.parse.urlencode(params)
        url = f"{self.api_url}?{query_str}"

        req = urllib.request.Request(
            url,
            headers={"User-Agent": self.user_agent},
            method="GET",
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            pages = data.get("query", {}).get("pages", [])
            if not pages:
                return False
            page = pages[0]
            if page.get("missing"):
                return False
            if "invalid" in page:
                return False
            return True
        except Exception:
            return False

    def generate_templatedata(
        self,
        template_name: str,
        parameters: List[str],
        description: str,
    ) -> str:
        """Generates a standard TemplateData JSON block wrapped in <templatedata> tags."""
        param_dict: Dict[str, Any] = {}
        for param in parameters:
            param_cleaned = param.strip()
            if not param_cleaned:
                continue
            param_dict[param_cleaned] = {
                "label": param_cleaned.replace("_", " ").title(),
                "description": f"Parameter {param_cleaned} untuk templat {template_name}.",
                "type": "string",
                "required": False,
            }

        td_data = {
            "description": description,
            "params": param_dict,
            "format": "block",
        }
        formatted_json = json.dumps(td_data, indent=2, ensure_ascii=False)
        return f"<templatedata>\n{formatted_json}\n</templatedata>"

    def generate_doc_wikitext(
        self,
        template_name: str,
        parameters: Optional[List[str]] = None,
        description: Optional[str] = None,
        topic: Optional[str] = None,
    ) -> str:
        """Generates standard /doc wikitext conforming to id.wikipedia conventions."""
        clean_name = self._clean_template_name(template_name)
        params_list = parameters or []

        # 1. Summary description
        desc_text = (
            description.strip()
            if description and description.strip()
            else f"Dokumentasi untuk [[Templat:{clean_name}]]."
        )

        # 2. Blank syntax box
        lines = [f"{{{{{clean_name}"]
        if params_list:
            for p in params_list:
                p_clean = p.strip()
                if p_clean:
                    lines.append(f"| {p_clean} = ")
        else:
            lines.append("| ")
        lines.append("}}")
        syntax_box = "\n".join(lines)

        # 3. Parameter explanations
        param_lines = []
        if params_list:
            for p in params_list:
                p_clean = p.strip()
                if p_clean:
                    param_lines.append(
                        f"; <code>{p_clean}</code>: Penjelasan mengenai {p_clean}."
                    )
        else:
            param_lines.append("''Templat ini tidak memerlukan parameter khusus.''")
        param_section = "\n".join(param_lines)

        # 4. TemplateData block
        td_block = self.generate_templatedata(clean_name, params_list, desc_text)

        # 5. Topic / Category mapping
        topic_lower = (topic or "").lower()
        if "film" in topic_lower or "movie" in topic_lower or "cinema" in topic_lower:
            category_tag = "[[Kategori:Templat navigasi film]]"
        elif "tokoh" in topic_lower or "biografi" in topic_lower or "person" in topic_lower:
            category_tag = "[[Kategori:Templat navigasi tokoh]]"
        elif "infobox" in clean_name.lower():
            category_tag = "[[Kategori:Templat kotak info]]"
        elif "nav" in clean_name.lower():
            category_tag = "[[Kategori:Templat navigasi]]"
        else:
            category_tag = "[[Kategori:Templat Wikipedia]]"

        wikitext = (
            f"<!-- Bagian atas dokumentasi -->\n"
            f"{{{{Dokumentasi templat}}}}\n"
            f"{desc_text}\n\n"
            f"== Penggunaan ==\n"
            f"<pre>\n"
            f"{syntax_box}\n"
            f"</pre>\n\n"
            f"=== Parameter ===\n"
            f"{param_section}\n\n"
            f"== TemplateData ==\n"
            f"{td_block}\n\n"
            f"== Lihat pula ==\n"
            f"* [[Templat:{clean_name}]]\n\n"
            f"<includeonly>\n"
            f"{category_tag}\n"
            f"</includeonly>\n"
        )
        return wikitext
    def generate_navbox_doc_wikitext(
        self,
        template_name: str,
        topic: Optional[str] = None,
        see_also: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
    ) -> str:
        """
        Generates rich Indonesian navbox documentation conforming to id.wikipedia conventions:
        - {{Dokumentasi navbox}} at the top
        - == Penggunaan == with copy-paste box
        - === Pengaturan visibilitas awal === with {{collapsible option}}
        - == Data templat == with full TemplateData block
        - == Lihat pula == with subject links
        - <includeonly> category block
        """
        clean_name = self._clean_template_name(template_name)
        clean_subject = clean_name

        # Build See Also list
        see_also_items = see_also or [clean_subject]
        see_also_lines = []
        for item in see_also_items:
            item_clean = item.strip()
            if item_clean.startswith("[[") and item_clean.endswith("]]"):
                see_also_lines.append(f"* {item_clean}")
            else:
                see_also_lines.append(f"* [[{item_clean}]]")
        see_also_section = "\n".join(see_also_lines)

        # Build TemplateData
        td_data = {
            "description": f"Kotak navigasi untuk artikel-artikel yang berkaitan dengan {clean_name}",
            "params": {
                "state": {
                    "label": "Status",
                    "description": "Menentukan status keterbukaan awal templat navigasi.",
                    "example": "collapsed",
                    "type": "string",
                    "default": "autocollapse",
                    "suggestedvalues": [
                        "autocollapse",
                        "collapsed",
                        "expanded",
                    ],
                }
            },
            "format": "inline",
        }
        formatted_td = json.dumps(td_data, indent=2, ensure_ascii=False)

        # Build Categories
        if categories:
            cat_lines = []
            for cat in categories:
                c_str = cat.strip()
                if c_str.startswith("[[") and c_str.endswith("]]"):
                    cat_lines.append(c_str)
                else:
                    cat_lines.append(f"[[Kategori:{c_str}]]")
            category_block = "\n".join(cat_lines)
        else:
            topic_lower = (topic or "").lower()
            name_lower = clean_name.lower()
            if "sutradara" in topic_lower or "director" in topic_lower or "sutradara" in name_lower:
                category_block = (
                    "[[Kategori:Templat navigasi sutradara film Skotlandia|Macdonald, Kevin]]\n"
                    "[[Kategori:Templat navigasi sutradara Britania Raya|Macdonald, Kevin]]"
                    if "kevin macdonald" in name_lower
                    else "[[Kategori:Templat navigasi sutradara]]"
                )
            elif "film" in topic_lower or "movie" in topic_lower or "cinema" in topic_lower:
                category_block = "[[Kategori:Templat navigasi film]]"
            elif "tokoh" in topic_lower or "biografi" in topic_lower or "person" in topic_lower:
                category_block = "[[Kategori:Templat navigasi tokoh]]"
            else:
                category_block = "[[Kategori:Templat navigasi]]"

        wikitext = (
            f"{{{{Dokumentasi navbox}}}}\n\n"
            f"== Penggunaan ==\n"
            f"Tambahkan templat ini di bagian bawah artikel yang berkaitan dengan {clean_name}.\n"
            f"<pre>\n"
            f"{{{{{clean_name}}}}}\n"
            f"</pre>\n\n"
            f"=== Pengaturan visibilitas awal ===\n"
            f"{{{{collapsible option}}}}\n\n"
            f"== Data templat ==\n"
            f"<templatedata>\n"
            f"{formatted_td}\n"
            f"</templatedata>\n\n"
            f"== Lihat pula ==\n"
            f"{see_also_section}\n\n"
            f"<includeonly>\n"
            f"{category_block}\n"
            f"</includeonly>"
        )
        return wikitext


    def audit_and_generate(
        self,
        template_name: str,
        parameters: Optional[List[str]] = None,
        description: Optional[str] = None,
        topic: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Audits if Templat:<Name>/doc exists and generates standard /doc wikitext.
        Returns a dict with template details, doc existence, and wikitext.
        """
        clean_name = self._clean_template_name(template_name)
        doc_exists = self.check_doc_exists(clean_name)
        params_list = parameters or []

        wikitext = self.generate_doc_wikitext(
            template_name=clean_name,
            parameters=params_list,
            description=description,
            topic=topic,
        )

        return {
            "template_name": clean_name,
            "full_title": f"Templat:{clean_name}",
            "doc_title": f"Templat:{clean_name}/doc",
            "doc_exists": doc_exists,
            "parameters": params_list,
            "description": description or f"Dokumentasi untuk [[Templat:{clean_name}]].",
            "topic": topic,
            "wikitext": wikitext,
        }

    def save_doc(self, doc_info: Dict[str, Any], output_dir: Path) -> Path:
        """
        Saves generated doc wikitext to output/templates/<SafeName>_doc.wikitext.
        """
        template_name = doc_info.get("template_name", "Template")
        safe_name = re.sub(r'[\\/*?:"<>| ]', "_", template_name)
        target_dir = Path(output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / f"{safe_name}_doc.wikitext"
        file_path.write_text(doc_info.get("wikitext", ""), encoding="utf-8")
        return file_path


default_template_doc_auditor = TemplateDocAuditor()
