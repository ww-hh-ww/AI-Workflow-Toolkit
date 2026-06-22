"""Goal Tree CLI handlers — Stage 3.2.

Read-only display and lightweight mutation for the Goal Tree Registry.
Does NOT integrate with task activation, task close, or status --prompt."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys


def _now_str() -> str:
    return datetime.now(timezone.utc).isoformat()


def _update_md_status(entity_type: str, entity_id: str, status: str,
                      summary: str = "") -> None:
    """Write status back to MD frontmatter and sync to JSON."""
    from ..core.index_ops import parse_md, write_narrative_doc, sync_index
    dir_map = {"goal": ".aiwf/goals", "plan": ".aiwf/plans",
               "milestone": ".aiwf/milestones"}
    subdir = dir_map.get(entity_type)
    if not subdir:
        return
    doc = Path.cwd() / subdir / f"{entity_id}.md"
    if not doc.exists():
        return
    fm, body = parse_md(doc)
    if fm is None:
        return
    fm["status"] = status
    if summary:
        fm.setdefault("closure_summary", summary)
    write_narrative_doc(doc, fm, body)
    sync_index(str(Path.cwd()))


def _cmd_goal_tree_help(args: argparse.Namespace) -> None:
    print("AIWF Goal Tree — recursive functional skeleton")
    print()
    print("The Goal Tree is the structural backbone of a project.")
    print("Goals may contain child Goals. Plans attach to any Goal.")
    print("Temporary roots support trial growth outside the main tree.")
    print()
    print("Available subcommands:")
    print("  aiwf goal-tree init-root <ID> [--type main|temporary|branch] [--title ...] [--intent ...]")
    print("  aiwf goal-tree add <ID> --parent <PARENT-ID> [--title ...] [--intent ...]")
    print("  aiwf goal-tree show [<ID>]")
    print("  aiwf goal-tree list")
    print("  aiwf goal-tree list-temporary")
    print("  aiwf goal-tree validate")
    print()
    print("Goal Tree does not affect task activation or close gates.")


def _cmd_goal_tree_init_root(args: argparse.Namespace) -> None:
    from ..core.state.goal_tree_ops import init_root

    try:
        result = init_root(
            str(Path.cwd()),
            args.goal_id,
            root_type=args.type or "main",
            title=args.title or "",
            intent=args.intent or "",
        )
    except ValueError as e:
        print(f"init-root blocked: {e}", file=sys.stderr)
        raise SystemExit(1)

    g = result["goal"]
    root_type = g.get("root_type", "")
    print(f"Root Goal created: {g['id']}")
    print(f"  Title: {g.get('title', '')}")
    print(f"  Type: {root_type}")
    if root_type == "temporary":
        print(f"  Visibility: {g.get('visibility', '')}")
    if g.get("intent"):
        print(f"  Intent: {g['intent']}")
    if getattr(args, "narrative", False):
        from ..core.index_ops import create_narrative_for_entity
        path = create_narrative_for_entity(str(Path.cwd()), args.goal_id, "goal",
                                           title=args.title or "", status=g.get("status", ""))
        print(f"  Narrative doc: {path}")


def _cmd_goal_tree_add(args: argparse.Namespace) -> None:
    from ..core.state.goal_tree_ops import add_child_goal

    try:
        result = add_child_goal(
            str(Path.cwd()),
            args.parent_id,
            args.goal_id,
            title=args.title or "",
            intent=args.intent or "",
        )
    except ValueError as e:
        print(f"add blocked: {e}", file=sys.stderr)
        raise SystemExit(1)

    child = result["child"]
    print(f"Child Goal added: {child['id']}")
    print(f"  Parent: {child.get('parent_goal_id', '')}")
    print(f"  Title: {child.get('title', '')}")
    if getattr(args, "narrative", False):
        from ..core.index_ops import create_narrative_for_entity
        path = create_narrative_for_entity(str(Path.cwd()), args.goal_id, "goal",
                                           title=args.title or "", status=child.get("status", ""))
        print(f"  Narrative doc: {path}")


def _cmd_goal_tree_show(args: argparse.Namespace) -> None:
    from ..core.state.goal_tree_ops import get_goal, get_active_goal, list_goals

    goal_id = args.goal_id or ""
    if goal_id:
        goal = get_goal(str(Path.cwd()), goal_id)
        if not goal:
            print(f"Goal not found: {goal_id}", file=sys.stderr)
            raise SystemExit(1)
        _print_goal_detail(goal)
    else:
        # Show tree from active root
        active = get_active_goal(str(Path.cwd()))
        if active:
            _print_goal_tree(active, indent=0)
        else:
            goals = list_goals(str(Path.cwd()))
            if not goals:
                print("Goal Tree: empty")
                return
            # Show all roots
            from ..core.state.goal_tree_ops import list_roots
            roots = list_roots(str(Path.cwd()))
            if roots:
                for root in roots:
                    _print_goal_tree(root, indent=0)
            else:
                for g in goals:
                    _print_goal_tree(g, indent=0)


def _print_goal_detail(goal: dict) -> None:
    print(f"Goal: {goal.get('id', '')}")
    print(f"  Title: {goal.get('title', '')}")
    rt = goal.get("root_type")
    if rt:
        print(f"  Root Type: {rt}")
    print(f"  Status: {goal.get('status', '')}")
    print(f"  Parent: {goal.get('parent_goal_id') or '(none — root)'}")
    children = goal.get("child_goal_ids", []) or []
    print(f"  Children: {', '.join(children) if children else '(none)'}")
    plans = goal.get("attached_plan_ids", []) or []
    print(f"  Plans: {', '.join(plans) if plans else '(none)'}")
    if goal.get("intent"):
        print(f"  Intent: {goal['intent']}")
    if goal.get("acceptance_boundary"):
        print(f"  Acceptance: {goal['acceptance_boundary']}")


def _print_goal_tree(goal: dict, indent: int) -> None:
    prefix = "  " * indent
    gid = goal.get("id", "")
    title = goal.get("title", "")
    status = goal.get("status", "")
    rt = goal.get("root_type")
    tag = f" [{rt}]" if rt else ""
    print(f"{prefix}├─ {gid}{tag}  ({status})  {title}")

    from ..core.state.goal_tree_ops import get_goal
    base = str(Path.cwd())
    order = goal.get("children_order", []) or goal.get("child_goal_ids", []) or []

    # Show attached plans
    for pid in goal.get("attached_plan_ids", []) or []:
        print(f"{prefix}│    plan: {pid}")

    for cid in order:
        child = get_goal(base, cid)
        if child:
            _print_goal_tree(child, indent + 1)


def _cmd_goal_tree_list(args: argparse.Namespace) -> None:
    from ..core.state.goal_tree_ops import list_goals, list_roots

    goals = list_goals(str(Path.cwd()))
    if not goals:
        print("Goal Tree: empty")
        return

    roots = {r["id"] for r in list_roots(str(Path.cwd()))}
    print(f"Goals: {len(goals)}  (roots: {len(roots)})")
    for g in goals:
        gid = g.get("id", "")
        rt = g.get("root_type", "")
        tag = f" root={rt}" if rt else ""
        children = len(g.get("child_goal_ids", []) or [])
        plans = len(g.get("attached_plan_ids", []) or [])
        print(
            f"  {gid}{tag}  [{g.get('status', '')}]  "
            f"children={children}  plans={plans}  "
            f"{g.get('title', '')}"
        )


def _cmd_goal_tree_validate(args: argparse.Namespace) -> None:
    from ..core.state.goal_tree_ops import validate_goal_tree

    result = validate_goal_tree(str(Path.cwd()))
    if result["valid"]:
        print("Goal Tree: valid")
    else:
        print(f"Goal Tree: INVALID ({len(result['issues'])} issues)")
        for issue in result["issues"]:
            print(f"  - {issue}")
        raise SystemExit(1)


def _cmd_goal_tree_list_temporary(args: argparse.Namespace) -> None:
    from ..core.state.goal_tree_ops import list_temporary_roots

    temps = list_temporary_roots(str(Path.cwd()))
    if not temps:
        print("Temporary Roots: none")
        return
    print(f"Temporary Roots: {len(temps)}")
    for g in temps:
        children = len(g.get("child_goal_ids", []) or [])
        plans = len(g.get("attached_plan_ids", []) or [])
        print(
            f"  {g['id']}  [{g.get('status', '')}]  "
            f"children={children}  plans={plans}  "
            f"{g.get('title', '')}"
        )


# ── Stage 3.6: graft & prune ────────────────────────────────────────────

def _cmd_goal_tree_graft(args: argparse.Namespace) -> None:
    from ..core.state.goal_tree_ops import graft_branch

    affected = getattr(args, "affected_plans", None) or []
    try:
        result = graft_branch(
            str(Path.cwd()),
            args.source_id,
            args.target_parent_id,
            reason=args.reason or "",
            interface_consumed=getattr(args, "interface_consumed", "") or "",
            capability_provided=getattr(args, "capability_provided", "") or "",
            relation_to_parent=getattr(args, "relation_to_parent", "") or "",
            affected_plan_ids=affected,
            whether_parent_meaning_changes=getattr(args, "parent_meaning_changes", False),
        )
    except ValueError as e:
        print(f"graft blocked: {e}", file=sys.stderr)
        raise SystemExit(1)

    r = result["graft_record"]
    print(f"Grafted: {r['source_id']} → {r['target_parent_id']}")
    print(f"  Previous root type: {r.get('previous_root_type') or '(none)'}")
    if r.get("reason"):
        print(f"  Reason: {r['reason']}")
    if r.get("interface_consumed"):
        print(f"  Interface consumed: {r['interface_consumed']}")
    if r.get("capability_provided"):
        print(f"  Capability provided: {r['capability_provided']}")
    if r.get("relation_to_parent"):
        print(f"  Relation to parent: {r['relation_to_parent']}")
    if r.get("affected_plan_ids"):
        print(f"  Affected plans: {', '.join(r['affected_plan_ids'])}")
    if r.get("whether_parent_meaning_changes"):
        print(f"  Parent meaning changes: yes")


def _cmd_goal_tree_prune(args: argparse.Namespace) -> None:
    from ..core.state.goal_tree_ops import prune_branch

    try:
        result = prune_branch(
            str(Path.cwd()),
            args.branch_id,
            reason=args.reason or "",
        )
    except ValueError as e:
        print(f"prune blocked: {e}", file=sys.stderr)
        raise SystemExit(1)

    print(f"Pruned: {args.branch_id} → archived")
    if result.get("abandoned_plans"):
        print(f"  Abandoned Plans: {', '.join(result['abandoned_plans'])}")
    if result.get("abandoned_child_goals"):
        print(f"  Abandoned Child Goals: {', '.join(result['abandoned_child_goals'])}")


# ── Stage 3.7: sibling relations ────────────────────────────────────────

def _cmd_relation_add(args: argparse.Namespace) -> None:
    from ..core.state.goal_tree_ops import add_relation

    try:
        result = add_relation(
            str(Path.cwd()),
            args.source_id,
            args.target_id,
            rel_type=args.rel_type,
            reason="",
            allow_cross=getattr(args, "cross", False),
        )
    except ValueError as e:
        print(f"relation add blocked: {e}", file=sys.stderr)
        raise SystemExit(1)

    r = result["relation"]
    tag = " (cross-parent)" if r.get("cross_parent") else ""
    from ..core.index_ops import sync_index
    sync_index(str(Path.cwd()))
    print(f"Relation: {r['source_id']} --[{r['type']}]--> {r['target_id']}{tag}")


def _cmd_relation_remove(args: argparse.Namespace) -> None:
    from ..core.state.goal_tree_ops import remove_relation

    result = remove_relation(str(Path.cwd()), args.source_id, args.target_id)
    if result.get("removed"):
        from ..core.index_ops import sync_index
        sync_index(str(Path.cwd()))
        print(f"Relation removed: {args.source_id} → {args.target_id}")
    else:
        print(f"Relation not found: {args.source_id} → {args.target_id}")


def _cmd_relation_show(args: argparse.Namespace) -> None:
    from ..core.state.goal_tree_ops import get_relations

    relations = get_relations(str(Path.cwd()), args.node_id)
    if not relations:
        print(f"Relations for {args.node_id}: none")
        return
    print(f"Relations for {args.node_id}: {len(relations)}")
    for r in relations:
        print(f"  {r['source_id']} --[{r['type']}]--> {r['target_id']}")


# ── Stage 3.8: impact cone ──────────────────────────────────────────────

def _cmd_goal_tree_impact(args: argparse.Namespace) -> None:
    from ..core.state.impact_ops import compute_impact_cone

    result = compute_impact_cone(str(Path.cwd()), args.goal_id)
    if not result.get("found"):
        print(f"Goal not found: {args.goal_id}", file=sys.stderr)
        raise SystemExit(1)

    print(f"Impact Cone for {args.goal_id}:")
    ancestors = result.get("ancestors", []) or []
    print(f"  Ancestors: {', '.join(ancestors) if ancestors else '(none — root)'}")
    children = [c["id"] for c in result.get("children", []) or []]
    print(f"  Children: {', '.join(children) if children else '(none)'}")
    relations = result.get("relations", []) or []
    if relations:
        print(f"  Sibling Relations:")
        for r in relations:
            print(f"    {r['source_id']} --[{r['type']}]--> {r['target_id']}")
    plans = result.get("attached_plans", []) or []
    print(f"  Attached Plans: {', '.join(plans) if plans else '(none)'}")
    print(f"  Active Tasks: {', '.join(result.get('active_tasks', []) or []) or '(none)'}")


# ── V2 unified goal commands ──

def _cmd_goal_create(args: argparse.Namespace) -> None:
    """Create a goal — root if no parent, child if --parent given."""
    from ..core.state.goal_tree_ops import init_root, add_child_goal
    def _g(key, default=""):
        return getattr(args, key, default)

    parent_id = _g("parent_id") or _g("parent")
    title = _g("title")
    goal_id = _g("goal_id")
    narrative = bool(_g("narrative"))

    try:
        if parent_id:
            result = add_child_goal(str(Path.cwd()), parent_id, goal_id, title=title)
        else:
            result = init_root(str(Path.cwd()), goal_id, root_type="main", title=title)
    except ValueError as e:
        print(f"Goal create blocked: {e}", file=sys.stderr)
        raise SystemExit(1)

    g = result.get("goal", result)
    gid = g.get("id") or g.get("goal_id") or goal_id
    print(f"Goal created: {gid}")
    from ..core.index_ops import create_narrative_for_entity, parse_md, compute_content_hash, sync_index
    from ..core.state.goal_tree_ops import load_goal_tree, save_goal_tree, _find_goal
    path = create_narrative_for_entity(str(Path.cwd()), gid, "goal", title=title,
                                       status=g.get("status", ""),
                                       parent_goal_id=parent_id)
    # Bind doc_path + hash in goals.json so sync can find it
    full_path = Path.cwd() / path
    if full_path.exists():
        _, body = parse_md(full_path)
        doc_hash = compute_content_hash(body) if body else ""
        tree = load_goal_tree(str(Path.cwd()))
        node = _find_goal(tree, gid)
        if node:
            node["doc_path"] = path
            node["doc_hash"] = doc_hash
            node["doc_updated_at"] = _now_str()
            save_goal_tree(str(Path.cwd()), tree)
    print(f"  Narrative doc: {path}")
    sync_result = sync_index(str(Path.cwd()))
    if sync_result["changes"]:
        for c in sync_result["changes"][:5]:
            print(f"  sync: {c}")


def _cmd_goal_update(args: argparse.Namespace) -> None:
    """Update a goal's title or status."""
    from ..core.state.goal_tree_ops import load_goal_tree, save_goal_tree, _find_goal
    tree = load_goal_tree(str(Path.cwd()))
    node = _find_goal(tree, args.goal_id)
    if not node:
        print(f"Goal not found: {args.goal_id}", file=sys.stderr)
        raise SystemExit(1)
    if getattr(args, "title", ""):
        node["title"] = args.title
    if getattr(args, "status", ""):
        node["status"] = args.status
    save_goal_tree(str(Path.cwd()), tree)
    print(f"Goal updated: {args.goal_id}")


def _cmd_goal_cancel(args: argparse.Namespace) -> None:
    """Archive a goal — delegates to goal_tree_prune."""
    from ..core.state.goal_tree_ops import load_goal_tree, save_goal_tree, _find_goal
    tree = load_goal_tree(str(Path.cwd()))
    node = _find_goal(tree, args.goal_id)
    if not node:
        print(f"Goal not found: {args.goal_id}", file=sys.stderr)
        raise SystemExit(1)
    node["status"] = "cancelled"
    reason = getattr(args, "reason", "") or ""
    if reason:
        node["cancel_reason"] = reason
    replaced_by = getattr(args, "replaced_by", "") or ""
    if replaced_by:
        node["replaced_by"] = replaced_by
    if tree.get("active_goal_id") == args.goal_id:
        tree["active_goal_id"] = None
    save_goal_tree(str(Path.cwd()), tree)
    _update_md_status("goal", args.goal_id, "cancelled")
    print(f"Goal cancelled: {args.goal_id}")
    if reason:
        print(f"  Reason: {reason}")
    if replaced_by:
        print(f"  Replaced by: {replaced_by}")



def _cmd_goal_close(args: argparse.Namespace) -> None:
    from ..core.state.goal_tree_ops import load_goal_tree, save_goal_tree, _find_goal
    tree = load_goal_tree(str(Path.cwd()))
    node = _find_goal(tree, getattr(args, "goal_id", ""))
    if not node:
        print(f"Goal not found: {getattr(args, 'goal_id', '')}", file=sys.stderr)
        raise SystemExit(1)
    summary = getattr(args, "summary", "") or ""
    node["status"] = "closed"
    node["closure"] = {"mode": "normal", "accepted": True, "summary": summary}
    save_goal_tree(str(Path.cwd()), tree)
    _update_md_status("goal", getattr(args, "goal_id", ""), "closed", summary)
    print(f"Goal closed: {getattr(args, 'goal_id', '')}")


def _cmd_goal_help(args: argparse.Namespace) -> None:
    print("AIWF Goal — node CRUD and linking")
    print()
    print("  aiwf goal create GOAL-001 --title '...'         — create a root goal")
    print("  aiwf goal create GOAL-002 --parent GOAL-001     — create a child goal")
    print("  aiwf goal show [GOAL-ID]                        — show goal or full tree")
    print("  aiwf goal list                                  — list all goals")
    print("  aiwf goal rename GOAL-001 --title '...'         — rename a goal")
    print("  aiwf goal close GOAL-001 --summary '...'        — close a goal")
    print("  aiwf goal cancel GOAL-001 --reason '...'        — cancel a goal")
    print("  aiwf goal link GOAL-A GOAL-B --type supports    — add a relation")
    print("  aiwf goal unlink GOAL-A GOAL-B                  — remove a relation")
