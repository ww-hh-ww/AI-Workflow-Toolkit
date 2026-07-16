import json, sys
from datetime import datetime, timezone
from pathlib import Path
from aiwf_core.adapters.claude.normalize_event import parse_claude_stdin, normalize
from aiwf_core.adapters.claude.responses import allow, deny_pre_tool_use
from aiwf_core.core.state._common import _exclusive_operation_lock
from aiwf_core.core.task_records import load_task_record
from aiwf_core.core.worktree_context import resolve_control_root

AGENT_SKILL_MAP = {
    "aiwf-executor": "aiwf-implement",
    "aiwf-tester": "aiwf-test",
    "aiwf-reviewer": "aiwf-review",
    "aiwf-architect": "aiwf-architect",
}

def _read_json(path, default=None):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else (default or {})
    except Exception:
        return default or {}

def _active_task(base, task_id):
    ledger = _read_json(base / ".aiwf" / "state" / "tasks.json", {"tasks": []})
    return next(
        (
            task for task in ledger.get("tasks", [])
            if isinstance(task, dict) and task.get("id") == task_id
        ),
        {},
    )

def _workflow_dispatch_blocker(base, task_id, subagent_type):
    """Reject expensive workflow dispatches that cannot consume current state."""
    if subagent_type not in {"aiwf-executor", "aiwf-tester", "aiwf-reviewer"}:
        return ""

    record = load_task_record(base, task_id)
    fix_loop = record.get("fix_loop", {}) or {}
    if fix_loop.get("status") == "open":
        route = str(fix_loop.get("route") or "planner")
        expected = {
            "aiwf-executor": "executor",
            "aiwf-tester": "tester",
        }.get(subagent_type, "")
        if route != expected:
            return (
                f"Cannot dispatch {subagent_type}: the open fix-loop routes to {route}. "
                "Run 'aiwf status --prompt' and follow that route first."
            )

    task = _active_task(base, task_id)
    requirements = task.get("requirements", {}) or {}
    implementation = record.get("implementation", {}) or {}
    testing = record.get("testing", {}) or {}

    if subagent_type == "aiwf-tester" and requirements.get("executor_required", True):
        if (
            implementation.get("task_id") != task_id
            or not implementation.get("implementation_ref")
        ):
            return (
                "Cannot dispatch aiwf-tester before the active Task has a current "
                "Executor implementation record. Finish Executor first."
            )

    if subagent_type == "aiwf-reviewer":
        if (
            testing.get("task_id") != task_id
            or testing.get("status") not in ("adequate", "passed")
            or not testing.get("tested_ref")
        ):
            return (
                "Cannot dispatch aiwf-reviewer before the active Task has a current "
                "adequate/passed tested snapshot. Finish Tester first."
            )
    return ""

def _running_workflow_role(path, task_id, session_id):
    counts = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except Exception:
                continue
            role = str(entry.get("subagent_type") or "")
            if (
                entry.get("task_id") != task_id
                or role not in {"aiwf-executor", "aiwf-tester", "aiwf-reviewer"}
            ):
                continue
            if entry.get("status") == "started":
                if str(entry.get("session_id") or "") != session_id:
                    continue
                counts[role] = counts.get(role, 0) + 1
            elif entry.get("status") == "completed":
                completed_session = str(entry.get("session_id") or "")
                if completed_session and completed_session != session_id:
                    continue
                counts[role] = max(0, counts.get(role, 0) - 1)
    return next((role for role, count in counts.items() if count > 0), "")

def main():
    data = parse_claude_stdin()
    if not data:
        allow()

    event = normalize(data)
    if event.tool_name not in ("Agent", "Task"):
        allow()

    subagent_type = event.tool_input.get("subagent_type", "")
    if subagent_type not in AGENT_SKILL_MAP:
        allow()

    required_skill = AGENT_SKILL_MAP[subagent_type]

    base = resolve_control_root(Path(__file__).resolve().parent.parent)

    ledger = _read_json(base / ".aiwf" / "state" / "tasks.json", {"tasks": []})
    prompt = "\n".join(
        str(event.tool_input.get(key) or "")
        for key in ("prompt", "description", "name")
    )
    matches = [
        task for task in ledger.get("tasks", []) or []
        if isinstance(task, dict)
        and task.get("status") == "active"
        and str(task.get("id") or "")
        and str(task.get("id")) in prompt
    ]
    if len(matches) != 1:
        deny_pre_tool_use(
            f"Cannot dispatch {subagent_type}: prompt must name exactly one active Task ID. "
            "Run 'aiwf status --prompt', then include the Task ID and assigned worktree in the Agent prompt."
        )
    task = matches[0]
    active_task_id = str(task.get("id"))
    worktree_path = str(task.get("worktree_path") or "")
    if not worktree_path or worktree_path not in prompt:
        deny_pre_tool_use(
            f"Cannot dispatch {subagent_type} for {active_task_id}: prompt must include its assigned "
            f"worktree path '{worktree_path or '(not bound)'}'."
        )
    # Check if required skill was loaded for this task
    log_path = base / ".aiwf" / "runtime" / "internal" / "skill-loads.jsonl"
    loaded = False
    if log_path.exists():
        for line in log_path.read_text().strip().split("\n"):
            try:
                d = json.loads(line)
                if (
                    d.get("skill") == required_skill
                    and str(d.get("session_id") or "") == event.session_id
                ):
                    loaded = True
                    break
            except Exception:
                pass

    if not loaded:
        deny_pre_tool_use(
            f"Cannot dispatch {subagent_type}: skill not loaded.\n"
            f"  → Load /{required_skill} first, then dispatch {subagent_type}."
        )

    blocker = _workflow_dispatch_blocker(base, active_task_id, subagent_type)
    if blocker:
        deny_pre_tool_use(blocker)

    dispatch_path = base / ".aiwf" / "runtime" / "internal" / "agent-dispatch.jsonl"
    dispatch_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with _exclusive_operation_lock(str(base), "agent-dispatch", timeout=2):
            running = _running_workflow_role(
                dispatch_path, active_task_id, event.session_id
            )
            if running and subagent_type in {"aiwf-executor", "aiwf-tester", "aiwf-reviewer"}:
                deny_pre_tool_use(
                    f"Cannot dispatch {subagent_type}: {running} is still running for "
                    f"{active_task_id}. Wait for it to return before starting another workflow role."
                )
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "subagent_type": subagent_type,
                "task_id": active_task_id,
                "plan_id": task.get("plan_id") or task.get("parent_plan") or "",
                "worktree_path": worktree_path,
                "session_id": event.session_id,
                "status": "started",
            }
            with open(dispatch_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry) + "\n")
    except TimeoutError as exc:
        deny_pre_tool_use(f"Cannot dispatch {subagent_type}: {exc}. Retry once.")

    allow()

if __name__ == "__main__":
    main()
