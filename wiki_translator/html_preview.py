"""
Visual HTML Browser Preview generator for Indonesian Wikipedia drafts.

Renders wikitext into a standalone HTML file mimicking Indonesian Wikipedia's
Vector 2022 skin (typography, headers, infobox cards, references, notice banner).
"""

import html
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from typing import Optional

VECTOR_2022_CSS = """
:root {
    --font-family-serif: 'Linux Libertine', 'Georgia', 'Times', serif;
    --font-family-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Lato, Helvetica, Arial, sans-serif;
    --color-base: #202122;
    --color-emphasized: #000000;
    --color-subtle: #54595d;
    --color-link: #36c;
    --color-link-visited: #6b4ba1;
    --border-color-base: #a2a9b1;
    --border-color-subtle: #eaecf0;
    --bg-page: #f8f9fa;
    --bg-content: #ffffff;
}

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    padding: 0;
    background-color: var(--bg-page);
    color: var(--color-base);
    font-family: var(--font-family-sans);
    font-size: 15px;
    line-height: 1.6;
}

.mw-page-container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 24px 32px 64px 32px;
    background-color: var(--bg-content);
    min-height: 100vh;
    border-left: 1px solid var(--border-color-subtle);
    border-right: 1px solid var(--border-color-subtle);
}

.preview-notice-banner {
    background-color: #fef6e7;
    border: 1px solid #f0c36d;
    border-left: 6px solid #f09000;
    border-radius: 4px;
    padding: 12px 18px;
    margin-bottom: 24px;
    display: flex;
    align-items: center;
    gap: 12px;
}

.preview-notice-title {
    font-weight: bold;
    font-size: 15px;
    color: #723e0a;
}

.preview-notice-desc {
    font-size: 13px;
    color: #54595d;
    margin-top: 2px;
}

.firstHeading {
    font-family: var(--font-family-serif);
    font-size: 2.2rem;
    font-weight: normal;
    line-height: 1.3;
    margin-top: 0;
    margin-bottom: 0.25em;
    padding-bottom: 0.2em;
    border-bottom: 1px solid var(--border-color-base);
    color: var(--color-emphasized);
}

.siteSub {
    font-size: 13px;
    color: var(--color-subtle);
    margin-bottom: 20px;
}

.mw-parser-output h2 {
    font-family: var(--font-family-serif);
    font-size: 1.6rem;
    font-weight: normal;
    margin-top: 1.5em;
    margin-bottom: 0.3em;
    padding-bottom: 0.2em;
    border-bottom: 1px solid var(--border-color-base);
    color: var(--color-emphasized);
}

.mw-parser-output h3 {
    font-size: 1.25rem;
    font-weight: bold;
    margin-top: 1.2em;
    margin-bottom: 0.3em;
    color: var(--color-emphasized);
}

.mw-parser-output h4 {
    font-size: 1.1rem;
    font-weight: bold;
    margin-top: 1em;
    margin-bottom: 0.2em;
}

.mw-parser-output p {
    margin: 0.6em 0 1em 0;
}

.mw-parser-output ul, .mw-parser-output ol {
    margin: 0.6em 0 1em 2em;
    padding: 0;
}

.mw-parser-output li {
    margin-bottom: 0.3em;
}

a {
    color: var(--color-link);
    text-decoration: none;
}

a:hover {
    text-decoration: underline;
}

/* Vector 2022 Infobox */
.infobox {
    float: right;
    clear: right;
    margin: 0 0 1em 1.5em;
    border: 1px solid var(--border-color-base);
    background-color: #f8f9fa;
    color: var(--color-base);
    padding: 0.4em;
    width: 22em;
    max-width: 100%;
    font-size: 88%;
    line-height: 1.5;
    border-radius: 4px;
    border-spacing: 2px;
}

.infobox th, .infobox td {
    vertical-align: top;
    text-align: left;
    padding: 0.3em 0.5em;
}

.infobox th {
    font-weight: bold;
    background-color: #eaecf0;
}

.infobox .infobox-title {
    font-size: 125%;
    font-weight: bold;
    text-align: center;
    background-color: #eaf3ff;
    padding: 0.5em;
}

.infobox .infobox-image {
    text-align: center;
    padding: 0.5em;
}

.infobox-header {
    background-color: #dbeafe !important;
    text-align: center !important;
    font-weight: bold;
}

/* References block */
.mw-references-wrap {
    font-size: 90%;
    margin-top: 1.5em;
    border-top: 1px solid var(--border-color-subtle);
    padding-top: 1em;
}

.mw-references-wrap ol {
    padding-left: 2em;
}

sup.reference {
    font-size: 80%;
    line-height: 1;
    font-weight: normal;
}

sup.reference a {
    color: var(--color-link);
}

.vector-body {
    position: relative;
}

.clearfix::after {
    content: "";
    clear: both;
    display: table;
}
"""


class HTMLPreviewGenerator:
    """Generates visual HTML previews of Indonesian Wikipedia drafts."""

    API_URL = "https://id.wikipedia.org/w/api.php"
    USER_AGENT = "WikiTranslator/1.0 (Indonesian Wikipedia Grade A++ Draft Preview; contact@example.com)"

    def __init__(self, api_timeout: float = 3.0):
        self.api_timeout = api_timeout

    def render_html(self, title: str, wikitext: str, try_api_parse: bool = True) -> str:
        """
        Renders wikitext into a complete standalone HTML document mimicking Vector 2022.
        Tries online Action API parse first if try_api_parse is True (timeout: 3s).
        Falls back to built-in offline renderer cleanly formatting wikitext headers,
        lists, italics, bolds, wikilinks, references, and infobox tables.
        """
        html_body = None
        used_api = False

        if try_api_parse:
            html_body = self._try_api_parse(title, wikitext)
            if html_body is not None:
                used_api = True

        if html_body is None:
            html_body = self._render_offline(wikitext)

        return self._wrap_vector_template(title, html_body, is_api_parsed=used_api)

    def _try_api_parse(self, title: str, wikitext: str) -> Optional[str]:
        """Attempts to render wikitext using id.wikipedia.org action=parse."""
        try:
            params = {
                "action": "parse",
                "title": title,
                "text": wikitext,
                "contentmodel": "wikitext",
                "prop": "text",
                "disablelimitreport": "1",
                "format": "json",
            }
            data = urllib.parse.urlencode(params).encode("utf-8")
            req = urllib.request.Request(
                self.API_URL,
                data=data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": self.USER_AGENT,
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.api_timeout) as resp:
                if resp.status == 200:
                    payload = json.loads(resp.read().decode("utf-8"))
                    if "parse" in payload and "text" in payload["parse"]:
                        return payload["parse"]["text"].get("*", "")
        except Exception:
            return None
        return None

    def _render_offline(self, wikitext: str) -> str:
        """
        Robust offline wikitext renderer converting headers, infoboxes,
        formatting, lists, links, and references into clean HTML.
        """
        text = wikitext

        # 1. Extract <ref>...</ref> citations
        references = []

        def ref_sub(match: re.Match) -> str:
            content = match.group(1).strip()
            # Clean citation template inside ref e.g. {{cite web|...}}
            if content.startswith("{{") and content.endswith("}}"):
                # Extract basic params like title/url or simplify template
                content = self._simplify_template(content)
            references.append(content)
            idx = len(references)
            return f'<sup class="reference" id="cite_ref-{idx}"><a href="#cite_note-{idx}">[{idx}]</a></sup>'

        def self_ref_sub(match: re.Match) -> str:
            # Self-closing <ref name="..." />
            return ""

        text = re.sub(r"<ref[^>/]*>(.*?)</ref>", ref_sub, text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<ref[^>]*/>", self_ref_sub, text, flags=re.IGNORECASE)

        # 2. Extract and format Infoboxes: {{Infobox ...}} or {{Kotak info ...}}
        infobox_blocks = []
        text = self._extract_and_format_infoboxes(text, infobox_blocks)

        # 3. Strip or format remaining general templates
        text = self._format_templates(text)

        # 4. Strip comments <!-- ... -->
        text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)

        # 5. Format inline typography: bold and italics
        # '''''bold italic'''''
        text = re.sub(r"'''''(.*?)'''''", r"<strong><em>\1</em></strong>", text)
        # '''bold'''
        text = re.sub(r"'''(.*?)'''", r"<strong>\1</strong>", text)
        # ''italic''
        text = re.sub(r"''(.*?)''", r"<em>\1</em>", text)

        # 6. Wikilinks [[Target|Display]] or [[Target]]
        def link_sub(match: re.Match) -> str:
            target = match.group(1).strip()
            display = match.group(2).strip() if match.group(2) else target
            # Strip Category: or Kategori: prefixes
            if target.lower().startswith(("kategori:", "category:")):
                return ""
            # File/Berkas links
            if target.lower().startswith(("berkas:", "file:", "image:", "gambar:")):
                return f'<span class="mw-file-link">[Gambar: {display}]</span>'
            safe_target = urllib.parse.quote(target.replace(" ", "_"))
            href = f"https://id.wikipedia.org/wiki/{safe_target}"
            return f'<a href="{href}" title="{html.escape(target)}">{html.escape(display)}</a>'

        text = re.sub(r"\[\[([^|\]]+)(?:\|([^\]]+))?\]\]", link_sub, text)

        # 7. External links [URL Display] or [URL]
        def ext_link_sub(match: re.Match) -> str:
            url = match.group(1).strip()
            disp = match.group(2).strip() if match.group(2) else url
            return f'<a href="{html.escape(url)}" class="external" target="_blank" rel="noopener">{html.escape(disp)}</a>'

        text = re.sub(r"\[([a-zA-Z]+://[^\s\]]+)(?:\s+([^\]]+))?\]", ext_link_sub, text)

        # 8. Process line by line: headers, list items, paragraphs
        lines = text.split("\n")
        output_lines = []
        in_ul = False
        in_ol = False

        for line in lines:
            stripped = line.strip()

            # Close lists if line is not a list item
            if not stripped.startswith("*") and in_ul:
                output_lines.append("</ul>")
                in_ul = False
            if not stripped.startswith("#") and in_ol:
                output_lines.append("</ol>")
                in_ol = False

            if not stripped:
                continue

            # Headers
            h_match = re.match(r"^(={2,6})\s*(.*?)\s*\1$", stripped)
            if h_match:
                level = len(h_match.group(1))
                h_text = h_match.group(2).strip()
                output_lines.append(f"<h{level}>{h_text}</h{level}>")
                continue

            # Unordered list item
            if stripped.startswith("*"):
                if not in_ul:
                    output_lines.append("<ul>")
                    in_ul = True
                item_text = re.sub(r"^\*+\s*", "", stripped)
                output_lines.append(f"<li>{item_text}</li>")
                continue

            # Ordered list item
            if stripped.startswith("#"):
                if not in_ol:
                    output_lines.append("<ol>")
                    in_ol = True
                item_text = re.sub(r"^#+\s*", "", stripped)
                output_lines.append(f"<li>{item_text}</li>")
                continue

            # Regular paragraph
            output_lines.append(f"<p>{stripped}</p>")

        if in_ul:
            output_lines.append("</ul>")
        if in_ol:
            output_lines.append("</ol>")

        body_html = "\n".join(output_lines)

        # Prepend infoboxes
        if infobox_blocks:
            body_html = "\n".join(infobox_blocks) + "\n" + body_html

        # Append references section if references exist
        if references:
            ref_list_items = []
            for i, ref in enumerate(references, start=1):
                clean_ref = html.escape(ref)
                ref_list_items.append(
                    f'<li id="cite_note-{i}">'
                    f'<a href="#cite_ref-{i}">↑</a> {clean_ref}'
                    f'</li>'
                )
            refs_html = (
                '<div class="mw-references-wrap">'
                '<ol class="references">'
                + "".join(ref_list_items)
                + '</ol>'
                '</div>'
            )
            # If there's already a references header or placeholder, place it or append
            if "<h2 id=\"Referensi\">" in body_html or "<h2>Referensi</h2>" in body_html or "<h2>Rujukan</h2>" in body_html:
                # Append to bottom of document
                body_html += "\n" + refs_html
            else:
                body_html += '\n<h2>Referensi</h2>\n' + refs_html

        return body_html

    def _extract_and_format_infoboxes(self, text: str, out_blocks: list) -> str:
        """Finds Infobox or Kotak info templates and converts them into Vector infobox tables."""
        pattern = re.compile(r"\{\{\s*(?:Infobox|Kotak info|Kotakinfo)\b", re.IGNORECASE)

        while True:
            match = pattern.search(text)
            if not match:
                break
            start_pos = match.start()
            depth = 0
            end_pos = -1
            for i in range(start_pos, len(text)):
                if text[i : i + 2] == "{{":
                    depth += 1
                elif text[i : i + 2] == "}}":
                    depth -= 1
                    if depth == 0:
                        end_pos = i + 2
                        break

            if end_pos == -1:
                break

            infobox_raw = text[start_pos:end_pos]
            rendered_box = self._render_infobox_table(infobox_raw)
            out_blocks.append(rendered_box)
            # Remove infobox from wikitext
            text = text[:start_pos] + text[end_pos:]

        return text

    def _render_infobox_table(self, infobox_raw: str) -> str:
        """Parses an infobox template and generates an HTML table."""
        # Strip outer {{ and }}
        content = infobox_raw.strip()[2:-2].strip()
        lines = content.split("|")
        if not lines:
            return ""

        title = lines[0].strip()
        # Clean title
        title = re.sub(r"^(?:Infobox|Kotak info|Kotakinfo)\s*", "", title, flags=re.IGNORECASE)

        rows = []
        box_title = None

        for param in lines[1:]:
            if "=" not in param:
                continue
            k, v = param.split("=", 1)
            key = k.strip()
            val = v.strip()

            if not val or key.startswith("<!--"):
                continue

            if key.lower() in ("nama", "name", "title", "judul"):
                box_title = val
            else:
                # Basic cleaning of value
                clean_val = re.sub(r"\[\[(?:[^|\]]+\|)?([^\]]+)\]\]", r"\1", val)
                clean_val = re.sub(r"'''''(.*?)'''''", r"<strong><em>\1</em></strong>", clean_val)
                clean_val = re.sub(r"'''(.*?)'''", r"<strong>\1</strong>", clean_val)
                clean_val = re.sub(r"''(.*?)''", r"<em>\1</em>", clean_val)
                clean_key = key.replace("_", " ").title()
                rows.append(f"<tr><th>{html.escape(clean_key)}</th><td>{clean_val}</td></tr>")

        display_title = box_title or title or "Informasi"
        table_html = [
            '<table class="infobox">',
            f'<tr><th colspan="2" class="infobox-title">{html.escape(display_title)}</th></tr>',
        ]
        table_html.extend(rows)
        table_html.append("</table>")
        return "\n".join(table_html)

    def _simplify_template(self, tpl: str) -> str:
        """Simplifies complex citation/formatting templates for offline reference rendering."""
        inner = tpl.strip()[2:-2].strip()
        parts = inner.split("|")
        name = parts[0].strip().lower()

        if name.startswith("cite") or name.startswith("sitasi"):
            params = {}
            for p in parts[1:]:
                if "=" in p:
                    k, v = p.split("=", 1)
                    params[k.strip().lower()] = v.strip()
            title = params.get("title", params.get("judul", ""))
            url = params.get("url", "")
            publisher = params.get("publisher", params.get("work", params.get("penerbit", "")))
            date = params.get("date", params.get("tanggal", ""))

            summary_parts = []
            if title:
                summary_parts.append(f'"{title}"')
            if publisher:
                summary_parts.append(f"({publisher})")
            if date:
                summary_parts.append(f"[{date}]")
            if url:
                summary_parts.append(f"<{url}>")
            return " ".join(summary_parts) or inner

        return inner

    def _format_templates(self, text: str) -> str:
        """Strips or cleanly displays residual inline templates."""
        # Strip {{reflist}} or {{daftar referensi}}
        text = re.sub(r"\{\{\s*(reflist|daftar pustaka|referensi|rujukan)[^}]*\}\}", "", text, flags=re.IGNORECASE)
        # Strip {{DEFAULTSORT:...}}
        text = re.sub(r"\{\{DEFAULTSORT:[^}]+\}\}", "", text, flags=re.IGNORECASE)
        # Format {{lang|id|...}} -> ...
        text = re.sub(r"\{\{lang(?:-[a-z]+)?\|[^|]+\|([^}]+)\}\}", r"\1", text, flags=re.IGNORECASE)
        # General templates: {{X|Y}} -> Y if single argument, else remove
        def gen_sub(m: re.Match) -> str:
            inner = m.group(1).strip()
            parts = inner.split("|")
            if len(parts) == 2 and "=" not in parts[1]:
                return parts[1].strip()
            return ""
        text = re.sub(r"\{\{([^}]+)\}\}", gen_sub, text)
        return text

    def _wrap_vector_template(self, title: str, body_content: str, is_api_parsed: bool) -> str:
        """Wraps parsed HTML inside a full Vector 2022 responsive layout."""
        escaped_title = html.escape(title)
        mode_badge = "Online MediaWiki Parse" if is_api_parsed else "Offline Fallback Renderer"

        return f"""<!DOCTYPE html>
<html lang="id" dir="ltr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escaped_title} - Wikipedia Bahasa Indonesia</title>
    <style>
{VECTOR_2022_CSS}
    </style>
</head>
<body>
    <div class="mw-page-container">
        <!-- Indonesian Wikipedia Draft Preview Banner -->
        <div class="preview-notice-banner">
            <div>
                <div class="preview-notice-title">Pratinjau Draf Terjemahan Wikipedia Bahasa Indonesia</div>
                <div class="preview-notice-desc">
                    Halaman ini adalah pratinjau lokal draf terjemahan artikel Wikipedia bahasa Indonesia (Skin: Vector 2022 | Mode: {mode_badge}).
                </div>
            </div>
        </div>

        <header class="mw-header">
            <h1 id="firstHeading" class="firstHeading mw-first-heading">{escaped_title}</h1>
            <div id="siteSub" class="siteSub">Dari Wikipedia bahasa Indonesia, ensiklopedia bebas</div>
        </header>

        <main id="content" class="mw-body">
            <div id="bodyContent" class="vector-body clearfix">
                <div id="mw-content-text" class="mw-parser-output">
{body_content}
                </div>
            </div>
        </main>
    </div>
</body>
</html>
"""

    def save_and_open_preview(
        self,
        title: str,
        wikitext: str,
        output_dir: str = "output",
        auto_open: bool = False,
        try_api_parse: bool = True,
    ) -> Path:
        """
        Saves HTML preview to output/<safe_title>.preview.html and optionally opens in browser.
        """
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        # Generate clean safe filename slug
        slug = re.sub(r"[^\w\s-]", "", title).strip()
        safe_name = re.sub(r"[-\s]+", "_", slug).lower()
        preview_file = out_path / f"{safe_name}.preview.html"

        html_content = self.render_html(title=title, wikitext=wikitext, try_api_parse=try_api_parse)
        with open(preview_file, "w", encoding="utf-8") as f:
            f.write(html_content)

        if auto_open:
            file_url = preview_file.resolve().as_uri()
            webbrowser.open(file_url)

        return preview_file


default_preview_generator = HTMLPreviewGenerator()
