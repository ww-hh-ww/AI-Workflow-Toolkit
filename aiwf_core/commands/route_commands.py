"""CLI route commands.

aiwf route explain   — show current routing decision
aiwf route override  — override routing level with recorded reason
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


def _count_prior_overrides(state: dict) -> int:
    records = state.get("substitution_records", []) or []
    overrides = 0
    for r in records:
        if not isinstance(r, dict):
            continue
        if not r.get("user_confirmed"):
            continue
        if r.get("status") != "confirmed":
            continue
        overrides += 1
    redemptions = state.get("routing_redemption_count", 0) or 0
    return max(0, overrides - redemptions)


def _cmd_route_explain(args: argparse.Namespace) -> None:
    root = Path.cwd()
    state = _read_state(root)
    from ..core.routing import explain_routing, LEVEL_TO_TOPOLOGY

    level = state.get("workflow_level", "L1_review_light")
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

    subs = state.get("substitution_records", []) or []
    if subs:
        print()
        print("Override history:")
        for s in subs[-5:]:
            print(f"  [{s.get('timestamp', '?')[:19]}] {s.get('from_topology', '?')} -> {s.get('to_topology', '?')}")
            print(f"    Reason: {s.get('reason', '?')[:120]}")


def _cmd_route_override(args: argparse.Namespace) -> None:
    root = Path.cwd()
    state = _read_state(root)
    from ..core.routing import LEVEL_TO_TOPOLOGY, TOPOLOGY_TO_LEVEL, compute_topology_override

    current_level = state.get("workflow_level", "L1_review_light")
    current_topo = LEVEL_TO_TOPOLOGY.get(current_level, "light_review")
    requested = args.to

    factors = {f: True for f in (state.get("routing_factors", []) or [])}
    hard = state.get("hard_constraints", []) or []
    prior_count = _count_prior_overrides(state)

    result = compute_topology_override(
        current_topology=current_topo,
        requested_topology=requested,
        factors=factors,
        hard=hard,
        reason=args.reason,
        downgrade_history_count=prior_count,
    )

    if not result["allowed"]:
        print("Override BLOCKED:")
        for w in result["warnings"]:
            print(f"  ! {w}")
        raise SystemExit(1)

    new_level = TOPOLOGY_TO_LEVEL.get(result["effective_topology"])
    pending = bool(result.get("is_downgrade") and not args.user_confirmed)

    record = {
        "timestamp": _now(),
        "from_topology": current_topo,
        "to_topology": result["effective_topology"],
        "from_level": current_level,
        "to_level": new_level or "",
        "task_id": args.task_id or "",
        "reason": args.reason,
        "user_confirmed": bool(args.user_confirmed),
        "status": "pending_user_confirmation" if pending else "confirmed",
        "type": "override",
    }
    subs = state.setdefault("substitution_records", [])
    subs.append(record)

    if pending:
        state["requires_user_decision"] = True
        state["quality_escalation_required"] = True
        state["quality_escalation_reason"] = (
            f"Route override requested from {current_level} ({current_topo}) to "
            f"{new_level} ({result['effective_topology']}) "
            f"(reason: {args.reason[:120]}); rerun with --user-confirmed to apply"
        )
    elif new_level:
        state["workflow_level"] = new_level
    _write_state(root, state)

    if pending:
        print(f"Route override pending: {current_level} ({current_topo}) -> {new_level} ({result['effective_topology']})")
        print(f"  Current: {current_level} ({current_topo})")
        print("  USER DECISION REQUIRED — rerun with --user-confirmed")
    else:
        print(f"Route overridden: {current_level} ({current_topo}) -> {new_level} ({result['effective_topology']})")
    if args.task_id:
        print(f"  Task: {args.task_id}")
    print(f"  Reason: {args.reason[:120]}")
    if result["warnings"]:
        for w in result["warnings"]:
            print(f"  Note: {w}")


def _cmd_route_help(args):
    print("Usage: aiwf route <explain|override>")
    print("  explain   — show current routing decision")
    print("  override  — override routing level with recorded reason")
