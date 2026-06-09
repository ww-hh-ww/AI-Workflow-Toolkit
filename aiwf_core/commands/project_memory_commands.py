"""CLI command handlers for AIWF embedded mainline."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..constants import VERSION

def _cmd_idea_capture(args: argparse.Namespace) -> None:
    """aiwf idea capture — capture a new idea."""
    from ..core.ideas import capture_idea
    idea = capture_idea(str(Path.cwd()), text=args.text, tags=args.tags or None,
                         source=args.source, expires_days=args.expires_days)
    print("Idea captured:")
    print(f"  ID:      {idea['id']}")
    print(f"  Status:  {idea['status']}")
    print(f"  Expires: {idea['expires_at'][:19]}")
    print(f"  Text:    {idea['text'][:120]}")
    if idea.get("tags"): print(f"  Tags:    {', '.join(idea['tags'])}")

def _cmd_idea_list(args: argparse.Namespace) -> None:
    """aiwf idea list — list ideas."""
    from ..core.ideas import list_ideas, is_idea_active
    from ..core.ideas import _parse_ideas as _pi
    if args.include_expired:
        # Show all with markers
        path = (Path.cwd() / ".aiwf" / "reports" / "ideas.md")
        all_ideas = _pi(path.read_text(encoding="utf-8")) if path.exists() else []
        if not all_ideas:
            print("Ideas: none")
            return
        print(f"Ideas: {len(all_ideas)}")
        for i in all_ideas:
            status = i['status']
            if status in ("raw","candidate") and not is_idea_active(i):
                status += " (stale)"
            print(f"  {i['id']} | {status} | {i.get('expires_at','')[:10]} | "
                  f"{', '.join(i.get('tags',[]))} | {i.get('text','')[:80]}")
    else:
        ideas = list_ideas(str(Path.cwd()), include_expired=False)
        if not ideas:
            print("Ideas: none")
            return
        print(f"Ideas: {len(ideas)}")
        for i in ideas:
            print(f"  {i['id']} | {i['status']} | {i.get('expires_at','')[:10]} | "
                  f"{', '.join(i.get('tags',[]))} | {i.get('text','')[:80]}")

def _cmd_idea_promote(args: argparse.Namespace) -> None:
    """aiwf idea promote — promote an idea to adopted."""
    from ..core.ideas import promote_idea
    try:
        idea = promote_idea(str(Path.cwd()), idea_id=args.id, target=args.target, note=args.note)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Idea promoted: {idea['id']} → adopted")
    if args.target: print(f"  Target: {args.target}")
    print("  Does NOT auto-modify goal/PROJECT-MAP/quality_brief. Update them explicitly.")

def _cmd_idea_expire(args: argparse.Namespace) -> None:
    """aiwf idea expire — expire an idea."""
    from ..core.ideas import expire_idea
    try:
        idea = expire_idea(str(Path.cwd()), idea_id=args.id, reason=args.reason)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Idea expired: {idea['id']}")
    if args.reason: print(f"  Reason: {args.reason[:120]}")

def _cmd_idea_help(args: argparse.Namespace) -> None:
    """aiwf idea — show available subcommands."""
    print("AIWF Idea Inbox")
    print()
    print("Available subcommands:")
    print("  aiwf idea capture  — capture a new idea")
    print("  aiwf idea list     — list active ideas")
    print("  aiwf idea promote  — promote an idea to adopted (does NOT modify formal state)")
    print("  aiwf idea expire   — expire an idea")

def _cmd_project_map_init(args: argparse.Namespace) -> None:
    """aiwf project-map init — create PROJECT-MAP.md."""
    from ..core.project_map import ensure_project_map
    ensure_project_map(str(Path.cwd()))
    print("PROJECT-MAP.md created at .aiwf/reports/项目地图.md")

def _cmd_project_map_show(args: argparse.Namespace) -> None:
    """aiwf project-map show — display PROJECT-MAP.md."""
    from ..core.project_map import load_project_map
    text = load_project_map(str(Path.cwd()))
    if not text:
        print("PROJECT-MAP.md not found. Run: aiwf project-map init")
    else:
        print(text)

def _cmd_project_map_update(args: argparse.Namespace) -> None:
    """aiwf project-map update — update a section."""
    from ..core.project_map import update_project_map_section
    try:
        result = update_project_map_section(str(Path.cwd()), args.section, args.text)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Updated section: {result['section']}")

def _cmd_project_map_summarize(args: argparse.Namespace) -> None:
    """aiwf project-map summarize — show short summary."""
    from ..core.project_map import summarize_project_map
    s = summarize_project_map(str(Path.cwd()))
    if not s.get("exists"):
        print("PROJECT-MAP.md not found. Run: aiwf project-map init")
        return
    print("Project Map summary:")
    if s.get("current_stage"): print(f"  Current stage: {s['current_stage']}")
    if s.get("architecture_direction"): print(f"  Architecture direction: {s['architecture_direction']}")
    print(f"  Next tasks: {s.get('next_tasks_count', 0)}")
    print(f"  Open decisions: {s.get('open_decisions_count', 0)}")
    print(f"  Deferred risks: {s.get('deferred_risks_count', 0)}")
    print(f"  Rejected routes: {s.get('rejected_routes_count', 0)}")

def _cmd_project_map_help(args: argparse.Namespace) -> None:
    """aiwf project-map — show available subcommands."""
    print("AIWF Project Map")
    print()
    print("Available subcommands:")
    print("  aiwf project-map init       — create PROJECT-MAP.md")
    print("  aiwf project-map show       — display PROJECT-MAP.md")
    print("  aiwf project-map update     — update a section")
    print("  aiwf project-map summarize  — show short summary")

def _cmd_rule_add(args: argparse.Namespace) -> None:
    from ..core.project_rules import add_project_rule
    r = add_project_rule(str(Path.cwd()), text=args.text, source=args.source, tags=args.tags or None)
    print(f"Rule added:")
    print(f"  ID:   {r['id']}")
    print(f"  Type: {r['type']}")
    print(f"  Text: {r['text'][:120]}")

def _cmd_rule_add_negative(args: argparse.Namespace) -> None:
    from ..core.project_rules import add_negative_rule
    r = add_negative_rule(str(Path.cwd()), text=args.text, source=args.source, tags=args.tags or None)
    print(f"Negative rule added:")
    print(f"  ID:   {r['id']}")
    print(f"  Text: {r['text'][:120]}")

def _cmd_rule_list(args: argparse.Namespace) -> None:
    from ..core.project_rules import list_project_rules
    rules = list_project_rules(str(Path.cwd()))
    if not rules:
        print("Rules: none")
        return
    print(f"Rules: {len(rules)}")
    for r in rules:
        print(f"  {r['id']} | {r['status']} | {r['type']} | {r.get('text','')[:100]}")

def _cmd_rule_retire(args: argparse.Namespace) -> None:
    from ..core.project_rules import retire_rule
    try:
        retire_rule(str(Path.cwd()), rule_id=args.id, reason=args.reason)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Rule retired: {args.id}")

def _cmd_rule_global_candidate(args: argparse.Namespace) -> None:
    from ..core.project_rules import mark_global_candidate
    try:
        mark_global_candidate(str(Path.cwd()), rule_id=args.id, note=args.note)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Marked global candidate: {args.id}")

def _cmd_rule_help(args: argparse.Namespace) -> None:
    print("AIWF Project Rules")
    print()
    print("Available subcommands:")
    print("  aiwf rule add              — add a project rule")
    print("  aiwf rule add-negative     — add a negative rule / guardrail")
    print("  aiwf rule list             — list active rules")
    print("  aiwf rule retire           — retire a rule")
    print("  aiwf rule global-candidate — mark as global lesson candidate")

def _cmd_goal_revise(args: argparse.Namespace) -> None:
    """aiwf goal revise — revise current goal with intent tracking."""
    from ..core.state_ops import revise_goal
    goal = revise_goal(str(Path.cwd()), args.new_goal, args.reason,
                       decision=args.decision or "", source=args.source or "user")
    print(f"Goal revised:")
    print(f"  Version: {goal['goal_version']}")
    print(f"  Current goal: {goal['current_goal'][:150]}")
    print(f"  Reason: {args.reason[:120]}")
    if args.decision: print(f"  Decision: {args.decision[:120]}")

def _cmd_goal_help(args: argparse.Namespace) -> None:
    """aiwf goal — show available subcommands."""
    print("AIWF Goal Operations")
    print()
    print("Available subcommands:")
    print("  aiwf goal revise   — revise current goal with intent tracking")
    print("  aiwf goal decide   — record a goal-level decision")

def _cmd_goal_decide(args: argparse.Namespace) -> None:
    """aiwf goal decide — record a goal-level decision."""
    from ..core.state_ops import record_goal_decision
    record_goal_decision(str(Path.cwd()), args.decision, source=args.source or "user")
    print(f"Decision recorded: {args.decision[:150]}")

def _cmd_memory_help(args: argparse.Namespace) -> None:
    """aiwf memory — show available subcommands."""
    print("AIWF Memory Operations")
    print()
    print("Available subcommands:")
    print("  aiwf memory suggest   — suggest relevant lessons (advisory)")

def _cmd_memory_suggest(args: argparse.Namespace) -> None:
    from ..core.memory import suggest_relevant_lessons
    result = suggest_relevant_lessons(str(Path.cwd()), goal=args.goal,
                                       task_type=args.task_type, files=args.files or None,
                                       limit=args.limit)
    if result.get("relevant_lessons"):
        print("Relevant lessons:")
        for l in result["relevant_lessons"]: print(f"  - {l[:200]}")
    if result.get("relevant_negative_patterns"):
        print("Relevant negative patterns:")
        for n in result["relevant_negative_patterns"]: print(f"  - {n[:200]}")
    if result.get("followup_candidates"):
        print("Follow-up candidates:")
        for f in result["followup_candidates"]: print(f"  - {f[:200]}")
    if result.get("relevant_deferred_risks"):
        print("Relevant deferred risks:")
        for r in result["relevant_deferred_risks"]: print(f"  - {r[:200]}")
    if not any([result.get("relevant_lessons"), result.get("relevant_negative_patterns"),
                    result.get("followup_candidates"), result.get("suggested_test_focus"),
                    result.get("suggested_review_focus"), result.get("suggested_non_goals"),
                    result.get("suggested_escalation_triggers")]):
        print("No relevant lessons found for current task context.")

    sug = False
    for key, label in [("suggested_test_focus", "test_focus"), ("suggested_review_focus", "review_focus"),
                        ("suggested_non_goals", "non_goals"), ("suggested_escalation_triggers", "escalation_triggers")]:
        items = result.get(key, [])
        if items:
            if not sug: print(); print("Suggested uses:"); sug = True
            print(f"  - {label}:")
            for item in items: print(f"      - {item[:160]}")

    print()
    print("These are advisory. Planner must explicitly adopt them before they affect the task.")

def _cmd_asset_init(args: argparse.Namespace) -> None:
    """aiwf asset init — create .aiwf/assets/ with project-map, test-map, conventions."""
    from ..assets.schema import init_assets
    result = init_assets(str(Path.cwd()))
    print(f"# AIWF Asset Layer Initialized")
    print(f"  Source files: {result['source_files']}")
    print(f"  Test files: {result['test_files']}")
    print(f"  Created: {', '.join(result['created'])}")

def _cmd_asset_refresh(args: argparse.Namespace) -> None:
    """aiwf asset refresh — check or update asset freshness."""
    from ..assets.schema import refresh_assets
    do_update = getattr(args, "update", False)
    result = refresh_assets(str(Path.cwd()), update=do_update)
    print(f"# AIWF Asset Refresh")
    print(f"  Overall: {result['overall']}")
    for name, status in result["assets"].items():
        print(f"  {name}: {status}")
    if result["stale_files"]:
        print("  Stale/changed files:")
        for f in result["stale_files"][:10]:
            print(f"    - {f}")


def _cmd_project_bootstrap(args: argparse.Namespace) -> None:
    """aiwf project bootstrap — scan existing code, create baseline assets."""
    from ..core.state_ops import bootstrap_project
    result = bootstrap_project(str(Path.cwd()))
    if not result.get("bootstrapped"):
        print(f"Bootstrap skipped: {result.get('reason', 'unknown')}")
        return
    print(f"Project bootstrapped:")
    print(f"  Files: {result['files']} source files")
    print(f"  Modules: {len(result['modules'])} detected ({', '.join(result['modules'][:8])})")
    for t in result['tasks']:
        print(f"  [OK] {t}")
