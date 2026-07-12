#!/usr/bin/env python3
"""AIWF UserPromptSubmit — quiet workflow nudge."""

import json
import os
import sys
from pathlib import Path


def _read_json(path, default):
    if not path.exists():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else default
    except Exception:
        return default


def _emit(text):
    if os.environ.get("AIWF_HOOK_ENGINE", "").lower() == "reasonix":
        print(text)
        return
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": text,
    }}))


def _close_ready(testing, review):
    return (
        testing.get("status") in ("adequate", "passed")
        and review.get("result") == "accepted"
        and bool(review.get("closure_allowed", False))
    )


def _closure_calibration_missing(cwd, task_id, testing, review):
    if not task_id or not _close_ready(testing, review):
        return False
    task_doc = cwd / ".aiwf" / "tasks" / f"{task_id}.md"
    if not task_doc.exists():
        return False
    try:
        return "## Closure Calibration" not in task_doc.read_text(
            encoding="utf-8",
            errors="ignore",
        )
    except Exception:
        return False


def _stage(state, testing, review):
    phase = state.get("phase", "planning")
    task_id = state.get("active_task_id", "")
    if not task_id or phase in ("planning", "planned", "discussing"):
        return "before"
    if _close_ready(testing, review):
        return "close"
    return "during"


def _top_problem(cwd, state, testing, review, fix_loop):
    if fix_loop.get("status") == "open":
        return "fix-loop open"
    if state.get("scope_violation"):
        return "scope violation"
    if review.get("result") in ("rejected", "needs_fix", "scope_violation"):
        return f"review {review.get('result')}"
    task_id = state.get("active_task_id", "")
    if _closure_calibration_missing(cwd, task_id, testing, review):
        return "closure calibration missing"
    return ""


def _message(stage, problem):
    if stage == "before":
        line = (
            "[AIWF] Plan Before Work: do not start from memory. "
            "Read reality, write a trustworthy contract, critique before activation."
        )
    elif stage == "close":
        line = (
            "[AIWF] Learn After Work: do not just close status. "
            "Calibrate actual outcome, handle follow-ups, and maintain memory."
        )
    else:
        line = (
            "[AIWF] Guard The Work: do not let the flow drift. "
            "Use status, route findings, and keep contracts honest."
        )
    suffix = " Run `aiwf status --prompt` before acting."
    if problem:
        suffix = f" Attention: {problem}. Run `aiwf status --prompt` before acting."
    return line + suffix


def main():
    cwd = Path(__file__).resolve().parent.parent

    state_path = cwd / ".aiwf" / "state" / "state.json"
    if not state_path.exists():
        _emit("[AIWF] Not initialized. Run: aiwf install claude")
        return

    state = _read_json(state_path, {})
    testing = _read_json(cwd / ".aiwf" / "records" / "testing.json", {"status": "missing"})
    review = _read_json(cwd / ".aiwf" / "records" / "review.json", {"result": "unknown"})
    fix_loop = _read_json(cwd / ".aiwf" / "state" / "fix-loop.json", {"status": "none"})

    stage = _stage(state, testing, review)
    problem = _top_problem(cwd, state, testing, review, fix_loop)
    fingerprint = {
        "stage": stage,
        "active_task_id": state.get("active_task_id", "") or "",
        "active_plan_id": state.get("active_plan_id", "") or "",
        "problem": problem,
    }

    fp_path = cwd / ".aiwf" / "runtime" / "internal" / "status-hook-last.json"
    old = _read_json(fp_path, {})
    if old == fingerprint:
        return

    try:
        fp_path.parent.mkdir(parents=True, exist_ok=True)
        fp_path.write_text(json.dumps(fingerprint, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass

    _emit(_message(stage, problem))


if __name__ == "__main__":
    main()
