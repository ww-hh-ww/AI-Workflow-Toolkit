"""AIWF embedded install for Claude-compatible coding shells.

Generates integration files using backend-neutral core logic.
Core defines engineering semantics; the Claude-compatible adapter formats hooks.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, NamedTuple

from .constants import VERSION
from .core.state_schema import MVP_STATE_FILES
from .core.paths import ALL_DIRS
from .io import read_json, rel, write_json, write_text
from .utils import now


# ── paths ──────────────────────────────────────────────────────────────

class EmbedTarget(NamedTuple):
    mode: str
    product_name: str
    command_name: str
    config_dir: str
    project_env_var: str
    instruction_file: str
    entry_command: str


TARGETS: Dict[str, EmbedTarget] = {
    "claude": EmbedTarget(
        mode="claude",
        product_name="Claude Code",
        command_name="claude",
        config_dir=".claude",
        project_env_var="CLAUDE_PROJECT_DIR",
        instruction_file="CLAUDE.md",
        entry_command="aiwf status --prompt",
    ),
    "reasonix": EmbedTarget(
        mode="reasonix",
        product_name="Reasonix",
        command_name="reasonix code .",
        config_dir=".reasonix",
        project_env_var="REASONIX_PROJECT_DIR",
        instruction_file="REASONIX.md",
        entry_command="aiwf status --prompt",
    ),
}


def _target(mode: str = "claude") -> EmbedTarget:
    if mode not in TARGETS:
        raise ValueError(f"Unsupported install mode: {mode}")
    return TARGETS[mode]


def _project_root() -> Path:
    return Path.cwd().resolve()


def _config_dir(target: EmbedTarget) -> Path:
    return _project_root() / target.config_dir


def _claude_dir() -> Path:
    return _config_dir(_target("claude"))


def _skills_dir(target: EmbedTarget | None = None) -> Path:
    return _config_dir(target or _target("claude")) / "skills"


def _agents_dir(target: EmbedTarget | None = None) -> Path:
    return _config_dir(target or _target("claude")) / "agents"


def _aiwf_dir() -> Path:
    return _project_root() / ".aiwf"


def _scripts_dir() -> Path:
    return _project_root() / "scripts"


def _aiwf_toolkit_root() -> Path:
    """Path to the AIWF toolkit installation (where aiwf_core/ lives)."""
    return Path(__file__).resolve().parent.parent


def _script_bootstrap() -> str:
    return r'''import sys, os
from pathlib import Path

# Add project root to sys.path for project-local imports.
_AH_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_AH_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AH_PROJECT_ROOT))

# === diagnostic log (persistent, check .aiwf/runtime/internal/hook-diag.log) ===
def _ah_diag(msg: str) -> None:
    try:
        _dp = _AH_PROJECT_ROOT / ".aiwf" / "runtime" / "internal"
        _dp.mkdir(parents=True, exist_ok=True)
        with open(_dp / "hook-diag.log", "a") as _df:
            import datetime
            _df.write(f"{datetime.datetime.now().isoformat()} [{os.path.basename(__file__)}] {msg}\n")
    except Exception:
        pass

_ah_diag(f"started, python={sys.executable}, argv={sys.argv[:3]}, cwd={os.getcwd()}, path={list(sys.path[:5])}")

# Discover aiwf_core at runtime — no hardcoded paths.
# 1. Pip-installed aiwf_core is importable directly.
# 2. Otherwise, read the toolkit path recorded by aiwf install.
try:
    import aiwf_core  # noqa: F401
    _ah_diag("import aiwf_core ok")
except ImportError as _e:
    _ah_diag(f"import aiwf_core failed: {_e}, trying toolkit-path.txt")
    _TK_CFG = _AH_PROJECT_ROOT / ".aiwf" / "runtime" / "internal" / "toolkit-path.txt"
    if _TK_CFG.exists():
        _TK_ROOT = _TK_CFG.read_text().strip()
        _ah_diag(f"toolkit-path.txt found: {_TK_ROOT}, exists={Path(_TK_ROOT).exists()}")
        if _TK_ROOT and Path(_TK_ROOT).exists() and _TK_ROOT not in sys.path:
            sys.path.insert(0, _TK_ROOT)
            _ah_diag("added toolkit root to sys.path")
    else:
        _ah_diag("toolkit-path.txt not found")
'''

def _script_bootstrap_stdlib_only() -> str:
    """Bootstrap for scripts that must stay stdlib-only (aiwf_status.py)."""
    return '''import sys
from pathlib import Path

# Add project root to sys.path for project-local imports.
_AH_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_AH_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AH_PROJECT_ROOT))
'''


# ── settings.json (Claude adapter) ─────────────────────────────────────

def _build_settings_json(target: EmbedTarget | None = None) -> Dict[str, Any]:
    """Build settings.json in the Claude-compatible hook schema.

    Schema: { hooks: { EventName: [ { matcher?, hooks: [ { type, command } ] } ] } }
    Uses the target project env var for portable paths.
    All commands are shell-quoted so paths with spaces (e.g. "External Asset Lab") work.
    """
    target = target or _target("claude")
    scripts = "${" + target.project_env_var + "}/scripts"

    # Pre-compute shell-quoted paths: "${CLAUDE_PROJECT_DIR}/scripts/aiwf_xxx.py"
    qs = f'"{scripts}'
    q_status       = qs + '/aiwf_status.py" --short'
    q_scope_check  = qs + '/aiwf_scope_check.py"'
    q_bash_guard   = qs + '/aiwf_bash_guard.py"'
    q_worktree_route = qs + '/aiwf_worktree_route.py"'
    q_skill_log    = qs + '/aiwf_skill_log.py"'
    q_agent_log    = qs + '/aiwf_agent_log.py"'
    q_agent_gate   = qs + '/aiwf_agent_gate.py"'
    q_auto_sync    = qs + '/aiwf_auto_sync.py"'
    q_review_gate  = qs + '/aiwf_review_gate.py"'

    if target.mode == "reasonix":
        pf = "AIWF_HOOK_ENGINE=reasonix "
        return {
            "hooks": {
                "UserPromptSubmit": [{
                    "command": pf + q_status, "description": "Inject compact AIWF workflow status before Reasonix handles the prompt", "timeout": 5000,
                }],
                "PreToolUse": [
                    {"command": pf + q_scope_check,  "match": "^(write|edit|edit_file|multi_edit|Write|Edit|MultiEdit)$", "description": "Block writes outside the active AIWF context scope", "timeout": 5000},
                    {"command": pf + q_bash_guard,   "match": "^(bash|Bash)$", "description": "Block dangerous shell commands before execution", "timeout": 5000},
                    {"command": pf + q_agent_gate,  "match": "^(agent|task|Agent|Task)$", "description": "Block Agent dispatch without prior SKILL load", "timeout": 5000},
                ],
                "PostToolUse": [
                    {"command": pf + q_skill_log,  "match": "^(skill|Skill)$", "description": "Log Skill loads for agent gate enforcement", "timeout": 5000},
                    {"command": pf + q_agent_log,  "match": "^(agent|task|Agent|Task)$", "description": "Log Agent/Task dispatch for close-gate enforcement", "timeout": 5000},
                    {"command": pf + q_auto_sync,  "match": "^(write|edit|edit_file|multi_edit|Write|Edit|MultiEdit)$", "description": "Auto-sync AIWF MD to JSON after governance file edits", "timeout": 15000},
                ],
                "Stop": [{
                    "command": pf + q_review_gate, "description": "Report AIWF closure gate status on session exit (Reasonix Stop is non-gating)", "timeout": 5000,
                }],
            }
        }
    _h = lambda cmd: {"hooks": [{"type": "command", "command": cmd}]}
    return {
        "env": {
            "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1",
        },
        "hooks": {
            "UserPromptSubmit": [_h(q_status)],
            "PreToolUse": [
                {"matcher": "Read|Glob|Grep",                        **_h(q_worktree_route)},
                {"matcher": "Write|Edit|MultiEdit",                 **_h(q_scope_check)},
                {"matcher": "Bash",                                 **_h(q_bash_guard)},
                {"matcher": "Agent|Task",                           **_h(q_agent_gate)},
            ],
            "PostToolUse": [
                {"matcher": "Skill",                                **_h(q_skill_log)},
                {"matcher": "Agent|Task",                           **_h(q_agent_log)},
                {"matcher": "TaskStop",                             **_h(q_agent_log)},
                {"matcher": "Write|Edit|MultiEdit",                 **_h(q_auto_sync)},
            ],
            "PostToolUseFailure": [
                {"matcher": "Agent|Task",                           **_h(q_agent_log)},
            ],
            "SubagentStart": [
                {"matcher": "aiwf-executor|aiwf-tester|aiwf-reviewer|aiwf-architect", **_h(q_agent_log)},
            ],
            "SubagentStop": [
                {"matcher": "aiwf-executor|aiwf-tester|aiwf-reviewer|aiwf-architect", **_h(q_agent_log)},
            ],
            "Stop": [_h(q_review_gate)],
        },
        "permissions": {
            "allow": [
                "Bash(aiwf:*)",
                "Bash(scripts/aiwf_status.py:*)",

                "Bash(scripts/aiwf_scope_check.py:*)",
                "Bash(scripts/aiwf_bash_guard.py:*)",
                "Bash(scripts/aiwf_worktree_route.py:*)",

                "Bash(scripts/aiwf_review_gate.py:*)",
                "Bash(scripts/aiwf_agent_log.py:*)",
                "Bash(scripts/aiwf_agent_gate.py:*)",
                "Bash(scripts/aiwf_skill_log.py:*)",
                "Bash(scripts/aiwf_auto_sync.py:*)",
                "Read(.aiwf/**)",
                "Write(.aiwf/**)",
                "Edit(.aiwf/**)",
            ]
        },
    }


def _is_aiwf_hook_handler(handler: Any) -> bool:
    """Return whether a hook handler is managed by AIWF."""
    if not isinstance(handler, dict):
        return False
    command = str(handler.get("command") or "").replace("\\", "/")
    return "scripts/aiwf_" in command


def _without_aiwf_hook_handlers(entry: Any) -> Any:
    """Remove AIWF-owned handlers while preserving user handlers in the group."""
    if not isinstance(entry, dict):
        return entry
    if isinstance(entry.get("hooks"), list):
        handlers = [
            handler for handler in entry["hooks"]
            if not _is_aiwf_hook_handler(handler)
        ]
        if not handlers:
            return None
        preserved = dict(entry)
        preserved["hooks"] = handlers
        return preserved
    if _is_aiwf_hook_handler(entry):
        return None
    return entry


def _merge_hooks(existing_hooks: Any, managed_hooks: Dict[str, Any]) -> Dict[str, Any]:
    """Refresh AIWF hooks without taking ownership of other project hooks."""
    merged: Dict[str, Any] = {}
    if isinstance(existing_hooks, dict):
        for event_name, current_entries in existing_hooks.items():
            if not isinstance(current_entries, list):
                merged[event_name] = current_entries
                continue
            preserved = []
            for entry in current_entries:
                clean = _without_aiwf_hook_handlers(entry)
                if clean is not None:
                    preserved.append(clean)
            if preserved:
                merged[event_name] = preserved

    for event_name, managed_entries in managed_hooks.items():
        current_entries = merged.get(event_name, [])
        if not isinstance(current_entries, list):
            current_entries = []
        merged[event_name] = current_entries + list(managed_entries or [])
    return merged


def _write_settings(target: EmbedTarget | None = None) -> Path:
    target = target or _target("claude")
    d = _config_dir(target)
    d.mkdir(parents=True, exist_ok=True)
    settings = _build_settings_json(target)
    target = d / "settings.json"
    if target.exists():
        existing = json.loads(target.read_text(encoding="utf-8"))
        new_hooks = settings.get("hooks", {})
        existing["hooks"] = _merge_hooks(existing.get("hooks"), new_hooks)
        for key, value in settings.get("env", {}).items():
            existing.setdefault("env", {}).setdefault(key, value)
        for perm in settings.get("permissions", {}).get("allow", []):
            existing.setdefault("permissions", {}).setdefault("allow", [])
            if perm not in existing["permissions"]["allow"]:
                existing["permissions"]["allow"].append(perm)
        write_json(target, existing)
    else:
        write_json(target, settings)
    return target


# ── embedded templates ───────────────────────────────────────────────

_TEMPLATE_ROOT = Path(__file__).resolve().parent / "embedded_templates"

SKILL_TEMPLATES = {
    "aiwf-critic": "skills/aiwf-critic/SKILL.md",
    "aiwf-planner": "skills/aiwf-planner/SKILL.md",
    "aiwf-implement": "skills/aiwf-implement/SKILL.md",
    "aiwf-test": "skills/aiwf-test/SKILL.md",
    "aiwf-review": "skills/aiwf-review/SKILL.md",
    "aiwf-close": "skills/aiwf-close/SKILL.md",
    "aiwf-architect": "skills/aiwf-architect/SKILL.md",
}

SKILL_REFERENCE_TEMPLATES = {
    "aiwf-planner": {
        "references/task-contract.md": "skills/aiwf-planner/references/task-contract.md",
        "references/structure-guide.md": "skills/aiwf-planner/references/structure-guide.md",
        "references/writing-guide.md": "skills/aiwf-planner/references/writing-guide.md",
        "references/goal-writing.md": "skills/aiwf-planner/references/goal-writing.md",
        "references/plan-writing.md": "skills/aiwf-planner/references/plan-writing.md",
        "references/milestone-writing.md": "skills/aiwf-planner/references/milestone-writing.md",
        "references/activation-critique.md": "skills/aiwf-planner/references/activation-critique.md",
        "references/lifecycle.md": "skills/aiwf-planner/references/lifecycle.md",
    },
    "aiwf-implement": {
        "inline-execution.md": "shared/inline-execution.md",
    },
    "aiwf-test": {
        "inline-execution.md": "shared/inline-execution.md",
    },
    "aiwf-review": {
        "inline-execution.md": "shared/inline-execution.md",
    },
    "aiwf-architect": {
        "references/code-review.md": "skills/aiwf-architect/references/code-review.md",
        "references/design-review.md": "skills/aiwf-architect/references/design-review.md",
        "references/structure-review.md": "skills/aiwf-architect/references/structure-review.md",
        "references/milestone-acceptance.md": "skills/aiwf-architect/references/milestone-acceptance.md",
    },
}

AGENT_TEMPLATES = {
    "aiwf-explorer.md": "agents/aiwf-explorer.md",
    "aiwf-executor.md": "agents/aiwf-executor.md",
    "aiwf-critic.md": "agents/aiwf-critic.md",
    "aiwf-tester.md": "agents/aiwf-tester.md",
    "aiwf-reviewer.md": "agents/aiwf-reviewer.md",
    "aiwf-architect.md": "agents/aiwf-architect.md",
}

REASONIX_ONLY_SKILL_TEMPLATES = {
    "aiwf-explorer": "agents/aiwf-explorer.md",
}

SCRIPT_TEMPLATES = {
    "aiwf_status.py": "scripts/aiwf_status.py",

    "aiwf_scope_check.py": "scripts/aiwf_scope_check.py",
    "aiwf_bash_guard.py": "scripts/aiwf_bash_guard.py",
    "aiwf_worktree_route.py": "scripts/aiwf_worktree_route.py",

    "aiwf_review_gate.py": "scripts/aiwf_review_gate.py",
    "aiwf_skill_log.py": "scripts/aiwf_skill_log.py",
    "aiwf_agent_log.py": "scripts/aiwf_agent_log.py",
    "aiwf_agent_gate.py": "scripts/aiwf_agent_gate.py",
    "aiwf_auto_sync.py": "scripts/aiwf_auto_sync.py",
}


def _template_text(relative_path: str) -> str:
    return (_TEMPLATE_ROOT / relative_path).read_text(encoding="utf-8")


def _target_template_text(relative_path: str, target: EmbedTarget) -> str:
    text = _template_text(relative_path)
    if target.mode == "reasonix" and relative_path in REASONIX_ROLE_SKILL_TEMPLATES:
        text = _reasonix_role_skill_text(relative_path, text)
    if target.mode == "reasonix":
        text = text.replace("Claude Code", "Reasonix")
        text = text.replace("Claude-compatible", "Reasonix-compatible")
        text = text.replace("Claude", "Reasonix")
        if relative_path.startswith("skills/"):
            text = _reasonix_skill_text(relative_path, text)
    return text


REASONIX_ROLE_SKILL_TEMPLATES = {
    "skills/aiwf-implement/SKILL.md": "agents/aiwf-executor.md",
    "skills/aiwf-test/SKILL.md": "agents/aiwf-tester.md",
    "skills/aiwf-review/SKILL.md": "agents/aiwf-reviewer.md",
    "skills/aiwf-architect/SKILL.md": "agents/aiwf-architect.md",
    "skills/aiwf-critic/SKILL.md": "agents/aiwf-critic.md",
}


def _reasonix_role_skill_text(relative_path: str, skill_text: str) -> str:
    """Keep the public skill identity but use the role prompt Reasonix runs."""
    role_text = _template_text(REASONIX_ROLE_SKILL_TEMPLATES[relative_path])
    skill_end = skill_text.find("\n---", 4)
    role_end = role_text.find("\n---", 4)
    if skill_end == -1 or role_end == -1:
        return skill_text
    role_body = role_text[role_end + len("\n---"):].lstrip("\n")
    return skill_text[:skill_end + len("\n---")] + "\n\n" + role_body


REASONIX_SUBAGENT_SKILL_CONFIG = {
    "aiwf-planner": {"runAs": "inline"},
    "aiwf-implement": {"runAs": "subagent", "description": "Implement the active Task.md contract."},
    "aiwf-test": {"runAs": "subagent", "description": "Independently test the active Task.md claim."},
    "aiwf-review": {"runAs": "subagent", "description": "Independently review the active Task.md result."},
    "aiwf-close": {"runAs": "inline"},
    "aiwf-architect": {"runAs": "subagent", "description": "Independently review completed work against the fixed mission."},
    "aiwf-critic": {"runAs": "subagent", "description": "Independently challenge a project claim, decision, or result."},
    "aiwf-explorer": {"runAs": "subagent", "description": "Locate facts or independently compare approaches before planning."},
}

REASONIX_SKILL_AGENT = {
    "aiwf-implement": "aiwf-executor",
    "aiwf-test": "aiwf-tester",
    "aiwf-review": "aiwf-reviewer",
    "aiwf-architect": "aiwf-architect",
    "aiwf-critic": "aiwf-critic",
    "aiwf-explorer": "aiwf-explorer",
}


def _configured_agent_model(target: EmbedTarget, agent_name: str) -> str:
    config_path = _aiwf_dir() / "config" / "agent-models.json"
    template_path = _TEMPLATE_ROOT / "config" / "agent-models.json"
    source = config_path if config_path.exists() else template_path
    try:
        config = json.loads(source.read_text(encoding="utf-8"))
        backend = config.get("models", {}).get(target.mode, {})
        value = str(backend.get(agent_name) or "inherit").strip()
        return value or "inherit"
    except Exception:
        return "inherit"


def _reasonix_skill_text(relative_path: str, text: str) -> str:
    skill_name = relative_path.split("/")[1]
    config = dict(REASONIX_SUBAGENT_SKILL_CONFIG.get(skill_name, {}))
    agent_name = REASONIX_SKILL_AGENT.get(skill_name)
    if agent_name:
        model = _configured_agent_model(_target("reasonix"), agent_name)
        if model != "inherit":
            config["model"] = model
    if config:
        text = _merge_frontmatter(text, config)
    return text


def _merge_frontmatter(text: str, updates: Dict[str, str]) -> str:
    if not text.startswith("---\n"):
        lines = ["---"] + [f"{k}: {v}" for k, v in updates.items()] + ["---", "", text]
        return "\n".join(lines)
    end = text.find("\n---", 4)
    if end == -1:
        return text
    frontmatter = text[4:end].strip("\n")
    body = text[end + len("\n---"):]
    lines = [line for line in frontmatter.splitlines() if line.strip()]
    existing_keys = {line.split(":", 1)[0].strip() for line in lines if ":" in line}
    for key, value in updates.items():
        if key in existing_keys:
            lines = [
                f"{key}: {value}" if line.split(":", 1)[0].strip() == key else line
                for line in lines
            ]
        else:
            lines.append(f"{key}: {value}")
    return "---\n" + "\n".join(lines) + "\n---" + body


def _write_skills(target: EmbedTarget | None = None) -> List[Path]:
    target_config = target or _target("claude")
    d = _skills_dir(target_config)
    d.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []

    for skill_name, template_path in SKILL_TEMPLATES.items():
        skill_dir = d / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path = skill_dir / "SKILL.md"
        write_text(skill_path, _target_template_text(template_path, target_config))
        paths.append(skill_path)

        for rel_out, rel_template in SKILL_REFERENCE_TEMPLATES.get(skill_name, {}).items():
            out_path = skill_dir / rel_out
            out_path.parent.mkdir(parents=True, exist_ok=True)
            write_text(out_path, _target_template_text(rel_template, target_config))
            paths.append(out_path)

    if target_config.mode == "reasonix":
        for skill_name, template_path in REASONIX_ONLY_SKILL_TEMPLATES.items():
            skill_dir = d / skill_name
            skill_dir.mkdir(parents=True, exist_ok=True)
            skill_path = skill_dir / "SKILL.md"
            text = _target_template_text(template_path, target_config)
            text = _reasonix_skill_text(f"skills/{skill_name}/SKILL.md", text)
            write_text(skill_path, text)
            paths.append(skill_path)

    return paths


# ── subagents ──────────────────────────────────────────────────────────

def _write_agents(target: EmbedTarget | None = None) -> List[Path]:
    target_config = target or _target("claude")
    d = _agents_dir(target_config)
    d.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, template_path in AGENT_TEMPLATES.items():
        agent_path = d / name
        text = _target_template_text(template_path, target_config)
        model = _configured_agent_model(target_config, Path(name).stem)
        if model != "inherit":
            text = _merge_frontmatter(text, {"model": model})
        write_text(agent_path, text)
        paths.append(agent_path)
    return paths


# ── .aiwf state files ─────────────────────────────────────────────────

def _write_state_files() -> List[Path]:
    d = _aiwf_dir()
    d.mkdir(parents=True, exist_ok=True)
    for subdir in ALL_DIRS:
        (d / subdir).mkdir(parents=True, exist_ok=True)
    paths = []
    file_paths = {
        "state/state.json": d / "state" / "state.json",
        "state/goals.json": d / "state" / "goals.json",
        "state/plans.json": d / "state" / "plans.json",
        "state/tasks.json": d / "state" / "tasks.json",
        "state/milestones.json": d / "state" / "milestones.json",
        "records/events.json": d / "records" / "events.json",
    }
    # Write .aiwf/README.md
    readme_target = d / "README.md"
    if not readme_target.exists():
        readme_target.write_text(
            "\n".join([
                "# AIWF Workspace",
                "",
                "This directory is AIWF's governance workspace.",
                "",
                "Zones:",
                "- `state/` — machine truth (JSON): registries, canonical state, gate inputs.",
                "- `records/tasks/` — implementation, testing, review, and fix-loop records by Task.",
                "- `records/events.json` — concise workflow events.",
                "- `goals/` — goal narrative docs (Markdown).",
                "- `plans/` — plan narrative docs (Markdown).",
                "- `tasks/` — task narrative docs (Markdown, execution contract).",
                "- `milestones/` — milestone narrative docs (Markdown).",
                "- `memory/` — Planner's tiny long-term planning memory.",
                "- `config/` — configuration (skill-map, command-policy, write-policy, agent-models).",
                "- `runtime/internal/` — toolkit-path, drift, hook, and agent logs.",
                "",
                "Human entry points:",
                "- `aiwf status`",
                "- `aiwf doctor`",
                "- Narrative docs in `goals/`, `plans/`, `tasks/`, `milestones/`",
                "- `memory/project-facts.md` — tiny Planner memory; keep only durable planning facts.",
            ]),
            encoding="utf-8",
        )
        paths.append(readme_target)
    mission_target = d / "mission.md"
    mission_src = _TEMPLATE_ROOT / "mission.md"
    if mission_src.exists() and not mission_target.exists():
        import shutil
        shutil.copy2(str(mission_src), str(mission_target))
        paths.append(mission_target)
    # Write config/skill-map.json
    skill_map_target = d / "config" / "skill-map.json"
    if not skill_map_target.exists():
        import shutil
        src = _TEMPLATE_ROOT / "config" / "skill-map.json"
        if src.exists():
            skill_map_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(skill_map_target))
            paths.append(skill_map_target)
    # Write config/command-policy.json
    cmd_policy_target = d / "config" / "command-policy.json"
    cmd_policy_src = _TEMPLATE_ROOT / "config" / "command-policy.json"
    if not cmd_policy_target.exists():
        import shutil
        if cmd_policy_src.exists():
            cmd_policy_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(cmd_policy_src), str(cmd_policy_target))
            paths.append(cmd_policy_target)
    elif cmd_policy_src.exists():
        try:
            current = json.loads(cmd_policy_target.read_text(encoding="utf-8"))
            template = json.loads(cmd_policy_src.read_text(encoding="utf-8"))
            current.setdefault("deny", [])
            existing = {
                str(entry.get("command") or "")
                for entry in current.get("deny", []) or []
                if isinstance(entry, dict)
            }
            changed = False
            for entry in template.get("deny", []) or []:
                command = str(entry.get("command") or "")
                if command and command not in existing:
                    current["deny"].append(entry)
                    existing.add(command)
                    changed = True
            if changed:
                cmd_policy_target.write_text(
                    json.dumps(current, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                paths.append(cmd_policy_target)
        except Exception:
            pass
    # Write config/write-policy.json
    write_policy_target = d / "config" / "write-policy.json"
    write_policy_src = _TEMPLATE_ROOT / "config" / "write-policy.json"
    if not write_policy_target.exists():
        import shutil
        if write_policy_src.exists():
            write_policy_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(write_policy_src), str(write_policy_target))
            paths.append(write_policy_target)
    elif write_policy_src.exists():
        try:
            current = json.loads(write_policy_target.read_text(encoding="utf-8"))
            template = json.loads(write_policy_src.read_text(encoding="utf-8"))
            changed = False
            if "reviewer_project_writes" in current:
                current.pop("reviewer_project_writes", None)
                changed = True
            for key in ("schema_version", "description", "allowed_values"):
                if current.get(key) != template.get(key):
                    current[key] = template.get(key)
                    changed = True
            for key, value in template.items():
                if key not in current:
                    current[key] = value
                    changed = True
            if changed:
                write_policy_target.write_text(
                    json.dumps(current, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                paths.append(write_policy_target)
        except Exception:
            pass
    # Write config/agent-models.json. Refresh help/default keys, preserve choices.
    agent_models_target = d / "config" / "agent-models.json"
    agent_models_src = _TEMPLATE_ROOT / "config" / "agent-models.json"
    if not agent_models_target.exists():
        import shutil
        if agent_models_src.exists():
            agent_models_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(agent_models_src), str(agent_models_target))
            paths.append(agent_models_target)
    elif agent_models_src.exists():
        try:
            current = json.loads(agent_models_target.read_text(encoding="utf-8"))
            template = json.loads(agent_models_src.read_text(encoding="utf-8"))
            changed = False
            for key in ("schema_version", "description", "allowed_values"):
                if current.get(key) != template.get(key):
                    current[key] = template.get(key)
                    changed = True
            current_models = current.setdefault("models", {})
            for backend, defaults in template.get("models", {}).items():
                backend_models = current_models.setdefault(backend, {})
                for agent_name, value in defaults.items():
                    if agent_name not in backend_models:
                        backend_models[agent_name] = value
                        changed = True
            if changed:
                agent_models_target.write_text(
                    json.dumps(current, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                paths.append(agent_models_target)
        except Exception:
            pass
    memory_templates = {
        "memory/MEMORY.md": _TEMPLATE_ROOT / "memory" / "MEMORY.md",
        "memory/project-facts.md": _TEMPLATE_ROOT / "memory" / "project-facts.md",
    }
    # Copy notes/ directory (topic files) — never overwrite existing
    notes_src = _TEMPLATE_ROOT / "memory" / "notes"
    notes_target = d / "memory" / "notes"
    if notes_src.exists() and notes_src.is_dir():
        import shutil
        notes_target.mkdir(parents=True, exist_ok=True)
        for f in notes_src.iterdir():
            target = notes_target / f.name
            if not target.exists():
                if f.is_dir():
                    shutil.copytree(str(f), str(target))
                else:
                    shutil.copy2(str(f), str(target))
                paths.append(target)
    for rel_path, src in memory_templates.items():
        target = d / rel_path
        if src.exists() and not target.exists():
            import shutil
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(target))
            paths.append(target)
    for filename, default_fn in MVP_STATE_FILES.items():
        target = file_paths.get(filename, d / filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            # Only create missing files — never overwrite existing user data.
            # The --force flag regenerates scripts/settings, not state data.
            write_json(target, default_fn())
            paths.append(target)
    paths.extend(_migrate_singleton_task_records(d))
    try:
        from .core.index_ops import sync_index
        sync_index(str(Path.cwd()))
        mission_state = d / "state" / "mission.json"
        if mission_state.exists() and mission_state not in paths:
            paths.append(mission_state)
    except Exception:
        pass
    return paths


def _migrate_singleton_task_records(aiwf_dir: Path) -> List[Path]:
    """Move retired singleton workflow records into Task-owned records."""
    from .core.task_records import default_task_record, save_task_record

    legacy = {
        "implementation": aiwf_dir / "records/implementation.json",
        "testing": aiwf_dir / "records/testing.json",
        "review": aiwf_dir / "records/review.json",
    }
    values = {name: read_json(path, {}) for name, path in legacy.items()}
    state = read_json(aiwf_dir / "state/state.json", {})
    fix_path = aiwf_dir / "state/fix-loop.json"
    fix_loop = read_json(fix_path, {})
    task_ids = {
        str(value.get("task_id") or "")
        for value in values.values()
        if isinstance(value, dict) and value.get("task_id")
    }
    legacy_active = str(state.get("active_task_id") or "")
    if legacy_active:
        task_ids.add(legacy_active)

    migrated: List[Path] = []
    for task_id in sorted(task_ids):
        record = default_task_record(task_id)
        changed = False
        for section, value in values.items():
            if isinstance(value, dict) and str(value.get("task_id") or "") == task_id:
                record[section] = value
                changed = True
        if (
            isinstance(fix_loop, dict)
            and fix_loop.get("status") in ("open", "resolved")
            and task_id == legacy_active
        ):
            record["fix_loop"] = fix_loop
            changed = True
        if changed:
            save_task_record(aiwf_dir.parent, record)
            migrated.append(aiwf_dir / "records/tasks" / f"{task_id}.json")

    for path in [*legacy.values(), fix_path]:
        if path.exists():
            path.unlink()
    return migrated


# ── hook scripts ───────────────────────────────────────────────────────

def _write_scripts() -> List[Path]:
    d = _scripts_dir()
    d.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, template_path in SCRIPT_TEMPLATES.items():
        target = d / name
        bootstrap = _script_bootstrap_stdlib_only() if name == "aiwf_status.py" else _script_bootstrap()
        body = _template_text(template_path).lstrip()
        if body.startswith("#!/usr/bin/env python3"):
            body = body[len("#!/usr/bin/env python3"):].lstrip("\n")
        elif body.startswith("#!"):
            first_nl = body.index("\n")
            body = body[first_nl + 1:]
        future_line = "from __future__ import annotations\n"
        if future_line in body:
            insert_at = body.index(future_line) + len(future_line)
            full = "#!/usr/bin/env python3\n" + body[:insert_at] + "\n" + bootstrap + body[insert_at:]
        else:
            full = "#!/usr/bin/env python3\n" + bootstrap + body
        write_text(target, full)
        target.chmod(0o755)
        paths.append(target)
    return paths


CLAUDE_MD_CONTENT = _template_text("CLAUDE.md").rstrip("\n")

AIWF_MANAGED_BLOCK_START = "<!-- AIWF MANAGED BLOCK START -->"
AIWF_MANAGED_BLOCK_END = "<!-- AIWF MANAGED BLOCK END -->"


def _write_instruction_md(target: EmbedTarget | None = None) -> Path:
    """Write AIWF managed block into the target instruction file."""
    target = target or _target("claude")
    instruction_path = _project_root() / target.instruction_file
    content = CLAUDE_MD_CONTENT
    if target.mode == "reasonix":
        content = content.replace("Claude Code", "Reasonix").replace("Claude", "Reasonix")
        content = content.replace("/aiwf-planner", "/skill aiwf-planner")
    block = f"{AIWF_MANAGED_BLOCK_START}\n{content}\n{AIWF_MANAGED_BLOCK_END}\n"

    if not instruction_path.exists():
        write_text(instruction_path, block)
        return instruction_path

    existing = instruction_path.read_text(encoding="utf-8")

    if AIWF_MANAGED_BLOCK_START in existing and AIWF_MANAGED_BLOCK_END in existing:
        # Replace existing managed block
        start_idx = existing.index(AIWF_MANAGED_BLOCK_START)
        end_idx = existing.index(AIWF_MANAGED_BLOCK_END) + len(AIWF_MANAGED_BLOCK_END)
        before = existing[:start_idx].rstrip("\n")
        after = existing[end_idx:].lstrip("\n")
        new_content = before + "\n\n" + block
        if after:
            new_content += "\n" + after
        write_text(instruction_path, new_content)
        return instruction_path

    # Append managed block to existing content
    write_text(instruction_path, existing.rstrip("\n") + "\n\n" + block)
    return instruction_path


def _write_claude_md() -> Path:
    return _write_instruction_md(_target("claude"))


# ── main install ───────────────────────────────────────────────────────


def _migrate_legacy_paths():
    """Move retired flat .aiwf files into the current five-zone layout."""
    root = _project_root()
    aiwf = root / ".aiwf"
    if not aiwf.exists():
        return

    legacy_map = {
        "state.json": "state/state.json",
        "goals.json": "state/goals.json",
        "plans.json": "state/plans.json",
        "tasks.json": "state/tasks.json",
        "milestones.json": "state/milestones.json",
        "fix-loop.json": "state/fix-loop.json",
        "task-ledger.json": "state/tasks.json",
        "evidence.json": "",
        "implementation.json": "records/implementation.json",
        "testing.json": "records/testing.json",
        "review.json": "records/review.json",
    }

    migrated = []
    for old_name, new_path in legacy_map.items():
        old = aiwf / old_name
        new = aiwf / new_path
        if new_path and old.exists() and not new.exists():
            new.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.move(str(old), str(new))
            migrated.append(f"{old_name} -> {new_path}")
    # Clean up old zone dirs that are no longer valid
    dead_dirs = ["archive", "assets", "artifacts", "runtime/history", "runtime/checkpoints"]
    for dd in dead_dirs:
        dead = aiwf / dd
        if dead.exists():
            import shutil
            shutil.rmtree(str(dead), ignore_errors=True)
            migrated.append(f"removed dead dir: {dd}/")
    # Clean up flat orphans
    orphan_cleanup = [
        "state.json", "contexts.json", "fix-loop.json",
        "evidence.json", "testing.json", "review.json",
        "task-history.json", "task-ledger.json",
        "current-state.md", "report.md", "quality-digest.md", "PROJECT-MAP.md",
        "baseline.json", "ideas.md",
    ]
    for orphan in orphan_cleanup:
        old_path = aiwf / orphan
        target = legacy_map.get(orphan, "")
        new_path = aiwf / target if target else None
        if old_path.exists() and (not target or (new_path and new_path.exists())):
            old_path.unlink()
            migrated.append(f"cleaned orphan: {orphan}")
    for retired in [
        aiwf / "architecture-review.json",
        aiwf / "records" / "architecture-review.json",
        aiwf / "records" / "evidence.json",
    ]:
        if retired.exists():
            retired.unlink()
            migrated.append(f"removed retired record: {retired.relative_to(aiwf)}")

    if migrated:
        print(f"aiwf: migrated {len(migrated)} files to v2 layout")
        for m in migrated:
            print(f"  {m}")


def _remove_retired_skills(target: EmbedTarget) -> List[Path]:
    removed: List[Path] = []
    for name in ["aiwf-milestone", "aiwf-project"]:
        path = _skills_dir(target) / name
        if path.exists():
            import shutil
            shutil.rmtree(str(path), ignore_errors=True)
            removed.append(path)
    for relative_path in [
        "aiwf-review/references/review-output.md",
        "aiwf-review/references/trace-checklist.md",
        "aiwf-review/references/verify-checklist.md",
    ]:
        path = _skills_dir(target) / relative_path
        if path.exists():
            path.unlink()
            removed.append(path)
        references_dir = path.parent
        if references_dir.exists() and not any(references_dir.iterdir()):
            references_dir.rmdir()
    return removed

def install_embedded(mode: str = "claude", force: bool = False) -> Dict[str, Any]:
    target = _target(mode)
    results: Dict[str, List[str]] = {
        "created": [],
        "updated": [],
        "skipped": [],
    }

    # Migrate legacy flat-layout .aiwf files to v2 subdirectory layout.
    _migrate_legacy_paths()


    # Embedded install uses the compact .aiwf state directory only.
    results["updated"].append(rel(_write_instruction_md(target)))
    results["updated"].append(rel(_write_settings(target)))

    for p in _write_skills(target):
        results["created"].append(rel(p))
    if force:
        for p in _remove_retired_skills(target):
            results["updated"].append(rel(p))
    if target.mode == "claude":
        for p in _write_agents(target):
            results["created"].append(rel(p))
    elif force:
        # Reasonix subagents are skills with runAs: subagent. Remove old generated
        # agent copies so there is one instruction source per role.
        for name in AGENT_TEMPLATES:
            old_agent = _agents_dir(target) / name
            if old_agent.exists():
                old_agent.unlink()
                results["updated"].append(rel(old_agent))
    for p in _write_state_files():
        results["created"].append(rel(p))
    for p in _write_scripts():
        results["created"].append(rel(p))

    # Record toolkit root path so generated scripts can discover aiwf_core
    # at runtime without hardcoded absolute paths.
    _tk_cfg = _aiwf_dir() / "runtime" / "internal" / "toolkit-path.txt"
    _tk_cfg.parent.mkdir(parents=True, exist_ok=True)
    _tk_cfg.write_text(str(_aiwf_toolkit_root()))
    results["created"].append(rel(_tk_cfg))

    # Write human-readable README
    readme_path = _aiwf_dir() / "README.md"
    if not readme_path.exists() or force:
        readme_path.write_text(_template_text("README.md"), encoding="utf-8")
        readme_rel = rel(readme_path)
        if readme_rel not in results["created"]:
            results["created"].append(readme_rel)

    # Write git baseline so PostToolUse diffs exclude install artifacts
    from .hooks.common.diff_snapshot import write_install_baseline
    baseline_ref = write_install_baseline(_project_root())
    if baseline_ref:
        results["created"].append(rel(_aiwf_dir() / "baseline.json"))

    return results


def install_claude(force: bool = False) -> Dict[str, Any]:
    return install_embedded("claude", force=force)


def install_reasonix(force: bool = False) -> Dict[str, Any]:
    return install_embedded("reasonix", force=force)


def doctor(mode: str | None = None) -> Dict[str, Any]:
    from .core.worktree_context import resolve_control_root
    root = resolve_control_root(_project_root())
    target = _target(mode) if mode else (_detect_installed_target(root) or _target("claude"))
    checks: Dict[str, Any] = {
        "mode": target.mode,
        "product_name": target.product_name,
        "config_dir": target.config_dir,
        "instruction_file": target.instruction_file,
        "instruction_md": (root / target.instruction_file).exists(),
        "claude_md": (root / target.instruction_file).exists(),
        "settings_json": (root / target.config_dir / "settings.json").exists(),
        "skills": {},
        "agents": {},
        "hooks": {},
        "state_files": {},
        "scripts": {},
    }

    for skill in ["aiwf-planner", "aiwf-implement", "aiwf-test", "aiwf-review",
        "aiwf-close", "aiwf-architect"]:
        path = root / target.config_dir / "skills" / skill / "SKILL.md"
        exists = path.exists()
        has_frontmatter = False
        if exists:
            content = path.read_text(encoding="utf-8")
            has_frontmatter = content.startswith("---")
        checks["skills"][skill] = {"exists": exists, "has_frontmatter": has_frontmatter}

    if target.mode == "claude":
        for agent in ["aiwf-explorer", "aiwf-executor", "aiwf-tester", "aiwf-reviewer", "aiwf-critic", "aiwf-architect"]:
            path = root / target.config_dir / "agents" / f"{agent}.md"
            exists = path.exists()
            has_frontmatter = False
            if exists:
                content = path.read_text(encoding="utf-8")
                has_frontmatter = content.startswith("---")
            checks["agents"][agent] = {"exists": exists, "has_frontmatter": has_frontmatter}

    settings_path = root / target.config_dir / "settings.json"
    if settings_path.exists():
        try:
            settings_data = json.loads(settings_path.read_text(encoding="utf-8"))
            hooks_cfg = settings_data.get("hooks", {})
            event_names = ["UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"]
            if target.mode == "claude":
                event_names.extend(["PostToolUseFailure", "SubagentStart", "SubagentStop"])
            for event_name in event_names:
                entries = hooks_cfg.get(event_name, [])
                if target.mode == "reasonix":
                    valid_schema = all(
                        isinstance(e, dict)
                        and isinstance(e.get("command"), str)
                        and e.get("command")
                        and "hooks" not in e
                        for e in entries
                    )
                else:
                    valid_schema = all(
                        isinstance(e, dict) and "hooks" in e
                        for e in entries
                    )
                checks["hooks"][event_name] = {
                    "configured": len(entries) > 0,
                    "valid_schema": valid_schema,
                }
        except Exception:
            event_names = ["UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"]
            if target.mode == "claude":
                event_names.extend(["PostToolUseFailure", "SubagentStart", "SubagentStop"])
            for ev in event_names:
                checks["hooks"][ev] = {"configured": False, "valid_schema": False}

    for sf in MVP_STATE_FILES:
        path = root / ".aiwf" / sf
        checks["state_files"][sf] = path.exists()

    for script in ["aiwf_status.py", "aiwf_scope_check.py",
                    "aiwf_bash_guard.py", "aiwf_worktree_route.py", "aiwf_skill_log.py",
                    "aiwf_agent_log.py", "aiwf_agent_gate.py",
                    "aiwf_auto_sync.py", "aiwf_review_gate.py"]:
        path = root / "scripts" / script
        exists = path.exists()
        executable = exists and (path.stat().st_mode & 0o111)
        checks["scripts"][script] = {"exists": exists, "executable": executable}

    # Directory structure check
    for subdir in ALL_DIRS:
        dir_path = root / ".aiwf" / subdir
        checks["state_files"][f"dir:{subdir}"] = dir_path.is_dir()

    # Index sync check (narrative doc binding)
    try:
        from .core.index_ops import check_index
        idx = check_index(str(root))
        checks["index"] = {"healthy": idx["healthy"], "issues_count": idx["issues_count"],
                           "issues": idx["issues"][:10]}
    except Exception as e:
        checks["index"] = {"healthy": False, "issues_count": 1, "issues": [str(e)]}

    # Sync check (MD frontmatter -> JSON compiler)
    try:
        from .core.index_ops import sync_index
        sync = sync_index(str(root), dry_run=True)
        sync_errors = sync.get("errors", [])
        sync_changes = sync.get("changes", [])
        has_warnings = any("WARNING" in c for c in sync_changes)
        checks["sync"] = {"healthy": len(sync_errors) == 0,
                         "error_count": len(sync_errors),
                         "warning_count": sum(1 for c in sync_changes if "WARNING" in c),
                         "warnings": [c for c in sync_changes if "WARNING" in c][:5],
                         "locked": sync.get("locked", False),
                         "errors": sync_errors[:10]}
    except Exception as e:
        checks["sync"] = {"healthy": False, "error_count": 1, "errors": [str(e)],
                         "warning_count": 0, "warnings": []}

    from .core.memory_health import memory_structure_warnings
    memory_warnings = memory_structure_warnings(root)
    checks["memory"] = {
        "healthy": not memory_warnings,
        "root": str(root / ".aiwf" / "memory"),
        "warning_count": len(memory_warnings),
        "warnings": memory_warnings[:10],
    }

    sync_ok = checks.get("sync", {}).get("healthy", True)
    sync_warnings = checks.get("sync", {}).get("warning_count", 0) > 0
    has_warnings = sync_warnings or bool(memory_warnings)

    all_ok = (
        checks["instruction_md"]
        and checks["settings_json"]
        and all(v["exists"] and v["has_frontmatter"] for v in checks["skills"].values())
        and all(v["exists"] and v["has_frontmatter"] for v in checks.get("agents", {}).values())
        and all(v["configured"] and v["valid_schema"] for v in checks["hooks"].values())
        and all(checks["state_files"].values())
        and all(v["exists"] and v["executable"] for v in checks["scripts"].values())
        and checks.get("index", {}).get("healthy", True)
        and sync_ok
    )
    if all_ok and has_warnings:
        checks["overall"] = "healthy_with_warnings"
    elif all_ok:
        checks["overall"] = "healthy"
    else:
        checks["overall"] = "issues_found"

    return checks


def _detect_installed_target(root: Path) -> EmbedTarget | None:
    for target in TARGETS.values():
        if (root / target.config_dir / "settings.json").exists():
            return target
    return None
