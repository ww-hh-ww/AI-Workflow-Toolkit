"""Bind native coding-agent work to the Task's Plan worktree."""
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
NATIVE_SESSION_ENGINES = frozenset({"claude", "opencode"})


class AgentWorktreeError(RuntimeError):
    """The hook could not safely bind a task-role Agent to one worktree."""


@dataclass(frozen=True)
class AgentAssignment:
    task_id: str
    worktree: Path
    declared_worktree: Path
    control_root: Path


@dataclass(frozen=True)
class RoutedToolInput:
    assignment: AgentAssignment
    tool_input: Dict[str, Any]
    changed: bool


def is_task_role(agent_type: str) -> bool:
    return str(agent_type or "").lower() in TASK_ROLE_TYPES


def _is_planner_session(event: NormalizedEvent) -> bool:
    """Return whether this is the main Planner session, not a subagent."""
    if event.engine not in NATIVE_SESSION_ENGINES or event.agent_id:
        return False
    role = str(event.agent_type or "").lower()
    return not role or "planner" in role or role == "main"


def _assignment(task: Dict[str, Any], control: Path) -> AgentAssignment:
    declared = Path(str(task["worktree_path"])).expanduser()
    return AgentAssignment(
        task_id=str(task["id"]),
        worktree=declared.resolve(),
        declared_worktree=declared,
        control_root=control,
    )


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


def _bash_task_ids(event: NormalizedEvent) -> set[str]:
    """Return Task IDs explicitly selected by a Bash --task-id argument."""
    if event.tool_name != "Bash":
        return set()
    command = str((event.tool_input or {}).get("command") or "")
    try:
        tokens = shlex.split(command)
    except ValueError:
        return set()

    task_ids: set[str] = set()
    for index, token in enumerate(tokens):
        if token == "--task-id" and index + 1 < len(tokens):
            task_ids.add(tokens[index + 1])
        elif token.startswith("--task-id="):
            task_ids.add(token.split("=", 1)[1])
    return {task_id for task_id in task_ids if task_id}


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
    from .agent_runtime import running_dispatches

    return [
        item["task_id"] for item in running_dispatches(
            control, session_id=event.session_id,
        )
        if item["subagent_type"].lower() == str(event.agent_type).lower()
    ]


def resolve_agent_assignment(
    event: NormalizedEvent,
    control_root: Optional[Path] = None,
) -> Optional[AgentAssignment]:
    """Resolve one task-role subagent to the Task named in its dispatch prompt."""
    if event.engine not in NATIVE_SESSION_ENGINES or not is_task_role(event.agent_type):
        return None

    control = (control_root or resolve_control_root(event.cwd or Path.cwd())).resolve()
    tasks = [
        task for task in active_tasks(str(control))
        if str(task.get("worktree_path") or "").strip()
    ]
    if not tasks:
        return None

    # The OpenCode plugin supplies the assigned worktree as the child session's
    # logical cwd. Claude keeps its transcript-based dispatch resolution.
    if event.engine == "opencode":
        try:
            current = Path(event.cwd).expanduser().resolve()
        except (OSError, RuntimeError, ValueError):
            current = None
        cwd_matches = [
            task for task in tasks
            if current is not None
            and Path(str(task["worktree_path"])).expanduser().resolve() == current
        ]
        if len(cwd_matches) == 1:
            return _assignment(cwd_matches[0], control)

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
            return _assignment(task, control)

    pending = set(_unfinished_dispatch_tasks(control, event))
    matches = [task for task in tasks if str(task.get("id") or "") in pending]
    if len(matches) == 1:
        return _assignment(matches[0], control)

    if len(tasks) == 1:
        return _assignment(tasks[0], control)

    raise AgentWorktreeError(
        f"Cannot tell which active Task belongs to {event.agent_type}. "
        "Dispatch it again with exactly one Task ID and assigned worktree; "
        "AIWF will route its tools automatically."
    )


def resolve_planner_assignment(
    event: NormalizedEvent,
    control_root: Optional[Path] = None,
) -> Optional[AgentAssignment]:
    """Resolve inline Planner work without adding a focus command or state field."""
    if not _is_planner_session(event):
        return None

    control = (control_root or resolve_control_root(event.cwd or Path.cwd())).resolve()
    tasks = [
        task for task in active_tasks(str(control))
        if str(task.get("worktree_path") or "").strip()
    ]
    if not tasks:
        return None

    try:
        current = Path(event.cwd).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        current = control
    current_matches = [
        task for task in tasks
        if Path(str(task["worktree_path"])).expanduser().resolve() == current
    ]
    if len(current_matches) == 1:
        return _assignment(current_matches[0], control)

    # In a parallel cycle, an absolute path or an explicit Bash --task-id may
    # identify one worktree. Route only when all selectors agree; never guess.
    tool_text = json.dumps(event.tool_input or {}, ensure_ascii=False)
    explicit_task_ids = _bash_task_ids(event)
    named: Dict[str, Dict[str, Any]] = {}
    for task in tasks:
        task_id = str(task.get("id") or "")
        raw_worktree = str(Path(str(task["worktree_path"])).expanduser())
        resolved_worktree = str(Path(raw_worktree).resolve())
        if (
            task_id in explicit_task_ids
            or raw_worktree in tool_text
            or resolved_worktree in tool_text
        ):
            named[task_id] = task
    if len(named) == 1:
        return _assignment(next(iter(named.values())), control)

    if len(tasks) == 1:
        return _assignment(tasks[0], control)
    return None


def _routed_path(raw_path: str, assignment: AgentAssignment) -> str:
    raw = str(raw_path or "").strip()
    if not raw:
        return str(assignment.worktree)
    path = Path(raw).expanduser()
    if path.is_absolute():
        try:
            relative = path.resolve().relative_to(assignment.worktree)
        except ValueError:
            relative = None
        if relative and relative.parts and relative.parts[0] == ".aiwf":
            return str((assignment.control_root / relative).resolve())
        return str(path)
    normalized = raw[2:] if raw.startswith("./") else raw
    if normalized == ".aiwf" or normalized.startswith(".aiwf/"):
        return str((assignment.control_root / normalized).resolve())
    return str((assignment.worktree / raw).resolve())


def _is_governance_path(raw_path: str, assignment: AgentAssignment) -> bool:
    raw = str(raw_path or "").strip()
    normalized = raw[2:] if raw.startswith("./") else raw
    if normalized == ".aiwf" or normalized.startswith(".aiwf/"):
        return True
    path = Path(raw).expanduser()
    if not path.is_absolute():
        return False
    try:
        relative = path.resolve().relative_to(assignment.worktree)
    except ValueError:
        return False
    return bool(relative.parts and relative.parts[0] == ".aiwf")


def _route_bash_governance(command: str, assignment: AgentAssignment) -> str:
    """Keep shell reads of shared governance out of stale Plan worktree copies."""
    control_aiwf = str((assignment.control_root / ".aiwf").resolve())
    routed = command
    worktree_paths = {
        str(assignment.declared_worktree / ".aiwf"),
        str((assignment.worktree / ".aiwf").resolve()),
    }
    for worktree_aiwf in sorted(worktree_paths, key=len, reverse=True):
        routed = routed.replace(worktree_aiwf, control_aiwf)
    return re.sub(
        r"(?<![A-Za-z0-9_./-])(?:\./)?\.aiwf(?=/|\b)",
        shlex.quote(control_aiwf),
        routed,
    )


def route_agent_tool(
    event: NormalizedEvent,
    control_root: Optional[Path] = None,
) -> Optional[RoutedToolInput]:
    assignment = resolve_agent_assignment(event, control_root)
    if assignment is None:
        assignment = resolve_planner_assignment(event, control_root)
    if assignment is None:
        return None

    updated = dict(event.tool_input or {})
    changed = False
    try:
        already_in_worktree = Path(event.cwd).expanduser().resolve() == assignment.worktree
    except (OSError, RuntimeError, ValueError):
        already_in_worktree = False
    # OpenCode child sessions keep the parent session directory even when AIWF
    # binds the child to a Plan worktree. Always make relative project tools
    # explicit there. Claude can continue using its native worktree cwd.
    route_from_parent = event.engine == "opencode"
    path_key = {
        "Read": "file_path",
        "Write": "file_path",
        "Edit": "file_path",
        "MultiEdit": "file_path",
        "Glob": "path",
        "Grep": "path",
        "List": "path",
    }.get(event.tool_name)
    if path_key:
        current = str(updated.get(path_key) or "")
        routed = (
            _routed_path(current, assignment)
            if (
                _is_governance_path(current, assignment)
                or route_from_parent
                or not already_in_worktree
            )
            else current
        )
        if routed != current:
            updated[path_key] = routed
            changed = True
    elif event.tool_name == "Bash":
        command = str(updated.get("command") or "")
        governed = _route_bash_governance(command, assignment)
        if governed != command:
            command = governed
            updated["command"] = command
            changed = True
        prefix = f"cd {shlex.quote(str(assignment.worktree))} &&"
        if (
            command.strip()
            and (route_from_parent or not already_in_worktree)
            and not command.lstrip().startswith(prefix)
        ):
            updated["command"] = f"{prefix} {command}"
            changed = True

    return RoutedToolInput(assignment, updated, changed)
