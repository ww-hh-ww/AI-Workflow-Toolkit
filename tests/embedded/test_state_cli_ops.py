"""State CLI ops: record-testing, mark-cleanup, prepare-close, help."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15

class TestStateCliOps(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awsco_"))
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                       capture_output=True, text=True, cwd=str(cls.tmp), env=env, timeout=20)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        (self.tmp/".aiwf").mkdir(parents=True, exist_ok=True)
        for fn, dfn in MVP_STATE_FILES.items():
            p = self.tmp / ".aiwf" / fn; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(dfn(), indent=2)+"\n")

    def _run(self, *args):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, "-m", "aiwf_core.cli"] + list(args),
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    def _seed_close_ready(self):
        s = json.loads((self.tmp/".aiwf" / "state" / "state.json").read_text())
        s["phase"] = "reviewing"
        (self.tmp/".aiwf" / "state" / "state.json").write_text(json.dumps(s, indent=2))
        (self.tmp/".aiwf" / "quality" / "testing.json").write_text(json.dumps(
            {"status": "adequate", "commands": ["pytest"]}, indent=2))
        (self.tmp/".aiwf" / "evidence" / "records.json").write_text(json.dumps(
            {"records": [{"id": "EV-001", "status": "accepted", "trust": "machine_observed",
                          "trust_level": "command_observed", "session_id": "s1"}]}, indent=2))
        (self.tmp/".aiwf" / "quality" / "review.json").write_text(json.dumps({
            "result": "accepted",
            "closure_allowed": True,
            "blockers": [],
            "cleanup_status": "fresh",
            "cleanup_blockers": [],
            "stale_items": [],
            "structure_status": "accepted",
            "structure_blockers": [],
        }, indent=2))

    # ── record-testing ──
    def test_record_testing_writes_fields(self):
        r = self._run("state", "record-testing", "--status", "passed",
                      "--context-id", "CTX-001", "--command", "npm test",
                      "--untested-risk", "manual UI", "--coverage-summary", "targeted passed")
        self.assertEqual(r.returncode, 0)
        t = json.loads((self.tmp/".aiwf" / "quality" / "testing.json").read_text())
        self.assertEqual(t["status"], "passed")
        self.assertEqual(t["context_id"], "CTX-001")
        self.assertEqual(t["commands"], ["npm test"])
        self.assertIn("manual UI", t["untested_risks"])
        self.assertEqual(t["coverage_summary"], "targeted passed")
        self.assertIn("Evidence:", r.stdout)
        ev = json.loads((self.tmp/".aiwf" / "evidence" / "records.json").read_text())
        self.assertEqual(ev["records"][-1]["agent_type"], "tester")
        self.assertEqual(ev["records"][-1]["command"], "npm test")

    def test_record_role_evidence_writes_executor_record(self):
        r = self._run("state", "record-role-evidence",
                      "--role", "executor",
                      "--summary", "implemented scoped files",
                      "--changed-file", "src/a.py")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Role evidence recorded:", r.stdout)
        ev = json.loads((self.tmp/".aiwf" / "evidence" / "records.json").read_text())
        rec = ev["records"][-1]
        self.assertEqual(rec["agent_type"], "executor")
        self.assertEqual(rec["changed_files"], ["src/a.py"])
        self.assertEqual(rec["trust"], "machine_observed")

    def test_record_role_evidence_scan_git_corroborates_working_tree(self):
        subprocess.run(["git", "init", "-b", "main"], cwd=str(self.tmp), capture_output=True, text=True, timeout=TIMEOUT)
        subprocess.run(["git", "config", "user.email", "a@b.c"], cwd=str(self.tmp), capture_output=True, text=True, timeout=TIMEOUT)
        subprocess.run(["git", "config", "user.name", "aiwf-test"], cwd=str(self.tmp), capture_output=True, text=True, timeout=TIMEOUT)
        (self.tmp / "README.md").write_text("baseline\n")
        subprocess.run(["git", "add", "README.md"], cwd=str(self.tmp), capture_output=True, text=True, timeout=TIMEOUT)
        subprocess.run(["git", "commit", "-m", "baseline"], cwd=str(self.tmp), capture_output=True, text=True, timeout=TIMEOUT)
        (self.tmp / "src").mkdir(exist_ok=True)
        (self.tmp / "src" / "bridge.py").write_text("value = 1\n")

        r = self._run("state", "record-role-evidence",
                      "--role", "executor",
                      "--summary", "implemented bridge file",
                      "--scan-git")

        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Git scan:", r.stdout)
        ev = json.loads((self.tmp/".aiwf" / "evidence" / "records.json").read_text())
        rec = ev["records"][-1]
        self.assertEqual(rec["changed_files_source"], "role_delivery_git_scan")
        self.assertEqual(rec["working_tree_source"], "git_diff")
        self.assertIn("src/bridge.py", rec["working_tree_changed_files"])
        self.assertIn("src/bridge.py", rec["changed_files"])
        self.assertEqual(rec["attribution"], "role_command")

    def test_record_review_writes_review_and_reviewer_evidence(self):
        self._run("state", "record-role-evidence", "--role", "executor",
                  "--summary", "implemented", "--status", "accepted")
        ev = json.loads((self.tmp/".aiwf" / "evidence" / "records.json").read_text())
        exec_id = ev["records"][-1]["id"]
        r = self._run("state", "record-review",
                      "--result", "accepted",
                      "--closure-allowed",
                      "--accepted-evidence-id", exec_id,
                      "--cleanup-status", "fresh",
                      "--structure-status", "accepted",
                      "--summary", "reviewed evidence")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Evidence:", r.stdout)
        review = json.loads((self.tmp/".aiwf" / "quality" / "review.json").read_text())
        reviewer_id = review["reviewer_evidence_id"]
        self.assertIn(reviewer_id, review["accepted_evidence_ids"])
        ev = json.loads((self.tmp/".aiwf" / "evidence" / "records.json").read_text())
        reviewer = [rec for rec in ev["records"] if rec["id"] == reviewer_id][0]
        self.assertEqual(reviewer["agent_type"], "reviewer")

    def _dimension_args(self, overrides=None, notes=None):
        from aiwf_core.core.state_schema import QUALITY_DIMENSIONS
        overrides = overrides or {}
        notes = notes or {}
        args = []
        for dim in QUALITY_DIMENSIONS:
            args.extend(["--dimension-score", f"{dim}={overrides.get(dim, 'PASS')}"])
            if dim in notes:
                args.extend(["--dimension-note", f"{dim}_note={notes[dim]}"])
        return args

    def _dimension_map(self, overrides=None, notes=None):
        from aiwf_core.core.state_schema import QUALITY_DIMENSIONS
        overrides = overrides or {}
        notes = notes or {}
        return {
            dim: {"score": overrides.get(dim, "PASS"), "note": notes.get(dim, "")}
            for dim in QUALITY_DIMENSIONS
        }

    def _basis_args(self, overrides=None, notes=None):
        from aiwf_core.core.state_schema import REVIEW_BASIS
        overrides = overrides or {}
        notes = notes or {}
        args = []
        for name in REVIEW_BASIS:
            args.extend(["--basis-status", f"{name}={overrides.get(name, 'covered')}"])
            if name in notes:
                args.extend(["--basis-note", f"{name}_note={notes[name]}"])
        return args

    def _basis_map(self, overrides=None, notes=None):
        from aiwf_core.core.state_schema import REVIEW_BASIS
        overrides = overrides or {}
        notes = notes or {}
        return {
            name: {"status": overrides.get(name, "covered"), "note": notes.get(name, "")}
            for name in REVIEW_BASIS
        }

    def test_record_review_verdict_pass_requires_all_quality_dimensions(self):
        r = self._run("state", "record-review",
                      "--verdict", "PASS",
                      "--cleanup-status", "fresh",
                      "--structure-status", "accepted",
                      "--summary", "quality verdict")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("requires scored quality dimensions", r.stderr)

    def test_record_review_verdict_pass_with_all_dimensions_allows_closure(self):
        r = self._run("state", "record-review",
                      "--verdict", "PASS",
                      "--cleanup-status", "fresh",
                      "--structure-status", "accepted",
                      "--summary", "quality verdict",
                      *self._dimension_args(),
                      *self._basis_args())
        self.assertEqual(r.returncode, 0, r.stderr)
        review = json.loads((self.tmp/".aiwf" / "quality" / "review.json").read_text())
        self.assertEqual(review["verdict"], "PASS")
        self.assertEqual(review["result"], "accepted")
        self.assertTrue(review["closure_allowed"])
        self.assertEqual(review["review_basis"]["goal"]["status"], "covered")

    def test_record_review_verdict_pass_requires_review_basis(self):
        r = self._run("state", "record-review",
                      "--verdict", "PASS",
                      "--cleanup-status", "fresh",
                      "--structure-status", "accepted",
                      "--summary", "quality verdict",
                      *self._dimension_args())
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("requires review basis coverage", r.stderr)

    def test_record_review_verdict_pass_rejects_basis_gap(self):
        r = self._run("state", "record-review",
                      "--verdict", "PASS",
                      "--cleanup-status", "fresh",
                      "--structure-status", "accepted",
                      "--summary", "quality verdict",
                      *self._dimension_args(),
                      *self._basis_args({"testing": "gap"}, {"testing": "tests did not cover plan"}))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("closure verdict cannot include review basis gaps", r.stderr)

    def test_record_review_verdict_pass_rejects_risk_dimension(self):
        r = self._run("state", "record-review",
                      "--verdict", "PASS",
                      "--cleanup-status", "fresh",
                      "--structure-status", "accepted",
                      "--summary", "quality verdict",
                      *self._dimension_args({"risk_debt": "RISK"}))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("PASS cannot include RISK", r.stderr)

    def test_record_review_pass_with_risk_requires_risk_note(self):
        r = self._run("state", "record-review",
                      "--verdict", "PASS_WITH_RISK",
                      "--cleanup-status", "fresh",
                      "--structure-status", "accepted",
                      "--summary", "quality verdict",
                      *self._dimension_args({"risk_debt": "RISK"}))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("RISK dimensions require dimension notes", r.stderr)

    def test_record_review_pass_with_risk_records_quality_dimensions(self):
        r = self._run("state", "record-review",
                      "--verdict", "PASS_WITH_RISK",
                      "--cleanup-status", "fresh",
                      "--structure-status", "accepted",
                      "--summary", "quality verdict",
                      *self._dimension_args(
                          {"risk_debt": "RISK"},
                          {"risk_debt": "deferred manual verification remains"},
                      ),
                      *self._basis_args())
        self.assertEqual(r.returncode, 0, r.stderr)
        review = json.loads((self.tmp/".aiwf" / "quality" / "review.json").read_text())
        self.assertEqual(review["verdict"], "PASS_WITH_RISK")
        self.assertEqual(review["quality_dimensions"]["risk_debt"]["score"], "RISK")
        self.assertTrue(review["closure_allowed"])

    def test_record_review_pass_with_risk_rejects_symptom_only(self):
        r = self._run("state", "record-review",
                      "--verdict", "PASS_WITH_RISK",
                      "--cleanup-status", "fresh",
                      "--structure-status", "accepted",
                      "--root-cause", "symptom_only",
                      "--summary", "quality verdict",
                      *self._dimension_args(
                          {"risk_debt": "RISK"},
                          {"risk_debt": "temporary risk accepted"},
                      ))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("symptom patch", r.stderr)

    def test_record_review_revise_requires_blocker(self):
        r = self._run("state", "record-review",
                      "--verdict", "REVISE",
                      "--summary", "quality verdict",
                      *self._basis_args({"testing": "gap"}, {"testing": "missing changed-file risk test"}))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("REVISE requires at least one --blocker", r.stderr)

    def test_record_review_revise_requires_review_basis(self):
        r = self._run("state", "record-review",
                      "--verdict", "REVISE",
                      "--blocker", "test adequacy risk",
                      "--summary", "quality verdict",
                      *self._dimension_args({"test_adequacy": "RISK"}))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("REVISE requires review basis coverage", r.stderr)

    def test_record_review_revise_with_all_pass_dimensions_is_blocked(self):
        r = self._run("state", "record-review",
                      "--verdict", "REVISE",
                      "--blocker", "needs targeted fix",
                      "--summary", "quality verdict",
                      *self._dimension_args(),
                      *self._basis_args({"testing": "gap"}, {"testing": "missing changed-file risk test"}))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("REVISE with quality dimensions requires", r.stderr)

    def test_record_review_revise_with_no_basis_gap_is_blocked(self):
        r = self._run("state", "record-review",
                      "--verdict", "REVISE",
                      "--blocker", "needs targeted fix",
                      "--summary", "quality verdict",
                      *self._dimension_args({"test_adequacy": "RISK"}),
                      *self._basis_args())
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("REVISE requires at least one review basis gap", r.stderr)

    def test_record_review_revise_records_needs_fix_without_closure(self):
        r = self._run("state", "record-review",
                      "--verdict", "REVISE",
                      "--blocker", "test adequacy risk",
                      "--summary", "quality verdict",
                      *self._dimension_args({"test_adequacy": "RISK"}),
                      *self._basis_args({"testing": "gap"}, {"testing": "missing changed-file risk test"}))
        self.assertEqual(r.returncode, 0, r.stderr)
        review = json.loads((self.tmp/".aiwf" / "quality" / "review.json").read_text())
        self.assertEqual(review["verdict"], "REVISE")
        self.assertEqual(review["result"], "needs_fix")
        self.assertFalse(review["closure_allowed"])
        self.assertIn("test adequacy risk", review["blockers"])
        self.assertEqual(review["review_basis"]["testing"]["status"], "gap")

    def test_record_review_reject_with_dimensions_requires_fail(self):
        r = self._run("state", "record-review",
                      "--verdict", "REJECT",
                      "--blocker", "wrong architecture direction",
                      "--summary", "quality verdict",
                      *self._dimension_args({"architecture_fit": "RISK"}),
                      *self._basis_args({"plan": "gap"}, {"plan": "plan mismatches implementation"}))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("REJECT with quality dimensions requires", r.stderr)

    def test_record_review_reject_records_rejected_without_closure(self):
        r = self._run("state", "record-review",
                      "--verdict", "REJECT",
                      "--blocker", "wrong architecture direction",
                      "--summary", "quality verdict",
                      *self._dimension_args({"architecture_fit": "FAIL"}),
                      *self._basis_args({"plan": "gap"}, {"plan": "plan mismatches implementation"}))
        self.assertEqual(r.returncode, 0, r.stderr)
        review = json.loads((self.tmp/".aiwf" / "quality" / "review.json").read_text())
        self.assertEqual(review["verdict"], "REJECT")
        self.assertEqual(review["result"], "rejected")
        self.assertFalse(review["closure_allowed"])
        self.assertIn("wrong architecture direction", review["blockers"])

    def test_record_testing_output_is_short(self):
        r = self._run("state", "record-testing", "--status", "adequate",
                      "--command", "pytest")
        self.assertLess(len(r.stdout), 500)
        self.assertNotIn("{", r.stdout)

    # ── mark-cleanup ──
    def test_mark_cleanup_fresh_clears_stale(self):
        # Pre-seed stale
        rv = json.loads((self.tmp/".aiwf" / "quality" / "review.json").read_text())
        rv["cleanup_status"] = "stale"; rv["stale_items"] = ["old"]; rv["cleanup_blockers"] = ["b"]
        (self.tmp/".aiwf" / "quality" / "review.json").write_text(json.dumps(rv, indent=2))
        self._run("state", "mark-cleanup-fresh", "--note", "resolved")
        rv2 = json.loads((self.tmp/".aiwf" / "quality" / "review.json").read_text())
        self.assertEqual(rv2["cleanup_status"], "fresh")
        self.assertEqual(rv2["stale_items"], [])
        self.assertEqual(rv2["cleanup_blockers"], [])

    def test_mark_cleanup_stale_writes_fields(self):
        self._run("state", "mark-cleanup-stale", "--stale-item", "old-ctx",
                  "--blocker", "needs review", "--note", "found stale context")
        rv = json.loads((self.tmp/".aiwf" / "quality" / "review.json").read_text())
        self.assertEqual(rv["cleanup_status"], "stale")
        self.assertIn("old-ctx", rv["stale_items"])
        self.assertIn("needs review", rv["cleanup_blockers"])

    # ── prepare-close ──
    def test_prepare_close_completes_closure(self):
        self._seed_close_ready()
        self._run("state", "prepare-close")
        s = json.loads((self.tmp/".aiwf" / "state" / "state.json").read_text())
        self.assertTrue(s["closure_allowed"])
        self.assertEqual(s["phase"], "closed")
        self.assertFalse(s["close_attempt"])

    def test_prepare_close_output_short(self):
        r = self._run("state", "prepare-close")
        self.assertLess(len(r.stdout), 1200)

    def test_prepare_close_summary_surfaces_quality_verdict(self):
        self._seed_close_ready()
        review_path = self.tmp/".aiwf" / "quality" / "review.json"
        review = json.loads(review_path.read_text())
        review["verdict"] = "PASS_WITH_RISK"
        review["quality_dimensions"] = self._dimension_map(
            {"risk_debt": "RISK"},
            {"risk_debt": "accepted deferred risk"},
        )
        review["review_basis"] = self._basis_map()
        review_path.write_text(json.dumps(review, indent=2))
        r = self._run("state", "prepare-close")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Review: accepted, verdict=PASS_WITH_RISK", r.stdout)
        self.assertIn("Quality verdict: quality dimensions PASS=7 RISK=1 FAIL=0", r.stdout)
        self.assertIn("Review basis: review basis covered=6 gap=0", r.stdout)

    # ── state help ──
    def test_state_help_lists_all_7(self):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, "-m", "aiwf_core.cli", "state"],
                          capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        for sub in ["record-quality-policy", "record-quality-brief", "start-context",
                     "record-testing", "mark-cleanup-fresh", "mark-cleanup-stale", "prepare-close"]:
            self.assertIn(sub, r.stdout, f"Missing: {sub}")

    # ── skill text ──
    def test_test_skill_has_record_testing_cli(self):
        c = (self.tmp/".claude"/"skills"/"aiwf-test"/"SKILL.md").read_text()
        self.assertIn("record-testing", c)

    def test_cli_no_modify_claude_md(self):
        before = (self.tmp/"CLAUDE.md").read_text()
        self._run("state", "record-testing", "--status", "passed")
        self._run("state", "mark-cleanup-fresh")
        self._run("state", "prepare-close")
        after = (self.tmp/"CLAUDE.md").read_text()
        self.assertEqual(before, after)



    # ── wording consistency ──

    def test_agent_tester_no_hand_edit_testing_json(self):
        c2 = (self.tmp/".claude"/"agents"/"aiwf-tester.md").read_text()
        self.assertNotIn("Update `.aiwf/quality/testing.json`", c2)
        self.assertIn("aiwf state record-testing", c2)

    def test_agent_tester_says_do_not_hand_edit(self):
        c2 = (self.tmp/".claude"/"agents"/"aiwf-tester.md").read_text()
        self.assertIn("do not hand-edit testing.json", c2.lower())

    def test_prepare_close_no_can_proceed_wording(self):
        r = self._run("state", "prepare-close")
        self.assertNotIn("Can proceed to Stop gate", r.stdout)

    def test_prepare_close_explains_authoritative_gate(self):
        r = self._run("state", "prepare-close")
        self.assertIn("prepare-close is authoritative", r.stdout)

    def test_prepare_close_no_closure_success(self):
        r = self._run("state", "prepare-close")
        self.assertNotIn("closure allowed", r.stdout.lower())
        self.assertNotIn("closure complete", r.stdout.lower())

    def test_review_skill_has_cleanup_helpers(self):
        c2 = (self.tmp/".claude"/"agents"/"aiwf-reviewer.md").read_text()
        self.assertIn("cleanup_verified_at", c2)
        self.assertIn("--cleanup-status", c2)




    def test_prepare_close_blockers_printed_once(self):
        # Seed cleanup stale
        self._seed_close_ready()
        self._run("state", "mark-cleanup-stale", "--stale-item", "old-context")
        r = self._run("state", "prepare-close")
        count = r.stdout.count("Blockers (")
        self.assertEqual(count, 1, f"Blockers printed {count} times, should be 1")
        self.assertIn("Resolve blockers before preparing closure", r.stdout)
        self.assertNotIn("closure allowed", r.stdout.lower())


if __name__ == "__main__":
    unittest.main()
