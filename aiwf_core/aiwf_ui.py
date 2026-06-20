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


_SHOW_CANCELLED = False

def set_show_cancelled(v):
    global _SHOW_CANCELLED
    _SHOW_CANCELLED = v

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
        gstatus = g.get("status", "open")
        if not _SHOW_CANCELLED and gstatus in ("cancelled", "closed"):
            return  # skip cancelled/closed goals entirely
        title = g.get("title_cache") or g.get("title") or gid
        nodes.append({"kind": "goal", "id": gid, "title": title,
                      "indent": base_indent, "status": gstatus, "active": False})

        # Plans under this goal
        for pid, p in plan_by_goal.get(gid, []):
            pstatus = p.get("status", "open")
            if not _SHOW_CANCELLED and pstatus in ("cancelled", "closed"):
                continue
            ptitle = (p.get("title_cache") or p.get("title") or pid)[:40]
            nodes.append({"kind": "plan", "id": pid,
                          "title": f"{pid}  {ptitle}",
                          "indent": base_indent + 1, "status": pstatus, "active": False})
            for tid in p.get("task_ids", []) or []:
                t = task_by_id.get(tid, {})
                tstatus = t.get("status", "ready")
                if not _SHOW_CANCELLED and tstatus in ("cancelled",):
                    continue
                ttitle = (t.get("title_cache") or t.get("title") or tid)[:40]
                nodes.append({"kind": "task", "id": tid,
                              "title": f"{tid}  {ttitle}",
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
    # Also filter by parent plan/goal cancelled status
    cancelled_plans = set()
    cancelled_goals = set()
    if not _SHOW_CANCELLED:
        for p in plan_list:
            if p.get("status") in ("cancelled", "closed"):
                cancelled_plans.add(p.get("plan_id") or p.get("id") or "")
        for g in goal_list:
            if g.get("status") in ("cancelled", "closed"):
                cancelled_goals.add(g.get("id", ""))
    for t in task_list:
        tid = t.get("id", "")
        if not any(n["id"] == tid for n in nodes):
            tstatus = t.get("status", "ready")
            if not _SHOW_CANCELLED:
                if tstatus in ("cancelled",):
                    continue
                pid = t.get("plan_id") or ""
                gid = t.get("goal_id") or ""
                if pid in cancelled_plans or gid in cancelled_goals:
                    continue
            ttitle = (t.get("title_cache") or t.get("title") or tid)[:40]
            nodes.append({"kind": "task", "id": tid,
                          "title": f"{tid}  {ttitle}",
                          "indent": 2, "status": tstatus,
                          "active": tid == active_task_id})

    # Milestones (appended after tree, skip cancelled/closed)
    ms_list = data["milestones"].get("milestones", []) or []
    for m in ms_list:
        mid = m.get("id") or m.get("milestone_id") or "?"
        mstatus = m.get("status", "pending")
        if not _SHOW_CANCELLED and mstatus in ("cancelled", "closed"):
            continue
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
_COL_DIVIDER = 1

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
        _pair(_COL_MISSION, 6, -1)
        _pair(_COL_GOAL, 4, -1)
        _pair(_COL_PLAN, 2, -1)
        _pair(_COL_TASK, 3, -1)
        _pair(_COL_MILESTONE, 5, -1)
        _pair(_COL_DIVIDER, 245, -1)
    else:
        _pair(_COL_MISSION, 6, -1)
        _pair(_COL_GOAL, 4, -1)
        _pair(_COL_PLAN, 2, -1)
        _pair(_COL_TASK, 3, -1)
        _pair(_COL_MILESTONE, 5, -1)
        _pair(_COL_DIVIDER, 7, -1)


def _kind_color(kind):
    return {"mission": _COL_MISSION, "goal": _COL_GOAL, "plan": _COL_PLAN,
            "task": _COL_TASK, "milestone": _COL_MILESTONE}.get(kind, 0)


def status_icon(status):
    return {"closed": "✓", "cancelled": "✗", "active": "◉",
            "ready": "○", "open": "○", "pending": "○"}.get(status, "○")


def render_tree(stdscr, nodes, selected_idx, scroll_offset, max_rows, detail_scroll=0, tree_mode=0, detail_visible=True, show_cancelled=False):
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    if detail_visible:
        tree_w = min(w * 2 // 3, 55)
    else:
        tree_w = w - 2
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

        # Color by node type, with status modifiers
        col = _kind_color(node["kind"])
        attr = curses.A_REVERSE if i == selected_idx else 0
        attr |= curses.color_pair(col) if has_color else 0
        if node["active"]:
            attr |= curses.A_BOLD
        if node["status"] in ("closed", "cancelled"):
            attr |= curses.A_DIM

        try:
            stdscr.addstr(y, 0, line[:tree_w].ljust(tree_w), attr)
        except curses.error:
            pass

    # Vertical divider + detail (only when visible)
    if detail_visible:
        for y in range(max_rows - 2):
            try:
                stdscr.addstr(y, tree_w, "│", curses.color_pair(_COL_DIVIDER) if has_color else 0)
            except curses.error:
                pass
        if 0 <= selected_idx < len(nodes):
            node = nodes[selected_idx]
            _render_node_detail(stdscr, detail_x, w, max_rows, node, data, detail_scroll)

    # ── Bottom bar ──
    bar_y = max_rows - 2
    bar_text = _build_status_bar(data)
    try:
        stdscr.addstr(bar_y, 0, bar_text[:w - 1].ljust(w - 1), curses.A_REVERSE)
    except curses.error:
        pass

    # ── Help line ──
    mode_labels = {0:"Main",1:"Milestones",2:"Tasks",3:"PlanChain",4:"GoalDeps"}
    canc_hint = "[+cancelled]" if show_cancelled else ""
    detail_hint = "[detail]" if detail_visible else "[full]"
    help_text = f"Tab:{mode_labels.get(tree_mode,'?')}{canc_hint}  j/k:nav  e:edit  r:rec  s:sync  d:toggle  x:cancelled  q:quit  {detail_hint}"
    try:
        stdscr.addstr(max_rows - 1, 0, help_text[:w - 1], curses.A_DIM)
    except curses.error:
        pass

    stdscr.refresh()


def _render_node_detail(stdscr, x, w, max_rows, node, data, detail_scroll=0):
    """Right panel: show MD body of selected node."""
    md_path = _md_path_for(node)
    lines = []
    if md_path:
        from pathlib import Path as _P
        doc = _P.cwd() / md_path
        if doc.exists():
            text = doc.read_text(encoding="utf-8")
            # Show frontmatter keys as a header, then body
            if text.startswith("---\n"):
                end = text.find("\n---\n", 4)
                if end != -1:
                    fm_text = text[4:end]
                    body = text[end + 5:].strip()
                    # One-line summary from frontmatter
                    fm_lines = fm_text.strip().split("\n")
                    for fl in fm_lines[:3]:
                        lines.append(fl.strip())
                    lines.append("")
                    # MD body (scrollable)
                    for bl in body.split("\n"):
                        lines.append(bl)
            if not lines:
                lines = text.split("\n")
    if not lines:
        lines = _node_summary(node, data)
    for i, line in enumerate(lines):
        di = i - detail_scroll
        if di < 0 or di >= max_rows - 2:
            continue
        try:
            stdscr.addstr(di, x, line[:w - x - 1])
        except curses.error:
            pass


def _render_deps_view(stdscr, x, w, max_rows, node, data, detail_scroll=0, deps_sub=0):
    """View 2: dependency order — press 2 to cycle Tasks(0)/Plans(1)/Goals(2)."""
    sub_labels = {0: "Plans", 1: "Tasks", 2: "Goals"}
    lines = [f"── Dependencies ({sub_labels.get(deps_sub, '?')})  [press 2 to switch] ──", ""]
    task_list = data["tasks"].get("tasks", []) or []
    plan_list = data["plans"].get("plans", []) or []
    nid = node["id"]

    if deps_sub == 0:
        # ── Plan chain — each plan shown once, at the end of its longest dep path ──
        plan_by_id = {}
        for p in plan_list:
            pid = p.get("plan_id") or p.get("id") or ""
            if pid:
                plan_by_id[pid] = p

        # Compute depth = longest path from any root
        def _plan_depth(pid, depth_cache=None):
            if depth_cache is None:
                depth_cache = {}
            if pid in depth_cache:
                return depth_cache[pid]
            p = plan_by_id.get(pid, {})
            deps = p.get("dependencies", []) or []
            if not deps:
                depth_cache[pid] = 0
                return 0
            d = max(_plan_depth(d, depth_cache) for d in deps) + 1
            depth_cache[pid] = d
            return d

        depths = {}
        for pid in plan_by_id:
            depths[pid] = _plan_depth(pid, depths)

        # Build a tree where each child's primary parent is its deepest dep
        primary_parent = {}  # pid -> parent_pid (the dep with max depth)
        for pid in plan_by_id:
            p = plan_by_id[pid]
            deps = p.get("dependencies", []) or []
            if deps:
                best = max(deps, key=lambda d: depths.get(d, 0))
                primary_parent[pid] = best

        # Children keyed by primary parent
        children_of = {}
        roots = []
        for pid in plan_by_id:
            pp = primary_parent.get(pid)
            if pp:
                children_of.setdefault(pp, []).append(pid)
            elif pid not in primary_parent:
                roots.append(pid)
        roots = sorted(roots)

        if roots:
            def _draw(pid, prefix, is_last, visited):
                if pid in visited:
                    return [f"{prefix}{pid} (cycle)"]
                visited.add(pid)
                p = plan_by_id.get(pid, {})
                title = (p.get("title_cache") or p.get("title") or "")[:40]
                label = f"{pid}  {title}" if title else pid
                branch = "└─ " if is_last else "├─ "
                result = [f"{prefix}{branch}{label}"]
                kids = children_of.get(pid, [])
                # Sort kids by depth descending so deepest branch comes first
                kids.sort(key=lambda k: -depths.get(k, 0))
                for i, k in enumerate(kids):
                    lk = (i == len(kids) - 1)
                    np = prefix + ("   " if is_last else "│  ")
                    result.extend(_draw(k, np, lk, visited.copy()))
                return result

            for i, root in enumerate(roots):
                for ll in _draw(root, "", i == len(roots) - 1, set()):
                    lines.append(ll)
        else:
            lines.append("  No plan dependencies. Set in Plan.md frontmatter.")

    elif deps_sub == 1:
        # ── Tasks grouped by Plan ──
        plan_task_map = {}
        for t in task_list:
            pid = t.get("plan_id") or ""
            if pid:
                plan_task_map.setdefault(pid, []).append(t)
        if plan_task_map:
            sorted_plans = sorted(plan_task_map.keys())
            for pid in sorted_plans:
                ptitle = ""
                for p in plan_list:
                    if (p.get("plan_id") or p.get("id")) == pid:
                        ptitle = (p.get("title_cache") or p.get("title") or "")[:40]
                        break
                label = f"{pid}  {ptitle}" if ptitle else pid
                lines.append(label + ":")
                tasks = plan_task_map[pid]
                task_dep_order = {}
                for t in tasks:
                    wv = _task_wave(data, t.get("id"))
                    task_dep_order[t.get("id")] = wv if wv is not None else 0
                sorted_tasks = sorted(tasks, key=lambda t: task_dep_order.get(t.get("id"), 0))
                for t in sorted_tasks:
                    icon = status_icon(t.get("status", ""))
                    title = (t.get("title_cache") or t.get("title") or "")[:45]
                    deps = t.get("dependencies", []) or []
                    plan_ids = [d for d in deps if any(t2.get("plan_id") == pid and t2.get("id") == d for t2 in task_list)]
                    plan_labels = []
                    for d in plan_ids:
                        dt = next((t2 for t2 in task_list if t2.get("id") == d), {})
                        dtitle = (dt.get("title_cache") or dt.get("title") or "")[:25]
                        plan_labels.append(f"{d} ({dtitle})" if dtitle else d)
                    dep_str = f"  ← {', '.join(plan_labels)}" if plan_labels else ""
                    mark = " ◀" if t.get("id") == nid else ""
                    lines.append(f"  {icon} {t['id']}{mark}  {title}{dep_str}")
                lines.append("")
        else:
            lines.append("  No task dependencies. Set in Task.md frontmatter.")

    elif deps_sub == 2:
        # ── Goal capability deps ──
        tree_relations = data["goals"].get("relations", []) or []
        goal_by_id = {}
        for g in data["goals"].get("goals", []) or []:
            goal_by_id[g.get("id","")] = g
        if tree_relations:
            lines.append("Goal capability deps (X depends on Y):")
            for r in tree_relations:
                if isinstance(r, dict):
                    src = r.get("source_id","?")
                    tgt = r.get("target_id","?")
                    typ = r.get("type","?")
                    stitle = (goal_by_id.get(src,{}).get("title_cache") or goal_by_id.get(src,{}).get("title") or "")[:35]
                    ttitle = (goal_by_id.get(tgt,{}).get("title_cache") or goal_by_id.get(tgt,{}).get("title") or "")[:35]
                    lines.append(f"  {src} ({stitle})")
                    lines.append(f"    depends on → {tgt} ({ttitle})")
        else:
            lines.append("  No goal relations. Use: aiwf goal link <A> <B> --type depends_on")

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

    if kind == "mission":
        lines.append(f"Title: {data.get('mission_title', 'Mission')}")
        lines.append(f"Path: .aiwf/mission.md")
        lines.append(f"")
        lines.append(f"Press e to edit mission.")

    elif kind == "task":
        task = next((t for t in task_list if t.get("id") == nid), {})
        lines.append(f"Title: {task.get('title','')}")
        lines.append(f"Status: {task.get('status','?')}")
        deps = task.get("dependencies", []) or []
        if deps:
            satisfied = all(_find_task(data, d).get("status") == "closed" for d in deps)
            lines.append(f"Deps: [{'OK' if satisfied else 'BLOCKED'}] {', '.join(deps)}")
        ms_ids = [m.get("id") or m.get("milestone_id") for m in ms_list if nid in (m.get("task_ids", []) or [])]
        if ms_ids:
            lines.append(f"Milestones: {', '.join(ms_ids)}")

    elif kind == "plan":
        plan = next((p for p in plan_list if (p.get("plan_id") or p.get("id")) == nid), {})
        lines.append(f"Title: {plan.get('title','')}")
        lines.append(f"Status: {plan.get('status','?')}")
        task_ids = plan.get("task_ids", []) or []
        closed = _count_closed(data, task_ids)
        lines.append(f"Tasks: {closed}/{len(task_ids)} closed")
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
    detail_scroll = 0       # independent scroll for right panel
    detail_visible = True   # d toggles detail panel
    show_cancelled = False  # x toggles cancelled nodes
    tree_mode = 0  # 0=Main 1=MS 2=TasksByPlan 3=PlanChain 4=GoalDeps

    nodes_cache = []
    nodes_cache_key = ""
    last_data_mtime = 0

    while True:
        # Only reload data when files changed (check state.json mtime)
        try:
            state_mtime = (root / ".aiwf" / "state" / "state.json").stat().st_mtime
        except Exception:
            state_mtime = 0
        if state_mtime != last_data_mtime:
            last_data_mtime = state_mtime
            data = load_all(root)
            data["mission_title"] = _read_mission_title(root)
            t0 = build_tree(data); _precompute_tree_prefixes(t0)
            t1 = _build_ms_tree(data); _precompute_tree_prefixes(t1)
            t2 = _build_tasks_tree(data); _precompute_tree_prefixes(t2)
            t3 = _build_plan_chain(data); _precompute_tree_prefixes(t3)
            t4 = _build_goal_deps(data); _precompute_tree_prefixes(t4)

        trees = [t0, t1, t2, t3, t4]
        nodes = trees[tree_mode] if tree_mode < len(trees) else t0

        h, w = stdscr.getmaxyx()
        max_rows = h

        # Clamp selection
        if selected >= len(nodes):
            selected = max(0, len(nodes) - 1)
        if selected < scroll:
            scroll = selected
        elif selected >= scroll + max_rows - 3:
            scroll = selected - max_rows + 4

        render_tree(stdscr, nodes, selected, scroll, max_rows, detail_scroll, tree_mode, detail_visible, show_cancelled)

        key = stdscr.getch()
        if key == -1:  # timeout, just re-render
            continue

        if key == ord("q"):
            break
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
            tree_mode = (tree_mode + 1) % 5; last_data_mtime = 0
            selected = 0; scroll = 0; detail_scroll = 0
        elif key in (ord("\n"), ord("e")):
            # Edit MD in $EDITOR, auto-sync on return
            if 0 <= selected < len(nodes):
                node = nodes[selected]
                md_path = _md_path_for(node)
                if md_path:
                    full = root / md_path
                    if not full.exists():
                        full.parent.mkdir(parents=True, exist_ok=True)
                        full.write_text(f"# {node['title']}\n\n(fill)\n", encoding="utf-8")
                    _edit_and_sync(root, md_path)
                    # Auto-refresh: reload data after sync
        elif key == ord("s"):
            _run_sync_inline(root)
        elif key == ord("r"):
            if 0 <= selected < len(nodes):
                node = nodes[selected]
                if node["kind"] == "task":
                    _show_records_inline(stdscr, data, node["id"])
        elif key == ord("d"): detail_visible = not detail_visible; last_data_mtime = 0
        elif key == ord("x"): show_cancelled = not show_cancelled; set_show_cancelled(show_cancelled); last_data_mtime = 0
            # Force full refresh (reread all JSON)


def _read_mission_title(root):
    ms = root / ".aiwf" / "mission.md"
    if ms.exists():
        text = ms.read_text(encoding="utf-8")
        # Skip YAML frontmatter
        if text.startswith("---\n"):
            end = text.find("\n---\n", 4)
            if end != -1:
                text = text[end + 5:]
        for line in text.split("\n"):
            if line.startswith("# "):
                return line[2:].strip()
    return "Mission"


def _md_path_for(node):
    kind = node["kind"]
    nid = node["id"]
    if kind == "mission":
        return ".aiwf/mission.md"
    elif kind == "goal":
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

def _build_ms_tree(data: dict) -> list:
    """Build a milestone-rooted tree: Milestone → Goal → Plan → Task.

    Each milestone shows the complete hierarchy: all Goals involved, their
    Plans, and the Tasks under each Plan. Tasks linked directly to a milestone
    are placed under their Goal (or directly under the milestone if no Goal).
    """
    nodes = []
    state = data["state"]
    active_milestone_id = state.get("active_milestone_id", "")
    active_task_id = state.get("active_task_id", "")

    ms_list = data["milestones"].get("milestones", []) or []
    goal_by_id = {g.get("id", ""): g for g in (data["goals"].get("goals", []) or [])}
    plan_by_id = {}
    for p in (data["plans"].get("plans", []) or []):
        pid = p.get("plan_id") or p.get("id") or ""
        if pid:
            plan_by_id[pid] = p
    task_by_id = {t.get("id", ""): t for t in (data["tasks"].get("tasks", []) or [])}

    nodes.append({"kind": "mission", "id": "milestones", "title": "Milestones",
                  "indent": 0, "status": "", "active": False})

    for ms in ms_list:
        mid = ms.get("id") or ms.get("milestone_id") or "?"
        mstatus = ms.get("status", "pending")
        if not _SHOW_CANCELLED and mstatus in ("cancelled", "closed"):
            continue
        nodes.append({"kind": "milestone", "id": mid,
                      "title": ms.get("title_cache", ms.get("title", mid)),
                      "indent": 1, "status": mstatus,
                      "active": mid == active_milestone_id})

        # ── Collect plans and tasks linked to this milestone ──
        linked_plan_ids = list(ms.get("plan_ids", []) or [])
        linked_task_ids = set(ms.get("task_ids", []) or [])

        # Group plans by goal, collect tasks from plan.task_ids (sync-derived)
        goal_plans = {}   # gid → [plan]
        plan_tasks = {}   # pid → [task]
        plan_task_ids = set()
        for pid in linked_plan_ids:
            p = plan_by_id.get(pid, {})
            if not p:
                continue
            pstatus = p.get("status", "open")
            if not _SHOW_CANCELLED and pstatus in ("cancelled", "closed"):
                continue
            gid = p.get("goal_id") or ""
            goal_plans.setdefault(gid, []).append(p)
            for tid in (p.get("task_ids", []) or []):
                t = task_by_id.get(tid, {})
                if not t or (not _SHOW_CANCELLED and t.get("status") in ("cancelled",)):
                    continue
                plan_tasks.setdefault(pid, []).append(t)
                plan_task_ids.add(tid)

        # Direct tasks (linked to milestone, not already under a plan)
        goal_direct_tasks = {}
        for tid in sorted(linked_task_ids - plan_task_ids):
            t = task_by_id.get(tid, {})
            if not t or (not _SHOW_CANCELLED and t.get("status") in ("cancelled",)):
                continue
            gid = t.get("goal_id") or ""
            goal_direct_tasks.setdefault(gid, []).append(t)

        # ── Render: Goal → Plan → Task ──
        all_gids = sorted(set(list(goal_plans.keys()) + list(goal_direct_tasks.keys())))
        for gid in all_gids:
            g = goal_by_id.get(gid) if gid else None
            gstatus = g.get("status", "open") if g else "open"
            if g and (_SHOW_CANCELLED or gstatus not in ("cancelled", "closed")):
                gtitle = g.get("title_cache") or g.get("title") or gid
                nodes.append({"kind": "goal", "id": gid,
                              "title": f"{gid}  {gtitle}",
                              "indent": 2, "status": gstatus, "active": False})

            for p in goal_plans.get(gid, []):
                pid = p.get("plan_id") or p.get("id") or ""
                ptitle = (p.get("title_cache") or p.get("title") or pid)[:40]
                nodes.append({"kind": "plan", "id": pid,
                              "title": f"{pid}  {ptitle}",
                              "indent": 3, "status": p.get("status", "open"),
                              "active": False})
                for t in plan_tasks.get(pid, []):
                    tid = t.get("id", "")
                    ttitle = (t.get("title_cache") or t.get("title") or tid)[:40]
                    nodes.append({"kind": "task", "id": tid,
                                  "title": f"{tid}  {ttitle}",
                                  "indent": 4, "status": t.get("status", "ready"),
                                  "active": tid == active_task_id})

            for t in goal_direct_tasks.get(gid, []):
                tid = t.get("id", "")
                ttitle = (t.get("title_cache") or t.get("title") or tid)[:40]
                nodes.append({"kind": "task", "id": tid,
                              "title": f"{tid}  {ttitle}",
                              "indent": 3, "status": t.get("status", "ready"),
                              "active": tid == active_task_id})

    return nodes
"""Dependency tree builder for AIWF TUI."""
def _old_deps_tree(data: dict) -> list:
    nodes = []
    state = data["state"]
    active_task_id = state.get("active_task_id", "")

    plan_list = data["plans"].get("plans", []) or []
    task_list = data["tasks"].get("tasks", []) or []

    plan_by_id = {}
    for p in plan_list:
        pid = p.get("plan_id") or p.get("id") or ""
        if pid:
            plan_by_id[pid] = p

    def _depth(pid, cache=None):
        if cache is None:
            cache = {}
        if pid in cache:
            return cache[pid]
        p = plan_by_id.get(pid, {})
        deps = p.get("dependencies", []) or []
        if not deps:
            cache[pid] = 0
            return 0
        d = max(_depth(d, cache) for d in deps) + 1
        cache[pid] = d
        return d

    depths = {}
    for pid in plan_by_id:
        depths[pid] = _depth(pid, depths)

    primary = {}
    for pid in plan_by_id:
        deps = plan_by_id[pid].get("dependencies", []) or []
        if deps:
            primary[pid] = max(deps, key=lambda d: depths.get(d, 0))

    children_of = {}
    roots = []
    for pid in plan_by_id:
        pp = primary.get(pid)
        if pp:
            children_of.setdefault(pp, []).append(pid)
        elif pid not in primary:
            roots.append(pid)
    roots.sort()

    task_by_plan = {}
    for t in task_list:
        pid = t.get("plan_id") or ""
        if pid:
            task_by_plan.setdefault(pid, []).append(t)

    nodes.append({"kind": "mission", "id": "deps", "title": "Dependencies",
                  "indent": 0, "status": "", "active": False})

    added = set()

    def _add(pid, depth):
        if pid in added:
            return
        added.add(pid)
        p = plan_by_id.get(pid, {})
        title = (p.get("title_cache") or p.get("title") or pid)[:50]
        pstatus = p.get("status", "open")
        nodes.append({"kind": "plan", "id": pid, "title": title,
                      "indent": depth + 1, "status": pstatus, "active": False})
        for tid in (p.get("task_ids", []) or []):
            tdata = next((t for t in task_list if t.get("id") == tid), {})
            if not tdata or tdata.get("status") in ("cancelled",):
                continue
            tstatus = tdata.get("status", "ready")
            ttitle = (tdata.get("title_cache") or tdata.get("title") or tid)[:50]
            nodes.append({"kind": "task", "id": tid, "title": ttitle,
                          "indent": depth + 2, "status": tstatus,
                          "active": tid == active_task_id})
        kids = children_of.get(pid, [])
        kids.sort(key=lambda k: -depths.get(k, 0))
        for k in kids:
            _add(k, depth + 1)

    for root in roots:
        _add(root, 0)

    return nodes

def _build_tasks_tree(data: dict) -> list:
    """Tasks grouped by Plan — each plan shows its tasks with deps."""
    nodes = []
    task_list = data["tasks"].get("tasks", []) or []
    plan_list = data["plans"].get("plans", []) or []
    active_task_id = data["state"].get("active_task_id", "")
    plan_task_map = {}
    for t in task_list:
        pid = t.get("plan_id") or ""
        if pid:
            plan_task_map.setdefault(pid, []).append(t)
    nodes.append({"kind": "mission", "id": "tasks", "title": "Tasks by Plan",
                  "indent": 0, "status": "", "active": False})
    for pid in sorted(plan_task_map.keys()):
        p = next((p for p in plan_list if (p.get("plan_id") or p.get("id")) == pid), {})
        if not _SHOW_CANCELLED and p.get("status") in ("cancelled", "closed"):
            continue
        ptitle = (p.get("title_cache") or p.get("title") or pid)[:40]
        nodes.append({"kind": "plan", "id": pid, "title": f"{pid}  {ptitle}",
                      "indent": 1, "status": p.get("status", "open"), "active": False})
        def _twave(tid):
            return _task_wave(data, tid) or 0
        for t in sorted(plan_task_map[pid], key=lambda t: _twave(t.get("id"))):
            tid = t.get("id", "")
            if not _SHOW_CANCELLED and t.get("status") in ("cancelled",):
                continue
            ttitle = (t.get("title_cache") or t.get("title") or tid)[:40]
            dep_ids = [d for d in (t.get("dependencies", []) or []) if any(
                t2.get("plan_id") == pid and t2.get("id") == d for t2 in task_list)]
            dep_labels = []
            for d in dep_ids:
                dt = next((t2 for t2 in task_list if t2.get("id") == d), {})
                dtitle = (dt.get("title_cache") or dt.get("title") or "")[:30]
                dep_labels.append(f"{d} ({dtitle})" if dtitle else d)
            dep_str = f"  ← {', '.join(dep_labels)}" if dep_labels else ""
            nodes.append({"kind": "task", "id": tid, "title": f"{tid}  {ttitle}{dep_str}",
                          "indent": 2, "status": t.get("status", "ready"),
                          "active": tid == active_task_id})
    return nodes


def _build_plan_chain(data: dict) -> list:
    """Plan dependency chain — each plan once at its topological position."""
    nodes = []
    plan_list = data["plans"].get("plans", []) or []
    plan_by_id = {}
    for p in plan_list:
        pid = p.get("plan_id") or p.get("id") or ""
        if pid: plan_by_id[pid] = p
    def _depth(pid, cache=None):
        if cache is None: cache = {}
        if pid in cache: return cache[pid]
        deps = plan_by_id.get(pid, {}).get("dependencies", []) or []
        if not deps: cache[pid] = 0; return 0
        d = max(_depth(d, cache) for d in deps) + 1; cache[pid] = d; return d
    depths = {pid: _depth(pid, {}) for pid in plan_by_id}
    primary = {}
    for pid in plan_by_id:
        deps = plan_by_id[pid].get("dependencies", []) or []
        if deps: primary[pid] = max(deps, key=lambda d: depths.get(d, 0))
    children_of = {}
    roots = []
    for pid in plan_by_id:
        pp = primary.get(pid)
        if pp: children_of.setdefault(pp, []).append(pid)
        elif pid not in primary: roots.append(pid)
    roots.sort()
    nodes.append({"kind": "mission", "id": "planchain", "title": "Plan Chain",
                  "indent": 0, "status": "", "active": False})
    added = set()
    def _add(pid, depth):
        if pid in added: return
        added.add(pid)
        p = plan_by_id.get(pid, {})
        if not _SHOW_CANCELLED and p.get("status") in ("cancelled", "closed"):
            return
        title = (p.get("title_cache") or p.get("title") or pid)[:45]
        nodes.append({"kind": "plan", "id": pid, "title": f"{pid}  {title}",
                      "indent": depth + 1, "status": p.get("status", "open"), "active": False})
        kids = children_of.get(pid, [])
        kids.sort(key=lambda k: -depths.get(k, 0))
        for k in kids:
            _add(k, depth + 1)
    for root in roots:
        _add(root, 0)
    return nodes


def _build_goal_deps(data: dict) -> list:
    """Goal capability dependencies."""
    nodes = []
    goal_list = data["goals"].get("goals", []) or []
    rels = data["goals"].get("relations", []) or []
    goal_by_id = {g.get("id", ""): g for g in goal_list}
    nodes.append({"kind": "mission", "id": "goaldeps", "title": "Goal Deps",
                  "indent": 0, "status": "", "active": False})
    for r in rels:
        if not isinstance(r, dict): continue
        src = r.get("source_id", "?"); tgt = r.get("target_id", "?")
        stitle = (goal_by_id.get(src, {}).get("title_cache") or goal_by_id.get(src, {}).get("title") or "")[:30]
        ttitle = (goal_by_id.get(tgt, {}).get("title_cache") or goal_by_id.get(tgt, {}).get("title") or "")[:30]
        gstatus = goal_by_id.get(src, {}).get("status", "open")
        if not _SHOW_CANCELLED and gstatus in ("cancelled", "closed"):
            continue
        nodes.append({"kind": "goal", "id": src, "title": f"{src} ({stitle})  depends on → {tgt} ({ttitle})",
                      "indent": 1, "status": gstatus, "active": False})
    if not rels:
        nodes.append({"kind": "goal", "id": "norel", "title": "No goal relations yet",
                      "indent": 1, "status": "", "active": False})
    return nodes
