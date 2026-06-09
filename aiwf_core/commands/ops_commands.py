"""CLI command handlers for AIWF embedded mainline."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..constants import VERSION

def _cmd_fix_loop_open(args: argparse.Namespace) -> None:
    """aiwf fix-loop open — open a fix-loop with route and required fixes."""
    from ..core.state_ops import open_fix_loop
    result = open_fix_loop(
        str(Path.cwd()),
        route=args.route,
        reason=args.reason,
        required_fixes=args.required_fixes or None,
        required_verification=args.required_verification or None,
        source=args.source or "reviewer",
    )
    print(f"Fix-loop opened: status={result['status']}")
    print(f"  Route: {args.route}")
    print(f"  Reason: {args.reason[:160]}")
    if args.required_fixes: print(f"  Required fixes: {len(args.required_fixes)}")
    if args.required_verification: print(f"  Required verification: {len(args.required_verification)}")
    print("  Fixes are NOT auto-executed. Route to the appropriate agent.")

def _cmd_fix_loop_resolve(args: argparse.Namespace) -> None:
    """aiwf fix-loop resolve — resolve a fix-loop. Does NOT auto-close workflow."""
    from ..core.state_ops import resolve_fix_loop
    try:
        result = resolve_fix_loop(
            str(Path.cwd()),
            resolution=args.resolution,
            source=args.source or "reviewer",
            force=bool(getattr(args, 'force', False)),
        )
    except ValueError as e:
        print(f"Fix-loop resolution blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Fix-loop resolved: status={result['status']}")
    print(f"  Resolution: {args.resolution[:160]}")
    print("  Fix-loop resolved. Does NOT auto-close workflow.")

def _cmd_fix_loop_status(args: argparse.Namespace) -> None:
    """aiwf fixloop status — show fix-loop status."""
    from ..core.state_ops import _read
    from pathlib import Path as _P
    fl = _read(_P(str(Path.cwd())) / ".aiwf" / "state" / "fix-loop.json")
    print("Fix-loop:")
    print(f"  Status:             {fl.get('status', 'none')}")
    print(f"  Route:              {fl.get('route', '?') or 'none'}")
    print(f"  Attempt:            {fl.get('attempt_count', 0)} / {fl.get('max_attempts', '?')}")
    print(f"  Escalation required:{'yes' if fl.get('escalation_required') else 'no'}")
    print(f"  Rollback recommended:{'yes' if fl.get('rollback_recommended') else 'no'}")
    if fl.get("reason"): print(f"  Reason:             {fl['reason'][:160]}")
    if fl.get("required_fixes"):
        print("  Required fixes:")
        for rf in fl["required_fixes"][:10]: print(f"    - {rf[:160]}")
    if fl.get("required_verification"):
        print("  Required verification:")
        for rv in fl["required_verification"][:10]: print(f"    - {rv[:160]}")
    if fl.get("route_history"):
        print("  Route history:")
        for rh in fl["route_history"][:10]:
            print(f"    - attempt {rh.get('attempt','?')}: {rh.get('route','?')} ({rh.get('reason','')[:80]})")

def _cmd_fix_loop_help(args: argparse.Namespace) -> None:
    """aiwf fix-loop — show available subcommands."""
    print("AIWF Fix-Loop")
    print()
    print("Available subcommands:")
    print("  aiwf fixloop open     — open a fix-loop with route and required fixes")
    print("  aiwf fixloop resolve  — resolve a fix-loop (does NOT auto-close)")
    print("  aiwf fixloop status   — show fix-loop status")

def _cmd_arch_change_request(args: argparse.Namespace) -> None:
    """aiwf arch-change request — append an architecture change request."""
    from ..core.state_ops import request_architecture_change
    acr = request_architecture_change(
        str(Path.cwd()),
        source=args.source,
        reason=args.reason,
        proposed_change=args.proposed_change,
        affected_files=args.affected_files or None,
        affected_modules=args.affected_modules or None,
        current_contract_gap=args.current_contract_gap or "",
        scope_impact=args.scope_impact or "",
        risk=args.risk or "",
        user_decision_required=args.user_decision_required,
    )
    print(f"Architecture change requested: {acr['id']} (proposed)")
    print(f"  Source: {acr['source']}")
    print(f"  Reason: {acr['reason'][:120]}")
    if acr.get("affected_files"): print(f"  Files: {', '.join(acr['affected_files'][:5])}")
    print("  Does NOT modify architecture_brief or context. Planner must decide.")

def _cmd_arch_change_list(args: argparse.Namespace) -> None:
    """aiwf arch-change list — list architecture change requests."""
    from ..core.state_ops import list_architecture_changes
    acrs = list_architecture_changes(str(Path.cwd()))
    if not acrs:
        print("Architecture change requests: none")
        return
    print(f"Architecture change requests: {len(acrs)}")
    for a in acrs:
        print(f"  {a.get('id','?')}: {a.get('status','?')} / {a.get('source','?')}")
        reason = a.get('reason', '')
        if reason: print(f"    {reason[:80]}")

def _cmd_arch_change_decide(args: argparse.Namespace) -> None:
    """aiwf arch-change decide — approve/reject/supersede an ACR."""
    from ..core.state_ops import decide_architecture_change
    try:
        result = decide_architecture_change(
            str(Path.cwd()),
            acr_id=args.id,
            status=args.status,
            decision=args.decision,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Architecture change {args.id}: {result['status']}")
    print(f"  Decision: {args.decision[:160]}")
    print("  Does NOT auto-modify architecture_brief or context. Update them explicitly.")

def _cmd_arch_change_help(args: argparse.Namespace) -> None:
    """aiwf arch-change — show available subcommands."""
    print("AIWF Architecture Change Requests")
    print()
    print("Available subcommands:")
    print("  aiwf arch-change request  — request an architecture change")
    print("  aiwf arch-change list     — list requests")
    print("  aiwf arch-change decide   — approve/reject/supersede a request")

def _cmd_git_summary(args: argparse.Namespace) -> None:
    from ..core.git_ops import get_git_summary
    s = get_git_summary(str(Path.cwd()))
    ckpt_exists = (Path.cwd()/".aiwf"/"checkpoints").exists() and any((Path.cwd()/".aiwf"/"checkpoints").iterdir())
    state = {}
    try: state = __import__('json').loads((Path.cwd()/".aiwf" / "state" / "state.json").read_text())
    except: pass
    print(f"Git Summary:")
    print(f"  Branch: {s.get('branch','?')}")
    print(f"  HEAD: {s.get('head','')[:8]}")
    print(f"  Dirty: {s['dirty']}")
    print(f"  Project changes: {s['project_changes']}")
    print(f"  Governance changes: {s['governance_changes']}")
    print(f"  Untracked: {s['untracked']}")
    print(f"  Checkpoint: {'available' if ckpt_exists else 'none'}")
    print(f"  Closure: {'allowed' if state.get('closure_allowed') else 'blocked' if state.get('close_attempt') else 'not attempted'}")

def _cmd_git_suggest(args: argparse.Namespace) -> None:
    from ..core.git_ops import suggest_commit_message
    print(f"Suggested commit: {suggest_commit_message(str(Path.cwd()))}")

def _cmd_git_commit(args: argparse.Namespace) -> None:
    from ..core.git_ops import commit_with_confirmation
    result = commit_with_confirmation(str(Path.cwd()), args.message,
                                       include_governance=args.include_governance,
                                       confirm=args.confirm)
    if result.get("error"): print(f"Error: {result['error']}"); raise SystemExit(1)
    if result.get("status") == "rejected": print(result.get("reason", "rejected"))
    elif result.get("status") == "committed": print(f"Committed: {result['hash']}")

def _cmd_checkpoint_create(args: argparse.Namespace) -> None:
    from ..core.checkpoints import create_checkpoint
    ck = create_checkpoint(str(Path.cwd()), label=args.label, include_governance=args.include_gov, mode=args.mode)
    print(f"Checkpoint created: {ck['id']}")
    if ck.get('label'): print(f"  Label: {ck['label']}")
    print(f"  Git HEAD: {ck['git_head'][:8]}")
    print(f"  Project files: {ck['project_files']}")
    print(f"  Governance files: {ck['governance_files']}")
    print(f"  Untracked: {ck['untracked_files']}")
    if ck.get('warnings'):
        for w in ck['warnings'][:3]: print(f"  Warning: {w}")

def _cmd_checkpoint_list(args: argparse.Namespace) -> None:
    from ..core.checkpoints import list_checkpoints
    cks = list_checkpoints(str(Path.cwd()))
    if not cks: print("No checkpoints."); return
    for ck in cks:
                print(ck["id"] + ": " + ck.get("label","")[:40] + " provider=" + ck.get("provider","patch") + " mode=" + ck.get("mode","patch") + " head=" + ck["git_head"][:8] + " dirty=" + str(ck["dirty"]) + " proj=" + str(ck["project_files"]))

def _cmd_checkpoint_show(args: argparse.Namespace) -> None:
    from ..core.checkpoints import show_checkpoint
    import json as _json
    ck = show_checkpoint(str(Path.cwd()), args.id)
    if not ck: print(f"Not found: {args.id}"); raise SystemExit(1)
    safe = {k:v for k,v in ck.items() if k not in ('project_file_list','governance_file_list')}
    print(_json.dumps(safe, ensure_ascii=False, indent=2))

def _cmd_checkpoint_restore_plan(args: argparse.Namespace) -> None:
    root = Path.cwd()
    plan = root/".aiwf"/"checkpoints"/args.id/"restore-plan.md"
    if plan.exists(): print(plan.read_text())
    else: print(f"No restore plan for {args.id}")

def _cmd_checkpoint_restore(args: argparse.Namespace) -> None:
    from ..core.checkpoints import restore_checkpoint
    result = restore_checkpoint(str(Path.cwd()), args.id, confirm=args.confirm)
    if result.get("error"): print(f"Error: {result['error']}"); raise SystemExit(1)
    if result.get("status") == "dry_run": print(result.get("message", "use --confirm"))
    elif result.get("status") == "restored": print(f"Restored to {result['checkpoint']} (pre-backup: {result.get('pre_restore_backup','')})")

def _cmd_install(args: argparse.Namespace) -> None:
    """aiwf install <target> — create embedded integration files."""
    from ..install_claude import TARGETS, install_embedded
    mode = getattr(args, "mode", "claude")
    target = TARGETS[mode]
    results = install_embedded(mode, force=getattr(args, "force", False))
    print(f"# AIWF V{VERSION} — {target.product_name} Integration Installed")
    print()
    if results["created"]:
        print(f"Created ({len(results['created'])}):")
        for p in results["created"]:
            print(f"  + {p}")
    if results["updated"]:
        print(f"Updated ({len(results['updated'])}):")
        for p in results["updated"]:
            print(f"  ~ {p}")
    print()
    print("Next steps:")
    print(f"  1. Start {target.product_name}: {target.command_name}")
    planner_command = target.planner_command.replace('"describe your goal"', '"I want to implement a feature. Let\'s discuss first."')
    print(f"  2. Talk to planner: {planner_command}")
    print("  3. Keep using planner as the main interface; it directs implement/test/review/close capabilities")
    print("  4. Run: aiwf doctor    (to verify installation health)")

def _cmd_doctor(args: argparse.Namespace) -> None:
    """aiwf doctor — check AIWF embedded installation health."""
    from ..install_claude import doctor
    import json as _json
    results = doctor()
    overall = results["overall"]
    product = results.get("product_name", "embedded")
    config_dir = results.get("config_dir", ".claude")
    instruction_file = results.get("instruction_file", "CLAUDE.md")
    print(f"# AIWF Doctor — {product} — {overall}")
    print()

    def _icon(ok: bool) -> str:
        return "✓" if ok else "✗"

    print(f"{_icon(results['instruction_md'])} {instruction_file}")
    print(f"{_icon(results['settings_json'])} {config_dir}/settings.json")
    print()

    print("Skills:")
    for name, info in results["skills"].items():
        fm_ok = info.get("has_frontmatter", False)
        print(f"  {_icon(info['exists'])} {name}  {'[frontmatter]' if fm_ok else '[MISSING frontmatter]' if info['exists'] else '[MISSING]'}")

    print()
    print("Agents:")
    for name, info in results["agents"].items():
        print(f"  {_icon(info['exists'])} {name}")

    print()
    print("Hooks (in settings.json):")
    for name, info in results["hooks"].items():
        configured = info.get("configured", False)
        valid = info.get("valid_schema", False)
        status = "[valid schema]" if valid else "[INVALID schema]" if configured else "[MISSING]"
        print(f"  {_icon(configured)} {name}  {status}")

    print()
    print("State files:")
    for name, ok in results["state_files"].items():
        print(f"  {_icon(ok)} .aiwf/{name}")

    print()
    print("Scripts:")
    for name, info in results["scripts"].items():
        print(f"  {_icon(info['exists'])} scripts/{name}  {'[executable]' if info.get('executable') else ''}")

    print()
    if overall == "healthy":
        print("✓ All checks passed. AIWF is ready.")
    else:
        print(f"✗ Some checks failed. Run: aiwf install {results.get('mode', 'claude')} --force    to fix.")

def _cmd_export_report(args: argparse.Namespace) -> None:
    """aiwf export-report — generate AIWF summary report."""
    import subprocess
    script = Path.cwd() / "scripts" / "aiwf_export_report.py"
    if script.exists():
        subprocess.run([sys.executable, str(script)], check=False)
    else:
        print("scripts/aiwf_export_report.py not found. Run: aiwf install claude")
        raise SystemExit(1)
