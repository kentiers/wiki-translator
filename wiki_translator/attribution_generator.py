"""
Wikimedia Talk Page Attribution Generator for CC-BY-SA Translation Compliance.

Generates official Talk Page (Halaman Pembicaraan) wikitext attribution as strictly mandated
by the Wikimedia Foundation Terms of Use when translating between language editions:
    {{Translated page|en|Source Article Title|version=OldRevisionID}}

Features:
- Standard {{Translated page}} banner with English source title and revision ID (oldid).
- Optional ProyekWiki banners integration (disabled by default).
- Timestamped translation record and contributor note.
- Topic-to-ProyekWiki banner mappings.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional


TOPIC_PROYEK_WIKI_MAP: Dict[str, str] = {
    "film": "{{ProyekWiki Film}}",
    "cinema": "{{ProyekWiki Film}}",
    "tv_series": "{{ProyekWiki Televisi}}",
    "television": "{{ProyekWiki Televisi}}",
    "entertainment": "{{ProyekWiki Hiburan}}",
    "media": "{{ProyekWiki Media}}",
    "computing_science": "{{ProyekWiki Komputasi}}\n{{ProyekWiki Sains}}",
    "physics_mathematics": "{{ProyekWiki Fisika}}\n{{ProyekWiki Matematika}}\n{{ProyekWiki Sains}}",
    "medical_biology": "{{ProyekWiki Biologi}}\n{{ProyekWiki Kedokteran}}\n{{ProyekWiki Sains}}",
    "history_social": "{{ProyekWiki Sejarah}}",
}


@dataclass
class AttributionMetadata:
    en_title: str
    id_title: str
    oldid: Optional[int] = None
    topic: Optional[str] = None
    timestamp: Optional[datetime] = None


class TalkPageAttributionGenerator:
    """
    Generates compliant Wikimedia talk page wikitext containing translation attribution,
    revision oldid, ProyekWiki banners, and audit notes.
    """

    def __init__(self):
        pass

    def generate_attribution_template(
        self, en_title: str, oldid: Optional[int] = None, insertversion: Optional[int] = None
    ) -> str:
        """
        Generates the standard {{Translated page}} banner for Indonesian Wikipedia.
        Format: {{Translated page|en|English Title|version=123456}}
        """
        clean_en_title = en_title.replace("_", " ").strip()
        parts = ["Translated page", "en", clean_en_title]
        if oldid:
            parts.append(f"version={oldid}")
        if insertversion:
            parts.append(f"insertversion={insertversion}")

        return "{{" + "|".join(parts) + "}}"
    def get_proyek_wiki_banners(self, topic: Optional[str] = None) -> List[str]:
        """Returns standard ProyekWiki banners for the given topic."""
        banners = ["{{ProyekWiki Terjemahan}}"]
        if topic:
            clean_topic = topic.strip().lower()
            if clean_topic in TOPIC_PROYEK_WIKI_MAP:
                custom_banners = TOPIC_PROYEK_WIKI_MAP[clean_topic].split("\n")
                banners.extend(custom_banners)
        return banners

    def generate_talk_page(
        self,
        en_title: str,
        id_title: str,
        oldid: Optional[int] = None,
        topic: Optional[str] = None,
        notes: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        include_proyek_wiki: bool = False,
        clean_banner_only: bool = True,
    ) -> str:
        """
        Generates compliant Halaman Pembicaraan wikitext content.
        By default (clean_banner_only=True without custom notes), produces the clean,
        authoritative Wikimedia translation banner ({{Translated page|en|...}}) preferred by
        Indonesian Wikipedia editors without cluttering talk pages with redundant self-threads.
        """
        now = timestamp or datetime.now(timezone.utc)
        date_str = now.strftime("%d %B %Y %H:%M UTC")

        # 1. Main translation attribution template
        attr_template = self.generate_attribution_template(en_title=en_title, oldid=oldid)

        # 2. Formatted talk page sections
        lines = []
        if include_proyek_wiki:
            banners = self.get_proyek_wiki_banners(topic)
            lines.append("\n".join(banners))

        lines.append(attr_template)
        if clean_banner_only and not notes:
            return "\n".join(lines).strip() + "\n"

        lines.append("")
        lines.append("== Terjemahan Artikel ==")
        lines.append(f"Artikel ini diterjemahkan sebagian atau seluruhnya dari artikel Wikipedia bahasa Inggris [[:en:{en_title}|{en_title}]].")

        if oldid:
            lines.append(f"* '''Revisi sumber (oldid):''' [https://en.wikipedia.org/w/index.php?oldid={oldid} {oldid}]")
        else:
            lines.append(f"* '''Revisi sumber:''' Versi mutakhir dari [[:en:{en_title}]]")

        lines.append(f"* '''Waktu penerjemahan:''' {date_str}")
        lines.append("* '''Lisensi:''' Konten dilisensikan di bawah Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0) dan GFDL.")

        if notes:
            lines.append(f"* '''Catatan penerjemah:''' {notes.strip()}")

        lines.append("\n~~~~")

        return "\n".join(lines).strip() + "\n"


default_attribution_generator = TalkPageAttributionGenerator()
