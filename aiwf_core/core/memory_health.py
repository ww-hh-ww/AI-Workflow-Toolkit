"""Non-blocking structural checks for Planner memory."""
from __future__ import annotations

import re
from pathlib import Path
from typing import List


def memory_structure_warnings(root: Path) -> List[str]:
    memory_root = root / ".aiwf" / "memory"
    if not memory_root.is_dir():
        return ["missing .aiwf/memory directory"]

    warnings: List[str] = []
    facts_path = memory_root / "project-facts.md"
    index_path = memory_root / "MEMORY.md"
    notes_root = memory_root / "notes"

    if not facts_path.is_file():
        warnings.append("missing .aiwf/memory/project-facts.md")
    else:
        facts = facts_path.read_text(encoding="utf-8")
        word_count = len(facts.split())
        compact_chars = len("".join(facts.split()))
        if word_count > 100 or compact_chars > 800:
            warnings.append(
                "project-facts.md is too large for quick Planner use "
                f"({word_count} words, {compact_chars} non-space characters)"
            )

    if not index_path.is_file():
        warnings.append("missing .aiwf/memory/MEMORY.md")
        indexed_notes: set[str] = set()
    else:
        index_text = index_path.read_text(encoding="utf-8")
        indexed_notes = {
            match.replace("\\", "/")
            for match in re.findall(r"\]\((notes/[^)#]+\.md)(?:#[^)]+)?\)", index_text)
        }
        for relative in sorted(indexed_notes):
            if not (memory_root / relative).is_file():
                warnings.append(f"MEMORY.md links to missing note: {relative}")

    if not notes_root.is_dir():
        warnings.append("missing .aiwf/memory/notes directory")
    elif index_path.is_file():
        actual_notes = {
            path.relative_to(memory_root).as_posix()
            for path in notes_root.rglob("*.md")
            if path.is_file()
        }
        for relative in sorted(actual_notes - indexed_notes):
            warnings.append(f"memory note is not indexed in MEMORY.md: {relative}")

    return warnings
