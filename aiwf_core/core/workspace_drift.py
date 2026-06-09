"""Workspace drift scan — low-frequency git-based workspace change detection.

Does NOT: read file contents, auto-adopt changes, generate evidence, auto-commit.
For Planner to use at phase boundaries, not every user turn.
"""
from __future__ import annotations
import json, subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Well-known manifest/dependency files — tracked regardless of extension
MANIFEST_NAMES = {
    "package.json", "requirements.txt", "Cargo.toml", "go.mod", "go.sum",
    "pyproject.toml", "Pipfile", "Pipfile.lock", "Gemfile", "Gemfile.lock",
    "CMakeLists.txt", "Makefile", "Dockerfile", "docker-compose.yml",
    "docker-compose.yaml", "setup.py", "setup.cfg", "renv.lock",
    "environment.yml", "environment.yaml", "poetry.lock", "yarn.lock",
    "package-lock.json", "composer.json", "composer.lock", "mix.exs",
    "rebar.config", "stack.yaml", "cabal.project", "WORKSPACE", "BUILD",
}

GOV_PREFIXES = [".aiwf/", ".claude/", ".reasonix/", "scripts/aiwf_", "CLAUDE.md", "REASONIX.md", "AGENTS.md"]


def _is_gov(path: str) -> bool:
    for p in GOV_PREFIXES:
        if path == p.rstrip("/") or path.startswith(p): return True
    return False


def _now():
    return datetime.now(timezone.utc).isoformat()



def _scan_non_git(root: Path, result: Dict[str, Any]) -> Dict[str, Any]:
    """Non-git fallback: detect changes via file mtime snapshot comparison."""
    result["mode"] = "mtime_snapshot"
    result["is_git_repo"] = False

    snapshot_path = root / ".aiwf" / "internal" / "file-snapshot.json"
    exclude = {".git", ".aiwf", ".claude", ".reasonix", "__pycache__", "node_modules", ".venv", "venv",
               ".pytest_cache", ".mypy_cache", ".ruff_cache", "dist", "build", ".DS_Store",
               "htmlcov", "*.egg-info"}

    # Build current file → mtime map
    current_snapshot: Dict[str, float] = {}
    for f in root.rglob("*"):
        if f.is_file() and not any(e in f.parts for e in exclude):
            try:
                rel = str(f.relative_to(root))
                current_snapshot[rel] = f.stat().st_mtime
            except OSError:
                pass

    # Load previous snapshot
    prev_snapshot: Dict[str, float] = {}
    if snapshot_path.exists():
        try:
            prev_snapshot = json.loads(snapshot_path.read_text()).get("files", {})
        except Exception:
            pass

    if not prev_snapshot:
        # First scan: just save snapshot, nothing to compare
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(
            json.dumps({"scanned_at": _now(), "files": current_snapshot}, indent=2))
        result["dirty"] = False
        result["needs_planner_review"] = False
        result["mode"] = "mtime_snapshot_first_scan"
        return result

    # Compare: added, deleted, modified (mtime changed)
    prev_files = set(prev_snapshot.keys())
    curr_files = set(current_snapshot.keys())

    added = curr_files - prev_files
    deleted = prev_files - curr_files
    modified = {
        f for f in (curr_files & prev_files)
        if abs(current_snapshot[f] - prev_snapshot[f]) > 0.01  # sub-second tolerance
    }

    for f in added:
        gov = _is_gov(f)
        entry = {"path": f, "status": "added"}
        if gov:
            result["governance_changes"].append(entry)
        else:
            result["project_changes"].append(entry)

    for f in deleted:
        gov = _is_gov(f)
        entry = {"path": f, "status": "deleted"}
        if gov:
            result["governance_changes"].append(entry)
        else:
            result["project_changes"].append(entry)
            result["deleted"].append(f)

    for f in modified:
        gov = _is_gov(f)
        entry = {"path": f, "status": "modified"}
        if gov:
            result["governance_changes"].append(entry)
        else:
            result["project_changes"].append(entry)

    result["dirty"] = bool(result["project_changes"] or result["governance_changes"])
    result["needs_planner_review"] = result["dirty"]

    # Save updated snapshot
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        json.dumps({"scanned_at": _now(), "files": current_snapshot}, indent=2))

    return result

def scan_workspace_drift(project_root: str) -> Dict[str, Any]:
    root = Path(project_root)
    result = {"schema_version": 1, "scanned_at": _now(), "is_git_repo": False,
              "git_head": "", "dirty": False, "project_changes": [],
              "governance_changes": [], "untracked": [], "deleted": [],
              "renamed": [], "needs_planner_review": False}

    # Check if git repo
    is_git = False
    try:
        r = subprocess.run(["git", "rev-parse", "--git-dir"], capture_output=True,
                           text=True, cwd=str(root), timeout=5)
        if r.returncode == 0:
            is_git = True
    except Exception:
        pass

    if not is_git:
        return _scan_non_git(root, result)

    result["is_git_repo"] = True

    # Get HEAD
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                           text=True, cwd=str(root), timeout=5)
        if r.returncode == 0: result["git_head"] = r.stdout.strip()
    except: pass

    # Get status
    try:
        r = subprocess.run(["git", "status", "--short", "--untracked-files=all"],
                           capture_output=True, text=True, cwd=str(root), timeout=5)
        if r.returncode != 0: return result
        for line in r.stdout.split("\n"):
            if not line.strip(): continue
            if len(line) < 3: continue
            st = line[:2].strip()
            rest = line[3:].strip()
            if " -> " in rest: rest = rest.split(" -> ")[-1]  # renamed
            if not rest: continue

            entry = {"path": rest, "status": "modified"}
            gov = _is_gov(rest)

            if "?" in st:  # untracked
                result["untracked"].append(rest)
                entry["status"] = "untracked"
            elif "D" in st:
                result["deleted"].append(rest)
                entry["status"] = "deleted"
            elif "R" in st:
                result["renamed"].append(rest)
                entry["status"] = "renamed"
            elif "M" in st or "A" in st:
                entry["status"] = "modified" if "M" in st else "added"

            if gov: result["governance_changes"].append(entry)
            else: result["project_changes"].append(entry)

        result["dirty"] = bool(result["project_changes"] or result["governance_changes"]
                               or result["untracked"])
        result["needs_planner_review"] = result["dirty"]
    except: pass

    return result


def write_workspace_drift(project_root: str, drift: Dict) -> Path:
    root = Path(project_root)
    path = root / ".aiwf" / "internal" / "workspace-drift.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(drift, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_workspace_drift(project_root: str) -> Dict:
    path = Path(project_root) / ".aiwf" / "internal" / "workspace-drift.json"
    if not path.exists(): return {"scanned_at": "", "needs_planner_review": False, "dirty": False}
    try: return json.loads(path.read_text(encoding="utf-8"))
    except: return {"scanned_at": "", "needs_planner_review": False, "dirty": False}


def auto_update_baseline(project_root: str) -> Dict[str, Any]:
    """After detecting drift, update baseline assets based on change magnitude.

    Small (1-2 files modified, no new/deleted): update task-history baseline only.
    Medium (3-5 files, or new/deleted files, module changes): + current-state rebuild.
    Large (>5 files, new modules, dependency changes): + env scan + capability scan.

    Human PROJECT-MAP.md is Planner-curated and is not overwritten here.
    Mechanically generated human summaries such as current-state.md may be rebuilt.
    Machine-readable files (.json) are freely updated to maintain integrity.
    """
    root = Path(project_root)
    result: Dict[str, Any] = {"updated": [], "skipped": [], "magnitude": "none"}

    # ── 1. Scan current code files ──
    code_files = []
    exclude = {".git", ".aiwf", ".claude", ".reasonix", "__pycache__", "node_modules", ".venv", "venv",
               ".pytest_cache", ".mypy_cache", "dist", "build", ".DS_Store", ".ruff_cache",
               "htmlcov", "*.egg-info"}
    for f in root.rglob("*"):
        if f.is_file() and not any(e in f.parts for e in exclude):
            if f.suffix in (".py", ".js", ".ts", ".go", ".rs", ".java", ".rb", ".sh",
                           ".md", ".toml", ".yaml", ".json"):
                rel = str(f.relative_to(root))
                code_files.append(rel)

    # Secondary scan: known manifest files regardless of extension
    for f in root.rglob("*"):
        if f.is_file() and not any(e in f.parts for e in exclude):
            if f.name in MANIFEST_NAMES:
                rel = str(f.relative_to(root))
                if rel not in code_files:
                    code_files.append(rel)

    if not code_files:
        result["reason"] = "no code files"
        return result

    # ── 2. Load existing baseline from task-history ──
    history_path = root / ".aiwf" / "history" / "task-history.json"
    history: Dict[str, Any] = {"tasks": [], "archived_hotspots": {}}
    if history_path.exists():
        try:
            history = json.loads(history_path.read_text())
        except Exception:
            pass

    tasks = history.get("tasks", [])
    existing_baseline_files: Set[str] = set()
    has_baseline = False
    for t in tasks:
        if t.get("bootstrap"):
            existing_baseline_files = set(t.get("changed_files", []) or [])
            has_baseline = True
            break

    # First run with no prior baseline: create one, update snapshot, return
    if not has_baseline:
        from datetime import datetime, timezone as _tz
        tasks.insert(0, {
            "id": "BASELINE-001",
            "title": f"[Bootstrap] Initial baseline {datetime.now(_tz.utc).strftime('%Y-%m-%d %H:%M')}",
            "changed_files": code_files[:100],
            "testing_status": "n/a",
            "review_result": "n/a",
            "bootstrap": True,
            "closed_at": datetime.now(_tz.utc).isoformat(),
        })
        history["tasks"] = tasks
        import json as _json
        history_path.write_text(_json.dumps(history, indent=2))
        # Create PROJECT-MAP snapshot for initial baseline
        try:
            modules_init: Dict[str, List[str]] = {}
            for f in code_files:
                mod = f.split("/")[0] if "/" in f else "root"
                modules_init.setdefault(mod, []).append(f)
            from .project_map import update_project_map_section
            update_project_map_section(
                project_root, "snapshot",
                f"- {len(code_files)} source files across {len(modules_init)} modules: {', '.join(sorted(modules_init.keys())[:8])}"
            )
            result["updated"].append(f"PROJECT-MAP snapshot initialized ({len(modules_init)} modules)")
        except Exception:
            pass
        result["magnitude"] = "initial"
        result["updated"].append("task-history baseline created")
        return result

    # ── 3. Compute delta ──
    current_set = set(code_files)
    existing_set = existing_baseline_files

    added = current_set - existing_set
    deleted = existing_set - current_set

    def _modules(files: Set[str]) -> Set[str]:
        mods: Set[str] = set()
        for f in files:
            mod = f.split("/")[0] if "/" in f else "root"
            mods.add(mod)
        return mods

    current_modules = _modules(current_set)
    existing_modules = _modules(existing_set) if existing_set else set()
    new_modules = current_modules - existing_modules
    removed_modules = existing_modules - current_modules

    # Dependency/manifest files — changes here signal structural shifts
    dep_filenames = {
        "package.json", "requirements.txt", "Cargo.toml", "go.mod", "go.sum",
        "pyproject.toml", "Pipfile", "Pipfile.lock", "Gemfile", "Gemfile.lock",
        "CMakeLists.txt", "Makefile", "Dockerfile", "docker-compose.yml",
        "docker-compose.yaml", "setup.py", "setup.cfg", "renv.lock",
    }
    dep_changes = [f for f in (added | deleted) if Path(f).name in dep_filenames]

    change_count = len(added) + len(deleted)

    # ── 4. Determine magnitude ──
    if change_count == 0 and not new_modules and not removed_modules:
        result["magnitude"] = "none"
        result["reason"] = "no file changes detected since baseline"
        return result

    # Large signals: new modules, removed modules, dependency changes, or >5 file delta
    if new_modules or removed_modules or dep_changes or change_count > 5:
        magnitude = "large"
    elif change_count > 2 or deleted:
        # 3-5 files changed, or any file deleted (not just added)
        magnitude = "medium"
    else:
        # 1-2 files added/modified, no deletions, no structural changes
        magnitude = "small"

    result["magnitude"] = magnitude
    result["delta"] = {
        "added": len(added), "deleted": len(deleted),
        "new_modules": sorted(new_modules)[:10],
        "removed_modules": sorted(removed_modules)[:10],
        "dep_changes": dep_changes[:5] if dep_changes else [],
    }

    # ── 5. Execute refresh ──
    from datetime import datetime, timezone

    # --- ALWAYS: update task-history baseline (machine JSON) ---
    baseline_updated = False
    for t in tasks:
        if t.get("bootstrap"):
            t["changed_files"] = code_files[:100]
            t["title"] = f"[Bootstrap] Updated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"
            result["updated"].append("task-history baseline refreshed")
            baseline_updated = True
            break
    if not baseline_updated:
        tasks.insert(0, {
            "id": "BASELINE-001",
            "title": "[Bootstrap] Existing codebase baseline",
            "changed_files": code_files[:100],
            "testing_status": "n/a",
            "review_result": "n/a",
            "bootstrap": True,
            "closed_at": datetime.now(timezone.utc).isoformat(),
        })
        result["updated"].append("task-history baseline created")

    history["tasks"] = tasks
    import json as _json
    history_path.write_text(_json.dumps(history, indent=2))

    if magnitude == "small":
        return result

    # PROJECT-MAP.md is human/Planner-facing and must be curated after source
    # inspection, not mechanically overwritten by drift bookkeeping.
        result["skipped"].append(f"current-state rebuild: {e}")

    if magnitude == "medium":
        return result

    # --- LARGE: env scan + capability scan (machine JSON) ---
    try:
        from .environment import scan_environment, write_environment_profile
        env = scan_environment(project_root)
        write_environment_profile(project_root, env)
        result["updated"].append("environment profile refreshed")
        if env.get("known_environment_risks"):
            result["env_risks"] = len(env["known_environment_risks"])
    except Exception as e:
        result["skipped"].append(f"env scan: {e}")

    try:
        from .capabilities import discover_capabilities, write_capabilities_registry
        caps = discover_capabilities(project_root)
        write_capabilities_registry(project_root, caps)
        cap_count = len(caps.get("capabilities", []))
        result["updated"].append(f"capability registry refreshed ({cap_count} capabilities)")
    except Exception as e:
        result["skipped"].append(f"capability scan: {e}")

    return result
