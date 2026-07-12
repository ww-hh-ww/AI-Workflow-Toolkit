
import json, sys
from pathlib import Path
from aiwf_core.adapters.claude.normalize_event import parse_claude_stdin
from aiwf_core.hooks.common.gate_checker import eval_closure_gates
from aiwf_core.adapters.claude.responses import allow, block_stop

def main():
    data = parse_claude_stdin()
    cwd = Path(__file__).resolve().parent.parent

    if not (cwd / ".aiwf" / "state" / "state.json").exists():
        allow()

    gates = eval_closure_gates(cwd)

    if gates["passed"]:
        allow()

    # Outside the closing stage there is no Stop gate to enforce.
    if not gates["blockers"]:
        allow()

    block_stop(
        "AIWF closure gates not met:\n" +
        "\n".join(f"  - {b}" for b in gates["blockers"])
    )

if __name__ == "__main__":
    main()
