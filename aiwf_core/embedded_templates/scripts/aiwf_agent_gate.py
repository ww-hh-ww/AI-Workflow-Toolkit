import json, re, sys
from pathlib import Path
from aiwf_core.adapters.claude.normalize_event import parse_claude_stdin, normalize
from aiwf_core.adapters.claude.responses import allow, allow_with_updated_input, deny_pre_tool_use
from aiwf_core.core.agent_runtime import (
    ROLE_REQUIRED_SKILL,
    WORKFLOW_ROLES,
    start_dispatch,
)
from aiwf_core.core.task_records import load_task_record
from aiwf_core.core.worktree_context import resolve_control_root

ROLE_ACTION = {
    "aiwf-executor": "Implement the contract, verify your work, and record implementation.",
    "aiwf-experimenter": "Resolve the assigned empirical unknown and record experiment evidence.",
    "aiwf-reviewer": "Judge the stable implementation and relevant evidence, then record review.",
}

CODEX_NEXT_ROLE = {
    "Executor": "aiwf-executor",
    "Implementation repair": "aiwf-executor",
    "Experimenter": "aiwf-experimenter",
    "Reviewer": "aiwf-reviewer",
    "Reviewer reconciliation": "aiwf-reviewer",
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


def _experiment_match(base, text):
    from aiwf_core.core.experiment_records import list_experiments

    matches = [
        item for item in list_experiments(base)
        if item.get("status") == "running"
        and re.search(
            rf"(?<![A-Za-z0-9_-]){re.escape(str(item.get('experiment_id') or ''))}(?![A-Za-z0-9_-])",
            text,
        )
    ]
    return matches[0] if len(matches) == 1 else {}

def _codex_inferred_role(base, task):
    from aiwf_core.commands.flow import _task_next

    task_id = str(task.get("id") or "")
    record = load_task_record(base, task_id)
    next_role, _action = _task_next(task, record, base, host="codex")
    return CODEX_NEXT_ROLE.get(next_role, ""), next_role


def _codex_selected_role(text):
    """Read an explicit main-session choice at a semantic dispatch point."""
    selected = [
        role for role in ("aiwf-executor", "aiwf-experimenter", "aiwf-reviewer")
        if re.search(
            rf"(?<![A-Za-z0-9_-]){re.escape(role)}(?![A-Za-z0-9_-])",
            str(text or ""),
        )
    ]
    return selected[0] if len(selected) == 1 else ""


def _codex_matched_freshness_packet(text, implementation_ref):
    """Recognize the exact-ref tree packet supplied by the stable Codex task."""
    def value(name):
        match = re.search(
            rf"(?<![A-Za-z0-9_]){re.escape(name)}=([^,\s]+)",
            str(text or ""),
        )
        return match.group(1).strip() if match else ""

    packet_ref = value("implementation_ref")
    implementation_tree = value("implementation_tree")
    candidate_tree = value("candidate_tree")
    status = value("candidate_tree_status")
    return bool(
        implementation_ref
        and packet_ref == implementation_ref
        and implementation_tree
        and implementation_tree == candidate_tree
        and status == "matched"
    )


def _codex_role_contract(base, subagent_type):
    path = base / ".codex" / "agents" / f"{subagent_type}.toml"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    marker = "developer_instructions = '''"
    start = text.find(marker)
    if start < 0:
        return ""
    start += len(marker)
    end = text.find("\n'''", start)
    return text[start:end].strip() if end >= 0 else ""


def _enriched_prompt(base, task, subagent_type, original_prompt, *, codex_fallback=False):
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
    if codex_fallback:
        role_contract = _codex_role_contract(base, subagent_type)
        lines.extend([
            "",
            "Codex host adaptation:",
            "This runtime exposed a generic child tool. AIWF derived the only valid next role "
            f"from Task state and bound this independent child as {subagent_type}.",
        ])
        if role_contract:
            lines.extend([
                "The installed role contract below is authoritative for this child:",
                "",
                role_contract,
            ])
    return "\n".join(lines)

def _workflow_dispatch_blocker(base, task_id, subagent_type):
    """Reject expensive workflow dispatches that cannot consume current state."""
    if subagent_type not in WORKFLOW_ROLES:
        return ""

    record = load_task_record(base, task_id)
    fix_loop = record.get("fix_loop", {}) or {}
    if fix_loop.get("status") == "open":
        if fix_loop.get("escalation_required"):
            return (
                f"Cannot dispatch {subagent_type}: repeated fix-loop failures require a human decision. "
                "Run 'aiwf status --prompt', explain the failure to the user, and ask what to do. "
                f"They may continue with 'aiwf fixloop continue --task-id {task_id}', pause with "
                f"'aiwf task interrupt {task_id}', or accept the unmet checks and close with "
                f"'aiwf task force-close {task_id}'. These commands are human-only."
            )
        route = str(fix_loop.get("route") or "planner")
        expected = {
            "aiwf-executor": "executor",
            "aiwf-reviewer": "reviewer",
        }.get(subagent_type, "")
        if route != expected:
            if route == "executor":
                return (
                    f"Cannot dispatch {subagent_type}: an implementation repair is still pending. "
                    "Load /aiwf-implement. Repair inline when it is tiny and fully understood; "
                    "otherwise dispatch aiwf-executor. Record the repaired implementation before judgment."
                )
            return (
                f"Cannot dispatch {subagent_type}: the open fix-loop routes to {route}. "
                "Run 'aiwf status --prompt' and follow that route first."
            )

    task = _active_task(base, task_id)
    requirements = task.get("requirements", {}) or {}
    implementation = record.get("implementation", {}) or {}

    if subagent_type == "aiwf-executor" and implementation.get("implementation_ref"):
        from aiwf_core.commands.flow import _task_next

        next_role, _action = _task_next(task, record, base)
        if next_role == "Main-session dispatch":
            return (
                "Cannot dispatch aiwf-executor after the current implementation and V/FIX "
                "evidence are complete. The stable main session must read Task.md Dispatch "
                "Decisions and choose its declared post-construction path."
            )

    if subagent_type == "aiwf-reviewer":
        if (
            implementation.get("task_id") != task_id
            or not implementation.get("implementation_ref")
        ):
            return (
                "Cannot dispatch aiwf-reviewer before the active Task has a current "
                "Executor implementation snapshot and V evidence. Finish Executor first."
            )
        from aiwf_core.core.experiment_records import (
            live_experiments,
            pending_experiment_dispositions,
        )

        empirical_work = live_experiments(str(base), task_id)
        if empirical_work:
            item = empirical_work[0]
            experiment_id = str(item.get("experiment_id") or "")
            status = str(item.get("status") or "")
            if status == "recorded":
                return (
                    f"Cannot dispatch aiwf-reviewer while {experiment_id} still owns a "
                    "disposable worktree. Finish that experiment, then review its immutable evidence."
                )
            return (
                f"Cannot dispatch aiwf-reviewer while experiment {experiment_id} is {status}. "
                "Complete the empirical question first."
            )
        empirical_decisions = pending_experiment_dispositions(
            str(base), task_id=task_id,
        )
        if empirical_decisions:
            return (
                "Cannot dispatch aiwf-reviewer before Planner dispositions planning "
                f"experiment {empirical_decisions[0].get('experiment_id')}."
            )
        from aiwf_core.core.task_proof import (
            construction_proof_gaps,
            validate_implementation_against_task,
        )

        gaps = construction_proof_gaps(
            validate_implementation_against_task(str(base), task, implementation)
        )
        if gaps:
            return (
                "Cannot dispatch aiwf-reviewer: Executor V evidence is incomplete for "
                f"{task_id}: {', '.join(gaps[:5])}."
            )
    return ""

def main():
    data = parse_claude_stdin()
    if not data:
        allow()

    event = normalize(data)
    if event.tool_name not in ("Agent", "Task"):
        allow()

    subagent_type = str(
        event.tool_input.get("subagent_type")
        or event.tool_input.get("agent_type")
        or event.tool_input.get("agent")
        or event.tool_input.get("agentName")
        or ""
    )
    base = resolve_control_root(Path(__file__).resolve().parent.parent)
    ledger = _read_json(base / ".aiwf" / "state" / "tasks.json", {"tasks": []})
    prompt_key = "message" if "message" in event.tool_input else "prompt"
    original_prompt = str(event.tool_input.get(prompt_key) or "")
    dispatch_text = "\n".join(
        str(event.tool_input.get(key) or "")
        for key in ("prompt", "message", "description", "name", "task_name")
    )
    matches = _task_matches(ledger.get("tasks", []) or [], dispatch_text)
    matched_experiment = _experiment_match(base, dispatch_text)
    codex_fallback = False
    if event.engine == "codex" and not subagent_type and matched_experiment:
        subagent_type = "aiwf-experimenter"
        codex_fallback = True
    elif event.engine == "codex" and not subagent_type and matches:
        if len(matches) != 1:
            deny_pre_tool_use(
                "Cannot infer a Codex AIWF role: the spawn message must name exactly one active Task."
            )
        subagent_type, next_role = _codex_inferred_role(base, matches[0])
        if not subagent_type and next_role in (
            "Main-session dispatch", "Main-session freshness preflight",
        ):
            subagent_type = _codex_selected_role(dispatch_text)
            if subagent_type == "aiwf-executor":
                deny_pre_tool_use(
                    "Cannot dispatch aiwf-executor after the current implementation and V/FIX "
                    "evidence are complete. The main-session Task.md decision may select a "
                    "post-implementation Experiment or Review."
                )
            if subagent_type == "aiwf-experimenter":
                deny_pre_tool_use(
                    "Cannot dispatch aiwf-experimenter from a Task-only prompt. The main "
                    "session must open and start the selected EXP first, then spawn a child "
                    "naming that EXP ID."
                )
            if (
                subagent_type == "aiwf-reviewer"
                and next_role == "Main-session freshness preflight"
            ):
                record = load_task_record(base, str(matches[0].get("id") or ""))
                implementation_ref = str(
                    (record.get("implementation", {}) or {}).get(
                        "implementation_ref"
                    ) or ""
                )
                if not _codex_matched_freshness_packet(
                    dispatch_text, implementation_ref,
                ):
                    subagent_type = ""
        if not subagent_type:
            deny_pre_tool_use(
                "Cannot bind a generic Codex child for this Task. Its current AIWF next role is "
                f"{next_role}, which is not an independent Executor, Experimenter, or Reviewer dispatch. "
                "Run 'aiwf status --prompt'. At a Main-session dispatch decision, read Task.md "
                "and task proof, choose the declared path yourself, and name exactly one selected "
                "aiwf-* role in the spawn message."
            )
        codex_fallback = True
    if subagent_type == "general-purpose" and matches:
        deny_pre_tool_use(
            "Cannot use general-purpose as a substitute for an active Task role. "
            "Run 'aiwf status --prompt' and dispatch the named AIWF role. "
            "Use aiwf-explorer for separate read-only exploration."
        )
    if subagent_type not in ROLE_REQUIRED_SKILL:
        allow()

    required_skill = ROLE_REQUIRED_SKILL[subagent_type]
    # Check if the matching role skill was loaded in this session.
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

    if not loaded and event.engine != "codex":
        deny_pre_tool_use(
            f"Cannot dispatch {subagent_type}: skill not loaded.\n"
            f"  → Load /{required_skill} first, then dispatch {subagent_type}."
        )

    if subagent_type == "aiwf-architect":
        updated = dict(event.tool_input or {})
        updated[prompt_key] = (
            f"AIWF Architect review\nControl root: {base}\n\n{original_prompt.strip()}"
        ).strip()
        allow_with_updated_input(updated)

    if subagent_type == "aiwf-experimenter":
        experiment = matched_experiment
        if not experiment:
            deny_pre_tool_use(
                "Cannot dispatch aiwf-experimenter: prompt must name exactly one running EXP-* ID. "
                "Open and start the experiment first."
            )
        experiment_id = str(experiment.get("experiment_id") or "")
        scope = experiment.get("scope", {}) or {}
        scope_id = str(scope.get("id") or experiment_id)
        worktree_path = str(experiment.get("worktree_path") or "")
        if not worktree_path:
            deny_pre_tool_use(f"Experiment {experiment_id} has no disposable worktree.")
        plan_id = ""
        if scope.get("kind") == "task":
            task = _active_task(base, scope_id)
            plan_id = str(task.get("plan_id") or task.get("parent_plan") or "")
        try:
            running = start_dispatch(
                base, scope_id, subagent_type, event.session_id, plan_id,
                worktree_path, experiment_id=experiment_id,
            )
            if running:
                deny_pre_tool_use(
                    f"Cannot dispatch aiwf-experimenter: {running} is still running for {scope_id}."
                )
        except TimeoutError as exc:
            deny_pre_tool_use(f"Cannot dispatch aiwf-experimenter: {exc}. Retry once.")
        lines = [
            "AIWF experiment assignment:",
            f"Experiment: {experiment_id}",
            f"Scope: {scope.get('kind')}:{scope_id}",
            f"Timing: {experiment.get('timing')}",
            f"Question: {experiment.get('question')}",
            f"Hypothesis: {experiment.get('hypothesis') or '(none)'}",
            f"Subject ref: {experiment.get('subject_ref')}",
            f"Disposable worktree: {worktree_path}",
            f"Read proof first: aiwf experiment show {experiment_id}",
            "Modify and probe the full disposable project as needed. Do not promote changes into the stable Plan worktree.",
            f"Record evidence with aiwf experiment record {experiment_id}, then return. The stable workflow disposes the worktree separately.",
        ]
        if scope.get("kind") == "task":
            lines.append(f"Also read Task proof: aiwf task proof {scope_id}")
        else:
            lines.append(f"Also read Plan contract: {base / '.aiwf/plans' / (scope_id + '.md')}")
        if original_prompt.strip():
            lines.extend(["", "Planner/Reviewer context:", original_prompt.strip()])
        updated = dict(event.tool_input or {})
        updated[prompt_key] = "\n".join(lines)
        allow_with_updated_input(updated)

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

    if event.engine == "codex" and subagent_type == "aiwf-reviewer":
        _inferred, next_role = _codex_inferred_role(base, task)
        if next_role == "Main-session freshness preflight":
            record = load_task_record(base, active_task_id)
            implementation_ref = str(
                (record.get("implementation", {}) or {}).get(
                    "implementation_ref"
                ) or ""
            )
            if not _codex_matched_freshness_packet(
                dispatch_text, implementation_ref,
            ):
                deny_pre_tool_use(
                    "Cannot dispatch aiwf-reviewer while Codex candidate freshness is "
                    "unavailable. In the stable main task, run 'aiwf task proof "
                    f"{active_task_id}' with the required permission, then include its exact "
                    "matched implementation_ref, implementation_tree, candidate_tree, and "
                    "candidate_tree_status packet in this Reviewer dispatch."
                )
        elif next_role == "Implementation repair":
            deny_pre_tool_use(
                "Cannot dispatch aiwf-reviewer: the stable candidate changed after its "
                "implementation snapshot. Route Executor and record the intended current "
                "candidate first."
            )

    blocker = _workflow_dispatch_blocker(base, active_task_id, subagent_type)
    if blocker:
        if event.engine == "codex":
            blocker = re.sub(r"(?<![A-Za-z0-9_])/(aiwf-[a-z-]+)", r"$\1", blocker)
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
    updated[prompt_key] = _enriched_prompt(
        base, task, subagent_type, original_prompt, codex_fallback=codex_fallback,
    )
    allow_with_updated_input(updated)

if __name__ == "__main__":
    main()
