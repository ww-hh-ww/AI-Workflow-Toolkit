"""Plan semantic documents.

.aiwf/state/plans.json is the Plan machine index.
.aiwf/plans/<PLAN-ID>.md is the Plan semantic document.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
import json

VALID_PLAN_SECTIONS = {
    # V2 sections
    "strategy": "Strategy",
    "scope": "Scope",
    "risks": "Risks",
    "verification": "Verification",
    "done-means": "Done Means",
    # Legacy sections (still valid)
    "goal": "Goal",
    "route": "Route",
    "decision": "Current Decision",
    "impact": "Impact",
    "docs-assets": "Impact",
    "goal-progress": "Goal Progress",
    "next-steps": "Next Steps",
}

# Retired V1 section aliases accepted only when editing old artifacts.
SECTION_COMPAT = {
    "open-questions": "goal",
    "decisions": "decision",
    "implementation": "route",
    "testing": "verification",
    "review": "verification",
    "evidence": "verification",
    "checklist": "next-steps",
}

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _plans_dir(base_dir: str) -> Path:
    return Path(base_dir) / ".aiwf" / "plans"

def _safe_task_id(task_id: str) -> str:
    cleaned = "".join(ch for ch in task_id.strip() if ch.isalnum() or ch in ("-", "_", "."))
    if not cleaned:
        raise ValueError("task_id is required")
    return cleaned

def plan_path(base_dir: str, task_id: str) -> Path:
    return _plans_dir(base_dir) / f"{_safe_task_id(task_id)}.md"

def _resolve_plan_artifact_id(base_dir: str, plan_or_task_id: str) -> str:
    """Resolve the requested Plan artifact id.

    The runtime contract is PLAN-ID first. The PLAN-<TASK-ID> branch exists only
    for artifacts created by the current registry-backed --task-id command.
    """
    requested = _safe_task_id(plan_or_task_id)
    legacy_mapped = f"PLAN-{requested}"
    if plan_path(base_dir, legacy_mapped).exists():
        return legacy_mapped
    if plan_path(base_dir, requested).exists():
        return requested
    return requested

def create_task_plan(
    base_dir: str,
    plan_id: str = "",
    goal_id: str = "",
    title: str = "",
    milestone_id: str = "",
    task_ids: Optional[List[str]] = None,
) -> Dict[str, object]:
    effective_plan_id = _safe_task_id(plan_id)
    attached_tasks = list(dict.fromkeys(task_ids or []))

    path = plan_path(base_dir, effective_plan_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    created = not path.exists()
    try:
        from .state.plan_ops import upsert_plan
        upsert_plan(base_dir, effective_plan_id, goal_id=goal_id, task_ids=attached_tasks,
                    status="open", title=title or effective_plan_id,
                    milestone_id=milestone_id)
    except ValueError:
        raise
    except Exception as exc:
        return {"path": str(path), "created": False, "error": str(exc),
                "plan_id": effective_plan_id}
    if created:
        from .index_ops import create_narrative_for_entity
        doc_path = create_narrative_for_entity(
            base_dir,
            effective_plan_id,
            "plan",
            title=title or effective_plan_id,
            goal_id=goal_id,
            milestone_id=milestone_id,
        )
        from .state.plan_ops import load_plans, save_plans

        plans = load_plans(base_dir)
        for plan in plans.get("plans", []) or []:
            if plan.get("plan_id") == effective_plan_id or plan.get("id") == effective_plan_id:
                plan["doc_path"] = doc_path
                break
        save_plans(base_dir, plans)
    return {
        "path": str(path), "created": created, "plan_id": effective_plan_id,
        "task_ids": attached_tasks, "milestone_id": milestone_id, "goal_id": goal_id,
    }

def load_task_plan(base_dir: str, task_id: str) -> str:
    path = plan_path(base_dir, _resolve_plan_artifact_id(base_dir, task_id))
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")

def _replace_section(text: str, section_title: str, content: str) -> str:
    import re
    pattern = rf"(## {re.escape(section_title)}\n)(.*?)(?=\n## |\Z)"
    body = content.strip()
    new_text, count = re.subn(
        pattern,
        lambda match: f"{match.group(1)}{body}\n",
        text,
        flags=re.DOTALL,
    )
    if count:
        return new_text
    return text.rstrip() + f"\n\n## {section_title}\n{body}\n"

def list_task_plans(base_dir: str) -> List[Dict[str, object]]:
    root = _plans_dir(base_dir)
    if not root.exists():
        return []
    plans = []
    registry = {}
    try:
        from .state.plan_ops import load_plans
        registry = {p.get("plan_id"): p for p in load_plans(base_dir).get("plans", []) if isinstance(p, dict)}
    except Exception:
        registry = {}
    for path in sorted(root.glob("*.md")):
        plan_id = path.stem
        entry = registry.get(plan_id, {})
        plans.append({"task_id": plan_id, "plan_id": plan_id, "path": str(path),
                      "registry": bool(entry), "task_ids": entry.get("task_ids", []) if entry else []})
    return plans
