"""Concise human and model status for the embedded workflow."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..constants import VERSION
from ..core.agent_runtime import WORKFLOW_ROLES, resumable_agent, running_dispatches
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


def _hook_problem(task: Dict[str, Any], record: Dict[str, Any]) -> str:
    fix_loop = record.get("fix_loop", {}) or {}
    if fix_loop.get("status") == "open":
        return f"{task['id']} fix-loop routes to {fix_loop.get('route') or 'planner'}"
    review = record.get("review", {}) or {}
    if review.get("result") in (
        "rejected", "needs_fix", "needs_more_testing", "scope_violation",
    ):
        return f"{task['id']} review={review.get('result')}"
    if task.get("scope_violation"):
        return f"{task['id']} has a scope violation"
    return ""


def _acknowledge_status_hook(control: Path) -> None:
    """Tell the short UserPrompt hook that this routing state was already read."""
    workflow_tasks = [
        task for task in load_ledger(str(control)).get("tasks", []) or []
        if isinstance(task, dict) and task.get("status") in ("active", "suspended")
    ]
    active = [task for task in workflow_tasks if task.get("status") == "active"]
    problems: List[str] = []
    tasks: List[Dict[str, Any]] = []
    for task in workflow_tasks:
        record = load_task_record(control, str(task.get("id") or ""))
        problem = _hook_problem(task, record)
        if problem:
            problems.append(problem)
        tasks.append({
            "id": task.get("id", ""),
            "phase": task.get("phase", ""),
            "worktree": task.get("worktree_path", ""),
            "testing": (record.get("testing", {}) or {}).get("status", "missing"),
            "review": (record.get("review", {}) or {}).get("result", "unknown"),
            "fix": (record.get("fix_loop", {}) or {}).get("status", "none"),
        })
    tasks.sort(key=lambda task: str(task.get("id") or ""))
    fingerprint = {
        "tasks": tasks,
        "problems": sorted(problems),
        "temporary_ai_writes": temporary_ai_writes_enabled(control) and not active,
    }
    path = control / ".aiwf/runtime/internal/status-hook-last.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(fingerprint, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def _task_next(
    task: Dict[str, Any],
    record: Dict[str, Any],
    control: Path | None = None,
    host: str = "",
) -> Tuple[str, str]:
    host = (host or os.environ.get("AIWF_HOST", "claude")).lower()
    task_id = str(task.get("id") or "")
    requirements = task.get("requirements", {}) or {}
    fix_loop = record.get("fix_loop", {}) or {}
    if fix_loop.get("status") == "open":
        if fix_loop.get("escalation_required"):
            return (
                "Planner decision",
                f"load /aiwf-planner and run aiwf fixloop status --task-id {task_id}; "
                "tell the user what failed and what still needs verification, then ask them to choose: "
                f"continue with aiwf fixloop continue --task-id {task_id}; pause and replan with "
                f"aiwf task interrupt {task_id}; or accept the unmet checks and close with "
                f"aiwf task force-close {task_id}. These commands are human-only. If they continue, "
                "run aiwf status --prompt again and follow its route",
            )
        route = str(fix_loop.get("route") or "planner")
        if route == "executor":
            previous = (
                resumable_agent(
                    control, task_id=task_id, subagent_type="aiwf-executor",
                )
                if control else None
            )
            if previous:
                if host == "opencode":
                    agent_route = (
                        f"otherwise continue the previous aiwf-executor child once with "
                        f"task_id {previous['agent_id']} and tell it to read aiwf task proof "
                        f"{task_id}; if continuation is unavailable, dispatch a new "
                        "aiwf-executor with the Task ID and current finding"
                    )
                else:
                    agent_route = (
                        f"otherwise, if available in this or the resumed original Claude session, "
                        f"try once to resume aiwf-executor {previous['agent_id']} with "
                        f"SendMessage: 'Resume {task_id} repair. Run aiwf task proof "
                        f"{task_id}, fix the current finding, record implementation, and return'; "
                        "if unavailable or resume fails, dispatch a new aiwf-executor with the "
                        "Task ID and current finding"
                    )
            else:
                agent_route = "otherwise dispatch aiwf-executor"
            return (
                "Implementation repair",
                f"load /aiwf-implement for {task_id}; repair and record inline if tiny "
                f"and clear; {agent_route}",
            )
        if route == "tester":
            return (
                "Verification follow-up",
                f"load /aiwf-test for {task_id}; retest inline if narrow and exact, "
                "otherwise dispatch aiwf-tester, then record testing",
            )
        return (
            "Planner decision",
            f"load /aiwf-planner, run aiwf fixloop status --task-id {task_id}, "
            "then resolve the decided issue or reroute remaining work",
        )

    implementation = record.get("implementation", {}) or {}
    testing = record.get("testing", {}) or {}
    review = record.get("review", {}) or {}
    if not implementation.get("implementation_ref"):
        if requirements.get("executor_required", True):
            previous = (
                resumable_agent(
                    control, task_id=task_id, subagent_type="aiwf-executor",
                )
                if control else None
            )
            if previous:
                if host == "opencode":
                    return (
                        "Executor",
                        f"load /aiwf-implement; continue the previous aiwf-executor child once "
                        f"with task_id {previous['agent_id']} and tell it to reread Task.md, "
                        "the current diff, and missing work; if continuation is unavailable, "
                        "dispatch a new aiwf-executor for the Task",
                    )
                return (
                    "Executor",
                    f"load /aiwf-implement; if available in this or the resumed original Claude "
                    f"session, try once to resume aiwf-executor {previous['agent_id']} "
                    f"with SendMessage: 'Resume {task_id}. Reread Task.md and the current "
                    "diff, finish any missing work, record implementation, and return'; "
                    "if unavailable or resume fails, dispatch a new aiwf-executor for the Task",
                )
            return "Executor", f"load /aiwf-implement and dispatch aiwf-executor for {task_id}"
        return "Inline implementation", f"load /aiwf-implement, implement {task_id} inline, and record it"
    proof_gaps: List[str] = []
    if (
        control
        and testing.get("tested_ref")
        and testing.get("status") in ("partial", "passed")
    ):
        from ..core.task_proof import testing_proof_gaps, validate_testing_against_task

        proof_gaps = testing_proof_gaps(
            validate_testing_against_task(str(control), task, testing)
        )
    if (
        testing.get("status") not in ("adequate", "passed")
        or not testing.get("tested_ref")
        or proof_gaps
    ):
        if requirements.get("tester_required", True):
            previous = (
                resumable_agent(
                    control, task_id=task_id, subagent_type="aiwf-tester",
                )
                if control else None
            )
            if previous:
                if host == "opencode":
                    return (
                        "Tester",
                        f"load /aiwf-test; continue the previous aiwf-tester child once with "
                        f"task_id {previous['agent_id']} and tell it to read aiwf task proof "
                        f"{task_id} and complete only missing verification; if continuation is "
                        "unavailable, dispatch a new aiwf-tester for the Task",
                    )
                return (
                    "Tester",
                    f"load /aiwf-test; if available in this or the resumed original Claude "
                    f"session, try once to resume aiwf-tester {previous['agent_id']} with "
                    f"SendMessage: 'Resume {task_id} testing. Read aiwf task proof, complete "
                    "only missing verification, record testing, and return'; if unavailable or "
                    "resume fails, dispatch a new aiwf-tester for the Task",
                )
            if proof_gaps:
                missing = ", ".join(proof_gaps[:5])
                return (
                    "Tester",
                    f"load /aiwf-test and complete the missing proof for {task_id}: {missing}; "
                    "valid results on the unchanged tested snapshot are preserved",
                )
            return "Tester", f"load /aiwf-test and dispatch aiwf-tester for {task_id}"
        return "Inline testing", f"load /aiwf-test, test {task_id} inline, and record it"
    pending = [
        item for item in review.get("adversarial_observations", []) or []
        if isinstance(item, dict) and item.get("disposition") == "pending"
    ]
    if review.get("result") == "accepted" and pending:
        return (
            "Planner decision",
            f"load /aiwf-planner and disposition {len(pending)} Reviewer observation(s) for {task_id}; "
            "fix an observation now when that is safe, bounded, and verifiable in this cycle; "
            "before choosing deferred, explain why it should wait and its return trigger, ask the "
            "user to agree, then write it into its downstream Task or "
            ".aiwf/memory/notes/deferred-findings.md",
        )
    if review.get("result") != "accepted" or not review.get("closure_allowed", False):
        if requirements.get("reviewer_required", True):
            previous = (
                resumable_agent(
                    control, task_id=task_id, subagent_type="aiwf-reviewer",
                )
                if control else None
            )
            if previous:
                if host == "opencode":
                    return (
                        "Reviewer",
                        f"load /aiwf-review; continue the previous aiwf-reviewer child once "
                        f"with task_id {previous['agent_id']} and tell it to reconcile Task.md, "
                        "the tested snapshot, and its report; if continuation is unavailable, "
                        "dispatch a new aiwf-reviewer for the Task",
                    )
                return (
                    "Reviewer",
                    f"load /aiwf-review; if available in this or the resumed original Claude "
                    f"session, try once to resume aiwf-reviewer {previous['agent_id']} with "
                    f"SendMessage: 'Resume {task_id} review. Reconcile Task.md, the tested "
                    "snapshot, and your report, record review, and return'; if unavailable or "
                    "resume fails, dispatch a new aiwf-reviewer for the Task",
                )
            return "Reviewer", f"load /aiwf-review and dispatch aiwf-reviewer for {task_id}"
        return "Inline review", f"load /aiwf-review, review {task_id} inline, and record it"
    deferred = [
        item for item in review.get("adversarial_observations", []) or []
        if isinstance(item, dict) and item.get("disposition") == "deferred"
    ]
    if deferred:
        return (
            "Close",
            f"load /aiwf-close; confirm {len(deferred)} deferred Reviewer observation(s) "
            "are written in a downstream Task or .aiwf/memory/notes/deferred-findings.md, "
            f"calibrate Task.md if needed, then close {task_id}",
        )
    return "Close", f"load /aiwf-close, calibrate Task.md if needed, then close {task_id}"


def _skill_for(next_role: str) -> str:
    return {
        "Executor": "/aiwf-implement",
        "Implementation repair": "/aiwf-implement",
        "Inline implementation": "/aiwf-implement",
        "Tester": "/aiwf-test",
        "Verification follow-up": "/aiwf-test",
        "Inline testing": "/aiwf-test",
        "Reviewer": "/aiwf-review",
        "Inline review": "/aiwf-review",
        "Close": "/aiwf-close",
        "Planner calibration": "/aiwf-planner",
        "Planner decision": "/aiwf-planner",
        "Agent running": "",
    }.get(next_role, "/aiwf-planner")


def _active_rows(control: Path, host: str = "") -> List[Dict[str, Any]]:
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
            if fix_loop.get("status") == "open":
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
        rows.append({
            "id": task_id,
            "task_status": task.get("status", ""),
            "plan_id": task.get("plan_id") or task.get("parent_plan") or "",
            "phase": task.get("phase", ""),
            "worktree_path": task.get("worktree_path", ""),
            "next_role": next_role,
            "action": action,
            "implementation_ref": (record.get("implementation", {}) or {}).get("implementation_ref", ""),
            "testing_status": (record.get("testing", {}) or {}).get("status", "missing"),
            "review_result": (record.get("review", {}) or {}).get("result", "unknown"),
            "fix_loop": (record.get("fix_loop", {}) or {}).get("status", "none"),
            "calibration_missing": calibration_missing,
            "running_agent": running[0]["subagent_type"] if len(running) == 1 else "",
            "agent_started_at": running[0].get("started_at", "") if len(running) == 1 else "",
        })
    return rows


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


def _installed(control: Path) -> bool:
    return (
        (control / ".aiwf/state/state.json").exists()
        and (
            (control / ".claude/settings.json").exists()
            or (control / ".reasonix/settings.json").exists()
            or (control / ".opencode/plugins/aiwf.js").exists()
        )
    )


def cmd_status(args) -> None:
    worktree = resolve_worktree_root(Path.cwd())
    control = resolve_control_root(worktree)
    if not _installed(control):
        print(f"AIWF V{VERSION}")
        print("No embedded AIWF installation found in this project.")
        print("Install with: aiwf install claude or aiwf install opencode")
        return

    host = os.environ.get("AIWF_HOST", "").lower()
    if not host:
        if (control / ".opencode/plugins/aiwf.js").exists() and not (
            control / ".claude/settings.json"
        ).exists():
            host = "opencode"
        elif (control / ".reasonix/settings.json").exists():
            host = "reasonix"
        else:
            host = "claude"
    rows = _active_rows(control, host)
    current = task_for_worktree(str(worktree))
    plans_closeout = _plans_at_closeout(control)
    plans_between = _plans_between_tasks(control)
    if getattr(args, "debug", False):
        _print_debug(control, worktree, rows, current, plans_closeout, plans_between)
    elif getattr(args, "prompt", False):
        _acknowledge_status_hook(control)
        _print_prompt(control, worktree, rows, current, plans_closeout, plans_between)
    else:
        _print_human(control, worktree, rows, current, plans_closeout, plans_between)


def _print_human(
    control: Path,
    worktree: Path,
    rows: List[Dict[str, Any]],
    current: Dict[str, Any] | None,
    plans_closeout: List[Dict[str, Any]],
    plans_between: List[Dict[str, Any]],
) -> None:
    if os.environ.get("AIWF_HOST", "").lower() == "opencode" or (
        (control / ".opencode/plugins/aiwf.js").exists()
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
        if state == "merged_pending_close":
            print(f"Plan merged; ready to verify and close: {plan_id}")
        elif state == "merged_unverified":
            print(f"Plan merged without an integration record: {plan_id}")
        elif state == "git_incomplete":
            print(f"Plan Git history needs attention before close: {plan_id}")
        elif state == "held":
            print(f"Plan intentionally left open: {plan_id}")
        elif state == "no_completed_work":
            print(f"Plan has no completed result: {plan_id}")
        else:
            print(f"Plan awaiting user decision: {plan_id}")
    for plan in plans_between:
        print(f"Plan ready for next Task review: {plan.get('plan_id') or plan.get('id')}")
    if not rows and not plans_closeout and not plans_between:
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
) -> None:
    memory_root = control / ".aiwf" / "memory"
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
        if "with SendMessage" in row["action"]:
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
        elif row["next_role"] != "Agent running":
            print(
                "Dispatch: give the Agent this Task ID. AIWF supplies the current "
                "Task contract and assigned worktree."
            )
        print(f"Next role: {row['next_role']}")
        print(
            f"State: phase={row['phase'] or '-'}, testing={row['testing_status']}, "
            f"review={row['review_result']}, fix-loop={row['fix_loop']}"
        )
        if _skill_for(row["next_role"]) == "/aiwf-planner":
            _print_planner_memory(memory_root)
        return

    if plans_closeout:
        print("Do now: handle each open Plan at its current closeout point:")
        awaiting = [
            plan for plan in plans_closeout
            if plan.get("_integration_state") == "awaiting_decision"
        ]
        if awaiting:
            print(
                "Before merge, ask whether the user wants /aiwf-architect. Review one Plan "
                "alone; review independent Plans one by one; or review several Plans as one "
                "slice when they form one capability path. Architect reports; it does not "
                "replace integration proof or merge the branches."
            )
        for plan in plans_closeout:
            plan_id = str(plan.get("plan_id") or plan.get("id"))
            branch = str(plan.get("git_branch") or "(unknown branch)")
            base = str(plan.get("git_base_branch") or "(unknown base)")
            integration_state = plan.get("_integration_state")
            if integration_state == "merged_pending_close":
                print(
                    f"- {plan_id} | verified candidate merged into {base} | close this Plan now."
                )
            elif integration_state == "merged_unverified":
                print(
                    f"- {plan_id} | already merged without integration proof | run "
                    f"aiwf plan integrate {plan_id}, verify the adopted candidate, and record "
                    "the exact results before close."
                )
            elif integration_state == "awaiting_decision":
                print(
                    f"- {plan_id} | awaiting user decision | ask whether to add another Task, "
                    f"leave {branch} open, or merge it into {base}. Do not merge before the user chooses. "
                    f"If they choose to leave it open, run aiwf plan hold {plan_id}."
                )
            elif integration_state == "integration_ready":
                candidate_path = str(
                    ((plan.get("integration") or {}).get("candidate_worktree"))
                    or plan.get("git_worktree_path") or "(candidate worktree missing)"
                )
                print(
                    f"- {plan_id} | candidate prepared at {candidate_path} | run its integration "
                    "checks there, then record "
                    f"the exact results with aiwf plan integrate {plan_id} --status passed ..."
                )
            elif integration_state == "integration_conflict":
                print(
                    f"- {plan_id} | base and Plan conflict | create a kind=integration Task under "
                    "this Plan, resolve it through Executor, Tester, Reviewer, and close, then rerun "
                    f"aiwf plan integrate {plan_id}."
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
                    "and repair its branch/base/head record before close."
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
            f"Do now: load /aiwf-planner. Before the next Task in {plan_ids}, compare the "
            "completed Task Calibration and proof with the Plan, correct changed assumptions, "
            "and maintain memory."
        )
        print("Required skills: /aiwf-planner")
        _print_planner_memory(memory_root)
        return
    else:
        print(
            "Do now: load /aiwf-planner. Discuss and investigate before creating or changing "
            "Mission, Goal, Plan, or Task documents."
        )
        print("Required skills: /aiwf-planner")
        _print_planner_memory(memory_root)
        return

    required = sorted({
        skill for row in rows
        if (skill := _skill_for(row["next_role"]))
    })
    if plans_closeout:
        required = sorted(set(required) | {"/aiwf-planner"})
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
            f"skill={_skill_for(row['next_role'])} | worktree={row['worktree_path']}"
        )
    if "/aiwf-planner" in required:
        _print_planner_memory(memory_root)


def _print_debug(
    control: Path,
    worktree: Path,
    rows: List[Dict[str, Any]],
    current: Dict[str, Any] | None,
    plans_closeout: List[Dict[str, Any]],
    plans_between: List[Dict[str, Any]],
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
        "plans_merged_ready_to_close": [
            plan.get("plan_id") or plan.get("id")
            for plan in plans_closeout
            if plan.get("_integration_state") == "merged_pending_close"
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
        "state": state,
        "plans": plans,
        "tasks": ledger,
        "task_records": records,
    }, ensure_ascii=False, indent=2))
