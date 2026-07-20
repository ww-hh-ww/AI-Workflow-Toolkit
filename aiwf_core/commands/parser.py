"""Argument parser — V1 whitelist-only command registration."""
from __future__ import annotations

import argparse
from pathlib import Path

from .flow import cmd_status
from .ops_commands import _cmd_doctor, _cmd_fix_loop_continue, _cmd_fix_loop_help, _cmd_fix_loop_open, _cmd_fix_loop_resolve, _cmd_fix_loop_status, _cmd_install
from .plan_commands import (
    _cmd_plan_attach,
    _cmd_plan_bind_worktree,
    _cmd_plan_cancel,
    _cmd_plan_close,
    _cmd_plan_create,
    _cmd_plan_dep_add,
    _cmd_plan_dep_remove,
    _cmd_plan_dep_show,
    _cmd_plan_detach,
    _cmd_plan_help,
    _cmd_plan_hold,
    _cmd_plan_list,
    _cmd_plan_show,
)
from .state_commands import _cmd_record_disposition, _cmd_record_help, _cmd_record_implementation, _cmd_record_review, _cmd_record_testing
from .goal_tree_commands import _cmd_goal_cancel, _cmd_goal_close, _cmd_goal_create, _cmd_goal_help, _cmd_goal_tree_list, _cmd_goal_tree_show, _cmd_relation_add, _cmd_relation_remove
from .milestone_commands import _cmd_milestone_arch_review, _cmd_milestone_assess, _cmd_milestone_cancel, _cmd_milestone_close, _cmd_milestone_confirm, _cmd_milestone_create, _cmd_milestone_help, _cmd_milestone_integration_test, _cmd_milestone_link_plan, _cmd_milestone_link_task, _cmd_milestone_list, _cmd_milestone_show, _cmd_milestone_unlink_plan, _cmd_milestone_unlink_task
from .mission_commands import _cmd_mission_show
from .task_commands import _cmd_task_activate, _cmd_task_calibrate, _cmd_task_cancel, _cmd_task_close, _cmd_task_critique, _cmd_task_force_close, _cmd_task_help, _cmd_task_interrupt, _cmd_task_plan, _cmd_task_proof, _cmd_task_show, _cmd_task_status
from ..constants import VERSION


def _cmd_ui(args: argparse.Namespace) -> None:
    """aiwf ui — TUI browser."""
    from ..aiwf_ui import run_ui
    run_ui()


def _cmd_sync(args: argparse.Namespace) -> None:
    """aiwf sync — compile MD frontmatter into JSON machine state."""
    from ..core.index_ops import sync_index
    result = sync_index(str(Path.cwd()), dry_run=bool(args.check))
    if result["errors"]:
        print(f"Sync: {len(result['errors'])} error(s)")
        for e in result["errors"]:
            print(f"  ERROR: {e}")
        raise SystemExit(1)
    if args.check:
        print(f"Sync check: {result['synced']} entities would be synced")
    else:
        print(f"Synced: {result['synced']} entities")
    for change in result.get("changes", [])[:20]:
        print(f"  {change}")
    for lock_msg in result.get("lock_messages", []):
        print(f"  {lock_msg}")


def build_parser(cmd_init) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aiwf",
        description="AIWF — Embedded coding-shell workflow governance.",
        epilog="Primary path: aiwf install claude (or reasonix)",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd")
    sub.required = False

    # ── sync ──
    p_sync = sub.add_parser("sync", help="sync MD frontmatter -> JSON (--check for dry-run)")
    p_sync.add_argument("--check", action="store_true", help="validate only, do not write")
    p_sync.set_defaults(func=_cmd_sync)

    # ── ui ──
    sub.add_parser("ui", help="TUI browser for governance structure").set_defaults(func=_cmd_ui)

    # ── status / install / doctor ──
    p_install = sub.add_parser("install", help="install AIWF integration (skills, hooks, agents, state, scripts)")
    p_install.add_argument("mode", choices=["claude", "reasonix"], help="installation mode")
    p_install.add_argument("--force", action="store_true", help="force overwrite")
    p_install.set_defaults(func=_cmd_install)
    sub.add_parser("doctor", help="check AIWF installation health").set_defaults(func=_cmd_doctor)
    p_status = sub.add_parser("status", help="show project status (--prompt for AI, --debug for full)")
    p_status.add_argument("--prompt", action="store_true", help="AI prompt injection format")
    p_status.add_argument("--debug", action="store_true", help="full debug panel")
    p_status.set_defaults(func=cmd_status)

    # ── fixloop ──
    p_fixloop = sub.add_parser("fixloop", help="fix-loop recovery")
    p_fl_sub = p_fixloop.add_subparsers(dest="fixloop_cmd")
    p_fl_open = p_fl_sub.add_parser("open", help="open a fix-loop")
    p_fl_open.add_argument("--route", required=True, choices=["executor","tester","planner","environment"])
    p_fl_open.add_argument("--reason", required=True, help="reason for opening")
    p_fl_open.add_argument("--required-fix", action="append", dest="required_fixes", default=[])
    p_fl_open.add_argument("--required-verification", action="append", default=[])
    p_fl_open.add_argument("--source", default="reviewer")
    p_fl_open.add_argument("--invalidated-file", action="append", dest="invalidated_files", default=[])
    p_fl_open.add_argument("--invalidated-obligation", action="append", dest="invalidated_obligations", default=[])
    p_fl_open.add_argument("--task-id", default="", help="Task ID (defaults to current worktree)")
    p_fl_open.set_defaults(func=_cmd_fix_loop_open)
    p_fl_status = p_fl_sub.add_parser("status", help="show fix-loop status")
    p_fl_status.add_argument("--task-id", default="", help="Task ID (defaults to current worktree)")
    p_fl_status.set_defaults(func=_cmd_fix_loop_status)
    p_fl_continue = p_fl_sub.add_parser("continue", help="human-only continuation after escalation")
    p_fl_continue.add_argument("--task-id", default="", help="Task ID (defaults to current worktree)")
    p_fl_continue.set_defaults(func=_cmd_fix_loop_continue)
    p_fl_resolve = p_fl_sub.add_parser("resolve", help="resolve a fix-loop")
    p_fl_resolve.add_argument("--resolution", required=True, help="how it was resolved")
    p_fl_resolve.add_argument("--source", default="reviewer")
    p_fl_resolve.add_argument("--force", action="store_true")
    p_fl_resolve.add_argument("--task-id", default="", help="Task ID (defaults to current worktree)")
    p_fl_resolve.set_defaults(func=_cmd_fix_loop_resolve)
    p_fixloop.set_defaults(func=_cmd_fix_loop_help)

    # ── mission ──
    p_mis = sub.add_parser("mission", help="project mission")
    p_mis_sub = p_mis.add_subparsers(dest="mission_cmd")
    p_mis_sub.add_parser("show", help="show current mission").set_defaults(func=_cmd_mission_show)
    p_mis.set_defaults(func=_cmd_mission_show)

    # ── goal ──
    p_goal = sub.add_parser("goal", help="Goal node CRUD and linking")
    p_goal_sub = p_goal.add_subparsers(dest="goal_cmd")
    p_gcr = p_goal_sub.add_parser("create", help="create a goal")
    p_gcr.add_argument("goal_id", help="goal ID, e.g. GOAL-001")
    p_gcr.add_argument("--parent", default="", dest="parent_id", help="parent goal ID (omit for root)")
    p_gcr.add_argument("--title", default="", help="goal title")
    p_gcr.set_defaults(func=_cmd_goal_create)
    p_gsh = p_goal_sub.add_parser("show", help="show a goal or the full tree")
    p_gsh.add_argument("goal_id", nargs="?", default="", help="goal ID (omit for tree view)")
    p_gsh.set_defaults(func=_cmd_goal_tree_show)
    p_goal_sub.add_parser("list", help="list all goals").set_defaults(func=_cmd_goal_tree_list)
    p_gcl = p_goal_sub.add_parser("close", help="close a goal")
    p_gcl.add_argument("goal_id", help="goal ID")
    p_gcl.add_argument("--summary", default="", help="closure summary")
    p_gcl.set_defaults(func=_cmd_goal_close)
    p_gca = p_goal_sub.add_parser("cancel", help="cancel a goal")
    p_gca.add_argument("goal_id", help="goal ID")
    p_gca.add_argument("--reason", default="", help="why this goal is cancelled")
    p_gca.set_defaults(func=_cmd_goal_cancel)
    p_gl = p_goal_sub.add_parser("link", help="link two goals")
    p_gl.add_argument("source_id", help="source goal ID")
    p_gl.add_argument("target_id", help="target goal ID")
    p_gl.add_argument("--type", default="supports", dest="rel_type", choices=["depends_on","blocks","conflicts_with","invalidates","supports"])
    p_gl.set_defaults(func=_cmd_relation_add)
    p_gul = p_goal_sub.add_parser("unlink", help="unlink two goals")
    p_gul.add_argument("source_id", help="source goal ID")
    p_gul.add_argument("target_id", help="target goal ID")
    p_gul.set_defaults(func=_cmd_relation_remove)
    p_goal.set_defaults(func=_cmd_goal_help)

    # ── plan ──
    p_plan = sub.add_parser("plan", help="Plan node CRUD and task linking")
    p_plan_sub = p_plan.add_subparsers(dest="plan_cmd")
    p_plc = p_plan_sub.add_parser("create", help="create a plan")
    p_plc.add_argument("plan_id", help="plan ID, e.g. PLAN-001")
    p_plc.add_argument("--goal", default="", dest="goal_id", help="GOAL-ID this plan serves")
    p_plc.add_argument("--title", default="", help="plan title")
    p_plc.add_argument("--task", action="append", default=[], dest="task_ids", help="task ID to link")
    p_plc.add_argument("--milestone-id", default="", help="optional milestone ID")
    p_plc.set_defaults(func=_cmd_plan_create)
    p_pls = p_plan_sub.add_parser("show", help="show a plan")
    p_pls.add_argument("plan_id", help="plan ID")
    p_pls.set_defaults(func=_cmd_plan_show)
    p_plan_sub.add_parser("list", help="list all plans").set_defaults(func=_cmd_plan_list)
    p_plw = p_plan_sub.add_parser("bind-worktree", help="create or bind a Plan worktree")
    p_plw.add_argument("plan_id", help="Plan ID")
    p_plw.add_argument("path", nargs="?", default="", help="existing or custom worktree path")
    p_plw.add_argument(
        "--create", action="store_true",
        help="create or reuse the Plan's persistent worktree and branch",
    )
    p_plw.set_defaults(func=_cmd_plan_bind_worktree)
    p_plh = p_plan_sub.add_parser("hold", help="leave a completed Plan open without repeated merge prompts")
    p_plh.add_argument("plan_id", help="Plan ID")
    p_plh.set_defaults(func=_cmd_plan_hold)
    p_plcl = p_plan_sub.add_parser("close", help="close a plan")
    p_plcl.add_argument("plan_id", help="plan ID")
    p_plcl.add_argument("--summary", default="", help="closure summary")
    p_plcl.set_defaults(func=_cmd_plan_close)
    p_plca = p_plan_sub.add_parser("cancel", help="cancel a plan")
    p_plca.add_argument("plan_id", help="plan ID")
    p_plca.add_argument("--reason", default="", help="why this plan is cancelled")
    p_plca.set_defaults(func=_cmd_plan_cancel)
    p_plt = p_plan_sub.add_parser("link-task", help="link a task to a plan")
    p_plt.add_argument("plan_id", help="plan ID")
    p_plt.add_argument("task_id", help="task ID to link")
    p_plt.set_defaults(func=_cmd_plan_attach)
    p_plut = p_plan_sub.add_parser("unlink-task", help="unlink a task from a plan")
    p_plut.add_argument("plan_id", help="plan ID")
    p_plut.add_argument("task_id", help="task ID to unlink")
    p_plut.set_defaults(func=_cmd_plan_detach)
    p_pldep = p_plan_sub.add_parser("dep", help="manage Plan dependencies")
    p_pldep_sub = p_pldep.add_subparsers(dest="plan_dep_cmd", required=True)
    p_pldep_add = p_pldep_sub.add_parser("add", help="add a Plan dependency")
    p_pldep_add.add_argument("plan_id")
    p_pldep_add.add_argument("dependency_id")
    p_pldep_add.set_defaults(func=_cmd_plan_dep_add)
    p_pldep_remove = p_pldep_sub.add_parser("remove", help="remove a Plan dependency")
    p_pldep_remove.add_argument("plan_id")
    p_pldep_remove.add_argument("dependency_id")
    p_pldep_remove.add_argument("--reason", required=True)
    p_pldep_remove.set_defaults(func=_cmd_plan_dep_remove)
    p_pldep_show = p_pldep_sub.add_parser("show", help="show Plan dependency readiness")
    p_pldep_show.add_argument("plan_id")
    p_pldep_show.set_defaults(func=_cmd_plan_dep_show)
    p_plan.set_defaults(func=_cmd_plan_help)

    # ── task ──
    p_task = sub.add_parser("task", help="Task node CRUD and runtime")
    p_task_sub = p_task.add_subparsers(dest="task_cmd")
    p_tcr = p_task_sub.add_parser("create", help="create a task")
    p_tcr.add_argument("task_id", help="task ID, e.g. TASK-001")
    p_tcr.add_argument("--title", default="", help="task title")
    p_tcr.add_argument("--status", default="ready", choices=["ready"], help="initial status")
    p_tcr.add_argument("--goal", default="", dest="goal_id", help="GOAL-ID this task serves")
    p_tcr.add_argument("--plan", default="", dest="plan_id", help="PLAN-ID this task belongs to")
    p_tcr.add_argument("--milestone-id", default="", help="optional milestone ID")
    p_tcr.add_argument("--kind", default="", help="task kind (e.g. milestone_verification)")
    p_tcr.set_defaults(func=_cmd_task_plan)
    p_tsh = p_task_sub.add_parser("show", help="show one task")
    p_tsh.add_argument("task_id", nargs="?", default="", help="task ID (defaults to active)")
    p_tsh.set_defaults(func=_cmd_task_show)
    p_tproof = p_task_sub.add_parser("proof", help="show Git snapshots and current Task records")
    p_tproof.add_argument("task_id", nargs="?", default="", help="task ID (defaults to active)")
    p_tproof.set_defaults(func=_cmd_task_proof)
    p_task_sub.add_parser("list", help="list all tasks").set_defaults(func=_cmd_task_status)
    p_tca = p_task_sub.add_parser("cancel", help="cancel a non-active task")
    p_tca.add_argument("task_id", help="task ID")
    p_tca.add_argument("--reason", default="", help="why this task is cancelled")
    p_tca.set_defaults(func=_cmd_task_cancel)
    p_ta = p_task_sub.add_parser("activate", help="activate a task")
    p_ta.add_argument("task_id", help="task ID")
    p_ta.set_defaults(func=_cmd_task_activate)
    p_tcrit = p_task_sub.add_parser("critique", help="record one Planner activation critique pass")
    p_tcrit.add_argument("task_id", help="task ID")
    p_tcrit.set_defaults(func=_cmd_task_critique)
    p_tcal = p_task_sub.add_parser("calibrate", help="write Task.md Closure Calibration")
    p_tcal.add_argument("task_id", nargs="?", default="", help="task ID (defaults to active)")
    p_tcal.add_argument("--summary", required=True, help="freeform closure calibration from Planner")
    p_tcal.set_defaults(func=_cmd_task_calibrate)
    p_tc = p_task_sub.add_parser("close", help="close an active task")
    p_tc.add_argument("task_id", nargs="?", default="", help="Task ID (defaults to the current worktree)")
    p_tc.add_argument("--note", default="", help="closure note")
    p_tc.set_defaults(func=_cmd_task_close)
    p_tfc = p_task_sub.add_parser("force-close", help="human-only emergency close of an active task")
    p_tfc.add_argument("task_id", nargs="?", default="", help="Task ID (defaults to the current worktree)")
    p_tfc.add_argument("--reason", default="", help="why force-close is necessary")
    p_tfc.set_defaults(func=_cmd_task_force_close)
    p_ti = p_task_sub.add_parser("interrupt", help="human-only interrupt of an active task")
    p_ti.add_argument("task_id", nargs="?", default="", help="Task ID (defaults to the current worktree)")
    p_ti.add_argument("--reason", default="", help="why interruption is necessary")
    p_ti.set_defaults(func=_cmd_task_interrupt)
    p_task.set_defaults(func=_cmd_task_help)

    # ── record ──
    p_rec = sub.add_parser("record", help="Record implementation, testing, review")
    p_rec_sub = p_rec.add_subparsers(dest="record_cmd")
    p_re_ev = p_rec_sub.add_parser("implementation", help="record Executor handoff and Git snapshot")
    p_re_ev.add_argument("--summary", required=True, help="what changed and what the self-check showed")
    p_re_ev.add_argument("--command", default="", help="command or action observed")
    p_re_ev.add_argument("--task-id", default="", help="task id (defaults to active)")
    p_re_ev.add_argument("--exit-code", type=int, default=0, help="command exit code")
    p_re_ev.set_defaults(func=_cmd_record_implementation)
    p_re_te = p_rec_sub.add_parser("testing", help="record testing results")
    p_re_te.add_argument("--status", required=True, choices=["missing","partial","adequate","passed","failed"])
    p_re_te.add_argument("--command", action="append", default=[], dest="commands")
    p_re_te.add_argument("--verification-result", action="append", default=[], dest="verification_results",
                         help="structured command result: command:::expected:::observed:::matched|mismatched")
    p_re_te.add_argument("--summary", default="", help="testing summary")
    p_re_te.add_argument("--task-id", default="", help="Task ID (defaults to the current worktree)")
    p_re_te.set_defaults(func=_cmd_record_testing)
    p_re_rv = p_rec_sub.add_parser("review", help="record review results")
    p_re_rv.add_argument("--result", required=True, choices=["accepted","needs_fix","rejected"])
    p_re_rv.add_argument("--summary", default="", help="review summary")
    p_re_rv.add_argument("--blocker", action="append", default=[], dest="blockers", help="specific blocker reason")
    p_re_rv.add_argument("--adversarial-observations", action="append", default=[], dest="adversarial_observations", help="adversarial observations: severity:::kind:::message")
    p_re_rv.add_argument("--cleanup-status", default="", help="cleanup status")
    p_re_rv.add_argument("--structure-status", default="", help="structure status")
    p_re_rv.add_argument("--task-id", default="", help="Task ID (defaults to the current worktree)")
    p_re_rv.set_defaults(func=_cmd_record_review)
    p_re_disp = p_rec_sub.add_parser("disposition", help="record Planner decision on one reviewer observation")
    p_re_disp.add_argument("observation_id", help="observation ID, for example ADV-001")
    p_re_disp.add_argument("--decision", required=True, choices=["accepted", "deferred", "dismissed", "resolved"])
    p_re_disp.add_argument("--reason", required=True, help="short reason for the decision")
    p_re_disp.add_argument("--task-id", default="", help="Task ID (defaults to the current worktree)")
    p_re_disp.set_defaults(func=_cmd_record_disposition)
    p_rec.set_defaults(func=_cmd_record_help)

    # ── milestone ──
    p_ms = sub.add_parser("milestone", help="Milestone node and acceptance")
    p_ms_sub = p_ms.add_subparsers(dest="milestone_cmd")
    p_msc = p_ms_sub.add_parser("create", help="create a milestone")
    p_msc.add_argument("milestone_id", help="milestone ID, e.g. MS-001")
    p_msc.add_argument("--title", default="", help="milestone title")
    p_msc.add_argument("--goal", default="", dest="goal_id", help="GOAL-ID this milestone belongs to")
    p_msc.add_argument("--status", default="open", choices=["open"], help="initial status")
    p_msc.add_argument("--narrative", "-n", action="store_true", help="create narrative .md doc")
    p_msc.set_defaults(func=_cmd_milestone_create)
    p_mss = p_ms_sub.add_parser("show", help="show a milestone")
    p_mss.add_argument("milestone_id", help="milestone ID")
    p_mss.set_defaults(func=_cmd_milestone_show)
    p_ms_sub.add_parser("list", help="list milestones").set_defaults(func=_cmd_milestone_list)
    p_msca = p_ms_sub.add_parser("cancel", help="cancel a milestone")
    p_msca.add_argument("milestone_id", help="milestone ID")
    p_msca.add_argument("--reason", default="", help="why this milestone is cancelled")
    p_msca.set_defaults(func=_cmd_milestone_cancel)
    p_mslp = p_ms_sub.add_parser("link-plan", help="link a plan to a milestone")
    p_mslp.add_argument("milestone_id", help="milestone ID")
    p_mslp.add_argument("plan_id", help="plan ID to link")
    p_mslp.set_defaults(func=_cmd_milestone_link_plan)
    p_msup = p_ms_sub.add_parser("unlink-plan", help="unlink a plan from a milestone")
    p_msup.add_argument("milestone_id", help="milestone ID")
    p_msup.add_argument("plan_id", help="plan ID to unlink")
    p_msup.set_defaults(func=_cmd_milestone_unlink_plan)
    p_mslt = p_ms_sub.add_parser("link-task", help="link a task to a milestone")
    p_mslt.add_argument("milestone_id", help="milestone ID")
    p_mslt.add_argument("task_id", help="task ID to link")
    p_mslt.set_defaults(func=_cmd_milestone_link_task)
    p_msut = p_ms_sub.add_parser("unlink-task", help="unlink a task from a milestone")
    p_msut.add_argument("milestone_id", help="milestone ID")
    p_msut.add_argument("task_id", help="task ID to unlink")
    p_msut.set_defaults(func=_cmd_milestone_unlink_task)
    p_msi = p_ms_sub.add_parser("integration-test", help="record milestone integration test")
    p_msi.add_argument("milestone_id", help="milestone ID")
    p_msi.add_argument("--status", required=True, choices=["passed","failed"])
    p_msi.add_argument("--coverage-mode", choices=["end_to_end_flow","function_reverse_trace"], default="")
    p_msi.add_argument("--main-path-status", choices=["passed","failed","not_run"], default="")
    p_msi.add_argument("--command", action="append", default=[], dest="command")
    p_msi.add_argument("--summary", default="", help="test summary")
    p_msi.set_defaults(func=_cmd_milestone_integration_test)
    p_msr = p_ms_sub.add_parser("arch-review", help="record milestone architecture review")
    p_msr.add_argument("milestone_id", help="milestone ID")
    p_msr.add_argument("--status", required=True, choices=["intact","issues_found"])
    p_msr.add_argument("--notes", default="", help="review notes")
    p_msr.add_argument("--interface", action="append", default=[], help="intact interface: FROM_GOAL→TO_GOAL")
    p_msr.add_argument("--issue", action="append", default=[], help="issue: SEVERITY:::DESCRIPTION")
    p_msr.add_argument("--resolution", default="", help="how earlier architecture issues were resolved")
    p_msr.set_defaults(func=_cmd_milestone_arch_review)
    p_msa = p_ms_sub.add_parser("assess", help="record milestone assessment")
    p_msa.add_argument("milestone_id", help="milestone ID")
    p_msa.add_argument("--verdict", required=True, choices=["PASS","PASS_WITH_RISK","REVISE","REJECT"])
    p_msa.add_argument("--summary", required=True, help="assessment summary")
    p_msa.set_defaults(func=_cmd_milestone_assess)
    p_msconfirm = p_ms_sub.add_parser("confirm", help="accept milestone after human review")
    p_msconfirm.add_argument("milestone_id", help="milestone ID")
    p_msconfirm.add_argument("--summary", required=True, help="what the user accepted")
    p_msconfirm.set_defaults(func=_cmd_milestone_confirm)
    p_msl = p_ms_sub.add_parser("close", help="close milestone after acceptance")
    p_msl.add_argument("milestone_id", help="milestone ID")
    p_msl.set_defaults(func=_cmd_milestone_close)
    p_ms.set_defaults(func=_cmd_milestone_help)

    return parser
