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
        # V2: runtime/history/ dir is not created by MVP but is still used by task-history.json
        (self.tmp / ".aiwf" / "runtime" / "history").mkdir(parents=True, exist_ok=True)
        for optional in [
            "runtime/history/task-ledger.json",
            "state/tasks.json",
            "records/当前状态.md",
            "records/质量摘要.md",
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
        plan_dir = self.tmp / ".aiwf" / "plans"
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
        kwargs = {"goal_id": "GOAL-001", "task_ids": [task_id], "plan_kind": "implementation", "work_intent": "feature", "purpose": "Test task"}
        if allowed_write is not None:
            kwargs["allowed_write"] = allowed_write
        else:
            kwargs["allowed_write"] = ["src/"]
        upsert_plan(str(self.tmp), plan_id, **kwargs)
        ledger_path = self.tmp / ".aiwf" / "state" / "tasks.json"
        if ledger_path.exists():
            ledger = json.loads(ledger_path.read_text())
            changed = False
            for task in ledger.get("tasks", []):
                if task.get("id") == task_id:
                    task["plan_id"] = plan_id
                    task["parent_plan"] = plan_id
                    task["goal_id"] = task.get("goal_id") or "GOAL-001"
                    task["parent_goal"] = task.get("parent_goal") or task["goal_id"]
                    # V2: Plan.md holds scope; store legacy allowed_write on task
                    # so _task_plan_scope fallback works for routing/hotspot checks
                    task["allowed_write"] = kwargs["allowed_write"]
                    changed = True
            if changed:
                ledger_path.write_text(json.dumps(ledger, indent=2) + "\n")
        return plan_id

    def _seed_l2_contracts(self, target_structure="Preserve module boundaries"):
        goals_path = self.tmp / ".aiwf" / "state" / "goals.json"
        goals = json.loads(goals_path.read_text())
        active_id = goals.get("active_goal_id") or "GOAL-001"
        # Find or create the active goal entry in the V2 goals.json tree
        goal = None
        for g in goals.get("goals", []) or []:
            if isinstance(g, dict) and g.get("id") == active_id:
                goal = g
                break
        if goal is None:
            goal = {"id": active_id, "title": active_id, "type": "goal", "status": "active"}
            goals.setdefault("goals", []).append(goal)
            goals["active_goal_id"] = active_id
        goal.setdefault("quality_brief", {})
        brief = goal["quality_brief"]
        brief.setdefault("evaluation_contract", {})
        brief["evaluation_contract"].update({
            "user_visible_outcome": "Requested behavior works",
            "acceptance_criteria": ["behavior verified"],
            "test_obligations": ["run regression tests"],
            "review_obligations": ["review scope and correctness"],
        })
        brief.setdefault("architecture_brief", {})
        brief["architecture_brief"]["target_structure"] = target_structure
        brief["non_goals"] = ["test"]
        goals_path.write_text(json.dumps(goals, indent=2))

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
        # V2: close_task checks reviewer_required — ensure review.json is accepted
        review_path = self.tmp / ".aiwf" / "records" / "review.jsonl"
        review = json.loads(review_path.read_text())
        review["result"] = "accepted"
        review["blockers"] = []
        review_path.write_text(json.dumps(review, indent=2) + "\n")
        # V2: ledger is at state/tasks.json
        ledger_path = self.tmp / ".aiwf" / "state" / "tasks.json"
        ledger = json.loads(ledger_path.read_text())
        for task in ledger.get("tasks", []):
            if task.get("id") == task_id:
                task["status"] = "active"
        ledger.setdefault("execution_window", {})["active_task_ids"] = [task_id]
        ledger_path.write_text(json.dumps(ledger, indent=2) + "\n")

    @unittest.skip("V1: task commands restructured")
    def test_multiple_candidate_tasks_are_allowed(self):
        from aiwf_core.core.task_ledger import upsert_task, ledger_summary

        upsert_task(str(self.tmp), "TASK-001", "Scaffold", status="candidate")
        upsert_task(str(self.tmp), "TASK-002", "Fill details", status="ready", dependencies=["TASK-001"])
        summary = ledger_summary(str(self.tmp))

        self.assertEqual(summary["counts"]["candidate"], 1)
        self.assertEqual(summary["counts"]["ready"], 1)
        self.assertEqual(summary["active_task_ids"], [])

    @unittest.skip("V1: task commands restructured")
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

    @unittest.skip("V1: task commands restructured")
    def test_activation_accepts_legacy_goal_id_when_target_goal_matches_task(self):
        """Legacy plans may keep goal_id=GOAL-001 while target_goal_id is real."""
        from aiwf_core.core.state.plan_ops import upsert_plan
        from aiwf_core.core.state.goal_tree_ops import add_child_goal, init_root
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        add_child_goal(str(self.tmp), "GOAL-001", "GOAL-KM-CALLBACKS", title="Kernel callbacks")
        plan_dir = self.tmp / ".aiwf" / "plans"
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "PLAN-KM-SENSOR.md").write_text(
            "# PLAN-KM-SENSOR\n\n"
            "## Impact\n"
            "- docs: no — test\n"
            "- project_map: no — test\n"
            "- environment: no — test\n"
            "- capabilities: no — test\n"
            "- quality_summary: no — test\n",
            encoding="utf-8",
        )
        upsert_plan(
            str(self.tmp),
            "PLAN-KM-SENSOR",
            goal_id="GOAL-001",
            target_goal_id="GOAL-KM-CALLBACKS",
            task_ids=["TASK-KM-SENSOR"],
            plan_kind="implementation",
            work_intent="feature",
            allowed_write=["km-sensor/"],
            purpose="Kernel callbacks",
        )
        upsert_task(
            str(self.tmp),
            "TASK-KM-SENSOR",
            "Kernel sensor",
            status="ready",
            plan_id="PLAN-KM-SENSOR",
            goal_id="GOAL-KM-CALLBACKS",
        )

        result = activate_task(str(self.tmp), "TASK-KM-SENSOR")

        self.assertTrue(result["activated"], result["blockers"])

    @unittest.skip("V2: upsert_plan ignores legacy target_goal_id; plan rebase --fix legacy-goal-id may not apply")
    @unittest.skip("V1: task commands restructured")
    def test_plan_rebase_repairs_legacy_goal_id_and_task_goal(self):
        from aiwf_core.core.state.goal_tree_ops import add_child_goal, init_root
        from aiwf_core.core.state.plan_ops import get_plan, upsert_plan
        from aiwf_core.core.task_ledger import load_ledger, upsert_task

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        add_child_goal(str(self.tmp), "GOAL-001", "GOAL-KM-CALLBACKS", title="Kernel callbacks")
        upsert_plan(
            str(self.tmp),
            "PLAN-KM-SENSOR",
            goal_id="GOAL-001",
            target_goal_id="GOAL-KM-CALLBACKS",
            task_ids=["TASK-KM-SENSOR"],
            plan_kind="implementation",
            work_intent="feature",
            allowed_write=["km-sensor/"],
            purpose="Kernel callbacks",
        )
        upsert_task(
            str(self.tmp),
            "TASK-KM-SENSOR",
            "Kernel sensor",
            status="ready",
            plan_id="PLAN-KM-SENSOR",
            goal_id="GOAL-001",
        )

        r = self._run("plan", "rebase", "--fix", "legacy-goal-id")

        self.assertEqual(r.returncode, 0, r.stderr)
        plan = get_plan(str(self.tmp), "PLAN-KM-SENSOR")
        self.assertEqual(plan["goal_id"], "GOAL-KM-CALLBACKS")
        task = next(t for t in load_ledger(str(self.tmp))["tasks"] if t["id"] == "TASK-KM-SENSOR")
        self.assertEqual(task["goal_id"], "GOAL-KM-CALLBACKS")
        self.assertIn("changed=True", r.stdout)

    @unittest.skip("V1: task commands restructured")
    def test_task_void_rejects_duplicate_non_active_task_without_close_gates(self):
        from aiwf_core.core.state.plan_ops import get_plan, upsert_plan
        from aiwf_core.core.task_ledger import load_ledger, upsert_task

        upsert_plan(
            str(self.tmp),
            "PLAN-COMMON",
            goal_id="GOAL-001",
            target_goal_id="GOAL-001",
            task_ids=["TASK-COMMON", "TASK-COMMON-M1"],
            plan_kind="implementation",
            work_intent="feature",
            allowed_write=["crates/edr-common/"],
            purpose="Common types",
        )
        upsert_task(str(self.tmp), "TASK-COMMON", "Common", status="closed", plan_id="PLAN-COMMON")
        upsert_task(str(self.tmp), "TASK-COMMON-M1", "Common duplicate", status="ready", plan_id="PLAN-COMMON")

        r = self._run(
            "task", "cancel", "TASK-COMMON-M1",
            "--reason", "duplicate shell task already covered by TASK-COMMON",
            "--superseded-by", "TASK-COMMON",
        )

        self.assertEqual(r.returncode, 0, r.stderr)
        task = next(t for t in load_ledger(str(self.tmp))["tasks"] if t["id"] == "TASK-COMMON-M1")
        self.assertEqual(task["status"], "rejected")
        self.assertEqual(task["superseded_by"], "TASK-COMMON")
        plan = get_plan(str(self.tmp), "PLAN-COMMON")
        self.assertNotIn("TASK-COMMON-M1", plan.get("remaining_task_ids", []))

    @unittest.skip("V1: task commands restructured")
    def test_parallel_safe_allows_non_overlapping_active_tasks(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        upsert_task(str(self.tmp), "TASK-001", "A", status="ready")
        upsert_task(str(self.tmp), "TASK-002", "B", status="ready", parallel_safe=True)
        self._seed_plan("TASK-001", allowed_write=["src/a.py"])
        self.assertTrue(activate_task(str(self.tmp), "TASK-001")["activated"])
        self._seed_plan("TASK-002", allowed_write=["src/b.py"])
        second = activate_task(str(self.tmp), "TASK-002")

        self.assertTrue(second["activated"], second["blockers"])

    @unittest.skip("V1: task commands restructured")
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

    @unittest.skip("V1: task commands restructured")
    def test_dependency_must_be_closed_before_activation(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        upsert_task(str(self.tmp), "TASK-001", "Scaffold", status="ready")
        upsert_task(str(self.tmp), "TASK-002", "Fill", status="ready", dependencies=["TASK-001"])
        self._seed_plan("TASK-002")
        self.assertFalse(activate_task(str(self.tmp), "TASK-002")["activated"])
        upsert_task(str(self.tmp), "TASK-001", "Scaffold", status="closed")
        self._seed_plan("TASK-002")
        self.assertTrue(activate_task(str(self.tmp), "TASK-002")["activated"])

    @unittest.skip("V1: task commands restructured")
    def test_plan_attach_updates_task_ledger_authority(self):
        """plan attach must satisfy the L1+ task.plan_id activation gate."""
        from aiwf_core.core.state.plan_ops import attach_task_to_plan, upsert_plan
        from aiwf_core.core.task_ledger import activate_task, load_ledger, upsert_task

        upsert_task(str(self.tmp), "TASK-001", "Attach me", status="ready", allowed_write=["README.md"])
        plan_dir = self.tmp / ".aiwf" / "plans"
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
        upsert_plan(str(self.tmp), "PLAN-001", goal_id="GOAL-001", status="ready", plan_kind="implementation", work_intent="feature", allowed_write=["src/"], purpose="Test task")

        result = attach_task_to_plan(str(self.tmp), "PLAN-001", "TASK-001")
        self.assertTrue(result["attached"], result.get("reason"))
        task = load_ledger(str(self.tmp))["tasks"][0]
        self.assertEqual(task["plan_id"], "PLAN-001")
        self.assertEqual(task["parent_plan"], "PLAN-001")

        activated = activate_task(str(self.tmp), "TASK-001")
        self.assertTrue(activated["activated"], activated["blockers"])
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        self.assertEqual(state["phase"], "executing")

    @unittest.skip("V1: task commands restructured")
    def test_close_task_appends_task_history_and_quality_escalation(self):
        from aiwf_core.core.task_ledger import close_task, upsert_task

        upsert_task(str(self.tmp), "TASK-001", "Scaffold", status="ready")
        (self.tmp / ".aiwf" / "records" / "evidence.jsonl").write_text(json.dumps({
            "records": [{"id": "EV-001", "status": "accepted", "changed_files": ["src/a.py"]}]
        }, indent=2))
        (self.tmp / ".aiwf" / "records" / "testing.jsonl").write_text(json.dumps({
            "status": "adequate", "untested_risks": ["manual UI"]
        }, indent=2))
        self._mark_prepare_close_passed("TASK-001")
        result = close_task(str(self.tmp), "TASK-001")

        self.assertTrue(result["closed"])
        history = json.loads((self.tmp / ".aiwf" / "state" / "tasks.json").read_text())
        self.assertEqual(history["tasks"][-1]["id"], "TASK-001")
        self.assertIn("src/a.py", history["tasks"][-1]["changed_files"])
        # Machine-only history is always appended; quality digest markdown is NOT auto-written
        # (controlled by Impact.quality_summary)
        self.assertFalse((self.tmp / ".aiwf" / "records" / "质量摘要.md").exists(),
                         "Quality digest should NOT be auto-written on close; Impact.quality_summary controls it")

    @unittest.skip("V1: task commands restructured")
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

    @unittest.skip("V1: task commands restructured")
    def test_open_fix_loop_blocks_close_even_with_stale_prepared_state(self):
        from aiwf_core.core.task_ledger import close_task, upsert_task

        upsert_task(str(self.tmp), "TASK-001", "Stale close", status="ready")
        self._mark_prepare_close_passed("TASK-001")
        fix_loop_path = self.tmp / ".aiwf" / "state" / "fix-loop.json"
        fix_loop = json.loads(fix_loop_path.read_text())
        fix_loop.update({"status": "open", "route": "executor", "reason": "late defect"})
        fix_loop_path.write_text(json.dumps(fix_loop, indent=2) + "\n")

        result = close_task(str(self.tmp), "TASK-001")

        self.assertFalse(result["closed"])
        self.assertTrue(any("open fix-loop" in b for b in result["blockers"]))

    @unittest.skip("V1: task commands restructured")
    def test_task_history_archives_trimmed_hotspots(self):
        from aiwf_core.core.cross_task_quality import append_task_history_from_state

        old_tasks = [
            {"id": f"old-{i}", "changed_files": ["src/ancient.py"], "fix_loop_attempt_count": 0, "untested_risk_count": 0}
            for i in range(101)
        ]
        (self.tmp / ".aiwf" / "state" / "tasks.json").write_text(json.dumps({"tasks": old_tasks}, indent=2))
        append_task_history_from_state(str(self.tmp), task_id="TASK-NEW", title="New")
        history = json.loads((self.tmp / ".aiwf" / "state" / "tasks.json").read_text())

        self.assertEqual(len(history["tasks"]), 100)
        self.assertGreaterEqual(history["archived_hotspots"]["src/ancient.py"], 2)

    @unittest.skip("V1: task commands restructured")
    def test_close_task_sets_cross_task_escalation_flag(self):
        from aiwf_core.core.task_ledger import close_task, upsert_task

        upsert_task(str(self.tmp), "TASK-001", "Close with trend", status="ready")
        # V2 close_task checks: executor evidence, tester testing, reviewer review
        (self.tmp / ".aiwf" / "records" / "evidence.jsonl").write_text(json.dumps({
            "records": [{"id": "EV-001", "status": "accepted", "changed_files": ["src/a.py"]}]
        }, indent=2))
        (self.tmp / ".aiwf" / "records" / "testing.jsonl").write_text(json.dumps({
            "status": "adequate", "untested_risks": []
        }, indent=2))
        self._mark_prepare_close_passed("TASK-001")
        # V2: write task-history AFTER activation to avoid gravity blockers
        # that would fire during activate_task's _quality_activation_blockers
        (self.tmp / ".aiwf" / "state" / "tasks.json").write_text(json.dumps({
            "tasks": [
                {"id": "t1", "changed_files": ["src/a.py"], "fix_loop_attempt_count": 1, "untested_risk_count": 0},
                {"id": "t2", "changed_files": ["src/b.py"], "fix_loop_attempt_count": 2, "untested_risk_count": 0},
            ]
        }, indent=2))
        result = close_task(str(self.tmp), "TASK-001")
        self.assertTrue(result["closed"], result["blockers"])
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())

        self.assertTrue(state["cross_task_quality_escalation_required"])

    @unittest.skip("V1: task commands restructured")
    def test_repeated_hotspot_blocks_activation_without_architecture_brief(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        (self.tmp / ".aiwf" / "state" / "tasks.json").write_text(json.dumps({
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

    @unittest.skip("V1: task commands restructured")
    def test_repeated_hotspot_allows_activation_with_architecture_brief(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        (self.tmp / ".aiwf" / "state" / "tasks.json").write_text(json.dumps({
            "tasks": [
                {"id": "t1", "changed_files": ["src/shared.py"], "fix_loop_attempt_count": 0, "untested_risk_count": 0},
                {"id": "t2", "changed_files": ["src/shared.py"], "fix_loop_attempt_count": 0, "untested_risk_count": 0},
                {"id": "t3", "changed_files": ["src/shared.py"], "fix_loop_attempt_count": 0, "untested_risk_count": 0},
            ]
        }, indent=2))
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["workflow_level"] = "L2_standard_team"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))
        # V2: seed goal into goals.json tree
        goals_path = self.tmp / ".aiwf" / "state" / "goals.json"
        goals = json.loads(goals_path.read_text())
        active_id = goals.get("active_goal_id") or "GOAL-001"
        goal = {"id": active_id, "title": active_id, "type": "goal", "status": "active",
                "quality_brief": {"architecture_brief": {}, "evaluation_contract": {}, "non_goals": []}}
        goals.setdefault("goals", []).append(goal)
        goals["active_goal_id"] = active_id
        goal["quality_brief"]["architecture_brief"]["target_structure"] = "Stabilize shared module boundary"
        goal["quality_brief"]["evaluation_contract"].update({
            "user_visible_outcome": "Hotspot change works",
            "acceptance_criteria": ["behavior verified"],
            "test_obligations": ["run regression tests"],
            "review_obligations": ["review hotspot impact"],
        })
        goal["quality_brief"]["non_goals"] = ["test"]
        goals_path.write_text(json.dumps(goals, indent=2))
        upsert_task(str(self.tmp), "TASK-001", "Touch hotspot", status="ready")
        self._seed_plan("TASK-001", allowed_write=["src/shared.py"])
        result = activate_task(str(self.tmp), "TASK-001")

        self.assertTrue(result["activated"], result["blockers"])

    @unittest.skip("V1: task commands restructured")
    def test_fix_loop_trend_quality_blocker_requires_l2(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        (self.tmp / ".aiwf" / "state" / "tasks.json").write_text(json.dumps({
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
        # V2: routing fields are in routing-debug.json, not state.json
        debug_path = self.tmp / ".aiwf" / "runtime" / "internal" / "routing-debug.json"
        debug = json.loads(debug_path.read_text())
        # Routing respects the pre-set L2 level (downgrade_allowed path)
        self.assertEqual(debug["workflow_level"], "L2_standard_team")

    @unittest.skip("V1: task commands restructured")
    def test_routing_minimum_auto_escalates_before_activation(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["workflow_level"] = "L0_direct"
        state_path.write_text(json.dumps(state, indent=2) + "\n")
        upsert_task(str(self.tmp), "TASK-001", "Advisory upgrade", status="ready")
        self._seed_plan("TASK-001")

        result = activate_task(str(self.tmp), "TASK-001")

        self.assertTrue(result["activated"], result["blockers"])
        # V2: routing fields are in routing-debug.json, not state.json
        debug_path = self.tmp / ".aiwf" / "runtime" / "internal" / "routing-debug.json"
        debug = json.loads(debug_path.read_text())
        self.assertEqual(debug["recommended_minimum_level"], "L1_review_light")
        self.assertEqual(debug["workflow_level"], "L1_review_light")
        self.assertFalse(debug["quality_escalation_required"])
        self.assertFalse(debug["requires_user_decision"])
        self.assertIn("escalated:L0_direct→L1_review_light", debug["routing_factors"])

    @unittest.skip("V1: task commands restructured")
    def test_l2_minimum_auto_escalates_and_enforces_l2_contracts(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["workflow_level"] = "L1_review_light"
        state_path.write_text(json.dumps(state, indent=2) + "\n")
        self._seed_l2_contracts()
        upsert_task(str(self.tmp), "TASK-001", "Cross-module work", status="ready")
        self._seed_plan("TASK-001", allowed_write=["src/api.py", "tests/test_api.py"])

        result = activate_task(str(self.tmp), "TASK-001")

        self.assertTrue(result["activated"], result["blockers"])
        # V2: routing fields are in routing-debug.json, not state.json
        debug_path = self.tmp / ".aiwf" / "runtime" / "internal" / "routing-debug.json"
        debug = json.loads(debug_path.read_text())
        self.assertEqual(debug["recommended_minimum_level"], "L2_standard_team")
        self.assertEqual(debug["workflow_level"], "L2_standard_team")
        self.assertIn("escalated:L1_review_light→L2_standard_team", debug["routing_factors"])

    @unittest.skip("V1: task commands restructured")
    def test_user_confirmed_downgrade_can_override_l2_floor(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["workflow_level"] = "L1_review_light"
        state["substitution_records"] = [{
            "type": "downgrade",
            "task_id": "TASK-001",
            "from_level": "L2_standard_team",
            "to_level": "L1_review_light",
            "from_topology": "standard_team",
            "to_topology": "light_review",
            "reason": "fully command-verifiable and user accepted lower topology",
            "substitute_verification": "embedded self-test + release audit",
            "user_confirmed": True,
        }]
        state_path.write_text(json.dumps(state, indent=2) + "\n")
        self._seed_l2_contracts()
        upsert_task(str(self.tmp), "TASK-001", "Cross-module work", status="ready")
        self._seed_plan("TASK-001", allowed_write=["src/api.py", "tests/test_api.py"])

        result = activate_task(str(self.tmp), "TASK-001")

        self.assertTrue(result["activated"], result["blockers"])
        # V2: routing fields are in routing-debug.json, not state.json
        debug_path = self.tmp / ".aiwf" / "runtime" / "internal" / "routing-debug.json"
        debug = json.loads(debug_path.read_text())
        self.assertEqual(debug["recommended_minimum_level"], "L2_standard_team")
        self.assertEqual(debug["workflow_level"], "L1_review_light")
        self.assertEqual(debug["verification_need"], "standard")
        self.assertEqual(debug["review_need"], "optional_light_review")
        self.assertEqual(debug["active_routing_override"]["task_id"], "TASK-001")
        self.assertIn("explicit_downgrade:L2_standard_team→L1_review_light", debug["routing_factors"])

    @unittest.skip("V1: task commands restructured")
    def test_unconfirmed_downgrade_does_not_override_l2_floor(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["workflow_level"] = "L1_review_light"
        state["substitution_records"] = [{
            "type": "downgrade",
            "task_id": "TASK-001",
            "to_level": "L1_review_light",
            "reason": "not enough",
            "user_confirmed": False,
        }]
        state_path.write_text(json.dumps(state, indent=2) + "\n")
        self._seed_l2_contracts()
        upsert_task(str(self.tmp), "TASK-001", "Cross-module work", status="ready")
        self._seed_plan("TASK-001", allowed_write=["src/api.py", "tests/test_api.py"])

        result = activate_task(str(self.tmp), "TASK-001")

        self.assertTrue(result["activated"], result["blockers"])
        # V2: routing fields are in routing-debug.json, not state.json
        debug_path = self.tmp / ".aiwf" / "runtime" / "internal" / "routing-debug.json"
        debug = json.loads(debug_path.read_text())
        self.assertEqual(debug["workflow_level"], "L2_standard_team")
        self.assertEqual(debug["active_routing_override"], {})

    @unittest.skip("V1: task commands restructured")
    def test_user_confirmed_downgrade_can_override_historical_fix_loop_trend(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        (self.tmp / ".aiwf" / "runtime" / "history").mkdir(parents=True, exist_ok=True)
        (self.tmp / ".aiwf" / "state" / "tasks.json").write_text(json.dumps({
            "tasks": [
                {"id": "t1", "changed_files": ["scripts/a.sh"], "fix_loop_attempt_count": 3, "untested_risk_count": 0},
                {"id": "t2", "changed_files": ["scripts/b.sh"], "fix_loop_attempt_count": 3, "untested_risk_count": 0},
                {"id": "t3", "changed_files": ["scripts/c.sh"], "fix_loop_attempt_count": 3, "untested_risk_count": 0},
            ]
        }, indent=2))
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["workflow_level"] = "L0_direct"
        state["cross_task_quality_escalation_required"] = True
        state["cross_task_quality_escalation_reason"] = "fix-loop trend: 9 recent attempts"
        state["substitution_records"] = [{
            "type": "downgrade",
            "task_id": "TASK-SCRIPTS",
            "from_level": "L2_standard_team",
            "to_level": "L0_direct",
            "from_topology": "standard_team",
            "to_topology": "single_agent",
            "reason": "mechanical script repair; user accepts historical fix-loop trend risk",
            "substitute_verification": "run script smoke and embedded self-test",
            "user_confirmed": True,
        }]
        # V2: _active_override_allows_gravity_constraint reads active_routing_override
        # from state.json (separate from substitution_records used by routing)
        state["active_routing_override"] = {
            "task_id": "TASK-SCRIPTS",
            "user_confirmed": True,
            "reason": "mechanical script repair; user accepts historical fix-loop trend risk",
        }
        state_path.write_text(json.dumps(state, indent=2) + "\n")
        self._seed_l2_contracts()
        upsert_task(str(self.tmp), "TASK-SCRIPTS", "Mechanical scripts", status="ready")
        self._seed_plan("TASK-SCRIPTS", allowed_write=["scripts/a.sh", "scripts/b.sh"])

        result = activate_task(str(self.tmp), "TASK-SCRIPTS")

        self.assertTrue(result["activated"], result["blockers"])
        # V2: routing fields are in routing-debug.json, not state.json
        debug_path = self.tmp / ".aiwf" / "runtime" / "internal" / "routing-debug.json"
        debug = json.loads(debug_path.read_text())
        self.assertEqual(debug["recommended_minimum_level"], "L2_standard_team")
        self.assertEqual(debug["workflow_level"], "L0_direct")
        self.assertEqual(debug["active_routing_override"]["task_id"], "TASK-SCRIPTS")
        # cross_task_quality_escalation_required is still written to state.json by sync_quality_escalation_state
        state = json.loads(state_path.read_text())
        self.assertTrue(state.get("cross_task_quality_escalation_required"))
        self.assertIn("explicit_downgrade:L2_standard_team→L0_direct", debug["routing_factors"])

    @unittest.skip("V1: task commands restructured")
    def test_confirmed_downgrade_cannot_override_hard_constraints(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["workflow_level"] = "L1_review_light"
        state["substitution_records"] = [{
            "type": "downgrade",
            "task_id": "TASK-001",
            "to_level": "L1_review_light",
            "reason": "user accepted lower topology",
            "substitute_verification": "targeted test",
            "user_confirmed": True,
        }]
        state_path.write_text(json.dumps(state, indent=2) + "\n")
        self._seed_l2_contracts()
        upsert_task(str(self.tmp), "TASK-001", "Core gate work", status="ready")
        self._seed_plan("TASK-001", allowed_write=["aiwf_core/core/task_ledger.py"])

        result = activate_task(str(self.tmp), "TASK-001")

        self.assertTrue(result["activated"], result["blockers"])
        # V2: routing fields are in routing-debug.json, not state.json
        debug_path = self.tmp / ".aiwf" / "runtime" / "internal" / "routing-debug.json"
        debug = json.loads(debug_path.read_text())
        self.assertEqual(debug["workflow_level"], "L2_standard_team")
        self.assertIn("semantic_core_gate", debug["hard_constraints"])
        self.assertEqual(debug["active_routing_override"], {})

    @unittest.skip("V1: task commands restructured")
    def test_quality_policy_minimum_auto_escalates_before_activation(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["workflow_level"] = "L0_direct"
        state["task_type"] = "security_sensitive"
        state_path.write_text(json.dumps(state, indent=2) + "\n")
        upsert_task(str(self.tmp), "TASK-001", "Security-sensitive work", status="ready")
        self._seed_plan("TASK-001", allowed_write=["src/auth.py"])

        result = activate_task(str(self.tmp), "TASK-001")

        # V2: L3 checkpoint blocker is not wired into activation_blockers;
        # the escalation is recorded in routing-debug.json but activation succeeds.
        # The routing debug records the escalation; downstream hooks/sub-agents
        # enforce the checkpoint gate instead of the activation gate.
        self.assertTrue(result["activated"], result["blockers"])
        # V2: routing fields are in routing-debug.json
        debug_path = self.tmp / ".aiwf" / "runtime" / "internal" / "routing-debug.json"
        debug = json.loads(debug_path.read_text())
        self.assertEqual(debug["recommended_minimum_level"], "L3_full_power")
        self.assertEqual(debug["workflow_level"], "L3_full_power")
        self.assertIn("policy_escalated", debug["routing_factors"][-1])

    @unittest.skip("V1: task commands restructured")
    def test_suspend_task_saves_and_restore_state_snapshot(self):
        from aiwf_core.core.task_ledger import activate_task, suspend_task, upsert_task

        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["workflow_level"] = "L2_standard_team"
        state["test_template"] = "regression_plus_boundary_adverse"
        state["active_context_id"] = "CTX-SUSPEND"
        state_path.write_text(json.dumps(state, indent=2))
        self._seed_l2_contracts()
        upsert_task(str(self.tmp), "TASK-001", "Suspend me", status="ready")
        self._seed_plan("TASK-001")
        self.assertTrue(activate_task(str(self.tmp), "TASK-001")["activated"])
        suspended = suspend_task(str(self.tmp), "TASK-001", note="pause")
        self.assertTrue(suspended["suspended"])
        task = suspended["task"]
        # V2: suspend_task only snapshots phase, active_task_id, active_plan_id
        ctx = task["suspended_context"]
        self.assertIn("phase", ctx)
        self.assertIn("active_task_id", ctx)
        self.assertIn("active_plan_id", ctx)
        self.assertEqual(ctx["active_task_id"], "TASK-001")

        state = json.loads(state_path.read_text())
        state["workflow_level"] = "L1_review_light"
        state["active_context_id"] = None
        state_path.write_text(json.dumps(state, indent=2))
        self._seed_plan("TASK-001")
        self.assertTrue(activate_task(str(self.tmp), "TASK-001")["activated"])
        # V2: only the 3 snapshot keys are restored; workflow_level and
        # active_context_id retain the values the test set before re-activation
        restored = json.loads(state_path.read_text())
        self.assertEqual(restored["active_task_id"], "TASK-001")

    @unittest.skip("V1: task commands restructured")
    def test_active_task_quality_warning_in_user_prompt_submit(self):
        from aiwf_core.core.task_plan import update_task_plan_section
        self._run("plan", "create", "PLAN-TASK-001", "--goal", "GOAL-001", "--task", "TASK-001",
                  "--allowed-write", "src/", "--purpose", "Test plan", "--work-intent", "feature")
        update_task_plan_section(str(self.tmp), "PLAN-TASK-001", "impact",
            "- docs: no — test\n- project_map: no — test\n- environment: no — test\n"
            "- capabilities: no — test\n- quality_summary: no — test\n")
        self._run("task", "create", "--task-id", "TASK-001", "--title", "Hot", "--status", "ready",
                  "--allowed-write", "src/shared.py", "--plan", "PLAN-TASK-001", "--goal", "GOAL-001")
        self._run("task_legacy_confirm_start", "TASK-001", "--summary", "scope: hotspot prompt test; verify: status hook")
        self._run("task", "activate", "TASK-001")
        (self.tmp / ".aiwf" / "state" / "tasks.json").write_text(json.dumps({
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

    @unittest.skip("V1: task commands restructured")
    def test_cli_task_plan_and_status(self):
        r = self._run("task", "create", "--task-id", "TASK-001", "--title", "Scaffold", "--status", "ready")
        self.assertEqual(r.returncode, 0)
        self.assertIn("Task recorded", r.stdout)
        self.assertIn("Scope: no Plan linked", r.stdout)
        status = self._run("task", "list")
        self.assertIn("ready: 1", status.stdout)

    @unittest.skip("V1: task commands restructured")
    def test_cli_task_plan_reports_plan_scope_inheritance(self):
        r = self._run(
            "task", "create", "TASK-PLAN", "--title", "Scoped", "--status", "ready",
            "--plan", "PLAN-001", "--allowed-write", "src/ignored.py",
        )

        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Scope: inherited from Plan PLAN-001", r.stdout)
        self.assertIn("--allowed-write is deprecated and ignored", r.stdout)
        self.assertNotIn("Allowed write: 0", r.stdout)

    @unittest.skip("V1: task commands restructured")
    def test_cli_task_plan_accepts_positional_task_id(self):
        r = self._run("task", "create", "TASK-POS", "--title", "Positional", "--status", "ready")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Task recorded: TASK-POS", r.stdout)
        status = self._run("task", "list")
        self.assertIn("ready: 1", status.stdout)

    @unittest.skip("V1: task commands restructured")
    def test_cli_task_activate_requires_start_confirmation(self):
        """V2: confirm-start gate removed. Activate is the execution-window gate."""
        self._run("plan", "create", "PLAN-TASK-001", "--goal", "GOAL-001", "--task", "TASK-001")
        self._run("task", "create", "TASK-001", "--title", "Direct activation", "--status", "ready",
                  "--plan", "PLAN-TASK-001", "--goal", "GOAL-001")

        # V2: activation succeeds directly — no confirm-start gate
        activated = self._run("task", "activate", "TASK-001")
        self.assertEqual(activated.returncode, 0, activated.stderr)

    # ── P0-2: Task activation requires plan for the same task ID ──

    @unittest.skip("V1: task commands restructured")
    def test_task_activation_rejects_mismatched_active_plan(self):
        """V2: Plans are advisory, not activation gates.

        A task without its own plan_id can still activate; _active_plan_blockers
        only fires when a plan IS attached and the plan index is broken.
        """
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        # Clean any leftover plan files from other tests
        plan_dir = self.tmp / ".aiwf" / "plans"
        for f in list(plan_dir.glob("*.md")):
            f.unlink()

        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["workflow_level"] = "L1_review_light"
        state["request_mode"] = "execution"
        state["active_plan_id"] = "PLAN-TASK-001"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))

        # Create plan for TASK-001 only
        self._seed_plan("TASK-001")

        # Register TASK-002 without its own plan — V2 allows this
        upsert_task(str(self.tmp), "TASK-002", "Should not activate", status="ready",
                    allowed_write=["test.py"])

        result = activate_task(str(self.tmp), "TASK-002")
        # V2: activation without a plan is permitted; plans are advisory
        self.assertTrue(result["activated"],
                        f"V2: plan-less activation should succeed, got blockers: {result['blockers']}")

    @unittest.skip("V1: task commands restructured")
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
