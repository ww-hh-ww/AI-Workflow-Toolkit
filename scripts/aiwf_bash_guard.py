#!/usr/bin/env python3
import sys, os
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
import json, sys
from pathlib import Path
from aiwf_core.adapters.claude.normalize_event import parse_claude_stdin, normalize
from aiwf_core.hooks.common.scope_checker import check_bash
from aiwf_core.adapters.claude.responses import allow, deny_pre_tool_use

def main():
    data = parse_claude_stdin()
    if not data:
        allow()

    event = normalize(data)
    if event.tool_name != "Bash":
        allow()

    result = check_bash(event)

    if result["decision"] == "deny":
        deny_pre_tool_use(
            f"AIWF Bash guard blocked: {result['command'][:100]}\n"
            f"Reason: {result['reason']} (pattern: {result['matched_pattern']})\n"
            "If this command is necessary, request approval from planner-main."
        )

    if result["decision"] == "ask":
        # For 'ask', we still allow but with a system message warning
        print(json.dumps({
            "systemMessage": f"AIWF: {result['reason']} — command: {result['command'][:80]}"
        }))
        sys.exit(0)

    allow()

if __name__ == "__main__":
    main()
