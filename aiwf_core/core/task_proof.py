"""Machine checks for Task.md proof contracts.

AIWF does not execute the project or decide whether an architecture is good.
This module only reads the task's declared proof contract and checks whether
the recorded testing surface covers it.
"""
from __future__ import annotations

import hashlib
import json
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
_COMMAND_PLACEHOLDER_RE = re.compile(r"(?<!\.)\.\.\.|<[A-Za-z_][A-Za-z0-9_./-]*>")


@dataclass
class VerificationCommand:
    verification_id: str
    command: str
    expected: str
    explicit_id: bool = True


@dataclass
class TaskProofContract:
    task_id: str
    path: Path
    schema_recognized: bool
    contract_errors: List[str]
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


def _verification_command_issue(command: str) -> str:
    """Return a small, obvious contract error without trying to parse a shell."""
    if _COMMAND_PLACEHOLDER_RE.search(str(command or "")):
        return "contains an ellipsis or angle-bracket placeholder"
    return ""


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
    id_index = next(
        (
            index for index, cell in enumerate(header)
            if cell in {"id", "check", "检查项", "检查 id"}
            or any(token in cell for token in ("verification id", "check id"))
        ),
        None,
    ) if is_header else None
    command_index = next(
        (
            index for index, cell in enumerate(header)
            if "command" in cell or "命令" in cell
        ),
        0,
    ) if is_header else 0
    expected_index = next(
        (
            index for index, cell in enumerate(header)
            if any(token in cell for token in ("expected", "observable", "预期", "可观察"))
        ),
        1,
    ) if is_header else 1
    commands: List[VerificationCommand] = []
    for row_index, row in enumerate(body, start=1):
        if len(row) <= max(command_index, expected_index):
            continue
        command = _norm_command(row[command_index])
        expected = _norm(row[expected_index])
        if not command or _is_placeholder(command):
            continue
        explicit_id = id_index is not None and id_index < len(row)
        verification_id = (
            _norm(row[id_index])
            if id_index is not None and id_index < len(row)
            else f"V-{row_index:03d}"
        )
        if not verification_id or _is_placeholder(verification_id):
            verification_id = f"V-{row_index:03d}"
            explicit_id = False
        commands.append(VerificationCommand(
            verification_id=verification_id,
            command=command,
            expected=expected,
            explicit_id=explicit_id,
        ))
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
    required_headings = (
        (2, "Fixed Contract"),
        (3, "Structural Home"),
        (3, "Objective"),
        (3, "Contract Responsibility"),
        (3, "Proof Standard"),
    )
    missing_headings = [
        f"{'#' * level} {heading}"
        for level, heading in required_headings
        if not _has_heading(text, level, heading)
    ]
    contract_errors = []
    if missing_headings:
        contract_errors.append(
            "Task.md contract structure is malformed; missing exact heading(s): "
            + ", ".join(missing_headings)
        )
    schema_recognized = not contract_errors
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
        schema_recognized=schema_recognized,
        contract_errors=contract_errors,
        proof_levels=levels,
        verification_commands=commands,
        placeholders=placeholders,
    )


def task_contract_structure_errors(base_dir: str, task: Dict[str, Any]) -> List[str]:
    contract = read_task_proof_contract(base_dir, task)
    if contract:
        return list(contract.contract_errors)
    from .worktree_context import resolve_control_root

    path = _task_doc_path(resolve_control_root(base_dir), task)
    return [f"Task.md proof contract is missing: {path}"]


def proof_contract_fingerprint(base_dir: str, task: Dict[str, Any]) -> str:
    """Identify the proof-bearing part of Task.md that testing establishes.

    Ordinary task prose is not part of the testing identity. The Proof Standard
    section is: it contains the proof level, claims, and verification table.
    """
    contract = read_task_proof_contract(base_dir, task)
    if not contract or not contract.path.exists():
        return ""
    proof_section = _section(
        contract.path.read_text(encoding="utf-8"), "Proof Standard"
    )
    canonical_lines = [
        _norm(line)
        for line in proof_section.splitlines()
        if _norm(line)
    ]
    payload = json.dumps(canonical_lines, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def activation_proof_blockers(base_dir: str, task: Dict[str, Any]) -> List[str]:
    """Block activation when the current Task contract is missing or incomplete."""
    contract = read_task_proof_contract(base_dir, task)
    structure_errors = task_contract_structure_errors(base_dir, task)
    if structure_errors:
        return structure_errors
    assert contract is not None
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
    seen_ids: Dict[str, str] = {}
    for cmd in contract.verification_commands:
        if not cmd.explicit_id:
            blockers.append(
                f"Verification command lacks stable ID: {cmd.command}"
            )
        elif cmd.verification_id in seen_ids:
            blockers.append(
                f"Verification commands reuse stable ID {cmd.verification_id}: "
                f"{seen_ids[cmd.verification_id]} and {cmd.command}"
            )
        else:
            seen_ids[cmd.verification_id] = cmd.command
        issue = _verification_command_issue(cmd.command)
        if issue:
            blockers.append(
                f"Verification command is not executable ({issue}): {cmd.verification_id}"
            )
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
    """Check proof coverage without treating command text as identity."""
    contract = read_task_proof_contract(base_dir, task)
    if not contract:
        return {
            "schema_recognized": False,
            "contract_errors": ["Task.md proof contract is missing"],
            "required_commands": [],
            "missing_commands": [],
        }
    if not contract.schema_recognized:
        return {
            "schema_recognized": False,
            "contract_errors": list(contract.contract_errors),
            "required_commands": [],
            "missing_commands": [],
        }
    required_items = contract.verification_commands
    required = [cmd.command for cmd in required_items]
    required_ids = [cmd.verification_id for cmd in required_items]
    verification_results = [
        item for item in (testing.get("verification_results", []) or [])
        if isinstance(item, dict)
    ]
    result_by_id = {
        str(item.get("verification_id") or "").strip(): item
        for item in verification_results
        if str(item.get("verification_id") or "").strip()
    }
    unbound_results = [
        _norm_command(item.get("command", ""))
        for item in verification_results
        if not str(item.get("verification_id") or "").strip()
        and _norm_command(item.get("command", ""))
    ]
    unknown_ids = [
        str(item.get("verification_id"))
        for item in verification_results
        if str(item.get("verification_id") or "").strip()
        and str(item.get("verification_id")) not in required_ids
    ]
    missing = [
        item.command for item in required_items
        if item.verification_id not in result_by_id
    ]
    missing_results = [
        item.command for item in required_items
        if item.verification_id not in result_by_id
    ]
    mismatched = [
        item.command for item in required_items
        if item.verification_id in result_by_id
        and result_by_id[item.verification_id].get("matched") is False
    ]
    blocked = [
        item.command for item in required_items
        if item.verification_id in result_by_id
        and str(result_by_id[item.verification_id].get("verdict") or "").lower() == "blocked"
    ]
    empty_observed = [
        item.command for item in required_items
        if item.verification_id in result_by_id
        and str(result_by_id[item.verification_id].get("verdict") or "").lower() != "blocked"
        and not _norm(result_by_id[item.verification_id].get("observed", ""))
    ]
    invalid_commands = [
        item.command for item in required_items
        if _verification_command_issue(item.command)
    ]
    return {
        "schema_recognized": True,
        "contract_errors": [],
        "required_commands": required,
        "required_verification_ids": required_ids,
        "recorded_commands": [
            _norm_command(item.get("command", ""))
            for item in verification_results
            if _norm_command(item.get("command", ""))
        ],
        "missing_commands": missing,
        "missing_verification_results": missing_results,
        "mismatched_results": mismatched,
        "blocked_results": blocked,
        "unknown_verification_ids": unknown_ids,
        "legacy_unbound_results": unbound_results,
        "empty_observed_results": empty_observed,
        "invalid_commands": invalid_commands,
    }


def testing_proof_gaps(proof: Dict[str, Any]) -> List[str]:
    """Return contract and proof gaps that still need Tester attention."""
    gaps: List[str] = list(proof.get("contract_errors", []) or [])
    for key in (
        "missing_commands",
        "missing_verification_results",
        "mismatched_results",
        "blocked_results",
        "unknown_verification_ids",
        "legacy_unbound_results",
        "empty_observed_results",
        "invalid_commands",
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
