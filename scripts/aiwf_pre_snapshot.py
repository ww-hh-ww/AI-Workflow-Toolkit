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
from aiwf_core.hooks.common.snapshot import take_snapshot
from aiwf_core.adapters.claude.normalize_event import parse_claude_stdin, normalize

def _log(msg: str) -> None:
    print(f"[aiwf_pre_snapshot] {msg}", file=sys.stderr)
    try:
        _ah_diag(msg)
    except NameError:
        pass

def main():
    cwd = Path.cwd()
    tool_name = "unknown"
    tool_input = {}
    data = parse_claude_stdin()
    if data:
        try:
            event = normalize(data)
            cwd = Path(event.cwd or str(Path.cwd()))
            tool_name = event.tool_name or tool_name
            tool_input = event.tool_input or tool_input
            _log(f"stdin ok, tool={tool_name} cwd={cwd}")
        except Exception as exc:
            _log(f"normalize failed: {exc}, falling back to cwd={cwd}")
    else:
        _log(f"stdin empty, using cwd={cwd}")
    snap = take_snapshot(cwd, tool_name, tool_input)
    _log(f"snapshot written: {snap.get('file_count', 0)} files")
    sys.exit(0)

if __name__ == "__main__":
    main()
