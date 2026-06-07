"""External research evidence: low-trust until Planner promotes it."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(base_dir: str) -> Path:
    return Path(base_dir) / ".aiwf" / "research" / "external.json"


def default_research() -> Dict:
    return {"schema_version": 1, "records": []}


def load_research(base_dir: str) -> Dict:
    path = _path(base_dir)
    if not path.exists():
        return default_research()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default_research()
    if not isinstance(data.get("records"), list):
        data["records"] = []
    data.setdefault("schema_version", 1)
    return data


def save_research(base_dir: str, data: Dict) -> Path:
    path = _path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _next_id(records: List[Dict]) -> str:
    return f"XR-{len(records) + 1:03d}"


def record_research(
    base_dir: str,
    source: str,
    query: str,
    claims: Optional[List[str]] = None,
    links: Optional[List[str]] = None,
    time_window: str = "",
    confidence: str = "low",
) -> Dict:
    data = load_research(base_dir)
    record = {
        "id": _next_id(data["records"]),
        "status": "raw",
        "source": source,
        "query": query,
        "time_window": time_window,
        "claims": claims or [],
        "links": links or [],
        "confidence": confidence,
        "used_for_decision": "",
        "promoted_by": "",
        "recorded_at": _now(),
    }
    data["records"].append(record)
    save_research(base_dir, data)
    return record


def promote_research(base_dir: str, research_id: str, decision: str, promoted_by: str = "planner") -> Dict:
    data = load_research(base_dir)
    for record in data["records"]:
        if record.get("id") == research_id:
            record["status"] = "promoted"
            record["used_for_decision"] = decision
            record["promoted_by"] = promoted_by
            record["promoted_at"] = _now()
            save_research(base_dir, data)
            return record
    raise ValueError(f"research record not found: {research_id}")


def list_research(base_dir: str, include_promoted: bool = True) -> List[Dict]:
    records = load_research(base_dir).get("records", [])
    if include_promoted:
        return records
    return [r for r in records if r.get("status") != "promoted"]
