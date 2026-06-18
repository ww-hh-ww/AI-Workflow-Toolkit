"""Architecture snapshot requirement contract."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_SNAPSHOT_PATH = ".aiwf/artifacts/reports/架构详细设计.md"

REQUIRED_HEADERS = [
    "Project Overview",
    "Architecture Summary",
    "Capability / Goal Tree Overview",
    "Module and Directory Responsibilities",
    "Key Flows",
    "Evidence Manifest",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_path(project_root: str) -> Path:
    return Path(project_root) / ".aiwf" / "records" / "architecture-doc.json"


def _default_state() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "required": False,
        "status": "not_required",
        "reason": "",
        "path": DEFAULT_SNAPSHOT_PATH,
        "required_at": "",
        "satisfied_at": "",
        "waived_at": "",
        "waive_reason": "",
        "validated_at": "",
        "validation": {"valid": False, "issues": [], "warnings": []},
        "history": [],
    }


def load_architecture_doc_state(project_root: str) -> Dict[str, Any]:
    path = _state_path(project_root)
    if not path.exists():
        return _default_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        data = _default_state()
        data["status"] = "invalid"
        data["validation"] = {
            "valid": False,
            "issues": [f"architecture-doc.json unreadable: {exc}"],
            "warnings": [],
        }
        return data
    if not isinstance(data, dict):
        return _default_state()
    state = _default_state()
    state.update(data)
    state.setdefault("history", [])
    state.setdefault("validation", {"valid": False, "issues": [], "warnings": []})
    return state


def save_architecture_doc_state(project_root: str, state: Dict[str, Any]) -> Dict[str, Any]:
    path = _state_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return state


def require_architecture_doc(project_root: str, reason: str, path: str = DEFAULT_SNAPSHOT_PATH) -> Dict[str, Any]:
    reason = str(reason or "").strip()
    if not reason:
        raise ValueError("--reason is required")
    state = load_architecture_doc_state(project_root)
    now = _now()
    state.update({
        "required": True,
        "status": "required",
        "reason": reason,
        "path": str(path or DEFAULT_SNAPSHOT_PATH).strip() or DEFAULT_SNAPSHOT_PATH,
        "required_at": now,
        "satisfied_at": "",
        "waived_at": "",
        "waive_reason": "",
    })
    state.setdefault("history", []).append({
        "action": "require",
        "reason": reason,
        "path": state["path"],
        "recorded_at": now,
    })
    return save_architecture_doc_state(project_root, state)


def waive_architecture_doc(project_root: str, reason: str) -> Dict[str, Any]:
    reason = str(reason or "").strip()
    if not reason:
        raise ValueError("--reason is required")
    state = load_architecture_doc_state(project_root)
    now = _now()
    state.update({
        "required": False,
        "status": "waived",
        "waived_at": now,
        "waive_reason": reason,
    })
    state.setdefault("history", []).append({
        "action": "waive",
        "reason": reason,
        "recorded_at": now,
    })
    return save_architecture_doc_state(project_root, state)


def _resolve_snapshot_path(project_root: str, path: str) -> Path:
    raw = str(path or DEFAULT_SNAPSHOT_PATH).strip() or DEFAULT_SNAPSHOT_PATH
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate
    return Path(project_root) / candidate


def validate_architecture_doc(project_root: str, path: str = "") -> Dict[str, Any]:
    state = load_architecture_doc_state(project_root)
    rel_path = str(path or state.get("path") or DEFAULT_SNAPSHOT_PATH)
    doc_path = _resolve_snapshot_path(project_root, rel_path)
    issues: List[str] = []
    warnings: List[str] = []

    if not doc_path.exists():
        issues.append(f"architecture snapshot missing: {rel_path}")
        text = ""
    else:
        text = doc_path.read_text(encoding="utf-8", errors="ignore")
        if len(text.strip()) < 400:
            issues.append("architecture snapshot is too short to be a useful system summary")
        for header in REQUIRED_HEADERS:
            if header not in text:
                issues.append(f"missing required section: {header}")
        manifest_idx = text.find("Evidence Manifest")
        if manifest_idx >= 0:
            manifest = text[manifest_idx:]
            evidence_markers = [
                ".aiwf/state/goals.json",
                ".aiwf/assets/project-map.json",
                ".aiwf/artifacts/reports/项目地图.md",
                "Source:",
                "Tests:",
                "Evidence:",
            ]
            if not any(marker in manifest for marker in evidence_markers):
                issues.append("Evidence Manifest has no concrete evidence references")
        if "TODO" in text or "Planner TODO" in text:
            warnings.append("snapshot contains TODO markers")

    result = {
        "valid": not issues,
        "issues": issues,
        "warnings": warnings,
        "path": rel_path,
        "checked_at": _now(),
    }
    state["path"] = rel_path
    state["validated_at"] = result["checked_at"]
    state["validation"] = result
    if state.get("required") and not result["valid"]:
        state["status"] = "required"
    save_architecture_doc_state(project_root, state)
    return result


def satisfy_architecture_doc(project_root: str, path: str = "") -> Dict[str, Any]:
    state = load_architecture_doc_state(project_root)
    rel_path = str(path or state.get("path") or DEFAULT_SNAPSHOT_PATH)
    result = validate_architecture_doc(project_root, rel_path)
    if not result["valid"]:
        raise ValueError("architecture snapshot validation failed: " + "; ".join(result["issues"]))
    state = load_architecture_doc_state(project_root)
    now = _now()
    state.update({
        "required": False,
        "status": "satisfied",
        "path": rel_path,
        "satisfied_at": now,
    })
    state.setdefault("history", []).append({
        "action": "satisfy",
        "path": rel_path,
        "recorded_at": now,
    })
    return save_architecture_doc_state(project_root, state)


def architecture_doc_blockers(project_root: str) -> List[str]:
    state = load_architecture_doc_state(project_root)
    if state.get("required") and state.get("status") != "satisfied":
        result = validate_architecture_doc(project_root, str(state.get("path") or DEFAULT_SNAPSHOT_PATH))
        if result.get("valid"):
            return [
                "architecture snapshot is valid but not marked satisfied. "
                "Run: aiwf architecture-doc satisfy"
            ]
        return [
            "architecture snapshot required but not satisfied. "
            "Run /aiwf-architecture-doc, then aiwf architecture-doc validate && aiwf architecture-doc satisfy. "
            + ("Issues: " + "; ".join(result.get("issues", [])[:3]) if result.get("issues") else "")
        ]
    return []

