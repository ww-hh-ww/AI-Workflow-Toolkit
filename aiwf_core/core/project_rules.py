"""AIWF Project Rules — confirmed project-local guidance, stronger than advisory lessons."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_RULES = """# AIWF Project Rules

Project rules are confirmed project-local guidance.
They are stronger than advisory lessons, but weaker than hard gates.
They should be concise, current, and maintained by Planner/Reviewer.

Rules are not raw history.
Rules are not ideas.
Rules are not full reports.

"""


def _now(): return datetime.now(timezone.utc)
def _ts(): return _now().isoformat()


def _path(project_root: str) -> Path:
    return Path(project_root) / ".aiwf" / "project-rules.md"


def _ensure(path: Path):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_RULES, encoding="utf-8")


def _parse(text: str) -> List[Dict[str, Any]]:
    rules = []
    current = None
    for line in text.split("\n"):
        # Section headers — don't parse these as rules
        if line.startswith("## "):
            current = None
            continue
        m = re.match(r'^### (RULE-\d{8}-\d{6}-\d{6})\s*\|\s*(\S+)\s*\|\s*(\S+)\s*(?:\|\s*(.*))?', line)
        if m:
            current = {
                "id": m.group(1), "status": m.group(2), "type": m.group(3),
                "text": "", "source": "", "tags": [],
                "created_at": "", "retired_reason": "", "global_candidate_note": "",
            }
            if m.group(4):
                current["tags"] = [t.strip() for t in m.group(4).split(",") if t.strip()]
            rules.append(current)
            continue
        if current is not None and line.startswith("- "):
            content = line[2:].strip()
            if content.startswith("text: "): current["text"] = content[6:]
            elif content.startswith("source: "): current["source"] = content[8:]
            elif content.startswith("created: "): current["created_at"] = content[9:]
            elif content.startswith("retired: "): current["retired_reason"] = content[9:]
            elif content.startswith("global_candidate: "): current["global_candidate_note"] = content[18:]
    return rules


def _write(path: Path, rules: List[Dict[str, Any]]):
    active_rules = [r for r in rules if r["status"] == "active" and r["type"] == "rule"]
    negative_rules = [r for r in rules if r["status"] == "active" and r["type"] == "negative_rule"]
    global_candidates = [r for r in rules if r["type"] == "global_candidate"]
    retired = [r for r in rules if r["status"] in ("retired", "superseded")]

    lines = [DEFAULT_RULES.rstrip()]
    for group_name, group_rules in [
        ("Active Rules", active_rules),
        ("Negative Rules / Guardrails", negative_rules),
        ("Retired / Superseded Rules", retired),
        ("Global Lesson Candidates", global_candidates),
    ]:
        lines.append(f"\n## {group_name}\n")
        if not group_rules:
            lines.append("(none)\n")
        else:
            for r in group_rules:
                tags = ", ".join(r.get("tags", []))
                lines.append(f"### {r['id']} | {r['status']} | {r['type']}" + (f" | {tags}" if tags else ""))
                if r.get("text"): lines.append(f"- text: {r['text']}")
                if r.get("source"): lines.append(f"- source: {r['source']}")
                if r.get("created_at"): lines.append(f"- created: {r['created_at']}")
                if r.get("retired_reason"): lines.append(f"- retired: {r['retired_reason']}")
                if r.get("global_candidate_note"): lines.append(f"- global_candidate: {r['global_candidate_note']}")
                lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _add_rule(project_root: str, text: str, rule_type: str, source: str = "",
              tags: Optional[List[str]] = None) -> Dict[str, Any]:
    path = _path(project_root)
    _ensure(path)
    rules = _parse(path.read_text(encoding="utf-8"))
    rule_id = f"RULE-{_now().strftime('%Y%m%d-%H%M%S-%f')}"
    rule = {
        "id": rule_id, "status": "active", "type": rule_type,
        "text": text, "source": source, "tags": tags or [],
        "created_at": _ts(), "retired_reason": "", "global_candidate_note": "",
    }
    rules.append(rule)
    _write(path, rules)
    return rule


def add_project_rule(project_root: str, text: str, source: str = "",
                     tags: Optional[List[str]] = None) -> Dict[str, Any]:
    return _add_rule(project_root, text, "rule", source, tags)


def add_negative_rule(project_root: str, text: str, source: str = "",
                      tags: Optional[List[str]] = None) -> Dict[str, Any]:
    return _add_rule(project_root, text, "negative_rule", source, tags)


def list_project_rules(project_root: str, include_retired: bool = False) -> List[Dict[str, Any]]:
    path = _path(project_root)
    if not path.exists():
        return []
    rules = _parse(path.read_text(encoding="utf-8"))
    if not include_retired:
        rules = [r for r in rules if r["status"] != "retired"]
    return rules


def _find(rules: List[Dict], rule_id: str) -> Optional[Dict]:
    for r in rules:
        if r["id"] == rule_id:
            return r
    return None


def retire_rule(project_root: str, rule_id: str, reason: str = "") -> Dict[str, Any]:
    path = _path(project_root)
    _ensure(path)
    rules = _parse(path.read_text(encoding="utf-8"))
    rule = _find(rules, rule_id)
    if not rule:
        raise ValueError(f"rule not found: {rule_id}")
    rule["status"] = "retired"
    rule["retired_reason"] = reason
    _write(path, rules)
    return rule


def mark_global_candidate(project_root: str, rule_id: str, note: str = "") -> Dict[str, Any]:
    path = _path(project_root)
    _ensure(path)
    rules = _parse(path.read_text(encoding="utf-8"))
    rule = _find(rules, rule_id)
    if not rule:
        raise ValueError(f"rule not found: {rule_id}")
    rule["type"] = "global_candidate"
    rule["global_candidate_note"] = note
    _write(path, rules)
    return rule
