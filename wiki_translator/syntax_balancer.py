"""
Wikitext Syntax Balancer & Repair Utility for Wikipedia ID Translation.

Inspects and balances wikitext markup:
- Wikilinks: [[ ... ]]
- Templates: {{ ... }}
- Citation/footnote tags: <ref> ... </ref>, <ref name="..."> ... </ref>, <ref name="..." />
- Wikitables: {| and |}
- Formatting tags: ''', '', <code>, <blockquote>, <nowiki>

Provides:
- check_balance(wikitext: str) -> List[Dict[str, Any]]
- auto_repair(wikitext: str) -> str
- default_syntax_balancer (global instance)
"""

from dataclasses import dataclass
import re
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class SyntaxIssue:
    tag_type: str
    line_number: int
    description: str
    severity: str  # "error", "warning"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tag_type": self.tag_type,
            "line_number": self.line_number,
            "description": self.description,
            "severity": self.severity,
        }


class WikitextSyntaxBalancer:
    """
    Syntax inspector and repair engine for wikitext.
    Detects mismatched or unclosed links, templates, tables, tags, and formatting.
    """

    # Self-closing tags or tags that don't need closing
    SELF_CLOSING_TAGS = {"br", "wbr", "hr"}

    def __init__(self):
        pass

    def check_balance(self, wikitext: str) -> List[Dict[str, Any]]:
        """
        Inspects wikitext and returns a list of issues found.
        Each issue dict contains:
        - tag_type: str (e.g. 'wikilink', 'template', 'ref', 'wikitable', 'bold', 'italic', 'html_tag')
        - line_number: int (1-based)
        - description: str
        - severity: str ('error' or 'warning')
        """
        issues: List[SyntaxIssue] = []
        if not wikitext:
            return []

        # 1. Check <nowiki> tags
        nowiki_issues = self._check_paired_tags(wikitext, "nowiki", severity="error")
        issues.extend(nowiki_issues)

        # Mask nowiki and comments to avoid false positives inside ignored blocks
        masked_text, masks = self._mask_literals(wikitext)

        # 2. Check Wikitables {| ... |}
        issues.extend(self._check_wikitables(masked_text))

        # 3. Check Templates {{ ... }}
        issues.extend(self._check_bracket_pairs(masked_text, "{{", "}}", "template"))

        # 4. Check Wikilinks [[ ... ]]
        issues.extend(self._check_bracket_pairs(masked_text, "[[", "]]", "wikilink"))

        # 5. Check Citation/footnote <ref> tags
        # 5. Check Citation/footnote <ref> tags (including unclosed tags and orphan named refs)
        issues.extend(self._check_ref_tags(masked_text))

        # 6. Check paired HTML formatting tags: <code>, <blockquote>
        issues.extend(self._check_paired_tags(masked_text, "code", severity="warning"))
        issues.extend(self._check_paired_tags(masked_text, "blockquote", severity="warning"))

        # 7. Check wiki bold ''' and italic ''
        issues.extend(self._check_quotes_formatting(masked_text))

        # Sort issues by line number
        issues.sort(key=lambda x: (x.line_number, x.tag_type))
        return [issue.to_dict() for issue in issues]

    def auto_repair(self, wikitext: str) -> str:
        """
        Safely fixes missing closing tags (like unclosed </ref>, unclosed }},
        unclosed ]], unclosed |}, unclosed formatting) without mangling valid contents or URLs.
        """
        if not wikitext:
            return wikitext

        repaired = wikitext

        # 1. Fix unclosed <nowiki>
        repaired = self._repair_paired_tags(repaired, "nowiki")

        # 2. Repair HTML formatting tags: <code>, <blockquote>
        repaired = self._repair_paired_tags(repaired, "code")
        repaired = self._repair_paired_tags(repaired, "blockquote")

        # 3. Repair <ref> tags
        # 3. Repair <ref> tags and resolve orphan self-closing references
        repaired = self._repair_ref_tags(repaired)
        repaired = self.resolve_orphan_references(repaired)

        # 4. Repair formatting quotes: bold ''' and italic ''
        repaired = self._repair_quotes_formatting(repaired)

        # 5. Repair wikilinks [[ ... ]]
        repaired = self._repair_wikilinks(repaired)

        # 6. Repair templates {{ ... }}
        repaired = self._repair_templates(repaired)

        # 7. Repair wikitables {| ... |}
        repaired = self._repair_wikitables(repaired)

        # 8. Normalize {{efn}} footnote groups (|group=lower-greek, etc.)
        repaired = self.normalize_efn_groups(repaired)

        return repaired

    # -------------------------------------------------------------------------
    # Helper & Detection Methods
    # -------------------------------------------------------------------------

    def _get_line_number(self, text: str, pos: int) -> int:
        """Returns 1-based line number for character index pos in text."""
        return text.count("\n", 0, pos) + 1

    def _mask_literals(self, text: str) -> Tuple[str, List[Tuple[str, str]]]:
        """
        Masks HTML comments and <nowiki> content so scanner doesn't trigger on them.
        Returns (masked_text, replacements).
        """
        replacements: List[Tuple[str, str]] = []

        def comment_repl(match):
            placeholder = f"§§COMMENT_{len(replacements)}§§"
            replacements.append((placeholder, match.group(0)))
            return placeholder

        def nowiki_repl(match):
            placeholder = f"§§NOWIKI_{len(replacements)}§§"
            replacements.append((placeholder, match.group(0)))
            return placeholder

        # Mask comments <!-- ... -->
        masked = re.sub(r"<!--[\s\S]*?-->", comment_repl, text)
        # Mask nowiki <nowiki> ... </nowiki>
        masked = re.sub(r"<nowiki\b[^>]*>[\s\S]*?</nowiki>", nowiki_repl, masked, flags=re.IGNORECASE)

        return masked, replacements

    def _unmask_literals(self, text: str, replacements: List[Tuple[str, str]]) -> str:
        for placeholder, original in reversed(replacements):
            text = text.replace(placeholder, original)
        return text

    def _check_paired_tags(self, text: str, tag_name: str, severity: str = "warning") -> List[SyntaxIssue]:
        issues: List[SyntaxIssue] = []
        open_pattern = re.compile(rf"<({tag_name})\b([^/>]*)(/?)>", re.IGNORECASE)
        close_pattern = re.compile(rf"</({tag_name})\s*>", re.IGNORECASE)

        # Tokenize tags in order of appearance
        tokens = []
        for m in open_pattern.finditer(text):
            if m.group(3) == "/":
                continue  # self-closing e.g. <nowiki/>
            tokens.append(("open", m.start(), m.end(), m.group(0)))
        for m in close_pattern.finditer(text):
            tokens.append(("close", m.start(), m.end(), m.group(0)))

        tokens.sort(key=lambda x: x[1])

        stack = []
        for token_type, start, end, raw in tokens:
            line_no = self._get_line_number(text, start)
            if token_type == "open":
                stack.append((start, line_no, raw))
            elif token_type == "close":
                if stack:
                    stack.pop()
                else:
                    issues.append(
                        SyntaxIssue(
                            tag_type=tag_name,
                            line_number=line_no,
                            description=f"Unmatched closing tag </{tag_name}> without preceding open tag.",
                            severity=severity,
                        )
                    )

        while stack:
            start, line_no, raw = stack.pop()
            issues.append(
                SyntaxIssue(
                    tag_type=tag_name,
                    line_number=line_no,
                    description=f"Unclosed tag <{tag_name}> (opened on line {line_no}).",
                    severity=severity,
                )
            )

        return issues

    def _check_wikitables(self, text: str) -> List[SyntaxIssue]:
        issues: List[SyntaxIssue] = []
        # Wikitables start with {| and end with |} typically at line starts / with whitespace
        # Standard mediawiki syntax requires {| and |}
        open_pattern = re.compile(r"\{\|")
        close_pattern = re.compile(r"\|\}")

        tokens = []
        for m in open_pattern.finditer(text):
            tokens.append(("open", m.start(), m.group(0)))
        for m in close_pattern.finditer(text):
            tokens.append(("close", m.start(), m.group(0)))

        tokens.sort(key=lambda x: x[1])

        stack = []
        for token_type, start, raw in tokens:
            line_no = self._get_line_number(text, start)
            if token_type == "open":
                stack.append((start, line_no))
            elif token_type == "close":
                if stack:
                    stack.pop()
                else:
                    issues.append(
                        SyntaxIssue(
                            tag_type="wikitable",
                            line_number=line_no,
                            description="Unmatched table closing markup '|}' without preceding '{|'.",
                            severity="error",
                        )
                    )

        while stack:
            start, line_no = stack.pop()
            issues.append(
                SyntaxIssue(
                    tag_type="wikitable",
                    line_number=line_no,
                    description=f"Unclosed wikitable '{{|' (opened on line {line_no}).",
                    severity="error",
                )
            )

        return issues

    def _check_bracket_pairs(
        self, text: str, open_delim: str, close_delim: str, tag_type: str
    ) -> List[SyntaxIssue]:
        issues: List[SyntaxIssue] = []
        open_len = len(open_delim)
        close_len = len(close_delim)

        pos = 0
        text_len = len(text)
        stack = []

        while pos < text_len:
            if text.startswith(open_delim, pos):
                line_no = self._get_line_number(text, pos)
                stack.append((pos, line_no))
                pos += open_len
            elif text.startswith(close_delim, pos):
                line_no = self._get_line_number(text, pos)
                if stack:
                    stack.pop()
                else:
                    issues.append(
                        SyntaxIssue(
                            tag_type=tag_type,
                            line_number=line_no,
                            description=f"Unmatched closing '{close_delim}' without preceding '{open_delim}'.",
                            severity="error",
                        )
                    )
                pos += close_len
            else:
                pos += 1

        while stack:
            pos, line_no = stack.pop()
            issues.append(
                SyntaxIssue(
                    tag_type=tag_type,
                    line_number=line_no,
                    description=f"Unclosed '{open_delim}' (opened on line {line_no}).",
                    severity="error",
                )
            )

        return issues

    def _check_ref_tags(self, text: str) -> List[SyntaxIssue]:
        issues: List[SyntaxIssue] = []
        # Match <ref ...>, <ref .../>, </ref>
        ref_regex = re.compile(r"<(/?)ref(\s+[^>/]*?)?(/?)>", re.IGNORECASE)

        stack = []
        for m in ref_regex.finditer(text):
            is_closing = bool(m.group(1))
            is_self_closing = (m.group(3) == "/")
            start_pos = m.start()
            line_no = self._get_line_number(text, start_pos)

            if is_self_closing:
                continue

            if not is_closing:
                stack.append((start_pos, line_no, m.group(0)))
            else:
                if stack:
                    stack.pop()
                else:
                    issues.append(
                        SyntaxIssue(
                            tag_type="ref",
                            line_number=line_no,
                            description="Unmatched closing </ref> tag without preceding open tag.",
                            severity="error",
                        )
                    )

        while stack:
            start_pos, line_no, raw = stack.pop()
            issues.append(
                SyntaxIssue(
                    tag_type="ref",
                    line_number=line_no,
                    description=f"Unclosed citation tag <ref> (opened on line {line_no}).",
                    severity="error",
                )
            )

        # Check for orphan self-closing <ref name="..." /> tags without defining <ref name="...">...</ref>
        defined_names, orphan_self_closing = self._scan_ref_names(text)
        for name, start_pos, raw_tag in orphan_self_closing:
            line_no = self._get_line_number(text, start_pos)
            issues.append(
                SyntaxIssue(
                    tag_type="ref",
                    line_number=line_no,
                    description=f"Orphan citation tag <ref name=\"{name}\" /> without defining <ref name=\"{name}\">...</ref> tag.",
                    severity="error",
                )
            )

        return issues

    def _check_quotes_formatting(self, text: str) -> List[SyntaxIssue]:
        """
        Checks for odd number of bold (''') and italic ('') wiki markups on each line.
        Wikitext inline formatting should normally be closed on the same paragraph/line.
        """
        issues: List[SyntaxIssue] = []
        lines = text.split("\n")

        for idx, line in enumerate(lines, start=1):
            # Ignore lines starting with wiki syntax where quotes have special meaning
            # Mask out 5 quotes (bold + italic) '''''
            clean_line = line
            # Count sequences of consecutive single quotes:
            # ''''' = 5 (bold italic)
            # ''' = 3 (bold)
            # '' = 2 (italic)
            # Ignore ' inside HTML tags or URLs or words (e.g. don't, O'Connor)
            # Only count isolated runs of 2, 3, or 5 single quotes:
            quote_runs = re.findall(r"(?<!')('{2,5})(?!')", clean_line)
            if not quote_runs:
                continue

            bold_count = 0
            italic_count = 0
            for run in quote_runs:
                if len(run) == 5:
                    bold_count += 1
                    italic_count += 1
                elif len(run) == 3:
                    bold_count += 1
                elif len(run) == 2:
                    italic_count += 1

            if bold_count % 2 != 0:
                issues.append(
                    SyntaxIssue(
                        tag_type="bold",
                        line_number=idx,
                        description=f"Unbalanced bold markup (''') on line {idx}.",
                        severity="warning",
                    )
                )
            if italic_count % 2 != 0:
                issues.append(
                    SyntaxIssue(
                        tag_type="italic",
                        line_number=idx,
                        description=f"Unbalanced italic markup ('') on line {idx}.",
                        severity="warning",
                    )
                )

        return issues

    # -------------------------------------------------------------------------
    # Auto Repair Implementations
    # -------------------------------------------------------------------------

    def _repair_paired_tags(self, text: str, tag_name: str) -> str:
        """Repairs unclosed HTML paired tags like <nowiki>, <code>, <blockquote>."""
        open_pattern = re.compile(rf"<({tag_name})\b([^/>]*)(/?)>", re.IGNORECASE)
        close_pattern = re.compile(rf"</({tag_name})\s*>", re.IGNORECASE)

        tokens = []
        for m in open_pattern.finditer(text):
            if m.group(3) == "/":
                continue
            tokens.append(("open", m.start(), m.end()))
        for m in close_pattern.finditer(text):
            tokens.append(("close", m.start(), m.end()))

        tokens.sort(key=lambda x: x[1])

        unclosed_count = 0
        for token_type, _, _ in tokens:
            if token_type == "open":
                unclosed_count += 1
            elif token_type == "close":
                if unclosed_count > 0:
                    unclosed_count -= 1

        if unclosed_count > 0:
            text = text.rstrip() + ("\n" if "\n" in text else "") + (f"</{tag_name}>" * unclosed_count)

        return text

    def _repair_ref_tags(self, text: str) -> str:
        """
        Safely closes dangling <ref> tags.
        If a <ref> is opened without a close:
        - If it's within a paragraph or before another ref/heading/end of line/text, close it.
        """
        ref_regex = re.compile(r"<(/?)ref(\s+[^>/]*?)?(/?)>", re.IGNORECASE)
        tokens = []
        for m in ref_regex.finditer(text):
            is_closing = bool(m.group(1))
            is_self_closing = (m.group(3) == "/")
            if is_self_closing:
                continue
            tokens.append((is_closing, m.start(), m.end(), m.group(0)))

        stack = []
        for is_closing, start, end, raw in tokens:
            if not is_closing:
                stack.append((start, end, raw))
            else:
                if stack:
                    stack.pop()

        if not stack:
            return text

        # We have unclosed refs. For each unclosed ref from right to left:
        # Find where it makes the most sense to insert </ref>:
        # - Before the next section heading (== ... ==)
        # - Before the next <ref> or {{reflist}} or [[Category:
        # - Or at the end of the line/paragraph/text.
        chars = list(text)
        # Sort stack in descending order of open position so insertions don't invalidate indices
        stack.sort(key=lambda x: x[0], reverse=True)

        for open_start, open_end, raw in stack:
            sub = text[open_end:]
            # Look for a boundary: next section header, category, reflist, or blank line
            boundary_match = re.search(
                r"(\n==+\s*[^=]+==+|\n\{\{(?:[Dd]aftar rujukan|[Rr]eflist)|\n\[\[(?:Category|Kategori):|\n\n|$)",
                sub,
            )
            if boundary_match and boundary_match.start() > 0:
                insert_pos = open_end + boundary_match.start()
            else:
                # Insert at end of string or before trailing whitespace
                m_trail = re.search(r"\s*$", text)
                insert_pos = m_trail.start() if m_trail else len(text)

            text = text[:insert_pos] + "</ref>" + text[insert_pos:]

        return text

    def _scan_ref_names(self, text: str) -> Tuple[set[str], List[Tuple[str, int, str]]]:
        """
        Scans wikitext for defined ref names and self-closing ref names.
        Returns (defined_names_set, list_of_orphan_self_closing_tuples: (name, start_pos, raw_tag)).
        """
        defined_names = set()
        self_closing_refs: List[Tuple[str, int, str]] = []

        # Regex for defining ref tag with name: <ref name="FOO" ...>...</ref> or <ref name=FOO ...>...</ref>
        # Notice it has content and closing </ref>
        # First find all <ref ...>...</ref> blocks
        ref_block_regex = re.compile(r"<ref\s+([^>/]*?)>([\s\S]*?)</ref>", re.IGNORECASE)
        for m in ref_block_regex.finditer(text):
            attrs = m.group(1)
            name_match = re.search(r'''name\s*=\s*(?:"([^"]+)"|'([^']+)'|([^\s/>]+))''', attrs, re.IGNORECASE)
            if name_match:
                ref_name = name_match.group(1) or name_match.group(2) or name_match.group(3)
                if ref_name:
                    defined_names.add(ref_name.strip())

        # Regex for self-closing ref tag: <ref name="FOO" ... /> or <ref ... name="FOO" />
        self_close_regex = re.compile(r"<ref\s+([^>]*?)/\s*>", re.IGNORECASE)
        for m in self_close_regex.finditer(text):
            attrs = m.group(1)
            name_match = re.search(r'''name\s*=\s*(?:"([^"]+)"|'([^']+)'|([^\s/>]+))''', attrs, re.IGNORECASE)
            if name_match:
                ref_name = name_match.group(1) or name_match.group(2) or name_match.group(3)
                if ref_name:
                    self_closing_refs.append((ref_name.strip(), m.start(), m.group(0)))

        orphan_self_closing = [
            item for item in self_closing_refs if item[0] not in defined_names
        ]
        return defined_names, orphan_self_closing

    def resolve_orphan_references(
        self,
        wikitext: str,
        source_en_wikitext: Optional[str] = None,
    ) -> str:
        """
        Resolves orphan self-closing citation tags <ref name="..." /> where no
        defining <ref name="...">...</ref> tag exists in the wikitext.

        - If source_en_wikitext is provided, attempts to find the defining tag from en.wiki source
          and injects it in place of the orphan self-closing tag.
        - Otherwise, safely removes the orphan self-closing tag so MediaWiki NEVER throws
          a citation error ("Tanda <ref> tidak sah; tidak ditemukan teks untuk ref bernama...").
        """
        if not wikitext:
            return wikitext

        defined_names, orphan_refs = self._scan_ref_names(wikitext)
        if not orphan_refs:
            return wikitext

        # Extract definitions from source_en_wikitext if available
        source_definitions: Dict[str, str] = {}
        if source_en_wikitext:
            ref_block_regex = re.compile(r"(<ref\s+([^>/]*?)>([\s\S]*?)</ref>)", re.IGNORECASE)
            for m in ref_block_regex.finditer(source_en_wikitext):
                full_tag = m.group(1)
                attrs = m.group(2)
                name_match = re.search(r'''name\s*=\s*(?:"([^"]+)"|'([^']+)'|([^\s/>]+))''', attrs, re.IGNORECASE)
                if name_match:
                    ref_name = name_match.group(1) or name_match.group(2) or name_match.group(3)
                    if ref_name and ref_name.strip() not in source_definitions:
                        source_definitions[ref_name.strip()] = full_tag

        result = wikitext
        # Replace or remove orphan self-closing tags
        # Process unique orphan names
        orphan_name_set = {name for name, _, _ in orphan_refs}
        for orphan_name in orphan_name_set:
            # Self-closing ref tag matching this orphan name
            escaped_name = re.escape(orphan_name)
            tag_pattern = re.compile(
                rf'''<ref\s+[^>]*?name\s*=\s*(?:"{escaped_name}"|'{escaped_name}'|{escaped_name})(?:\s+[^>]*)?/\s*>''',
                re.IGNORECASE,
            )

            if orphan_name in source_definitions:
                # Inject the defining tag for the first occurrence, keep subsequent occurrences as self-closing
                defining_tag = source_definitions[orphan_name]
                first = True

                def repl(match: re.Match) -> str:
                    nonlocal first
                    if first:
                        first = False
                        return defining_tag
                    return match.group(0)

                result = tag_pattern.sub(repl, result)
            else:
                # Safely remove orphan self-closing tag so MediaWiki never throws citation error
                result = tag_pattern.sub("", result)

        return result

    def _repair_quotes_formatting(self, text: str) -> str:
        """
        Safely balances bold (''') and italic ('') quotes on a per-line basis.
        """
        lines = text.split("\n")
        repaired_lines = []

        for line in lines:
            # Find quote runs: ''''' (5), ''' (3), '' (2)
            quote_runs = list(re.finditer(r"(?<!')('{2,5})(?!')", line))
            if not quote_runs:
                repaired_lines.append(line)
                continue

            bold_count = 0
            italic_count = 0
            for m in quote_runs:
                run = m.group(1)
                if len(run) == 5:
                    bold_count += 1
                    italic_count += 1
                elif len(run) == 3:
                    bold_count += 1
                elif len(run) == 2:
                    italic_count += 1

            need_bold = (bold_count % 2 != 0)
            need_italic = (italic_count % 2 != 0)

            if need_bold and need_italic:
                line = line + "'''''"
            elif need_bold:
                line = line + "'''"
            elif need_italic:
                line = line + "''"

            repaired_lines.append(line)

        return "\n".join(repaired_lines)

    def _repair_wikilinks(self, text: str) -> str:
        """
        Safely fixes unclosed wikilinks [[ ... without closing ]].
        E.g., "See [[Article Name for more info." -> "See [[Article Name]] for more info."
        Also ensures nested or trailing unclosed brackets are closed.
        """
        # Count [[ and ]]
        open_count = text.count("[[")
        close_count = text.count("]]")

        if open_count == close_count:
            return text

        if open_count > close_count:
            # We have missing ]]
            # Try to locate unclosed [[ that has no closing ]] before newline or separator
            diff = open_count - close_count
            
            # Pattern: [[ followed by text up to newline, pipe, or end without ]]
            # Let's inspect tokens sequentially
            pos = 0
            tokens = []
            while pos < len(text):
                if text.startswith("[[", pos):
                    tokens.append(("open", pos))
                    pos += 2
                elif text.startswith("]]", pos):
                    tokens.append(("close", pos))
                    pos += 2
                else:
                    pos += 1

            stack = []
            for token_type, p in tokens:
                if token_type == "open":
                    stack.append(p)
                elif token_type == "close":
                    if stack:
                        stack.pop()

            # For each unclosed [[ in reverse order:
            # Find the best place to close it:
            # A wikilink target/anchor usually ends before a pipe (if closing target),
            # or after 1-5 words before punctuation, or before markup/newline.
            # If there's a space after a single capitalized/named term e.g. "[[Indonesia untuk",
            # we prefer closing the single entity or before punctuation/newline.
            for open_pos in reversed(stack):
                sub = text[open_pos + 2:]
                # Check if starts with a word or multi-word title:
                # E.g. "[[Target|Anchor ..." or "[[Target Word ..."
                # Look for first boundary: pipe, punctuation, newline, next tag, or word break after 1-4 words
                # Match standard wikilink title characters: letters, numbers, spaces, underscore, hyphen
                title_match = re.match(r"^([^\[\]\{\}\|\n<>#]+)(\|[^\[\]\{\}\n<>]*)?", sub)
                if title_match:
                    full_match_text = title_match.group(0)
                    # If there's a pipe, e.g. [[Target|Anchor, close right at end of Anchor
                    if "|" in full_match_text:
                        close_idx = open_pos + 2 + len(full_match_text.rstrip(" .,;:"))
                    else:
                        # No pipe. Look for punctuation or first 1-3 words:
                        # If there is punctuation in the line (comma, period, etc.), close before it
                        punc_match = re.search(r"[,\.;:!\?]", full_match_text)
                        if punc_match:
                            # Close before punctuation or first word if followed by lowercase Indonesian preposition/verb
                            words = full_match_text[:punc_match.start()].strip().split()
                            if len(words) > 1 and words[1].lower() in {"untuk", "dan", "di", "ke", "dari", "yang", "pada", "adalah", "sebagai", "dengan", "saat"}:
                                close_idx = open_pos + 2 + len(words[0])
                            else:
                                close_idx = open_pos + 2 + punc_match.start()
                        else:
                            words = full_match_text.strip().split()
                            if len(words) > 1 and words[1].lower() in {"untuk", "dan", "di", "ke", "dari", "yang", "pada", "adalah", "sebagai", "dengan", "saat"}:
                                close_idx = open_pos + 2 + len(words[0])
                            else:
                                close_idx = open_pos + 2 + len(full_match_text.rstrip())
                    text = text[:close_idx] + "]]" + text[close_idx:]
                else:
                    text = text + "]]"
        elif close_count > open_count:
            # Extra closing ]] without [[ - remove orphan ]] if standalone or prefix
            # Find unmatched ]]
            pos = 0
            tokens = []
            while pos < len(text):
                if text.startswith("[[", pos):
                    tokens.append(("open", pos))
                    pos += 2
                elif text.startswith("]]", pos):
                    tokens.append(("close", pos))
                    pos += 2
                else:
                    pos += 1

            matched_opens = set()
            unmatched_closes = []
            open_stack = []
            for token_type, p in tokens:
                if token_type == "open":
                    open_stack.append(p)
                elif token_type == "close":
                    if open_stack:
                        open_stack.pop()
                    else:
                        unmatched_closes.append(p)

            for close_pos in reversed(unmatched_closes):
                text = text[:close_pos] + text[close_pos + 2:]

        return text

    def _repair_templates(self, text: str) -> str:
        """
        Safely fixes unclosed templates {{ ... without closing }}.
        Appends missing }} where appropriate or at end.
        """
        open_count = text.count("{{")
        close_count = text.count("}}")

        if open_count == close_count:
            return text

        if open_count > close_count:
            diff = open_count - close_count
            text = text.rstrip() + ("\n" if "\n" in text else "") + ("}}" * diff)
        elif close_count > open_count:
            # Extra }} - remove unmatched closing brackets
            pos = 0
            tokens = []
            while pos < len(text):
                if text.startswith("{{", pos):
                    tokens.append(("open", pos))
                    pos += 2
                elif text.startswith("}}", pos):
                    tokens.append(("close", pos))
                    pos += 2
                else:
                    pos += 1

            open_stack = []
            unmatched_closes = []
            for token_type, p in tokens:
                if token_type == "open":
                    open_stack.append(p)
                elif token_type == "close":
                    if open_stack:
                        open_stack.pop()
                    else:
                        unmatched_closes.append(p)

            for close_pos in reversed(unmatched_closes):
                text = text[:close_pos] + text[close_pos + 2:]

        return text

    def _repair_wikitables(self, text: str) -> str:
        """
        Safely fixes unclosed wikitables {| ... without closing |}.
        Appends |} on a new line at the end.
        """
        open_count = len(re.findall(r"\{\|", text))
        close_count = len(re.findall(r"\|\}", text))

        if open_count > close_count:
            diff = open_count - close_count
            for _ in range(diff):
                if not text.endswith("\n"):
                    text += "\n"
                text += "|}\n"
        elif close_count > open_count:
            # Remove orphan |}
            tokens = []
            for m in re.finditer(r"\{\|", text):
                tokens.append(("open", m.start()))
            for m in re.finditer(r"\|\}", text):
                tokens.append(("close", m.start()))
            tokens.sort(key=lambda x: x[1])

            open_stack = []
            unmatched_closes = []
            for token_type, p in tokens:
                if token_type == "open":
                    open_stack.append(p)
                elif token_type == "close":
                    if open_stack:
                        open_stack.pop()
                    else:
                        unmatched_closes.append(p)

            for close_pos in reversed(unmatched_closes):
                text = text[:close_pos] + text[close_pos + 2:]

        return text
    def normalize_efn_groups(self, text: str) -> str:
        """
        Repairs malformed or missing |group= parameter in {{efn}} templates.
        e.g. {{Efn|...lower-greek}} -> {{Efn|...|group=lower-greek}}
        e.g. {{Efn|...|group=Lower-greek}} -> {{Efn|...|group=lower-greek}}
        Ensures all footnotes are properly bound to the corresponding <references group="..." />.
        """
        if not text:
            return ""
        pat = re.compile(r"(?:\|group=\s*|\b(?<!\|group=))([Ll]ower-(?:greek|alpha|roman))\s*\}\}")
        def repl(m: re.Match) -> str:
            return "|group=" + m.group(1).lower() + "}}"
        return pat.sub(repl, text)


default_syntax_balancer = WikitextSyntaxBalancer()
