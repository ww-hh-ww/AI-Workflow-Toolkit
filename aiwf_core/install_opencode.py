"""Native OpenCode integration for the shared AIWF governance core."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, List

from .install_claude import (
    AGENT_TEMPLATES,
    AIWF_MANAGED_BLOCK_END,
    AIWF_MANAGED_BLOCK_START,
    SKILL_REFERENCE_TEMPLATES,
    SKILL_TEMPLATES,
    _aiwf_dir,
    _aiwf_toolkit_root,
    _migrate_legacy_paths,
    _remove_retired_skills,
    _template_text,
    _write_scripts,
    _write_state_files,
)
from .io import rel, write_text


PRODUCT_NAME = "OpenCode"
COMMAND_NAME = "opencode --agent aiwf-planner"
ENTRY_COMMAND = "/aiwf-planner"


def _root() -> Path:
    return Path.cwd().resolve()


def _body(text: str) -> str:
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---", 4)
    return text[end + 4:].lstrip("\n") if end >= 0 else text


def _description(text: str, fallback: str) -> str:
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        for line in text[4:end].splitlines():
            if line.startswith("description:"):
                return line.split(":", 1)[1].strip()
    return fallback


def _opencode_text(text: str) -> str:
    converted = (
        text.replace("Claude Code", "OpenCode")
        .replace("`EnterWorktree`", "a worktree-switching tool")
        .replace("`isolation: worktree`", "tool-managed worktree isolation")
        .replace("Follow /aiwf-critic.", "Follow the aiwf-critic role instructions.")
        .replace("Agent({subagent_type:", "task({subagent_type:")
    )
    converted = re.sub(
        r"## SendMessage\n.*?(?=\n## Parallel Plans)",
        """## Continue a child session

Do not start the next Task role while the current child session is running.
When a returned child missed a small, specific item, continue that child once
with `task_id` set to its Task session ID and send only the new finding. If continuation
is unavailable, dispatch a new role with the Task ID and tell it to read
`aiwf task proof`. Do not repeat Task.md.

If the new information changes execution, boundaries, or acceptance, ask the
user to interrupt. Revise and critique the contract before dispatching again.
""".rstrip(),
        converted,
        flags=re.DOTALL,
    )
    converted = converted.replace(
        "When `aiwf status --prompt` names a previous Executor ID, resume that Agent for\n"
        "a non-trivial repair only if it is available in the current session or the\n"
        "resumed original session. Try `SendMessage` once. Send only the Task ID and\n"
        "tell it to read `aiwf task proof`. If resume is unavailable or fails, dispatch\n"
        "a new Executor with the Task ID and current finding. Do not retry the resume.",
        "When a previous Executor child session is still available, continue it once "
        "with the Task ID and tell it to read `aiwf task proof`. If continuation is "
        "unavailable, dispatch a new Executor with the Task ID and current finding.",
    )
    converted = converted.replace(
        "Planner does not switch worktrees to manage Task roles. Use the exact Task ID\n"
        "and assigned worktree for every dispatch or Task command. When several Tasks\n"
        "are active, `aiwf status --prompt` shows all Plan worktrees and marks the one\n"
        "matching the current directory.",
        "Keep planning decisions in the control-root Planner session. Dispatch the named\n"
        "OpenCode subagent there with exactly one Task ID. AIWF binds the child session to\n"
        "that Task and routes its project tools to the assigned Plan worktree. Run Executor,\n"
        "Tester, and Reviewer in the foreground. Independent Plans may use separate\n"
        "control-root OpenCode sessions when they need to run at the same time.",
    )
    return converted


def _configured_model(name: str) -> str:
    config = _aiwf_dir() / "config" / "agent-models.json"
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
        return str(data.get("models", {}).get("opencode", {}).get(name) or "inherit")
    except (OSError, json.JSONDecodeError):
        return "inherit"


def _agent_text(name: str, source: str, *, primary: bool = False) -> str:
    description = _description(source, "AIWF Planner" if primary else f"AIWF {name}")
    # AIWF's write policy owns the configurable role boundaries. OpenCode only
    # keeps Reviewer read-only because that role has no project-write mode.
    can_edit = name != "aiwf-reviewer"
    web = name in {"aiwf-planner", "aiwf-explorer", "aiwf-critic", "aiwf-architect"}
    lines = [
        "---",
        f"description: {description}",
        f"mode: {'primary' if primary else 'subagent'}",
        "permission:",
        "  read: allow",
        f"  edit: {'allow' if can_edit else 'deny'}",
        "  glob: allow",
        "  grep: allow",
        "  list: allow",
        "  bash: allow",
        f"  task: {'allow' if primary else 'deny'}",
        "  skill: allow",
        f"  webfetch: {'allow' if web else 'deny'}",
        f"  websearch: {'allow' if web else 'deny'}",
        "  external_directory: allow",
    ]
    model = _configured_model(name)
    if model != "inherit":
        lines.append(f"model: {model}")
    lines.extend(["---", "", _opencode_text(_body(source)).rstrip(), ""])
    return "\n".join(lines)


def _write_instruction() -> Path:
    path = _root() / "AGENTS.md"
    content = _opencode_text(_template_text("CLAUDE.md")).replace(
        "/aiwf-planner", "/aiwf-planner"
    )
    block = f"{AIWF_MANAGED_BLOCK_START}\n{content.rstrip()}\n{AIWF_MANAGED_BLOCK_END}\n"
    if not path.exists():
        write_text(path, block)
        return path
    existing = path.read_text(encoding="utf-8")
    if AIWF_MANAGED_BLOCK_START in existing and AIWF_MANAGED_BLOCK_END in existing:
        start = existing.index(AIWF_MANAGED_BLOCK_START)
        end = existing.index(AIWF_MANAGED_BLOCK_END) + len(AIWF_MANAGED_BLOCK_END)
        before = existing[:start].rstrip("\n")
        after = existing[end:].lstrip("\n")
        merged = (before + "\n\n" if before else "") + block
        if after:
            merged += "\n" + after
        write_text(path, merged)
    else:
        write_text(path, existing.rstrip("\n") + "\n\n" + block)
    return path


def _write_config() -> Path:
    path = _root() / "opencode.json"
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise ValueError("opencode.json must be valid JSON before AIWF can install")
    data.setdefault("$schema", "https://opencode.ai/config.json")
    data.setdefault("default_agent", "aiwf-planner")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _write_skills() -> List[Path]:
    paths: List[Path] = []
    root = _root() / ".opencode" / "skills"
    for name, template in SKILL_TEMPLATES.items():
        target = root / name / "SKILL.md"
        write_text(target, _opencode_text(_template_text(template)))
        paths.append(target)
        for relative, reference in SKILL_REFERENCE_TEMPLATES.get(name, {}).items():
            output = root / name / relative
            write_text(output, _opencode_text(_template_text(reference)))
            paths.append(output)
    return paths


def _write_agents() -> List[Path]:
    paths: List[Path] = []
    root = _root() / ".opencode" / "agents"
    planner_source = """# AIWF Planner

Own AIWF governance in the main OpenCode session. Run `aiwf status --prompt`
first, load every required skill, and follow the selected skill. Discuss before
creating governance documents unless the user explicitly asks you to proceed.
Do not implement project code while acting as Planner.
"""
    planner = root / "aiwf-planner.md"
    write_text(planner, _agent_text("aiwf-planner", planner_source, primary=True))
    paths.append(planner)
    for filename, template in AGENT_TEMPLATES.items():
        name = Path(filename).stem
        target = root / filename
        write_text(target, _agent_text(name, _template_text(template)))
        paths.append(target)
    return paths


def _write_opencode_assets() -> List[Path]:
    paths: List[Path] = []
    plugin = _template_text("opencode/aiwf.js")
    plugin_path = _root() / ".opencode" / "plugins" / "aiwf.js"
    write_text(plugin_path, plugin)
    paths.append(plugin_path)
    command_path = _root() / ".opencode" / "commands" / "aiwf-planner.md"
    write_text(command_path, _template_text("opencode/commands/aiwf-planner.md"))
    paths.append(command_path)
    return paths


def install_opencode(force: bool = False) -> Dict[str, List[str]]:
    results: Dict[str, List[str]] = {"created": [], "updated": [], "skipped": []}
    _migrate_legacy_paths()
    results["updated"].extend([rel(_write_instruction()), rel(_write_config())])
    for path in [*_write_skills(), *_write_agents(), *_write_opencode_assets()]:
        results["created"].append(rel(path))
    if force:
        # This helper only removes retired names inside the selected config tree.
        class Target:
            config_dir = ".opencode"
        for path in _remove_retired_skills(Target()):
            results["updated"].append(rel(path))
    for path in [*_write_state_files(), *_write_scripts()]:
        results["created"].append(rel(path))
    toolkit = _aiwf_dir() / "runtime" / "internal" / "toolkit-path.txt"
    toolkit.parent.mkdir(parents=True, exist_ok=True)
    toolkit.write_text(str(_aiwf_toolkit_root()), encoding="utf-8")
    results["created"].append(rel(toolkit))
    python_command = _aiwf_dir() / "runtime" / "internal" / "python-command.json"
    python_command.write_text(
        json.dumps({"argv": [sys.executable]}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    results["created"].append(rel(python_command))
    readme = _aiwf_dir() / "README.md"
    if not readme.exists() or force:
        readme.write_text(_template_text("README.md"), encoding="utf-8")
        readme_rel = rel(readme)
        if readme_rel not in results["created"]:
            results["created"].append(readme_rel)
    from .hooks.common.diff_snapshot import write_install_baseline
    write_install_baseline(_root())
    return results


def doctor_opencode() -> Dict[str, object]:
    """Check the native OpenCode adapter without applying Claude hook rules."""
    from .core.index_ops import check_index, sync_index
    from .core.memory_health import memory_structure_warnings
    from .core.paths import ALL_DIRS
    from .core.state_schema import MVP_STATE_FILES
    from .core.worktree_context import resolve_control_root

    root = resolve_control_root(_root())
    skills = {}
    for name in SKILL_TEMPLATES:
        path = root / ".opencode" / "skills" / name / "SKILL.md"
        skills[name] = {
            "exists": path.exists(),
            "has_frontmatter": path.exists() and path.read_text(encoding="utf-8").startswith("---"),
        }
    agents = {}
    for name in ["aiwf-planner", *(Path(item).stem for item in AGENT_TEMPLATES)]:
        path = root / ".opencode" / "agents" / f"{name}.md"
        agents[name] = {
            "exists": path.exists(),
            "has_frontmatter": path.exists() and path.read_text(encoding="utf-8").startswith("---"),
        }
    plugin = root / ".opencode" / "plugins" / "aiwf.js"
    plugin_text = plugin.read_text(encoding="utf-8") if plugin.exists() else ""
    hooks = {
        "chat.message": {
            "configured": '"chat.message"' in plugin_text,
            "valid_schema": '"chat.message"' in plugin_text,
        },
        "shell.env": {
            "configured": '"shell.env"' in plugin_text,
            "valid_schema": '"shell.env"' in plugin_text,
        },
        "tool.execute.before": {
            "configured": '"tool.execute.before"' in plugin_text,
            "valid_schema": '"tool.execute.before"' in plugin_text,
        },
        "tool.execute.after": {
            "configured": '"tool.execute.after"' in plugin_text,
            "valid_schema": '"tool.execute.after"' in plugin_text,
        },
        "experimental.session.compacting": {
            "configured": '"experimental.session.compacting"' in plugin_text,
            "valid_schema": '"experimental.session.compacting"' in plugin_text,
        },
    }
    state_files = {name: (root / ".aiwf" / name).exists() for name in MVP_STATE_FILES}
    state_files.update({f"dir:{name}": (root / ".aiwf" / name).is_dir() for name in ALL_DIRS})
    script_names = [
        "aiwf_status.py", "aiwf_scope_check.py", "aiwf_bash_guard.py",
        "aiwf_worktree_route.py", "aiwf_skill_log.py", "aiwf_agent_log.py",
        "aiwf_agent_gate.py", "aiwf_auto_sync.py", "aiwf_review_gate.py",
    ]
    scripts = {
        name: {"exists": (root / "scripts" / name).exists(), "executable": (root / "scripts" / name).exists()}
        for name in script_names
    }
    try:
        index_result = check_index(str(root))
        index = {
            "healthy": index_result["healthy"],
            "issues_count": index_result["issues_count"],
            "issues": index_result["issues"][:10],
        }
    except Exception as exc:
        index = {"healthy": False, "issues_count": 1, "issues": [str(exc)]}
    try:
        sync_result = sync_index(str(root), dry_run=True)
        errors = sync_result.get("errors", [])
        warnings = [item for item in sync_result.get("changes", []) if "WARNING" in item]
        sync = {
            "healthy": not errors,
            "error_count": len(errors),
            "errors": errors[:10],
            "warning_count": len(warnings),
            "warnings": warnings[:5],
        }
    except Exception as exc:
        sync = {"healthy": False, "error_count": 1, "errors": [str(exc)], "warning_count": 0, "warnings": []}
    warnings = memory_structure_warnings(root)
    memory = {"healthy": not warnings, "warning_count": len(warnings), "warnings": warnings[:10]}
    all_ok = (
        (root / "AGENTS.md").exists()
        and (root / "opencode.json").exists()
        and all(item["exists"] and item["has_frontmatter"] for item in skills.values())
        and all(item["exists"] and item["has_frontmatter"] for item in agents.values())
        and all(item["valid_schema"] for item in hooks.values())
        and all(state_files.values())
        and all(item["exists"] for item in scripts.values())
        and index["healthy"]
        and sync["healthy"]
    )
    has_warnings = bool(warnings) or bool(sync.get("warning_count"))
    return {
        "mode": "opencode",
        "product_name": PRODUCT_NAME,
        "config_dir": ".opencode",
        "instruction_file": "AGENTS.md",
        "instruction_md": (root / "AGENTS.md").exists(),
        "settings_json": (root / "opencode.json").exists(),
        "settings_label": "opencode.json",
        "skills": skills,
        "agents": agents,
        "hooks": hooks,
        "state_files": state_files,
        "scripts": scripts,
        "index": index,
        "sync": sync,
        "memory": memory,
        "overall": "healthy_with_warnings" if all_ok and has_warnings else ("healthy" if all_ok else "issues_found"),
    }
