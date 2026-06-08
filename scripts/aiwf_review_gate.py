#!/usr/bin/env python3
import sys
from pathlib import Path

# Add project root to sys.path for project-local imports.
_AH_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_AH_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AH_PROJECT_ROOT))

# Discover aiwf_core at runtime — no hardcoded paths.
# 1. Pip-installed aiwf_core is importable directly.
# 2. Otherwise, read the toolkit path recorded by aiwf install.
try:
    import aiwf_core  # noqa: F401
except ImportError:
    _TK_CFG = _AH_PROJECT_ROOT / ".aiwf" / "internal" / "toolkit-path.txt"
    if _TK_CFG.exists():
        _TK_ROOT = _TK_CFG.read_text().strip()
        if _TK_ROOT and Path(_TK_ROOT).exists() and _TK_ROOT not in sys.path:
            sys.path.insert(0, _TK_ROOT)
import json, sys
from pathlib import Path
from aiwf_core.adapters.claude.normalize_event import parse_claude_stdin
from aiwf_core.hooks.common.gate_checker import eval_closure_gates
from aiwf_core.adapters.claude.responses import allow, block_stop

def main():
    data = parse_claude_stdin()
    cwd = Path.cwd()
    if data:
        if data.get("cwd"):
            cwd = Path(data["cwd"])

    cs_exists = (cwd / ".aiwf" / "reports" / "当前状态.md").exists()
    if not (cwd / ".aiwf" / "state" / "state.json").exists():
        allow()

    gates = eval_closure_gates(cwd)

    if not gates["close_attempt"]:
        # Not trying to close — optionally warn but don't block
        issues = []
        if gates["scope_violation"]:
            issues.append("scope violation detected")
        if gates["fix_loop_open"]:
            issues.append("fix-loop is open")
        if issues:
            print(json.dumps({
                "systemMessage": f"AIWF: {'; '.join(issues)}. Resolve before closing."
            }))
        allow()

    if not gates["passed"]:
        block_stop(
            "AIWF closure gates not met:\n" +
            "\n".join(f"  - {b}" for b in gates["blockers"])
        )

    # Gates passed
    allow()

if __name__ == "__main__":
    main()
