"""AIWF Project Environment Profile — light scan, no secrets, no network, no installs."""
from __future__ import annotations

import json, os, shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


KNOWN_TOOLS = ["git", "node", "npm", "pnpm", "yarn", "python3", "pytest",
               "cargo", "cmake", "make", "pio", "platformio", "go", "javac", "mvn"]

CONFIG_FILES = [
    "package.json", "pnpm-lock.yaml", "package-lock.json", "yarn.lock",
    "pyproject.toml", "requirements.txt", "Cargo.toml", "CMakeLists.txt",
    "platformio.ini", "Makefile", "go.mod", "pom.xml", "build.gradle",
    "vite.config.js", "vite.config.ts", "next.config.js", "next.config.mjs",
    "tsconfig.json",
]

SIMPLE_JSON_FILES = {"package.json"}


def _now(): return datetime.now(timezone.utc).isoformat()


def _detected_tools() -> Dict[str, bool]:
    return {tool: shutil.which(tool) is not None for tool in KNOWN_TOOLS}


def _find_config_files(root: Path) -> List[str]:
    found = []
    for fname in CONFIG_FILES:
        # Support glob-style for vite.config.*, next.config.*
        if "*" in fname:
            for match in root.glob(fname):
                found.append(str(match.relative_to(root)))
        elif (root / fname).exists():
            found.append(fname)
    # Sort for determinism
    return sorted(found)


def _infer_languages(config_files: List[str]) -> List[str]:
    langs = set()
    triggers = {
        "javascript": ["package.json", "tsconfig.json", "vite.config", "next.config"],
        "typescript": ["tsconfig.json"],
        "python": ["pyproject.toml", "requirements.txt"],
        "rust": ["Cargo.toml"],
        "cpp": ["CMakeLists.txt"],
        "embedded": ["platformio.ini"],
        "go": ["go.mod"],
        "java": ["pom.xml", "build.gradle"],
    }
    for lang, files in triggers.items():
        for f in config_files:
            for pat in files:
                if pat in f:
                    langs.add(lang)
    return sorted(langs)


def _infer_package_managers(config_files: List[str]) -> List[str]:
    pms = []
    mapping = [
        (["pnpm-lock.yaml"], "pnpm"),
        (["yarn.lock"], "yarn"),
        (["package-lock.json"], "npm"),
        (["package.json"], "npm"),
        (["pyproject.toml"], "poetry/pip"),
        (["requirements.txt"], "pip"),
        (["Cargo.toml"], "cargo"),
        (["CMakeLists.txt"], "cmake"),
        (["Makefile"], "make"),
        (["platformio.ini"], "platformio"),
    ]
    seen = set()
    for triggers, name in mapping:
        for t in triggers:
            if t in config_files and name not in seen:
                pms.append(name)
                seen.add(name)
    return pms


def _required_tools(config_files: List[str]) -> List[str]:
    """Return tools required by the detected config files (not all known tools)."""
    required = set()
    has_js = "package.json" in config_files
    if has_js:
        if "pnpm-lock.yaml" in config_files: required.add("pnpm")
        elif "yarn.lock" in config_files: required.add("yarn")
        else: required.add("npm")  # package.json alone implies npm
    if "pyproject.toml" in config_files or "requirements.txt" in config_files:
        required.add("python3")
    if "Cargo.toml" in config_files:
        required.add("cargo")
    if "CMakeLists.txt" in config_files:
        required.add("cmake")
    if "Makefile" in config_files:
        required.add("make")
    if "platformio.ini" in config_files:
        # Require at least one of pio or platformio
        required.add("pio")
    if "go.mod" in config_files:
        required.add("go")
    if "pom.xml" in config_files or "build.gradle" in config_files:
        required.add("mvn")
    return sorted(required)


def _extract_commands(root: Path, config_files: List[str]) -> Dict[str, List[str]]:
    test_cmds, build_cmds, run_cmds = [], [], []

    # package.json
    if "package.json" in config_files:
        try:
            pkg = json.loads((root / "package.json").read_text(encoding="utf-8"))
            scripts = pkg.get("scripts", {})
            if isinstance(scripts, dict):
                if "test" in scripts: test_cmds.append("npm test")
                if "build" in scripts: build_cmds.append("npm run build")
                if "dev" in scripts: run_cmds.append("npm run dev")
                elif "start" in scripts: run_cmds.append("npm start")
        except (json.JSONDecodeError, OSError):
            pass

    # platformio.ini
    if "platformio.ini" in config_files:
        test_cmds.append("pio test")
        build_cmds.append("pio run")

    # CMakeLists.txt
    if "CMakeLists.txt" in config_files:
        build_cmds.append("cmake --build build")

    # Makefile
    if "Makefile" in config_files:
        try:
            content = (root / "Makefile").read_text(encoding="utf-8")
            for line in content.split("\n"):
                if line.startswith("test:"):
                    test_cmds.append("make test")
                    break
        except OSError:
            pass
        build_cmds.append("make")

    # pyproject / requirements: candidate pytest if tests/ exists
    if any(f in config_files for f in ["pyproject.toml", "requirements.txt"]):
        if (root / "tests").exists() or (root / "test").exists():
            test_cmds.append("pytest" if "pyproject.toml" in config_files else "python -m pytest")

    return {"test_commands": test_cmds[:5], "build_commands": build_cmds[:5],
            "run_commands": run_cmds[:3]}


def scan_environment(project_root: str) -> Dict[str, Any]:
    """Light environment scan. No network, no installs, no test/build execution."""
    root = Path(project_root).resolve()
    config_files = _find_config_files(root)
    tools = _detected_tools()

    # Required tools = only what this project actually needs
    required = _required_tools(config_files)
    missing = [t for t in required if not tools.get(t)]

    cmds = _extract_commands(root, config_files)

    # Known risks = only relevant config/tool mismatches
    risks = []
    if "platformio.ini" in config_files and not tools.get("pio") and not tools.get("platformio"):
        risks.append("platformio project but pio/platformio CLI not found")
    if "CMakeLists.txt" in config_files and not tools.get("cmake"):
        risks.append("CMake project but cmake CLI not found")
    if "Cargo.toml" in config_files and not tools.get("cargo"):
        risks.append("Rust project but cargo CLI not found")
    js_cfgs = [f for f in config_files if f in ("package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock")]
    if js_cfgs:
        pm = "pnpm" if "pnpm-lock.yaml" in config_files else "yarn" if "yarn.lock" in config_files else "npm"
        if not tools.get(pm):
            risks.append(f"JavaScript project but {pm} CLI not found")
    if "Makefile" in config_files and not tools.get("make"):
        risks.append("Makefile project but make CLI not found")
    if "go.mod" in config_files and not tools.get("go"):
        risks.append("Go project but go CLI not found")
    if ("pom.xml" in config_files or "build.gradle" in config_files) and not tools.get("mvn"):
        risks.append("Java project but mvn CLI not found")

    return {
        "schema_version": 1,
        "generated_at": _now(),
        "project_root": str(root),
        "os": os.uname().sysname if hasattr(os, "uname") else "",
        "shell": os.environ.get("SHELL", ""),
        "languages": _infer_languages(config_files),
        "package_managers": _infer_package_managers(config_files),
        "frameworks": [],
        "build_commands": cmds["build_commands"],
        "test_commands": cmds["test_commands"],
        "run_commands": cmds["run_commands"],
        "detected_tools": tools,
        "missing_tools": missing,
        "config_files": config_files,
        "known_environment_risks": risks,
        "notes": [],
        "mode": "light_scan",
    }


def write_environment_profile(project_root: str, profile: Dict[str, Any]) -> Path:
    """Write environment profile to .aiwf/assets/environment.json."""
    dest = Path(project_root) / ".aiwf" / "records" / "events.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dest


def load_environment_profile(project_root: str) -> Dict[str, Any]:
    """Load environment profile, or return empty dict if missing."""
    path = Path(project_root) / ".aiwf" / "records" / "events.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
