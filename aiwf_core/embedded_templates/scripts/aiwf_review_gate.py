
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
