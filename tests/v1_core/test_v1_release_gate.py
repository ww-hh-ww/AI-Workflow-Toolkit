"""V1 Release Gate — minimum passing tests for a stable V1 install.

Runs a full install then exercises every core command path.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 20


def _run(cmd, cwd, **kw):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    return subprocess.run(cmd, capture_output=True, text=True,
                          cwd=str(cwd), env=env, timeout=TIMEOUT, **kw)


class TestV1ReleaseGate(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awv1_"))
        _run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"], cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ── 1. Install surface ──

    def test_01_install_has_12_commands(self):
        r = _run([sys.executable, "-m", "aiwf_core.cli", "--help", "--all"], self.tmp)
        self.assertIn("doctor", r.stdout)
        self.assertIn("sync", r.stdout)

    def test_02_seven_skills_four_agents(self):
        skills = sorted((self.tmp / ".claude" / "skills").iterdir())
        self.assertEqual(len(skills), 7)
        agents = sorted((self.tmp / ".claude" / "agents").iterdir())
        self.assertEqual(len(agents), 4)

    def test_03_six_scripts_executable(self):
        scripts = sorted((self.tmp / "scripts").glob("aiwf_*.py"))
        self.assertEqual(len(scripts), 6)
        for s in scripts:
            self.assertTrue(s.stat().st_mode & 0o111, f"Not executable: {s.name}")

    def test_04_state_and_records_exist(self):
        for f in ["state/state.json", "state/goals.json", "state/plans.json",
                  "state/tasks.json", "state/milestones.json", "state/fix-loop.json",
                  "records/evidence.json", "records/testing.json", "records/review.json",
                  "records/architecture-review.json", "records/events.json"]:
            self.assertTrue((self.tmp / ".aiwf" / f).exists(), f"Missing: {f}")

    def test_05_no_dead_zones(self):
        for dead in ["artifacts", "assets", "archive"]:
            self.assertFalse((self.tmp / ".aiwf" / dead).is_dir(), f"Dead zone exists: {dead}")

    # ── 2. Create commands (MD-first) ──

    def test_06_goal_create_writes_md(self):
        _run([sys.executable, "-m", "aiwf_core.cli", "goal", "create", "GOAL-001", "--title", "Test Goal"], self.tmp)
        md = self.tmp / ".aiwf" / "goals" / "GOAL-001.md"
        self.assertTrue(md.exists())
        content = md.read_text()
        self.assertIn("id: GOAL-001", content)
        self.assertIn("title: Test Goal", content)

    def test_07_plan_create_writes_md(self):
        _run([sys.executable, "-m", "aiwf_core.cli", "plan", "create", "PLAN-001", "--goal", "GOAL-001", "--title", "Test Plan"], self.tmp)
        self.assertTrue((self.tmp / ".aiwf" / "plans" / "PLAN-001.md").exists())

    def test_08_task_create_writes_md(self):
        _run([sys.executable, "-m", "aiwf_core.cli", "task", "create", "TASK-001", "--plan", "PLAN-001", "--goal", "GOAL-001", "--title", "Test Task"], self.tmp)
        md = self.tmp / ".aiwf" / "tasks" / "TASK-001.md"
        self.assertTrue(md.exists())
        content = md.read_text()
        self.assertIn("executor_required: true", content)
        self.assertIn("tester_required: true", content)
        self.assertIn("reviewer_required: true", content)

    def test_09_milestone_create_writes_md(self):
        _run([sys.executable, "-m", "aiwf_core.cli", "milestone", "create", "MS-001", "--goal", "GOAL-001", "--title", "Test MS"], self.tmp)
        self.assertTrue((self.tmp / ".aiwf" / "milestones" / "MS-001.md").exists())

    # ── 3. Sync ──

    def test_10_sync_check_passes(self):
        r = _run([sys.executable, "-m", "aiwf_core.cli", "sync", "--check"], self.tmp)
        self.assertEqual(r.returncode, 0)

    def test_11_sync_updates_json(self):
        _run([sys.executable, "-m", "aiwf_core.cli", "sync"], self.tmp)
        goals = json.loads((self.tmp / ".aiwf" / "state" / "goals.json").read_text())
        self.assertGreater(len(goals.get("goals", [])), 0)
        self.assertIn("Test Goal", goals["goals"][0]["title_cache"])

    # ── 4. Activate + compile lock ──

    def test_12_task_activate_sets_frozen_hash(self):
        _run([sys.executable, "-m", "aiwf_core.cli", "task", "activate", "TASK-001"], self.tmp)
        tasks = json.loads((self.tmp / ".aiwf" / "state" / "tasks.json").read_text())
        task = [t for t in tasks["tasks"] if t["id"] == "TASK-001"][0]
        self.assertEqual(task["status"], "active")
        self.assertTrue(task.get("frozen_contract_hash"))

    def test_13_active_task_md_skipped_during_sync(self):
        r = _run([sys.executable, "-m", "aiwf_core.cli", "sync", "--check"], self.tmp)
        self.assertIn("frozen", r.stdout.lower())
        self.assertIn("skipped", r.stdout.lower())

    # ── 5. Record commands ──

    def test_14_record_evidence(self):
        r = _run([sys.executable, "-m", "aiwf_core.cli", "record", "evidence",
                  "--role", "executor", "--summary", "implemented feature"], self.tmp)
        self.assertEqual(r.returncode, 0)

    def test_15_record_testing(self):
        r = _run([sys.executable, "-m", "aiwf_core.cli", "record", "testing",
                  "--status", "passed", "--summary", "all tests pass"], self.tmp)
        self.assertEqual(r.returncode, 0)

    def test_16_record_review(self):
        r = _run([sys.executable, "-m", "aiwf_core.cli", "record", "review",
                  "--result", "accepted", "--summary", "LGTM"], self.tmp)
        self.assertEqual(r.returncode, 0)

    def test_17_record_architecture_review(self):
        r = _run([sys.executable, "-m", "aiwf_core.cli", "record", "architecture-review",
                  "--status", "intact", "--summary", "structure ok"], self.tmp)
        self.assertEqual(r.returncode, 0)

    # ── 6. Close ──

    def test_18_task_close_succeeds(self):
        r = _run([sys.executable, "-m", "aiwf_core.cli", "task", "close"], self.tmp)
        self.assertEqual(r.returncode, 0)
        tasks = json.loads((self.tmp / ".aiwf" / "state" / "tasks.json").read_text())
        task = [t for t in tasks["tasks"] if t["id"] == "TASK-001"][0]
        self.assertEqual(task["status"], "closed")

    # ── 7. Milestone gates ──

    def test_19_milestone_integration_arch_assess(self):
        _run([sys.executable, "-m", "aiwf_core.cli", "milestone", "link-plan", "MS-001", "PLAN-001"], self.tmp)
        r1 = _run([sys.executable, "-m", "aiwf_core.cli", "milestone", "integration-test", "MS-001",
                   "--status", "passed", "--coverage-mode", "end_to_end_flow",
                   "--main-path-status", "passed", "--summary", "e2e ok"], self.tmp)
        self.assertEqual(r1.returncode, 0)
        r2 = _run([sys.executable, "-m", "aiwf_core.cli", "milestone", "arch-review", "MS-001",
                   "--status", "intact", "--notes", "structure ok"], self.tmp)
        self.assertEqual(r2.returncode, 0)
        r3 = _run([sys.executable, "-m", "aiwf_core.cli", "milestone", "assess", "MS-001",
                   "--verdict", "PASS", "--summary", "all gates passed"], self.tmp)
        self.assertEqual(r3.returncode, 0)

    # ── 8. Non-whitelist commands must fail ──

    def test_20_non_whitelist_rejected(self):
        for bad_cmd in [["route"], ["workspace"], ["goal-tree"], ["project-map"],
                        ["research"], ["frontier"], ["checkpoint"]]:
            r = _run([sys.executable, "-m", "aiwf_core.cli"] + bad_cmd, self.tmp,
                     **{"check": False})
            self.assertNotEqual(r.returncode, 0,
                              f"Non-whitelist command should fail: aiwf {' '.join(bad_cmd)}")

    # ── 9. Doctor ──

    def test_21_doctor_includes_sync(self):
        r = _run([sys.executable, "-m", "aiwf_core.cli", "doctor"], self.tmp)
        self.assertIn("sync", r.stdout.lower())

    # ── 10. Surface pollution ──

    def test_22_surface_has_no_stale_commands(self):
        import subprocess
        r = subprocess.run(
            ["grep", "-R", "aiwf state\\|aiwf route\\|aiwf workspace\\|aiwf goal-tree\\|"
             "aiwf project-map\\|aiwf checkpoint\\|prepare-close\\|cancel-close\\|"
             "aiwf milestone update"],
            capture_output=True, text=True,
            cwd=str(self.tmp / ".claude"))
        self.assertEqual(r.returncode, 1, f"Stale commands in installed surface:\n{r.stdout[:500]}")
        r2 = subprocess.run(
            ["grep", "-R", "\\.aiwf/artifacts\\|\\.aiwf/assets\\|runtime/checkpoints"],
            capture_output=True, text=True,
            cwd=str(self.tmp / ".claude"))
        self.assertEqual(r2.returncode, 1, f"Stale paths in installed surface:\n{r2.stdout[:500]}")


if __name__ == "__main__":
    unittest.main()
