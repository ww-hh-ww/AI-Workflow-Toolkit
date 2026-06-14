"""Command-line interface for AIWF."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

from .commands.flow import cmd_status
from .commands.parser import build_parser
from .constants import VERSION
from .core.state_schema import MVP_STATE_FILES
from .core.project_root import resolve_aiwf_project_root


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
    print("Next: aiwf install claude (or reasonix)  # install skills, hooks, agents, and scripts")


def _show_planner_facade() -> None:
    """Default aiwf output: embedded mainline status or install guidance."""
    root = Path.cwd()
    aiwf_state_path = root / ".aiwf" / "state" / "state.json"
    claude_settings = root / ".claude" / "settings.json"
    reasonix_settings = root / ".reasonix" / "settings.json"
    if aiwf_state_path.exists() and (reasonix_settings.exists() or claude_settings.exists()):
        cmd_status(argparse.Namespace())
        return
    print(f"AIWF V{VERSION} — Embedded Workflow Governance")
    print()
    print("No embedded AIWF installation found in this project.")
    print()
    print("Start here:")
    print("  aiwf install claude      # Claude Code")
    print("  aiwf install reasonix    # Reasonix")
    print()
    print("Useful checks after install:")
    print("  aiwf doctor")
    print("  aiwf status")


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in {"install", "init", "--version", "version", "--help", "-h", "help"}:
        os.chdir(resolve_aiwf_project_root(Path.cwd()))
    if not argv:
        try:
            _show_planner_facade()
            return 0
        except SystemExit:
            return 1
    if argv[0] in {"--version", "version"}:
        print(f"AIWF V{VERSION}")
        return 0

    # Deprecation warning (show even with --help)
    from .core.command_manifest import COMMAND_MANIFEST, DEPRECATED, QUARANTINE
    cmd_name = argv[0]
    if cmd_name in COMMAND_MANIFEST and COMMAND_MANIFEST[cmd_name]["tier"] in (DEPRECATED, QUARANTINE):
        dep = COMMAND_MANIFEST[cmd_name].get("deprecation", "")
        label = "quarantined" if COMMAND_MANIFEST[cmd_name]["tier"] == QUARANTINE else "deprecated"
        print(f"Warning: '{cmd_name}' is {label}. {dep}", file=sys.stderr)

    # --help and help command: show tiered command list
    # But if a command name is given (e.g. "idea --help"), let it through to argparse
    is_bare_help = argv[0] in {"--help", "-h", "help"}
    is_subcommand_help = len(argv) >= 2 and argv[1] in {"--help", "-h"} and argv[0] not in {"--help", "-h", "help"}
    if is_bare_help or (is_subcommand_help and argv[0] == "help"):
        show_all = "--all" in argv or "-a" in argv
        _show_tiered_help(show_all)
        return 0

    known = set(COMMAND_MANIFEST.keys())
    # Also accept "next" which is a convenience alias
    known.add("next")
    if "audit-archive" not in known:
        known.add("audit-archive")
    if argv and argv[0] not in known and not argv[0].startswith("-"):
        print(f"Unknown command: {argv[0]}", file=sys.stderr)
        print("Run 'aiwf --help' to see available commands.", file=sys.stderr)
        return 2
    parser = build_parser(cmd_init)
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    args.func(args)
    return 0


def _show_tiered_help(show_all: bool = False) -> None:
    from .core.command_manifest import COMMAND_MANIFEST, PRIMARY, ADVANCED, INTERNAL, DEPRECATED, QUARANTINE
    from .constants import VERSION

    print(f"AIWF V{VERSION}")
    print()
    if show_all:
        print("All commands (--all):")
        print()
        for tier, label in [(PRIMARY, "Primary"), (ADVANCED, "Advanced"), (INTERNAL, "Internal"), (DEPRECATED, "Deprecated"), (QUARANTINE, "Quarantine")]:
            cmds = sorted(k for k, v in COMMAND_MANIFEST.items() if v["tier"] == tier)
            if not cmds:
                continue
            print(f"  {label}:")
            for cmd in cmds:
                entry = COMMAND_MANIFEST[cmd]
                core = entry["core"]
                if tier == DEPRECATED:
                    dep = f" [DEPRECATED: {entry.get('deprecation', '')[:60]}]"
                elif tier == QUARANTINE:
                    dep = f" [QUARANTINE: {entry.get('deprecation', '')[:60]}]"
                else:
                    dep = ""
                print(f"    {cmd:20s} → {core}{dep}")
            print()
    else:
        print("Primary commands:")
        print()
        primary = sorted(k for k, v in COMMAND_MANIFEST.items() if v["tier"] == PRIMARY)
        for cmd in primary:
            entry = COMMAND_MANIFEST[cmd]
            core = entry["core"]
            print(f"  {cmd:16s} {core}")
        print()
        print("Run 'aiwf --help --all' to see all commands.")
        print("Run 'aiwf <command> --help' for command-specific help.")
    print()
    print("Primary path:")
    print("  aiwf install claude      # Claude Code")
    print("  aiwf install reasonix    # Reasonix")


if __name__ == "__main__":
    raise SystemExit(main())
