"""Contract tests for Stage 4.7.3: AIWF Workspace Layout Refactor."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _install(cwd):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    subprocess.run(
        [sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
        capture_output=True, text=True, cwd=str(cwd), env=env, timeout=20,
    )


class TestWorkspaceLayoutInit(unittest.TestCase):
    """Install creates v2 5-zone layout."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awf473_"))
        _install(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @unittest.skip("V1: workspace internal")
    def test_readme_exists(self):
        self.assertTrue((self.tmp / ".aiwf" / "README.md").exists())

    @unittest.skip("V1: workspace internal")
    def test_readme_describes_five_zones(self):
        text = (self.tmp / ".aiwf" / "README.md").read_text()
        self.assertTrue(
            all(kw in text for kw in ["state/", "artifacts/", "runtime/", "assets/", "archive/"]),
            f"README doesn't describe AIWF zones: {text[:200]}",
        )
        self.assertIn("Humans do not normally read raw `.aiwf` files", text)
        self.assertIn(".aiwf/records/当前状态.md", text)
        self.assertNotIn("- `reports/", text)
        self.assertNotIn("- `quality/", text)

    @unittest.skip("V1: workspace internal")
    def test_v2_zone_dirs_exist(self):
        for zone in ["state", "artifacts", "runtime", "assets", "archive"]:
            self.assertTrue((self.tmp / ".aiwf" / zone).is_dir(), f"Missing zone: {zone}")

    @unittest.skip("V1: workspace internal")
    def test_artifact_subdirs_exist(self):
        for sub in ["evidence", "quality"]:
            self.assertTrue(
                (self.tmp / ".aiwf" / "artifacts" / sub).is_dir(),
                f"Missing artifacts/{sub}",
            )
        # plans moved to top-level .aiwf/plans/ in V2
        self.assertTrue((self.tmp / ".aiwf" / "plans").is_dir(), "Missing top-level plans/")

    @unittest.skip("V1: workspace internal")
    def test_runtime_subdirs_exist(self):
        for sub in ["checkpoints", "internal"]:
            self.assertTrue(
                (self.tmp / ".aiwf" / "runtime" / sub).is_dir(),
                f"Missing runtime/{sub}",
            )

    @unittest.skip("V1: workspace internal")
    def test_old_compat_dirs_not_created(self):
        """Stage 4.7.3 clean break: old top-level dirs are NOT created."""
        for sub in ["evidence", "quality", "history", "reports", "checkpoints", "internal", "research"]:
            self.assertFalse((self.tmp / ".aiwf" / sub).is_dir(),
                           f"Old dir should not exist: {sub}")
        # plans is a V2 top-level dir (moved from artifacts/plans)

    @unittest.skip("V1: workspace internal")
    def test_state_dir_unchanged(self):
        self.assertTrue((self.tmp / ".aiwf" / "state").is_dir())
        self.assertTrue((self.tmp / ".aiwf" / "state" / "state.json").exists())


class TestPathResolver(unittest.TestCase):
    """Path resolver returns correct v2 paths."""

    @unittest.skip("V1: workspace internal")
    def test_state_dir_returns_state(self):
        from aiwf_core.core.paths import state_dir
        p = state_dir("/tmp/test")
        self.assertTrue(p.endswith(".aiwf/state"), p)

    @unittest.skip("V1: workspace internal")
    def test_artifacts_dir_returns_artifacts(self):
        from aiwf_core.core.paths import artifacts_dir
        p = artifacts_dir("/tmp/test")
        self.assertTrue(p.endswith(".aiwf/artifacts"), p)

    @unittest.skip("V1: workspace internal")
    def test_runtime_dir_returns_runtime(self):
        from aiwf_core.core.paths import runtime_dir
        p = runtime_dir("/tmp/test")
        self.assertTrue(p.endswith(".aiwf/runtime"), p)

    @unittest.skip("V1: workspace internal")
    def test_plan_artifacts_dir(self):
        from aiwf_core.core.paths import plan_artifacts_dir
        p = plan_artifacts_dir("/tmp/test")
        self.assertTrue(p.endswith(".aiwf/plans"), p)

    @unittest.skip("V1: workspace internal")
    def test_evidence_artifacts_dir(self):
        from aiwf_core.core.paths import evidence_artifacts_dir
        p = evidence_artifacts_dir("/tmp/test")
        self.assertTrue(p.endswith(".aiwf/artifacts/evidence"), p)

    @unittest.skip("V1: workspace internal")
    def test_checkpoints_dir_returns_runtime(self):
        from aiwf_core.core.paths import checkpoints_dir
        p = checkpoints_dir("/tmp/test")
        self.assertTrue(p.endswith(".aiwf/runtime/checkpoints"), p)

    @unittest.skip("V1: workspace internal")
    def test_history_dir_returns_runtime(self):
        from aiwf_core.core.paths import history_dir
        p = history_dir("/tmp/test")
        self.assertTrue(p.endswith(".aiwf/runtime/history"), p)

    @unittest.skip("V1: workspace internal")
    def test_legacy_to_new_mapping_covers_old_dirs(self):
        from aiwf_core.core.paths import LEGACY_TO_NEW
        for old in ["evidence", "reports", "quality", "checkpoints", "history", "internal"]:
            legacy = f".aiwf/{old}"
            self.assertIn(legacy, LEGACY_TO_NEW, f"Missing legacy mapping: {legacy}")

    @unittest.skip("V1: workspace internal")
    def test_is_layout_v2_detects_new_layout(self):
        from aiwf_core.core.paths import is_layout_v2
        with tempfile.TemporaryDirectory() as tmp:
            # Create only v2 dirs
            for d in ["artifacts", "runtime"]:
                os.makedirs(os.path.join(tmp, ".aiwf", d), exist_ok=True)
            self.assertTrue(is_layout_v2(tmp))


class TestMigrationCLI(unittest.TestCase):
    """Workspace migrate-layout CLI behavior."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awf473m_"))
        _install(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _run(self, *args):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", *args],
            capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=15,
        )

    @unittest.skip("V1: workspace internal")
    def test_migrate_dry_run_lists_moves(self):
        # Create a file in an OLD location (simulating pre-migration project)
        old_plans = self.tmp / ".aiwf" / "plans"
        old_plans.mkdir(parents=True, exist_ok=True)
        (old_plans / "test-plan.md").write_text("test", encoding="utf-8")
        r = self._run("workspace", "migrate-layout", "--dry-run")
        self.assertEqual(0, r.returncode, f"stderr: {r.stderr}")
        self.assertIn(".aiwf/plans/", r.stdout)

    @unittest.skip("V1: workspace internal")
    def test_migrate_execute_moves_content(self):
        # Create a file in OLD location
        old_reports = self.tmp / ".aiwf" / "artifacts" / "reports"
        old_reports.mkdir(parents=True, exist_ok=True)
        (old_reports / "test-report.md").write_text("test content", encoding="utf-8")

        r = self._run("workspace", "migrate-layout")
        self.assertEqual(0, r.returncode, f"stderr: {r.stderr}")

    @unittest.skip("V1: workspace internal")
    def test_migrate_does_not_move_state(self):
        state_before = (self.tmp / ".aiwf" / "state" / "state.json").read_text()
        r = self._run("workspace", "migrate-layout")
        self.assertEqual(0, r.returncode, f"stderr: {r.stderr}")
        self.assertTrue((self.tmp / ".aiwf" / "state" / "state.json").exists())
        self.assertEqual(state_before, (self.tmp / ".aiwf" / "state" / "state.json").read_text())

    @unittest.skip("V1: workspace internal")
    def test_migrate_idempotent(self):
        r1 = self._run("workspace", "migrate-layout")
        self.assertEqual(0, r1.returncode)
        r2 = self._run("workspace", "migrate-layout")
        self.assertEqual(0, r2.returncode, f"Second run should succeed: {r2.stderr}")

    @unittest.skip("V1: workspace internal")
    def test_migrate_generates_report(self):
        # Put a file in OLD location (pre-v2 layout) so migration has work
        old_plans = self.tmp / ".aiwf" / "plans"
        old_plans.mkdir(parents=True, exist_ok=True)
        (old_plans / "sample.md").write_text("sample", encoding="utf-8")

        r = self._run("workspace", "migrate-layout")
        self.assertEqual(0, r.returncode, f"stderr: {r.stderr}")
        self.assertIn("Migration complete", r.stdout)


class TestLayoutDocExists(unittest.TestCase):
    """Layout contract doc exists and is consistent with code."""

    @unittest.skip("V1: workspace internal")
    def test_layout_doc_exists(self):
        self.assertTrue((PROJECT_ROOT / "docs" / "AIWF_WORKSPACE_LAYOUT.md").exists())

    @unittest.skip("V1: workspace internal")
    def test_layout_doc_defines_five_zones(self):
        text = (PROJECT_ROOT / "docs" / "AIWF_WORKSPACE_LAYOUT.md").read_text()
        self.assertIn("state/", text)
        self.assertIn("artifacts/", text)
        self.assertIn("runtime/", text)
        self.assertIn("assets/", text)
        self.assertIn("archive/", text)

    @unittest.skip("V1: workspace internal")
    def test_layout_doc_has_migration_mapping(self):
        text = (PROJECT_ROOT / "docs" / "AIWF_WORKSPACE_LAYOUT.md").read_text()
        self.assertIn("Migration Mapping", text)
        self.assertIn("artifacts/plans", text)
        self.assertIn("runtime/checkpoints", text)


class TestStatusPromptLayoutRegression(unittest.TestCase):
    """status --prompt stays within budget after layout changes."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awf473s_"))
        _install(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @unittest.skip("V1: workspace internal")
    def test_status_prompt_within_budget(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", "status", "--prompt"],
            capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=15,
        )
        self.assertEqual(0, r.returncode, f"stderr: {r.stderr}")
        self.assertLess(len(r.stdout), 800, f"status --prompt is {len(r.stdout)} chars")


if __name__ == "__main__":
    unittest.main()
