"""CLI route override commands for Complexity Routing V2-A.

aiwf route explain     — explain the current routing decision
aiwf route downgrade   — request a topology downgrade with recorded reason
aiwf route substitute  — request topology substitution with alternative verification
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_state(root: Path) -> dict:
    path = root / ".aiwf" / "state" / "state.json"
    if not path.exists():
        print("Error: no AIWF state found. Run aiwf init or aiwf install first.", file=sys.stderr)
        raise SystemExit(1)
    return json.loads(path.read_text(encoding="utf-8"))


def _write_state(root: Path, state: dict) -> None:
    path = root / ".aiwf" / "state" / "state.json"
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _cmd_route_explain(args: argparse.Namespace) -> None:
    """aiwf route explain — show the current routing decision with reasons."""
    root = Path.cwd()
    state = _read_state(root)

    from ..core.routing import explain_routing

    from ..core.routing import LEVEL_TO_TOPOLOGY

    level = state.get("workflow_level", "L1_review_light")
    # Build a decision-like dict from current state
    decision = {
        "workflow_level": level,
        "label": level,
        "execution_topology": LEVEL_TO_TOPOLOGY.get(level, "light_review"),
        "verification_need": state.get("verification_need", "standard"),
        "review_need": state.get("review_need", "optional_light_review"),
        "routing_factors": state.get("routing_factors", []),
        "routing_background_factors": state.get("routing_background_factors", []),
        "hard_upgrades": state.get("hard_constraints", []),
        "downgrade_allowed": state.get("downgrade_allowed", True),
        "substitution_allowed": state.get("substitution_allowed", False),
    }

    print(explain_routing(decision))

    # Show substitution history if any
    subs = state.get("substitution_records", []) or []
    if subs:
        print()
        print("Substitution history:")
        for s in subs[-5:]:
            print(f"  [{s.get('timestamp', '?')[:19]}] {s.get('from_topology', '?')} -> {s.get('to_topology', '?')}")
            print(f"    Reason: {s.get('reason', '?')[:120]}")


def _cmd_route_downgrade(args: argparse.Namespace) -> None:
    """aiwf route downgrade — request a topology downgrade with recorded reason."""
    root = Path.cwd()
    state = _read_state(root)

    from ..core.routing import LEVEL_TO_TOPOLOGY, TOPOLOGY_TO_LEVEL, compute_topology_override

    current_level = state.get("workflow_level", "L1_review_light")
    current_topo = LEVEL_TO_TOPOLOGY.get(current_level, "light_review")
    requested = args.to

    # Build factors from current state
    factors = {}
    for f in state.get("routing_factors", []):
        factors[f] = True
    hard = state.get("hard_constraints", []) or []

    result = compute_topology_override(
        current_topology=current_topo,
        requested_topology=requested,
        factors=factors,
        hard=hard,
        reason=args.reason,
    )

    if not result["allowed"]:
        print("Downgrade BLOCKED:")
        for w in result["warnings"]:
            print(f"  ! {w}")
        raise SystemExit(1)

    # Record the substitution
    record = {
        "timestamp": _now(),
        "from_topology": current_topo,
        "to_topology": result["effective_topology"],
        "from_level": current_level,
        "reason": args.reason,
        "substitute_verification": args.substitute or "",
        "type": "downgrade",
    }
    subs = state.setdefault("substitution_records", [])
    subs.append(record)

    # workflow_level is the canonical stored field — topology derives from it
    new_level = TOPOLOGY_TO_LEVEL.get(result["effective_topology"])
    old_level = current_level
    if new_level:
        state["workflow_level"] = new_level
    # Downgrades require explicit user confirmation — never silent
    if result.get("is_downgrade"):
        state["requires_user_decision"] = True
        state["quality_escalation_required"] = True
        state["quality_escalation_reason"] = (
            f"Workflow downgraded from {current_level} ({current_topo}) to "
            f"{new_level} ({result['effective_topology']}) "
            f"(reason: {args.reason[:120]})"
        )
    _write_state(root, state)

    print(f"Workflow downgraded: {current_level} ({current_topo}) -> {new_level} ({result['effective_topology']})")
    if state.get("requires_user_decision"):
        print("  USER DECISION REQUIRED — confirm or reject this downgrade")
    print(f"  Reason: {args.reason[:120]}")
    if args.substitute:
        print(f"  Substitute verification: {args.substitute[:120]}")
    if result["warnings"]:
        for w in result["warnings"]:
            print(f"  Note: {w}")


def _cmd_route_substitute(args: argparse.Namespace) -> None:
    """aiwf route substitute — waive a topology requirement with alternative verification."""
    root = Path.cwd()
    state = _read_state(root)

    from ..core.routing import LEVEL_TO_TOPOLOGY, TOPOLOGY_TO_LEVEL, compute_topology_override

    current_level = state.get("workflow_level", "L1_review_light")
    current_topo = LEVEL_TO_TOPOLOGY.get(current_level, "light_review")
    requested = args.use

    factors = {}
    for f in state.get("routing_factors", []):
        factors[f] = True
    hard = state.get("hard_constraints", []) or []

    result = compute_topology_override(
        current_topology=current_topo,
        requested_topology=requested,
        factors=factors,
        hard=hard,
        reason=args.reason,
    )

    if not result["allowed"]:
        print("Substitution BLOCKED:")
        for w in result["warnings"]:
            print(f"  ! {w}")
        raise SystemExit(1)

    # Record the substitution with alternative verification
    record = {
        "timestamp": _now(),
        "from_topology": current_topo,
        "to_topology": result["effective_topology"],
        "from_level": current_level,
        "reason": args.reason,
        "waived": args.waive or "",
        "substitute_verification": args.substitute or "",
        "type": "substitution",
    }
    subs = state.setdefault("substitution_records", [])
    subs.append(record)

    # workflow_level is canonical — topology derives from it
    new_level = TOPOLOGY_TO_LEVEL.get(result["effective_topology"])
    if new_level:
        state["workflow_level"] = new_level
    # Downgrades require explicit user confirmation
    if result.get("is_downgrade"):
        state["requires_user_decision"] = True
        state["quality_escalation_required"] = True
        state["quality_escalation_reason"] = (
            f"Workflow substituted from {current_level} ({current_topo}) to "
            f"{new_level} ({result['effective_topology']}) "
            f"(reason: {args.reason[:120]})"
        )
    if args.substitute:
        state["substitution_allowed"] = True
    _write_state(root, state)

    print(f"Workflow substituted: {current_level} ({current_topo}) -> {new_level} ({result['effective_topology']})")
    if state.get("requires_user_decision"):
        print("  USER DECISION REQUIRED — confirm or reject this substitution")
    print(f"  Reason: {args.reason[:120]}")
    if args.waive:
        print(f"  Waived: {args.waive}")
    if args.substitute:
        print(f"  Alternative verification: {args.substitute[:120]}")
    if result["warnings"]:
        for w in result["warnings"]:
            print(f"  Note: {w}")


def _cmd_route_help(args: argparse.Namespace) -> None:
    """aiwf route — show available routing subcommands."""
    print("AIWF Route Operations (V2-A)")
    print()
    print("Available subcommands:")
    print("  aiwf route explain       — explain the current routing decision")
    print("  aiwf route downgrade     — request a topology downgrade with recorded reason")
    print("  aiwf route substitute    — waive a topology requirement with alternative verification")
    print()
    print("Execution topologies (least to most intensive):")
    print("  single_agent                         — one agent, self-review ok")
    print("  single_agent_with_machine_evidence   — one agent + machine-verifiable commands")
    print("  light_review                         — executor + reviewer-light")
    print("  standard_team                        — executor + tester + reviewer")
    print("  fanout_merge                         — parallel agents + merge")
    print()
    print("Verification needs:")
    print("  deterministic   — machine-verifiable (neg/pos test, diff check)")
    print("  standard        — targeted + regression")
    print("  broad           — full regression + boundary + adverse")
    print("  adversarial     — full adversarial matrix")
