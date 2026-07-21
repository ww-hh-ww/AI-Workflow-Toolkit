"""Machine checks for Task.md proof contracts.

AIWF does not execute the project or decide whether an architecture is good.
This module only reads the task's declared proof contract and checks whether
the recorded testing surface covers it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


PROOF_LEVELS = {"Built", "Wired", "Running"}
HEADING_ALIASES = {
    "Fixed Contract": ("Fixed Contract", "固定契约"),
    "Structural Home": ("Structural Home", "结构归属"),
    "Objective": ("Objective", "目标"),
    "Contract Responsibility": ("Contract Responsibility", "契约责任"),
    "Proof Standard": ("Proof Standard", "证明标准"),
}
VERIFICATION_LABELS = ("Verification Commands", "验证命令")
PLACEHOLDERS = {"", "fill", "(fill)", "tbd", "todo", "n/a"}


@dataclass
class VerificationCommand:
    command: str
    expected: str


@dataclass
class TaskProofContract:
    task_id: str
    path: Path
    strict: bool
    proof_levels: List[str]
    verification_commands: List[VerificationCommand]
    placeholders: List[str]


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _norm_command(value: str) -> str:
    return _norm(value).strip("` ")


def _is_placeholder(value: str) -> bool:
    cleaned = _norm(value).strip("` ").lower()
    return (
        cleaned in PLACEHOLDERS
        or cleaned.startswith("(fill")
        or "(fill" in cleaned
        or "<fill" in cleaned
    )


def _heading_aliases(heading: str) -> tuple[str, ...]:
    return HEADING_ALIASES.get(heading, (heading,))


def _has_heading(text: str, level: int, heading: str) -> bool:
    names = "|".join(re.escape(name) for name in _heading_aliases(heading))
    return bool(re.search(rf"^{'#' * level}\s+(?:{names})\s*$", text, re.MULTILINE))


def _section(text: str, heading: str) -> str:
    names = "|".join(re.escape(name) for name in _heading_aliases(heading))
    pattern = re.compile(
        rf"^###\s+(?:{names})\s*$([\s\S]*?)(?=^##\s+|^###\s+|\Z)",
        re.MULTILINE,
    )
    m = pattern.search(text)
    return m.group(1).strip() if m else ""


def _table_rows(section: str) -> List[List[str]]:
    rows: List[List[str]] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells:
            continue
        if all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells):
            continue
        rows.append(cells)
    return rows


def _extract_verification_commands(section: str) -> List[VerificationCommand]:
    rows = _table_rows(section)
    if not rows:
        return []
    header = [cell.lower() for cell in rows[0]]
    is_header = any(
        token in cell for cell in header for token in ("command", "命令")
    )
    body = rows[1:] if is_header else rows
    commands: List[VerificationCommand] = []
    for row in body:
        if len(row) < 2:
            continue
        command = _norm_command(row[0])
        expected = _norm(row[1])
        if not command or _is_placeholder(command):
            continue
        commands.append(VerificationCommand(command=command, expected=expected))
    return commands


def _task_doc_path(base: Path, task: Dict[str, Any]) -> Path:
    task_id = str(task.get("id") or task.get("task_id") or "")
    doc_path = str(task.get("doc_path") or "").strip()
    if doc_path:
        return base / doc_path
    return base / ".aiwf" / "tasks" / f"{task_id}.md"


def read_task_proof_contract(base_dir: str, task: Dict[str, Any]) -> Optional[TaskProofContract]:
    from .worktree_context import resolve_control_root
    base = resolve_control_root(base_dir)
    path = _task_doc_path(base, task)
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    strict = (
        _has_heading(text, 2, "Fixed Contract")
        and _has_heading(text, 3, "Proof Standard")
    )
    proof_section = _section(text, "Proof Standard")
    proof_text = "\n".join(
        line for line in proof_section.splitlines()
        if not _is_placeholder(line)
    )
    levels = re.findall(r"\b(Built|Wired|Running)\b", proof_text)
    commands = _extract_verification_commands(proof_section)

    placeholders: List[str] = []
    for label in (
        "Structural Home",
        "Objective",
        "Contract Responsibility",
        "Proof Standard",
    ):
        content = _section(text, label)
        if _is_placeholder(content):
            placeholders.append(label)
    if any(label in proof_section for label in VERIFICATION_LABELS) and not commands:
        placeholders.append("Verification Commands")

    return TaskProofContract(
        task_id=str(task.get("id") or task.get("task_id") or ""),
        path=path,
        strict=strict,
        proof_levels=levels,
        verification_commands=commands,
        placeholders=placeholders,
    )


def activation_proof_blockers(base_dir: str, task: Dict[str, Any]) -> List[str]:
    """Block activation of strict Task Packets with vague proof contracts."""
    contract = read_task_proof_contract(base_dir, task)
    if not contract or not contract.strict:
        return []
    blockers: List[str] = []
    if contract.placeholders:
        blockers.append(
            "Task Packet has unfilled proof contract fields: "
            + ", ".join(contract.placeholders)
        )
    if not contract.proof_levels:
        blockers.append("Task Packet Proof Standard has no Built/Wired/Running proof level")
    needs_commands = any(level in ("Wired", "Running") for level in contract.proof_levels)
    if needs_commands and not contract.verification_commands:
        blockers.append(
            "Task Packet has Wired/Running proof but no concrete Verification Commands"
        )
    for cmd in contract.verification_commands:
        if _is_placeholder(cmd.expected):
            blockers.append(
                f"Verification command lacks expected observable output: {cmd.command}"
            )
    return blockers


def validate_testing_against_task(
    base_dir: str,
    task: Dict[str, Any],
    testing: Dict[str, Any],
) -> Dict[str, Any]:
    """Compare recorded testing commands with the task's required commands."""
    contract = read_task_proof_contract(base_dir, task)
    if not contract or not contract.strict:
        return {"strict": False, "required_commands": [], "missing_commands": []}
    required = [cmd.command for cmd in contract.verification_commands]
    recorded = [
        _norm_command(cmd) for cmd in (testing.get("commands", []) or [])
        if _norm_command(cmd)
    ]
    verification_results = [
        item for item in (testing.get("verification_results", []) or [])
        if isinstance(item, dict)
    ]
    result_by_command = {
        _norm_command(item.get("command", "")): item
        for item in verification_results
        if _norm_command(item.get("command", ""))
    }
    recorded_set = set(recorded)
    missing = [cmd for cmd in required if _norm_command(cmd) not in recorded_set]
    missing_results = [cmd for cmd in required if _norm_command(cmd) not in result_by_command]
    mismatched = [
        cmd for cmd in required
        if _norm_command(cmd) in result_by_command
        and not bool(result_by_command[_norm_command(cmd)].get("matched", False))
    ]
    empty_observed = [
        cmd for cmd in required
        if _norm_command(cmd) in result_by_command
        and not _norm(result_by_command[_norm_command(cmd)].get("observed", ""))
    ]
    return {
        "strict": True,
        "required_commands": required,
        "recorded_commands": recorded,
        "missing_commands": missing,
        "missing_verification_results": missing_results,
        "mismatched_results": mismatched,
        "empty_observed_results": empty_observed,
    }


def testing_proof_gaps(proof: Dict[str, Any]) -> List[str]:
    """Return the exact strict-proof gaps that still need Tester attention."""
    if not proof.get("strict"):
        return []
    gaps: List[str] = []
    for key in (
        "missing_commands",
        "missing_verification_results",
        "mismatched_results",
        "empty_observed_results",
    ):
        gaps.extend(str(value) for value in (proof.get(key, []) or []))
    return list(dict.fromkeys(gaps))


def build_task_proof(base_dir: str, task: Dict[str, Any]) -> Dict[str, Any]:
    """Return the concise implementation/testing/review truth for one Task."""
    from .task_records import load_task_record

    task_id = str(task.get("id") or "")
    record = load_task_record(base_dir, task_id)
    implementation = record["implementation"]
    testing = record["testing"]
    review = record["review"]
    fix_loop = record["fix_loop"]

    origin = str(task.get("git_origin_ref") or "")
    implementation_ref = str(implementation.get("implementation_ref") or "")
    tested_ref = str(testing.get("tested_ref") or "")
    reviewed_ref = str(review.get("reviewed_ref") or "")
    diffs = []
    if origin and implementation_ref:
        diffs.append({
            "name": "implementation",
            "command": f"git diff {origin}..{implementation_ref}",
        })
    if implementation_ref and tested_ref:
        diffs.append({
            "name": "tester changes",
            "command": f"git diff {implementation_ref}..{tested_ref}",
        })
    if origin and tested_ref:
        diffs.append({
            "name": "final task",
            "command": f"git diff {origin}..{tested_ref}",
        })
    return {
        "task_id": task_id,
        "status": task.get("status", ""),
        "kind": task.get("kind", ""),
        "git": {
            "branch": task.get("git_branch", ""),
            "origin_ref": origin,
            "implementation_ref": implementation_ref,
            "tested_ref": tested_ref,
            "reviewed_ref": reviewed_ref,
            "commit": (task.get("closure", {}) or {}).get("git_commit", ""),
            "integration_base_ref": task.get("integration_base_ref", ""),
            "integration_plan_ref": task.get("integration_plan_ref", ""),
            "diffs": diffs,
        },
        "implementation": implementation,
        "testing": testing,
        "review": review,
        "fix_loop": fix_loop,
    }
