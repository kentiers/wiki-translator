"""Materialize reviewed category plans as local idwiki wikitext drafts."""

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re
from typing import Any, Callable, Dict, List, Optional

from .category_creator import CategoryCreationPlan
from .category_reconciler import ID_API_URL
from .http_client import MediaWikiApiClient
from .approval_journal import ApprovalManifest, TransactionJournal


@dataclass
class CategoryMaterializationResult:
    title: str
    wikitext: str
    output_path: str
    publication_ready: bool
    required_dependencies: List[str] = field(default_factory=list)
    required_parent_categories: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    approval_manifest_path: str = ""
    journal_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CategoryMaterializer:
    """Adapt a creation plan without publishing or overwriting wiki pages."""

    def __init__(
        self,
        id_client: Optional[MediaWikiApiClient] = None,
        translate_plain_text: Optional[Callable[[str], str]] = None,
    ) -> None:
        self.id_client = id_client or MediaWikiApiClient(api_url=ID_API_URL)
        self.translate_plain_text = translate_plain_text

    @staticmethod
    def _local_invocation_name(title: str) -> str:
        return re.sub(r"^(?:Template|Templat|Module|Modul):", "", title, flags=re.IGNORECASE)

    @staticmethod
    def _fallback_parent_title(en_title: str) -> Optional[str]:
        match = re.fullmatch(r"Category:Works by (.+)", en_title, flags=re.IGNORECASE)
        return f"Kategori:Karya {match.group(1)}" if match else None

    def _translated_parent_fallback(
        self, en_title: str, blockers: List[str]
    ) -> Optional[str]:
        """Translate the descriptive part; never silently keep English prose."""
        match = re.fullmatch(r"Category:Works by (.+)", en_title, flags=re.IGNORECASE)
        if not match:
            return None
        source = match.group(1).strip()
        if self.translate_plain_text:
            try:
                translated = self.translate_plain_text(source).strip()
            except Exception:
                translated = ""
            if translated and translated.casefold() != source.casefold():
                return f"Kategori:Karya {translated}"
        # A single token is usually a proper name (e.g. a person), but a
        # multi-word unchanged phrase is English prose and must be reviewed.
        if " " not in source:
            return f"Kategori:Karya {source}"
        blockers.append(f"Untranslated parent category: {en_title}")
        return None

    def _translate_plain_lines(self, wikitext: str, warnings: List[str]) -> str:
        output: List[str] = []
        for line in wikitext.splitlines():
            stripped = line.strip()
            is_plain = bool(stripped) and not any(
                marker in stripped for marker in ("{{", "}}", "[[", "]]", "<", ">", "__")
            )
            if not is_plain:
                output.append(line)
            elif self.translate_plain_text:
                translated = self.translate_plain_text(stripped).strip()
                if not translated:
                    raise ValueError("Gemini returned an empty category prose translation")
                output.append(translated)
            else:
                warnings.append(f"Untranslated category prose: {stripped}")
                output.append(line)
        return "\n".join(output)

    def _validate(self, title: str, wikitext: str) -> List[str]:
        payload, error = self.id_client.post(
            {
                "action": "parse",
                "title": title,
                "text": wikitext,
                "contentmodel": "wikitext",
                "prop": "text|categories|templates",
                "disablelimitreport": "1",
                "formatversion": "2",
            }
        )
        if error:
            return [f"Parse validation failed: {error}"]
        if not payload or payload.get("error") or "parse" not in payload:
            info = (payload or {}).get("error", {}).get("info", "invalid parse response")
            return [f"Parse validation failed: {info}"]
        return [
            f"MediaWiki parse warning ({name}): {value.get('*', value)}"
            for name, value in payload.get("warnings", {}).items()
        ]

    def materialize(
        self,
        plan: CategoryCreationPlan,
        output_dir: Path,
        parent_overrides: Optional[Dict[str, str]] = None,
    ) -> CategoryMaterializationResult:
        if plan.target_exists:
            raise ValueError(f"Target category already exists: {plan.id_category}")

        overrides = parent_overrides or {}
        blockers = [
            f"Unresolved dependency: {item.en_title}"
            for item in plan.dependencies
            if not item.id_title
        ]
        required_dependencies = [
            item.id_title
            for item in plan.dependencies
            if item.id_title and not item.exists_on_id
        ]

        parent_titles: List[tuple[str, str]] = []
        required_parents: List[str] = []
        warnings: List[str] = []
        for parent in plan.parent_categories:
            target = parent.id_title or overrides.get(parent.en_title)
            if not target:
                target = self._translated_parent_fallback(parent.en_title, blockers)
            if not target:
                if not any(parent.en_title in item for item in blockers):
                    blockers.append(f"Unresolved parent category: {parent.en_title}")
                continue
            if not target.lower().startswith("kategori:"):
                target = f"Kategori:{target}"
            sort_key = parent.sort_key
            if sort_key and self.translate_plain_text:
                try:
                    translated_sort_key = self.translate_plain_text(sort_key).strip()
                except Exception as exc:
                    translated_sort_key = ""
                    blockers.append(f"Parent sort key translation failed ({parent.en_title}): {exc}")
                if translated_sort_key:
                    sort_key = translated_sort_key
            elif sort_key:
                warnings.append(f"Untranslated category sort key: {sort_key}")
            if target not in [title for title, _ in parent_titles]:
                parent_titles.append((target, sort_key))
            if not parent.exists_on_id:
                required_parents.append(target)

        body = re.sub(
            r"\n?\[\[\s*(?:Category|Kategori)\s*:[^\]]+\]\]",
            "",
            plan.source_wikitext,
            flags=re.IGNORECASE,
        ).strip()

        for dependency in plan.dependencies:
            if not dependency.id_title:
                continue
            local_name = self._local_invocation_name(dependency.id_title)
            if dependency.kind == "module":
                source_name = self._local_invocation_name(dependency.en_title)
                body = re.sub(
                    rf"(#invoke\s*:\s*){re.escape(source_name)}(?=\s*[|}}])",
                    rf"\g<1>{local_name}",
                    body,
                    flags=re.IGNORECASE,
                )
            else:
                source_name = self._local_invocation_name(dependency.en_title)
                body = re.sub(
                    rf"(\{{\{{\s*){re.escape(source_name)}(?=\s*[|}}])",
                    rf"\g<1>{local_name}",
                    body,
                    flags=re.IGNORECASE,
                )

        body = self._translate_plain_lines(body, warnings)
        category_lines = [
            f"[[{title}|{sort_key}]]" if sort_key else f"[[{title}]]"
            for title, sort_key in parent_titles
        ]
        wikitext = "\n".join(part for part in (body, "\n".join(category_lines)) if part).strip() + "\n"
        warnings.extend(self._validate(plan.id_category, wikitext))

        publication_ready = not blockers and not required_dependencies and not required_parents and not warnings
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r'[\\/*?:"<>|]+', "_", plan.id_category)
        output_path = output_dir / f"{safe_name}.wikitext"
        result = CategoryMaterializationResult(
            title=plan.id_category,
            wikitext=wikitext,
            output_path=str(output_path),
            publication_ready=publication_ready,
            required_dependencies=required_dependencies,
            required_parent_categories=required_parents,
            blockers=blockers,
            warnings=warnings,
        )
        output_path.write_text(wikitext, encoding="utf-8")
        report_path = output_path.with_suffix(".json")
        manifest_path = output_path.with_name("approval-manifest.json")
        journal_path = output_path.with_name("transaction-journal.jsonl")
        result.approval_manifest_path = str(manifest_path)
        result.journal_path = str(journal_path)
        ApprovalManifest.create(f"category:{plan.id_category}", [output_path]).write(manifest_path)
        journal = TransactionJournal(journal_path)
        journal.record(plan.id_category, "materialized", output=str(output_path), publication_ready=result.publication_ready)
        report_path.write_text(
            json.dumps(
                {"source": plan.to_dict(), "materialization": result.to_dict()},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return result


default_category_materializer = CategoryMaterializer()
