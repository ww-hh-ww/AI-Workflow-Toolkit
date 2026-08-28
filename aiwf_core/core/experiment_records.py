"""Disposable full-project experiments and their concise evidence records."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .state._common import _exclusive_operation_lock, _atomic_write
from .worktree_context import resolve_control_root, resolve_worktree_root, same_path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_id(experiment_id: str) -> str:
    value = str(experiment_id or "").strip()
    if not re.fullmatch(r"EXP-[A-Za-z0-9._-]+", value):
        raise ValueError("experiment ID must start with EXP- and contain safe ID characters")
    return value


def experiment_record_path(base_dir: str | Path, experiment_id: str) -> Path:
    control = resolve_control_root(base_dir)
    return control / ".aiwf" / "records" / "experiments" / f"{_safe_id(experiment_id)}.json"


def load_experiment(base_dir: str | Path, experiment_id: str) -> Dict[str, Any]:
    path = experiment_record_path(base_dir, experiment_id)
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read experiment record {experiment_id}: {exc}") from exc
    return value if isinstance(value, dict) else {}


def save_experiment(base_dir: str | Path, record: Dict[str, Any]) -> None:
    experiment_id = _safe_id(str(record.get("experiment_id") or ""))
    record["updated_at"] = _now()
    _atomic_write(experiment_record_path(base_dir, experiment_id), record)


def list_experiments(base_dir: str | Path, task_id: str = "") -> List[Dict[str, Any]]:
    control = resolve_control_root(base_dir)
    root = control / ".aiwf" / "records" / "experiments"
    found: List[Dict[str, Any]] = []
    if not root.exists():
        return found
    for path in sorted(root.glob("EXP-*.json")):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(item, dict):
            continue
        scope = item.get("scope") or {}
        if task_id and (
            scope.get("kind") != "task"
            or str(scope.get("id") or "") != task_id
        ):
            continue
        found.append(item)
    return found


def experiment_for_worktree(base_dir: str | Path) -> Dict[str, Any]:
    current = resolve_worktree_root(base_dir)
    for item in list_experiments(base_dir):
        worktree = str(item.get("worktree_path") or "")
        if item.get("status") == "running" and worktree and same_path(current, worktree):
            return item
    return {}


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=str(root), capture_output=True, text=True,
        encoding="utf-8", errors="surrogateescape",
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or result.stdout.strip() or "git command failed")
    return result.stdout.strip()


def open_experiment(
    base_dir: str,
    experiment_id: str,
    question: str,
    hypothesis: str = "",
    task_id: str = "",
    plan_id: str = "",
    subject_ref: str = "",
    timing: str = "",
) -> Dict[str, Any]:
    """Create an empirical question against one immutable stable ref."""
    experiment_id = _safe_id(experiment_id)
    question = " ".join(str(question or "").split())
    if not question:
        raise ValueError("experiment question is required")
    if bool(task_id) == bool(plan_id):
        raise ValueError("experiment requires exactly one of task_id or plan_id")
    control = resolve_control_root(base_dir)
    path = experiment_record_path(control, experiment_id)
    if path.exists():
        raise ValueError(f"experiment already exists: {experiment_id}")

    if task_id:
        from .task_ledger import load_ledger
        from .task_records import load_task_record, update_task_record

        task = next((item for item in load_ledger(str(control)).get("tasks", [])
                     if item.get("id") == task_id), None)
        if not task:
            raise ValueError(f"Task not found: {task_id}")
        implementation = load_task_record(control, task_id).get("implementation", {}) or {}
        current_ref = str(implementation.get("implementation_ref") or task.get("git_origin_ref") or "")
        subject_ref = subject_ref or current_ref
        timing = timing or ("post_implementation" if implementation.get("implementation_ref") else "pre_implementation")
        scope = {"kind": "task", "id": task_id}
    else:
        from .state.plan_ops import get_plan

        plan = get_plan(str(control), plan_id)
        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")
        subject_ref = subject_ref or str(plan.get("git_head_ref") or plan.get("git_base_ref") or "")
        timing = timing or "pre_implementation"
        scope = {"kind": "plan", "id": plan_id}
    if timing not in {"pre_implementation", "post_implementation"}:
        raise ValueError("timing must be pre_implementation or post_implementation")
    if not subject_ref:
        raise ValueError("experiment subject ref is missing")
    subject_ref = _git(control, "rev-parse", f"{subject_ref}^{{commit}}")

    record = {
        "schema_version": 1,
        "experiment_id": experiment_id,
        "scope": scope,
        "timing": timing,
        "question": question,
        "hypothesis": " ".join(str(hypothesis or "").split()),
        "subject_ref": subject_ref,
        "status": "open",
        "worktree_path": "",
        "experiment_ref": "",
        "snapshot_ref": "",
        "commands": [],
        "observations": [],
        "conclusion": "",
        "summary": "",
        "promotion_candidates": [],
        "created_at": _now(),
        "updated_at": _now(),
    }
    save_experiment(control, record)
    if task_id:
        update_task_record(
            control, task_id,
            lambda task_record: task_record.setdefault("experiment_ids", []).append(experiment_id),
        )
    return record


def start_experiment(base_dir: str, experiment_id: str) -> Dict[str, Any]:
    """Create a detached full-project worktree at the experiment subject ref."""
    control = resolve_control_root(base_dir)
    with _exclusive_operation_lock(str(control), f"experiment-{_safe_id(experiment_id)}"):
        record = load_experiment(control, experiment_id)
        if not record:
            raise ValueError(f"experiment not found: {experiment_id}")
        if record.get("status") not in ("open", "running"):
            raise ValueError(f"experiment is {record.get('status')}; it cannot be started")
        target = control / ".aiwf" / "runtime" / "experiments" / experiment_id / "worktree"
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            _git(control, "worktree", "add", "--detach", str(target), str(record["subject_ref"]))
        record["worktree_path"] = str(target.resolve())
        record["status"] = "running"
        record["started_at"] = _now()
        save_experiment(control, record)
        return record


def record_experiment(
    base_dir: str,
    experiment_id: str,
    conclusion: str,
    summary: str,
    commands: Optional[List[str]] = None,
    observations: Optional[List[str]] = None,
    promotion_candidates: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Freeze the disposable project tree and record its empirical conclusion."""
    from .git_snapshots import create_experiment_snapshot
    from .state_schema import VALID_EXPERIMENT_CONCLUSIONS

    if conclusion not in VALID_EXPERIMENT_CONCLUSIONS:
        raise ValueError(f"invalid experiment conclusion: {conclusion}")
    summary = " ".join(str(summary or "").split())
    if not summary:
        raise ValueError("experiment summary is required")
    observations = [str(item).strip() for item in (observations or []) if str(item).strip()]
    if not observations:
        raise ValueError("experiment evidence requires at least one concrete observation")
    control = resolve_control_root(base_dir)
    with _exclusive_operation_lock(str(control), f"experiment-{_safe_id(experiment_id)}"):
        record = load_experiment(control, experiment_id)
        if not record:
            raise ValueError(f"experiment not found: {experiment_id}")
        worktree = str(record.get("worktree_path") or "")
        if record.get("status") != "running" or not worktree:
            raise ValueError("experiment must be running before evidence can be recorded")
        if not same_path(resolve_worktree_root(base_dir), worktree):
            raise ValueError(f"record experiment from its disposable worktree: {worktree}")
        snapshot = create_experiment_snapshot(
            worktree, experiment_id, str(record.get("subject_ref") or ""), summary=summary,
        )
        record.update({
            "status": "recorded",
            "conclusion": conclusion,
            "summary": summary[:1000],
            "commands": list(dict.fromkeys(commands or [])),
            "observations": observations,
            "promotion_candidates": list(promotion_candidates or []),
            "experiment_ref": snapshot["ref"],
            "snapshot_ref": snapshot["named_ref"],
            "changed_files": snapshot["files"],
            "attempt": snapshot["attempt"],
            "recorded_at": _now(),
        })
        save_experiment(control, record)

    return record


def finish_experiment(base_dir: str, experiment_id: str) -> Dict[str, Any]:
    """Dispose the experiment worktree after its snapshot has been recorded."""
    control = resolve_control_root(base_dir)
    with _exclusive_operation_lock(str(control), f"experiment-{_safe_id(experiment_id)}"):
        record = load_experiment(control, experiment_id)
        if not record:
            raise ValueError(f"experiment not found: {experiment_id}")
        if not record.get("experiment_ref"):
            raise ValueError("record experiment evidence before disposing its worktree")
        worktree = Path(str(record.get("worktree_path") or ""))
        if worktree.exists():
            _git(control, "worktree", "remove", "--force", str(worktree))
        runtime_root = control / ".aiwf" / "runtime" / "experiments" / experiment_id
        if runtime_root.exists():
            shutil.rmtree(runtime_root, ignore_errors=True)
        record["status"] = "closed"
        record["finished_at"] = _now()
        save_experiment(control, record)
        return record


def stale_post_implementation_experiments(base_dir: str, task_id: str, current_ref: str) -> List[str]:
    """Mark empirical evidence about an older implementation as stale."""
    stale: List[str] = []
    for record in list_experiments(base_dir, task_id=task_id):
        if (
            record.get("timing") == "post_implementation"
            and record.get("subject_ref") != current_ref
            and record.get("status") == "closed"
        ):
            record["status"] = "stale"
            record["stale_reason"] = "implementation ref changed"
            save_experiment(base_dir, record)
            stale.append(str(record.get("experiment_id") or ""))
    return stale


def pending_experiments(base_dir: str, task_id: str, subject_ref: str) -> List[Dict[str, Any]]:
    return [
        item for item in list_experiments(base_dir, task_id=task_id)
        if item.get("status") in ("open", "running", "recorded")
        and str(item.get("subject_ref") or "") == subject_ref
    ]
