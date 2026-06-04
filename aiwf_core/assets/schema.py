"""Deterministic Context Asset Layer — stdlib only, no LLM, no dependencies.

Assets:
  project-map.json — source files, imports, exports, module roles
  test-map.json    — test files, imports, test commands, patterns
  conventions.md   — manual template, never auto-generated
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

ASSET_DIR = ".aiwf/assets"
ASSET_FILES = ["project-map.json", "test-map.json", "conventions.md"]

# Files/dirs to exclude from scanning
EXCLUDE_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv",
                ".aiwf", ".claude", ".reasonix", "scripts"}
EXCLUDE_FILES = {"package-lock.json", "yarn.lock", ".DS_Store"}

# Recognized source extensions
SOURCE_EXTS = {".js", ".ts", ".py", ".go", ".rs", ".java", ".rb", ".c", ".h",
               ".cpp", ".hpp", ".cs", ".swift", ".kt", ".scala", ".php", ".sh"}

# Import patterns per language
IMPORT_PATTERNS = {
    ".js": re.compile(r"""(?:require\(['"]|from\s+['"]|import\s+['"])([^'"]+)['"]"""),
    ".ts": re.compile(r"""(?:from\s+['"]|import\s+['"])([^'"]+)['"]"""),
    ".py": re.compile(r"""(?:^from\s+|^import\s+)([^\s.]+)"""),
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _hash_file(path: Path) -> str:
    try:
        h = hashlib.md5()
        h.update(path.read_bytes())
        return h.hexdigest()
    except Exception:
        return ""


def _hash_files(paths: List[Path]) -> Dict[str, str]:
    return {str(p): _hash_file(p) for p in paths}


# Asset tiers:
#   Tier 1 — auto-refreshed mechanical data (hashes, imports, exports)
#   Tier 2 — human-curated structural knowledge (conventions, strategy)
TIER_MAP = {"project-map": 1, "test-map": 1, "conventions": 2}

def _asset_metadata(kind: str) -> Dict[str, Any]:
    return {
        "version": 1,
        "kind": kind,
        "tier": TIER_MAP.get(kind, 1),
        "status": "partial",
        "generated_at": _now(),
        "source_files": [],
        "source_hashes": {},
        "stale_detection": "hash",
        "tier1_mechanical_fields": ["source_hashes", "imports", "exports", "dependency_edges", "source_files"],
        "tier2_curated_fields": ["conventions", "strategy", "architecture_notes"],
        "last_verified_by": None,
        "last_used_by": [],
    }


def _scan_files(root: Path) -> List[Path]:
    """Find all project source files, excluding AIWF internals and known dirs."""
    files = []
    for dirpath, dirnames, filenames in os.walk(str(root)):
        # Filter dirs in-place
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        # Skip paths starting with .
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fname in filenames:
            if fname in EXCLUDE_FILES or fname.startswith("."):
                continue
            fpath = Path(dirpath) / fname
            rel = str(fpath.relative_to(root))
            # Only include recognized source files + package.json + config files
            if fpath.suffix in SOURCE_EXTS or fname in ("package.json", "Makefile", "Dockerfile"):
                files.append(fpath)
    return sorted(files)


def _detect_imports(fpath: Path) -> List[str]:
    """Detect imports/requires using regex patterns. Returns list of module names."""
    ext = fpath.suffix
    pattern = IMPORT_PATTERNS.get(ext)
    if not pattern:
        return []
    try:
        text = fpath.read_text(encoding="utf-8", errors="ignore")
        return [m for m in pattern.findall(text) if not m.startswith(".")]
    except Exception:
        return []


def _detect_exports(fpath: Path) -> List[str]:
    """Detect exported symbols (JS/TS: module.exports, export; Py: __all__, def)."""
    exports = []
    try:
        text = fpath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return exports

    ext = fpath.suffix
    if ext in (".js", ".ts"):
        exports.extend(re.findall(r"""(?:module\.exports\s*=\s*\{|export\s+(?:const|function|class|default)\s+)(\w+)""", text))
        exports.extend(re.findall(r"""exports\.(\w+)\s*=""", text))
    elif ext == ".py":
        all_match = re.search(r"""__all__\s*=\s*\[([^\]]+)\]""", text)
        if all_match:
            exports.extend(re.findall(r"""['"](\w+)['"]""", all_match.group(1)))
        exports.extend(re.findall(r"""^def\s+(\w+)""", text, re.MULTILINE))

    return sorted(set(exports))[:20]


def _module_role(fpath: Path) -> str:
    """Guess module role from path name."""
    rel = str(fpath).lower()
    parts = rel.replace("\\", "/").split("/")
    for part in parts:
        if part in ("test", "tests", "spec", "__tests__"):
            return "test"
        if part in ("lib", "utils", "helpers", "common", "shared"):
            return "library"
        if part in ("config", "settings", "env", "constants"):
            return "config"
        if part in ("routes", "controllers", "handlers", "views", "pages"):
            return "interface"
        if part in ("models", "entities", "types", "schemas", "db"):
            return "model"
        if part in ("services", "api", "gateway", "client"):
            return "service"
    return "source"


def init_assets(root_dir: str) -> Dict[str, Any]:
    """Initialize .aiwf/assets/ with project-map, test-map, conventions template.

    Deterministic scanning only — no LLM, no inference beyond regex.
    Returns dict with created paths and status.
    """
    root = Path(root_dir)
    asset_dir = root / ASSET_DIR
    asset_dir.mkdir(parents=True, exist_ok=True)

    all_files = _scan_files(root)
    source_files = [f for f in all_files if _module_role(f) != "test"]
    test_files = [f for f in all_files if _module_role(f) == "test"]

    # ── project-map.json ──
    pm = {"_asset": _asset_metadata("project-map")}
    pm["_asset"]["source_files"] = [str(f.relative_to(root)) for f in source_files]
    pm["_asset"]["source_hashes"] = _hash_files(source_files)
    pm["_asset"]["status"] = "fresh"
    pm["_asset"]["generated_at"] = _now()

    pm["modules"] = []
    pm["dependency_edges"] = []
    imports_map = {}

    for sf in source_files:
        rel = str(sf.relative_to(root))
        imports = _detect_imports(sf)
        exports = _detect_exports(sf)
        role = _module_role(sf)
        pm["modules"].append({
            "path": rel,
            "role": role,
            "exports": exports,
            "hash": pm["_asset"]["source_hashes"].get(str(sf), ""),
        })
        imports_map[rel] = imports
        for imp in imports:
            pm["dependency_edges"].append({"from": rel, "to": imp, "kind": "import"})

    (asset_dir / "project-map.json").write_text(
        json.dumps(pm, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # ── test-map.json ──
    tm = {"_asset": _asset_metadata("test-map")}
    tm["_asset"]["source_files"] = [str(f.relative_to(root)) for f in test_files]
    tm["_asset"]["source_hashes"] = _hash_files(test_files)
    tm["_asset"]["status"] = "fresh"
    tm["_asset"]["generated_at"] = _now()

    tm["tests"] = []
    for tf in test_files:
        rel = str(tf.relative_to(root))
        imports = _detect_imports(tf)
        tm["tests"].append({
            "path": rel,
            "imports": imports,
            "hash": tm["_asset"]["source_hashes"].get(str(tf), ""),
        })

    # Detect test command from package.json
    pkg_path = root / "package.json"
    test_cmd = ""
    if pkg_path.exists():
        try:
            pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
            scripts = pkg.get("scripts", {})
            test_cmd = scripts.get("test", "") or ""
        except Exception:
            pass
    tm["test_command"] = test_cmd
    tm["assertion_patterns"] = []  # Manual hint field

    (asset_dir / "test-map.json").write_text(
        json.dumps(tm, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # ── conventions.md ──
    conv_path = asset_dir / "conventions.md"
    if not conv_path.exists():
        conv_path.write_text("""# Project Conventions

*Manual template — fill in with project-specific conventions.*

## Code Style
-

## Naming
-

## Testing
-

## Architecture
-

## Dependencies
-

## Known Risks
-
""", encoding="utf-8")

    return {
        "created": [str(p.relative_to(root)) for p in asset_dir.iterdir() if p.is_file()],
        "source_files": len(source_files),
        "test_files": len(test_files),
        "status": "initialized",
    }


def refresh_assets(root_dir: str, update: bool = False) -> Dict[str, Any]:
    """Check or update asset freshness by comparing stored hashes.

    Args:
        root_dir: Project root.
        update: If True, update source_hashes for changed files.
                If False (--check), only report staleness.

    Returns dict with status per asset.
    """
    root = Path(root_dir)
    asset_dir = root / ASSET_DIR
    result = {"assets": {}, "stale_files": [], "overall": "fresh"}

    for asset_name in ["project-map.json", "test-map.json"]:
        asset_path = asset_dir / asset_name
        if not asset_path.exists():
            result["assets"][asset_name] = "missing"
            continue

        try:
            asset = json.loads(asset_path.read_text(encoding="utf-8"))
        except Exception:
            result["assets"][asset_name] = "corrupt"
            continue

        meta = asset.get("_asset", {})
        stored_hashes = meta.get("source_hashes", {})
        changed = []

        for fpath_str, old_hash in stored_hashes.items():
            fpath = root / fpath_str
            if not fpath.exists():
                changed.append(f"{fpath_str} (deleted)")
                continue
            new_hash = _hash_file(fpath)
            if new_hash != old_hash:
                changed.append(f"{fpath_str} (modified)")

        if changed:
            meta["status"] = "stale"
            result["assets"][asset_name] = "stale"
            result["stale_files"].extend(changed)
            result["overall"] = "stale"

            if update:
                # Refresh hashes
                new_hashes = {}
                for fpath_str in stored_hashes:
                    fpath = root / fpath_str
                    if fpath.exists():
                        new_hashes[fpath_str] = _hash_file(fpath)
                meta["source_hashes"] = new_hashes
                meta["status"] = "fresh"
                meta["generated_at"] = _now()
                asset["_asset"] = meta
                asset_path.write_text(
                    json.dumps(asset, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
                result["assets"][asset_name] = "fresh (updated)"
        else:
            result["assets"][asset_name] = "fresh"

    # Check conventions.md presence (Tier 2 — never auto-overwritten)
    conv_path = asset_dir / "conventions.md"
    result["assets"]["conventions.md"] = "present" if conv_path.exists() else "missing"
    # Stale assets are advisory only: stale Tier 1 warns, Tier 2 is human-curated.
    # Stale assets must NEVER be trusted as source of truth.

    return result


def asset_status(root_dir: str) -> Dict[str, Any]:
    """Return concise asset status for aiwf status display."""
    return refresh_assets(root_dir, update=False)
