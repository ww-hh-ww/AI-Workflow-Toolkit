"""Bind Claude task-role tool calls to the Task's Plan worktree."""
from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .event_model import NormalizedEvent
from .task_ledger import active_tasks
from .worktree_context import resolve_control_root


TASK_ROLE_TYPES = frozenset({"aiwf-executor", "aiwf-tester", "aiwf-reviewer"})


class AgentWorktreeError(RuntimeError):
    """The hook could not safely bind a task-role Agent to one worktree."""


@dataclass(frozen=True)
class AgentAssignment:
    task_id: str
    worktree: Path
    control_root: Path


@dataclass(frozen=True)
class RoutedToolInput:
    assignment: AgentAssignment
    tool_input: Dict[str, Any]
    changed: bool


def is_task_role(agent_type: str) -> bool:
    return str(agent_type or "").lower() in TASK_ROLE_TYPES


def _task_id_in_text(task_id: str, text: str) -> bool:
    return bool(re.search(
        rf"(?<![A-Za-z0-9_-]){re.escape(task_id)}(?![A-Za-z0-9_-])",
        text,
    ))


def _matching_tasks(tasks: Iterable[Dict[str, Any]], text: str) -> List[Dict[str, Any]]:
    matches = []
    for task in tasks:
        task_id = str(task.get("id") or "")
        worktree = str(task.get("worktree_path") or "")
        if task_id and worktree and _task_id_in_text(task_id, text) and worktree in text:
            matches.append(task)
    return matches


def _transcript_candidates(event: NormalizedEvent) -> List[Tuple[Path, bool]]:
    raw = str(event.transcript_path or "").strip()
    if not raw:
        return []
    transcript = Path(raw).expanduser()
    candidates: List[Tuple[Path, bool]] = []
    if event.agent_id:
        filenames = [
            f"agent-{event.agent_id}.jsonl",
            f"{event.agent_id}.jsonl",
        ]
        roots = [
            transcript.with_suffix("") / "subagents",
            transcript.parent / transcript.stem / "subagents",
            transcript.parent / "subagents",
        ]
        for root in roots:
            candidates.extend((root / name, True) for name in filenames)
    if transcript.name.startswith("agent-"):
        candidates.insert(0, (transcript, True))
    else:
        candidates.append((transcript, False))
    unique: Dict[str, Tuple[Path, bool]] = {}
    for candidate, agent_specific in candidates:
        unique.setdefault(str(candidate), (candidate, agent_specific))
    return list(unique.values())


def _read_transcript(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return handle.read(512 * 1024)
    except (OSError, UnicodeError):
        return ""


def _unfinished_dispatch_tasks(
    control: Path,
    event: NormalizedEvent,
) -> List[str]:
    path = control / ".aiwf/runtime/internal/agent-dispatch.jsonl"
    counts: Dict[str, int] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            entry = json.loads(line)
        except Exception:
            continue
        if str(entry.get("subagent_type") or "").lower() != str(event.agent_type).lower():
            continue
        if event.session_id and str(entry.get("session_id") or "") != event.session_id:
            continue
        task_id = str(entry.get("task_id") or "")
        if not task_id:
            continue
        if entry.get("status") == "started":
            counts[task_id] = counts.get(task_id, 0) + 1
        elif entry.get("status") == "completed":
            counts[task_id] = max(0, counts.get(task_id, 0) - 1)
    return [task_id for task_id, count in counts.items() if count > 0]


def resolve_agent_assignment(
    event: NormalizedEvent,
    control_root: Optional[Path] = None,
) -> Optional[AgentAssignment]:
    """Resolve one task-role subagent to the Task named in its dispatch prompt."""
    if event.engine != "claude" or not is_task_role(event.agent_type):
        return None

    control = (control_root or resolve_control_root(event.cwd or Path.cwd())).resolve()
    tasks = [
        task for task in active_tasks(str(control))
        if str(task.get("worktree_path") or "").strip()
    ]
    if not tasks:
        return None

    for transcript, agent_specific in _transcript_candidates(event):
        text = _read_transcript(transcript)
        if not text:
            continue
        matches = []
        if agent_specific:
            for line in text.splitlines():
                matches = _matching_tasks(tasks, line)
                if len(matches) == 1:
                    break
                matches = []
        else:
            matches = _matching_tasks(tasks, text)
        if len(matches) == 1:
            task = matches[0]
            return AgentAssignment(
                task_id=str(task["id"]),
                worktree=Path(str(task["worktree_path"])).expanduser().resolve(),
                control_root=control,
            )

    pending = set(_unfinished_dispatch_tasks(control, event))
    matches = [task for task in tasks if str(task.get("id") or "") in pending]
    if len(matches) == 1:
        task = matches[0]
        return AgentAssignment(
            task_id=str(task["id"]),
            worktree=Path(str(task["worktree_path"])).expanduser().resolve(),
            control_root=control,
        )

    if len(tasks) == 1:
        task = tasks[0]
        return AgentAssignment(
            task_id=str(task["id"]),
            worktree=Path(str(task["worktree_path"])).expanduser().resolve(),
            control_root=control,
        )

    raise AgentWorktreeError(
        f"Cannot tell which active Task belongs to {event.agent_type}. "
        "Dispatch it again with exactly one Task ID and assigned worktree; "
        "AIWF will route its tools automatically."
    )


def _routed_path(raw_path: str, assignment: AgentAssignment) -> str:
    raw = str(raw_path or "").strip()
    if not raw:
        return str(assignment.worktree)
    path = Path(raw).expanduser()
    if path.is_absolute():
        return str(path)
    if raw == ".aiwf" or raw.startswith(".aiwf/"):
        return str((assignment.control_root / raw).resolve())
    return str((assignment.worktree / raw).resolve())


def route_agent_tool(
    event: NormalizedEvent,
    control_root: Optional[Path] = None,
) -> Optional[RoutedToolInput]:
    assignment = resolve_agent_assignment(event, control_root)
    if assignment is None:
        return None

    updated = dict(event.tool_input or {})
    changed = False
    try:
        already_in_worktree = Path(event.cwd).expanduser().resolve() == assignment.worktree
    except (OSError, RuntimeError, ValueError):
        already_in_worktree = False
    path_key = {
        "Read": "file_path",
        "Write": "file_path",
        "Edit": "file_path",
        "MultiEdit": "file_path",
        "Glob": "path",
        "Grep": "path",
    }.get(event.tool_name)
    if path_key:
        current = str(updated.get(path_key) or "")
        routed = current if already_in_worktree else _routed_path(current, assignment)
        if routed != current:
            updated[path_key] = routed
            changed = True
    elif event.tool_name == "Bash":
        command = str(updated.get("command") or "")
        prefix = f"cd {shlex.quote(str(assignment.worktree))} &&"
        if (
            command.strip()
            and not already_in_worktree
            and not command.lstrip().startswith(prefix)
        ):
            updated["command"] = f"{prefix} {command}"
            changed = True

    return RoutedToolInput(assignment, updated, changed)
