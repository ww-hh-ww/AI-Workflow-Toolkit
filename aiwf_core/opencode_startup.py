"""OpenCode Plugin startup validation and graceful fallback."""
from __future__ import annotations

import json
import os
import signal
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional


PLUGIN_SPEC = "./scripts/aiwf_opencode_plugin.js"
STARTUP_STATUS_PATH = Path(".aiwf/runtime/internal/opencode-startup.json")
STARTUP_CHECK_ENV = "AIWF_OPENCODE_STARTUP_CHECK"
WARM_STARTUP_TIMEOUT = 8.0
COLD_STARTUP_TIMEOUT = 120.0
FALLBACK_STARTUP_TIMEOUT = 15.0


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


def _plugin_sdk_ready(root: Path) -> bool:
    return (
        root / ".opencode/node_modules/@opencode-ai/plugin/package.json"
    ).is_file()


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()


def _run_probe(
    command: List[str], root: Path, env: Dict[str, str], timeout: float
) -> subprocess.CompletedProcess[str]:
    options: Dict[str, object] = {
        "cwd": str(root),
        "env": env,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "surrogateescape",
    }
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    process = subprocess.Popen(command, **options)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process)
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
        raise
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def probe_opencode_startup(
    root: Path, timeout: Optional[float] = None
) -> Dict[str, object]:
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
    effective_timeout = timeout
    if effective_timeout is None:
        effective_timeout = (
            WARM_STARTUP_TIMEOUT if _plugin_sdk_ready(root) else COLD_STARTUP_TIMEOUT
        )
    try:
        result = _run_probe(
            [executable, "debug", "config"],
            root,
            env,
            effective_timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "checked": True,
            "ok": False,
            "reason": (
                "OpenCode did not finish loading the project plugin within "
                f"{effective_timeout:g}s; "
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
        fallback = probe_opencode_startup(root, timeout=FALLBACK_STARTUP_TIMEOUT)
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
