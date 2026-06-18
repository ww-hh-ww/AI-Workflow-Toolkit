"""Project operations — bootstrap_project, get_state_summary."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._common import _execution_contract_frozen, _freeze_explanation, _read, _write

def bootstrap_project(base_dir: str) -> Dict[str, Any]:
    """Bootstrap AIWF assets for an existing project. Scans code, creates baseline."""
    root = Path(base_dir)
    aiwf = root / ".aiwf"

    results = {"tasks": [], "files": 0, "modules": []}

    # 1. Scan project structure
    code_files = []
    exclude = {".git", ".aiwf", ".claude", ".reasonix", "__pycache__", "node_modules", ".venv", "venv",
               ".pytest_cache", ".mypy_cache", "dist", "build", ".DS_Store"}
    for f in root.rglob("*"):
        if f.is_file() and not any(e in f.parts for e in exclude):
            if f.suffix in (".py", ".js", ".ts", ".go", ".rs", ".java", ".rb", ".sh", ".md", ".toml", ".yaml", ".json"):
                rel = str(f.relative_to(root))
                code_files.append(rel)

    if not code_files:
        return {"bootstrapped": False, "reason": "no code files found"}

    results["files"] = len(code_files)

    # 2. Identify modules from directory structure
    modules = {}
    for f in code_files:
        parts = f.split("/")
        if len(parts) > 1:
            mod = parts[0]
        else:
            mod = "root"
        modules.setdefault(mod, []).append(f)
    results["modules"] = sorted(modules.keys())

    # 3. Write baseline task-history entry
    from datetime import datetime, timezone
    history_path = aiwf / "state" / "tasks.json"
    history = {"tasks": [], "historical_hotspots": {}}
    if history_path.exists():
        try:
            import json
            history = json.loads(history_path.read_text())
        except Exception:
            pass
    baseline_task = {
        "id": "BASELINE-001",
        "title": "[Bootstrap] Existing codebase baseline",
        "goal": "Project bootstrapped from existing code",
        "workflow_level": "baseline",
        "task_type": "bootstrap",
        "changed_files": code_files[:50],
        "testing_status": "n/a",
        "review_result": "n/a",
        "fix_loop_attempt_count": 0,
        "untested_risk_count": 0,
        "closed_at": datetime.now(timezone.utc).isoformat(),
        "bootstrap": True,
    }
    tasks = history.get("tasks", [])
    tasks = [t for t in tasks if not t.get("bootstrap")]
    tasks.insert(0, baseline_task)
    history["tasks"] = tasks
    import json
    (aiwf / "state" / "tasks.json").write_text(json.dumps(history, indent=2))
    results["tasks"].append("task-history baseline written")

    # 4. Run env scan if possible (machine-only asset)
    try:
        from ..environment import scan_environment, write_environment_profile
        env = scan_environment(base_dir)
        write_environment_profile(base_dir, env)
        results["tasks"].append("environment profile written")
    except Exception:
        pass

    # 5. Run capability scan
    try:
        from ..capabilities import discover_capabilities, write_capabilities_registry
        caps = discover_capabilities(base_dir)
        write_capabilities_registry(base_dir, caps)
        results["tasks"].append(f"capability scan: {len(caps.get('capabilities',[]))} found")
    except Exception:
        pass

    # 6. Create initial workspace-drift snapshot
    try:
        from ..workspace_drift import scan_workspace_drift, write_workspace_drift
        drift = scan_workspace_drift(base_dir)
        write_workspace_drift(base_dir, drift)
        results["tasks"].append("workspace drift baseline captured")
    except Exception:
        pass

    return {"bootstrapped": True, **results}

def get_state_summary(base_dir: str) -> Dict[str, Any]:
    """Return a concise summary of current AIWF state for skills."""
    base = Path(base_dir)

    def rj(name, default=None):
        return _read(base / ".aiwf" / name) if (base / ".aiwf" / name).exists() else (default or {})

    state = rj("state/state.json", {"phase": "unknown"})
    goals = rj("state/goals.json", {"goals": [], "active_goal_id": None})
    active_id = goals.get("active_goal_id") or "GOAL-001"
    goal = next((g for g in goals.get("goals", []) if isinstance(g, dict) and g.get("id") == active_id), {})
    review = rj("records/review.json", {})
    fix_loop = rj("state/fix-loop.json", {"status": "none"})

    return {
        "phase": state.get("phase", "unknown"),
        "complexity": state.get("complexity", "standard"),
        "workflow_level": state.get("workflow_level", state.get("workflow_strength", "L1_review_light")),
        "task_type": state.get("task_type", ""),
        "test_template": state.get("test_template", ""),
        "review_template": state.get("review_template", ""),
        "exploration_budget": state.get("exploration_budget", ""),
        "git_policy": state.get("git_policy", "no_auto_commit"),
        "recommended_minimum_level": state.get("recommended_minimum_level", ""),
        "requires_user_decision": state.get("requires_user_decision", False),
        "quality_escalation_required": state.get("quality_escalation_required", False),
        "quality_escalation_reason": state.get("quality_escalation_reason", ""),
        "active_goal": goal.get("active_goal", ""),
        "active_context_id": state.get("active_context_id", ""),
        "close_attempt": state.get("close_attempt", False),
        "scope_violation": state.get("scope_violation", False),
        "review_result": review.get("result", "unknown"),
        "closure_allowed": review.get("closure_allowed", False),
        "cleanup_status": review.get("cleanup_status", "unknown"),
        "structure_status": review.get("structure_status", "unknown"),
        "fix_loop_status": fix_loop.get("status", "none"),
    }
