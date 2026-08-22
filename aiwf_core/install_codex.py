"""Native Codex integration for the shared AIWF governance core."""
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
    _shared_agents_instruction_text,
    _template_text,
    _write_scripts,
    _write_state_files,
)
from .io import rel, write_text


PRODUCT_NAME = "Codex"
COMMAND_NAME = "codex"
ENTRY_COMMAND = "$aiwf-planner"


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


def _codex_text(text: str) -> str:
    converted = (
        text.replace("Claude Code", "Codex")
        .replace("`EnterWorktree`", "a worktree-switching tool")
        .replace("`isolation: worktree`", "tool-managed worktree isolation")
        .replace("Agent/Task tool", "native subagent tool")
        .replace("Agent call", "subagent call")
    )
    converted = re.sub(r"(?<![A-Za-z0-9_])/(aiwf-[a-z-]+)", r"$\1", converted)
    converted = converted.replace(
        "with `SendMessage`", "by sending one follow-up message to the existing agent thread"
    ).replace(
        "with SendMessage", "by sending one follow-up message to the existing agent thread"
    ).replace("`SendMessage`", "the existing agent thread").replace(
        "## SendMessage", "## Resume an existing agent"
    )
    converted = re.sub(
        r'`Agent\(\{subagent_type: "([^"]+)", prompt: "(.*?)"\}\)`',
        lambda match: (
            f"Dispatch the `{match.group(1)}` custom agent with this message: "
            f"`{match.group(2)}`"
        ),
        converted,
    )
    return converted


def _write_instruction() -> Path:
    path = _root() / "AGENTS.md"
    content = _shared_agents_instruction_text()
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


def _write_skills() -> List[Path]:
    paths: List[Path] = []
    root = _root() / ".agents" / "skills"
    for name, template in SKILL_TEMPLATES.items():
        target = root / name / "SKILL.md"
        write_text(target, _codex_text(_template_text(template)))
        paths.append(target)
        for relative, reference in SKILL_REFERENCE_TEMPLATES.get(name, {}).items():
            output = root / name / relative
            write_text(output, _codex_text(_template_text(reference)))
            paths.append(output)
    return paths


def _configured_model(name: str) -> str:
    config = _aiwf_dir() / "config" / "agent-models.json"
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
        return str(data.get("models", {}).get("codex", {}).get(name) or "inherit")
    except (OSError, json.JSONDecodeError):
        return "inherit"


def _agent_toml(name: str, source: str) -> str:
    description = _description(source, f"AIWF {name}")
    body = _codex_text(_body(source)).rstrip()
    if "'''" in body:
        raise ValueError(f"Codex agent instructions for {name} contain unsupported TOML delimiter")
    lines = [
        f"name = {json.dumps(name, ensure_ascii=False)}",
        f"description = {json.dumps(description, ensure_ascii=False)}",
    ]
    model = _configured_model(name)
    if model != "inherit":
        lines.append(f"model = {json.dumps(model, ensure_ascii=False)}")
    # Reviewer must still write its AIWF record, Tester may add test assets, and
    # Architect may write a report. AIWF hooks own the narrower role boundary.
    lines.append('sandbox_mode = "workspace-write"')
    lines.extend(["developer_instructions = '''", body, "'''", ""])
    return "\n".join(lines)


def _write_agents() -> List[Path]:
    paths: List[Path] = []
    root = _root() / ".codex" / "agents"
    for filename, template in AGENT_TEMPLATES.items():
        name = Path(filename).stem
        target = root / f"{name}.toml"
        write_text(target, _agent_toml(name, _template_text(template)))
        paths.append(target)
    return paths


def _hook_command(script: str, *args: str) -> str:
    launcher = _root() / "scripts" / "aiwf_codex_hook.py"
    values = [sys.executable, str(launcher), script, *args]
    return " ".join(json.dumps(value) for value in values)


def _write_codex_launcher() -> Path:
    path = _root() / "scripts" / "aiwf_codex_hook.py"
    write_text(path, '''#!/usr/bin/env python3
import os
import runpy
import sys
from pathlib import Path

os.environ["AIWF_HOOK_ENGINE"] = "codex"
os.environ["AIWF_HOST"] = "codex"
if len(sys.argv) < 2:
    raise SystemExit("AIWF Codex hook launcher requires a script name")
target = Path(__file__).resolve().parent / sys.argv[1]
sys.argv = [str(target), *sys.argv[2:]]
runpy.run_path(str(target), run_name="__main__")
''')
    return path


def _hook(command: str) -> Dict[str, object]:
    return {"hooks": [{"type": "command", "command": command, "timeout": 30}]}


def _write_hooks() -> Path:
    path = _root() / ".codex" / "hooks.json"
    managed = {
        "hooks": {
            "UserPromptSubmit": [_hook(_hook_command("aiwf_status.py", "--short"))],
            "PreToolUse": [
                {"matcher": "Read|Glob|Grep|List", **_hook(_hook_command("aiwf_worktree_route.py"))},
                {"matcher": "apply_patch|Edit|Write", **_hook(_hook_command("aiwf_scope_check.py"))},
                {"matcher": "Bash", **_hook(_hook_command("aiwf_bash_guard.py"))},
                {"matcher": "Agent", **_hook(_hook_command("aiwf_agent_gate.py"))},
            ],
            "PostToolUse": [
                {"matcher": "Agent", **_hook(_hook_command("aiwf_agent_log.py"))},
                {"matcher": "apply_patch|Edit|Write", **_hook(_hook_command("aiwf_auto_sync.py"))},
            ],
            "SubagentStart": [{"matcher": "aiwf-.*", **_hook(_hook_command("aiwf_agent_log.py"))}],
            "SubagentStop": [{"matcher": "aiwf-.*", **_hook(_hook_command("aiwf_agent_log.py"))}],
            "Stop": [_hook(_hook_command("aiwf_review_gate.py"))],
        }
    }
    existing: Dict[str, object] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (OSError, json.JSONDecodeError):
            raise ValueError(".codex/hooks.json must be valid JSON before AIWF can install")
    # Refresh AIWF handlers while preserving user hooks in every event.
    existing_hooks = existing.get("hooks", {}) if isinstance(existing.get("hooks"), dict) else {}
    merged_hooks: Dict[str, object] = {}
    event_names = dict.fromkeys([*existing_hooks, *managed["hooks"]])
    for event_name in event_names:
        preserved = []
        for entry in existing_hooks.get(event_name, []) or []:
            encoded = json.dumps(entry, ensure_ascii=False)
            if "aiwf_codex_hook.py" not in encoded:
                preserved.append(entry)
        merged_hooks[event_name] = preserved + list(managed["hooks"].get(event_name, []) or [])
    existing["hooks"] = merged_hooks
    write_text(path, json.dumps(existing, ensure_ascii=False, indent=2) + "\n")
    return path


def install_codex(force: bool = False) -> Dict[str, List[str]]:
    results: Dict[str, List[str]] = {
        "created": [], "updated": [], "skipped": [], "warnings": [],
    }
    _migrate_legacy_paths()
    results["updated"].append(rel(_write_instruction()))
    for path in [*_write_skills(), *_write_agents()]:
        results["created"].append(rel(path))
    if force:
        class Target:
            config_dir = ".agents"
        for path in _remove_retired_skills(Target()):
            results["updated"].append(rel(path))
    state_paths = _write_state_files()
    from .core.governance_git import ensure_governance_gitignore

    ensure_governance_gitignore(_root())
    for path in [*state_paths, *_write_scripts(), _write_codex_launcher(), _write_hooks()]:
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
        results["created"].append(rel(readme))
    from .hooks.common.diff_snapshot import write_install_baseline

    write_install_baseline(_root())
    results["warnings"].append(
        "Codex requires project hook trust. Review .codex/hooks.json with /hooks before relying on enforcement."
    )
    return results


def doctor_codex() -> Dict[str, object]:
    from .codex_doctor import doctor_codex as inspect_codex

    return inspect_codex(_root())
