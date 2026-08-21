"""Stable proof identities for Task-local fix loops."""
from __future__ import annotations

from typing import Any, Dict, List

from ..task_ledger import load_ledger


def validate_verification_obligations(
    base_dir: str,
    task_id: str,
    obligations: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Validate proof identities and structure without judging command semantics."""
    from ..task_proof import read_task_proof_contract

    task = next(
        (
            item for item in load_ledger(base_dir).get("tasks", []) or []
            if isinstance(item, dict) and str(item.get("id") or "") == task_id
        ),
        None,
    )
    if not task:
        raise ValueError(f"Task not found: {task_id}")
    contract = read_task_proof_contract(base_dir, task)
    task_ids = {
        item.verification_id for item in (contract.verification_commands if contract else [])
    }
    normalized: List[Dict[str, Any]] = []
    seen = set()
    for raw in obligations:
        if not isinstance(raw, dict):
            raise ValueError("fix-loop verification obligations must be structured objects")
        verification_id = str(raw.get("verification_id") or "").strip()
        source = str(raw.get("source") or "").strip()
        if not verification_id:
            raise ValueError("fix-loop verification obligation is missing verification_id")
        if verification_id in seen:
            raise ValueError(f"duplicate fix-loop verification ID: {verification_id}")
        seen.add(verification_id)
        if source == "task":
            if verification_id not in task_ids:
                raise ValueError(
                    f"unknown Task verification ID: {verification_id}; use a declared V-* ID"
                )
            normalized.append({"verification_id": verification_id, "source": "task"})
            continue
        if source != "fix_loop":
            raise ValueError(
                f"verification obligation {verification_id} needs source=task or fix_loop"
            )
        if not verification_id.startswith("FIX-"):
            raise ValueError("fix-loop-local verification IDs must start with FIX-")
        if verification_id in task_ids:
            raise ValueError(f"fix-loop verification ID conflicts with Task.md: {verification_id}")
        command = str(raw.get("command") or "").strip()
        expected = str(raw.get("expected") or "").strip()
        if not command or not expected:
            raise ValueError(
                f"fix-loop-local verification {verification_id} needs command and expected"
            )
        normalized.append({
            "verification_id": verification_id,
            "source": "fix_loop",
            "command": command,
            "expected": expected,
        })
    return normalized


def uncovered_verification_obligations(
    obligations: List[Dict[str, Any]],
    testing: Dict[str, Any],
) -> List[str]:
    """Return obligation IDs without a matched, observable Tester result."""
    result_by_id = {
        str(item.get("verification_id") or "").strip(): item
        for item in testing.get("verification_results", []) or []
        if isinstance(item, dict) and str(item.get("verification_id") or "").strip()
    }
    uncovered = []
    for obligation in obligations:
        verification_id = str(obligation.get("verification_id") or "").strip()
        result = result_by_id.get(verification_id, {})
        verdict = str(result.get("verdict") or "").lower()
        if (
            result.get("matched") is True
            and verdict in ("", "matched")
            and str(result.get("observed") or "").strip()
        ):
            continue
        uncovered.append(verification_id or "<missing-id>")
    return uncovered
