"""Shared helpers for the Plan integration transaction."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def find_plan(data: Dict[str, Any], plan_id: str) -> Optional[Dict[str, Any]]:
    return next(
        (
            plan for plan in data.get("plans", []) or []
            if isinstance(plan, dict)
            and str(plan.get("plan_id") or plan.get("id") or "") == plan_id
        ),
        None,
    )
