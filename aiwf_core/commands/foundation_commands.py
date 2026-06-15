"""Day-1 Foundation Tree CLI handlers — Stage 4.5.

Planner proposes → machine validates → human reviews → then manually create structure.
Validate only. Never auto-creates state."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def _cmd_foundation_validate(args: argparse.Namespace) -> None:
    from ..core.state.foundation_ops import validate_foundation_tree

    file_path = getattr(args, "file", "") or ""
    as_json = getattr(args, "json_output", False)
    foundation = {}

    if file_path:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                foundation = json.loads(f.read())
        except json.JSONDecodeError as e:
            print(f"Invalid JSON: {e}", file=sys.stderr)
            raise SystemExit(1)
        except FileNotFoundError:
            print(f"File not found: {file_path}", file=sys.stderr)
            raise SystemExit(1)
    else:
        try:
            foundation = json.loads(sys.stdin.read())
        except json.JSONDecodeError as e:
            print(f"Invalid JSON on stdin: {e}", file=sys.stderr)
            raise SystemExit(1)
        except Exception:
            print("No input provided. Pipe JSON or use --file.", file=sys.stderr)
            raise SystemExit(1)

    result = validate_foundation_tree(foundation)

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result["valid"]:
            raise SystemExit(1)
        return

    if not result["valid"]:
        print(f"Foundation Tree INVALID ({len(result['issues'])} issues):")
        for issue in result["issues"]:
            print(f"  ISSUE: {issue}")
        warnings = result.get("warnings", []) or []
        if warnings:
            for w in warnings:
                print(f"  WARN:  {w}")
        raise SystemExit(1)

    # ── Human-readable Foundation Proposal ──
    _print_human_foundation(foundation, result)


def _print_human_foundation(foundation: dict, result: dict) -> None:
    s = result.get("summary", {})

    print("Foundation Tree Proposal")
    print("=" * 25)
    print()

    # Root Goal
    root = foundation.get("root_goal") or {}
    print("Root Goal:")
    print(f"  {root.get('id', '')}: {root.get('title', '')}")
    if root.get("intent"):
        print(f"  {root['intent']}")
    print()

    # First-level Goals
    fl_goals = foundation.get("first_level_goals") or []
    print(f"First-level Goals ({s.get('first_level_count', 0)}):")
    for g in fl_goals:
        rel = g.get("relation_to_root", "")
        rel_tag = f" [{rel}]" if rel else ""
        print(f"  {g.get('id', '')}: {g.get('title', '')}{rel_tag}")
        if g.get("intent"):
            print(f"    {g['intent']}")
        _print_child_goals(g.get("child_goals"), indent=2)
    print()

    # Structural Plan
    sp = foundation.get("structural_plan") or {}
    print("Structural Plan:")
    print(f"  {sp.get('plan_id', '')}: {sp.get('purpose', '')}")
    print(f"  Target: {sp.get('target_goal_id', '')}")
    print(f"  Phase: {sp.get('active_phase', '')}")
    interfaces = sp.get("interfaces") or []
    if interfaces:
        print(f"  Interfaces ({len(interfaces)}):")
        for iface in interfaces:
            consumers = ", ".join(iface.get("consumers", []) or [])
            consumer_tag = f" → {consumers}" if consumers else ""
            print(f"    - {iface.get('owner', '')}: {iface.get('description', '')}{consumer_tag}")
    constraints = sp.get("constraints") or []
    if constraints:
        for c in constraints:
            print(f"    Constraint: {c}")
    print()

    # Active Path
    ap = foundation.get("active_path") or {}
    seq = ap.get("sequence") or []
    print(f"Active Path ({len(seq)} steps):")
    print(f"  {' → '.join(seq)}")
    if ap.get("reason"):
        print(f"  Why: {ap['reason']}")
    print()

    # Temporary Roots / Uncertain
    tmp_roots = foundation.get("temporary_roots") or []
    if tmp_roots:
        print(f"Uncertain Areas ({len(tmp_roots)}):")
        for tr in tmp_roots:
            print(f"  {tr.get('title', '')}")
            if tr.get("reason"):
                print(f"    Why: {tr['reason']}")
            if tr.get("resolution_criterion"):
                print(f"    Resolve when: {tr['resolution_criterion']}")
        print()

    # Evidence Rollup
    erp = foundation.get("evidence_rollup_policy") or {}
    if erp.get("task_to_plan") or erp.get("plan_to_goal"):
        print("Evidence Rollup:")
        if erp.get("task_to_plan"):
            print(f"  Task → Plan: {erp['task_to_plan']}")
        if erp.get("plan_to_goal"):
            print(f"  Plan → Goal: {erp['plan_to_goal']}")
        if erp.get("test_surface"):
            print(f"  Test surface: {erp['test_surface']}")
        print()

    # Initial Milestone
    ms = foundation.get("initial_milestone") or {}
    if ms and ms.get("title"):
        print("First Milestone:")
        print(f"  {ms.get('title', '')}")
        covers = ms.get("covers") or []
        if covers:
            print(f"  Covers: {', '.join(covers)}")
        ac = ms.get("acceptance_criteria") or []
        if ac:
            for i, c in enumerate(ac, 1):
                print(f"  {i}. {c}")
        print()

    # Warnings
    warnings = result.get("warnings", []) or []
    if warnings:
        print(f"Review Notes ({len(warnings)}):")
        for w in warnings:
            print(f"  - {w}")
        print()

    print("—")
    print("This is a proposal. Review, then create structure manually.")
    print("See docs/DAY1_FOUNDATION_TREE.md for the full design contract.")


def _print_child_goals(children: object, indent: int) -> None:
    if not isinstance(children, list):
        return
    prefix = "  " * indent
    detail_prefix = "  " * (indent + 1)
    for child in children:
        if not isinstance(child, dict):
            continue
        print(f"{prefix}└─ {child.get('id', '')}: {child.get('title', '')}")
        if child.get("intent"):
            print(f"{detail_prefix}{child['intent']}")
        rationale = child.get("hierarchy_rationale") or {}
        if isinstance(rationale, dict):
            composition = str(rationale.get("composition") or "").strip()
            ownership = str(rationale.get("primary_ownership") or "").strip()
            if composition:
                print(f"{detail_prefix}composition: {composition}")
            if ownership:
                print(f"{detail_prefix}primary ownership: {ownership}")
        _print_child_goals(child.get("child_goals"), indent + 1)
