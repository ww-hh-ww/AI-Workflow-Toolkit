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

    def test_review_skill_mentions_review_template(self):
        content = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        self.assertIn("review_template", content)
        self.assertIn("Do NOT expand depth unilaterally", content)

    def test_review_skill_has_review_lite(self):
        content = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        self.assertIn("review_lite", content)
        self.assertIn("Do NOT expand to architecture", content)

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
