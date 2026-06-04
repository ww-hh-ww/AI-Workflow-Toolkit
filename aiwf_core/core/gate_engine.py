"""Backend-neutral gate engine.

Evaluates all AIWF gates using state, evidence, testing, review, fix-loop.
Returns structured results that adapters can format for their engine.
No Claude-specific logic.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .closure_contract import closure_conditions_met
from .event_model import StatusContext
from .scope_policy import check_scope
from .state_schema import active_context


def evaluate_closure_gates(
    state: Dict[str, Any],
    evidence: Dict[str, Any],
    testing: Dict[str, Any],
    review: Dict[str, Any],
    fix_loop: Dict[str, Any],
) -> Dict[str, Any]:
    """Evaluate all closure gates. Returns same dict as closure_contract."""
    return closure_conditions_met(state, evidence, testing, review, fix_loop)


def build_status_context(
    state: Dict[str, Any],
    goal: Dict[str, Any],
    review: Dict[str, Any],
    fix_loop: Dict[str, Any],
) -> StatusContext:
    """Build a concise status context for injection into user prompts."""
    ctx = StatusContext(
        phase=state.get("phase", "unknown"),
        active_goal=goal.get("active_goal", ""),
        active_context_id=state.get("active_context_id") or "",
        close_attempt=bool(state.get("close_attempt", False)),
        scope_violation=bool(state.get("scope_violation", False)),
        review_result=review.get("result", "unknown"),
        fix_loop_status=fix_loop.get("status", "none"),
        fix_loop_route=fix_loop.get("route") or "",
    )

    # Determine next required gate
    gates = _next_gate(state, review, fix_loop)
    ctx.next_gate = gates[0] if gates else ""

    # Build messages
    if ctx.scope_violation:
        ctx.messages.append("Scope violation detected — must be resolved before closure.")
    if ctx.fix_loop_status == "open":
        ctx.messages.append(f"Fix-loop open: route to {ctx.fix_loop_route}.")
    if ctx.close_attempt and ctx.review_result != "accepted":
        ctx.messages.append("Close attempted but review not accepted.")

    return ctx


def _next_gate(state: Dict[str, Any], review: Dict[str, Any], fix_loop: Dict[str, Any]) -> List[str]:
    """Return the list of next required gates as human-readable strings."""
    phase = state.get("phase", "discussing")
    gates = []

    if phase == "discussing":
        gates.append("Confirm goal with user and move to planning")
    elif phase == "planned":
        gates.append("Invoke executor subagent to implement")
    elif phase == "implementing":
        gates.append("Invoke tester subagent for deep testing")
    elif phase == "testing":
        gates.append("Invoke reviewer subagent for independent review")
    elif phase == "reviewing":
        if review.get("result") == "accepted":
            gates.append("All gates passed — invoke /aiwf-close to close")
        else:
            gates.append(f"Review result: {review.get('result')} — resolve blockers")
    elif phase == "closing":
        if state.get("scope_violation"):
            gates.append("Resolve scope violation before closure")
        if fix_loop.get("status") == "open":
            gates.append("Resolve fix-loop before closure")
        if review.get("result") != "accepted":
            gates.append("Review must be accepted before closure")

    if not gates:
        gates.append("Discuss with user to determine next step")

    return gates
