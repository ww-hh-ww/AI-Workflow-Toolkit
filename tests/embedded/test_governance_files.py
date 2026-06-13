"""Governance file policy: .aiwf artifacts allowed, classified separately."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

def _install(cwd):
    env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
    subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                   capture_output=True, text=True, cwd=str(cwd), env=env, timeout=20)

class TestGovernanceFiles(unittest.TestCase):
    """Governance file writes are always allowed, classified separately."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awgv_"))
        _install(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for fn, dfn in MVP_STATE_FILES.items():
            p = self.tmp / ".aiwf" / fn; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(dfn(), indent=2) + "\n")

    def _set_scope(self, allowed):
        s = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        s["active_context_id"] = "CTX-001"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(s, indent=2))
        (self.tmp / ".aiwf" / "state" / "contexts.json").write_text(json.dumps(
            {"contexts": [{"id": "CTX-001", "allowed_write": allowed}]}, indent=2))

    def _scope_check(self, path):
        inp = json.dumps({"session_id": "t", "cwd": str(self.tmp),
                         "tool_name": "Write", "tool_input": {"file_path": path}})
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_scope_check.py")],
                          input=inp, capture_output=True, text=True,
                          cwd=str(self.tmp), env=env, timeout=10)
        try: out = json.loads(r.stdout.strip()) if r.stdout.strip() else {}
        except: out = {}
        return r.returncode, out

    # ── MVP state files ──
    def test_state_json_allowed(self):
        self._set_scope(["src/"]); _, out = self._scope_check(".aiwf/state/state.json")
        self.assertNotIn("permissionDecision", out)

    def test_review_json_allowed(self):
        self._set_scope(["src/"]); _, out = self._scope_check(".aiwf/artifacts/quality/review.json")
        self.assertNotIn("permissionDecision", out)

    # ── report and assets ──
    def test_report_md_allowed(self):
        self._set_scope(["src/"]); _, out = self._scope_check(".aiwf/artifacts/reports/闭合报告.md")
        self.assertNotIn("permissionDecision", out)

    def test_project_map_md_allowed(self):
        self._set_scope(["src/"]); _, out = self._scope_check(".aiwf/artifacts/reports/项目地图.md")
        self.assertNotIn("permissionDecision", out)

    def test_ideas_md_allowed(self):
        self._set_scope(["src/"]); _, out = self._scope_check(".aiwf/artifacts/reports/ideas.md")
        self.assertNotIn("permissionDecision", out)

    def test_current_state_md_allowed(self):
        self._set_scope(["src/"]); _, out = self._scope_check(".aiwf/artifacts/reports/当前状态.md")
        self.assertNotIn("permissionDecision", out)

    def test_assets_project_map_allowed(self):
        self._set_scope(["src/"]); _, out = self._scope_check(".aiwf/assets/project-map.json")
        self.assertNotIn("permissionDecision", out)

    def test_assets_test_map_allowed(self):
        self._set_scope(["src/"]); _, out = self._scope_check(".aiwf/assets/test-map.json")
        self.assertNotIn("permissionDecision", out)

    # ── experiment artifacts ──
    def test_experiment_artifacts_allowed(self):
        self._set_scope(["src/"])
        _, out = self._scope_check(".aiwf/experiment-artifacts/experiment-report.md")
        self.assertNotIn("permissionDecision", out)

    def test_internal_snapshot_allowed(self):
        self._set_scope(["src/"])
        _, out = self._scope_check(".aiwf/runtime/internal/pre-tool-snapshot.json")
        self.assertNotIn("permissionDecision", out)

    # ── project files still denied ──
    def test_project_file_still_denied(self):
        self._set_scope(["src/"])
        _, out = self._scope_check("danger/x.py")
        self.assertEqual(out.get("hookSpecificOutput", {}).get("permissionDecision"), "deny")

    # ── classification ──
    def test_classify_governance(self):
        from aiwf_core.core.scope_policy import classify_file_change
        self.assertEqual(classify_file_change(".aiwf/state/state.json"), "governance")
        self.assertEqual(classify_file_change(".aiwf/artifacts/reports/闭合报告.md"), "governance")
        self.assertEqual(classify_file_change(".aiwf/artifacts/reports/项目地图.md"), "governance")
        self.assertEqual(classify_file_change(".aiwf/artifacts/reports/ideas.md"), "governance")
        self.assertEqual(classify_file_change(".aiwf/assets/project-map.json"), "governance")
        self.assertEqual(classify_file_change(".aiwf/experiment-artifacts/x.md"), "governance")
        self.assertEqual(classify_file_change("src/main.py"), "project")
        self.assertEqual(classify_file_change("danger/x.py"), "project")

    def test_governance_not_in_scope_violation(self):
        """Governance files never trigger project scope violation."""
        self._set_scope(["src/"])
        from aiwf_core.hooks.common.evidence_writer import check_and_record_scope_violations
        files = [".aiwf/artifacts/reports/闭合报告.md", ".aiwf/assets/x.json", ".aiwf/experiment-artifacts/r.md"]
        violations = check_and_record_scope_violations(
            files, {"id": "CTX-001", "allowed_write": ["src/"]}, self.tmp)
        self.assertEqual(len(violations), 0)


if __name__ == "__main__":
    unittest.main()
