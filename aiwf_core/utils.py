"""Small pure helpers."""
from __future__ import annotations

import datetime as _dt
import re
from typing import Iterable, Any, List


def now() -> str:
    return _dt.datetime.now().replace(microsecond=0).isoformat()


def slug(value: str, max_len: int = 48) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    return (cleaned or "capture")[:max_len]


def bullet(items: Iterable[str]) -> str:
    materialized = [str(x).strip() for x in items if str(x).strip()]
    return "\n".join(f"- {x}" for x in materialized) if materialized else "- none"


def list_or_default(value: Any, default: List[str]) -> List[str]:
    if isinstance(value, list):
        cleaned = [str(x).strip() for x in value if str(x).strip()]
        return cleaned or list(default)
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return list(default)
