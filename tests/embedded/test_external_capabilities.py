"""External capability registry: classification, filtering, no secrets, status.
Uses setUpClass template project to avoid per-test install. ~2s full file."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15

class TestExternalCapabilities(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._template = Path(tempfile.mkdtemp(prefix="awec_tmpl_"))
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                           capture_output=True, text=True, cwd=str(cls._template), env=env, timeout=30)
        if r.returncode != 0:
            shutil.rmtree(cls._template, ignore_errors=True)
            raise RuntimeError(f"install failed: {r.stderr}")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._template, ignore_errors=True)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="awec_t_"))
        shutil.copytree(self._template, self.tmp, dirs_exist_ok=True, symlinks=False)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *args):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, "-m", "aiwf_core.cli"] + list(args),
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    def _run_ok(self, *args):
        r = self._run(*args)
        self.assertEqual(r.returncode, 0, f"Command failed: {args}\nstderr: {r.stderr[:300]}")
        return r

    def _status(self):
        inp = json.dumps({"session_id":"t","cwd":str(self.tmp),"hook_event_name":"UserPromptSubmit"})
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp/"scripts"/"aiwf_status.py")],
                           input=inp, capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        self.assertEqual(r.returncode, 0, f"status script failed: {r.stderr[:200]}")
        return json.loads(r.stdout.strip())["hookSpecificOutput"]["additionalContext"]

    def _reg(self):
        v2 = self.tmp / ".aiwf" / "assets" / "capabilities.json"
        legacy = self.tmp / ".aiwf" / "capabilities.json"
        src = v2 if v2.exists() else legacy
        return json.loads(src.read_text())

    def _add_skill(self, name, content):
        (self.tmp/".claude"/"skills"/name).mkdir(parents=True)
        (self.tmp/".claude"/"skills"/name/"SKILL.md").write_text(content)

    def _add_hook(self, event_name):
        s = json.loads((self.tmp/".claude"/"settings.json").read_text())
        s.setdefault("hooks",{})
        s["hooks"][event_name] = [{"matcher":"","hooks":[{"type":"command","command":"osascript -e beep"}]}]
        (self.tmp/".claude"/"settings.json").write_text(json.dumps(s, indent=2))

    def _add_mcp(self, name="docs", secret="do-not-store"):
        s = json.loads((self.tmp/".claude"/"settings.json").read_text())
        s["mcpServers"] = {name: {"command":"node","args":["s.js"],"env":{"SECRET_TOKEN":secret}}}
        (self.tmp/".claude"/"settings.json").write_text(json.dumps(s, indent=2))

    def _add_command(self, name):
        (self.tmp/".claude"/"commands").mkdir(parents=True, exist_ok=True)
        (self.tmp/".claude"/"commands"/f"{name}.md").write_text("# Check\nRun checks.\n")

    def _seed_plan(self, task_id):
        plan_dir = self.tmp / ".aiwf" / "plans"
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / f"{task_id}.md").write_text(
            f"# {task_id}\n\n"
            "## Goal\nTest task\n\n"
            "## Scope\n- Change: test files\n\n"
            "## Verification\n- Machine-verifiable: yes\n\n"
            "## Impact\n"
            "- docs: no — test\n"
            "- project_map: no — test\n"
            "- environment: no — test\n"
            "- capabilities: no — test\n"
            "- quality_summary: no — test\n",
            encoding="utf-8",
        )

    # ── clean install ──
    def test_clean_install_zero_external(self):
        self._run_ok("capability", "scan")
        leaked = [c["id"] for c in self._reg()["capabilities"]
                  if c["id"].startswith(("skill:aiwf-","agent:aiwf-"))]
        self.assertEqual(len(leaked), 0, f"AIWF internals leaked: {leaked}")

    # ── normal skill ──
    def test_normal_skill_method_advisory_advisory(self):
        self._add_skill("karpathy", "# Karpathy\nThink first.\n")
        self._run_ok("capability", "scan")
        sk = [c for c in self._reg()["capabilities"] if c["id"]=="skill:karpathy"][0]
        self.assertEqual(sk["risk"], "method_advisory")
        self.assertEqual(sk["use_policy"], "advisory")
        self.assertFalse(sk["may_modify_project"])

    def test_normal_skill_no_high_risk_status(self):
        self._add_skill("karpathy", "# Karpathy\nThink first.\n")
        self._run_ok("capability", "scan")
        ctx = self._status()
        self.assertIn("Process: level=L1_review_light mode=execution route=linear", ctx)
        self.assertNotIn("External capabilities:", ctx)
        self.assertNotIn("high-risk", ctx)

    # ── dangerous skill ──
    def test_dangerous_skill_requires_user_decision(self):
        self._add_skill("deployer", "# Deployer\nDeploy and git push.\n")
        self._run_ok("capability", "scan")
        sk = [c for c in self._reg()["capabilities"] if c["id"]=="skill:deployer"][0]
        self.assertEqual(sk["use_policy"], "requires_user_decision")
        self.assertTrue(sk["may_modify_project"])

    def test_dangerous_skill_high_risk_status(self):
        self._add_skill("deployer", "# Deployer\nDeploy and git push.\n")
        self._run_ok("capability", "scan")
        ctx = self._status()
        self.assertIn("Process: level=L1_review_light mode=execution route=linear", ctx)
        self.assertNotIn("high-risk entries need Planner review", ctx)

    # ── unknown hook ──
    def test_external_hook_detected(self):
        self._add_hook("Notification")
        self._run_ok("capability", "scan")
        hooks = [c for c in self._reg()["capabilities"] if c["kind"]=="hook"]
        self.assertGreater(len(hooks), 0)

    def test_unknown_hook_high_risk_status(self):
        self._add_hook("Notification")
        self._run_ok("capability", "scan")
        ctx = self._status()
        self.assertIn("Process: level=L1_review_light mode=execution route=linear", ctx)
        self.assertNotIn("high-risk entries need Planner review", ctx)

    # ── MCP secrets ──
    def test_mcp_no_secrets(self):
        self._add_mcp(secret="do-not-store")
        self._run_ok("capability", "scan")
        text = json.dumps(self._reg())
        self.assertNotIn("do-not-store", text)
        self.assertNotIn("SECRET_TOKEN", text)

    # ── command ──
    def test_command_detected(self):
        self._add_command("check")
        self._run_ok("capability", "scan")
        cmds = [c for c in self._reg()["capabilities"] if c["kind"]=="slash_command"]
        self.assertIn("command:check", [c["id"] for c in cmds])

    # ── list / show ──
    def test_list_shows_fields(self):
        self._add_skill("karpathy", "# Karpathy\nThink first.\n")
        r = self._run_ok("capability", "scan")
        r = self._run_ok("capability", "list")
        self.assertIn("risk=", r.stdout); self.assertIn("policy=", r.stdout)
        self.assertIn("type=", r.stdout)
        self.assertIn("skill:karpathy", r.stdout)
        self.assertNotIn("skill:aiwf-planner", r.stdout)

    def test_lifecycle_skill_requires_planner_decision(self):
        self._add_skill("tdd", "# TDD\nWrite a failing test before implementation.\n")
        self._run_ok("capability", "scan")
        sk = [c for c in self._reg()["capabilities"] if c["id"]=="skill:tdd"][0]

        self.assertEqual(sk["capability_type"], "testing_method")
        self.assertTrue(sk["lifecycle_overlap"])
        self.assertEqual(sk["use_policy"], "requires_user_decision")

    def test_requirements_grill_is_clarification_not_execution(self):
        self._add_skill("grill-me", "# Grill Me\nAsk clarifying questions until requirements are precise.\n")
        self._run_ok("capability", "scan")
        sk = [c for c in self._reg()["capabilities"] if c["id"]=="skill:grill-me"][0]

        self.assertEqual(sk["capability_type"], "clarification")
        self.assertFalse(sk["lifecycle_overlap"])
        self.assertEqual(sk["use_policy"], "advisory")

    def test_compound_workflow_commands_are_lifecycle_overlap(self):
        self._add_command("ce-plan")
        self._add_command("ce-work")
        self._run_ok("capability", "scan")
        caps = {c["id"]: c for c in self._reg()["capabilities"]}

        self.assertEqual(caps["command:ce-plan"]["capability_type"], "planning_advisory")
        self.assertTrue(caps["command:ce-plan"]["lifecycle_overlap"])
        self.assertEqual(caps["command:ce-work"]["capability_type"], "implementation_helper")
        self.assertTrue(caps["command:ce-work"]["lifecycle_overlap"])
        self.assertEqual(caps["command:ce-work"]["use_policy"], "requires_user_decision")

    def test_planned_lifecycle_capability_blocks_activation_until_decided(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        (self.tmp / ".aiwf" / "reports" / "当前状态.md").unlink(missing_ok=True)
        self._add_skill("tdd", "# TDD\nWrite a failing test before implementation.\n")
        self._run_ok("capability", "scan")
        upsert_task(str(self.tmp), "TASK-001", "Use external TDD helper", status="ready")
        self._seed_plan("TASK-001")

        without_planned_use = activate_task(str(self.tmp), "TASK-001")
        self.assertTrue(without_planned_use["activated"], without_planned_use["blockers"])

        from aiwf_core.core.task_ledger import close_task
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["phase"] = "closed"
        state["closure_allowed"] = True
        state_path.write_text(json.dumps(state, indent=2))
        close_task(str(self.tmp), "TASK-001")
        upsert_task(str(self.tmp), "TASK-002", "Use external TDD helper", status="ready")
        self._seed_plan("TASK-002")
        self._run_ok("capability", "plan-use", "skill:tdd")
        blocked = activate_task(str(self.tmp), "TASK-002")
        self.assertFalse(blocked["activated"])
        self.assertTrue(any("lifecycle-overlap capability requires explicit Planner decision" in b for b in blocked["blockers"]))

        self._run_ok("capability", "decide", "skill:tdd", "--decision", "Use only as a testing method; AIWF Tester remains authoritative")
        allowed = activate_task(str(self.tmp), "TASK-002")
        self.assertTrue(allowed["activated"], allowed["blockers"])

    def test_show_returns_zero(self):
        self._add_mcp(); self._run_ok("capability", "scan")
        self.assertEqual(self._run_ok("capability", "show", "mcp:docs").returncode, 0)

    def test_show_no_secrets(self):
        self._add_mcp(secret="do-not-store"); self._run_ok("capability", "scan")
        self.assertNotIn("do-not-store", self._run("capability", "show", "mcp:docs").stdout)

    def test_show_missing_no_traceback(self):
        self._run_ok("capability", "scan")
        self.assertNotEqual(self._run("capability", "show", "nonexistent").returncode, 0)

    # ── no side effects ──
    def test_scan_no_modify_settings(self):
        self._add_skill("karpathy", "# K\n")
        before = (self.tmp/".claude"/"settings.json").read_text()
        self._run_ok("capability", "scan")
        self.assertEqual(before, (self.tmp/".claude"/"settings.json").read_text())

    def test_scan_no_modify_claude_md(self):
        self._add_skill("karpathy", "# K\n")
        before = (self.tmp/"CLAUDE.md").read_text()
        self._run_ok("capability", "scan")
        self.assertEqual(before, (self.tmp/"CLAUDE.md").read_text())

    # ── status prompt cache ──
    def test_status_none_when_empty(self):
        ctx = self._status()
        self.assertIn("Process: level=L1_review_light mode=execution route=linear", ctx)
        self.assertNotIn("External capabilities:", ctx)

    def test_status_no_dump_registry(self):
        self._add_skill("karpathy", "# Karpathy\nThink first.\n")
        self._run_ok("capability", "scan")
        ctx = self._status()
        self.assertNotIn("mcp_server", ctx)
        self.assertNotIn("skill:karpathy", ctx)

    # ── planner skill ──
    def test_planner_skill_mentions_cannot_override(self):
        c = (self.tmp/".claude"/"skills"/"aiwf-planner-contracts"/"SKILL.md").read_text()
        self.assertIn("cannot override", c.lower())


if __name__ == "__main__":
    unittest.main()
