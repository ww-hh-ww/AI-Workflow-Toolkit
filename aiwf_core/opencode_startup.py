"""OpenCode Plugin startup validation and graceful fallback."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List


PLUGIN_SPEC = "./scripts/aiwf_opencode_plugin.js"
STARTUP_STATUS_PATH = Path(".aiwf/runtime/internal/opencode-startup.json")
STARTUP_CHECK_ENV = "AIWF_OPENCODE_STARTUP_CHECK"


def set_plugin_enabled(root: Path, enabled: bool) -> Path:
    """Change only AIWF's plugin registration and preserve user configuration."""
    path = root / "opencode.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    plugins = data.setdefault("plugin", [])
    if not isinstance(plugins, list):
        raise ValueError("opencode.json 'plugin' must be a list before AIWF can install")
    plugins = [item for item in plugins if item != PLUGIN_SPEC]
    if enabled:
        plugins.append(PLUGIN_SPEC)
    if plugins:
        data["plugin"] = plugins
    else:
        data.pop("plugin", None)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def probe_opencode_startup(root: Path, timeout: float = 8.0) -> Dict[str, object]:
    """Check that OpenCode can finish loading the installed project plugin."""
    if os.environ.get(STARTUP_CHECK_ENV, "").strip().lower() == "skip":
        return {"checked": False, "ok": True, "reason": "startup check skipped"}
    executable = shutil.which("opencode")
    if not executable:
        return {
            "checked": False,
            "ok": False,
            "reason": "OpenCode executable was not found on PATH",
        }
    env = os.environ.copy()
    env["OPENCODE_DISABLE_MODELS_FETCH"] = "true"
    try:
        result = subprocess.run(
            [executable, "debug", "config"],
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="surrogateescape",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "checked": True,
            "ok": False,
            "reason": (
                f"OpenCode did not finish loading the project plugin within {timeout:g}s; "
                "its local Plugin SDK may be unavailable"
            ),
        }
    except OSError as exc:
        return {"checked": True, "ok": False, "reason": str(exc)}
    if result.returncode == 0:
        return {"checked": True, "ok": True, "reason": "startup probe passed"}
    detail = (result.stderr or result.stdout or "OpenCode config load failed").strip()
    return {"checked": True, "ok": False, "reason": detail[-800:]}


def finalize_plugin_startup(root: Path, results: Dict[str, List[str]]) -> Path:
    probe = probe_opencode_startup(root)
    enabled = bool(probe.get("ok"))
    fallback = {"checked": False, "ok": enabled, "reason": "not needed"}
    if not enabled:
        config = set_plugin_enabled(root, False)
        config_rel = str(config.relative_to(root))
        if config_rel not in results["updated"]:
            results["updated"].append(config_rel)
        fallback = probe_opencode_startup(root, timeout=3.0)
        if fallback.get("ok"):
            warning = (
                "OpenCode startup recovered after AIWF Plugin registration was disabled: "
                f"{probe.get('reason')}. Agents and Skills remain installed, but AIWF hook "
                "enforcement is unavailable. Restore OpenCode Plugin SDK access and rerun "
                "`aiwf install opencode --force`."
            )
        else:
            warning = (
                "AIWF Plugin registration was disabled after its startup probe failed, but "
                "OpenCode still did not load. The remaining failure is not limited to AIWF: "
                f"{fallback.get('reason')}."
            )
        results.setdefault("warnings", []).append(warning)
    status_path = root / STARTUP_STATUS_PATH
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps(
            {
                "plugin_enabled": enabled,
                "startup_checked": bool(probe.get("checked")),
                "reason": str(probe.get("reason") or ""),
                "fallback_startup_ok": bool(fallback.get("ok")),
                "fallback_reason": str(fallback.get("reason") or ""),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return status_path
