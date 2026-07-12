"""Index and sync operations — Markdown frontmatter compiled into guarded JSON machine state.

Rules:
- MD frontmatter is compiled into JSON (sync_index). Body is semantic narrative, never inferred.
- Machine-owned runtime fields (status, timestamps, close state) are never overwritten.
- Plan.task_ids is a computed field derived from Task.plan_id, not from MD.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from .state._common import _atomic_write, _read_json as _read_state_json

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _read_json(path: Path, default=None) -> Dict[str, Any]:
    return _read_state_json(path, default)

def _write_json(path: Path, data: Dict[str, Any]) -> None:
    _atomic_write(path, data)

def _empty_json_entry(etype: str, eid: str, fm: Dict[str, Any]) -> Dict[str, Any]:
    """Create a minimal JSON entry from MD frontmatter for a newly registered doc."""
    now = _now()
    entry = {
        "id": eid,
        "type": etype,
        "title": str(fm.get("title", eid) or eid),
        "title_cache": str(fm.get("title", eid) or eid),
        "status": str(fm.get("status", "open") or "open"),
        "created_at": now,
        "updated_at": now,
    }
    if etype == "goal":
        entry["goal_id"] = eid
        entry["parent_goal_id"] = str(fm.get("parent_goal_id") or "")
        entry["child_goal_ids"] = []
        entry["children_order"] = []
        entry["attached_plan_ids"] = []
    elif etype == "plan":
        entry["plan_id"] = eid
        entry["goal_id"] = str(fm.get("goal_id") or "")
        entry["milestone_id"] = str(fm.get("milestone_id") or "")
        entry["task_ids"] = []
        entry["remaining_task_ids"] = []
        entry["report_policy"] = str(fm.get("report_policy", "ask") or "ask")
        entry["dependencies"] = list(fm.get("dependencies", []) or [])
    elif etype == "task":
        entry["goal_id"] = str(fm.get("goal_id") or "")
        entry["plan_id"] = str(fm.get("plan_id") or "")
        entry["milestone_id"] = str(fm.get("milestone_id") or "")
        entry["kind"] = str(fm.get("kind") or "")
    elif etype == "milestone":
        entry["milestone_id"] = eid
        entry["goal_id"] = str(fm.get("goal_id") or "")
        entry["plan_ids"] = list(fm.get("plan_ids", []) or [])
        entry["task_ids"] = list(fm.get("task_ids", []) or [])
    return entry

# ── md parse/write ────────────────────────────────────────────────────

def parse_md(path: Path) -> Tuple[Optional[Dict[str, Any]], str]:
    """Parse a Markdown file into (frontmatter dict, body text).

    Uses real YAML parser. Returns (None, raw_text) if no frontmatter found.
    Frontmatter values retain their YAML types: str, bool, int, list.
    """
    if not path.exists():
        return None, ""

    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None, text

    end_idx = text.find("\n---\n", 4)
    if end_idx == -1:
        return None, text

    fm_text = text[4:end_idx]
    body = text[end_idx + 5:].lstrip("\n")

    try:
        fm: Dict[str, Any] = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        return None, text

    return fm, body

def write_narrative_doc(path: Path, frontmatter: Dict[str, Any], body: str) -> None:
    """Write a narrative .md file with YAML frontmatter + body."""
    path.parent.mkdir(parents=True, exist_ok=True)

    normalized_body = body.lstrip("\n")
    fm_yaml = yaml.dump(dict(frontmatter), default_flow_style=False,
                        allow_unicode=True, sort_keys=False).rstrip("\n")
    content = f"---\n{fm_yaml}\n---\n\n{normalized_body}"
    path.write_text(content, encoding="utf-8")

# ── index check ───────────────────────────────────────────────────────

def check_index(base_dir: str) -> Dict[str, Any]:
    """Check binding, index, and hash sync for all objects with doc_path.

    Returns:
        {"healthy": bool, "issues": [{"type": "task", "id": "TASK-001", "issue": "..."}]}
    """
    issues: List[Dict[str, str]] = []
    root = Path(base_dir)

    # Check tasks
    tasks_path = root / ".aiwf" / "state" / "tasks.json"
    if tasks_path.exists():
        tasks_data = _read_json(tasks_path, {"tasks": []})
        for task in tasks_data.get("tasks", []) or []:
            _check_one(root, task, "task", issues)

    # Check plans
    plans_path = root / ".aiwf" / "state" / "plans.json"
    if plans_path.exists():
        plans_data = _read_json(plans_path, {"plans": []})
        for plan in plans_data.get("plans", []) or []:
            _check_one(root, plan, "plan", issues)

    # Check goals
    goals_path = root / ".aiwf" / "state" / "goals.json"
    if goals_path.exists():
        goals_data = _read_json(goals_path, {"goals": []})
        for goal in goals_data.get("goals", []) or []:
            _check_one(root, goal, "goal", issues)

    # Check milestones
    ms_path = root / ".aiwf" / "state" / "milestones.json"
    if ms_path.exists():
        ms_data = _read_json(ms_path, {"milestones": []})
        for ms in ms_data.get("milestones", []) or []:
            _check_one(root, ms, "milestone", issues)

    return {
        "healthy": len(issues) == 0,
        "issues_count": len(issues),
        "issues": issues[:50],
    }

def _check_one(root: Path, entry: Dict[str, Any], etype: str, issues: List[Dict[str, str]]) -> None:
    eid = entry.get("id", "?")
    doc_path_str = entry.get("doc_path", "")
    if not doc_path_str:
        return  # No narrative doc configured, not an error

    full_path = root / doc_path_str
    if not full_path.exists():
        issues.append({"type": etype, "id": eid, "issue": f"doc_path points to missing file: {doc_path_str}"})
        return

    fm, body = parse_md(full_path)
    if fm is None:
        issues.append({"type": etype, "id": eid, "issue": f"narrative doc missing frontmatter: {doc_path_str}"})
        return

    if fm.get("id") != eid:
        issues.append({"type": etype, "id": eid,
                       "issue": f"frontmatter id '{fm.get('id')}' != JSON id '{eid}'"})

    if fm.get("type") != etype:
        issues.append({"type": etype, "id": eid,
                       "issue": f"frontmatter type '{fm.get('type')}' != JSON type '{etype}'"})

# ── index refresh ─────────────────────────────────────────────────────

FRONTMATTER_TO_JSON_MAP = {
    "goal": {
        "title": "title", "status": "status", "parent_goal_id": "parent_goal_id",
        "child_goal_ids": "child_goal_ids", "attached_plan_ids": "attached_plan_ids",
    },
    "plan": {
        "title": "title", "status": "status", "goal_id": "goal_id",
        "milestone_id": "milestone_id", "report_policy": "report_policy",
        "dependencies": "dependencies",
    },
    "task": {
        "title": "title", "contract_status": "status", "goal_id": "goal_id",
        "plan_id": "plan_id", "milestone_id": "milestone_id", "kind": "kind",
        "executor_required": "requirements.executor_required",
        "tester_required": "requirements.tester_required",
        "reviewer_required": "requirements.reviewer_required",
        "rollback_required": "requirements.rollback_required",
        "tester_write": "requirements.tester_write",
        "report_policy": "report_policy", "dependencies": "dependencies",
    },
    "milestone": {
        "title": "title", "status": "status", "goal_id": "goal_id",
        "plan_ids": "plan_ids", "task_ids": "task_ids",
        "covered_goal_ids": "covered_goal_ids",
        "verification_task_id": "verification_task_id",
        "integration_test_required": "integration_test.required",
        "architecture_review_required": "architecture_review.required",
        "human_acceptance_required": "human_acceptance.required",
        "verification_task_required": "verification_task.required",
        "report_policy": "report_policy",
    },
}

MACHINE_OWNED_FIELDS = {
    "goal": {"created_at", "updated_at"},
    "plan": {"created_at", "updated_at", "task_ids", "remaining_task_ids"},
    "task": {
        "created_at", "updated_at", "activated_at", "closed_at", "close_mode",
        "requirements", "git_origin_ref", "closure",
    },
    "milestone": {
        "created_at", "updated_at", "integration_test", "architecture_review",
        "user_acceptance",
    },
}

def _parse_list_field(value: str) -> list:
    """Parse a frontmatter list field into a Python list."""
    if not value or not str(value).strip():
        return []
    raw = str(value).strip()
    if raw.startswith("[") and raw.endswith("]"):
        import json
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            pass
    return [item.strip() for item in raw.replace(",", " ").split() if item.strip()]

def sync_index(base_dir: str, dry_run: bool = False) -> Dict[str, Any]:
    """Sync MD frontmatter -> JSON for all entities with narrative docs.

    dry_run=True: validate only (sync --check).
    dry_run=False: validate then write JSON.
    """
    root = Path(base_dir)
    state_path = root / ".aiwf" / "state" / "state.json"
    state = _read_json(state_path, {})
    active_task_id = state.get("active_task_id") or ""

    errors: List[str] = []
    changes: List[str] = []
    synced: List[str] = []

    _sync_mission(root, dry_run, changes, errors, synced)

    for etype, json_path, entries_key in [
        ("goal", root / ".aiwf" / "state" / "goals.json", "goals"),
        ("plan", root / ".aiwf" / "state" / "plans.json", "plans"),
        ("task", root / ".aiwf" / "state" / "tasks.json", "tasks"),
        ("milestone", root / ".aiwf" / "state" / "milestones.json", "milestones"),
    ]:
        if not json_path.exists():
            continue
        data = _read_json(json_path)
        entries = data.get(entries_key, []) or []
        mapping = FRONTMATTER_TO_JSON_MAP.get(etype, {})
        machine_fields = MACHINE_OWNED_FIELDS.get(etype, set())
        changed = False

        for entry in entries:
            eid = entry.get("id", "")
            doc_path_str = entry.get("doc_path", "")
            if not doc_path_str:
                dirs = {"goal": ".aiwf/goals", "plan": ".aiwf/plans",
                        "task": ".aiwf/tasks", "milestone": ".aiwf/milestones"}
                subdir = dirs.get(etype, f".aiwf/{etype}s")
                doc_path_str = f"{subdir}/{eid}.md"
                entry["doc_path"] = doc_path_str
            full_path = root / doc_path_str
            if not full_path.exists():
                errors.append(f"{etype}:{eid}: doc_path missing: {doc_path_str}")
                continue

            fm, body = parse_md(full_path)
            if fm is None:
                errors.append(f"{etype}:{eid}: frontmatter missing or unparseable")
                continue

            if fm.get("id") != eid:
                errors.append(f"{etype}:{eid}: frontmatter id '{fm.get('id')}' != JSON id")
                continue
            if fm.get("type") != etype:
                errors.append(f"{etype}:{eid}: frontmatter type '{fm.get('type')}' != {etype}")
                continue

            if not fm.get("title", "").strip():
                errors.append(f"{etype}:{eid}: title is empty")

            if etype == "task":
                if fm.get("kind") == "milestone_verification":
                    if not fm.get("milestone_id", "").strip():
                        errors.append(f"{etype}:{eid}: milestone verification task requires milestone_id")
                else:
                    if not fm.get("goal_id", "").strip():
                        errors.append(f"{etype}:{eid}: goal_id is empty — every task must have a goal")
                    if not fm.get("plan_id", "").strip():
                        errors.append(f"{etype}:{eid}: plan_id is empty — every task must belong to a plan")
            elif etype == "plan":
                if not fm.get("goal_id", "").strip():
                    errors.append(f"{etype}:{eid}: goal_id is empty — every plan must have a goal")

            # Active task: locked JSON fields are not overwritten by sync.
            if active_task_id and etype == "task" and eid == active_task_id:
                synced.append(f"{etype}:{eid}")
                continue

            _LIST_KEYS = ("task_ids", "plan_ids", "covered_goal_ids",
                         "attached_plan_ids", "child_goal_ids", "dependencies",
                         "tester_write")
            _BOOL_KEYS = ("executor_required", "tester_required",
                         "reviewer_required", "rollback_required",
                         "integration_test_required", "architecture_review_required",
                         "human_acceptance_required", "verification_task_required")

            for fm_key, json_key in mapping.items():
                fm_value = fm.get(fm_key)

                if json_key == "title":
                    fm_value = (fm.get("title") or "").strip()
                elif fm_key in _LIST_KEYS or json_key in _LIST_KEYS:
                    if isinstance(fm_value, list):
                        pass  # YAML parsed list, use directly
                    elif fm_value is not None:
                        fm_value = _parse_list_field(str(fm_value))
                    else:
                        fm_value = []
                elif fm_key in _BOOL_KEYS or json_key in _BOOL_KEYS:
                    if isinstance(fm_value, bool):
                        pass  # YAML parsed bool, use directly
                    else:
                        fm_value = str(fm_value or "").strip().lower() in ("true", "yes", "1")
                elif json_key == "parent_goal_id":
                    fm_value = str(fm_value or "").strip()
                elif fm_value is None:
                    fm_value = ""
                else:
                    fm_value = str(fm_value).strip()

                if json_key in machine_fields and "." not in json_key:
                    continue
                if "." in json_key:
                    parts = json_key.split(".")
                    container = entry
                    for part in parts[:-1]:
                        if part not in container:
                            container[part] = {}
                        container = container[part]
                    last = parts[-1]
                    if container.get(last) != fm_value:
                        container[last] = fm_value
                        changed = True
                        changes.append(f"{etype}:{eid}: {json_key} = {fm_value}")
                else:
                    if entry.get(json_key) != fm_value:
                        entry[json_key] = fm_value
                        changed = True
                        changes.append(f"{etype}:{eid}: {json_key} = {fm_value}")

            synced.append(f"{etype}:{eid}")

        if changed and not dry_run:
            tmp_path = Path(str(json_path) + ".tmp")
            _write_json(tmp_path, data)
            tmp_path.rename(json_path)

    # Second pass: register .md files not yet in JSON
    for etype, json_path, entries_key, md_dir in [
        ("goal", root / ".aiwf" / "state" / "goals.json", "goals", root / ".aiwf" / "goals"),
        ("plan", root / ".aiwf" / "state" / "plans.json", "plans", root / ".aiwf" / "plans"),
        ("task", root / ".aiwf" / "state" / "tasks.json", "tasks", root / ".aiwf" / "tasks"),
        ("milestone", root / ".aiwf" / "state" / "milestones.json", "milestones", root / ".aiwf" / "milestones"),
    ]:
        if not md_dir.exists():
            continue
        data = _read_json(json_path, {})
        entries = data.setdefault(entries_key, [])
        registered = {e.get("id", "") for e in entries if e.get("id")}
        for md_file in sorted(md_dir.glob("*.md")):
            eid = md_file.stem
            if eid in registered:
                continue
            fm, body = parse_md(md_file)
            if not fm:
                continue
            if fm.get("id") != eid or fm.get("type") != etype:
                continue
            doc_path_str = f".aiwf/{etype}s/{eid}.md"
            entry = _empty_json_entry(etype, eid, fm)
            entry["doc_path"] = doc_path_str
            entries.append(entry)
            synced.append(f"{etype}:{eid}")
            changes.append(f"{etype}:{eid}: registered from .md")
            if not dry_run:
                tmp_path = Path(str(json_path) + ".tmp")
                _write_json(tmp_path, data)
                tmp_path.rename(json_path)

    # Post-sync: derive Plan.task_ids from Task.plan_id (master relationship)
    _sync_plan_task_relations(root, dry_run, changes)
    _sync_milestone_plan_relations(root, dry_run, changes)
    _sync_goal_children_order(root, dry_run, changes)

    # Always report active task in output
    if active_task_id and f"task:{active_task_id}" not in synced:
        synced.append(f"task:{active_task_id}")

    return {
        "synced": len(synced),
        "changes": changes[:50],
        "errors": errors,
        "locked": False,
    }

def _section_text(body: str, heading: str) -> str:
    lines = body.splitlines()
    capture = False
    captured: List[str] = []
    wanted = f"## {heading}".strip().lower()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            if capture:
                break
            capture = stripped.lower() == wanted
            continue
        if capture:
            captured.append(line)
    return "\n".join(captured).strip()

def _section_bullets(body: str, heading: str) -> List[str]:
    text = _section_text(body, heading)
    items: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        value = stripped[2:].strip()
        if not value or value.lower().startswith("unknown"):
            continue
        items.append(value)
    return items

def _sync_mission(
    root: Path,
    dry_run: bool,
    changes: List[str],
    errors: List[str],
    synced: List[str],
) -> None:
    """Derive state/mission.json from .aiwf/mission.md.

    mission.md is the human/Planner write surface. mission.json is derived state
    for commands, status, UI, and context dispatch.
    """
    md_path = root / ".aiwf" / "mission.md"
    if not md_path.exists():
        return

    fm, body = parse_md(md_path)
    if fm is None:
        fm = {}

    mission_id = str(fm.get("id") or "MISSION-001").strip() or "MISSION-001"
    if fm.get("type") and str(fm.get("type")).strip() != "mission":
        errors.append(f"mission:{mission_id}: frontmatter type '{fm.get('type')}' != mission")
        return

    from .state_schema import default_mission, VALID_MISSION_STATUSES

    state_path = root / ".aiwf" / "state" / "mission.json"
    current = _read_json(state_path, default_mission())
    mission = dict(current or default_mission())

    statement = _section_text(body, "Statement")
    if statement.lower().startswith("unknown"):
        statement = ""
    boundaries = _section_bullets(body, "Boundaries")
    goal_roots = _section_bullets(body, "Goal Roots")
    milestones = _section_bullets(body, "Milestones")

    status = str(fm.get("status") or mission.get("status") or "draft").strip() or "draft"
    if status not in VALID_MISSION_STATUSES:
        errors.append(f"mission:{mission_id}: invalid status '{status}'")
        return

    expected = dict(mission)
    expected["schema_version"] = int(fm.get("schema_version") or expected.get("schema_version") or 1)
    expected["id"] = mission_id
    expected["type"] = "mission"
    expected["status"] = status
    expected["version"] = int(fm.get("version") or expected.get("version") or 1)
    expected["statement"] = statement
    expected["boundaries"] = boundaries
    expected["goal_tree_root_ids"] = goal_roots
    expected["milestone_ids"] = milestones
    expected["updated_at"] = _now()
    expected.setdefault("created_at", current.get("created_at") or "")

    comparable = dict(expected)
    comparable.pop("updated_at", None)
    current_comparable = dict(current or {})
    current_comparable.pop("updated_at", None)
    if not state_path.exists() or comparable != current_comparable:
        changes.append("mission:MISSION-001: synced from mission.md")
        if not dry_run:
            if not expected.get("created_at"):
                expected["created_at"] = _now()
            _write_json(state_path, expected)
    synced.append(f"mission:{mission_id}")

def _sync_plan_task_relations(root: Path, dry_run: bool, changes: List[str]) -> None:
    """Derive Plan.task_ids, task_status, remaining_task_ids from Task.plan_id."""
    plans_path = root / ".aiwf" / "state" / "plans.json"
    tasks_path = root / ".aiwf" / "state" / "tasks.json"
    if not plans_path.exists() or not tasks_path.exists():
        return
    plans_data = _read_json(plans_path)
    tasks_data = _read_json(tasks_path)
    plans = plans_data.get("plans", []) or []
    tasks = tasks_data.get("tasks", []) or []

    # Build plan_id -> active plans map
    plan_by_id = {}
    for p in plans:
        pid = p.get("plan_id") or p.get("id") or ""
        if pid:
            plan_by_id[pid] = p

    for pid, plan in plan_by_id.items():
        linked_tasks = [t for t in tasks
                       if (t.get("plan_id") or t.get("parent_plan") or "") == pid]
        task_ids = sorted(t.get("id", "") for t in linked_tasks if t.get("id"))
        task_status = {}
        for t in linked_tasks:
            tid = t.get("id", "")
            if tid:
                task_status[tid] = t.get("status", "ready")
        remaining = [tid for tid, st in task_status.items()
                    if st not in ("closed", "cancelled")]
        closed_count = sum(1 for st in task_status.values() if st == "closed")

        plan_changed = False
        if plan.get("task_ids") != task_ids:
            plan["task_ids"] = task_ids
            plan_changed = True
        if plan.get("task_status") != task_status:
            plan["task_status"] = task_status
            plan_changed = True
        if plan.get("remaining_task_ids") != remaining:
            plan["remaining_task_ids"] = remaining
            plan_changed = True
        rollup = plan.get("task_rollup", {}) or {}
        expected_rollup = f"{closed_count}/{len(task_ids)} tasks closed under this plan."
        if rollup.get("summary") != expected_rollup or rollup.get("closed_count") != closed_count:
            rollup.update({
                "summary": expected_rollup,
                "closed_count": closed_count,
                "total_count": len(task_ids),
            })
            plan["task_rollup"] = rollup
            plan_changed = True
        if "evidence_rollup" in plan:
            plan.pop("evidence_rollup", None)
            plan_changed = True

        if plan_changed:
            changes.append(f"plan:{pid}: task_ids/status/remaining synced from tasks ({len(task_ids)} tasks)")
            if not dry_run:
                tmp_path = Path(str(plans_path) + ".tmp")
                _write_json(tmp_path, plans_data)
                tmp_path.rename(plans_path)

def _sync_milestone_plan_relations(root: Path, dry_run: bool, changes: List[str]) -> None:
    """Sync plan.milestone_id from milestone.plan_ids. Milestone.md is authoritative."""
    ms_path = root / ".aiwf" / "state" / "milestones.json"
    plans_path = root / ".aiwf" / "state" / "plans.json"
    if not ms_path.exists() or not plans_path.exists():
        return
    ms_data = _read_json(ms_path)
    plans_data = _read_json(plans_path)
    milestones = ms_data.get("milestones", []) or []
    plans = plans_data.get("plans", []) or []

    # Build milestone_id → valid plan_ids from milestone.plan_ids (MD authority)
    ms_plan_map: Dict[str, set] = {}
    for ms in milestones:
        mid = str(ms.get("id") or ms.get("milestone_id") or "").strip()
        if not mid:
            continue
        ms_plan_map[mid] = set(str(pid).strip() for pid in (ms.get("plan_ids", []) or []) if pid)

    # Sync plan.milestone_id from milestone authority, and clean up stale refs
    plan_by_id = {}
    for p in plans:
        pid = str(p.get("plan_id") or p.get("id") or "").strip()
        if pid:
            plan_by_id[pid] = p

    ms_changed = False
    plans_changed = False

    # Ensure milestone.plan_ids only contains plans that actually exist
    for ms in milestones:
        mid = str(ms.get("id") or ms.get("milestone_id") or "").strip()
        if not mid:
            continue
        valid = sorted(pid for pid in ms_plan_map.get(mid, set()) if pid in plan_by_id)
        removed = sorted(pid for pid in ms_plan_map.get(mid, set()) if pid not in plan_by_id)
        if removed:
            changes.append(f"milestone:{mid}: removed {len(removed)} nonexistent plan(s) from plan_ids: {', '.join(removed[:3])}")
        current = sorted(set(ms.get("plan_ids", []) or []))
        if valid != current:
            ms["plan_ids"] = valid
            ms_changed = True
            changes.append(f"milestone:{mid}: plan_ids = {valid}")

    # Sync plan.milestone_id to match milestone.plan_ids
    plan_to_ms: Dict[str, str] = {}
    for ms in milestones:
        mid = str(ms.get("id") or ms.get("milestone_id") or "").strip()
        for pid in ms.get("plan_ids", []) or []:
            plan_to_ms[str(pid).strip()] = mid

    for pid, p in plan_by_id.items():
        expected_mid = plan_to_ms.get(pid, "")
        current_mid = str(p.get("milestone_id") or "").strip()
        if current_mid != expected_mid:
            p["milestone_id"] = expected_mid if expected_mid else None
            plans_changed = True
            if expected_mid:
                changes.append(f"plan:{pid}: milestone_id = {expected_mid}")
            else:
                changes.append(f"plan:{pid}: milestone_id cleared (not in any milestone)")

    if ms_changed and not dry_run:
        tmp_path = Path(str(ms_path) + ".tmp")
        _write_json(tmp_path, ms_data)
        tmp_path.rename(ms_path)

    if plans_changed and not dry_run:
        tmp_path = Path(str(plans_path) + ".tmp")
        _write_json(tmp_path, plans_data)
        tmp_path.rename(plans_path)

def _sync_goal_children_order(root: Path, dry_run: bool, changes: List[str]) -> None:
    """Prune children_order to match child_goal_ids. Remove stale entries from
    removed/reparented goals."""
    goals_path = root / ".aiwf" / "state" / "goals.json"
    if not goals_path.exists():
        return
    goals_data = _read_json(goals_path)
    goals = goals_data.get("goals", []) or []
    changed = False

    for g in goals:
        child_ids = set(g.get("child_goal_ids", []) or [])
        order = g.get("children_order", []) or []
        seen = set()
        pruned = []
        for cid in order:
            if cid in child_ids and cid not in seen:
                pruned.append(cid)
                seen.add(cid)
        # Add any child_goal_ids not yet in order
        for cid in child_ids:
            if cid not in seen:
                pruned.append(cid)
                seen.add(cid)
        if pruned != order:
            gid = g.get("id", "?")
            stale = len(order) - len([c for c in order if c in child_ids])
            g["children_order"] = pruned
            changed = True
            changes.append(f"goal:{gid}: children_order pruned ({stale} stale, {len(pruned)} kept)")

    if changed and not dry_run:
        tmp_path = Path(str(goals_path) + ".tmp")
        _write_json(tmp_path, goals_data)
        tmp_path.rename(goals_path)

# ── narrative doc generation ──────────────────────────────────────────

def generate_narrative_doc_path(entity_id: str, entity_type: str) -> str:
    """Generate relative path for a narrative doc.

    Returns e.g. ".aiwf/plans/PLAN-001.md"
    """
    dirs = {"goal": ".aiwf/goals", "plan": ".aiwf/plans",
            "task": ".aiwf/tasks", "milestone": ".aiwf/milestones"}
    subdir = dirs.get(entity_type, ".aiwf/tasks")
    safe_id = "".join(c for c in entity_id if c.isalnum() or c in "-_.()")
    return f"{subdir}/{safe_id}.md"

# ── default narrative templates ──────────────────────────────────────

_GOAL_TEMPLATE = """# {id} — {title}

## Mission Capability

Unknown — blocks: capability this Goal makes true and who or what uses it

## Success

- Unknown — blocks: observable mission-path behavior, not artifact existence

## Structural Home

Unknown — blocks: why this capability belongs here and which missing pieces or
neighboring capabilities matter

## Plan Handoff

Unknown — blocks: what later Plans must preserve, decide, or prove
"""

_PLAN_TEMPLATE = """# {id} — {title}

## Goal Link And Current Problem

Unknown — blocks: capability advanced and verified limitation or risk changed

## Target Mechanism

Unknown — blocks: operating loop, information model, and main path from entry
to consumer to observable result

## Key Decisions

- Unknown — blocks: important choice, source-backed basis, and credible alternative

## Delivery And Validation

- Unknown — blocks: ordered deliverables or experiments that prove risk early
  and integrate the mechanism
"""

_TASK_TEMPLATE = """# {id} — {title}

## Fixed Contract

### Structural Home

Unknown — blocks: why this Task belongs under its Goal and Plan

### Objective

Unknown — blocks: outcome, not implementation recipe

### Contract Responsibility

Unknown — blocks: the outcome this task is responsible for delivering and proving.
Do not list every file the agent may touch.

### Proof Standard

Done When:

Unknown — blocks: each item tagged Built/Wired/Running

Verification Commands:

| Command | Expected Observable Output |
|---------|----------------------------|
| Unknown — blocks: | Unknown — blocks: |

### Dispatch Decisions

Unknown — blocks: set frontmatter role booleans from the work's real need and
briefly explain any non-obvious choice

## Known Context

Write free bullets with only verified facts that prevent wrong edits or wasted
rediscovery: main path, consumer, invariants, integration anchors, old paths,
tests, representative cases, and real Unknowns.

- Unknown — blocks: verified facts and anchors needed before implementation

## Open Judgment

Add only questions that give Executor, Tester, or Reviewer meaningful room for
independent judgment. Remove this section when there is no open judgment.
"""

_TASK_MS_VERIFY_TEMPLATE = """# {id} — {title}

This task verifies {milestone_id} against `.aiwf/milestones/{milestone_id}.md`.
Do NOT implement feature changes here.
Run integration and acceptance sub-steps through `/aiwf-architect` with the
`milestone-acceptance` lens.

## Objective

Verify milestone {milestone_id}.

## Milestone Reference

- Milestone: {milestone_id}
- Milestone.md: `.aiwf/milestones/{milestone_id}.md`
- This task is: kind=milestone_verification

## Pass Standard Source

The authoritative Pass Standard is in `.aiwf/milestones/{milestone_id}.md`.

## Verification

Unknown — blocks: real commands and runtime scenarios for every Pass Standard
item, plus cross-Goal interfaces and main paths that must remain intact

## Done When

- [ ] Every Pass Standard item was exercised in the running system
- [ ] Main-path evidence recorded with `aiwf milestone integration-test`
- [ ] Architecture integrity recorded with `aiwf milestone arch-review`
- [ ] Assessment recorded: aiwf milestone assess {milestone_id} --verdict PASS
- [ ] Human explicitly confirmed before milestone close
"""

_MILESTONE_TEMPLATE = """# {id} — {title}

## Purpose

Unknown — blocks: stable mission slice being proven

## Coverage

- Unknown — blocks: Goals, Plans, Tasks, and capability claims included

## Pass Standard

- Unknown — blocks: concrete, observable, end-to-end acceptance criteria

## Real Verification

Unknown — blocks: running-system commands or scenarios, evidence needed, and
architecture questions for the `milestone-acceptance` lens

## Human Acceptance

Unknown — blocks: what the human is being asked to accept after technical proof
"""

def create_narrative_for_entity(base_dir: str, entity_id: str, entity_type: str,
                                title: str = "", status: str = "",
                                goal_id: str = "", plan_id: str = "",
                                milestone_id: str = "", kind: str = "",
                                parent_goal_id: str = "") -> str:
    """Create a narrative .md doc with V1 contract frontmatter.

    Returns the doc_path string.
    """
    root = Path(base_dir)
    doc_path_str = generate_narrative_doc_path(entity_id, entity_type)
    title = title or entity_id

    # Frontmatter per V1 Design Contract §3
    fm = {"id": entity_id, "type": entity_type}

    if entity_type == "goal":
        fm["title"] = title
        fm["status"] = status or "open"
        fm["parent_goal_id"] = parent_goal_id
        fm["child_goal_ids"] = []
        fm["attached_plan_ids"] = []
        body = _GOAL_TEMPLATE.format(id=entity_id, title=title)

    elif entity_type == "plan":
        fm["title"] = title
        fm["status"] = status or "open"
        fm["goal_id"] = goal_id
        fm["milestone_id"] = milestone_id
        fm["report_policy"] = "ask"
        fm["dependencies"] = []
        body = _PLAN_TEMPLATE.format(id=entity_id, title=title)

    elif entity_type == "task":
        fm["title"] = title
        fm["contract_status"] = "ready"
        fm["goal_id"] = goal_id
        fm["plan_id"] = plan_id
        fm["milestone_id"] = milestone_id
        fm["kind"] = kind or "implementation"
        is_milestone_verification = kind == "milestone_verification"
        fm["executor_required"] = not is_milestone_verification
        fm["tester_required"] = not is_milestone_verification
        fm["reviewer_required"] = not is_milestone_verification
        fm["rollback_required"] = False
        fm["tester_write"] = []
        fm["report_policy"] = "ask"
        fm["dependencies"] = []
        if kind == "milestone_verification":
            body = _TASK_MS_VERIFY_TEMPLATE.format(id=entity_id, title=title,
                                                   milestone_id=milestone_id or "MS-???")
        else:
            body = _TASK_TEMPLATE.format(id=entity_id, title=title)

    elif entity_type == "milestone":
        fm["title"] = title
        fm["status"] = status or "open"
        fm["goal_id"] = goal_id
        fm["plan_ids"] = []
        fm["task_ids"] = []
        fm["covered_goal_ids"] = []
        fm["integration_test_required"] = True
        fm["architecture_review_required"] = True
        fm["human_acceptance_required"] = True
        fm["verification_task_required"] = True
        fm["verification_task_id"] = ""
        fm["report_policy"] = "ask"
        body = _MILESTONE_TEMPLATE.format(id=entity_id, title=title)

    else:
        fm["title"] = title
        body = f"# {entity_id} — {title}\n\nUnknown — blocks: unsupported narrative type requires explicit content.\n"

    full_path = root / doc_path_str
    write_narrative_doc(full_path, fm, body)
    return doc_path_str
