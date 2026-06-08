"""AIWF Rollback Checkpoint — git-based, no auto-commit, restore with safety."""
from __future__ import annotations
import json, os, shutil, subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

GOV_PREFIXES = [".aiwf/", ".claude/", ".reasonix/", "scripts/aiwf_", "CLAUDE.md", "REASONIX.md", "AGENTS.md"]
CHECKPOINT_SELF = ".aiwf/checkpoints/"
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

def _now(): return datetime.now(timezone.utc).isoformat()
def _short(s): return s[:8] if s else "?"

def _is_gov(p): return any(p == x.rstrip("/") or p.startswith(x) for x in GOV_PREFIXES)
def _is_checkpoint(p): return p.startswith(CHECKPOINT_SELF)

def _run(cmd, cwd, timeout=15):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd), timeout=timeout)
        return r if r.returncode == 0 else None
    except: return None

def _current_untracked_files(root: Path) -> List[str]:
    r = _run(["git", "ls-files", "--others", "--exclude-standard"], root)
    if not r:
        return []
    return [line.strip() for line in r.stdout.splitlines() if line.strip()]

def _remove_untracked_before_restore(root: Path) -> None:
    """Remove current untracked files before restoring checkpoint content.

    A pre-restore backup checkpoint is created before this runs, so removed
    files remain recoverable. Checkpoint storage itself is never removed.
    """
    for rel in _current_untracked_files(root):
        if _is_checkpoint(rel):
            continue
        target = root / rel
        if target.is_file() or target.is_symlink():
            target.unlink(missing_ok=True)
        elif target.is_dir():
            shutil.rmtree(target, ignore_errors=True)

        parent = target.parent
        while parent != root and parent.exists():
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent

def create_checkpoint(project_root: str, label: str = "", include_governance: bool = True, mode: str = "patch") -> Dict:
    root = Path(project_root)
    ckpt_dir = root / ".aiwf" / "checkpoints"
    
    # Get git info
    head_r = _run(["git", "rev-parse", "HEAD"], root)
    git_head = head_r.stdout.strip() if head_r else ""
    branch_r = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], root)
    branch = branch_r.stdout.strip() if branch_r else ""
    
    # Status
    status_r = _run(["git", "status", "--short", "--untracked-files=all"], root)
    dirty = False
    project_files, gov_files, untracked_files, staged_files = [], [], [], []
    warnings = []
    
    if status_r:
        for line in status_r.stdout.split("\n"):
            if len(line) < 3: continue
            st = line[:2].strip()
            rest = line[3:].strip()
            if " -> " in rest: rest = rest.split(" -> ")[-1]
            if not rest: continue
            if _is_checkpoint(rest): continue  # exclude old checkpoints
            is_gov = _is_gov(rest)
            dirty = True  # any status line means dirty
            if "?" in st:
                untracked_files.append(rest)
                if is_gov: gov_files.append(rest)
                else: project_files.append(rest)
            elif "M" in st or "A" in st or "D" in st or "R" in st:
                pass  # dirty already set above
                if "M" in st[:1] and " " not in st: staged_files.append(rest)
                if is_gov: gov_files.append(rest)
                else: project_files.append(rest)

    chk_id = f"CHK-{_now().replace(':', '-').replace('.', '-')}"
    provider = "patch" if mode == "patch" else "git_stash"
    stash_ref, stash_hash = "", ""

    if mode == "stash" and dirty:
        stash_msg = f"aiwf checkpoint: {label or chk_id}"
        sr = _run(["git", "stash", "push", "-u", "-m", stash_msg], root)
        if not sr: return {"error": "git stash push failed", "status": "failed"}
        if sr:
            # Get the stash ref
            stash_list = _run(["git", "stash", "list"], root)
            if stash_list and "stash@{0}" in stash_list.stdout:
                stash_ref = "stash@{0}"
                # Get hash
                sh = _run(["git", "rev-parse", "stash@{0}"], root)
                if sh: stash_hash = sh.stdout.strip()
            # Apply stash back immediately to preserve working tree
            apply_r = _run(["git", "stash", "apply", "--index", "stash@{0}"], root)
            if not apply_r:
                return {"error": "stash was created but apply failed; inspect git stash list", "status": "failed"}
        if not stash_ref:
            return {"error": "stash push succeeded but could not resolve stash ref", "status": "failed"}
    chk_path = ckpt_dir / chk_id
    chk_path.mkdir(parents=True, exist_ok=True)

    # Save patches
    tracked_patch = chk_path / "tracked.patch"
    tr = _run(["git", "diff", "--binary"], root)
    if tr and tr.stdout.strip():
        tracked_patch.write_text(tr.stdout, encoding="utf-8")
    
    staged_patch = chk_path / "staged.patch"
    sr = _run(["git", "diff", "--cached", "--binary"], root)
    if sr and sr.stdout.strip():
        staged_patch.write_text(sr.stdout, encoding="utf-8")
    
    if include_governance:
        gov_patch = chk_path / "governance.patch"
        gov_paths = [f for f in gov_files + [x for x in untracked_files if _is_gov(x)] if not f.startswith(".aiwf/checkpoints/")]
        if gov_paths:
            diff_args = ["git", "diff", "--binary", "--"] + gov_paths
            gr = _run(diff_args, root)
            if gr and gr.stdout.strip():
                gov_patch.write_text(gr.stdout, encoding="utf-8")

    # Copy untracked files (respecting size limit)
    untracked_dir = chk_path / "untracked"
    for f in untracked_files:
        src = root / f
        if not src.exists(): continue
        sz = src.stat().st_size
        if sz > MAX_FILE_SIZE:
            warnings.append(f"skipped large file: {f} ({sz} bytes)")
            continue
        dst = untracked_dir / f
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    # Write restore-plan.md (mode-specific)
    if mode == "stash":
        plan = [f"# AIWF Git Stash Checkpoint — Restore Plan: {chk_id}", "",
                f"Checkpoint: {label or chk_id}", f"Git HEAD: {git_head}", f"Branch: {branch}",
                f"Stash ref: {stash_ref}", f"Stash hash: {stash_hash}", "",
                "## Git stash checkpoint",
                "This checkpoint is backed by Git stash.",
                "",
                "Restore options:",
                f"- git stash apply --index {stash_ref or stash_hash}",
                "- or use aiwf checkpoint restore <ID> --confirm",
                "",
                "AIWF does not drop the stash automatically.",
                "This checkpoint is not a git commit."]
    else:
        plan = [f"# AIWF Patch Checkpoint — Restore Plan: {chk_id}", "",
                f"Checkpoint: {label or chk_id}", f"Git HEAD: {git_head}", f"Branch: {branch}", "",
                "## Steps", "1. Verify current git HEAD matches checkpoint HEAD",
                "2. Create pre-restore backup checkpoint",
                "3. git reset --hard <checkpoint HEAD>",
                "4. git apply tracked.patch (unstaged changes)"]
        if staged_files: plan.append("5. git apply staged.patch (staged changes)")
        plan.extend(["", "## Warnings", "Restore will discard current unstaged changes.",
                     "A pre-restore backup checkpoint is created automatically.",
                     "Restore does NOT create a git commit."])
    (chk_path / "restore-plan.md").write_text("\n".join(plan) + "\n")

    # Write CHECKPOINT.json
    ckpt = {
        "schema_version": 1, "id": chk_id, "created_at": _now(),
        "label": label, "git_head": git_head, "branch": branch, "dirty": dirty,
        "project_files": len(project_files), "governance_files": len(gov_files),
        "untracked_files": len(untracked_files), "staged_files": len(staged_files),
        "project_file_list": project_files[:50], "governance_file_list": gov_files[:50],
        "provider": provider, "mode": mode, "stash_ref": stash_ref, "stash_hash": stash_hash, "warnings": warnings, "restore_supported": True,
    }
    (chk_path / "CHECKPOINT.json").write_text(json.dumps(ckpt, ensure_ascii=False, indent=2) + "\n")
    # Status
    (chk_path / "status.txt").write_text(status_r.stdout if status_r else "")

    return ckpt


def list_checkpoints(project_root: str) -> List[Dict]:
    root = Path(project_root)
    ckpt_dir = root / ".aiwf" / "checkpoints"
    if not ckpt_dir.exists(): return []
    result = []
    for d in sorted(ckpt_dir.iterdir(), reverse=True):
        jf = d / "CHECKPOINT.json"
        if jf.exists():
            try: result.append(json.loads(jf.read_text()))
            except: pass
    return result


def show_checkpoint(project_root: str, checkpoint_id: str) -> Optional[Dict]:
    root = Path(project_root)
    jf = root / ".aiwf" / "checkpoints" / checkpoint_id / "CHECKPOINT.json"
    return json.loads(jf.read_text()) if jf.exists() else None


def restore_checkpoint(project_root: str, checkpoint_id: str, confirm: bool = False) -> Dict:
    """Restore with pre-backup + HEAD guard. Requires --confirm."""
    root = Path(project_root)
    jf = root / ".aiwf" / "checkpoints" / checkpoint_id / "CHECKPOINT.json"
    if not jf.exists(): return {"error": f"checkpoint not found: {checkpoint_id}"}
    ckpt = json.loads(jf.read_text())
    
    if not confirm: return {"status": "dry_run", "message": "use --confirm to execute restore", "plan": str(root/".aiwf"/"checkpoints"/checkpoint_id/"restore-plan.md")}
    
    # HEAD guard
    head_r = _run(["git", "rev-parse", "HEAD"], root)
    current_head = head_r.stdout.strip() if head_r else ""
    if current_head != ckpt.get("git_head", ""):
        return {"error": f"git HEAD changed: current={_short(current_head)} vs checkpoint={_short(ckpt['git_head'])}", "status": "rejected"}
    
    # Pre-restore backup
    pre = create_checkpoint(project_root, label=f"pre-restore backup before {checkpoint_id}")
    
    # Reset + apply with error handling
    rr = _run(["git", "reset", "--hard", ckpt["git_head"]], root)
    if not rr: return {"error": "git reset --hard failed", "status": "failed"}
    
    _remove_untracked_before_restore(root)

    # Stash mode: use git stash apply
    if ckpt.get("mode") == "stash":
        stash_ref = ckpt.get("stash_ref") or ckpt.get("stash_hash", "")
        if not stash_ref: return {"error": "stash checkpoint missing stash_ref", "status": "failed"}
        sr2 = _run(["git", "stash", "apply", "--index", stash_ref], root)
        if not sr2: return {"error": "git stash apply failed", "status": "failed"}
        return {"status": "restored", "checkpoint": checkpoint_id, "pre_restore_backup": pre["id"], "mode": "stash"}

    # Patch mode: restore staged state first, then apply unstaged changes.
    # Applying staged.patch to both the working tree and index avoids an
    # index-only restore that leaves newly staged files missing on disk.
    staged = root / ".aiwf" / "checkpoints" / checkpoint_id / "staged.patch"
    if staged.exists() and staged.stat().st_size > 0:
        sw = _run(["git", "apply", str(staged)], root)
        if not sw: return {"error": "git apply staged.patch to working tree failed", "status": "failed"}
        sr = _run(["git", "apply", "--cached", str(staged)], root)
        if not sr: return {"error": "git apply staged.patch failed", "status": "failed"}

    tracked = root / ".aiwf" / "checkpoints" / checkpoint_id / "tracked.patch"
    if tracked.exists() and tracked.stat().st_size > 0:
        tr = _run(["git", "apply", str(tracked)], root)
        if not tr: return {"error": "git apply tracked.patch failed", "status": "failed"}
    
    # Restore untracked
    untracked_dir = root / ".aiwf" / "checkpoints" / checkpoint_id / "untracked"
    if untracked_dir.exists():
        try:
            for f in untracked_dir.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(untracked_dir)
                    dst = root / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dst)
        except Exception as e:
            return {"error": f"untracked restore failed: {e}", "status": "failed"}
    
    return {"status": "restored", "checkpoint": checkpoint_id, "pre_restore_backup": pre["id"]}
