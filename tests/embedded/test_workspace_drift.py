"""Workspace drift: scan, classify, status hook, no side effects."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
TIMEOUT = 15

class TestWorkspaceDrift(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmpl = Path(tempfile.mkdtemp(prefix="awwd_tmpl_"))
        subprocess.run(["git", "init", "-b", "main"], cwd=str(cls._tmpl), capture_output=True, timeout=10)
        subprocess.run(["git", "config", "user.email", "a@b.c"], cwd=str(cls._tmpl), capture_output=True, timeout=10)
        subprocess.run(["git", "config", "user.name", "t"], cwd=str(cls._tmpl), capture_output=True, timeout=10)
        (cls._tmpl/"README.md").write_text("init\n")
        subprocess.run(["git", "add", "README.md"], cwd=str(cls._tmpl), capture_output=True, timeout=10)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(cls._tmpl), capture_output=True, timeout=10)
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                       capture_output=True, text=True, cwd=str(cls._tmpl), env=env, timeout=30)
        drift = cls._tmpl / ".aiwf" / "runtime" / "internal" / "workspace-drift.json"
        if drift.exists():
            drift.unlink()
        subprocess.run(["git", "add", "-A"], cwd=str(cls._tmpl), capture_output=True, timeout=10)
        subprocess.run(["git", "commit", "-m", "aiwf-install"], cwd=str(cls._tmpl), capture_output=True, timeout=10)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmpl, ignore_errors=True)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="awwd_t_"))
        shutil.copytree(self._tmpl, self.tmp, dirs_exist_ok=True, symlinks=False)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *args):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, "-m", "aiwf_core.cli"] + list(args),
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    def _run_ok(self, *args):
        r = self._run(*args)
        self.assertEqual(r.returncode, 0, f"Failed: {args}\n{r.stderr[:300]}")
        return r

    def _status(self):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, "-m", "aiwf_core.cli", "status", "--debug"],
                           capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        return r.stdout

    def _drift(self):
        return json.loads((self.tmp/".aiwf"/"runtime"/"internal"/"workspace-drift.json").read_text())

    # ── clean repo ──
    def test_clean_repo_dirty_false(self):
        self._run_ok("workspace", "scan")
        d = self._drift()
        self.assertFalse(d["dirty"])
        self.assertFalse(d["needs_planner_review"])
        self.assertEqual(len(d["project_changes"]), 0)

    # ── modified tracked file ──
    def test_modified_tracked_file_detected(self):
        (self.tmp/"README.md").write_text("modified\n")
        self._run_ok("workspace", "scan")
        d = self._drift()
        self.assertTrue(d["dirty"])
        proj = [c["path"] for c in d["project_changes"]]
        self.assertIn("README.md", proj)

    # ── untracked file ──
    def test_untracked_file_detected(self):
        (self.tmp/"src").mkdir(exist_ok=True)
        (self.tmp/"src"/"new.js").write_text("new\n")
        self._run_ok("workspace", "scan")
        d = self._drift()
        self.assertIn("src/new.js", d["untracked"])

    # ── governance ──
    def test_governance_change_classified(self):
        (self.tmp/".aiwf" / "state" / "state.json").write_text("changed\n")
        self._run_ok("workspace", "scan")
        d = self._drift()
        gov = [c["path"] for c in d["governance_changes"]]
        self.assertIn(".aiwf/state/state.json", gov)

    def test_non_ascii_governance_path_is_not_git_quoted(self):
        report = self.tmp / ".aiwf" / "artifacts" / "reports" / "项目地图.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("changed\n", encoding="utf-8")

        self._run_ok("workspace", "scan")

        d = self._drift()
        gov = [c["path"] for c in d["governance_changes"]]
        project = [c["path"] for c in d["project_changes"]]
        self.assertIn(".aiwf/artifacts/reports/项目地图.md", gov)
        self.assertNotIn(".aiwf/artifacts/reports/项目地图.md", project)

    # ── writes file ──
    def test_scan_writes_drift_json(self):
        self._run_ok("workspace", "scan")
        self.assertTrue((self.tmp/".aiwf"/"runtime"/"internal"/"workspace-drift.json").exists())

    # ── output short ──
    def test_output_is_short_no_json_dump(self):
        r = self._run_ok("workspace", "scan")
        self.assertLess(len(r.stdout), 600)
        self.assertNotIn("{", r.stdout)

    # ── no side effects ──
    def test_scan_no_modify_claude_md(self):
        before = (self.tmp/"CLAUDE.md").read_text()
        self._run_ok("workspace", "scan")
        self.assertEqual(before, (self.tmp/"CLAUDE.md").read_text())

    def test_scan_no_modify_settings(self):
        before = (self.tmp/".claude"/"settings.json").read_text()
        self._run_ok("workspace", "scan")
        self.assertEqual(before, (self.tmp/".claude"/"settings.json").read_text())

    # ── status ──
    def test_status_not_scanned_initially(self):
        ctx = self._status()
        self.assertIn("not scanned", ctx)

    def test_status_clean_after_scan(self):
        self._run_ok("workspace", "scan")
        self.assertIn("clean", self._status().lower())

    def test_status_pending_after_dirty(self):
        (self.tmp/"README.md").write_text("dirty\n")
        self._run_ok("workspace", "scan")
        self.assertIn("pending", self._status().lower())

    def test_status_no_list_files(self):
        (self.tmp/"README.md").write_text("dirty_secret_xyz\n")
        self._run_ok("workspace", "scan")
        ctx = self._status()
        self.assertNotIn("dirty_secret_xyz", ctx)
        self.assertNotIn("README.md", ctx)

    # ── planner skill ──
    def test_planner_skill_mentions_workspace_scan(self):
        c = (self.tmp/".claude"/"skills"/"aiwf-planner-execute"/"SKILL.md").read_text()
        self.assertIn("workspace scan", c.lower())



    # ── non-git repo ──
    def test_non_git_repo_limited_mode(self):
        d = Path(tempfile.mkdtemp(prefix="awwd_ng_"))
        try:
            from aiwf_core.core.workspace_drift import scan_workspace_drift
            drift = scan_workspace_drift(str(d))
            self.assertFalse(drift["is_git_repo"])
            self.assertEqual(drift.get("mode"), "mtime_snapshot_first_scan")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    # ── deleted file ──
    def test_deleted_file_detected(self):
        (self.tmp/"to_delete.txt").write_text("will delete\n")
        subprocess.run(["git", "add", "to_delete.txt"], cwd=str(self.tmp), capture_output=True, timeout=10)
        subprocess.run(["git", "commit", "-m", "add"], cwd=str(self.tmp), capture_output=True, timeout=10)
        (self.tmp/"to_delete.txt").unlink()
        self._run_ok("workspace", "scan")
        d = self._drift()
        self.assertIn("to_delete.txt", d["deleted"])

    # ── scripts py_compile ──
    def test_scripts_py_compile(self):
        import py_compile
        for s in sorted((self.tmp/"scripts").glob("aiwf_*.py")):
            py_compile.compile(str(s), doraise=True)



if __name__ == "__main__":
    unittest.main()
