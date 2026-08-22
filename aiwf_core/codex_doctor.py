"""Health checks for an installed Codex adapter."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from .install_claude import AGENT_TEMPLATES, SKILL_TEMPLATES


def doctor_codex(start: Path) -> Dict[str, object]:
    from .core.index_ops import check_index, sync_index
    from .core.memory_health import memory_structure_warnings
    from .core.paths import ALL_DIRS
    from .core.state_schema import MVP_STATE_FILES
    from .core.worktree_context import resolve_control_root

    root = resolve_control_root(start)
    skills = {}
    for name in SKILL_TEMPLATES:
        path = root / ".agents" / "skills" / name / "SKILL.md"
        skills[name] = {
            "exists": path.exists(),
            "has_frontmatter": path.exists()
            and path.read_text(encoding="utf-8").startswith("---"),
        }
    agents = {}
    for filename in AGENT_TEMPLATES:
        name = Path(filename).stem
        path = root / ".codex" / "agents" / f"{name}.toml"
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        agents[name] = {
            "exists": path.exists(),
            "has_frontmatter": bool(
                "developer_instructions = " in text and f'name = "{name}"' in text
            ),
        }
    hooks_path = root / ".codex" / "hooks.json"
    try:
        hooks_data = json.loads(hooks_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        hooks_data = {}
    configured = hooks_data.get("hooks", {}) if isinstance(hooks_data, dict) else {}
    required_hooks = [
        "UserPromptSubmit", "PreToolUse", "PostToolUse",
        "SubagentStart", "SubagentStop", "Stop",
    ]
    hooks = {
        name: {
            "configured": bool(configured.get(name)),
            "valid_schema": isinstance(configured.get(name), list)
            and bool(configured.get(name)),
        }
        for name in required_hooks
    }
    state_files = {name: (root / ".aiwf" / name).exists() for name in MVP_STATE_FILES}
    state_files.update(
        {f"dir:{name}": (root / ".aiwf" / name).is_dir() for name in ALL_DIRS}
    )
    script_names = [
        "aiwf_status.py", "aiwf_scope_check.py", "aiwf_bash_guard.py",
        "aiwf_worktree_route.py", "aiwf_agent_log.py", "aiwf_agent_gate.py",
        "aiwf_auto_sync.py", "aiwf_review_gate.py", "aiwf_codex_hook.py",
    ]
    scripts = {
        name: {
            "exists": (root / "scripts" / name).exists(),
            "executable": (root / "scripts" / name).exists(),
        }
        for name in script_names
    }
    try:
        result = check_index(str(root))
        index = {
            "healthy": result["healthy"],
            "issues_count": result["issues_count"],
            "issues": result["issues"][:10],
        }
    except Exception as exc:
        index = {"healthy": False, "issues_count": 1, "issues": [str(exc)]}
    try:
        result = sync_index(str(root), dry_run=True)
        errors = result.get("errors", [])
        warnings = [item for item in result.get("changes", []) if "WARNING" in item]
        sync = {
            "healthy": not errors,
            "error_count": len(errors),
            "errors": errors[:10],
            "warning_count": len(warnings),
            "warnings": warnings[:5],
        }
    except Exception as exc:
        sync = {
            "healthy": False, "error_count": 1, "errors": [str(exc)],
            "warning_count": 0, "warnings": [],
        }
    memory_warnings = memory_structure_warnings(root)
    memory = {
        "healthy": not memory_warnings,
        "warning_count": len(memory_warnings),
        "warnings": memory_warnings[:10],
    }
    all_ok = (
        (root / "AGENTS.md").exists()
        and all(item["exists"] and item["has_frontmatter"] for item in skills.values())
        and all(item["exists"] and item["has_frontmatter"] for item in agents.values())
        and all(item["valid_schema"] for item in hooks.values())
        and all(state_files.values())
        and all(item["exists"] for item in scripts.values())
        and index["healthy"]
        and sync["healthy"]
    )
    return {
        "mode": "codex",
        "product_name": "Codex",
        "config_dir": ".codex",
        "instruction_file": "AGENTS.md",
        "instruction_md": (root / "AGENTS.md").exists(),
        "settings_json": hooks_path.exists(),
        "settings_label": ".codex/hooks.json",
        "skills": skills,
        "agents": agents,
        "hooks": hooks,
        "state_files": state_files,
        "scripts": scripts,
        "index": index,
        "sync": sync,
        "memory": memory,
        "adapter_warnings": ["Confirm project hook trust with /hooks in Codex."],
        "overall": "healthy_with_warnings" if all_ok else "issues_found",
    }
