"""Read-only environment continuity guidance for native role handoffs."""
from pathlib import Path


def environment_handoff(control: Path, *, task_id: str = "", plan_id: str = "",
                        experiment_id: str = "", task_doc: str = "") -> str:
    sources = []
    if task_id:
        document = control / (task_doc or f".aiwf/tasks/{task_id}.md")
        sources.append(f"Known Context in {document}; aiwf task proof {task_id}")
    if plan_id:
        sources.append(f"Plan context in {control / '.aiwf/plans' / (plan_id + '.md')}")
    if experiment_id:
        sources.append(f"aiwf experiment show {experiment_id}")
    return "\n".join([
        "Environment continuity: a new worktree isolates code, not a new machine.",
        "Environment sources: " + ("; ".join(sources) or "the supplied project documentation and evidence references"),
        "Follow those sources and the main-session context to existing runtime, tools, dependencies, services, and build instructions. Inspect compatibility and repair only missing or incompatible parts; do not bootstrap everything merely because the worktree is new.",
        "Confirm which source tree the runtime actually loads and which revision/configuration produced reused build outputs. Prior runtime success is not proof of this candidate.",
        "Share compatible resources only within existing permissions. Do not overwrite another worktree's mutable outputs or reconfigure shared services; isolate outputs when needed. Do not copy secrets or bulk-link dependency/configuration directories.",
        "Record relevant environment provenance and current-code checks in existing V/FIX command/basis or EXP commands/observations, not a new environment certificate.",
    ])
