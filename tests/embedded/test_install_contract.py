"""Focused install contract test — fast, deterministic, no shared state."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15


def _run(cmd, cwd, **kw):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    return subprocess.run(cmd, capture_output=True, text=True,
                          cwd=str(cwd), env=env, timeout=TIMEOUT, **kw)


class TestInstall(unittest.TestCase):
    """aiwf install claude produces correct files and structure."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="awin_"))
        _run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
             self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _j(self, rel):
        return json.loads((self.tmp / rel).read_text())

    def test_v2_state_files_created_without_flat_runtime_state(self):
        expected = [
            ".aiwf/state/contexts.json",
            ".aiwf/evidence/records.json",
            ".aiwf/state/fix-loop.json",
            ".aiwf/state/goal.json",
            ".aiwf/quality/review.json",
            ".aiwf/state/state.json",
            ".aiwf/quality/testing.json",
        ]
        for rel in expected:
            self.assertTrue((self.tmp / rel).exists(), f"Missing: {rel}")
        for old in ["contexts.json", "evidence.json", "fix-loop.json",
                    "goal.json", "review.json", "state.json", "testing.json"]:
            self.assertFalse((self.tmp / ".aiwf" / old).exists(), f"Flat runtime file should not exist: {old}")
        self.assertFalse((self.tmp / ".aiwf" / "lessons.md").exists())
        self.assertFalse((self.tmp / ".aiwf" / "negative-memory.md").exists())

    def test_settings_json_has_nested_hooks(self):
        s = self._j(".claude/settings.json")
        for ev in ["UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"]:
            for entry in s["hooks"][ev]:
                for h in entry["hooks"]:
                    self.assertEqual(h["type"], "command")
                    self.assertIn("command", h)

    def test_pre_tool_use_has_snapshot_and_scope_and_bash(self):
        s = self._j(".claude/settings.json")
        matchers = [e.get("matcher", "") for e in s["hooks"]["PreToolUse"]]
        self.assertIn("Write|Edit|MultiEdit|Bash", matchers)  # snapshot
        self.assertIn("Write|Edit|MultiEdit", matchers)       # scope check
        self.assertIn("Bash", matchers)                        # bash guard

    def test_skills_exist_with_frontmatter(self):
        for skill in ["aiwf-planner", "aiwf-implement", "aiwf-test",
                      "aiwf-review", "aiwf-close", "aiwf-explore", "aiwf-curate"]:
            path = self.tmp / ".claude" / "skills" / skill / "SKILL.md"
            self.assertTrue(path.exists(), f"Missing: {skill}")
            self.assertTrue(path.read_text().startswith("---"),
                          f"No frontmatter: {skill}")

    def test_subagents_exist(self):
        for agent in ["aiwf-explorer", "aiwf-executor", "aiwf-tester",
                      "aiwf-reviewer", "aiwf-curator"]:
            path = self.tmp / ".claude" / "agents" / f"{agent}.md"
            self.assertTrue(path.exists(), f"Missing: {agent}")

    def test_claude_subagents_have_connection_recovery(self):
        for agent in ["aiwf-executor", "aiwf-tester", "aiwf-reviewer"]:
            content = (self.tmp / ".claude" / "agents" / f"{agent}.md").read_text()
            self.assertIn("Connection Recovery", content)
            self.assertIn("PAUSED_FOR_PLANNER", content)
            self.assertIn("resume package", content)
            self.assertNotIn("max-iters", content)
        planner = (self.tmp / ".claude" / "skills" / "aiwf-planner" / "SKILL.md").read_text()
        self.assertIn("Subagent Connection Recovery", planner)
        self.assertIn("interrupted/resumable run", planner)

    def test_status_shows_embedded_mode(self):
        r = _run([sys.executable, "-m", "aiwf_core.cli", "status"], self.tmp)
        self.assertIn("Embedded Claude Code", r.stdout)
        self.assertIn("Phase:", r.stdout)

    def test_claude_md_exists(self):
        self.assertTrue((self.tmp / "CLAUDE.md").exists())

    def test_scripts_are_executable(self):
        for s in ["aiwf_status.py", "aiwf_pre_snapshot.py", "aiwf_scope_check.py",
                  "aiwf_bash_guard.py", "aiwf_capture_evidence.py",
                  "aiwf_review_gate.py", "aiwf_export_report.py"]:
            p = self.tmp / "scripts" / s
            self.assertTrue(p.exists(), f"Missing: {s}")
            self.assertTrue(p.stat().st_mode & 0o111, f"Not executable: {s}")



    def test_no_legacy_ai_workflow_dir(self):
        """Embedded install does NOT create legacy .ai-workflow directory."""
        self.assertFalse((self.tmp / ".ai-workflow").exists(),
                        ".ai-workflow should NOT be created by embedded install")

    def test_claude_md_has_managed_block(self):
        """CLAUDE.md contains AIWF managed block markers."""
        content = (self.tmp / "CLAUDE.md").read_text()
        self.assertIn("AIWF MANAGED BLOCK START", content)
        self.assertIn("AIWF MANAGED BLOCK END", content)

    def test_claude_md_has_runtime_protocol(self):
        """Generated CLAUDE.md tells planner-main how to resume from mechanical state."""
        content = (self.tmp / "CLAUDE.md").read_text()
        self.assertIn("## Runtime Protocol", content)
        self.assertIn("Run `aiwf status` before deciding the next workflow action", content)
        self.assertIn("Recovery", content)
        self.assertIn("PRIMARY", content)
        self.assertIn("REQUIRED NEXT", content)
        self.assertIn("Do not roleplay Executor, Tester, or Reviewer", content)

    def test_claude_md_managed_block_idempotent(self):
        """Second install does not duplicate managed block."""
        import subprocess, sys, os
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, "-m", "aiwf_core.cli",
                        "install", "claude", "--force"],
                       capture_output=True, text=True,
                       cwd=str(self.tmp), env=env, timeout=20)
        content = (self.tmp / "CLAUDE.md").read_text()
        count = content.count("AIWF MANAGED BLOCK START")
        self.assertEqual(count, 1, f"Managed block should appear once, got {count}")

    def test_claude_md_preserves_user_content(self):
        """Existing CLAUDE.md user content is preserved."""
        # Write a custom CLAUDE.md
        (self.tmp / "CLAUDE.md").write_text("# My Project Rules\nKeep this.\n")
        import subprocess, sys, os
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, "-m", "aiwf_core.cli",
                        "install", "claude", "--force"],
                       capture_output=True, text=True,
                       cwd=str(self.tmp), env=env, timeout=20)
        content = (self.tmp / "CLAUDE.md").read_text()
        self.assertIn("My Project Rules", content)
        self.assertIn("Keep this.", content)
        self.assertIn("AIWF MANAGED BLOCK START", content)

    def test_all_scripts_py_compile(self):
        """All generated scripts pass py_compile."""
        import py_compile, sys
        for s in sorted((self.tmp / "scripts").glob("aiwf_*.py")):
            try:
                py_compile.compile(str(s), doraise=True)
            except py_compile.PyCompileError as e:
                self.fail(f"{s.name} failed py_compile: {e}")


class TestReasonixInstall(unittest.TestCase):
    """aiwf install reasonix preserves AIWF governance while targeting Reasonix."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="awin_reasonix_"))
        self.result = _run([sys.executable, "-m", "aiwf_core.cli", "install", "reasonix", "--force"],
                           self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _j(self, rel):
        return json.loads((self.tmp / rel).read_text())

    def test_reasonix_files_created(self):
        self.assertEqual(self.result.returncode, 0, self.result.stderr)
        self.assertTrue((self.tmp / "REASONIX.md").exists())
        self.assertTrue((self.tmp / ".reasonix" / "settings.json").exists())
        self.assertTrue((self.tmp / ".reasonix" / "skills" / "aiwf-planner" / "SKILL.md").exists())
        self.assertFalse((self.tmp / ".reasonix" / "agents" / "aiwf-executor.md").exists())
        self.assertTrue((self.tmp / ".aiwf" / "state" / "state.json").exists())
        self.assertFalse((self.tmp / ".ai-workflow").exists())

    def test_reasonix_force_install_removes_legacy_duplicate_agents(self):
        agents = self.tmp / ".reasonix" / "agents"
        agents.mkdir(parents=True, exist_ok=True)
        (agents / "aiwf-executor.md").write_text("legacy duplicate")
        result = _run([sys.executable, "-m", "aiwf_core.cli", "install", "reasonix", "--force"],
                      self.tmp)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((agents / "aiwf-executor.md").exists())

    def test_reasonix_install_output_uses_skill_command(self):
        self.assertIn("reasonix", self.result.stdout)
        self.assertIn('/skill aiwf-planner "I want to implement a feature. Let\'s discuss first."', self.result.stdout)
        self.assertNotIn('/aiwf-planner "I want to implement a feature', self.result.stdout)

    def test_reasonix_settings_use_reasonix_project_dir(self):
        settings = self._j(".reasonix/settings.json")
        commands = []
        for entries in settings["hooks"].values():
            for entry in entries:
                self.assertIn("command", entry)
                self.assertNotIn("hooks", entry)
                if "match" in entry:
                    self.assertIsInstance(entry["match"], str)
                self.assertIsInstance(entry.get("timeout"), int)
                commands.append(entry["command"])
        self.assertTrue(commands)
        self.assertTrue(all("AIWF_HOOK_ENGINE=reasonix ${REASONIX_PROJECT_DIR}/scripts/" in c for c in commands))

    def test_reasonix_subagent_skills_have_connection_recovery_without_hard_budget(self):
        for skill in ["aiwf-implement", "aiwf-test", "aiwf-review", "aiwf-architect"]:
            content = (self.tmp / ".reasonix" / "skills" / skill / "SKILL.md").read_text()
            self.assertIn("runAs: subagent", content)
            self.assertNotIn("max-iters:", content)
            self.assertNotIn("runaway loops", content)
            self.assertNotIn("Do not retry the same command", content)
            self.assertIn("Connection Recovery", content)
            self.assertIn("PAUSED_FOR_PLANNER", content)
            self.assertTrue(
                "last successful evidence" in content or "evidence reviewed" in content or "partial findings" in content,
                f"{skill} should include resumable evidence context",
            )
            if skill != "aiwf-implement":
                self.assertIn("must not be used to skip required", content)
        planner = (self.tmp / ".reasonix" / "skills" / "aiwf-planner" / "SKILL.md").read_text()
        self.assertIn("runAs: inline", planner)
        self.assertIn("Subagent Connection Recovery", planner)
        self.assertIn("interrupted/resumable run", planner)
        self.assertIn("Planner Process Guidance", planner)

    def test_reasonix_has_explorer_and_curator_subagent_skills(self):
        for skill in ["aiwf-explore", "aiwf-curate"]:
            content = (self.tmp / ".reasonix" / "skills" / skill / "SKILL.md").read_text()
            self.assertIn("runAs: subagent", content)

    def test_reasonix_planner_prompt_contains_complete_state_machine(self):
        planner = (self.tmp / ".reasonix" / "skills" / "aiwf-planner" / "SKILL.md").read_text()
        for phrase in [
            "Mandatory State Machine",
            "Request Mode Triage",
            "Orient",
            "Freeze the contract",
            "Route and dispatch",
            "Cleanup before review",
            "Fix loop when needed",
            "Planner meta-critique",
            "Task completion",
            "Closure",
            "Carry forward",
        ]:
            self.assertIn(phrase, planner)
        machine = planner.split("## Mandatory State Machine", 1)[1].split("## How to Run a Task", 1)[0]
        self.assertLess(machine.index("Cleanup before review"), machine.index("**Review**"))
        self.assertIn("Reasonix Stop **NEVER** blocks closure", planner)
        self.assertIn("run `aiwf status` once, read its Planner Process Guidance, then answer directly", planner)
        self.assertIn("blocks only activation of the next ordinary task", planner)
        self.assertIn("periodic Architect review **NEVER** blocks the current task close", planner)
        self.assertIn("Reasonix Stop **NEVER** blocks closure, regardless of `close_attempt`", planner)
        self.assertNotIn("Reasonix Stop **NEVER** treats `close_attempt=false`", planner)
        self.assertNotIn("Reasonix Stop revalidates and can block", planner)
        self.assertIn("Reasonix Stop never blocks closure, regardless of `close_attempt`", machine)

    def test_reasonix_stop_is_described_as_non_gating(self):
        settings = self._j(".reasonix/settings.json")
        self.assertIn("non-gating", settings["hooks"]["Stop"][0]["description"])
        close = (self.tmp / ".reasonix" / "skills" / "aiwf-close" / "SKILL.md").read_text()
        self.assertIn("non-gating", close)

    def test_connection_recovery_source_is_shared_partial(self):
        shared = PROJECT_ROOT / "aiwf_core" / "embedded_templates" / "shared"
        self.assertTrue((shared / "connection_recovery_planner.md").exists())
        self.assertTrue((shared / "connection_recovery_test.md").exists())
        handwritten_sources = [
            PROJECT_ROOT / "aiwf_core" / "embedded_templates" / "skills" / "aiwf-implement" / "SKILL.md",
            PROJECT_ROOT / "aiwf_core" / "embedded_templates" / "skills" / "aiwf-test" / "SKILL.md",
            PROJECT_ROOT / "aiwf_core" / "embedded_templates" / "skills" / "aiwf-review" / "SKILL.md",
            PROJECT_ROOT / "aiwf_core" / "embedded_templates" / "skills" / "aiwf-architect" / "SKILL.md",
            PROJECT_ROOT / "aiwf_core" / "embedded_templates" / "skills" / "aiwf-planner" / "SKILL.md",
            PROJECT_ROOT / "aiwf_core" / "embedded_templates" / "agents" / "aiwf-executor.md",
            PROJECT_ROOT / "aiwf_core" / "embedded_templates" / "agents" / "aiwf-tester.md",
            PROJECT_ROOT / "aiwf_core" / "embedded_templates" / "agents" / "aiwf-reviewer.md",
        ]
        for path in handwritten_sources:
            self.assertNotIn("PAUSED_FOR_PLANNER", path.read_text(), f"Recovery text should live in shared partials: {path}")

    def test_reasonix_hook_payload_blocks_by_exit_code(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        env["AIWF_HOOK_ENGINE"] = "reasonix"

        state = self._j(".aiwf/state/state.json")
        state["active_context_id"] = "CTX-001"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))
        (self.tmp / ".aiwf" / "state" / "contexts.json").write_text(json.dumps({
            "contexts": [{"id": "CTX-001", "allowed_write": ["src/"], "forbidden_write": []}]
        }, indent=2))

        write_payload = json.dumps({
            "event": "PreToolUse",
            "cwd": str(self.tmp),
            "toolName": "edit_file",
            "toolArgs": {"path": "outside.py"},
        })
        write_result = subprocess.run(
            [sys.executable, str(self.tmp / "scripts" / "aiwf_scope_check.py")],
            input=write_payload, capture_output=True, text=True,
            cwd=str(self.tmp), env=env, timeout=TIMEOUT,
        )
        self.assertEqual(write_result.returncode, 2)
        self.assertIn("outside.py", write_result.stdout)

        bash_payload = json.dumps({
            "event": "PreToolUse",
            "cwd": str(self.tmp),
            "toolName": "bash",
            "toolArgs": {"command": "sudo reboot"},
        })
        bash_result = subprocess.run(
            [sys.executable, str(self.tmp / "scripts" / "aiwf_bash_guard.py")],
            input=bash_payload, capture_output=True, text=True,
            cwd=str(self.tmp), env=env, timeout=TIMEOUT,
        )
        self.assertEqual(bash_result.returncode, 2)
        self.assertIn("AIWF Bash guard blocked", bash_result.stdout)

    def test_reasonix_status_hook_outputs_plain_text(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        env["AIWF_HOOK_ENGINE"] = "reasonix"
        payload = json.dumps({"event": "UserPromptSubmit", "cwd": str(self.tmp), "prompt": "status"})
        result = subprocess.run(
            [sys.executable, str(self.tmp / "scripts" / "aiwf_status.py")],
            input=payload, capture_output=True, text=True,
            cwd=str(self.tmp), env=env, timeout=TIMEOUT,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("[AIWF]", result.stdout)
        self.assertNotIn("hookSpecificOutput", result.stdout)

    def test_reasonix_doctor_and_status(self):
        doctor = _run([sys.executable, "-m", "aiwf_core.cli", "doctor"], self.tmp)
        self.assertEqual(doctor.returncode, 0, doctor.stderr)
        self.assertIn("Reasonix", doctor.stdout)
        self.assertIn("healthy", doctor.stdout)

        status = _run([sys.executable, "-m", "aiwf_core.cli", "status"], self.tmp)
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("Embedded Reasonix", status.stdout)

    def test_claude_install_still_supported(self):
        other = Path(tempfile.mkdtemp(prefix="awin_claude_compat_"))
        try:
            r = _run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"], other)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue((other / "CLAUDE.md").exists())
            self.assertTrue((other / ".claude" / "settings.json").exists())
        finally:
            shutil.rmtree(other, ignore_errors=True)



if __name__ == "__main__":
    unittest.main()
