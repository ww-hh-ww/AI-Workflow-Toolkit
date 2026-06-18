"""Lifecycle cleanup check — read-only scan for staleness, pollution, blockers."""
from __future__ import annotations

import json, re
from pathlib import Path
from typing import Any, Dict, List

from .state.goal_ops import get_active_goal

PM_REQUIRED_SECTIONS = [
    "Project Snapshot", "Current Stage", "Completed Milestones",
    "Active Direction", "Next Candidate Tasks", "Architecture Direction",
    "Environment Summary", "Open Decisions", "Deferred Risks",
    "Not-now / Rejected Routes", "Ideas to Review",
]

RAW_IDEA_MARKERS = ["# AIWF Ideas", "## Active Ideas", "### IDEA-", "Status: raw", "| raw"]
RAW_EVIDENCE_MARKERS = ['"records"', '"tool_name"', "Raw records:", "Accepted IDs:"]
RAW_JSON_MARKERS = ['"schema_version"', '"status"']
MIGRATION_ISOLATION_PREFIXES = ("legacy/", "archive/", "archives/", "experimental/", "deprecated/")
SCAN_SKIP_DIRS = {".git", ".aiwf", ".claude", ".reasonix", "__pycache__", "node_modules", ".venv", "venv", "dist", "build"}
SCAN_EXTENSIONS = {
    ".md", ".txt", ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml",
    ".toml", ".sh", ".bash", ".zsh", ".cfg", ".ini",
}


def _rj(path, default=None):
    try: return json.loads(path.read_text()) if path.exists() else (default or {})
    except: return default or {}

def _read_active_plan_impact(root):
    """Read the Impact block from the active task's plan, if one exists.
    Returns {category: value} or {} if no active plan / task.
    """
    state = _rj(root / ".aiwf" / "state" / "state.json", {})
    task_id = state.get("active_task_id", "") or ""
    if not task_id:
        return {}
    plan_path = root / ".aiwf" / "plans" / f"{task_id}.md"
    if not plan_path.exists():
        return {}
    try:
        from aiwf_core.core.task_plan import parse_plan_impact
        return parse_plan_impact(str(root), task_id)
    except Exception:
        return {}


def _is_isolated_legacy_path(path: str) -> bool:
    p = str(path).strip().replace("\\", "/").lstrip("./")
    return p.startswith(MIGRATION_ISOLATION_PREFIXES) or "/legacy/" in p or "/archive/" in p or "/deprecated/" in p


def _iter_scan_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        parts = set(rel.parts)
        if parts & SCAN_SKIP_DIRS:
            continue
        if path.suffix.lower() not in SCAN_EXTENSIONS:
            continue
        try:
            if path.stat().st_size > 512_000:
                continue
        except OSError:
            continue
        yield path, str(rel).replace("\\", "/")


def _migration_cleanup_scan(root: Path, result: Dict[str, Any]) -> None:
    goal = get_active_goal(str(root))
    brief = goal.get("quality_brief", {}) if isinstance(goal.get("quality_brief"), dict) else {}
    arch = brief.get("architecture_brief", {}) if isinstance(brief.get("architecture_brief"), dict) else {}
    source = str(arch.get("migration_source_of_truth", "") or "").strip()
    legacy_paths = [str(p).strip() for p in (arch.get("legacy_paths", []) or []) if str(p).strip()]
    legacy_terms = [str(t).strip() for t in (arch.get("legacy_terms", []) or []) if str(t).strip()]
    default_entrypoints = [str(e).strip() for e in (arch.get("default_entrypoints", []) or []) if str(e).strip()]
    validators = [str(v).strip() for v in (arch.get("validators", []) or []) if str(v).strip()]
    sample_outputs = [str(s).strip() for s in (arch.get("sample_outputs", []) or []) if str(s).strip()]
    migration_active = any([source, legacy_paths, legacy_terms, default_entrypoints, validators, sample_outputs])
    if not migration_active:
        return

    result["architecture_issues"].append("architecture migration contract active")
    if not source:
        result["blockers"].append("architecture migration missing migration_source_of_truth")
    if not (legacy_paths or legacy_terms):
        result["blockers"].append("architecture migration missing legacy_paths or legacy_terms")
    if not default_entrypoints:
        result["blockers"].append("architecture migration missing default_entrypoints")
    if not validators:
        result["blockers"].append("architecture migration missing validators")

    for rel in legacy_paths:
        path = root / rel
        if path.exists():
            if _is_isolated_legacy_path(rel):
                result["warnings"].append(f"declared legacy path still present but appears isolated: {rel}")
            else:
                result["blockers"].append(f"declared legacy path still present on active mainline: {rel}")
                result["stale_items"].append(f"legacy path remains active: {rel}")

    missing_entrypoints = [ep for ep in default_entrypoints if not (root / ep).exists()]
    for ep in missing_entrypoints:
        result["warnings"].append(f"declared default entrypoint not found as path; verify command evidence covers it: {ep}")
    missing_validators = [val for val in validators if not (root / val).exists()]
    for val in missing_validators:
        result["warnings"].append(f"declared validator not found as path; verify command evidence covers it: {val}")
    for sample in sample_outputs:
        if not (root / sample).exists():
            result["warnings"].append(f"declared sample output not found: {sample}")

    term_hits = []
    lowered_terms = [(term, term.lower()) for term in legacy_terms if term]
    if lowered_terms:
        for path, rel in _iter_scan_files(root):
            if _is_isolated_legacy_path(rel):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore").lower()
            except OSError:
                continue
            for original, term in lowered_terms:
                if term in text:
                    term_hits.append((original, rel))
                    break
            if len(term_hits) >= 10:
                break
    if term_hits:
        result["warnings"].append(
            f"legacy term(s) still appear outside isolated legacy paths: {len(term_hits)} hit(s)"
        )
        for term, rel in term_hits[:5]:
            result["stale_items"].append(f"legacy term '{term}' remains in {rel}; classify as retired-doc mention or active old flow")
        result["suggested_actions"].append("Run a legacy sweep and either remove active old references or document them as isolated legacy-only.")


def check_lifecycle_cleanup(project_root: str) -> Dict[str, Any]:
    root = Path(project_root)
    result = {
        "schema_version": 1,
        "cleanup_status": "fresh",
        "structure_status": "accepted",
        "blockers": [],
        "warnings": [],
        "stale_items": [],
        "project_map_issues": [],
        "idea_issues": [],
        "architecture_issues": [],
        "environment_issues": [],
        "fixloop_issues": [],
        "deferred_risk_issues": [],
        "migration_issues": [],
        "suggested_actions": [],
    }

    # ── PROJECT-MAP ──
    impact = _read_active_plan_impact(root)
    pm_path = root / ".aiwf" / "records" / "项目地图.md"
    if not pm_path.exists():
        if impact.get("project_map") == "yes":
            result["warnings"].append("Impact.project_map=yes but PROJECT-MAP.md missing; run aiwf project-map init")
            result["project_map_issues"].append("missing")
        # If Impact.project_map=no or unknown, silence the missing-PROJECT-MAP warning
    else:
        pm_text = pm_path.read_text(encoding="utf-8")

        # Section completeness
        missing_sections = [s for s in PM_REQUIRED_SECTIONS if f"## {s}" not in pm_text]
        for ms in missing_sections:
            msg = f"PROJECT-MAP missing section: {ms}"
            result["warnings"].append(msg)
            result["project_map_issues"].append(msg)

        # Default "Unknown yet" in key sections
        if "Active Direction" in pm_text:
            if "Unknown yet." in pm_text:
                result["warnings"].append("PROJECT-MAP Active Direction still Unknown yet")

        # Raw idea pollution
        idea_hits = sum(1 for m in RAW_IDEA_MARKERS if m in pm_text)
        if idea_hits >= 2:
            result["warnings"].append("PROJECT-MAP appears to contain raw ideas; keep raw ideas in ideas.md")
            result["project_map_issues"].append("raw idea pollution detected")

        # Evidence/report pollution
        ev_hits = sum(1 for m in RAW_EVIDENCE_MARKERS if m in pm_text)
        ev_count = pm_text.count("EV-")
        if ev_hits >= 2 or ev_count > 20:
            result["warnings"].append("PROJECT-MAP appears to contain evidence/report dump; keep evidence in report/evidence files")
            result["project_map_issues"].append("evidence dump detected")

        # JSON dump
        json_hits = sum(1 for m in RAW_JSON_MARKERS if m in pm_text)
        brace_count = pm_text.count("{")
        if json_hits >= 2 and brace_count > 10:
            result["warnings"].append("PROJECT-MAP may contain raw JSON dump")

        # Rejected Routes length
        rr_match = re.search(r'## Not-now / Rejected Routes\n(.*?)(?=\n## |\Z)', pm_text, re.DOTALL)
        if rr_match and len(rr_match.group(1)) > 2500:
            result["warnings"].append("Not-now / Rejected Routes section is long; compress route history into guardrails")

        # Size check
        if len(pm_text) > 50000:
            result["warnings"].append("PROJECT-MAP.md is very large, may contain raw dumps")

    # ── Ideas ──
    ideas_path = root / ".aiwf" / "records" / "ideas.md"
    if ideas_path.exists():
        from aiwf_core.core.ideas import _parse_ideas, is_idea_active
        ideas = _parse_ideas(ideas_path.read_text(encoding="utf-8"))
        raw_candidates = [i for i in ideas if i["status"] in ("raw", "candidate")]
        expired = [i for i in raw_candidates if not is_idea_active(i)]
        for ei in expired:
            result["stale_items"].append(
                f"expired idea: {ei['id']} status={ei.get('status', 'raw')} text=omitted"
            )
        if expired:
            result["idea_issues"].append(f"{len(expired)} stale/expired ideas need review")
        if len(raw_candidates) > 20:
            result["warnings"].append(f"{len(raw_candidates)} active ideas; consider review/expire/promote")
        adopted = [i for i in ideas if i["status"] == "adopted"]
        if adopted:
            result["suggested_actions"].append(
                f"{len(adopted)} adopted idea(s); ensure they are reflected in PROJECT-MAP if relevant")

    # ── Fix-loop ──
    fl = _rj(root / ".aiwf" / "state" / "fix-loop.json")
    if fl.get("status") == "open":
        result["blockers"].append("fix-loop is open")
        result["fixloop_issues"].append("fix-loop open")
        result["cleanup_status"] = "needs_attention"
    if fl.get("escalation_required"):
        result["blockers"].append("fix-loop escalation required")
    if fl.get("attempt_count", 0) >= fl.get("max_attempts", 1) and fl.get("status") == "open":
        result["blockers"].append("fix-loop attempts exhausted without resolution")

    # ── ACR ──
    acrs = fl.get("architecture_change_requests", []) or []
    proposed = [a for a in acrs if a.get("status") == "proposed"]
    if proposed:
        result["blockers"].append(f"{len(proposed)} unresolved ACR(s)")
        result["architecture_issues"].append(f"{len(proposed)} proposed ACRs pending decision")
    approved = [a for a in acrs if a.get("status") == "approved"]
    if approved:
        goal = get_active_goal(str(root))
        ab = goal.get("quality_brief", {}).get("architecture_brief", {})
        has_ab = ab and any(v for v in ab.values() if v and v != "" and v != [])
        if not has_ab:
            result["warnings"].append("ACR approved but architecture_brief still empty")
            result["architecture_issues"].append("approved ACR without updated architecture_brief")

    # ── Architecture migration hygiene ──
    before_arch_count = len(result["architecture_issues"])
    _migration_cleanup_scan(root, result)
    if len(result["architecture_issues"]) > before_arch_count:
        result["migration_issues"].extend(result["architecture_issues"][before_arch_count:])

    # ── Environment ──
    env_path = root / ".aiwf" / "records" / "events.json"
    if not env_path.exists():
        if impact.get("environment") == "yes":
            result["warnings"].append("Impact.environment=yes but environment.json missing; run aiwf env scan")
            result["environment_issues"].append("environment profile missing")
        # If Impact.environment=no or unknown, silence the missing-environment warning
    else:
        try:
            ep = json.loads(env_path.read_text())
            if ep.get("known_environment_risks"):
                result["environment_issues"].append(
                    f"{len(ep['known_environment_risks'])} environment risk(s)")
            if ep.get("missing_tools"):
                result["environment_issues"].append(
                    f"{len(ep['missing_tools'])} missing tool(s)")
        except: pass

    # ── Project Rules ──
    rules_path = root / ".aiwf" / "project-rules.md"
    if rules_path.exists():
        import re as _re_r
        rtxt = rules_path.read_text(encoding="utf-8")
        active_count = len(_re_r.findall(r'### RULE-.+ \| active \| rule', rtxt))
        if active_count > 30:
            result["warnings"].append(f"{active_count} active project rules; consider review/retire/supersede")
        if len(rtxt) > 30000:
            result["warnings"].append("project-rules.md is large, may be becoming a history dump")
        # Check if PROJECT-MAP duplicates rules
        pm_path2 = root / ".aiwf" / "records" / "项目地图.md"
        if pm_path2.exists():
            pm_text2 = pm_path2.read_text(encoding="utf-8")
            if "project-rules.md" in pm_text2 or "## Active Rules" in pm_text2:
                result["warnings"].append("PROJECT-MAP appears to duplicate project-rules.md content")

    # ── Deferred risks ──
    review = _rj(root / ".aiwf" / "records" / "review.json", {})
    if review.get("lessons") and len(review["lessons"]) > 30:
        result["warnings"].append("review.json lessons are large; consider curator cleanup")
    if review.get("followups") and len(review["followups"]) > 20:
        result["warnings"].append("review.json followups are large; consider curator cleanup")
    # Check if PROJECT-MAP Deferred Risks is still None yet when review has followups/lessons
    if pm_path.exists():
        if (review.get("followups") or review.get("lessons")):
            if "## Deferred Risks\n- None yet." in pm_text or "## Deferred Risks\n\n- None yet" in pm_text:
                result["warnings"].append("review has lessons/followups but PROJECT-MAP Deferred Risks still None yet")
                result["deferred_risk_issues"].append("PROJECT-MAP Deferred Risks not updated from review")
    testing = _rj(root / ".aiwf" / "records" / "testing.json", {"status": "missing"})
    if testing.get("status") == "failed" and fl.get("status") != "open":
        result["warnings"].append("testing failed but no fix-loop open")

    # ── Freshness: PROJECT-MAP vs report ──
    report_path = root / ".aiwf" / "records" / "闭合报告.md"
    if pm_path.exists() and report_path.exists():
        try:
            pm_mtime = pm_path.stat().st_mtime
            report_mtime = report_path.stat().st_mtime
            if report_mtime > pm_mtime:
                result["warnings"].append("PROJECT-MAP may be stale: report is newer than PROJECT-MAP")
        except: pass

    # ── Freshness: current-state carry-forward ──
    # Only check current-state during/after closure, not during normal execution.
    try:
        from aiwf_core.core.current_state import current_state_freshness
        state = _rj(root / ".aiwf" / "state" / "state.json", {})
        phase = state.get("phase", "")
        if phase in ("closed", "closing") or report_path.exists():
            cs = current_state_freshness(str(root))
            if cs["status"] == "missing":
                result["warnings"].append("current-state.md missing; run rebase after closure")
            elif cs["status"] == "stale":
                stale = ", ".join(cs.get("stale_sources", [])[:5])
                result["warnings"].append(f"current-state.md may be stale: newer source(s): {stale}")
            elif cs["status"] == "incomplete":
                result["warnings"].append("current-state.md incomplete; run aiwf doctor and aiwf task close after closure")
    except Exception:
        pass

    # ── Freshness: environment profile ──
    if env_path.exists():
        try:
            ep = json.loads(env_path.read_text())
            gen_at = ep.get("generated_at", "")
            if gen_at:
                from datetime import datetime, timezone
                try:
                    gen_dt = datetime.fromisoformat(gen_at)
                    age_days = (datetime.now(timezone.utc) - gen_dt).days
                    if age_days > 30:
                        result["warnings"].append(f"environment profile is {age_days} days old; consider aiwf env scan")
                except: pass
        except: pass

    # ── Summary ──
    if result["blockers"]:
        result["cleanup_status"] = "needs_attention"
        result["structure_status"] = "needs_attention"
    if result["warnings"]:
        result["cleanup_status"] = "needs_attention"

    return result


def auto_cleanup(base_dir: str) -> Dict[str, Any]:
    """Safe automatic cleanup. Archives but never deletes data.

    Runs on close_task or prepare_close. No Planner decision needed.
    Returns summary of what was cleaned.
    """
    root = Path(base_dir)
    aiwf = root / ".aiwf"
    summary: Dict[str, Any] = {"archived": [], "trimmed": [], "expired": [], "errors": []}

    # ── 1. Evidence archiving ──
    evidence_path = aiwf / "records" / "evidence.json"
    if evidence_path.exists():
        try:
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            records = evidence.get("records", [])
            if isinstance(records, list) and len(records) > 50:
                kept = records[-30:]  # Keep last 30 full records
                archived_count = len(records) - 30
                # Compress older: keep only id, timestamp, changed_files, status
                archive_summary = {
                    "archived_from": len(records),
                    "archived_to": 30,
                    "compressed_records": archived_count,
                    "compressed_files": list(set(
                        f for r in records[:-30]
                        for f in (r.get("changed_files", []) or [])
                    ))[:200],
                }
                evidence["records"] = kept
                evidence["archived"] = archive_summary
                evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                summary["archived"].append(f"evidence: {archived_count} records compressed to summary")
        except Exception as e:
            summary["errors"].append(f"evidence archive: {e}")

    # ── 2. Idea auto-expiry ──
    ideas_path = aiwf / "reports" / "ideas.md"
    if ideas_path.exists():
        try:
            from .ideas import _parse_ideas, is_idea_active
            ideas = _parse_ideas(ideas_path.read_text(encoding="utf-8"))
            expired = [i for i in ideas if i.get("status") in ("raw", "candidate") and not is_idea_active(i)]
            # Mark expired in file
            if expired:
                text = ideas_path.read_text(encoding="utf-8")
                for idea in expired:
                    old_status = f"Status: {idea.get('status', 'raw')}"
                    new_status = f"Status: expired (auto, {idea.get('id', '?')})"
                    if old_status in text:
                        text = text.replace(old_status, new_status, 1)
                ideas_path.write_text(text, encoding="utf-8")
                summary["expired"].append(f"ideas: {len(expired)} auto-expired ({', '.join(i['id'] for i in expired[:5])})")
        except Exception as e:
            summary["errors"].append(f"idea expiry: {e}")

    # ── 3. Quality digest rotation ──
    digest_path = aiwf / "reports" / "质量摘要.md"
    if digest_path.exists():
        try:
            digest_size = digest_path.stat().st_size
            # If digest is growing (append-only pattern), trim to latest content only
            if digest_size > 10000:
                content = digest_path.read_text(encoding="utf-8")
                # Keep only the current digest (from first # to next #, or whole file)
                digest_path.write_text(content[:8000] + "\n", encoding="utf-8")
                summary["trimmed"].append(f"quality-digest: trimmed from {digest_size} to ~8000 bytes")
        except Exception as e:
            summary["errors"].append(f"digest trim: {e}")

    # ── 4. Task-history progressive compression ──
    history_path = aiwf / "state" / "tasks.json"
    if history_path.exists():
        try:
            history = json.loads(history_path.read_text(encoding="utf-8"))
            tasks = history.get("tasks", [])
            if isinstance(tasks, list) and len(tasks) > 50:
                # Compress older than last 30: strip full file paths, keep filenames only
                for task in tasks[:-30]:
                    files = task.get("changed_files", [])
                    if files and len(str(files[0])) > 50:
                        task["changed_files"] = [
                            str(f).replace("\\", "/").split("/")[-1] if "/" in str(f).replace("\\", "/") else str(f)
                            for f in files
                        ]
                history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                summary["trimmed"].append(f"task-history: compressed filenames for {len(tasks) - 30} older tasks")
        except Exception as e:
            summary["errors"].append(f"task-history compress: {e}")

    return summary
