"""AIWF Project Map — human direction plus machine Goal-to-module bindings."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_MAP = """# Project Map

> **What It Is**: Planner TODO — one sentence. A user who knows nothing about this project should understand what it does.

> **How It Works**: Planner TODO — one paragraph. An engineer who has never seen this codebase should know where to start: which directories do what, which files are the entry points, and which design decisions shape the architecture. Do not list every file. Describe boundaries, not contents.

## One-line Overview
- Planner TODO: inspect the project and summarize what it does in one sentence.

## Technical Stack
- Planner TODO: identify languages, frameworks, storage, test tools, and runtime assumptions from source files.

## Project Structure
- Planner TODO: describe the important directories/modules and their responsibilities.

## Capability to Module Map
- Machine authority: `.aiwf/assets/project-map.json` → `goal_bindings`.
- Human projection: this file (`.aiwf/artifacts/reports/项目地图.md`) explains the map.
- User/agent entrypoints: `aiwf project-map relations`, `aiwf project-map validate`, and `aiwf project-map show`.
- Do not duplicate the full file tree here.

## Architecture Layers
- Planner TODO: explain the major layers, entry points, data flow, and boundary rules.

## Project Snapshot
- Planner TODO: concise current-state snapshot based on real project inspection.

## Current Stage
- Planner TODO: current lifecycle stage and readiness.

## Completed Milestones
- None yet.

## Architecture Direction
- Planner TODO: intended structural direction, constraints, and seams to preserve.

## Next Candidate Tasks
- None yet.

## Environment Summary
- Planner TODO: environment requirements, local setup, generated files, and operational assumptions.

## Deferred Risks
- None yet.

## Cleanup Candidates
- None yet.

## Open Decisions
- None yet.

## Not-now / Rejected Routes
- None yet.
"""

SECTION_MAP = {
    "snapshot": "Project Snapshot",
    "current-stage": "Current Stage",
    "completed-milestones": "Completed Milestones",
    "next-candidate-tasks": "Next Candidate Tasks",
    "architecture-direction": "Architecture Direction",
    "environment-summary": "Environment Summary",
    "open-decisions": "Open Decisions",
    "deferred-risks": "Deferred Risks",
    "cleanup-candidates": "Cleanup Candidates",
    "rejected-routes": "Not-now / Rejected Routes",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(project_root: str) -> Path:
    return Path(project_root) / ".aiwf" / "artifacts" / "reports" / "项目地图.md"


def _asset_path(project_root: str) -> Path:
    return Path(project_root) / ".aiwf" / "assets" / "project-map.json"


def _normalize_repo_path(value: str) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    if not raw:
        raise ValueError("project-map path must not be empty")
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"project-map path must be repository-relative: {value}")
    normalized = path.as_posix().lstrip("./")
    if not normalized:
        raise ValueError("project-map path must not resolve to project root")
    return normalized


def _load_machine_map(project_root: str, create: bool = False) -> Dict[str, Any]:
    path = _asset_path(project_root)
    if not path.exists() and create:
        from ..assets.schema import init_assets
        init_assets(project_root)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"invalid project-map.json: {exc}") from exc
    data.setdefault("goal_bindings", [])
    return data


def _write_machine_map(project_root: str, data: Dict[str, Any]) -> None:
    path = _asset_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def bind_goal_modules(
    project_root: str,
    goal_id: str,
    module_paths: List[str],
    entrypoints: Optional[List[str]] = None,
    interfaces: Optional[List[str]] = None,
    note: str = "",
) -> Dict[str, Any]:
    """Create or replace one Goal's curated code ownership binding."""
    from .state.goal_tree_ops import goal_exists

    goal_id = str(goal_id or "").strip()
    if not goal_id or not goal_exists(project_root, goal_id):
        raise ValueError(f"goal not found: {goal_id or '<empty>'}")
    modules = sorted(set(_normalize_repo_path(p) for p in (module_paths or [])))
    entries = sorted(set(_normalize_repo_path(p) for p in (entrypoints or [])))
    if not modules:
        raise ValueError("at least one --module path is required")

    root = Path(project_root).resolve()
    missing = [p for p in modules + entries if not (root / p).exists()]
    if missing:
        raise ValueError(f"project-map paths do not exist: {', '.join(missing)}")

    data = _load_machine_map(project_root, create=True)
    bindings = [
        item for item in data.get("goal_bindings", []) or []
        if isinstance(item, dict) and item.get("goal_id") != goal_id
    ]
    binding = {
        "goal_id": goal_id,
        "module_paths": modules,
        "entrypoints": entries,
        "interfaces": sorted(set(str(v).strip() for v in (interfaces or []) if str(v).strip())),
        "note": str(note or "").strip(),
        "updated_at": _now(),
    }
    bindings.append(binding)
    bindings.sort(key=lambda item: str(item.get("goal_id", "")))
    data["goal_bindings"] = bindings
    _write_machine_map(project_root, data)
    return binding


def unbind_goal_modules(project_root: str, goal_id: str, reason: str) -> Dict[str, Any]:
    """Remove a Goal binding with an explicit audit reason."""
    if not str(reason or "").strip():
        raise ValueError("--reason is required when removing a Goal binding")
    data = _load_machine_map(project_root, create=False)
    if not data:
        raise ValueError("project-map.json not found; run aiwf asset init")
    bindings = data.get("goal_bindings", []) or []
    kept = [item for item in bindings if not isinstance(item, dict) or item.get("goal_id") != goal_id]
    if len(kept) == len(bindings):
        raise ValueError(f"goal binding not found: {goal_id}")
    data["goal_bindings"] = kept
    history = data.setdefault("goal_binding_history", [])
    history.append({
        "action": "remove",
        "goal_id": goal_id,
        "reason": str(reason).strip(),
        "recorded_at": _now(),
    })
    _write_machine_map(project_root, data)
    return history[-1]


def list_goal_bindings(project_root: str) -> List[Dict[str, Any]]:
    data = _load_machine_map(project_root, create=False)
    return list(data.get("goal_bindings", []) or []) if data else []


def validate_goal_bindings(project_root: str) -> Dict[str, Any]:
    """Validate semantic Goal bindings against current Goal Tree and repository."""
    from .state.goal_tree_ops import load_goal_tree

    data = _load_machine_map(project_root, create=False)
    if not data:
        return {"valid": False, "issues": ["project-map.json missing"], "warnings": []}

    tree = load_goal_tree(project_root)
    goals = {
        str(goal.get("id")): goal
        for goal in tree.get("goals", []) or []
        if isinstance(goal, dict) and goal.get("id")
    }
    bindings = data.get("goal_bindings", []) or []
    issues: List[str] = []
    warnings: List[str] = []
    seen = set()
    root = Path(project_root)

    for binding in bindings:
        if not isinstance(binding, dict):
            issues.append("goal binding is not an object")
            continue
        goal_id = str(binding.get("goal_id") or "")
        if not goal_id:
            issues.append("goal binding missing goal_id")
            continue
        if goal_id in seen:
            issues.append(f"duplicate goal binding: {goal_id}")
        seen.add(goal_id)
        if goal_id not in goals:
            issues.append(f"goal binding references unknown Goal: {goal_id}")
        modules = binding.get("module_paths", []) or []
        if not modules:
            issues.append(f"{goal_id}: module_paths is empty")
        for value in modules + (binding.get("entrypoints", []) or []):
            try:
                normalized = _normalize_repo_path(str(value))
            except ValueError as exc:
                issues.append(f"{goal_id}: {exc}")
                continue
            if not (root / normalized).exists():
                issues.append(f"{goal_id}: mapped path missing: {normalized}")

    # Leaf Goals are concrete capability surfaces and should have an explicit
    # module binding. Aggregate parents may remain unbound.
    for goal_id, goal in goals.items():
        if goal.get("root_type") == "temporary" or goal.get("status") in ("pruned", "rejected"):
            continue
        if not (goal.get("child_goal_ids", []) or []) and goal_id not in seen:
            warnings.append(f"leaf capability Goal has no project-map binding: {goal_id}")

    return {
        "valid": not issues,
        "issues": issues,
        "warnings": warnings,
        "binding_count": len(bindings),
        "goal_count": len(goals),
    }


def ensure_project_map(project_root: str, force: bool = False) -> Path:
    """Create PROJECT-MAP.md if it doesn't exist. Use force to overwrite."""
    p = _path(project_root)
    if not p.exists() or force:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(DEFAULT_MAP, encoding="utf-8")
    return p


def load_project_map(project_root: str) -> str:
    """Read PROJECT-MAP.md, returns empty string if missing."""
    p = _path(project_root)
    if p.exists():
        return p.read_text(encoding="utf-8")
    return ""


def update_project_map_section(project_root: str, section: str, content: str) -> Dict:
    """Replace a single section in PROJECT-MAP.md. Creates file if missing."""
    section_name = SECTION_MAP.get(section)
    if not section_name:
        raise ValueError(f"unknown section: {section}. Valid: {', '.join(SECTION_MAP.keys())}")

    p = _path(project_root)
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(DEFAULT_MAP, encoding="utf-8")

    text = p.read_text(encoding="utf-8")
    # Find the section header and replace everything until next ## header
    import re
    pattern = rf'(## {re.escape(section_name)}\n)(.*?)(?=\n## |\Z)'
    body = content.strip()
    new_text, count = re.subn(
        pattern,
        lambda match: f"{match.group(1)}{body}\n",
        text,
        flags=re.DOTALL,
    )

    if count == 0:
        # Section not found, append
        new_text = text.rstrip() + f"\n\n## {section_name}\n{body}\n"

    p.write_text(new_text, encoding="utf-8")
    return {"section": section, "updated": True}


def summarize_project_map(project_root: str) -> Dict:
    """Return a short summary dict of key PROJECT-MAP fields."""
    text = load_project_map(project_root)
    summary = {"exists": bool(text)}
    if not text:
        return summary

    def _extract(header: str) -> str:
        import re
        m = re.search(rf'## {re.escape(header)}\n(.*?)(?=\n## |\Z)', text, re.DOTALL)
        if m:
            content = m.group(1).strip()
            return content if content and content != "- None yet." else ""
        return ""

    for key, header in SECTION_MAP.items():
        val = _extract(header)
        if key in ("open-decisions", "deferred-risks", "rejected-routes"):
            # Count non-empty bullet lines
            bullets = [l for l in val.split("\n") if l.strip().startswith("- ") and "None yet" not in l]
            summary[f"{key}_count"] = len(bullets)
        elif key == "next-candidate-tasks":
            bullets = [l for l in val.split("\n") if l.strip().startswith("- ") and "None yet" not in l]
            summary["next_tasks_count"] = len(bullets)
        elif key == "current-stage":
            summary["current_stage"] = val.split("\n")[0].lstrip("- ")[:120] if val else ""
        elif key == "architecture-direction":
            summary["architecture_direction"] = val.split("\n")[0].lstrip("- ")[:120] if val else ""

    return summary
