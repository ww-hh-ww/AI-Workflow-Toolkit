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
            "runtime/history/task-ledger.json",
            "runtime/history/task-history.json",
            "artifacts/reports/当前状态.md",
            "artifacts/reports/质量摘要.md",
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

    def _seed_plan(self, task_id, allowed_write=None):
        """Create a registry-backed plan artifact so L1+ activation can pass."""
        from aiwf_core.core.state.plan_ops import upsert_plan

        plan_id = f"PLAN-{task_id}"
        plan_dir = self.tmp / ".aiwf" / "artifacts" / "plans"
        plan_dir.mkdir(parents=True, exist_ok=True)
        plan_path = plan_dir / f"{plan_id}.md"
        if not plan_path.exists():
            plan_path.write_text(
                f"# {plan_id}\n\n"
                "> AI working plan.\n\n"
                f"Plan ID: {plan_id}\n"
                "Parent Goal: GOAL-001\n"
                f"Task IDs: {task_id}\n\n"
                "## Goal\nTest task\n\n"
                "## Route\n- How: direct fix\n\n"
                "## Scope\n- Change: test files\n\n"
                "## Risks\n- none\n\n"
                "## Verification\n- Machine-verifiable: yes\n\n"
                "## Impact\n- docs: no — test\n- project_map: no — test\n- environment: no — test\n- capabilities: no — test\n- quality_summary: no — test\n\n"
                "## Done Means\n- test passes\n\n"
                "## Goal Progress\n- Parent goal: test\n\n"
                "## Next Steps\n1. done\n",
                encoding="utf-8",
            )
        kwargs = {"goal_id": "GOAL-001", "task_ids": [task_id], "plan_kind": "implementation", "work_intent": "feature"}
        if allowed_write is not None:
            kwargs["allowed_write"] = allowed_write
        upsert_plan(str(self.tmp), plan_id, **kwargs)
        ledger_path = self.tmp / ".aiwf" / "runtime" / "history" / "task-ledger.json"
        if ledger_path.exists():
            ledger = json.loads(ledger_path.read_text())
            changed = False
            for task in ledger.get("tasks", []):
                if task.get("id") == task_id:
                    task["plan_id"] = plan_id
                    task["parent_plan"] = plan_id
                    task["goal_id"] = task.get("goal_id") or "GOAL-001"
                    task["parent_goal"] = task.get("parent_goal") or task["goal_id"]
                    changed = True
            if changed:
                ledger_path.write_text(json.dumps(ledger, indent=2) + "\n")
        return plan_id

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
        brief["non_goals"] = ["test"]
        goal_path.write_text(json.dumps(goal, indent=2))

    def _mark_prepare_close_passed(self, task_id):
        from aiwf_core.core.task_ledger import activate_task

        self._seed_plan(task_id)
        activate_task(str(self.tmp), task_id)
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["phase"] = "closed"
        state["closure_allowed"] = True
        state["active_task_id"] = task_id
        state["close_prepared_task_id"] = task_id
        state["close_prepared_at"] = ""
        state_path.write_text(json.dumps(state, indent=2) + "\n")
        ledger_path = self.tmp / ".aiwf" / "runtime" / "history" / "task-ledger.json"
        ledger = json.loads(ledger_path.read_text())
        for task in ledger.get("tasks", []):
            if task.get("id") == task_id:
                task["status"] = "active"
        ledger.setdefault("execution_window", {})["active_task_ids"] = [task_id]
        ledger_path.write_text(json.dumps(ledger, indent=2) + "\n")

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
        self._seed_plan("TASK-001")
        self.assertTrue(activate_task(str(self.tmp), "TASK-001")["activated"])
        self._seed_plan("TASK-002")
        second = activate_task(str(self.tmp), "TASK-002")

        self.assertFalse(second["activated"])
        self.assertTrue(any("active execution window" in b for b in second["blockers"]))

    def test_parallel_safe_allows_non_overlapping_active_tasks(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        upsert_task(str(self.tmp), "TASK-001", "A", status="ready")
        upsert_task(str(self.tmp), "TASK-002", "B", status="ready", parallel_safe=True)
        self._seed_plan("TASK-001", allowed_write=["src/a.py"])
        self.assertTrue(activate_task(str(self.tmp), "TASK-001")["activated"])
        self._seed_plan("TASK-002", allowed_write=["src/b.py"])
        second = activate_task(str(self.tmp), "TASK-002")

        self.assertTrue(second["activated"], second["blockers"])

    def test_parallel_safe_blocks_write_boundary_overlap(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        upsert_task(str(self.tmp), "TASK-001", "A", status="ready")
        upsert_task(str(self.tmp), "TASK-002", "B", status="ready", parallel_safe=True)
        self._seed_plan("TASK-001", allowed_write=["src/shared.py"])
        self.assertTrue(activate_task(str(self.tmp), "TASK-001")["activated"])
        self._seed_plan("TASK-002", allowed_write=["src/shared.py"])
        second = activate_task(str(self.tmp), "TASK-002")

        self.assertFalse(second["activated"])
        self.assertTrue(any("write boundary conflict" in b for b in second["blockers"]))

    def test_dependency_must_be_closed_before_activation(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        upsert_task(str(self.tmp), "TASK-001", "Scaffold", status="ready")
        upsert_task(str(self.tmp), "TASK-002", "Fill", status="ready", dependencies=["TASK-001"])
        self._seed_plan("TASK-002")
        self.assertFalse(activate_task(str(self.tmp), "TASK-002")["activated"])
        upsert_task(str(self.tmp), "TASK-001", "Scaffold", status="closed")
        self._seed_plan("TASK-002")
        self.assertTrue(activate_task(str(self.tmp), "TASK-002")["activated"])

    def test_plan_attach_updates_task_ledger_authority(self):
        """plan attach must satisfy the L1+ task.plan_id activation gate."""
        from aiwf_core.core.state.plan_ops import attach_task_to_plan, upsert_plan
        from aiwf_core.core.task_ledger import activate_task, load_ledger, upsert_task

        upsert_task(str(self.tmp), "TASK-001", "Attach me", status="ready", allowed_write=["README.md"])
        plan_dir = self.tmp / ".aiwf" / "artifacts" / "plans"
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "PLAN-001.md").write_text(
            "# PLAN-001\n\n"
            "## Impact\n"
            "- docs: no — test\n"
            "- project_map: no — test\n"
            "- environment: no — test\n"
            "- capabilities: no — test\n"
            "- quality_summary: no — test\n",
            encoding="utf-8",
        )
        upsert_plan(str(self.tmp), "PLAN-001", goal_id="GOAL-001", status="ready")

        result = attach_task_to_plan(str(self.tmp), "PLAN-001", "TASK-001")
        self.assertTrue(result["attached"], result.get("reason"))
        task = load_ledger(str(self.tmp))["tasks"][0]
        self.assertEqual(task["plan_id"], "PLAN-001")
        self.assertEqual(task["parent_plan"], "PLAN-001")

        activated = activate_task(str(self.tmp), "TASK-001")
        self.assertTrue(activated["activated"], activated["blockers"])
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        self.assertEqual(state["phase"], "implementing")

    def test_close_task_appends_task_history_and_quality_escalation(self):
        from aiwf_core.core.task_ledger import close_task, upsert_task

        upsert_task(str(self.tmp), "TASK-001", "Scaffold", status="ready")
        (self.tmp / ".aiwf" / "artifacts" / "evidence" / "records.json").write_text(json.dumps({
            "records": [{"id": "EV-001", "status": "accepted", "changed_files": ["src/a.py"]}]
        }, indent=2))
        (self.tmp / ".aiwf" / "artifacts" / "quality" / "testing.json").write_text(json.dumps({
            "status": "adequate", "untested_risks": ["manual UI"]
        }, indent=2))
        self._mark_prepare_close_passed("TASK-001")
        result = close_task(str(self.tmp), "TASK-001")

        self.assertTrue(result["closed"])
        history = json.loads((self.tmp / ".aiwf" / "runtime" / "history" / "task-history.json").read_text())
        self.assertEqual(history["tasks"][-1]["id"], "TASK-001")
        self.assertIn("src/a.py", history["tasks"][-1]["changed_files"])
        # Machine-only history is always appended; quality digest markdown is NOT auto-written
        # (controlled by Impact.quality_summary)
        self.assertFalse((self.tmp / ".aiwf" / "artifacts" / "reports" / "质量摘要.md").exists(),
                         "Quality digest should NOT be auto-written on close; Impact.quality_summary controls it")

    def test_ready_task_cannot_close_without_activation(self):
        from aiwf_core.core.task_ledger import close_task, upsert_task

        upsert_task(str(self.tmp), "TASK-001", "Not active", status="ready")
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["phase"] = "closed"
        state["closure_allowed"] = True
        state["active_task_id"] = "TASK-001"
        state["close_prepared_task_id"] = "TASK-001"
        state_path.write_text(json.dumps(state, indent=2) + "\n")

        result = close_task(str(self.tmp), "TASK-001")

        self.assertFalse(result["closed"])
        self.assertTrue(any("not active" in b for b in result["blockers"]))

    def test_task_history_archives_trimmed_hotspots(self):
        from aiwf_core.core.cross_task_quality import append_task_history_from_state

        old_tasks = [
            {"id": f"old-{i}", "changed_files": ["src/ancient.py"], "fix_loop_attempt_count": 0, "untested_risk_count": 0}
            for i in range(101)
        ]
        (self.tmp / ".aiwf" / "runtime" / "history" / "task-history.json").write_text(json.dumps({"tasks": old_tasks}, indent=2))
        append_task_history_from_state(str(self.tmp), task_id="TASK-NEW", title="New")
        history = json.loads((self.tmp / ".aiwf" / "runtime" / "history" / "task-history.json").read_text())

        self.assertEqual(len(history["tasks"]), 100)
        self.assertGreaterEqual(history["archived_hotspots"]["src/ancient.py"], 2)

    def test_close_task_sets_cross_task_escalation_flag(self):
        from aiwf_core.core.task_ledger import close_task, upsert_task

        (self.tmp / ".aiwf" / "runtime" / "history" / "task-history.json").write_text(json.dumps({
            "tasks": [
                {"id": "t1", "changed_files": ["src/a.py"], "fix_loop_attempt_count": 1, "untested_risk_count": 0},
                {"id": "t2", "changed_files": ["src/b.py"], "fix_loop_attempt_count": 2, "untested_risk_count": 0},
            ]
        }, indent=2))
        upsert_task(str(self.tmp), "TASK-001", "Close with trend", status="ready")
        self._mark_prepare_close_passed("TASK-001")
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["workflow_level"] = "L0_direct"
        state_path.write_text(json.dumps(state, indent=2) + "\n")
        result = close_task(str(self.tmp), "TASK-001")
        self.assertTrue(result["closed"], result["blockers"])
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())

        self.assertTrue(state["cross_task_quality_escalation_required"])

    def test_repeated_hotspot_blocks_activation_without_architecture_brief(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        (self.tmp / ".aiwf" / "runtime" / "history" / "task-history.json").write_text(json.dumps({
            "tasks": [
                {"id": "t1", "changed_files": ["src/shared.py"], "fix_loop_attempt_count": 0, "untested_risk_count": 0},
                {"id": "t2", "changed_files": ["src/shared.py"], "fix_loop_attempt_count": 0, "untested_risk_count": 0},
                {"id": "t3", "changed_files": ["src/shared.py"], "fix_loop_attempt_count": 0, "untested_risk_count": 0},
            ]
        }, indent=2))
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["workflow_level"] = "L2_standard_team"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))
        upsert_task(str(self.tmp), "TASK-001", "Touch hotspot", status="ready")
        self._seed_plan("TASK-001", allowed_write=["src/shared.py"])
        result = activate_task(str(self.tmp), "TASK-001")

        self.assertFalse(result["activated"])
        self.assertTrue(any("repeated-change hotspot" in b for b in result["blockers"]))

    def test_repeated_hotspot_allows_activation_with_architecture_brief(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        (self.tmp / ".aiwf" / "runtime" / "history" / "task-history.json").write_text(json.dumps({
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
        goal["quality_brief"]["non_goals"] = ["test"]
        (self.tmp / ".aiwf" / "state" / "goal.json").write_text(json.dumps(goal, indent=2))
        upsert_task(str(self.tmp), "TASK-001", "Touch hotspot", status="ready")
        self._seed_plan("TASK-001", allowed_write=["src/shared.py"])
        result = activate_task(str(self.tmp), "TASK-001")

        self.assertTrue(result["activated"], result["blockers"])

    def test_fix_loop_trend_quality_blocker_requires_l2(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        (self.tmp / ".aiwf" / "runtime" / "history" / "task-history.json").write_text(json.dumps({
            "tasks": [
                {"id": "t1", "changed_files": ["src/a.py"], "fix_loop_attempt_count": 1, "untested_risk_count": 0},
                {"id": "t2", "changed_files": ["src/b.py"], "fix_loop_attempt_count": 2, "untested_risk_count": 0},
            ]
        }, indent=2))
        self._seed_l2_contracts()
        # Pre-set L2 — quality blocker requires L2+ for fix_loop_trend hard constraint
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["workflow_level"] = "L2_standard_team"
        state_path.write_text(json.dumps(state, indent=2))

        upsert_task(str(self.tmp), "TASK-001", "Next", status="ready")
        self._seed_plan("TASK-001")
        result = activate_task(str(self.tmp), "TASK-001")

        self.assertTrue(result["activated"], result["blockers"])
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        # Routing respects the pre-set L2 level (downgrade_allowed path)
        self.assertEqual(state["workflow_level"], "L2_standard_team")

    def test_suspend_task_saves_and_restore_state_snapshot(self):
        from aiwf_core.core.task_ledger import activate_task, suspend_task, upsert_task

        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["workflow_level"] = "L2_standard_team"
        state["test_template"] = "regression_plus_boundary_adverse"
        state["active_context_id"] = "CTX-SUSPEND"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))
        self._seed_l2_contracts()
        upsert_task(str(self.tmp), "TASK-001", "Suspend me", status="ready")
        self._seed_plan("TASK-001")
        self.assertTrue(activate_task(str(self.tmp), "TASK-001")["activated"])
        suspended = suspend_task(str(self.tmp), "TASK-001", note="pause")
        self.assertTrue(suspended["suspended"])
        task = suspended["task"]
        self.assertEqual(task["suspended_context"]["workflow_level"], "L2_standard_team")

        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["workflow_level"] = "L1_review_light"
        state["active_context_id"] = None
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))
        self._seed_plan("TASK-001")
        self.assertTrue(activate_task(str(self.tmp), "TASK-001")["activated"])
        restored = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        self.assertEqual(restored["workflow_level"], "L2_standard_team")
        self.assertEqual(restored["active_context_id"], "CTX-SUSPEND")

    def test_active_task_quality_warning_in_user_prompt_submit(self):
        self._run("plan", "create", "PLAN-TASK-001", "--goal-id", "GOAL-001", "--task", "TASK-001")
        self._run("task", "plan", "--task-id", "TASK-001", "--title", "Hot", "--status", "ready",
                  "--allowed-write", "src/shared.py", "--plan", "PLAN-TASK-001", "--goal", "GOAL-001")
        self._run("task", "activate", "TASK-001")
        (self.tmp / ".aiwf" / "runtime" / "history" / "task-history.json").write_text(json.dumps({
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

        # Diet: hotspot warnings are in --debug mode only, not in default short context
        # Short context shows only phase, task, health, primary, forbidden, anchor
        self.assertIn("[AIWF]", ctx)
        self.assertIn("TASK-001", ctx)

    def test_cli_task_plan_and_status(self):
        r = self._run("task", "plan", "--task-id", "TASK-001", "--title", "Scaffold", "--status", "ready")
        self.assertEqual(r.returncode, 0)
        self.assertIn("Task recorded", r.stdout)
        status = self._run("task", "status")
        self.assertIn("ready: 1", status.stdout)

    def test_cli_task_plan_accepts_positional_task_id(self):
        r = self._run("task", "plan", "TASK-POS", "--title", "Positional", "--status", "ready")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Task recorded: TASK-POS", r.stdout)
        status = self._run("task", "status")
        self.assertIn("ready: 1", status.stdout)

    # ── P0-2: Task activation requires plan for the same task ID ──

    def test_task_activation_rejects_mismatched_active_plan(self):
        """TASK-002 cannot activate using TASK-001's plan."""
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        # Clean any leftover plan files from other tests
        plan_dir = self.tmp / ".aiwf" / "artifacts" / "plans"
        for f in list(plan_dir.glob("*.md")):
            f.unlink()

        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["workflow_level"] = "L1_review_light"
        state["request_mode"] = "execution"
        state["active_plan_id"] = "PLAN-TASK-001"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))

        # Create plan for TASK-001 only
        self._seed_plan("TASK-001")

        # Register TASK-002 without its own plan
        upsert_task(str(self.tmp), "TASK-002", "Should not activate", status="ready",
                    allowed_write=["test.py"])

        result = activate_task(str(self.tmp), "TASK-002")
        self.assertFalse(result["activated"],
                         "TASK-002 should not activate with TASK-001's plan")
        self.assertTrue(any("has no plan_id" in b or "registry-backed plan" in b for b in result["blockers"]),
                        f"Should require TASK-002's plan, got: {result['blockers']}")

    def test_task_activation_requires_plan_for_same_task_id(self):
        """Activation only succeeds when the plan matches the task ID."""
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["workflow_level"] = "L1_review_light"
        state["request_mode"] = "execution"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))

        # Create plan AND task for TASK-001
        self._seed_plan("TASK-001")
        upsert_task(str(self.tmp), "TASK-001", "Should activate", status="ready",
                    allowed_write=["test.py"], plan_id="PLAN-TASK-001", goal_id="GOAL-001")

        result = activate_task(str(self.tmp), "TASK-001")
        self.assertTrue(result["activated"],
                        f"TASK-001 with its own plan should activate, got: {result['blockers']}")


if __name__ == "__main__":
    unittest.main()
