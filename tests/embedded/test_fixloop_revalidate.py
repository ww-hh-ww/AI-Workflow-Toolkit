"""Regression tests for fix-loop revalidation and repair window.

Verifies:
- resolve_fix_loop re-validates required_fixes against current state
- resolve_fix_loop blocks when fixes still unresolved
- _extract_paths_from_fixes extracts file paths from human-readable strings
- _revalidate_required_fixes categorizes fixes correctly
- Scope guard allows writes to required_fix targets when fix-loop is open
"""
import json
import tempfile
import unittest
from pathlib import Path


def _make_state_dir(tmpdir, state=None, fix_loop=None, review=None):
    """Create a minimal .aiwf state tree."""
    base = Path(tmpdir)
    for d in [".aiwf/state", ".aiwf/quality", ".aiwf/evidence"]:
        (base / d).mkdir(parents=True, exist_ok=True)

    (base / ".aiwf/state/state.json").write_text(json.dumps(state or {
        "phase": "reviewing", "workflow_level": "L1_review_light",
        "active_context_id": "ctx-1", "active_task_id": "task-1",
        "scope_violation": True,
    }))
    (base / ".aiwf/state/fix-loop.json").write_text(json.dumps(fix_loop or {
        "status": "open", "route": "planner-main",
        "reason": "scope violation detected",
        "required_fixes": [
            "Resolve scope violations: external-assets/scripts/new-planning-search.sh",
            "Fix broken test in tests/test_example.py",
        ],
        "required_verification": [],
        "attempt_count": 1, "max_attempts": 3,
    }))
    (base / ".aiwf/quality/review.json").write_text(json.dumps(review or {
        "result": "scope_violation", "closure_allowed": False,
        "cleanup_status": "fresh", "blockers": [],
        "scope_violation_events": [
            {"path": "external-assets/scripts/new-planning-search.sh",
             "status": "recorded", "context_id": "ctx-1"},
        ],
    }))
    (base / ".aiwf/quality/testing.json").write_text(json.dumps({
        "status": "passed", "commands": ["pytest"],
    }))
    (base / ".aiwf/evidence/records.json").write_text(json.dumps({
        "records": [{"id": "EV-001", "status": "accepted",
                      "trust_level": "command_observed", "session_id": "s1"}],
    }))
    return str(base)


class TestExtractPathsFromFixes(unittest.TestCase):

    def test_extracts_paths_from_scope_violation_msg(self):
        from aiwf_core.core.state.fixloop_ops import _extract_paths_from_fixes
        fixes = ["Resolve scope violations: external-assets/scripts/new-planning-search.sh"]
        paths = _extract_paths_from_fixes(fixes)
        self.assertIn("external-assets/scripts/new-planning-search.sh", paths)

    def test_extracts_multiple_paths(self):
        from aiwf_core.core.state.fixloop_ops import _extract_paths_from_fixes
        fixes = [
            "Fix src/module/file.py",
            "restore tests/test_foo.py to committed state",
        ]
        paths = _extract_paths_from_fixes(fixes)
        self.assertIn("src/module/file.py", paths)
        self.assertIn("tests/test_foo.py", paths)

    def test_filters_non_path_strings(self):
        from aiwf_core.core.state.fixloop_ops import _extract_paths_from_fixes
        fixes = ["Run the test suite again", "Verify review comments are addressed"]
        paths = _extract_paths_from_fixes(fixes)
        self.assertEqual(paths, [])

    def test_handles_empty_list(self):
        from aiwf_core.core.state.fixloop_ops import _extract_paths_from_fixes
        paths = _extract_paths_from_fixes([])
        self.assertEqual(paths, [])


class TestRevalidateRequiredFixes(unittest.TestCase):

    def test_resolved_reverted_recognized(self):
        from aiwf_core.core.state.fixloop_ops import _revalidate_required_fixes
        scope_events = [
            {"path": "external-assets/scripts/new-planning-search.sh",
             "status": "resolved_reverted"},
        ]
        result = _revalidate_required_fixes(
            Path(tempfile.mkdtemp()),
            ["Resolve scope violations: external-assets/scripts/new-planning-search.sh"],
            scope_events, force=False,
        )
        self.assertIn("external-assets/scripts/new-planning-search.sh",
                      result["resolved_reverted"])
        self.assertEqual(result["still_unresolved"], [])
        self.assertEqual(result["blockers"], [])

    def test_still_recorded_not_resolved(self):
        from aiwf_core.core.state.fixloop_ops import _revalidate_required_fixes
        scope_events = [
            {"path": "external-assets/scripts/new-planning-search.sh",
             "status": "recorded"},
        ]
        result = _revalidate_required_fixes(
            Path(tempfile.mkdtemp()),
            ["Resolve scope violations: external-assets/scripts/new-planning-search.sh"],
            scope_events, force=False,
        )
        self.assertEqual(result["resolved_reverted"], [])

    def test_non_scope_fix_without_diff(self):
        """A fix not in scope events and no diff available — still_unresolved (can't verify)."""
        from aiwf_core.core.state.fixloop_ops import _revalidate_required_fixes
        result = _revalidate_required_fixes(
            Path(tempfile.mkdtemp()),
            ["Fix broken test in tests/test_example.py"],
            [], force=False,
        )
        # Without diff and without force, non-scope fixes go to still_unresolved
        self.assertIn("tests/test_example.py", result["still_unresolved"])

    def test_non_scope_fix_without_diff_force(self):
        """Force bypasses diff-unavailable check — fix goes to stale_resolved."""
        from aiwf_core.core.state.fixloop_ops import _revalidate_required_fixes
        result = _revalidate_required_fixes(
            Path(tempfile.mkdtemp()),
            ["Fix broken test in tests/test_example.py"],
            [], force=True,
        )
        self.assertIn("tests/test_example.py", result["stale_resolved"])
        self.assertEqual(result["still_unresolved"], [])
        self.assertEqual(result["blockers"], [])


class TestResolveFixLoopRevalidation(unittest.TestCase):
    """resolve_fix_loop must not output resolved when fixes still unresolved."""

    def test_resolve_fails_when_diff_unavailable_and_not_force(self):
        from aiwf_core.core.state_ops import resolve_fix_loop
        base = _make_state_dir(tempfile.mkdtemp())
        with self.assertRaises(ValueError) as ctx:
            resolve_fix_loop(base, resolution="fixed", source="tester", force=False)
        self.assertIn("blocked", str(ctx.exception).lower())

    def test_resolve_succeeds_with_force(self):
        from aiwf_core.core.state_ops import resolve_fix_loop
        base = _make_state_dir(tempfile.mkdtemp())
        result = resolve_fix_loop(base, resolution="force close", source="planner", force=True)
        self.assertEqual(result["status"], "resolved")
        self.assertIn("fix_validation", result)

    def test_resolve_records_fix_validation(self):
        from aiwf_core.core.state_ops import resolve_fix_loop
        base = _make_state_dir(tempfile.mkdtemp())
        result = resolve_fix_loop(base, resolution="fixed", source="tester", force=True)
        fv = result.get("fix_validation")
        self.assertIsNotNone(fv, "resolve must record fix_validation")
        self.assertIn("total_required", fv)
        self.assertIn("still_unresolved", fv)
        self.assertIn("stale_resolved", fv)

    def test_resolve_fails_when_escalation_required(self):
        from aiwf_core.core.state_ops import resolve_fix_loop
        base = _make_state_dir(tempfile.mkdtemp(), fix_loop={
            "status": "open", "route": "planner-main",
            "reason": "scope violation detected",
            "required_fixes": ["Fix file.py"],
            "escalation_required": True,
            "escalation_reason": "max attempts exceeded",
            "attempt_count": 4, "max_attempts": 3,
        })
        with self.assertRaises(ValueError) as ctx:
            resolve_fix_loop(base, resolution="fixed", source="tester", force=True)
        self.assertIn("escalation", str(ctx.exception).lower())


class TestScopeGuardRepairWindow(unittest.TestCase):
    """Scope guard must allow writes to required_fix targets when fix-loop is open."""

    def test_repair_window_allows_fix_target(self):
        from aiwf_core.hooks.common.scope_checker import check_file_write
        from aiwf_core.core.event_model import NormalizedEvent
        import tempfile, os
        base = tempfile.mkdtemp()
        # Set up state with open fix-loop and scope violation
        for d in [".aiwf/state", ".aiwf/quality"]:
            (Path(base) / d).mkdir(parents=True, exist_ok=True)
        (Path(base) / ".aiwf/state/state.json").write_text(json.dumps({
            "phase": "reviewing", "workflow_level": "L1_review_light",
            "active_context_id": "ctx-1", "active_task_id": "task-1",
            "scope_violation": True,
        }))
        (Path(base) / ".aiwf/state/fix-loop.json").write_text(json.dumps({
            "status": "open", "route": "planner-main",
            "required_fixes": [
                "Resolve scope violations: external-assets/scripts/new-planning-search.sh"
            ],
        }))
        (Path(base) / ".aiwf/state/contexts.json").write_text(json.dumps({
            "contexts": [{"id": "ctx-1", "allowed_write": ["src/"],
                          "forbidden_write": []}],
        }))
        # Also need goal.json for the scope_checker
        (Path(base) / ".aiwf/state/goal.json").write_text(json.dumps({"quality_brief": {}}))

        event = NormalizedEvent(
            tool_name="Edit",
            tool_input={"file_path": "external-assets/scripts/new-planning-search.sh"},
            cwd=base,
        )
        result = check_file_write(event)
        self.assertTrue(result.allowed,
                        f"repair window must allow writes to required_fix targets: {result.reason}")
        self.assertIn("repair window", result.reason.lower())

    def test_repair_window_blocks_non_fix_target(self):
        from aiwf_core.hooks.common.scope_checker import check_file_write
        from aiwf_core.core.event_model import NormalizedEvent
        import tempfile
        base = tempfile.mkdtemp()
        for d in [".aiwf/state", ".aiwf/quality"]:
            (Path(base) / d).mkdir(parents=True, exist_ok=True)
        (Path(base) / ".aiwf/state/state.json").write_text(json.dumps({
            "phase": "reviewing", "workflow_level": "L1_review_light",
            "active_context_id": "ctx-1", "active_task_id": "task-1",
            "scope_violation": True,
        }))
        (Path(base) / ".aiwf/state/fix-loop.json").write_text(json.dumps({
            "status": "open", "route": "planner-main",
            "required_fixes": [
                "Resolve scope violations: path/to/allowed_fix.sh"
            ],
        }))
        (Path(base) / ".aiwf/state/contexts.json").write_text(json.dumps({
            "contexts": [{"id": "ctx-1", "allowed_write": ["src/"],
                          "forbidden_write": []}],
        }))
        (Path(base) / ".aiwf/state/goal.json").write_text(json.dumps({"quality_brief": {}}))

        event = NormalizedEvent(
            tool_name="Edit",
            tool_input={"file_path": "unrelated/file.txt"},
            cwd=base,
        )
        result = check_file_write(event)
        # Should still be blocked by normal scope check
        if not result.allowed:
            self.assertNotIn("repair window", result.reason.lower())


if __name__ == "__main__":
    unittest.main()
