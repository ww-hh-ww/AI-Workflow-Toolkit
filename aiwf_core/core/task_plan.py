"""Task-level plan artifacts: human-readable recovery notes, never truth."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List
import json

VALID_PLAN_SECTIONS = {
    "open-questions": "Open Questions",
    "decisions": "Decisions",
    "scope": "Scope And Non-Goals",
    "implementation": "Implementation Outline",
    "testing": "Test Obligations",
    "review": "Review Focus",
    "evidence": "Evidence Links",
    "checklist": "Current Checklist",
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


def _default_plan(task_id: str, context_id: str = "", title: str = "") -> str:
    title = title or task_id
    return "\n".join([
        f"# AIWF Task Plan: {task_id}",
        "",
        "> Human-readable task plan and recovery artifact. This file is not AIWF mechanical truth.",
        "> Closure still depends on .aiwf JSON gates: evidence, testing, cleanup, review, meta-critique, and prepare-close.",
        "",
        "## Metadata",
        f"- Task: {task_id}",
        f"- Context: {context_id or '(none)'}",
        f"- Title: {title}",
        f"- Created: {_now()}",
        "- Truth source: .aiwf/state/*.json, .aiwf/quality/*.json, .aiwf/evidence/*.json, .aiwf/history/*.json",
        "",
        "## Open Questions",
        "- None yet.",
        "",
        "## Decisions",
        "- None yet.",
        "",
        "## Scope And Non-Goals",
        "- Scope must match contexts.json allowed_write.",
        "- This plan cannot expand write boundaries.",
        "",
        "## Implementation Outline",
        "- Pending.",
        "",
        "## Test Obligations",
        "- Pending.",
        "",
        "## Review Focus",
        "- Pending.",
        "",
        "## Evidence Links",
        "- Evidence IDs are recorded in .aiwf/evidence/records.json.",
        "",
        "## Current Checklist",
        "- [ ] Execution contract frozen in JSON before implementation.",
        "- [ ] Testing recorded in testing.json.",
        "- [ ] Cleanup verified before review.",
        "- [ ] Review recorded in review.json.",
        "",
    ]) + "\n"


def create_task_plan(base_dir: str, task_id: str, context_id: str = "", title: str = "") -> Dict[str, object]:
    task_id = _safe_task_id(task_id)
    path = plan_path(base_dir, task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    created = not path.exists()
    if created:
        path.write_text(_default_plan(task_id, context_id=context_id, title=title), encoding="utf-8")
    state_path = Path(base_dir) / ".aiwf" / "state" / "state.json"
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            state = {}
        state["active_plan_id"] = task_id
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"path": str(path), "created": created, "task_id": task_id}


def load_task_plan(base_dir: str, task_id: str) -> str:
    path = plan_path(base_dir, task_id)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _replace_section(text: str, section_title: str, content: str) -> str:
    import re
    pattern = rf"(## {re.escape(section_title)}\n)(.*?)(?=\n## |\Z)"
    replacement = rf"\1{content.strip()}\n"
    new_text, count = re.subn(pattern, replacement, text, flags=re.DOTALL)
    if count:
        return new_text
    return text.rstrip() + f"\n\n## {section_title}\n{content.strip()}\n"


def update_task_plan_section(base_dir: str, task_id: str, section: str, content: str) -> Dict[str, object]:
    if section not in VALID_PLAN_SECTIONS:
        raise ValueError(f"unknown plan section: {section}")
    path = plan_path(base_dir, task_id)
    if not path.exists():
        create_task_plan(base_dir, task_id)
    text = path.read_text(encoding="utf-8")
    text = _replace_section(text, VALID_PLAN_SECTIONS[section], content)
    path.write_text(text, encoding="utf-8")
    return {"path": str(path), "updated": True, "section": section}


def summarize_task_plan(base_dir: str, task_id: str) -> Dict[str, object]:
    text = load_task_plan(base_dir, task_id)
    if not text:
        return {"exists": False, "task_id": task_id}
    checklist = [line for line in text.splitlines() if line.strip().startswith("- [")]
    checked = [line for line in checklist if line.strip().startswith("- [x]")]
    return {
        "exists": True,
        "task_id": task_id,
        "path": str(plan_path(base_dir, task_id)),
        "line_count": len(text.splitlines()),
        "checklist_total": len(checklist),
        "checklist_checked": len(checked),
    }


def list_task_plans(base_dir: str) -> List[Dict[str, object]]:
    root = _plans_dir(base_dir)
    if not root.exists():
        return []
    plans = []
    for path in sorted(root.glob("*.md")):
        plans.append({"task_id": path.stem, "path": str(path)})
    return plans
