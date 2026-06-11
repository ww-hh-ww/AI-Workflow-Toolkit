"""CLI command handlers for AIWF embedded mainline."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..constants import VERSION

def _cmd_capability_scan(args: argparse.Namespace) -> None:
    """aiwf capability scan — discover external capabilities."""
    from ..core.capabilities import discover_capabilities, write_capabilities_registry
    reg = discover_capabilities(str(Path.cwd()))
    write_capabilities_registry(str(Path.cwd()), reg)
    caps = reg["capabilities"]
    kinds = {}
    risks = {}
    for cap in caps:
        kinds[cap["kind"]] = kinds.get(cap["kind"], 0) + 1
        risks[cap["risk"]] = risks.get(cap["risk"], 0) + 1
    ignored = reg.get("aiwf_internal_ignored", 0)
    print(f"Capability scan: {len(caps)} external found" + (f" ({ignored} AIWF internal ignored)" if ignored else ""))
    for k, v in sorted(kinds.items()): print(f"  {k}: {v}")
    if risks:
        print("Risk levels:")
        for r, v in sorted(risks.items()): print(f"  {r}: {v}")

def _cmd_capability_list(args: argparse.Namespace) -> None:
    """aiwf capability list — list discovered capabilities."""
    from ..core.capabilities import load_capabilities_registry
    reg = load_capabilities_registry(str(Path.cwd()))
    caps = reg.get("capabilities", [])
    if not caps:
        print("No capabilities registered. Run: aiwf capability scan")
        return
    for cap in caps:
        overlap = " overlap=aiwf" if cap.get("lifecycle_overlap") else ""
        print(
            f"{cap['id']}: {cap['kind']} type={cap.get('capability_type', 'unknown')} "
            f"risk={cap['risk']} policy={cap['use_policy']}{overlap}"
        )
        if cap.get("summary"): print(f"  {cap['summary'][:120]}")

def _cmd_capability_show(args: argparse.Namespace) -> None:
    """aiwf capability show ID — show one capability."""
    import json as _json
    from ..core.capabilities import load_capabilities_registry
    reg = load_capabilities_registry(str(Path.cwd()))
    for cap in reg.get("capabilities", []):
        if cap["id"] == args.id:
            safe = {k: v for k, v in cap.items() if k not in ("has_env",)}
            print(_json.dumps(safe, ensure_ascii=False, indent=2))
            if cap.get("has_env"): print("(has environment variables — values not stored)")
            return
    print(f"Capability not found: {args.id}")
    raise SystemExit(1)

def _cmd_capability_plan_use(args: argparse.Namespace) -> None:
    """aiwf capability plan-use ID — mark an external capability as intended for use."""
    from ..core.capabilities import mark_capability_planned, load_capabilities_registry
    reg = load_capabilities_registry(str(Path.cwd()))
    known = {c.get("id") for c in reg.get("capabilities", [])}
    if args.id not in known:
        print(f"Capability not found: {args.id}. Run: aiwf capability scan", file=sys.stderr)
        raise SystemExit(1)
    state = mark_capability_planned(str(Path.cwd()), args.id)
    print(f"Capability planned for use: {args.id}")
    print(f"  Planned capabilities: {len(state.get('planned_capability_ids', []) or [])}")

def _cmd_capability_decide(args: argparse.Namespace) -> None:
    """aiwf capability decide ID — record Planner decision for lifecycle-overlap capability."""
    from ..core.capabilities import record_capability_decision
    try:
        entry = record_capability_decision(str(Path.cwd()), args.id, args.decision, decided_by=args.decided_by)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Capability decision recorded: {entry['capability_id']}")
    print(f"  Decision: {entry['decision'][:160]}")

def _cmd_env_scan(args: argparse.Namespace) -> None:
    """aiwf env scan — scan project environment, write profile."""
    from ..core.environment import scan_environment, write_environment_profile
    profile = scan_environment(str(Path.cwd()))
    write_environment_profile(str(Path.cwd()), profile)
    print("Environment profile:")
    if profile["languages"]: print(f"  Languages:        {', '.join(profile['languages'])}")
    if profile["package_managers"]: print(f"  Package managers:  {', '.join(profile['package_managers'])}")
    if profile["test_commands"]: print(f"  Test commands:     {', '.join(profile['test_commands'][:3])}")
    if profile["build_commands"]: print(f"  Build commands:    {', '.join(profile['build_commands'][:3])}")
    if profile["missing_tools"]: print(f"  Missing tools:     {', '.join(profile['missing_tools'][:8])}")
    risks = profile.get("known_environment_risks", [])
    if risks: print(f"  Risks:             {len(risks)} item(s)")
    else: print("  Risks:             none")
    print(f"  Written to .aiwf/assets/environment.json")

def _cmd_env_show(args: argparse.Namespace) -> None:
    """aiwf env show — display environment profile."""
    from ..core.environment import load_environment_profile
    profile = load_environment_profile(str(Path.cwd()))
    if not profile:
        print("No environment profile found. Run: aiwf env scan")
        return
    print("Environment profile:")
    if profile.get("languages"): print(f"  Languages:        {', '.join(profile['languages'])}")
    if profile.get("package_managers"): print(f"  Package managers:  {', '.join(profile['package_managers'])}")
    if profile.get("test_commands"): print(f"  Test commands:     {', '.join(profile['test_commands'][:3])}")
    if profile.get("build_commands"): print(f"  Build commands:    {', '.join(profile['build_commands'][:3])}")
    if profile.get("missing_tools"): print(f"  Missing tools:     {', '.join(profile['missing_tools'][:8])}")
    risks = profile.get("known_environment_risks", [])
    if risks: print(f"  Risks:             {len(risks)} item(s)")
    else: print("  Risks:             none")

def _cmd_env_help(args: argparse.Namespace) -> None:
    """aiwf env — show available subcommands."""
    print("AIWF Environment Profile")
    print()
    print("Available subcommands:")
    print("  aiwf env scan  — scan project environment, write .aiwf/assets/environment.json")
    print("  aiwf env show  — display environment profile")

def _cmd_quality_surfaces(args: argparse.Namespace) -> None:
    """aiwf quality surfaces — list known quality surfaces."""
    from ..core.quality_surfaces import list_surfaces
    surfaces = list_surfaces()
    print("Quality surfaces:")
    for s in surfaces:
        print(f"  - {s}")

def _cmd_quality_surface(args: argparse.Namespace) -> None:
    """aiwf quality surface <name> — show test/review obligations."""
    from ..core.quality_surfaces import get_surface
    s = get_surface(args.name)
    if not s:
        print(f"Error: unknown surface type: {args.name}", file=sys.stderr)
        raise SystemExit(1)
    print(f"## {s['label']} ({args.name})")
    print()
    if s.get("test_obligations"):
        print("Test obligations:")
        for t in s["test_obligations"]:
            print(f"  - {t}")
    if s.get("review_obligations"):
        print()
        print("Review obligations:")
        for r in s["review_obligations"]:
            print(f"  - {r}")

def _cmd_quality_digest(args: argparse.Namespace) -> None:
    """aiwf quality digest — refresh and show cross-task quality digest."""
    cwd = Path.cwd()
    state = json.loads((cwd / ".aiwf" / "state" / "state.json").read_text(encoding="utf-8")) if (cwd / ".aiwf" / "state" / "state.json").exists() else {}

    # Impact guard: only write quality digest when Impact.quality_summary=yes
    task_id = state.get("active_task_id") or state.get("active_plan_id") or ""
    if task_id:
        from ..core.task_plan import parse_plan_impact
        impact = parse_plan_impact(str(cwd), task_id)
        if impact.get("quality_summary") != "yes" and not getattr(args, "force", False):
            print(
                f"Quality digest blocked: Impact.quality_summary is not 'yes' for {task_id}.\n"
                f"  Impact.quality_summary={impact.get('quality_summary', 'not set')}\n"
                f"  Use --force to bypass this guard, or set quality_summary: yes in the plan Impact section.",
                file=sys.stderr,
            )
            raise SystemExit(1)

    from ..core.cross_task_quality import evaluate_cross_task_quality, write_quality_digest
    path = write_quality_digest(str(cwd))
    result = evaluate_cross_task_quality(str(cwd))
    print(f"Quality digest written: {path.relative_to(cwd)}")
    print(f"  Recent tasks: {result['recent_task_count']}")
    print(f"  Signals: {len(result['signals'])}")
    for sig in result["signals"][:5]:
        print(f"    - {sig['severity']} / {sig['kind']}: {sig['message']}")

def _cmd_quality_help(args: argparse.Namespace) -> None:
    """aiwf quality — show available subcommands."""
    print("AIWF Quality Surfaces")
    print()
    print("Available subcommands:")
    print("  aiwf quality surfaces       — list known surfaces")
    print("  aiwf quality surface <name> — show obligations for a surface")
    print("  aiwf quality digest         — refresh cross-task quality digest")

def _cmd_workspace_scan(args: argparse.Namespace) -> None:
    """aiwf workspace scan — detect workspace drift."""
    from ..core.workspace_drift import scan_workspace_drift, write_workspace_drift, auto_update_baseline
    drift = scan_workspace_drift(str(Path.cwd()))
    write_workspace_drift(str(Path.cwd()), drift)
    print(f"Workspace drift scan:")
    print(f"  Git repo: {drift.get('is_git_repo', False)}")
    print(f"  Dirty: {drift.get('dirty', False)}")
    print(f"  Project changes: {len(drift.get('project_changes', []))}")
    print(f"  Governance/support changes: {len(drift.get('governance_changes', []))}")
    print(f"  Untracked: {len(drift.get('untracked', []))}")
    print(f"  Needs planner review: {drift.get('needs_planner_review', False)}")
    if drift.get('project_changes'):
        for ch in drift['project_changes'][:10]:
            print(f"    project: {ch['path']} ({ch['status']})")
    # Auto-update baseline on structural changes (new/deleted files)
    if drift.get('project_changes') or drift.get('untracked'):
        result = auto_update_baseline(str(Path.cwd()))
        if result.get('updated'):
            print(f"  Baseline: auto-updated ({result['updated']})")
