"""Shared utilities and constants for state operation modules."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypeVar

WORKFLOW_LEVELS = ["L0_direct", "L1_review_light", "L2_standard_team", "L3_full_power"]
BLOCKING_REVIEW_RESULTS = {
    "needs_fix", "needs_more_testing", "evidence_insufficient",
    "scope_violation", "rejected",
}

T = TypeVar("T")


def _read(path: Path) -> Dict:
    try: return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except: return {}


def _write(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _atomic_write(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _locked_json_update(path: Path, default: Dict, mutator: Callable[[Dict], T]) -> T:
    """Update a JSON object under a sibling lock file.

    Evidence writes can come from several hook/subagent processes at nearly the
    same time. The lock covers read -> compute next ID -> append -> write so
    records are not overwritten by a concurrent writer.
    """
    import fcntl

    lock_path = path.with_name(f"{path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        data = _read(path)
        if not data:
            data = dict(default)
        result = mutator(data)
        _atomic_write(path, data)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        return result


def execution_contract_freeze_reasons(base_dir: str, state: Optional[Dict] = None) -> List[str]:
    """Explain why execution truth may only become stricter."""
    base = Path(base_dir)
    state = state if state is not None else _read(base / ".aiwf" / "state" / "state.json")
    testing = _read(base / ".aiwf" / "artifacts" / "quality" / "testing.json")
    review = _read(base / ".aiwf" / "artifacts" / "quality" / "review.json")
    fix_loop = _read(base / ".aiwf" / "state" / "fix-loop.json")
    reasons: List[str] = []
    if state.get("active_task_id"): reasons.append(f"active_task={state['active_task_id']}")
    if state.get("scope_violation"): reasons.append("scope_violation=true")
    if state.get("close_attempt"): reasons.append("close_attempt=true")
    if state.get("phase") in ("testing", "reviewing", "closing"):
        reasons.append(f"phase={state['phase']}")
    if testing.get("status") == "failed": reasons.append("testing=failed")
    if review.get("result") in BLOCKING_REVIEW_RESULTS:
        reasons.append(f"review={review['result']}")
    if fix_loop.get("status") == "open": reasons.append("fix_loop=open")
    return reasons


def _execution_contract_frozen(base: Path, state: Optional[Dict] = None) -> bool:
    return bool(execution_contract_freeze_reasons(str(base), state))


def _freeze_explanation(base: Path, state: Optional[Dict] = None) -> str:
    reasons = execution_contract_freeze_reasons(str(base), state)
    return (
        f"freeze reasons: {', '.join(reasons) or 'unknown'}; "
        "allowed now: add constraints or record evidence; "
        "unlock: finish/revert the failing work, satisfy testing/review, resolve the fix-loop, then close the cycle"
    )


def _require_additive_list(existing: Any, proposed: List[str], field: str, detail: str = "") -> None:
    missing = [item for item in (existing or []) if item not in proposed]
    if missing:
        raise ValueError(
            f"execution contract is frozen; {field} may add constraints but cannot remove existing items"
            + (f"; {detail}" if detail else "")
        )


def _require_stable_scalar(existing: Any, proposed: str, field: str, detail: str = "") -> None:
    if existing and proposed and existing != proposed:
        raise ValueError(
            f"execution contract is frozen; {field} cannot replace an existing value"
            + (f"; {detail}" if detail else "")
        )
