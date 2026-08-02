"""Small YAML compatibility wrapper for AIWF frontmatter.

PyYAML is the normal runtime dependency. The fallback exists so embedded tests
and partially installed environments can still read AIWF's simple frontmatter
instead of failing before governance can explain what is wrong.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List


try:  # pragma: no cover - exercised when PyYAML is installed
    import yaml as yaml  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal envs
    class YAMLError(Exception):
        pass

    def _parse_scalar(value: str) -> Any:
        raw = value.strip()
        lowered = raw.lower()
        if lowered in ("true", "false"):
            return lowered == "true"
        if lowered in ("null", "none", "~"):
            return None
        if raw.startswith("[") and raw.endswith("]"):
            try:
                loaded = json.loads(raw.replace("'", '"'))
                return loaded if isinstance(loaded, list) else raw
            except Exception:
                inner = raw[1:-1].strip()
                return [item.strip().strip("'\"") for item in inner.split(",") if item.strip()]
        if (
            len(raw) >= 2
            and raw[0] == raw[-1]
            and raw[0] in ("'", '"')
        ):
            return raw[1:-1]
        return raw

    def _safe_load(text: str) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        current_key = ""
        for raw_line in text.splitlines():
            if not raw_line.strip() or raw_line.lstrip().startswith("#"):
                continue
            if raw_line.startswith(("  - ", "- ")) and current_key:
                value = raw_line.split("-", 1)[1].strip()
                bucket = result.get(current_key)
                if bucket is None:
                    bucket = []
                    result[current_key] = bucket
                if not isinstance(bucket, list):
                    raise YAMLError(f"frontmatter key is not a list: {current_key}")
                bucket.append(_parse_scalar(value))
                continue
            if raw_line.startswith((" ", "\t")):
                continue
            if ":" not in raw_line:
                raise YAMLError(f"invalid frontmatter line: {raw_line}")
            key, value = raw_line.split(":", 1)
            current_key = key.strip()
            if not current_key:
                raise YAMLError("empty frontmatter key")
            result[current_key] = None if not value.strip() else _parse_scalar(value)
        return result

    def _dump(data: Dict[str, Any], **_: Any) -> str:
        lines: List[str] = []
        for key, value in data.items():
            if isinstance(value, bool):
                lines.append(f"{key}: {'true' if value else 'false'}")
            elif isinstance(value, list):
                if not value:
                    lines.append(f"{key}: []")
                else:
                    lines.append(f"{key}:")
                    for item in value:
                        lines.append(f"  - {item}")
            elif value is None:
                lines.append(f"{key}:")
            else:
                text = str(value)
                if any(ch in text for ch in (":", "#", "\n")):
                    text = json.dumps(text, ensure_ascii=False)
                lines.append(f"{key}: {text}")
        return "\n".join(lines) + "\n"

    class _YamlCompat:
        YAMLError = YAMLError

        @staticmethod
        def safe_load(text: str) -> Dict[str, Any]:
            return _safe_load(text)

        @staticmethod
        def dump(data: Dict[str, Any], **kwargs: Any) -> str:
            return _dump(data, **kwargs)

    yaml = _YamlCompat()
