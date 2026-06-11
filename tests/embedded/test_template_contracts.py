"""Template contracts: per-depth test/review requirements, no 'all required'."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

def _install(cwd):
    env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
    subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                   capture_output=True, text=True, cwd=str(cwd), env=env, timeout=20)

class TestTemplateContracts(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awtc_"))
        _install(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ── test contracts ──
    def test_targeted_not_required_full_regression(self):
        from aiwf_core.core.quality_policy import get_test_template_contract
        c = get_test_template_contract("targeted")
        self.assertIn("full regression", c["not_required"])
        self.assertIn("broad edge matrix", c["not_required"])

    def test_risk_matrix_required_fields(self):
        from aiwf_core.core.quality_policy import get_test_template_contract
        c = get_test_template_contract("risk_matrix_plus_integration_adversarial")
        for field in ["risk matrix", "integration path", "adversarial/error path", "deferred risks"]:
            self.assertTrue(any(field in r for r in c["required"]), f"missing: {field}")

    def test_review_lite_no_architecture(self):
        from aiwf_core.core.quality_policy import get_review_template_contract
        c = get_review_template_contract("review_lite")
        self.assertIn("architecture review unless risk found", c["do_not_expand_to"])
        self.assertNotIn("architecture", c["inspect"])

    def test_full_review_includes_cleanup_deferred_git(self):
        from aiwf_core.core.quality_policy import get_review_template_contract
        c = get_review_template_contract("full_review_structure_cleanup_deferred_risks")
        inspects = c["inspect"]
        for keyword in ["cleanup", "deferred risks", "git diff"]:
            self.assertTrue(any(keyword in i for i in inspects), f"missing: {keyword}")

    # ── skill text ──
    def test_test_skill_no_all_required(self):
        content = (self.tmp / ".claude" / "skills" / "aiwf-test" / "SKILL.md").read_text()
        self.assertNotIn("all required", content.lower())
        self.assertIn("test_template", content)

    def test_test_skill_mentions_targeted_no_matrix(self):
        content = (self.tmp / ".claude" / "skills" / "aiwf-test" / "SKILL.md").read_text()
        self.assertIn("Do NOT build a test matrix", content)

    def test_test_skill_locks_plan_verification_and_changed_file_risk(self):
        content = (self.tmp / ".claude" / "skills" / "aiwf-test" / "SKILL.md").read_text()
        self.assertIn("Testing Basis Contract", content)
        self.assertIn("active plan's `Verification` section", content)
        self.assertIn("risk implied by changed files", content)
        self.assertIn("return to Planner to update the plan", content)

    def test_review_skill_mentions_review_template(self):
        content = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        self.assertIn("review_template", content)
        self.assertIn("Do NOT expand depth unilaterally", content)

    def test_review_skill_has_review_lite(self):
        content = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        self.assertIn("review_lite", content)
        # "Do NOT expand to architecture" is in the review-verify sub-skill.
        self.assertIn("Do NOT expand depth unilaterally", content)

    def test_review_skill_locks_goal_plan_scope_evidence_testing_impact_basis(self):
        content = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        self.assertIn("Review Basis Contract", content)
        self.assertIn("Goal + Plan + Scope + Evidence + Testing + Impact", content)
        self.assertIn("active plan's `Impact` section", content)
        self.assertIn("Do not accept by testing status alone", content)

    def test_planner_execute_locks_plan_drift_update_before_continuing(self):
        content = (self.tmp / ".claude" / "skills" / "aiwf-planner-execute" / "SKILL.md").read_text()
        self.assertIn("Plan Drift During Execution", content)
        self.assertIn("aiwf plan update --task-id <TASK-ID>", content)
        self.assertIn("Plan is the pre-work contract; prepare-close is the post-work gate", content)

    def test_close_skill_requires_prepare_close_before_task_close(self):
        content = (self.tmp / ".claude" / "skills" / "aiwf-close" / "SKILL.md").read_text()
        self.assertIn("while the active task is still active", content)
        self.assertIn("If `passed=True`, run `aiwf task close <ACTIVE-TASK-ID>`", content)
        self.assertIn("Do NOT close the ledger task before `prepare_close` passes", content)

    def test_review_output_skill_promotes_quality_verdict_dimensions(self):
        content = (self.tmp / ".claude" / "skills" / "aiwf-review-output" / "SKILL.md").read_text()
        self.assertIn("--verdict PASS", content)
        self.assertIn("--dimension-score requirement_fit=PASS", content)
        self.assertIn("--basis-status goal=covered", content)
        self.assertIn("--basis-status impact=covered", content)
        self.assertIn("--docs-checked not_applicable", content)
        self.assertIn("PASS_WITH_RISK", content)
        self.assertIn("Requires at least one `--blocker`", content)
        self.assertIn("at least one must be FAIL", content)
        self.assertIn("symptom-only", content)
        self.assertIn("Use full V2 Quality Verdict when the route is L2/L3", content)

    def test_review_output_records_quality_basis(self):
        content = (self.tmp / ".claude" / "skills" / "aiwf-review-output" / "SKILL.md").read_text()
        self.assertIn("Review Basis Recording", content)
        self.assertIn("Every V2 verdict must record all six review basis items", content)
        self.assertIn("active `.aiwf/plans/<TASK>.md`", content)
        self.assertIn("changed-file risk", content)
        self.assertIn("Use `gap` when that source contradicts closure", content)
        self.assertIn("Impact-Aware Docs Check", content)

    def test_review_output_maps_quality_dimensions_to_engineering_questions(self):
        content = (self.tmp / ".claude" / "skills" / "aiwf-review-output" / "SKILL.md").read_text()
        for required in [
            "Quality Dimension Questions",
            "Goal, Evaluation Contract, and active plan Done Means",
            "architecture_brief invariants",
            "speculative abstraction",
            "Plan.Verification, changed-file risk",
            "hidden coupling or unclear ownership",
            "deferred tests, hotspots, and technical debt",
            "trust the evidence chain",
        ]:
            self.assertIn(required, content)

    # ── security_sensitive wording ──
    def test_security_sensitive_no_old_wording(self):
        from aiwf_core.core.quality_policy import select_quality_policy
        import inspect
        src = inspect.getsource(select_quality_policy)
        self.assertNotIn("at least L2", src)
        self.assertNotIn("at least standard_review", src)

    def test_security_doc_has_L3_recommended(self):
        doc = (PROJECT_ROOT / "docs" / "AIWF-QUALITY-POLICY.md").read_text()
        self.assertIn("L3_full_power", doc)
        self.assertIn("user decision", doc)

    # ── prompt cache ──
    def test_contracts_are_short_not_fulltext(self):
        from aiwf_core.core.quality_policy import get_test_template_contract
        c = get_test_template_contract("targeted")
        text = str(c)
        self.assertLess(len(text), 600)

    def test_state_does_not_store_contract_fulltext(self):
        """State stores template keys only, not contract fulltext."""
        import json
        s = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        for k, v in s.items():
            if isinstance(v, str) and len(v) > 100:
                self.fail(f"state.{k} is {len(v)} chars; should be a short key")


if __name__ == "__main__":
    unittest.main()
