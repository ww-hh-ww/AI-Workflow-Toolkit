"""prepare_close protection: L0/L1 auto-fill, L2/L3 block, blockers always block."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

def _install(cwd):
    env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
    subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                   capture_output=True, text=True, cwd=str(cwd), env=env, timeout=20)

class TestPrepareCloseGates(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awpc_"))
        _install(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _setup(self, level, cleanup_status=None, structure_status=None,
               stale_items=None, cleanup_blockers=None, structure_blockers=None,
               fix_loop_status="none", evidence_accepted=True, resume_ready=True):
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for fn, dfn in MVP_STATE_FILES.items():
            p = self.tmp / ".aiwf" / fn; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(dfn(), indent=2) + "\n")
        s = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        s["workflow_level"] = level
        s["phase"] = "reviewing"
        if level in ("L2_standard_team", "L3_full_power"):
            s["complexity"] = "complex" if level == "L2_standard_team" else "critical"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(s, indent=2))
        r = json.loads((self.tmp / ".aiwf" / "quality" / "review.json").read_text())
        r["result"] = "accepted"; r["closure_allowed"] = True
        if level in ("L2_standard_team", "L3_full_power"):
            r["accepted_evidence_ids"] = ["EV-TEST", "EV-EXEC", "EV-REVIEW"]
        if cleanup_status is not None: r["cleanup_status"] = cleanup_status
        else: r.pop("cleanup_status", None)
        if structure_status is not None: r["structure_status"] = structure_status
        else: r.pop("structure_status", None)
        if stale_items is not None: r["stale_items"] = stale_items
        if cleanup_blockers is not None: r["cleanup_blockers"] = cleanup_blockers
        if structure_blockers is not None: r["structure_blockers"] = structure_blockers
        (self.tmp / ".aiwf" / "quality" / "review.json").write_text(json.dumps(r, indent=2))
        if evidence_accepted:
            records = [{"id": "EV-001", "status": "accepted", "trust": "machine_observed"}]
            if level in ("L2_standard_team", "L3_full_power"):
                records = [
                    {"id": "EV-EXEC", "status": "accepted", "trust": "machine_observed", "session_id": "executor-session",
                     "command": "python3 -m compileall aiwf_core", "exit_code": 0},
                    {"id": "EV-TEST", "status": "accepted", "trust": "machine_observed", "session_id": "tester-session",
                     "command": "pytest", "exit_code": 0},
                    {"id": "EV-REVIEW", "status": "accepted", "trust": "machine_observed", "session_id": "reviewer-session",
                     "command": "aiwf review", "exit_code": 0},
                ]
            (self.tmp / ".aiwf" / "evidence" / "records.json").write_text(json.dumps({
                "records": records
            }, indent=2))
        (self.tmp / ".aiwf" / "state" / "fix-loop.json").write_text(json.dumps({
            "status": fix_loop_status, "route": None, "required_fixes": []
        }, indent=2))
        (self.tmp / ".aiwf" / "quality" / "testing.json").write_text(json.dumps({
            "status": "adequate", "commands": ["pytest"]
        }, indent=2))
        if resume_ready and level in ("L2_standard_team", "L3_full_power"):
            self._seed_resume_ready_assets()

    def _seed_resume_ready_assets(self):
        goal_path = self.tmp / ".aiwf" / "state" / "goal.json"
        goal = json.loads(goal_path.read_text())
        goal.setdefault("decisions", []).append({
            "decision": "Meta-critique: review accepted; no structural gaps remain.",
            "source": "planner",
        })
        goal_path.write_text(json.dumps(goal, indent=2))

        reports = self.tmp / ".aiwf" / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        (reports / "项目地图.md").write_text(
            "# AIWF Project Map\n\n"
            "## Project Snapshot\n- Reviewed project state is current.\n\n"
            "## Current Stage\n- Closing.\n\n"
            "## Completed Milestones\n- Implementation, testing, review.\n\n"
            "## Active Direction\n- Preserve governance flow.\n\n"
            "## Next Candidate Tasks\n- None.\n\n"
            "## Architecture Direction\n- No structural drift.\n\n"
            "## Environment Summary\n- Local tests verified.\n\n"
            "## Open Decisions\n- None.\n\n"
            "## Deferred Risks\n- None.\n\n"
            "## Not-now / Rejected Routes\n- None.\n\n"
            "## Ideas to Review\n- None.\n",
            encoding="utf-8",
        )
        (reports / "质量摘要.md").write_text("# Quality Digest\n\n- Current task has no cross-task debt.\n", encoding="utf-8")
        (reports / "当前状态.md").write_text(
            "# AIWF Current State\n\n"
            "## Goal & Intent\n- Close verified task with resume assets present.\n\n"
            "## Current Status\n- Review accepted, cleanup fresh, structure accepted, and resume audit ready.\n\n"
            "## Quality Snapshot\n- Testing adequate and review accepted.\n\n"
            "## Raw References\n- .aiwf/state/state.json\n- .aiwf/quality/review.json\n",
            encoding="utf-8",
        )

    def _prepare(self):
        from aiwf_core.core.state_ops import prepare_close
        return prepare_close(str(self.tmp))

    # ── L0 auto-fill ──
    def test_L0_missing_cleanup_structure_auto_fills(self):
        self._setup("L0_direct")
        r = self._prepare()
        self.assertTrue(r["auto_filled"])
        self.assertTrue(r["can_proceed_to_gate"])
        review = json.loads((self.tmp / ".aiwf" / "quality" / "review.json").read_text())
        self.assertEqual(review["cleanup_status"], "fresh")
        self.assertEqual(review["structure_status"], "accepted")

    # ── L1 auto-fill ──
    def test_L1_missing_cleanup_structure_auto_fills(self):
        self._setup("L1_review_light")
        r = self._prepare()
        self.assertTrue(r["auto_filled"])
        self.assertTrue(r["can_proceed_to_gate"])

    # ── L2 blocks on missing ──
    def test_L2_missing_cleanup_blocks(self):
        self._setup("L2_standard_team", cleanup_status=None, structure_status="accepted")
        r = self._prepare()
        self.assertFalse(r["can_proceed_to_gate"])
        self.assertTrue(any("cleanup_status missing" in b for b in r["blockers"]))

    def test_L2_missing_structure_blocks(self):
        self._setup("L2_standard_team", cleanup_status="fresh", structure_status=None)
        r = self._prepare()
        self.assertFalse(r["can_proceed_to_gate"])
        self.assertTrue(any("structure_status missing" in b for b in r["blockers"]))

    # ── L3 blocks on missing ──
    def test_L3_missing_cleanup_blocks(self):
        self._setup("L3_full_power", cleanup_status=None, structure_status="accepted")
        r = self._prepare()
        self.assertFalse(r["can_proceed_to_gate"])

    def test_L3_missing_structure_blocks(self):
        self._setup("L3_full_power", cleanup_status="fresh", structure_status=None)
        r = self._prepare()
        self.assertFalse(r["can_proceed_to_gate"])

    # ── Blockers always block (any level) ──
    def test_L0_stale_items_blocks(self):
        self._setup("L0_direct", stale_items=["old-ctx"])
        r = self._prepare()
        self.assertFalse(r["can_proceed_to_gate"])
        self.assertTrue(any("stale_items" in b for b in r["blockers"]))

    def test_L1_cleanup_blockers_blocks(self):
        self._setup("L1_review_light", cleanup_blockers=["unresolved"])
        r = self._prepare()
        self.assertFalse(r["can_proceed_to_gate"])

    def test_L2_structure_blockers_blocks(self):
        self._setup("L2_standard_team", structure_blockers=["over-engineered"],
                    cleanup_status="fresh", structure_status="needs_fix")
        r = self._prepare()
        self.assertFalse(r["can_proceed_to_gate"])

    def test_L3_fix_loop_open_blocks(self):
        self._setup("L3_full_power", cleanup_status="fresh", structure_status="accepted",
                    fix_loop_status="open")
        r = self._prepare()
        self.assertFalse(r["can_proceed_to_gate"])
        self.assertTrue(any("fix-loop" in b for b in r["blockers"]))

    def test_L2_explicit_valid_cleanup_passes(self):
        self._setup("L2_standard_team", cleanup_status="fresh", structure_status="accepted")
        r = self._prepare()
        self.assertTrue(r["can_proceed_to_gate"])

    def test_L3_all_valid_passes(self):
        self._setup("L3_full_power", cleanup_status="fresh", structure_status="accepted")
        r = self._prepare()
        self.assertTrue(r["can_proceed_to_gate"])

    def test_L2_missing_meta_critique_blocks_resume(self):
        self._setup("L2_standard_team", cleanup_status="fresh", structure_status="accepted",
                    resume_ready=False)
        r = self._prepare()
        self.assertFalse(r["can_proceed_to_gate"])
        self.assertTrue(any("meta-critique" in b for b in r["blockers"]))
        self.assertEqual(r["closure_resume"]["status"], "blocked")

    def test_L2_user_sourced_meta_critique_blocks_resume(self):
        self._setup("L2_standard_team", cleanup_status="fresh", structure_status="accepted")
        goal_path = self.tmp / ".aiwf" / "state" / "goal.json"
        goal = json.loads(goal_path.read_text())
        goal["decisions"] = [{
            "decision": "Meta-critique: fake entry without Planner provenance.",
            "source": "user",
        }]
        goal_path.write_text(json.dumps(goal, indent=2))
        r = self._prepare()
        self.assertFalse(r["can_proceed_to_gate"])
        self.assertTrue(any("Planner-sourced meta-critique" in b for b in r["blockers"]))

    def test_L2_testing_status_without_machine_evidence_blocks_resume(self):
        self._setup("L2_standard_team", cleanup_status="fresh", structure_status="accepted")
        evidence_path = self.tmp / ".aiwf" / "evidence" / "records.json"
        evidence = json.loads(evidence_path.read_text())
        for record in evidence["records"]:
            if record["id"] == "EV-TEST":
                record["exit_code"] = 1
        evidence_path.write_text(json.dumps(evidence, indent=2))
        r = self._prepare()
        self.assertFalse(r["can_proceed_to_gate"])
        self.assertTrue(any("testing commands are not backed" in b for b in r["blockers"]))

    def test_L2_stale_current_state_blocks_resume(self):
        self._setup("L2_standard_team", cleanup_status="fresh", structure_status="accepted")
        (self.tmp / ".aiwf" / "quality" / "review.json").write_text(json.dumps({
            "result": "accepted",
            "closure_allowed": True,
            "cleanup_status": "fresh",
            "structure_status": "accepted",
            "stale_items": [],
            "cleanup_blockers": [],
            "structure_blockers": [],
        }, indent=2))
        r = self._prepare()
        self.assertFalse(r["can_proceed_to_gate"])
        self.assertTrue(any("current-state.md not fresh" in b for b in r["blockers"]))

    def test_missing_testing_does_not_set_close_attempt(self):
        self._setup("L1_review_light")
        (self.tmp / ".aiwf" / "quality" / "testing.json").write_text(json.dumps({"status": "missing"}, indent=2))
        r = self._prepare()
        self.assertFalse(r["close_attempt_set"])
        self.assertFalse(r["can_proceed_to_gate"])
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        self.assertFalse(state.get("close_attempt"))
        self.assertEqual(state.get("phase"), "reviewing")

    def test_missing_accepted_evidence_does_not_set_close_attempt(self):
        self._setup("L1_review_light", evidence_accepted=False)
        (self.tmp / ".aiwf" / "evidence" / "records.json").write_text(json.dumps({"records": []}, indent=2))
        r = self._prepare()
        self.assertFalse(r["close_attempt_set"])
        self.assertTrue(any("accepted evidence" in b for b in r["blockers"]))

    def test_discussing_phase_does_not_set_close_attempt(self):
        self._setup("L1_review_light")
        s = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        s["phase"] = "discussing"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(s, indent=2))
        r = self._prepare()
        self.assertFalse(r["close_attempt_set"])
        self.assertTrue(any("phase not ready" in b for b in r["blockers"]))


if __name__ == "__main__":
    unittest.main()
