"""Index and sync operations — Markdown frontmatter compiled into guarded JSON machine state.

Rules:
- MD frontmatter is compiled into JSON (sync_index). Body is semantic narrative, never inferred.
- Active Task.md is frozen by contract_hash (frontmatter + body) after activation.
- Machine-owned runtime fields (status, timestamps, frozen hash, close state) are never overwritten.
- Plan.task_ids is a computed field derived from Task.plan_id, not from MD.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default=None) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else (default or {})
    except Exception:
        return default or {}


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ── hash ──────────────────────────────────────────────────────────────

# Canonical frontmatter keys that form the task execution contract.
# When these change after activation, the contract is considered dirty.
_TASK_CONTRACT_FM_KEYS = [
    "title", "goal_id", "plan_id", "milestone_id", "kind",
    "executor_required", "tester_required", "reviewer_required",
    "rollback_required", "dependencies",
]


def compute_content_hash(md_text: str) -> str:
    """SHA-256 of Markdown body (without frontmatter).

    Returns "sha256:<hex>".
    """
    digest = hashlib.sha256(md_text.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def compute_contract_hash(fm: Dict[str, Any], body: str) -> str:
    """SHA-256 of canonical frontmatter keys + normalized body.

    Contract keys are YAML-serialized for deterministic output.
    Returns "sha256:<hex>".
    """
    contract = {}
    if fm:
        for key in _TASK_CONTRACT_FM_KEYS:
            contract[key] = fm.get(key)
    canonical = yaml.dump(contract, default_flow_style=False,
                         allow_unicode=True, sort_keys=True).rstrip("\n")
    canonical += "\n" + body.lstrip("\n")
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


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


def write_narrative_doc(path: Path, frontmatter: Dict[str, Any], body: str) -> str:
    """Write a narrative .md file with YAML frontmatter + body.

    Returns the SHA-256 hash of the normalized body (not frontmatter).
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    normalized_body = body.lstrip("\n")
    fm_yaml = yaml.dump(dict(frontmatter), default_flow_style=False,
                        allow_unicode=True, sort_keys=False).rstrip("\n")
    content = f"---\n{fm_yaml}\n---\n\n{normalized_body}"
    path.write_text(content, encoding="utf-8")

    return compute_content_hash(normalized_body)


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

    expected_hash = entry.get("doc_hash", "")
    if expected_hash:
        actual_hash = compute_content_hash(body)
        if actual_hash != expected_hash:
            issues.append({"type": etype, "id": eid,
                           "issue": f"doc_hash mismatch (body changed since last index refresh)"})

    # Active task freeze check
    if etype == "task" and entry.get("status") == "active":
        frozen = entry.get("frozen_doc_hash", "")
        if frozen and expected_hash and frozen != expected_hash:
            issues.append({"type": etype, "id": eid,
                           "issue": "ACTIVE TASK .md was modified during execution (doc_hash != frozen_doc_hash)"})


# ── index refresh ─────────────────────────────────────────────────────

def refresh_index(base_dir: str) -> Dict[str, Any]:
    """Scan all narrative .md files and update JSON doc_hash, title_cache, summary_cache.

    Returns summary of what was updated.
    """
    root = Path(base_dir)
    updated: List[str] = []

    for etype, state_path, entries_key in [
        ("task", root / ".aiwf" / "state" / "tasks.json", "tasks"),
        ("plan", root / ".aiwf" / "state" / "plans.json", "plans"),
        ("goal", root / ".aiwf" / "state" / "goals.json", "goals"),
        ("milestone", root / ".aiwf" / "state" / "milestones.json", "milestones"),
    ]:
        if not state_path.exists():
            continue
        data = _read_json(state_path)
        entries = data.get(entries_key, []) or []
        changed = False
        for entry in entries:
            doc_path_str = entry.get("doc_path", "")
            if not doc_path_str:
                dirs = {"goal": ".aiwf/goals", "plan": ".aiwf/plans",
                        "task": ".aiwf/tasks", "milestone": ".aiwf/milestones"}
                subdir = dirs.get(etype, f".aiwf/{etype}s")
                doc_path_str = f"{subdir}/{eid}.md"
                entry["doc_path"] = doc_path_str
            full_path = root / doc_path_str
            if not full_path.exists():
                continue
            fm, body = parse_md(full_path)
            if fm is None:
                continue

            new_hash = compute_content_hash(body)
            if entry.get("doc_hash") != new_hash:
                entry["doc_hash"] = new_hash
                entry["doc_updated_at"] = _now()
                changed = True

            # Update title: frontmatter.title primary, body H1 fallback
            fm_title = (fm or {}).get("title", "").strip()
            if fm_title:
                title = fm_title
            elif body.strip():
                first_line = body.strip().split("\n")[0]
                title = first_line[2:].strip() if first_line.startswith("# ") else ""
            else:
                title = ""
            if title:
                if entry.get("title") != title:
                    entry["title"] = title
                    changed = True
                if entry.get("title_cache") != title:
                    entry["title_cache"] = title

            updated.append(f"{etype}:{entry.get('id', '?')}")

        if changed:
            _write_json(state_path, data)

    return {"refreshed": len(updated), "updated": updated}


# ── index repair ──────────────────────────────────────────────────────

def repair_index(base_dir: str) -> Dict[str, Any]:
    """Safe repairs only: recompute doc_hash, fix missing frontmatter, update caches.

    Does NOT modify Markdown body content.
    """
    root = Path(base_dir)
    repaired: List[str] = []
    fixed_files: List[str] = []

    for etype, state_path, entries_key, doc_subdir in [
        ("task", root / ".aiwf" / "state" / "tasks.json", "tasks", ".aiwf/tasks"),
        ("plan", root / ".aiwf" / "state" / "plans.json", "plans", ".aiwf/plans"),
        ("goal", root / ".aiwf" / "state" / "goals.json", "goals", ".aiwf/goals"),
        ("milestone", root / ".aiwf" / "state" / "milestones.json", "milestones", ".aiwf/milestones"),
    ]:
        if not state_path.exists():
            continue
        data = _read_json(state_path)
        entries = data.get(entries_key, []) or []
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
                continue

            fm, body = parse_md(full_path)

            # Fix missing frontmatter
            if fm is None:
                fm = {"id": eid, "type": etype}
                write_narrative_doc(full_path, fm, body)
                fm, body = parse_md(full_path)
                fixed_files.append(str(doc_path_str))

            # Fix missing id/type in frontmatter
            need_rewrite = False
            if fm and fm.get("id") != eid:
                fm["id"] = eid
                need_rewrite = True
            if fm and fm.get("type") != etype:
                fm["type"] = etype
                need_rewrite = True
            if need_rewrite and fm:
                write_narrative_doc(full_path, fm, body)
                fixed_files.append(str(doc_path_str))

            # Recompute hash
            if body:
                actual_hash = compute_content_hash(body)
                if entry.get("doc_hash") != actual_hash:
                    entry["doc_hash"] = actual_hash
                    entry["doc_updated_at"] = _now()
                    changed = True

                # Update title_cache: frontmatter.title primary, body H1 fallback
                fm_title = (fm or {}).get("title", "").strip()
                if fm_title:
                    title = fm_title
                elif body.strip():
                    first_line = body.strip().split("\n")[0]
                    title = first_line[2:].strip() if first_line.startswith("# ") else ""
                else:
                    title = ""
                if title and entry.get("title_cache") != title:
                    entry["title_cache"] = title
                    changed = True

            repaired.append(f"{etype}:{eid}")

        if changed:
            _write_json(state_path, data)

    return {"repaired": len(repaired), "items": repaired, "fixed_files": fixed_files}


# ── sync ──────────────────────────────────────────────────────────────

FRONTMATTER_TO_JSON_MAP = {
    "goal": {
        "title": "title",
        "status": "status",
        "parent_goal_id": "parent_goal_id",
        "child_goal_ids": "child_goal_ids",
        "attached_plan_ids": "attached_plan_ids",
        "report_policy": "report_policy",
    },
    "plan": {
        "title": "title",
        "status": "status",
        "goal_id": "goal_id",
        "milestone_id": "milestone_id",
        "report_policy": "report_policy",
        "dependencies": "dependencies",
    },
    "task": {
        "title": "title",
        "goal_id": "goal_id",
        "plan_id": "plan_id",
        "milestone_id": "milestone_id",
        "kind": "kind",
        "executor_required": "requirements.executor_required",
        "tester_required": "requirements.tester_required",
        "reviewer_required": "requirements.reviewer_required",
        "rollback_required": "requirements.rollback_required",
        "report_policy": "report_policy",
        "dependencies": "dependencies",
    },
    "milestone": {
        "title": "title",
        "status": "status",
        "goal_id": "goal_id",
        "plan_ids": "plan_ids",
        "task_ids": "task_ids",
        "covered_goal_ids": "covered_goal_ids",
        "verification_task_id": "verification_task_id",
        "integration_test_required": "integration_test.required",
        "architecture_review_required": "architecture_review.required",
        "human_acceptance_required": "human_acceptance.required",
        "verification_task_required": "verification_task.required",
        "report_policy": "report_policy",
    },
}

MACHINE_OWNED_TASK_FIELDS = {
    "status", "frozen_doc_hash", "activated_at", "closed_at", "close_mode",
    "changed_files", "evidence_ids", "test_ids", "review_ids",
    "created_at", "updated_at", "doc_hash", "doc_updated_at",
    "requirements",  # sub-object; only explicit dotted keys synced
}

MACHINE_OWNED_FIELDS = {
    "task": MACHINE_OWNED_TASK_FIELDS,
    "goal": {"created_at", "updated_at", "doc_hash", "doc_updated_at",
             "goal_version", "original_intent", "current_goal", "active_goal",
             "goal_status", "confirmed", "quality_brief"},
    "plan": {"created_at", "updated_at", "doc_hash", "doc_updated_at",
             "remaining_task_ids", "plan_status"},
    "milestone": {"created_at", "updated_at", "doc_hash", "doc_updated_at",
                  "integration_test", "architecture_review", "user_acceptance"},
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
                if not fm.get("goal_id", "").strip():
                    errors.append(f"{etype}:{eid}: goal_id is empty — every task must have a goal")
                if not fm.get("plan_id", "").strip():
                    errors.append(f"{etype}:{eid}: plan_id is empty — every task must belong to a plan")
            elif etype == "plan":
                if not fm.get("goal_id", "").strip():
                    errors.append(f"{etype}:{eid}: goal_id is empty — every plan must have a goal")

            # Active task: only the active Task.md is locked. Others sync normally.
            if active_task_id and etype == "task" and eid == active_task_id:
                new_hash = compute_contract_hash(fm or {}, body) if body else ""
                frozen = entry.get("frozen_contract_hash", "")
                if frozen and new_hash != frozen:
                    changes.append(f"task:{eid}: WARNING active Task.md changed after activation (not compiled)")
                changes.append(f"active task {eid}: Task.md frozen, skipped (contract from activation)")
                synced.append(f"{etype}:{eid}")
                continue

            _LIST_KEYS = ("task_ids", "plan_ids", "covered_goal_ids",
                         "attached_plan_ids", "child_goal_ids", "dependencies")
            _BOOL_KEYS = ("executor_required", "tester_required",
                         "reviewer_required", "rollback_required")

            for fm_key, json_key in mapping.items():
                fm_value = fm.get(fm_key)

                if json_key == "title":
                    fm_value = (fm.get("title") or "").strip()
                elif json_key in _LIST_KEYS:
                    if isinstance(fm_value, list):
                        pass  # YAML parsed list, use directly
                    elif fm_value is not None:
                        fm_value = _parse_list_field(str(fm_value))
                    else:
                        fm_value = []
                elif json_key in _BOOL_KEYS or "." in json_key:
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

            if body:
                new_hash = compute_content_hash(body)
                if entry.get("doc_hash") != new_hash:
                    entry["doc_hash"] = new_hash
                    entry["doc_updated_at"] = _now()
                    changed = True
                    changes.append(f"{etype}:{eid}: hash updated")

            synced.append(f"{etype}:{eid}")

        if changed and not dry_run:
            tmp_path = Path(str(json_path) + ".tmp")
            _write_json(tmp_path, data)
            tmp_path.rename(json_path)

    # Post-sync: derive Plan.task_ids from Task.plan_id (master relationship)
    _sync_plan_task_relations(root, dry_run, changes)
    _sync_milestone_plan_relations(root, dry_run, changes)
    _sync_goal_children_order(root, dry_run, changes)

    # Always report active task status in output
    if active_task_id and not any("frozen" in c for c in changes):
        task_doc = root / ".aiwf" / "tasks" / f"{active_task_id}.md"
        if task_doc.exists():
            changes.append(f"active task {active_task_id}: Task.md frozen, skipped (contract from activation)")
            synced.append(f"task:{active_task_id}")

    return {
        "synced": len(synced),
        "changes": changes[:50],
        "errors": errors,
        "locked": False,  # narrowed: only active Task.md is locked, not all governance
    }


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
        rollup = plan.get("evidence_rollup", {}) or {}
        expected_rollup = f"{closed_count}/{len(task_ids)} tasks closed under this plan."
        if rollup.get("summary") != expected_rollup or rollup.get("closed_task_count") != closed_count:
            plan["evidence_rollup"] = {"summary": expected_rollup,
                                       "closed_task_count": closed_count,
                                       "total_task_count": len(task_ids)}
            plan_changed = True

        if plan_changed:
            changes.append(f"plan:{pid}: task_ids/status/remaining synced from tasks ({len(task_ids)} tasks)")
            if not dry_run:
                tmp_path = Path(str(plans_path) + ".tmp")
                _write_json(tmp_path, plans_data)
                tmp_path.rename(plans_path)


def _sync_milestone_plan_relations(root: Path, dry_run: bool, changes: List[str]) -> None:
    """Derive milestone.plan_ids from plan.milestone_id (reverse reference)."""
    ms_path = root / ".aiwf" / "state" / "milestones.json"
    plans_path = root / ".aiwf" / "state" / "plans.json"
    if not ms_path.exists() or not plans_path.exists():
        return
    ms_data = _read_json(ms_path)
    plans_data = _read_json(plans_path)
    milestones = ms_data.get("milestones", []) or []
    plans = plans_data.get("plans", []) or []

    # Build milestone_id → plan_ids from plan.milestone_id
    ms_plan_map: Dict[str, List[str]] = {}
    for p in plans:
        mid = str(p.get("milestone_id") or "").strip()
        pid = str(p.get("plan_id") or p.get("id") or "").strip()
        if mid and pid:
            ms_plan_map.setdefault(mid, []).append(pid)

    changed = False
    for ms in milestones:
        mid = str(ms.get("id") or ms.get("milestone_id") or "").strip()
        if not mid:
            continue
        derived = sorted(set(ms_plan_map.get(mid, [])))
        current = sorted(set(ms.get("plan_ids", []) or []))
        if derived != current:
            ms["plan_ids"] = derived
            changed = True
            changes.append(f"milestone:{mid}: plan_ids synced from plan.milestone_id ({len(derived)} plans)")

    if changed and not dry_run:
        tmp_path = Path(str(ms_path) + ".tmp")
        _write_json(tmp_path, ms_data)
        tmp_path.rename(ms_path)


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

## Intent

(fill)

## Success Criteria

(fill)

## Non-goals

(fill)

## Context

(fill)

## Human Decisions

(fill)

## Open Questions

(fill)
"""

_PLAN_TEMPLATE = """# {id} — {title}

## Intent

(fill)

## Current Problems

(fill)

## Target Design

(fill)

## Key Decisions

(fill)

## Non-goals

(fill)

## Task Breakdown

(fill)

## Risks

(fill)

## Validation Strategy

(fill)

## Open Questions

(fill)
"""

_TASK_TEMPLATE = """# {id} — {title}

## Objective

(fill)

## Scope

(fill)

## Allowed Write

(fill)

## Forbidden Write

(fill)

## Dispatch Decisions

Review the task complexity and set frontmatter booleans deliberately (see references/task-contract.md):
- Trivial (typo/doc): all false. Simple (single file): executor=false, tester=true, reviewer=false. Normal (multi-file): all true. Complex (API/refactor): all true + rollback.

## Executor Requirements

(fill)

## Tester Requirements

(fill)

## Reviewer Requirements

(fill)

## Done When

(fill)

## Rollback Strategy required: no

(fill — if yes, describe Git-based rollback)

## Report Policy

Default `ask`. Only change to `silent_until_done` if the user explicitly asked for quiet mode.

## Dependencies

(fill)
"""

_TASK_MS_VERIFY_TEMPLATE = """# {id} — {title}

This task verifies {milestone_id} against `.aiwf/milestones/{milestone_id}.md`.
Do NOT implement feature changes here.
Run integration and architecture review sub-steps through `/aiwf-milestone`.

## Objective

Verify milestone {milestone_id}.

## Milestone Reference

- Milestone: {milestone_id}
- Milestone.md: `.aiwf/milestones/{milestone_id}.md`
- This task is: kind=milestone_verification

## Pass Standard Source

The authoritative Pass Standard is in `.aiwf/milestones/{milestone_id}.md`.

## Integration Test Requirements

(fill — what must the integration tester verify?)

## Architect Review Requirements

(fill — is architecture review required? what must be checked?)

## Milestone Review Requirements

(fill — what must the final milestone reviewer verify?)

## Residual Risk Handling

(fill — which risks are acceptable? which block?)

## Human Acceptance Check

(fill — is explicit human acceptance required?)

## Done When

- [ ] Integration test passed and testing record exists (aiwf record testing)
- [ ] Architecture review intact (if required)
- [ ] Milestone review passed and review record exists (aiwf record review)
- [ ] Records in records/review.json, records/architecture-review.json
- [ ] Assessment recorded: aiwf milestone assess {milestone_id} --verdict PASS
"""

_MILESTONE_TEMPLATE = """# {id} — {title}

## Purpose

What stage result is being proven by this milestone?

(fill)

## Covered Plans / Tasks

- (fill)

## Pass Standard

What exactly counts as passing? Which flows must work? Which old mechanisms must not return?

(fill)

## Milestone Verification Task Requirement

A milestone verification Task (kind=milestone_verification) is REQUIRED before close.
This Task coordinates: integration tester, architect reviewer, milestone reviewer.

(fill with verification task ID once created)

## Integration Test Requirements

What cross-Goal integration points must be verified?

(fill)

## Architect Review Requirements

Is a structure-level architecture review required for this milestone? (yes/no)

(fill)

## Documentation Requirements

What docs must be updated before milestone close?

(fill)

## Residual Risk Policy

Which risks are acceptable? Which risks block the milestone?

(fill)

## Human Acceptance Requirement

Is explicit human acceptance required? (yes/no)

(fill)

## Final Verdict

To be filled by milestone reviewer after verification Task completes.

(fill)
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
        fm["executor_required"] = True
        fm["tester_required"] = True
        fm["reviewer_required"] = True
        fm["rollback_required"] = False
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
        body = f"# {entity_id} — {title}\n\n(fill)\n"

    full_path = root / doc_path_str
    write_narrative_doc(full_path, fm, body)
    return doc_path_str
