"""AIWF Project Map — human/Planner project-level state and direction summary."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

DEFAULT_MAP = """# Project Map

> **What It Is**: Planner TODO — one sentence. A user who knows nothing about this project should understand what it does.

> **How It Works**: Planner TODO — one paragraph. An engineer who has never seen this codebase should know where to start: which directories do what, which files are the entry points, and which design decisions shape the architecture. Do not list every file. Describe boundaries, not contents.

## One-line Overview
- Planner TODO: inspect the project and summarize what it does in one sentence.

## Technical Stack
- Planner TODO: identify languages, frameworks, storage, test tools, and runtime assumptions from source files.

## Project Structure
- Planner TODO: describe the important directories/modules and their responsibilities.

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


def _path(project_root: str) -> Path:
    return Path(project_root) / ".aiwf" / "reports" / "项目地图.md"


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
        elif key == "active-direction":
            summary["active_direction"] = val.split("\n")[0].lstrip("- ")[:120] if val else ""

    return summary
