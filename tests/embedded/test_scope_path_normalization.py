"""Scope path normalization: absolute Claude paths, governance files, forbidden_write."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 10

def _install(cwd):
    env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
    subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                   capture_output=True, text=True, cwd=str(cwd), env=env, timeout=20)

def _scope_check(cwd, tool_name, file_path, allowed_write=None):
    """Run scope check hook with given config. Returns (exit_code, stdout_dict_or_empty)."""
    from aiwf_core.core.state_schema import MVP_STATE_FILES
    for fn, dfn in MVP_STATE_FILES.items():
        p = cwd / ".aiwf" / fn; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(dfn(), indent=2) + "\n")

    if allowed_write is not None:
        s = json.loads((cwd / ".aiwf" / "state" / "state.json").read_text())
        s["active_context_id"] = "CTX-001"
        (cwd / ".aiwf" / "state" / "state.json").write_text(json.dumps(s, indent=2))
        (cwd / ".aiwf" / "state" / "state.json").write_text(json.dumps(
            {"contexts": [{"id": "CTX-001", "allowed_write": allowed_write,
             "forbidden_write": []}]}, indent=2))

    inp = json.dumps({"session_id": "t", "cwd": str(cwd),
                      "tool_name": tool_name, "tool_input": {"file_path": file_path}})
    env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
    r = subprocess.run([sys.executable, str(cwd / "scripts" / "aiwf_scope_check.py")],
                       input=inp, capture_output=True, text=True, cwd=str(cwd),
                       env=env, timeout=TIMEOUT)
    try:
        out = json.loads(r.stdout.strip()) if r.stdout.strip() else {}
    except json.JSONDecodeError:
        out = {}
    return r.returncode, out


class TestScopePathNormalization(unittest.TestCase):
    """Absolute Claude paths are normalized before matching."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awsp_"))
        _install(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_relative_path_in_scope_allowed(self):
        """Relative path inside allowed_write passes."""
        _, out = _scope_check(self.tmp, "Write", "src/calculator.js",
                             allowed_write=["src/calculator.js"])
        self.assertNotIn("permissionDecision", out)

    def test_absolute_path_in_scope_allowed(self):
        """Absolute Claude path inside allowed_write passes after normalization."""
        abs_path = str(self.tmp / "src" / "calculator.js")
        _, out = _scope_check(self.tmp, "Write", abs_path,
                             allowed_write=["src/calculator.js"])
        self.assertNotIn("permissionDecision", out,
                        f"Absolute path {abs_path} should be normalized to relative and allowed")

    def test_absolute_path_outside_scope_denied(self):
        """Absolute path outside allowed_write is denied."""
        abs_path = str(self.tmp / "danger" / "hack.py")
        _, out = _scope_check(self.tmp, "Write", abs_path,
                             allowed_write=["src/calculator.js"])
        self.assertEqual(out.get("hookSpecificOutput", {}).get("permissionDecision"), "deny")

    def test_relative_path_outside_scope_denied(self):
        """Relative path outside allowed_write is denied."""
        _, out = _scope_check(self.tmp, "Write", "danger/hack.py",
                             allowed_write=["src/calculator.js"])
        self.assertEqual(out.get("hookSpecificOutput", {}).get("permissionDecision"), "deny")

    def test_dot_slash_prefix_normalized(self):
        """'./src/calculator.js' is treated same as 'src/calculator.js'."""
        _, out = _scope_check(self.tmp, "Write", "./src/calculator.js",
                             allowed_write=["src/calculator.js"])
        self.assertNotIn("permissionDecision", out)

    def test_governance_markdown_is_writable(self):
        for path in [
            ".aiwf/mission.md", ".aiwf/goals/GOAL-001.md",
            ".aiwf/plans/PLAN-001.md", ".aiwf/tasks/TASK-002.md",
            ".aiwf/milestones/MS-001.md", ".aiwf/memory/project-facts.md",
        ]:
            _, out = _scope_check(self.tmp, "Write", path,
                                 allowed_write=["src/calculator.js"])
            self.assertNotIn("permissionDecision", out,
                            f"Governance Markdown {path} must be writable")

    def test_direct_edit_to_core_mechanical_truth_denied(self):
        """Models cannot bypass state operations by directly editing core truth."""
        abs_path = str(self.tmp / ".aiwf" / "state" / "state.json")
        _, out = _scope_check(self.tmp, "Write", abs_path,
                             allowed_write=["src/calculator.js"])
        self.assertEqual(out.get("hookSpecificOutput", {}).get("permissionDecision"), "deny")

    def test_mission_md_governance_write_allowed_without_active_task(self):
        """mission.md is a Planner governance MD, not a project file."""
        _, out = _scope_check(self.tmp, "Write", ".aiwf/mission.md",
                             allowed_write=["src/calculator.js"])
        self.assertNotIn("permissionDecision", out)

    def test_control_root_mission_write_allowed_from_plan_worktree(self):
        """A Plan worktree may update the shared Planner governance surface."""
        primary = Path(tempfile.mkdtemp(prefix="awsp_primary_"))
        worktree = Path(tempfile.mkdtemp(prefix="awsp_worktree_"))
        shutil.rmtree(worktree)
        try:
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=primary, check=True)
            subprocess.run(["git", "config", "user.name", "AIWF Test"], cwd=primary, check=True)
            subprocess.run(["git", "config", "user.email", "aiwf@example.com"], cwd=primary, check=True)
            subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "init"], cwd=primary, check=True)
            _install(primary)
            subprocess.run(
                ["git", "worktree", "add", "-q", "-b", "plan-test", str(worktree)],
                cwd=primary,
                check=True,
            )

            from aiwf_core.core.event_model import NormalizedEvent
            from aiwf_core.hooks.common.scope_checker import check_file_write

            mission = check_file_write(NormalizedEvent(
                cwd=str(worktree),
                tool_name="Write",
                tool_input={"file_path": str(primary / ".aiwf" / "mission.md")},
            ))
            self.assertTrue(mission.allowed, mission.reason)

            state = check_file_write(NormalizedEvent(
                cwd=str(worktree),
                tool_name="Write",
                tool_input={"file_path": str(primary / ".aiwf" / "state" / "state.json")},
            ))
            self.assertFalse(state.allowed)
            self.assertIn("must be changed through aiwf CLI", state.reason)
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree)],
                cwd=primary,
                capture_output=True,
                text=True,
            )
            shutil.rmtree(primary, ignore_errors=True)
            shutil.rmtree(worktree, ignore_errors=True)

    def test_direct_edits_to_machine_truth_denied(self):
        for rel in [
            ".aiwf/state/state.json",
            ".aiwf/state/goals.json",
            ".aiwf/state/tasks.json",
            ".aiwf/state/fix-loop.json",
            ".aiwf/records/implementation.json",
            ".aiwf/records/testing.json",
            ".aiwf/records/review.json",
        ]:
            _, out = _scope_check(self.tmp, "Edit", rel, allowed_write=["src/calculator.js"])
            self.assertEqual(out.get("hookSpecificOutput", {}).get("permissionDecision"), "deny")

    def test_project_file_still_denied_when_out_of_scope(self):
        """Governance file allowlist does not leak to non-governance files."""
        _, out = _scope_check(self.tmp, "Write", "danger/x.py",
                             allowed_write=["src/calculator.js"])
        self.assertEqual(out.get("hookSpecificOutput", {}).get("permissionDecision"), "deny")

    def test_no_active_context_denies_project_writes(self):
        """Without active_context_id, project writes are denied until context dispatch."""
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for fn, dfn in MVP_STATE_FILES.items():
            p = self.tmp / ".aiwf" / fn; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(dfn(), indent=2) + "\n")
        inp = json.dumps({"session_id": "t", "cwd": str(self.tmp),
                         "tool_name": "Write", "tool_input": {"file_path": "anything.py"}})
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_scope_check.py")],
                          input=inp, capture_output=True, text=True,
                          cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        self.assertEqual(r.returncode, 0)
        out = json.loads(r.stdout.strip())
        self.assertEqual(out.get("hookSpecificOutput", {}).get("permissionDecision"), "deny")


class TestCoreScopePolicyNormalization(unittest.TestCase):
    """Direct core logic tests for _normalize_path and _matches."""

    def test_normalize_relative_unchanged(self):
        from aiwf_core.core.scope_policy import _normalize_path
        self.assertEqual(_normalize_path("src/calc.js", "/project"), "src/calc.js")

    def test_normalize_absolute_to_relative(self):
        from aiwf_core.core.scope_policy import _normalize_path
        self.assertEqual(
            _normalize_path("/project/src/calc.js", "/project"), "src/calc.js")

    def test_normalize_dot_slash_stripped(self):
        from aiwf_core.core.scope_policy import _normalize_path
        self.assertEqual(_normalize_path("./src/calc.js", "/project"), "src/calc.js")

    def test_normalize_project_root_with_spaces(self):
        from aiwf_core.core.scope_policy import _normalize_path
        result = _normalize_path("/Users/test/my project/src/x.py", "/Users/test/my project")
        self.assertEqual(result, "src/x.py")

    def test_is_governance_file(self):
        from aiwf_core.core.scope_policy import _is_governance_file
        self.assertTrue(_is_governance_file(".aiwf/runtime/internal/baseline.json"))
        self.assertTrue(_is_governance_file(".aiwf/mission.md"))
        self.assertTrue(_is_governance_file(".aiwf/goals/GOAL-001.md"))
        self.assertFalse(_is_governance_file(".aiwf/state/state.json"))
        self.assertFalse(_is_governance_file(".aiwf/records/review.json"))
        self.assertFalse(_is_governance_file("src/main.py"))

    def test_matches_exact(self):
        from aiwf_core.core.scope_policy import _matches
        self.assertTrue(_matches("src/calc.js", "src/calc.js"))

    def test_matches_not_child_of_pattern(self):
        from aiwf_core.core.scope_policy import _matches
        # "src/calc" should NOT match "src/calculator.js" (it's not a prefix)
        self.assertFalse(_matches("src/calculator.js", "src/calc"))


if __name__ == "__main__":
    unittest.main()
