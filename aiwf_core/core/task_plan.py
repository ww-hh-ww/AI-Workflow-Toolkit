"""Task plan artifacts — AI working memory, not long-form documentation.

.aiwf/state/plans.json is the Plan machine authority.
.aiwf/artifacts/plans/<PLAN-ID>.md is the compact human artifact. Task-named
plan markdown is retired and never activation truth.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
import json

VALID_PLAN_SECTIONS = {
    # New V2 sections
    "goal": "Goal",
    "route": "Route",
    "scope": "Scope",
    "risks": "Risks",
    "decision": "Current Decision",
    "verification": "Verification",
    "impact": "Impact",
    "docs-assets": "Impact",  # retired alias accepted only when editing old artifacts
    "done-means": "Done Means",
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
    return Path(base_dir) / ".aiwf" / "artifacts" / "plans"


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


def _default_plan(task_id: str, context_id: str = "", title: str = "",
                  goal_id: str = "", task_ids: Optional[List[str]] = None,
                  target_goal_id: str = "", plan_kind: str = "",
                  active_phase: str = "",
                  interfaces: Optional[List[str]] = None,
                  constraints: Optional[List[str]] = None,
                  child_goal_policy: str = "",
                  work_intent: str = "") -> str:
    title = title or task_id
    task_ids = task_ids or ([task_id] if task_id.startswith("TASK-") else [])
    tg = target_goal_id or goal_id or "GOAL-001"
    kind = plan_kind or "implementation"
    phase = active_phase or "implementation"

    header_lines = [
        f"# {task_id}",
        "",
        "> AI working plan. Compact task-local execution memory.",
        "> Closure gates: .aiwf JSON (testing, review, evidence, cleanup, meta-critique).",
        "",
        f"Plan ID: {task_id}",
        f"Target Goal: {tg}",
        f"Plan Kind: {kind}",
        f"Active Phase: {phase}",
    ]
    if work_intent:
        header_lines.append(f"Work Intent: {work_intent}")
    if interfaces:
        header_lines.append(f"Interfaces: {', '.join(interfaces)}")
    if constraints:
        header_lines.append(f"Constraints: {', '.join(constraints)}")
    if child_goal_policy:
        header_lines.append(f"Child Goal Policy: {child_goal_policy}")
    header_lines += [
        f"Task IDs: {', '.join(task_ids) if task_ids else '(attach tasks later)'}",
    ]

    return "\n".join(header_lines + [
        "",
        "## Goal",
        f"{title}",
        "",
        "## Route",
        "- How: (fill — what approach, why this way)",
        "- Alternatives considered: (fill or N/A)",
        "",
        "## Scope",
        "- Change: (fill)",
        "- Do NOT change: (fill)",
        "",
        "## Risks",
        "- (fill or none)",
        "",
        "## Current Decision",
        "- Approach: (fill)",
        "- Why: (fill)",
        "",
        "## Verification",
        "- Must verify: (fill)",
        "- Machine-verifiable: yes / no",
        "- Can waive subagent if: (fill or N/A)",
        "",
        "## Impact",
        "",
        "> One block for all read/write/sync decisions. yes/no/unknown + short reason.",
        "> Review checks this against actual changes. No other suggest/read/write policy needed.",
        "",
        "- docs:          (yes/no) — does this change project surface area, README, or public docs?",
        "- project_map:   unknown — fill",
        "- environment:   unknown — fill",
        "- capabilities:  unknown — fill",
        "- quality_summary: unknown — fill",
        "",
        "## Done Means",
        "- This task is done when: (fill)",
        "",
        "## Goal Progress",
        "- Parent goal: (fill)",
        "- This task advances milestone: (fill)",
        "- Goal complete after: (fill — which tasks remain)",
        "",
        "## Next Steps",
        "1. (fill)",
        "2. (fill)",
        "3. (fill)",
        "",
    ]) + "\n"


def create_task_plan(
    base_dir: str,
    task_id: str = "",
    context_id: str = "",
    title: str = "",
    plan_id: str = "",
    goal_id: str = "",
    milestone_id: str = "",
    task_ids: Optional[List[str]] = None,
    target_goal_id: str = "",
    plan_kind: str = "",
    active_phase: str = "",
    interfaces: Optional[List[str]] = None,
    constraints: Optional[List[str]] = None,
    child_goal_policy: str = "",
    work_intent: str = "",
    allowed_write: Optional[List[str]] = None,
    forbidden_write: Optional[List[str]] = None,
    purpose: str = "",
    test_focus: Optional[List[str]] = None,
    review_focus: Optional[List[str]] = None,
    dependencies: Optional[List[str]] = None,
    interface_contract: str = "",
    escalation_triggers: Optional[List[str]] = None,
) -> Dict[str, object]:
    legacy_task_id = _safe_task_id(task_id) if task_id else ""
    if plan_id:
        effective_plan_id = _safe_task_id(plan_id)
    elif legacy_task_id:
        effective_plan_id = _safe_task_id(f"PLAN-{legacy_task_id}")
    else:
        raise ValueError("plan_id or task_id is required")
    attached_tasks = list(dict.fromkeys(task_ids or ([legacy_task_id] if legacy_task_id else [])))
    tg = target_goal_id or goal_id or "GOAL-001"
    kind = plan_kind or "implementation"
    phase = active_phase or "implementation"
    iface_list = list(dict.fromkeys(interfaces or []))
    constraint_list = list(dict.fromkeys(constraints or []))
    cgp = child_goal_policy or ""

    path = plan_path(base_dir, effective_plan_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    created = not path.exists()
    if created:
        text = _default_plan(effective_plan_id, context_id=context_id, title=title,
                             goal_id=goal_id, task_ids=attached_tasks,
                             target_goal_id=tg, plan_kind=kind, active_phase=phase,
                             interfaces=iface_list, constraints=constraint_list,
                             child_goal_policy=cgp, work_intent=work_intent)
        # Previous Plan completed without README → force this one to create it
        state_path = Path(base_dir) / ".aiwf" / "state" / "state.json"
        if state_path.exists():
            import json as _json
            state = _json.loads(state_path.read_text(encoding="utf-8"))
            if state.get("next_plan_docs_required"):
                text = text.replace(
                    "- docs:          (yes/no) — does this change project surface area, README, or public docs?",
                    "- docs:          yes — previous Plan finished without README.md, create it now")
                state["next_plan_docs_required"] = False
                state_path.write_text(_json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        path.write_text(text, encoding="utf-8")
    try:
        from .state.plan_ops import upsert_plan
        upsert_plan(base_dir, effective_plan_id, goal_id=goal_id, task_ids=attached_tasks,
                    status="ready", title=title or effective_plan_id,
                    milestone_id=milestone_id,
                    target_goal_id=tg,
                    plan_kind=kind,
                    active_phase=phase,
                    interfaces=iface_list,
                    constraints=constraint_list,
                    child_goal_policy=cgp,
                    work_intent=work_intent,
                    allowed_write=allowed_write,
                    forbidden_write=forbidden_write,
                    purpose=purpose,
                    test_focus=test_focus,
                    review_focus=review_focus,
                    dependencies=dependencies,
                    interface_contract=interface_contract,
                    escalation_triggers=escalation_triggers)
    except ValueError:
        raise
    except Exception:
        pass
    # Plan is created; activation (setting active_plan_id) is a separate,
    # explicit decision made by the planner-executor via aiwf plan activate.
    # Creating a plan does NOT auto-activate it — otherwise creating N plans
    # means the last one silently wins, causing plan_only_drift deadlocks.
    return {"path": str(path), "created": created, "task_id": legacy_task_id or effective_plan_id,
            "plan_id": effective_plan_id, "task_ids": attached_tasks, "milestone_id": milestone_id,
            "target_goal_id": tg,
            "plan_kind": kind,
            "active_phase": phase,
            "interfaces": iface_list,
            "constraints": constraint_list,
            "dependencies": list(dict.fromkeys(dependencies or [])),
            "child_goal_policy": cgp,
            "work_intent": work_intent or None}


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


def update_task_plan_section(base_dir: str, task_id: str, section: str, content: str) -> Dict[str, object]:
    # Backward-compat: map old V1 section names to new V2 sections
    effective = SECTION_COMPAT.get(section, section)
    if effective not in VALID_PLAN_SECTIONS:
        raise ValueError(f"unknown plan section: {section}")
    artifact_id = _resolve_plan_artifact_id(base_dir, task_id)
    path = plan_path(base_dir, artifact_id)
    if not path.exists():
        create_task_plan(base_dir, task_id=task_id)
        artifact_id = _resolve_plan_artifact_id(base_dir, task_id)
        path = plan_path(base_dir, artifact_id)
    text = path.read_text(encoding="utf-8")
    text = _replace_section(text, VALID_PLAN_SECTIONS[effective], content)
    path.write_text(text, encoding="utf-8")
    return {"path": str(path), "updated": True, "section": section, "effective_section": effective}


def summarize_task_plan(base_dir: str, task_id: str) -> Dict[str, object]:
    text = load_task_plan(base_dir, task_id)
    if not text:
        return {"exists": False, "task_id": task_id}
    checklist = [line for line in text.splitlines() if line.strip().startswith("- [")]
    checked = [line for line in checklist if line.strip().startswith("- [x]")]
    return {
        "exists": True,
        "task_id": task_id,
        "path": str(plan_path(base_dir, _resolve_plan_artifact_id(base_dir, task_id))),
        "line_count": len(text.splitlines()),
        "checklist_total": len(checklist),
        "checklist_checked": len(checked),
    }


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


# Impact categories — the single block that governs read/write/sync decisions
IMPACT_CATEGORIES = ["docs", "project_map", "environment", "capabilities", "quality_summary"]
VALID_IMPACT_VALUES = {"yes", "no"}

# Patterns that indicate an unfilled/placeholder Impact value — must be rejected
_IMPACT_PLACEHOLDER_SUBSTRINGS = [
    "unknown",
    "fill",
    "(reason)",
    "todo",
    "yes / no / unknown",
    "yes/no/unknown",
]


def parse_plan_impact(base_dir: str, task_id: str) -> Dict[str, str]:
    """Parse the Impact section from a plan and return {category: value}.

    Returns empty dict if plan or Impact section not found.
    Used by Review to check Impact consistency against actual changes.
    """
    import re
    text = load_task_plan(base_dir, task_id)
    if not text:
        return {}

    # Find Impact section (new heading "## Impact" or old "## Docs / Assets Impact")
    m = re.search(r'## (?:Impact|Docs / Assets Impact)\n(.*?)(?=\n## |\Z)', text, re.DOTALL)
    if not m:
        return {}

    impact = {}
    body = m.group(1)
    for cat in IMPACT_CATEGORIES:
        pattern = rf'(?:^|\n)\s*-?\s*{cat}\s*(?::|=)\s*(yes|no)\b'
        match = re.search(pattern, body)
        if match:
            impact[cat] = match.group(1)
    return impact


def validate_plan_impact(base_dir: str, task_id: str) -> List[str]:
    """Check if the Impact section is complete and valid.

    Returns a list of issues (empty = valid). Used as a planning gate.
    docs and project_map are required; all categories must be yes/no with a reason.
    Placeholder values (unknown, fill, (reason), TODO, etc.) are rejected.
    """
    import re
    text = load_task_plan(base_dir, task_id)
    issues = []

    if not text:
        issues.append("Impact section missing — plan must have an Impact block")
        return issues

    # Find Impact section
    m = re.search(r'## (?:Impact|Docs / Assets Impact)\n(.*?)(?=\n## |\Z)', text, re.DOTALL)
    if not m:
        issues.append("Impact section missing — plan must have an Impact block")
        return issues

    body = m.group(1)

    for cat in IMPACT_CATEGORIES:
        # Extract the full value text after the category label
        pattern = rf'(?:^|\n)\s*-?\s*{cat}\s*(?::|=)\s*(.+)'
        match = re.search(pattern, body)
        if not match:
            issues.append(f"Impact.{cat}: missing — all 5 categories must be yes/no with a reason")
            continue

        raw = match.group(1).strip().lower()

        # Check for placeholder patterns
        for ph in _IMPACT_PLACEHOLDER_SUBSTRINGS:
            if ph in raw:
                issues.append(
                    f"Impact.{cat}: appears unfilled (contains '{ph}') — "
                    f"must be yes or no with a short reason"
                )
                break
        else:
            # Not a placeholder — check if it starts with yes/no
            if raw.startswith("yes"):
                if len(raw) <= 4 or raw[3:].strip() in ("", "-", "—", ":"):
                    issues.append(f"Impact.{cat}: yes requires a reason after the value")
            elif raw.startswith("no"):
                if len(raw) <= 3 or raw[2:].strip() in ("", "-", "—", ":"):
                    issues.append(f"Impact.{cat}: no requires a reason after the value")
            else:
                issues.append(f"Impact.{cat}: must be yes or no with a reason, got '{match.group(1).strip()[:40]}'")

    return issues

def impact_review_check(base_dir: str, task_id: str, changed_files: list) -> dict:
    """Check Impact declarations against actual changed files.

    Returns {"warnings": [...], "blockers": [...]} for use by Review/Close gates.
    Only checks docs, project_map, and quality_summary — the categories with
    detectable file patterns.
    """
    impact = parse_plan_impact(base_dir, task_id)
    if not impact:
        return {"warnings": ["Impact section not found — cannot verify consistency"], "blockers": []}

    warnings = []
    blockers = []

    def _matches(changed, patterns):
        """Check if a changed file path matches any of the given patterns.
        Matches against the full path and the filename component (case-insensitive).
        """
        lower = changed.lower()
        for p in patterns:
            if lower == p or p in lower:
                return True
            # Also check just the filename for path patterns
            name = Path(changed).name.lower()
            if name == p or p in name:
                return True
        return False

    # Doc patterns: README, CHANGELOG, anything in docs/ or doc/
    doc_patterns = {"readme.md", "readme", "changelog.md", "changelog", "docs/", "doc/"}
    # Project-map patterns: the human markdown, the machine JSON, any path component
    pm_patterns = {"project-map.md", "项目地图.md", "project-map.json", "project_map"}
    # Quality summary patterns
    qs_patterns = {"质量摘要.md", "quality-digest.md", "quality_digest", "quality-digest"}

    # Check docs
    docs_val = impact.get("docs", "")
    docs_changed = [f for f in changed_files if _matches(f, doc_patterns)]
    if docs_val == "no" and docs_changed:
        blockers.append(
            f"Impact.docs=no but doc files were changed: {', '.join(docs_changed[:3])}"
        )
    elif docs_val == "yes" and not docs_changed:
        warnings.append("Impact.docs=yes but no doc files detected in changes")

    # Check project_map
    pm_val = impact.get("project_map", "")
    pm_changed = [f for f in changed_files if _matches(f, pm_patterns)]
    if pm_val == "no" and pm_changed:
        blockers.append(
            f"Impact.project_map=no but project-map files were changed: {', '.join(pm_changed[:3])}"
        )
    elif pm_val == "yes" and not pm_changed:
        warnings.append("Impact.project_map=yes but no project-map files detected in changes")

    # Check quality_summary
    qs_val = impact.get("quality_summary", "")
    qs_changed = [f for f in changed_files if _matches(f, qs_patterns)]
    if qs_val == "no" and qs_changed:
        blockers.append(
            f"Impact.quality_summary=no but quality digest was written: {', '.join(qs_changed[:3])}"
        )

    return {"warnings": warnings, "blockers": blockers}
