"""Scope checker — project writes require active task; executor dispatch per Task.requirements."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import subprocess

from ...core.event_model import NormalizedEvent, ScopeResult
from ...core.scope_policy import check_scope, check_bash_command
from ...core.state.goal_ops import get_active_goal
from ...core.task_ledger import active_tasks, task_for_worktree
from ...core.task_records import load_task_record
from ...core.temporary_access import MARKER as TEMPORARY_AI_WRITES_MARKER
from ...core.temporary_access import temporary_ai_writes_enabled
from ...core.worktree_context import resolve_control_root
from .worktree_guard import (
    foreign_bash_write,
    foreign_worktree_target,
    managed_worktrees,
    shell_write_targets,
)


DEFAULT_WRITE_POLICY: Dict[str, Any] = {
    "project_writes_require_active_task": True,
    "freeze_active_task_md": True,
    "first_implementation_requires_executor": True,
    "tester_project_writes": "test_assets_only",
    "architect_project_writes": "reports_only",
    "explorer_project_writes": "deny",
    "critic_project_writes": "deny",
}

HUMAN_ONLY_COMMANDS = {
    "aiwf task force-close": "force-close bypasses all Task gates",
    "aiwf task interrupt": "interrupt releases the active Task execution window",
}


def _read_json(path: Path, default: Dict) -> Dict:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _read_write_policy(cwd: Path) -> Dict[str, Any]:
    """Read project write policy, falling back to today's strict defaults."""
    policy = dict(DEFAULT_WRITE_POLICY)
    raw = _read_json(cwd / ".aiwf" / "config" / "write-policy.json", {})
    if not isinstance(raw, dict):
        return policy
    for key in (
        "project_writes_require_active_task",
        "freeze_active_task_md",
        "first_implementation_requires_executor",
    ):
        if isinstance(raw.get(key), bool):
            policy[key] = raw[key]
    if raw.get("tester_project_writes") in ("deny", "test_assets_only", "allow_all"):
        policy["tester_project_writes"] = raw["tester_project_writes"]
    for key in ("explorer_project_writes", "critic_project_writes"):
        if raw.get(key) in ("deny", "allow"):
            policy[key] = raw[key]
    if raw.get("architect_project_writes") in ("deny", "reports_only", "allow"):
        policy["architect_project_writes"] = raw["architect_project_writes"]
    return policy


def _role_project_write_mode(role: str, write_policy: Dict[str, Any]) -> str:
    role = role.lower()
    if "architect" in role:
        return str(write_policy.get("architect_project_writes") or "deny")
    if "explorer" in role:
        return str(write_policy.get("explorer_project_writes") or "deny")
    if "critic" in role:
        return str(write_policy.get("critic_project_writes") or "deny")
    return "allow"


def _role_read_only_name(role: str) -> str:
    role = role.lower()
    for name in ("architect", "explorer", "critic"):
        if name in role:
            return f"aiwf-{name}"
    return "this role"


def _configured_read_only_role_can_write(role: str, write_policy: Dict[str, Any]) -> bool:
    role = role.lower()
    return (
        any(name in role for name in ("architect", "explorer", "critic"))
        and _role_project_write_mode(role, write_policy) == "allow"
    )


def _is_architect_report_path(path: str) -> bool:
    """Return whether path is an Architect-owned Markdown report."""
    parts = Path(path).parts
    return (
        len(parts) >= 4
        and parts[0] == "docs"
        and parts[1] == "architect"
        and parts[2].startswith("ARCH-")
        and ".." not in parts
        and parts[-1].lower().endswith(".md")
    )


def _is_gitignored(file_path: str, cwd: Path) -> bool:
    # Fast path: no .git directory means not a git repo
    if not (cwd / ".git").exists():
        return False
    try:
        r = subprocess.run(
            ["git", "check-ignore", "-q", file_path],
            capture_output=True, cwd=str(cwd), timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


def _get_active_task_requirements(cwd: Path, task_id: str) -> Optional[Dict[str, Any]]:
    """Read the active task's requirements from Task.md frontmatter.

    Reads directly from the MD contract, not from synced JSON. This means
    editing Task.md and changing executor_required takes effect immediately
    without needing aiwf sync — same as forbidden_write already works.
    """
    if not task_id:
        return None
    control = resolve_control_root(cwd)
    task_md = control / ".aiwf" / "tasks" / f"{task_id}.md"
    if not task_md.exists():
        return None
    try:
        text = task_md.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            return None
        end_idx = text.find("\n---\n", 4)
        if end_idx == -1:
            return None
        import yaml
        fm = yaml.safe_load(text[4:end_idx]) or {}
        reqs = {}
        for key in ("executor_required", "tester_required", "reviewer_required"):
            val = fm.get(key)
            if isinstance(val, bool):
                reqs[key] = val
        tester_write = fm.get("tester_write", [])
        if isinstance(tester_write, list):
            reqs["tester_write"] = [str(x).strip() for x in tester_write if str(x).strip()]
        elif isinstance(tester_write, str) and tester_write.strip():
            reqs["tester_write"] = [s.strip() for s in tester_write.replace(",", " ").split() if s.strip()]
        return reqs or None
    except Exception:
        return None


def _get_task_forbidden_write(cwd: Path, task_id: str) -> list:
    """Read forbidden_write from active Task.md frontmatter."""
    task_md = resolve_control_root(cwd) / ".aiwf" / "tasks" / f"{task_id}.md"
    if not task_md.exists():
        return []
    try:
        text = task_md.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            return []
        end_idx = text.find("\n---\n", 4)
        if end_idx == -1:
            return []
        import yaml
        fm = yaml.safe_load(text[4:end_idx]) or {}
        fw = fm.get("forbidden_write", [])
        if isinstance(fw, list):
            return [str(x).strip() for x in fw if str(x).strip()]
        if isinstance(fw, str) and fw.strip():
            return [s.strip() for s in fw.replace(",", " ").split() if s.strip()]
        return []
    except Exception:
        return []


def _is_test_asset_path(path: str) -> bool:
    """Return True for project test/verification assets a tester may write."""
    p = path.strip().lstrip("./").replace("\\", "/")
    parts = p.split("/")
    filename = parts[-1] if parts else p
    lowered = p.lower()
    lower_name = filename.lower()
    test_dirs = {
        "test",
        "tests",
        "__tests__",
        "spec",
        "specs",
        "e2e",
        "integration",
        "integration_tests",
        "fixtures",
        "__fixtures__",
        "snapshots",
        "__snapshots__",
        "golden",
        "goldens",
        "expected",
    }

    if any(part.lower() in test_dirs for part in parts[:-1]):
        return True
    if lower_name.startswith("test_") or lower_name.startswith("test-"):
        return True
    if any(marker in lower_name for marker in (
        ".test.", ".spec.",
        "_test.", "-test.", "_spec.", "-spec.",
        "_tests.", "-tests.",
        ".e2e.", "_e2e.", "-e2e.",
        ".integration.", "_integration.", "-integration.",
        "_validation.", "-validation.", ".validation.",
    )):
        return True
    if lower_name in {
        "tests.rs",
        "test.rs",
        "conftest.py",
        "pytest.ini",
        "tox.ini",
        "jest.config.js",
        "jest.config.ts",
        "vitest.config.js",
        "vitest.config.ts",
        "playwright.config.js",
        "playwright.config.ts",
    }:
        return True
    if lowered.endswith((".snap", ".snapshot", ".golden", ".expected")):
        return True
    return False


def _tester_write_allowed(path: str, reqs: Dict[str, Any]) -> bool:
    from ...core.scope_policy import _matches

    tester_write = [str(p).strip() for p in (reqs.get("tester_write") or []) if str(p).strip()]
    if tester_write:
        return any(_matches(path, pattern) for pattern in tester_write)
    return _is_test_asset_path(path)


def _is_planner_inline_role(role: str) -> bool:
    if not role:
        return True
    if any(blocked in role for blocked in ("executor", "tester", "reviewer", "architect")):
        return False
    return "planner" in role or "main" in role


def _is_planner_owned_governance_path(path: str) -> bool:
    return (
        path == ".aiwf/mission.md"
        or any(
            path.startswith(prefix)
            for prefix in (
                ".aiwf/goals/",
                ".aiwf/plans/",
                ".aiwf/tasks/",
                ".aiwf/milestones/",
                ".aiwf/memory/",
                ".aiwf/config/",
            )
        )
    )


def _has_any_active_task(control: Path) -> bool:
    ledger = _read_json(control / ".aiwf" / "state" / "tasks.json", {"tasks": []})
    return any(
        isinstance(task, dict) and task.get("status") == "active"
        for task in ledger.get("tasks", []) or []
    )


def _temporary_project_writes_allowed(
    control: Path,
    role: str,
    write_policy: Dict[str, Any],
) -> bool:
    return (
        temporary_ai_writes_enabled(control)
        and not _has_any_active_task(control)
        and _role_project_write_mode(role, write_policy) == "allow"
    )


def _project_shell_write_targets(command: str, cwd: Path, control: Path) -> list[str]:
    """Return explicit shell write targets inside any managed project worktree."""
    owners = managed_worktrees(control)
    targets = []
    for raw in shell_write_targets(command):
        value = str(raw or "").strip()
        if not value or any(marker in value for marker in ("$", "`")):
            continue
        try:
            path = Path(value).expanduser()
            if not path.is_absolute():
                path = cwd / path
            path = path.resolve()
        except (OSError, RuntimeError, ValueError):
            continue
        for owner in owners:
            try:
                relative = path.relative_to(owner.resolve()).as_posix()
            except ValueError:
                continue
            if owner == control and (
                relative == ".aiwf" or relative.startswith(".aiwf/")
            ):
                break
            targets.append(relative)
            break
    return targets


def _task_has_executor_evidence(cwd: Path, task_id: str) -> bool:
    if not task_id:
        return False
    implementation = load_task_record(cwd, task_id).get("implementation", {}) or {}
    return (
        str(implementation.get("task_id") or "") == str(task_id)
        and bool(implementation.get("implementation_ref"))
    )


def _closed_plan_for_path(cwd: Path, normalized: str) -> str:
    path = Path(normalized)
    if len(path.parts) != 3 or path.parts[:2] != (".aiwf", "plans"):
        return ""
    if path.suffix.lower() != ".md":
        return ""
    plan_id = path.stem
    plans = _read_json(cwd / ".aiwf" / "state" / "plans.json", {"plans": []})
    for plan in plans.get("plans", []) or []:
        if not isinstance(plan, dict):
            continue
        current_id = str(plan.get("plan_id") or plan.get("id") or "")
        if current_id == plan_id and str(plan.get("status") or "") == "closed":
            return plan_id
    return ""


def check_file_write(event: NormalizedEvent) -> ScopeResult:
    """Check if a file write/edit is within active scope.

    V2 policy:
    - Project writes require an active task.
    - Governance/planning writes do not require an active task.
    - Executor subagent requirement is decided by Task.requirements.executor_required.
    """
    file_path = event.tool_input.get("file_path", "")
    if not file_path:
        return ScopeResult(file_path="", allowed=True, reason="no file_path in event")

    cwd = Path(event.cwd) if event.cwd else Path.cwd()
    control = resolve_control_root(cwd)
    active_task = task_for_worktree(str(cwd))
    active_task_id = str((active_task or {}).get("id") or "")
    state = _read_json(control / ".aiwf" / "state" / "state.json", {})
    write_policy = _read_write_policy(control)
    from ...core.scope_policy import _is_governance_file, _normalize_path
    normalized = _normalize_path(file_path, str(cwd))
    if Path(normalized).is_absolute() and control != cwd:
        control_relative = _normalize_path(file_path, str(control))
        if control_relative == ".aiwf" or control_relative.startswith(".aiwf/"):
            normalized = control_relative

    # ── Mechanical truth: JSON run state must use CLI, never direct Write/Edit ──
    _PROTECTED_JSON_PREFIXES = (".aiwf/state/", ".aiwf/records/")
    if normalized.endswith(".json") and any(normalized.startswith(p) for p in _PROTECTED_JSON_PREFIXES):
        return ScopeResult(
            file_path=normalized,
            allowed=False,
            active_context_id=state.get("active_context_id") or "(none)",
            reason=(
                f"mechanical truth '{normalized}' must be changed through aiwf CLI commands; "
                "direct Write/Edit of .aiwf/state/*.json and .aiwf/records/*.json is denied."
            ),
        )

    if normalized == TEMPORARY_AI_WRITES_MARKER:
        return ScopeResult(
            file_path=normalized,
            allowed=False,
            active_context_id=state.get("active_context_id") or "(none)",
            reason="temporary AI project writes can be changed only by a human in `aiwf ui`.",
        )

    if active_task_id and not _is_governance_file(normalized):
        assigned = Path(str(active_task.get("worktree_path") or cwd))
        violation = foreign_worktree_target(
            file_path,
            cwd=cwd,
            control_root=control,
            assigned_worktree=assigned,
        )
        if violation:
            target, owner = violation
            return ScopeResult(
                file_path=str(target),
                allowed=False,
                active_context_id=active_task_id,
                reason=(
                    f"Task {active_task_id} is assigned to worktree '{assigned.resolve()}'. "
                    f"Write target '{target}' belongs to a different AIWF worktree '{owner}'. "
                    "Write only inside the assigned worktree; do not copy or sync Task changes "
                    "to the primary or another Plan worktree."
                ),
            )

    role = str(event.agent_type or "").lower()
    if (
        "architect" in role
        and _role_project_write_mode(role, write_policy) in ("reports_only", "allow")
        and _is_architect_report_path(normalized)
    ):
        return ScopeResult(
            file_path=normalized,
            allowed=True,
            active_context_id=state.get("active_context_id") or "(none)",
            reason="aiwf-architect may write its assigned Markdown review report",
        )

    # ── Fix-loop repair window: allow explicit repair targets ──
    fix_loop = (
        load_task_record(control, active_task_id).get("fix_loop", {})
        if active_task_id else {}
    )
    if fix_loop.get("status") == "open":
        import re
        required_fixes = fix_loop.get("required_fixes", []) or []
        for rf in required_fixes:
            if not isinstance(rf, str):
                continue
            paths = re.findall(r'([\w./-]+\.[\w]+)', rf)
            for p in paths:
                p_clean = p.lstrip("./")
                candidates = {p_clean, "." + p_clean}
                if normalized in candidates or any(normalized.endswith("/" + c) for c in candidates):
                    if (
                        not _is_governance_file(normalized)
                        and active_task_id
                    ):
                        reqs = _get_active_task_requirements(control, active_task_id) or {}
                        tester_test_write = (
                            "tester" in role
                            and reqs.get("tester_required")
                            and _tester_write_allowed(normalized, reqs)
                        )
                        if _role_project_write_mode(role, write_policy) != "allow":
                            role_name = _role_read_only_name(role)
                            return ScopeResult(
                                file_path=normalized,
                                allowed=False,
                                active_context_id=state.get("active_context_id") or "(none)",
                                reason=(
                                    f"{role_name} is read-only for project files. It may inspect and run checks, "
                                    f"but must not write '{normalized}'."
                                ),
                            )
                        tester_mode = write_policy.get("tester_project_writes")
                        tester_can_write = (
                            tester_mode == "allow_all"
                            or (tester_mode == "test_assets_only" and tester_test_write)
                        )
                        role_can_write = _configured_read_only_role_can_write(role, write_policy)
                        if "tester" in role and not tester_can_write:
                            return ScopeResult(
                                file_path=normalized,
                                allowed=False,
                                active_context_id=state.get("active_context_id") or "(none)",
                                reason=(
                                    f"fix-loop tester repair may write test/verification assets only. "
                                    f"Dispatch aiwf-executor for implementation writes to '{normalized}'."
                                ),
                            )
                        if (
                            write_policy.get("first_implementation_requires_executor")
                            and reqs.get("executor_required")
                            and "executor" not in role
                            and not tester_can_write
                            and not role_can_write
                            and not _task_has_executor_evidence(cwd, active_task_id)
                        ):
                            if (
                                _is_planner_inline_role(role)
                                and _task_has_executor_evidence(cwd, active_task_id)
                            ):
                                return ScopeResult(
                                    file_path=normalized,
                                    allowed=True,
                                    active_context_id=state.get("active_context_id") or "(none)",
                                    reason=(
                                        f"fix-loop inline repair allowed for '{normalized}': "
                                        f"task {active_task_id} already has an Executor implementation. "
                                        "Planner may choose inline repair for tiny, well-understood follow-up fixes; "
                                        "dispatch aiwf-executor for unclear or high-risk repairs."
                                    ),
                                )
                            return ScopeResult(
                                file_path=normalized,
                                allowed=False,
                                active_context_id=state.get("active_context_id") or "(none)",
                                reason=(
                                    f"fix-loop repair for project file '{normalized}' requires aiwf-executor because "
                                    f"task {active_task_id} has no Executor implementation yet. "
                                    "A Task's first implementation must come from Executor; later tiny repairs may be inline."
                                ),
                            )
                    return ScopeResult(
                        file_path=file_path,
                        allowed=True,
                        reason=f"fix-loop repair window: '{normalized}' is a required_fix target"
                    )

    # ── Governance files ──
    if _is_governance_file(normalized):
        if normalized == ".aiwf/config/command-policy.json":
            return ScopeResult(
                file_path=normalized,
                allowed=False,
                active_context_id=state.get("active_context_id") or "(none)",
                reason=(
                    "command-policy.json protects human-only commands and cannot be edited "
                    "by AI tools. A human may edit it outside the Claude Code session."
                ),
            )
        if normalized.startswith(".aiwf/memory/") and not _is_planner_inline_role(role):
            return ScopeResult(
                file_path=normalized,
                allowed=False,
                active_context_id=state.get("active_context_id") or "(none)",
                reason=(
                    f"AIWF memory is owned by Planner; {role} may read but not edit "
                    f"'{normalized}'."
                ),
            )
        if normalized.startswith(".aiwf/config/") and role and not _is_planner_inline_role(role):
            return ScopeResult(
                file_path=normalized,
                allowed=False,
                active_context_id=state.get("active_context_id") or "(none)",
                reason=(
                    f"AIWF configuration is owned by Planner; {role} may read but not edit "
                    f"'{normalized}'."
                ),
            )
        if _is_planner_owned_governance_path(normalized) and not _is_planner_inline_role(role):
            return ScopeResult(
                file_path=normalized,
                allowed=False,
                active_context_id=state.get("active_context_id") or "(none)",
                reason=(
                    f"AIWF governance documents are owned by Planner; {role or 'this role'} "
                    f"may read but not edit '{normalized}'. Return the proposed change to Planner."
                ),
            )
        closed_plan_id = _closed_plan_for_path(control, normalized)
        if closed_plan_id:
            return ScopeResult(
                file_path=normalized,
                allowed=False,
                active_context_id=state.get("active_context_id") or "(none)",
                reason=(
                    f"Plan '{closed_plan_id}' is closed and records completed work. "
                    "Create a new Plan for new work; only the human may correct this document."
                ),
            )
        # Only the active Task.md is frozen during execution
        if active_task_id and write_policy.get("freeze_active_task_md"):
            task_md_path = f".aiwf/tasks/{active_task_id}.md"
            if normalized == task_md_path:
                return ScopeResult(
                    file_path=normalized,
                    allowed=False,
                    active_context_id=state.get("active_context_id") or "(none)",
                    reason=(
                        f"active Task.md '{normalized}' is frozen during execution. "
                        "If this was a real contract correction, stop the Task workflow, explain the "
                        "exact conflict, and ask the human to run 'aiwf task interrupt'. After interruption, "
                        "Planner may revise and sync the contract, critique it again, and reactivate. "
                        "Do not leave the choice to Executor or continue with a known-bad contract."
                    ),
                )

        return ScopeResult(file_path=normalized, allowed=True,
                          reason="governance file — always allowed")

    # ── Project files: require active task ──
    if not active_task_id and write_policy.get("project_writes_require_active_task"):
        if _temporary_project_writes_allowed(control, role, write_policy):
            return ScopeResult(
                file_path=normalized,
                allowed=True,
                active_context_id="(temporary)",
                reason="human enabled temporary AI project writes in `aiwf ui`",
            )
        active_elsewhere = active_tasks(str(control))
        if active_elsewhere:
            assignments = ", ".join(
                f"{task.get('id')} -> {task.get('worktree_path')}"
                for task in active_elsewhere
            )
            return ScopeResult(
                file_path=normalized,
                allowed=False,
                active_context_id=state.get("active_context_id") or "(none)",
                reason=(
                    "active Task exists, but this write is not bound to its Plan worktree. "
                    f"Use the assigned worktree shown by 'aiwf status --prompt': {assignments}. "
                    "Do not change executor_required or enable temporary writes to bypass routing."
                ),
            )
        return ScopeResult(
            file_path=normalized,
            allowed=False,
            active_context_id=state.get("active_context_id") or "(none)",
            reason=(
                f"no active task — run 'aiwf task activate <TASK-ID>' before writing to '{normalized}'. "
                "Project writes require an active task."
            ),
        )

    # ── Role write boundaries ──
    reqs = _get_active_task_requirements(control, active_task_id) or {}
    if _role_project_write_mode(role, write_policy) != "allow":
        role_name = _role_read_only_name(role)
        return ScopeResult(
            file_path=normalized,
            allowed=False,
            active_context_id=state.get("active_context_id") or "(none)",
            reason=(
                f"{role_name} is read-only for project files. It may inspect and run checks, "
                f"but must not write '{normalized}'."
            ),
        )

    tester_mode = write_policy.get("tester_project_writes")
    tester_test_write = (
        "tester" in role
        and tester_mode == "test_assets_only"
        and _tester_write_allowed(normalized, reqs)
    )
    tester_can_write = (
        "tester" in role
        and (
            tester_mode == "allow_all"
            or tester_test_write
        )
    )
    role_can_write = _configured_read_only_role_can_write(role, write_policy)
    if "tester" in role and not tester_can_write:
        return ScopeResult(
            file_path=normalized,
            allowed=False,
            active_context_id=state.get("active_context_id") or "(none)",
            reason=(
                f"aiwf-tester may write test/verification assets only. "
                f"Dispatch aiwf-executor for implementation writes to '{normalized}'."
            ),
        )
    if tester_test_write and not reqs.get("tester_required"):
        return ScopeResult(
            file_path=normalized,
            allowed=False,
            active_context_id=state.get("active_context_id") or "(none)",
            reason=(
                f"Task.requirements.tester_required is not true, so aiwf-tester may not write "
                f"test asset '{normalized}'."
            ),
        )

    if (
        write_policy.get("first_implementation_requires_executor")
        and reqs.get("executor_required")
        and "executor" not in role
        and not _task_has_executor_evidence(cwd, active_task_id)
    ):
        if tester_can_write or role_can_write:
            pass
        elif _is_planner_inline_role(role) and _task_has_executor_evidence(cwd, active_task_id):
            pass
        else:
            return ScopeResult(
                file_path=normalized,
                allowed=False,
                active_context_id=state.get("active_context_id") or "(none)",
                reason=(
                    f"Task.requirements.executor_required=true: the first implementation write for "
                    f"task {active_task_id} must be performed by an aiwf-executor subagent. "
                    f"After the Executor implementation exists, Planner may choose inline repair for tiny fixes. "
                    f"Dispatch aiwf-executor before writing '{normalized}'."
                ),
            )

    # ── Forbidden write: mechanically enforce Task.md forbidden_write patterns ──
    forbidden = _get_task_forbidden_write(cwd, active_task_id)
    if forbidden:
        from ...core.scope_policy import _matches
        for pattern in forbidden:
            if _matches(normalized, pattern):
                return ScopeResult(
                    file_path=normalized,
                    allowed=False,
                    active_context_id=active_task_id,
                    reason=(
                        f"'{normalized}' matches Forbidden Write pattern '{pattern}' "
                        f"from active Task.md ({active_task_id}). "
                        f"Task contract prohibits writing to this path."
                    ),
                )

    # ── Project file: allowed (guarded by active_task_id + executor_required + forbidden_write above) ──
    return ScopeResult(file_path=normalized, allowed=True,
                      reason=f"project write allowed (task={active_task_id}, executor_required={reqs.get('executor_required', False)})")


def _path_matches(file_path: str, pattern: str) -> bool:
    fp = file_path.lstrip("./")
    pat = pattern.lstrip("./")
    if pat.endswith("/") or pat.endswith("/**"):
        prefix = pat.rstrip("*").rstrip("/")
        return fp == prefix or fp.startswith(prefix + "/")
    if pat.startswith("**/"):
        suffix = pat[3:]
        return fp == suffix or fp.endswith("/" + suffix)
    if "*" in pat:
        import fnmatch
        return fnmatch.fnmatch(fp, pat)
    return fp == pat


def check_bash(event: NormalizedEvent) -> Dict:
    command = event.tool_input.get("command", "")
    cwd = Path(event.cwd) if event.cwd else Path.cwd()
    control = resolve_control_root(cwd)
    active_task = task_for_worktree(str(cwd))
    active_task_id = str((active_task or {}).get("id") or "")
    write_policy = _read_write_policy(control)
    role = str(event.agent_type or "").lower()

    # ── Command-policy: mechanically block AI-forbidden commands ──
    policy_result = _check_command_policy(command, control)
    if policy_result:
        return policy_result

    base_result = check_bash_command(command)
    if TEMPORARY_AI_WRITES_MARKER in command:
        return {
            "allowed": False,
            "decision": "deny",
            "command": command[:200],
            "matched_pattern": TEMPORARY_AI_WRITES_MARKER,
            "reason": "temporary AI project writes can be changed only by a human in `aiwf ui`.",
        }

    if active_task_id:
        assigned = Path(str(active_task.get("worktree_path") or cwd))
        violation = foreign_bash_write(
            command,
            cwd=cwd,
            control_root=control,
            assigned_worktree=assigned,
        )
        if violation:
            target, owner = violation
            return {
                "allowed": False,
                "decision": "deny",
                "command": command[:200],
                "matched_pattern": str(target),
                "reason": (
                    f"Task {active_task_id} is assigned to worktree '{assigned.resolve()}'. "
                    f"Shell write target '{target}' belongs to a different AIWF worktree "
                    f"'{owner}'. Write only inside the assigned worktree; do not copy or sync "
                    "Task changes to the primary or another Plan worktree."
                ),
            }

    protected_config_result = _check_command_policy_bash_write(command, control)
    if protected_config_result:
        return protected_config_result

    role_config_result = _check_role_config_bash_write(event, command)
    if role_config_result:
        return role_config_result

    role_memory_result = _check_role_memory_bash_write(event, command, control)
    if role_memory_result:
        return role_memory_result

    role_governance_result = _check_role_governance_bash_write(event, command, control)
    if role_governance_result:
        return role_governance_result

    closed_plan_result = _check_closed_plan_bash(command, control)
    if closed_plan_result:
        return closed_plan_result

    # ── Active Task.md: block bash writes to frozen contract ──
    active_lock_result = _check_active_task_md_bash(command, control, active_task_id)
    if active_lock_result:
        return active_lock_result

    if base_result.get("decision") != "allow":
        return base_result

    project_targets = _project_shell_write_targets(command, cwd, control)
    if (
        project_targets
        and not active_task_id
        and write_policy.get("project_writes_require_active_task")
    ):
        temporary_allowed = _temporary_project_writes_allowed(
            control, role, write_policy,
        )
        if not temporary_allowed:
            active_elsewhere = active_tasks(str(control))
            if active_elsewhere:
                assignments = ", ".join(
                    f"{task.get('id')} -> {task.get('worktree_path')}"
                    for task in active_elsewhere
                )
                return {
                    "allowed": False,
                    "decision": "deny",
                    "command": command[:200],
                    "matched_pattern": project_targets[0],
                    "reason": (
                        "active Task exists, but this shell write is not bound to its Plan worktree. "
                        f"Use the assigned worktree shown by 'aiwf status --prompt': {assignments}."
                    ),
                }
            return {
                "allowed": False,
                "decision": "deny",
                "command": command[:200],
                "matched_pattern": project_targets[0],
                "reason": (
                    f"no active task — project shell writes require an active Task. "
                    f"A human may temporarily allow AI project writes in `aiwf ui`; "
                    f"first target: '{project_targets[0]}'."
                ),
            }

    if active_task_id:
        import re
        if re.search(r"(^|[;&|]\s*)git\s+commit\b", command, re.IGNORECASE):
            return {
                "allowed": False,
                "decision": "deny",
                "command": command[:200],
                "matched_pattern": "git commit",
                "reason": (
                    "The active Task is committed by 'aiwf task close' after testing and review. "
                    "Do not create an unreviewed commit during the Task."
                ),
            }

    return base_result


def _check_closed_plan_bash(command: str, cwd: Path) -> Optional[Dict]:
    """Block shell writes to closed Plan documents."""
    plans = _read_json(cwd / ".aiwf" / "state" / "plans.json", {"plans": []})
    closed_ids = [
        str(plan.get("plan_id") or plan.get("id") or "")
        for plan in plans.get("plans", []) or []
        if isinstance(plan, dict) and str(plan.get("status") or "") == "closed"
    ]
    if not closed_ids:
        return None

    import re
    write_pattern = re.compile(
        r">>|(?<![<])>|\b(?:rm|unlink|mv|cp|tee|truncate)\b|"
        r"\b(?:sed|perl)\b[^\n]*(?:\s-i|\s--in-place)|"
        r"\bopen\s*\([^\n]*['\"](?:w|a)|\bdd\b[^\n]*\bof=",
        re.IGNORECASE,
    )
    if not write_pattern.search(command):
        return None
    for plan_id in closed_ids:
        relative = f".aiwf/plans/{plan_id}.md"
        if relative not in command and str(cwd / relative) not in command:
            continue
        return {
            "allowed": False,
            "decision": "deny",
            "command": command[:200],
            "matched_pattern": relative,
            "reason": (
                f"Plan '{plan_id}' is closed and records completed work. "
                "Create a new Plan for new work; only the human may correct this document."
            ),
        }
    return None


def _check_active_task_md_bash(command: str, cwd: Path, active_task_id: str) -> Optional[Dict]:
    """Block bash commands that write to or delete the active Task.md during execution."""
    if not _read_write_policy(cwd).get("freeze_active_task_md"):
        return None
    if not active_task_id:
        return None

    import re
    md_path = f".aiwf/tasks/{active_task_id}.md"
    esc = re.escape(md_path)

    # Destructive patterns targeting the active Task.md
    deny_patterns = [
        # Redirect/append: echo x >> path, echo x > path
        rf">>?\s*{esc}",
        # In-place edit: sed -i ... path, perl -i ... path
        rf"(sed|perl)\s+.*-i[^ ]*\s+.*{esc}",
        # Remove/unlink: rm path, rm -f path, unlink path
        rf"\brm\s+[^;|&]*{esc}",
        rf"\bunlink\s+{esc}",
        # Move/rename: mv path dest, mv -f path dest
        rf"\bmv\s+.*{esc}\s",
        # Copy over: cp ... path (copies TO the locked file)
        rf"\bcp\s+.*\s+{esc}",
        # Tee overwrite: | tee path, tee path
        rf"\btee\s+.*{esc}",
        # Python write: open("path","w"), open('path','w')
        rf"open\s*\(\s*['\"]{esc}['\"]\s*,\s*['\"]w",
        # dd write: dd of=path
        rf"\bdd\s+.*of={esc}",
        # Truncate: truncate path, > path
        rf"\btruncate\s+.*{esc}",
    ]

    for pattern in deny_patterns:
        if re.search(pattern, command, re.IGNORECASE):
            return {
                "allowed": False,
                "decision": "deny",
                "command": command[:200],
                "matched_pattern": pattern,
                "reason": (
                    f"Active Task.md '{md_path}' is frozen during execution. "
                    "If the contract really needs correction, stop normal work, explain the conflict, "
                    "and ask the human to run 'aiwf task interrupt'. Then Planner may revise, sync, "
                    "critique, and reactivate. Do not continue with a known-bad contract."
                ),
            }
    return None


def _check_command_policy(command: str, cwd: Path) -> Optional[Dict]:
    """Check .aiwf/config/command-policy.json for AI-blocked commands.

    Returns a deny result dict if the command matches a blocked pattern,
    or None if the command is allowed.
    """
    command_lower = command.lower()
    for pattern, reason in HUMAN_ONLY_COMMANDS.items():
        if pattern in command_lower:
            return {
                "allowed": False,
                "decision": "deny",
                "command": command[:200],
                "matched_pattern": pattern,
                "reason": f"{reason}. Human action is required.",
            }

    policy_path = cwd / ".aiwf" / "config" / "command-policy.json"
    if not policy_path.exists():
        return None
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "allowed": False,
            "decision": "deny",
            "command": command[:200],
            "matched_pattern": "invalid command-policy.json",
            "reason": f"command-policy.json is invalid; refusing Bash until a human repairs it: {exc}",
        }
    for entry in policy.get("deny", []) or []:
        if not isinstance(entry, dict):
            continue
        pattern = entry.get("command", "")
        if not pattern:
            continue
        if pattern.lower() in command.lower():
            return {
                "allowed": False,
                "decision": "deny",
                "command": command[:200],
                "matched_pattern": pattern,
                "reason": (
                    f"Command '{pattern}' is blocked by command-policy: "
                    f"{entry.get('reason', 'AI is not allowed to run this command.')}"
                ),
            }
    return None


def _check_command_policy_bash_write(command: str, cwd: Path) -> Optional[Dict]:
    """Prevent shell commands from rewriting the policy that guards the shell."""
    target = ".aiwf/config/command-policy.json"
    absolute = str(cwd / target)
    if target not in command and absolute not in command:
        return None

    if not _looks_like_shell_write(command):
        return None
    return {
        "allowed": False,
        "decision": "deny",
        "command": command[:200],
        "matched_pattern": target,
        "reason": (
            "command-policy.json protects human-only commands and cannot be edited "
            "by AI shell commands. A human may edit it outside the Claude Code session."
        ),
    }


def _check_role_config_bash_write(event: NormalizedEvent, command: str) -> Optional[Dict]:
    role = str(event.agent_type or "").lower()
    if not role or _is_planner_inline_role(role):
        return None
    if ".aiwf/config/" not in command or not _looks_like_shell_write(command):
        return None
    return {
        "allowed": False,
        "decision": "deny",
        "command": command[:200],
        "matched_pattern": ".aiwf/config/",
        "reason": f"AIWF configuration is owned by Planner; {role} may read but not edit it.",
    }


def _check_role_memory_bash_write(
    event: NormalizedEvent,
    command: str,
    control: Path,
) -> Optional[Dict]:
    role = str(event.agent_type or "").lower()
    if _is_planner_inline_role(role):
        return None

    targets = shell_write_targets(command)
    import re
    targets.extend(re.findall(
        r"\bopen\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"][^'\"]*[wax+]",
        command,
    ))
    memory_root = (control / ".aiwf" / "memory").resolve()
    writes_memory = False
    for raw_target in targets:
        relative = str(raw_target).lstrip("./")
        if relative == "aiwf/memory" or relative.startswith("aiwf/memory/"):
            writes_memory = True
            break
        try:
            target = Path(raw_target).expanduser()
            if not target.is_absolute():
                target = Path(event.cwd or Path.cwd()) / target
            target = target.resolve()
            if target == memory_root or memory_root in target.parents:
                writes_memory = True
                break
        except (OSError, RuntimeError, ValueError):
            continue
    if not writes_memory:
        return None
    return {
        "allowed": False,
        "decision": "deny",
        "command": command[:200],
        "matched_pattern": ".aiwf/memory/",
        "reason": f"AIWF memory is owned by Planner; {role} may read but not edit it.",
    }


def _check_role_governance_bash_write(
    event: NormalizedEvent,
    command: str,
    control: Path,
) -> Optional[Dict]:
    role = str(event.agent_type or "").lower()
    if _is_planner_inline_role(role) or not _looks_like_shell_write(command):
        return None

    targets = shell_write_targets(command)
    import re
    targets.extend(re.findall(
        r"\bopen\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"][^'\"]*[wax+]",
        command,
    ))
    for raw_target in targets:
        try:
            target = Path(raw_target).expanduser()
            if not target.is_absolute():
                target = Path(event.cwd or Path.cwd()) / target
            normalized = target.resolve().relative_to(control.resolve()).as_posix()
        except (OSError, RuntimeError, ValueError):
            continue
        if _is_planner_owned_governance_path(normalized):
            return {
                "allowed": False,
                "decision": "deny",
                "command": command[:200],
                "matched_pattern": normalized,
                "reason": (
                    f"AIWF governance documents are owned by Planner; {role or 'this role'} "
                    f"may read but not edit '{normalized}'. Return the proposed change to Planner."
                ),
            }
    return None


def _looks_like_shell_write(command: str) -> bool:
    import re

    return bool(re.search(
        r">>|(?<![<])>|\b(?:rm|unlink|mv|cp|tee|truncate)\b|"
        r"\b(?:sed|perl)\b[^\n]*(?:\s-i|\s--in-place)|"
        r"\bopen\s*\([^\n]*['\"](?:w|a)|\bdd\b[^\n]*\bof=",
        command,
        re.IGNORECASE,
    ))
