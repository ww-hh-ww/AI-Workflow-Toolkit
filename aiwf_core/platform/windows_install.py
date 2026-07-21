"""Windows compatibility pass for an embedded Claude Code installation."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict


def _managed_script(command: str) -> tuple[str, list[str]] | None:
    normalized = str(command or "").replace("\\", "/")
    marker = "/scripts/aiwf_"
    if marker not in normalized:
        return None
    quoted = normalized.split('"')
    script = next((item for item in quoted if marker in item.replace("\\", "/")), "")
    if not script:
        return None
    suffix = normalized[normalized.find(script) + len(script):].strip('" ')
    return script, suffix.split() if suffix else []


def _rewrite_handler(handler: Any) -> None:
    if not isinstance(handler, dict):
        return
    parsed = _managed_script(str(handler.get("command") or ""))
    if not parsed:
        return
    script, args = parsed
    handler["command"] = sys.executable
    handler["args"] = [script, *args]


def apply_windows_claude_compat(project_root: Path) -> Path:
    """Use Claude's shell-free hook form so Windows paths need no quoting."""
    settings_path = project_root / ".claude" / "settings.json"
    data: Dict[str, Any] = json.loads(settings_path.read_text(encoding="utf-8"))
    for groups in (data.get("hooks", {}) or {}).values():
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, dict):
                continue
            for handler in group.get("hooks", []) or []:
                _rewrite_handler(handler)
    settings_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return settings_path

