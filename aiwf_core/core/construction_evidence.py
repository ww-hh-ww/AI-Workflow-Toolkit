"""Structured Executor evidence for Task V-ID obligations."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def _observed(item: Dict[str, Any], identity: str, root: Path) -> str:
    value = item.get("observed", "")
    observed_file = str(item.get("observed_file") or "").strip()
    if observed_file:
        path = Path(observed_file).expanduser()
        if not path.is_absolute():
            path = root / path
        try:
            value = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"cannot read observed_file for {identity}: {exc}") from exc
    return str(value)


def load_construction_proof_file(path: str) -> List[Dict[str, Any]]:
    """Load a non-empty JSON array of Executor V-ID results."""
    proof_path = Path(path).expanduser()
    try:
        payload = json.loads(proof_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read proof file {proof_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"proof file is not valid JSON: {proof_path}: {exc}") from exc
    if isinstance(payload, dict):
        payload = payload.get("results", [])
    if not isinstance(payload, list) or not payload:
        raise ValueError("proof file must contain a non-empty results array")

    results: List[Dict[str, Any]] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"proof file result {index} must be an object")
        verification_id = str(
            item.get("verification_id") or item.get("check") or item.get("id") or ""
        ).strip()
        if not verification_id:
            raise ValueError(f"proof file result {index} is missing verification_id/check")
        verdict = str(item.get("verdict") or "").strip().lower()
        basis = str(item.get("basis") or item.get("reason") or "").strip()
        observed = _observed(item, verification_id, proof_path.parent)
        if verdict not in {"matched", "mismatched", "blocked"}:
            raise ValueError(f"proof file result {verification_id} has invalid verdict")
        if verdict != "blocked" and not observed.strip():
            raise ValueError(f"proof file result {verification_id} has empty observed output")
        if verdict == "blocked" and not basis:
            raise ValueError(f"blocked proof result {verification_id} requires basis/reason")
        results.append({
            "verification_id": verification_id,
            "observed": observed,
            "verdict": verdict,
            "basis": basis,
            "executed_command": str(item.get("executed_command") or "").strip(),
        })
    return results
