#!/usr/bin/env python3
"""AIWF TUI — terminal UI for browsing governance structure.

Reads .aiwf/state/*.json and .aiwf/records/*.json directly.
Edits MD files via $EDITOR, then runs aiwf sync.
No new dependencies (curses stdlib), no new CLI commands.

Usage:
    aiwf ui                # or: python -m aiwf_core.aiwf_ui
"""

import curses
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── data layer ────────────────────────────────────────────────────────

def rj(path):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        return {}


def load_all(root: Path) -> dict:
    state = rj(root / ".aiwf" / "state" / "state.json")
    goals = rj(root / ".aiwf" / "state" / "goals.json")
    plans = rj(root / ".aiwf" / "state" / "plans.json")
    tasks = rj(root / ".aiwf" / "state" / "tasks.json")
    milestones = rj(root / ".aiwf" / "state" / "milestones.json")
    evidence = rj(root / ".aiwf" / "records" / "evidence.json")
    testing = rj(root / ".aiwf" / "records" / "testing.json")
    review = rj(root / ".aiwf" / "records" / "review.json")
    return {
        "state": state, "goals": goals, "plans": plans, "tasks": tasks,
        "milestones": milestones, "evidence": evidence, "testing": testing,
        "review": review,
    }


# ── tree builder ───────────────────────────────────────────────────────

def build_tree(data: dict) -> list:
    """Build a flat list of tree nodes with correct nesting indent levels."""
    nodes = []
    state = data["state"]
    active_task_id = state.get("active_task_id", "")
    active_milestone_id = state.get("active_milestone_id", "")

    # Mission (root)
    mission_title = data.get("mission_title", "Mission")
    nodes.append({"kind": "mission", "id": "mission", "title": mission_title,
                  "indent": 0, "status": "", "active": False})

    goal_list = data["goals"].get("goals", []) or []
    goal_by_id = {g.get("id", ""): g for g in goal_list}
    plan_list = data["plans"].get("plans", []) or []
    plan_by_goal = {}
    for p in plan_list:
        pid = p.get("plan_id") or p.get("id") or ""
        gid = p.get("goal_id") or ""
        plan_by_goal.setdefault(gid, []).append((pid, p))
    task_list = data["tasks"].get("tasks", []) or []
    task_by_id = {t.get("id", ""): t for t in task_list}

    # Compute goal nesting depth via parent_goal_id chain
    def _goal_depth(gid, seen=None):
        if seen is None:
            seen = set()
        if gid in seen:
            return 1  # cycle guard
        seen.add(gid)
        g = goal_by_id.get(gid, {})
        pid = g.get("parent_goal_id", "")
        if pid and pid in goal_by_id:
            return _goal_depth(pid, seen) + 1
        return 1  # root-level goal

    # Sort goals: roots first, then children by depth, then alphabetically
    def _goal_order_key(g):
        depth = _goal_depth(g.get("id", ""))
        pid = g.get("parent_goal_id", "")
        return (depth, pid or "", g.get("id", ""))

    sorted_goals = sorted(goal_list, key=_goal_order_key)

    # Track which goals have already been added as children of others
    added_goals = set()

    def _add_goal(gid, base_indent):
        """Recursively add a goal, its plans/tasks, and child goals."""
        nonlocal nodes
        if gid in added_goals:
            return
        added_goals.add(gid)
        g = goal_by_id.get(gid, {})
        title = g.get("title_cache") or g.get("title") or gid
        gstatus = g.get("status", "open")
        nodes.append({"kind": "goal", "id": gid, "title": title,
                      "indent": base_indent, "status": gstatus, "active": False})

        # Plans under this goal
        for pid, p in plan_by_goal.get(gid, []):
            pstatus = p.get("status", "open")
            nodes.append({"kind": "plan", "id": pid,
                          "title": p.get("title_cache", p.get("title", pid)),
                          "indent": base_indent + 1, "status": pstatus, "active": False})
            for tid in p.get("task_ids", []) or []:
                t = task_by_id.get(tid, {})
                tstatus = t.get("status", "ready")
                nodes.append({"kind": "task", "id": tid,
                              "title": t.get("title_cache", t.get("title", tid)),
                              "indent": base_indent + 2, "status": tstatus,
                              "active": tid == active_task_id})

        # Child goals
        children = [g for g in goal_list if g.get("parent_goal_id") == gid]
        for c in sorted(children, key=lambda g: g.get("id", "")):
            _add_goal(c.get("id", ""), base_indent + 1)

    # Add root goals (no parent), then their children cascade
    roots = [g for g in sorted_goals if not g.get("parent_goal_id")]
    for g in roots:
        _add_goal(g.get("id", ""), 1)

    # Any goals not reached (e.g., parent not found) — add at depth 1
    for g in sorted_goals:
        _add_goal(g.get("id", ""), 1)

    # Orphan tasks: linked to plan but plan's goal missing from tree
    for t in task_list:
        tid = t.get("id", "")
        if not any(n["id"] == tid for n in nodes):
            tstatus = t.get("status", "ready")
            nodes.append({"kind": "task", "id": tid,
                          "title": t.get("title_cache", t.get("title", tid)),
                          "indent": 2, "status": tstatus,
                          "active": tid == active_task_id})

    # Milestones (appended after tree)
    ms_list = data["milestones"].get("milestones", []) or []
    for m in ms_list:
        mid = m.get("id") or m.get("milestone_id") or "?"
        mstatus = m.get("status", "pending")
        nodes.append({"kind": "milestone", "id": mid,
                      "title": m.get("title_cache", m.get("title", mid)),
                      "indent": 1, "status": mstatus,
                      "active": mid == active_milestone_id})

    return nodes


def _precompute_tree_prefixes(nodes):
    """Precompute tree-drawing prefixes for all nodes.

    For each node, check its ancestors: if an ancestor at depth d has any
    later child (indirectly) after the current node, draw a pipe at depth d.
    """
    n = len(nodes)
    for i in range(n):
        depth = nodes[i]["indent"]
        parts = []

        for d in range(1, depth):
            # Is there any node at depth >= d after position i?
            has_later = False
            for j in range(i + 1, n):
                nj = nodes[j]
                if nj["indent"] < d:
                    break  # moved to a different branch entirely
                if nj["indent"] >= d:
                    has_later = True
                    break
            parts.append("│ " if has_later else "  ")

        if depth > 0:
            # Last child at this depth (same parent)?
            is_last = True
            for j in range(i + 1, n):
                nj = nodes[j]
                if nj["indent"] < depth:
                    break
                if nj["indent"] == depth:
                    is_last = False
                    break
            parts.append("└─" if is_last else "├─")

        nodes[i]["_prefix"] = "".join(parts)


# ── rendering ──────────────────────────────────────────────────────────

# Layer colors (curses pair numbers)
_COL_MISSION = 2
_COL_GOAL = 3
_COL_PLAN = 4
_COL_TASK = 5
_COL_MILESTONE = 6
_COL_GRAY = 1
_COL_ACTIVE = 7
_COL_DIVIDER = 8

def _init_colors():
    if not curses.has_colors():
        return
    try:
        curses.use_default_colors()
    except Exception:
        pass

    has_256 = curses.COLORS >= 256

    def _pair(n, fg, bg):
        curses.init_pair(n, fg, bg)

    if has_256:
        _pair(_COL_GRAY, 245, -1)
        _pair(_COL_MISSION, 6, -1)
        _pair(_COL_GOAL, 4, -1)
        _pair(_COL_PLAN, 2, -1)
        _pair(_COL_TASK, 3, -1)
        _pair(_COL_MILESTONE, 5, -1)
        _pair(_COL_ACTIVE, 15, -1)
        _pair(_COL_DIVIDER, 245, -1)
    else:
        # 8-color fallback — uses standard ANSI colors
        _pair(_COL_GRAY, 7, -1)        # white as gray substitute
        _pair(_COL_MISSION, 6, -1)     # cyan
        _pair(_COL_GOAL, 4, -1)        # blue
        _pair(_COL_PLAN, 2, -1)        # green
        _pair(_COL_TASK, 3, -1)        # yellow
        _pair(_COL_MILESTONE, 5, -1)   # magenta
        _pair(_COL_ACTIVE, 7, -1)      # white
        _pair(_COL_DIVIDER, 7, -1)     # white as divider


def _kind_color(kind):
    return {"mission": _COL_MISSION, "goal": _COL_GOAL, "plan": _COL_PLAN,
            "task": _COL_TASK, "milestone": _COL_MILESTONE}.get(kind, 0)


def status_icon(status):
    return {"closed": "✓", "cancelled": "✗", "active": "◉",
            "ready": "○", "open": "○", "pending": "○"}.get(status, "○")


def render_tree(stdscr, nodes, selected_idx, scroll_offset, max_rows, view_mode, milestone_view=False, detail_scroll=0):
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    tree_w = min(w * 2 // 3, 55)
    detail_x = tree_w + 1
    has_color = curses.has_colors()

    # ── Left panel: tree with box-drawing (prefixes precomputed) ──
    for i, node in enumerate(nodes):
        y = i - scroll_offset
        if y < 0 or y >= max_rows - 2:
            continue
        depth = node["indent"]
        icon = status_icon(node["status"])
        title = node["title"][:tree_w - (depth * 3) - 6]
        prefix = node.get("_prefix", "")

        line = f"{prefix} {icon} {title}"

        # Color by layer
        attr = curses.A_REVERSE if i == selected_idx else 0
        col = _kind_color(node["kind"])
        if node["active"]:
            attr |= curses.color_pair(_COL_ACTIVE) if has_color else curses.A_BOLD
        elif node["status"] in ("closed", "cancelled"):
            attr |= curses.color_pair(_COL_GRAY) if has_color else 0
        else:
            attr |= curses.color_pair(col) if has_color else 0

        try:
            stdscr.addstr(y, 0, line[:tree_w].ljust(tree_w), attr)
        except curses.error:
            pass

    # Vertical divider ─ persistent, not tree-connected
    for y in range(max_rows - 2):
        try:
            stdscr.addstr(y, tree_w, "│", curses.color_pair(_COL_DIVIDER) if has_color else 0)
        except curses.error:
            pass

    # ── Right panel: depends on view mode ──
    if 0 <= selected_idx < len(nodes):
        node = nodes[selected_idx]
        if milestone_view:
            _render_milestone_detail(stdscr, detail_x, w, max_rows, node, data, detail_scroll)
        elif view_mode == 1:
            _render_tree_detail(stdscr, detail_x, w, max_rows, node, data, detail_scroll)
        elif view_mode == 2:
            _render_deps_view(stdscr, detail_x, w, max_rows, node, data, detail_scroll)
        elif view_mode == 3:
            _render_relations_view(stdscr, detail_x, w, max_rows, data, detail_scroll)

    # ── Bottom bar ──
    bar_y = max_rows - 2
    bar_text = _build_status_bar(data)
    try:
        stdscr.addstr(bar_y, 0, bar_text[:w - 1].ljust(w - 1), curses.A_REVERSE)
    except curses.error:
        pass

    # ── Help line ──
    view_hint = {1: "detail", 2: "deps", 3: "relations"}.get(view_mode, "")
    help_text = f"j/k:tree  1:detail  2:deps  3:ms  Enter/e:edit  r:records  s:sync  shift+J/K:scroll right  Tab:ms  q:quit  [{view_hint}]"
    try:
        stdscr.addstr(max_rows - 1, 0, help_text[:w - 1], curses.A_DIM)
    except curses.error:
        pass

    stdscr.refresh()


def _render_tree_detail(stdscr, x, w, max_rows, node, data, detail_scroll=0):
    """View 1: selected node detail — key fields."""
    lines = _node_summary(node, data)
    for i, line in enumerate(lines):
        di = i - detail_scroll
        if di < 0 or di >= max_rows - 2:
            continue
        try:
            stdscr.addstr(i, x, line[:w - x - 1])
        except curses.error:
            pass


def _render_deps_view(stdscr, x, w, max_rows, node, data, detail_scroll=0):
    """View 2: dependency order — tasks by wave, plans by chain."""
    lines = ["── Dependencies ──", ""]
    task_list = data["tasks"].get("tasks", []) or []
    plan_list = data["plans"].get("plans", []) or []
    nid = node["id"]
    has_any = False

    # Task dependencies — always show, not just when node is task
    waves = {}
    for t in task_list:
        wv = _task_wave(data, t.get("id"))
        if wv is not None:
            waves.setdefault(wv, []).append(t)
    if waves:
        has_any = True
        lines.append("Task order:")
        for wv in sorted(waves.keys()):
            labels = {0: "Wave 0 (no deps)", 1: "Wave 1", 2: "Wave 2", 3: "Wave 3"}
            lines.append(f"  {labels.get(wv, f'第{wv}波')}")
            for t in waves[wv]:
                icon = status_icon(t.get("status", ""))
                title = t.get("title_cache", t.get("title", t.get("id", "?")))
                mark = " ◀" if t.get("id") == nid else ""
                deps = t.get("dependencies", []) or []
                dep_str = f" deps→[{', '.join(deps)}]" if deps else ""
                lines.append(f"    {icon} {t['id']}{mark}{dep_str}")
            lines.append("")
    else:
        lines.append("  (暂无任务依赖关系)")

    # Plan dependency chain — tree form with box drawing + titles
    plan_dep_map = {}
    plan_by_id = {}
    for p in plan_list:
        pid = p.get("plan_id") or p.get("id") or ""
        if pid:
            plan_by_id[pid] = p
            for d in (p.get("dependencies", []) or []):
                plan_dep_map.setdefault(d, []).append(pid)  # d depends on → [kids]

    if plan_dep_map:
        has_any = True
        # Roots: plans that are not depended-on by anyone
        all_kids = {k for kids in plan_dep_map.values() for k in kids}
        roots = sorted([pid for pid in plan_by_id if pid not in all_kids and pid in plan_dep_map or plan_by_id[pid].get("dependencies")])

        def _deps_tree(pid, prefix, is_last, visited):
            if pid in visited:
                return [f"{prefix}{pid} (cycle)"]
            visited.add(pid)
            p = plan_by_id.get(pid, {})
            title = (p.get("title_cache") or p.get("title") or pid)[:35]
            branch = "└─ " if is_last else "├─ "
            result = [f"{prefix}{branch}{pid}  {title}"]
            kids = plan_dep_map.get(pid, [])
            for i, k in enumerate(kids):
                last_kid = (i == len(kids) - 1)
                new_prefix = prefix + ("   " if is_last else "│  ")
                result.extend(_deps_tree(k, new_prefix, last_kid, visited.copy()))
            return result

        lines.append("")
        lines.append("Plan dependency tree:")
        for i, root in enumerate(roots):
            result_lines = _deps_tree(root, "", i == len(roots) - 1, set())
            lines.extend(result_lines)

    # Cross-reference: which tasks link to which plans
    task_plan = {}
    for t in task_list:
        pid = t.get("plan_id") or ""
        if pid:
            task_plan.setdefault(pid, []).append(t.get("id"))
    if task_plan and len(task_plan) > 1:
        lines.append("")
        lines.append("Task→Plan 归属:")
        for pid, tids in sorted(task_plan.items()):
            lines.append(f"  {pid}: {', '.join(tids)}")

    if not has_any and not (task_plan and len(task_plan) > 1):
        lines.append("  No dependencies.在 Plan.md frontmatter 中设置 dependencies 字段。")

    for i, line in enumerate(lines):
        di = i - detail_scroll
        if di < 0 or di >= max_rows - 2:
            continue
        try:
            stdscr.addstr(di, x, line[:w - x - 1])
        except curses.error:
            pass


def _render_milestone_detail(stdscr, x, w, max_rows, node, data, detail_scroll=0):
    """Milestone-only view: show focused milestone detail with all linked items."""
    ms_list = data["milestones"].get("milestones", []) or []
    nid = node["id"]
    ms = next((m for m in ms_list if (m.get("id") or m.get("milestone_id")) == nid), {})
    if not ms:
        return

    stlabel = {"open": "开放", "closed": "已关闭", "pending": "待定"}
    lines = [f"里程碑 {nid}", f"标题: {ms.get('title','')}", f"状态: {stlabel.get(ms.get('status',''), ms.get('status','?'))}", ""]

    plan_ids = ms.get("plan_ids", []) or []
    task_ids = ms.get("task_ids", []) or []
    task_list = data["tasks"].get("tasks", []) or []
    plan_list = data["plans"].get("plans", []) or []

    if plan_ids:
        lines.append(f"关联 Plan ({len(plan_ids)}):")
        for pid in plan_ids:
            p = _find_plan(data, pid)
            ptitle = p.get("title_cache", p.get("title", ""))[:30] if p else ""
            pst = p.get("status", "?") if p else "?"
            lines.append(f"  {status_icon(pst)} {pid}  {ptitle}")
        lines.append("")

    if task_ids:
        lines.append(f"关联 Task ({len(task_ids)}):")
        for tid in task_ids:
            t = _find_task(data, tid)
            ttitle = t.get("title_cache", t.get("title", ""))[:30] if t else ""
            tst = t.get("status", "?") if t else "?"
            lines.append(f"  {status_icon(tst)} {tid}  {ttitle}")
        lines.append("")

    it = ms.get("integration_test", {}) or {}
    ar = ms.get("architecture_review", {}) or {}
    it_st = it.get("status", "-")
    ar_st = ar.get("status", "-")
    it_label = {"passed": "✓ 通过", "failed": "✗ 失败"}.get(it_st, "未运行")
    ar_label = {"intact": "✓ 完整", "issues_found": "✗ 有问题"}.get(ar_st, "未运行")
    lines.append(f"门禁状态:")
    lines.append(f"  集成测试: {it_label}")
    lines.append(f"  架构审查: {ar_label}")

    for i, line in enumerate(lines):
        di = i - detail_scroll
        if di < 0 or di >= max_rows - 2:
            continue
        try:
            stdscr.addstr(di, x, line[:w - x - 1])
        except curses.error:
            pass


def _render_relations_view(stdscr, x, w, max_rows, data, detail_scroll=0):
    """View 3: cross-cutting — goal capability deps + milestones."""
    lines = []
    goal_list = data["goals"].get("goals", []) or []

    # ── Goal capability dependencies (stored at tree level in goals.json) ──
    goal_rels = []
    tree_relations = data["goals"].get("relations", []) or []
    for r in tree_relations:
        if isinstance(r, dict) and r.get("type") and r.get("source_id") and r.get("target_id"):
            goal_rels.append((r["source_id"], r["type"], r["target_id"]))
    if goal_rels:
        lines.append("── Goal capability deps ──")
        lines.append("(logical: capability needs another to exist)")
        lines.append("")
        sym = {"depends_on": "needs ->", "blocks": "blocks ->", "supports": "supports ->", "invalidates": "replaces ->"}
        for src, typ, tgt in goal_rels:
            lines.append(f"  {src}  {sym.get(typ, typ + ' ->')}  {tgt}")
        lines.append("")

    # ── Milestones ──
    lines.append("── Milestones ──")
    lines.append("")
    ms_list = data["milestones"].get("milestones", []) or []
    if not ms_list:
        lines.append("  暂无里程碑。")
    for ms in ms_list:
        mid = ms.get("id") or ms.get("milestone_id") or "?"
        mstatus = ms.get("status", "?")
        icon = status_icon(mstatus)
        st_label = {"open": "开放", "closed": "已关闭", "pending": "待定"}.get(mstatus, mstatus)
        lines.append(f"{icon} {mid} [{st_label}]")
        lines.append(f"   标题: {ms.get('title','')[:40]}")
        plan_ids = ms.get("plan_ids", []) or []
        if plan_ids:
            lines.append(f"   关联 Plan: {', '.join(plan_ids)}")
        task_ids = ms.get("task_ids", []) or []
        if task_ids:
            lines.append(f"   关联 Task: {', '.join(task_ids)}")
        it = ms.get("integration_test", {}) or {}
        ar = ms.get("architecture_review", {}) or {}
        it_st = it.get("status", "-")
        ar_st = ar.get("status", "-")
        it_label = {"passed": "✓ 通过", "failed": "✗ 失败"}.get(it_st, it_st)
        ar_label = {"intact": "✓ 完整", "issues_found": "✗ 有问题"}.get(ar_st, ar_st)
        lines.append(f"   门禁: 集成测试={it_label}  架构审查={ar_label}")
        lines.append("")
    for i, line in enumerate(lines):
        di = i - detail_scroll
        if di < 0 or di >= max_rows - 2:
            continue
        try:
            stdscr.addstr(di, x, line[:w - x - 1])
        except curses.error:
            pass


def _node_summary(node, data):
    """节点详情 — view 1."""
    kind = node["kind"]
    nid = node["id"]
    klabel = {"mission": "使命", "goal": "目标", "plan": "计划", "task": "任务", "milestone": "里程碑"}
    stlabel = {"open": "开放", "closed": "已关闭", "cancelled": "已取消", "active": "执行中", "ready": "就绪", "pending": "待定"}

    lines = [f"{kind.upper()} {nid}"]
    task_list = data["tasks"].get("tasks", []) or []
    plan_list = data["plans"].get("plans", []) or []
    goal_list = data["goals"].get("goals", []) or []
    ms_list = data["milestones"].get("milestones", []) or []

    if kind == "task":
        task = next((t for t in task_list if t.get("id") == nid), {})
        lines.append(f"标题: {task.get('title','')}")
        lines.append(f"状态: {stlabel.get(task.get('status',''), task.get('status','?'))}")
        deps = task.get("dependencies", []) or []
        if deps:
            satisfied = all(_find_task(data, d).get("status") == "closed" for d in deps)
            lines.append(f"依赖: [{'✓ 已满足' if satisfied else '✗ 未满足'}] {', '.join(deps)}")
        ms_ids = [m.get("id") or m.get("milestone_id") for m in ms_list if nid in (m.get("task_ids", []) or [])]
        if ms_ids:
            lines.append(f"所属里程碑: {', '.join(ms_ids)}")

    elif kind == "plan":
        plan = next((p for p in plan_list if (p.get("plan_id") or p.get("id")) == nid), {})
        lines.append(f"标题: {plan.get('title','')}")
        lines.append(f"状态: {stlabel.get(plan.get('status',''), plan.get('status','?'))}")
        task_ids = plan.get("task_ids", []) or []
        closed = _count_closed(data, task_ids)
        lines.append(f"任务: {closed}/{len(task_ids)} 已完成")
        deps = plan.get("dependencies", []) or []
        if deps:
            dep_list = []
            for d in deps:
                dp = _find_plan(data, d)
                dep_list.append(f"{d}[{stlabel.get(dp.get('status',''), dp.get('status','?'))}]")
            lines.append(f"依赖: {', '.join(dep_list)}")

    elif kind == "goal":
        goal = next((g for g in goal_list if g.get("id") == nid), {})
        lines.append(f"标题: {goal.get('title','')}")
        lines.append(f"状态: {stlabel.get(goal.get('status',''), goal.get('status','?'))}")
        pid = goal.get("parent_goal_id")
        if pid:
            parent = next((g for g in goal_list if g.get("id") == pid), {})
            lines.append(f"父目标: {pid} ({parent.get('title','')[:20]})")
        children = [g.get("id") for g in goal_list if g.get("parent_goal_id") == nid]
        if children:
            lines.append(f"Children: {', '.join(children)}")
        tree_rels = data["goals"].get("relations", []) or []
        for r in tree_rels:
            if isinstance(r, dict) and r.get("source_id") == nid:
                lines.append(f"Relation: {r.get('type','?')} → {r.get('target_id','?')}")

    elif kind == "milestone":
        ms = next((m for m in ms_list if (m.get("id") or m.get("milestone_id")) == nid), {})
        lines.append(f"Title: {ms.get('title','')}")
        lines.append(f"Status: {ms.get('status','?')}")
        it = ms.get("integration_test", {}) or {}
        ar = ms.get("architecture_review", {}) or {}
        lines.append(f"门禁: 集成测试={it.get('status','-')}  架构审查={ar.get('status','-')}")

    return lines


def _task_wave(data, task_id):
    """Compute topological wave number for a task (0 = no deps)."""
    task_list = data["tasks"].get("tasks", []) or []
    task = _find_task(data, task_id)
    if not task:
        return None
    deps = task.get("dependencies", []) or []
    if not deps:
        return 0
    # Simple: max wave of deps + 1, capped to avoid cycles
    max_wave = 0
    seen = {task_id}
    for d in deps:
        if d in seen:
            continue
        w = _task_wave(data, d)
        if w is not None:
            max_wave = max(max_wave, w)
    return max_wave + 1


def _build_detail(node, data):
    lines = [f" {node['kind'].upper()} {node['id']}", f" Title: {node['title']}", ""]
    kind = node["kind"]
    nid = node["id"]

    if kind == "task":
        task_list = data["tasks"].get("tasks", []) or []
        task = next((t for t in task_list if t.get("id") == nid), {})
        reqs = task.get("requirements", {}) or {}
        lines.append(f" Status: {task.get('status', '?')}")
        lines.append(f" Kind: {task.get('kind', '') or '-'}")
        lines.append(f" Plan: {task.get('plan_id', '-')}")
        lines.append(f" Goal: {task.get('goal_id', '-')}")
        lines.append(f" MS:   {task.get('milestone_id', '-')}")
        lines.append(f" Executor: {'required' if reqs.get('executor_required') else 'inline'}")
        lines.append(f" Tester:   {'required' if reqs.get('tester_required') else 'inline'}")
        lines.append(f" Reviewer: {'required' if reqs.get('reviewer_required') else 'inline'}")
        if task.get("dependencies"):
            lines.append(f" Depends on: {', '.join(task['dependencies'])}")
        if task.get("frozen_contract_hash"):
            lines.append(f" Frozen: {task['frozen_contract_hash'][:16]}...")

    elif kind == "plan":
        plan_list = data["plans"].get("plans", []) or []
        plan = next((p for p in plan_list if (p.get("plan_id") or p.get("id")) == nid), {})
        lines.append(f" Status: {plan.get('status', '?')}")
        lines.append(f" Goal: {plan.get('goal_id', '-')}")
        lines.append(f" MS:   {plan.get('milestone_id', '-')}")
        task_ids = plan.get("task_ids", []) or []
        lines.append(f" Tasks: {len(task_ids)} ({_count_closed(data, task_ids)} closed)")
        for tid in task_ids[:10]:
            t = _find_task(data, tid)
            icon = status_icon(t.get("status", "")) if t else "?"
            lines.append(f"   {icon} {tid}")
        deps = plan.get("dependencies", []) or []
        if deps:
            lines.append(f" Depends on: {', '.join(deps)}")

    elif kind == "goal":
        goal_list = data["goals"].get("goals", []) or []
        goal = next((g for g in goal_list if g.get("id") == nid), {})
        lines.append(f" Status: {goal.get('status', '?')}")
        lines.append(f" Parent: {goal.get('parent_goal_id', '-')}")
        plans = _plans_for_goal(data, nid)
        lines.append(f" Plans: {len(plans)}")
        for pid in plans[:10]:
            p = _find_plan(data, pid)
            icon = status_icon(p.get("status", "")) if p else "?"
            lines.append(f"   {icon} {pid}")

    elif kind == "milestone":
        ms_list = data["milestones"].get("milestones", []) or []
        ms = next((m for m in ms_list if (m.get("id") or m.get("milestone_id")) == nid), {})
        lines.append(f" Status: {ms.get('status', '?')}")
        lines.append(f" Goal: {ms.get('goal_id', '-')}")
        lines.append(f" Plans: {', '.join(ms.get('plan_ids', []) or [])}")
        lines.append(f" Tasks: {', '.join(ms.get('task_ids', []) or [])}")
        it = ms.get("integration_test", {}) or {}
        ar = ms.get("architecture_review", {}) or {}
        lines.append(f" Integration: {it.get('status', 'not run')}")
        lines.append(f" Arch review: {ar.get('status', 'not run')}")

    return lines


def _find_task(data, tid):
    task_list = data["tasks"].get("tasks", []) or []
    for t in task_list:
        if t.get("id") == tid:
            return t
    return {}

def _find_plan(data, pid):
    plan_list = data["plans"].get("plans", []) or []
    for p in plan_list:
        if (p.get("plan_id") or p.get("id")) == pid:
            return p
    return {}

def _plans_for_goal(data, gid):
    plan_list = data["plans"].get("plans", []) or []
    return [p.get("plan_id") or p.get("id") for p in plan_list if p.get("goal_id") == gid]

def _count_closed(data, task_ids):
    closed = 0
    for tid in task_ids:
        t = _find_task(data, tid)
        if t and t.get("status") == "closed":
            closed += 1
    return closed


def _build_status_bar(data):
    state = data["state"]
    phase = state.get("phase", "?")
    active = state.get("active_task_id", "") or "-"
    blocked = "阻塞" if state.get("blocked") else "正常"
    return f" AIWF | 阶段={phase} | 活跃任务={active} | 状态={blocked}"


# ── interactivity ─────────────────────────────────────────────────────

def main(stdscr):
    global data
    curses.curs_set(0)
    _init_colors()
    has_color = curses.has_colors()

    root = Path.cwd()
    selected = 0
    scroll = 0
    view_mode = 1           # 1=detail, 2=deps, 3=relations
    deps_sub = 0            # 0=tasks, 1=plans, 2=goals (cycle within deps view)
    detail_scroll = 0       # independent scroll for right panel
    milestone_view = False  # Tab toggles between tree and milestone-only view

    nodes_cache = []
    nodes_cache_key = ""
    last_data_mtime = 0

    while True:
        # Only reload data when files changed (check state.json mtime)
        state_mtime = (root / ".aiwf" / "state" / "state.json").stat().st_mtime
        if state_mtime != last_data_mtime:
            last_data_mtime = state_mtime
            data = load_all(root)
            data["mission_title"] = _read_mission_title(root)
            all_nodes = build_tree(data)
            _precompute_tree_prefixes(all_nodes)
            milestone_nodes = [n for n in all_nodes if n["kind"] == "milestone"]
            nodes_cache_key = ""

        # Filter
        if milestone_view:
            nodes = milestone_nodes
        else:
            nodes = all_nodes

        h, w = stdscr.getmaxyx()
        max_rows = h

        # Clamp selection
        if selected >= len(nodes):
            selected = max(0, len(nodes) - 1)
        if selected < scroll:
            scroll = selected
        elif selected >= scroll + max_rows - 3:
            scroll = selected - max_rows + 4

        render_tree(stdscr, nodes, selected, scroll, max_rows, view_mode, milestone_view, detail_scroll)

        key = stdscr.getch()

        if key == ord("q"):
            break
        elif key == ord("1"):
            view_mode = 1; detail_scroll = 0
        elif key == ord("2"):
            if view_mode == 2:
                deps_sub = (deps_sub + 1) % 3  # cycle tasks→plans→goals
            view_mode = 2; detail_scroll = 0
        elif key == ord("3"):
            view_mode = 3; detail_scroll = 0
            view_mode = 3
        elif key == ord("J"):  # Shift+J → scroll right panel down
            detail_scroll += 1
        elif key == ord("K"):  # Shift+K → scroll right panel up
            detail_scroll = max(0, detail_scroll - 1)
        elif key == ord("j") or key == curses.KEY_DOWN:
            selected = min(selected + 1, len(nodes) - 1)
            detail_scroll = 0  # reset right scroll on tree move
        elif key == ord("k") or key == curses.KEY_UP:
            selected = max(selected - 1, 0)
        elif key == ord("g"):
            selected = 0
        elif key == ord("G"):
            selected = len(nodes) - 1
        elif key == 9:  # Tab
            milestone_view = not milestone_view
            selected = 0; scroll = 0; detail_scroll = 0
        elif key in (ord("\n"), ord("e")):
            # Edit MD in $EDITOR, auto-sync on return
            if 0 <= selected < len(nodes):
                node = nodes[selected]
                md_path = _md_path_for(node)
                if md_path and (root / md_path).exists():
                    _edit_and_sync(root, md_path)
                    # Auto-refresh: reload data after sync
        elif key == ord("s"):
            _run_sync_inline(root)
        elif key == ord("r"):
            if 0 <= selected < len(nodes):
                node = nodes[selected]
                if node["kind"] == "task":
                    _show_records_inline(stdscr, data, node["id"])
        elif key == ord("R"):
            # Force full refresh (reread all JSON)
            pass  # data reload happens at top of loop


def _read_mission_title(root):
    ms = root / ".aiwf" / "mission.md"
    if ms.exists():
        first = ms.read_text().split("\n")[0]
        if first.startswith("# "):
            return first[2:].strip()
    return "Mission"


def _md_path_for(node):
    kind = node["kind"]
    nid = node["id"]
    if kind == "goal":
        return f".aiwf/goals/{nid}.md"
    elif kind == "plan":
        return f".aiwf/plans/{nid}.md"
    elif kind == "task":
        return f".aiwf/tasks/{nid}.md"
    elif kind == "milestone":
        return f".aiwf/milestones/{nid}.md"
    return None


def _edit_and_sync(root, md_path):
    """Open MD in $EDITOR, auto-sync on exit, return to TUI."""
    editor = os.environ.get("EDITOR", "nano")
    full = root / md_path
    curses.endwin()
    try:
        subprocess.run([editor, str(full)])
    except Exception:
        pass
    try:
        _run_sync_inline(root)
    except Exception:
        pass
    curses.doupdate()
    curses.doupdate()


def _run_sync_inline(root):
    try:
        r = subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", "sync"],
            capture_output=True, text=True, timeout=15, cwd=str(root))
        if r.returncode != 0:
            sys.stdout.write(f"sync error: {r.stderr.strip()[:200]}\n")
    except Exception as e:
        sys.stdout.write(f"sync failed: {e}\n")


def _show_records_inline(stdscr, data, task_id):
    """Show records overlay in the TUI right panel area."""
    h, w = stdscr.getmaxyx()
    evidence = data["evidence"]
    testing = data["testing"]
    review = data["review"]

    lines = [f"── {task_id} 记录 ──", ""]
    recs = evidence.get("records", []) or []
    rlabel = {"executor": "执行", "tester": "测试", "reviewer": "审查", "planner": "规划"}
    lines.append(f"证据 ({len(recs)} 条):")
    for r in recs[:h - 8]:
        role = rlabel.get(r.get('role',''), r.get('role','?'))
        lines.append(f"  {r.get('id','?')} [{role}] {r.get('summary','')[:80]}")
    lines.append("")
    tlabel = {"passed": "✓ 通过", "failed": "✗ 失败", "adequate": "△ 基本", "missing": "缺失"}
    lines.append(f"测试: {tlabel.get(testing.get('status',''), testing.get('status','?'))}")
    if testing.get("summary"):
        lines.append(f"  {testing['summary'][:120]}")
    lines.append("")
    rvlabel = {"accepted": "✓ 已接受", "needs_fix": "✗ 需修复", "rejected": "✗ 已拒绝"}
    lines.append(f"审查: {rvlabel.get(review.get('result',''), review.get('result','?'))}  允许闭合={review.get('closure_allowed')}")
    if review.get("blockers"):
        for b in review["blockers"]:
            lines.append(f"  阻塞: {b}")

    for i, line in enumerate(lines[:h - 2]):
        try:
            stdscr.addstr(i, 1, line[:w - 2])
        except curses.error:
            pass
    try:
        stdscr.addstr(h - 1, 1, "Press any key", curses.A_REVERSE)
    except curses.error:
        pass
    stdscr.refresh()
    stdscr.getch()


# ── entry ──────────────────────────────────────────────────────────────

def run_ui():
    root = Path.cwd()
    if not (root / ".aiwf" / "state" / "state.json").exists():
        print("No AIWF installation found. Run: aiwf install claude")
        sys.exit(1)
    curses.wrapper(main)


if __name__ == "__main__":
    run_ui()
