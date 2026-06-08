"""Focused evidence contract — per-operation snapshot evidence with git repo."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 10


def _install(cwd):
    env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
    subprocess.run([sys.executable, "-m", "aiwf_core.cli",
                    "install", "claude", "--force"],
                   capture_output=True, text=True, cwd=str(cwd), env=env, timeout=20)


def _run_script(script_path, stdin_json, cwd):
    env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
    return subprocess.run([sys.executable, str(script_path)], input=stdin_json,
                          capture_output=True, text=True,
                          cwd=str(cwd), env=env, timeout=TIMEOUT)


def _snapshot(cwd, tool="Write", tool_input=None):
    if tool_input is None:
        tool_input = {"file_path": "dummy"}
    inp = json.dumps({"session_id": "t", "cwd": str(cwd),
                      "tool_name": tool, "tool_input": tool_input})
    _run_script(cwd / "scripts" / "aiwf_pre_snapshot.py", inp, cwd)


def _capture(cwd, tool="Write", tool_input=None):
    if tool_input is None:
        tool_input = {"file_path": "dummy"}
    inp = json.dumps({"session_id": "t", "cwd": str(cwd),
                      "tool_name": tool, "tool_input": tool_input})
    _run_script(cwd / "scripts" / "aiwf_capture_evidence.py", inp, cwd)


def _ev_records(cwd):
    return json.loads((cwd / ".aiwf" / "evidence" / "records.json").read_text())["records"]


class TestEvidence(unittest.TestCase):
    """Per-operation evidence: snapshot-based, not cumulative dirty-set delta."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awev_"))
        # Git repo for baseline support
        subprocess.run(["git", "init"], cwd=str(cls.tmp),
                       capture_output=True, timeout=10)
        subprocess.run(["git", "config", "user.email", "t@t.com"],
                       cwd=str(cls.tmp), capture_output=True, timeout=10)
        subprocess.run(["git", "config", "user.name", "T"],
                       cwd=str(cls.tmp), capture_output=True, timeout=10)
        (cls.tmp / "README.md").write_text("# Test")
        subprocess.run(["git", "add", "-A"], cwd=str(cls.tmp),
                       capture_output=True, timeout=10)
        subprocess.run(["git", "commit", "-m", "init"],
                       cwd=str(cls.tmp), capture_output=True, timeout=10)
        _install(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        # Reset evidence between tests
        (self.tmp / ".aiwf" / "evidence" / "records.json").write_text('{"records":[]}')
        # Reset state
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for fn, dfn in MVP_STATE_FILES.items():
            if fn == "evidence.json":
                continue
            p = self.tmp / ".aiwf" / fn; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(dfn(), indent=2) + "\n")

    def test_op1_new_file_detected(self):
        """Creating a new file is detected."""
        _snapshot(self.tmp)
        (self.tmp / "src").mkdir(exist_ok=True)
        (self.tmp / "src" / "a.py").write_text("def a(): pass")
        _capture(self.tmp)
        last = _ev_records(self.tmp)[-1]
        self.assertIn("src/a.py", last["changed_files"])
        self.assertEqual(last["changed_files_source"], "pre_post_snapshot")
        self.assertEqual(last["attribution"], "strong")

    def test_op2_same_file_modified_again_detected(self):
        """Modifying an already-dirty file again IS detected (hash changed)."""
        (self.tmp / "src").mkdir(exist_ok=True)
        (self.tmp / "src" / "a.py").write_text("v1")
        _snapshot(self.tmp)
        (self.tmp / "src" / "a.py").write_text("v2-modified")
        _capture(self.tmp)
        last = _ev_records(self.tmp)[-1]
        self.assertIn("src/a.py", last["changed_files"],
                     f"Modified file must be detected, got {last['changed_files']}")

    def test_op3_noop_empty_changed_files(self):
        """No-op operations produce empty changed_files."""
        (self.tmp / "src").mkdir(exist_ok=True)
        (self.tmp / "src" / "a.py").write_text("v1")
        _snapshot(self.tmp)
        # No file changes between snapshot and capture
        _capture(self.tmp)
        last = _ev_records(self.tmp)[-1]
        self.assertEqual(last["changed_files"], [],
                        f"No-op must be empty, got {last['changed_files']}")

    def test_op4_out_of_scope_detected(self):
        """Bash modifying out-of-scope file is detected."""
        s = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        s["active_context_id"] = "CTX-001"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(s, indent=2))
        (self.tmp / ".aiwf" / "state" / "contexts.json").write_text(json.dumps(
            {"contexts": [{"id": "CTX-001", "allowed_write": ["src/"]}]}, indent=2))

        _snapshot(self.tmp, "Bash", {"command": "echo hack"})
        (self.tmp / "danger").mkdir(exist_ok=True)
        (self.tmp / "danger" / "x.py").write_text("hacked")
        _capture(self.tmp, "Bash", {"command": "echo hack"})

        last = _ev_records(self.tmp)[-1]
        self.assertIn("danger/x.py", last["changed_files"])

        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        self.assertTrue(state["scope_violation"])

    def test_agent_tool_boundary_captures_subagent_file_changes(self):
        """Agent/Task tool calls get pre/post snapshots around subagent work."""
        _snapshot(self.tmp, "Agent", {"agent": "aiwf-executor"})
        (self.tmp / "src").mkdir(exist_ok=True)
        (self.tmp / "src" / "agent_created.py").write_text("value = 2\n")
        _capture(self.tmp, "Agent", {"agent": "aiwf-executor"})

        last = _ev_records(self.tmp)[-1]
        self.assertEqual(last["tool_name"], "Agent")
        self.assertIn("src/agent_created.py", last["changed_files"])
        self.assertEqual(last["changed_files_source"], "pre_post_snapshot")
        self.assertEqual(last["attribution"], "strong")

    def test_internal_paths_never_trigger_scope_violation(self):
        """AIWF internal files excluded from scope checks."""
        s = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        s["active_context_id"] = "CTX-001"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(s, indent=2))
        (self.tmp / ".aiwf" / "state" / "contexts.json").write_text(json.dumps(
            {"contexts": [{"id": "CTX-001", "allowed_write": ["src/"]}]}, indent=2))

        # Simulate evidence with internal file changes
        ev = json.loads((self.tmp / ".aiwf" / "evidence" / "records.json").read_text())
        ev["records"].append({
            "id": "EV-999", "changed_files": [".aiwf/state/state.json", ".claude/settings.json",
                                               "CLAUDE.md", "scripts/aiwf_status.py", "src/ok.py"],
            "changed_files_source": "test", "attribution": "strong",
            "status": "pending", "trust": "machine_observed",
        })
        (self.tmp / ".aiwf" / "evidence" / "records.json").write_text(json.dumps(ev, indent=2))

        from aiwf_core.hooks.common.evidence_writer import check_and_record_scope_violations
        ctx = {"id": "CTX-001", "allowed_write": ["src/"]}
        violations = check_and_record_scope_violations(
            [".aiwf/state/state.json", ".claude/settings.json", "CLAUDE.md",
             "scripts/aiwf_status.py", "src/ok.py"],
            ctx, self.tmp)
        self.assertEqual(len(violations), 0,
                        f"Internal paths must not trigger violations, got {violations}")


if __name__ == "__main__":
    unittest.main()
