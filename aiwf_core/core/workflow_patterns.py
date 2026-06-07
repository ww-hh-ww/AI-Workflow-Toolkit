"""Uncertainty routing: workflow shape orthogonal to L0-L3 depth."""
from __future__ import annotations

from pathlib import Path
from typing import Dict
import json

REQUEST_MODES = {
    "discussion": "Raw discussion; do not freeze execution state.",
    "clarification": "Requirements are unclear; question before planning.",
    "research": "External or broad read-only research is needed before deciding.",
    "spike": "Feasibility is uncertain; run a bounded experiment before final contract.",
    "execution": "Execution contract may be frozen and activated.",
}

WORKFLOW_PATTERNS = {
    "linear": "Default AIWF state machine.",
    "clarification_first": "Stress-test requirements before freezing a plan.",
    "research_first": "Collect low-trust external/read-only evidence before deciding.",
    "spike_first": "Bounded experiment, then revise or freeze the real contract.",
    "adversarial_early": "Introduce adversarial critique before implementation.",
}

NON_EXECUTION_MODES = {"discussion", "clarification", "research"}


def _state_path(base_dir: str) -> Path:
    return Path(base_dir) / ".aiwf" / "state" / "state.json"


def _read_state(base_dir: str) -> Dict:
    path = _state_path(base_dir)
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        return {}


def _write_state(base_dir: str, state: Dict) -> None:
    path = _state_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def set_workflow_mode(
    base_dir: str,
    request_mode: str,
    workflow_pattern: str = "",
    reason: str = "",
    external_research_required: bool | None = None,
) -> Dict:
    if request_mode not in REQUEST_MODES:
        raise ValueError(f"invalid request_mode: {request_mode}")
    if workflow_pattern and workflow_pattern not in WORKFLOW_PATTERNS:
        raise ValueError(f"invalid workflow_pattern: {workflow_pattern}")
    state = _read_state(base_dir)
    state["request_mode"] = request_mode
    if workflow_pattern:
        state["workflow_pattern"] = workflow_pattern
    elif not state.get("workflow_pattern"):
        state["workflow_pattern"] = "linear"
    state["pattern_reason"] = reason
    if external_research_required is not None:
        state["external_research_required"] = bool(external_research_required)
    _write_state(base_dir, state)
    return state


def mode_activation_blocker(state: Dict) -> str:
    mode = state.get("request_mode", "execution")
    pattern = state.get("workflow_pattern", "linear")
    if mode in NON_EXECUTION_MODES:
        return (
            f"request_mode={mode} blocks implementation activation; "
            "continue discussion/research and switch to request_mode=execution before activating"
        )
    if mode == "spike" and pattern == "spike_first":
        return (
            "request_mode=spike is experimental; record spike findings and switch to "
            "request_mode=execution before activating a final implementation task"
        )
    return ""


def guidance_for_state(state: Dict) -> Dict[str, str]:
    mode = state.get("request_mode", "execution")
    pattern = state.get("workflow_pattern", "linear")
    return {
        "request_mode": mode,
        "request_mode_description": REQUEST_MODES.get(mode, REQUEST_MODES["execution"]),
        "workflow_pattern": pattern,
        "workflow_pattern_description": WORKFLOW_PATTERNS.get(pattern, WORKFLOW_PATTERNS["linear"]),
        "pattern_reason": state.get("pattern_reason", ""),
    }
