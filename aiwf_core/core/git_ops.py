"""Git commit safety — summary, suggest, commit with safety gates."""
from __future__ import annotations
import json, subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from .state.goal_ops import get_active_goal
GOV_PREFIXES = [".aiwf/", ".claude/", ".reasonix/", "scripts/aiwf_", "CLAUDE.md", "REASONIX.md", "AGENTS.md"]

def _is_gov(p): return any(p == x.rstrip("/") or p.startswith(x) for x in GOV_PREFIXES)

def _run(cmd, cwd, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd), timeout=timeout)
        return r if r.returncode == 0 else None
    except: return None

def _rj(path, default=None):
    try: return json.loads(path.read_text()) if path.exists() else (default or {})
    except: return default or {}

def get_git_summary(project_root: str) -> Dict[str, Any]:
    root = Path(project_root)
    result = {"branch": "", "head": "", "dirty": False, "project_changes": 0,
              "governance_changes": 0, "untracked": 0, "stat": ""}
    br = _run(["git", "branch", "--show-current"], root)
    if br: result["branch"] = br.stdout.strip()
    hd = _run(["git", "rev-parse", "HEAD"], root)
    if hd: result["head"] = hd.stdout.strip()
    st = _run(["git", "status", "--short", "--untracked-files=all"], root)
    if st:
        proj, gov, unt = 0, 0, 0
        for line in st.stdout.split("\n"):
            if len(line) < 3: continue
            rest = line[3:].strip()
            if " -> " in rest: rest = rest.split(" -> ")[-1]
            if not rest: continue
            if "?" in line[:2]: unt += 1
            else:
                if _is_gov(rest): gov += 1
                else: proj += 1
        result["project_changes"] = proj
        result["governance_changes"] = gov
        result["untracked"] = unt
        result["dirty"] = bool(proj + gov + unt)
    ds = _run(["git", "diff", "--stat"], root)
    if ds: result["stat"] = ds.stdout.strip()[:500]
    return result


def suggest_commit_message(project_root: str) -> str:
    root = Path(project_root)
    goal = get_active_goal(project_root)
    gs = get_git_summary(project_root)
    current_goal = goal.get("current_goal") or goal.get("active_goal", "")
    if current_goal:
        return f"feat: {current_goal[:80]}"
    if gs["project_changes"] > 0:
        return f"chore: update {gs['project_changes']} project file(s)"
    if gs["governance_changes"] > 0:
        return "chore(aiwf): update governance state"
    return "chore: update"


def commit_with_confirmation(
    project_root: str, message: str,
    include_governance: bool = False, confirm: bool = False,
    require_closure: bool = True,
) -> Dict[str, Any]:
    root = Path(project_root)
    if not message: return {"error": "message is required", "status": "rejected"}
    if not confirm: return {"status": "rejected", "reason": "--confirm required to commit"}

    # Closure check
    state = _rj(root / ".aiwf" / "state" / "state.json")
    if require_closure and not state.get("closure_allowed"):
        return {"error": "closure not allowed; commit blocked", "status": "rejected"}

    # Check working tree
    gs = get_git_summary(project_root)
    if not gs["dirty"]:
        return {"error": "no changes to commit", "status": "rejected"}

    # Stage files
    if include_governance:
        _run(["git", "add", "-A"], root)
    else:
        # Only add project files
        st = _run(["git", "status", "--short", "--untracked-files=all"], root)
        if st:
            for line in st.stdout.split("\n"):
                if len(line) < 3: continue
                rest = line[3:].strip()
                if " -> " in rest: rest = rest.split(" -> ")[-1]
                if not rest: continue
                if not _is_gov(rest) and "?" not in line[:2]:
                    _run(["git", "add", rest], root)
        # Add untracked project files too
        if st:
            for line in st.stdout.split("\n"):
                if len(line) < 3: continue
                if "?" in line[:2]:
                    rest = line[3:].strip()
                    if rest and not _is_gov(rest):
                        _run(["git", "add", rest], root)

    r = _run(["git", "commit", "-m", message], root)
    if not r: return {"error": "git commit failed", "status": "failed"}
    hd = _run(["git", "rev-parse", "HEAD"], root)
    commit_hash = hd.stdout.strip() if hd else "unknown"

    # Record commit in report.md if it exists
    report_path = root / ".aiwf" / "records" / "闭合报告.md"
    if report_path.exists():
        existing = report_path.read_text(encoding="utf-8")
        entry = (f"\n## Git Commit\n\n"
                 f"- Commit: {commit_hash}\n"
                 f"- Message: {message}\n"
                 f"- Governance included: {str(include_governance).lower()}\n"
                 f"- Push: not performed\n")
        report_path.write_text(existing.rstrip() + "\n" + entry, encoding="utf-8")

    return {"status": "committed", "hash": commit_hash,
            "message": message, "include_governance": include_governance}
