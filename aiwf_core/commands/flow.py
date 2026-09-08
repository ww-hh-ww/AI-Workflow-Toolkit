"""Concise human and model status for the embedded workflow."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from ..constants import VERSION
from ..core.agent_runtime import WORKFLOW_ROLES, running_dispatches
from ..core.task_routes import _task_next
from ..core.task_dispatch import _post_construction_next, _live_experiment_next
from ..core.git_workflow import plan_integration_state
from ..core.state.goal_ops import get_active_goal
from ..core.state.plan_ops import load_plans
from ..core.task_ledger import load_ledger, task_for_worktree
from ..core.task_records import load_task_record
from ..core.temporary_access import temporary_ai_writes_enabled
from ..core.worktree_context import resolve_control_root, resolve_worktree_root


def _read_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else default
    except Exception:
        return default




def _acknowledge_status_hook(control: Path) -> None:
    """Tell the short UserPrompt hook that this routing state was already read."""
    workflow_tasks = [
        task for task in load_ledger(str(control)).get("tasks", []) or []
        if isinstance(task, dict) and task.get("status") in ("active", "suspended")
    ]
    from ..core.status_context import fingerprint as status_fingerprint

    fingerprint = status_fingerprint(control, workflow_tasks)
    path = control / ".aiwf/runtime/internal/status-hook-last.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(fingerprint, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def _named_skill(name: str) -> str:
    prefix = "$" if os.environ.get("AIWF_HOST", "").lower() == "codex" else "/"
    return prefix + name


def _skill_for(next_role: str) -> str:
    name = {
        "Executor": "aiwf-implement",
        "Implementation repair": "aiwf-implement",
        "Inline implementation": "aiwf-implement",
        "Experimenter": "aiwf-experiment",
        "Experiment cleanup": "aiwf-experiment",
        "Reviewer": "aiwf-review",
        "Reviewer reconciliation": "aiwf-review",
        "Inline review": "aiwf-review",
        "Close": "aiwf-close",
        "Planner calibration": "aiwf-planner",
        "Planner decision": "aiwf-planner",
        "Milestone acceptance": "aiwf-architect",
        "Human acceptance": "",
        "Agent running": "",
        "Main-session dispatch": "",
        "Main-session freshness preflight": "",
    }.get(next_role, "aiwf-planner")
    if not name:
        return ""
    return _named_skill(name)


def _host_action(action: str, host: str) -> str:
    from ..adapters.host_prompts import host_action

    return host_action(action, host)


def _active_rows(control: Path, host: str = "") -> List[Dict[str, Any]]:
    host = (host or os.environ.get("AIWF_HOST", "claude")).lower()
    rows: List[Dict[str, Any]] = []
    for task in load_ledger(str(control)).get("tasks", []) or []:
        if not isinstance(task, dict) or task.get("status") not in ("active", "suspended"):
            continue
        record = load_task_record(control, str(task.get("id") or ""))
        task_id = str(task.get("id") or "")
        suspended = task.get("status") == "suspended"
        if suspended:
            fix_loop = record.get("fix_loop", {}) or {}
            next_role = "Planner decision"
            if task.get("kind") == "integration":
                plan_id = str(task.get("plan_id") or task.get("parent_plan") or "")
                action = (
                    f"load /aiwf-planner; refresh the stale integration preflight with "
                    f"'aiwf plan integrate {plan_id}'. If it reports new Plan commits, "
                    "inspect them with the user before accepting them. When the recorded "
                    "refs change, update Task.md if needed, repeat both activation critiques, "
                    f"then reactivate {task_id}"
                )
            elif fix_loop.get("status") == "open":
                action = (
                    f"load /aiwf-planner; inspect the open fix-loop for suspended {task_id}, "
                    "run any required activation critique, then reactivate this same Task and "
                    "continue its routed repair; do not resolve an unfixed problem. If activation "
                    "reports a changed Git HEAD, ask the user before using --accept-head-change"
                )
            else:
                action = (
                    f"load /aiwf-planner; inspect why {task_id} was suspended and decide whether "
                    "to revise and reactivate it or cancel it"
                )
            running = []
        else:
            next_role, action = _task_next(task, record, control, host)
            running = [
                item for item in running_dispatches(control, task_id=task_id)
                if item["subagent_type"] in WORKFLOW_ROLES
            ]
        if len(running) == 1:
            role = running[0]["subagent_type"]
            started_at = str(running[0].get("started_at") or "unknown")
            next_role = "Agent running"
            action = (
                f"wait for {role} on {task_id}; dispatch started at {started_at} and no return has been observed. "
                "Elapsed time or missing output alone is not proof that the Agent is stuck. "
                "Do not stop, retry, or substitute another Agent without an explicit failure or user request"
            )
        calibration_missing = False
        if next_role == "Close":
            task_doc = control / ".aiwf/tasks" / f"{task_id}.md"
            if task_doc.exists():
                calibration_missing = "## Closure Calibration" not in task_doc.read_text(
                    encoding="utf-8", errors="ignore",
                )
            if calibration_missing:
                next_role = "Planner calibration"
                deferred_count = len([
                    item for item in (record.get("review", {}) or {}).get(
                        "adversarial_observations", []
                    ) or []
                    if isinstance(item, dict) and item.get("disposition") == "deferred"
                ])
                if deferred_count:
                    action = (
                        f"load /aiwf-planner; confirm {deferred_count} deferred Reviewer "
                        "observation(s) are written in a downstream Task or "
                        ".aiwf/memory/notes/deferred-findings.md, then run "
                        f"aiwf task calibrate {task_id} with the actual result"
                    )
                else:
                    action = (
                        f"load /aiwf-planner and run aiwf task calibrate {task_id} "
                        "with the actual result"
                    )
        review_state = record.get("review", {}) or {}
        review_result = str(review_state.get("result") or "unknown")
        review_story = (
            "complete"
            if review_result == "accepted" and review_state.get("closure_allowed", False)
            else "unasserted"
            if review_result == "accepted"
            else "pending"
            if review_result == "unknown"
            else "incomplete"
        )
        rows.append({
            "id": task_id,
            "task_status": task.get("status", ""),
            "plan_id": task.get("plan_id") or task.get("parent_plan") or "",
            "phase": task.get("phase", ""),
            "worktree_path": task.get("worktree_path", ""),
            "next_role": next_role,
            "action": _host_action(action, host),
            "implementation_ref": (record.get("implementation", {}) or {}).get("implementation_ref", ""),
            "construction_status": (
                "recorded" if (record.get("implementation", {}) or {}).get(
                    "implementation_ref"
                ) else "missing"
            ),
            "experiment_ids": list(record.get("experiment_ids", []) or []),
            "review_result": review_result,
            "review_story": review_story,
            "fix_loop": (record.get("fix_loop", {}) or {}).get("status", "none"),
            "fix_loop_context": dict(record.get("fix_loop", {}) or {}),
            "calibration_missing": calibration_missing,
            "running_agent": running[0]["subagent_type"] if len(running) == 1 else "",
            "agent_started_at": running[0].get("started_at", "") if len(running) == 1 else "",
        })
    return rows


def _print_fix_loop_context(row: Dict[str, Any]) -> None:
    fix_loop = row.get("fix_loop_context", {}) or {}
    if fix_loop.get("status") != "open":
        return
    source = str(fix_loop.get("source") or "unknown")
    route = str(fix_loop.get("route") or "planner")
    attempt = int(fix_loop.get("attempt_count", 0) or 0)
    maximum = int(fix_loop.get("max_attempts", 0) or 0)
    attempt_text = f"{attempt}/{maximum}" if maximum else str(attempt)
    print(f"Fix-loop: source={source}, route={route}, attempt={attempt_text}")
    reason = " ".join(str(fix_loop.get("reason") or "").split())
    if reason:
        print(f"Finding: {reason[:500]}")

    def compact(items: List[str]) -> str:
        visible = items[:3]
        suffix = f"; (+{len(items) - 3} more in task proof)" if len(items) > 3 else ""
        return "; ".join(visible) + suffix

    required_fixes = [
        " ".join(str(item).split())
        for item in fix_loop.get("required_fixes", []) or []
        if str(item).strip()
    ]
    if required_fixes:
        print("Required fixes: " + compact(required_fixes))
    verification_obligations = []
    for item in fix_loop.get("verification_obligations", []) or []:
        if not isinstance(item, dict):
            continue
        verification_id = " ".join(str(item.get("verification_id") or "").split())
        command = " ".join(str(item.get("command") or "").split())
        if verification_id:
            verification_obligations.append(
                f"{verification_id}: {command}" if command else verification_id
            )
    if verification_obligations:
        print("Verification obligations: " + compact(verification_obligations))
    if fix_loop.get("required_verification"):
        print(
            "Verification contract: legacy free text is unsupported; reopen this "
            "fix-loop with ID-bound --verify entries."
        )
    print(
        "Repair brief: use these verified facts and project judgment to state the "
        "specific problem, expected correction, preserved work, and focused proof. "
        "Keep USER_DELTA separate and only for an explicit user clarification."
    )


def _plans_at_closeout(control: Path) -> List[Dict[str, Any]]:
    closeout = []
    for plan in load_plans(str(control), migrate=False).get("plans", []) or []:
        if not isinstance(plan, dict) or plan.get("status") != "open":
            continue
        statuses = plan.get("task_status", {}) or {}
        if statuses and all(value in ("closed", "cancelled") for value in statuses.values()):
            item = dict(plan)
            item["_integration_state"] = plan_integration_state(str(control), plan)
            closeout.append(item)
    return closeout


def _plans_between_tasks(control: Path) -> List[Dict[str, Any]]:
    plans = []
    for plan in load_plans(str(control), migrate=False).get("plans", []) or []:
        if not isinstance(plan, dict) or plan.get("status") != "open":
            continue
        statuses = plan.get("task_status", {}) or {}
        has_closed = any(value == "closed" for value in statuses.values())
        has_remaining = any(value not in ("closed", "cancelled") for value in statuses.values())
        if has_closed and has_remaining:
            plans.append(plan)
    return plans


def _milestones_at_acceptance(control: Path) -> List[Dict[str, Any]]:
    """Return open delivery slices whose linked work is terminal."""
    from ..core.state.milestone_ops import load_milestones

    plan_by_id = {
        str(plan.get("plan_id") or plan.get("id")): plan
        for plan in load_plans(str(control), migrate=False).get("plans", []) or []
        if isinstance(plan, dict) and (plan.get("plan_id") or plan.get("id"))
    }
    tasks = [
        task for task in load_ledger(str(control)).get("tasks", []) or []
        if isinstance(task, dict)
    ]
    task_by_id = {str(task.get("id")): task for task in tasks if task.get("id")}
    ready: List[Dict[str, Any]] = []
    for milestone in load_milestones(str(control)).get("milestones", []) or []:
        if not isinstance(milestone, dict) or milestone.get("status") != "open":
            continue
        plan_ids = [str(item) for item in milestone.get("plan_ids", []) or []]
        task_ids = [str(item) for item in milestone.get("task_ids", []) or []]
        task_refs_exist = all(task_id in task_by_id for task_id in task_ids)
        delivery_tasks = [
            task_by_id[task_id] for task_id in task_ids
            if task_id in task_by_id
            and task_by_id[task_id].get("kind") != "milestone_verification"
        ]
        has_delivery_scope = bool(plan_ids or delivery_tasks)
        plans_done = bool(plan_ids) and all(
            plan_id in plan_by_id and plan_by_id[plan_id].get("status") == "closed"
            for plan_id in plan_ids
        )
        tasks_done = all(
            task.get("status") in ("closed", "cancelled") for task in delivery_tasks
        )
        if (
            not has_delivery_scope
            or (plan_ids and not plans_done)
            or not task_refs_exist
            or not tasks_done
        ):
            continue
        verification = next((
            task for task in tasks
            if task.get("kind") == "milestone_verification"
            and task.get("milestone_id") == milestone.get("milestone_id")
        ), None)
        item = dict(milestone)
        item["_verification_task"] = verification
        ready.append(item)
    return ready


def _plan_experiment_attention(control: Path) -> Dict[str, Any]:
    """Return the first Plan-scoped experiment that needs lifecycle attention."""
    from ..core.experiment_records import list_experiments

    for item in list_experiments(str(control)):
        scope = item.get("scope", {}) or {}
        if scope.get("kind") != "plan":
            continue
        status = str(item.get("status") or "")
        disposition = item.get("disposition", {}) or {}
        if status in ("open", "running", "recorded"):
            return item
        if status == "closed" and disposition.get("status") == "pending":
            return item
    return {}


def _print_plan_experiment_prompt(experiment: Dict[str, Any]) -> None:
    experiment_id = str(experiment.get("experiment_id") or "")
    status = str(experiment.get("status") or "")
    scope = experiment.get("scope", {}) or {}
    if status == "open":
        action = (
            f"run aiwf experiment start {experiment_id}, then load /aiwf-architect "
            f"and dispatch aiwf-architect for {experiment_id}"
        )
        skill = _named_skill("aiwf-architect")
        role = "Architect investigation"
    elif status == "running":
        action = f"load /aiwf-architect and dispatch or resume aiwf-architect for {experiment_id}"
        skill = _named_skill("aiwf-architect")
        role = "Architect investigation"
    elif status == "recorded":
        action = f"run aiwf experiment finish {experiment_id}, then rerun aiwf status --prompt"
        skill = _named_skill("aiwf-architect")
        role = "Experiment cleanup"
    else:
        action = (
            f"load /aiwf-planner, run aiwf experiment show {experiment_id}, then run "
            f"aiwf experiment disposition {experiment_id} "
            "--decision proceed|replan|no_action|promote --reason '<why>'"
        )
        skill = _named_skill("aiwf-planner")
        role = "Planner decision"
    print(f"Do now: {action}.")
    print(f"Required skills: {skill}")
    print(f"Plan: {scope.get('id') or '(none)'}")
    print(f"Experiment: {experiment_id}")
    print(f"Next role: {role}")


def _installed(control: Path) -> bool:
    from ..core.project_root import has_codex_adapter, has_opencode_adapter

    return (
        (control / ".aiwf/state/state.json").exists()
        and (
            (control / ".claude/settings.json").exists()
            or (control / ".reasonix/settings.json").exists()
            or has_codex_adapter(control)
            or has_opencode_adapter(control)
        )
    )


def cmd_status(args) -> None:
    worktree = resolve_worktree_root(Path.cwd())
    control = resolve_control_root(worktree)
    if not _installed(control):
        print(f"AIWF V{VERSION}")
        print("No embedded AIWF installation found in this project.")
        print("Install with: aiwf install claude, aiwf install codex, or aiwf install opencode")
        return

    host = os.environ.get("AIWF_HOST", "").lower()
    if not host:
        from ..core.project_root import (
            has_codex_adapter,
            has_opencode_adapter,
            in_codex_session,
        )

        if has_codex_adapter(control) and in_codex_session():
            host = "codex"
        elif has_opencode_adapter(control) and not (
            control / ".claude/settings.json"
        ).exists():
            host = "opencode"
        elif (control / ".reasonix/settings.json").exists():
            host = "reasonix"
        else:
            host = "claude"
    os.environ["AIWF_HOST"] = host
    rows = _active_rows(control, host)
    current = task_for_worktree(str(worktree))
    plans_closeout = _plans_at_closeout(control)
    plans_between = _plans_between_tasks(control)
    milestones_acceptance = _milestones_at_acceptance(control)
    plan_experiment = _plan_experiment_attention(control)
    if getattr(args, "debug", False):
        _print_debug(
            control, worktree, rows, current, plans_closeout, plans_between,
            milestones_acceptance,
        )
    elif getattr(args, "prompt", False):
        _acknowledge_status_hook(control)
        if plan_experiment:
            _print_plan_experiment_prompt(plan_experiment)
            return
        _print_prompt(
            control, worktree, rows, current, plans_closeout, plans_between,
            milestones_acceptance,
        )
    else:
        _print_human(
            control, worktree, rows, current, plans_closeout, plans_between,
            milestones_acceptance,
        )
        if plan_experiment:
            print(f"Architect Plan investigation: {plan_experiment['experiment_id']} ({plan_experiment['status']}); run aiwf status --prompt for the next action.")


def _print_human(
    control: Path,
    worktree: Path,
    rows: List[Dict[str, Any]],
    current: Dict[str, Any] | None,
    plans_closeout: List[Dict[str, Any]],
    plans_between: List[Dict[str, Any]],
    milestones_acceptance: List[Dict[str, Any]],
) -> None:
    from ..core.project_root import has_codex_adapter, has_opencode_adapter

    configured_host = os.environ.get("AIWF_HOST", "").lower()
    if configured_host == "codex" or (
        has_codex_adapter(control)
        and not (control / ".claude/settings.json").exists()
        and not has_opencode_adapter(control)
    ):
        product = "Codex"
    elif configured_host == "opencode" or (
        has_opencode_adapter(control)
        and not (control / ".claude/settings.json").exists()
    ):
        product = "OpenCode"
    elif (control / ".reasonix/settings.json").exists():
        product = "Reasonix"
    else:
        product = "Claude Code"
    print(f"AIWF V{VERSION} - {product}")
    print(f"Control root: {control}")
    print(f"Current worktree: {worktree}")
    print(f"Workflow Tasks: {len(rows)}")
    if not rows and temporary_ai_writes_enabled(control):
        print("Temporary AI project writes: enabled by human")
    for row in rows:
        marker = "*" if current and current.get("id") == row["id"] else " "
        print(
            f"{marker} {row['id']}  plan={row['plan_id'] or '-'}  phase={row['phase'] or '-'}  "
            f"next={row['next_role']}"
        )
        from .task_reading import read_task_story

        story = read_task_story(control, {"id": row["id"]})
        if story.get("Intent"):
            intent = " ".join(story["Intent"].split())
            print(f"    intent={intent[:240]}" + ("… (see task show)" if len(intent) > 240 else ""))
        print(f"    worktree={row['worktree_path']}")
        if row.get("running_agent"):
            print(
                f"    agent={row['running_agent']}  "
                f"started={row.get('agent_started_at') or 'unknown'}  "
                "return=not observed"
            )
    for plan in plans_closeout:
        plan_id = plan.get("plan_id") or plan.get("id")
        state = plan.get("_integration_state")
        if state == "closure_recovery":
            print(f"Plan merge needs governance closure recovery: {plan_id}")
        elif state == "merged_unverified":
            print(f"Plan merged without an integration record: {plan_id}")
        elif state == "git_incomplete":
            print(f"Plan Git history needs attention before integration: {plan_id}")
        elif state == "held":
            print(f"Plan intentionally left open: {plan_id}")
        elif state == "no_completed_work":
            print(f"Plan has no completed result: {plan_id}")
        else:
            print(f"Plan awaiting user decision: {plan_id}")
    for plan in plans_between:
        print(f"Plan ready for next Task review: {plan.get('plan_id') or plan.get('id')}")
    for milestone in milestones_acceptance:
        verification = milestone.get("_verification_task") or {}
        print(
            f"Milestone ready for acceptance: {milestone.get('milestone_id')} "
            f"verification={verification.get('status') or 'missing'}"
        )
    if not rows and not plans_closeout and not plans_between and not milestones_acceptance:
        goal = get_active_goal(str(control))
        print(f"Planning: {goal.get('current_goal') or goal.get('active_goal') or 'no active Goal'}")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _memory_index_entries(path: Path) -> List[str]:
    entries: List[str] = []
    current = ""
    for line in _read_text(path).splitlines():
        stripped = line.strip()
        if stripped.startswith("- ["):
            if current:
                entries.append(current)
            current = stripped
        elif current and line.startswith(("  ", "\t")) and stripped:
            current += " " + stripped
        elif current:
            entries.append(current)
            current = ""
    if current:
        entries.append(current)
    return entries


def _print_planner_memory(memory_root: Path) -> None:
    print(f"Planner memory root: {memory_root}")
    print("Planner memory snapshot:")
    print("[project-facts.md]")
    print(_read_text(memory_root / "project-facts.md") or "(empty)")
    print("[MEMORY.md note index]")
    entries = _memory_index_entries(memory_root / "MEMORY.md")
    print("\n".join(entries) if entries else "(no indexed notes)")
    print("Open a note only when its index entry matches the current decision.")


def _print_prompt(
    control: Path,
    worktree: Path,
    rows: List[Dict[str, Any]],
    current: Dict[str, Any] | None,
    plans_closeout: List[Dict[str, Any]],
    plans_between: List[Dict[str, Any]],
    milestones_acceptance: List[Dict[str, Any]] | None = None,
) -> None:
    milestones_acceptance = milestones_acceptance or []
    memory_root = control / ".aiwf" / "memory"
    planner_skill = _named_skill("aiwf-planner")
    architect_skill = _named_skill("aiwf-architect")
    if not rows and temporary_ai_writes_enabled(control):
        print("Do now: complete the user's current small project-file operation directly.")
        print("Temporary AI project writes were enabled by a human in `aiwf ui`.")
        print("Do not create a Task for this operation. AIWF state and records remain protected.")
        return
    if len(rows) == 1 and not plans_closeout:
        row = rows[0]
        print(f"Do now: {row['action']}.")
        print(f"Required skills: {_skill_for(row['next_role']) or 'none'}")
        print(f"Task: {row['id']}")
        print(f"Task contract: {control / '.aiwf/tasks' / (row['id'] + '.md')}")
        print(f"Plan: {row['plan_id'] or '(none)'}")
        print(f"Worktree: {row['worktree_path']}")
        if row["next_role"] == "Human acceptance":
            print(
                "Human gate: present the recorded result and wait for explicit approval. "
                "AIWF does not dispatch, confirm, or close automatically."
            )
        elif "with SendMessage" in row["action"]:
            print(
                "Resume: try the listed Agent ID once only when it is available in this or "
                "the resumed original Claude session. If it fails, start a new Agent."
            )
        elif row["next_role"].startswith("Inline"):
            print(
                "Inline work: use relative project paths normally. AIWF routes this "
                "session's project tools to the assigned worktree."
            )
        elif row["next_role"] in ("Implementation repair", "Verification follow-up"):
            print(
                "Follow-up: work inline or dispatch the named role as directed above. "
                "AIWF routes either choice to the assigned worktree."
            )
        elif row["next_role"] == "Main-session dispatch":
            print(
                "Main-session decision: read Task.md and Task proof, choose one declared "
                "branch yourself, then load and dispatch that branch's role."
            )
        elif row["next_role"] == "Main-session freshness preflight":
            print(
                "Codex permission boundary: perform only the mechanical tree check in the "
                "stable main task; semantic acceptance remains Reviewer-owned."
            )
        elif row["next_role"] == "Reviewer reconciliation":
            print(
                "Reconciliation boundary: Reviewer owns the complete-story judgment; "
                "the main session only dispatches or resumes Reviewer."
            )
        elif row["next_role"] == "Experimenter":
            print("Dispatch: use the EXP ID above; it belongs to this Task and carries its experiment assignment.")
        elif row["next_role"] not in ("Agent running", "Experiment cleanup"):
            print(
                "Dispatch: give the Agent this Task ID. AIWF supplies the current "
                "Task contract and assigned worktree."
            )
        print(f"Next role: {row['next_role']}")
        print(
            f"State: phase={row['phase'] or '-'}, construction={row['construction_status']}, "
            f"experiments={len(row['experiment_ids'])}, review={row['review_result']}, "
            f"story={row['review_story']}, fix-loop={row['fix_loop']}"
        )
        _print_fix_loop_context(row)
        if _skill_for(row["next_role"]).endswith("aiwf-planner"):
            _print_planner_memory(memory_root)
        return

    if plans_closeout:
        print("Do now: handle each open Plan at its current closeout point:")
        for plan in plans_closeout:
            plan_id = str(plan.get("plan_id") or plan.get("id"))
            branch = str(plan.get("git_branch") or "(unknown branch)")
            base = str(plan.get("git_base_branch") or "(unknown base)")
            integration_state = plan.get("_integration_state")
            if integration_state == "closure_recovery":
                verification_status = str(
                    ((plan.get("integration") or {}).get("verification_status"))
                    or "passed"
                )
                print(
                    f"- {plan_id} | project merge completed but governance closure was interrupted | "
                    f"rerun the same aiwf plan integrate {plan_id} --status "
                    f"{verification_status} ... command with the same proof and gap arguments. "
                    "It will not merge the candidate again."
                )
            elif integration_state == "merged_unverified":
                print(
                    f"- {plan_id} | already merged without integration proof | run "
                    f"aiwf plan integrate {plan_id}, verify the adopted candidate, and record "
                    "the exact results to finish the Plan."
                )
            elif integration_state == "awaiting_decision":
                print(
                    f"- {plan_id} | awaiting user decision | ask whether to add another Task, "
                    f"leave {branch} open, or merge it into {base}. Do not merge before the user chooses. "
                    f"If they choose to leave it open, run aiwf plan hold {plan_id}."
                )
            elif integration_state == "integration_ready":
                from ..core.git_workflow import changed_project_files

                candidate_path = str(
                    ((plan.get("integration") or {}).get("candidate_worktree"))
                    or plan.get("git_worktree_path") or "(candidate worktree missing)"
                )
                dirty = (
                    changed_project_files(candidate_path)
                    if Path(candidate_path).exists()
                    else []
                )
                if dirty:
                    print(
                        f"- {plan_id} | candidate worktree changed after preparation: "
                        f"{', '.join(dirty[:6])} | the old candidate is stale. Planner classifies "
                        "the change: resolve local, generated, or non-semantic integration work "
                        "directly; use a Task only for semantic project work. Then rerun the same "
                        "plan integrate command before proof."
                    )
                else:
                    print(
                        f"- {plan_id} | candidate prepared at {candidate_path} | run its integration "
                        f"checks there. Before merge, ask whether the user wants {architect_skill} "
                        "on this exact candidate; the user chooses one or several Plans whose "
                        "results are present in it. If a finding changes the candidate, resolve "
                        "environment, generated, or non-semantic work directly and use a Task "
                        "only for semantic project work; then prepare again. Otherwise, after the user declines or "
                        "decides the findings, write Plan.md '## Closure Calibration' with "
                        "the actual outcome and only any difference or remaining gap that "
                        "matters. Then run "
                        f"aiwf plan integrate {plan_id} --status passed ...; it records the exact "
                        "results, immediately merges the passing candidate, and closes the Plan. "
                        "If an original Plan outcome remains unmet, do not call it passed: after "
                        "showing the observed result and consequence, ask whether the user explicitly "
                        "accepts closing with that gap. If they do, use --status accepted_with_gaps "
                        "with machine-readable --known-gap and --acceptance-reason arguments. If the user "
                        f"wants to keep it open instead, run aiwf plan hold {plan_id}."
                    )
            elif integration_state == "integration_audit":
                integration = plan.get("integration", {}) or {}
                audit = integration.get("audit", {}) or {}
                blocking = "; ".join(audit.get("blocking", []) or [])
                print(
                    f"- {plan_id} | integration audit | {blocking or 'inspect advisory assets'}. "
                    "No candidate has been prepared. Planner may use normal editing and Git "
                    "to classify and resolve local residue, deliverable assets, reproducible "
                    "output, or unknown risk; then rerun the same aiwf plan integrate command."
                )
            elif integration_state == "integration_conflict":
                print(
                    f"- {plan_id} | integration conflict\n"
                    "  Planner inspects the actual diff and chooses the lightest honest path. "
                    "Small Git, generated-file, or environment conflicts may be resolved directly "
                    "in the Plan worktree with normal Git, without a Task or role dispatch; then "
                    f"rerun aiwf plan integrate {plan_id}. If resolution changes behavior, "
                    "interfaces, dependencies, or product meaning, create one kind=integration "
                    "Task. Explain meaningful resolution choices in Plan Closure Calibration."
                )
            elif integration_state == "integration_failed":
                print(
                    f"- {plan_id} | integration proof failed | inspect the failure and add or repair "
                    "a Task before preparing the Plan again."
                )
            elif integration_state == "base_changed":
                print(
                    f"- {plan_id} | {base} changed after preparation | rerun "
                    f"aiwf plan integrate {plan_id}; old proof does not apply."
                )
            elif integration_state == "held":
                print(
                    f"- {plan_id} | intentionally left open at "
                    f"{str(plan.get('integration_hold_ref') or '')[:12]} | do not ask again or merge. "
                    "Revisit only when the user asks or the Plan result changes."
                )
            elif integration_state == "no_completed_work":
                print(
                    f"- {plan_id} | all Tasks cancelled | ask whether to add a Task or cancel the Plan. "
                    "There is no completed result to merge."
                )
            else:
                print(
                    f"- {plan_id} | Git history incomplete | run aiwf plan show {plan_id} "
                    "and repair its branch/base/head record before integration."
                )
        if rows:
            print("Other active Tasks:")
    elif rows:
        ready = [row for row in rows if row["next_role"] != "Agent running"]
        running = [row for row in rows if row["next_role"] == "Agent running"]
        if ready and running:
            print(
                "Do now: advance the ready Tasks below now. Do not wait for Agents in other "
                "Plan worktrees; process each Plan as its Agent returns."
            )
        elif running:
            print(
                "Do now: no Task is ready for another role. Wait for the next individual Agent "
                "return without stopping, retrying, or substituting it."
            )
        else:
            print(
                "Do now: manage the ready Plan worktrees below. Dispatch each Task's next role "
                "with its Task ID and assigned worktree. Independent Plans may run in parallel."
            )
    elif plans_between:
        plan_ids = ", ".join(
            str(plan.get("plan_id") or plan.get("id")) for plan in plans_between
        )
        print(
            f"Do now: load {planner_skill}. Before the next Task in {plan_ids}, compare the "
            "completed Task Calibration and proof with the Plan, correct changed assumptions, "
            "and maintain memory."
        )
        print(f"Required skills: {planner_skill}")
        _print_planner_memory(memory_root)
        return
    elif milestones_acceptance:
        print("Do now: advance each ready Milestone to explicit acceptance. AIWF only routes this work; it does not create a Task, dispatch Architect, confirm, or close automatically:")
        required = set()
        for milestone in milestones_acceptance:
            milestone_id = str(milestone.get("milestone_id") or milestone.get("id"))
            verification = milestone.get("_verification_task") or {}
            verification_id = str(verification.get("id") or "")
            verification_status = str(verification.get("status") or "")
            acceptance = milestone.get("user_acceptance", {}) or {}
            synthesis = milestone.get("stage_synthesis", {}) or {}
            if not verification:
                required.add(planner_skill)
                print(
                    f"- {milestone_id} | verification Task missing | load {planner_skill}; "
                    "choose a Task ID, create kind=milestone_verification with "
                    f"--milestone-id {milestone_id}, write its contract from "
                    f"{control / '.aiwf/milestones' / (milestone_id + '.md')}, link it with "
                    f"aiwf milestone link-task {milestone_id} <TASK-ID>, then critique and activate it"
                )
            elif verification_status in ("ready", "suspended"):
                required.add(planner_skill)
                print(
                    f"- {milestone_id} | verification Task {verification_id} "
                    f"status={verification_status} | load {planner_skill}, inspect its contract, "
                    "complete activation critique if needed, and activate or resume it"
                )
            elif verification_status == "closed" and acceptance.get("status") == "confirmed":
                required.add(planner_skill)
                print(
                    f"- {milestone_id} | accepted verification Task {verification_id} closed | "
                    f"run aiwf milestone close {milestone_id}"
                )
            elif verification_status == "closed":
                required.add(planner_skill)
                print(
                    f"- {milestone_id} | verification Task {verification_id} closed before "
                    f"Milestone acceptance completed | load {planner_skill} and inspect the inconsistent "
                    "state; do not claim or force Milestone closure"
                )
            elif synthesis.get("verdict") in ("PASS", "PASS_WITH_RISK"):
                print(
                    f"- {milestone_id} | technical assessment passed | present its summary and "
                    f"risks, then ask the user whether to run aiwf milestone confirm {milestone_id}"
                )
            else:
                required.add(architect_skill)
                print(
                    f"- {milestone_id} | verification Task {verification_id} active | load "
                    f"{architect_skill} and dispatch an independent Architect with milestone-acceptance; "
                    f"Milestone.md is authoritative"
                )
        print("Required skills: " + (", ".join(sorted(required)) if required else "none"))
        return
    else:
        print(
            f"Do now: load {planner_skill}. Discuss and investigate before creating or changing "
            "Mission, Goal, Plan, or Task documents."
        )
        print(f"Required skills: {planner_skill}")
        _print_planner_memory(memory_root)
        return

    required = sorted({
        skill for row in rows
        if (skill := _skill_for(row["next_role"]))
    })
    if plans_closeout:
        required = sorted(set(required) | {planner_skill})
    print("Required skills: " + (", ".join(required) if required else "none"))

    current_id = str((current or {}).get("id") or "")
    display_rows = sorted(
        rows,
        key=lambda row: (
            row["next_role"] == "Agent running",
            row["id"] != current_id,
            row["id"],
        ),
    )
    for row in display_rows:
        marker = " [current]" if row["id"] == current_id else ""
        print(
            f"- {row['id']}{marker} | plan={row['plan_id'] or '-'} | "
            f"do={row['action']} | next={row['next_role']} | "
            f"skill={_skill_for(row['next_role'])} | "
            f"evidence=construction:{row['construction_status']},"
            f"experiments:{len(row['experiment_ids'])},review:{row['review_result']},"
            f"story:{row['review_story']} | worktree={row['worktree_path']}"
        )
        _print_fix_loop_context(row)
    if any(skill.endswith("aiwf-planner") for skill in required):
        _print_planner_memory(memory_root)


def _print_debug(
    control: Path,
    worktree: Path,
    rows: List[Dict[str, Any]],
    current: Dict[str, Any] | None,
    plans_closeout: List[Dict[str, Any]],
    plans_between: List[Dict[str, Any]],
    milestones_acceptance: List[Dict[str, Any]],
) -> None:
    state = _read_json(control / ".aiwf/state/state.json", {})
    plans = load_plans(str(control), migrate=False)
    ledger = load_ledger(str(control))
    records = {
        str(task.get("id")): load_task_record(control, str(task.get("id")))
        for task in ledger.get("tasks", []) or []
        if isinstance(task, dict) and task.get("id")
    }
    print(json.dumps({
        "version": VERSION,
        "control_root": str(control),
        "current_worktree": str(worktree),
        "current_task_id": (current or {}).get("id", ""),
        "active_tasks": rows,
        "plans_at_closeout": [
            plan.get("plan_id") or plan.get("id") for plan in plans_closeout
        ],
        "plans_needing_closure_recovery": [
            plan.get("plan_id") or plan.get("id")
            for plan in plans_closeout
            if plan.get("_integration_state") == "closure_recovery"
        ],
        "plans_awaiting_integration_decision": [
            plan.get("plan_id") or plan.get("id")
            for plan in plans_closeout
            if plan.get("_integration_state") == "awaiting_decision"
        ],
        "plans_intentionally_held": [
            plan.get("plan_id") or plan.get("id")
            for plan in plans_closeout if plan.get("_integration_state") == "held"
        ],
        "plans_between_tasks": [
            plan.get("plan_id") or plan.get("id") for plan in plans_between
        ],
        "milestones_at_acceptance": [
            milestone.get("milestone_id") or milestone.get("id")
            for milestone in milestones_acceptance
        ],
        "state": state,
        "plans": plans,
        "tasks": ledger,
        "task_records": records,
    }, ensure_ascii=False, indent=2))
