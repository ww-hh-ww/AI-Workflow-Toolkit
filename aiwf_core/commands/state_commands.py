"""CLI command handlers for AIWF embedded mainline."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..constants import VERSION

def _cmd_record_quality_brief(args: argparse.Namespace) -> None:
    """aiwf state record-quality-brief — write task-specific quality brief to goal.json."""
    from ..core.state_ops import record_quality_brief
    # Validate surface types
    validated_surfaces = []
    if args.surface_types:
        from ..core.quality_surfaces import VALID_SURFACE_TYPES
        for st in args.surface_types:
            if st not in VALID_SURFACE_TYPES:
                print(f"Error: unknown surface type: {st}", file=sys.stderr)
                print(f"  Valid surfaces: {', '.join(sorted(VALID_SURFACE_TYPES))}", file=sys.stderr)
                raise SystemExit(1)
            validated_surfaces.append(st)
    try:
        goal = record_quality_brief(
        str(Path.cwd()),
        acceptance_criteria=args.acceptance or None,
        test_focus=args.test_focus or None,
        review_focus=args.review_focus or None,
        non_goals=args.non_goals or None,
        escalation_triggers=args.escalation_triggers or None,
        target_structure=args.target_structure or "",
        module_boundaries=args.module_boundaries or None,
        allowed_files=args.allowed_files or None,
        protected_files=args.protected_files or None,
        allowed_new_files=args.allowed_new_files or None,
        public_api_changes=args.public_api_changes or None,
        integration_points=args.integration_points or None,
        architecture_invariants=args.architecture_invariants or None,
        forbidden_restructures=args.forbidden_restructures or None,
        architecture_risks=args.architecture_risks or None,
        migration_source_of_truth=args.migration_source_of_truth or "",
        legacy_paths=args.legacy_paths or None,
        legacy_terms=args.legacy_terms or None,
        default_entrypoints=args.default_entrypoints or None,
        validators=args.validators or None,
        sample_outputs=args.sample_outputs or None,
        surface_types=validated_surfaces or None,
        user_visible_outcome=args.user_visible_outcome or "",
        evaluation_acceptance_criteria=args.acceptance_criteria or None,
        evaluation_non_goals=args.non_goals or None,
        test_obligations=args.test_obligations or None,
        review_obligations=args.review_obligations or None,
        known_risks=args.known_risks or None,
        closure_question=args.closure_question or "",
        system_integration_obligations=args.system_integration_obligations or None)
    except ValueError as e:
        print(f"Quality brief update blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    brief = goal.get("quality_brief", {})
    print("Quality brief recorded:")
    if brief.get("acceptance_criteria"):
        print(f"  Acceptance: {len(brief['acceptance_criteria'])} criteria")
    if brief.get("test_focus"):
        print(f"  Test focus: {len(brief['test_focus'])} items")
    if brief.get("review_focus"):
        print(f"  Review focus: {len(brief['review_focus'])} items")
    if brief.get("non_goals"):
        print(f"  Non-goals: {len(brief['non_goals'])} items")
    if brief.get("escalation_triggers"):
        print(f"  Escalation triggers: {len(brief['escalation_triggers'])} items")
    ab = brief.get("architecture_brief", {})
    if ab:
        ab_count = sum(1 for v in ab.values() if v and v != "" and v != [])
        if ab_count: print(f"  Architecture brief: {ab_count} field(s)")

def _cmd_start_context(args: argparse.Namespace) -> None:
    """aiwf state start-context — create/update context with dispatch fields."""
    from ..core.state_ops import start_context
    try:
        # Split comma-separated values: --allowed-write "a,b,c" → ["a","b","c"]
        def _split_csv(vals):
            if not vals: return None
            out = []
            for v in vals:
                for part in str(v).split(","):
                    part = part.strip()
                    if part:
                        out.append(part)
            return out or None

        ctxs = start_context(
            str(Path.cwd()), args.context_id, args.label or "",
            allowed_write=_split_csv(args.allowed_write),
            forbidden_write=_split_csv(args.forbidden_write),
            note=args.note or "",
            purpose=args.purpose or "",
            read_hints=_split_csv(args.read_hints),
            non_goals=_split_csv(args.non_goals),
            dependencies=_split_csv(args.dependencies),
            interface_contract=args.interface_contract or "",
            test_focus=_split_csv(args.test_focus),
            review_focus=_split_csv(args.review_focus),
            escalation_triggers=_split_csv(args.escalation_triggers))
    except ValueError as e:
        print(f"Context update blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    ctx = [c for c in ctxs["contexts"] if c["id"] == args.context_id][0]
    print(f"Context started:")
    print(f"  ID: {ctx['id']}")
    print(f"  Title: {ctx.get('title', '')}")
    print(f"  Allowed write: {len(ctx.get('allowed_write', []))} paths")
    print(f"  Forbidden write: {len(ctx.get('forbidden_write', []))} paths")
    has_dispatch = any(ctx.get(k) for k in ["purpose","test_focus","review_focus"])
    print(f"  Dispatch: {'present' if has_dispatch else 'not set'}")
    print(f"  Active context: {args.context_id}")

def _cmd_record_testing(args: argparse.Namespace) -> None:
    """aiwf state record-testing — write testing results."""
    from ..core.state_ops import record_testing
    import json as _json

    # Guard: L2/L3 must use independent tester session unless forced
    cwd = Path.cwd()
    state_path = cwd / ".aiwf" / "state" / "state.json"
    if state_path.exists():
        state = _json.loads(state_path.read_text(encoding="utf-8"))
        level = state.get("workflow_level", "")
        if level in ("L2_standard_team", "L3_full_power"):
            evidence_path = cwd / ".aiwf" / "artifacts" / "evidence" / "records.json"
            evidence = _json.loads(evidence_path.read_text(encoding="utf-8")) if evidence_path.exists() else {"records": []}
            records = evidence.get("records", []) or []

            executor_session = set()
            tester_session = set()
            for r in records:
                if not isinstance(r, dict):
                    continue
                role = (r.get("agent_type") or r.get("role") or "").lower()
                sid = r.get("session_id") or ""
                if "executor" in role and sid:
                    executor_session.add(sid)
                if "tester" in role and sid:
                    tester_session.add(sid)

            # Tester is independent when they have evidence from a session
            # the executor did NOT work in. If all tester sessions are also
            # executor sessions (or tester has no evidence), block.
            if tester_session.issubset(executor_session):
                # L2/L3: always block, --force is NOT honored. Must spawn subagent.
                if level in ("L2_standard_team", "L3_full_power"):
                    detail = ""
                    if tester_session:
                        detail = (
                            f"  Tester evidence ONLY from executor session(s): {sorted(tester_session)}.\n"
                            "  The Tester must run in a DIFFERENT session from the Executor.\n"
                        )
                    print(
                        f"Testing blocked: workflow level is {level}, which requires an independent Tester session.\n"
                        f"{detail}"
                        f"  Fix: Use Agent tool to spawn aiwf-tester subagent. Run tests\n"
                        f"  in the subagent session, then call aiwf state record-testing.\n"
                        f"  --force is NOT honored at L2/L3 — spawn the subagent.",
                        file=sys.stderr,
                    )
                    raise SystemExit(1)
                elif not args.force:
                    print(
                        f"Testing blocked: workflow level is {level}, which requires an independent Tester session.\n"
                        f"  Fix: Use Agent tool (subagent_type=aiwf-tester) to spawn tester.\n"
                        f"  Or use --force if L0 inline execution.",
                        file=sys.stderr,
                    )
                    raise SystemExit(1)

    testing = record_testing(str(Path.cwd()), args.context_id, args.status,
                   commands=args.commands or None,
                   evidence_ids=args.evidence_ids or None,
                   untested_risks=args.untested_risks or None,
                   coverage_summary=args.coverage_summary or "",
                   failure_summary=args.failure_summary or "",
                   failed_obligations=args.failed_obligations or None,
                   failed_commands=args.failed_commands or None,
                   suspected_route=args.suspected_route or "",
                   required_verification=args.required_verification or None,
                   acceptance_coverage=args.acceptance_coverage or None,
                   system_coverage=args.system_coverage or None,
                   validation_layers=args.validation_layers or None,
                   full_suite_status=args.full_suite_status or "",
                   full_suite_reason=args.full_suite_reason or "",
                   real_usage_status=args.real_usage_status or "",
                   real_usage_reason=args.real_usage_reason or "",
                   inferred_surfaces=args.inferred_surfaces or None,
                   missing_surface_notes=args.missing_surface_notes or None,
                   cross_task_risks=args.cross_task_risks or None,
                   testing_debt=args.testing_debt or None,
                   repeated_change_hotspots=args.repeated_change_hotspots or None,
                   adversarial_mode=bool(getattr(args, 'adversarial_mode', False)),
                   delta_verification=getattr(args, 'delta_verification', '') or '',
                   reused_evidence_ids=getattr(args, 'reused_evidence_ids', None) or None,
                   invalidated_evidence_ids=getattr(args, 'invalidated_evidence_ids', None) or None,
                   supports_plan=getattr(args, 'supports_plan', '') or '',
                   supports_goal=getattr(args, 'supports_goal', '') or '')
    print(f"Testing recorded: status={args.status}")
    if testing.get("evidence_id"): print(f"  Evidence: {testing['evidence_id']} (tester)")
    if args.commands: print(f"  Commands: {len(args.commands)}")
    if args.untested_risks: print(f"  Untested risks: {len(args.untested_risks)}")
    if args.failure_summary: print(f"  Failure: {args.failure_summary[:120]}")
    if args.failed_obligations: print(f"  Failed obligations: {len(args.failed_obligations)}")
    if args.suspected_route: print(f"  Suspected route: {args.suspected_route}")
    if args.system_coverage: print(f"  System coverage: {len(args.system_coverage)} items")
    if args.validation_layers: print(f"  Validation layers: {', '.join(args.validation_layers)}")
    if args.full_suite_status: print(f"  Full suite: {args.full_suite_status}")
    if args.real_usage_status: print(f"  Real usage: {args.real_usage_status}")
    if getattr(args, 'supports_plan', ''): print(f"  Supports plan: {args.supports_plan}")
    if getattr(args, 'supports_goal', ''): print(f"  Supports goal: {args.supports_goal}")
    if args.inferred_surfaces: print(f"  Inferred surfaces: {', '.join(args.inferred_surfaces)}")
    if args.cross_task_risks: print(f"  Cross-task risks: {len(args.cross_task_risks)}")
    if args.testing_debt: print(f"  Testing debt: {len(args.testing_debt)}")
    delta = getattr(args, 'delta_verification', '') or ''
    if delta: print(f"  Delta verification: {delta[:120]}")
    reused = getattr(args, 'reused_evidence_ids', None) or []
    if reused: print(f"  Reused evidence: {len(reused)}")
    invalidated = getattr(args, 'invalidated_evidence_ids', None) or []
    if invalidated: print(f"  Invalidated evidence: {len(invalidated)}")


def _cmd_record_review(args: argparse.Namespace) -> None:
    """aiwf state record-review — write review results and reviewer evidence."""
    from ..core.state_ops import record_review
    import json as _json

    # Guard: L2/L3 must use independent reviewer session unless forced
    cwd = Path.cwd()
    state_path = cwd / ".aiwf" / "state" / "state.json"
    level = "L1_review_light"
    if state_path.exists():
        state = _json.loads(state_path.read_text(encoding="utf-8"))
        level = state.get("workflow_level", level)
        if level in ("L2_standard_team", "L3_full_power"):
            evidence_path = cwd / ".aiwf" / "artifacts" / "evidence" / "records.json"
            evidence = _json.loads(evidence_path.read_text(encoding="utf-8")) if evidence_path.exists() else {"records": []}
            records = evidence.get("records", []) or []

            executor_session = set()
            reviewer_session = set()
            for r in records:
                if not isinstance(r, dict):
                    continue
                role = (r.get("agent_type") or r.get("role") or "").lower()
                sid = r.get("session_id") or ""
                if "executor" in role and sid:
                    executor_session.add(sid)
                if "reviewer" in role and sid:
                    reviewer_session.add(sid)

            if reviewer_session.issubset(executor_session):
                # L2/L3: always block, --force is NOT honored. Must spawn subagent.
                if level in ("L2_standard_team", "L3_full_power"):
                    detail = ""
                    if reviewer_session:
                        detail = (
                            f"  Reviewer evidence ONLY from executor session(s): {sorted(reviewer_session)}.\n"
                            "  The Reviewer must run in a DIFFERENT session from the Executor.\n"
                        )
                    print(
                        f"Review blocked: workflow level is {level}, which requires an independent Reviewer session.\n"
                        f"{detail}"
                        f"  Fix: Use Agent tool to spawn aiwf-reviewer subagent. Run review\n"
                        f"  in the subagent session, then call aiwf state record-review.\n"
                        f"  Do NOT run record-review from the executor's session.",
                        file=sys.stderr,
                    )
                    raise SystemExit(1)
                elif not args.force:
                    print(
                        f"Review blocked: workflow level is {level}, which requires an independent Reviewer session.\n"
                        f"  Reviewer must produce evidence from a session different from the Executor.\n"
                        f"  Actions:\n"
                        f"    - Dispatch the aiwf-reviewer subagent from a new session and run record-review there, or\n"
                        f"    - If this is a legitimate Planner inline execution (L0 task), use --force to override.",
                        file=sys.stderr,
                    )
                    raise SystemExit(1)

    verdict = getattr(args, "verdict", "") or ""
    effective_accepted = (args.result == "accepted") or verdict in ("PASS", "PASS_WITH_RISK")

    # Guard: accepted review must confirm cleanup, docs, and root-cause checks.
    # L2/L3: --force is NOT honored — must fix the issues, not bypass them.
    quality_blockers = []
    if getattr(args, "cleanup_code", "") == "needs_work":
        quality_blockers.append("code cleanup needed (--cleanup-code needs_work)")
    if getattr(args, "docs_checked", "") == "no":
        quality_blockers.append("docs not updated for changed subsystems (--docs-checked no)")
    if getattr(args, "root_cause", "") == "symptom_only":
        quality_blockers.append("symptom patch, not root cause fix (--root-cause symptom_only)")
    if quality_blockers:
        if level in ("L2_standard_team", "L3_full_power"):
            print(
                "Review blocked: accepted/PASS verdict requires all quality checks to pass.\n"
                + "\n".join(f"  - {b}" for b in quality_blockers) + "\n"
                + "  Fix the issues and re-run record-review. --force is NOT honored at L2/L3.",
                file=sys.stderr,
            )
            raise SystemExit(1)
        elif not args.force:
            print(
                "Review blocked: accepted/PASS verdict requires all quality checks to pass.\n"
                + "\n".join(f"  - {b}" for b in quality_blockers) + "\n"
                + "  Fix the issues and re-run record-review, or use --force to override.",
                file=sys.stderr,
            )
            raise SystemExit(1)

    observations = []
    for idx, msg in enumerate(args.adversarial_observations or [], start=1):
        observations.append({
            "id": f"ADV-{idx:03d}",
            "severity": "warn",
            "kind": "review_observation",
            "message": msg,
            "suggestion": "",
            "disposition": "pending",
        })
    # V2 quality dimensions
    dims = {}
    dim_scores = getattr(args, "dimension_scores", None) or []
    dim_notes = getattr(args, "dimension_notes", None) or []
    from ..core.state_schema import (
        QUALITY_DIMENSIONS, VALID_DIMENSION_SCORES,
        REVIEW_BASIS, VALID_BASIS_STATUSES,
    )
    for entry in dim_scores:
        if "=" in entry:
            name, score = entry.split("=", 1)
            name = name.strip()
            score = score.strip()
            if name not in QUALITY_DIMENSIONS:
                print(f"Review record blocked: unknown quality dimension: {name}", file=sys.stderr)
                print(f"Valid dimensions: {', '.join(sorted(QUALITY_DIMENSIONS))}", file=sys.stderr)
                raise SystemExit(1)
            if score not in VALID_DIMENSION_SCORES or score == "unscored":
                print(f"Review record blocked: invalid score for {name}: {score}", file=sys.stderr)
                raise SystemExit(1)
            dims[name] = {"score": score, "note": ""}
    for entry in dim_notes:
        if "=" in entry:
            key, note = entry.split("=", 1)
            name = key.replace("_note", "").strip()
            if name not in QUALITY_DIMENSIONS:
                print(f"Review record blocked: unknown quality dimension note: {name}", file=sys.stderr)
                print(f"Valid dimensions: {', '.join(sorted(QUALITY_DIMENSIONS))}", file=sys.stderr)
                raise SystemExit(1)
            if name in dims:
                dims[name]["note"] = note.strip()

    # V2 review basis
    basis = {}
    basis_statuses = getattr(args, "basis_statuses", None) or []
    basis_notes = getattr(args, "basis_notes", None) or []
    for entry in basis_statuses:
        if "=" in entry:
            name, status = entry.split("=", 1)
            name = name.strip()
            status = status.strip()
            if name not in REVIEW_BASIS:
                print(f"Review record blocked: unknown review basis: {name}", file=sys.stderr)
                raise SystemExit(1)
            if status not in VALID_BASIS_STATUSES or status == "missing":
                print(f"Review record blocked: invalid basis status for {name}: {status}", file=sys.stderr)
                raise SystemExit(1)
            basis[name] = {"status": status, "note": ""}
    for entry in basis_notes:
        if "=" in entry:
            key, note = entry.split("=", 1)
            name = key.replace("_note", "").strip()
            if name not in REVIEW_BASIS:
                print(f"Review record blocked: unknown review basis note: {name}", file=sys.stderr)
                raise SystemExit(1)
            if name in basis:
                basis[name]["note"] = note.strip()

    if verdict in ("PASS", "PASS_WITH_RISK"):
        missing = [name for name in QUALITY_DIMENSIONS if name not in dims]
        if missing:
            print(
                "Review record blocked: PASS/PASS_WITH_RISK requires scored quality dimensions.\n"
                + "  Missing: " + ", ".join(missing),
                file=sys.stderr,
            )
            raise SystemExit(1)
        failed = [name for name, entry in dims.items() if entry.get("score") == "FAIL"]
        if failed:
            print(
                "Review record blocked: closure verdict cannot include FAIL dimensions.\n"
                + "  Failed: " + ", ".join(failed),
                file=sys.stderr,
            )
            raise SystemExit(1)
        risks = [name for name, entry in dims.items() if entry.get("score") == "RISK"]
        if verdict == "PASS" and risks:
            print(
                "Review record blocked: PASS cannot include RISK dimensions; use PASS_WITH_RISK or resolve them.\n"
                + "  Risk: " + ", ".join(risks),
                file=sys.stderr,
            )
            raise SystemExit(1)
        if verdict == "PASS_WITH_RISK":
            if not risks:
                print("Review record blocked: PASS_WITH_RISK requires at least one RISK dimension.", file=sys.stderr)
                raise SystemExit(1)
            missing_notes = [name for name in risks if not str(dims[name].get("note", "")).strip()]
            if missing_notes:
                print(
                    "Review record blocked: RISK dimensions require dimension notes.\n"
                    + "  Missing notes: " + ", ".join(missing_notes),
                    file=sys.stderr,
                )
                raise SystemExit(1)
        missing_basis = [name for name in REVIEW_BASIS if name not in basis]
        if missing_basis:
            print(
                "Review record blocked: PASS/PASS_WITH_RISK requires review basis coverage.\n"
                + "  Missing: " + ", ".join(missing_basis),
                file=sys.stderr,
            )
            raise SystemExit(1)
        basis_gaps = [name for name, entry in basis.items() if entry.get("status") == "gap"]
        if basis_gaps:
            print(
                "Review record blocked: closure verdict cannot include review basis gaps.\n"
                + "  Gaps: " + ", ".join(basis_gaps),
                file=sys.stderr,
            )
            raise SystemExit(1)
        basis_notes_missing = [
            name for name, entry in basis.items()
            if entry.get("status") == "not_applicable" and not str(entry.get("note", "")).strip()
        ]
        if basis_notes_missing:
            print(
                "Review record blocked: not_applicable review basis items require notes.\n"
                + "  Missing notes: " + ", ".join(basis_notes_missing),
                file=sys.stderr,
            )
            raise SystemExit(1)
    elif verdict in ("REVISE", "REJECT"):
        if not args.blockers:
            print(
                f"Review record blocked: {verdict} requires at least one --blocker explaining the quality failure.",
                file=sys.stderr,
            )
            raise SystemExit(1)
        missing_basis = [name for name in REVIEW_BASIS if name not in basis]
        if missing_basis:
            print(
                f"Review record blocked: {verdict} requires review basis coverage.\n"
                + "  Missing: " + ", ".join(missing_basis),
                file=sys.stderr,
            )
            raise SystemExit(1)
        basis_gaps = [name for name, entry in basis.items() if entry.get("status") == "gap"]
        if not basis_gaps:
            print(
                f"Review record blocked: {verdict} requires at least one review basis gap.",
                file=sys.stderr,
            )
            raise SystemExit(1)
        gap_notes_missing = [
            name for name in basis_gaps
            if not str(basis[name].get("note", "")).strip()
        ]
        if gap_notes_missing:
            print(
                "Review record blocked: gap review basis items require notes.\n"
                + "  Missing notes: " + ", ".join(gap_notes_missing),
                file=sys.stderr,
            )
            raise SystemExit(1)
        if dims:
            failed = [name for name, entry in dims.items() if entry.get("score") == "FAIL"]
            risks = [name for name, entry in dims.items() if entry.get("score") == "RISK"]
            if verdict == "REVISE" and not (failed or risks):
                print(
                    "Review record blocked: REVISE with quality dimensions requires at least one RISK or FAIL dimension.",
                    file=sys.stderr,
                )
                raise SystemExit(1)
            if verdict == "REJECT" and not failed:
                print(
                    "Review record blocked: REJECT with quality dimensions requires at least one FAIL dimension.",
                    file=sys.stderr,
                )
                raise SystemExit(1)

    try:
        review = record_review(
            str(Path.cwd()),
            result=getattr(args, "result", "") or "",
            verdict=getattr(args, "verdict", "") or "",
            quality_dimensions=dims or None,
            review_basis=basis or None,
            closure_allowed=bool(args.closure_allowed),
            accepted_evidence_ids=args.accepted_evidence_ids or None,
            rejected_evidence_ids=args.rejected_evidence_ids or None,
            blockers=args.blockers or None,
            adversarial_observations=observations or None,
            cleanup_status=args.cleanup_status or "",
            structure_status=args.structure_status or "",
            summary=args.summary or "",
            context_id=args.context_id or "",
            cleanup_code=getattr(args, "cleanup_code", "") or "",
            docs_checked=getattr(args, "docs_checked", "") or "",
            root_cause=getattr(args, "root_cause", "") or "",
        )
    except ValueError as e:
        print(f"Review record blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    verdict_str = f" verdict={review.get('verdict')}" if review.get('verdict') not in ('pending', '', None) else ""
    print(f"Review recorded: result={review.get('result')}{verdict_str}")
    print(f"  Closure allowed: {review.get('closure_allowed', False)}")
    if review.get("reviewer_evidence_id"):
        print(f"  Evidence: {review['reviewer_evidence_id']} (reviewer)")
    if review.get("accepted_evidence_ids"):
        print(f"  Accepted evidence: {len(review['accepted_evidence_ids'])}")
    if review.get("blockers"):
        print(f"  Blockers: {len(review['blockers'])}")


def _cmd_record_role_evidence(args: argparse.Namespace) -> None:
    """aiwf state record-role-evidence — explicit role evidence for hook gaps."""
    from ..core.state_ops import record_role_evidence
    try:
        ev = record_role_evidence(
            str(Path.cwd()),
            args.role,
            summary=args.summary or "",
            command=args.command or "",
            changed_files=args.changed_files or None,
            session_id=args.session_id or "",
            agent_id=args.agent_id or "",
            agent_type=args.agent_type or "",
            context_id=args.context_id or "",
            status=args.status,
            exit_code=args.exit_code,
            scan_git=bool(getattr(args, "scan_git", False)),
            supports_plan=getattr(args, "supports_plan", "") or "",
            supports_goal=getattr(args, "supports_goal", "") or "",
        )
    except ValueError as e:
        print(f"Role evidence blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Role evidence recorded: {ev['id']} ({ev['agent_type']})")
    if ev.get("working_tree_source") != "not_scanned":
        print(f"  Git scan: {ev.get('working_tree_source')} / {len(ev.get('working_tree_changed_files', []) or [])} files")

def _cmd_cleanup_check(args: argparse.Namespace) -> None:
    """aiwf cleanup check — run lifecycle cleanup check (read-only)."""
    from ..core.lifecycle_cleanup import check_lifecycle_cleanup
    result = check_lifecycle_cleanup(str(Path.cwd()))
    print("Cleanup check:")
    print(f"  Cleanup:   {result['cleanup_status']}")
    print(f"  Structure: {result['structure_status']}")
    print(f"  Blockers:  {len(result['blockers'])}")
    print(f"  Warnings:  {len(result['warnings'])}")
    print(f"  Stale items: {len(result['stale_items'])}")
    if result["blockers"]:
        print("  Blockers:")
        for b in result["blockers"][:10]: print(f"    - {b}")
    if result["warnings"]:
        print("  Warnings:")
        for w in result["warnings"][:15]: print(f"    - {w}")
    if result["stale_items"]:
        print("  Stale:")
        for s in result["stale_items"][:10]: print(f"    - {str(s)[:160]}")
    if result["suggested_actions"]:
        print("  Suggested:")
        for s in result["suggested_actions"][:5]: print(f"    - {s}")
    if not result["blockers"] and not result["warnings"]:
        print("  No blockers.")

def _cmd_mark_cleanup_fresh(args: argparse.Namespace) -> None:
    """aiwf state mark-cleanup-fresh — mark cleanup as fresh."""
    from ..core.state_ops import mark_cleanup_fresh
    mark_cleanup_fresh(str(Path.cwd()), resolved_notes=args.notes or None)
    print("Cleanup marked fresh: stale_items/blockers cleared")

def _cmd_mark_cleanup_stale(args: argparse.Namespace) -> None:
    """aiwf state mark-cleanup-stale — mark cleanup as stale."""
    from ..core.state_ops import mark_cleanup_stale
    mark_cleanup_stale(str(Path.cwd()), args.stale_items,
                       blockers=args.blockers or None, notes=args.notes or None)
    print(f"Cleanup marked stale: {len(args.stale_items)} stale items")

def _cmd_cancel_close(args: argparse.Namespace) -> None:
    """aiwf state cancel-close — reset close_attempt and unblock task activation."""
    from ..core.state_ops import cancel_close
    result = cancel_close(str(Path.cwd()))
    print(result["message"])


def _cmd_prepare_close(args: argparse.Namespace) -> None:
    """aiwf state prepare-close — run authoritative closure gate checks."""
    from ..core.state_ops import prepare_close
    result = prepare_close(str(Path.cwd()))
    passed = result.get('passed', False)
    print(f"Close prepared: passed={passed}")
    if result.get('blockers'):
        print(f"  Blockers ({len(result['blockers'])}):")
        for b in result['blockers'][:5]: print(f"    - {b}")
        print("  Resolve blockers before preparing closure")
        print("  prepare-close is authoritative; close attempt was not prepared.")
        raise SystemExit(1)
    else:
        # Post-hoc warnings: displayed even on pass — the model should review them
        post_hoc = result.get("post_hoc_warnings", []) or []
        if post_hoc:
            print(f"  Post-hoc warnings ({len(post_hoc)}):")
            for w in post_hoc[:5]:
                print(f"    ! {w}")
        summary = result.get("summary", "")
        if summary:
            print(summary)
        task_id = result.get("state", {}).get("active_task_id", "") or ""
        if task_id:
            print(f"\nClosure gate passed. Next: run aiwf task close {task_id}.")
        else:
            print("\nClosure complete. Stop hook will revalidate.")

def _cmd_set_goal_confirmed(args: argparse.Namespace) -> None:
    """aiwf state set-goal-confirmed — toggle goal confirmation."""
    import json
    goal_path = Path.cwd() / ".aiwf" / "state" / "goal.json"
    goal = json.loads(goal_path.read_text()) if goal_path.exists() else {}
    goal["confirmed"] = args.confirmed == "true"
    goal_path.write_text(json.dumps(goal, ensure_ascii=False, indent=2) + "\n")
    print(f"Goal confirmed: {goal['confirmed']}")


def _cmd_set_planner_inline(args: argparse.Namespace) -> None:
    """aiwf state set-planner-inline — record Planner inline execution decision.

    Only valid for L0_direct and L1_review_light. L2+ requires independent
    subagents — planner_inline_session does NOT waive session diversity.
    """
    import json
    from datetime import datetime, timezone
    state_path = Path.cwd() / ".aiwf" / "state" / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    level = state.get("workflow_level", "")
    if level in ("L2_standard_team", "L3_full_power"):
        print(
            f"Error: planner_inline_session is not valid for {level}.\n"
            "  L2/L3 requires independent subagents (executor, tester, reviewer)\n"
            "  dispatched via Agent tool. Inline execution is not allowed.\n"
            "  Use aiwf state set-workflow-mode to downgrade if appropriate.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    state["planner_inline_session"] = True
    state["planner_inline_reason"] = args.reason
    state["planner_inline_recorded_at"] = datetime.now(timezone.utc).isoformat()
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    print(f"Planner inline session recorded: {args.reason[:120]}")
    print(f"Valid at {level}: session diversity gate is not required at this level.")


def _cmd_disposition_adversarial(args: argparse.Namespace) -> None:
    """aiwf state disposition-adversarial — disposition a single adversarial observation."""
    from ..core.state_ops import disposition_adversarial_observation
    try:
        result = disposition_adversarial_observation(
            str(Path.cwd()),
            adv_id=args.adv_id,
            disposition=args.disposition,
            reason=args.reason or "",
            disposed_by=args.disposed_by,
        )
        print(f"Adversarial observation {args.adv_id}: {args.disposition}")
        if args.reason:
            print(f"  Reason: {args.reason[:160]}")
    except ValueError as e:
        print(f"Error: {e}")
        import sys; sys.exit(1)


def _cmd_record_meta_critique(args: argparse.Namespace) -> None:
    from ..core.state_ops import record_meta_critique
    record_meta_critique(str(Path.cwd()), args.summary, recorded_by="planner")
    print("Planner meta-critique recorded.")


def _cmd_set_workflow_mode(args: argparse.Namespace) -> None:
    """aiwf state set-workflow-mode — record uncertainty routing shape."""
    from ..core.workflow_patterns import set_workflow_mode
    try:
        state = set_workflow_mode(
            str(Path.cwd()),
            request_mode=args.request_mode,
            workflow_pattern=args.workflow_pattern or "",
            reason=args.reason or "",
            external_research_required=args.external_research_required,
        )
    except ValueError as e:
        print(f"Workflow mode update blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    print("Workflow mode recorded:")
    print(f"  Request mode: {state.get('request_mode')}")
    print(f"  Pattern:      {state.get('workflow_pattern')}")
    if state.get("pattern_reason"):
        print(f"  Reason:       {state['pattern_reason'][:160]}")
    print(f"  External research required: {state.get('external_research_required', False)}")


def _cmd_state_help(args: argparse.Namespace) -> None:
    """aiwf state — show available state subcommands."""
    print("AIWF State Operations")
    print()
    print("Available subcommands:")
    print("  aiwf state record-quality-policy   — record quality policy")
    print("  aiwf state record-quality-brief    — record task-specific quality brief")
    print("  aiwf state start-context           — create/update context with dispatch")
    print("  aiwf state record-testing          — record testing results")
    print("  aiwf state record-review           — record review results")
    print("  aiwf state record-role-evidence    — record explicit role evidence")
    print("  aiwf state mark-cleanup-fresh      — mark cleanup as fresh")
    print("  aiwf state mark-cleanup-stale      — mark cleanup as stale")
    print("  aiwf state record-meta-critique    — record structured Planner meta-critique")
    print("  aiwf state set-workflow-mode       — record uncertainty routing mode")
    print("  aiwf state prepare-close           — run authoritative closure gate checks")
    print("  aiwf state cancel-close            — reset close_attempt, recover from stuck closing state")

def _cmd_record_quality_policy(args: argparse.Namespace) -> None:
    """aiwf state record-quality-policy — write quality policy short keys to state.json."""
    from ..core.state_ops import record_quality_policy
    try:
        policy = record_quality_policy(
            str(Path.cwd()), args.task_type, args.workflow_level,
            risk_flags=args.risk_flags or [], routing_reason=args.reason)
    except ValueError as e:
        print(f"Quality policy update blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Quality policy recorded:")
    print(f"  Level: {policy['workflow_level']}")
    print(f"  Task type: {policy['task_type_label']}")
    print(f"  Test: {policy['test_template']}")
    print(f"  Review: {policy['review_template']}")
    print(f"  Exploration: {policy['exploration_budget']}")
    print(f"  Git: {policy['git_policy']}")
    if policy.get('level_escalations_applied'):
        for e in policy['level_escalations_applied']:
            print(f"  Escalation: {e}")
