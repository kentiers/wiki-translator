"""Sandbox-only deployment planning for template/module dependency graphs."""

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .template_ecosystem import RecursiveDependencyScanner, SandboxTestcaseEngine
from .template_syncer import TemplateSyncer
from .approval_journal import ApprovalManifest, TransactionJournal


@dataclass
class DependencyDeploymentResult:
    root_title: str
    report_path: str = ""
    order: List[str] = field(default_factory=list)
    reused: List[str] = field(default_factory=list)
    drafted: List[str] = field(default_factory=list)
    blocked: List[str] = field(default_factory=list)
    artifacts: Dict[str, Dict[str, str]] = field(default_factory=dict)
    validation: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DependencyDeployer:
    """Materialize missing dependencies locally, with publication disabled."""

    def __init__(
        self,
        scanner: Optional[RecursiveDependencyScanner] = None,
        template_syncer: Optional[TemplateSyncer] = None,
        sandbox_engine: Optional[SandboxTestcaseEngine] = None,
    ) -> None:
        self.scanner = scanner or RecursiveDependencyScanner()
        self.template_syncer = template_syncer or TemplateSyncer()
        self.sandbox_engine = sandbox_engine or SandboxTestcaseEngine()

    @staticmethod
    def _module_filename(title: str) -> str:
        return title.replace("Module:", "").replace("/", "_").replace(" ", "_")

    def deploy(
        self,
        root_title: str,
        output_dir: Optional[Path] = None,
        max_depth: int = 5,
        resume: bool = True,
    ) -> DependencyDeploymentResult:
        normalized_root = self.scanner.normalize_title(root_title)
        safe_root = normalized_root.replace(":", "_").replace("/", "_").replace(" ", "_")
        target_dir = Path(output_dir or "output/dependencies") / safe_root
        target_dir.mkdir(parents=True, exist_ok=True)
        report_path = target_dir / "deployment-report.json"
        journal = TransactionJournal(target_dir / "transaction-journal.jsonl")
        previous = journal.latest() if resume else {}
        if self.scanner.check_existence_on_idwiki(normalized_root):
            result = DependencyDeploymentResult(
                root_title=normalized_root,
                report_path=str(report_path),
                order=[normalized_root],
                reused=[normalized_root],
            )
            journal.record(normalized_root, "reused")
            report_path.write_text(
                json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return result

        nodes = self.scanner.scan_dependencies_recursive(normalized_root, max_depth=max_depth, fetch_from_en=True)
        relevant: set[str] = set()

        def collect(title: str) -> None:
            if title in relevant or title not in nodes:
                return
            relevant.add(title)
            node = nodes[title]
            if node.exists_on_id:
                return
            for dependency in node.dependencies:
                collect(self.scanner.normalize_title(dependency))

        collect(normalized_root)
        order = [title for title in self.scanner.topological_sort(nodes) if title in relevant]
        result = DependencyDeploymentResult(
            root_title=normalized_root, report_path=str(report_path), order=order
        )
        available = {title for title, node in nodes.items() if node.exists_on_id}

        for title in order:
            node = nodes[title]
            if previous.get(title, {}).get("status") == "drafted":
                result.drafted.append(title)
                available.add(title)
                continue
            journal.record(title, "planned")
            if node.exists_on_id:
                result.reused.append(title)
                available.add(title)
                journal.record(title, "reused")
                continue
            missing = [dep for dep in node.missing_dependencies if dep not in available]
            if missing:
                result.blocked.append(f"{title}: unresolved dependencies: {', '.join(missing)}")
                journal.record(title, "blocked", reason=result.blocked[-1])
                continue
            try:
                draft_wikitext = ""
                if title.startswith("Template:"):
                    sync = self.template_syncer.sync_template(
                        title,
                        id_template_name=title.replace("Template:", "", 1),
                        publish=False,
                        output_dir=target_dir / "templates",
                        link_wikidata=False,
                    )
                    result.artifacts[title] = {
                        "template": str(sync["template_file"]),
                        "doc": str(sync["doc_file"]),
                    }
                    draft_wikitext = sync["wikitext"]
                elif title.startswith("Module:"):
                    path = target_dir / "modules" / f"{self._module_filename(title)}.lua"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(node.content or "", encoding="utf-8")
                    result.artifacts[title] = {"module": str(path)}
                    draft_wikitext = node.content or ""
                else:
                    result.blocked.append(f"{title}: unsupported dependency kind")
                    journal.record(title, "blocked", reason=result.blocked[-1])
                    continue
                validation = self.sandbox_engine.simulate_parse(title, draft_wikitext)
                passed, reason = self.sandbox_engine.evaluate_promotion_gate(validation)
                if validation.has_missing_template:
                    passed = False
                    reason = "Promotion blocked: missing template transclusion detected"
                result.validation[title] = {
                    "passed": passed,
                    "reason": reason,
                    "errors": list(validation.errors),
                    "warnings": list(validation.warnings),
                }
                if not passed:
                    result.blocked.append(f"{title}: {reason}")
                    journal.record(title, "blocked", reason=reason)
                    continue
                result.drafted.append(title)
                available.add(title)
                journal.record(title, "drafted", artifacts=result.artifacts.get(title, {}))
            except Exception as exc:
                result.blocked.append(f"{title}: {exc}")
                journal.record(title, "blocked", reason=str(exc))
        report_path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        artifact_paths = [Path(path) for artifact in result.artifacts.values() for path in artifact.values()]
        ApprovalManifest.create(f"dependency:{normalized_root}", artifact_paths).write(
            target_dir / "approval-manifest.json"
        )
        return result


default_dependency_deployer = DependencyDeployer()
