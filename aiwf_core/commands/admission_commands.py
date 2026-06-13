"""Change Admission CLI handlers — Stage 4.2 Semantic Admission Protocol.

Two modes:
1. aiwf change admit --summary "..."   → heuristic fallback (non-authoritative)
2. aiwf change validate-decision ...  → machine validation of Admission Decision JSON
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def _cmd_change_admit(args: argparse.Namespace) -> None:
    from ..core.state.admission_ops import admit_change

    summary = args.summary or ""
    result = admit_change(
        str(Path.cwd()),
        summary=summary,
        target_goal_hint=args.target_goal or "",
    )

    if result["admission"] == "unknown":
        print(f"Change admission: {result['reason']}", file=sys.stderr)
        raise SystemExit(1)

    print("WARNING: Heuristic recommendation only. Do not treat as authoritative.")
    print(f"Use 'aiwf change validate-decision' with an Admission Decision JSON for the authoritative check.")
    print()

    print(f"Recommended admission: {result['admission']}")
    if result.get("target_goal_id"):
        goal_info = result["target_goal_id"]
        if result.get("target_goal_title"):
            goal_info += f" ({result['target_goal_title']})"
        print(f"Target Goal: {goal_info}")
    print(f"Plan Kind: {result.get('plan_kind', '') or '(none — temporary root)'}")
    print(f"Reason: {result['reason']}")
    print(f"Impact: {result['impact']}")
    print(f"Confidence: {result['confidence']}")

    notes = result.get("notes", []) or []
    # Strip the "heuristic only" note from the first position (added by admit_change)
    display_notes = [n for n in notes if "Heuristic recommendation only" not in n]
    if display_notes:
        print()
        print("Notes:")
        for note in display_notes:
            print(f"  - {note}")

    # Shell commands are hidden by default — humans should NOT see raw commands.
    # Only show in --debug mode.
    if args.debug:
        print(f"Signals detected: {', '.join(result.get('signals_found', []) or [])}")
        next_cmds = result.get("next_commands", []) or []
        if next_cmds:
            print()
            print("Next (debug only):")
            for cmd in next_cmds:
                print(f"  {cmd}")

    print()
    print("Use 'aiwf change validate-decision' + 'aiwf change prepare' for the authoritative path.")


def _cmd_change_validate_decision(args: argparse.Namespace) -> None:
    from ..core.state.admission_ops import validate_admission_decision

    file_path = getattr(args, "file", "") or ""
    decision = {}

    if file_path:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                decision = json.loads(f.read())
        except json.JSONDecodeError as e:
            print(f"Invalid JSON: {e}", file=sys.stderr)
            raise SystemExit(1)
        except FileNotFoundError:
            print(f"File not found: {file_path}", file=sys.stderr)
            raise SystemExit(1)
    else:
        # Read from stdin
        try:
            decision = json.loads(sys.stdin.read())
        except json.JSONDecodeError as e:
            print(f"Invalid JSON on stdin: {e}", file=sys.stderr)
            raise SystemExit(1)
        except Exception:
            print("No input provided. Pipe a JSON decision or use --file.", file=sys.stderr)
            raise SystemExit(1)

    result = validate_admission_decision(str(Path.cwd()), decision)

    if result["valid"]:
        print(f"Decision valid: {result['admission_type']}")
    else:
        print(f"Decision INVALID ({len(result['issues'])} issues):")
        for issue in result["issues"]:
            print(f"  ISSUE: {issue}")

    if result.get("warnings"):
        print(f"  Warnings ({len(result['warnings'])}):")
        for w in result["warnings"]:
            print(f"    {w}")

    if not result["valid"]:
        raise SystemExit(1)


def _cmd_change_prepare(args: argparse.Namespace) -> None:
    from ..core.state.admission_ops import prepare_action_plan

    file_path = getattr(args, "file", "") or ""
    as_json = getattr(args, "json_output", False)
    decision = {}

    if file_path:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                decision = json.loads(f.read())
        except json.JSONDecodeError as e:
            print(f"Invalid JSON: {e}", file=sys.stderr)
            raise SystemExit(1)
        except FileNotFoundError:
            print(f"File not found: {file_path}", file=sys.stderr)
            raise SystemExit(1)
    else:
        try:
            decision = json.loads(sys.stdin.read())
        except json.JSONDecodeError as e:
            print(f"Invalid JSON on stdin: {e}", file=sys.stderr)
            raise SystemExit(1)
        except Exception:
            print("No input provided. Pipe a JSON decision or use --file.", file=sys.stderr)
            raise SystemExit(1)

    result = prepare_action_plan(str(Path.cwd()), decision)

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result["valid"]:
            raise SystemExit(1)
        return

    if not result["valid"]:
        issues = result.get("validation_issues", []) or []
        print(f"Decision INVALID ({len(issues)} issues):")
        for issue in issues:
            print(f"  {issue}")
        raise SystemExit(1)

    human = result.get("human_action_plan") or {}
    ops = result.get("operation_plan") or {}
    warnings = result.get("warnings", []) or []

    # ── Human-readable Action Plan ──
    print("Change Action Plan")
    print("=" * 18)
    print()
    print(f"Entry: {human.get('title', '')}")
    print()

    if human.get("target_goal_id"):
        goal_label = human["target_goal_id"]
        if human.get("target_goal_title"):
            goal_label += f" ({human['target_goal_title']})"
        print(f"Target Goal: {goal_label}")

    if human.get("target_parent_goal_id"):
        parent_label = human["target_parent_goal_id"]
        if human.get("target_parent_goal_title"):
            parent_label += f" ({human['target_parent_goal_title']})"
        print(f"Target Parent Goal: {parent_label}")

    if human.get("new_goal_title"):
        print(f"New Goal: {human['new_goal_title']}")

    if human.get("action_granularity"):
        glabel = human.get("granularity_label", human["action_granularity"])
        gsummary = human.get("granularity_summary", "")
        print(f"Granularity: {human['action_granularity']} — {glabel}")
        print(f"  {gsummary}")
        if human.get("target_plan_id"):
            print(f"  Existing Plan: {human['target_plan_id']}")

    if human.get("plan_kind"):
        print(f"Plan Kind: {human['plan_kind']}")
        if human.get("plan_kind_label"):
            print(f"  {human['plan_kind_label']}")

    if human.get("active_phase"):
        print(f"Active Phase: {human['active_phase']}")
        if human.get("active_phase_label"):
            print(f"  {human['active_phase_label']}")

    if human.get("interface_consumed"):
        print(f"Interface Consumed: {human['interface_consumed']}")
    if human.get("capability_provided"):
        print(f"Capability Provided: {human['capability_provided']}")
    if human.get("relation_to_parent"):
        print(f"Relation to Parent: {human['relation_to_parent']}")

    print()
    print("Why:")
    print(f"  {human.get('reason', '')}")

    if human.get("impact_notes"):
        print()
        print(f"Impact: {human['impact_notes']}")

    print()
    print("Risk:")

    risks = human.get("risks", []) or []
    for r in risks:
        print(f"  - {r}")

    print()
    print(f"Human Check: {'Required' if human.get('requires_confirmation') else 'Not required.'}")

    if human.get("next_review_focus"):
        print()
        print(f"Next Review: {human['next_review_focus']}")

    if warnings:
        print()
        print("Warnings:")
        for w in warnings:
            print(f"  - {w}")

    print()
    print("—")
    print("This Action Plan is advisory. Review before creating any structure.")


def _cmd_change_help(args: argparse.Namespace) -> None:
    print("AIWF Change Admission — Semantic Admission Protocol (Stage 4.3)")
    print()
    print("Three modes:")
    print()
    print("  1. Heuristic fallback (non-authoritative):")
    print("     aiwf change admit --summary \"one-line description\"")
    print()
    print("  2. Machine validation (authoritative):")
    print("     aiwf change validate-decision --file admission.json")
    print()
    print("  3. Prepare Action Plan (Stage 4.3):")
    print("     aiwf change prepare --file admission.json")
    print("     aiwf change prepare --file admission.json --json")
    print()
    print("Admission Protocol:")
    print("  1. Planner reads user request")
    print("  2. Planner produces an Admission Decision (JSON)")
    print("  3. Validate: aiwf change validate-decision --file admission.json")
    print("  4. Prepare: aiwf change prepare --file admission.json")
    print("  5. Review the Action Plan, confirm, then create structure manually")
    print()
    print("The Action Plan shows the entry path, risks, and review focus — not shell commands.")
    print()
    print("See docs/CHANGE_ADMISSION.md for the full design contract.")
