"""
Indonesian Wikipedia Navigation Box (Navbox) Generator.

Auto-constructs and adapts missing navigation boxes (navboxes) from en.wikipedia
for id.wikipedia.

Features:
- Fetches raw wikitext of `Template:<Name>` from en.wikipedia.org (via WikipediaClient or direct API).
- Checks whether `Templat:<Name>` already exists on id.wikipedia.org.
- Converts `{{Navbox ...}}` into id.wikipedia format `{{Kotak navigasi ...}}` (or preserves standard parameter syntax).
- Translates standard navbox parameters:
  * `title` / `judul`
  * `name` / `nama`
  * `above` / `atas`
  * `below` / `bawah`
  * `group1` / `kelompok1` ... `groupN` / `kelompokN`
  * `list1` / `daftar1` ... `listN` / `daftarN`
  * `state` / `status`
  * `image` / `gambar`
- Translates common navbox group labels (e.g. "Directed by" -> "Disutradarai oleh",
  "Films" -> "Film", "Television" -> "Televisi", "Cast" -> "Pemeran", "Awards" -> "Penghargaan").
- Resolves and maps internal wikilinks inside lists using WikiLinkMapper / default_link_mapper.
- Maps or adds standard categories: `[[Kategori:Templat navigasi ...]]`.
- Wraps in standard documentation tags `<noinclude>{{Dokumentasi}}</noinclude>`.
"""

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
import urllib.error
import urllib.parse
import urllib.request

from .wiki_client import PageNotFoundError, WikipediaClient
from .wiki_link_mapper import WikiLinkMapper, default_link_mapper


# Standard Navbox group name translations
STANDARD_GROUP_TRANSLATIONS: Dict[str, str] = {
    "directed by": "Disutradarai oleh",
    "director": "Sutradara",
    "directors": "Sutradara",
    "produced by": "Diproduseri oleh",
    "producer": "Produser",
    "producers": "Produser",
    "written by": "Ditulis oleh",
    "writer": "Penulis",
    "writers": "Penulis",
    "screenplay by": "Skenario oleh",
    "cast": "Pemeran",
    "starring": "Pemeran",
    "films": "Film",
    "feature films": "Film layar lebar",
    "short films": "Film pendek",
    "animated films": "Film animasi",
    "documentary films": "Film dokumenter",
    "documentaries": "Dokumenter",
    "television": "Televisi",
    "tv series": "Serial TV",
    "television series": "Serial televisi",
    "episodes": "Episode",
    "music": "Musik",
    "albums": "Album",
    "studio albums": "Album studio",
    "live albums": "Album rekaman langsung",
    "compilation albums": "Album kompilasi",
    "singles": "Singel",
    "songs": "Lagu",
    "discography": "Diskografi",
    "filmography": "Filmografi",
    "awards": "Penghargaan",
    "accolades": "Penghargaan",
    "related": "Terkait",
    "related articles": "Artikel terkait",
    "see also": "Lihat pula",
    "characters": "Karakter",
    "people": "Tokoh",
    "crew": "Kru",
    "novels": "Novel",
    "books": "Buku",
    "games": "Permainan",
    "video games": "Permainan video",
    "franchise": "Waralaba",
    "media": "Media",
}

# Standard parameter translation map (English -> Indonesian parameter names)
PARAM_TRANSLATION_MAP: Dict[str, str] = {
    "name": "nama",
    "title": "judul",
    "above": "atas",
    "below": "bawah",
    "state": "status",
    "image": "gambar",
    "imageleft": "gambarkiri",
}


class NavboxGenerator:
    """Auto-constructs Indonesian Wikipedia navigation box templates from English Wikipedia."""

    def __init__(
        self,
        en_client: Optional[WikipediaClient] = None,
        id_client: Optional[WikipediaClient] = None,
        link_mapper: Optional[WikiLinkMapper] = None,
    ):
        self.en_client = en_client or WikipediaClient(lang="en")
        self.id_client = id_client or WikipediaClient(lang="id")
        self.link_mapper = link_mapper or default_link_mapper

    def _normalize_template_title(self, name: str, default_prefix: str = "Template:") -> str:
        """Removes Template: or Templat: prefix and cleans title."""
        name = name.strip()
        name = re.sub(r"^(Template|Templat)\s*:\s*", "", name, flags=re.IGNORECASE)
        return name.strip()

    def check_template_exists_on_id(self, template_name: str) -> bool:
        """Checks if Templat:<Name> already exists on id.wikipedia.org."""
        norm_name = self._normalize_template_title(template_name)
        id_title = f"Templat:{norm_name}"
        try:
            # Quick check via ID client
            self.id_client.fetch_wikitext(id_title, check_disambiguation=False)
            return True
        except PageNotFoundError:
            return False
        except Exception:
            return False

    def fetch_en_navbox_wikitext(self, template_name: str) -> str:
        """Fetches raw wikitext for Template:<Name> from en.wikipedia."""
        norm_name = self._normalize_template_title(template_name)
        en_title = f"Template:{norm_name}"
        return self.en_client.fetch_wikitext(en_title, check_disambiguation=False)

    def translate_group_label(self, label: str) -> str:
        """Translates standard group labels like 'Directed by' -> 'Disutradarai oleh'."""
        clean_label = label.strip()
        lower_label = clean_label.lower()

        # Direct match
        if lower_label in STANDARD_GROUP_TRANSLATIONS:
            return STANDARD_GROUP_TRANSLATIONS[lower_label]

        # Case with link or formatting: e.g. "[[Film director|Directed by]]" or "'''Films'''"
        plain = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", clean_label)
        plain = re.sub(r"['*#]", "", plain).strip().lower()

        if plain in STANDARD_GROUP_TRANSLATIONS:
            trans = STANDARD_GROUP_TRANSLATIONS[plain]
            # If wrapped in bold, preserve bold
            if clean_label.startswith("'''") and clean_label.endswith("'''"):
                return f"'''{trans}'''"
            return trans

        return clean_label

    def _split_template_parameters(self, template_body: str) -> List[Tuple[str, str]]:
        """
        Parses top-level parameters of a template body into (param_name, param_value) tuples.
        Correctly respects nested {{...}} and [[...]].
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
                # Top level parameter boundary
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

    def convert_navbox(self, en_wikitext: str, template_name: str) -> str:
        """
        Converts English Navbox wikitext to Indonesian {{Kotak navigasi}} wikitext.
        Translates parameters, group labels, internal links, categories, and docs.
        """
        # 1. Extract the main {{Navbox ...}} template invocation
        match = re.search(r"\{\{\s*(?:Template:)?(?:Navbox|Kotak navigasi)\s*([\|\}].*?)\}\}\s*(?:<noinclude>.*?</noinclude>)?$", en_wikitext, flags=re.DOTALL | re.IGNORECASE)
        
        # If regex match didn't catch due to complex nesting, find balanced {{Navbox ...}}
        navbox_content = ""
        prefix_text = ""
        suffix_text = ""

        navbox_start = re.search(r"\{\{\s*(?:Template:)?(?:Navbox|Kotak navigasi)\s*\|", en_wikitext, flags=re.IGNORECASE)
        if navbox_start:
            start_idx = navbox_start.start()
            prefix_text = en_wikitext[:start_idx].strip()
            # Balanced bracket scan
            depth = 0
            end_idx = start_idx
            for i in range(start_idx, len(en_wikitext) - 1):
                if en_wikitext[i:i+2] == "{{":
                    depth += 1
                elif en_wikitext[i:i+2] == "}}":
                    depth -= 1
                    if depth == 0:
                        end_idx = i + 2
                        break
            navbox_full = en_wikitext[start_idx:end_idx]
            suffix_text = en_wikitext[end_idx:].strip()
            # Strip outer {{ and }}
            inner = navbox_full[2:-2].strip()
            # Remove leading "Navbox" or "Kotak navigasi"
            inner = re.sub(r"^(?:Template:)?(?:Navbox|Kotak navigasi)\s*\|\s*", "", inner, flags=re.IGNORECASE)
            navbox_content = inner
        else:
            # Fallback: whole wikitext or inner
            navbox_content = en_wikitext.strip()
            if navbox_content.startswith("{{") and navbox_content.endswith("}}"):
                navbox_content = navbox_content[2:-2].strip()
                navbox_content = re.sub(r"^(?:Template:)?(?:Navbox|Kotak navigasi)\s*\|\s*", "", navbox_content, flags=re.IGNORECASE)

        # 2. Parse top-level parameters
        raw_params = self._split_template_parameters(navbox_content)
        norm_name = self._normalize_template_title(template_name)

        converted_params: List[Tuple[str, str]] = []
        for name, val in raw_params:
            if not name:
                continue
            lower_name = name.lower()

            # Translate parameter key
            new_key = PARAM_TRANSLATION_MAP.get(lower_name, lower_name)

            # Check groupN / kelompokN
            group_match = re.match(r"^group(\d+)$", lower_name)
            list_match = re.match(r"^list(\d+)$", lower_name)

            if group_match:
                new_key = f"kelompok{group_match.group(1)}"
                val = self.translate_group_label(val)
            elif list_match:
                new_key = f"daftar{list_match.group(1)}"
                # Translate wikilinks inside lists
                val = self.link_mapper.map_wikilinks(val)
            elif lower_name == "name" or new_key == "nama":
                # Ensure name matches Indonesian template name
                val = norm_name
            elif lower_name == "title" or new_key == "judul":
                val = self.link_mapper.map_wikilinks(val)
            elif lower_name in ("above", "below") or new_key in ("atas", "bawah"):
                val = self.link_mapper.map_wikilinks(val)

            converted_params.append((new_key, val))

        # 3. Assemble {{Kotak navigasi}} wikitext
        lines = ["{{Kotak navigasi"]
        for k, v in converted_params:
            if "\n" in v:
                lines.append(f"| {k} = \n{v}")
            else:
                lines.append(f"| {k} = {v}")
        lines.append("}}")
        result_wikitext = "\n".join(lines)

        # 4. Handle categories in suffix or add default navigation template category
        cat_lines: List[str] = []
        # Find any existing categories in the original wikitext
        existing_cats = re.findall(r"\[\[Category:\s*([^\]]+)\]\]", en_wikitext, flags=re.IGNORECASE)
        if existing_cats:
            for cat in existing_cats:
                cat_clean = cat.strip()
                # Map category via link mapper
                mapped_cat = self.link_mapper.map_categories(f"[[Category:{cat_clean}]]")
                if mapped_cat and "Kategori:" in mapped_cat:
                    cat_lines.append(mapped_cat)
        
        # If no specific navigation categories found, add default category
        has_navbox_cat = any("Templat navigasi" in c for c in cat_lines)
        if not has_navbox_cat:
            cat_lines.append("[[Kategori:Templat navigasi]]")

        # 5. Add standard documentation wrap (Dokumentasi navbox) and preserve DEFAULTSORT
        defaultsort_m = re.search(r"\{\{\s*DEFAULTSORT\s*:\s*([^}]+)\}\}", en_wikitext, re.IGNORECASE)
        defaultsort_block = f"\n{{{{DEFAULTSORT:{defaultsort_m.group(1).strip()}}}}}" if defaultsort_m else ""

        cats_formatted = "\n".join(cat_lines)
        doc_block = f"<noinclude>\n{{{{Dokumentasi navbox}}}}{defaultsort_block}\n{cats_formatted}\n</noinclude>"

        return f"{result_wikitext}\n{doc_block}".strip()

    def generate_navbox(
        self, en_template_name: str, check_existence: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Generates Indonesian navbox dictionary given English template name.

        Returns:
        {
            "template_name": str,
            "id_title": str,
            "wikitext": str,
            "already_exists": bool
        }
        """
        norm_name = self._normalize_template_title(en_template_name)
        id_title = f"Templat:{norm_name}"

        already_exists = False
        if check_existence:
            already_exists = self.check_template_exists_on_id(norm_name)

        # Fetch English wikitext
        try:
            en_wikitext = self.fetch_en_navbox_wikitext(norm_name)
        except Exception as e:
            raise RuntimeError(f"Failed to fetch template 'Template:{norm_name}' from en.wikipedia: {e}") from e

        # Convert wikitext
        converted = self.convert_navbox(en_wikitext, norm_name)

        return {
            "template_name": norm_name,
            "id_title": id_title,
            "wikitext": converted,
            "already_exists": already_exists,
        }

    def save_navbox(self, navbox_info: Dict[str, Any], output_dir: Path) -> Path:
        """
        Saves navbox to output_dir/templates/<SafeName>.wikitext.

        Returns saved file Path.
        """
        out_dir = Path(output_dir)
        target_dir = out_dir / "templates"
        target_dir.mkdir(parents=True, exist_ok=True)

        template_name = navbox_info.get("template_name", "navbox")
        wikitext = navbox_info.get("wikitext", "")

        safe_name = re.sub(r'[\\/*?:"<>|]', "_", template_name).strip()
        if not safe_name:
            safe_name = "navbox"

        file_path = target_dir / f"{safe_name}.wikitext"
        file_path.write_text(wikitext, encoding="utf-8")
        return file_path


default_navbox_generator = NavboxGenerator()
