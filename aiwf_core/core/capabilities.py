"""External Capability Registry — discover, classify, registry for Claude Code resources.

Filters out AIWF internal components. Stores short metadata, never secrets.
"""
from __future__ import annotations
import json, os, re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import CAPABILITIES_JSON, CAPABILITY_DECISIONS_JSON

DANGEROUS_WORDS = ["deploy", "publish", "push", "commit", "delete", "rm ", "sudo",
                    "secret", "token", "password", "destroy", "drop", "truncate",
                    "git push", "npm publish"]

AIWF_HOOK_EVENTS = {"UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"}

AIWF_INTERNAL_PREFIXES = ("aiwf-",)
AIWF_SCRIPT_HOOKS = {"scripts/aiwf_status.py", "scripts/aiwf_pre_snapshot.py",
                      "scripts/aiwf_scope_check.py", "scripts/aiwf_bash_guard.py",
                      "scripts/aiwf_capture_evidence.py", "scripts/aiwf_review_gate.py"}

RISK_MAP = {"docs": "read_only_context", "read": "read_only_context",
            "search": "read_only_context", "fetch": "read_only_context",
            "query": "read_only_context", "db": "project_mutation",
            "write": "project_mutation", "deploy": "destructive_or_deploy",
            "publish": "destructive_or_deploy", "github": "project_mutation",
            "git": "project_mutation", "filesystem": "project_mutation",
            "shell": "project_mutation"}

LIFECYCLE_CAPABILITY_HINTS = {
    "grill": "clarification",
    "requirements": "clarification",
    "docs": "external_research",
    "last30days": "external_research",
    "research": "external_research",
    "plan": "planning_advisory",
    "ce:plan": "planning_advisory",
    "ce-plan": "planning_advisory",
    "work": "implementation_helper",
    "ce:work": "implementation_helper",
    "ce-work": "implementation_helper",
    "tdd": "testing_method",
    "test": "testing_method",
    "review": "review_method",
    "architecture": "architecture_advisory",
    "improve-codebase-architecture": "architecture_advisory",
    "caveman": "output_style",
}

AIWF_LIFECYCLE_OVERLAPS = {
    "planning_advisory",
    "implementation_helper",
    "testing_method",
    "review_method",
    "architecture_advisory",
}


def _first_n_lines(path: Path, n: int = 5) -> str:
    try: return "".join(path.read_text(encoding="utf-8", errors="ignore").splitlines(True)[:n])
    except: return ""


def _has_dangerous_words(text: str) -> List[str]:
    return [w for w in DANGEROUS_WORDS if w in text.lower()]


def _classify_risk_kind(name: str, kind: str, content_hint: str = "") -> str:
    lowered = (name + " " + content_hint[:200]).lower()
    for pattern, risk in RISK_MAP.items():
        if pattern in lowered: return risk
    return "unknown"


def _classify_use_policy(risk: str, has_dangerous: bool, overlaps_aiwf: bool) -> str:
    if risk == "destructive_or_deploy" or has_dangerous: return "requires_user_decision"
    if overlaps_aiwf: return "requires_user_decision"
    if risk in ("unknown", "project_mutation", "network_access"): return "ask_before_use"
    return "advisory"


def _classify_capability_type(name: str, kind: str, content_hint: str = "") -> str:
    """Describe what lifecycle niche an external capability appears to occupy."""
    lowered = f"{name} {kind} {content_hint[:500]}".lower()
    for pattern, capability_type in LIFECYCLE_CAPABILITY_HINTS.items():
        if pattern in lowered:
            return capability_type
    if kind in ("skill", "slash_command", "subagent"):
        return "method_advisory"
    if kind == "mcp_server":
        return "tool_bridge"
    if kind == "hook":
        return "lifecycle_hook"
    return "unknown"


def _lifecycle_overlap(capability_type: str, kind: str, source: str = "") -> bool:
    """True when a capability might replace or reorder AIWF lifecycle stages."""
    if capability_type in AIWF_LIFECYCLE_OVERLAPS:
        return True
    if kind == "hook":
        return True
    if "compound" in source.lower() or "dynamic" in source.lower():
        return True
    return False


def _capability_metadata(name: str, kind: str, hint: str, source: str = "") -> Dict[str, Any]:
    capability_type = _classify_capability_type(name, kind, hint)
    lifecycle_overlap = _lifecycle_overlap(capability_type, kind, source)
    return {
        "capability_type": capability_type,
        "lifecycle_overlap": lifecycle_overlap,
        "governance_note": (
            "May assist this lifecycle stage but must not replace AIWF state gates"
            if lifecycle_overlap else
            "Advisory or auxiliary capability; promote outputs through Planner judgment"
        ),
    }


def classify_capability(raw: dict) -> dict:
    """Classify a raw capability dict, returning risk/use_policy fields."""
    name = raw.get("name", raw.get("id", ""))
    kind = raw.get("kind", "unknown")
    hint = raw.get("summary", raw.get("content_hint", ""))
    dangerous = _has_dangerous_words(name + " " + hint)
    risk = raw.get("risk") or _classify_risk_kind(name, kind, hint)
    meta = _capability_metadata(name, kind, hint, raw.get("source", ""))
    overlaps = raw.get("overlaps_aiwf", False) or bool(meta["lifecycle_overlap"])
    return {
        **meta,
        "risk": risk,
        "use_policy": _classify_use_policy(risk, bool(dangerous), overlaps),
        "may_modify_project": risk in ("project_mutation", "destructive_or_deploy") or bool(dangerous),
        "may_access_network": kind == "mcp_server",
        "requires_evidence": risk in ("project_mutation", "destructive_or_deploy"),
    }


def _is_aiwf_internal(name: str, source: str = "", command: str = "") -> bool:
    if name.startswith(AIWF_INTERNAL_PREFIXES): return True
    if any(cmd in str(command) for cmd in AIWF_SCRIPT_HOOKS): return True
    if any(script in str(source) for script in AIWF_SCRIPT_HOOKS): return True
    return False


def _capability_id(capabilities: List[Dict[str, Any]], kind: str, config_dir: str, name: str) -> str:
    """Keep legacy unqualified IDs; namespace only an actual cross-engine collision."""
    base = f"{kind}:{name}"
    if not any(c.get("id") == base for c in capabilities):
        return base
    return f"{kind}:{config_dir}:{name}"


def discover_capabilities(project_root: str) -> Dict[str, Any]:
    root = Path(project_root)
    capabilities = []
    ignored = 0

    for config_dir in (".claude", ".reasonix"):
        # ── skills ──
        skills_dir = root / config_dir / "skills"
        if skills_dir.is_dir():
            for skill_dir in skills_dir.iterdir():
                if not skill_dir.is_dir(): continue
                if _is_aiwf_internal(skill_dir.name): ignored += 1; continue
                skill_md = skill_dir / "SKILL.md"
                if not skill_md.exists(): continue
                hint = _first_n_lines(skill_md, 8)
                summary = hint[:200].replace("\n", " ").strip()
                dangerous = _has_dangerous_words(hint)
                meta = _capability_metadata(skill_dir.name, "skill", hint, str(skill_md.relative_to(root)))
                if dangerous:
                    risk = _classify_risk_kind(skill_dir.name, "skill", hint)
                    if risk == "unknown": risk = "project_mutation"
                else:
                    risk = "method_advisory"
                capabilities.append({
                    "id": _capability_id(capabilities, "skill", config_dir, skill_dir.name), "kind": "skill",
                    "source": str(skill_md.relative_to(root)),
                    "risk": risk, "roles": ["planner"],
                    "use_policy": _classify_use_policy(risk, bool(dangerous), meta["lifecycle_overlap"]),
                    "may_modify_project": bool(dangerous),
                    "may_access_network": False,
                    "requires_evidence": bool(dangerous),
                    **meta,
                    "summary": summary, "dangerous_words": dangerous,
                })

        # ── slash commands ──
        commands_dir = root / config_dir / "commands"
        if commands_dir.is_dir():
            for cmd_file in sorted(commands_dir.rglob("*.md")):
                hint = _first_n_lines(cmd_file, 5)
                summary = hint[:150].replace("\n", " ").strip()
                name = cmd_file.relative_to(commands_dir).with_suffix("").as_posix()
                meta = _capability_metadata(name, "slash_command", hint, str(cmd_file.relative_to(root)))
                capabilities.append({
                    "id": _capability_id(capabilities, "command", config_dir, name), "kind": "slash_command",
                    "source": str(cmd_file.relative_to(root)),
                    "risk": "method_advisory", "roles": ["planner"],
                    "use_policy": _classify_use_policy("method_advisory", False, meta["lifecycle_overlap"]),
                    "may_modify_project": False, "may_access_network": False,
                    "requires_evidence": False, **meta, "summary": summary,
                })

        # ── settings.json MCP + hooks ──
        settings_path = root / config_dir / "settings.json"
        if settings_path.exists():
            try:
                settings = json.loads(settings_path.read_text(encoding="utf-8"))
                mcp = settings.get("mcpServers", {})
                for name, cfg in mcp.items():
                    if not isinstance(cfg, dict): continue
                    risk = _classify_risk_kind(name, "mcp_server", str(cfg))
                    has_env = bool(cfg.get("env"))
                    meta = _capability_metadata(name, "mcp_server", str(cfg), f"{config_dir}/settings.json")
                    capabilities.append({
                        "id": _capability_id(capabilities, "mcp", config_dir, name), "kind": "mcp_server",
                        "source": f"{config_dir}/settings.json",
                        "risk": risk, "roles": [],
                        "use_policy": _classify_use_policy(risk, False, meta["lifecycle_overlap"]),
                        "may_modify_project": risk in ("project_mutation", "destructive_or_deploy"),
                        "may_access_network": True,
                        "requires_evidence": risk in ("project_mutation", "destructive_or_deploy"),
                        **meta,
                        "summary": f"MCP server '{name}' ({cfg.get('command', '?')})",
                        "has_env": has_env,
                    })
                hooks = settings.get("hooks", {})
                for event_name, entries in hooks.items():
                    if not entries: continue
                    all_aiwf = True
                    for entry in entries:
                        for h in entry.get("hooks", []):
                            cmd = h.get("command", "")
                            if not any(s in cmd for s in AIWF_SCRIPT_HOOKS):
                                all_aiwf = False; break
                    if all_aiwf:
                        ignored += 1; continue
                    overlaps = event_name in AIWF_HOOK_EVENTS
                    meta = _capability_metadata(event_name, "hook", "", f"{config_dir}/settings.json")
                    overlaps = overlaps or meta["lifecycle_overlap"]
                    capabilities.append({
                        "id": _capability_id(capabilities, "hook", config_dir, event_name), "kind": "hook",
                        "source": f"{config_dir}/settings.json",
                        "risk": "unknown", "roles": [],
                        "use_policy": _classify_use_policy("unknown", False, overlaps),
                        "may_modify_project": False, "may_access_network": False,
                        "requires_evidence": False,
                        **meta,
                        "summary": f"Hook on {event_name}" + (" (overlaps AIWF lifecycle)" if overlaps else ""),
                    })
            except Exception: pass

        # ── agents ──
        agents_dir = root / config_dir / "agents"
        if agents_dir.is_dir():
            for agent_file in agents_dir.glob("*.md"):
                if _is_aiwf_internal(agent_file.stem): ignored += 1; continue
                hint = _first_n_lines(agent_file, 5)
                summary = hint[:150].replace("\n", " ").strip()
                dangerous = _has_dangerous_words(hint)
                meta = _capability_metadata(agent_file.stem, "subagent", hint, str(agent_file.relative_to(root)))
                capabilities.append({
                    "id": _capability_id(capabilities, "agent", config_dir, agent_file.stem), "kind": "subagent",
                    "source": str(agent_file.relative_to(root)),
                    "risk": "method_advisory" if not dangerous else "project_mutation",
                    "roles": ["planner"],
                    "use_policy": _classify_use_policy("method_advisory", bool(dangerous), meta["lifecycle_overlap"]),
                    "may_modify_project": bool(dangerous),
                    "may_access_network": False, "requires_evidence": False,
                    **meta,
                    "summary": summary,
                })

    return {"schema_version": 1, "capabilities": capabilities, "aiwf_internal_ignored": ignored}


def write_capabilities_registry(project_root: str, registry: Dict) -> Path:
    root = Path(project_root)
    path = root / CAPABILITIES_JSON
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_capabilities_registry(project_root: str) -> Dict:
    root = Path(project_root)
    path = root / CAPABILITIES_JSON
    legacy_path = root / ".aiwf" / "records" / "events.json"
    if not path.exists() and legacy_path.exists():
        path = legacy_path
    if not path.exists(): return {"schema_version": 1, "capabilities": []}
    try: return json.loads(path.read_text(encoding="utf-8"))
    except: return {"schema_version": 1, "capabilities": []}


def _state_path(project_root: str) -> Path:
    return Path(project_root) / ".aiwf" / "state" / "state.json"


def _read_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mark_capability_planned(project_root: str, capability_id: str) -> Dict[str, Any]:
    """Mark an external capability as intended for use in the current cycle."""
    path = _state_path(project_root)
    state = _read_json(path, {})
    planned = [str(cid) for cid in state.get("planned_capability_ids", []) or [] if str(cid)]
    if capability_id not in planned:
        planned.append(capability_id)
    state["planned_capability_ids"] = planned
    _write_json(path, state)
    return state


def capability_decisions_path(project_root: str) -> Path:
    return Path(project_root) / CAPABILITY_DECISIONS_JSON


def load_capability_decisions(project_root: str) -> Dict[str, Any]:
    data = _read_json(capability_decisions_path(project_root), {"schema_version": 1, "decisions": []})
    if not isinstance(data.get("decisions"), list):
        data["decisions"] = []
    data.setdefault("schema_version", 1)
    return data


def record_capability_decision(project_root: str, capability_id: str, decision: str, decided_by: str = "planner") -> Dict[str, Any]:
    """Record an explicit Planner decision allowing or rejecting lifecycle-overlap capability use."""
    from datetime import datetime, timezone
    if not decision.strip():
        raise ValueError("capability decision text is required")
    data = load_capability_decisions(project_root)
    entry = {
        "capability_id": capability_id,
        "decision": decision,
        "decided_by": decided_by,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    data["decisions"].append(entry)
    _write_json(capability_decisions_path(project_root), data)
    return entry


def _capability_by_id(registry: Dict[str, Any], capability_id: str) -> Dict[str, Any]:
    for cap in registry.get("capabilities", []) or []:
        if cap.get("id") == capability_id:
            return cap
    return {}


def capability_use_blockers(project_root: str) -> List[str]:
    """Block only planned lifecycle-overlap capabilities that lack explicit decision."""
    state = _read_json(_state_path(project_root), {})
    planned = [str(cid) for cid in state.get("planned_capability_ids", []) or [] if str(cid)]
    if not planned:
        return []
    registry = load_capabilities_registry(project_root)
    decisions = load_capability_decisions(project_root).get("decisions", []) or []
    decided = {
        str(d.get("capability_id"))
        for d in decisions
        if str(d.get("decision", "")).strip()
    }
    blockers: List[str] = []
    for capability_id in planned:
        cap = _capability_by_id(registry, capability_id)
        if not cap:
            blockers.append(
                f"planned external capability not found in registry: {capability_id}; run aiwf capability scan"
            )
            continue
        if cap.get("lifecycle_overlap") and cap.get("use_policy") == "requires_user_decision" and capability_id not in decided:
            blockers.append(
                f"planned lifecycle-overlap capability requires explicit Planner decision before execution: {capability_id}"
            )
    return blockers
