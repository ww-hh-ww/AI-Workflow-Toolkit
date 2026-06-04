
#!/usr/bin/env python3
'''AIWF export report — self-contained, stdlib-only, no aiwf_core imports.'''
import json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

GOV_PREFIXES = [".aiwf/", ".claude/", ".reasonix/", "scripts/aiwf_", "scripts/__pycache__/", "CLAUDE.md", "REASONIX.md", "AGENTS.md"]

def rj(path, default=None):
    try: return json.loads(path.read_text(encoding="utf-8")) if path.exists() else (default or {})
    except: return default or {}

def is_gov(path):
    for p in GOV_PREFIXES:
        if path == p.rstrip("/") or path.startswith(p): return True
    return False

def _path_from_status_line(line):
    # Return path from `git status --short` line, including untracked and renames.
    raw = line.rstrip()
    if not raw:
        return ""
    # Format is "XY path" or "XY old -> new"; for untracked: "?? path".
    payload = raw[3:] if len(raw) >= 3 else raw
    if " -> " in payload:
        payload = payload.split(" -> ", 1)[1]
    return payload.strip()

def git_summary(base):
    try:
        r = subprocess.run(["git", "status", "--short", "--untracked-files=all"], capture_output=True, text=True, cwd=str(base), timeout=5)
        if r.returncode != 0: return None
        status_lines = [l.rstrip() for l in r.stdout.split("\n") if l.strip()]
        r2 = subprocess.run(["git", "diff", "--stat"], capture_output=True, text=True, cwd=str(base), timeout=5)
        stat = [l for l in r2.stdout.split("\n") if l.strip()]

        changed = []
        seen = set()
        for line in status_lines:
            f = _path_from_status_line(line)
            if f and f not in seen:
                changed.append(f)
                seen.add(f)

        proj = [f for f in changed if not is_gov(f)]
        gov = [f for f in changed if is_gov(f)]
        return {"status_count": len(status_lines), "changed": changed, "project": proj, "governance": gov, "stat": stat[:20], "dirty": len(status_lines) > 0}
    except: return None

def task_history_summary(base):
    history = rj(base / ".aiwf" / "history" / "task-history.json", {"tasks": []})
    tasks = history.get("tasks", []) if isinstance(history.get("tasks"), list) else []
    recent = tasks[-5:]
    file_counts = {}
    for task in recent:
        for path in task.get("changed_files", []) or []:
            file_counts[path] = file_counts.get(path, 0) + 1
    repeated = sorted([p for p, count in file_counts.items() if count >= 2])
    return {
        "total": len(tasks),
        "recent": recent,
        "recent_fix_attempts": sum(int(t.get("fix_loop_attempt_count", 0) or 0) for t in recent),
        "recent_risk_tasks": sum(1 for t in recent if int(t.get("untested_risk_count", 0) or 0) > 0),
        "repeated_files": repeated,
    }

def main():
    base = Path.cwd()
    out_path = base / ".aiwf" / "reports" / "闭合报告.md"

    state = rj(base / ".aiwf" / "state" / "state.json")
    goal = rj(base / ".aiwf" / "state" / "goal.json")
    evidence = rj(base / ".aiwf" / "evidence" / "records.json", {"records": []})
    testing = rj(base / ".aiwf" / "quality" / "testing.json", {"status": "missing"})
    review = rj(base / ".aiwf" / "quality" / "review.json", {"result": "unknown", "closure_allowed": False})
    fix_loop = rj(base / ".aiwf" / "state" / "fix-loop.json", {"status": "none"})
    contexts = rj(base / ".aiwf" / "state" / "contexts.json", {"contexts": []})

    recs = evidence.get("records", []) or []
    accepted_ids = [r["id"] for r in recs if r.get("status") == "accepted"]
    changed = set()
    gov_changed = set()
    for r in recs:
        for f in (r.get("changed_files") or []): changed.add(f)
        for f in (r.get("governance_changed_files") or []): gov_changed.add(f)

    lines = []
    lines.append("# AIWF Closure Report")
    lines.append("")
    lines.append("*Human-readable closure basis. Machine state: .aiwf/state|quality|evidence|history JSON. Carry-forward: .aiwf/reports/当前状态.md.*")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append("")
    lines.append("## Goal")
    lines.append(f"- {goal.get('active_goal', '') or '(none)'}")
    lines.append(f"- Confirmed: {goal.get('confirmed', False)}")
    lines.append("")

    # ── Quality Policy ──
    lines.append("## Quality Policy")
    qp_fields = [("workflow_level", "Level"), ("task_type", "Task type"), ("test_template", "Test"), ("review_template", "Review"), ("exploration_budget", "Exploration"), ("asset_policy", "Asset"), ("cleanup_policy", "Cleanup"), ("git_policy", "Git")]
    for key, label in qp_fields:
        v = state.get(key, "")
        if v: lines.append(f"- {label}: {v}")
    if state.get("quality_escalation_required"):
        lines.append(f"- ⚠ Escalation required: recommended {state.get('recommended_minimum_level', '?')}")
        if state.get("quality_escalation_reason"): lines.append(f"  Reason: {state['quality_escalation_reason'][:200]}")
    lines.append("")

    # ── Quality Brief ──
    brief = goal.get("quality_brief", {})
    lines.append("## Quality Brief")
    if brief.get("acceptance_criteria") or brief.get("test_focus"):
        for key, label in [("acceptance_criteria", "Acceptance"), ("test_focus", "Test focus"), ("review_focus", "Review focus"), ("non_goals", "Non-goals"), ("escalation_triggers", "Escalation triggers")]:
            items = brief.get(key, [])
            if items:
                lines.append(f"- {label}:")
                for item in items[:5]:
                    lines.append(f"  - {str(item)[:160]}")
    else:
        lines.append("- Quality brief: missing")
    # Quality surfaces
    surfaces = brief.get("surface_types", []) or []
    inferred = testing.get("inferred_surfaces", []) or []
    missing_notes = testing.get("missing_surface_notes", []) or []
    if surfaces or inferred:
        if surfaces:
            lines.append(f"- Quality surfaces (declared): {', '.join(surfaces)}")
        if inferred:
            lines.append(f"- Quality surfaces (inferred by tester): {', '.join(inferred)}")
        if missing_notes:
            lines.append("- Missing surface notes:")
            for n in missing_notes[:5]: lines.append(f"  - {n[:160]}")
    lines.append("")

    # ── Architecture Brief ──
    ab = brief.get("architecture_brief", {}) if isinstance(brief, dict) else {}
    has_ab = ab and any(v for v in ab.values() if v and v != "" and v != [])
    lines.append("## Architecture Brief")
    if has_ab:
        if ab.get("target_structure"): lines.append(f"- Target structure: {ab['target_structure'][:200]}")
        if ab.get("module_boundaries"):
            lines.append("- Module boundaries:"); [lines.append(f"  - {m[:160]}") for m in ab["module_boundaries"][:10]]
        if ab.get("allowed_files"):
            lines.append("- Allowed files:"); [lines.append(f"  - {f[:160]}") for f in ab["allowed_files"][:15]]
        if ab.get("protected_files"):
            lines.append("- Protected files:"); [lines.append(f"  - {f[:160]}") for f in ab["protected_files"][:10]]
        if ab.get("allowed_new_files"):
            lines.append("- Allowed new files:"); [lines.append(f"  - {f[:160]}") for f in ab["allowed_new_files"][:10]]
        if ab.get("public_api_changes"):
            lines.append("- Public API changes:"); [lines.append(f"  - {p[:160]}") for p in ab["public_api_changes"][:5]]
        if ab.get("integration_points"):
            lines.append("- Integration points:"); [lines.append(f"  - {ip[:160]}") for ip in ab["integration_points"][:10]]
        if ab.get("architecture_invariants"):
            lines.append("- Architecture invariants:"); [lines.append(f"  - {ai[:160]}") for ai in ab["architecture_invariants"][:10]]
        if ab.get("forbidden_restructures"):
            lines.append("- Forbidden restructures:"); [lines.append(f"  - {fr[:160]}") for fr in ab["forbidden_restructures"][:10]]
        if ab.get("architecture_risks"):
            lines.append("- Architecture risks:"); [lines.append(f"  - {ar[:160]}") for ar in ab["architecture_risks"][:10]]
    else:
        lines.append("- Architecture brief: none")
    lines.append("")

    # ── Git Summary ──
    lines.append("## Git Summary")
    gs = git_summary(base)
    if gs is None:
        lines.append("- Not a git repository")
    else:
        lines.append(f"- Dirty working tree: {gs['dirty']}")
        lines.append(f"- Changed files: {len(gs['changed'])}")
        lines.append(f"- Project files: {len(gs['project'])}")
        lines.append(f"- Governance/support files: {len(gs['governance'])}")
        if gs["project"]:
            lines.append("- Project changes:")
            for f in gs["project"][:15]: lines.append(f"  - {f}")
        if gs["governance"]:
            lines.append("- Governance/support changes:")
            for f in gs["governance"][:15]: lines.append(f"  - {f}")
        if gs["stat"]:
            lines.append("- Diff stat:")
            for s in gs["stat"][:15]: lines.append(f"  {s}")
    lines.append("")

    # ── Task History Trend ──
    lines.append("## Task History Trend")
    th = task_history_summary(base)
    if th["total"]:
        lines.append(f"- Closed tasks recorded: {th['total']}")
        lines.append(f"- Recent fix-loop attempts: {th['recent_fix_attempts']}")
        lines.append(f"- Recent tasks with deferred/untested risk: {th['recent_risk_tasks']}")
        if th["repeated_files"]:
            lines.append("- Repeatedly changed files:")
            for f in th["repeated_files"][:10]:
                lines.append(f"  - {f}")
        else:
            lines.append("- Repeatedly changed files: none")
    else:
        lines.append("- Closed task history: none")
    lines.append("")

    # ── Cross-task Quality ──
    lines.append("## Cross-task Quality")
    qd_path = base / ".aiwf" / "reports" / "质量摘要.md"
    if qd_path.exists():
        qd = qd_path.read_text(encoding="utf-8", errors="ignore")
        signal_lines = [line for line in qd.splitlines() if line.startswith("- ")][:10]
        lines.append("- Quality digest: available")
        for line in signal_lines:
            lines.append(f"  {line}")
    else:
        lines.append("- Quality digest: none")
    lines.append("")

    # ── Environment ──
    lines.append("## Environment")
    env_profile = {}
    env_path = base / ".aiwf" / "assets" / "environment.json"
    if env_path.exists():
        try: env_profile = json.loads(env_path.read_text(encoding="utf-8"))
        except: pass
    if env_profile:
        lines.append("- Profile: available")
        if env_profile.get("languages"): lines.append(f"- Languages: {', '.join(env_profile['languages'])}")
        if env_profile.get("package_managers"): lines.append(f"- Package managers: {', '.join(env_profile['package_managers'])}")
        if env_profile.get("test_commands"): lines.append(f"- Test commands: {', '.join(env_profile['test_commands'][:3])}")
        missing = env_profile.get("missing_tools", [])
        if missing: lines.append(f"- Missing tools: {', '.join(missing[:8])}")
        risks = env_profile.get("known_environment_risks", [])
        if risks:
            lines.append("- Environment risks:")
            for r in risks[:5]: lines.append(f"  - {r[:160]}")
    else:
        lines.append("- Profile: missing")
    lines.append("")

    # ── Lifecycle Cleanup ──
    lines.append("## Lifecycle Cleanup")
    try:
        from aiwf_core.core.lifecycle_cleanup import check_lifecycle_cleanup
        result = check_lifecycle_cleanup(str(base))
        lines.append(f"- Cleanup: {result['cleanup_status']}")
        lines.append(f"- Structure: {result['structure_status']}")
        if result["blockers"]:
            lines.append("- Blockers:")
            for b in result["blockers"][:10]: lines.append(f"  - {b}")
        if result["warnings"]:
            lines.append("- Warnings:")
            for w in result["warnings"][:10]: lines.append(f"  - {w}")
        if result["stale_items"]:
            lines.append("- Stale items:")
            for s in result["stale_items"][:10]: lines.append(f"  - {str(s)[:160]}")
        # Source trust/freshness summary
        trust_warnings = []
        if result.get("idea_issues"): trust_warnings.extend(result["idea_issues"])
        if result.get("deferred_risk_issues"): trust_warnings.extend(result["deferred_risk_issues"])
        if trust_warnings:
            lines.append("- Source trust / freshness:")
            for tw in trust_warnings[:5]: lines.append(f"  - {str(tw)[:160]}")
        if result["suggested_actions"]:
            lines.append("- Suggested:")
            for s in result["suggested_actions"][:5]: lines.append(f"  - {s}")
        if not result["blockers"] and not result["warnings"] and not trust_warnings:
            lines.append("- No blockers.")
            lines.append("- No warnings.")
    except Exception:
        lines.append("- Cleanup check: not run")
    lines.append("")

    # ── Project Rules ──
    lines.append("## Project Rules")
    import re as _re3
    rules_path = base / ".aiwf" / "project-rules.md"
    if rules_path.exists():
        rtxt = rules_path.read_text(encoding="utf-8")
        active = len(_re3.findall(r'### RULE-.+ \| active \| rule', rtxt))
        negatives = len(_re3.findall(r'### RULE-.+ \| active \| negative_rule', rtxt))
        candidates = len(_re3.findall(r'### RULE-.+ \| .+ \| global_candidate', rtxt))
        lines.append(f"- Active rules: {active}")
        lines.append(f"- Negative rules: {negatives}")
        lines.append(f"- Global candidates: {candidates}")
    else:
        lines.append("- Project rules: none")
    lines.append("")

    # ── Evidence ──
    lines.append("## Evidence")
    lines.append(f"- Raw records: {len(recs)}")
    lines.append(f"- Accepted: {len(accepted_ids)}")
    if accepted_ids: lines.append(f"- Accepted IDs: {', '.join(accepted_ids[:10])}")
    if changed:
        lines.append("- Changed project files:")
        [lines.append(f"  - {f}") for f in sorted(changed)[:15]]
    if gov_changed:
        lines.append("- Changed governance/support files:")
        [lines.append(f"  - {f}") for f in sorted(gov_changed)[:15]]
    lines.append("")

    # ── Testing ──
    lines.append("## Testing")
    lines.append(f"- Status: {testing.get('status', 'missing')}")
    if testing.get("untested_risks"):
        lines.append("- Untested risks:"); [lines.append(f"  - {r[:160]}") for r in testing["untested_risks"][:5]]
    lines.append("")

    # ── Review ──
    lines.append("## Review")
    lines.append(f"- Result: {review.get('result', 'unknown')}")
    lines.append(f"- Closure allowed: {review.get('closure_allowed', False)}")
    if review.get("blockers"):
        lines.append("- Blockers:"); [lines.append(f"  - {b[:200]}") for b in review["blockers"][:10]]
    lines.append("")

    # ── Closure Gate ──
    # Evaluation Contract
    ec = goal.get("quality_brief", {}).get("evaluation_contract", {})
    if ec.get("user_visible_outcome") or ec.get("acceptance_criteria"):
        lines.append("## Evaluation Contract")
        if ec.get("user_visible_outcome"): lines.append(f"- Outcome: {ec['user_visible_outcome'][:200]}")
        if ec.get("acceptance_criteria"):
            lines.append("- Acceptance criteria:"); [lines.append(f"  - {a[:160]}") for a in ec["acceptance_criteria"][:10]]
        if ec.get("non_goals"):
            lines.append("- Non-goals:"); [lines.append(f"  - {n[:160]}") for n in ec["non_goals"][:10]]
        if ec.get("test_obligations"):
            lines.append("- Test obligations:"); [lines.append(f"  - {t[:160]}") for t in ec["test_obligations"][:10]]
        if ec.get("review_obligations"):
            lines.append("- Review obligations:"); [lines.append(f"  - {r[:160]}") for r in ec["review_obligations"][:10]]
        if ec.get("system_integration_obligations"):
            lines.append("- System integration obligations:"); [lines.append(f"  - {s[:160]}") for s in ec["system_integration_obligations"][:10]]
        if ec.get("known_risks"):
            lines.append("- Known risks:"); [lines.append(f"  - {k[:160]}") for k in ec["known_risks"][:10]]
        if ec.get("closure_question"): lines.append(f"- Closure question: {ec['closure_question'][:200]}")
        lines.append("")
        lines.append("## Evaluation Coverage")
        # Show real coverage from testing.json, not just placeholders
        ac = testing.get("acceptance_coverage", []) or []
        sc = testing.get("system_coverage", []) or []
        fo = testing.get("failed_obligations", []) or []
        ur = testing.get("untested_risks", []) or []
        if ac:
            lines.append("- Acceptance coverage:"); [lines.append(f"  - {a[:160]}") for a in ac[:20]]
        else:
            lines.append("- Acceptance coverage: none / not recorded")
        if sc:
            lines.append("- System coverage:"); [lines.append(f"  - {s[:160]}") for s in sc[:20]]
        else:
            lines.append("- System coverage: none / not recorded")
        if fo:
            lines.append("- Failed obligations:"); [lines.append(f"  - {f[:160]}") for f in fo[:10]]
        if ur:
            lines.append("- Untested risks:"); [lines.append(f"  - {u[:160]}") for u in ur[:10]]
        # Non-goals and gaps
        lines.append("- Non-goals respected: (see Reviewer report)")
        lines.append("- Known risks handled/deferred: (see Reviewer report)")
        blockers_rpt = review.get("blockers", []) or []
        gaps = list(fo[:5]) + list(ur[:5]) + list(str(b)[:160] for b in blockers_rpt[:5])
        if gaps:
            lines.append("- Remaining gaps:")
            for g in gaps[:10]: lines.append(f"  - {str(g)[:160]}")
        else:
            lines.append("- Remaining gaps: none reported")
        lines.append("")
    else:
        lines.append("## Evaluation Contract")
        lines.append("- Evaluation contract: missing")
        lines.append("")

    lines.append("## Closure Gate")
    close_attempt = state.get("close_attempt", False)
    ev_ok = len(accepted_ids) > 0
    test_ok = testing.get("status") in ("adequate", "passed")
    review_ok = review.get("result") == "accepted" and review.get("closure_allowed", False)
    fix_ok = fix_loop.get("status") != "open"
    scope_ok = not state.get("scope_violation", False)
    cleanup_ok = review.get("cleanup_status") == "fresh" and not review.get("stale_items") and not review.get("cleanup_blockers")
    structure_ok = review.get("structure_status") == "accepted"
    all_ok = close_attempt and ev_ok and test_ok and review_ok and fix_ok and scope_ok and cleanup_ok and structure_ok

    lines.append(f"- Close attempt: {close_attempt}")
    lines.append(f"- Evidence accepted: {ev_ok} ({len(accepted_ids)} records)")
    lines.append(f"- Testing adequate: {test_ok} ({testing.get('status', '?')})")
    lines.append(f"- Review accepted: {review_ok}")
    lines.append(f"- Fix loop clear: {fix_ok}")
    lines.append(f"- Scope clean: {scope_ok}")
    lines.append(f"- Cleanup fresh: {cleanup_ok}")
    lines.append(f"- Structure accepted: {structure_ok}")
    lines.append(f"- Closure status: {'ALLOWED' if all_ok else 'BLOCKED'}")
    if not all_ok:
        blockers = []
        if not ev_ok: blockers.append("no accepted evidence")
        if not test_ok: blockers.append("testing not adequate")
        if not review_ok: blockers.append("review not accepted")
        if not fix_ok: blockers.append("fix-loop open")
        if not scope_ok: blockers.append("scope violation")
        if not cleanup_ok: blockers.append("cleanup not fresh")
        if not structure_ok: blockers.append("structure not accepted")
        if not close_attempt: blockers.append("close_attempt not set")
        if blockers: lines.append(f"- Blockers: {', '.join(blockers)}")
    lines.append("")

    # ── Fix-loop ──
    lines.append("## Fix-loop")
    if fix_loop.get("status") == "open":
        lines.append(f"- Status: {fix_loop['status']}")
        lines.append(f"- Route: {fix_loop.get('route', '?')}")
        attempt = fix_loop.get('attempt_count', 0)
        max_att = fix_loop.get('max_attempts', '?')
        lines.append(f"- Attempt: {attempt} / {max_att}")
        if fix_loop.get("escalation_required"):
            lines.append(f"- ⚠ Escalation required: yes")
            if fix_loop.get("escalation_reason"):
                lines.append(f"  Reason: {fix_loop['escalation_reason'][:200]}")
        if fix_loop.get("rollback_recommended"):
            lines.append(f"- ⚠ Rollback recommended: yes (checkpoint exists)")
        lines.append(f"- Reason: {fix_loop.get('reason', '')[:200]}")
        if fix_loop.get("required_fixes"):
            lines.append("- Required fixes:")
            for rf in fix_loop["required_fixes"][:10]:
                lines.append(f"  - {str(rf)[:160]}")
        if fix_loop.get("required_verification"):
            lines.append("- Required verification:")
            for rv in fix_loop.get("required_verification", [])[:10]:
                lines.append(f"  - {str(rv)[:160]}")
        if fix_loop.get("source"):
            lines.append(f"- Source: {fix_loop['source']}")
        # Route history summary
        rh = fix_loop.get("route_history", []) or []
        if len(rh) > 1:
            lines.append("- Route history:")
            for h in rh[-5:]:
                lines.append(f"  - #{h.get('attempt','?')} → {h.get('route','?')}: {h.get('reason','')[:80]}")
    elif fix_loop.get("status") == "resolved":
        lines.append(f"- Status: resolved")
        if fix_loop.get("resolution"):
            lines.append(f"- Resolution: {fix_loop['resolution'][:200]}")
    elif fix_loop.get("status") == "none":
        # If testing failed but no fix-loop, warn
        if testing.get("status") == "failed":
            lines.append("- Fix-loop: missing for failed testing")
        else:
            lines.append("- Status: none")
    else:
        lines.append(f"- Status: {fix_loop.get('status', 'none')}")
    lines.append("")

    # ── Architecture Change Requests ──
    acrs = fix_loop.get("architecture_change_requests", []) or []
    lines.append("## Architecture Change Requests")
    if acrs:
        for a in acrs:
            lines.append(f"- {a.get('id','?')}: {a.get('status','?')}")
            if a.get("source"): lines.append(f"  - source: {a['source']}")
            if a.get("reason"): lines.append(f"  - reason: {a['reason'][:160]}")
            if a.get("proposed_change"): lines.append(f"  - proposed: {a['proposed_change'][:160]}")
            if a.get("planner_decision"): lines.append(f"  - decision: {a['planner_decision'][:160]}")
    else:
        lines.append("- Architecture change requests: none")
    lines.append("")

    # ── Lessons / Negative Patterns / Follow-ups ──
    def _fmt(item):
        # Format a lesson/pattern/followup item (string or dict) safely.
        if isinstance(item, str):
            return str(item)[:200]
        if isinstance(item, dict):
            main = item.get("lesson") or item.get("pattern") or item.get("followup") or item.get("title") or item.get("description", "")
            main = str(main)[:200]
            extras = []
            for key, label in [("applies_to", "applies_to"), ("affects", "affects"), ("source", "source")]:
                v = item.get(key)
                if v:
                    if isinstance(v, list):
                        extras.append(f"{label}: {', '.join(str(x) for x in v[:5])}")
                    elif isinstance(v, str) and v:
                        extras.append(f"{label}: {v[:120]}")
            if extras:
                return main + "\n    " + "\n    ".join(extras)
            return main or "(empty)"
        return str(item)[:200]

    if review.get("lessons"):
        lines.append("## Lessons")
        for l in review["lessons"][:10]:
            lines.append(f"- {_fmt(l)}")
        lines.append("")
    if review.get("negative_patterns"):
        lines.append("## Negative Patterns")
        for p in review["negative_patterns"][:10]:
            lines.append(f"- {_fmt(p)}")
        lines.append("")
    if review.get("followups"):
        lines.append("## Follow-ups")
        for f in review["followups"][:10]:
            lines.append(f"- {_fmt(f)}")
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report written to {out_path}")

if __name__ == "__main__":
    main()
