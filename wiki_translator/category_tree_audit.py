"""Read-only category tree planning and enwiki/idwiki membership audits."""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set

from .category_creator import CategoryCreationPlan, CategoryCreationPlanner
from .category_reconciler import CategoryCandidate, CategoryReconciler


@dataclass
class CategoryTreeNode:
    en_category: str
    id_category: Optional[str]
    depth: int
    target_exists: bool
    blockers: List[str] = field(default_factory=list)
    parent_nodes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CategoryTreePlan:
    root: str
    nodes: List[CategoryTreeNode] = field(default_factory=list)
    cycles: List[str] = field(default_factory=list)
    truncated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root": self.root,
            "nodes": [node.to_dict() for node in self.nodes],
            "cycles": list(self.cycles),
            "truncated": self.truncated,
        }


@dataclass
class CategoryDiffAudit:
    en_category: str
    id_category: str
    expected_articles: List[CategoryCandidate] = field(default_factory=list)
    missing_articles: List[CategoryCandidate] = field(default_factory=list)
    extra_id_articles: List[str] = field(default_factory=list)
    en_subcategories: List[str] = field(default_factory=list)
    id_subcategories: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["expected_articles"] = [asdict(item) for item in self.expected_articles]
        result["missing_articles"] = [asdict(item) for item in self.missing_articles]
        return result


class CategoryTreePlanner:
    """Plan one creation node per category; never flatten subcategories."""

    def __init__(self, planner: Optional[CategoryCreationPlanner] = None) -> None:
        self.planner = planner or CategoryCreationPlanner()

    def build_plan(self, en_category: str, id_category: Optional[str] = None, max_depth: int = 2, max_nodes: int = 25) -> CategoryTreePlan:
        root = CategoryReconciler._category_title(en_category, "en")
        root_id = CategoryReconciler._category_title(id_category, "id") if id_category else None
        result = CategoryTreePlan(root=root)
        seen: Set[str] = set()

        def visit(current_en: str, current_id: Optional[str], depth: int) -> None:
            key = current_en.casefold()
            if key in seen:
                result.cycles.append(current_en)
                return
            if len(result.nodes) >= max_nodes:
                result.truncated = True
                return
            seen.add(key)
            if current_id:
                plan = self.planner.build_plan(current_en, current_id)
                blockers = list(plan.blockers)
                mapped_parents = [(parent.en_title, parent.id_title) for parent in plan.parent_categories]
                node = CategoryTreeNode(current_en, current_id, depth, plan.target_exists, blockers)
                node.parent_nodes = [en for en, _ in mapped_parents]
                result.nodes.append(node)
                if depth >= max_depth:
                    return
                for parent_en, parent_id in mapped_parents:
                    if parent_id:
                        visit(parent_en, parent_id, depth + 1)
            else:
                parents = self.planner._fetch_rendered_parents(current_en)
                node = CategoryTreeNode(current_en, None, depth, False, [f"Unresolved idwiki category: {current_en}"])
                node.parent_nodes = parents
                result.nodes.append(node)
                if depth >= max_depth:
                    return
                mappings = self.planner._resolve_id_titles(parents)
                for parent_en in parents:
                    visit(parent_en, mappings.get(parent_en), depth + 1)

        visit(root, root_id, 0)
        return result


class CategoryDiffAuditor:
    """Compare direct article membership without proposing automatic removal."""

    def __init__(self, reconciler: Optional[CategoryReconciler] = None) -> None:
        self.reconciler = reconciler or CategoryReconciler()

    def audit(self, en_category: str, id_category: str, limit: int = 500) -> CategoryDiffAudit:
        en_category = self.reconciler._category_title(en_category, "en")
        id_category = self.reconciler._category_title(id_category, "id")
        en_articles, en_subcats = self.reconciler._fetch_members(self.reconciler.en_client, en_category, False)
        id_articles, id_subcats = self.reconciler._fetch_members(self.reconciler.id_client, id_category, False)
        resolved, _ = self.reconciler._resolve_id_titles(en_articles[:limit])
        id_folded = {title.casefold() for title in id_articles}
        expected = list(resolved)
        missing = [item for item in expected if item.id_title.casefold() not in id_folded]
        expected_folded = {item.id_title.casefold() for item in expected}
        extra = [title for title in id_articles if title.casefold() not in expected_folded]
        return CategoryDiffAudit(
            en_category=en_category,
            id_category=id_category,
            expected_articles=expected,
            missing_articles=missing,
            extra_id_articles=extra,
            en_subcategories=en_subcats,
            id_subcategories=id_subcats,
        )


default_category_tree_planner = CategoryTreePlanner()
default_category_diff_auditor = CategoryDiffAuditor()
