#!/usr/bin/env python3
import sys, os
from pathlib import Path

# Add project root to sys.path for project-local imports.
_AH_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_AH_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AH_PROJECT_ROOT))

# === diagnostic log (persistent, check .aiwf/runtime/internal/hook-diag.log) ===
def _ah_diag(msg: str) -> None:
    try:
        _dp = _AH_PROJECT_ROOT / ".aiwf" / "runtime" / "internal"
        _dp.mkdir(parents=True, exist_ok=True)
        with open(_dp / "hook-diag.log", "a") as _df:
            import datetime
            _df.write(f"{datetime.datetime.now().isoformat()} [{os.path.basename(__file__)}] {msg}\n")
    except Exception:
        pass

_ah_diag(f"started, python={sys.executable}, argv={sys.argv[:3]}, cwd={os.getcwd()}, path={list(sys.path[:5])}")

# Discover aiwf_core at runtime — no hardcoded paths.
# 1. Pip-installed aiwf_core is importable directly.
# 2. Otherwise, read the toolkit path recorded by aiwf install.
try:
    import aiwf_core  # noqa: F401
    _ah_diag("import aiwf_core ok")
except ImportError as _e:
    _ah_diag(f"import aiwf_core failed: {_e}, trying toolkit-path.txt")
    _TK_CFG = _AH_PROJECT_ROOT / ".aiwf" / "runtime" / "internal" / "toolkit-path.txt"
    if _TK_CFG.exists():
        _TK_ROOT = _TK_CFG.read_text().strip()
        _ah_diag(f"toolkit-path.txt found: {_TK_ROOT}, exists={Path(_TK_ROOT).exists()}")
        if _TK_ROOT and Path(_TK_ROOT).exists() and _TK_ROOT not in sys.path:
            sys.path.insert(0, _TK_ROOT)
            _ah_diag("added toolkit root to sys.path")
    else:
        _ah_diag("toolkit-path.txt not found")
'''AIWF rebase state - generate .aiwf/artifacts/reports/当前状态.md carry-forward summary.'''
import json, sys
from datetime import datetime, timezone
from pathlib import Path

MAX_ITEMS = 5
MAX_HISTORY = 100
QUALITY_DIMENSIONS = [
    "requirement_fit",
    "architecture_fit",
    "minimality",
    "correctness",
    "test_adequacy",
    "maintainability",
    "risk_debt",
    "human_trust",
]
REVIEW_BASIS = ["goal", "plan", "scope", "evidence", "testing", "impact"]

def rj(path, default=None):
    try: return json.loads(path.read_text(encoding="utf-8")) if path.exists() else (default or {})
    except: return default or {}

def trunc(items, n=MAX_ITEMS):
    return (items or [])[:n]


def changed_files_from_evidence(evidence):
    changed = set()
    for rec in evidence.get("records", []) or []:
        if rec.get("status") == "accepted":
            for path in rec.get("changed_files") or []:
                changed.add(path)
    return sorted(changed)


def impact_quality_summary_requested(base, state):
    task_id = state.get("active_task_id") or state.get("active_plan_id") or ""
    if not task_id:
        return False
    plan_path = base / ".aiwf" / "artifacts" / "plans" / f"{task_id}.md"
    if not plan_path.exists():
        return False
    try:
        text = plan_path.read_text(encoding="utf-8")
    except Exception:
        return False
    import re
    match = re.search(r"## (?:Impact|Docs / Assets Impact)\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
    if not match:
        return False
    return bool(re.search(r"-\s+quality_summary:\s*yes\b", match.group(1), re.IGNORECASE))


def quality_dimension_summary(review):
    dims = review.get("quality_dimensions") or {}
    if not isinstance(dims, dict) or not dims:
        return "not scored"
    counts = {"PASS": 0, "RISK": 0, "FAIL": 0}
    non_pass = []
    for dim in QUALITY_DIMENSIONS:
        value = dims.get(dim, {})
        score = value.get("score") if isinstance(value, dict) else str(value or "")
        if score in counts:
            counts[score] += 1
        if score and score != "PASS":
            non_pass.append(f"{dim}={score}")
    text = f"PASS={counts['PASS']} RISK={counts['RISK']} FAIL={counts['FAIL']}"
    if non_pass:
        text += " (" + ", ".join(non_pass[:5]) + ")"
    return text


def review_basis_summary(review):
    basis = review.get("review_basis") or {}
    if not isinstance(basis, dict) or not basis:
        return "not recorded"
    counts = {"covered": 0, "gap": 0, "not_applicable": 0, "missing": 0}
    exceptions = []
    for name in REVIEW_BASIS:
        value = basis.get(name, {})
        status = value.get("status") if isinstance(value, dict) else "missing"
        if status not in counts:
            status = "missing"
        counts[status] += 1
        if status != "covered":
            exceptions.append(f"{name}={status}")
    text = (
        f"covered={counts['covered']} gap={counts['gap']} "
        f"not_applicable={counts['not_applicable']} missing={counts['missing']}"
    )
    if exceptions:
        text += " (" + ", ".join(exceptions[:5]) + ")"
    return text


def upsert_history(base, state, goal, evidence, testing, review, contexts, fix_loop):
    path = base / ".aiwf" / "runtime" / "history" / "task-history.json"
    history = rj(path, {"tasks": []})
    tasks = history.get("tasks", []) if isinstance(history.get("tasks"), list) else []

    goal_version = goal.get("goal_version", 1)
    changed = changed_files_from_evidence(evidence)
    ctx_ids = [c.get("id", "") for c in contexts.get("contexts", []) or [] if c.get("id")]

    # Use actual closed task IDs from the ledger when available, to avoid
    # double-counting alongside the synthetic goal-v{version}-closed entry.
    source_ids = []
    try:
        ledger_path = base / ".aiwf" / "runtime" / "history" / "task-ledger.json"
        if ledger_path.exists():
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            for t in ledger.get("tasks", []) or []:
                if isinstance(t, dict) and t.get("status") == "closed":
                    source_ids.append(t.get("id", ""))
    except Exception:
        pass

    if not source_ids:
        source_ids = [f"goal-v{goal_version}-closed"]

    existing_ids = {t.get("id") for t in tasks}
    for tid in source_ids:
        if tid in existing_ids:
            continue
        record = {
            "id": tid,
            "closed_at": datetime.now(timezone.utc).isoformat(),
            "goal_version": goal_version,
            "goal": goal.get("current_goal") or goal.get("active_goal", "") or "",
            "workflow_level": state.get("workflow_level", state.get("workflow_strength", "")),
            "task_type": state.get("task_type", ""),
            "context_ids": ctx_ids[:20],
            "accepted_evidence_count": len([r for r in evidence.get("records", []) or [] if r.get("status") == "accepted"]),
            "changed_files": changed[:50],
            "testing_status": testing.get("status", "missing"),
            "untested_risk_count": len(testing.get("untested_risks", []) or []),
            "review_result": review.get("result", "unknown"),
            "review_verdict": review.get("verdict", "pending"),
            "review_basis_status": review_basis_summary(review),
            "fix_loop_attempt_count": fix_loop.get("attempt_count", 0) or 0,
            "cleanup_status": review.get("cleanup_status", ""),
            "structure_status": review.get("structure_status", ""),
        }
        tasks.append(record)
    archived = history.get("archived_hotspots", {})
    if not isinstance(archived, dict): archived = {}
    if len(tasks) > MAX_HISTORY:
        for old in tasks[:-MAX_HISTORY]:
            for f in old.get("changed_files", []) or []:
                archived[f] = int(archived.get(f, 0) or 0) + 1
    history = {"tasks": tasks[-MAX_HISTORY:], "archived_hotspots": archived}
    path.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return history


def history_trend(history):
    recent = (history.get("tasks", []) or [])[-5:]
    if not recent:
        return []
    total_fix_attempts = sum(int(t.get("fix_loop_attempt_count", 0) or 0) for t in recent)
    risk_tasks = sum(1 for t in recent if int(t.get("untested_risk_count", 0) or 0) > 0)
    file_counts = {}
    for task in recent:
        for path in task.get("changed_files", []) or []:
            file_counts[path] = file_counts.get(path, 0) + 1
    repeated = sorted([p for p, c in file_counts.items() if c >= 2])[:5]
    lines = [
        f"- Recent closed tasks: {len(recent)}",
        f"- Fix-loop attempts across recent tasks: {total_fix_attempts}",
        f"- Tasks with deferred/untested risk: {risk_tasks}",
    ]
    if repeated:
        lines.append(f"- Repeatedly changed files: {', '.join(repeated)}")
    else:
        lines.append("- Repeatedly changed files: none")
    return lines


def quality_digest_lines(history, testing, review):
    recent = (history.get("tasks", []) or [])[-5:]
    file_counts = {}
    for task in recent:
        for path in task.get("changed_files", []) or []:
            file_counts[path] = file_counts.get(path, 0) + 1
    repeated = sorted([(p, c) for p, c in file_counts.items() if c >= 2], key=lambda x: (-x[1], x[0]))
    fix_attempts = sum(int(t.get("fix_loop_attempt_count", 0) or 0) for t in recent)
    risk_tasks = sum(1 for t in recent if int(t.get("untested_risk_count", 0) or 0) > 0)
    signals = []
    if repeated:
        signals.append(f"repeated_change_hotspot: {len(repeated)} file(s) changed repeatedly")
    if fix_attempts >= 3:
        signals.append(f"fix_loop_trend: {fix_attempts} recent attempts")
    if risk_tasks >= 2:
        signals.append(f"testing_debt_trend: {risk_tasks} recent tasks carried risk")
    if testing.get("cross_task_risks"):
        signals.append(f"tester_cross_task_risks: {len(testing['cross_task_risks'])}")
    if review.get("architecture_drift"):
        signals.append(f"architecture_drift: {len(review['architecture_drift'])}")
    lines = ["# AIWF Quality Digest", "", "## Recent Trend"]
    lines.append(f"- Recent closed tasks: {len(recent)}")
    lines.append(f"- Fix-loop attempts: {fix_attempts}")
    lines.append(f"- Tasks with untested/deferred risk: {risk_tasks}")
    lines.append("")
    lines.append("## Signals")
    if signals:
        for sig in signals: lines.append(f"- {sig}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Repeated Change Hotspots")
    if repeated:
        for path, count in repeated[:10]: lines.append(f"- {path} ({count} recent tasks)")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Tester / Reviewer Observations")
    observations = []
    for key in ["cross_task_risks", "testing_debt", "repeated_change_hotspots"]:
        observations.extend(testing.get(key, []) or [])
    for key in ["cross_task_risks", "architecture_drift", "testing_debt", "repeated_change_hotspots"]:
        observations.extend(review.get(key, []) or [])
    if observations:
        for obs in observations[:10]: lines.append(f"- {str(obs)[:200]}")
    else:
        lines.append("- none")
    return lines

def main():
    base = Path.cwd()
    state = rj(base / ".aiwf" / "state" / "state.json")

    # Safety guard: only rebase when workflow is closed
    if state.get("phase") != "closed" or not state.get("closure_allowed"):
        print("Rebase skipped: workflow is not closed / closure not allowed")
        sys.exit(2)

    goal = rj(base / ".aiwf" / "state" / "goal.json")
    evidence = rj(base / ".aiwf" / "artifacts" / "evidence" / "records.json", {"records": []})
    testing = rj(base / ".aiwf" / "artifacts" / "quality" / "testing.json")
    review = rj(base / ".aiwf" / "artifacts" / "quality" / "review.json")
    contexts = rj(base / ".aiwf" / "state" / "contexts.json")
    fix_loop = rj(base / ".aiwf" / "state" / "fix-loop.json")
    report_exists = (base / ".aiwf" / "artifacts" / "reports" / "闭合报告.md").exists()
    history = upsert_history(base, state, goal, evidence, testing, review, contexts, fix_loop)
    qd_path = base / ".aiwf" / "artifacts" / "reports" / "质量摘要.md"
    if impact_quality_summary_requested(base, state):
        qd_path.write_text("\n".join(quality_digest_lines(history, testing, review)) + "\n", encoding="utf-8")

    lines = []
    lines.append("# AIWF Current State")
    lines.append("")
    lines.append("*Carry-forward summary for Planner. Raw audit: .aiwf/artifacts/evidence/records.json, .aiwf/artifacts/quality/review.json, .aiwf/artifacts/reports/闭合报告.md.*")
    lines.append("")
    accepted_count = len([r for r in evidence.get('records', []) or [] if r.get('status') == 'accepted'])
    blockers = []
    if fix_loop.get("status") == "open":
        blockers.append(f"fix-loop route={fix_loop.get('route','?')}")
    if state.get("scope_violation"):
        blockers.append("scope violation")
    pending_adv = [
        o for o in (review.get("adversarial_observations", []) or [])
        if isinstance(o, dict) and o.get("disposition") == "pending"
    ]
    if pending_adv:
        blockers.append(f"{len(pending_adv)} pending adversarial observation(s)")
    lines.append("## Executive Summary")
    lines.append(f"- Goal: {goal.get('current_goal') or goal.get('active_goal', '') or '(none)'}")
    lines.append(f"- Now: phase={state.get('phase', 'unknown')}, task={state.get('active_task_id') or '(none)'}, workflow={state.get('workflow_level', state.get('workflow_strength', '?'))}")
    lines.append(f"- Quality: testing={testing.get('status', 'missing')}, review={review.get('result', 'unknown')}, verdict={review.get('verdict', 'pending')}, evidence={accepted_count}/{len(evidence.get('records', []) or [])} accepted")
    lines.append("- Blockers: " + (", ".join(blockers) if blockers else "none"))
    lines.append("")
    lines.append("## Goal & Intent")
    lines.append(f"- Goal: {goal.get('current_goal') or goal.get('active_goal', '') or '(none)'}")
    lines.append(f"- Goal version: {goal.get('goal_version', 1)}")
    lines.append(f"- Goal status: {goal.get('goal_status', 'discussion')}")
    lines.append("")
    lines.append("## Current Status")
    lines.append(f"- Phase: {state.get('phase', 'unknown')}")
    lines.append(f"- Workflow level: {state.get('workflow_level', state.get('workflow_strength', '?'))}")
    lines.append(f"- Task type: {state.get('task_type', '') or '(none)'}")
    lines.append(f"- Closure allowed: {state.get('closure_allowed', False)}")
    lines.append("")
    lines.append("## Quality Snapshot")
    lines.append(f"- Testing: {testing.get('status', 'missing')}")
    lines.append(f"- Review: {review.get('result', 'unknown')}")
    lines.append(f"- Verdict: {review.get('verdict', 'pending')}")
    lines.append(f"- Quality dimensions: {quality_dimension_summary(review)}")
    lines.append(f"- Review basis: {review_basis_summary(review)}")
    lines.append(f"- Accepted evidence: {accepted_count}")
    lines.append("")
    lines.append("## Last closed task")
    lines.append(f"- Goal: {goal.get('current_goal') or goal.get('active_goal', '') or '(none)'}")
    lines.append(f"- Goal version: {goal.get('goal_version', 1)}")
    lines.append(f"- Goal status: {goal.get('goal_status', 'discussion')}")
    lines.append(f"- Workflow level: {state.get('workflow_level', state.get('workflow_strength', '?'))}")
    lines.append(f"- Task type: {state.get('task_type', '') or '(none)'}")
    lines.append(f"- Phase: {state.get('phase', 'unknown')}")
    lines.append(f"- Closure allowed: {state.get('closure_allowed', False)}")
    lines.append("")

    changed = changed_files_from_evidence(evidence)
    if changed:
        lines.append("## Changed project files")
        for f in changed[:15]: lines.append(f"- {f}")
    else:
        lines.append("## Changed project files")
        lines.append("- none")
    lines.append("")

    lines.append(f"## Test result: {testing.get('status', 'missing')}")
    if testing.get("commands"): lines.append(f"- Commands: {', '.join(testing['commands'][:3])}")
    lines.append("")

    lines.append(f"## Review result: {review.get('result', 'unknown')} / verdict: {review.get('verdict', 'pending')}")
    lines.append("")

    lines.append("## Task history trend")
    for line in history_trend(history):
        lines.append(line)
    lines.append("")

    lines.append("## Quality digest")
    if qd_path.exists():
        lines.append("- .aiwf/artifacts/reports/质量摘要.md")
    else:
        lines.append("- not generated (Impact.quality_summary is not yes)")
    lines.append("")

    lessons = trunc(review.get("lessons", []))
    lines.append("## Carry-forward lessons")
    if lessons:
        for l in lessons: lines.append(f"- {str(l)[:200]}")
    else: lines.append("- none")
    lines.append("")

    neg = trunc(review.get("negative_patterns", []))
    lines.append("## Negative patterns to avoid")
    if neg:
        for n in neg: lines.append(f"- {str(n)[:200]}")
    else: lines.append("- none")
    lines.append("")

    fups = trunc(review.get("followups", []))
    lines.append("## Follow-up candidates")
    if fups:
        for f in fups: lines.append(f"- {str(f)[:200]}")
    else: lines.append("- none")
    lines.append("")

    risks = trunc(testing.get("untested_risks", []))
    lines.append("## Deferred risks")
    if risks:
        for r in risks: lines.append(f"- {str(r)[:200]}")
    else: lines.append("- none")
    lines.append("")

    ctx_list = contexts.get("contexts", []) or []
    ctx_ids = [c.get("id","") for c in ctx_list if c.get("id")][:10]
    lines.append("## Contexts involved")
    if ctx_ids: lines.append(f"- {', '.join(ctx_ids)}")
    else: lines.append("- none")
    lines.append("")

    lines.append("## Raw References")
    lines.append("")
    lines.append("## Raw audit references")
    lines.append("- .aiwf/artifacts/reports/闭合报告.md" if report_exists else "- .aiwf/artifacts/reports/闭合报告.md (not generated)")
    lines.append("- .aiwf/artifacts/reports/质量摘要.md" if qd_path.exists() else "- .aiwf/artifacts/reports/质量摘要.md (not generated)")
    lines.append("- .aiwf/artifacts/evidence/records.json")
    lines.append("- .aiwf/artifacts/quality/review.json")
    lines.append("")

    out = base / ".aiwf" / "artifacts" / "reports" / "当前状态.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Current state written to {out}")

if __name__ == "__main__":
    main()
