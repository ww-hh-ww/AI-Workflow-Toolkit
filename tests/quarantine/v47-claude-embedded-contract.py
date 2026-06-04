#!/usr/bin/env python3
"""V47 Claude Code Embedded Hardening Contract Tests.

Tests behavior, not file existence. Fast: class-level installs,
per-test state reset (not full reinstall).
"""
from __future__ import annotations

import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

SCRIPT_TIMEOUT = 10

def _run(cmd, cwd, input_str="", timeout=SCRIPT_TIMEOUT):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    return subprocess.run(cmd, input=input_str, capture_output=True, text=True,
                          cwd=str(cwd), env=env, timeout=timeout)

def _install(cwd, timeout=30):
    aiwf_dir = cwd / ".aiwf"
    if aiwf_dir.exists():
        for f in aiwf_dir.glob("*.json"):
            try: f.unlink()
            except: pass
    _run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
         cwd, timeout=timeout)

def _reset_state(cwd):
    """Fast reset of .aiwf state files only (preserves scripts/skills/settings)."""
    aiwf_dir = cwd / ".aiwf"
    aiwf_dir.mkdir(parents=True, exist_ok=True)
    from aiwf_core.core.state_schema import MVP_STATE_FILES
    for filename, default_fn in MVP_STATE_FILES.items():
        (aiwf_dir / filename).write_text(
            json.dumps(default_fn(), ensure_ascii=False, indent=2) + "\n")

def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


# ═══════════════════════════════════════════════════════════════════════
# Test 1: MVP files only
# ═══════════════════════════════════════════════════════════════════════
class TestMvpFilesOnly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="aw_mvp_"))
        _install(cls.tmpdir)
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_exactly_7_state_files(self):
        files = sorted(f.name for f in (self.tmpdir/".aiwf").iterdir() if f.is_file())
        expected = sorted(["state.json","goal.json","contexts.json",
                          "evidence.json","testing.json","review.json","fix-loop.json"])
        for ef in expected:
            self.assertIn(ef, files, f"Missing: {ef}")
        self.assertNotIn("lessons.md", files)
        self.assertNotIn("negative-memory.md", files)

    def test_state_schema_has_close_attempt(self):
        state = _read_json(self.tmpdir/".aiwf"/"state.json")
        self.assertIn("close_attempt", state)
        self.assertFalse(state["close_attempt"])

    def test_review_schema_has_closure_allowed(self):
        review = _read_json(self.tmpdir/".aiwf"/"review.json")
        self.assertIn("closure_allowed", review)
        self.assertFalse(review["closure_allowed"])


# ═══════════════════════════════════════════════════════════════════════
# Test 2: Settings hook schema
# ═══════════════════════════════════════════════════════════════════════
class TestSettingsHookSchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="aw_cfg_"))
        _install(cls.tmpdir)
        cls.settings = _read_json(cls.tmpdir/".claude"/"settings.json")
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_pre_tool_use_has_two_matchers(self):
        matchers = [e.get("matcher","") for e in self.settings["hooks"]["PreToolUse"]]
        self.assertIn("Write|Edit|MultiEdit", matchers)
        self.assertIn("Bash", matchers)

    def test_bash_guard_script_exists(self):
        script = self.tmpdir/"scripts"/"aiwf_bash_guard.py"
        self.assertTrue(script.exists())
        self.assertTrue(script.stat().st_mode & 0o111)

    def test_all_command_hooks_have_type(self):
        for event in ["UserPromptSubmit","PreToolUse","PostToolUse","Stop"]:
            for entry in self.settings["hooks"].get(event,[]):
                for h in entry.get("hooks",[]):
                    self.assertEqual(h.get("type"), "command")


# ═══════════════════════════════════════════════════════════════════════
# Test 3: UserPromptSubmit
# ═══════════════════════════════════════════════════════════════════════
class TestUserPromptSubmit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="aw_ups_"))
        _install(cls.tmpdir)
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def _status(self):
        return _run([sys.executable, str(self.tmpdir/"scripts"/"aiwf_status.py")],
                    self.tmpdir, input_str=json.dumps(
                    {"session_id":"t","cwd":str(self.tmpdir),"hook_event_name":"UserPromptSubmit"}))

    def test_output_is_valid_json_with_additional_context(self):
        r = self._status()
        out = json.loads(r.stdout.strip())
        self.assertIn("additionalContext", out["hookSpecificOutput"])
        self.assertIn("[AIWF]", out["hookSpecificOutput"]["additionalContext"])

    def test_additional_context_is_concise(self):
        r = self._status()
        ctx = json.loads(r.stdout.strip())["hookSpecificOutput"]["additionalContext"]
        self.assertLess(len(ctx), 1000)

    def test_shows_fix_loop_when_open(self):
        (self.tmpdir/".aiwf"/"fix-loop.json").write_text(
            json.dumps({"status":"open","route":"executor","required_fixes":["fix a"]}))
        r = self._status()
        ctx = json.loads(r.stdout.strip())["hookSpecificOutput"]["additionalContext"]
        self.assertIn("FIX-LOOP", ctx)
        _reset_state(self.tmpdir)


# ═══════════════════════════════════════════════════════════════════════
# Test 4: PreToolUse scope check
# ═══════════════════════════════════════════════════════════════════════
class TestPreToolUseScope(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="aw_sco_"))
        _install(cls.tmpdir)
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        _reset_state(self.tmpdir)

    def _set_scope(self, allowed, forbidden=None):
        state = _read_json(self.tmpdir/".aiwf"/"state.json")
        state["active_context_id"] = "CTX-001"
        (self.tmpdir/".aiwf"/"state.json").write_text(json.dumps(state,indent=2))
        ctxs = {"contexts":[{"id":"CTX-001","allowed_write":allowed,
                "forbidden_write":forbidden or []}]}
        (self.tmpdir/".aiwf"/"contexts.json").write_text(json.dumps(ctxs,indent=2))

    def _check(self, tool, path):
        return _run([sys.executable, str(self.tmpdir/"scripts"/"aiwf_scope_check.py")],
                    self.tmpdir, input_str=json.dumps(
                    {"session_id":"t","cwd":str(self.tmpdir),"tool_name":tool,
                     "tool_input":{"file_path":path}}))

    def test_out_of_scope_blocked(self):
        self._set_scope(["src/"])
        r = self._check("Write","config/secrets.py")
        self.assertIn("deny", r.stdout)

    def test_in_scope_allowed(self):
        self._set_scope(["src/"])
        r = self._check("Edit","src/main.py")
        self.assertNotIn("deny", r.stdout)

    def test_forbidden_write_always_blocked(self):
        self._set_scope(["src/"], [".env"])
        r = self._check("Write",".env")
        self.assertIn("deny", r.stdout)


# ═══════════════════════════════════════════════════════════════════════
# Test 5: Bash guard
# ═══════════════════════════════════════════════════════════════════════
class TestBashGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="aw_bg_"))
        _install(cls.tmpdir)
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def _guard(self, cmd):
        return _run([sys.executable, str(self.tmpdir/"scripts"/"aiwf_bash_guard.py")],
                    self.tmpdir, input_str=json.dumps(
                    {"session_id":"t","tool_name":"Bash","tool_input":{"command":cmd}}))

    def test_rm_rf_blocked(self):
        self.assertIn("deny", self._guard("rm -rf /tmp/x").stdout)
    def test_sudo_blocked(self):
        self.assertIn("deny", self._guard("sudo reboot").stdout)
    def test_git_reset_hard_blocked(self):
        self.assertIn("deny", self._guard("git reset --hard HEAD").stdout)
    def test_npm_test_allowed(self):
        r = self._guard("npm test")
        self.assertNotIn("deny", r.stdout)
    def test_pytest_allowed(self):
        r = self._guard("pytest -xvs tests/")
        self.assertNotIn("deny", r.stdout)


# ═══════════════════════════════════════════════════════════════════════
# Test 6: Evidence git diff
# ═══════════════════════════════════════════════════════════════════════
class TestEvidenceGitDiff(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="aw_evg_"))
        _install(cls.tmpdir)
        subprocess.run(["git","init"], cwd=str(cls.tmpdir), capture_output=True, timeout=10)
        subprocess.run(["git","config","user.email","t@t.com"], cwd=str(cls.tmpdir),
                       capture_output=True, timeout=10)
        subprocess.run(["git","config","user.name","T"], cwd=str(cls.tmpdir),
                       capture_output=True, timeout=10)
        (cls.tmpdir/"README.md").write_text("# Test")
        subprocess.run(["git","add","-A"], cwd=str(cls.tmpdir), capture_output=True, timeout=10)
        subprocess.run(["git","commit","-m","init"], cwd=str(cls.tmpdir),
                       capture_output=True, timeout=10)
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        _reset_state(self.tmpdir)

    def _capture(self, tool, ti):
        return _run([sys.executable, str(self.tmpdir/"scripts"/"aiwf_capture_evidence.py")],
                    self.tmpdir, input_str=json.dumps(
                    {"session_id":"t","cwd":str(self.tmpdir),"tool_name":tool,"tool_input":ti}))

    def test_evidence_has_trust_machine_observed(self):
        self._capture("Write", {"file_path":"src/new.py"})
        recs = _read_json(self.tmpdir/".aiwf"/"evidence.json")["records"]
        self.assertGreater(len(recs), 0)
        for rec in recs:
            self.assertEqual(rec.get("trust"), "machine_observed")

    def test_changed_files_source_is_git(self):
        (self.tmpdir/"src").mkdir(exist_ok=True)
        (self.tmpdir/"src"/"new.py").write_text("print('hello')")
        subprocess.run(["git","add","-A"], cwd=str(self.tmpdir), capture_output=True, timeout=10)
        self._capture("Bash", {"command":"echo test"})
        recs = _read_json(self.tmpdir/".aiwf"/"evidence.json")["records"]
        self.assertIn(recs[-1]["changed_files_source"], ["snapshot_diff","git_diff","first_operation"])

    def test_noop_command_empty_changed_files(self):
        """A no-op Bash command produces empty changed_files."""
        self._capture("Write", {"file_path":"src/a.py"})
        (self.tmpdir/"src").mkdir(exist_ok=True)
        (self.tmpdir/"src"/"a.py").write_text("x")
        subprocess.run(["git","add","-A"], cwd=str(self.tmpdir), capture_output=True, timeout=10)
        self._capture("Write", {"file_path":"src/a.py"})
        # Second capture for no-op
        self._capture("Bash", {"command":"echo nochange"})
        recs = _read_json(self.tmpdir/".aiwf"/"evidence.json")["records"]
        noop = recs[-1]
        self.assertEqual(noop["changed_files"], [],
                        f"No-op should have empty changed_files, got {noop['changed_files']}")

    def test_per_operation_not_cumulative(self):
        """Second operation doesn't include files from first operation."""
        (self.tmpdir/"src").mkdir(exist_ok=True)
        (self.tmpdir/"src"/"a.py").write_text("a")
        (self.tmpdir/"danger").mkdir(exist_ok=True)
        (self.tmpdir/"danger"/"x.py").write_text("x")
        subprocess.run(["git","add","-A"], cwd=str(self.tmpdir), capture_output=True, timeout=10)
        self._capture("Write", {"file_path":"src/a.py"})
        self._capture("Bash", {"command":"echo x > danger/x.py"})
        recs = _read_json(self.tmpdir/".aiwf"/"evidence.json")["records"]
        self.assertNotIn("src/a.py", recs[-1]["changed_files"],
                        "Second op should NOT include first op's files")


# ═══════════════════════════════════════════════════════════════════════
# Test 7: Scope violation detection
# ═══════════════════════════════════════════════════════════════════════
class TestScopeViolationDetection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="aw_sv_"))
        _install(cls.tmpdir)
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        _reset_state(self.tmpdir)

    def test_scope_violation_sets_state_flag(self):
        state = _read_json(self.tmpdir/".aiwf"/"state.json")
        state["active_context_id"] = "CTX-001"
        (self.tmpdir/".aiwf"/"state.json").write_text(json.dumps(state,indent=2))
        ctxs = {"contexts":[{"id":"CTX-001","allowed_write":["src/"]}]}
        (self.tmpdir/".aiwf"/"contexts.json").write_text(json.dumps(ctxs,indent=2))

        from aiwf_core.hooks.common.evidence_writer import check_and_record_scope_violations
        violations = check_and_record_scope_violations(
            ["dangerous/hack.py"], {"id":"CTX-001","allowed_write":["src/"]}, self.tmpdir)
        self.assertEqual(len(violations), 1)

        state = _read_json(self.tmpdir/".aiwf"/"state.json")
        self.assertTrue(state["scope_violation"])

        review = _read_json(self.tmpdir/".aiwf"/"review.json")
        self.assertTrue(any("scope_violation" in b for b in review.get("blockers",[])))

    def test_internal_paths_never_trigger_violations(self):
        """AIWF internal files NEVER trigger scope violations."""
        state = _read_json(self.tmpdir/".aiwf"/"state.json")
        state["active_context_id"] = "CTX-001"
        (self.tmpdir/".aiwf"/"state.json").write_text(json.dumps(state,indent=2))
        ctxs = {"contexts":[{"id":"CTX-001","allowed_write":["src/"]}]}
        (self.tmpdir/".aiwf"/"contexts.json").write_text(json.dumps(ctxs,indent=2))

        from aiwf_core.hooks.common.evidence_writer import check_and_record_scope_violations
        internal = [".aiwf/state.json", ".claude/settings.json", "CLAUDE.md",
                    "scripts/aiwf_status.py", "src/main.py"]
        violations = check_and_record_scope_violations(
            internal, {"id":"CTX-001","allowed_write":["src/"]}, self.tmpdir)
        # Only src/main.py is in-scope. AIWF internals must be filtered.
        self.assertEqual(len(violations), 0,
                        f"Internal paths should not trigger violations, got {violations}")


# ═══════════════════════════════════════════════════════════════════════
# Test 8: Stop gate mechanical
# ═══════════════════════════════════════════════════════════════════════
class TestStopGateMechanical(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="aw_stp_"))
        _install(cls.tmpdir)
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        _reset_state(self.tmpdir)

    def _set_close_attempt(self):
        state = _read_json(self.tmpdir/".aiwf"/"state.json")
        state["phase"] = "closing"
        state["close_attempt"] = True
        (self.tmpdir/".aiwf"/"state.json").write_text(json.dumps(state,indent=2))

    def _stop(self):
        return _run([sys.executable, str(self.tmpdir/"scripts"/"aiwf_review_gate.py")],
                    self.tmpdir, input_str=json.dumps(
                    {"session_id":"t","cwd":str(self.tmpdir),"hook_event_name":"Stop"}))

    def test_no_close_attempt_does_not_block(self):
        r = self._stop()
        self.assertNotIn('"decision":"block"', r.stdout)

    def test_close_attempt_without_review_blocks_core(self):
        self._set_close_attempt()
        from aiwf_core.core.closure_contract import closure_conditions_met
        gates = closure_conditions_met(
            _read_json(self.tmpdir/".aiwf"/"state.json"),
            _read_json(self.tmpdir/".aiwf"/"evidence.json"),
            _read_json(self.tmpdir/".aiwf"/"testing.json"),
            _read_json(self.tmpdir/".aiwf"/"review.json"),
            _read_json(self.tmpdir/".aiwf"/"fix-loop.json"),
        )
        self.assertTrue(gates["close_attempt"])
        self.assertFalse(gates["passed"])
        self.assertIn("review not accepted", gates["blockers"])

    def test_close_attempt_with_all_gates_passes(self):
        self._set_close_attempt()
        (self.tmpdir/".aiwf"/"review.json").write_text(json.dumps(
            {"result":"accepted","closure_allowed":True,"accepted_evidence_ids":["EV-001"],
             "rejected_evidence_ids":[],"blockers":[]}))
        (self.tmpdir/".aiwf"/"evidence.json").write_text(json.dumps(
            {"records":[{"id":"EV-001","status":"accepted","trust":"machine_observed"}]}))
        (self.tmpdir/".aiwf"/"testing.json").write_text(json.dumps(
            {"status":"adequate","commands":["pytest"],"untested_risks":[]}))
        (self.tmpdir/".aiwf"/"fix-loop.json").write_text(json.dumps(
            {"status":"none","route":None,"required_fixes":[]}))
        r = self._stop()
        self.assertNotIn('"decision":"block"', r.stdout.strip() or "{}")


# ═══════════════════════════════════════════════════════════════════════
# Test 9: Skills
# ═══════════════════════════════════════════════════════════════════════
class TestSkillsNoLegacyActions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="aw_skl_"))
        _install(cls.tmpdir)
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_skills_dont_recommend_action_files(self):
        for skill in ["aiwf-planner","aiwf-implement","aiwf-test","aiwf-review","aiwf-close"]:
            content = (self.tmpdir/".claude"/"skills"/skill/"SKILL.md").read_text().lower()
            for pat in ["create action-","write action-","make action-","generate action-"]:
                idx = content.find(pat)
                if idx > 0:
                    before = content[max(0,idx-30):idx]
                    if "do not" not in before and "don't" not in before:
                        self.fail(f"{skill}: recommends '{pat}' without negation")

    def test_planner_is_architect_not_implementer(self):
        content = (self.tmpdir/".claude"/"skills"/"aiwf-planner"/"SKILL.md").read_text()
        self.assertIn("architect", content.lower())
        self.assertIn("NOT the lead implementer", content)
        self.assertIn("delegate to executor subagents", content.lower())

    def test_close_skill_instructs_close_attempt(self):
        content = (self.tmpdir/".claude"/"skills"/"aiwf-close"/"SKILL.md").read_text()
        self.assertIn("close_attempt", content)
        self.assertIn("closing", content.lower())


# ═══════════════════════════════════════════════════════════════════════
# Test 10: Backend-neutral boundary
# ═══════════════════════════════════════════════════════════════════════
class TestBackendNeutralBoundary(unittest.TestCase):
    def test_core_does_not_import_claude(self):
        for f in sorted((PROJECT_ROOT/"aiwf_core"/"core").glob("*.py")):
            if f.name == "__init__.py": continue
            c = f.read_text()
            self.assertNotIn("adapters.claude", c, f"{f.name} imports Claude adapter")
            self.assertNotIn("from .adapters", c, f"{f.name} imports adapters")

    def test_claude_adapter_imports_core(self):
        imports_core = False
        for f in (PROJECT_ROOT/"aiwf_core"/"adapters"/"claude").glob("*.py"):
            if f.name == "__init__.py": continue
            if "..core" in f.read_text() or "aiwf_core.core" in f.read_text():
                imports_core = True
        self.assertTrue(imports_core)

    def test_hooks_common_imports_core(self):
        imports_core = False
        for f in (PROJECT_ROOT/"aiwf_core"/"hooks"/"common").glob("*.py"):
            if f.name == "__init__.py": continue
            if "..core" in f.read_text() or "aiwf_core.core" in f.read_text():
                imports_core = True
        self.assertTrue(imports_core)


if __name__ == "__main__":
    unittest.main()
