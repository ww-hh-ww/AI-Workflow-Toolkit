"""Read retained experiment assets without restoring trees or changing evidence."""
from __future__ import annotations

import base64
import re
import subprocess
from pathlib import PurePosixPath

from .experiment_records import load_experiment
from .worktree_context import resolve_control_root


def _git(root, *args):
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, timeout=30)
    if result.returncode:
        raise ValueError(result.stderr.decode("utf-8", "replace").strip())
    return result.stdout


def retained_experiment(base_dir, experiment_id):
    root = resolve_control_root(base_dir)
    record = load_experiment(root, experiment_id)
    ref = str(record.get("experiment_ref") or "")
    if not re.fullmatch(r"[0-9a-f]{40,64}", ref):
        raise ValueError("experiment has no recorded immutable snapshot")
    _git(root, "cat-file", "-e", ref + "^{commit}")
    return root, record


def _entries(root, ref):
    entries = {}
    for row in _git(root, "ls-tree", "-r", "-l", "-z", ref).split(b"\0"):
        if not row:
            continue
        metadata, path = row.split(b"\t", 1)
        mode, kind, oid, size = metadata.split()
        name = path.decode("utf-8", "surrogateescape")
        if name == ".aiwf" or name.startswith(".aiwf/"):
            continue
        entries[name] = {
            "path": name, "mode": mode.decode(), "object_id": oid.decode(),
            "kind": "symlink" if mode == b"120000" else kind.decode(),
            "size": int(size) if size != b"-" else None,
        }
    return entries


def experiment_assets(base_dir, experiment_id, path=""):
    root, record = retained_experiment(base_dir, experiment_id)
    ref = record["experiment_ref"]
    entries = _entries(root, ref)
    result = {
        "experiment_id": experiment_id, "scope": record.get("scope"),
        "subject_ref": record["subject_ref"], "experiment_ref": ref,
        "status": record.get("status"),
        "note": "Assets are retained Git objects, not acceptance evidence for another candidate. Ignored files, external data and environment are not guaranteed retained.",
    }
    if path:
        parts = PurePosixPath(path).parts
        if path.startswith("/") or ".." in parts or str(PurePosixPath(path)) != path:
            raise ValueError("asset path must be an exact repository-relative path")
        entry = entries.get(path)
        if not entry:
            raise ValueError(f"asset is not present in the snapshot: {path}")
        if entry["kind"] not in ("blob", "symlink"):
            raise ValueError("submodule contents are not retained in the experiment snapshot")
        content = _git(root, "cat-file", "blob", entry["object_id"])
        try:
            text = content.decode("utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError:
            text = base64.b64encode(content).decode("ascii")
            encoding = "base64"
        return {**result, "asset": {**entry, "encoding": encoding, "content": text}}
    changes = _git(root, "diff", "--name-status", "--no-renames", "-z",
                   record["subject_ref"], ref, "--").split(b"\0")
    assets = []
    for i in range(0, len(changes) - 1, 2):
        status, raw_path = changes[i:i + 2]
        name = raw_path.decode("utf-8", "surrogateescape")
        if name == ".aiwf" or name.startswith(".aiwf/"):
            continue
        assets.append({**entries.get(name, {"path": name}),
                       "change": status.decode(), "available": name in entries})
    return {**result, "assets": assets,
            "promotion_candidates": record.get("promotion_candidates", [])}


def experiment_asset_bytes(base_dir, experiment_id, path):
    asset = experiment_assets(base_dir, experiment_id, path)["asset"]
    return (base64.b64decode(asset["content"]) if asset["encoding"] == "base64"
            else asset["content"].encode("utf-8"))
