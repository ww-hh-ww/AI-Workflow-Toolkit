"""AIWF Idea Inbox — volatile, low-trust planning inputs. Not requirements/decisions."""
from __future__ import annotations

import json, re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


IDEAS_HEADER = """# AIWF Ideas

Ideas are volatile, low-trust planning inputs.
They are not requirements, decisions, roadmap items, or execution contracts until promoted by Planner.
Expired ideas should not guide planning unless revived by user/Planner.

"""


def _now(): return datetime.now(timezone.utc)
def _ts(): return _now().isoformat()


def _ideas_path(project_root: str) -> Path:
    return Path(project_root) / ".aiwf" / "reports" / "ideas.md"


def _ensure_exists(path: Path):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(IDEAS_HEADER, encoding="utf-8")


def ensure_ideas_file(project_root: str) -> Path:
    """Create the human idea inbox if missing and return its path."""
    path = _ideas_path(project_root)
    _ensure_exists(path)
    return path


def _parse_ideas(text: str) -> List[Dict[str, Any]]:
    """Parse ideas.md into structured records. Each idea is a markdown section."""
    ideas = []
    current = None
    for line in text.split("\n"):
        if line.startswith("## ") and "Active Ideas" in line:
            continue
        if line.startswith("## ") and "Adopted Ideas" in line:
            continue
        if line.startswith("## ") and "Expired Ideas" in line:
            continue
        # Idea header: ### IDEA-YYYYMMDD-HHMMSS | status | tags
        m = re.match(r'^### (IDEA-\d{8}-\d{6}(?:-\d{6})?)\s*\|\s*(\w+)\s*(?:\|\s*(.*))?', line)
        if m:
            current = {"id": m.group(1), "status": m.group(2), "tags": [],
                       "text": "", "source": "", "expires_at": "", "promote_target": "",
                       "promote_note": "", "expired_reason": "", "created_at": ""}
            if m.group(3):
                current["tags"] = [t.strip() for t in m.group(3).split(",") if t.strip()]
            ideas.append(current)
            continue
        if current is not None and line.startswith("- "):
            content = line[2:].strip()
            if content.startswith("text: "): current["text"] = content[6:]
            elif content.startswith("source: "): current["source"] = content[8:]
            elif content.startswith("created: "): current["created_at"] = content[9:]
            elif content.startswith("expires: "): current["expires_at"] = content[9:]
            elif content.startswith("promote_target: "): current["promote_target"] = content[17:]
            elif content.startswith("promote_note: "): current["promote_note"] = content[14:]
            elif content.startswith("expired_reason: "): current["expired_reason"] = content[16:]
    return ideas


def _write_ideas(path: Path, ideas: List[Dict[str, Any]]):
    """Serialize ideas back to markdown, grouped by status."""
    active = [i for i in ideas if i["status"] in ("raw", "candidate")]
    adopted = [i for i in ideas if i["status"] == "adopted"]
    expired = [i for i in ideas if i["status"] == "expired"]
    lines = [IDEAS_HEADER.rstrip()]
    for group_name, group_ideas in [("Active Ideas", active), ("Adopted Ideas", adopted), ("Expired Ideas", expired)]:
        lines.append(f"\n## {group_name}\n")
        if not group_ideas:
            lines.append("(none)\n")
        else:
            for idea in group_ideas:
                tags = ", ".join(idea.get("tags", []))
                lines.append(f"### {idea['id']} | {idea['status']}" + (f" | {tags}" if tags else ""))
                if idea.get("text"): lines.append(f"- text: {idea['text']}")
                if idea.get("source"): lines.append(f"- source: {idea['source']}")
                if idea.get("created_at"): lines.append(f"- created: {idea['created_at']}")
                if idea.get("expires_at"): lines.append(f"- expires: {idea['expires_at']}")
                if idea.get("promote_target"): lines.append(f"- promote_target: {idea['promote_target']}")
                if idea.get("promote_note"): lines.append(f"- promote_note: {idea['promote_note']}")
                if idea.get("expired_reason"): lines.append(f"- expired_reason: {idea['expired_reason']}")
                lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def capture_idea(project_root: str, text: str, tags: Optional[List[str]] = None,
                 source: str = "user", expires_days: int = 14) -> Dict[str, Any]:
    """Capture a new idea. Does NOT modify goal/quality_brief/PROJECT-MAP/decision."""
    path = _ideas_path(project_root)
    _ensure_exists(path)
    ideas = _parse_ideas(path.read_text(encoding="utf-8"))

    ts = _ts()
    idea_id = f"IDEA-{_now().strftime('%Y%m%d-%H%M%S-%f')}"
    expires = (_now() + timedelta(days=expires_days)).isoformat()

    idea = {
        "id": idea_id, "status": "raw", "created_at": ts,
        "source": source, "text": text, "tags": tags or [],
        "expires_at": expires, "promote_target": "", "promote_note": "",
        "expired_reason": "",
    }
    ideas.append(idea)
    _write_ideas(path, ideas)
    return idea


def is_idea_expired(idea: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    """Check if an idea should be considered expired/stale by time.
    - status=='expired' → True
    - status=='adopted' → False (not expired, just promoted)
    - expires_at present and <= now → True
    """
    if idea.get("status") == "expired":
        return True
    if idea.get("status") == "adopted":
        return False
    expires = idea.get("expires_at", "")
    if not expires:
        return False  # no expiry set, don't guess
    now = now or _now()
    try:
        # Parse ISO, strip tz if present and compare as aware
        exp_dt = datetime.fromisoformat(expires)
        # If exp_dt is naive and now is aware, or vice versa, make consistent
        if exp_dt.tzinfo is None and now.tzinfo is not None:
            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
        elif exp_dt.tzinfo is not None and now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return exp_dt <= now
    except (ValueError, TypeError):
        return False


def is_idea_active(idea: Dict[str, Any]) -> bool:
    """An idea is active if raw/candidate and not expired by time."""
    if idea.get("status") not in ("raw", "candidate"):
        return False
    return not is_idea_expired(idea)


def list_ideas(project_root: str, include_expired: bool = False) -> List[Dict[str, Any]]:
    """List ideas. By default excludes adopted, expired, and time-expired raw/candidate."""
    path = _ideas_path(project_root)
    if not path.exists():
        return []
    ideas = _parse_ideas(path.read_text(encoding="utf-8"))
    if not include_expired:
        # Default: only active (raw/candidate, not time-expired, not adopted, not manually expired)
        ideas = [i for i in ideas if is_idea_active(i)]
    return ideas


def _find_idea(ideas: List[Dict], idea_id: str) -> Optional[Dict]:
    for i in ideas:
        if i["id"] == idea_id:
            return i
    return None


def promote_idea(project_root: str, idea_id: str, target: str = "", note: str = "") -> Dict[str, Any]:
    """Promote an idea to adopted. Does NOT modify formal state.
    Raises ValueError if idea_id not found.
    """
    path = _ideas_path(project_root)
    _ensure_exists(path)
    ideas = _parse_ideas(path.read_text(encoding="utf-8"))
    idea = _find_idea(ideas, idea_id)
    if not idea:
        raise ValueError(f"idea not found: {idea_id}")
    idea["status"] = "adopted"
    idea["promote_target"] = target
    idea["promote_note"] = note
    _write_ideas(path, ideas)
    return idea


def expire_idea(project_root: str, idea_id: str, reason: str = "") -> Dict[str, Any]:
    """Expire an idea. Does NOT delete. Raises ValueError if idea_id not found."""
    path = _ideas_path(project_root)
    _ensure_exists(path)
    ideas = _parse_ideas(path.read_text(encoding="utf-8"))
    idea = _find_idea(ideas, idea_id)
    if not idea:
        raise ValueError(f"idea not found: {idea_id}")
    idea["status"] = "expired"
    idea["expired_reason"] = reason
    _write_ideas(path, ideas)
    return idea
