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
from .core.paths import ALL_DIRS, STATE_JSON, GOAL_JSON, CONTEXTS_JSON, FIX_LOOP_JSON, EVIDENCE_JSON, TESTING_JSON, REVIEW_JSON, TASK_HISTORY_JSON, TASK_LEDGER_JSON, QUALITY_DIGEST_MD, PROJECT_MAP_MD, BASELINE_JSON
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
    planner_command: str


TARGETS: Dict[str, EmbedTarget] = {
    "claude": EmbedTarget(
        mode="claude",
        product_name="Claude Code",
        command_name="claude",
        config_dir=".claude",
        project_env_var="CLAUDE_PROJECT_DIR",
        instruction_file="CLAUDE.md",
        planner_command='/aiwf-planner "describe your goal"',
    ),
    "reasonix": EmbedTarget(
        mode="reasonix",
        product_name="Reasonix",
        command_name="reasonix code .",
        config_dir=".reasonix",
        project_env_var="REASONIX_PROJECT_DIR",
        instruction_file="REASONIX.md",
        planner_command='/skill aiwf-planner "describe your goal"',
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

# === diagnostic log (persistent, check .aiwf/internal/hook-diag.log) ===
def _ah_diag(msg: str) -> None:
    try:
        _dp = _AH_PROJECT_ROOT / ".aiwf" / "internal"
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
    _TK_CFG = _AH_PROJECT_ROOT / ".aiwf" / "internal" / "toolkit-path.txt"
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
    q_status       = qs + '/aiwf_status.py"'
    q_pre_snapshot = qs + '/aiwf_pre_snapshot.py"'
    q_scope_check  = qs + '/aiwf_scope_check.py"'
    q_bash_guard   = qs + '/aiwf_bash_guard.py"'
    q_capture      = qs + '/aiwf_capture_evidence.py"'
    q_review_gate  = qs + '/aiwf_review_gate.py"'

    if target.mode == "reasonix":
        pf = "AIWF_HOOK_ENGINE=reasonix "
        return {
            "hooks": {
                "UserPromptSubmit": [{
                    "command": pf + q_status, "description": "Inject compact AIWF workflow status before Reasonix handles the prompt", "timeout": 5000,
                }],
                "PreToolUse": [
                    {"command": pf + q_pre_snapshot, "match": "^(write|edit|edit_file|multi_edit|bash|agent|task|Write|Edit|MultiEdit|Bash|Agent|Task)$", "description": "Capture a pre-tool filesystem snapshot for AIWF evidence", "timeout": 5000},
                    {"command": pf + q_scope_check,  "match": "^(write|edit|edit_file|multi_edit|Write|Edit|MultiEdit)$", "description": "Block writes outside the active AIWF context scope", "timeout": 5000},
                    {"command": pf + q_bash_guard,   "match": "^(bash|Bash)$", "description": "Block dangerous shell commands before execution", "timeout": 5000},
                ],
                "PostToolUse": [{
                    "command": pf + q_capture, "match": "^(write|edit|edit_file|multi_edit|bash|agent|task|Write|Edit|MultiEdit|Bash|Agent|Task)$", "description": "Capture git-diff evidence after file or shell tools", "timeout": 30000,
                }],
                "Stop": [{
                    "command": pf + q_review_gate, "description": "Report AIWF closure gate status on session exit (Reasonix Stop is non-gating)", "timeout": 5000,
                }],
            }
        }
    _h = lambda cmd: {"hooks": [{"type": "command", "command": cmd}]}
    return {
        "hooks": {
            "UserPromptSubmit": [_h(q_status)],
            "PreToolUse": [
                {"matcher": "Write|Edit|MultiEdit|Bash|Agent|Task", **_h(q_pre_snapshot)},
                {"matcher": "Write|Edit|MultiEdit",                 **_h(q_scope_check)},
                {"matcher": "Bash",                                 **_h(q_bash_guard)},
            ],
            "PostToolUse": [
                {"matcher": "Write|Edit|MultiEdit|Bash|Agent|Task", **_h(q_capture)},
            ],
            "Stop": [_h(q_review_gate)],
        },
        "permissions": {
            "allow": [
                "Bash(aiwf:*)",
                "Bash(scripts/aiwf_status.py:*)",
                "Bash(scripts/aiwf_pre_snapshot.py:*)",
                "Bash(scripts/aiwf_scope_check.py:*)",
                "Bash(scripts/aiwf_bash_guard.py:*)",
                "Bash(scripts/aiwf_capture_evidence.py:*)",
                "Bash(scripts/aiwf_review_gate.py:*)",
                "Read(.aiwf/**)",
                "Write(.aiwf/**)",
                "Edit(.aiwf/**)",
            ]
        },
    }


def _write_settings(target: EmbedTarget | None = None) -> Path:
    target = target or _target("claude")
    d = _config_dir(target)
    d.mkdir(parents=True, exist_ok=True)
    settings = _build_settings_json(target)
    target = d / "settings.json"
    if target.exists():
        existing = json.loads(target.read_text(encoding="utf-8"))
        new_hooks = settings.get("hooks", {})
        existing.setdefault("hooks", {})
        for event_name, matcher_entries in new_hooks.items():
            existing["hooks"][event_name] = matcher_entries
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
    "aiwf-planner": "skills/aiwf-planner/SKILL.md",
    "aiwf-implement": "skills/aiwf-implement/SKILL.md",
    "aiwf-test": "skills/aiwf-test/SKILL.md",
    "aiwf-review": "skills/aiwf-review/SKILL.md",
    "aiwf-close": "skills/aiwf-close/SKILL.md",
    "aiwf-architect": "skills/aiwf-architect/SKILL.md",
    "aiwf-explore": "skills/aiwf-explore/SKILL.md",
    "aiwf-curate": "skills/aiwf-curate/SKILL.md",
}

AGENT_TEMPLATES = {
    "aiwf-explorer.md": "agents/aiwf-explorer.md",
    "aiwf-executor.md": "agents/aiwf-executor.md",
    "aiwf-tester.md": "agents/aiwf-tester.md",
    "aiwf-reviewer.md": "agents/aiwf-reviewer.md",
    "aiwf-curator.md": "agents/aiwf-curator.md",
}

SCRIPT_TEMPLATES = {
    "aiwf_status.py": "scripts/aiwf_status.py",
    "aiwf_pre_snapshot.py": "scripts/aiwf_pre_snapshot.py",
    "aiwf_scope_check.py": "scripts/aiwf_scope_check.py",
    "aiwf_bash_guard.py": "scripts/aiwf_bash_guard.py",
    "aiwf_capture_evidence.py": "scripts/aiwf_capture_evidence.py",
    "aiwf_review_gate.py": "scripts/aiwf_review_gate.py",
}


def _template_text(relative_path: str) -> str:
    return (_TEMPLATE_ROOT / relative_path).read_text(encoding="utf-8")


def _reasonix_semantic_text(text: str) -> str:
    """Adapt Claude-only gate semantics before applying product-name substitutions."""
    text = text.replace(
        "The **Stop hook** (`scripts/aiwf_review_gate.py`) mechanically verifies all gates only after "
        "`prepare-close` sets `close_attempt=true`. Claude Code can then block Stop; an ordinary Stop "
        "without a close attempt is not treated as workflow closure. Reasonix Stop is non-gating, so "
        "`prepare-close` is the authoritative Reasonix closure gate.",
        "The **Stop hook** (`scripts/aiwf_review_gate.py`) reports gate status but is non-gating in "
        "Reasonix. It never blocks closure, regardless of `close_attempt`; successful `prepare-close` "
        "is the authoritative Reasonix closure gate.",
    ).replace(
        "Claude Stop revalidates and can block only when `close_attempt=true`; an ordinary stop before "
        "prepare-close does not manufacture a closure attempt. Reasonix Stop only reports, so successful "
        "`prepare-close` is authoritative there.",
        "Reasonix Stop never blocks closure, regardless of `close_attempt`; successful `prepare-close` "
        "is authoritative.",
    ).replace(
        "Claude Stop revalidates and can block only when `close_attempt=true`; ordinary Stop does not "
        "create a closure attempt. Reasonix Stop reports only.",
        "Reasonix Stop never blocks closure, regardless of `close_attempt`; successful `prepare-close` "
        "is authoritative.",
    ).replace(
        "`prepare-close` is authoritative; Claude Stop checks close_attempt again.",
        "`prepare-close` is authoritative; Reasonix Stop is report-only.",
    ).replace(
        "Reasonix Stop is non-gating, so `prepare-close` is the authoritative Reasonix closure gate.",
        "Reasonix Stop never blocks closure, regardless of `close_attempt`; successful `prepare-close` "
        "is the authoritative Reasonix closure gate.",
    )
    return "\n".join(line for line in text.splitlines() if not line.startswith("- Claude Stop"))


def _target_template_text(relative_path: str, target: EmbedTarget) -> str:
    text = _template_text(relative_path)
    text = _inject_shared_partials(relative_path, text)
    if target.mode == "reasonix":
        text = _reasonix_semantic_text(text)
        text = text.replace("Claude Code", "Reasonix")
        text = text.replace("Claude-compatible", "Reasonix-compatible")
        text = text.replace("Claude", "Reasonix")
        if relative_path.startswith("skills/"):
            text = _reasonix_skill_text(relative_path, text)
    return text


SHARED_PARTIALS = {
    "skills/aiwf-planner/SKILL.md": ["shared/connection_recovery_planner.md"],
    "skills/aiwf-implement/SKILL.md": ["shared/connection_recovery_implement.md"],
    "skills/aiwf-test/SKILL.md": ["shared/connection_recovery_test.md"],
    "skills/aiwf-review/SKILL.md": ["shared/connection_recovery_review.md"],
    "skills/aiwf-architect/SKILL.md": ["shared/connection_recovery_architect.md"],
    "agents/aiwf-executor.md": ["shared/connection_recovery_implement.md"],
    "agents/aiwf-tester.md": ["shared/connection_recovery_test.md"],
    "agents/aiwf-reviewer.md": ["shared/connection_recovery_review.md"],
}


def _inject_shared_partials(relative_path: str, text: str) -> str:
    partials = SHARED_PARTIALS.get(relative_path, [])
    if not partials:
        return text
    blocks = [_template_text(path).rstrip("\n") for path in partials]
    return text.rstrip("\n") + "\n\n" + "\n\n".join(blocks) + "\n"


REASONIX_SUBAGENT_SKILL_CONFIG = {
    "aiwf-implement": {
        "runAs": "subagent",
        "allowed-tools": "read,write,edit_file,bash,glob",
        "model": "deepseek-chat",
    },
    "aiwf-test": {
        "runAs": "subagent",
        "allowed-tools": "read,bash,glob",
        "model": "deepseek-chat",
    },
    "aiwf-review": {
        "runAs": "subagent",
        "allowed-tools": "read,bash,glob",
        "model": "deepseek-chat",
    },
    "aiwf-architect": {
        "runAs": "subagent",
        "allowed-tools": "read,bash,glob",
        "model": "deepseek-chat",
    },
    "aiwf-explore": {
        "runAs": "subagent",
        "allowed-tools": "read,bash,glob",
        "model": "deepseek-chat",
    },
    "aiwf-curate": {
        "runAs": "subagent",
        "allowed-tools": "read,glob",
        "model": "deepseek-chat",
    },
    "aiwf-close": {
        "runAs": "inline",
    },
    "aiwf-planner": {
        "runAs": "inline",
    },
}


def _reasonix_skill_text(relative_path: str, text: str) -> str:
    skill_name = relative_path.split("/")[1]
    config = REASONIX_SUBAGENT_SKILL_CONFIG.get(skill_name, {})
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
    paths = []
    for skill_name, template_path in SKILL_TEMPLATES.items():
        skill_dir = d / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path = skill_dir / "SKILL.md"
        write_text(skill_path, _target_template_text(template_path, target_config))
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
        write_text(agent_path, _target_template_text(template_path, target_config))
        paths.append(agent_path)
    return paths


# ── .aiwf state files (MVP: 7 files only) ──────────────────────────────

def _write_state_files() -> List[Path]:
    d = _aiwf_dir()
    d.mkdir(parents=True, exist_ok=True)
    # Create all subdirectories
    for subdir in ALL_DIRS:
        (d / subdir).mkdir(parents=True, exist_ok=True)
    paths = []
    # Map state files to new subdirectory paths
    file_paths = {
        "state.json": d / "state" / "state.json",
        "goal.json": d / "state" / "goal.json",
        "contexts.json": d / "state" / "contexts.json",
        "fix-loop.json": d / "state" / "fix-loop.json",
        "evidence.json": d / "evidence" / "records.json",
        "testing.json": d / "quality" / "testing.json",
        "review.json": d / "quality" / "review.json",
    }
    for filename, default_fn in MVP_STATE_FILES.items():
        target = file_paths.get(filename, d / filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            # Only create missing files — never overwrite existing user data.
            # The --force flag regenerates scripts/settings, not state data.
            write_json(target, default_fn())
            paths.append(target)
    return paths


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
        content = _reasonix_semantic_text(content)
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
    """Migrate .aiwf/ files from flat v1 layout to v2 subdirectory layout."""
    root = _project_root()
    aiwf = root / ".aiwf"
    if not aiwf.exists():
        return

    legacy_map = {
        "state.json": "state/state.json",
        "goal.json": "state/goal.json",
        "contexts.json": "state/contexts.json",
        "fix-loop.json": "state/fix-loop.json",
        "evidence.json": "evidence/records.json",
        "testing.json": "quality/testing.json",
        "review.json": "quality/review.json",
        "task-history.json": "history/task-history.json",
        "task-ledger.json": "history/task-ledger.json",
        "current-state.md": "reports/当前状态.md",
        "report.md": "reports/闭合报告.md",
        "quality-digest.md": "reports/质量摘要.md",
        "PROJECT-MAP.md": "reports/项目地图.md",
        "baseline.json": "internal/baseline.json",
    }

    migrated = []
    for old_name, new_path in legacy_map.items():
        old = aiwf / old_name
        new = aiwf / new_path
        if old.exists() and not new.exists():
            new.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.move(str(old), str(new))
            migrated.append(f"{old_name} -> {new_path}")
    # Clean up any remaining flat-path orphans (written by old code after partial migration)
    orphan_cleanup = [
        "state.json", "goal.json", "contexts.json", "fix-loop.json",
        "evidence.json", "testing.json", "review.json",
        "task-history.json", "task-ledger.json",
        "current-state.md", "report.md", "quality-digest.md", "PROJECT-MAP.md",
        "baseline.json", "ideas.md",
    ]
    for orphan in orphan_cleanup:
        old_path = aiwf / orphan
        new_path = aiwf / legacy_map.get(orphan, "")
        if old_path.exists() and new_path and (aiwf / new_path).exists():
            old_path.unlink()
            migrated.append(f"cleaned orphan: {orphan}")

    if migrated:
        print(f"aiwf: migrated {len(migrated)} files to v2 layout")
        for m in migrated:
            print(f"  {m}")

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
    _tk_cfg = _aiwf_dir() / "internal" / "toolkit-path.txt"
    _tk_cfg.parent.mkdir(parents=True, exist_ok=True)
    _tk_cfg.write_text(str(_aiwf_toolkit_root()))
    results["created"].append(rel(_tk_cfg))

    # Brownfield scan: if project isn't empty, run full bootstrap
    try:
        project_files = list(_project_root().glob("*"))
        ignored = {".aiwf", ".claude", ".reasonix", ".git", ".DS_Store"}
        non_aiwf = [p for p in project_files if p.name not in ignored]
        if non_aiwf:
            from .core.state_ops import bootstrap_project
            bootstrap_project(str(_project_root()))
            results["created"].append(rel(_project_root() / ".aiwf" / "history" / "task-history.json"))
    except Exception:
        pass

    # Write human-readable README
    readme_path = _aiwf_dir() / "README.md"
    if not readme_path.exists() or force:
        readme_path.write_text(_template_text("README.md"), encoding="utf-8")
        results["created"].append(rel(readme_path))

    # Auto-init PROJECT-MAP if missing
    from .core.project_map import ensure_project_map
    pm_path = ensure_project_map(str(_project_root()))
    if pm_path.exists():
        results["created"].append(rel(pm_path))

    # Auto-init idea inbox if missing
    from .core.ideas import ensure_ideas_file
    ideas_path = ensure_ideas_file(str(_project_root()))
    if ideas_path.exists():
        results["created"].append(rel(ideas_path))

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
    root = _project_root()
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

    for skill in ["aiwf-planner", "aiwf-implement", "aiwf-test", "aiwf-review", "aiwf-close", "aiwf-architect", "aiwf-explore", "aiwf-curate"]:
        path = root / target.config_dir / "skills" / skill / "SKILL.md"
        exists = path.exists()
        has_frontmatter = False
        if exists:
            content = path.read_text(encoding="utf-8")
            has_frontmatter = content.startswith("---")
        checks["skills"][skill] = {"exists": exists, "has_frontmatter": has_frontmatter}

    if target.mode == "claude":
        for agent in ["aiwf-explorer", "aiwf-executor", "aiwf-tester", "aiwf-reviewer", "aiwf-curator"]:
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
            for event_name in ["UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"]:
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
            for ev in ["UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"]:
                checks["hooks"][ev] = {"configured": False, "valid_schema": False}

    state_paths = {
        "state.json": STATE_JSON,
        "goal.json": GOAL_JSON,
        "contexts.json": CONTEXTS_JSON,
        "fix-loop.json": FIX_LOOP_JSON,
        "evidence.json": EVIDENCE_JSON,
        "testing.json": TESTING_JSON,
        "review.json": REVIEW_JSON,
    }
    for sf in MVP_STATE_FILES:
        path = root / state_paths.get(sf, f".aiwf/{sf}")
        checks["state_files"][sf] = path.exists()

    for script in ["aiwf_status.py", "aiwf_pre_snapshot.py", "aiwf_scope_check.py",
                    "aiwf_bash_guard.py", "aiwf_capture_evidence.py",
                    "aiwf_review_gate.py"]:
        path = root / "scripts" / script
        exists = path.exists()
        executable = exists and (path.stat().st_mode & 0o111)
        checks["scripts"][script] = {"exists": exists, "executable": executable}

    all_ok = (
        checks["instruction_md"]
        and checks["settings_json"]
        and all(v["exists"] and v["has_frontmatter"] for v in checks["skills"].values())
        and all(v["exists"] and v["has_frontmatter"] for v in checks["agents"].values())
        and all(v["configured"] and v["valid_schema"] for v in checks["hooks"].values())
        and all(checks["state_files"].values())
        and all(v["exists"] and v["executable"] for v in checks["scripts"].values())
    )
    checks["overall"] = "healthy" if all_ok else "issues_found"

    return checks


def show_status() -> str:
    root = _project_root()
    target = _detect_installed_target(root) or _target("claude")
    lines = [f"AIWF V{VERSION} — Embedded {target.product_name} Mode", ""]

    state_path = root / ".aiwf" / "state" / "state.json"
    if state_path.exists():
        state = read_json(state_path, {})
        lines.append(f"Project: {root}")
        lines.append(f"Goal: {state.get('active_goal', '(none)')}")
        lines.append(f"Phase: {state.get('phase', 'unknown')}")
        lines.append(f"Active context: {state.get('active_context_id', '(none)')}")
        lines.append(f"Scope violation: {state.get('scope_violation', False)}")
        lines.append(f"Close attempt: {state.get('close_attempt', False)}")
    else:
        lines.append(f"Project: {root}")
        lines.append(f"Not initialized. Run: aiwf install {target.mode}")

    lines.append("")
    lines.append("State files:")
    state_paths = {
        "state.json": STATE_JSON,
        "goal.json": GOAL_JSON,
        "contexts.json": CONTEXTS_JSON,
        "fix-loop.json": FIX_LOOP_JSON,
        "evidence.json": EVIDENCE_JSON,
        "testing.json": TESTING_JSON,
        "review.json": REVIEW_JSON,
    }
    for sf in MVP_STATE_FILES:
        state_rel = state_paths.get(sf, f".aiwf/{sf}")
        path = root / state_rel
        status = "✓" if path.exists() else "✗"
        lines.append(f"  {status} {state_rel}")

    lines.append("")
    if target.mode == "reasonix":
        lines.append("Skills: /skill aiwf-planner, /skill aiwf-implement, /skill aiwf-test, /skill aiwf-review, /skill aiwf-close")
    else:
        lines.append("Skills: /aiwf-planner, /aiwf-implement, /aiwf-test, /aiwf-review, /aiwf-close")
    lines.append("Scripts: scripts/aiwf_*.py")
    lines.append("")
    lines.append("Continue:")
    lines.append(f"  {target.planner_command}    # discuss with planner-main")
    lines.append("  aiwf doctor                            # check installation health")

    return "\n".join(lines) + "\n"


def _detect_installed_target(root: Path) -> EmbedTarget | None:
    for target in TARGETS.values():
        if (root / target.config_dir / "settings.json").exists():
            return target
    return None
