"""Task ledger: flexible planning, guarded execution window."""
import json, os, shutil, subprocess, sys, tempfile, time, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
TIMEOUT = 15


class TestTaskLedger(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awtl_"))
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                       capture_output=True, text=True, cwd=str(cls.tmp), env=env, timeout=20)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for fn, dfn in MVP_STATE_FILES.items():
            p = self.tmp / ".aiwf" / fn; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(dfn(), indent=2) + "\n")
        for optional in [
            "history/task-ledger.json",
            "history/task-history.json",
            "reports/当前状态.md",
            "reports/质量摘要.md",
            "task-ledger.json",
            "task-history.json",
            "current-state.md",
            "quality-digest.md",
        ]:
            path = self.tmp / ".aiwf" / optional
            if path.exists():
                path.unlink()

    def _run(self, *args):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, "-m", "aiwf_core.cli", *args],
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    def _seed_l2_contracts(self, target_structure="Preserve module boundaries"):
        goal_path = self.tmp / ".aiwf" / "state" / "goal.json"
        goal = json.loads(goal_path.read_text())
        brief = goal["quality_brief"]
        brief["evaluation_contract"].update({
            "user_visible_outcome": "Requested behavior works",
            "acceptance_criteria": ["behavior verified"],
            "test_obligations": ["run regression tests"],
            "review_obligations": ["review scope and correctness"],
        })
        brief["architecture_brief"]["target_structure"] = target_structure
        goal_path.write_text(json.dumps(goal, indent=2))

    def test_multiple_candidate_tasks_are_allowed(self):
        from aiwf_core.core.task_ledger import upsert_task, ledger_summary

        upsert_task(str(self.tmp), "TASK-001", "Scaffold", status="candidate")
        upsert_task(str(self.tmp), "TASK-002", "Fill details", status="ready", dependencies=["TASK-001"])
        summary = ledger_summary(str(self.tmp))

        self.assertEqual(summary["counts"]["candidate"], 1)
        self.assertEqual(summary["counts"]["ready"], 1)
        self.assertEqual(summary["active_task_ids"], [])

    def test_activation_enforces_default_single_execution_window(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        upsert_task(str(self.tmp), "TASK-001", "A", status="ready", allowed_write=["src/a.py"])
        upsert_task(str(self.tmp), "TASK-002", "B", status="ready", allowed_write=["src/b.py"])
        self.assertTrue(activate_task(str(self.tmp), "TASK-001")["activated"])
        second = activate_task(str(self.tmp), "TASK-002")

        self.assertFalse(second["activated"])
        self.assertTrue(any("active execution window" in b for b in second["blockers"]))

    def test_parallel_safe_allows_non_overlapping_active_tasks(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        upsert_task(str(self.tmp), "TASK-001", "A", status="ready", allowed_write=["src/a.py"])
        upsert_task(str(self.tmp), "TASK-002", "B", status="ready", allowed_write=["src/b.py"], parallel_safe=True)
        self.assertTrue(activate_task(str(self.tmp), "TASK-001")["activated"])
        second = activate_task(str(self.tmp), "TASK-002")

        self.assertTrue(second["activated"], second["blockers"])

    def test_parallel_safe_blocks_write_boundary_overlap(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        upsert_task(str(self.tmp), "TASK-001", "A", status="ready", allowed_write=["src/shared.py"])
        upsert_task(str(self.tmp), "TASK-002", "B", status="ready", allowed_write=["src/shared.py"], parallel_safe=True)
        self.assertTrue(activate_task(str(self.tmp), "TASK-001")["activated"])
        second = activate_task(str(self.tmp), "TASK-002")

        self.assertFalse(second["activated"])
        self.assertTrue(any("write boundary conflict" in b for b in second["blockers"]))

    def test_dependency_must_be_closed_before_activation(self):
        from aiwf_core.core.task_ledger import activate_task, close_task, upsert_task

        upsert_task(str(self.tmp), "TASK-001", "Scaffold", status="ready")
        upsert_task(str(self.tmp), "TASK-002", "Fill", status="ready", dependencies=["TASK-001"])
        self.assertFalse(activate_task(str(self.tmp), "TASK-002")["activated"])
        close_task(str(self.tmp), "TASK-001")
        self.assertTrue(activate_task(str(self.tmp), "TASK-002")["activated"])

    def test_close_task_appends_task_history_and_quality_digest(self):
        from aiwf_core.core.task_ledger import close_task, upsert_task

        upsert_task(str(self.tmp), "TASK-001", "Scaffold", status="ready")
        (self.tmp / ".aiwf" / "evidence" / "records.json").write_text(json.dumps({
            "records": [{"id": "EV-001", "status": "accepted", "changed_files": ["src/a.py"]}]
        }, indent=2))
        (self.tmp / ".aiwf" / "quality" / "testing.json").write_text(json.dumps({
            "status": "adequate", "untested_risks": ["manual UI"]
        }, indent=2))
        result = close_task(str(self.tmp), "TASK-001")

        self.assertTrue(result["closed"])
        history = json.loads((self.tmp / ".aiwf" / "history" / "task-history.json").read_text())
        self.assertEqual(history["tasks"][-1]["id"], "TASK-001")
        self.assertIn("src/a.py", history["tasks"][-1]["changed_files"])
        self.assertTrue((self.tmp / ".aiwf" / "reports" / "质量摘要.md").exists())

    def test_task_history_archives_trimmed_hotspots(self):
        from aiwf_core.core.cross_task_quality import append_task_history_from_state

        old_tasks = [
            {"id": f"old-{i}", "changed_files": ["src/ancient.py"], "fix_loop_attempt_count": 0, "untested_risk_count": 0}
            for i in range(101)
        ]
        (self.tmp / ".aiwf" / "history" / "task-history.json").write_text(json.dumps({"tasks": old_tasks}, indent=2))
        append_task_history_from_state(str(self.tmp), task_id="TASK-NEW", title="New")
        history = json.loads((self.tmp / ".aiwf" / "history" / "task-history.json").read_text())

        self.assertEqual(len(history["tasks"]), 100)
        self.assertGreaterEqual(history["archived_hotspots"]["src/ancient.py"], 2)

    def test_close_task_sets_cross_task_escalation_flag(self):
        from aiwf_core.core.task_ledger import close_task, upsert_task

        (self.tmp / ".aiwf" / "history" / "task-history.json").write_text(json.dumps({
            "tasks": [
                {"id": "t1", "changed_files": ["src/a.py"], "fix_loop_attempt_count": 1, "untested_risk_count": 0},
                {"id": "t2", "changed_files": ["src/b.py"], "fix_loop_attempt_count": 2, "untested_risk_count": 0},
            ]
        }, indent=2))
        upsert_task(str(self.tmp), "TASK-001", "Close with trend", status="ready")
        close_task(str(self.tmp), "TASK-001")
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())

        self.assertTrue(state["cross_task_quality_escalation_required"])

    def test_repeated_hotspot_blocks_activation_without_architecture_brief(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        (self.tmp / ".aiwf" / "history" / "task-history.json").write_text(json.dumps({
            "tasks": [
                {"id": "t1", "changed_files": ["src/shared.py"], "fix_loop_attempt_count": 0, "untested_risk_count": 0},
                {"id": "t2", "changed_files": ["src/shared.py"], "fix_loop_attempt_count": 0, "untested_risk_count": 0},
                {"id": "t3", "changed_files": ["src/shared.py"], "fix_loop_attempt_count": 0, "untested_risk_count": 0},
            ]
        }, indent=2))
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["workflow_level"] = "L2_standard_team"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))
        upsert_task(str(self.tmp), "TASK-001", "Touch hotspot", status="ready", allowed_write=["src/shared.py"])
        result = activate_task(str(self.tmp), "TASK-001")

        self.assertFalse(result["activated"])
        self.assertTrue(any("repeated-change hotspot" in b for b in result["blockers"]))

    def test_repeated_hotspot_allows_activation_with_architecture_brief(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        (self.tmp / ".aiwf" / "history" / "task-history.json").write_text(json.dumps({
            "tasks": [
                {"id": "t1", "changed_files": ["src/shared.py"], "fix_loop_attempt_count": 0, "untested_risk_count": 0},
                {"id": "t2", "changed_files": ["src/shared.py"], "fix_loop_attempt_count": 0, "untested_risk_count": 0},
                {"id": "t3", "changed_files": ["src/shared.py"], "fix_loop_attempt_count": 0, "untested_risk_count": 0},
            ]
        }, indent=2))
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["workflow_level"] = "L2_standard_team"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))
        goal = json.loads((self.tmp / ".aiwf" / "state" / "goal.json").read_text())
        goal["quality_brief"]["architecture_brief"]["target_structure"] = "Stabilize shared module boundary"
        goal["quality_brief"]["evaluation_contract"].update({
            "user_visible_outcome": "Hotspot change works",
            "acceptance_criteria": ["behavior verified"],
            "test_obligations": ["run regression tests"],
            "review_obligations": ["review hotspot impact"],
        })
        (self.tmp / ".aiwf" / "state" / "goal.json").write_text(json.dumps(goal, indent=2))
        upsert_task(str(self.tmp), "TASK-001", "Touch hotspot", status="ready", allowed_write=["src/shared.py"])
        result = activate_task(str(self.tmp), "TASK-001")

        self.assertTrue(result["activated"], result["blockers"])

    def test_fix_loop_trend_mechanically_upgrades_to_l2_before_activation(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        (self.tmp / ".aiwf" / "history" / "task-history.json").write_text(json.dumps({
            "tasks": [
                {"id": "t1", "changed_files": ["src/a.py"], "fix_loop_attempt_count": 1, "untested_risk_count": 0},
                {"id": "t2", "changed_files": ["src/b.py"], "fix_loop_attempt_count": 2, "untested_risk_count": 0},
            ]
        }, indent=2))
        self._seed_l2_contracts()
        upsert_task(str(self.tmp), "TASK-001", "Next", status="ready")
        result = activate_task(str(self.tmp), "TASK-001")

        self.assertTrue(result["activated"], result["blockers"])
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        self.assertEqual(state["workflow_level"], "L2_standard_team")
        self.assertEqual(state["test_template"], "regression_plus_boundary_adverse")
        self.assertEqual(state["review_template"], "standard_review")

    def test_stale_current_state_blocks_activation(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        current = self.tmp / ".aiwf" / "reports" / "当前状态.md"
        current.parent.mkdir(parents=True, exist_ok=True)
        current.write_text(
            "# AIWF Current State\n\n"
            "## Goal & Intent\n- Goal: test\n\n"
            "## Current Status\n- Phase: planned\n\n"
            "## Quality Snapshot\n- Testing: unknown\n\n"
            "## Raw References\n- state/state.json\n",
            encoding="utf-8",
        )
        time.sleep(0.02)
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["phase"] = "planned"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))
        upsert_task(str(self.tmp), "TASK-001", "A", status="ready")
        result = activate_task(str(self.tmp), "TASK-001")

        self.assertFalse(result["activated"])
        self.assertTrue(any("current-state.md is stale" in b for b in result["blockers"]))
        after = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        self.assertEqual(after["phase"], "planned")
        self.assertIsNone(after.get("active_task_id"))

    def test_suspend_task_saves_and_restore_state_snapshot(self):
        from aiwf_core.core.task_ledger import activate_task, suspend_task, upsert_task

        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["workflow_level"] = "L2_standard_team"
        state["test_template"] = "regression_plus_boundary_adverse"
        state["active_context_id"] = "CTX-SUSPEND"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))
        self._seed_l2_contracts()
        upsert_task(str(self.tmp), "TASK-001", "Suspend me", status="ready")
        self.assertTrue(activate_task(str(self.tmp), "TASK-001")["activated"])
        suspended = suspend_task(str(self.tmp), "TASK-001", note="pause")
        self.assertTrue(suspended["suspended"])
        task = suspended["task"]
        self.assertEqual(task["suspended_context"]["workflow_level"], "L2_standard_team")

        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["workflow_level"] = "L1_review_light"
        state["active_context_id"] = None
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))
        self.assertTrue(activate_task(str(self.tmp), "TASK-001")["activated"])
        restored = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        self.assertEqual(restored["workflow_level"], "L2_standard_team")
        self.assertEqual(restored["active_context_id"], "CTX-SUSPEND")

    def test_active_task_quality_warning_in_user_prompt_submit(self):
        self._run("task", "plan", "--task-id", "TASK-001", "--title", "Hot", "--status", "ready", "--allowed-write", "src/shared.py")
        self._run("task", "activate", "TASK-001")
        (self.tmp / ".aiwf" / "history" / "task-history.json").write_text(json.dumps({
            "tasks": [
                {"id": "t1", "changed_files": ["src/shared.py"], "fix_loop_attempt_count": 0, "untested_risk_count": 0},
                {"id": "t2", "changed_files": ["src/shared.py"], "fix_loop_attempt_count": 0, "untested_risk_count": 0},
                {"id": "t3", "changed_files": ["src/shared.py"], "fix_loop_attempt_count": 0, "untested_risk_count": 0},
            ]
        }, indent=2))
        inp = json.dumps({"session_id": "t", "cwd": str(self.tmp), "hook_event_name": "UserPromptSubmit"})
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_status.py")],
                           input=inp, capture_output=True, text=True,
                           cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        ctx = json.loads(r.stdout.strip())["hookSpecificOutput"]["additionalContext"]

        self.assertIn("ACTIVE TASK QUALITY WARNING: TASK-001 hits hotspot src/shared.py", ctx)

    def test_cli_task_plan_and_status(self):
        r = self._run("task", "plan", "--task-id", "TASK-001", "--title", "Scaffold", "--status", "ready")
        self.assertEqual(r.returncode, 0)
        self.assertIn("Task recorded", r.stdout)
        status = self._run("task", "status")
        self.assertIn("ready: 1", status.stdout)


if __name__ == "__main__":
    unittest.main()
