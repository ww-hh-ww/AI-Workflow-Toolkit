"""Codex permission-bearing candidate preflight; no acceptance judgment."""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Dict, Tuple


def freshness_packet(binding):
    """Use a single representation for the producer and the dispatch reader."""
    return ", ".join(f"{key}={binding.get(key, '')}" for key in (
        "implementation_ref", "implementation_tree", "candidate_tree",
    )) + ", candidate_tree_status=matched"


def matched_freshness_packet(text, implementation_ref):
    def value(name):
        match = re.search(rf"(?<![A-Za-z0-9_]){name}=([^,\s]+)", str(text or ""))
        return match.group(1).rstrip(".;") if match else ""

    tree = value("implementation_tree")
    return bool(implementation_ref and value("implementation_ref") == implementation_ref
                and tree and tree == value("candidate_tree")
                and value("candidate_tree_status") == "matched")


def _codex_freshness_preflight(
    task: Dict[str, Any], implementation: Dict[str, Any], control: Path,
) -> Tuple[str, str] | Dict[str, Any]:
    """Preflight the stable candidate where Codex can request host permission."""
    from ..core.git_snapshots import format_tree_changes, snapshot_binding

    task_id = str(task.get("id") or "")
    implementation_ref = str(implementation.get("implementation_ref") or "")
    worktree = str(task.get("worktree_path") or control)
    binding = snapshot_binding(worktree, implementation_ref)
    status = str(binding.get("candidate_tree_status") or "unavailable")
    if status == "matched":
        return binding
    if status == "changed":
        changes = format_tree_changes(binding.get("tree_changes", []) or [])
        return (
            "Implementation repair",
            f"load /aiwf-implement for {task_id}; the stable candidate tree changed after "
            f"implementation_ref {implementation_ref}. Inspect and record the intended current "
            f"candidate before any Experiment or Review"
            + (f": {changes}" if changes else ""),
        )
    detail = " ".join(str(binding.get("candidate_tree_error") or "").split())
    suffix = f" Reported Git error: {detail[:500]}." if detail else ""
    return (
        "Main-session freshness preflight",
        f"in the stable Codex main task, run aiwf task proof {task_id} with the permission "
        f"needed to inspect Plan worktree {worktree}. Confirm its implementation_ref is exactly "
        f"{implementation_ref}. If candidate_tree_status=matched, continue directly with the "
        "Task.md Dispatch Decisions and copy the exact implementation/tree binding into any "
        "Reviewer dispatch; if changed, route Executor; do not dispatch a child while the result "
        f"is unavailable.{suffix}",
    )
