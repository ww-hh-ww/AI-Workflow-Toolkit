"""Workspace layout migration — Stage 4.7.3.

Moves content from old flat .aiwf/ layout to new 5-zone layout.
"""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path
import sys


# ═══════════════════════════════════════════════════════════════════════════
# Migration mapping: old_top_dir → new_dir (relative from .aiwf/)
# ═══════════════════════════════════════════════════════════════════════════

_MIGRATION_MAP = {
    "plans": "plans",
    "internal": "runtime/internal",
}

_NEVER_MOVE = {"state", "assets", "archive", "artifacts", "runtime"}


def _cmd_workspace_migrate_layout(args: argparse.Namespace) -> None:
    base = Path.cwd()
    aiwf = base / ".aiwf"

    if not aiwf.is_dir():
        print("No .aiwf directory found.", file=sys.stderr)
        raise SystemExit(1)

    dry_run = getattr(args, "dry_run", False)

    moves = []
    for old_dir, new_dir in _MIGRATION_MAP.items():
        old_path = aiwf / old_dir
        if not old_path.is_dir():
            continue
        new_path = aiwf / new_dir
        # Skip if new path already exists and has content
        new_path.parent.mkdir(parents=True, exist_ok=True)
        moves.append((old_path, new_path, old_dir, new_dir))

    if not moves:
        print("Nothing to migrate — workspace already uses v2 layout.")
        return

    if dry_run:
        print(f"Dry run: {len(moves)} directories would be moved:")
        for old_path, new_path, old_dir, new_dir in moves:
            file_count = sum(1 for _ in old_path.rglob("*") if _.is_file())
            print(f"  .aiwf/{old_dir}/ → .aiwf/{new_dir}/  ({file_count} files)")
        print()
        print("Run without --dry-run to execute.")
        return

    # Execute migration
    moved_count = 0
    for old_path, new_path, old_dir, new_dir in moves:
        # Move files from old to new
        for item in list(old_path.iterdir()):
            dest = new_path / item.name
            if dest.exists():
                # Merge: don't overwrite existing
                if item.is_dir():
                    for sub in item.rglob("*"):
                        if sub.is_file():
                            rel = sub.relative_to(item)
                            dest_sub = dest / rel
                            if not dest_sub.exists():
                                dest_sub.parent.mkdir(parents=True, exist_ok=True)
                                shutil.move(str(sub), str(dest_sub))
            else:
                shutil.move(str(item), str(dest))
        # Remove old dir if empty
        if not any(old_path.iterdir()):
            old_path.rmdir()
        moved_count += 1

    # Generate migration report
    report_dir = aiwf / "artifacts" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report = report_dir / "workspace-layout-migration.md"
    report.write_text(
        "\n".join([
            "# Workspace Layout Migration",
            f"",
            f"Migrated {moved_count} directories from flat layout to 5-zone layout.",
            f"",
            f"## Target layout",
            f"- `state/` — Machine truth (unchanged)",
            f"- `artifacts/` — Human-readable outputs",
            f"- `runtime/` — Execution traces",
            f"- `assets/` — Input assets (unchanged)",
            f"- `archive/` — Deprecated material",
            f"",
            f"See `docs/AIWF_WORKSPACE_LAYOUT.md` for the full contract.",
        ]),
        encoding="utf-8",
    )

    print(f"Migration complete. {moved_count} directories moved.")
    print(f"Report: {report.relative_to(base)}")
