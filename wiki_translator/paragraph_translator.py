"""
Context-Aware Paragraph-by-Paragraph Translation Engine.

Splits long multi-paragraph wikitext sections into coherent paragraph chunks,
translates each chunk with section header and preceding context for smooth flow,
and reassembles them seamlessly while keeping tables, infoboxes, and template
blocks as atomic units.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

from .prompts import SYSTEM_PROMPT_GRADE_A_PLUS_PLUS, build_translation_prompt


def split_into_paragraph_chunks(
    wikitext: str, max_chunk_words: int = 250
) -> List[Dict[str, Any]]:
    """
    Splits long multi-paragraph wikitext sections into coherent paragraph chunks.

    - Keeps tables (`{| ... |}`), infoboxes, and template blocks as atomic units (not split).
    - Splits prose paragraphs (separated by `\\n\\n`).
    - Groups short adjacent paragraphs or keeps individual paragraphs within `max_chunk_words`.
    - Returns list of chunks with metadata:
      `{"type": "prose"|"table"|"infobox"|"template", "content": chunk_text, "index": i}`
    """
    raw = wikitext.strip()
    if not raw:
        return []

    raw_blocks: List[Dict[str, Any]] = []
    last_end = 0
    n = len(raw)

    table_pattern = re.compile(r"(?:(?<=\n)|^)[ \t]*\{\|")
    template_pattern = re.compile(r"(?:(?<=\n)|^)[ \t]*\{\{")

    pos = 0
    while pos < n:
        m_table = table_pattern.search(raw, pos)
        m_template = template_pattern.search(raw, pos)

        candidates = []
        if m_table:
            candidates.append((m_table.start(), "table", m_table))
        if m_template:
            candidates.append((m_template.start(), "template", m_template))

        if not candidates:
            break

        candidates.sort(key=lambda x: x[0])
        match_start, block_kind, match_obj = candidates[0]

        line_start = match_start
        if block_kind == "table":
            opener_idx = raw.find("{|", line_start)
            depth = 0
            idx = opener_idx
            matched_end = -1
            while idx < n - 1:
                if raw[idx : idx + 2] == "{|":
                    depth += 1
                    idx += 2
                elif raw[idx : idx + 2] == "|}":
                    depth -= 1
                    idx += 2
                    if depth == 0:
                        matched_end = idx
                        break
                else:
                    idx += 1

            if matched_end != -1:
                if line_start > last_end:
                    preceding = raw[last_end:line_start].strip()
                    if preceding:
                        raw_blocks.append({"type": "prose", "content": preceding})
                table_content = raw[line_start:matched_end].strip()
                raw_blocks.append({"type": "table", "content": table_content})
                last_end = matched_end
                pos = matched_end
            else:
                pos = opener_idx + 2

        elif block_kind == "template":
            opener_idx = raw.find("{{", line_start)
            depth = 0
            idx = opener_idx
            matched_end = -1
            while idx < n - 1:
                if raw[idx : idx + 2] == "{{":
                    depth += 1
                    idx += 2
                elif raw[idx : idx + 2] == "}}":
                    depth -= 1
                    idx += 2
                    if depth == 0:
                        matched_end = idx
                        break
                else:
                    idx += 1

            if matched_end != -1:
                tmpl_text = raw[line_start:matched_end].strip()
                is_infobox = bool(
                    re.match(r"^\{\{\s*(?:[Ii]nfobox|[Tt]emplat:[Ii]nfobox)", raw[opener_idx:matched_end])
                )
                if is_infobox or ("\n" in tmpl_text) or len(tmpl_text) > 80:
                    if line_start > last_end:
                        preceding = raw[last_end:line_start].strip()
                        if preceding:
                            raw_blocks.append({"type": "prose", "content": preceding})
                    raw_blocks.append({
                        "type": "infobox" if is_infobox else "template",
                        "content": tmpl_text,
                    })
                    last_end = matched_end
                    pos = matched_end
                else:
                    rest_of_line = raw[matched_end:raw.find("\n", matched_end) if "\n" in raw[matched_end:] else n].strip()
                    if not rest_of_line:
                        if line_start > last_end:
                            preceding = raw[last_end:line_start].strip()
                            if preceding:
                                raw_blocks.append({"type": "prose", "content": preceding})
                        raw_blocks.append({
                            "type": "template",
                            "content": tmpl_text,
                        })
                        last_end = matched_end
                        pos = matched_end
                    else:
                        pos = opener_idx + 2
            else:
                pos = opener_idx + 2

    if last_end < n:
        trailing = raw[last_end:].strip()
        if trailing:
            raw_blocks.append({"type": "prose", "content": trailing})

    final_chunks: List[Dict[str, Any]] = []

    for block in raw_blocks:
        b_type = block["type"]
        b_content = block["content"].strip()
        if not b_content:
            continue

        if b_type in ("table", "infobox", "template"):
            final_chunks.append({
                "type": b_type,
                "content": b_content,
                "index": len(final_chunks),
            })
        else:
            # Prose: split on \n\n
            paras = [p.strip() for p in re.split(r"\n\s*\n", b_content) if p.strip()]
            if not paras:
                continue

            # If max_chunk_words is 0 or None, keep each paragraph as separate chunk
            if max_chunk_words <= 0:
                for p in paras:
                    final_chunks.append({
                        "type": "prose",
                        "content": p,
                        "index": len(final_chunks),
                    })
                continue

            current_group: List[str] = []
            current_words = 0

            for p in paras:
                p_words = len(p.split())
                if current_group and (current_words + p_words > max_chunk_words):
                    chunk_text = "\n\n".join(current_group).strip()
                    final_chunks.append({
                        "type": "prose",
                        "content": chunk_text,
                        "index": len(final_chunks),
                    })
                    current_group = [p]
                    current_words = p_words
                else:
                    current_group.append(p)
                    current_words += p_words

            if current_group:
                chunk_text = "\n\n".join(current_group).strip()
                final_chunks.append({
                    "type": "prose",
                    "content": chunk_text,
                    "index": len(final_chunks),
                })

    for i, c in enumerate(final_chunks):
        c["index"] = i

    return final_chunks


class ParagraphTranslator:
    """Context-aware paragraph-by-paragraph translation coordinator."""

    def __init__(self, max_chunk_words: int = 250):
        self.max_chunk_words = max_chunk_words

    def split_into_paragraph_chunks(
        self, wikitext: str, max_chunk_words: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        return split_into_paragraph_chunks(
            wikitext=wikitext,
            max_chunk_words=self.max_chunk_words if max_chunk_words is None else max_chunk_words,
        )

    def translate_section_by_paragraphs(
        self,
        section_title: str,
        wikitext: str,
        translator_func: Callable[[str, Optional[str]], str],
        topic: Optional[str] = None,
        context_notes: Optional[str] = None,
        custom_glossary: Optional[Dict[str, str]] = None,
        resolved_glossary: Optional[Dict[str, str]] = None,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """
        Translates a section using context-aware paragraph-by-paragraph translation.

        - If section only has 1 paragraph or is atomic (table/infobox/single template),
          translates directly without splitting.
        - If section has multiple chunks:
          * Iterates through each chunk.
          * In the prompt for each chunk, injects:
            - Section Title (== [Title] ==)
            - Preceding translated context summary (to maintain seamless narrative flow)
            - The current chunk to translate.
          * Collects translated chunks and joins with \\n\\n.
        """
        cleaned = wikitext.strip()
        if not cleaned:
            return ""

        # Separate header if present at top of wikitext
        header_line = ""
        body_wikitext = cleaned
        header_match = re.match(r"^(=+\s*([^=]+?)\s*=+)\s*\n?", cleaned)
        if header_match:
            header_line = header_match.group(1).strip()
            body_wikitext = cleaned[header_match.end() :].strip()

        chunks = self.split_into_paragraph_chunks(body_wikitext)

        # If only 0 or 1 chunk, or all chunks is just 1 non-prose or single prose:
        if len(chunks) <= 1:
            # Direct translation using full wikitext
            prompt = build_translation_prompt(
                section_title=section_title,
                wikitext_content=cleaned,
                context_notes=context_notes,
                topic=topic,
                custom_glossary=custom_glossary,
                resolved_glossary=resolved_glossary,
            )
            res = translator_func(prompt, SYSTEM_PROMPT_GRADE_A_PLUS_PLUS)
            if stream_callback:
                stream_callback(res)
            return res.strip()

        # Multiple chunks: translate sequentially with preceding context
        translated_chunks: List[str] = []
        preceding_contexts: List[str] = []

        for i, chunk in enumerate(chunks):
            chunk_content = chunk["content"]
            chunk_type = chunk["type"]

            # Formulate preceding context summary / text
            preceding_summary = ""
            if preceding_contexts:
                recent_ctx = "\n\n".join(preceding_contexts[-2:]).strip()
                words = recent_ctx.split()
                if len(words) > 150:
                    recent_ctx = " ".join(words[-150:])
                source_ctx = "\n\n".join(c["content"] for c in chunks[max(0, i - 2):i])
                source_ctx = " ".join(source_ctx.split()[-150:])
                preceding_summary = (
                    "Konteks sumber paragraf sebelumnya (acuan makna, jangan diterjemahkan ulang):\n"
                    f"{source_ctx}\n"
                    "Konteks terjemahan paragraf sebelumnya (draf dapat keliru; "
                    "sumber Inggris tetap menjadi acuan):\n"
                    f"{recent_ctx}"
                )

            # Combine additional context notes with preceding context
            combined_context_notes = []
            if context_notes:
                combined_context_notes.append(context_notes)
            if preceding_summary:
                combined_context_notes.append(preceding_summary)
            merged_context = "\n\n".join(combined_context_notes) if combined_context_notes else None

            # For the first chunk, if there's a header_line, include it in the chunk
            is_first = (i == 0)
            if is_first and header_line:
                chunk_to_send = f"{header_line}\n{chunk_content}"
            else:
                chunk_to_send = chunk_content

            chunk_title = section_title or "Lead"
            sub_title_desc = f"{chunk_title} (Bagian Paragraf {i+1} dari {len(chunks)})"

            prompt = build_translation_prompt(
                section_title=sub_title_desc,
                wikitext_content=chunk_to_send,
                context_notes=merged_context,
                topic=topic,
                custom_glossary=custom_glossary,
                resolved_glossary=resolved_glossary,
            )

            translated_chunk = translator_func(prompt, SYSTEM_PROMPT_GRADE_A_PLUS_PLUS).strip()

            if stream_callback:
                if i > 0:
                    stream_callback("\n\n")
                stream_callback(translated_chunk)

            translated_chunks.append(translated_chunk)
            clean_for_ctx = re.sub(r"^=+\s*[^=]+?\s*=+\s*\n?", "", translated_chunk).strip()
            if clean_for_ctx:
                preceding_contexts.append(clean_for_ctx)

        # Reassemble
        return "\n\n".join(translated_chunks).strip()


default_paragraph_translator = ParagraphTranslator()
