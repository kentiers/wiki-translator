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
from typing import Optional, Tuple

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


/* Standard Wikitable (Vector 2022) */
table.wikitable {
    background-color: #f8f9fa;
    color: #202122;
    margin: 1em 0;
    border: 1px solid #a2a9b1;
    border-collapse: collapse;
    font-size: 14px;
    line-height: 1.5;
    width: 100%;
}

table.wikitable > tr > th,
table.wikitable > tr > td,
table.wikitable > tbody > tr > th,
table.wikitable > tbody > tr > td {
    border: 1px solid #a2a9b1;
    padding: 0.5em 0.8em;
    vertical-align: middle;
}

table.wikitable > tr > th,
table.wikitable > tbody > tr > th {
    background-color: #eaecf0;
    text-align: left;
    font-weight: bold;
}

table.wikitable > caption {
    font-weight: bold;
    font-size: 95%;
    padding: 0.4em;
    text-align: center;
    caption-side: bottom;
    color: #54595d;
}

table.wikitable.sortable th {
    padding-right: 22px;
    position: relative;
}

table.wikitable.sortable th::after {
    content: " ⇕";
    font-size: 0.85em;
    color: #72777d;
    position: absolute;
    right: 6px;
    top: 50%;
    transform: translateY(-50%);
}

table.wikitable tr:hover {
    background-color: #f1f3f5;
}
/* Hatnotes (Vector 2022) */
.hatnote {
    font-style: italic;
    color: #54595d;
    padding-left: 1.6em;
    margin: 0.5em 0 1em 0;
    font-size: 13.5px;
    background: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 20 20"><path fill="%2354595d" d="M19 10l-7-7v4H1v6h11v4z"/></svg>') no-repeat left center;
    background-size: 13px;
}

.hatnote a {
    color: var(--color-link);
    text-decoration: none;
}

.hatnote a:hover {
    text-decoration: underline;
}

/* Sister project box */
.sister-project-box {
    float: right;
    clear: right;
    margin: 0 0 1em 1em;
    padding: 10px 14px;
    background: #f8f9fa;
    border: 1px solid #c8ccd1;
    border-radius: 4px;
    font-size: 13px;
    max-width: 320px;
    line-height: 1.4;
    box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}

/* Succession table */
table.succession-table {
    margin: 1.5em auto;
    font-size: 13px;
    width: 100%;
    max-width: 900px;
    border-collapse: collapse;
}

table.succession-table td {
    padding: 8px 12px;
}
/* References block (Vector 2022 2-column responsive layout) */
.mw-references-wrap {
    font-size: 90%;
    margin-top: 1em;
    margin-bottom: 1.5em;
}

.references-2column ol.references, .mw-references-columns ol.references {
    column-width: 30em;
    -webkit-column-width: 30em;
    -moz-column-width: 30em;
    margin-top: 0.3em;
}

ol.references {
    list-style-type: decimal;
    padding-left: 2em;
    margin-bottom: 0.5em;
}

ol.references li {
    margin-bottom: 0.5em;
    padding-left: 0.2em;
    break-inside: avoid-column;
    -webkit-column-break-inside: avoid;
    word-wrap: break-word;
}

.mw-cite-backlink {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 85%;
    font-weight: bold;
    margin-right: 4px;
}

.mw-cite-backlink a {
    color: var(--color-link);
    text-decoration: none;
    margin-right: 2px;
}

.mw-cite-backlink a:hover {
    text-decoration: underline;
}

.reference-text {
    color: var(--color-base);
}

sup.reference {
    font-size: 80%;
    line-height: 1;
    font-weight: normal;
    padding-left: 1px;
}

sup.reference a {
    color: var(--color-link);
    text-decoration: none;
}

sup.reference a:hover {
    text-decoration: underline;
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
        # 1. Global <ref> citation parsing & grouping (MediaWiki Cite extension)
        ref_pattern = re.compile(r"<ref\b([^>/]*)(?:>(.*?)</ref>|/>)", re.DOTALL | re.IGNORECASE)
        ordered_refs = []
        named_refs = {}
        ref_matches = []

        for m in ref_pattern.finditer(text):
            attr_str = m.group(1) or ""
            content = (m.group(2) or "").strip()
            name_m = re.search(r"name\s*=\s*(?:\"([^\"]+)\"|'([^']+)'|([^\s/>]+))", attr_str)
            name = (name_m.group(1) or name_m.group(2) or name_m.group(3)) if name_m else None

            if name:
                if name not in named_refs:
                    ref_num = len(ordered_refs) + 1
                    ref_data = {
                        "num": ref_num,
                        "name": name,
                        "content": self._clean_ref_content(content) if content else "",
                        "citations": [0],
                    }
                    named_refs[name] = ref_data
                    ordered_refs.append(ref_data)
                else:
                    if content and not named_refs[name]["content"]:
                        named_refs[name]["content"] = self._clean_ref_content(content)
                    named_refs[name]["citations"].append(len(named_refs[name]["citations"]))
                ref_matches.append((m, named_refs[name]["num"]))
            else:
                ref_num = len(ordered_refs) + 1
                ref_data = {
                    "num": ref_num,
                    "name": None,
                    "content": self._clean_ref_content(content) if content else "",
                    "citations": [0],
                }
                ordered_refs.append(ref_data)
                ref_matches.append((m, ref_num))

        # Reconstruct text replacing <ref> tags with proper anchors
        cite_counters = {}
        pos = 0
        ref_text_parts = []
        for m, ref_num in ref_matches:
            ref_text_parts.append(text[pos:m.start()])
            ref_data = ordered_refs[ref_num - 1]
            total_cites = len(ref_data["citations"])
            k = cite_counters.get(ref_num, 0)
            cite_counters[ref_num] = k + 1

            if total_cites == 1:
                anchor_id = f"cite_ref-{ref_num}"
            else:
                anchor_id = f"cite_ref-{ref_num}_{k}"
            ref_text_parts.append(f'<sup class="reference" id="{anchor_id}"><a href="#cite_note-{ref_num}">[{ref_num}]</a></sup>')
            pos = m.end()

        ref_text_parts.append(text[pos:])
        text = "".join(ref_text_parts)

        # 2. Extract notes (Family name footnote & Efn) sequentially from top to bottom
        efn_notes = []
        fn_regex = re.compile(
            r"\{\{\s*(?:Family name footnote|Eastern Slavic name|Slavic name|efn\b|efn-lr\b)",
            re.IGNORECASE,
        )

        pos = 0
        reconstructed_text = []

        while pos < len(text):
            m = fn_regex.search(text, pos)
            if not m:
                reconstructed_text.append(text[pos:])
                break

            reconstructed_text.append(text[pos:m.start()])

            start_pos = m.start()
            depth = 0
            end_pos = -1
            for p_idx in range(start_pos, len(text) - 1):
                if text[p_idx : p_idx + 2] == "{{":
                    depth += 1
                elif text[p_idx : p_idx + 2] == "}}":
                    depth -= 1
                    if depth == 0:
                        end_pos = p_idx + 2
                        break

            if end_pos == -1:
                reconstructed_text.append(m.group(0))
                pos = m.end()
                continue

            tpl_raw = text[start_pos:end_pos]
            if tpl_raw.lower().startswith(("{{family name", "{{eastern slavic", "{{slavic name")):
                inner = tpl_raw[2:-2].strip()
                parts = []
                cur = []
                d = 0
                for ch in inner:
                    if ch in "{[":
                        d += 1
                    elif ch in "}]":
                        d -= 1
                    if ch == "|" and d == 0:
                        parts.append("".join(cur).strip())
                        cur = []
                    else:
                        cur.append(ch)
                if cur:
                    parts.append("".join(cur).strip())

                patronymic = parts[1] if len(parts) > 1 and "=" not in parts[1] else ""
                family = parts[2] if len(parts) > 2 and "=" not in parts[2] else ""

                # Format family if ill or wikilink
                ill_m = re.match(r"\{\{ill\|([^|}]+)\|([a-z]{2,3})\|([^|}]+)(.*?)\}\}", family, re.I)
                if ill_m:
                    id_t, lang, foreign = ill_m.group(1), ill_m.group(2), ill_m.group(3)
                    family_html = f'{html.escape(id_t)} <a href="https://{lang}.wikipedia.org/wiki/{foreign}" class="extiw" target="_blank" rel="noopener">[{lang}]</a>'
                elif re.match(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", family):
                    wl_m = re.match(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", family)
                    target_w, label_w = wl_m.group(1), wl_m.group(2) or wl_m.group(1)
                    family_html = f'<a href="https://id.wikipedia.org/wiki/{target_w}">{html.escape(label_w)}</a>'
                else:
                    family_html = html.escape(family)

                note_text = (
                    f'Dalam nama yang mengikuti <a href="https://id.wikipedia.org/wiki/Sistem_penamaan_Slavik_Timur">kebiasaan penamaan Slavik Timur</a> ini, '
                    f'nama patronimiknya adalah <em>{html.escape(patronymic)}</em> dan nama keluarganya adalah <em>{family_html}</em>.'
                )
                efn_notes.append(note_text)
                idx = len(efn_notes)
                letter = chr(96 + idx)
                reconstructed_text.append(f'<sup class="reference" id="cite_ref-efn-{letter}"><a href="#cite_note-efn-{letter}">[{letter}]</a></sup>')
                pos = end_pos
            else:
                raw_efn = text[start_pos:end_pos]
                content = raw_efn[2:-2].strip()
                content = re.sub(r"^[Ee]fn\s*\|\s*", "", content)
                content = re.sub(r"^name\s*=\s*(?:\"[^\"]*\"|\'[^\']*\'|[^\s|]+)\s*\|\s*", "", content)
                efn_notes.append(content)
                idx = len(efn_notes)
                letter = chr(96 + idx)
                reconstructed_text.append(f'<sup class="reference" id="cite_ref-efn-{letter}"><a href="#cite_note-efn-{letter}">[{letter}]</a></sup>')
                pos = end_pos

        text = "".join(reconstructed_text)
        # 2. Extract and format Infoboxes: {{Infobox ...}} or {{Kotak info ...}}
        infobox_blocks = []
        text = self._extract_and_format_infoboxes(text, infobox_blocks)

        # 2.5 Extract and format Wikitext tables / notice boxes: {| ... |}
        text = self._extract_and_format_tables(text)
        # 2.8 Format Multiple image templates: {{Multiple image ...}}
        text = self._format_multiple_images(text)
        # 2.9 Format Single File / Berkas image links: [[File:...]] or [[Berkas:...]]
        text = self._format_single_images(text)
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
                item_text = re.sub(r"^\*+\s*", "", stripped).strip()
                if not item_text:
                    continue
                if not in_ul:
                    output_lines.append("<ul>")
                    in_ul = True
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
            # HTML block elements (do not wrap in <p>)
            if stripped.startswith(("<div", "</div", "<table", "</table", "<caption", "</caption", "<thead", "</thead", "<tbody", "</tbody", "<tr", "</tr", "<td", "<th", "<blockquote", "</blockquote")):
                output_lines.append(stripped)
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

        # Inject explanatory notes (Catatan)
        if efn_notes:
            notes_items = []
            for i, note in enumerate(efn_notes, start=1):
                letter = chr(96 + i)
                clean_note = re.sub(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", "", note)
                def note_link(m: re.Match) -> str:
                    t = m.group(1).strip()
                    d = m.group(2).strip() if m.group(2) else t
                    safe_href = urllib.parse.quote(t.replace(" ", "_"))
                    return f'<a href="https://id.wikipedia.org/wiki/{safe_href}">{html.escape(d)}</a>'
                clean_note = re.sub(r"\[\[([^|\]]+)(?:\|([^\]]+))?\]\]", note_link, clean_note)
                clean_note = re.sub(r"'''(.*?)'''", r"<strong>\1</strong>", clean_note)
                clean_note = re.sub(r"''(.*?)''", r"<em>\1</em>", clean_note)
                notes_items.append(
                    f'<li id="cite_note-efn-{letter}">'
                    f'<span class="mw-cite-backlink"><a href="#cite_ref-efn-{letter}">^</a></span> {clean_note}'
                    f'</li>'
                )
            notes_html = (
                '<div class="mw-references-wrap">'
                '<ol class="references" style="list-style-type: lower-alpha;">'
                + "".join(notes_items)
                + '</ol>'
                '</div>'
            )
            if "<!-- NOTELIST_PLACEHOLDER -->" in body_html:
                body_html = body_html.replace("<!-- NOTELIST_PLACEHOLDER -->", notes_html, 1)
            else:
                catatan_pattern = re.compile(r"(<h2\b[^>]*>Catatan</h2>)", re.IGNORECASE)
                if catatan_pattern.search(body_html):
                    body_html = catatan_pattern.sub(r"\1\n" + notes_html, body_html, count=1)
        # Inject references (Referensi) in Vector 2022 2-column layout
        if ordered_refs:
            ref_list_items = []
            for r in ordered_refs:
                num = r["num"]
                cites = r["citations"]
                if len(cites) == 1:
                    backlink = f'<span class="mw-cite-backlink"><a href="#cite_ref-{num}">^</a></span>'
                else:
                    letters = []
                    for k in range(len(cites)):
                        if k < 26:
                            let_str = chr(97 + k)
                        else:
                            let_str = chr(97 + (k // 26) - 1) + chr(97 + (k % 26))
                        letters.append(f'<a href="#cite_ref-{num}_{k}"><sup><em>{let_str}</em></sup></a>')
                    backlink = f'<span class="mw-cite-backlink">^ {" ".join(letters)}</span>'

                ref_body = r["content"] or "Rujukan tanpa rincian sitasi."
                ref_list_items.append(
                    f'<li id="cite_note-{num}">'
                    f'{backlink} <span class="reference-text">{ref_body}</span>'
                    f'</li>'
                )
            refs_html = (
                '<div class="mw-references-wrap references-2column">'
                '<ol class="references">'
                + "".join(ref_list_items)
                + '</ol>'
                '</div>'
            )
            if "<!-- REFLIST_PLACEHOLDER -->" in body_html:
                body_html = body_html.replace("<!-- REFLIST_PLACEHOLDER -->", refs_html, 1)
            else:
                kutipan_pattern = re.compile(r"(<h3\b[^>]*>(?:Kutipan|Catatan kaki)</h3>)", re.IGNORECASE)
                if kutipan_pattern.search(body_html):
                    body_html = kutipan_pattern.sub(r"\1\n" + refs_html, body_html, count=1)
                else:
                    ref_header_pattern = re.compile(r"(<h2\b[^>]*>(?:Referensi|Rujukan)</h2>)", re.IGNORECASE)
                    if ref_header_pattern.search(body_html):
                        body_html = ref_header_pattern.sub(r"\1\n" + refs_html, body_html, count=1)
                    else:
                        body_html += '\n<h2>Referensi</h2>\n' + refs_html
        return body_html
    def _format_multiple_images(self, text: str) -> str:
        """Formats {{Multiple image}} into responsive Wikimedia-style thumbnail containers."""
        pat = re.compile(r"\{\{\s*Multiple[ _]image\b([\s\S]*?)\}\}", re.IGNORECASE)

        def repl(m: re.Match) -> str:
            content = m.group(1).strip()
            parts = []
            cur = []
            d = 0
            for ch in content:
                if ch in "{[":
                    d += 1
                elif ch in "}]":
                    d -= 1
                if ch == "|" and d == 0:
                    parts.append("".join(cur).strip())
                    cur = []
                else:
                    cur.append(ch)
            if cur:
                parts.append("".join(cur).strip())

            params = {}
            for p in parts:
                if "=" in p:
                    k, v = p.split("=", 1)
                    params[k.strip().lower()] = v.strip()

            images = []
            for i in range(1, 10):
                img_k = f"image{i}"
                if img_k in params and params[img_k]:
                    images.append((
                        params[img_k],
                        params.get(f"caption{i}", ""),
                        params.get(f"alt{i}", ""),
                    ))

            if not images:
                return ""

            footer = params.get("footer", params.get("keterangan", ""))
            footer_html = re.sub(
                r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]",
                lambda lm: f'<a href="https://id.wikipedia.org/wiki/{lm.group(1)}">{lm.group(2) or lm.group(1)}</a>',
                footer,
            )

            width = params.get("total_width", params.get("width", "320"))

            box_lines = [
                f'<div class="thumb tmulti tright" style="width:{width}px; float:right; margin:0.5em 0 1em 1em; padding:4px; border:1px solid #c8ccd1; background:#f8f9fa;">',
                '<div class="thumbinner" style="display:flex; flex-direction:row; gap:4px; justify-content:center;">',
            ]
            for img, cap, alt in images:
                clean_img = img.strip()
                if clean_img.lower().startswith(("file:", "berkas:")):
                    clean_img = clean_img.split(":", 1)[1].strip()
                escaped_img = urllib.parse.quote(clean_img.replace(" ", "_"), safe="()-_.")
                box_lines.append(
                    f'<div style="flex:1; text-align:center;">'
                    f'<img src="https://commons.wikimedia.org/wiki/Special:FilePath/{escaped_img}?width=220" alt="{html.escape(alt)}" style="max-width:100%; height:auto; display:block; margin:auto;">'
                )
                if cap:
                    box_lines.append(f'<div style="font-size:12px; color:#54595d; margin-top:2px;">{html.escape(cap)}</div>')
                box_lines.append('</div>')
            box_lines.append('</div>')
            if footer_html:
                box_lines.append(f'<div class="thumbcaption" style="font-size:12px; color:#202122; margin-top:4px; line-height:1.4;">{footer_html}</div>')
            box_lines.append('</div>')
            return "\n".join(box_lines)

        return pat.sub(repl, text)
    def _format_single_images(self, text: str) -> str:
        """Formats [[File:...]] and [[Berkas:...]] into standard Wikimedia thumbnail containers."""
        def parse_balanced_file(s: str, start_pos: int) -> Tuple[Optional[str], int]:
            depth = 0
            for i in range(start_pos, len(s) - 1):
                if s[i : i + 2] == "[[":
                    depth += 1
                elif s[i : i + 2] == "]]":
                    depth -= 1
                    if depth == 0:
                        return s[start_pos : i + 2], i + 2
            return None, start_pos

        file_re = re.compile(r"\[\[\s*(?:File|Berkas|Image|Gambar)\s*:", re.IGNORECASE)
        pos = 0
        out = []
        while pos < len(text):
            m = file_re.search(text, pos)
            if not m:
                out.append(text[pos:])
                break
            out.append(text[pos : m.start()])
            raw_file, end_pos = parse_balanced_file(text, m.start())
            if not raw_file:
                out.append(text[m.start() : m.end()])
                pos = m.end()
                continue

            inner = raw_file[2:-2].strip()
            parts = []
            cur = []
            d = 0
            for ch in inner:
                if ch in "{[":
                    d += 1
                elif ch in "}]":
                    d -= 1
                if ch == "|" and d == 0:
                    parts.append("".join(cur).strip())
                    cur = []
                else:
                    cur.append(ch)
            if cur:
                parts.append("".join(cur).strip())

            if not parts:
                pos = end_pos
                continue

            filename = parts[0].split(":", 1)[1].strip()
            caption = ""
            alt = ""
            align = "right"
            width = "220"

            for p in parts[1:]:
                p_low = p.lower()
                if p_low in ("thumb", "thumbnail", "jempolan"):
                    pass
                elif p_low in ("right", "kanan"):
                    align = "right"
                elif p_low in ("left", "kiri"):
                    align = "left"
                elif p_low in ("center", "tengah"):
                    align = "center"
                elif p_low.startswith("alt="):
                    alt = p[4:].strip()
                elif re.match(r"^\d+px$", p_low):
                    width = p_low[:-2]
                elif p_low.startswith("upright"):
                    width = "220"
                else:
                    caption = p

            escaped_file = urllib.parse.quote(filename.replace(" ", "_"), safe="()-_.")
            caption_html = re.sub(
                r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]",
                lambda lm: f'<a href="https://id.wikipedia.org/wiki/{lm.group(1)}">{lm.group(2) or lm.group(1)}</a>',
                caption,
            )
            align_css = f"float:{align}; margin:0.5em 0 1em 1em;" if align == "right" else f"float:{align}; margin:0.5em 1em 1em 0;"

            out.append(
                f'<div class="thumb t{align}" style="width:{width}px; {align_css} padding:4px; border:1px solid #c8ccd1; background:#f8f9fa;">'
                f'<div class="thumbinner" style="text-align:center;">'
                f'<img src="https://commons.wikimedia.org/wiki/Special:FilePath/{escaped_file}?width=240" alt="{html.escape(alt)}" style="max-width:100%; height:auto; display:block; margin:auto;">'
                f'<div class="thumbcaption" style="font-size:12px; color:#202122; margin-top:4px; line-height:1.4; text-align:left;">{caption_html}</div>'
                f'</div></div>'
            )
            pos = end_pos

        return "".join(out)


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
            i = start_pos
            while i < len(text):
                if text[i : i + 2] == "{{":
                    depth += 1
                    i += 2
                elif text[i : i + 2] == "}}":
                    depth -= 1
                    if depth == 0:
                        end_pos = i + 2
                        break
                    i += 2
                else:
                    i += 1

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
        content = infobox_raw.strip()[2:-2].strip()

        # Split top-level parameters respecting nested {{...}} and [[...]]
        parts = []
        cur = []
        d_brace = 0
        d_bracket = 0
        i = 0
        while i < len(content):
            if content[i : i + 2] == "{{":
                d_brace += 1
                cur.append(content[i : i + 2])
                i += 2
            elif content[i : i + 2] == "}}":
                d_brace = max(0, d_brace - 1)
                cur.append(content[i : i + 2])
                i += 2
            elif content[i : i + 2] == "[[":
                d_bracket += 1
                cur.append(content[i : i + 2])
                i += 2
            elif content[i : i + 2] == "]]":
                d_bracket = max(0, d_bracket - 1)
                cur.append(content[i : i + 2])
                i += 2
            elif content[i] == "|" and d_brace == 0 and d_bracket == 0:
                parts.append("".join(cur).strip())
                cur = []
                i += 1
            else:
                cur.append(content[i])
                i += 1
        if cur:
            parts.append("".join(cur).strip())

        if not parts:
            return ""

        title = parts[0].strip()
        title = re.sub(r"^(?:Infobox|Kotak info|Kotakinfo)\s*", "", title, flags=re.IGNORECASE)

        rows = []
        box_title = None

        for param in parts[1:]:
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
                # Clean up nested templates
                val = re.sub(r"\{\{nobold\|([^}]+)\}\}", r"\1", val, flags=re.I)
                val = re.sub(r"\{\{marriage\|([^|]+)\|([^|]+)\|([^|]+)(?:\|[^}]+)?\}\}", r"\1 (m. \2; w. \3)", val, flags=re.I)
                val = re.sub(r"\{\{ill\|([^|]+)(?:\|[^}]+)*\}\}", r"\1", val, flags=re.I)
                val = re.sub(r"\{\{small\|([^}]+)\}\}", r"<small>\1</small>", val, flags=re.I)
                val = re.sub(r"\{\{resmi\|([^}]+)\}\}", r'<a href="\1" class="external" target="_blank" rel="noopener">\1</a>', val, flags=re.I)
                # Wikilinks
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
    def _extract_and_format_tables(self, text: str) -> str:
        """Converts wikitext tables ({| ... |}) into styled HTML tables or notice cards."""
        table_pattern = re.compile(r"\{\|[^\n]*\n([\s\S]*?)\|\}", re.MULTILINE)

        def clean_cell_markup(raw_cell: str) -> Tuple[str, str]:
            raw_cell = raw_cell.strip()
            attr = ""
            content = raw_cell
            if "|" in raw_cell:
                parts = raw_cell.split("|", 1)
                if re.match(r"^\s*(?:style|class|scope|width|colspan|rowspan|align|valign|bgcolor)\s*=", parts[0], re.I):
                    attr = " " + parts[0].strip()
                    content = parts[1].strip()
            content = re.sub(r"\[\[([^|\]]+)\|([^\]]+)\]\]", r'<a href="https://id.wikipedia.org/wiki/\1">\2</a>', content)
            content = re.sub(r"\[\[([^|\]]+)\]\]", r'<a href="https://id.wikipedia.org/wiki/\1">\1</a>', content)
            content = re.sub(r"'''''(.*?)'''''", r"<strong><em>\1</em></strong>", content)
            content = re.sub(r"'''(.*?)'''", r"<strong>\1</strong>", content)
            content = re.sub(r"''(.*?)''", r"<em>\1</em>", content)
            content = re.sub(r"\{\{ISBN\|([^}]+)\}\}", r"ISBN \1", content)
            return attr, content

        def table_replacer(match: re.Match) -> str:
            raw_table = match.group(0)
            inner = match.group(1).strip()

            # Special case: Review / draft notice banner
            if "Draf perbaikan" in inner or "ℹ️" in inner:
                msg = re.sub(r"^\|\s*", "", inner, flags=re.MULTILINE).strip()
                return (
                    '<div class="preview-notice-banner" style="background:#f0f4f8; border:1px solid #c8ccd1; border-left:5px solid #36c; padding:12px 18px; border-radius:4px; margin-bottom:20px;">'
                    f"{msg}"
                    "</div>\n"
                )

            # General Wikitable parser
            header_line = raw_table.split("\n", 1)[0]
            table_classes = ["wikitable"]
            if "sortable" in header_line.lower():
                table_classes.append("sortable")

            caption_html = ""
            rows_html = []
            cur_row = []

            for line in inner.splitlines():
                line = line.strip()
                if not line or line == "|}" or line.startswith("|}"):
                    continue

                if line.startswith("|+"):
                    cap_text = line[2:].strip()
                    if "|" in cap_text:
                        parts = cap_text.split("|", 1)
                        if any(k in parts[0].lower() for k in ["align=", "style="]):
                            cap_text = parts[1].strip()
                    _, cap_clean = clean_cell_markup(cap_text)
                    caption_html = f"<caption>{cap_clean}</caption>\n"
                    continue

                if line.startswith("|-"):
                    if cur_row:
                        rows_html.append("<tr>" + "".join(cur_row) + "</tr>\n")
                        cur_row = []
                    continue

                if line.startswith("!"):
                    content = line[1:].strip()
                    cells = re.split(r"\s*!!\s*|\s*!(?![^\[]*\]\])(?![^{]*\}\})\s*", content)
                    for c in cells:
                        if c.strip():
                            attr, c_clean = clean_cell_markup(c)
                            cur_row.append(f"<th{attr}>{c_clean}</th>")
                    continue

                if line.startswith("|"):
                    content = line[1:].strip()
                    cells = re.split(r"\s*\|\|\s*", content)
                    for c in cells:
                        attr, c_clean = clean_cell_markup(c)
                        cur_row.append(f"<td{attr}>{c_clean}</td>")
                    continue

            if cur_row:
                rows_html.append("<tr>" + "".join(cur_row) + "</tr>\n")

            cls_str = " ".join(table_classes)
            return f'<table class="{cls_str}">\n{caption_html}' + "".join(rows_html) + "</table>\n"

        return table_pattern.sub(table_replacer, text)
    def _clean_ref_content(self, content: str) -> str:
        """Processes reference content, formatting citation templates or preserving plain text."""
        trimmed = content.strip()
        if trimmed.startswith("{{") and trimmed.endswith("}}"):
            return self._simplify_template(trimmed)
        return trimmed

    def _simplify_template(self, tpl: str) -> str:
        """Simplifies complex citation/formatting templates for offline reference rendering."""
        clean_tpl = tpl.strip()
        if not (clean_tpl.startswith("{{") and clean_tpl.endswith("}}")):
            return clean_tpl
        inner = clean_tpl[2:-2].strip()
        parts = inner.split("|")
        name = parts[0].strip().lower()

        if name.startswith(("cite", "sitasi")):
            params = {}
            for p in parts[1:]:
                if "=" in p:
                    k, v = p.split("=", 1)
                    params[k.strip().lower()] = v.strip()

            # Authors
            authors = []
            last1 = params.get("last", params.get("last1", params.get("penulis", "")))
            first1 = params.get("first", params.get("first1", ""))
            if last1:
                authors.append(f"{last1}, {first1}" if first1 else last1)
            last2 = params.get("last2", "")
            first2 = params.get("first2", "")
            if last2:
                authors.append(f"{last2}, {first2}" if first2 else last2)
            last3 = params.get("last3", "")
            first3 = params.get("first3", "")
            if last3:
                authors.append(f"{last3}, {first3}" if first3 else last3)
            author_str = "; ".join(authors)

            year = params.get("year", params.get("date", params.get("tahun", "")))
            chapter = params.get("chapter", params.get("bab", ""))
            title = params.get("title", params.get("judul", ""))
            journal = params.get("journal", params.get("jurnal", ""))
            publisher = params.get("publisher", params.get("work", params.get("penerbit", "")))
            location = params.get("location", params.get("tempat", ""))
            pages = params.get("pages", params.get("page", params.get("halaman", "")))
            isbn = params.get("isbn", "")
            url = params.get("url", "")

            # Editors
            ed_last = params.get("editor-last", params.get("editor-last1", ""))
            ed_first = params.get("editor-first", params.get("editor-first1", ""))
            editor_str = f"{ed_last}, {ed_first} (ed.)" if ed_last else ""

            res_parts = []
            if author_str:
                res_parts.append(html.escape(author_str))
            if year:
                clean_yr = re.search(r"\b\d{4}\b", year)
                res_parts.append(f"({clean_yr.group(0) if clean_yr else html.escape(year)}).")

            if chapter:
                res_parts.append(f'"{html.escape(chapter)}".')
                if editor_str:
                    res_parts.append(f"In {html.escape(editor_str)},")
                if title:
                    if url:
                        res_parts.append(f'<em><a href="{html.escape(url)}" class="external" target="_blank" rel="noopener">{html.escape(title)}</a></em>.')
                    else:
                        res_parts.append(f'<em>{html.escape(title)}</em>.')
            elif title:
                if url:
                    res_parts.append(f'<em><a href="{html.escape(url)}" class="external" target="_blank" rel="noopener">{html.escape(title)}</a></em>.')
                else:
                    res_parts.append(f'<em>{html.escape(title)}</em>.')

            if journal:
                res_parts.append(f'<em>{html.escape(journal)}</em>.')
            if location and publisher:
                res_parts.append(f"{html.escape(location)}: {html.escape(publisher)}.")
            elif publisher:
                res_parts.append(f"{html.escape(publisher)}.")

            if pages:
                norm_pages = re.sub(r"(\d+)\s*[-–]\s*(\d+)", r"\1–\2", pages)
                res_parts.append(f"pp. {html.escape(norm_pages)}.")
            if isbn:
                res_parts.append(f'ISBN <a href="https://id.wikipedia.org/wiki/Istimewa:Sumber_buku/{isbn}" class="external">{html.escape(isbn)}</a>.')

            return " ".join(res_parts) or inner

        return inner

    def _format_templates(self, text: str) -> str:
        """Strips or cleanly displays residual inline templates."""
        # Convert {{notelist}} or {{daftar catatan}} to placeholder
        text = re.sub(r"\{\{\s*(?:notelist|daftar catatan|efn-lr)[^}]*\}\}", "<!-- NOTELIST_PLACEHOLDER -->", text, flags=re.IGNORECASE)
        # Convert {{reflist}} or {{daftar referensi}} to placeholder
        text = re.sub(r"\{\{\s*(reflist|daftar pustaka|referensi|rujukan)[^}]*\}\}", "<!-- REFLIST_PLACEHOLDER -->", text, flags=re.IGNORECASE)
        # Handle {{refbegin}} and {{refend}}
        text = re.sub(r"\{\{\s*refbegin[^}]*\}\}", '<div class="mw-references-wrap references-2column" style="column-width: 30em; margin-top: 0.5em;">', text, flags=re.IGNORECASE)
        text = re.sub(r"\{\{\s*refend\s*\}\}", "</div>", text, flags=re.IGNORECASE)

        # Handle Hatnotes: {{See also|...}}, {{Lihat pula|...}}, {{Utama|...}}, {{Main|...}}
        def hatnote_sub(m: re.Match) -> str:
            tpl_name = m.group(1).lower().strip()
            inner = m.group(2).strip()
            links = []
            for p in inner.split("|"):
                p_clean = p.strip()
                if p_clean and not "=" in p_clean:
                    href = f"https://id.wikipedia.org/wiki/{urllib.parse.quote(p_clean.replace(' ', '_'))}"
                    links.append(f'<a href="{href}">{html.escape(p_clean)}</a>')
            label = "Artikel utama:" if tpl_name in ["utama", "main"] else "Lihat pula:"
            links_str = ", ".join(links) or inner
            return f'<div class="hatnote navigation-not-searchable">{label} {links_str}</div>'
        text = re.sub(r"\{\{\s*(See also|Lihat pula|Utama|Main)\s*\|([^}]+)\}\}", hatnote_sub, text, flags=re.IGNORECASE)

        # Handle sister project callouts: {{wikiquote|...}}, {{commonscat|...}}, {{commons|...}}
        def sister_sub(m: re.Match) -> str:
            name = m.group(1).lower().strip()
            val = m.group(2).strip() if m.group(2) else ""
            clean_val = val.split("|")[0].strip()
            if "commonscat" in name or "commons" in name:
                url = f"https://commons.wikimedia.org/wiki/Category:{clean_val.replace(' ', '_')}"
                return (
                    f'<div class="sister-project-box">'
                    f'📁 <strong>Wikimedia Commons</strong> memiliki galeri mengenai <a href="{url}" class="external" target="_blank" rel="noopener"><em>{html.escape(clean_val)}</em></a>.'
                    f'</div>'
                )
            elif "wikiquote" in name:
                url = f"https://id.wikiquote.org/wiki/{clean_val.replace(' ', '_')}"
                return (
                    f'<div class="sister-project-box">'
                    f'💬 <strong>Wikikutip</strong> memiliki koleksi kutipan mengenai <a href="{url}" class="external" target="_blank" rel="noopener"><em>{html.escape(clean_val)}</em></a>.'
                    f'</div>'
                )
            return ""
        text = re.sub(r"\{\{\s*(commonscat|commons|wikiquote)\s*(?:\|([^}]+))?\}\}", sister_sub, text, flags=re.IGNORECASE)

        # Handle succession boxes: {{S-start}}...{{S-end}}
        def succession_sub(m: re.Match) -> str:
            inner = m.group(0)
            rows = []
            box_pat = re.compile(r"\{\{\s*Succession[ _]box\b", re.I)
            pos = 0
            while pos < len(inner):
                bm = box_pat.search(inner, pos)
                if not bm:
                    break
                b_start = bm.start()
                i = b_start
                d = 0
                b_end = -1
                while i < len(inner):
                    if inner[i : i + 2] == "{{":
                        d += 1
                        i += 2
                    elif inner[i : i + 2] == "}}":
                        d -= 1
                        if d == 0:
                            b_end = i + 2
                            break
                        i += 2
                    else:
                        i += 1
                if b_end == -1:
                    pos = bm.end()
                    continue

                raw_box = inner[b_start:b_end]
                box_content = raw_box.strip()[2:-2].strip()

                params = {}
                p_parts = []
                p_cur = []
                p_db = 0
                p_dk = 0
                pj = 0
                while pj < len(box_content):
                    if box_content[pj : pj + 2] == "{{":
                        p_db += 1
                        p_cur.append(box_content[pj : pj + 2])
                        pj += 2
                    elif box_content[pj : pj + 2] == "}}":
                        p_db = max(0, p_db - 1)
                        p_cur.append(box_content[pj : pj + 2])
                        pj += 2
                    elif box_content[pj : pj + 2] == "[[":
                        p_dk += 1
                        p_cur.append(box_content[pj : pj + 2])
                        pj += 2
                    elif box_content[pj : pj + 2] == "]]":
                        p_dk = max(0, p_dk - 1)
                        p_cur.append(box_content[pj : pj + 2])
                        pj += 2
                    elif box_content[pj] == "|" and p_db == 0 and p_dk == 0:
                        p_parts.append("".join(p_cur).strip())
                        p_cur = []
                        pj += 1
                    else:
                        p_cur.append(box_content[pj])
                        pj += 1
                if p_cur:
                    p_parts.append("".join(p_cur).strip())

                for p in p_parts:
                    if "=" in p:
                        k, v = p.split("=", 1)
                        params[k.strip().lower()] = v.strip()

                before = params.get("before", "–")
                title = params.get("title", "")
                years = params.get("years", "")
                after = params.get("after", "–")

                def clean_succ_cell(c: str) -> str:
                    c = re.sub(r"\{\{\s*flagicon\s*\|[^}]*\}\}\s*", "", c, flags=re.I)
                    c = re.sub(r"\{\{\s*ill\s*\|([^|]+)(?:\|[^}]+)*\}\}", r"\1", c, flags=re.I)
                    c = re.sub(r"\[\[([^|\]]+)\|([^\]]+)\]\]", r'<a href="https://id.wikipedia.org/wiki/\1">\2</a>', c)
                    c = re.sub(r"\[\[([^\]]+)\]\]", r'<a href="https://id.wikipedia.org/wiki/\1">\1</a>', c)
                    c = re.sub(r"'''''(.*?)'''''", r"<strong><em>\1</em></strong>", c)
                    c = re.sub(r"'''(.*?)'''", r"<strong>\1</strong>", c)
                    c = re.sub(r"''(.*?)''", r"<em>\1</em>", c)
                    return c.strip()

                rows.append(
                    f'<tr><td style="width:30%; text-align:center; vertical-align:middle;">{clean_succ_cell(before)}</td>'
                    f'<td style="width:40%; text-align:center; font-weight:bold; vertical-align:middle;">{clean_succ_cell(title)}<br><span style="font-weight:normal; font-size:90%; color:#555;">{clean_succ_cell(years)}</span></td>'
                    f'<td style="width:30%; text-align:center; vertical-align:middle;">{clean_succ_cell(after)}</td></tr>'
                )
                pos = b_end

            if rows:
                return (
                    '<table class="wikitable succession-table">'
                    '<tr><th colspan="3" style="background:#eaecf0; text-align:center;">Gelar Politik & Jabatan Pemerintahan</th></tr>'
                    + "".join(rows) +
                    '</table>'
                )
            return ""
        text = re.sub(r"\{\{\s*S-start\s*\}\}[\s\S]*?\{\{\s*S-end\s*\}\}", succession_sub, text, flags=re.IGNORECASE)

        # Handle {{sfn|Author|Year|p=...}}
        def sfn_sub(m: re.Match) -> str:
            parts = [p.strip() for p in m.group(1).split("|")]
            author = parts[0] if len(parts) > 0 else "Rujukan"
            year = parts[1] if len(parts) > 1 else ""
            page = ""
            for p in parts[2:]:
                if p.startswith(("p=", "page=", "halaman=", "hlm=")):
                    page = f", hlm. {p.split('=', 1)[1]}"
                elif not "=" in p and not page:
                    page = f", hlm. {p}"
            label = f"{author} {year}{page}".strip()
            return f'<sup class="reference sfn"><a href="#cite_note-{author}_{year}">[{html.escape(label)}]</a></sup>'
        text = re.sub(r"\{\{\s*sfn\s*\|([^}]+)\}\}", sfn_sub, text, flags=re.IGNORECASE)

        # Simplify standalone citation templates in wikitext (like in === Sumber ===)
        text = re.sub(r"\{\{\s*(?:Cite|sitasi)[ _][a-z0-9_]*\b([\s\S]*?)\}\}", lambda m: self._simplify_template(m.group(0)), text, flags=re.IGNORECASE)

        # Strip {{DEFAULTSORT:...}}
        text = re.sub(r"\{\{DEFAULTSORT:[^}]+\}\}", "", text, flags=re.IGNORECASE)
        # Strip {{Authority control}} and metadata templates
        text = re.sub(r"\{\{\s*(?:authority control|pengawasan otoritas|normdaten|pemimpinrusia|nobel perdamaian)[^}]*\}\}", "", text, flags=re.IGNORECASE)
        # Format {{Commons-inline|...}}
        def commons_sub(m: re.Match) -> str:
            parts = [p.strip() for p in m.group(1).split("|")] if m.group(1) else []
            cat = parts[0] if parts else ""
            target = f"https://commons.wikimedia.org/wiki/{cat}" if cat else "https://commons.wikimedia.org"
            return f'<a href="{target}" class="external" target="_blank" rel="noopener">Wikimedia Commons</a> memiliki media mengenai artikel ini.'
        text = re.sub(r"\{\{\s*commons-inline\s*(?:\|([^}]+))?\}\}", commons_sub, text, flags=re.IGNORECASE)

        # Format {{Wikisourcelang-inline|lang|Page}}
        def wikisource_sub(m: re.Match) -> str:
            parts = [p.strip() for p in m.group(1).split("|")]
            lang = parts[0] if len(parts) > 0 else "id"
            title = parts[1] if len(parts) > 1 else ""
            clean_title = re.sub(r"^[^/]+/", "", title)
            target = f"https://{lang}.wikisource.org/wiki/{urllib.parse.quote(title)}"
            return f'<a href="{target}" class="external" target="_blank" rel="noopener">Wikisumber</a> memiliki naskah asli berbahasa {lang} mengenai <em>{html.escape(clean_title or title)}</em>.'
        text = re.sub(r"\{\{\s*wikisourcelang-inline\s*\|([^}]+)\}\}", wikisource_sub, text, flags=re.IGNORECASE)
        # Format {{ill|Title|lang|Orig...}} or {{interlanguage link|Title|lang|Orig...}}
        def ill_sub(m: re.Match) -> str:
            inner = m.group(1).strip()
            parts = [p.strip() for p in inner.split("|")]
            if parts:
                title = parts[0]
                lang = parts[1] if len(parts) > 1 and len(parts[1]) <= 3 and "=" not in parts[1] else ""
                for p in parts[1:]:
                    if p.lower().startswith("lt="):
                        title = p.split("=", 1)[1].strip()
                        break
                slug = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_")
                badge = (
                    f' <span class="interlanguage-link-badge" style="color:#72777d; font-size:85%;">({lang})</span>'
                    if lang
                    else ""
                )
                return f'<a href="https://id.wikipedia.org/wiki/{slug}" class="new" title="{html.escape(title)}">{html.escape(title)}</a>{badge}'
            return ""

        text = re.sub(
            r"\{\{\s*(?:ill|interlanguage link|interlanguage link multi)\s*\|([^}]+)\}\}",
            ill_sub,
            text,
            flags=re.IGNORECASE,
        )

        LANG_NAMES = {
            "ru": "Rusia", "en": "Inggris", "fr": "Prancis", "de": "Jerman",
            "nl": "Belanda", "es": "Spanyol", "it": "Italia", "ja": "Jepang",
            "zh": "Tionghoa", "ar": "Arab", "la": "Latin", "el": "Yunani",
            "ko": "Korea", "pt": "Portugis", "pl": "Polandia", "uk": "Ukraina",
        }

        # Format {{langx|lang|Text}} -> bahasa X: Text
        def langx_sub(m: re.Match) -> str:
            parts = [p.strip() for p in m.group(1).split("|")]
            if len(parts) >= 2:
                code = parts[0].lower()
                val = ""
                no_label = False
                for p in parts[1:]:
                    if p.lower() == "label=none":
                        no_label = True
                    elif not p.startswith("label="):
                        val = p
                lang_name = LANG_NAMES.get(code, code.upper())
                if no_label:
                    return f'<span lang="{code}">{val}</span>'
                return (
                    f'<a href="https://id.wikipedia.org/wiki/Bahasa_{lang_name}" title="Bahasa {lang_name}">bahasa {lang_name}</a>: '
                    f'<span lang="{code}">{val}</span>'
                )
            return ""

        text = re.sub(r"\{\{\s*langx\s*\|([^}]+)\}\}", langx_sub, text, flags=re.IGNORECASE)

        # Format {{lang-xx|Text}} -> bahasa X: Text
        def lang_xx_sub(m: re.Match) -> str:
            code = m.group(1).lower()
            parts = [p.strip() for p in m.group(2).split("|")]
            val = parts[0] if parts else ""
            lang_name = LANG_NAMES.get(code, code.upper())
            return (
                f'<a href="https://id.wikipedia.org/wiki/Bahasa_{lang_name}" title="Bahasa {lang_name}">bahasa {lang_name}</a>: '
                f'<span lang="{code}">{val}</span>'
            )

        text = re.sub(r"\{\{\s*lang-([a-z]{2,3})\s*\|([^}]+)\}\}", lang_xx_sub, text, flags=re.IGNORECASE)
        # Format {{lang|id|...}} -> ...
        text = re.sub(r"\{\{lang(?:-[a-z]+)?\|[^|]+\|([^}]+)\}\}", r"\1", text, flags=re.IGNORECASE)
        # Format {{OldStyleDate|new_date|year|old_date}} -> new_date year (K.J. old_date)
        def old_style_date_sub(m: re.Match) -> str:
            parts = [p.strip() for p in m.group(1).split("|")]
            if len(parts) >= 3:
                new_date, year, old_date = parts[0], parts[1], parts[2]
                return f"{new_date} {year} (K.J. {old_date})"
            elif len(parts) == 2:
                return f"{parts[0]} (K.J. {parts[1]})"
            elif len(parts) == 1:
                return parts[0]
            return ""

        text = re.sub(r"\{\{\s*OldStyleDate\s*\|([^}]+)\}\}", old_style_date_sub, text, flags=re.IGNORECASE)


        # General templates: {{X|Y}} -> Y if single argument, else remove
        def gen_sub(m: re.Match) -> str:
            inner = m.group(1).strip()
            parts = inner.split("|")
            if len(parts) == 2 and "=" not in parts[1]:
                return parts[1].strip()
            return ""
        text = re.sub(r"\{\{([^}]+)\}\}", gen_sub, text)

        # Clean up any duplicate punctuation left by removed or inline templates
        text = re.sub(r",\s*,+", ",", text)
        text = re.sub(r"\s+([,.:;!?])", r"\1", text)
        text = re.sub(r",\s*\.", ".", text)
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
