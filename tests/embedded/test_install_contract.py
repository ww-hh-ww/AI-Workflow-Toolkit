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

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awin_"))
        _run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
             cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _j(self, rel):
        return json.loads((self.tmp / rel).read_text())

    def test_v2_state_files_created_without_flat_runtime_state(self):
        expected = [
            ".aiwf/state/state.json",
            ".aiwf/state/goals.json",
            ".aiwf/state/milestones.json",
            ".aiwf/state/mission.json",
            ".aiwf/state/plans.json",
            ".aiwf/state/tasks.json",
            ".aiwf/records/events.json",
        ]
        for rel in expected:
            self.assertTrue((self.tmp / rel).exists(), f"Missing: {rel}")
        for old in ["contexts.json", "evidence.json", "fix-loop.json",
                    "goals.json", "review.json", "state.json", "testing.json",
                    "mission.json"]:
            self.assertFalse((self.tmp / ".aiwf" / old).exists(), f"Flat runtime file should not exist: {old}")
        self.assertFalse((self.tmp / ".aiwf" / "lessons.md").exists())
        self.assertFalse((self.tmp / ".aiwf" / "negative-memory.md").exists())
        # V1 layout — state/, records/, goals/, plans/, tasks/, milestones/, config/, runtime/
        self.assertTrue((self.tmp / ".aiwf" / "README.md").exists())
        self.assertTrue((self.tmp / ".aiwf" / "mission.md").exists())
        self.assertTrue((self.tmp / ".aiwf" / "config" / "write-policy.json").exists())
        self.assertTrue((self.tmp / ".aiwf" / "config" / "agent-models.json").exists())
        self.assertTrue((self.tmp / ".aiwf" / "records").is_dir())
        self.assertTrue((self.tmp / ".aiwf" / "records" / "tasks").is_dir())
        for retired in (
            ".aiwf/state/fix-loop.json",
            ".aiwf/records/implementation.json",
            ".aiwf/records/testing.json",
            ".aiwf/records/review.json",
        ):
            self.assertFalse((self.tmp / retired).exists())
        self.assertTrue((self.tmp / ".aiwf" / "runtime").is_dir())
        self.assertTrue((self.tmp / ".aiwf" / "config").is_dir())
        self.assertFalse((self.tmp / ".aiwf" / "artifacts").is_dir(), "artifacts/ directory retired in V1")
        self.assertFalse((self.tmp / ".aiwf" / "archive").is_dir(), "archive/ directory retired in V1")

    def test_doctor_memory_structure_warnings_are_non_blocking(self):
        index_path = self.tmp / ".aiwf/memory/MEMORY.md"
        note_path = self.tmp / ".aiwf/memory/notes/unindexed.md"
        original_index = index_path.read_text(encoding="utf-8")
        try:
            index_path.write_text(
                original_index + "\n- [Missing](notes/missing.md) - broken link\n",
                encoding="utf-8",
            )
            note_path.write_text("# Unindexed\n", encoding="utf-8")

            result = _run(
                [sys.executable, "-m", "aiwf_core.cli", "doctor"],
                self.tmp,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("healthy_with_warnings", result.stdout)
            self.assertIn("WARN memory:", result.stdout)
            self.assertIn("links to missing note", result.stdout)
            self.assertIn("not indexed", result.stdout)
        finally:
            index_path.write_text(original_index, encoding="utf-8")
            note_path.unlink(missing_ok=True)

    def test_mission_md_is_write_surface_and_sync_derives_json(self):
        tmp = Path(tempfile.mkdtemp(prefix="awmission_"))
        try:
            r = _run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"], tmp)
            self.assertEqual(r.returncode, 0, r.stderr)

            mission_md = tmp / ".aiwf" / "mission.md"
            mission_md.write_text("""---
id: MISSION-001
type: mission
status: active
---

# Mission

## Statement

Ship the product safely.

## Boundaries

- No cloud dependency
- No silent data loss

## Goal Roots

- GOAL-ROOT

## Milestones

- MS-DEPLOY
""", encoding="utf-8")

            sync = _run([sys.executable, "-m", "aiwf_core.cli", "sync"], tmp)
            self.assertEqual(sync.returncode, 0, sync.stderr)

            mission = json.loads((tmp / ".aiwf" / "state" / "mission.json").read_text(encoding="utf-8"))
            self.assertEqual(mission["statement"], "Ship the product safely.")
            self.assertEqual(mission["boundaries"], ["No cloud dependency", "No silent data loss"])
            self.assertEqual(mission["goal_tree_root_ids"], ["GOAL-ROOT"])
            self.assertEqual(mission["milestone_ids"], ["MS-DEPLOY"])

            show = _run([sys.executable, "-m", "aiwf_core.cli", "mission", "show"], tmp)
            self.assertEqual(show.returncode, 0, show.stderr)
            self.assertIn("Ship the product safely.", show.stdout)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_install_merges_human_only_command_policy(self):
        tmp = Path(tempfile.mkdtemp(prefix="awpol_"))
        try:
            policy_path = tmp / ".aiwf" / "config" / "command-policy.json"
            policy_path.parent.mkdir(parents=True, exist_ok=True)
            policy_path.write_text(json.dumps({
                "schema_version": 1,
                "description": "old policy",
                "deny": [{
                    "command": "aiwf task force-close",
                    "reason": "old force close rule",
                    "human_only": True,
                }],
            }), encoding="utf-8")

            r = _run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"], tmp)

            self.assertEqual(r.returncode, 0, r.stderr)
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            denied = {entry["command"]: entry for entry in policy["deny"]}
            self.assertTrue(denied["aiwf task force-close"]["human_only"])
            self.assertTrue(denied["aiwf task interrupt"]["human_only"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_install_writes_default_write_policy(self):
        policy = self._j(".aiwf/config/write-policy.json")
        self.assertEqual(policy["schema_version"], 1)
        self.assertTrue(policy["project_writes_require_active_task"])
        self.assertTrue(policy["freeze_active_task_md"])
        self.assertTrue(policy["first_implementation_requires_executor"])
        self.assertEqual(policy["tester_project_writes"], "test_assets_only")
        self.assertNotIn("reviewer_project_writes", policy)
        self.assertEqual(policy["architect_project_writes"], "reports_only")
        self.assertEqual(policy["explorer_project_writes"], "deny")
        self.assertEqual(policy["critic_project_writes"], "deny")
        allowed = policy["allowed_values"]
        self.assertEqual(allowed["tester_project_writes"], ["deny", "test_assets_only", "allow_all"])
        self.assertNotIn("reviewer_project_writes", allowed)
        self.assertEqual(allowed["architect_project_writes"], ["deny", "reports_only", "allow"])
        self.assertEqual(allowed["explorer_project_writes"], ["deny", "allow"])
        self.assertEqual(allowed["critic_project_writes"], ["deny", "allow"])

    def test_package_declares_yaml_runtime_dependency(self):
        pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('dependencies = ["PyYAML>=6.0"]', pyproject)

    def test_reinstall_refreshes_write_policy_help_without_overwriting_choice(self):
        tmp = Path(tempfile.mkdtemp(prefix="awwritepolicy_"))
        try:
            policy_path = tmp / ".aiwf" / "config" / "write-policy.json"
            policy_path.parent.mkdir(parents=True, exist_ok=True)
            policy_path.write_text(json.dumps({
                "schema_version": 1,
                "description": "old help",
                "allowed_values": {"architect_project_writes": ["deny", "allow"]},
                "architect_project_writes": "deny",
                "reviewer_project_writes": "deny",
            }), encoding="utf-8")

            result = _run(
                [sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                tmp,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            self.assertEqual(policy["architect_project_writes"], "deny")
            self.assertNotIn("reviewer_project_writes", policy)
            self.assertEqual(
                policy["allowed_values"]["architect_project_writes"],
                ["deny", "reports_only", "allow"],
            )
            self.assertIn("reports_only", policy["description"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_aiwf_subagents_inherit_claude_code_tools(self):
        for agent in ["aiwf-executor", "aiwf-tester", "aiwf-reviewer",
                      "aiwf-architect", "aiwf-explorer", "aiwf-critic"]:
            content = (
                PROJECT_ROOT
                / "aiwf_core"
                / "embedded_templates"
                / "agents"
                / f"{agent}.md"
            ).read_text(encoding="utf-8")
            frontmatter = content.split("---", 2)[1]
            self.assertNotIn("tools:", frontmatter)
            self.assertNotIn("disallowedTools:", frontmatter)

    def test_agent_models_config_controls_generated_agents(self):
        tmp = Path(tempfile.mkdtemp(prefix="awmodels_"))
        try:
            first = _run(
                [sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                tmp,
            )
            self.assertEqual(first.returncode, 0, first.stderr)

            config_path = tmp / ".aiwf" / "config" / "agent-models.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(config["models"]["claude"]["aiwf-executor"], "inherit")
            self.assertEqual(config["models"]["claude"]["aiwf-explorer"], "inherit")

            executor = (tmp / ".claude" / "agents" / "aiwf-executor.md").read_text()
            explorer = (tmp / ".claude" / "agents" / "aiwf-explorer.md").read_text()
            self.assertNotIn("model:", executor.split("---", 2)[1])
            self.assertNotIn("model:", explorer.split("---", 2)[1])

            config["models"]["claude"]["aiwf-executor"] = "opus"
            config["models"]["claude"]["aiwf-explorer"] = "inherit"
            config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
            second = _run(
                [sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                tmp,
            )
            self.assertEqual(second.returncode, 0, second.stderr)

            executor = (tmp / ".claude" / "agents" / "aiwf-executor.md").read_text()
            explorer = (tmp / ".claude" / "agents" / "aiwf-explorer.md").read_text()
            self.assertIn("model: opus", executor.split("---", 2)[1])
            self.assertNotIn("model:", explorer.split("---", 2)[1])

            reasonix_first = _run(
                [sys.executable, "-m", "aiwf_core.cli", "install", "reasonix", "--force"],
                tmp,
            )
            self.assertEqual(reasonix_first.returncode, 0, reasonix_first.stderr)
            review_skill = (
                tmp / ".reasonix" / "skills" / "aiwf-review" / "SKILL.md"
            ).read_text()
            self.assertNotIn("model:", review_skill.split("---", 2)[1])
            self.assertNotIn("allowed-tools:", review_skill.split("---", 2)[1])

            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["models"]["reasonix"]["aiwf-reviewer"] = "deepseek-chat"
            config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
            reasonix_second = _run(
                [sys.executable, "-m", "aiwf_core.cli", "install", "reasonix", "--force"],
                tmp,
            )
            self.assertEqual(reasonix_second.returncode, 0, reasonix_second.stderr)
            review_skill = (
                tmp / ".reasonix" / "skills" / "aiwf-review" / "SKILL.md"
            ).read_text()
            self.assertIn("model: deepseek-chat", review_skill.split("---", 2)[1])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_reinstall_preserves_custom_claude_hooks(self):
        tmp = Path(tempfile.mkdtemp(prefix="awhooks_"))
        try:
            settings_path = tmp / ".claude" / "settings.json"
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            settings_path.write_text(json.dumps({
                "hooks": {
                    "PreToolUse": [{
                        "matcher": "Bash",
                        "hooks": [
                            {"type": "command", "command": "./custom-security-hook.sh"},
                            {"type": "command", "command": "${CLAUDE_PROJECT_DIR}/scripts/aiwf_old.py"},
                        ],
                    }],
                    "SessionEnd": [{
                        "hooks": [{"type": "command", "command": "./custom-session-hook.sh"}],
                    }],
                    "Notification": [{
                        "hooks": [{"type": "command", "command": "${CLAUDE_PROJECT_DIR}/scripts/aiwf_retired.py"}],
                    }],
                },
                "permissions": {"deny": ["Bash(rm:*)"]},
                "customSetting": "keep-me",
            }), encoding="utf-8")

            for _ in range(2):
                result = _run(
                    [sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                    tmp,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

            installed = json.loads(settings_path.read_text(encoding="utf-8"))
            commands = []
            for entries in installed["hooks"].values():
                for entry in entries:
                    commands.extend(
                        handler.get("command", "")
                        for handler in entry.get("hooks", [])
                        if isinstance(handler, dict)
                    )

            self.assertIn("./custom-security-hook.sh", commands)
            self.assertIn("./custom-session-hook.sh", commands)
            self.assertFalse(any("aiwf_old.py" in command for command in commands))
            self.assertEqual(sum("aiwf_scope_check.py" in command for command in commands), 1)
            self.assertEqual(sum("aiwf_status.py" in command for command in commands), 1)
            self.assertEqual(installed["permissions"]["deny"], ["Bash(rm:*)"])
            self.assertEqual(installed["customSetting"], "keep-me")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_settings_json_has_nested_hooks(self):
        s = self._j(".claude/settings.json")
        for ev in ["UserPromptSubmit", "PreToolUse", "PostToolUse", "SubagentStop", "Stop"]:
            for entry in s["hooks"][ev]:
                for h in entry["hooks"]:
                    self.assertEqual(h["type"], "command")
                    self.assertIn("command", h)

    def test_pre_tool_use_has_scope_bash_and_agent_gates(self):
        s = self._j(".claude/settings.json")
        matchers = [e.get("matcher", "") for e in s["hooks"]["PreToolUse"]]
        self.assertIn("Write|Edit|MultiEdit", matchers)
        self.assertIn("Bash", matchers)
        self.assertIn("Agent|Task", matchers)
        post_matchers = [e.get("matcher", "") for e in s["hooks"]["PostToolUse"]]
        self.assertIn("Skill", post_matchers)
        self.assertIn("Agent|Task", post_matchers)
        self.assertIn("Write|Edit|MultiEdit", post_matchers)
        stop_matchers = [e.get("matcher", "") for e in s["hooks"]["SubagentStop"]]
        self.assertIn(
            "aiwf-executor|aiwf-tester|aiwf-reviewer|aiwf-architect",
            stop_matchers,
        )

    def test_skills_exist_with_frontmatter(self):
        """Expected top-level skills installed, with SKILL.md frontmatter."""
        for skill in ["aiwf-planner", "aiwf-implement", "aiwf-test",
                      "aiwf-review", "aiwf-close", "aiwf-architect"]:
            path = self.tmp / ".claude" / "skills" / skill / "SKILL.md"
            self.assertTrue(path.exists(), f"Missing: {skill}")
            self.assertTrue(path.read_text().startswith("---"),
                          f"No frontmatter: {skill}")

    def test_skill_references_exist(self):
        """Reference files exist under their parent skill directories."""
        refs = {
            "aiwf-planner": ["references/task-contract.md", "references/structure-guide.md",
                           "references/writing-guide.md", "references/goal-writing.md",
                           "references/plan-writing.md", "references/milestone-writing.md"],
            "aiwf-architect": [
                "references/code-review.md",
                "references/design-review.md",
                "references/structure-review.md",
                "references/milestone-acceptance.md",
            ],
        }
        for skill, files in refs.items():
            for ref in files:
                path = self.tmp / ".claude" / "skills" / skill / ref
                self.assertTrue(path.exists(), f"Missing reference: {skill}/{ref}")

    def test_retired_skill_dirs_do_not_exist(self):
        for retired in ["aiwf-init", "aiwf-planner-docs", "aiwf-architecture-doc",
                       "aiwf-retro", "aiwf-milestone"]:
            path = self.tmp / ".claude" / "skills" / retired
            self.assertFalse(path.exists(), f"Retired skill should not exist: {retired}")

    def test_reinstall_removes_retired_review_references(self):
        tmp = Path(tempfile.mkdtemp(prefix="awretiredrefs_"))
        try:
            references = tmp / ".claude" / "skills" / "aiwf-review" / "references"
            references.mkdir(parents=True)
            for name in ["review-output.md", "trace-checklist.md", "verify-checklist.md"]:
                (references / name).write_text("old", encoding="utf-8")

            result = _run(
                [sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                tmp,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(references.exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_subagents_exist(self):
        """Expected Claude agents installed."""
        for agent in ["aiwf-explorer", "aiwf-executor", "aiwf-tester",
                      "aiwf-reviewer", "aiwf-architect"]:
            path = self.tmp / ".claude" / "agents" / f"{agent}.md"
            self.assertTrue(path.exists(), f"Missing: {agent}")
        # Curator is retired
        self.assertFalse((self.tmp / ".claude" / "agents" / "aiwf-curator.md").exists(),
                        "aiwf-curator should not be installed")

    def test_claude_prompts_do_not_inject_interruption_protocol(self):
        for agent in ["aiwf-executor", "aiwf-tester", "aiwf-reviewer", "aiwf-architect"]:
            content = (self.tmp / ".claude" / "agents" / f"{agent}.md").read_text()
            self.assertNotIn("Connection Recovery", content)
            self.assertNotIn("PAUSED_FOR_PLANNER", content)
        planner = (self.tmp / ".claude" / "skills" / "aiwf-planner" / "SKILL.md").read_text()
        self.assertNotIn("Connection Recovery", planner)
        self.assertNotIn("PAUSED_FOR_PLANNER", planner)

    def test_planner_and_reviewer_explain_governance_recovery_paths(self):
        planner = (self.tmp / ".claude" / "skills" / "aiwf-planner" / "SKILL.md").read_text()
        reviewer = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        executor = (self.tmp / ".claude" / "agents" / "aiwf-executor.md").read_text()
        self.assertIn("do not edit project source files", planner.lower())
        self.assertIn("do not hand-edit `.aiwf/state/`", planner.lower())
        self.assertIn("record implementation", executor.lower())

    def test_status_shows_embedded_mode(self):
        r = _run([sys.executable, "-m", "aiwf_core.cli", "status"], self.tmp)
        self.assertIn("AIWF V1.0 - Claude Code", r.stdout)
        self.assertIn("Active Tasks:", r.stdout)

    def test_claude_md_exists(self):
        self.assertTrue((self.tmp / "CLAUDE.md").exists())

    def test_scripts_are_executable(self):
        for s in ["aiwf_status.py", "aiwf_scope_check.py", "aiwf_bash_guard.py",
                  "aiwf_review_gate.py", "aiwf_skill_log.py", "aiwf_agent_log.py",
                  "aiwf_agent_gate.py", "aiwf_auto_sync.py"]:
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
        """Generated CLAUDE.md is a slim constitution — starts with aiwf status --prompt."""
        content = (self.tmp / "CLAUDE.md").read_text()
        self.assertIn("aiwf status", content)
        self.assertNotIn("aiwf-init", content)
        self.assertIn("routing source of truth", content)
        self.assertIn("Use AIWF assets first", content)
        self.assertIn("Do not hand-edit `.aiwf/state/`", content)

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

    def test_install_output_lists_each_created_path_once(self):
        result = _run(
            [sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
            self.tmp,
        )

        created = [
            line.strip()[2:]
            for line in result.stdout.splitlines()
            if line.strip().startswith("+ ")
        ]
        self.assertEqual(created.count(".aiwf/README.md"), 1)
        self.assertEqual(len(created), len(set(created)))

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

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awin_reasonix_"))
        cls.result = _run([sys.executable, "-m", "aiwf_core.cli", "install", "reasonix", "--force"],
                          cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

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
        # This test modifies install state — needs isolated tmpdir
        tmp = Path(tempfile.mkdtemp(prefix="awin_ri_legacy_"))
        try:
            _run([sys.executable, "-m", "aiwf_core.cli", "install", "reasonix", "--force"], tmp)
            agents = tmp / ".reasonix" / "agents"
            agents.mkdir(parents=True, exist_ok=True)
            (agents / "aiwf-executor.md").write_text("legacy duplicate")
            result = _run([sys.executable, "-m", "aiwf_core.cli", "install", "reasonix", "--force"], tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((agents / "aiwf-executor.md").exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_reasonix_install_output_starts_with_status(self):
        self.assertIn("reasonix", self.result.stdout)
        self.assertIn("aiwf status --prompt", self.result.stdout)
        self.assertIn("Describe the goal or question", self.result.stdout)

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
        pre_matches = [entry.get("match", "") for entry in settings["hooks"]["PreToolUse"]]
        post_matches = [entry.get("match", "") for entry in settings["hooks"]["PostToolUse"]]
        self.assertTrue(any("agent" in m and "task" in m for m in pre_matches))
        self.assertTrue(any("agent" in m and "task" in m for m in post_matches))
        self.assertTrue(commands)
        self.assertTrue(all("AIWF_HOOK_ENGINE=reasonix" in c and "REASONIX_PROJECT_DIR}/scripts/" in c for c in commands))

    def test_reinstall_preserves_custom_reasonix_hooks(self):
        tmp = Path(tempfile.mkdtemp(prefix="awhooks_reasonix_"))
        try:
            settings_path = tmp / ".reasonix" / "settings.json"
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            settings_path.write_text(json.dumps({
                "hooks": {
                    "PreToolUse": [
                        {"command": "./custom-reasonix-hook.sh", "match": "^bash$"},
                        {"command": "${REASONIX_PROJECT_DIR}/scripts/aiwf_old.py", "match": "^bash$"},
                    ],
                    "SessionEnd": [{"command": "./custom-reasonix-session-hook.sh"}],
                    "Notification": [{"command": "${REASONIX_PROJECT_DIR}/scripts/aiwf_retired.py"}],
                },
                "customSetting": "keep-me",
            }), encoding="utf-8")

            for _ in range(2):
                result = _run(
                    [sys.executable, "-m", "aiwf_core.cli", "install", "reasonix", "--force"],
                    tmp,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

            installed = json.loads(settings_path.read_text(encoding="utf-8"))
            commands = [
                entry.get("command", "")
                for entries in installed["hooks"].values()
                for entry in entries
                if isinstance(entry, dict)
            ]
            self.assertIn("./custom-reasonix-hook.sh", commands)
            self.assertIn("./custom-reasonix-session-hook.sh", commands)
            self.assertFalse(any("aiwf_old.py" in command for command in commands))
            self.assertEqual(sum("aiwf_scope_check.py" in command for command in commands), 1)
            self.assertEqual(sum("aiwf_status.py" in command for command in commands), 1)
            self.assertEqual(installed["customSetting"], "keep-me")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_reasonix_subagent_skills_have_no_hard_budget_or_interruption_protocol(self):
        for skill in ["aiwf-implement", "aiwf-test", "aiwf-review", "aiwf-architect"]:
            content = (self.tmp / ".reasonix" / "skills" / skill / "SKILL.md").read_text()
            self.assertIn("runAs: subagent", content)
            self.assertNotIn("max-iters:", content)
            self.assertNotIn("runaway loops", content)
            self.assertNotIn("Do not retry the same command", content)
            self.assertNotIn("Connection Recovery", content)
            self.assertNotIn("PAUSED_FOR_PLANNER", content)
        planner = (self.tmp / ".reasonix" / "skills" / "aiwf-planner" / "SKILL.md").read_text()
        self.assertIn("runAs: inline", planner)
        self.assertNotIn("PAUSED_FOR_PLANNER", planner)

    def test_reasonix_planner_prompt_contains_lifecycle(self):
        # Lifecycle reference contains the compact task lifecycle orientation.
        lifecycle = (self.tmp / ".reasonix" / "skills" / "aiwf-planner" / "references" / "lifecycle.md").read_text()
        for phrase in [
            "task create",
            "task critique",
            "task activate",
            "records the implementation snapshot",
            "records the tested snapshot",
            "records review",
            "task close",
        ]:
            self.assertIn(phrase, lifecycle)
        self.assertIn("Planner", lifecycle)

        # REASONIX.md carries the constitution — platform-neutral hard boundaries.
        reasonix_md = (self.tmp / "REASONIX.md").read_text()
        self.assertIn("routing source of truth", reasonix_md)
        self.assertIn("Hard Rules", reasonix_md)

        # Planner-main provides the core workflow orchestrator guidance.
        planner = (self.tmp / ".reasonix" / "skills" / "aiwf-planner" / "SKILL.md").read_text()
        self.assertIn("aiwf status", planner.lower())

        # aiwf-init is retired; check planner SKILL.md is the primary planning entry
        self.assertIn("AIWF Planner", planner)

    def test_connection_recovery_partials_are_removed(self):
        shared = PROJECT_ROOT / "aiwf_core" / "embedded_templates" / "shared"
        self.assertFalse((shared / "connection_recovery_planner.md").exists())
        self.assertFalse((shared / "connection_recovery_test.md").exists())
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
            self.assertNotIn("PAUSED_FOR_PLANNER", path.read_text())

    def test_reasonix_hook_payload_blocks_by_exit_code(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        env["AIWF_HOOK_ENGINE"] = "reasonix"

        state = self._j(".aiwf/state/state.json")
        state["active_context_id"] = "CTX-001"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps({
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
        self.assertIn("AIWF V1.0 - Reasonix", status.stdout)

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
