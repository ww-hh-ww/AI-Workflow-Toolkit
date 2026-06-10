"""Command-line interface for AIWF."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from .commands.flow import cmd_status
from .commands.parser import build_parser
from .constants import VERSION
from .core.state_schema import MVP_STATE_FILES


def cmd_init(args: argparse.Namespace) -> None:
    root = Path.cwd()
    state_dir = root / ".aiwf"
    state_dir.mkdir(parents=True, exist_ok=True)
    created = []
    for filename, default_fn in MVP_STATE_FILES.items():
        target = state_dir / filename
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(default_fn(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            created.append(target)
    print(f"# AIWF V{VERSION} embedded state initialized")
    print()
    if created:
        print("Created:")
        for path in created:
            print(f"- {path.relative_to(root)}")
    else:
        print("No state files needed creation.")
    print()
    print("Next: aiwf install reasonix  # install skills, hooks, agents, and scripts")


def _show_planner_facade() -> None:
    """Default aiwf output: embedded mainline status or install guidance."""
    root = Path.cwd()
    aiwf_state_path = root / ".aiwf" / "state" / "state.json"
    claude_settings = root / ".claude" / "settings.json"
    reasonix_settings = root / ".reasonix" / "settings.json"
    if aiwf_state_path.exists() and (reasonix_settings.exists() or claude_settings.exists()):
        cmd_status(argparse.Namespace())
        return
    print(f"AIWF V{VERSION} — Embedded Reasonix Workflow Governance")
    print()
    print("No embedded AIWF installation found in this project.")
    print()
    print("Start here:")
    print("  aiwf install reasonix")
    print("  reasonix code .")
    print('  /skill aiwf-planner "describe your goal"')
    print()
    print("Useful checks after install:")
    print("  aiwf doctor")
    print("  aiwf status")


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        try:
            _show_planner_facade()
            return 0
        except SystemExit:
            return 1
    if argv[0] in {"--version", "version"}:
        print(f"AIWF V{VERSION}")
        return 0
    known = {"init", "install", "doctor", "status", "state", "cleanup", "plan", "task", "fixloop", "arch-change", "capability", "recipe", "research", "env", "quality", "idea", "rule", "project-map", "memory", "git", "checkpoint", "goal", "workspace", "asset"}
    if argv and argv[0] not in known and not argv[0].startswith("-"):
        print(f"Unknown command: {argv[0]}", file=sys.stderr)
        print("Primary path: aiwf install reasonix → reasonix code . → /skill aiwf-planner", file=sys.stderr)
        return 2
    parser = build_parser(cmd_init)
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
