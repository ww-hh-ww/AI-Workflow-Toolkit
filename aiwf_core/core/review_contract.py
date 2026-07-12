"""Small helpers shared by review, scope, and closure hooks."""
from __future__ import annotations

from typing import Any, Dict


def add_scope_violation_blocker(
    review: Dict[str, Any], file_path: str, context_id: str
) -> Dict[str, Any]:
    review["closure_allowed"] = False
    blockers = review.setdefault("blockers", [])
    message = f"scope_violation: '{file_path}' modified outside {context_id} scope"
    if message not in blockers:
        blockers.append(message)
    review["result"] = "scope_violation"
    return review
