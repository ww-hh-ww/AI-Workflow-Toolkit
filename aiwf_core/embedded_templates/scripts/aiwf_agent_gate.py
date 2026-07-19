import json, re, sys
from pathlib import Path
from aiwf_core.adapters.claude.normalize_event import parse_claude_stdin, normalize
from aiwf_core.adapters.claude.responses import allow, allow_with_updated_input, deny_pre_tool_use
from aiwf_core.core.agent_runtime import start_dispatch
from aiwf_core.core.task_records import load_task_record
from aiwf_core.core.worktree_context import resolve_control_root

AGENT_SKILL_MAP = {
    "aiwf-executor": "aiwf-implement",
    "aiwf-tester": "aiwf-test",
    "aiwf-reviewer": "aiwf-review",
    "aiwf-architect": "aiwf-architect",
}

ROLE_ACTION = {
    "aiwf-executor": "Implement the contract, verify your work, and record implementation.",
    "aiwf-tester": "Test the current result independently and record testing.",
    "aiwf-reviewer": "Review the tested result independently and record review.",
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

def _task_matches(tasks, text):
    matches = []
    for task in tasks:
        if not isinstance(task, dict) or task.get("status") != "active":
            continue
        task_id = str(task.get("id") or "")
        worktree = str(task.get("worktree_path") or "")
        if (
            task_id and re.search(
                rf"(?<![A-Za-z0-9_-]){re.escape(task_id)}(?![A-Za-z0-9_-])",
                text,
            )
        ) or (worktree and worktree in text):
            matches.append(task)
    return matches

def _enriched_prompt(base, task, subagent_type, original_prompt):
    task_id = str(task.get("id") or "")
    worktree = str(task.get("worktree_path") or "")
    task_path = base / str(task.get("doc_path") or f".aiwf/tasks/{task_id}.md")
    lines = [
        "AIWF assignment:",
        f"Task: {task_id}",
        f"Task contract: {task_path}",
        f"Assigned worktree: {worktree}",
        "Read the current Task contract from the control root and follow your AIWF role instructions.",
        ROLE_ACTION.get(subagent_type, "Complete the assigned AIWF role."),
        "Use the assigned worktree for project files. Task.md remains the contract.",
        "If the contract conflicts with project reality, return RETURN_TO_PLANNER instead of guessing.",
    ]
    if str(original_prompt or "").strip():
        lines.extend(["", "Planner context:", str(original_prompt).strip()])
    return "\n".join(lines)

def _workflow_dispatch_blocker(base, task_id, subagent_type):
    """Reject expensive workflow dispatches that cannot consume current state."""
    if subagent_type not in {"aiwf-executor", "aiwf-tester", "aiwf-reviewer"}:
        return ""

    record = load_task_record(base, task_id)
    fix_loop = record.get("fix_loop", {}) or {}
    if fix_loop.get("status") == "open":
        if fix_loop.get("escalation_required"):
            return (
                f"Cannot dispatch {subagent_type}: repeated fix-loop attempts require a Planner and user decision. "
                "Run 'aiwf status --prompt' and show the recorded failures before retrying."
            )
        route = str(fix_loop.get("route") or "planner")
        expected = {
            "aiwf-executor": "executor",
            "aiwf-tester": "tester",
        }.get(subagent_type, "")
        if route != expected:
            if route == "executor":
                return (
                    f"Cannot dispatch {subagent_type}: an implementation repair is still pending. "
                    "Load /aiwf-implement. Repair inline when it is tiny and fully understood; "
                    "otherwise dispatch aiwf-executor. Record the repaired implementation before Tester."
                )
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

def main():
    data = parse_claude_stdin()
    if not data:
        allow()

    event = normalize(data)
    if event.tool_name not in ("Agent", "Task"):
        allow()

    subagent_type = event.tool_input.get("subagent_type", "")
    base = resolve_control_root(Path(__file__).resolve().parent.parent)
    ledger = _read_json(base / ".aiwf" / "state" / "tasks.json", {"tasks": []})
    original_prompt = str(event.tool_input.get("prompt") or "")
    dispatch_text = "\n".join(
        str(event.tool_input.get(key) or "")
        for key in ("prompt", "description", "name")
    )
    matches = _task_matches(ledger.get("tasks", []) or [], dispatch_text)
    if subagent_type == "general-purpose" and matches:
        deny_pre_tool_use(
            "Cannot use general-purpose as a substitute for an active Task role. "
            "Run 'aiwf status --prompt' and dispatch the named AIWF role. "
            "Use aiwf-explorer for separate read-only exploration."
        )
    if subagent_type not in AGENT_SKILL_MAP:
        allow()

    required_skill = AGENT_SKILL_MAP[subagent_type]
    if len(matches) != 1:
        deny_pre_tool_use(
            f"Cannot dispatch {subagent_type}: prompt must name exactly one active Task ID. "
            "Run 'aiwf status --prompt' and name the intended Task clearly."
        )
    task = matches[0]
    active_task_id = str(task.get("id"))
    worktree_path = str(task.get("worktree_path") or "")
    if not worktree_path:
        deny_pre_tool_use(
            f"Cannot dispatch {subagent_type} for {active_task_id}: the Task has no assigned worktree."
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

    try:
        running = start_dispatch(
            base,
            active_task_id,
            subagent_type,
            event.session_id,
            str(task.get("plan_id") or task.get("parent_plan") or ""),
            worktree_path,
        )
        if running:
            deny_pre_tool_use(
                f"Cannot dispatch {subagent_type}: {running} is still running for "
                f"{active_task_id}. Wait for its Agent call to return; do not retry or substitute another Agent."
            )
    except TimeoutError as exc:
        deny_pre_tool_use(f"Cannot dispatch {subagent_type}: {exc}. Retry once.")

    updated = dict(event.tool_input or {})
    updated["prompt"] = _enriched_prompt(base, task, subagent_type, original_prompt)
    allow_with_updated_input(updated)

if __name__ == "__main__":
    main()
