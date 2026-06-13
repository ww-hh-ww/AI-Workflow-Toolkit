"""Execution Frontier CLI handlers — Stage 4.7 Semantic Frontier + Work Packet.

Planner decides frontier semantically.
AIWF validates frontier structurally.
AIWF prepares Work Packet.
No automatic scheduling. No automatic execution.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def _cmd_frontier_validate(args: argparse.Namespace) -> None:
    from ..core.frontier_ops import validate_frontier_decision

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
        try:
            decision = json.loads(sys.stdin.read())
        except json.JSONDecodeError as e:
            print(f"Invalid JSON on stdin: {e}", file=sys.stderr)
            raise SystemExit(1)
        except Exception:
            print("No input provided. Pipe a JSON decision or use --file.", file=sys.stderr)
            raise SystemExit(1)

    result = validate_frontier_decision(str(Path.cwd()), decision)

    if result["valid"]:
        print(f"Frontier valid: {decision.get('frontier_type', '')}")
    else:
        print(f"Frontier INVALID ({len(result['issues'])} issues):")
        for issue in result["issues"]:
            print(f"  ISSUE: {issue}")

    if result.get("warnings"):
        for w in result["warnings"]:
            print(f"  WARNING: {w}")

    if not result["valid"]:
        raise SystemExit(1)


def _cmd_frontier_prepare(args: argparse.Namespace) -> None:
    from ..core.frontier_ops import prepare_work_packet

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

    result = prepare_work_packet(str(Path.cwd()), decision)

    if as_json:
        print(json.dumps(result["agent_work_packet"], ensure_ascii=False, indent=2))
        if not result["valid"]:
            raise SystemExit(1)
        return

    if not result["valid"]:
        issues = result.get("validation_issues", []) or []
        print(f"Frontier INVALID ({len(issues)} issues):")
        for issue in issues:
            print(f"  {issue}")
        raise SystemExit(1)

    # Default: human-readable Work Packet
    human = result.get("human_work_packet", {})
    text = human.get("text", "")
    if text:
        print(text)


def _cmd_frontier_help(args: argparse.Namespace) -> None:
    print("AIWF Execution Frontier — Semantic Dispatch + Work Packet (Stage 4.7)")
    print()
    print("Planner decides frontier semantically.")
    print("AIWF validates frontier structurally.")
    print("AIWF prepares Work Packet.")
    print("Agents consume Work Packet.")
    print("No automatic scheduling. No automatic execution.")
    print()
    print("Commands:")
    print()
    print("  aiwf frontier validate --file frontier.json")
    print("    Validate a Frontier Decision JSON (structural checks only).")
    print()
    print("  aiwf frontier prepare --file frontier.json")
    print("    Validate and prepare a human-readable Work Packet Proposal.")
    print()
    print("  aiwf frontier prepare --file frontier.json --json")
    print("    Output the Agent Work Packet as JSON.")
    print()
    print("Frontier types:")
    print("  execute_plan       — implement within a Plan")
    print("  verify_plan        — test/verify a Plan's outputs")
    print("  review_plan        — review a Plan's work")
    print("  integrate_goal     — integrate child Goals/Plans under a parent Goal")
    print("  architect_structure — design structure, interfaces, boundaries")
    print("  explore_temporary_root — exploratory/spike work")
    print()
    print("See docs/EXECUTION_FRONTIER.md for the full design contract.")
